"""Juge visuel local basé sur CLIP (zero-shot image-texte).

Deux usages éprouvés :
    * `identify(image, labels)` — classe une image parmi des étiquettes texte
      (« qu'est-ce que c'est ? »), à la manière d'un classifieur zero-shot.
    * `best_of(images, prompt)` — choisit, parmi plusieurs variantes, l'image
      la plus proche d'un prompt (« laquelle est la meilleure ? »).

Sous le capot : CLIP (`openai/clip-vit-base-patch32`) via `transformers`. On
calcule des similarités image-texte (cosinus des embeddings projetés) ; pour
`identify` on renvoie en plus une distribution softmax interprétable comme des
probabilités.

Tous les imports lourds (torch, transformers) sont PARESSEUX : faits dans les
fonctions, jamais au niveau module. Ainsi `import studio.judge` reste gratuit et
ne casse pas si CLIP n'est pas installé. Le modèle est chargé une seule fois puis
mis en cache sur une variable de module.

Coût : le tout premier `score`/`identify`/`best_of` déclenche le téléchargement
du modèle (~600 Mo) depuis le Hub Hugging Face, puis son chargement en mémoire
(quelques secondes). Les appels suivants réutilisent le cache disque + RAM/VRAM.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

# Modèle CLIP par défaut : petit, rapide, largement éprouvé en zero-shot.
DEFAULT_MODEL = "openai/clip-vit-base-patch32"

# Cache module-level : (model, processor, device). Chargé une seule fois.
# Clé = nom du modèle, pour autoriser plusieurs modèles sans collision.
_CACHE: dict[str, tuple] = {}


def clip_available() -> tuple[bool, str]:
    """Indique si CLIP est utilisable, SANS rien télécharger.

    On se contente de vérifier que `torch` et `transformers` sont importables.
    Renvoie (True, "ok") si tout est là, sinon (False, message explicite).
    """
    try:
        import torch  # noqa: F401
    except ImportError:
        return False, "paquet 'torch' non installé (pip install torch)"
    try:
        import transformers  # noqa: F401
    except ImportError:
        return False, "paquet 'transformers' non installé (pip install transformers)"
    return True, "ok"


def _load(model_name: str = DEFAULT_MODEL):
    """Charge (et met en cache) le modèle CLIP et son processeur.

    Premier appel : télécharge le modèle si absent du cache disque, puis le
    charge sur GPU si disponible, sinon CPU. Appels suivants : renvoie le cache.
    Lève RuntimeError avec un message clair si CLIP n'est pas disponible.
    """
    cached = _CACHE.get(model_name)
    if cached is not None:
        return cached

    ok, reason = clip_available()
    if not ok:
        raise RuntimeError(f"CLIP indisponible : {reason}")

    # Imports lourds différés ici, après le garde-fou clip_available().
    import torch
    from transformers import CLIPModel, CLIPProcessor

    try:
        model = CLIPModel.from_pretrained(model_name)
        processor = CLIPProcessor.from_pretrained(model_name)
    except Exception as exc:  # téléchargement échoué, modèle inconnu, hors-ligne…
        raise RuntimeError(
            f"Impossible de charger le modèle CLIP '{model_name}' : {exc}. "
            "Vérifie la connexion réseau (1er téléchargement ~600 Mo) ou le cache "
            "Hugging Face."
        ) from exc

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    model.eval()  # pas d'entraînement : mode évaluation.

    entry = (model, processor, device)
    _CACHE[model_name] = entry
    return entry


def _open_image(image_path):
    """Ouvre une image en RGB via PIL.

    PIL gère nativement les chemins avec espaces/accents (on passe par un objet
    Path puis sa forme str). Convertit en RGB pour rester compatible CLIP.
    """
    from PIL import Image

    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(f"Image introuvable : {p}")
    return Image.open(p).convert("RGB")


def _logits_image_vs_texts(image, texts: list[str], model_name: str):
    """Calcule les logits image↔textes bruts de CLIP (par lot de textes).

    Renvoie un tenseur 1-D (un score par texte), sur CPU pour exploitation aisée.
    Mutualise l'inférence pour `score`, `identify` et `best_of`.
    """
    import torch

    model, processor, device = _load(model_name)
    inputs = processor(
        text=texts,
        images=image,
        return_tensors="pt",
        padding=True,
    ).to(device)

    with torch.no_grad():
        outputs = model(**inputs)
    # logits_per_image : (n_images=1, n_texts). On aplatit en (n_texts,).
    return outputs.logits_per_image[0].detach().cpu()


def score(image_path, text: str, model_name: str = DEFAULT_MODEL) -> float:
    """Similarité CLIP brute entre une image et un texte (plus haut = plus proche).

    C'est le logit image-texte de CLIP (cosinus mis à l'échelle par la
    température apprise). Comparable entre textes pour UNE même image ; non borné.
    """
    image = _open_image(image_path)
    logit = _logits_image_vs_texts(image, [text], model_name)
    return float(logit[0])


def identify(
    image_path,
    labels: list[str],
    top_k: int = 3,
    model_name: str = DEFAULT_MODEL,
) -> list[tuple[str, float]]:
    """Classement zero-shot d'une image parmi `labels`.

    Renvoie les `top_k` meilleures paires (label, probabilité) triées par score
    décroissant. Les probabilités sont un softmax des logits CLIP sur l'ensemble
    des labels (elles somment à 1), donc interprétables et comparables entre eux.
    """
    if not labels:
        raise ValueError("`labels` ne doit pas être vide.")

    import torch

    image = _open_image(image_path)
    logits = _logits_image_vs_texts(image, list(labels), model_name)
    probs = torch.softmax(logits, dim=0)

    pairs = [(label, float(p)) for label, p in zip(labels, probs)]
    pairs.sort(key=lambda lp: lp[1], reverse=True)
    return pairs[: max(1, top_k)]


def best_of(
    image_paths,
    prompt: str,
    model_name: str = DEFAULT_MODEL,
) -> tuple[Optional[object], dict]:
    """Choisit l'image la plus proche de `prompt` parmi plusieurs variantes.

    Renvoie (meilleur_chemin, scores) où `scores` mappe chaque chemin (en str)
    vers sa similarité CLIP au prompt. Si la liste est vide, renvoie (None, {}).
    """
    paths = list(image_paths)
    if not paths:
        return None, {}

    scores: dict[str, float] = {}
    for p in paths:
        # On score chaque image séparément : même prompt, donc les logits sont
        # directement comparables d'une image à l'autre.
        scores[str(p)] = score(p, prompt, model_name)

    best_path = max(paths, key=lambda p: scores[str(p)])
    return best_path, scores

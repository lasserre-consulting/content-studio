"""Post-traitement d'images : détourage (fond transparent), recadrage.

Le détourage tourne en LOCAL via rembg (modèle U²-Net, CPU) : plus besoin de
passer par remove.bg à la main pour obtenir des sprites transparents prêts pour
Godot. Comme pour les providers, l'import lourd est fait à l'usage et une
session rembg est mise en cache (sa création est coûteuse).
"""
from __future__ import annotations

from pathlib import Path

# Modèle de détourage par défaut. birefnet-general donne des bords nettement
# plus propres que u2net sur des personnages/sprites (résolution interne 1024).
# Téléchargé automatiquement au premier appel (poids ouverts, gratuit).
DEFAULT_MODEL = "birefnet-general"

# Sessions rembg réutilisées entre appels, indexées par modèle (création coûteuse).
_sessions: dict[str, object] = {}


def rembg_available() -> tuple[bool, str]:
    """(ok, raison) — le détourage local est-il possible ?"""
    try:
        import rembg  # noqa: F401
    except ImportError:
        return False, "paquet 'rembg' non installé (pip install rembg onnxruntime)"
    return True, "ok"


def _get_session(model: str):
    if model not in _sessions:
        from rembg import new_session

        _sessions[model] = new_session(model)
    return _sessions[model]


def remove_background(
    src: Path | str,
    dest: Path | str | None = None,
    *,
    autocrop: bool = True,
    suffix: str = "",
    model: str = DEFAULT_MODEL,
    alpha_matting: bool = True,
) -> Path:
    """Détoure une image → PNG à fond transparent.

    dest None : écrit à côté de la source (même nom + `suffix`, extension .png).
    autocrop : rogne les marges transparentes pour un sprite serré (meilleur pour
    le placement et les collisions dans Godot).
    alpha_matting : affine les bords (cheveux, contours fins) — un peu plus lent
    mais nettement plus propre ; post_process_mask nettoie les artefacts de masque.
    """
    from PIL import Image
    from rembg import remove

    src = Path(src)
    if dest is None:
        dest = src.with_name(f"{src.stem}{suffix}.png")
    dest = Path(dest)

    with Image.open(src) as im:
        cutout = remove(
            im.convert("RGBA"),
            session=_get_session(model),
            alpha_matting=alpha_matting,
            post_process_mask=True,
        )

    if autocrop:
        bbox = cutout.getbbox()  # boîte englobante des pixels non transparents
        if bbox:
            cutout = cutout.crop(bbox)

    dest.parent.mkdir(parents=True, exist_ok=True)
    cutout.save(dest)
    return dest

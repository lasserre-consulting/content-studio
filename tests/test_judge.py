"""Tests du juge visuel CLIP (studio.judge).

Deux niveaux :
    * structure de `clip_available()` — toujours exécuté, ne télécharge rien.
    * un test fonctionnel `identify()` sur des images synthétiques — exécuté
      seulement si CLIP est utilisable ET déjà en cache disque, pour ne pas
      déclencher un téléchargement de ~600 Mo dans une CI/run normal.
"""
from __future__ import annotations

import pytest
from PIL import Image

from studio.judge import DEFAULT_MODEL, best_of, clip_available, identify, score


# --------------------------------------------------------------------------- #
# clip_available() : structure (sans téléchargement)                           #
# --------------------------------------------------------------------------- #
def test_clip_available_structure():
    ok, reason = clip_available()
    assert isinstance(ok, bool)
    assert isinstance(reason, str) and reason  # message non vide
    # Cohérence : si dispo -> "ok", sinon le message cite le paquet manquant.
    if ok:
        assert reason == "ok"
    else:
        assert "torch" in reason or "transformers" in reason


# --------------------------------------------------------------------------- #
# Garde : ne lance le test lourd que si CLIP est dispo ET le modèle en cache.   #
# --------------------------------------------------------------------------- #
def _model_in_cache(model_name: str = DEFAULT_MODEL) -> bool:
    """Vrai si le modèle CLIP est déjà téléchargé localement (pas de réseau)."""
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return False
    # CLIP base-patch32 est distribué en safetensors (et historiquement .bin).
    for fname in ("model.safetensors", "pytorch_model.bin"):
        if isinstance(try_to_load_from_cache(model_name, fname), str):
            return True
    return False


def _make_square(color: tuple[int, int, int], path) -> str:
    """Génère un PNG carré uni de la couleur donnée et renvoie son chemin str."""
    img = Image.new("RGB", (128, 128), color)
    img.save(path)
    return str(path)


# --------------------------------------------------------------------------- #
# Test fonctionnel : un carré rouge doit être identifié "red", pas "blue".      #
# --------------------------------------------------------------------------- #
def test_identify_red_vs_blue(tmp_path):
    ok, reason = clip_available()
    if not ok:
        pytest.skip(f"CLIP indisponible : {reason}")
    if not _model_in_cache():
        pytest.skip(
            "Modèle CLIP non présent en cache (1er run = téléchargement ~600 Mo). "
            "Lance une fois `identify` manuellement pour le mettre en cache."
        )

    red = _make_square((255, 0, 0), tmp_path / "rouge.png")
    blue = _make_square((0, 0, 255), tmp_path / "bleu.png")
    labels = ["a red square", "a blue square"]

    # identify : "red" doit arriver en tête pour l'image rouge.
    ranking = identify(red, labels)
    assert ranking, "identify ne doit pas renvoyer une liste vide"
    assert ranking[0][0] == "a red square"
    # Les scores sont des probabilités softmax : la 1re domine la 2nde.
    assert ranking[0][1] >= ranking[-1][1]

    # best_of : entre rouge et bleu, le prompt "a red square" doit choisir le rouge.
    best, scores = best_of([red, blue], "a red square")
    assert best == red
    assert set(scores) == {red, blue}
    assert scores[red] > scores[blue]

    # score : cohérent avec best_of (rouge plus proche du prompt rouge).
    assert score(red, "a red square") > score(blue, "a red square")


# --------------------------------------------------------------------------- #
# best_of : cas dégénéré (liste vide) sans charger le modèle.                   #
# --------------------------------------------------------------------------- #
def test_best_of_empty_returns_none():
    best, scores = best_of([], "n'importe quoi")
    assert best is None
    assert scores == {}

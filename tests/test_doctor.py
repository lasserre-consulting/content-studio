"""Tests du preflight `studio.doctor`.

On vérifie la STRUCTURE, pas l'état réel des paquets : ces tests doivent passer
au vert quelle que soit la machine (avec ou sans torch/CUDA/audiocraft installés).
On contrôle donc que `check()` renvoie bien une liste de Check, qu'il ne lève
jamais, et que les noms de checks attendus sont présents.
"""
from __future__ import annotations

from studio import doctor
from studio.doctor import Check, check


# Noms (sous-chaînes) attendus dans le rapport. On compare en sous-chaîne pour
# ne pas se lier aux libellés exacts (ex. "rembg + onnxruntime").
EXPECTED = [
    "Python",
    "torch",
    "torchvision",
    "diffusers",
    "rembg",
    "onnxruntime",
    "ffmpeg",
    "audiocraft",
    "xformers",
    "scikit-learn",
    "PIL",
    "numpy",
    "soundfile",
]


def test_check_returns_list_of_check():
    """check() renvoie une liste non vide de Check bien typés."""
    results = check()
    assert isinstance(results, list)
    assert len(results) > 0
    for c in results:
        assert isinstance(c, Check)


def test_check_fields_have_right_types():
    """Chaque Check expose les bons champs avec les bons types."""
    for c in check():
        assert isinstance(c.name, str) and c.name
        assert isinstance(c.ok, bool)
        assert isinstance(c.detail, str)
        assert isinstance(c.fix_hint, str)
        assert isinstance(c.critical, bool)


def test_failed_checks_provide_fix_hint():
    """Un check en échec doit toujours proposer une piste de réparation."""
    for c in check():
        if not c.ok:
            assert c.fix_hint, f"check '{c.name}' échoué sans fix_hint"


def test_expected_check_names_present():
    """Tous les checks attendus de la recette sont couverts."""
    blob = " | ".join(c.name for c in check())
    for name in EXPECTED:
        assert name in blob, f"check manquant : {name}"


def test_check_never_raises():
    """check() est totalement tolérant : aucune exception ne remonte."""
    try:
        check()
    except BaseException as e:  # noqa: BLE001
        raise AssertionError(f"check() a levé : {e!r}")


def test_critical_checks_declared():
    """Au moins torch et PIL sont marqués critiques (pilotent l'exit code)."""
    by_name = {c.name: c for c in check()}
    assert by_name["torch"].critical is True
    pil = next(c for c in check() if c.name.startswith("PIL"))
    assert pil.critical is True


def test_main_returns_int_exit_code():
    """La CLI renvoie un code de sortie entier (0 ou 1) sans lever."""
    rc = doctor.main()
    assert rc in (0, 1)

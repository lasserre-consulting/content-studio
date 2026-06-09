"""Tests des helpers de robustesse de chemins (studio.assembly.paths)."""
from __future__ import annotations

from pathlib import Path

from studio.assembly.paths import ascii_workspace, is_ascii_safe, to_ascii_slug


# -- is_ascii_safe ------------------------------------------------------------

def test_is_ascii_safe_chemin_propre():
    assert is_ascii_safe("/tmp/projet/asset.png") is True
    assert is_ascii_safe(Path("relatif/sous_dossier/x.txt")) is True


def test_is_ascii_safe_detecte_espace():
    assert is_ascii_safe(r"C:\Program Files (x86)\tool\x.exe") is False


def test_is_ascii_safe_detecte_accent():
    assert is_ascii_safe("le repère des sorcières/sprite.png") is False
    assert is_ascii_safe("café.png") is False


# -- to_ascii_slug ------------------------------------------------------------

def test_to_ascii_slug_accents_et_espaces():
    assert to_ascii_slug("le repère") == "le_repere"


def test_to_ascii_slug_preserve_extension():
    assert to_ascii_slug("sorcières & co.PNG") == "sorcieres_co.PNG"


def test_to_ascii_slug_vide_donne_fallback():
    assert to_ascii_slug("é") == "e"
    assert to_ascii_slug("!!!") == "fichier"


# -- ascii_workspace ----------------------------------------------------------

def test_ascii_workspace_stage_et_recopie(tmp_path):
    # Entrée sous un dossier avec espaces ET accents.
    src_dir = tmp_path / "le repère des sorcières"
    src_dir.mkdir()
    src = src_dir / "sprite goblin.png"
    src.write_bytes(b"PIXELS")

    # Destination finale avec accents.
    out_dir = tmp_path / "sortie générée"

    with ascii_workspace([src], out_dir=out_dir) as ws:
        # Les entrées stagées sont ASCII-safe et lisibles.
        assert len(ws.inputs) == 1
        staged = ws.inputs[0]
        assert is_ascii_safe(staged) is True
        assert staged.read_bytes() == b"PIXELS"
        # Le dossier de sortie de travail est ASCII-safe.
        assert is_ascii_safe(ws.out) is True

        # Simulate un outil tiers qui écrit un livrable dans ws.out.
        (ws.out / "result.png").write_bytes(b"DONE")

    # À la sortie : le livrable est recopié dans out_dir (chemin avec accents).
    produced = out_dir / "result.png"
    assert produced.exists()
    assert produced.read_bytes() == b"DONE"


def test_ascii_workspace_nettoie_le_temp(tmp_path):
    src = tmp_path / "café.txt"
    src.write_text("x", encoding="utf-8")
    out_dir = tmp_path / "out"

    with ascii_workspace([src], out_dir=out_dir) as ws:
        tmp_used = ws.inputs[0].parent.parent  # racine du tmpdir
        assert tmp_used.exists()

    # Le dossier temporaire a été nettoyé.
    assert not tmp_used.exists()


def test_ascii_workspace_evite_collisions(tmp_path):
    d = tmp_path / "dossier accentué"
    d.mkdir()
    # Deux noms qui slugifient à l'identique.
    a = d / "café.txt"
    b = d / "cafe.txt"
    a.write_text("A", encoding="utf-8")
    b.write_text("B", encoding="utf-8")
    out_dir = tmp_path / "out"

    with ascii_workspace([a, b], out_dir=out_dir) as ws:
        names = {p.name for p in ws.inputs}
        assert len(names) == 2  # pas d'écrasement

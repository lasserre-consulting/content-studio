"""Tests de la couche EXPORTERS.

Aucun moteur réel, aucun réseau : on travaille dans des tmp dirs avec des
fichiers factices. On vérifie surtout le ROUTAGE DES CHEMINS et le NOMMAGE. La
conversion ffmpeg (WAV->OGG) est testée seulement si le binaire est présent ;
sinon on se contente de vérifier le chemin de sortie via une source .ogg
factice (pas d'encodage requis) + un test du message d'erreur quand ffmpeg
manque.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from studio.assembly.ffmpeg import ffmpeg_bin
from studio.exporters import (
    GODOT_PROFILE,
    MEMORIA_PROFILE,
    GodotExporter,
    MemoriaExporter,
    canonical_sfx_name,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #
def _fake(path: Path, data: bytes = b"FAKE") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# --------------------------------------------------------------------------- #
# EngineProfile : garde-fous                                                    #
# --------------------------------------------------------------------------- #
def test_profile_valid_kinds():
    assert MEMORIA_PROFILE.is_valid_kind("bgm")
    assert MEMORIA_PROFILE.is_valid_kind("model_texture")
    assert not MEMORIA_PROFILE.is_valid_kind("sprite")  # persos FF9 = 3D
    assert GODOT_PROFILE.is_valid_kind("sprite")


def test_profile_audio_format():
    assert MEMORIA_PROFILE.audio_format("bgm") == "ogg"
    assert MEMORIA_PROFILE.audio_format("model_texture") is None
    assert GODOT_PROFILE.audio_format("audio") in {"ogg", "wav"}


def test_profile_check_rejects_unknown_kind():
    with pytest.raises(ValueError, match="n'est pas un asset valide"):
        MEMORIA_PROFILE.check("spritesheet")


def test_profile_check_rejects_wrong_representation():
    # Le piège vécu : pousser une spritesheet 2D vers un asset qui veut des
    # textures de modèle 3D doit être refusé.
    with pytest.raises(ValueError, match="attend"):
        MEMORIA_PROFILE.check("model_texture", representation="2D spritesheet")
    # La bonne représentation passe.
    MEMORIA_PROFILE.check("model_texture", representation="3D model textures")


def test_kind_spec_unknown_raises_keyerror():
    with pytest.raises(KeyError):
        MEMORIA_PROFILE.kind_spec("inexistant")


# --------------------------------------------------------------------------- #
# Nommage canonique SFX                                                         #
# --------------------------------------------------------------------------- #
def test_canonical_sfx_name():
    assert canonical_sfx_name("Coup d'Épée !") == "coup_d_epee"
    assert canonical_sfx_name("Impact  Lourd") == "impact_lourd"
    assert canonical_sfx_name("boom.wav") == "boom"
    assert canonical_sfx_name("") == "sfx"


# --------------------------------------------------------------------------- #
# MemoriaExporter : routage de chemins (sans encodage)                          #
# --------------------------------------------------------------------------- #
def test_memoria_audio_path_from_ogg_source(tmp_path):
    # Source déjà en .ogg -> simple copie, pas besoin de ffmpeg : on teste le
    # chemin canonique de sortie.
    src = _fake(tmp_path / "src" / "Theme Combat.ogg")
    exp = MemoriaExporter(tmp_path / "mod")
    out = exp.export(src, "bgm", "Thème de Combat")
    expected = (
        tmp_path / "mod" / "StreamingAssets" / "Assets" / "Audio" / "BGM"
        / "theme_de_combat.ogg"
    )
    assert out == expected
    assert out.exists()


def test_memoria_sfx_path_and_naming(tmp_path):
    src = _fake(tmp_path / "boom.ogg")
    exp = MemoriaExporter(tmp_path / "mod")
    out = exp.export(src, "sfx", "Explosion Énorme !")
    assert out.parent.as_posix().endswith("StreamingAssets/Assets/Audio/SFX")
    assert out.name == "explosion_enorme.ogg"


def test_memoria_generic_audio_path(tmp_path):
    src = _fake(tmp_path / "amb.ogg")
    exp = MemoriaExporter(tmp_path / "mod")
    out = exp.export(src, "audio", "Ambiance Crypte")
    # Pas de sous-dossier BGM/SFX pour 'audio'.
    assert out.parent.as_posix().endswith("StreamingAssets/Assets/Audio")
    assert out.name == "ambiance_crypte.ogg"


def test_memoria_model_texture_override_path(tmp_path):
    src = _fake(tmp_path / "skin.png")
    exp = MemoriaExporter(tmp_path / "mod")
    out = exp.export_model_texture(src, group="MAIN", model_id="GEO_MAIN_B0_ZDN", index=2)
    expected = (
        tmp_path / "mod" / "StreamingAssets" / "Assets" / "Resources" / "Models"
        / "MAIN" / "GEO_MAIN_B0_ZDN" / "GEO_MAIN_B0_ZDN_2.png"
    )
    assert out == expected
    assert out.exists()


def test_memoria_export_rejects_invalid_kind(tmp_path):
    src = _fake(tmp_path / "x.png")
    exp = MemoriaExporter(tmp_path / "mod")
    with pytest.raises(ValueError):
        exp.export(src, "sprite", "perso")  # sprite invalide pour Memoria


def test_memoria_no_hardcoded_path_uses_given_root(tmp_path):
    # Le chemin de sortie est entièrement sous la racine fournie (pas de Steam).
    src = _fake(tmp_path / "s.ogg")
    root = tmp_path / "un" / "chemin" / "quelconque"
    out = MemoriaExporter(root).export(src, "sfx", "ping")
    assert str(out).startswith(str(root))


@pytest.mark.skipif(ffmpeg_bin() is None, reason="ffmpeg absent : encodage non testé")
def test_memoria_wav_to_ogg_encodes(tmp_path):
    # Génère un vrai WAV silencieux via ffmpeg puis vérifie la conversion OGG.
    import subprocess

    wav = tmp_path / "tone.wav"
    subprocess.run(
        [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1", str(wav)],
        check=True,
    )
    exp = MemoriaExporter(tmp_path / "mod")
    out = exp.export(wav, "sfx", "Tone Test")
    assert out.suffix == ".ogg"
    assert out.exists() and out.stat().st_size > 0


def test_memoria_wav_without_ffmpeg_raises(tmp_path, monkeypatch):
    # Si ffmpeg est introuvable, la conversion WAV->OGG lève une erreur claire,
    # mais le ROUTAGE jusqu'à l'appel d'encodage est bien exercé.
    import studio.assembly.ffmpeg as ff

    monkeypatch.setattr(ff, "ffmpeg_bin", lambda: None)
    src = _fake(tmp_path / "raw.wav")
    exp = MemoriaExporter(tmp_path / "mod")
    with pytest.raises(ff.FFmpegUnavailable):
        exp.export(src, "sfx", "raw")


# --------------------------------------------------------------------------- #
# GodotExporter                                                                 #
# --------------------------------------------------------------------------- #
def test_godot_sprite_path_and_slug(tmp_path):
    src = _fake(tmp_path / "morra.png")
    exp = GodotExporter(tmp_path / "proj")
    out = exp.export(src, "sprite", "Vieille Sorcière Morra")
    expected = tmp_path / "proj" / "assets" / "sprites" / "vieille-sorciere-morra.png"
    assert out == expected
    assert out.exists()


def test_godot_sprite_with_category(tmp_path):
    src = _fake(tmp_path / "g.png")
    exp = GodotExporter(tmp_path / "proj")
    out = exp.export(src, "sprite", "Gobelin", category="Ennemis")
    assert out.parent.as_posix().endswith("assets/sprites/ennemis")
    assert out.name == "gobelin.png"


def test_godot_audio_keeps_supported_ext(tmp_path):
    for ext in ("ogg", "wav"):
        src = _fake(tmp_path / f"snd.{ext}")
        exp = GodotExporter(tmp_path / f"proj_{ext}")
        out = exp.export(src, "audio", "Saut", category=None)
        assert out.name == f"saut.{ext}"
        assert out.parent.as_posix().endswith("assets/audio")


def test_godot_audio_rejects_unsupported_ext(tmp_path):
    src = _fake(tmp_path / "voice.flac")
    exp = GodotExporter(tmp_path / "proj")
    with pytest.raises(ValueError, match="non supporté"):
        exp.export(src, "audio", "voix")


def test_godot_export_rejects_invalid_kind(tmp_path):
    src = _fake(tmp_path / "x.png")
    exp = GodotExporter(tmp_path / "proj")
    with pytest.raises(ValueError):
        exp.export(src, "model_texture", "perso")  # n'existe pas côté Godot

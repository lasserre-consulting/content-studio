"""Tests de l'exporter Unity.

Aucun Unity requis : on vérifie l'arborescence produite, le nommage, les
garde-fous de format et l'idempotence du postprocessor. Tout se joue dans un
tmp_path.
"""
from __future__ import annotations

import re

import pytest

from studio.exporters import UNITY_PROFILE, UnityExporter


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
@pytest.fixture
def png(tmp_path):
    p = tmp_path / "source.png"
    # En-tête PNG minimal : le contenu n'est jamais lu, seule l'extension compte.
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    return p


@pytest.fixture
def wav(tmp_path):
    p = tmp_path / "source.wav"
    p.write_bytes(b"RIFF" + b"\x00" * 40)
    return p


@pytest.fixture
def projet(tmp_path):
    return tmp_path / "MonJeuUnity"


# --------------------------------------------------------------------------- #
# Profil                                                                       #
# --------------------------------------------------------------------------- #
def test_profil_declare_les_quatre_types():
    assert UNITY_PROFILE.name == "unity"
    assert set(UNITY_PROFILE.kinds) == {"sprite", "music", "sfx", "voice"}


def test_profil_refuse_un_type_inconnu():
    with pytest.raises(ValueError, match="n'est pas un asset valide"):
        UNITY_PROFILE.check("spritesheet")


def test_music_et_sfx_ont_des_representations_distinctes():
    """Garde-fou : c'est cette distinction qui pilote les réglages d'import
    (streaming pour la musique, decompress-on-load pour les SFX)."""
    assert "stream" in UNITY_PROFILE.kinds["music"].representation
    assert "decompress" in UNITY_PROFILE.kinds["sfx"].representation


# --------------------------------------------------------------------------- #
# Sprites                                                                      #
# --------------------------------------------------------------------------- #
def test_sprite_atterrit_dans_assets_art_sprites(projet, png):
    dest = UnityExporter(projet).export_sprite(png, "Goblin Presseur")
    assert dest == projet / "Assets" / "Art" / "Sprites" / "goblin-presseur.png"
    assert dest.exists()


def test_sprite_avec_categorie(projet, png):
    dest = UnityExporter(projet).export_sprite(png, "Morra", category="Ennemis")
    assert dest == projet / "Assets" / "Art" / "Sprites" / "ennemis" / "morra.png"


def test_sprite_slugifie_les_accents(projet, png):
    """Les noms accentués doivent devenir ASCII : Unity et git s'en portent mieux."""
    dest = UnityExporter(projet).export_sprite(png, "Sorcière Éveillée")
    assert dest.name == "sorciere-eveillee.png"


def test_sprite_refuse_autre_chose_que_png(projet, wav):
    with pytest.raises(ValueError, match="sprite attendu en .png"):
        UnityExporter(projet).export_sprite(wav, "test")


# --------------------------------------------------------------------------- #
# Audio                                                                        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "kind, sous_dossier",
    [("music", "Music"), ("sfx", "SFX"), ("voice", "Voice")],
)
def test_audio_atterrit_dans_le_bon_sous_dossier(projet, wav, kind, sous_dossier):
    dest = UnityExporter(projet).export_audio(wav, kind, "Theme Boss")
    assert dest == projet / "Assets" / "Audio" / sous_dossier / "theme-boss.wav"
    assert dest.exists()


def test_audio_conserve_le_wav(projet, wav):
    """Contrairement à Godot/Memoria, PAS de conversion en OGG : le WAV est la
    source et la compression est un réglage d'import Unity."""
    dest = UnityExporter(projet).export_audio(wav, "sfx", "potion")
    assert dest.suffix == ".wav"


def test_audio_refuse_un_format_inconnu(projet, tmp_path):
    flac = tmp_path / "x.flac"
    flac.write_bytes(b"fLaC")
    with pytest.raises(ValueError, match="format audio non supporté"):
        UnityExporter(projet).export_audio(flac, "sfx", "test")


def test_audio_refuse_un_type_inconnu(projet, wav):
    with pytest.raises(ValueError, match="type audio inconnu"):
        UnityExporter(projet).export_audio(wav, "ambiance", "test")


# --------------------------------------------------------------------------- #
# Routage générique                                                            #
# --------------------------------------------------------------------------- #
def test_export_route_selon_le_kind(projet, png, wav):
    exp = UnityExporter(projet)
    assert exp.export(png, "sprite", "a").parent.name == "Sprites"
    assert exp.export(wav, "music", "b").parent.name == "Music"
    assert exp.export(wav, "voice", "c").parent.name == "Voice"


# --------------------------------------------------------------------------- #
# Postprocessor                                                                #
# --------------------------------------------------------------------------- #
def test_postprocessor_est_installe_dans_assets_editor(projet):
    dest = UnityExporter(projet).install_postprocessor()
    assert dest == projet / "Assets" / "Editor" / "ContentStudioAssetPostprocessor.cs"
    assert dest.exists()


def test_postprocessor_cible_les_bons_chemins(projet):
    """Le C# décide des réglages d'après l'emplacement : les constantes doivent
    correspondre EXACTEMENT à ce que l'exporter écrit, sinon rien ne s'applique."""
    contenu = UnityExporter(projet).install_postprocessor().read_text(encoding="utf-8")
    for chemin in (
        "Assets/Art/Sprites/",
        "Assets/Audio/Music/",
        "Assets/Audio/SFX/",
        "Assets/Audio/Voice/",
    ):
        assert chemin in contenu


def test_postprocessor_applique_les_reglages_mobiles(projet):
    contenu = UnityExporter(projet).install_postprocessor().read_text(encoding="utf-8")
    assert "ASTC" in contenu                      # compression Android
    assert "Streaming" in contenu                 # musique
    assert "DecompressOnLoad" in contenu          # SFX et voix
    assert "forceToMono" in contenu               # SFX/voix en mono sur mobile
    # Le C# est aligné visuellement (espaces multiples avant le '='), l'assertion
    # doit donc tolérer l'espacement plutôt que de figer le formatage.
    assert re.search(r"mipmapEnabled\s*=\s*false", contenu)


def test_postprocessor_est_idempotent(projet):
    exp = UnityExporter(projet)
    premier = exp.install_postprocessor().read_text(encoding="utf-8")
    second = exp.install_postprocessor().read_text(encoding="utf-8")
    assert premier == second

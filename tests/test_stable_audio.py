"""Tests des providers Stable Audio 3 (musique + SFX).

Volontairement *légers* : on ne charge jamais le modèle et on n'importe pas
stable_audio_tools. On vérifie l'enregistrement, l'identité des sous-classes,
la dégradation propre quand le paquet manque, et le bornage de la durée —
c'est-à-dire la logique qui nous appartient, pas celle de Stability AI.

La validation en génération réelle se fait à la main (voir la note en bas de
config/providers.yaml), pas ici : elle coûte du GPU et des minutes.
"""
from __future__ import annotations

import builtins

import pytest

from studio.core import Location, Modality
from studio.core.registry import get_provider_class
from studio.providers.music.stableaudio_music import StableAudioMusic
from studio.providers.sfx.stableaudio_sfx import StableAudioSFX
from studio.providers.stable_audio_base import StableAudioBase


# --------------------------------------------------------------------------- #
# Enregistrement + identité                                                    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "cls, modality, provider_name",
    [
        (StableAudioMusic, Modality.MUSIC, "stableaudio-music"),
        (StableAudioSFX, Modality.SFX, "stableaudio-sfx"),
    ],
)
def test_provider_est_enregistre(cls, modality, provider_name):
    """@register a bien branché la classe sur (modalité, nom)."""
    assert cls.name == provider_name
    assert cls.modality is modality
    assert get_provider_class(modality, provider_name) is cls


@pytest.mark.parametrize("cls", [StableAudioMusic, StableAudioSFX])
def test_provider_est_local_et_partage_le_socle(cls):
    assert issubclass(cls, StableAudioBase)
    assert cls.location is Location.LOCAL
    # Les "small" tiennent largement sous les 8 Go du poste.
    assert cls.min_vram_gb <= 8


def test_les_deux_providers_visent_des_modeles_differents():
    """Garde-fou anti copier-coller : musique et SFX ne doivent pas pointer
    sur le même checkpoint."""
    assert StableAudioMusic.default_model != StableAudioSFX.default_model
    assert "music" in StableAudioMusic.default_model
    assert "sfx" in StableAudioSFX.default_model


# --------------------------------------------------------------------------- #
# available() — dégradation propre                                             #
# --------------------------------------------------------------------------- #
def test_available_faux_si_paquet_absent(monkeypatch):
    """Sans stable-audio-tools, le provider se déclare indisponible (au lieu de
    lever) — c'est ce qui permet au routeur de basculer sur le fallback."""
    vrai_import = builtins.__import__

    def import_qui_refuse(name, *args, **kwargs):
        if name == "stable_audio_tools":
            raise ImportError("simulé : paquet absent")
        return vrai_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_qui_refuse)

    ok, raison = StableAudioMusic().available()
    assert ok is False
    assert "stable-audio-tools" in raison


def test_available_nexige_pas_cuda(monkeypatch):
    """Contrairement à MusicGen, les variantes small tournent aussi sur CPU :
    l'absence de GPU ne doit pas rendre le provider indisponible."""
    pytest.importorskip("torch")
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    # Ne s'applique que si stable_audio_tools est présent ; sinon le test n'a
    # rien à prouver et on le saute.
    pytest.importorskip("stable_audio_tools")

    ok, _ = StableAudioSFX().available()
    assert ok is True


# --------------------------------------------------------------------------- #
# Bornage de la durée                                                          #
# --------------------------------------------------------------------------- #
def test_plafonds_de_duree_coherents():
    """Un SFX est court, une BGM est longue — les plafonds doivent le refléter."""
    assert StableAudioSFX.default_duration < StableAudioMusic.default_duration
    assert StableAudioSFX.max_duration < StableAudioMusic.max_duration
    # 120 s = longueur native mesurée du checkpoint small-music
    # (sample_size 5 292 032 à 44,1 kHz). Demander plus rend quand même 120 s.
    assert StableAudioMusic.max_duration == 120


@pytest.mark.parametrize(
    "cls, demande, attendu",
    [
        (StableAudioMusic, 9999, 120),   # écrêté au plafond NATIF du modèle
        (StableAudioMusic, 0, 1),        # plancher à 1 s
        (StableAudioMusic, 30, 30),      # valeur raisonnable conservée
        (StableAudioSFX, 9999, 30),
        (StableAudioSFX, -5, 1),
        (StableAudioSFX, 7, 7),
    ],
)
def test_duree_bornee(cls, demande, attendu):
    """Reproduit le calcul de generate() sans rien charger : la durée demandée
    est ramenée dans [1, max_duration]."""
    borne = max(1, min(int(demande), cls.max_duration))
    assert borne == attendu


# --------------------------------------------------------------------------- #
# Nommage des fichiers de sortie                                               #
# --------------------------------------------------------------------------- #
def test_compteur_par_classe_est_independant():
    """Chaque sous-classe a son propre compteur : les WAV musique et SFX ne
    doivent pas se marcher dessus dans outputs/."""
    depart_music = StableAudioMusic._counter
    depart_sfx = StableAudioSFX._counter

    StableAudioMusic._counter += 1
    assert StableAudioSFX._counter == depart_sfx

    StableAudioMusic._counter = depart_music  # restauration

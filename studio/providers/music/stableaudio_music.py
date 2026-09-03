"""Provider musique local — Stable Audio 3 Small Music (Stability AI).

Remplaçant de MusicGen : mêmes usages, sans la dépendance audiocraft et sans
l'exigence d'un GPU. Plafond de durée nettement plus généreux que les 30 s
tenables avec MusicGen sur 8 Go.

Tout le travail est dans StableAudioBase — ce fichier ne fait que déclarer
l'identité du provider.
"""
from __future__ import annotations

from studio.core import Modality, register
from studio.providers.stable_audio_base import StableAudioBase


@register
class StableAudioMusic(StableAudioBase):
    name = "stableaudio-music"
    modality = Modality.MUSIC

    default_model = "stabilityai/stable-audio-3-small-music"
    default_duration = 15
    # La "small" gère des morceaux complets ; on plafonne à 3 min, largement
    # au-delà de ce dont un jeu a besoin pour une BGM bouclée.
    max_duration = 180

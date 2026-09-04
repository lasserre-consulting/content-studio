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
    # 120 s est la longueur NATIVE du modèle (sample_size = 5 292 032 à 44,1 kHz),
    # mesurée sur ce poste : demander plus rend quand même 120 s. Ne pas remonter
    # ce plafond sans changer de variante (la "medium" va jusqu'à 6:20).
    max_duration = 120

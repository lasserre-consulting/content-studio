"""Provider SFX local — Stable Audio 3 Small SFX (Stability AI).

Remplaçant d'AudioGen : même rôle, sans audiocraft, et tourne aussi sur CPU.

Tout le travail est dans StableAudioBase — ce fichier ne fait que déclarer
l'identité du provider.
"""
from __future__ import annotations

from studio.core import Modality, register
from studio.providers.stable_audio_base import StableAudioBase


@register
class StableAudioSFX(StableAudioBase):
    name = "stableaudio-sfx"
    modality = Modality.SFX

    default_model = "stabilityai/stable-audio-3-small-sfx"
    default_duration = 5
    # Un effet sonore utile dépasse rarement quelques secondes ; ce plafond
    # évite surtout de gaspiller du temps de génération par erreur de paramètre.
    max_duration = 30

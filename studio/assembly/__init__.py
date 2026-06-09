"""Couche d'assemblage : transformer des assets bruts (images, voix, musique)
en livrables finis (vidéos montées, planches de sprites...).

Le cœur du studio sait *générer* des fichiers isolés ; l'assemblage les
*combine*. Tout passe par ffmpeg (vidéo/audio) et Pillow (images).
"""
from .ffmpeg import (
    FFmpegUnavailable,
    burn_subtitles,
    ffmpeg_available,
    mix_audio,
    mux_audio_video,
    slideshow,
    still_to_video,
)
from .image_ops import rembg_available, remove_background

__all__ = [
    "FFmpegUnavailable",
    "ffmpeg_available",
    "still_to_video",
    "slideshow",
    "mux_audio_video",
    "mix_audio",
    "burn_subtitles",
    "rembg_available",
    "remove_background",
]

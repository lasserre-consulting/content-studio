"""Auto-enregistrement des providers.

Chaque module concret est importé ici pour exécuter son @register. Les imports
sont tolérants aux pannes : si les dépendances lourdes d'un provider local
(torch, diffusers, audiocraft...) ne sont pas installées, le module est ignoré
au lieu de faire tomber tout le studio. Le provider devient simplement
"indisponible" et le routeur passe au suivant.
"""
from __future__ import annotations

import importlib
import logging

log = logging.getLogger("studio.providers")

# Liste des modules de providers à charger. Ajouter une ligne = brancher un modèle.
_PROVIDER_MODULES = [
    # LLM
    "studio.providers.llm.anthropic_llm",
    "studio.providers.llm.openai_llm",
    "studio.providers.llm.ollama_llm",
    # Image
    "studio.providers.image.sdxl_local",
    "studio.providers.image.fal_image",
    # Vidéo
    "studio.providers.video.fal_video",
    # Musique
    "studio.providers.music.stableaudio_music",
    "studio.providers.music.musicgen_local",
    # SFX
    "studio.providers.sfx.stableaudio_sfx",
    "studio.providers.sfx.audiogen_local",
    # Voix
    "studio.providers.tts.kokoro_local",
]


def _load_all() -> None:
    for mod in _PROVIDER_MODULES:
        try:
            importlib.import_module(mod)
        except Exception as e:  # noqa: BLE001 — on veut vraiment tout attraper
            log.debug("Provider non chargé (%s): %s", mod, e)


_load_all()

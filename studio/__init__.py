"""Content Studio — génération unifiée image / vidéo / musique / SFX / voix / texte.

Usage rapide :
    from studio import get_router
    r = get_router()
    r.image("un chat astronaute, style pixar")     # → GenResult avec un .png
    print(r.llm("améliore ce prompt: chat"))         # → texte

Studios (orchestration de haut niveau) :
    from studio import content_studio, game_studio
    content_studio().short("Mon script...")          # → MP4 vertical monté
    game_studio().sprite("sorcière", name="morra")   # → sprite(s) PNG
"""
from .config import get_router

# Couche d'orchestration / outillage (ajoutée 2026-06-05). Imports légers :
# tout ce qui est lourd (torch/transformers/audiocraft) reste paresseux DANS
# ces modules — les importer ici ne charge aucun gros modèle.
from . import procedural  # primitives procédurales déterministes (vignette, sphere, duotone…)
from .batch import BatchRunner, BatchReport, contact_sheet, force_utf8
from .verify import verify_image, verify_audio, verify_manifest, Spec
from .exporters import Exporter, EngineProfile, MemoriaExporter, GodotExporter
from .judge import identify, best_of, score, clip_available  # CLIP (modèle chargé à l'appel)
from .assembly.paths import ascii_workspace, is_ascii_safe, to_ascii_slug

__all__ = [
    "get_router", "content_studio", "game_studio",
    # outillage
    "procedural", "BatchRunner", "BatchReport", "contact_sheet", "force_utf8",
    "verify_image", "verify_audio", "verify_manifest", "Spec",
    "Exporter", "EngineProfile", "MemoriaExporter", "GodotExporter",
    "identify", "best_of", "score", "clip_available",
    "ascii_workspace", "is_ascii_safe", "to_ascii_slug",
]
__version__ = "0.1.0"


def content_studio(workspace=None):
    """Raccourci : un ContentStudio prêt à l'emploi (router auto-configuré)."""
    from .studios import ContentStudio
    return ContentStudio(get_router(), workspace)


def game_studio(workspace=None):
    """Raccourci : un GamedevStudio prêt à l'emploi.

    `workspace` peut pointer vers le dossier d'assets d'un projet de jeu pour y
    écrire directement (ex: le dossier res:// d'un projet Godot)."""
    from .studios import GamedevStudio
    return GamedevStudio(get_router(), workspace)

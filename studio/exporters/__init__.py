"""Exporters : adaptateurs qui écrivent les assets au bon format/nom/emplacement
selon le moteur cible.

Le moteur de génération produit des fichiers « neutres » (WAV, PNG) dans un
workspace. Un *exporter* prend ces livrables et les matérialise dans
l'arborescence d'un projet/moteur précis, en appliquant ses conventions :
conversion de format (WAV->OGG), nommage canonique, structure de dossiers,
override de textures.

Chaque exporter porte un `EngineProfile` qui décrit ce que la cible accepte
réellement (garde-fou : éviter de pousser une spritesheet 2D vers un perso 3D).

- MemoriaExporter : mods FF9 (audio OGG, textures de modèles 3D).
- GodotExporter   : projets Godot (sprites 2D PNG, audio ogg/wav).

La racine de la cible est toujours passée en paramètre — jamais de chemin Steam
ou de projet codé en dur.
"""
from .base import AssetKindSpec, EngineProfile, Exporter
from .godot import GODOT_PROFILE, GodotExporter
from .memoria import MEMORIA_PROFILE, MemoriaExporter, canonical_sfx_name

__all__ = [
    "Exporter",
    "EngineProfile",
    "AssetKindSpec",
    "MemoriaExporter",
    "MEMORIA_PROFILE",
    "canonical_sfx_name",
    "GodotExporter",
    "GODOT_PROFILE",
]

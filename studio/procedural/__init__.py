"""Primitives procédurales génériques (PIL/numpy), déterministes et réutilisables.

Module CŒUR du studio, indépendant de tout projet (ex. FF9). Regroupe des
primitives de génération d'images : couleurs, champs de distance, vignettes,
anneaux, disques doux, sphère ombrée, transformations colorimétriques
(duotone/désaturation/teinte), spritesheets, texte et étoiles.

Tout est ré-exporté depuis `studio.procedural.shapes`.
"""
from __future__ import annotations

from studio.procedural.shapes import *  # noqa: F401,F403
from studio.procedural.shapes import __all__ as _shapes_all

__all__ = list(_shapes_all)

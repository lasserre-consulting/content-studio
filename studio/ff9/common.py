"""Primitives PIL/numpy partagées par les générateurs d'assets FF9.

Ce module est désormais une simple FAÇADE de rétro-compatibilité : les
primitives procédurales génériques vivent dans `studio.procedural` (module
CŒUR réutilisable). On ré-exporte ici l'ensemble de l'API historique afin que
les imports existants continuent de fonctionner à l'identique, par exemple :

    from studio.ff9 import common as c
    c.sphere(...), c.vignette(...), c.Sphere, c.Image, ...

Toutes les fonctions restent DÉTERMINISTES (le bruit utilise un RNG seedé) et
produisent du RGBA (PNG-32), conformément à la bible visuelle.
"""
from __future__ import annotations

# Modules tiers historiquement accessibles via `common` (ex. gen_enemy_overlays
# utilise `c.Image`). On les réexpose pour ne casser aucun import existant.
import numpy as np  # noqa: F401
from PIL import Image, ImageDraw, ImageEnhance, ImageFont  # noqa: F401

# Ré-export de toutes les primitives génériques du CŒUR procédural.
from studio.procedural import *  # noqa: F401,F403
from studio.procedural import __all__ as _procedural_all

# Quelques détails internes encore utiles côté FF9 (police par défaut, helper
# luminance) sont également exposés pour une compat parfaite.
from studio.procedural.shapes import _FONTS, _luminance  # noqa: F401

# `__all__` = primitives procédurales + symboles tiers historiquement exposés.
__all__ = list(_procedural_all) + [
    "np",
    "Image",
    "ImageDraw",
    "ImageEnhance",
    "ImageFont",
]

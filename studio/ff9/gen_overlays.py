"""Génère les overlays GLOBAUX de contamination du Troisième Monde.

Tier 1 — spec EXACTE du manifest overlays/_MANIFEST.txt :
  - 3 vignettes radiales #2D0A47 (Actes I/II/III) à 3% / 12% / 25%.
  - 1 overlay architectural Palimpseste (lignes de perspective doubles).

Tout est déterministe (PIL/numpy), aucun modèle génératif.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from studio.ff9 import common as c

SUBDIR = "overlays"

W, H = 1920, 1080
SIGNATURE = "#2D0A47"
PALIMPSESTE_COLOR = "#E8E8F0"

# (nom, opacité, inner_frac, outer_frac) — voir manifest fichiers 1-3.
_VIGNETTES = (
    ("overlay_third_world_vignette_act1.png", 0.03, 0.75, 0.90),
    ("overlay_third_world_vignette_act2.png", 0.12, 0.70, 0.88),
    ("overlay_third_world_vignette_act3.png", 0.25, 0.60, 0.82),
)


def _palimpseste() -> Image.Image:
    """Lignes de perspective fines #E8E8F0 à 15%, doublées (+3px bas-droite).

    Point de fuite au centre : un faisceau de diagonales rayonne depuis le
    centre, complété d'horizontales régulières. Rendu en ×2 puis réduit en
    LANCZOS pour un antialiasing propre des traits 1px.
    """
    s = 2  # supersampling
    cw, ch = W * s, H * s
    img = c.new_canvas(cw, ch)
    draw = ImageDraw.Draw(img)
    color = (*c.hex_to_rgb(PALIMPSESTE_COLOR), c.frac_to_alpha(0.15))

    cx, cy = (cw - 1) / 2.0, (ch - 1) / 2.0
    diag = (cw ** 2 + ch ** 2) ** 0.5  # longueur suffisante pour sortir du cadre
    off = 3 * s  # décalage bas-droite, exprimé en pixels supersamplés

    def line(p0, p1):
        """Dessine la ligne originale + sa copie décalée (palimpseste)."""
        draw.line([p0, p1], fill=color, width=s)
        draw.line(
            [(p0[0] + off, p0[1] + off), (p1[0] + off, p1[1] + off)],
            fill=color,
            width=s,
        )

    # Diagonales rayonnant depuis le point de fuite central (perspective).
    # Espacement angulaire => sur le pourtour, traits tous les ~80-120px.
    n_rays = 48
    for i in range(n_rays):
        a = 2.0 * np.pi * i / n_rays
        line((cx, cy), (cx + diag * np.cos(a), cy + diag * np.sin(a)))

    # Horizontales régulières (~100px en espace ×1) cohérentes avec la scène.
    step = 100 * s
    y = step // 2
    while y < ch:
        line((0, y), (cw, y))
        y += step

    return img.resize((W, H), Image.LANCZOS)


def generate(out_root: Path) -> list[Path]:
    """Produit les 4 overlays dans `<out_root>/overlays`, renvoie les chemins."""
    out = Path(out_root) / SUBDIR
    paths: list[Path] = []

    # Fichiers 1-3 : vignettes radiales (centre transparent -> coins #2D0A47).
    for name, opacity, inner, outer in _VIGNETTES:
        img = c.vignette(W, H, SIGNATURE, opacity, inner, outer, normalize="corner")
        paths.append(c.save_png(img, out / name))

    # Fichier 4 : overlay architectural Palimpseste (lignes doubles).
    paths.append(c.save_png(_palimpseste(), out / "overlay_palimpseste_act3_lines.png"))

    return paths

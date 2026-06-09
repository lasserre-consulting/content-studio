"""Générateur d'overlays PROCÉDURAUX pour les ennemis de La Troisième Fissure.

Produit UNIQUEMENT les assets déterministes (gradients/formes) décrits dans les
manifestes : ombres inversées et overlays de désaturation radiale.

NE produit AUCUN spritesheet figuratif (idle/scan/attack/death/portrait) :
ceux-ci exigent un modèle génératif ou un artiste — hors périmètre de ce module.

Dossiers gérés :
- enemies/deathguise_scout/
- enemies/nova_dragon_crystal/
"""
from __future__ import annotations

from pathlib import Path

from PIL import ImageDraw, ImageFilter

from studio.ff9 import common as c

# Couleur d'ombre confirmée par LES DEUX manifestes : #2D0A47 (violet, pas noir).
SHADOW_COLOR = "#2D0A47"
# 60% d'opacité globale -> alpha ≈ 153 (manifestes : "Semi-transparence 60%").
SHADOW_ALPHA = c.frac_to_alpha(0.60)  # 153


def _soft_ellipse_shadow(
    w: int,
    h: int,
    *,
    color: str,
    alpha: int,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    blur: float,
) -> "c.Image.Image":
    """Ombre elliptique douce sur canvas transparent w×h.

    Dessine une ellipse pleine puis applique un flou gaussien. L'alpha maximal
    après flou est ramené à `alpha` (l'opacité globale demandée).
    """
    img = c.new_canvas(w, h)
    draw = ImageDraw.Draw(img)
    rgb = c.hex_to_rgb(color)
    # Ellipse opaque (alpha 255) avant flou ; on ajustera l'opacité ensuite.
    draw.ellipse(
        [cx - rx, cy - ry, cx + rx, cy + ry],
        fill=(*rgb, 255),
    )
    img = img.filter(ImageFilter.GaussianBlur(blur))
    # Ramène l'alpha global au niveau de semi-transparence voulu (60%).
    r, g, b, a = img.split()
    a = a.point(lambda v: int(v * alpha / 255))
    img.putalpha(a)
    return img


def generate(out_root: Path) -> list[Path]:
    paths: list[Path] = []
    dg = Path(out_root) / "enemies" / "deathguise_scout"
    nd = Path(out_root) / "enemies" / "nova_dragon_crystal"

    # ------------------------------------------------------------------ #
    # DEATHGUISE ÉCLAIREUR
    # ------------------------------------------------------------------ #

    # deathguise_shadow_inverted.png — 128×64.
    # Ombre violette douce (#2D0A47, 60%) ; l'ombre "ne colle pas au sol" :
    # décalée de 8px vers le HAUT et étirée verticalement (pointe vers le haut).
    W, H = 128, 64
    dg_shadow = _soft_ellipse_shadow(
        W, H,
        color=SHADOW_COLOR,
        alpha=SHADOW_ALPHA,
        cx=W / 2,
        cy=H / 2 - 8,          # décalage 8px vers le haut (source inexistante)
        rx=W * 0.34,
        ry=H * 0.40,           # étirée verticalement -> orientée vers le haut
        blur=6.0,
    )
    paths.append(c.save_png(dg_shadow, dg / "deathguise_shadow_inverted.png"))

    # deathguise_desaturation_overlay.png — 256×256.
    # Masque radial niveaux de gris : centre blanc (désat max) -> bord noir.
    # Manifeste : centre 0-30% blanc, transition douce -> gamma 1.0 (linéaire).
    dg_desat = c.radial_gray(256, gamma=1.0)
    paths.append(c.save_png(dg_desat, dg / "deathguise_desaturation_overlay.png"))

    # ------------------------------------------------------------------ #
    # NOVA DRAGON CRISTALLIN
    # ------------------------------------------------------------------ #

    # nova_dragon_shadow_inverted.png — 256×128.
    # Grande échelle. Source fictive en haut-gauche -> ombre projetée vers le
    # bas-droit. Ellipse violette douce (#2D0A47, 60%), aplatie au sol.
    W, H = 256, 128
    nd_shadow = _soft_ellipse_shadow(
        W, H,
        color=SHADOW_COLOR,
        alpha=SHADOW_ALPHA,
        cx=W / 2 + 14,         # décalée vers la droite (source en haut-gauche)
        cy=H / 2 + 8,          # décalée vers le bas (ombre vers le bas-droit)
        rx=W * 0.40,
        ry=H * 0.30,           # aplatie au sol
        blur=10.0,
    )
    paths.append(c.save_png(nd_shadow, nd / "nova_dragon_shadow_inverted.png"))

    # nova_dragon_desaturation_large.png — 512×512.
    # Grande échelle (rayon 4 tiles). Courbe non-linéaire pow(d, 0.7) alignée
    # sur le shader NovaDesaturationGround (VFX 003).
    nd_desat = c.radial_gray(512, gamma=0.7)
    paths.append(c.save_png(nd_desat, nd / "nova_dragon_desaturation_large.png"))

    return paths

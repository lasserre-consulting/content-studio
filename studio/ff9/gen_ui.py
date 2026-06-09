"""Générateur d'assets UI procéduraux — La Troisième Fissure (FF9 Suite).

Produit les assets UI du Tier 1 (générables de zéro) : glyphes de statut,
barre HP corrompue, affichage HP Ozma, chiffre TERMINUS, et un atlas de police
glitché *approximatif*.

Non produits ici (extraction Moguri requise, hors Tier 1 procédural) :
  - ui_battle_hud_act2_desaturated.png : désaturation du HUD Moguri (source requise).
  - ui_save_menu_intact.png            : copie exacte du menu Moguri (extraction).
  - ui_name_font_glitch_atlas.png      : la vraie version nécessite l'atlas de
    police Moguri ; on en produit une APPROXIMATION (police bold système).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from studio.ff9 import common as c

SUBDIR = "ui/sprites"

# Échelle de suréchantillonnage pour la netteté des petits glyphes.
_SS = 8
_SEED = 0x0FF9


# --------------------------------------------------------------------------- #
# 1. Glyphe [CATALOGUÉ] — œil stylisé SANS pupille
# --------------------------------------------------------------------------- #
def _catalogued_glyph() -> Image.Image:
    """Œil ovale (#2D0A47), iris plein au centre, paupières en arcs fins."""
    s = 32 * _SS
    col = c.hex_to_rgba("#2D0A47")
    img = c.new_canvas(s, s)
    d = ImageDraw.Draw(img)
    cx = cy = s / 2.0

    # Ovale horizontal : ~24px large, ~12px haut (à l'échelle ×8).
    rx, ry = 12 * _SS, 6 * _SS
    lw = max(1, int(round(1.2 * _SS)))  # paupières ~1px @32

    # Paupière supérieure et inférieure : 2 arcs encadrant l'iris.
    bbox = [cx - rx, cy - ry, cx + rx, cy + ry]
    d.arc(bbox, start=180, end=360, fill=col, width=lw)  # paupière haute
    d.arc(bbox, start=0, end=180, fill=col, width=lw)    # paupière basse

    # Iris : cercle PLEIN rayon ~4px (pas de pupille = aucun "trou" interne).
    ir = 4 * _SS
    d.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=col)

    return img.resize((32, 32), Image.LANCZOS)


# --------------------------------------------------------------------------- #
# 2. Glyphe [RÉMINISCENCE] — anneau + étoile à 5 branches
# --------------------------------------------------------------------------- #
def _reminiscence_glyph() -> Image.Image:
    """Anneau or (#E8C547) rayon ~14px + étoile 5 branches centrée."""
    s = 32 * _SS
    col = c.hex_to_rgba("#E8C547")
    img = c.new_canvas(s, s)
    d = ImageDraw.Draw(img)
    cx = cy = s / 2.0

    # Anneau extérieur : 1px @32, rayon 14px.
    R = 14 * _SS
    lw = max(1, int(round(1.2 * _SS)))
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=col, width=lw)

    # Étoile à 5 branches : pointes r=10px, creux r=6px.
    pts = c.star_points(cx, cy, r_outer=10 * _SS, r_inner=6 * _SS, n=5, rot=-math.pi / 2)
    d.polygon(pts, fill=col)

    return img.resize((32, 32), Image.LANCZOS)


# --------------------------------------------------------------------------- #
# 3. Barre HP corrompue — rouge + gaps transparents semi-aléatoires
# --------------------------------------------------------------------------- #
def _hp_bar_corrupted() -> Image.Image:
    """Barre HP rouge (cadre gris + dégradé) percée de 6-8 gaps transparents."""
    w, h = 256, 16
    arr = np.zeros((h, w, 4), dtype=np.uint8)

    # Cadre fin gris foncé (1px) tout autour.
    frame = c.hex_to_rgb("#3A3A42")
    arr[0, :, :3] = frame
    arr[-1, :, :3] = frame
    arr[:, 0, :3] = frame
    arr[:, -1, :3] = frame
    arr[0, :, 3] = arr[-1, :, 3] = arr[:, 0, 3] = arr[:, -1, 3] = 255

    # Remplissage : dégradé horizontal rouge #C03028 -> #E04038.
    c0 = np.array(c.hex_to_rgb("#C03028"), dtype=np.float64)
    c1 = np.array(c.hex_to_rgb("#E04038"), dtype=np.float64)
    inner_x0, inner_x1 = 1, w - 1
    span = inner_x1 - inner_x0
    for x in range(inner_x0, inner_x1):
        t = (x - inner_x0) / max(1, span - 1)
        rgb = (c0 + (c1 - c0) * t).round().astype(np.uint8)
        arr[1:-1, x, :3] = rgb
        arr[1:-1, x, 3] = 255

    # Gaps : 7 trous de 2-3px, répartis semi-aléatoirement, isolés.
    rng = np.random.default_rng(_SEED)
    n_gaps = 7
    # Découpe la longueur utile en n segments, un gap par segment (jamais collés).
    segs = np.linspace(inner_x0 + 4, inner_x1 - 4, n_gaps + 1)
    for i in range(n_gaps):
        lo, hi = int(segs[i]), int(segs[i + 1])
        gw = int(rng.integers(2, 4))           # largeur 2-3px
        gx = int(rng.integers(lo, max(lo + 1, hi - gw)))
        # Perce la colonne (intérieur seulement) -> transparent.
        arr[1:-1, gx:gx + gw, 3] = 0

    return Image.fromarray(arr, "RGBA")


# --------------------------------------------------------------------------- #
# 4. Affichage HP Ozma — "????" blanc dans un cadre de panneau
# --------------------------------------------------------------------------- #
def _ozma_hp_display() -> Image.Image:
    """Panneau 192×32 : fond sombre semi-transparent + bordure + '????' blanc."""
    w, h = 192, 32
    img = c.new_canvas(w, h)
    d = ImageDraw.Draw(img)

    # Fond légèrement sombre semi-transparent.
    d.rectangle([0, 0, w - 1, h - 1], fill=(16, 18, 24, 170))
    # Bordure fine 1px gris clair.
    d.rectangle([0, 0, w - 1, h - 1], outline=(200, 204, 212, 255), width=1)

    # Texte "????" blanc centré.
    font = c.load_font(22)
    txt = c.centered_text(w, h, "????", "#FFFFFF", font)
    img.alpha_composite(txt)
    return img


# --------------------------------------------------------------------------- #
# 5. Chiffre TERMINUS "1" — or vif, très gros, centré
# --------------------------------------------------------------------------- #
def _terminus_one() -> Image.Image:
    """'1' #FFD700 en ~200px, centré sur 256×256 transparent."""
    font = c.load_font(200)
    return c.centered_text(256, 256, "1", "#FFD700", font)


# --------------------------------------------------------------------------- #
# 6. (APPROXIMATION) Atlas de police glitché — A-Z sur 2 rangées
# --------------------------------------------------------------------------- #
def _name_font_glitch_atlas() -> Image.Image:
    """Approximation 512×128 : rangée 1 = A-Z bold, rangée 2 = version glitchée.

    NB : ce n'est PAS la vraie police FF9/Moguri (atlas source non disponible) ;
    c'est une approximation système destinée au prototypage.
    """
    w, h = 512, 128
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    cols, rows = 13, 2  # 26 cases sur la rangée du haut
    cell_w = w // cols          # ~39px
    cell_h = h // (rows * 2)    # une "ligne logique" = 2 rangées physiques A-M / N-Z

    img = c.new_canvas(w, h)
    font = c.load_font(24)
    white = (235, 235, 240)

    # Rangée 1 (haut) = glyphes nets ; rangée 2 (bas) = glyphes glitchés.
    # On dispose A-Z sur la moitié haute (2 lignes de 13), puis la version
    # corrompue sur la moitié basse, alignée case à case.
    def render_cell(ch: str) -> Image.Image:
        cell = c.new_canvas(cell_w, cell_h)
        cd = ImageDraw.Draw(cell)
        box = cd.textbbox((0, 0), ch, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        cd.text(((cell_w - tw) / 2 - box[0], (cell_h - th) / 2 - box[1]),
                ch, fill=(*white, 255), font=font)
        return cell

    def glitch(cell: Image.Image, rng: np.random.Generator) -> Image.Image:
        a = np.asarray(cell, dtype=np.uint8).copy()
        ys, xs = np.where(a[..., 3] > 0)
        if len(xs) == 0:
            return cell
        # 2-4 pixels arrachés (transparent).
        for _ in range(int(rng.integers(2, 5))):
            k = int(rng.integers(0, len(xs)))
            a[ys[k], xs[k], 3] = 0
        # Opacité réduite (50%) sur quelques pixels.
        for _ in range(int(rng.integers(3, 7))):
            k = int(rng.integers(0, len(xs)))
            a[ys[k], xs[k], 3] = a[ys[k], xs[k], 3] // 2
        out = Image.fromarray(a, "RGBA")
        # 1-2 pixels "déplacés" : décale une fine bande de 1px.
        for _ in range(int(rng.integers(1, 3))):
            ry = int(rng.integers(0, cell_h))
            shifted = c.new_canvas(cell_w, cell_h)
            band = out.crop((0, ry, cell_w, ry + 1))
            shifted.paste(band, (int(rng.integers(-1, 2)), ry))
            out.alpha_composite(shifted)
        return out

    rng = np.random.default_rng(_SEED + 1)
    half = h // 2
    for i, ch in enumerate(letters):
        r, col = divmod(i, cols)            # r in {0,1}, col in [0,12]
        x = col * cell_w
        y_clean = r * cell_h                # moitié haute
        y_dirty = half + r * cell_h         # moitié basse
        clean = render_cell(ch)
        img.alpha_composite(clean, (x, y_clean))
        img.alpha_composite(glitch(clean, rng), (x, y_dirty))

    return img


# --------------------------------------------------------------------------- #
# Point d'entrée
# --------------------------------------------------------------------------- #
def generate(out_root: Path) -> list[Path]:
    out = Path(out_root) / SUBDIR
    paths: list[Path] = []

    paths.append(c.save_png(_catalogued_glyph(), out / "ui_status_catalogued_glyph.png"))
    paths.append(c.save_png(_reminiscence_glyph(), out / "ui_status_reminiscence_glyph.png"))
    paths.append(c.save_png(_hp_bar_corrupted(), out / "ui_hp_bar_corrupted.png"))
    paths.append(c.save_png(_ozma_hp_display(), out / "ui_ozma_hp_display.png"))
    paths.append(c.save_png(_terminus_one(), out / "ui_terminus_one.png"))
    # Approximation (pas la vraie police FF9) — signalée dans le rapport.
    paths.append(c.save_png(_name_font_glitch_atlas(), out / "ui_name_font_glitch_atlas.png"))

    return paths

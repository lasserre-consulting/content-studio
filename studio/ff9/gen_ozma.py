"""Générateur d'assets — OZMA Forme Véritable (boss final, P0 absolu).

Ozma est une sphère parfaite #050508 + noise 2% qui "absorbe la lumière".
TOUT dérive de la sphère canonique (FICHIER 1) : idle = micro-rotation par seed,
phases = filaments tracés SUR LA COURBURE via les normales, charge/mort =
assombrissement par `brightness`.

Conventions du module : voir studio/ff9/__init__.py.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from studio.ff9 import common as c

SUBDIR = "enemies/ozma_true_form"

# --- Constantes de spec (le manifeste insiste : chaque pixel compte) -------- #
CANVAS = 512                 # canvas d'une frame
DIAMETER = 480               # sphère centrée, bordure 16px transparente
BASE_HEX = "#050508"         # surface
LIGHT_HEX = "#080810"        # point le plus clair (dégradé interne TRÈS subtil)
NOISE = 0.02                 # 2% de variation de luminance

FILAMENT_HEX = "#0F3460"     # filaments phase 2/3
FILAMENT_ALPHA = 13          # 5% opacité = 13/255
FRACTURE_HEX = "#2D0A47"     # zones pulsantes phase 3
FRACTURE_ALPHA = 26          # 10% opacité = 26/255

GOLD_HEX = "#FFD700"         # overlay "1" TERMINUS
WHITE = (255, 255, 255, 255)

# Seeds de micro-rotation idle (un seed distinct par frame => noise sub-pixel).
IDLE_SEEDS = (1001, 1002, 1003, 1004)


# --------------------------------------------------------------------------- #
# Briques internes
# --------------------------------------------------------------------------- #

def _base_sphere(seed: int, brightness: float = 1.0):
    """Sphère canonique Ozma (FICHIER 1) — paramétrée par seed/luminosité."""
    return c.sphere(
        DIAMETER,
        BASE_HEX,
        canvas_size=CANVAS,
        noise_pct=NOISE,
        light=LIGHT_HEX,
        seed=seed,
        brightness=brightness,
    )


def _idle_frames() -> list:
    """4 frames idle : micro-rotation (seed/frame) + frames 2 & 4 à -3% lum."""
    frames = []
    for i, seed in enumerate(IDLE_SEEDS):
        # Frames 2 et 4 (index 1 et 3) absorbent +3% de lumière.
        brightness = 0.97 if i in (1, 3) else 1.0
        frames.append(_base_sphere(seed, brightness).image)
    return frames


def _surface_coords(sph):
    """Coordonnées sphériques (lon, lat) par pixel, NaN hors sphère.

    Dérivées des normales : longitude = atan2(nx, nz), latitude = asin(ny).
    Servent à tracer les filaments SUR la courbure (et non en projection plate).
    """
    lon = np.arctan2(sph.nx, sph.nz)        # ~[-pi, pi]
    lat = np.arcsin(np.clip(sph.ny, -1.0, 1.0))  # ~[-pi/2, pi/2]
    return lon, lat


def _filament_mask(sph) -> np.ndarray:
    """Masque float [0,1] des veines fines (1px) sur la courbure, ~40% surface.

    Veines = lieux où une combinaison sinusoïdale des coords sphériques frôle 0.
    On module par un second champ lent pour ne couvrir qu'environ 40% (le reste
    des veines est éteint). Antialiasing 1px via la distance au zéro de la sinus.
    """
    lon, lat = _surface_coords(sph)
    inside = sph.inside

    # Réseau de veines : motif fin et oblique (pas un seul axe).
    field = np.sin(lon * 9.0 + lat * 5.0) + 0.6 * np.sin(lat * 13.0 - lon * 3.0)
    # Largeur des lignes : on garde la crête proche de 0 -> lignes fines 1px.
    line = np.clip(1.0 - np.abs(field) / 0.05, 0.0, 1.0)

    # Champ lent de présence : n'allume les veines que sur ~40% de la surface.
    presence = np.sin(lon * 1.7 + 0.8) * np.cos(lat * 2.3 - 0.4)
    gate = (presence > 0.20).astype(np.float64)  # ~40% de la sphère

    mask = line * gate
    mask = np.where(inside, mask, 0.0)
    return np.nan_to_num(mask, nan=0.0)


def _compose_overlay(base_img, sph, mask: np.ndarray, color_hex: str, alpha: int):
    """Compose une couleur unie modulée par `mask` PAR-DESSUS la sphère.

    L'alpha effectif = mask * alpha, borné, et uniquement là où `inside`.
    Retourne une nouvelle image RGBA (base inchangée).
    """
    h, w = mask.shape
    rgb = c.hex_to_rgb(color_hex)
    layer = np.zeros((h, w, 4), dtype=np.uint8)
    layer[..., 0], layer[..., 1], layer[..., 2] = rgb
    a = (mask * alpha).round()
    a[~sph.inside] = 0
    layer[..., 3] = np.clip(a, 0, 255).astype(np.uint8)
    out = base_img.convert("RGBA").copy()
    out.alpha_composite(Image.fromarray(layer, "RGBA"))
    return out


def _phase2_frames() -> list:
    """idle + filaments #0F3460 à 5% sur ~40% de la surface, sur la courbure."""
    frames = []
    for i, seed in enumerate(IDLE_SEEDS):
        brightness = 0.97 if i in (1, 3) else 1.0
        sph = _base_sphere(seed, brightness)
        mask = _filament_mask(sph)
        frames.append(_compose_overlay(sph.image, sph, mask, FILAMENT_HEX, FILAMENT_ALPHA))
    return frames


def _phase3_frames() -> list:
    """Phase2 mais filaments BRISÉS (gaps) + zones #2D0A47 à 10% aux fractures."""
    frames = []
    for i, seed in enumerate(IDLE_SEEDS):
        brightness = 0.97 if i in (1, 3) else 1.0
        sph = _base_sphere(seed, brightness)
        h, w = sph.inside.shape

        # Filaments de base puis fragmentation : on éteint des segments.
        fil = _filament_mask(sph)
        rng = np.random.default_rng(2000 + i)
        gaps = rng.random((h, w))
        # ~45% des pixels de veine deviennent des "trous" -> discontinuité.
        broken = np.where(gaps < 0.45, 0.0, fil)

        # Zones de fracture : aux ruptures (là où il y avait veine mais coupée).
        fracture_sites = (fil > 0.5) & (broken < 0.05)
        # Étale chaque site en petite tache douce via un champ aléatoire lissé.
        spot_field = rng.random((h, w))
        fracture = np.where(fracture_sites, 1.0, 0.0)
        # Élargit légèrement les taches (dilatation 3x3 par max sur voisinage).
        fracture = _dilate(fracture, 2)
        fracture = fracture * (0.6 + 0.4 * spot_field)  # modulation d'intensité
        fracture[~sph.inside] = 0.0

        img = _compose_overlay(sph.image, sph, broken, FILAMENT_HEX, FILAMENT_ALPHA)
        img = _compose_overlay(img, sph, fracture, FRACTURE_HEX, FRACTURE_ALPHA)
        frames.append(img)
    return frames


def _dilate(mask: np.ndarray, it: int) -> np.ndarray:
    """Dilatation binaire douce (max sur voisinage) — `it` itérations 3x3."""
    m = mask.copy()
    for _ in range(it):
        acc = m.copy()
        acc[1:, :] = np.maximum(acc[1:, :], m[:-1, :])
        acc[:-1, :] = np.maximum(acc[:-1, :], m[1:, :])
        acc[:, 1:] = np.maximum(acc[:, 1:], m[:, :-1])
        acc[:, :-1] = np.maximum(acc[:, :-1], m[:, 1:])
        m = acc
    return m


def _death_frames() -> list:
    """4 frames de mort : -5%, -10%, -20% (vs idle), puis canvas transparent."""
    # F1..F3 : sphère arrêtée (seed fixe = pas de micro-rotation), assombrie.
    f1 = _base_sphere(IDLE_SEEDS[0], brightness=0.95).image   # -5%
    f2 = _base_sphere(IDLE_SEEDS[0], brightness=0.90).image   # -10%
    f3 = _base_sphere(IDLE_SEEDS[0], brightness=0.80).image   # -20%, tend au noir
    f4 = c.new_canvas(CANVAS, CANVAS)                         # disparue : transparent
    return [f1, f2, f3, f4]


# --------------------------------------------------------------------------- #
# Entrée publique
# --------------------------------------------------------------------------- #

def generate(out_root: Path) -> list[Path]:
    out = Path(out_root) / SUBDIR
    paths: list[Path] = []

    # FICHIER 1 — base canonique (template absolu).
    base = _base_sphere(IDLE_SEEDS[0]).image
    paths.append(c.save_png(base, out / "ozma_true_form_base.png"))

    # FICHIER 2 — idle (micro-rotation + frames 2/4 -3%).
    idle = _idle_frames()
    paths.append(c.save_png(c.hsheet(idle), out / "ozma_true_form_idle_frames.png"))

    # FICHIER 3 — phase 1 : copie exacte des idle_frames (spec explicite).
    paths.append(c.save_png(c.hsheet(idle), out / "ozma_phase1_learning_sheet.png"))

    # FICHIER 4 — phase 2 : filaments subtils sur la courbure.
    paths.append(c.save_png(c.hsheet(_phase2_frames()), out / "ozma_phase2_analysis_sheet.png"))

    # FICHIER 5 — phase 3 : filaments brisés + zones de fracture.
    paths.append(c.save_png(c.hsheet(_phase3_frames()), out / "ozma_phase3_entropy_sheet.png"))

    # FICHIER 6 — terminus charge : base -5% lum, aucun autre indice.
    charge = _base_sphere(IDLE_SEEDS[0], brightness=0.95).image
    paths.append(c.save_png(charge, out / "ozma_terminus_charge.png"))

    # FICHIER 7 — extinction flash : blanc pur 1920×1080, alpha 255.
    flash = c.solid(1920, 1080, WHITE)
    paths.append(c.save_png(flash, out / "ozma_extinction_flash.png"))

    # FICHIER 8 — overlay "1" or, gros (≈×3), centré, fond transparent.
    font = c.load_font(48)  # ~×3 d'une police de dégâts standard ~16px
    one = c.centered_text(512, 64, "1", GOLD_HEX, font)
    paths.append(c.save_png(one, out / "ozma_terminus_result_overlay.png"))

    # FICHIER 9 — death sheet (assombrissement progressif puis disparition).
    paths.append(c.save_png(c.hsheet(_death_frames()), out / "ozma_death_sheet.png"))

    return paths

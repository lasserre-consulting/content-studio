"""Primitives procédurales GÉNÉRIQUES (PIL/numpy), déterministes et réutilisables.

Ce module est le CŒUR procédural du studio : il ne dépend d'aucun projet
particulier (ni FF9, ni autre). Toutes les fonctions sont DÉTERMINISTES (le bruit
utilise un RNG seedé) afin que la génération soit reproductible. Les images sont
toujours produites/manipulées en RGBA (PNG-32).

Conventions :
- Les couleurs sont passées en hex ("#2D0A47") ou en tuple (r, g, b[, a]).
- Les opacités "fraction" sont dans [0, 1] ; converties en alpha 0-255.
- Le repère de distance radiale "corner" : 0 au centre, 1.0 exactement au coin
  du canvas (utile pour les vignettes qui doivent saturer dans les coins).
- Le repère "half" : 1.0 au milieu d'un bord (utile pour un gradient circulaire
  inscrit, ex. textures de désaturation carrées).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

# --------------------------------------------------------------------------- #
# Couleurs
# --------------------------------------------------------------------------- #

def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """'#2D0A47' (ou '2D0A47') -> (45, 10, 71)."""
    s = value.lstrip("#")
    return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def hex_to_rgba(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    r, g, b = hex_to_rgb(value)
    return (r, g, b, alpha)


def frac_to_alpha(frac: float) -> int:
    """Opacité [0,1] -> alpha entier [0,255] (arrondi)."""
    return int(round(max(0.0, min(1.0, frac)) * 255))


# --------------------------------------------------------------------------- #
# E/S
# --------------------------------------------------------------------------- #

def save_png(img: Image.Image, path: Path | str) -> Path:
    """Sauve en PNG-32 sans perte (RGBA garanti). Crée les dossiers parents."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    # compress_level par défaut = sans perte (PNG est toujours lossless) ; on
    # garde le blanc pur intact pour d'éventuels flashs.
    img.save(path, format="PNG", optimize=True)
    return path


def new_canvas(w: int, h: int, rgba: tuple[int, int, int, int] = (0, 0, 0, 0)) -> Image.Image:
    """Canvas RGBA uni (transparent par défaut)."""
    return Image.new("RGBA", (w, h), rgba)


def solid(w: int, h: int, rgba: tuple[int, int, int, int]) -> Image.Image:
    return Image.new("RGBA", (w, h), rgba)


# --------------------------------------------------------------------------- #
# Champs de distance / interpolation
# --------------------------------------------------------------------------- #

def smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    """Hermite smoothstep vectorisé, renvoie un tableau dans [0,1]."""
    if edge1 == edge0:
        return (x >= edge1).astype(np.float64)
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def radial_distance(
    w: int, h: int, center: tuple[float, float] | None = None, normalize: str = "corner"
) -> np.ndarray:
    """Tableau (h, w) de distance radiale normalisée.

    normalize="corner" : 1.0 au coin le plus éloigné du centre.
    normalize="half"   : 1.0 au milieu du bord le plus proche (cercle inscrit).
    normalize="none"   : distance en pixels.
    """
    cx, cy = center if center else ((w - 1) / 2.0, (h - 1) / 2.0)
    ys, xs = np.mgrid[0:h, 0:w]
    d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    if normalize == "corner":
        norm = np.sqrt(max(cx, w - 1 - cx) ** 2 + max(cy, h - 1 - cy) ** 2)
    elif normalize == "half":
        norm = min(cx, w - 1 - cx, cy, h - 1 - cy)
    else:
        norm = 1.0
    return d / norm if norm else d


# --------------------------------------------------------------------------- #
# Vignettes & gradients (overlays, freeze, désaturation)
# --------------------------------------------------------------------------- #

def vignette(
    w: int,
    h: int,
    color: str | tuple[int, int, int],
    max_alpha: float,
    inner: float,
    outer: float,
    *,
    normalize: str = "corner",
) -> Image.Image:
    """Vignette radiale : centre transparent -> `color` à `max_alpha` aux bords.

    inner/outer sont des fractions de la distance normalisée (ex. 0.75, 0.90).
    Transparent pour d<inner, plein (max_alpha) pour d>=outer, dégradé entre.
    max_alpha est une FRACTION d'opacité [0,1] (ex. 0.03 = 3%).
    """
    rgb = hex_to_rgb(color) if isinstance(color, str) else color
    d = radial_distance(w, h, normalize=normalize)
    ramp = smoothstep(inner, outer, d)  # 0..1
    alpha = (ramp * frac_to_alpha(max_alpha)).round().astype(np.uint8)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = rgb
    arr[..., 3] = alpha
    return Image.fromarray(arr, "RGBA")


def radial_gray(
    size: int, gamma: float = 1.0, *, invert: bool = False, normalize: str = "half"
) -> Image.Image:
    """Texture de désaturation : gradient radial niveaux de gris, alpha plein.

    Centre blanc (#FFF) -> bord noir (#000) avec courbe pow(d, gamma).
    invert=True : centre noir -> bord blanc.
    Le canal alpha est 255 partout (c'est un masque d'intensité lookup).
    """
    d = np.clip(radial_distance(size, size, normalize=normalize), 0.0, 1.0)
    v = np.power(d, gamma)
    val = v if invert else (1.0 - v)
    g = (val * 255).round().astype(np.uint8)
    arr = np.zeros((size, size, 4), dtype=np.uint8)
    arr[..., 0] = arr[..., 1] = arr[..., 2] = g
    arr[..., 3] = 255
    return Image.fromarray(arr, "RGBA")


# --------------------------------------------------------------------------- #
# Anneaux & disques doux (ondes de choc, compression, particules)
# --------------------------------------------------------------------------- #

def ring(
    size: int,
    radius: float,
    thickness: float,
    color: str | tuple[int, int, int],
    alpha: int = 255,
    *,
    center: tuple[float, float] | None = None,
) -> Image.Image:
    """Anneau antialiasé (bord seulement) sur canvas transparent `size`×`size`.

    `thickness` = largeur totale de l'anneau en px (réparti autour de `radius`).
    """
    rgb = hex_to_rgb(color) if isinstance(color, str) else color
    d = radial_distance(size, size, center=center, normalize="none")
    half = thickness / 2.0
    # couverture : 1 au centre de l'anneau, fondu sur ~1px de chaque côté.
    cov = np.clip(1.0 - (np.abs(d - radius) - half) / 1.0, 0.0, 1.0)
    a = (cov * alpha).round().astype(np.uint8)
    arr = np.zeros((size, size, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = rgb
    arr[..., 3] = a
    return Image.fromarray(arr, "RGBA")


def soft_disc(
    size: int,
    radius: float,
    color: str | tuple[int, int, int],
    *,
    center_alpha: int = 255,
    edge_alpha: int = 0,
    gamma: float = 1.0,
    center: tuple[float, float] | None = None,
) -> Image.Image:
    """Disque à dégradé radial doux (brillant au centre -> transparent au bord).

    Pour les particules 'âme'/'énergie'. alpha interpolé de center_alpha (d=0)
    à edge_alpha (d=radius) avec courbe pow.
    """
    rgb = hex_to_rgb(color) if isinstance(color, str) else color
    d = radial_distance(size, size, center=center, normalize="none")
    t = np.clip(d / radius, 0.0, 1.0) ** gamma
    a = (center_alpha + (edge_alpha - center_alpha) * t).round().astype(np.uint8)
    a[d > radius] = edge_alpha
    arr = np.zeros((size, size, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = rgb
    arr[..., 3] = a
    return Image.fromarray(arr, "RGBA")


# --------------------------------------------------------------------------- #
# Sphère — surface + normales pour filaments sur la courbure
# --------------------------------------------------------------------------- #

@dataclass
class Sphere:
    image: Image.Image          # RGBA, sphère sur canvas transparent
    cx: float
    cy: float
    radius: float
    inside: np.ndarray          # masque bool (h, w) des pixels de la sphère
    nx: np.ndarray              # normales (h, w) — composantes x/y/z (NaN dehors)
    ny: np.ndarray
    nz: np.ndarray


def sphere(
    diameter: int,
    base: str | tuple[int, int, int],
    *,
    canvas_size: int | None = None,
    noise_pct: float = 0.02,
    light: str | tuple[int, int, int] | None = None,
    light_dir: tuple[float, float, float] = (-0.5, -0.5, 1.0),
    seed: int = 0,
    brightness: float = 1.0,
) -> Sphere:
    """Sphère parfaite éclairée subtilement (dégradé interne très comprimé).

    base       : couleur de fond (ex. #050508).
    noise_pct  : variation aléatoire de luminance (2% = 0.02), seedée.
    light      : couleur du point le plus 'clair' (ex. #080810) ; dégradé interne
                 TRÈS subtil orienté par light_dir (haut-gauche par défaut).
    brightness : multiplicateur global de luminance.
    Renvoie un objet Sphere (image + géométrie + normales pour les filaments).
    """
    cs = canvas_size or diameter
    cx = cy = (cs - 1) / 2.0
    R = diameter / 2.0
    base_rgb = np.array(hex_to_rgb(base) if isinstance(base, str) else base, dtype=np.float64)
    light_rgb = (
        np.array(hex_to_rgb(light) if isinstance(light, str) else light, dtype=np.float64)
        if light is not None
        else base_rgb.copy()
    )

    ys, xs = np.mgrid[0:cs, 0:cs]
    dx = (xs - cx) / R
    dy = (ys - cy) / R
    rr = dx * dx + dy * dy
    inside = rr <= 1.0

    nz = np.sqrt(np.clip(1.0 - rr, 0.0, 1.0))
    nx = np.where(inside, dx, np.nan)
    ny = np.where(inside, dy, np.nan)
    nzf = np.where(inside, nz, np.nan)

    # éclairage : t = max(0, N·L) normalisé, mais TRÈS comprimé (subtil).
    L = np.array(light_dir, dtype=np.float64)
    L = L / np.linalg.norm(L)
    dot = np.clip(dx * L[0] + dy * L[1] + nz * L[2], 0.0, 1.0)
    t = dot[..., None]  # (cs, cs, 1)

    rgb = base_rgb[None, None, :] + (light_rgb - base_rgb)[None, None, :] * t

    # bruit de luminance déterministe.
    if noise_pct > 0:
        rng = np.random.default_rng(seed)
        noise = 1.0 + (rng.random((cs, cs)) * 2.0 - 1.0) * noise_pct
        rgb = rgb * noise[..., None]

    rgb = np.clip(rgb * brightness, 0, 255)

    # alpha antialiasé sur ~1px au bord (pas de contour dur).
    d_px = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    alpha = np.clip(R - d_px + 0.5, 0.0, 1.0) * 255.0

    arr = np.zeros((cs, cs, 4), dtype=np.uint8)
    arr[..., :3] = rgb.round().astype(np.uint8)
    arr[..., 3] = alpha.round().astype(np.uint8)
    img = Image.fromarray(arr, "RGBA")
    return Sphere(img, cx, cy, R, inside, nx, ny, nzf)


# --------------------------------------------------------------------------- #
# Transformations colorimétriques (recolor, désaturation, teinte)
# --------------------------------------------------------------------------- #

def adjust_brightness(img: Image.Image, factor: float) -> Image.Image:
    """Multiplie la luminance RGB par `factor`, alpha inchangé."""
    arr = np.asarray(img.convert("RGBA"), dtype=np.float64)
    arr[..., :3] = np.clip(arr[..., :3] * factor, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def _luminance(arr: np.ndarray) -> np.ndarray:
    """Luminance perceptuelle [0,1] depuis un tableau RGBA float (canaux 0-255)."""
    return (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]) / 255.0


def duotone(
    img: Image.Image,
    shadow_hex: str,
    mid_hex: str,
    highlight_hex: str,
    blend: float = 0.7,
) -> Image.Image:
    """Mapping luminance -> 3 arrêts de couleur (ombre / médium / haute lumière).

    La luminance perceptuelle de chaque pixel pilote une interpolation :
      - [0, 0.5]   : shadow_hex -> mid_hex
      - [0.5, 1.0] : mid_hex    -> highlight_hex
    Le résultat est mélangé avec l'original FORTEMENT désaturé selon `blend`
    (blend=0.7 -> 70% duotone / 30% désaturé). Alpha préservé.
    """
    a = np.asarray(img.convert("RGBA")).astype(float)
    rgb, alpha = a[..., :3], a[..., 3:4]
    t = _luminance(a)[..., None]  # 0..1
    shadow = np.array(hex_to_rgb(shadow_hex), dtype=float)
    mid = np.array(hex_to_rgb(mid_hex), dtype=float)
    highlight = np.array(hex_to_rgb(highlight_hex), dtype=float)
    lo = shadow + (mid - shadow) * (np.clip(t, 0, 0.5) / 0.5)
    hi = mid + (highlight - mid) * (np.clip(t - 0.5, 0, 0.5) / 0.5)
    duo = np.where(t < 0.5, lo, hi)
    g = t * 255.0
    desat = rgb * 0.3 + g * 0.7  # original fortement désaturé
    out = duo * blend + desat * (1.0 - blend)
    res = np.concatenate([np.clip(out, 0, 255), alpha], axis=-1).astype("uint8")
    return Image.fromarray(res, "RGBA")


def desaturate(img: Image.Image, factor: float) -> Image.Image:
    """Réduit la saturation de `factor` (0 = inchangé, 1 = niveaux de gris).

    Alpha préservé.
    """
    rgb = ImageEnhance.Color(img.convert("RGB")).enhance(1.0 - factor)
    return Image.merge("RGBA", (*rgb.split(), img.convert("RGBA").split()[3]))


def tint(img: Image.Image, hex_col: str, frac: float) -> Image.Image:
    """Mélange chaque pixel non transparent vers `hex_col` à hauteur de `frac`.

    Alpha préservé ; seuls les pixels opaques (alpha > 0) sont teintés.
    """
    a = np.asarray(img.convert("RGBA")).astype(float)
    col = np.array(hex_to_rgb(hex_col), dtype=float)
    m = a[..., 3:4] > 0
    a[..., :3] = np.where(m, a[..., :3] * (1 - frac) + col * frac, a[..., :3])
    return Image.fromarray(a.astype("uint8"), "RGBA")


# --------------------------------------------------------------------------- #
# Spritesheets
# --------------------------------------------------------------------------- #

def hsheet(frames: list[Image.Image]) -> Image.Image:
    """Concatène des frames de même taille en une bande horizontale."""
    w, h = frames[0].size
    sheet = new_canvas(w * len(frames), h)
    for i, f in enumerate(frames):
        sheet.alpha_composite(f.convert("RGBA"), (i * w, 0))
    return sheet


def grid_sheet(frames: list[Image.Image], cols: int, rows: int) -> Image.Image:
    """Place des frames de même taille dans une grille cols×rows (ligne par ligne)."""
    w, h = frames[0].size
    sheet = new_canvas(w * cols, h * rows)
    for i, f in enumerate(frames):
        r, c = divmod(i, cols)
        sheet.alpha_composite(f.convert("RGBA"), (c * w, r * h))
    return sheet


# --------------------------------------------------------------------------- #
# Texte
# --------------------------------------------------------------------------- #

_FONTS = ("arialbd.ttf", "seguisb.ttf", "consolab.ttf")


def load_font(size: int, candidates: tuple[str, ...] = _FONTS) -> ImageFont.FreeTypeFont:
    """Charge une police bold Windows ; fallback police bitmap PIL."""
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def centered_text(
    w: int,
    h: int,
    text: str,
    color: str | tuple[int, int, int],
    font: ImageFont.FreeTypeFont,
    *,
    alpha: int = 255,
) -> Image.Image:
    """Rend `text` centré sur un canvas transparent w×h."""
    rgb = hex_to_rgb(color) if isinstance(color, str) else color
    img = new_canvas(w, h)
    draw = ImageDraw.Draw(img)
    box = draw.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    x = (w - tw) / 2 - box[0]
    y = (h - th) / 2 - box[1]
    draw.text((x, y), text, fill=(*rgb, alpha), font=font)
    return img


# --------------------------------------------------------------------------- #
# Étoile à n branches
# --------------------------------------------------------------------------- #

def star_points(
    cx: float, cy: float, r_outer: float, r_inner: float, n: int = 5, rot: float = -np.pi / 2
) -> list[tuple[float, float]]:
    """Sommets d'une étoile à `n` branches (alternance rayon ext/int)."""
    pts = []
    for i in range(n * 2):
        r = r_outer if i % 2 == 0 else r_inner
        a = rot + i * np.pi / n
        pts.append((cx + r * np.cos(a), cy + r * np.sin(a)))
    return pts


# --------------------------------------------------------------------------- #
# Normalisation sur canvas fixe (placement cohérent moteur — Godot Sprite2D…)
# --------------------------------------------------------------------------- #

def fit_to_canvas(
    img: Image.Image,
    canvas_w: int,
    canvas_h: int,
    *,
    anchor: str = "bottom",
    fill: float = 0.95,
    margin: int = 0,
) -> Image.Image:
    """Place `img` (RVBA, déjà détouré) sur un canvas fixe canvas_w×canvas_h.

    Le sujet est redimensionné EN PRÉSERVANT le ratio pour occuper `fill` de la
    hauteur disponible (canvas_h - 2*margin), centré horizontalement, et ancré :
      - "bottom" : pieds collés au bas (jeux à personnages debout / fenêtre) ;
      - "center" : centré (objets/stations) ;
      - "top"    : tête en haut.
    Garantit que TOUS les assets d'un type ont la MÊME taille de canvas → rendu
    cohérent quand le moteur applique un scale fixe (ex. Godot Sprite2D scale 0.4).
    On rogne d'abord les marges transparentes du sujet (bbox) pour un cadrage net.
    """
    src = img.convert("RGBA")
    bbox = src.getbbox()
    if bbox:
        src = src.crop(bbox)
    avail_h = canvas_h - 2 * margin
    scale = (avail_h * fill) / src.height
    # ne déborde jamais en largeur
    max_w = canvas_w - 2 * margin
    if src.width * scale > max_w:
        scale = max_w / src.width
    nw, nh = max(1, round(src.width * scale)), max(1, round(src.height * scale))
    resized = src.resize((nw, nh), Image.LANCZOS)
    canvas = new_canvas(canvas_w, canvas_h)
    x = (canvas_w - nw) // 2
    if anchor == "bottom":
        y = canvas_h - margin - nh
    elif anchor == "top":
        y = margin
    else:  # center
        y = (canvas_h - nh) // 2
    canvas.alpha_composite(resized, (x, y))
    return canvas


def cover_resize(img: Image.Image, w: int, h: int) -> Image.Image:
    """Redimensionne `img` pour COUVRIR exactement w×h (préserve le ratio, rogne
    le débord) — équivalent de `keep_aspect_covered`. Pour les fonds plein écran."""
    src = img.convert("RGBA")
    scale = max(w / src.width, h / src.height)
    nw, nh = round(src.width * scale), round(src.height * scale)
    resized = src.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return resized.crop((left, top, left + w, top + h))


__all__ = [
    # couleurs
    "hex_to_rgb",
    "hex_to_rgba",
    "frac_to_alpha",
    # E/S
    "save_png",
    "new_canvas",
    "solid",
    # distance / interpolation
    "smoothstep",
    "radial_distance",
    # vignettes & gradients
    "vignette",
    "radial_gray",
    # anneaux & disques
    "ring",
    "soft_disc",
    # sphère
    "Sphere",
    "sphere",
    # colorimétrie
    "adjust_brightness",
    "duotone",
    "desaturate",
    "tint",
    # spritesheets
    "hsheet",
    "grid_sheet",
    # texte
    "load_font",
    "centered_text",
    # géométrie
    "star_points",
    # normalisation canvas (placement moteur cohérent)
    "fit_to_canvas",
    "cover_resize",
]

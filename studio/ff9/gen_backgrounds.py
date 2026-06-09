"""Génère les OVERLAYS de décors PROCÉDURAUX du mod « La Troisième Fissure ».

Technique « Palimpseste » : un CALQUE 0 (décor Moguri original, hors périmètre)
+ des overlays PNG à canal alpha. Ce module ne produit QUE les overlays
définissables géométriquement ou par gradient (lignes, fissures, désaturation,
vide progressif, teintes, ombres doubles, halos). Tout contenu figuratif
(flammes, ruines, fontaine, barricades, réfugiés, tour de guet, journaux,
cartes, ciel peint, plateforme cristal…) est SKIPPÉ — il requiert un artiste.

Noms/dimensions repris EXACTEMENT des 3 _MANIFEST.txt (act1/act2/act3).
Tout aléatoire passe par un RNG seedé -> rendu strictement déterministe.

⚠️ Versions « génériques » signalées : faute d'accès au calque 0 Moguri, les
overlays dont la spec dit « suivre l'architecture de la scène » / « les zones
d'ombre existantes » / « les objets meublés » sont produits en perspective
centrale générique (point de fuite au centre, distribution seedée). Voir les
commentaires GÉNÉRIQUE ci-dessous.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from studio.ff9 import common as c

# --------------------------------------------------------------------------- #
# Constantes palette (manifestes)
# --------------------------------------------------------------------------- #
SIGNATURE = "#2D0A47"   # violet contamination Troisième Monde
CRYSTAL_GLOW = "#0F3460"  # bleu cristal sain (bords de fissure)
MEMORIA_LINE = "#E8E8F0"  # blanc bleuté (lignes doubles Memoria)
SHADOW_NORMAL = "#1A1A1A"  # ombre normale Ipsen
SAFE_AMBER = "#C8823A"  # ambre zone sûre

SS = 2  # supersampling pour l'antialiasing des traits 1px (×2 puis LANCZOS)

# Sous-dossiers d'actes (== noms de dossiers des manifestes).
DIR_ACT1 = "act1_alexandria"
DIR_ACT2 = "act2_treno_ipsens"
DIR_ACT3 = "act3_crystal_memoria_threshold"


# --------------------------------------------------------------------------- #
# Outils internes
# --------------------------------------------------------------------------- #
def _supersampled(w: int, h: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Canvas transparent ×SS prêt à dessiner (à réduire ensuite en LANCZOS)."""
    img = c.new_canvas(w * SS, h * SS)
    return img, ImageDraw.Draw(img)


def _reduce(img: Image.Image, w: int, h: int) -> Image.Image:
    return img.resize((w, h), Image.LANCZOS)


def _zigzag(
    rng: np.random.Generator, x0: float, y0: float, length: float, segs: int
) -> list[tuple[float, float]]:
    """Polyligne anguleuse (zigzag) partant de (x0,y0), orientation aléatoire."""
    pts = [(x0, y0)]
    ang = rng.uniform(0, 2 * np.pi)
    seg_len = length / segs
    x, y = x0, y0
    for _ in range(segs):
        ang += rng.uniform(-1.1, 1.1)  # cassures angulaires marquées
        x += seg_len * np.cos(ang)
        y += seg_len * np.sin(ang)
        pts.append((x, y))
    return pts


# --------------------------------------------------------------------------- #
# ACTE I
# --------------------------------------------------------------------------- #
def _alexandria_ext_capillary(w: int, h: int) -> Image.Image:
    """F1 — lignes capillaires violettes #2D0A47, 1px, 40%, couvrant ~20%.

    GÉNÉRIQUE : faute de la grille des dalles du calque 0, on trace des fines
    lignes irrégulières orientées majoritairement selon deux axes de dalles
    (pseudo-grille en perspective) + déviations, concentrées dans la moitié
    basse (la « place » sous les pieds du joueur).
    """
    rng = np.random.default_rng(0xA1EC)
    img, draw = _supersampled(w, h)
    color = (*c.hex_to_rgb(SIGNATURE), c.frac_to_alpha(0.40))

    # Zone traitée : place centrale ~ moitié basse, marges latérales.
    zx0, zx1 = int(w * 0.12 * SS), int(w * 0.88 * SS)
    zy0, zy1 = int(h * 0.45 * SS), int(h * 0.98 * SS)

    # Densité « 1 ligne tous les 4-6px » -> beaucoup de petits segments le long
    # de joints pseudo-grille. Deux familles d'orientation (dalles en losange).
    base_angles = (np.deg2rad(28), np.deg2rad(-28))
    n = 5200  # calibré pour ~20% de couverture visuelle de la zone
    for _ in range(n):
        x = rng.uniform(zx0, zx1)
        y = rng.uniform(zy0, zy1)
        a = rng.choice(base_angles) + rng.uniform(-0.18, 0.18)  # suit puis dévie
        ln = rng.uniform(6, 18) * SS
        x2 = x + ln * np.cos(a)
        y2 = y + ln * np.sin(a)
        draw.line([(x, y), (x2, y2)], fill=color, width=SS)

    return _reduce(img, w, h)


def _alexandria_castle_tint(w: int, h: int) -> Image.Image:
    """F2 — teinte #2D0A47 +8% dans les zones d'ombre des tours.

    GÉNÉRIQUE : sans le calque 0, on ne connaît pas les ombres réelles des
    tours. On produit une teinte douce #2D0A47 8% concentrée dans la moitié
    haute (silhouette des tours) avec un masque vertical en bandes douces
    (approximant des fûts de tours) — imperceptible, perceptible au second
    regard, conforme à l'intention.
    """
    rgb = c.hex_to_rgb(SIGNATURE)
    ys, xs = np.mgrid[0:h, 0:w]

    # Atténuation verticale : plein en haut (tours/ombres) -> 0 vers le sol.
    vfall = c.smoothstep(h * 0.62, h * 0.05, ys.astype(np.float64))

    # Bandes verticales douces = fûts de tours génériques (déterministe).
    centers = np.array([0.18, 0.38, 0.5, 0.62, 0.82]) * w
    band = np.zeros((h, w), dtype=np.float64)
    for cxv in centers:
        band += np.exp(-((xs - cxv) ** 2) / (2 * (w * 0.05) ** 2))
    band = np.clip(band, 0.0, 1.0)

    mask = vfall * band
    alpha = (mask * c.frac_to_alpha(0.08)).round().astype(np.uint8)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = rgb
    arr[..., 3] = alpha
    return Image.fromarray(arr, "RGBA")


# --------------------------------------------------------------------------- #
# ACTE II
# --------------------------------------------------------------------------- #
def _treno_sky_layer2(w: int, h: int) -> Image.Image:
    """F3 — overlay #2D0A47 8% sur ~60% central du ciel (bords épargnés)."""
    rgb = c.hex_to_rgb(SIGNATURE)
    xs = np.arange(w, dtype=np.float64)[None, :].repeat(h, axis=0)

    # 60% central : plein entre 20% et 80% de la largeur, fondu sur les bords.
    edge = w * 0.20
    left = c.smoothstep(0.0, edge, xs)
    right = c.smoothstep(0.0, edge, (w - 1) - xs)
    mask = np.minimum(left, right)

    alpha = (mask * c.frac_to_alpha(0.08)).round().astype(np.uint8)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = rgb
    arr[..., 3] = alpha
    return Image.fromarray(arr, "RGBA")


def _ipsens_double_shadow(w: int, h: int) -> Image.Image:
    """F6 — ombres doubles : normale #1A1A1A 50% + impossible #2D0A47 30%.

    GÉNÉRIQUE : sans les objets meublés du calque 0, on ne peut pas projeter
    les vraies ombres. On distribue des « pieds d'objets » génériques (ellipses
    seedées) au sol, et pour chacun on trace :
      - ombre NORMALE : ellipse #1A1A1A 50% décalée bas-gauche (lumière
        haut-droite, angle standard).
      - ombre IMPOSSIBLE : ellipse #2D0A47 30% décalée 12px bas-gauche
        SUPPLÉMENTAIRES (source inexistante) — l'ombre « hésite ».
    """
    rng = np.random.default_rng(0x1D5E)
    img, draw = _supersampled(w, h)
    cn = (*c.hex_to_rgb(SHADOW_NORMAL), c.frac_to_alpha(0.50))
    ci = (*c.hex_to_rgb(SIGNATURE), c.frac_to_alpha(0.30))

    n_objs = 22
    for _ in range(n_objs):
        # base d'objet quelque part dans la salle (privilégier moitié basse).
        bx = rng.uniform(0.05, 0.95) * w
        by = rng.uniform(0.45, 0.92) * h
        ow = rng.uniform(28, 70)   # empreinte au sol
        oh = ow * rng.uniform(0.35, 0.55)

        # Ombre normale : lumière haut-droite -> ombre vers bas-gauche (~14px).
        nx, ny = bx - 14, by + 8
        # Ombre impossible : 12px bas-gauche EN PLUS (source impossible).
        ix, iy = nx - 12, ny + 12

        def ell(cx, cy, fill):
            box = [
                (cx - ow / 2) * SS, (cy - oh / 2) * SS,
                (cx + ow / 2) * SS, (cy + oh / 2) * SS,
            ]
            draw.ellipse(box, fill=fill)

        # On dessine l'impossible d'abord (dessous), puis la normale.
        ell(ix, iy, ci)
        ell(nx, ny, cn)

    out = _reduce(img, w, h)
    # léger flou : ombres molles plutôt que des disques nets.
    return out.filter(ImageFilter.GaussianBlur(radius=1.2))


def _ipsens_safe_zone(w: int, h: int) -> Image.Image:
    """F7 — disque ambré #C8823A 10%, rayon 60px, dégradé vers le centre.

    Spec : « bords dégradé transparent VERS le centre » -> anneau lumineux au
    bord du disque (r=60), s'estompant vers le centre et au-delà du rayon.
    """
    rgb = c.hex_to_rgb(SAFE_AMBER)
    d = c.radial_distance(w, h, normalize="none")  # px depuis le centre
    radius = 60.0
    # pic d'intensité sur l'anneau r≈60, fondu de part et d'autre (~16px).
    band = np.clip(1.0 - np.abs(d - radius) / 24.0, 0.0, 1.0)
    band[d > radius] = np.clip(1.0 - (d[d > radius] - radius) / 8.0, 0.0, 1.0)
    alpha = (band * c.frac_to_alpha(0.10)).round().astype(np.uint8)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = rgb
    arr[..., 3] = alpha
    return Image.fromarray(arr, "RGBA")


# --------------------------------------------------------------------------- #
# ACTE III — Crystal World
# --------------------------------------------------------------------------- #
def _crystal_cracks(w: int, h: int) -> Image.Image:
    """F2 — fissures géométriques sur la moitié DROITE (corrompue) uniquement.

    Par fissure : zigzag 1-2px #2D0A47, bordé 1px de chaque côté par #0F3460
    (lueur cristal). On trace d'abord la lueur (trait plus large) puis le cœur.
    """
    rng = np.random.default_rng(0xC3AC)
    img, draw = _supersampled(w, h)
    core = (*c.hex_to_rgb(SIGNATURE), c.frac_to_alpha(0.90))
    glow = (*c.hex_to_rgb(CRYSTAL_GLOW), c.frac_to_alpha(0.55))

    # Moitié droite seulement (corrompue), point de départ x>=680px.
    n = 60
    for _ in range(n):
        x0 = rng.uniform(0.53, 0.96) * w * SS
        y0 = rng.uniform(0.08, 0.92) * h * SS
        length = rng.uniform(20, 60) * SS
        segs = rng.integers(3, 6)
        pts = _zigzag(rng, x0, y0, length, int(segs))
        thick = rng.integers(1, 3)  # 1-2px (×SS)
        # lueur dessous (2px plus large), puis cœur.
        draw.line(pts, fill=glow, width=int(thick) * SS + 2 * SS, joint="curve")
        draw.line(pts, fill=core, width=int(thick) * SS, joint="curve")

    return _reduce(img, w, h)


# --------------------------------------------------------------------------- #
# ACTE III — Memoria
# --------------------------------------------------------------------------- #
def _memoria_corrupted_zones(w: int, h: int) -> Image.Image:
    """F4 — taches de désaturation couvrant ~30%, gris #808080, contours flous.

    CHOIX documenté : ce layer est un overlay GRIS #808080 dont l'ALPHA est un
    masque de taches (gaussiennes seedées floutées), à blender sur le calque 0
    pour « éteindre » les zones. Couverture visée ≈30% de la surface ; alpha
    max ~80% (la zone semble morte sans être 100% N&B, cf. note manifest).
    """
    rng = np.random.default_rng(0x3E3A)
    # Masque numpy : somme de disques gaussiens, ~30% de couverture.
    mask = np.zeros((h, w), dtype=np.float64)
    ys, xs = np.mgrid[0:h, 0:w]
    n_blobs = 9
    for _ in range(n_blobs):
        cx = rng.uniform(0.05, 0.95) * w
        cy = rng.uniform(0.05, 0.95) * h
        # diamètre 100-400px -> sigma ~ diam/4.
        sigma = rng.uniform(100, 400) / 4.0
        mask += np.exp(-((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * sigma ** 2))

    # binariser doucement -> taches franches à contours flous (1-2px en dégradé).
    mask = c.smoothstep(0.30, 0.62, mask)  # bords doux ; seuil bas -> ~30% couverts
    alpha = (mask * c.frac_to_alpha(0.80)).round().astype(np.uint8)

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., 0] = arr[..., 1] = arr[..., 2] = 0x80  # gris moyen #808080
    arr[..., 3] = alpha
    img = Image.fromarray(arr, "RGBA")
    # flou final léger pour des contours en dégradé propres.
    return img.filter(ImageFilter.GaussianBlur(radius=1.5))


def _memoria_double_lines(w: int, h: int) -> Image.Image:
    """F5 — lignes d'architecture dédoublées : #E8E8F0 1px 15%, copie +3px BD.

    GÉNÉRIQUE : sans les lignes de perspective réelles du calque 0, on génère
    une perspective centrale générique (faisceau de diagonales depuis un point
    de fuite + horizontales) et on double chaque trait avec un décalage de 3px
    bas-droite -> architecture « fantôme ».
    """
    img, draw = _supersampled(w, h)
    color = (*c.hex_to_rgb(MEMORIA_LINE), c.frac_to_alpha(0.15))
    cw, ch = w * SS, h * SS
    cx, cy = (cw - 1) / 2.0, (ch - 1) / 2.0
    diag = (cw ** 2 + ch ** 2) ** 0.5
    off = 3 * SS  # décalage bas-droite

    def dbl(p0, p1):
        draw.line([p0, p1], fill=color, width=SS)
        draw.line(
            [(p0[0] + off, p0[1] + off), (p1[0] + off, p1[1] + off)],
            fill=color, width=SS,
        )

    # Faisceau de perspective (point de fuite central).
    n_rays = 40
    for i in range(n_rays):
        a = 2.0 * np.pi * i / n_rays
        dbl((cx, cy), (cx + diag * np.cos(a), cy + diag * np.sin(a)))

    # Horizontales régulières (~110px en ×1).
    step = 110 * SS
    y = step // 2
    while y < ch:
        dbl((0, y), (cw, y))
        y += step

    return _reduce(img, w, h)


def _memoria_void(w: int, h: int) -> Image.Image:
    """F6 — vide #000000 progressant des 4 bords, dégradé sur 20% (256/192px).

    Spec exacte : gauche 0->256, droite 1280->1024, haut 0->192, bas 960->768.
    Champ alpha = max des 4 rampes smoothstep (opaque au bord -> transparent).
    """
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    # Chaque rampe : 1 au bord -> 0 à la distance d'arrêt. inner_px = 20% dim.
    ix = w * 0.20  # 256 pour 1280
    iy = h * 0.20  # 192 pour 960
    left = 1.0 - c.smoothstep(0.0, ix, xs)
    right = 1.0 - c.smoothstep(0.0, ix, (w - 1) - xs)
    top = 1.0 - c.smoothstep(0.0, iy, ys)
    bottom = 1.0 - c.smoothstep(0.0, iy, (h - 1) - ys)
    field = np.maximum.reduce([left, right, top, bottom])

    alpha = (field * 255).round().astype(np.uint8)
    arr = np.zeros((h, w, 4), dtype=np.uint8)  # RGB=#000000
    arr[..., 3] = alpha
    return Image.fromarray(arr, "RGBA")


# --------------------------------------------------------------------------- #
# ACTE III — Le Seuil
# --------------------------------------------------------------------------- #
def _threshold_void(w: int, h: int) -> Image.Image:
    """F8 — fond noir absolu #000000 + 8-12 particules #2D0A47 2×2px.

    Le fond #000000 est PLEIN (opaque) : c'est le « fond de vide » statique du
    Seuil. Quelques particules violettes statiques (animées par shader runtime).
    """
    rng = np.random.default_rng(0x5EE1)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., 3] = 255  # noir pur opaque
    img = Image.fromarray(arr, "RGBA")
    draw = ImageDraw.Draw(img)

    n = int(rng.integers(8, 13))  # 8-12 particules
    pr, pg, pb = c.hex_to_rgb(SIGNATURE)
    for _ in range(n):
        x = int(rng.uniform(0, w - 2))
        y = int(rng.uniform(0, h - 2))
        a = c.frac_to_alpha(rng.uniform(0.40, 0.80))
        draw.rectangle([x, y, x + 1, y + 1], fill=(pr, pg, pb, a))  # 2×2 px
    return img


def _threshold_fissure(w: int, h: int) -> Image.Image:
    """F9 — fissure verticale étroite #2D0A47 + RGB shift 2px aux bords.

    Déchirure verticale (ouverture 4-12px) centrée, hauteur ~65% du canvas.
    Intérieur #2D0A47 pur (aura interne -> #3D1A57), bords avec aberration
    chromatique : fringe rouge à gauche (-2px), fringe cyan à droite (+2px).
    Construit par canaux numpy pour un RGB shift propre.
    """
    rng = np.random.default_rng(0xF155)
    cx = w / 2.0
    y_top = h * 0.175
    y_bot = h * 0.825  # ~65% de hauteur, centrée

    inner = np.array(c.hex_to_rgb(SIGNATURE), dtype=np.float64)
    aura = np.array(c.hex_to_rgb("#3D1A57"), dtype=np.float64)

    ys = np.arange(h)
    # demi-largeur par ligne : plus large au centre vertical (2-6px -> 4-12 tot).
    halfw = np.zeros(h)
    inb = (ys >= y_top) & (ys <= y_bot)
    tt = (ys - y_top) / max(1.0, (y_bot - y_top))
    profile = np.sin(np.clip(tt, 0, 1) * np.pi)  # 0 aux extrémités, 1 au milieu
    # +bruit seedé léger sur le contour (irrégulier).
    noise = rng.uniform(-0.6, 0.6, size=h)
    halfw[inb] = (2.0 + 4.0 * profile[inb]) + noise[inb]
    halfw = np.clip(halfw, 0.0, None)

    xs = np.arange(w)[None, :]
    cxs = np.abs(xs - cx)  # distance horizontale au centre
    hw = halfw[:, None]
    interior = (hw > 0) & (cxs <= hw)

    # alpha intérieur plein ; aura : dégradé depuis le bord interne vers centre.
    a_field = np.zeros((h, w))
    a_field[interior] = 1.0

    rgb = np.zeros((h, w, 3))
    # mélange inner->aura selon proximité du bord (bords plus clairs = aura).
    with np.errstate(invalid="ignore", divide="ignore"):
        edge_t = np.where(hw > 0, cxs / np.maximum(hw, 1e-6), 0.0)  # 0 centre,1 bord
    edge_t = np.clip(edge_t, 0, 1)
    blend = edge_t[..., None]
    rgb = inner[None, None, :] * (1 - blend) + aura[None, None, :] * blend

    arr = np.zeros((h, w, 4))
    arr[..., :3] = rgb
    arr[..., 3] = a_field * 255

    img = Image.fromarray(arr.round().astype(np.uint8), "RGBA")

    # RGB shift 2px : fringe rouge -2px (gauche), fringe cyan +2px (droite).
    base = np.asarray(img, dtype=np.uint8)
    r = np.roll(base[..., 0], -2, axis=1)
    g = np.roll(base[..., 1], 2, axis=1)
    b = np.roll(base[..., 2], 2, axis=1)
    # alpha élargi pour couvrir les bords décalés (union des alphas roulés).
    a0 = base[..., 3]
    a = np.maximum.reduce([a0, np.roll(a0, -2, axis=1), np.roll(a0, 2, axis=1)])
    shifted = np.dstack([r, g, b, a]).astype(np.uint8)
    return Image.fromarray(shifted, "RGBA")


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
# (sous-dossier, nom de fichier, dims, fonction génératrice)
_SPECS: tuple[tuple[str, str, tuple[int, int], object], ...] = (
    # Acte I
    (DIR_ACT1, "bg_alexandria_ext_layer1_overlay.png", (1280, 960), _alexandria_ext_capillary),
    (DIR_ACT1, "bg_alexandria_castle_layer1_overlay.png", (1280, 960), _alexandria_castle_tint),
    # Acte II
    (DIR_ACT2, "bg_treno_sky_layer2.png", (1280, 240), _treno_sky_layer2),
    (DIR_ACT2, "bg_ipsens_double_shadow.png", (1280, 960), _ipsens_double_shadow),
    (DIR_ACT2, "bg_ipsens_safe_zone_indicator.png", (128, 128), _ipsens_safe_zone),
    # Acte III — Crystal / Memoria / Seuil
    (DIR_ACT3, "bg_crystal_world_cracks.png", (1280, 960), _crystal_cracks),
    (DIR_ACT3, "bg_memoria_corrupted_zones.png", (1280, 960), _memoria_corrupted_zones),
    (DIR_ACT3, "bg_memoria_double_lines.png", (1280, 960), _memoria_double_lines),
    (DIR_ACT3, "bg_memoria_void_encroachment.png", (1280, 960), _memoria_void),
    (DIR_ACT3, "bg_threshold_void.png", (1280, 480), _threshold_void),
    (DIR_ACT3, "bg_threshold_fissure_visible.png", (320, 960), _threshold_fissure),
)


def generate(out_root: Path) -> list[Path]:
    """Produit les overlays procéduraux sous `<out_root>/backgrounds/<acte>/`.

    Renvoie la liste des chemins écrits (un par overlay générique/géométrique).
    """
    base = Path(out_root) / "backgrounds"
    paths: list[Path] = []
    for subdir, name, (w, h), fn in _SPECS:
        img = fn(w, h)
        paths.append(c.save_png(img, base / subdir / name))
    return paths

"""Tests des primitives procédurales du CŒUR (`studio.procedural`).

On vérifie :
- le DÉTERMINISME (deux runs -> octets PNG identiques),
- la sémantique de la vignette (transparente au centre, opaque au coin),
- la géométrie de la sphère (bbox alpha == diamètre),
- le mapping duotone (3 arrêts de luminance),
- la garantie RGBA de save_png,
- la rétro-compatibilité de `studio.ff9.common` (même objets ré-exportés).
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

from studio import procedural as p


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Déterminisme : deux runs -> mêmes octets                                     #
# --------------------------------------------------------------------------- #

def test_sphere_deterministe():
    a = p.sphere(48, "#050508", light="#080810", noise_pct=0.05, seed=7)
    b = p.sphere(48, "#050508", light="#080810", noise_pct=0.05, seed=7)
    assert _png_bytes(a.image) == _png_bytes(b.image)


def test_vignette_deterministe():
    a = p.vignette(64, 64, "#2D0A47", 0.2, 0.6, 0.95)
    b = p.vignette(64, 64, "#2D0A47", 0.2, 0.6, 0.95)
    assert _png_bytes(a) == _png_bytes(b)


def test_seed_different_change_resultat():
    a = p.sphere(48, "#050508", light="#FFFFFF", noise_pct=0.1, seed=1)
    b = p.sphere(48, "#050508", light="#FFFFFF", noise_pct=0.1, seed=2)
    assert _png_bytes(a.image) != _png_bytes(b.image)


# --------------------------------------------------------------------------- #
# Vignette : alpha du coin vs centre                                           #
# --------------------------------------------------------------------------- #

def test_vignette_alpha_coin():
    img = p.vignette(64, 64, "#2D0A47", 1.0, 0.5, 1.0, normalize="corner")
    arr = np.asarray(img)
    # centre transparent, coin opaque (max_alpha=1.0 -> 255).
    assert arr[32, 32, 3] == 0
    assert arr[0, 0, 3] == 255
    # la couleur RGB est bien le violet demandé.
    assert tuple(arr[0, 0, :3]) == (0x2D, 0x0A, 0x47)


# --------------------------------------------------------------------------- #
# Sphère : bbox de l'alpha == diamètre                                         #
# --------------------------------------------------------------------------- #

def test_sphere_bbox():
    diameter = 40
    s = p.sphere(diameter, "#101010", noise_pct=0.0)
    assert s.image.size == (diameter, diameter)
    bbox = s.image.getbbox()  # (x0, y0, x1, y1) des pixels alpha > 0
    assert bbox is not None
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    # la bbox couvre tout le diamètre (tolérance antialiasing ~1px).
    assert abs(w - diameter) <= 1
    assert abs(h - diameter) <= 1
    # masque inside cohérent : ~pi/4 de la surface du canvas.
    ratio = s.inside.mean()
    assert abs(ratio - np.pi / 4) < 0.05


# --------------------------------------------------------------------------- #
# Duotone : mapping luminance -> 3 arrêts                                      #
# --------------------------------------------------------------------------- #

def test_duotone_arrets():
    # 3 pixels : noir (lum 0), gris moyen, blanc (lum 1).
    src = Image.fromarray(
        np.array([[[0, 0, 0, 255], [128, 128, 128, 255], [255, 255, 255, 255]]], dtype=np.uint8),
        "RGBA",
    )
    out = p.duotone(src, "#000000", "#2D0A47", "#FFFFFF", blend=1.0)
    arr = np.asarray(out)
    assert arr.shape == (1, 3, 4)
    # blend=1.0 -> 100% duotone. Ombre -> ~noir, médium -> ~violet, haute -> ~blanc.
    assert tuple(arr[0, 0, :3]) == (0, 0, 0)
    # pixel médian proche du violet d'arrêt (lum du gris 128 ~ 0.5).
    assert abs(int(arr[0, 1, 0]) - 0x2D) <= 6
    assert abs(int(arr[0, 1, 1]) - 0x0A) <= 6
    assert abs(int(arr[0, 1, 2]) - 0x47) <= 6
    assert tuple(arr[0, 2, :3]) == (255, 255, 255)
    # alpha préservé.
    assert arr[0, 0, 3] == 255


def test_desaturate_et_tint_preservent_alpha():
    src = Image.fromarray(
        np.array([[[200, 50, 50, 128]]], dtype=np.uint8), "RGBA"
    )
    d = np.asarray(p.desaturate(src, 1.0))
    assert d[0, 0, 3] == 128
    # désaturation totale -> R≈G≈B.
    assert abs(int(d[0, 0, 0]) - int(d[0, 0, 1])) <= 2
    t = np.asarray(p.tint(src, "#0000FF", 1.0))
    assert tuple(t[0, 0, :3]) == (0, 0, 255)
    assert t[0, 0, 3] == 128


# --------------------------------------------------------------------------- #
# save_png : garantit le RGBA                                                  #
# --------------------------------------------------------------------------- #

def test_save_png_rgba(tmp_path):
    rgb = Image.new("RGB", (8, 8), (10, 20, 30))
    out = p.save_png(rgb, tmp_path / "sub" / "x.png")
    assert out.exists()
    reloaded = Image.open(out)
    assert reloaded.mode == "RGBA"


# --------------------------------------------------------------------------- #
# Rétro-compatibilité de la façade studio.ff9.common                           #
# --------------------------------------------------------------------------- #

def test_common_facade_backcompat():
    from studio.ff9 import common as c

    # mêmes objets ré-exportés.
    assert c.sphere is p.sphere
    assert c.vignette is p.vignette
    assert c.Sphere is p.Sphere
    # symboles tiers historiquement exposés via common.
    assert c.Image is Image
    assert hasattr(c, "np")
    # appel concret via la façade.
    s = c.sphere(16, "#050508", noise_pct=0.0)
    assert isinstance(s, p.Sphere)

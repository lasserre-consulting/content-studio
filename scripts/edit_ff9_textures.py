"""Édite des textures de modèles Moguri (transfos globales) et écrit des OVERRIDES mod.

Lit la texture Moguri source (`MoguriMain/.../Models/<grp>/<id>/<id>_<n>.png`),
applique une transformation GLOBALE déterministe (recolor Troisième Monde,
désaturation, teinte), et écrit le résultat :
  - dans le mod : `FF9_Suite/StreamingAssets/Assets/Resources/Models/<grp>/<id>/...`
    (chemin miroir = override chargé par-dessus Moguri si le mod a une priorité
     supérieure dans ModCatalog.xml)
  - et une copie QA dans outputs/ff9/texture_edits/.

⚠️ Transfos GLOBALES uniquement (recolor/desat/teinte). Les ajouts LOCALISÉS
(ruban, étoile, cicatrice) nécessitent un travail UV par modèle, non couvert ici.

Usage : python scripts/edit_ff9_textures.py [--no-mod] [--only 328]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

MOGURI = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY IX\MoguriMain\StreamingAssets\Assets\Resources\Models"
)
MOD = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY IX\FF9_Suite\StreamingAssets\Assets\Resources\Models"
)
OUT = Path(__file__).resolve().parent.parent / "outputs" / "ff9" / "texture_edits"

# Jobs : transfos GLOBALES sur des modèles à l'identité CONFIRMÉE visuellement.
JOBS = [
    # Deathguise Éclaireur (ennemi 500) ← Deathguise base : palette Troisième Monde.
    {"model": "3/328", "textures": ["_0", "_1", "_2"], "transform": "third_world",
     "label": "Deathguise -> Eclaireur (Troisieme Monde)"},
]


def _lum(a: np.ndarray) -> np.ndarray:
    return (0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]) / 255.0


def third_world(img: Image.Image) -> Image.Image:
    """Duotone sur la luminance : ombres->#0A0A0A, mids->#2D0A47, hautes->#C8C8C8.
    Blend 70% duotone / 30% original désaturé. Alpha préservé."""
    a = np.asarray(img.convert("RGBA")).astype(float)
    rgb, alpha = a[..., :3], a[..., 3:4]
    t = _lum(a)[..., None]  # 0..1
    black = np.array([0x0A, 0x0A, 0x0A]); violet = np.array([0x2D, 0x0A, 0x47]); silver = np.array([0xC8, 0xC8, 0xC8])
    lo = black + (violet - black) * (np.clip(t, 0, 0.5) / 0.5)
    hi = violet + (silver - violet) * (np.clip(t - 0.5, 0, 0.5) / 0.5)
    duo = np.where(t < 0.5, lo, hi)
    g = _lum(a)[..., None] * 255.0
    desat = rgb * 0.3 + g * 0.7  # original fortement désaturé
    out = duo * 0.7 + desat * 0.3
    res = np.concatenate([np.clip(out, 0, 255), alpha], axis=-1).astype("uint8")
    return Image.fromarray(res, "RGBA")


def desaturate(img: Image.Image, factor: float) -> Image.Image:
    rgb = ImageEnhance.Color(img.convert("RGB")).enhance(1.0 - factor)
    return Image.merge("RGBA", (*rgb.split(), img.convert("RGBA").split()[3]))


def tint(img: Image.Image, hex_col: str, frac: float) -> Image.Image:
    a = np.asarray(img.convert("RGBA")).astype(float)
    col = np.array([int(hex_col[i:i + 2], 16) for i in (1, 3, 5)])
    m = a[..., 3:4] > 0
    a[..., :3] = np.where(m, a[..., :3] * (1 - frac) + col * frac, a[..., :3])
    return Image.fromarray(a.astype("uint8"), "RGBA")


TRANSFORMS = {
    "third_world": third_world,
    "desat15": lambda im: desaturate(im, 0.15),
    "desat20": lambda im: desaturate(im, 0.20),
    "contam12": lambda im: tint(im, "#2D0A47", 0.12),
}


def _checker(im: Image.Image) -> Image.Image:
    s = Image.new("RGB", im.size, (190, 190, 190)); d = ImageDraw.Draw(s)
    for y in range(0, im.height, 16):
        for x in range(0, im.width, 16):
            if (x // 16 + y // 16) % 2:
                d.rectangle([x, y, x + 16, y + 16], fill=(160, 160, 160))
    s = s.convert("RGBA"); s.alpha_composite(im); return s.convert("RGB")


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-mod", action="store_true", help="ne pas écrire l'override dans le mod")
    ap.add_argument("--only", help="ne traiter que les model contenant cette sous-chaîne")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    jobs = [j for j in JOBS if not args.only or args.only in j["model"]]
    done = 0
    for job in jobs:
        grp, mid = job["model"].split("/")
        fn = TRANSFORMS[job["transform"]]
        befores, afters = [], []
        for suf in job["textures"]:
            src = MOGURI / grp / mid / f"{mid}{suf}.png"
            if not src.exists():
                print(f"  ⚠ source absente : {src}"); continue
            base = Image.open(src).convert("RGBA")
            edited = fn(base)
            # QA local
            edited.save(OUT / f"{grp}_{mid}{suf}_{job['transform']}.png")
            befores.append(base); afters.append(edited)
            # override mod
            if not args.no_mod:
                dest = MOD / grp / mid / f"{mid}{suf}.png"
                dest.parent.mkdir(parents=True, exist_ok=True)
                edited.save(dest)
            done += 1
        # planche avant/après (1re texture)
        if befores:
            b, a = _checker(befores[0]), _checker(afters[0])
            TH = 320; font = ImageFont.truetype("arialbd.ttf", 18)
            m = Image.new("RGB", (2 * (TH + 12) + 12, TH + 40), (235, 235, 235)); dr = ImageDraw.Draw(m)
            m.paste(b.resize((TH, TH), Image.LANCZOS), (12, 32)); dr.text((12, 8), "Moguri original", fill=(0, 0, 0), font=font)
            m.paste(a.resize((TH, TH), Image.LANCZOS), (TH + 24, 32)); dr.text((TH + 24, 8), job["label"], fill=(0, 0, 0), font=font)
            m.save(OUT / f"POC_{grp}_{mid}_{job['transform']}.jpg", quality=90)
    print(f"Terminé : {done} textures éditées." + ("" if args.no_mod else f" Overrides → {MOD}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

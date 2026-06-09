"""Standardise les assets visuels du jeu Godot 'Le Repaire des Sorcières'
pour qu'ils s'affichent COHÉRENTS et au bon endroit en jeu.

Problème : le jeu applique des scale FIXES (Sprite2D personnages = 0.4, stations
= 0.3, fond = Sprite2D centré à (540,960)), mais les PNG générés ont des tailles
toutes différentes (détourage autocrop) → rendu incohérent et désaligné.

Solution (profil canonique par type d'asset) :
  - personnages : canvas 1024×1536, figure ancrée BAS-centre (réf. validée
    goblin_presse 1024×1536 → 410×614 à scale 0.4). Tous identiques.
  - stations    : canvas 1024×1024, objet centré.
  - fonds       : 1080×1920 STRICT (cover), car affichés via Sprite2D non étiré.
  - icônes ui/recipes 64×64 : déjà cohérentes (procédurales) → ignorées.

Sauvegarde d'abord assets/sprites → assets/_sprites_backup_<ts>/ (sauf --no-backup).
Patche aussi les .import (mipmaps/generate=true) pour un anti-aliasing propre au scale 0.4.

Usage : python scripts/standardize_repaire_assets.py [--dry-run] [--no-backup]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
from studio.procedural import fit_to_canvas, cover_resize, save_png

PROJECT = Path(r"C:\Users\lasse\workspace\jeux mobiles\le repère des sorcières")
SPRITES = PROJECT / "assets" / "sprites"

CHAR_STATES = ("idle", "happy", "angry")   # walk = placeholders 128×192 non affichés → ignorés
CHAR_CANVAS = (1024, 1536)   # réf. goblin_presse ; scale jeu 0.4 → 410×614
STATION_CANVAS = (1024, 1024)
BG_SIZE = (1080, 1920)       # viewport exact


def _patch_import_mipmaps(png: Path) -> bool:
    """Active mipmaps/generate dans le .import voisin (anti-aliasing au downscale)."""
    imp = png.with_suffix(png.suffix + ".import")
    if not imp.exists():
        return False
    txt = imp.read_text(encoding="utf-8")
    if "mipmaps/generate=true" in txt:
        return False
    if "mipmaps/generate=false" in txt:
        imp.write_text(txt.replace("mipmaps/generate=false", "mipmaps/generate=true"), encoding="utf-8")
        return True
    return False


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    if not SPRITES.exists():
        print(f"✗ dossier sprites introuvable : {SPRITES}")
        return 1

    # 1) Backup
    if not args.no_backup and not args.dry_run:
        import time
        bk = PROJECT / "assets" / "_sprites_backup"
        if not bk.exists():
            shutil.copytree(SPRITES, bk)
            print(f"Backup → {bk}")
        else:
            print(f"Backup déjà présent ({bk}) — conservé")

    changed, imports_patched = [], 0

    def process(png: Path, canvas, anchor, fill):
        nonlocal imports_patched
        im = Image.open(png).convert("RGBA")
        if canvas == "bg":
            if im.size == BG_SIZE:
                return  # déjà bon
            out = cover_resize(im, *BG_SIZE)
            label = f"{im.size} -> {BG_SIZE} (cover)"
        else:
            if im.size == canvas:
                return  # déjà au canevas
            out = fit_to_canvas(im, *canvas, anchor=anchor, fill=fill)
            label = f"{im.size} -> {canvas} (anchor={anchor})"
        changed.append((png.relative_to(PROJECT), label))
        if not args.dry_run:
            save_png(out, png)
            if _patch_import_mipmaps(png):
                imports_patched += 1

    # 2) Personnages (sous-dossiers, 4 états)
    for cdir in sorted((SPRITES / "characters").iterdir()):
        if cdir.is_dir():
            for st in CHAR_STATES:
                p = cdir / f"{st}.png"
                if p.exists():
                    process(p, CHAR_CANVAS, "bottom", 0.95)

    # 3) Stations
    sdir = SPRITES / "stations"
    if sdir.exists():
        for p in sorted(sdir.glob("*.png")):
            process(p, STATION_CANVAS, "center", 0.90)

    # 4) Fonds
    bdir = SPRITES / "backgrounds"
    if bdir.exists():
        for p in sorted(bdir.glob("*.png")):
            process(p, "bg", "", 0)

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Assets à standardiser : {len(changed)}")
    for rel, label in changed:
        print(f"  {rel}  {label}")
    if not args.dry_run:
        print(f"\n.import patchés (mipmaps) : {imports_patched}")
        print("→ Rouvrir le projet dans Godot pour réimporter les textures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

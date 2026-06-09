"""Orchestrateur des assets procéduraux Tier 1 du mod FF9 'La Troisième Fissure'.

Importe chaque générateur de catégorie (studio.ff9.gen_*) et écrit tous les PNG
sous un dossier racine miroir de la structure EmbeddedAsset/ du mod.

Par défaut, écrit dans outputs/ff9/EmbeddedAsset/ (chemin ASCII, pour la QA),
PAS directement dans le mod sous Program Files (qui contient des espaces et peut
nécessiter une élévation). La copie finale vers le mod est une étape séparée.

Usage :
    python scripts/generate_ff9_assets.py [--out DIR] [--only overlays,ozma,...] [--sheet]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "outputs" / "ff9" / "EmbeddedAsset"

# (clé CLI, module) — l'ordre = ordre de génération.
CATEGORIES = [
    ("overlays", "studio.ff9.gen_overlays"),
    ("ozma", "studio.ff9.gen_ozma"),
    ("ui", "studio.ff9.gen_ui"),
    ("vfx", "studio.ff9.gen_vfx"),
    ("enemies", "studio.ff9.gen_enemy_overlays"),
    ("backgrounds", "studio.ff9.gen_backgrounds"),
]


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main() -> int:
    _force_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="dossier racine de sortie")
    ap.add_argument("--only", help="catégories à générer (séparées par des virgules)")
    ap.add_argument("--sheet", action="store_true", help="produit une planche-contact JPG par catégorie")
    args = ap.parse_args()

    import importlib

    only = set(args.only.split(",")) if args.only else None
    out_root = args.out
    out_root.mkdir(parents=True, exist_ok=True)
    print(f"Sortie : {out_root}")

    all_paths: dict[str, list[Path]] = {}
    t0 = time.time()
    for key, modname in CATEGORIES:
        if only and key not in only:
            continue
        mod = importlib.import_module(modname)
        try:
            paths = mod.generate(out_root)
            all_paths[key] = paths
            total = sum(p.stat().st_size for p in paths)
            print(f"  [{key:11}] {len(paths):2} fichiers, {total/1024:.0f} Ko")
        except Exception as e:  # un générateur en échec ne bloque pas les autres
            print(f"  [{key:11}] ✗ ÉCHEC : {e}")

    n = sum(len(v) for v in all_paths.values())
    print(f"\nTerminé : {n} assets en {time.time()-t0:.1f}s")

    if args.sheet:
        _contact_sheets(out_root, all_paths)
    return 0


def _contact_sheets(out_root: Path, all_paths: dict[str, list[Path]]) -> None:
    """Planche-contact JPG par catégorie, sur damier, pour QA visuelle rapide."""
    from PIL import Image

    sheets_dir = out_root.parent / "sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)
    THUMB, COLS, PAD = 256, 5, 8

    def checker(size: int) -> Image.Image:
        bg = Image.new("RGB", (size, size), (40, 40, 48))
        c = 16
        for y in range(0, size, c):
            for x in range(0, size, c):
                if (x // c + y // c) % 2:
                    bg.paste((70, 70, 82), (x, y, x + c, y + c))
        return bg

    for key, paths in all_paths.items():
        if not paths:
            continue
        rows = (len(paths) + COLS - 1) // COLS
        sheet = Image.new("RGB", (COLS * (THUMB + PAD) + PAD, rows * (THUMB + PAD) + PAD), (24, 24, 30))
        for i, p in enumerate(paths):
            im = Image.open(p).convert("RGBA")
            im.thumbnail((THUMB, THUMB), Image.LANCZOS)
            cell = checker(THUMB)
            cell.paste(im, ((THUMB - im.width) // 2, (THUMB - im.height) // 2), im)
            r, cc = divmod(i, COLS)
            sheet.paste(cell, (PAD + cc * (THUMB + PAD), PAD + r * (THUMB + PAD)))
        dest = sheets_dir / f"sheet_{key}.jpg"
        sheet.save(dest, quality=88)
        print(f"  planche : {dest}")


if __name__ == "__main__":
    sys.exit(main())

"""Génère les 8 backgrounds FIGURATIFS manquants (P0) du mod FF9 via SDXL.

SDXL (résolution cappée pour éviter l'OOM, puis resize à la dimension cible) →
détourage optionnel (overlays transparents) → écrit dans le mod
FF9_Data/EmbeddedAsset/backgrounds/<acte>/ + copie QA dans outputs/ff9/backgrounds/.

⚠️ Placeholders : SDXL ne s'aligne pas sur la géométrie exacte des scènes Moguri ;
ce sont des éléments génériques on-theme, à recaler par un artiste pour l'alignement.

Usage : python scripts/generate_ff9_backgrounds.py [--only fissure] [--no-mod] [--steps 30]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "scripts" / "ff9_backgrounds_manifest.json"
OUT_DIR = ROOT / "outputs" / "ff9" / "backgrounds"
MOD = Path(r"C:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY IX\FF9_Suite\FF9_Data\EmbeddedAsset")

CAP = 1024  # dimension max pour la génération SDXL (anti-OOM 8 Go), puis resize


def _gen_size(w: int, h: int) -> tuple[int, int]:
    """Dimensions de génération : cap sur le plus grand côté, multiples de 8."""
    scale = min(1.0, CAP / max(w, h))
    gw, gh = int(w * scale), int(h * scale)
    return max(8, gw - gw % 8), max(8, gh - gh % 8)


def _seed_for(name: str) -> int:
    return abs(hash(name)) % 100_000


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--no-mod", action="store_true")
    ap.add_argument("--steps", type=int, default=30)
    args = ap.parse_args()

    jobs = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.only:
        jobs = [j for j in jobs if args.only in j["name"]]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    from PIL import Image
    from studio import get_router
    from studio.core import Modality
    from studio.assembly import image_ops

    router = get_router()
    ok, _ = image_ops.rembg_available()
    done, failed = 0, []
    t0 = time.time()
    print(f"{len(jobs)} backgrounds à générer (SDXL) → mod + {OUT_DIR}")
    for i, job in enumerate(jobs, 1):
        tw, th = job["width"], job["height"]
        gw, gh = _gen_size(tw, th)
        t = time.time()
        try:
            res = router.generate(
                Modality.IMAGE, job["subject"], width=gw, height=gh,
                steps=args.steps, seed=_seed_for(job["name"]),
                negative_prompt=job.get("negative_prompt", ""),
            )
            img = Image.open(res.path).convert("RGBA")
            if job.get("detour") and ok:
                tmp = OUT_DIR / f"_{job['name']}_raw.png"
                img.save(tmp)
                image_ops.remove_background(tmp, tmp, autocrop=True)
                img = Image.open(tmp).convert("RGBA")
            img = img.resize((tw, th), Image.LANCZOS)
            local = OUT_DIR / f"{job['name']}.png"
            img.save(local)
            if not args.no_mod:
                dest = MOD / job["out_path"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                img.save(dest)
            done += 1
            print(f"[{i}/{len(jobs)}] OK {job['name']} ({tw}x{th}, {time.time()-t:.0f}s)", flush=True)
        except Exception as e:
            failed.append((job["name"], str(e)))
            print(f"[{i}/{len(jobs)}] ECHEC {job['name']} : {e}", flush=True)

    print(f"\nTerminé : {done}/{len(jobs)} en {(time.time()-t0)/60:.1f} min. Échecs : {len(failed)}")
    for n, e in failed:
        print(f"  ECHEC {n} : {e}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

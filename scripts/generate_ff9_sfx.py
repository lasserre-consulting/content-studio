"""Génère les SFX du mod FF9 via AudioGen local (GPU).

Lit ff9_sfx_manifest.json et route chaque SFX par le studio (Modality.SFX →
audiogen-local). Séquentiel (un seul GPU). Tolérant aux pannes.
Sortie : outputs/ff9/sfx/<name>.wav.

Usage :
    python scripts/generate_ff9_sfx.py --top12        # les 12 prioritaires
    python scripts/generate_ff9_sfx.py --only ozma    # sous-chaîne sur le name
    python scripts/generate_ff9_sfx.py                # tout (60)
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
MANIFEST = ROOT / "scripts" / "ff9_sfx_manifest.json"
OUT_DIR = ROOT / "outputs" / "ff9" / "sfx"


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--top12", action="store_true", help="ne générer que les 12 prioritaires")
    ap.add_argument("--only", help="ne traiter que les name contenant cette sous-chaîne")
    ap.add_argument("--limit", type=int, help="limiter au N premiers jobs")
    ap.add_argument("--skip-existing", action="store_true", help="sauter les WAV déjà présents")
    args = ap.parse_args()

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sfx = data["sfx"]
    if args.top12:
        top = set(data["top12"])
        sfx = [s for s in sfx if s["name"] in top]
    if args.only:
        sfx = [s for s in sfx if args.only in s["name"]]
    if args.limit:
        sfx = sfx[: args.limit]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.skip_existing:
        sfx = [s for s in sfx if not (OUT_DIR / s["out_path"]).exists()]

    from studio import get_router
    from studio.core import Modality

    router = get_router()
    done, failed = 0, []
    t_start = time.time()
    print(f"{len(sfx)} SFX à générer (AudioGen) → {OUT_DIR}")
    for i, job in enumerate(sfx, 1):
        out = OUT_DIR / job["out_path"]
        t0 = time.time()
        try:
            res = router.generate(
                Modality.SFX,
                job["prompt"],
                duration=int(round(job.get("duration_s", 4))),
            )
            src = Path(res.path)
            if src != out:
                shutil.copyfile(src, out)
            done += 1
            print(f"[{i:2}/{len(sfx)}] OK {job['name']} ({job['duration_s']}s, {time.time()-t0:.0f}s)", flush=True)
        except Exception as e:
            failed.append((job["name"], str(e)))
            print(f"[{i:2}/{len(sfx)}] ECHEC {job['name']} : {e}", flush=True)

    print(f"\nTerminé : {done}/{len(sfx)} en {(time.time()-t_start)/60:.1f} min. Échecs : {len(failed)}")
    for name, err in failed:
        print(f"  ECHEC {name} : {err}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

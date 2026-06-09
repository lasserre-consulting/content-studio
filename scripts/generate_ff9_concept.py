"""Génère le CONCEPT ART des nouveaux ennemis FF9 via SDXL local (GPU).

Illustrations de référence de design (PAS des spritesheets de jeu) : servent à
cadrer l'esthétique des boss du mod avant un éventuel travail d'artiste.

Séquentiel (un seul GPU). Tolérant aux pannes. Sortie : outputs/ff9/concept/.

Usage : python scripts/generate_ff9_concept.py [--only kuja] [--steps 30]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "scripts" / "ff9_concept_manifest.json"
OUT_DIR = ROOT / "outputs" / "ff9" / "concept"


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
    ap.add_argument("--only", help="ne traiter que les name contenant cette sous-chaîne")
    ap.add_argument("--steps", type=int, default=30, help="pas de diffusion (qualité)")
    args = ap.parse_args()

    jobs = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.only:
        jobs = [j for j in jobs if args.only in j["name"]]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    from studio import get_router
    from studio.core import Modality

    router = get_router()
    done, failed = 0, []
    t_start = time.time()
    for i, job in enumerate(jobs, 1):
        out = OUT_DIR / job["out_path"]
        t0 = time.time()
        try:
            res = router.generate(
                Modality.IMAGE,
                job["subject"],
                width=job.get("width", 1024),
                height=job.get("height", 1024),
                steps=args.steps,
                seed=job.get("seed", _seed_for(job["name"])),
                negative_prompt=job.get("negative_prompt", ""),
            )
            if Path(res.path) != out:
                import shutil

                shutil.copyfile(res.path, out)
            done += 1
            print(f"[{i}/{len(jobs)}] OK {job['name']}  ({time.time()-t0:.0f}s) -> {out.name}", flush=True)
        except Exception as e:
            failed.append((job["name"], str(e)))
            print(f"[{i}/{len(jobs)}] ECHEC {job['name']} : {e}", flush=True)

    print(f"\nTerminé : {done}/{len(jobs)} en {(time.time()-t_start)/60:.1f} min. Échecs : {len(failed)}")
    for name, err in failed:
        print(f"  ECHEC {name} : {err}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

"""Générateur d'assets pour 'Le Repaire des Sorcières'.

Lit un manifeste JSON (produit par le workflow de prompts) et, pour chaque job :
  SDXL (local, GPU) → détourage transparent (rembg) → écrit dans le projet Godot.

Séquentiel par conception : un seul GPU (RTX 2080 8 Go), SDXL = une instance.
Tolérant aux pannes : un sprite qui échoue est journalisé et on continue.

Usage :
    python scripts/generate_repaire_assets.py manifest.json [--dry-run] [--only fantome]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

# Rend le package 'studio' importable même lancé depuis scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Le projet Godot cible.
PROJECT = Path(r"C:\Users\lasse\workspace\jeux mobiles\le repère des sorcières")

# Style calé sur goblin_presse (peinture fantasy sombre détaillée). CLIP tronque
# à 77 tokens : on met donc un style COURT EN PRÉFIXE (il survit à la troncature),
# puis le sujet détaillé du manifeste (identité front-loadée par les agents).
STYLE = {
    "character": "dark fantasy painterly game character sprite, dramatic rim lighting, full body centered on plain dark background,",
    "portrait": "dark fantasy painterly character portrait, head and shoulders, dramatic lighting, plain dark background,",
    "station": "dark fantasy painterly game asset, single magical object centered, no character, dramatic lighting, plain dark background,",
}


def _seed_for(path: str) -> int:
    """Seed déterministe (reproductible) dérivée du chemin de sortie."""
    return abs(hash(path)) % 100_000


def main() -> int:
    # Console Windows souvent en cp1252 : on force UTF-8 pour les libellés/accents.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass

    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--dry-run", action="store_true", help="liste les jobs sans générer")
    ap.add_argument("--only", help="ne traiter que les out_path contenant cette sous-chaîne")
    args = ap.parse_args()

    jobs = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if isinstance(jobs, dict):
        jobs = jobs.get("jobs", [])
    if args.only:
        jobs = [j for j in jobs if args.only in j["out_path"]]

    print(f"{len(jobs)} jobs à traiter (projet: {PROJECT.name})")
    if args.dry_run:
        for j in jobs:
            print(f"  [{j['kind']:9}] {j['out_path']}")
            print(f"             {j['subject'][:90]}")
        return 0

    # Imports lourds seulement si on génère vraiment.
    from studio import get_router
    from studio.core import Modality
    from studio.assembly import image_ops

    router = get_router()
    ok, reason = image_ops.rembg_available()
    if not ok:
        print(f"⚠ détourage indisponible ({reason}) — sprites laissés avec fond")

    done, failed = 0, []
    t_start = time.time()
    for i, job in enumerate(jobs, 1):
        out = PROJECT / job["out_path"]
        out.parent.mkdir(parents=True, exist_ok=True)
        prompt = f"{STYLE[job['kind']]} {job['subject']}"
        label = job["out_path"].replace("assets/sprites/", "")
        t0 = time.time()
        try:
            gen_kw = {
                "width": job.get("width", 1024), "height": job.get("height", 1024),
                # seed explicite si fournie (régénération ciblée), sinon dérivée du chemin.
                "seed": job.get("seed", _seed_for(job["out_path"])),
            }
            if job.get("negative_prompt"):
                gen_kw["negative_prompt"] = job["negative_prompt"]
            res = router.generate(Modality.IMAGE, prompt, **gen_kw)
            src = res.path
            if job.get("detour") and ok:
                image_ops.remove_background(src, out, autocrop=True)
            else:
                shutil.copyfile(src, out)
            done += 1
            print(f"[{i:2}/{len(jobs)}] ✓ {label}  ({time.time()-t0:.0f}s)", flush=True)
        except Exception as e:  # on continue malgré un échec isolé
            failed.append((label, str(e)))
            print(f"[{i:2}/{len(jobs)}] ✗ {label} — {e}", flush=True)

    dt = time.time() - t_start
    print(f"\nTerminé : {done}/{len(jobs)} en {dt/60:.1f} min. Échecs : {len(failed)}")
    for label, err in failed:
        print(f"  ✗ {label} : {err}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

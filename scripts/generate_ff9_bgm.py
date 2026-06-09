"""Génère les 7 BGM du mod FF9 via MusicGen local (GPU) et les intègre dans le mod.

Pour chaque thème : MusicGen → WAV (outputs/ff9/bgm/) → conversion OGG (libvorbis)
→ écrit dans StreamingAssets/Assets/Audio/<name>.ogg, AUX NOMS EXACTS référencés par
la section [Audio] de Memoria.ini (theme_act1_field, theme_battle_scout, ...).

⚠️ Ce sont des nappes d'AMBIANCE (placeholder) : MusicGen ne reproduit ni le motif
exact (Sol#) ni les citations de thèmes Uematsu — il calque l'instrumentation et le mood.

Séquentiel (un seul GPU). Tolérant aux pannes.
Usage : python scripts/generate_ff9_bgm.py [--only kuja] [--no-mod]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "scripts" / "ff9_bgm_manifest.json"
OUT_DIR = ROOT / "outputs" / "ff9" / "bgm"
MOD_AUDIO = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY IX\FF9_Suite\StreamingAssets\Assets\Audio"
)


def _to_ogg(wav: Path, ogg: Path, ffmpeg: str) -> None:
    ogg.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libvorbis", "-q:a", "5", str(ogg)],
        check=True,
    )


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="ne traiter que les name contenant cette sous-chaîne")
    ap.add_argument("--no-mod", action="store_true", help="ne pas écrire l'OGG dans le mod")
    ap.add_argument("--manifest", type=Path, default=MANIFEST, help="manifeste JSON à utiliser")
    ap.add_argument("--subdir", default="", help="sous-dossier sous Audio/ (ex. 'BGM')")
    args = ap.parse_args()

    mod_audio = MOD_AUDIO / args.subdir if args.subdir else MOD_AUDIO
    jobs = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.only:
        jobs = [j for j in jobs if args.only in j["name"]]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    from studio import get_router
    from studio.core import Modality
    from studio.assembly.ffmpeg import ffmpeg_bin

    ffmpeg = ffmpeg_bin()
    if not ffmpeg:
        print("⚠ ffmpeg introuvable — les WAV seront produits mais pas convertis en OGG")

    router = get_router()
    import time

    done, failed = 0, []
    t_start = time.time()
    print(f"{len(jobs)} BGM à générer (MusicGen 30s) → {OUT_DIR}" + ("" if args.no_mod else f" + mod"))
    for i, job in enumerate(jobs, 1):
        wav = OUT_DIR / f"{job['name']}.wav"
        t0 = time.time()
        try:
            res = router.generate(Modality.MUSIC, job["prompt"], duration=int(job.get("duration_s", 30)))
            src = Path(res.path)
            if src != wav:
                shutil.copyfile(src, wav)
            line = f"[{i}/{len(jobs)}] OK {job['name']} ({time.time()-t0:.0f}s)"
            if ffmpeg:
                _to_ogg(wav, OUT_DIR / f"{job['name']}.ogg", ffmpeg)
                if not args.no_mod:
                    _to_ogg(wav, mod_audio / f"{job['name']}.ogg", ffmpeg)
                    line += " -> mod/.ogg"
            done += 1
            print(line, flush=True)
        except Exception as e:
            failed.append((job["name"], str(e)))
            print(f"[{i}/{len(jobs)}] ECHEC {job['name']} : {e}", flush=True)

    print(f"\nTerminé : {done}/{len(jobs)} en {(time.time()-t_start)/60:.1f} min. Échecs : {len(failed)}")
    for name, err in failed:
        print(f"  ECHEC {name} : {err}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

"""Génère des SPRITESHEETS de combat (placeholder) pour les ennemis FF9 via SDXL.

Pour chaque ennemi : 1 sprite SDXL par STATE (idle/attack/death/...) → détourage
transparent (rembg) → tuilé aux dimensions/grilles exactes de chaque spritesheet
(cf. visual_bible.md) → écrit dans le mod enemies/<id>/.

⚠️ LIMITE ASSUMÉE : SDXL ne produit pas d'animation frame-cohérente. Chaque sheet
contient UN sprite propre, répété sur sa grille de frames (statique mais non cassé).
Ce sont des sprites de DESIGN/placeholder ; l'animation réelle reste à faire par un
artiste, et le découpage de frames est à ajuster selon le BattleEngine.

Séquentiel (un GPU). Tolérant aux pannes.
Usage : python scripts/generate_ff9_sprites.py [--only necron] [--no-mod] [--steps 30]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "scripts" / "ff9_sprite_manifest.json"
OUT_DIR = ROOT / "outputs" / "ff9" / "sprites"
MOD_ASSET = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY IX\FF9_Suite\FF9_Data\EmbeddedAsset"
)


def _fit(sprite, fw: int, fh: int):
    """Redimensionne le sprite pour tenir dans (fw,fh) en préservant le ratio, centré, fond transparent."""
    from PIL import Image

    s = sprite.copy()
    s.thumbnail((fw, fh), Image.LANCZOS)
    frame = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
    frame.alpha_composite(s, ((fw - s.width) // 2, (fh - s.height) // 2))
    return frame


def _tile(frame, w: int, h: int, cols: int, rows: int):
    from PIL import Image

    sheet = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    fw, fh = frame.size
    for i in range(cols * rows):
        r, c = divmod(i, cols)
        sheet.alpha_composite(frame, (c * fw, r * fh))
    return sheet


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="ne traiter que les ennemis contenant cette sous-chaîne")
    ap.add_argument("--no-mod", action="store_true", help="écrire seulement dans outputs/ff9/sprites/")
    ap.add_argument("--steps", type=int, default=30)
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    enemies = {k: v for k, v in manifest.items() if not args.only or args.only in k}

    from PIL import Image
    from studio import get_router
    from studio.core import Modality
    from studio.assembly import image_ops

    router = get_router()
    ok, reason = image_ops.rembg_available()
    if not ok:
        print(f"⚠ détourage indisponible ({reason}) — sprites laissés avec fond")

    tmp = OUT_DIR / "_raw"
    tmp.mkdir(parents=True, exist_ok=True)
    done_sheets, failed = 0, []
    t_start = time.time()

    for ename, cfg in enemies.items():
        out_mod = MOD_ASSET / cfg["out_subdir"]
        out_local = OUT_DIR / ename
        out_local.mkdir(parents=True, exist_ok=True)
        if not args.no_mod:
            out_mod.mkdir(parents=True, exist_ok=True)

        # 1) Un sprite détouré par state.
        states = {s["state"] for s in cfg["sheets"]}
        sprites: dict[str, object] = {}
        for si, state in enumerate(sorted(states)):
            gw, gh = (1024, 1024) if state == "portrait" else cfg["gen_size"]
            prompt = f"{cfg['style_prefix']} {cfg['states'][state]}"
            t0 = time.time()
            try:
                res = router.generate(
                    Modality.IMAGE, prompt, width=gw, height=gh,
                    steps=args.steps, seed=cfg["seed"] + si,
                    negative_prompt=cfg.get("negative_prompt", ""),
                )
                raw = tmp / f"{ename}_{state}.png"
                if ok:
                    image_ops.remove_background(res.path, raw, autocrop=True)
                else:
                    raw.write_bytes(Path(res.path).read_bytes())
                sprites[state] = Image.open(raw).convert("RGBA")
                print(f"  [{ename}:{state}] sprite OK ({time.time()-t0:.0f}s)", flush=True)
            except Exception as e:
                failed.append((f"{ename}:{state}", str(e)))
                print(f"  [{ename}:{state}] ECHEC : {e}", flush=True)

        # 2) Composition des spritesheets (tuilage du sprite du state).
        for sh in cfg["sheets"]:
            sprite = sprites.get(sh["state"])
            if sprite is None:
                continue
            fw, fh = sh["w"] // sh["cols"], sh["h"] // sh["rows"]
            sheet = _tile(_fit(sprite, fw, fh), sh["w"], sh["h"], sh["cols"], sh["rows"])
            sheet.save(out_local / sh["file"])
            if not args.no_mod:
                sheet.save(out_mod / sh["file"])
            done_sheets += 1
            print(f"    -> {sh['file']} ({sh['w']}x{sh['h']}, {sh['cols']}x{sh['rows']})", flush=True)

    print(f"\nTerminé : {done_sheets} spritesheets en {(time.time()-t_start)/60:.1f} min. Échecs gen : {len(failed)}")
    for name, err in failed:
        print(f"  ECHEC {name} : {err}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

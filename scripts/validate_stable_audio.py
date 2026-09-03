"""Validation en génération réelle des providers Stable Audio 3.

But : prouver, sur CE poste, que `stableaudio-sfx` et `stableaudio-music`
produisent un WAV exploitable — avant de les passer `active` dans
config/providers.yaml et de retirer audiocraft.

Le SFX passe en premier : il est plus court, donc il échoue plus vite si
quelque chose ne va pas (modèle inaccessible, VRAM insuffisante, API changée).

    python scripts/validate_stable_audio.py            # les deux
    python scripts/validate_stable_audio.py --only sfx
"""
from __future__ import annotations

import argparse
import sys
import time
import wave
from pathlib import Path

# Les imports du studio restent en haut : ils sont légers (le lourd est paresseux).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from studio import get_router  # noqa: E402
from studio.core import Modality  # noqa: E402


def decrire_wav(path: Path) -> str:
    """Ouvre le WAV produit pour vérifier qu'il est lisible et non silencieux."""
    try:
        with wave.open(str(path), "rb") as w:
            canaux = w.getnchannels()
            taux = w.getframerate()
            frames = w.getnframes()
            duree = frames / float(taux) if taux else 0.0
        taille_ko = path.stat().st_size / 1024
        return f"{duree:.1f}s | {taux} Hz | {canaux} canal/aux | {taille_ko:.0f} Ko"
    except Exception as e:  # noqa: BLE001
        return f"ILLISIBLE ({e})"


def essayer(nom: str, modalite: Modality, provider: str, prompt: str, duree: int) -> bool:
    print(f"\n--- {nom} ---")
    print(f"  provider : {provider}")
    print(f"  prompt   : {prompt!r}  ({duree}s demandées)")

    routeur = get_router()

    # available() d'abord : distingue « pas installé » de « plantage à la génération ».
    from studio.core.registry import get_provider_class

    cls = get_provider_class(modalite, provider)
    ok, raison = cls().available()
    print(f"  available: {ok} — {raison}")
    if not ok:
        print("  => ÉCHEC : provider indisponible, génération non tentée.")
        return False

    depart = time.time()
    try:
        res = routeur.generate(modalite, prompt, provider=provider, duration=duree)
    except Exception as e:  # noqa: BLE001
        print(f"  => ÉCHEC après {time.time() - depart:.0f}s : {e}")
        return False

    ecoule = time.time() - depart
    chemin = res.path
    if not chemin or not Path(chemin).exists():
        print(f"  => ÉCHEC : aucun fichier produit (en {ecoule:.0f}s)")
        return False

    print(f"  => OK en {ecoule:.0f}s")
    print(f"     fichier : {chemin}")
    print(f"     audio   : {decrire_wav(Path(chemin))}")
    print(f"     meta    : {res.meta}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["sfx", "music"], help="ne valider qu'une modalité")
    args = parser.parse_args()

    print("=" * 62)
    print("  Validation Stable Audio 3 — génération réelle")
    print("=" * 62)
    try:
        import torch

        print(f"  torch {torch.__version__} | CUDA={torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"  GPU  : {torch.cuda.get_device_name(0)}")
    except Exception as e:  # noqa: BLE001
        print(f"  torch indisponible : {e}")

    print("\n  Note : le premier appel télécharge les poids (plusieurs Go).")

    resultats: dict[str, bool] = {}

    if args.only in (None, "sfx"):
        resultats["SFX"] = essayer(
            "SFX", Modality.SFX, "stableaudio-sfx",
            "bruit de potion qui bout dans un chaudron", 5,
        )
    if args.only in (None, "music"):
        resultats["MUSIQUE"] = essayer(
            "MUSIQUE", Modality.MUSIC, "stableaudio-music",
            "thème de combat épique, orgue sombre, percussions", 15,
        )

    print("\n" + "=" * 62)
    for nom, ok in resultats.items():
        print(f"  {nom:9} {'OK' if ok else 'ÉCHEC'}")
    print("=" * 62)

    return 0 if all(resultats.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

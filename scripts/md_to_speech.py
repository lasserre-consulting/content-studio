"""Lit un fichier Markdown à voix haute via Kokoro (TTS local) -> WAV + MP3.

Usage :
    python scripts/md_to_speech.py FICHIER.md --lang f --voice ff_siwis --out DOSSIER

Le Markdown est nettoyé (titres, gras, liens, listes) puis découpé en blocs ;
chaque bloc est synthétisé séparément pour pouvoir insérer de vraies respirations
entre les paragraphes et des pauses plus longues après les titres.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import soundfile as sf

from studio.assembly.ffmpeg import ffmpeg_bin

SAMPLE_RATE = 24000
PAUSE_PARAGRAPH = 0.45   # secondes entre deux paragraphes
PAUSE_HEADING = 0.9      # secondes après un titre de section


def clean_inline(text: str) -> str:
    """Retire la syntaxe Markdown inline et normalise la ponctuation parlée."""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)   # liens -> libellé
    text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text)  # gras / italique
    text = text.replace("`", "")
    # Les tirets cadratins ne se prononcent pas : on les rend comme des pauses.
    text = text.replace(" — ", ", ").replace("—", ", ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def blocks_from_markdown(md: str) -> list[tuple[str, float]]:
    """Renvoie une liste (texte à dire, pause en secondes après)."""
    out: list[tuple[str, float]] = []
    for raw in md.split("\n\n"):
        raw = raw.strip()
        if not raw:
            continue
        heading = raw.startswith("#")
        # Un titre reste dit (il structure l'écoute), sans les dièses.
        lines = []
        for line in raw.splitlines():
            line = re.sub(r"^#{1,6}\s*", "", line.strip())
            line = re.sub(r"^[-*+]\s+", "", line)
            lines.append(line)
        text = clean_inline(" ".join(lines))
        if not text:
            continue
        # Un titre sans ponctuation finale s'enchaîne mal : on le termine.
        if heading and text[-1] not in ".!?:":
            text += "."
        out.append((text, PAUSE_HEADING if heading else PAUSE_PARAGRAPH))
    return out


def synthesize(blocks, lang: str, voice: str, speed: float) -> np.ndarray:
    from kokoro import KPipeline

    pipe = KPipeline(lang_code=lang)
    chunks: list[np.ndarray] = []
    for i, (text, pause) in enumerate(blocks, 1):
        parts = []
        for _gs, _ps, audio in pipe(text, voice=voice, speed=speed):
            if audio is None:
                continue
            arr = audio.detach().cpu().numpy() if hasattr(audio, "detach") else audio
            parts.append(np.asarray(arr, dtype="float32").reshape(-1))
        if not parts:
            print(f"  ! bloc {i} : aucun audio produit ({text[:50]}...)")
            continue
        chunks.append(np.concatenate(parts))
        chunks.append(np.zeros(int(pause * SAMPLE_RATE), dtype="float32"))
        print(f"  bloc {i}/{len(blocks)} : {len(chunks[-2]) / SAMPLE_RATE:5.1f}s")
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype="float32")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("--lang", default="f", help="'f' français, 'a' anglais US, 'b' anglais UK")
    ap.add_argument("--voice", default="ff_siwis")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--out", type=Path, default=None, help="dossier de sortie")
    args = ap.parse_args()

    md = args.source.read_text(encoding="utf-8")
    blocks = blocks_from_markdown(md)
    print(f"{args.source.name} : {len(blocks)} blocs, voix {args.voice} (lang={args.lang})")

    audio = synthesize(blocks, args.lang, args.voice, args.speed)
    out_dir = args.out or args.source.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / f"{args.source.stem}.wav"
    sf.write(str(wav), audio, SAMPLE_RATE)
    print(f"OK -> {wav}  ({len(audio) / SAMPLE_RATE:.1f}s)")

    ff = ffmpeg_bin()
    if ff:
        mp3 = out_dir / f"{args.source.stem}.mp3"
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(wav),
                        "-codec:a", "libmp3lame", "-b:a", "128k", str(mp3)], check=True)
        print(f"OK -> {mp3}")


if __name__ == "__main__":
    main()

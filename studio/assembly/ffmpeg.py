"""Wrapper fin et robuste autour de ffmpeg.

On ne dépend pas d'une lib Python : ffmpeg en ligne de commande est plus stable
et couvre tous nos besoins (image→vidéo, mux voix+musique, sous-titres incrustés,
concaténation). Chaque fonction renvoie le Path du fichier produit.

ffmpeg est localisé via le PATH (shutil.which) ou les emplacements winget
classiques sous Windows. Si absent, on lève FFmpegUnavailable avec un message
actionnable plutôt que de planter avec une FileNotFoundError obscure.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("studio.ffmpeg")

# Résolutions verticales/horizontales usuelles pour le social.
VERTICAL = (1080, 1920)   # TikTok / Reels / Shorts
SQUARE = (1080, 1080)     # post Insta
LANDSCAPE = (1920, 1080)  # YouTube classique

# Codec de repli logiciel (toujours disponible). Le codec matériel (NVENC) est
# tenté en priorité quand le GPU le permet — voir _video_codec_args().
_LIBX264 = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium"]
_NVENC = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "23", "-pix_fmt", "yuv420p"]

_video_codec_cache: list[str] | None = None  # codec retenu (détection mise en cache)
_nvenc_disabled = False                       # passe à True si NVENC échoue à l'exécution


class FFmpegUnavailable(RuntimeError):
    pass


def _winget_candidates() -> list[Path]:
    """Emplacements où winget (Gyan.FFmpeg) dépose ffmpeg.exe sous Windows."""
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return []
    base = Path(local) / "Microsoft" / "WinGet" / "Packages"
    if not base.exists():
        return []
    # Le binaire est enfoui dans un sous-dossier versionné : on le cherche.
    return list(base.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"))


def ffmpeg_bin() -> str | None:
    """Chemin vers ffmpeg, ou None s'il est introuvable."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    for cand in _winget_candidates():
        if cand.exists():
            return str(cand)
    return None


def ffmpeg_available() -> tuple[bool, str]:
    """(ok, raison) — pour que les studios vérifient avant de lancer un montage."""
    if ffmpeg_bin():
        return True, "ok"
    return False, "ffmpeg introuvable (winget install Gyan.FFmpeg, puis rouvrir le terminal)"


def _run(args: list[str], *, cwd: str | None = None) -> None:
    """Exécute ffmpeg en mode silencieux ; remonte stderr en cas d'échec.

    `cwd` permet de lancer depuis un dossier donné : utile pour le filtre
    subtitles qui n'aime pas les chemins absolus Windows (`:`, espaces, accents)
    — on s'y place et on ne lui passe qu'un nom de fichier relatif simple."""
    binary = ffmpeg_bin()
    if not binary:
        raise FFmpegUnavailable(ffmpeg_available()[1])
    cmd = [binary, "-y", "-hide_banner", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg a échoué :\n{proc.stderr.strip() or proc.stdout.strip()}")


# --------------------------------------------------------------------------- #
# ffprobe : durée d'un média (sert à caler le montage sur la voix)             #
# --------------------------------------------------------------------------- #
def ffprobe_bin() -> str | None:
    """Chemin vers ffprobe (livré avec ffmpeg : même dossier que ffmpeg.exe)."""
    found = shutil.which("ffprobe")
    if found:
        return found
    ff = ffmpeg_bin()
    if ff:
        cand = Path(ff).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if cand.exists():
            return str(cand)
    return None


def media_duration(path: Path | str) -> float | None:
    """Durée d'un fichier audio/vidéo en secondes, ou None si indéterminable."""
    binary = ffprobe_bin()
    if not binary:
        return None
    proc = subprocess.run(
        [binary, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except (ValueError, AttributeError):
        return None


# --------------------------------------------------------------------------- #
# Encodage vidéo : NVENC (GPU) si dispo, repli libx264                          #
# --------------------------------------------------------------------------- #
def _has_nvenc() -> bool:
    """L'encodeur matériel h264_nvenc est-il listé par ffmpeg ?"""
    binary = ffmpeg_bin()
    if not binary:
        return False
    try:
        out = subprocess.run([binary, "-hide_banner", "-encoders"],
                             capture_output=True, text=True)
        return "h264_nvenc" in out.stdout
    except OSError:
        return False


def _video_codec_args() -> list[str]:
    """Args du codec vidéo à utiliser (NVENC si dispo et non désactivé)."""
    global _video_codec_cache
    if _nvenc_disabled:
        return _LIBX264
    if _video_codec_cache is None:
        _video_codec_cache = _NVENC if _has_nvenc() else _LIBX264
        log.info("Codec vidéo retenu : %s", _video_codec_cache[1])
    return _video_codec_cache


def _run_encode(build_cmd, *, cwd: str | None = None) -> None:
    """Lance un encodage en injectant le codec choisi. Si NVENC échoue à
    l'exécution (driver, session pleine…), bascule une fois pour toutes sur
    libx264 et réessaie — le rendu reste garanti."""
    global _nvenc_disabled
    codec = _video_codec_args()
    try:
        _run(build_cmd(codec), cwd=cwd)
    except RuntimeError as e:
        msg = str(e).lower()
        used_nvenc = any("nvenc" in c for c in codec)
        nvenc_err = any(k in msg for k in ("nvenc", "cannot load", "unknown encoder", "cuda"))
        if used_nvenc and nvenc_err:
            log.warning("NVENC a échoué à l'exécution → repli libx264 pour la session")
            _nvenc_disabled = True
            _run(build_cmd(_LIBX264), cwd=cwd)
        else:
            raise


def _scale_pad(size: tuple[int, int]) -> str:
    """Filtre qui met l'image à l'échelle SANS la déformer puis comble en noir
    (letterbox/pillarbox) pour atteindre exactement la résolution cible."""
    w, h = size
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    )


def still_to_video(
    image: Path | str,
    out: Path | str,
    *,
    duration: float = 5.0,
    size: tuple[int, int] = VERTICAL,
    fps: int = 30,
    zoom: bool = True,
) -> Path:
    """Une image fixe → un clip vidéo. Optionnellement un léger effet Ken Burns
    (zoom lent) pour éviter un plan totalement statique."""
    image, out = Path(image), Path(out)
    frames = max(1, int(duration * fps))
    if zoom:
        # Zoom progressif de 1.0 à ~1.1 centré ; d= nombre de frames.
        vf = (
            f"scale={size[0]*2}:-2,"
            f"zoompan=z='min(zoom+0.0008,1.12)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={size[0]}x{size[1]}:fps={fps},"
            f"{_scale_pad(size)}"
        )
    else:
        vf = f"{_scale_pad(size)}"
    _run_encode(lambda codec: [
        "-loop", "1", "-i", str(image),
        "-t", f"{duration}", "-r", f"{fps}",
        "-vf", vf,
        *codec,
        str(out),
    ])
    return out


def slideshow(
    images: list[Path | str],
    out: Path | str,
    *,
    per_image: float = 3.0,
    size: tuple[int, int] = VERTICAL,
    fps: int = 30,
    zoom: bool = True,
) -> Path:
    """Plusieurs images → un diaporama vidéo (chaque image tient `per_image` s).

    On rend chaque plan séparément puis on les concatène : plus robuste que de
    jongler avec des filtres concat complexes, et chaque plan peut zoomer.
    """
    images = [Path(i) for i in images]
    out = Path(out)
    if not images:
        raise ValueError("slideshow: aucune image fournie")
    tmp_dir = out.parent / f".{out.stem}_parts"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for i, img in enumerate(images):
        part = tmp_dir / f"part_{i:03d}.mp4"
        still_to_video(img, part, duration=per_image, size=size, fps=fps, zoom=zoom)
        parts.append(part)

    # Fichier de liste pour le démuxeur concat de ffmpeg.
    listing = tmp_dir / "concat.txt"
    listing.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in parts),
        encoding="utf-8",
    )
    _run(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out)])

    # Nettoyage des fragments intermédiaires.
    for p in parts:
        p.unlink(missing_ok=True)
    listing.unlink(missing_ok=True)
    tmp_dir.rmdir()
    return out


def mix_audio(
    tracks: list[Path | str],
    out: Path | str,
    *,
    volumes: list[float] | None = None,
) -> Path:
    """Mixe plusieurs pistes audio en une seule (ex: voix + musique de fond).

    `volumes` (gains linéaires, 1.0 = inchangé) s'aligne sur `tracks` ; typique :
    [1.0, 0.25] pour garder la voix au-dessus d'une musique discrète.
    """
    tracks = [Path(t) for t in tracks]
    out = Path(out)
    if not tracks:
        raise ValueError("mix_audio: aucune piste fournie")
    if len(tracks) == 1 and not volumes:
        shutil.copyfile(tracks[0], out)
        return out
    vols = volumes or [1.0] * len(tracks)
    inputs: list[str] = []
    filters: list[str] = []
    for i, _ in enumerate(tracks):
        inputs += ["-i", str(tracks[i])]
        filters.append(f"[{i}:a]volume={vols[i]}[a{i}]")
    labels = "".join(f"[a{i}]" for i in range(len(tracks)))
    # duration=longest : la musique courte ne coupe pas une voix plus longue.
    filtergraph = ";".join(filters) + f";{labels}amix=inputs={len(tracks)}:duration=longest[out]"
    _run([*inputs, "-filter_complex", filtergraph, "-map", "[out]", str(out)])
    return out


def mux_audio_video(
    video: Path | str,
    audio: Path | str,
    out: Path | str,
    *,
    fit_to_audio: bool = True,
) -> Path:
    """Colle une piste audio sur une vidéo muette.

    fit_to_audio=True : la vidéo est bouclée/coupée pour durer aussi longtemps
    que l'audio (utile quand la narration dicte la longueur du short)."""
    video, audio, out = Path(video), Path(audio), Path(out)
    args = []
    if fit_to_audio:
        args += ["-stream_loop", "-1", "-i", str(video), "-i", str(audio), "-shortest"]
    else:
        args += ["-i", str(video), "-i", str(audio)]
    _run_encode(lambda codec: [
        *args,
        "-map", "0:v:0", "-map", "1:a:0",
        *codec, "-c:a", "aac", "-b:a", "192k",
        str(out),
    ])
    return out


def burn_subtitles(video: Path | str, srt: Path | str, out: Path | str,
                   *, size: tuple[int, int] = VERTICAL) -> Path:
    """Incruste des sous-titres .srt dans l'image (hardsub) — indispensable sur
    mobile où la plupart regardent sans le son.

    Robustesse Windows : le filtre `subtitles` gère mal les chemins absolus
    (lettre de lecteur `:`, espaces, accents). On copie donc le .srt sous un nom
    ASCII simple dans le dossier de sortie et on lance ffmpeg DEPUIS ce dossier,
    en ne passant qu'un nom relatif. La taille de police s'adapte au format."""
    video, srt, out = Path(video).resolve(), Path(srt), Path(out)
    work = out.parent
    work.mkdir(parents=True, exist_ok=True)

    # Copie ASCII-safe du SRT dans le dossier de travail.
    tmp_srt = work / "_subs_tmp.srt"
    tmp_srt.write_text(Path(srt).read_text(encoding="utf-8"), encoding="utf-8")

    # FontSize est interprété par libass contre une résolution de référence
    # (~288px), pas la hauteur réelle : une valeur ~14-16 donne un sous-titre
    # mobile lisible sans envahir l'écran. On le calibre sur la petite dimension.
    font = max(12, round(min(size) / 72))
    margin = max(40, round(size[1] / 18))  # remonte le texte du bas de l'écran
    style = f"FontSize={font},Outline=2,Shadow=1,Alignment=2,MarginV={margin}"
    try:
        _run_encode(lambda codec: [
            "-i", str(video),
            "-vf", f"subtitles=_subs_tmp.srt:force_style='{style}'",
            *codec, "-c:a", "copy",
            str(out.resolve()),
        ], cwd=str(work))
    finally:
        tmp_srt.unlink(missing_ok=True)
    return out

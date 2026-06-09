"""Studio Contenu : production sociale autonome (Insta / TikTok / YouTube).

Pipeline phare — `short()` : à partir d'un script texte, produire un MP4 vertical
prêt à poster : narration voix + plans visuels (images animées) + musique de fond
discrète + sous-titres incrustés. Chaque brique repose sur le moteur, donc bascule
local↔cloud automatiquement et profite des modèles installés.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .. import assembly
from ..assembly import ffmpeg
from ..core import GenResult, Modality, Router
from .base import Studio, slugify

log = logging.getLogger("studio.content")


def _split_beats(script: str, max_beats: int = 6) -> list[str]:
    """Découpe un script en « beats » (un plan visuel par idée). On coupe sur les
    lignes vides puis les phrases, en plafonnant pour ne pas exploser le nombre
    d'images à générer."""
    blocks = [b.strip() for b in script.split("\n\n") if b.strip()]
    if not blocks:
        blocks = [s.strip() for s in script.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    if len(blocks) > max_beats:
        # Regroupe pour tenir dans max_beats plans.
        step = (len(blocks) + max_beats - 1) // max_beats
        blocks = [" ".join(blocks[i:i + step]) for i in range(0, len(blocks), step)]
    return blocks or [script.strip()]


def _to_srt(beats: list[str], total_seconds: float) -> str:
    """Sous-titres .srt naïfs : répartit les beats uniformément sur la durée."""
    if not beats:
        return ""
    per = total_seconds / len(beats)

    def stamp(t: float) -> str:
        h, rem = divmod(int(t), 3600)
        m, s = divmod(rem, 60)
        ms = int((t - int(t)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, beat in enumerate(beats):
        start, end = i * per, (i + 1) * per
        lines.append(f"{i+1}\n{stamp(start)} --> {stamp(end)}\n{beat}\n")
    return "\n".join(lines)


@dataclass
class Short:
    """Résultat d'une production de short, avec tous les intermédiaires (pour
    inspection / ré-itération ciblée)."""
    video: Path | None
    voice: Path | None = None
    music: Path | None = None
    images: list[Path] = field(default_factory=list)
    beats: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class ContentStudio(Studio):
    """Studio de contenu social. workspace par défaut = <outputs>/content."""

    def __init__(self, router: Router, workspace: Path | str | None = None):
        super().__init__(router, workspace or (router.config.output_dir / "content"))

    # -- briques ---------------------------------------------------------------
    def narrate(self, script: str, *, name: str, voice: str | None = None) -> GenResult | None:
        """Voix off du script (TTS)."""
        kw = {"voice": voice} if voice else {}
        return self.try_gen(Modality.TTS, script, **kw)

    def visuals(self, beats: list[str], *, style: str, name: str) -> list[Path]:
        """Une image par beat. `style` est suffixé à chaque prompt pour un rendu
        cohérent sur tout le short."""
        images: list[Path] = []
        for i, beat in enumerate(beats):
            prompt = f"{beat}, {style}" if style else beat
            res = self.try_gen(Modality.IMAGE, prompt, seed=1000 + i)
            if res and res.path:
                images.append(res.path)
        return images

    # -- pipeline complet ------------------------------------------------------
    def short(
        self,
        script: str,
        *,
        title: str | None = None,
        style: str = "cinematic, dramatic lighting, high detail, vertical composition",
        music_prompt: str | None = "ambient background music, subtle, emotional",
        size: tuple[int, int] = ffmpeg.VERTICAL,
        voice: str | None = None,
        subtitles: bool = True,
    ) -> Short:
        """Script → MP4 vertical monté, prêt à poster.

        Tolérant aux briques manquantes : si l'image n'est pas dispo, on produit
        au moins l'audio ; si ffmpeg manque, on renvoie les assets sans montage.
        Chaque manque est consigné dans Short.notes.
        """
        name = slugify(title or script.split("\n", 1)[0])
        notes: list[str] = []
        beats = _split_beats(script)
        log.info("[content] short '%s' — %d beats", name, len(beats))

        # 1) Narration
        voice_res = self.narrate(script, name=name, voice=voice)
        voice_path = voice_res.path if voice_res else None
        if not voice_path:
            notes.append("voix indisponible (TTS non installé ?)")

        # 2) Visuels
        images = self.visuals(beats, style=style, name=name)
        if not images:
            notes.append("aucune image générée (provider image non installé ?)")

        # 3) Musique de fond (optionnelle)
        music_path = None
        if music_prompt:
            m = self.try_gen(Modality.MUSIC, music_prompt)
            music_path = m.path if m else None
            if not music_path:
                notes.append("musique de fond ignorée (provider music non installé)")

        # 4) Montage
        video_path = self._assemble(
            name=name, images=images, voice=voice_path, music=music_path,
            beats=beats, size=size, subtitles=subtitles, notes=notes,
        )

        return Short(video=video_path, voice=voice_path, music=music_path,
                     images=images, beats=beats, notes=notes)

    def _assemble(self, *, name, images, voice, music, beats, size, subtitles, notes) -> Path | None:
        ok, reason = ffmpeg.ffmpeg_available()
        if not ok:
            notes.append(f"montage sauté : {reason}")
            return None
        if not images:
            notes.append("montage impossible sans image")
            return None

        # 1) Piste audio finale (voix + musique de fond mixées si les deux).
        if voice and music:
            mixed = self.path("audio", f"{name}_mix.wav")
            assembly.mix_audio([voice, music], mixed, volumes=[1.0, 0.22])
            audio_track = mixed
        else:
            audio_track = voice or music

        # 2) Durée cible = durée RÉELLE de l'audio (ffprobe). C'est elle qui doit
        #    piloter à la fois la longueur des plans ET le timing des sous-titres
        #    (sinon désync : la vidéo est rebouclée sur l'audio au mux).
        duration = ffmpeg.media_duration(audio_track) if audio_track else None
        per_image = (duration / len(images)) if duration else 3.0
        total = duration if duration else per_image * len(images)

        # 3) Diaporama muet calé sur cette durée.
        silent = self.path("video", f"{name}_silent.mp4")
        assembly.slideshow(images, silent, per_image=per_image, size=size)

        # 4) Mux voix/musique (la vidéo épouse exactement la durée audio).
        final = self.path("video", f"{name}.mp4")
        if audio_track:
            assembly.mux_audio_video(silent, audio_track, final, fit_to_audio=True)
            silent.unlink(missing_ok=True)
        else:
            final = silent

        # 5) Sous-titres calés sur la vraie durée totale.
        if subtitles and beats:
            srt = self.path("video", f"{name}.srt")
            srt.write_text(_to_srt(beats, total_seconds=total), encoding="utf-8")
            try:
                subbed = self.path("video", f"{name}_sub.mp4")
                assembly.burn_subtitles(final, srt, subbed, size=size)
                final.unlink(missing_ok=True)
                final = subbed
            except Exception as e:  # incrustation non bloquante
                notes.append(f"sous-titres non incrustés : {e}")

        return final

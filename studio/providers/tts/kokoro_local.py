"""Provider TTS local via Kokoro (KPipeline).

Kokoro est un modèle de synthèse vocale léger qui tourne très bien sur CPU
(pas besoin de VRAM), ce qui en fait notre option locale par défaut pour la
voix. On charge le pipeline une seule fois puis on réutilise l'instance.
"""
from __future__ import annotations

import logging
from pathlib import Path

from studio.config import Config
from studio.core import BaseProvider, GenRequest, GenResult, Location, Modality, register

log = logging.getLogger("studio.tts.kokoro")

# Fréquence d'échantillonnage native de Kokoro.
_SAMPLE_RATE = 24000


@register
class KokoroLocal(BaseProvider):
    name = "kokoro-local"
    modality = Modality.TTS
    location = Location.LOCAL
    min_vram_gb = 0  # tourne sur CPU

    # Pipeline mis en cache sur l'instance (le routeur réutilise l'instance).
    _pipe = None
    # Compteur de classe pour des noms uniques (évite la collision du glob()).
    _counter = 0

    def available(self) -> tuple[bool, str]:
        # Vérification rapide et sans effet de bord : on importe juste les paquets,
        # on ne charge surtout pas le modèle ici.
        try:
            import kokoro  # noqa: F401
        except ImportError:
            return False, "paquet 'kokoro' non installé (pip install kokoro)"
        try:
            import soundfile  # noqa: F401
        except ImportError:
            return False, "paquet 'soundfile' non installé (pip install soundfile)"
        return True, "ok"

    def _get_pipe(self, lang_code: str):
        """Crée (et met en cache) le KPipeline pour la langue demandée."""
        # Import lourd fait dans la méthode pour ne pas casser l'import du module
        # quand kokoro est absent (sinon l'auto-enregistrement tomberait).
        if self._pipe is None:
            from kokoro import KPipeline

            self._pipe = KPipeline(lang_code=lang_code)
        return self._pipe

    def generate(self, req: GenRequest) -> GenResult:
        import numpy as np
        import soundfile as sf

        # Réglages : 'f' = français, 'a' = anglais (cf. codes de langue Kokoro).
        lang = req.get("lang") or self.config.get("lang", "f")
        voice = req.get("voice") or self.config.get("voice", "af_heart")
        # Vitesse de lecture optionnelle (1.0 = normal).
        speed = req.get("speed", self.config.get("speed", 1.0))

        pipe = self._get_pipe(lang)

        # KPipeline renvoie un générateur de segments (gs, ps, audio). On
        # concatène les tronçons audio pour obtenir un seul WAV continu.
        segments: list = []
        for _gs, _ps, audio in pipe(req.prompt, voice=voice, speed=speed):
            if audio is None:
                continue
            # L'audio peut être un tensor torch ou un array numpy ; on normalise.
            arr = np.asarray(audio.detach().cpu().numpy() if hasattr(audio, "detach") else audio)
            segments.append(arr.astype("float32").reshape(-1))

        if segments:
            full_audio = np.concatenate(segments) if len(segments) > 1 else segments[0]
        else:
            # Aucun segment produit : on le signale (plutôt qu'un WAV vide silencieux).
            log.warning("Kokoro n'a produit aucun audio pour ce texte (WAV vide écrit)")
            full_audio = np.zeros(0, dtype="float32")

        # Écriture avec un nom unique via compteur de classe (le glob() précédent
        # provoquait des collisions/écrasements quand des fichiers étaient supprimés
        # ou en accès concurrent).
        out_dir = Config.load().output_dir
        KokoroLocal._counter += 1
        dest = out_dir / f"kokoro_{KokoroLocal._counter}.wav"
        sf.write(str(dest), full_audio, _SAMPLE_RATE)

        return GenResult(
            modality=Modality.TTS,
            provider=self.name,
            location=self.location,
            paths=[dest],
            # duration_seconds : exploité par ContentStudio pour caler le montage/sous-titres.
            meta={"voice": voice, "lang": lang,
                  "duration_seconds": len(full_audio) / _SAMPLE_RATE},
        )

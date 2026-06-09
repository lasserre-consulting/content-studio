"""Provider musique local via audiocraft (MusicGen, par Meta).

Génère de la musique à partir d'un prompt texte, entièrement en local sur le
GPU. Sur une RTX 2080 SUPER (8 Go), le modèle "medium" tient en VRAM ; les
modèles plus gros ("large") risquent l'OOM. Le modèle est chargé une seule fois
puis mis en cache sur l'instance, car le routeur réutilise le même provider.
"""
from __future__ import annotations

import logging
from pathlib import Path

from studio.config import Config
from studio.core import BaseProvider, GenRequest, GenResult, Location, Modality, register

log = logging.getLogger("studio.music.musicgen")

# Plafond de durée : au-delà, le risque d'OOM sur 8 Go devient sérieux.
_MAX_DURATION = 30


@register
class MusicGenLocal(BaseProvider):
    name = "musicgen-local"
    modality = Modality.MUSIC
    location = Location.LOCAL
    min_vram_gb = 8

    # Compteur d'instance pour des noms de fichiers uniques sans dépendre de l'horloge.
    _counter = 0

    def available(self) -> tuple[bool, str]:
        # Vérifs rapides et sans effet de bord : on ne charge surtout pas le modèle.
        try:
            import audiocraft  # noqa: F401
        except ImportError:
            return False, "paquet 'audiocraft' non installé (pip install audiocraft)"
        try:
            import torch
        except ImportError:
            return False, "paquet 'torch' non installé"
        if not torch.cuda.is_available():
            return False, "CUDA indisponible (GPU requis pour MusicGen)"
        return True, "ok"

    def _ensure_model(self):
        """Charge MusicGen une seule fois et le met en cache sur l'instance."""
        if getattr(self, "_model", None) is None:
            # Import paresseux : audiocraft tire torch + diffusion, trop lourd au top-level.
            from audiocraft.models import MusicGen

            model_name = self.config.get("model", "facebook/musicgen-medium")
            self._model = MusicGen.get_pretrained(model_name)
        return self._model

    def generate(self, req: GenRequest) -> GenResult:
        import torch
        from audiocraft.data.audio import audio_write

        # Libère la VRAM fragmentée avant de charger/générer : MusicGen + SDXL
        # chargés ensemble frôlent les 8 Go (short() fait image PUIS musique).
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        model = self._ensure_model()
        model_name = self.config.get("model", "facebook/musicgen-medium")

        # Durée : requête > config > 15 s, plafonnée pour éviter l'OOM.
        duration = int(req.get("duration") or self.config.get("duration", 15))
        duration = max(1, min(duration, _MAX_DURATION))
        model.set_generation_params(duration=duration)

        out_dir = Config.load().output_dir
        MusicGenLocal._counter += 1
        # audio_write ajoute lui-même l'extension .wav, on donne donc un stem sans suffixe.
        stem = out_dir / f"musicgen_{MusicGenLocal._counter}"
        try:
            # MusicGen attend une liste de prompts, renvoie un batch de tenseurs.
            wav = model.generate([req.prompt])
            audio_write(str(stem), wav[0].cpu(), model.sample_rate, strategy="loudness")
        except Exception as e:  # OOM, disque plein, audio corrompu… → erreur exploitable
            raise RuntimeError(f"MusicGen a échoué (durée={duration}s) : {e}") from e
        wav_path = stem.with_suffix(".wav")

        return GenResult(
            modality=Modality.MUSIC,
            provider=self.name,
            location=self.location,
            paths=[Path(wav_path)],
            meta={"model": model_name, "duration": duration},
        )

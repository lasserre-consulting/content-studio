"""Socle commun aux providers Stable Audio 3 (Stability AI, mai 2026).

Musique et SFX partagent exactement le même chemin d'inférence — seuls le
modèle, la modalité et la durée par défaut changent. Le code vit donc ici une
seule fois ; `music/stableaudio_music.py` et `sfx/stableaudio_sfx.py` ne sont
que deux sous-classes de trois lignes.

Pourquoi ce socle existe : il remplace audiocraft (MusicGen + AudioGen), qui
épingle torch==2.1 et impose par ricochet toute une cascade de contraintes
(ABI xformers, DLL scikit-learn, conflit av). Voir constraints.txt.

Modèles (poids ouverts, Stability AI Community License) :
    stabilityai/stable-audio-3-small-music   0.6 B — musique complète
    stabilityai/stable-audio-3-small-sfx     0.6 B — effets sonores
    stabilityai/stable-audio-3-medium        2 B   — musicalité supérieure, jusqu'à 6:20

Sur 8 Go de VRAM en float16, les variantes "small" tiennent très large
(~2-4 Go) et génèrent en 8 steps. La "medium" est envisageable mais laisse
peu de marge si SDXL est chargé en parallèle.
"""
from __future__ import annotations

import logging
import random
from pathlib import Path

from studio.config import Config
from studio.core import BaseProvider, GenRequest, GenResult, Location

log = logging.getLogger("studio.stableaudio")


class StableAudioBase(BaseProvider):
    """Base partagée : chargement paresseux, mise en cache, écriture du WAV.

    Les sous-classes définissent `name`, `modality`, `default_model`,
    `default_duration` et `max_duration`.
    """

    location = Location.LOCAL
    min_vram_gb = 4

    default_model: str = "stabilityai/stable-audio-3-small-music"
    default_duration: int = 15
    # Plafond de sécurité. Les "small" acceptent bien plus, mais on garde une
    # marge : le studio charge parfois SDXL et l'audio dans la même session.
    max_duration: int = 120

    # Compteur de classe pour des noms de fichiers uniques sans dépendre de
    # l'horloge (même approche que MusicGenLocal, évite les collisions de glob).
    _counter = 0

    # -- disponibilité --------------------------------------------------------

    def available(self) -> tuple[bool, str]:
        """Vérifs rapides et sans effet de bord — surtout ne pas charger le modèle."""
        try:
            import stable_audio_tools  # noqa: F401
        except ImportError:
            return False, "paquet 'stable-audio-tools' non installé (pip install stable-audio-tools)"
        try:
            import torch  # noqa: F401
        except ImportError:
            return False, "paquet 'torch' non installé"
        # Pas d'exigence CUDA : les variantes "small" tournent aussi sur CPU
        # (plus lentement). C'est un gain net face à MusicGen, qui exigeait un GPU.
        return True, "ok"

    # -- chargement -----------------------------------------------------------

    def _model_name(self) -> str:
        return self.config.get("model", self.default_model)

    def _ensure_model(self):
        """Charge le modèle une seule fois et le met en cache sur l'instance."""
        if getattr(self, "_model", None) is None:
            # Import paresseux : stable_audio_tools tire torch, trop lourd au top-level.
            import torch
            from stable_audio_tools import get_pretrained_model

            name = self._model_name()
            log.info("Chargement de %s (première fois, peut être long)…", name)
            model, model_config = get_pretrained_model(name)

            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = model.to(device)
            if device == "cuda":
                # float16 sur GPU : divise l'empreinte VRAM par deux, sans perte
                # audible sur ces modèles.
                model = model.to(torch.float16)

            self._model = model
            self._model_config = model_config
            self._device = device
        return self._model, self._model_config, self._device

    # -- génération -----------------------------------------------------------

    def generate(self, req: GenRequest) -> GenResult:
        import torch
        import torchaudio
        from einops import rearrange
        from stable_audio_tools.inference.generation import generate_diffusion_cond_inpaint

        # Libère la VRAM fragmentée avant de charger/générer : un pipeline qui
        # fait image PUIS audio frôle sinon le plafond des 8 Go.
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        model, model_config = self._ensure_model()[:2]
        device = self._device

        # Durée : requête > config > défaut de la sous-classe, plafonnée.
        duration = int(req.get("duration") or self.config.get("duration", self.default_duration))
        duration = max(1, min(duration, self.max_duration))

        steps = int(req.get("steps") or self.config.get("steps", 8))
        cfg_scale = float(req.get("cfg_scale") or self.config.get("cfg_scale", 1.0))

        # Graine explicite, pour deux raisons.
        # 1) Bug Windows : laissee a -1, stable-audio-tools tire lui-meme
        #    `np.random.randint(0, 2**32 - 1)` SANS dtype, ce qui deborde l'int32
        #    sous Windows et leve « high is out of bounds for int32 ».
        # 2) Reproductibilite : la graine effective part dans meta, donc une
        #    generation reussie peut etre rejouee a l'identique.
        seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)

        sample_rate = model_config["sample_rate"]
        sample_size = model_config["sample_size"]

        out_dir = Config.load().output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        type(self)._counter += 1
        wav_path = out_dir / f"{self.name.replace('-', '_')}_{type(self)._counter}.wav"

        conditioning = [{"prompt": req.prompt, "seconds_total": duration}]

        try:
            output = generate_diffusion_cond_inpaint(
                model,
                steps=steps,
                cfg_scale=cfg_scale,
                conditioning=conditioning,
                sample_size=sample_size,
                sampler_type="pingpong",
                seed=seed,
                device=device,
            )
            # (batch, canaux, échantillons) -> (canaux, échantillons) attendu par torchaudio
            output = rearrange(output, "b d n -> d (b n)")

            # Le modèle rend TOUJOURS `sample_size` échantillons (≈11 s sur les
            # "small"), quelle que soit la durée demandée : `seconds_total`
            # conditionne le CONTENU, pas la longueur du tenseur. Sans cette
            # coupe, un SFX de 5 s arrive en 11 s, avec du silence ou de la
            # matière parasite au bout.
            attendu = int(duration * sample_rate)
            if output.shape[-1] > attendu:
                output = output[..., :attendu]
            # Normalisation puis conversion en PCM 16 bits stéréo.
            output = (
                output.to(torch.float32)
                .div(torch.max(torch.abs(output)))
                .clamp(-1, 1)
                .mul(32767)
                .to(torch.int16)
                .cpu()
            )
            torchaudio.save(str(wav_path), output, sample_rate)
        except Exception as e:  # OOM, disque plein, audio corrompu… → erreur exploitable
            raise RuntimeError(
                f"Stable Audio a échoué ({self._model_name()}, durée={duration}s, steps={steps}) : {e}"
            ) from e

        return GenResult(
            modality=self.modality,
            provider=self.name,
            location=self.location,
            paths=[Path(wav_path)],
            meta={
                "model": self._model_name(),
                "duration": duration,
                "steps": steps,
                "cfg_scale": cfg_scale,
                "seed": seed,
                "sample_rate": sample_rate,
                "device": device,
            },
        )

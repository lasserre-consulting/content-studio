"""Provider vidéo cloud via fal.ai (text-to-video, ex. Kling).

fal.ai expose plusieurs modèles text-to-video derrière UNE clé API. C'est
notre solution vidéo "cloud" puisqu'aucun modèle vidéo ne tient sur 8 Go de
VRAM. Même style que studio/providers/image/fal_image.py.
"""
from __future__ import annotations

import os
import time
import urllib.request
from pathlib import Path

from studio.config import Config
from studio.core import BaseProvider, GenRequest, GenResult, Location, Modality, register


@register
class FalVideo(BaseProvider):
    name = "fal-video"
    modality = Modality.VIDEO
    location = Location.CLOUD

    def available(self) -> tuple[bool, str]:
        # Vérif rapide et sans effet de bord : clé API + paquet importable.
        if not os.environ.get("FAL_KEY"):
            return False, "FAL_KEY manquante"
        try:
            import fal_client  # noqa: F401
        except ImportError:
            return False, "paquet 'fal-client' non installé (pip install fal-client)"
        return True, "ok"

    def generate(self, req: GenRequest) -> GenResult:
        # Import paresseux : ne casse pas l'auto-enregistrement si fal-client absent.
        import fal_client

        model = req.get("model") or self.config.get(
            "model", "fal-ai/kling-video/v1/standard/text-to-video"
        )
        args = {"prompt": req.prompt}
        if req.negative_prompt:
            args["negative_prompt"] = req.negative_prompt
        if req.seed is not None:
            args["seed"] = req.seed

        result = fal_client.subscribe(model, arguments=args, with_logs=False)

        # La réponse contient un seul objet vidéo {"video": {"url": ...}}.
        url = result["video"]["url"]
        out_dir = Config.load().output_dir
        dest = out_dir / f"fal_video_{int(time.time())}.mp4"
        urllib.request.urlretrieve(url, dest)

        return GenResult(
            modality=Modality.VIDEO,
            provider=self.name,
            location=self.location,
            paths=[dest],
            meta={"model": model},
        )

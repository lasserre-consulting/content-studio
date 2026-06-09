"""Provider image cloud via fal.ai (agrégateur : Flux, SDXL, etc.).

fal.ai expose des dizaines de modèles derrière UNE clé API. C'est notre
fallback "qualité supérieure" quand le GPU 8 Go local ne suffit pas.
Sert aussi de référence pour le contrat BaseProvider côté image.
"""
from __future__ import annotations

import os
import time
import urllib.request
from pathlib import Path

from studio.config import Config
from studio.core import BaseProvider, GenRequest, GenResult, Location, Modality, register


@register
class FalImage(BaseProvider):
    name = "fal-image"
    modality = Modality.IMAGE
    location = Location.CLOUD

    def available(self) -> tuple[bool, str]:
        if not os.environ.get("FAL_KEY"):
            return False, "FAL_KEY manquante"
        try:
            import fal_client  # noqa: F401
        except ImportError:
            return False, "paquet 'fal-client' non installé (pip install fal-client)"
        return True, "ok"

    def generate(self, req: GenRequest) -> GenResult:
        import fal_client

        model = req.get("model") or self.config.get("model", "fal-ai/flux/dev")
        args = {
            "prompt": req.prompt,
            "image_size": req.get("image_size", "square_hd"),
            "num_images": req.get("num_images", 1),
        }
        if req.seed is not None:
            args["seed"] = req.seed

        result = fal_client.subscribe(model, arguments=args, with_logs=False)

        out_dir = Config.load().output_dir
        paths: list[Path] = []
        for i, img in enumerate(result.get("images", [])):
            dest = out_dir / f"fal_{int(time.time())}_{i}.png"
            urllib.request.urlretrieve(img["url"], dest)
            paths.append(dest)

        return GenResult(
            modality=Modality.IMAGE,
            provider=self.name,
            location=self.location,
            paths=paths,
            meta={"model": model, "seed": result.get("seed")},
        )

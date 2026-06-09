"""Provider image local "sdxl-local" via diffusers (StableDiffusionXLPipeline).

Génère des images en 1024x1024 directement sur le GPU de la machine, sans
appel réseau. Conçu pour une RTX 2080 SUPER (8 Go VRAM) : on active donc des
optimisations mémoire agressives (CPU offload + VAE slicing) qui échangent un
peu de vitesse contre la capacité à tenir dans 8 Go.

Tous les imports lourds (torch, diffusers) sont faits *dans* les méthodes :
si la dépendance manque, le module reste importable et l'auto-enregistrement
des autres providers ne casse pas.
"""
from __future__ import annotations

from pathlib import Path

from studio.config import Config
from studio.core import BaseProvider, GenRequest, GenResult, Location, Modality, register


@register
class SDXLLocal(BaseProvider):
    name = "sdxl-local"
    modality = Modality.IMAGE
    location = Location.LOCAL
    min_vram_gb = 8.0

    # Pipeline mis en cache sur l'instance (le routeur réutilise l'instance,
    # on ne recharge donc le modèle qu'une seule fois).
    _pipe = None
    # Compteur d'images pour des noms de fichiers uniques sans time.time().
    _counter = 0

    def available(self) -> tuple[bool, str]:
        """Vérif rapide et sans effet de bord : pas de chargement de modèle."""
        try:
            import torch  # noqa: F401
        except ImportError:
            return False, "paquet 'torch' non installé (pip install torch)"
        try:
            import diffusers  # noqa: F401
        except ImportError:
            return False, "paquet 'diffusers' non installé (pip install diffusers)"
        if not torch.cuda.is_available():
            return False, "CUDA indisponible"
        return True, "ok"

    def _load_pipe(self):
        """Charge le pipeline SDXL une seule fois et le met en cache."""
        if self._pipe is not None:
            return self._pipe

        import torch
        from diffusers import DPMSolverMultistepScheduler, StableDiffusionXLPipeline

        model = self.config.get("model", "stabilityai/stable-diffusion-xl-base-1.0")
        pipe = StableDiffusionXLPipeline.from_pretrained(
            model,
            torch_dtype=torch.float16,
            use_safetensors=True,
            variant="fp16",
        )
        pipe = pipe.to("cuda")

        # --- Scheduler rapide : DPM++ 2M Karras ---
        # Converge en ~20 steps là où le scheduler par défaut en demande ~30,
        # à qualité équivalente. ~30 % de temps de génération en moins, gratuit.
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(
            pipe.scheduler.config, algorithm_type="dpmsolver++", use_karras_sigmas=True
        )

        # --- Optimisations mémoire 8 Go (obligatoires) ---
        # Décharge les sous-modules sur le CPU et ne les remonte sur le GPU
        # qu'au moment où ils servent : indispensable pour tenir dans 8 Go.
        pipe.enable_model_cpu_offload()
        # Découpe le décodage VAE (API moderne) + tiling : évite le pic mémoire
        # final et sécurise les grandes résolutions. attention_slicing réduit
        # encore l'empreinte de l'attention. Marge anti-OOM sur 8 Go.
        pipe.vae.enable_slicing()
        pipe.vae.enable_tiling()
        pipe.enable_attention_slicing()

        self.__class__._pipe = pipe
        return pipe

    def generate(self, req: GenRequest) -> GenResult:
        import torch

        pipe = self._load_pipe()

        model = self.config.get("model", "stabilityai/stable-diffusion-xl-base-1.0")
        steps = req.get("steps", self.config.get("steps", 20))
        width = req.get("width", self.config.get("width", 1024))
        height = req.get("height", self.config.get("height", 1024))
        # Échelle CFG (adhérence au prompt) et negative_prompt par défaut : deux
        # leviers qualité gratuits. La requête prime, sinon la config.
        guidance = req.get("guidance_scale", self.config.get("guidance_scale", 7.5))
        negative = req.negative_prompt or self.config.get("negative_prompt") or None

        # Générateur déterministe si une seed est fournie.
        generator = None
        if req.seed is not None:
            generator = torch.Generator("cuda").manual_seed(req.seed)

        result = pipe(
            prompt=req.prompt,
            negative_prompt=negative,
            num_inference_steps=steps,
            guidance_scale=guidance,
            width=width,
            height=height,
            generator=generator,
        )
        image = result.images[0]

        # Nom de fichier unique via un compteur de classe (pas de time.time()).
        self.__class__._counter += 1
        out_dir = Config.load().output_dir
        dest = out_dir / f"sdxl_{self.__class__._counter:04d}.png"
        image.save(dest)

        return GenResult(
            modality=Modality.IMAGE,
            provider=self.name,
            location=self.location,
            paths=[dest],
            meta={"model": model, "seed": req.seed, "steps": steps},
        )

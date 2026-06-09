"""Le contrat que TOUT provider doit respecter.

Ajouter un nouveau modèle (local ou cloud) = écrire une classe qui hérite de
BaseProvider (ou LLMProvider), décorée par @register. Rien d'autre dans le
reste du code n'a besoin de changer : le routeur la découvre toute seule.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .types import GenRequest, GenResult, Location, Modality


class BaseProvider(ABC):
    """Classe de base de tous les providers de génération.

    Attributs de classe à définir dans chaque sous-classe :
        name        identifiant unique (ex: "sdxl-local", "fal-image")
        modality    Modality gérée
        location    LOCAL ou CLOUD
        min_vram_gb VRAM minimale conseillée (0 si cloud / CPU)
    """
    name: str = "base"
    modality: Modality
    location: Location = Location.LOCAL
    min_vram_gb: float = 0.0

    def __init__(self, **config):
        # config vient de providers.yaml (section settings du provider) + .env
        self.config = config

    def available(self) -> tuple[bool, str]:
        """Le provider peut-il tourner ici, maintenant ?

        Renvoie (ok, raison). Surchargé pour vérifier une clé API, la présence
        d'un modèle téléchargé, assez de VRAM, etc. Doit rester *rapide et sans
        effet de bord* : le routeur l'appelle avant chaque tentative.
        """
        return True, "ok"

    @abstractmethod
    def generate(self, req: GenRequest) -> GenResult:
        """Produit le contenu. C'est le seul point d'entrée réel."""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name} ({self.location})>"


class LLMProvider(BaseProvider):
    """Spécialisation pour le texte : Anthropic, OpenAI, Ollama local, etc.

    On expose complete() comme API naturelle ; generate() y délègue pour rester
    compatible avec le routeur unifié.
    """
    modality = Modality.LLM

    @abstractmethod
    def complete(self, prompt: str, *, system: str | None = None, **kwargs) -> str:
        ...

    def generate(self, req: GenRequest) -> GenResult:
        text = self.complete(
            req.prompt,
            system=req.get("system"),
            **{k: v for k, v in req.params.items() if k != "system"},
        )
        return GenResult(
            modality=Modality.LLM,
            provider=self.name,
            location=self.location,
            text=text,
            meta={"model": self.config.get("model")},
        )

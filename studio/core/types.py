"""Types partagés par tout le studio.

Tout passe par GenRequest (ce qu'on demande) et GenResult (ce qu'on récupère),
quelle que soit la modalité ou le provider. C'est ce qui rend les providers
interchangeables : ils parlent tous le même langage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Modality(str, Enum):
    """Les grands types de contenu que le studio sait générer."""
    LLM = "llm"      # texte (chat / complétion / amélioration de prompt)
    IMAGE = "image"
    VIDEO = "video"
    MUSIC = "music"
    SFX = "sfx"
    TTS = "tts"      # voix de synthèse

    def __str__(self) -> str:  # pour un affichage propre en CLI
        return self.value


class Location(str, Enum):
    """Où tourne un provider."""
    LOCAL = "local"   # sur le GPU/CPU de la machine
    CLOUD = "cloud"   # via une API distante


@dataclass
class GenRequest:
    """Une demande de génération, agnostique du provider."""
    prompt: str
    modality: Modality
    negative_prompt: str | None = None
    seed: int | None = None
    # Tous les réglages spécifiques (steps, width, duration, voice, model...) vivent ici.
    params: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)


@dataclass
class GenResult:
    """Le résultat d'une génération."""
    modality: Modality
    provider: str
    location: Location
    text: str | None = None          # rempli pour la modalité LLM
    paths: list[Path] = field(default_factory=list)  # fichiers produits (png, wav, mp4...)
    meta: dict[str, Any] = field(default_factory=dict)  # seed effective, modèle, coût estimé...

    @property
    def path(self) -> Path | None:
        """Raccourci pour le premier fichier produit."""
        return self.paths[0] if self.paths else None

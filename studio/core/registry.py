"""Registre global des providers.

Chaque provider se déclare avec @register. Le registre permet ensuite de
retrouver une classe par (modalité, nom) sans que le routeur connaisse les
modules concrets. C'est le mécanisme qui rend l'ajout de modèles "plug-in".
"""
from __future__ import annotations

from .provider import BaseProvider
from .types import Modality

# (modality, name) -> classe de provider
_REGISTRY: dict[tuple[Modality, str], type[BaseProvider]] = {}


def register(cls: type[BaseProvider]) -> type[BaseProvider]:
    """Décorateur d'enregistrement. À poser sur chaque classe de provider."""
    if not getattr(cls, "name", None) or cls.name == "base":
        raise ValueError(f"{cls.__name__}: attribut de classe 'name' manquant")
    if not getattr(cls, "modality", None):
        raise ValueError(f"{cls.__name__}: attribut de classe 'modality' manquant")
    key = (cls.modality, cls.name)
    if key in _REGISTRY:
        raise ValueError(f"Provider déjà enregistré: {key}")
    _REGISTRY[key] = cls
    return cls


def get_provider_class(modality: Modality, name: str) -> type[BaseProvider]:
    try:
        return _REGISTRY[(modality, name)]
    except KeyError:
        known = [n for (m, n) in _REGISTRY if m == modality]
        raise KeyError(
            f"Provider '{name}' introuvable pour {modality}. Connus: {known or 'aucun'}"
        )


def list_providers(modality: Modality | None = None) -> list[str]:
    return [
        f"{m}:{n}" for (m, n) in sorted(_REGISTRY, key=lambda k: (k[0].value, k[1]))
        if modality is None or m == modality
    ]

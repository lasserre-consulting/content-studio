"""Chargement de la configuration : providers.yaml + variables d'environnement (.env)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .core.types import Modality

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "providers.yaml"


def _load_dotenv(path: Path) -> None:
    """Mini-parseur .env (évite une dépendance). Ne réécrit pas les vars déjà posées."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


class Config:
    def __init__(self, data: dict[str, Any]):
        self.data = data

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Config":
        _load_dotenv(ROOT / ".env")
        p = Path(path) if path else DEFAULT_CONFIG
        try:
            raw = p.read_text(encoding="utf-8")
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"Configuration introuvable : {p}\n"
                f"  → copie 'config/providers.yaml' (ou indique un chemin valide)."
            ) from e
        data = yaml.safe_load(raw) or {}
        return cls(data)

    # -- accès --
    @property
    def output_dir(self) -> Path:
        d = ROOT / self.data.get("defaults", {}).get("output_dir", "outputs")
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def prefer(self) -> str:
        return self.data.get("defaults", {}).get("prefer", "local")

    def _section(self, modality: Modality) -> dict[str, Any]:
        return self.data.get(modality.value, {}) or {}

    def chain(self, modality: Modality) -> list[str]:
        """Liste ordonnée des providers à essayer : [active, *fallback]."""
        sec = self._section(modality)
        active = sec.get("active")
        # `or []` : tolère `fallback:` laissé vide (null) dans le YAML.
        chain = ([active] if active else []) + list(sec.get("fallback") or [])
        # dédup en gardant l'ordre
        seen: set[str] = set()
        return [c for c in chain if c and not (c in seen or seen.add(c))]

    def provider_settings(self, modality: Modality, name: str) -> dict[str, Any]:
        """Réglages d'un provider donné, transmis à son constructeur."""
        sec = self._section(modality)
        # `or {}` à chaque niveau : tolère `providers:` ou un bloc provider laissé vide (null).
        providers = sec.get("providers") or {}
        return dict(providers.get(name) or {})


def get_router(path: Path | str | None = None):
    """Point d'entrée principal : construit un Router prêt à l'emploi.

    Importe studio.providers pour déclencher l'auto-enregistrement de tous
    les providers avant de construire le routeur.
    """
    from .core.router import Router
    from . import providers  # noqa: F401 — effet de bord : enregistre les providers

    cfg = Config.load(path)
    return Router(cfg)

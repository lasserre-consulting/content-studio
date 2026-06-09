"""Provider LLM LOCAL "ollama" — texte via un serveur Ollama tournant en local.

Aucune clé API : Ollama expose une API HTTP locale (par défaut sur le port 11434).
On reste sur la stdlib (urllib) pour le ping de disponibilité et la génération,
afin de ne dépendre d'aucun paquet pip.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from studio.core import LLMProvider, Location, register


@register
class OllamaLLM(LLMProvider):
    name = "ollama"
    location = Location.LOCAL

    def _host(self) -> str:
        # Hôte du serveur Ollama, configurable via providers.yaml (clé "host").
        return self.config.get("host", "http://localhost:11434").rstrip("/")

    def available(self) -> tuple[bool, str]:
        # Ping rapide et sans effet de bord : on interroge la liste des modèles.
        host = self._host()
        try:
            req = urllib.request.Request(f"{host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status != 200:
                    return False, f"serveur Ollama injoignable sur {host}"
        except (urllib.error.URLError, OSError):
            # Connexion refusée, DNS, timeout… -> serveur non disponible.
            return False, f"serveur Ollama injoignable sur {host}"
        return True, "ok"

    def complete(self, prompt: str, *, system: str | None = None, **kwargs) -> str:
        host = self._host()
        model = kwargs.pop("model", None) or self.config.get("model", "llama3.1")

        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{host}/api/generate",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        # Pas de timeout court ici : la génération peut être longue.
        timeout = kwargs.pop("timeout", None) or self.config.get("timeout", 300)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        return body.get("response", "")

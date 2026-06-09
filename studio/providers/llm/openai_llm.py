"""Provider LLM OpenAI (GPT). Modèle cloud, même contrat que AnthropicLLM."""
from __future__ import annotations

import os

from studio.core import LLMProvider, Location, register


@register
class OpenAILLM(LLMProvider):
    name = "openai"
    location = Location.CLOUD

    def available(self) -> tuple[bool, str]:
        # Vérif rapide et sans effet de bord : clé API présente + paquet importable.
        if not os.environ.get("OPENAI_API_KEY"):
            return False, "OPENAI_API_KEY manquante"
        try:
            import openai  # noqa: F401
        except ImportError:
            return False, "paquet 'openai' non installé (pip install openai)"
        return True, "ok"

    def complete(self, prompt: str, *, system: str | None = None, **kwargs) -> str:
        # Import paresseux : ne casse pas l'auto-enregistrement si openai manque.
        import openai

        client = openai.OpenAI()  # lit OPENAI_API_KEY depuis l'environnement
        model = kwargs.pop("model", None) or self.config.get("model", "gpt-4o")

        # Construit la liste de messages : message système optionnel + message utilisateur.
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
        )
        # Renvoie le texte de la première réponse.
        return resp.choices[0].message.content or ""

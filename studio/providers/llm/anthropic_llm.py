"""Provider LLM Anthropic (Claude). Sert de référence pour le contrat LLMProvider."""
from __future__ import annotations

import os

from studio.core import LLMProvider, Location, register


@register
class AnthropicLLM(LLMProvider):
    name = "anthropic"
    location = Location.CLOUD

    def available(self) -> tuple[bool, str]:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False, "ANTHROPIC_API_KEY manquante"
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False, "paquet 'anthropic' non installé (pip install anthropic)"
        return True, "ok"

    def complete(self, prompt: str, *, system: str | None = None, **kwargs) -> str:
        import anthropic

        client = anthropic.Anthropic()  # lit ANTHROPIC_API_KEY
        model = kwargs.pop("model", None) or self.config.get("model", "claude-sonnet-4-6")
        max_tokens = kwargs.pop("max_tokens", None) or self.config.get("max_tokens", 2048)
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system or "Tu es un assistant créatif concis.",
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in msg.content if block.type == "text")

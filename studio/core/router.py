"""Le routeur : transforme une demande en résultat en choisissant le bon provider.

Logique de sélection, dans l'ordre :
  1. provider explicite passé à l'appel (override ponctuel)
  2. provider 'active' de la config pour cette modalité
  3. la chaîne 'fallback' de la config, dans l'ordre

Pour chaque candidat on appelle available(). Si indisponible (pas de clé API,
modèle absent, VRAM insuffisante), on passe au suivant. C'est ce qui fait
basculer automatiquement du local vers le cloud.
"""
from __future__ import annotations

import logging

from .provider import BaseProvider
from .registry import get_provider_class, list_providers
from .types import GenRequest, GenResult, Modality

log = logging.getLogger("studio.router")


class NoProviderAvailable(RuntimeError):
    pass


class Router:
    def __init__(self, config):
        self.config = config
        self._instances: dict[tuple[Modality, str], BaseProvider] = {}
        self._preflight_check()

    def _preflight_check(self) -> None:
        """Avertit (sans bloquer) si un provider déclaré 'active'/'fallback' dans
        la config n'est pas enregistré : transforme un échec runtime opaque en
        message clair dès la construction du routeur."""
        for modality in Modality:
            for name in self.config.chain(modality):
                try:
                    get_provider_class(modality, name)
                except KeyError:
                    available = list_providers(modality)
                    log.warning(
                        "Provider '%s' déclaré pour %s mais non enregistré. Disponibles: %s",
                        name, modality, available or "(aucun)",
                    )

    # -- instanciation paresseuse + mise en cache (un modèle local n'est chargé qu'une fois) --
    def _instance(self, modality: Modality, name: str) -> BaseProvider:
        key = (modality, name)
        if key not in self._instances:
            cls = get_provider_class(modality, name)
            settings = self.config.provider_settings(modality, name)
            self._instances[key] = cls(**settings)
        return self._instances[key]

    def _candidates(self, modality: Modality, provider: str | None) -> list[str]:
        if provider:
            return [provider]
        return self.config.chain(modality)

    def generate(
        self,
        modality: Modality,
        prompt: str,
        *,
        provider: str | None = None,
        negative_prompt: str | None = None,
        seed: int | None = None,
        **params,
    ) -> GenResult:
        req = GenRequest(
            prompt=prompt,
            modality=modality,
            negative_prompt=negative_prompt,
            seed=seed,
            params=params,
        )
        tried: list[str] = []
        for name in self._candidates(modality, provider):
            # Instanciation : un __init__ qui lève (ImportError, modèle manquant…)
            # ne doit PAS tuer la chaîne — on traite ça comme une indisponibilité.
            try:
                prov = self._instance(modality, name)
            except KeyError as e:
                log.warning("Provider inconnu ignoré: %s", e)
                tried.append(f"{name} (inconnu)")
                continue
            except Exception as e:  # noqa: BLE001 — on veut basculer sur le fallback
                log.warning("Init %s:%s a échoué, on passe au suivant — %s", modality, name, e)
                tried.append(f"{name} (init: {e})")
                continue
            # available() doit rester sûr ; si elle lève quand même, idem : on bascule.
            try:
                ok, reason = prov.available()
            except Exception as e:  # noqa: BLE001
                log.warning("available() de %s:%s a levé, on passe au suivant — %s",
                            modality, name, e)
                tried.append(f"{name} (available: {e})")
                continue
            if not ok:
                log.info("Skip %s:%s — %s", modality, name, reason)
                tried.append(f"{name} (indispo: {reason})")
                continue
            log.info("→ génération via %s:%s", modality, name)
            return prov.generate(req)
            # NB: si generate() lève, on laisse remonter — c'est une vraie erreur,
            # pas une indisponibilité. On ne masque pas les bugs derrière un fallback.
        raise NoProviderAvailable(
            f"Aucun provider disponible pour {modality}. Essayés: {tried or 'aucun configuré'}"
        )

    # raccourcis confort
    def llm(self, prompt: str, **kw) -> str:
        return self.generate(Modality.LLM, prompt, **kw).text or ""

    def image(self, prompt: str, **kw) -> GenResult:
        return self.generate(Modality.IMAGE, prompt, **kw)

    def video(self, prompt: str, **kw) -> GenResult:
        return self.generate(Modality.VIDEO, prompt, **kw)

    def music(self, prompt: str, **kw) -> GenResult:
        return self.generate(Modality.MUSIC, prompt, **kw)

    def sfx(self, prompt: str, **kw) -> GenResult:
        return self.generate(Modality.SFX, prompt, **kw)

    def tts(self, prompt: str, **kw) -> GenResult:
        return self.generate(Modality.TTS, prompt, **kw)

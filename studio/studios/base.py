"""Base commune aux studios.

Un Studio possède :
  - un Router (le moteur de génération, partagé),
  - un dossier de travail (workspace) où atterrissent les livrables,
  - des helpers transverses : génération avec repli silencieux, variations par
    seed, et une boucle d'itération « génère N candidats, garde le meilleur ».

Tout est conçu pour qu'un agent pilote le studio en quelques appels et puisse
ré-itérer agressivement (c'est l'objectif : produire vite, en boucle).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Callable

from ..core import GenResult, Modality, Router
from ..core.router import NoProviderAvailable

log = logging.getLogger("studio.studios")


def slugify(text: str, *, max_len: int = 48) -> str:
    """Transforme un texte libre en nom de fichier ASCII-safe et lisible.

    Les accents sont translittérés (é→e, ç→c) : indispensable pour des noms
    d'assets sûrs côté système de fichiers et imports Godot."""
    text = text.strip().lower()
    # Décompose puis retire les diacritiques (NFKD → drop des marques combinantes).
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return (text[:max_len].rstrip("-")) or "sans-titre"


class Studio:
    """Studio générique. Les studios concrets héritent et ajoutent leurs pipelines."""

    def __init__(self, router: Router, workspace: Path | str):
        self.router = router
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

    # -- emplacements ----------------------------------------------------------
    def path(self, *parts: str) -> Path:
        """Construit un chemin dans le workspace, en créant les dossiers parents."""
        dest = self.workspace.joinpath(*parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        return dest

    # -- génération ------------------------------------------------------------
    def gen(self, modality: Modality, prompt: str, **kw) -> GenResult:
        """Appel direct au routeur (laisse remonter les vraies erreurs)."""
        log.info("[%s] génération %s: %s", type(self).__name__, modality, prompt[:60])
        return self.router.generate(modality, prompt, **kw)

    def try_gen(self, modality: Modality, prompt: str, **kw) -> GenResult | None:
        """Comme gen() mais renvoie None si aucun provider n'est dispo.

        Utile dans un pipeline composite : si la musique de fond échoue (modèle
        pas installé), on veut quand même livrer la vidéo avec la seule voix."""
        try:
            return self.gen(modality, prompt, **kw)
        except NoProviderAvailable as e:
            log.warning("[%s] %s indisponible — étape ignorée : %s",
                        type(self).__name__, modality, e)
            return None

    # -- amélioration de prompt (optionnelle, via LLM) -------------------------
    def refine(self, prompt: str, instruction: str) -> str:
        """Demande au LLM d'enrichir un prompt. Si aucun LLM n'est dispo, renvoie
        le prompt d'origine inchangé (jamais bloquant)."""
        res = self.try_gen(
            Modality.LLM,
            f"{instruction}\n\nPrompt: {prompt}\n\nRéponds UNIQUEMENT par le prompt amélioré.",
        )
        return (res.text or prompt).strip() if res else prompt

    # -- itération -------------------------------------------------------------
    def variations(
        self,
        modality: Modality,
        prompt: str,
        *,
        n: int = 4,
        base_seed: int = 1000,
        **kw,
    ) -> list[GenResult]:
        """Génère n variations du même prompt (seeds différentes). Le cœur de la
        ré-itération rapide : on produit un lot, on choisit après coup."""
        out: list[GenResult] = []
        for i in range(n):
            res = self.try_gen(modality, prompt, seed=base_seed + i, **kw)
            if res:
                out.append(res)
        return out

    def best_of(
        self,
        modality: Modality,
        prompt: str,
        *,
        n: int = 4,
        score: Callable[[GenResult], float] | None = None,
        **kw,
    ) -> GenResult | None:
        """Génère n candidats et renvoie le meilleur selon `score`.

        Sans fonction de score, renvoie simplement le premier candidat. Le point
        d'extension naturel : brancher un juge (LLM vision / heuristique) pour
        une boucle de sélection automatique."""
        cands = self.variations(modality, prompt, n=n, **kw)
        if not cands:
            return None
        if score is None:
            return cands[0]
        return max(cands, key=score)

"""Les studios : couche d'orchestration métier au-dessus du moteur.

Le moteur (core/router + providers) sait générer un fichier isolé pour une
modalité. Un *studio* enchaîne plusieurs générations + assemblage pour produire
un livrable complet, et expose une API pensée pour être pilotée par un agent
(boucles d'itération, variations, batch).

- ContentStudio : production sociale (shorts verticaux, narration, vignettes).
- GamedevStudio : production d'assets de jeu (sprites, BGM, SFX, voix) + ré-itération.
"""
from .base import Studio
from .content import ContentStudio
from .gamedev import GamedevStudio

__all__ = ["Studio", "ContentStudio", "GamedevStudio"]

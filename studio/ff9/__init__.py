"""Générateurs procéduraux d'assets pour le mod FF9 'La Troisième Fissure'.

Tier 1 : assets dont la bible visuelle donne une spécification EXACTE (hex,
géométrie, dimensions, alpha) → produits par du code PIL/numpy déterministe,
pixel-perfect, sans modèle génératif ni artiste.

Chaque sous-module `gen_<catégorie>.py` expose :
    SUBDIR : str            # sous-dossier cible dans EmbeddedAsset/
    generate(out_root: Path) -> list[Path]   # écrit ses PNG, renvoie les chemins

`common.py` fournit les primitives partagées (vignette, sphère, anneaux,
spritesheets, texte) pour garantir la cohérence entre catégories.
"""

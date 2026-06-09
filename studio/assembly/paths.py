"""Robustesse des chemins pour les outils tiers récalcitrants.

Certains outils (agents de vision, binaires de modèles, scripts externes) se
comportent mal — voire échouent — sur des chemins contenant des espaces, des
accents ou d'autres caractères non-ASCII (ex. ``le repère des sorcières`` ou
``C:\\Program Files (x86)\\...``). Python, lui, manipule ces chemins sans
problème : c'est uniquement la couche tierce qui patauge.

La parade éprouvée à la main : copier les entrées dans un dossier ASCII propre,
lancer le traitement là-bas, puis recopier les sorties vers l'emplacement
d'origine (qui peut, lui, contenir espaces et accents). Ce module automatise
exactement ce flux via :

  - :func:`is_ascii_safe`   — diagnostic d'un chemin,
  - :func:`to_ascii_slug`   — translittération nom libre -> nom ASCII-safe,
  - :func:`ascii_workspace` — context manager de staging/destaging.

Aucune dépendance lourde : stdlib uniquement (``unicodedata`` pour translittérer).
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence


def is_ascii_safe(path: str | os.PathLike) -> bool:
    """Renvoie ``True`` si le chemin est sûr pour un outil tiers fragile.

    Est considéré comme problématique tout caractère non-ASCII (accents,
    caractères composés...) ainsi que les espaces, qui cassent fréquemment les
    invocations en ligne de commande mal quotées. On inspecte la chaîne
    complète du chemin (dossiers parents inclus), car le problème vient souvent
    d'un dossier intermédiaire (``Program Files``, ``le repère``...).
    """
    text = os.fspath(path)
    for ch in text:
        # Au-delà de l'ASCII (>127) : accents et autres -> risque.
        if ord(ch) > 127:
            return False
        # Les espaces cassent beaucoup d'invocations CLI non quotées.
        if ch.isspace():
            return False
    return True


def to_ascii_slug(name: str) -> str:
    """Translittère un nom libre en identifiant ASCII-safe.

    Réutilise la même logique de translittération que ``slugify`` de
    ``studio/studios/base.py`` (décomposition NFKD puis suppression des marques
    combinantes : é->e, ç->c). Différence assumée : on conserve un séparateur
    par *underscore* (``le repère`` -> ``le_repere``) et on préserve la casse,
    ce qui colle mieux à des noms de fichiers d'entrée déjà nommés par l'humain.

    L'extension de fichier éventuelle est préservée telle quelle (après
    translittération) afin de ne pas perturber les outils qui s'y fient.
    """
    # Sépare une éventuelle extension pour la traiter à part (ex. ".png").
    stem, dot, ext = name.rpartition(".")
    if not dot:  # pas d'extension détectée
        stem, ext = name, ""

    def _translit(part: str) -> str:
        # Décompose puis retire les diacritiques (cf. slugify de base.py).
        part = unicodedata.normalize("NFKD", part)
        part = "".join(c for c in part if not unicodedata.combining(c))
        # Tout ce qui n'est pas alphanumérique ASCII devient un underscore.
        part = re.sub(r"[^A-Za-z0-9]+", "_", part)
        return part.strip("_")

    slug_stem = _translit(stem) or "fichier"
    slug_ext = _translit(ext)
    return f"{slug_stem}.{slug_ext}" if slug_ext else slug_stem


@dataclass
class _Workspace:
    """Poignée exposée par :func:`ascii_workspace` pendant le ``with``."""

    inputs: list[Path]  # chemins ASCII des entrées stagées
    out: Path           # dossier de sortie ASCII (temporaire)


@contextmanager
def ascii_workspace(
    sources: Sequence[str | os.PathLike],
    *,
    out_dir: str | os.PathLike,
) -> Iterator[_Workspace]:
    """Stage des fichiers vers un espace de travail ASCII, le temps d'un bloc.

    Déroulé :
      1. Crée un dossier temporaire garanti ASCII (``tempfile``).
      2. Copie chaque entrée dedans sous un nom ASCII-safe -> ``ws.inputs``.
      3. Fournit un sous-dossier de sortie ASCII -> ``ws.out``.
      4. À la sortie du bloc, recopie tout le contenu de ``ws.out`` vers
         ``out_dir`` (qui peut contenir espaces/accents : Python gère).
      5. Nettoie le dossier temporaire dans tous les cas.

    Exemple ::

        with ascii_workspace([src1, src2], out_dir=quelque_part) as ws:
            traiter(ws.inputs, ws.out)   # outil tiers, chemins 100 % ASCII
        # -> les fichiers produits dans ws.out sont maintenant dans quelque_part
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # mkdtemp() vit sous un chemin temp système : ASCII en pratique sur les OS
    # courants. On force un préfixe ASCII par sécurité.
    tmp_root = Path(tempfile.mkdtemp(prefix="ascii_ws_"))
    in_dir = tmp_root / "in"
    work_out = tmp_root / "out"
    in_dir.mkdir()
    work_out.mkdir()

    try:
        staged: list[Path] = []
        used: set[str] = set()
        for src in sources:
            src = Path(src)
            slug = to_ascii_slug(src.name)
            # Évite les collisions de noms après translittération (deux entrées
            # qui slugifient pareil) en suffixant un index.
            candidate = slug
            i = 1
            while candidate in used:
                stem, dot, ext = slug.rpartition(".")
                if dot:
                    candidate = f"{stem}_{i}.{ext}"
                else:
                    candidate = f"{slug}_{i}"
                i += 1
            used.add(candidate)

            dest = in_dir / candidate
            if src.is_dir():
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
            staged.append(dest)

        ws = _Workspace(inputs=staged, out=work_out)
        yield ws

        # Recopie des sorties vers la destination d'origine (espaces/accents OK).
        for item in work_out.iterdir():
            target = out_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
    finally:
        # Nettoyage best-effort du dossier temporaire.
        shutil.rmtree(tmp_root, ignore_errors=True)

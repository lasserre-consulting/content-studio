"""Base commune aux exporters : adaptateurs vers un moteur/projet cible.

Un *exporter* prend un asset déjà produit (par un studio ou un générateur) et
l'écrit au bon FORMAT, sous le bon NOM, au bon EMPLACEMENT pour un moteur donné.

C'est la couche qui évite de refaire à la main, à chaque session, les mêmes
manipulations :
  - renommer un SFX selon la convention canonique de la cible,
  - convertir un WAV en OGG (Vorbis),
  - reconstruire l'arborescence d'override d'un mod,
  - déposer un sprite transparent au bon endroit d'un projet Godot.

Pourquoi un `EngineProfile` ?
----------------------------
Piège vécu : on a généré des spritesheets 2D pour des persos FF9 qui sont en
réalité des modèles 3D — l'asset était inutilisable. Un *profil* décrit ce qui
est VALIDE pour une cible (quels « asset_kind » existent, ce qu'ils attendent
réellement), de sorte qu'un studio puisse demander au profil « est-ce que des
spritesheets ont un sens pour `characters` ici ? » et se faire répondre non.

Le profil ne convertit rien : il DÉCRIT. La conversion concrète vit dans les
exporters spécialisés (memoria.py, godot.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------- #
# Description d'un type d'asset valide pour une cible                          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AssetKindSpec:
    """Décrit UN type d'asset accepté par un moteur.

    - `audio_format` / `image_format` : format(s) attendu(s) (extensions sans
      point, ex. {"ogg"}). Vide = pas un asset de ce média.
    - `representation` : note libre mais NORMATIVE sur la nature réelle attendue.
      C'est elle qui désamorce le piège des spritesheets : pour des persos 3D on
      y met "3D model textures", pas "2D spritesheet".
    - `subdir` : sous-dossier conventionnel (relatif à la racine du projet/mod).
    """
    kind: str
    audio_formats: frozenset[str] = field(default_factory=frozenset)
    image_formats: frozenset[str] = field(default_factory=frozenset)
    representation: str = ""
    subdir: str = ""

    @property
    def is_audio(self) -> bool:
        return bool(self.audio_formats)

    @property
    def is_image(self) -> bool:
        return bool(self.image_formats)


@dataclass(frozen=True)
class EngineProfile:
    """Carte d'identité d'une cible : QUOI est valide et SOUS QUELLE forme.

    Sert de garde-fou en amont de l'export. Un studio interroge le profil
    (`is_valid_kind`, `kind_spec`, `audio_format`) avant de produire, plutôt que
    de générer en aveugle des assets que la cible ne pourra pas consommer.
    """
    name: str
    kinds: dict[str, AssetKindSpec] = field(default_factory=dict)

    # -- interrogation --------------------------------------------------------
    def is_valid_kind(self, kind: str) -> bool:
        """Ce type d'asset existe-t-il pour cette cible ?"""
        return kind in self.kinds

    def kind_spec(self, kind: str) -> AssetKindSpec:
        """Spec d'un type d'asset ; lève KeyError (message clair) si inconnu."""
        try:
            return self.kinds[kind]
        except KeyError:
            valid = ", ".join(sorted(self.kinds)) or "(aucun)"
            raise KeyError(
                f"[{self.name}] type d'asset inconnu : '{kind}'. "
                f"Types valides : {valid}"
            ) from None

    def audio_format(self, kind: str) -> str | None:
        """Format audio canonique (le premier déclaré) attendu pour ce kind."""
        spec = self.kind_spec(kind)
        return next(iter(sorted(spec.audio_formats)), None) if spec.audio_formats else None

    def check(self, kind: str, *, representation: str | None = None) -> None:
        """Garde-fou : lève ValueError si `kind` est invalide pour la cible, ou
        si la `representation` annoncée par l'appelant ne correspond pas à ce que
        la cible attend (ex. on tente de pousser une « 2D spritesheet » là où la
        cible veut des « 3D model textures »)."""
        if not self.is_valid_kind(kind):
            valid = ", ".join(sorted(self.kinds)) or "(aucun)"
            raise ValueError(
                f"[{self.name}] '{kind}' n'est pas un asset valide pour cette "
                f"cible. Types valides : {valid}"
            )
        if representation is not None:
            expected = self.kinds[kind].representation
            if expected:
                # On ne compare QUE contre la partie positive de la description :
                # tout ce qui suit une clause de négation ("not ...", "pas ...")
                # liste justement les formes À REJETER, pas à accepter.
                positive = re.split(r"\bnot\b|\bpas\b", expected, maxsplit=1)[0]
                if representation.strip().lower() not in positive.lower():
                    raise ValueError(
                        f"[{self.name}] '{kind}' attend « {expected} », "
                        f"pas « {representation} ». Asset probablement inadapté à la cible."
                    )


# --------------------------------------------------------------------------- #
# Interface des exporters                                                      #
# --------------------------------------------------------------------------- #
class Exporter:
    """Interface commune. Un exporter concret connaît un `EngineProfile` et sait
    matérialiser un asset dans l'arborescence de la cible.

    `root` est la racine du projet/mod cible (jamais un chemin Steam en dur :
    c'est l'appelant qui la fournit)."""

    profile: EngineProfile

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def export(self, src_path: Path | str, asset_kind: str, name: str, **opts) -> Path:
        """Écrit `src_path` dans la cible pour le type `asset_kind` sous `name`.

        Renvoie le chemin final écrit. À implémenter par les sous-classes.
        """
        raise NotImplementedError

    # -- utilitaire partagé ---------------------------------------------------
    def _dest(self, *parts: str) -> Path:
        """Chemin sous la racine cible, dossiers parents créés au besoin."""
        dest = self.root.joinpath(*parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        return dest

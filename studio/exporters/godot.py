"""Exporter pour un projet Godot.

Godot importe les assets depuis l'arborescence du projet (généralement sous
`res://`, soit le dossier du projet sur disque). Cet exporter dépose des sprites
PNG (idéalement déjà transparents, cf. GamedevStudio.detour/_cutout) dans une
arborescence propre, avec un slug ASCII-safe pour des noms de fichiers et des
chemins `res://` sans surprise.

Conventions :
    sprite -> assets/sprites/[<categorie>/]<slug>.png
    audio  -> assets/audio/<slug>.<ext>   (ogg ou wav, Godot lit les deux)

La racine (`project_root`) est fournie par l'appelant : aucun chemin codé en dur.
On réutilise `slugify` de studio.studios.base pour le nommage ASCII (é->e, etc.).
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .base import AssetKindSpec, EngineProfile, Exporter

log = logging.getLogger("studio.exporters.godot")

# Formats audio que Godot importe nativement.
_GODOT_AUDIO = frozenset({"ogg", "wav"})


GODOT_PROFILE = EngineProfile(
    name="godot",
    kinds={
        # Les sprites SONT des images 2D ici (contrairement à Memoria/persos 3D).
        "sprite": AssetKindSpec(
            kind="sprite",
            image_formats=frozenset({"png"}),
            representation="2D transparent sprite (PNG RGBA)",
            subdir="assets/sprites",
        ),
        "audio": AssetKindSpec(
            kind="audio",
            audio_formats=_GODOT_AUDIO,
            representation="OGG or WAV audio",
            subdir="assets/audio",
        ),
    },
)


def _slugify(text: str) -> str:
    """slugify partagé du projet si présent, sinon repli ASCII minimal."""
    try:
        from ..studios.base import slugify
        return slugify(text)
    except Exception:  # pragma: no cover - repli si l'arbo studios bouge
        import re
        import unicodedata

        t = unicodedata.normalize("NFKD", text.strip().lower())
        t = "".join(c for c in t if not unicodedata.combining(c))
        t = re.sub(r"[^a-z0-9\s-]", "", t)
        t = re.sub(r"[\s_-]+", "-", t).strip("-")
        return t or "sans-titre"


class GodotExporter(Exporter):
    """Écrit des assets dans un projet Godot. `project_root` = dossier du projet."""

    profile = GODOT_PROFILE

    def __init__(self, project_root: Path | str):
        super().__init__(project_root)

    def export(self, src_path: Path | str, asset_kind: str, name: str, **opts) -> Path:
        """Route selon `asset_kind` (sprite | audio).

        opts:
            category : sous-dossier optionnel (ex. 'ennemis', 'ui').
        """
        self.profile.check(asset_kind)
        if asset_kind == "sprite":
            return self.export_sprite(src_path, name, category=opts.get("category"))
        if asset_kind == "audio":
            return self.export_audio(src_path, name, category=opts.get("category"))
        raise ValueError(f"[godot] kind non géré par export() : {asset_kind}")

    # -- sprite ---------------------------------------------------------------
    def export_sprite(
        self, src_path: Path | str, name: str, *, category: str | None = None
    ) -> Path:
        """Dépose un sprite PNG sous assets/sprites/[<category>/]<slug>.png.

        Le nom est slugifié (ASCII-safe). La source est copiée telle quelle : on
        suppose un PNG déjà transparent (le détourage est du ressort du studio).
        """
        slug = _slugify(name)
        parts = ["assets", "sprites"]
        if category:
            parts.append(_slugify(category))
        parts.append(f"{slug}.png")
        dest = self._dest(*parts)
        if Path(src_path).resolve() != dest.resolve():
            shutil.copyfile(src_path, dest)
        log.info("[godot] sprite -> %s", dest)
        return dest

    # -- audio ----------------------------------------------------------------
    def export_audio(
        self, src_path: Path | str, name: str, *, category: str | None = None
    ) -> Path:
        """Dépose un audio (ogg/wav) sous assets/audio/[<category>/]<slug>.<ext>.

        L'extension d'origine est conservée si Godot la supporte (ogg/wav) ;
        sinon on lève une erreur claire (Godot n'importe pas, p. ex., du .flac
        par cet exporter — convertir en amont au besoin).
        """
        src = Path(src_path)
        ext = src.suffix.lower().lstrip(".")
        if ext not in _GODOT_AUDIO:
            raise ValueError(
                f"[godot] format audio non supporté : .{ext} "
                f"(attendu : {', '.join(sorted(_GODOT_AUDIO))}). Convertir en amont."
            )
        slug = _slugify(name)
        parts = ["assets", "audio"]
        if category:
            parts.append(_slugify(category))
        parts.append(f"{slug}.{ext}")
        dest = self._dest(*parts)
        if src.resolve() != dest.resolve():
            shutil.copyfile(src, dest)
        log.info("[godot] audio -> %s", dest)
        return dest

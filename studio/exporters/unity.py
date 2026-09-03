"""Exporter pour un projet Unity.

Unity importe tout ce qui se trouve sous `Assets/`. Cet exporter y dépose les
livrables du studio avec un nommage ASCII-safe et une arborescence stable.

Deux différences de fond avec l'exporter Godot
----------------------------------------------

1. **On ne convertit PAS le WAV en OGG.** Chez Godot et Memoria, la conversion
   sur disque a du sens. Chez Unity, non : le WAV est la *source* et la
   compression (Vorbis, ADPCM…) est un réglage d'import appliqué au build,
   par plateforme. Convertir en amont revient à compresser deux fois et à
   perdre de la qualité pour rien.

2. **Les réglages d'import comptent plus que le fichier.** Une texture non
   compressée en ASTC peut quadrupler la mémoire ; un SFX court laissé en
   streaming coûte plus cher à jouer qu'à charger. Ces réglages ne vivent pas
   dans le fichier mais dans son `.meta`.

Pourquoi un AssetPostprocessor plutôt que des `.meta` écrits à la main
----------------------------------------------------------------------
Écrire des `.meta` soi-même est fragile : le format est versionné, verbeux, et
un champ manquant se solde par un import silencieusement faux. Unity fournit le
mécanisme prévu pour ça — `AssetPostprocessor` — qui applique les réglages à
l'import, de façon déterministe et indépendante de la version du format.

`install_postprocessor()` dépose ce script dans le projet. Les assets exportés
tombent alors automatiquement sur les bons réglages, sans clic ni discipline.

Conventions d'arborescence
--------------------------
    sprite -> Assets/Art/Sprites/[<categorie>/]<slug>.png
    music  -> Assets/Audio/Music/[<categorie>/]<slug>.wav
    sfx    -> Assets/Audio/SFX/[<categorie>/]<slug>.wav
    voice  -> Assets/Audio/Voice/[<categorie>/]<slug>.wav

La racine (`project_root`) est fournie par l'appelant : aucun chemin en dur.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .base import AssetKindSpec, EngineProfile, Exporter

log = logging.getLogger("studio.exporters.unity")

# Formats audio qu'Unity importe nativement et qu'on accepte ici.
# Le WAV est la source privilégiée (cf. en-tête) ; l'OGG est toléré si l'appelant
# n'a que ça sous la main.
_UNITY_AUDIO = frozenset({"wav", "ogg"})

# Sous-dossier par type d'asset audio. Le postprocessor s'appuie sur ces chemins
# pour décider des réglages : ne pas les changer sans mettre le C# à jour.
_AUDIO_SUBDIR = {
    "music": "Music",
    "sfx": "SFX",
    "voice": "Voice",
}


UNITY_PROFILE = EngineProfile(
    name="unity",
    kinds={
        "sprite": AssetKindSpec(
            kind="sprite",
            image_formats=frozenset({"png"}),
            representation="2D transparent sprite (PNG RGBA)",
            subdir="Assets/Art/Sprites",
        ),
        "music": AssetKindSpec(
            kind="music",
            audio_formats=_UNITY_AUDIO,
            representation="long audio track, streamed",
            subdir="Assets/Audio/Music",
        ),
        "sfx": AssetKindSpec(
            kind="sfx",
            audio_formats=_UNITY_AUDIO,
            representation="short audio effect, decompressed on load",
            subdir="Assets/Audio/SFX",
        ),
        "voice": AssetKindSpec(
            kind="voice",
            audio_formats=_UNITY_AUDIO,
            representation="spoken audio line",
            subdir="Assets/Audio/Voice",
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


# --------------------------------------------------------------------------- #
# Le postprocessor déposé dans le projet Unity                                 #
# --------------------------------------------------------------------------- #
_POSTPROCESSOR_CS = '''// Généré par Content Studio (studio/exporters/unity.py).
// Applique les réglages d'import mobile aux assets déposés par le studio,
// d'après leur emplacement. Modifier ce fichier à la main sera écrasé au
// prochain install_postprocessor().
//
// Pourquoi ce script plutôt que des .meta écrits à la main : le format .meta
// est versionné et verbeux, un champ manquant produit un import silencieusement
// faux. L'AssetPostprocessor est le mécanisme prévu par Unity pour ça.
using UnityEditor;
using UnityEngine;

namespace ContentStudio.Editor
{
    public sealed class ContentStudioAssetPostprocessor : AssetPostprocessor
    {
        const string SpritesRoot = "Assets/Art/Sprites/";
        const string MusicRoot   = "Assets/Audio/Music/";
        const string SfxRoot     = "Assets/Audio/SFX/";
        const string VoiceRoot   = "Assets/Audio/Voice/";

        // Plateformes ciblées pour les surcharges de compression.
        const string Android = "Android";

        void OnPreprocessTexture()
        {
            if (!assetPath.StartsWith(SpritesRoot)) return;

            var importer = (TextureImporter)assetImporter;
            importer.textureType         = TextureImporterType.Sprite;
            importer.spriteImportMode    = SpriteImportMode.Single;
            importer.alphaIsTransparency = true;
            // Pas de mipmaps sur de la 2D d'écran : mémoire gaspillée et flou.
            importer.mipmapEnabled       = false;

            // ASTC est le format compressé attendu sur Android. Sans surcharge
            // explicite, on risque du non compressé (jusqu'à x4 en mémoire).
            var android = new TextureImporterPlatformSettings
            {
                name              = Android,
                overridden        = true,
                maxTextureSize    = 1024,
                format            = TextureImporterFormat.ASTC_6x6,
                textureCompression = TextureImporterCompression.Compressed,
            };
            importer.SetPlatformTextureSettings(android);
        }

        void OnPreprocessAudio()
        {
            var importer = assetImporter as AudioImporter;
            if (importer == null) return;

            bool isMusic = assetPath.StartsWith(MusicRoot);
            bool isSfx   = assetPath.StartsWith(SfxRoot);
            bool isVoice = assetPath.StartsWith(VoiceRoot);
            if (!isMusic && !isSfx && !isVoice) return;

            var settings = importer.defaultSampleSettings;
            settings.compressionFormat = AudioCompressionFormat.Vorbis;

            if (isMusic)
            {
                // Long : on diffuse au lieu de tout charger en mémoire.
                settings.loadType = AudioClipLoadType.Streaming;
                settings.quality  = 0.7f;
            }
            else
            {
                // Court : décompressé au chargement, pour un déclenchement
                // sans latence. C'est le premier poste de mémoire gaspillée
                // quand on l'oublie.
                settings.loadType = AudioClipLoadType.DecompressOnLoad;
                settings.quality  = isVoice ? 0.7f : 0.5f;
                // Un SFX ou une voix n'a pas besoin de stéréo sur mobile.
                importer.forceToMono = true;
            }

            importer.defaultSampleSettings = settings;
        }
    }
}
'''


class UnityExporter(Exporter):
    """Écrit des assets dans un projet Unity. `project_root` = dossier contenant `Assets/`."""

    profile = UNITY_PROFILE

    def __init__(self, project_root: Path | str):
        super().__init__(project_root)

    # -- routage --------------------------------------------------------------
    def export(self, src_path: Path | str, asset_kind: str, name: str, **opts) -> Path:
        """Route selon `asset_kind` (sprite | music | sfx | voice).

        opts:
            category : sous-dossier optionnel (ex. 'ennemis', 'ui').
        """
        self.profile.check(asset_kind)
        category = opts.get("category")
        if asset_kind == "sprite":
            return self.export_sprite(src_path, name, category=category)
        if asset_kind in _AUDIO_SUBDIR:
            return self.export_audio(src_path, asset_kind, name, category=category)
        raise ValueError(f"[unity] kind non géré par export() : {asset_kind}")

    # -- sprite ---------------------------------------------------------------
    def export_sprite(
        self, src_path: Path | str, name: str, *, category: str | None = None
    ) -> Path:
        """Dépose un sprite PNG sous Assets/Art/Sprites/[<category>/]<slug>.png.

        La source est copiée telle quelle : on suppose un PNG déjà transparent,
        le détourage étant du ressort du studio (GamedevStudio.detour).
        """
        src = Path(src_path)
        ext = src.suffix.lower().lstrip(".")
        if ext != "png":
            raise ValueError(
                f"[unity] sprite attendu en .png, reçu .{ext}. Convertir en amont."
            )
        parts = ["Assets", "Art", "Sprites"]
        if category:
            parts.append(_slugify(category))
        parts.append(f"{_slugify(name)}.png")
        dest = self._dest(*parts)
        if src.resolve() != dest.resolve():
            shutil.copyfile(src, dest)
        log.info("[unity] sprite -> %s", dest)
        return dest

    # -- audio ----------------------------------------------------------------
    def export_audio(
        self,
        src_path: Path | str,
        asset_kind: str,
        name: str,
        *,
        category: str | None = None,
    ) -> Path:
        """Dépose un audio sous Assets/Audio/{Music,SFX,Voice}/[<category>/]<slug>.<ext>.

        Le WAV est conservé tel quel : c'est la source, la compression est un
        réglage d'import (cf. en-tête du module). L'extension d'origine est
        préservée.
        """
        if asset_kind not in _AUDIO_SUBDIR:
            raise ValueError(
                f"[unity] type audio inconnu : '{asset_kind}' "
                f"(attendu : {', '.join(sorted(_AUDIO_SUBDIR))})"
            )
        src = Path(src_path)
        ext = src.suffix.lower().lstrip(".")
        if ext not in _UNITY_AUDIO:
            raise ValueError(
                f"[unity] format audio non supporté : .{ext} "
                f"(attendu : {', '.join(sorted(_UNITY_AUDIO))}). Convertir en amont."
            )
        parts = ["Assets", "Audio", _AUDIO_SUBDIR[asset_kind]]
        if category:
            parts.append(_slugify(category))
        parts.append(f"{_slugify(name)}.{ext}")
        dest = self._dest(*parts)
        if src.resolve() != dest.resolve():
            shutil.copyfile(src, dest)
        log.info("[unity] %s -> %s", asset_kind, dest)
        return dest

    # -- outillage ------------------------------------------------------------
    def install_postprocessor(self) -> Path:
        """Dépose l'AssetPostprocessor dans Assets/Editor/ du projet cible.

        Idempotent : réécrit le fichier à l'identique s'il est déjà à jour.
        À appeler une fois par projet ; les assets exportés ensuite reçoivent
        automatiquement les bons réglages d'import.
        """
        dest = self._dest("Assets", "Editor", "ContentStudioAssetPostprocessor.cs")
        existant = dest.read_text(encoding="utf-8") if dest.exists() else None
        if existant != _POSTPROCESSOR_CS:
            dest.write_text(_POSTPROCESSOR_CS, encoding="utf-8")
            log.info("[unity] postprocessor installé -> %s", dest)
        else:
            log.info("[unity] postprocessor déjà à jour -> %s", dest)
        return dest

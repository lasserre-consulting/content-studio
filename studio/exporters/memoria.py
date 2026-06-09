"""Exporter pour le moteur Memoria (mods FF9 type 'La Troisième Fissure').

Memoria charge des assets depuis l'arborescence `StreamingAssets/Assets/` du
mod. Cet exporter connaît trois choses utiles, glanées en production :

1. AUDIO en OGG (Vorbis) : Memoria consomme de l'OGG, pas du WAV. On convertit
   donc à la volée via ffmpeg (libvorbis -q:a 5, bon compromis taille/qualité).
   Placement :
       BGM -> StreamingAssets/Assets/Audio/BGM/<nom canonique>.ogg
       SFX -> StreamingAssets/Assets/Audio/SFX/<nom canonique>.ogg
       (autre audio) -> StreamingAssets/Assets/Audio/<nom canonique>.ogg

2. NOM CANONIQUE des SFX : on normalise en ASCII minuscule à underscores
   (`canonical_sfx_name`) pour des noms stables et sûrs côté FS/moteur.

3. OVERRIDE de TEXTURE de MODÈLE 3D : les persos FF9 sont des MODÈLES 3D ; on
   ne pousse donc PAS des spritesheets mais des textures qui remplacent celles
   du modèle :
       StreamingAssets/Assets/Resources/Models/<grp>/<id>/<id>_<n>.png

La racine du mod (`mod_root`) est TOUJOURS fournie par l'appelant : aucun chemin
Steam n'est codé en dur. Les imports lourds (ffmpeg) restent paresseux.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

from .base import AssetKindSpec, EngineProfile, Exporter

log = logging.getLogger("studio.exporters.memoria")

# Sous-dossiers conventionnels sous la racine du mod.
_AUDIO_BASE = ("StreamingAssets", "Assets", "Audio")
_MODELS_BASE = ("StreamingAssets", "Assets", "Resources", "Models")


# --------------------------------------------------------------------------- #
# Profil moteur : ce que Memoria sait consommer                               #
# --------------------------------------------------------------------------- #
#  - audio = OGG (BGM/SFX),
#  - characters = TEXTURES de modèle 3D (PNG), surtout PAS des spritesheets 2D.
MEMORIA_PROFILE = EngineProfile(
    name="memoria",
    kinds={
        "bgm": AssetKindSpec(
            kind="bgm",
            audio_formats=frozenset({"ogg"}),
            representation="OGG Vorbis background music",
            subdir="/".join(_AUDIO_BASE) + "/BGM",
        ),
        "sfx": AssetKindSpec(
            kind="sfx",
            audio_formats=frozenset({"ogg"}),
            representation="OGG Vorbis sound effect",
            subdir="/".join(_AUDIO_BASE) + "/SFX",
        ),
        "audio": AssetKindSpec(
            kind="audio",
            audio_formats=frozenset({"ogg"}),
            representation="OGG Vorbis audio",
            subdir="/".join(_AUDIO_BASE),
        ),
        # Les persos sont des modèles 3D : on remplace leurs TEXTURES, on ne
        # fournit pas de planches de sprites.
        "model_texture": AssetKindSpec(
            kind="model_texture",
            image_formats=frozenset({"png"}),
            representation="3D model textures (PNG), not 2D spritesheets",
            subdir="/".join(_MODELS_BASE),
        ),
    },
)


# --------------------------------------------------------------------------- #
# Nommage canonique des SFX                                                    #
# --------------------------------------------------------------------------- #
def canonical_sfx_name(name: str) -> str:
    """Nom canonique d'un SFX : ASCII minuscule, underscores, sans extension.

    'Coup d'Épée !' -> 'coup_d_epee'. Stable et sûr pour FS + moteur.
    """
    name = Path(name).stem  # tolère qu'on passe 'truc.wav'
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return name or "sfx"


class MemoriaExporter(Exporter):
    """Écrit des assets dans l'arborescence d'un mod Memoria.

    `mod_root` : racine du mod (contient/contiendra `StreamingAssets/`). Fournie
    par l'appelant — on ne devine PAS l'installation Steam.
    """

    profile = MEMORIA_PROFILE

    def __init__(self, mod_root: Path | str):
        super().__init__(mod_root)

    # -- API générique --------------------------------------------------------
    def export(self, src_path: Path | str, asset_kind: str, name: str, **opts) -> Path:
        """Route vers le bon helper selon `asset_kind`.

        asset_kind ∈ {bgm, sfx, audio} -> audio OGG ;
        asset_kind == 'model_texture'  -> override de texture (requiert grp/id/n).
        """
        self.profile.check(asset_kind)
        if asset_kind in ("bgm", "sfx", "audio"):
            return self.export_audio(src_path, asset_kind, name)
        if asset_kind == "model_texture":
            return self.export_model_texture(
                src_path,
                group=opts["group"],
                model_id=opts["model_id"],
                index=opts.get("index", 0),
            )
        # check() a déjà filtré les kinds inconnus ; garde-fou défensif.
        raise ValueError(f"[memoria] kind non géré par export() : {asset_kind}")

    # -- audio (WAV -> OGG) ---------------------------------------------------
    def export_audio(self, src_path: Path | str, kind: str, name: str) -> Path:
        """Place un BGM/SFX en OGG au bon emplacement audio.

        Le nom est canonisé (convention SFX) ; l'extension finale est forcée à
        .ogg. Si la source est déjà .ogg, on copie ; sinon on encode en Vorbis.
        """
        src = Path(src_path)
        canon = canonical_sfx_name(name)
        sub = {"bgm": ("BGM",), "sfx": ("SFX",), "audio": ()}[kind]
        dest = self._dest(*_AUDIO_BASE, *sub, f"{canon}.ogg")

        if src.suffix.lower() == ".ogg":
            if src.resolve() != dest.resolve():
                shutil.copyfile(src, dest)
        else:
            self._encode_ogg(src, dest)
        log.info("[memoria] %s -> %s", kind, dest)
        return dest

    def _encode_ogg(self, src: Path, dest: Path) -> None:
        """Encode `src` (ex. WAV) en OGG Vorbis q5 via ffmpeg (import paresseux).

        Réutilise studio.assembly.ffmpeg.ffmpeg_bin() pour localiser le binaire,
        SANS recopier la logique de découverte. Lève FFmpegUnavailable si absent.
        """
        from ..assembly.ffmpeg import FFmpegUnavailable, ffmpeg_bin

        binary = ffmpeg_bin()
        if not binary:
            raise FFmpegUnavailable(
                "ffmpeg introuvable : conversion WAV->OGG impossible "
                "(winget install Gyan.FFmpeg, puis rouvrir le terminal)"
            )
        cmd = [
            binary, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(src),
            "-c:a", "libvorbis", "-q:a", "5",
            str(dest),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg a échoué (WAV->OGG) :\n{proc.stderr.strip() or proc.stdout.strip()}"
            )

    # -- texture d'override de modèle 3D --------------------------------------
    def export_model_texture(
        self,
        src_path: Path | str,
        *,
        group: str,
        model_id: str,
        index: int = 0,
    ) -> Path:
        """Écrit une texture d'override pour un modèle 3D.

        Chemin :
            StreamingAssets/Assets/Resources/Models/<group>/<model_id>/<model_id>_<index>.png

        `group`/`model_id` sont des identifiants du moteur (on ne les slugifie
        pas : ils doivent matcher EXACTEMENT les ID Memoria). La source est
        copiée telle quelle (on suppose déjà un PNG RGBA conforme).
        """
        src = Path(src_path)
        dest = self._dest(
            *_MODELS_BASE, group, model_id, f"{model_id}_{index}.png"
        )
        if src.resolve() != dest.resolve():
            shutil.copyfile(src, dest)
        log.info("[memoria] texture modèle %s/%s -> %s", group, model_id, dest)
        return dest

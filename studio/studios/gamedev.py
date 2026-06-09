"""Studio Jeu Vidéo : production d'assets + ré-itération rapide.

Pensé pour alimenter directement des projets de jeu (ex: Le Repaire des
Sorcières sous Godot, FF9 Suite). On génère sprites, planches, BGM, SFX et voix
de dialogue, en lots, avec variations par seed — puis on dépose les fichiers
retenus dans le dossier d'assets du projet cible.

Le studio ne sait rien de Godot en particulier : il écrit des PNG/WAV dans un
dossier ; c'est l'agent (ou un manifeste) qui décide quoi produire et où.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..core import GenResult, Modality, Router
from .base import Studio, slugify

log = logging.getLogger("studio.gamedev")

# Suffixe de style commun aux sprites 2D pour un rendu cohérent et détourable.
# On insiste sur un fond blanc uni SANS fumée/ombre/effet : ça maximise la
# qualité du détourage automatique (rembg) qui suit.
SPRITE_STYLE = (
    "2D game sprite, full body, single character, centered, "
    "isolated on solid plain white background, no shadow, no smoke, no effects, "
    "clean vector-like shading, crisp edges, game asset"
)


@dataclass
class AssetSpec:
    """Une ligne d'un manifeste d'assets : quoi générer et combien de variantes."""
    kind: str            # "sprite" | "bgm" | "sfx" | "voice"
    name: str            # identifiant -> nom de fichier
    prompt: str          # description / texte (pour voice)
    variants: int = 1    # nombre de variations à produire
    extra: dict = field(default_factory=dict)  # voice=..., duration=..., style=...


_MODALITY = {
    "sprite": Modality.IMAGE,
    "bgm": Modality.MUSIC,
    "sfx": Modality.SFX,
    "voice": Modality.TTS,
}


class GamedevStudio(Studio):
    """Studio d'assets de jeu. workspace par défaut = <outputs>/game ;
    passe `workspace=<dossier assets du jeu>` pour écrire directement dedans."""

    def __init__(self, router: Router, workspace: Path | str | None = None):
        super().__init__(router, workspace or (router.config.output_dir / "game"))

    # -- assets unitaires ------------------------------------------------------
    def sprite(self, prompt: str, *, name: str, style: str = SPRITE_STYLE,
               variants: int = 1, seed: int = 2000, transparent: bool = True) -> list[Path]:
        """Génère un (ou plusieurs) sprite(s), détouré(s) à fond transparent.

        Le style par défaut force un fond uni (plus facile à détourer). Avec
        transparent=True (défaut), chaque sprite est passé au détourage local
        (rembg) pour sortir un PNG transparent rogné, directement utilisable dans
        Godot — sans étape manuelle. Si rembg est absent, on garde l'image brute
        et on le signale dans les logs (jamais bloquant)."""
        full = f"{prompt}, {style}" if style else prompt
        results = self.variations(Modality.IMAGE, full, n=variants, base_seed=seed)
        paths = self._collect(results, name, "sprite")
        if transparent and paths:
            paths = [self._cutout(p) for p in paths]
        return paths

    def _cutout(self, png: Path) -> Path:
        """Détoure un sprite sur place (fond → transparent). Renvoie le chemin
        (inchangé si rembg indisponible)."""
        from ..assembly import image_ops

        ok, reason = image_ops.rembg_available()
        if not ok:
            log.warning("[game] détourage sauté (%s) — sprite laissé avec son fond", reason)
            return png
        try:
            return image_ops.remove_background(png, png, autocrop=True)
        except Exception as e:  # un échec de détourage ne doit pas perdre le sprite
            log.warning("[game] détourage échoué sur %s : %s", png.name, e)
            return png

    def bgm(self, prompt: str, *, name: str, duration: int | None = None,
            variants: int = 1) -> list[Path]:
        """Musique de fond (boucle d'ambiance, thème de combat...)."""
        kw = {"duration": duration} if duration else {}
        results = self.variations(Modality.MUSIC, prompt, n=variants, base_seed=3000, **kw)
        return self._collect(results, name, "bgm")

    def sfx(self, prompt: str, *, name: str, variants: int = 1) -> list[Path]:
        """Effet sonore (impact, sort, ramassage d'objet...)."""
        results = self.variations(Modality.SFX, prompt, n=variants, base_seed=4000)
        return self._collect(results, name, "sfx")

    def voice_line(self, text: str, *, name: str, voice: str | None = None) -> list[Path]:
        """Ligne de dialogue parlée (voix de PNJ)."""
        kw = {"voice": voice} if voice else {}
        res = self.try_gen(Modality.TTS, text, **kw)
        return self._collect([res] if res else [], name, "voice")

    # -- détourage d'assets existants -----------------------------------------
    def detour(self, images: list[Path | str], *, dest_dir: Path | str | None = None,
               in_place: bool = False, suffix: str = "_t") -> list[Path]:
        """Détoure des images DÉJÀ produites (fond → transparent), en local.

        Pile le besoin récurrent : nettoyer des sprites au fond opaque sans
        passer par remove.bg. Par défaut écrit des copies (`nom_t.png`) à côté ou
        dans `dest_dir` ; `in_place=True` écrase les originaux (à utiliser en
        connaissance de cause). Renvoie la liste des chemins transparents."""
        from ..assembly import image_ops

        ok, reason = image_ops.rembg_available()
        if not ok:
            log.warning("[game] détourage indisponible : %s", reason)
            return []
        out: list[Path] = []
        for img in images:
            src = Path(img)
            if in_place:
                dest = src.with_suffix(".png")
            elif dest_dir:
                dest = Path(dest_dir) / f"{src.stem}{suffix}.png"
            else:
                dest = src.with_name(f"{src.stem}{suffix}.png")
            try:
                out.append(image_ops.remove_background(src, dest, autocrop=True))
            except Exception as e:
                log.warning("[game] détourage échoué sur %s : %s", src.name, e)
        return out

    # -- production par lot (manifeste) ---------------------------------------
    def batch(self, specs: list[AssetSpec]) -> dict[str, list[Path]]:
        """Produit tout un manifeste d'assets. Renvoie {name: [chemins produits]}.

        C'est le point d'entrée « autonome » : un agent décrit la liste des
        assets d'un niveau, le studio les sort tous, et l'agent ré-itère sur ce
        qui ne va pas (en relançant juste la spec concernée avec d'autres seeds).
        """
        out: dict[str, list[Path]] = {}
        for spec in specs:
            log.info("[game] %s '%s' x%d", spec.kind, spec.name, spec.variants)
            if spec.kind == "sprite":
                out[spec.name] = self.sprite(
                    spec.prompt, name=spec.name, variants=spec.variants,
                    style=spec.extra.get("style", SPRITE_STYLE))
            elif spec.kind == "bgm":
                out[spec.name] = self.bgm(
                    spec.prompt, name=spec.name, variants=spec.variants,
                    duration=spec.extra.get("duration"))
            elif spec.kind == "sfx":
                out[spec.name] = self.sfx(spec.prompt, name=spec.name, variants=spec.variants)
            elif spec.kind == "voice":
                out[spec.name] = self.voice_line(
                    spec.prompt, name=spec.name, voice=spec.extra.get("voice"))
            else:
                log.warning("[game] type d'asset inconnu ignoré: %s", spec.kind)
                out[spec.name] = []
        return out

    # -- helpers ---------------------------------------------------------------
    def _collect(self, results: list[GenResult | None], name: str, subdir: str) -> list[Path]:
        """Copie/renomme les fichiers produits sous <workspace>/<subdir>/ avec un
        nom lisible et indexé (name_00, name_01...)."""
        import shutil

        paths: list[Path] = []
        slug = slugify(name)
        for i, res in enumerate([r for r in results if r and r.path]):
            src = res.path
            dest = self.path(subdir, f"{slug}_{i:02d}{src.suffix}")
            if src.resolve() != dest.resolve():
                shutil.copyfile(src, dest)
            paths.append(dest)
        return paths

"""Linter d'assets — vérifie dimensions / alpha / format / durée / conformité.

Ce module automatise ce que les agents vérifiaient à la main : dimensions
exactes ou minimales, mode couleur (RGBA), présence d'un canal alpha réellement
utilisé (au moins un pixel transparent), poids du fichier, format, et pour
l'audio le samplerate / nombre de canaux / durée.

Principe directeur : TOLÉRANCE. Aucune fonction ne lève jamais d'exception —
un fichier illisible, manquant ou corrompu produit une `Issue` de niveau
'error' plutôt qu'un crash. On peut donc passer un manifeste entier sans
filet try/except côté appelant.

Exemple rapide :
    from studio.verify import verify_image, Spec
    issues = verify_image("overlay.png", Spec(exact_size=(1920, 1080),
                                              mode="RGBA", require_alpha=True))
    if issues:
        for i in issues:
            print(i["level"], i["msg"])
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, TypedDict

# --------------------------------------------------------------------------- #
# Types publics
# --------------------------------------------------------------------------- #

# Une anomalie détectée sur un asset. `level` suit la convention usuelle :
#   'error' = non conforme / bloquant, 'warn' = suspect, 'info' = remarque.
class Issue(TypedDict):
    path: str
    level: str  # 'error' | 'warn' | 'info'
    msg: str


# Rapport agrégé renvoyé par verify_manifest.
class Report(TypedDict):
    ok: bool                 # True si aucune Issue de niveau 'error'
    n: int                   # nombre d'entrées vérifiées
    issues: list[Issue]      # toutes les Issues (toutes entrées confondues)
    missing: list[str]       # chemins (relatifs) des fichiers introuvables


@dataclass
class Spec:
    """Contrat attendu pour un asset. Tous les champs sont optionnels :
    un champ à None n'est tout simplement pas vérifié.

    Image :
        width / height : dimensions exactes (alternative à exact_size).
        exact_size     : (w, h) exact — prioritaire sur width/height.
        min_size       : (w, h) minimum (largeur ET hauteur >=).
        mode           : mode PIL attendu (ex. 'RGBA', 'RGB').
        require_alpha  : exige un vrai canal alpha avec >=1 pixel transparent.
        max_kb         : poids maximal du fichier en kilo-octets.
        formats        : formats PIL autorisés (ex. {'PNG'} ou ('PNG', 'WEBP')).

    Audio :
        samplerate     : fréquence d'échantillonnage exacte attendue (Hz).
        channels       : nombre de canaux exact (1 = mono, 2 = stéréo).
        min_duration / max_duration : bornes de durée en secondes.
    """

    # --- image ---
    width: Optional[int] = None
    height: Optional[int] = None
    exact_size: Optional[tuple[int, int]] = None
    min_size: Optional[tuple[int, int]] = None
    mode: Optional[str] = None
    require_alpha: bool = False
    max_kb: Optional[float] = None
    formats: Optional[tuple[str, ...]] = None

    # --- audio ---
    samplerate: Optional[int] = None
    channels: Optional[int] = None
    min_duration: Optional[float] = None
    max_duration: Optional[float] = None


# --------------------------------------------------------------------------- #
# Fabriques d'Issue (helpers internes)
# --------------------------------------------------------------------------- #

def _issue(path, level: str, msg: str) -> Issue:
    return {"path": str(path), "level": level, "msg": msg}


def _normalize_formats(formats) -> tuple[str, ...]:
    """Accepte str, list, set ou tuple ; renvoie un tuple de formats MAJUSCULES."""
    if isinstance(formats, str):
        formats = (formats,)
    return tuple(str(f).upper() for f in formats)


def _file_kb(path: Path) -> float:
    """Taille du fichier en kilo-octets (1024 o)."""
    return path.stat().st_size / 1024.0


# --------------------------------------------------------------------------- #
# Vérification d'image
# --------------------------------------------------------------------------- #

def verify_image(path, spec: Spec) -> list[Issue]:
    """Vérifie une image vis-à-vis de `spec`. Ne lève jamais.

    Renvoie la liste (éventuellement vide) des anomalies détectées.
    """
    path = Path(path)
    issues: list[Issue] = []

    if not path.exists():
        return [_issue(path, "error", "fichier introuvable")]

    # Poids : vérifiable même si l'image est illisible.
    if spec.max_kb is not None:
        try:
            kb = _file_kb(path)
            if kb > spec.max_kb:
                issues.append(
                    _issue(path, "error",
                           f"poids {kb:.1f} Ko > max {spec.max_kb:.1f} Ko")
                )
        except OSError as exc:
            issues.append(_issue(path, "error", f"taille fichier illisible : {exc}"))

    # Ouverture PIL.
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - PIL est une dépendance dure
        return issues + [_issue(path, "error", f"Pillow indisponible : {exc}")]

    try:
        with Image.open(path) as img:
            img.load()  # force le décodage (détecte les fichiers tronqués)
            w, h = img.size
            mode = img.mode
            fmt = (img.format or "").upper()
            # Snapshot des données alpha avant fermeture du contexte.
            alpha_band = None
            if spec.require_alpha and "A" in img.getbands():
                alpha_band = img.getchannel("A")
                alpha_extrema = alpha_band.getextrema()  # (min, max)
            else:
                alpha_extrema = None
    except Exception as exc:  # PIL lève des erreurs variées (UnidentifiedImageError, OSError…)
        return issues + [_issue(path, "error", f"image illisible : {exc}")]

    # --- dimensions ---
    if spec.exact_size is not None:
        ew, eh = spec.exact_size
        if (w, h) != (ew, eh):
            issues.append(_issue(path, "error",
                                 f"dimensions {w}x{h} != attendu {ew}x{eh}"))
    else:
        if spec.width is not None and w != spec.width:
            issues.append(_issue(path, "error",
                                 f"largeur {w} != attendu {spec.width}"))
        if spec.height is not None and h != spec.height:
            issues.append(_issue(path, "error",
                                 f"hauteur {h} != attendu {spec.height}"))

    if spec.min_size is not None:
        mw, mh = spec.min_size
        if w < mw or h < mh:
            issues.append(_issue(path, "error",
                                 f"dimensions {w}x{h} < minimum {mw}x{mh}"))

    # --- mode ---
    if spec.mode is not None and mode != spec.mode:
        issues.append(_issue(path, "error",
                             f"mode '{mode}' != attendu '{spec.mode}'"))

    # --- format ---
    if spec.formats is not None:
        allowed = _normalize_formats(spec.formats)
        if fmt not in allowed:
            issues.append(_issue(path, "error",
                                 f"format '{fmt or '?'}' non autorisé "
                                 f"(attendu {'/'.join(allowed)})"))

    # --- canal alpha non trivial ---
    if spec.require_alpha:
        if alpha_extrema is None:
            # Pas de canal alpha du tout.
            issues.append(_issue(path, "error",
                                 f"canal alpha requis mais absent (mode '{mode}')"))
        else:
            amin, amax = alpha_extrema
            if amin >= 255:
                # Canal alpha présent mais entièrement opaque => alpha "trivial".
                issues.append(_issue(path, "warn",
                                     "canal alpha présent mais entièrement opaque "
                                     "(aucun pixel transparent)"))

    return issues


# --------------------------------------------------------------------------- #
# Vérification d'audio
# --------------------------------------------------------------------------- #

def verify_audio(path, spec: Spec) -> list[Issue]:
    """Vérifie un fichier audio via soundfile. Ne lève jamais."""
    path = Path(path)
    issues: list[Issue] = []

    if not path.exists():
        return [_issue(path, "error", "fichier introuvable")]

    if spec.max_kb is not None:
        try:
            kb = _file_kb(path)
            if kb > spec.max_kb:
                issues.append(
                    _issue(path, "error",
                           f"poids {kb:.1f} Ko > max {spec.max_kb:.1f} Ko")
                )
        except OSError as exc:
            issues.append(_issue(path, "error", f"taille fichier illisible : {exc}"))

    try:
        import soundfile as sf
    except ImportError as exc:  # pragma: no cover - soundfile est installé
        return issues + [_issue(path, "error", f"soundfile indisponible : {exc}")]

    try:
        info = sf.info(str(path))
        samplerate = info.samplerate
        channels = info.channels
        frames = info.frames
    except Exception as exc:  # RuntimeError/LibsndfileError pour un fichier corrompu
        return issues + [_issue(path, "error", f"audio illisible : {exc}")]

    # Durée en secondes (sécurise une division par zéro improbable).
    duration = frames / samplerate if samplerate else 0.0

    if spec.samplerate is not None and samplerate != spec.samplerate:
        issues.append(_issue(path, "error",
                             f"samplerate {samplerate} Hz != attendu {spec.samplerate} Hz"))

    if spec.channels is not None and channels != spec.channels:
        issues.append(_issue(path, "error",
                             f"canaux {channels} != attendu {spec.channels}"))

    if spec.min_duration is not None and duration < spec.min_duration:
        issues.append(_issue(path, "error",
                             f"durée {duration:.2f}s < minimum {spec.min_duration:.2f}s"))

    if spec.max_duration is not None and duration > spec.max_duration:
        issues.append(_issue(path, "error",
                             f"durée {duration:.2f}s > maximum {spec.max_duration:.2f}s"))

    return issues


# --------------------------------------------------------------------------- #
# Détection image vs audio (pour verify_manifest générique)
# --------------------------------------------------------------------------- #

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".tif"}
_AUDIO_EXTS = {".wav", ".flac", ".ogg", ".mp3", ".aiff", ".aif", ".aifc"}


def _verify_by_ext(path: Path, spec: Spec) -> list[Issue]:
    """Aiguille vers verify_image / verify_audio selon l'extension.

    Si l'extension est inconnue, on déduit la nature des champs du Spec
    (samplerate/channels/durée => audio, sinon image)."""
    ext = path.suffix.lower()
    if ext in _AUDIO_EXTS:
        return verify_audio(path, spec)
    if ext in _IMAGE_EXTS:
        return verify_image(path, spec)
    # Extension inconnue : on devine d'après le Spec.
    is_audio = any(v is not None for v in (
        spec.samplerate, spec.channels, spec.min_duration, spec.max_duration))
    return verify_audio(path, spec) if is_audio else verify_image(path, spec)


# --------------------------------------------------------------------------- #
# Vérification d'un manifeste complet
# --------------------------------------------------------------------------- #

def verify_manifest(
    manifest: list[dict],
    root,
    key_path: str = "out_path",
    spec_for: Optional[Callable[[dict], Optional[Spec]]] = None,
) -> Report:
    """Vérifie chaque entrée d'un manifeste (liste de dicts).

    Args:
        manifest : liste d'entrées (ex. contenu de scripts/ff9_*_manifest.json).
        root     : dossier racine sous lequel résoudre `out_path`.
        key_path : clé de l'entrée donnant le chemin relatif du fichier produit.
        spec_for : callable(entry) -> Spec | None. Permet de dériver un Spec par
                   entrée (ex. depuis ses champs width/height/duration_s). Si
                   None ou s'il renvoie None pour une entrée, seule l'existence
                   du fichier est vérifiée.

    Renvoie un Report. Ne lève jamais : une entrée mal formée (sans clé chemin)
    produit une Issue 'error'.
    """
    root = Path(root)
    issues: list[Issue] = []
    missing: list[str] = []
    n = 0

    for entry in manifest:
        n += 1

        # Récupération du chemin relatif.
        rel = entry.get(key_path) if isinstance(entry, dict) else None
        if not rel:
            issues.append(_issue(f"<entrée #{n}>", "error",
                                 f"clé '{key_path}' absente ou vide"))
            continue

        full = root / rel

        if not full.exists():
            missing.append(str(rel))
            issues.append(_issue(rel, "error", "fichier introuvable sous root"))
            continue

        # Dérivation du Spec pour cette entrée.
        spec: Optional[Spec] = None
        if spec_for is not None:
            try:
                spec = spec_for(entry)
            except Exception as exc:
                issues.append(_issue(rel, "error",
                                     f"spec_for a échoué : {exc}"))
                continue

        if spec is None:
            # Pas de contrat précis : l'existence suffit.
            continue

        # On préfixe chaque Issue par le chemin relatif (lisibilité dans le rapport).
        sub = _verify_by_ext(full, spec)
        for it in sub:
            it["path"] = str(rel)
            issues.append(it)

    ok = not any(it["level"] == "error" for it in issues)
    return {"ok": ok, "n": n, "issues": issues, "missing": missing}


__all__ = [
    "Spec",
    "Issue",
    "Report",
    "verify_image",
    "verify_audio",
    "verify_manifest",
]

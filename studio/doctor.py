"""Preflight de l'environnement — diagnostique la stack et explique quoi corriger.

But : avant de lancer une génération (image / vidéo / musique / SFX / voix), on
veut savoir en un coup d'œil ce qui est cassé ET la commande exacte pour réparer.
Cette session a perdu du temps sur une stack audio fragile : ce doctor fige la
RECETTE QUI MARCHE et la propose comme `fix_hint` dès qu'un paquet manque ou est
incompatible.

Usage :
    python -m studio.doctor

Chaque vérification est totalement tolérante (try/except large) : elle ne lève
JAMAIS, elle renvoie un Check avec ok=False + un indice de réparation. La CLI
affiche un tableau ✓/✗ et sort en code 1 uniquement si un check CRITIQUE casse
(torch / PIL) ; l'audio est traité comme un simple avertissement.
"""
from __future__ import annotations

import importlib
import platform
import sys
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# La RECETTE FIGÉE (stack validée sur RTX 2080, torch 2.6.0+cu124).            #
# Réutilisée dans les fix_hint pour donner la commande pip exacte.             #
# --------------------------------------------------------------------------- #
RECIPE_TORCH = (
    "pip install torch==2.6.0 torchvision torchaudio "
    "--index-url https://download.pytorch.org/whl/cu124"
)
RECIPE_AUDIOCRAFT = (
    "pip install audiocraft --no-deps  &&  "
    "pip install omegaconf hydra-core julius num2words sentencepiece encodec "
    "einops dora-search flashy librosa torchmetrics av"
)
RECIPE_XFORMERS = (
    "pip install xformers==0.0.29.post3  "
    "(seule version ABI-compatible torch 2.6 ; backend d'attention = torch)"
)
RECIPE_SKLEARN = (
    "pip install scikit-learn==1.5.2  "
    "(la DLL de sklearn >= 1.9 est bloquée par le Smart App Control de Windows)"
)


@dataclass
class Check:
    """Résultat d'une vérification unitaire.

    name      : libellé court affiché dans le tableau.
    ok        : True si tout va bien.
    detail    : ce qu'on a effectivement constaté (version, GPU, erreur…).
    fix_hint  : commande/action concrète pour réparer (vide si ok).
    critical  : si True, un échec fait sortir la CLI en code 1.
    """
    name: str
    ok: bool
    detail: str = ""
    fix_hint: str = ""
    critical: bool = False


# --------------------------------------------------------------------------- #
# Petit utilitaire : importer un module en attrapant TOUTE erreur.             #
# (ImportError mais aussi les OSError/DLL Windows, ABI mismatch, etc.)         #
# --------------------------------------------------------------------------- #
def _safe_import(modname: str):
    """Renvoie (module, None) ou (None, message_erreur). Ne lève jamais."""
    try:
        return importlib.import_module(modname), None
    except BaseException as e:  # noqa: BLE001 — on veut TOUT capturer (DLL, SystemExit rare…)
        return None, f"{type(e).__name__}: {e}"


def _version_of(mod) -> str:
    """Version d'un module (best effort)."""
    return getattr(mod, "__version__", "?")


# --------------------------------------------------------------------------- #
# Les vérifications individuelles. Chacune renvoie un Check, jamais d'exception.#
# --------------------------------------------------------------------------- #
def _check_python() -> Check:
    v = sys.version_info
    detail = f"{v.major}.{v.minor}.{v.micro} ({platform.python_implementation()})"
    ok = v >= (3, 10)
    return Check(
        "Python", ok, detail,
        fix_hint="" if ok else "Python >= 3.10 recommandé pour cette stack",
        critical=True,
    )


def _check_torch() -> Check:
    """torch + CUDA + nom du GPU. Critique : rien de local ne tourne sans lui."""
    torch, err = _safe_import("torch")
    if torch is None:
        return Check("torch", False, err or "import impossible",
                     fix_hint=RECIPE_TORCH, critical=True)
    try:
        cuda_ok = bool(torch.cuda.is_available())
        gpu = torch.cuda.get_device_name(0) if cuda_ok else "—"
    except BaseException as e:  # noqa: BLE001
        cuda_ok, gpu = False, f"erreur CUDA ({type(e).__name__})"
    detail = f"v{_version_of(torch)} | CUDA={'oui' if cuda_ok else 'non'} | GPU={gpu}"
    # torch importable = OK (critique satisfait) ; CUDA absent = juste un détail
    # (le CPU reste possible pour certains providers, ex. Kokoro).
    hint = "" if cuda_ok else (
        "CUDA indisponible : réinstalle la roue cu124 → " + RECIPE_TORCH
    )
    return Check("torch", True, detail, fix_hint=hint, critical=True)


def _check_torchvision() -> Check:
    mod, err = _safe_import("torchvision")
    if mod is None:
        return Check("torchvision", False, err or "absent",
                     fix_hint="silence le fallback PIL des processors → " + RECIPE_TORCH)
    return Check("torchvision", True, f"v{_version_of(mod)}")


def _check_diffusers() -> Check:
    mod, err = _safe_import("diffusers")
    if mod is None:
        return Check("diffusers", False, err or "absent",
                     fix_hint="pip install 'diffusers>=0.27' transformers accelerate safetensors")
    return Check("diffusers", True, f"v{_version_of(mod)}")


def _check_rembg() -> Check:
    """rembg (détourage) + son backend onnxruntime."""
    rembg, err = _safe_import("rembg")
    ort, ort_err = _safe_import("onnxruntime")
    if rembg is None:
        return Check("rembg + onnxruntime", False, err or "rembg absent",
                     fix_hint="pip install 'rembg>=2.0.76' onnxruntime")
    if ort is None:
        return Check("rembg + onnxruntime", False, f"rembg ok mais onnxruntime: {ort_err}",
                     fix_hint="pip install onnxruntime")
    return Check("rembg + onnxruntime", True,
                 f"rembg v{_version_of(rembg)} | onnxruntime v{_version_of(ort)}")


def _check_ffmpeg() -> Check:
    """ffmpeg présent (via notre wrapper) + encodeur libvorbis (audio ogg)."""
    try:
        from studio.assembly.ffmpeg import ffmpeg_bin
    except BaseException as e:  # noqa: BLE001
        return Check("ffmpeg", False, f"wrapper inimportable: {type(e).__name__}: {e}",
                     fix_hint="vérifie studio/assembly/ffmpeg.py")
    try:
        binary = ffmpeg_bin()
    except BaseException as e:  # noqa: BLE001
        binary = None
        _ = e
    if not binary:
        return Check("ffmpeg", False, "introuvable",
                     fix_hint="winget install Gyan.FFmpeg, puis rouvrir le terminal")
    # Vérifie l'encodeur libvorbis (utile pour exporter de l'audio .ogg).
    has_vorbis = False
    try:
        import subprocess
        out = subprocess.run([binary, "-hide_banner", "-encoders"],
                             capture_output=True, text=True)
        has_vorbis = "libvorbis" in out.stdout
    except BaseException:  # noqa: BLE001
        has_vorbis = False
    detail = f"{binary} | libvorbis={'oui' if has_vorbis else 'non'}"
    hint = "" if has_vorbis else (
        "libvorbis absent : utilise un build ffmpeg complet (Gyan.FFmpeg)"
    )
    # ffmpeg présent = OK même sans vorbis (l'aac suffit pour la vidéo).
    return Check("ffmpeg", True, detail, fix_hint=hint)


def _check_audiocraft() -> Check:
    """audiocraft (MusicGen / AudioGen). Audio = avertissement, pas critique."""
    mod, err = _safe_import("audiocraft")
    if mod is None:
        return Check("audiocraft", False, err or "absent",
                     fix_hint=RECIPE_AUDIOCRAFT)
    return Check("audiocraft", True, f"v{_version_of(mod)}")


def _check_xformers() -> Check:
    """xformers doit s'importer AVEC le torch courant (détecte l'ABI mismatch).

    Le symptôme classique d'incompatibilité torch 2.6 / mauvaise roue xformers
    est une erreur mentionnant `GroupName` au moment de l'import des ops C++.
    """
    mod, err = _safe_import("xformers")
    if mod is None:
        hint = RECIPE_XFORMERS
        if err and "GroupName" in err:
            hint = "ABI incompatible torch 2.6 → " + RECIPE_XFORMERS
        return Check("xformers", False, err or "absent", fix_hint=hint)
    # Importé : on tente de charger ses ops pour confirmer la compat ABI.
    detail = f"v{_version_of(mod)}"
    _, ops_err = _safe_import("xformers.ops")
    if ops_err is not None:
        hint = RECIPE_XFORMERS
        if "GroupName" in ops_err:
            hint = "ABI incompatible torch 2.6 (erreur GroupName) → " + RECIPE_XFORMERS
        return Check("xformers", False, f"{detail} mais ops KO: {ops_err}", fix_hint=hint)
    return Check("xformers", True, f"{detail} | ops OK")


def _check_sklearn() -> Check:
    """scikit-learn : version ET chargement effectif de sa DLL.

    Sous Windows, le Smart App Control bloque la DLL des versions >= 1.9 :
    importer `sklearn.utils.validation` force ce chargement et révèle le souci.
    """
    mod, err = _safe_import("scikit-learn".replace("-", "_"))  # -> sklearn
    # Note : le paquet pip est "scikit-learn" mais le module est "sklearn".
    if mod is None:
        mod, err = _safe_import("sklearn")
    if mod is None:
        return Check("scikit-learn", False, err or "absent", fix_hint=RECIPE_SKLEARN)
    # Force le chargement de la DLL native via un sous-module qui en dépend.
    _, dll_err = _safe_import("sklearn.utils.validation")
    if dll_err is not None:
        return Check("scikit-learn", False,
                     f"v{_version_of(mod)} mais DLL KO: {dll_err}",
                     fix_hint=RECIPE_SKLEARN)
    return Check("scikit-learn", True, f"v{_version_of(mod)} | DLL OK")


def _check_pil() -> Check:
    """PIL : critique — toute la chaîne image en dépend."""
    mod, err = _safe_import("PIL")
    if mod is None:
        return Check("PIL (Pillow)", False, err or "absent",
                     fix_hint="pip install Pillow", critical=True)
    return Check("PIL (Pillow)", True, f"v{_version_of(mod)}", critical=True)


def _check_numpy() -> Check:
    mod, err = _safe_import("numpy")
    if mod is None:
        return Check("numpy", False, err or "absent",
                     fix_hint="pip install numpy", critical=True)
    return Check("numpy", True, f"v{_version_of(mod)}", critical=True)


def _check_soundfile() -> Check:
    mod, err = _safe_import("soundfile")
    if mod is None:
        return Check("soundfile", False, err or "absent",
                     fix_hint="pip install soundfile")
    return Check("soundfile", True, f"v{_version_of(mod)}")


# --------------------------------------------------------------------------- #
# API publique.                                                                #
# --------------------------------------------------------------------------- #
def check() -> list[Check]:
    """Lance toutes les vérifications et renvoie la liste des Check.

    Robuste de bout en bout : si une fonction de check venait malgré tout à
    lever, on capture et on insère un Check ok=False plutôt que de tout casser.
    """
    checks = [
        _check_python,
        _check_torch,
        _check_torchvision,
        _check_diffusers,
        _check_rembg,
        _check_ffmpeg,
        _check_audiocraft,
        _check_xformers,
        _check_sklearn,
        _check_pil,
        _check_numpy,
        _check_soundfile,
    ]
    results: list[Check] = []
    for fn in checks:
        try:
            results.append(fn())
        except BaseException as e:  # noqa: BLE001 — garde-fou ultime
            results.append(Check(
                fn.__name__.replace("_check_", ""), False,
                f"check interne en erreur: {type(e).__name__}: {e}",
                fix_hint="bug du doctor — à signaler",
            ))
    return results


# --------------------------------------------------------------------------- #
# CLI.                                                                          #
# --------------------------------------------------------------------------- #
def _enable_utf8() -> None:
    """Console UTF-8 : indispensable pour ✓/✗ et les accents sous Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def main() -> int:
    _enable_utf8()
    results = check()

    width = max(len(c.name) for c in results)
    print("=" * (width + 30))
    print("  Content Studio — preflight (doctor)")
    print("=" * (width + 30))
    for c in results:
        mark = "✓" if c.ok else "✗"
        tag = " [CRITIQUE]" if (c.critical and not c.ok) else ""
        print(f"  {mark}  {c.name.ljust(width)}  {c.detail}{tag}")
        if not c.ok and c.fix_hint:
            print(f"       ↳ {c.fix_hint}")
    print("-" * (width + 30))

    broken = [c for c in results if not c.ok]
    critical_broken = [c for c in broken if c.critical]
    if critical_broken:
        print(f"  {len(critical_broken)} check(s) CRITIQUE(S) cassé(s). "
              "Corrige-les avant toute génération.")
    elif broken:
        print(f"  {len(broken)} avertissement(s) (non bloquant). "
              "Certaines fonctions seront indisponibles.")
    else:
        print("  Tout est OK. ✓")

    # Exit 0 si aucun check critique cassé ; 1 sinon.
    return 1 if critical_broken else 0


if __name__ == "__main__":
    raise SystemExit(main())

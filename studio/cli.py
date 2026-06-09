"""CLI du studio.

Exemples :
    python -m studio.cli providers
    python -m studio.cli image "un chat astronaute, style pixar"
    python -m studio.cli tts "Bonjour, ceci est un test"
    python -m studio.cli music "musique de boss épique, orchestral"
    python -m studio.cli llm "améliore ce prompt: chat" --provider ollama

Studios (pipelines complets) :
    python -m studio.cli content short "Script du short..." --title mon-short
    python -m studio.cli game sprite "vieille sorcière" --name morra --variants 4
    python -m studio.cli game bgm "thème de combat épique" --name boss
"""
from __future__ import annotations

import argparse
import logging
import sys

from . import get_router
from .core import Modality, NoProviderAvailable, list_providers


def _add_studio_parsers(sub) -> None:
    """Sous-commandes des studios : `content ...` et `game ...`."""
    # -- content -------------------------------------------------------------
    content = sub.add_parser("content", help="studio contenu (shorts sociaux)")
    csub = content.add_subparsers(dest="action", required=True)
    short = csub.add_parser("short", help="script → MP4 vertical monté")
    short.add_argument("script", help="le script (texte) ou @fichier.txt")
    short.add_argument("--title", help="titre / nom de fichier")
    short.add_argument("--style", help="style visuel des images")
    short.add_argument("--voice", help="voix TTS (ex: ff_siwis)")
    short.add_argument("--no-music", action="store_true", help="pas de musique de fond")
    short.add_argument("--no-subs", action="store_true", help="pas de sous-titres")

    # -- game ----------------------------------------------------------------
    game = sub.add_parser("game", help="studio jeu vidéo (assets)")
    gsub = game.add_subparsers(dest="action", required=True)
    for kind in ("sprite", "bgm", "sfx", "voice"):
        g = gsub.add_parser(kind, help=f"générer un asset {kind}")
        g.add_argument("prompt", help="description (ou texte pour 'voice')")
        g.add_argument("--name", required=True, help="nom de l'asset (fichier)")
        g.add_argument("--variants", type=int, default=1, help="nombre de variations")
        g.add_argument("--out", help="dossier de sortie (ex: dossier assets Godot)")
        if kind == "voice":
            g.add_argument("--voice", help="voix TTS")


def _run_content(args) -> int:
    from . import content_studio

    script = args.script
    if script.startswith("@"):
        from pathlib import Path
        try:
            script = Path(script[1:]).read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError, IsADirectoryError, UnicodeDecodeError) as e:
            print(f"✗ Impossible de lire le script '{script[1:]}' : {e}", file=sys.stderr)
            return 2
    studio = content_studio()
    kw = {}
    if args.title:
        kw["title"] = args.title
    if args.style:
        kw["style"] = args.style
    if args.voice:
        kw["voice"] = args.voice
    if args.no_music:
        kw["music_prompt"] = None
    if args.no_subs:
        kw["subtitles"] = False
    short = studio.short(script, **kw)
    if short.video:
        print(f"✓ short monté : {short.video}")
    else:
        print("⚠ pas de vidéo finale (voir notes ci-dessous)")
    for note in short.notes:
        print(f"  · {note}")
    if short.images:
        print(f"  {len(short.images)} image(s), voix={'oui' if short.voice else 'non'}, "
              f"musique={'oui' if short.music else 'non'}")
    return 0 if short.video else 2


def _run_game(args) -> int:
    from . import game_studio

    studio = game_studio(args.out if getattr(args, "out", None) else None)
    if args.action == "sprite":
        paths = studio.sprite(args.prompt, name=args.name, variants=args.variants)
    elif args.action == "bgm":
        paths = studio.bgm(args.prompt, name=args.name, variants=args.variants)
    elif args.action == "sfx":
        paths = studio.sfx(args.prompt, name=args.name, variants=args.variants)
    elif args.action == "voice":
        paths = studio.voice_line(args.prompt, name=args.name,
                                  voice=getattr(args, "voice", None))
    else:
        print(f"✗ action inconnue: {args.action}", file=sys.stderr)
        return 2
    if paths:
        print(f"✓ {len(paths)} asset(s) {args.action} :")
        for p in paths:
            print(f"  {p}")
        return 0
    print(f"⚠ aucun asset produit — provider {args.action} non installé ?", file=sys.stderr)
    return 2


def _force_utf8_console() -> None:
    """Sur Windows, la console est souvent en cp1252 et plante sur les caractères
    non-latin1 (flèches, ✓, accents selon les cas). On force l'UTF-8 pour que les
    libellés français et les symboles d'aide s'affichent sans UnicodeEncodeError."""
    for stream in (sys.stdout, sys.stderr):
        reconfig = getattr(stream, "reconfigure", None)
        if reconfig:
            try:
                reconfig(encoding="utf-8")
            except (ValueError, OSError):
                pass  # stream redirigé/non reconfigurable : on n'insiste pas


def main(argv: list[str] | None = None) -> int:
    _force_utf8_console()
    parser = argparse.ArgumentParser(prog="studio", description="Content Studio")
    parser.add_argument("-v", "--verbose", action="store_true", help="logs détaillés")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("providers", help="lister les providers enregistrés")

    for modality in ("llm", "image", "video", "music", "sfx", "tts"):
        p = sub.add_parser(modality, help=f"générer ({modality})")
        p.add_argument("prompt")
        p.add_argument("--provider", help="forcer un provider précis")
        p.add_argument("--seed", type=int)
        p.add_argument("--negative", dest="negative_prompt", help="prompt négatif (image)")

    _add_studio_parsers(sub)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.cmd == "providers":
        import studio.providers  # noqa: F401 — déclenche l'auto-enregistrement
        print("Providers enregistrés :")
        for p in list_providers():
            print(f"  - {p}")
        return 0

    if args.cmd == "content":
        return _run_content(args)
    if args.cmd == "game":
        return _run_game(args)

    router = get_router()
    modality = Modality(args.cmd)
    kwargs = {}
    if args.provider:
        kwargs["provider"] = args.provider
    if args.seed is not None:
        kwargs["seed"] = args.seed
    if getattr(args, "negative_prompt", None):
        kwargs["negative_prompt"] = args.negative_prompt

    try:
        result = router.generate(modality, args.prompt, **kwargs)
    except NoProviderAvailable as e:
        print(f"✗ {e}", file=sys.stderr)
        print("  → vérifie config/providers.yaml, tes clés .env, ou installe les "
              "dépendances locales (requirements-local.txt).", file=sys.stderr)
        return 2

    if result.text:
        print(result.text)
    if result.paths:
        print(f"✓ {len(result.paths)} fichier(s) via {result.provider} :")
        for path in result.paths:
            print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

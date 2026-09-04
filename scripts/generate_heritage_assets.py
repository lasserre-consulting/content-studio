"""Génère les assets de L'Héritage et les dépose dans le projet Unity.

Douze sprites d'objets (quatre chaînes × trois niveaux, plus le Grimoire) et
deux musiques d'ambiance. Tout en local : SDXL pour les images, détourage rembg,
Stable Audio 3 pour la musique.

    python scripts/generate_heritage_assets.py --only sprites
    python scripts/generate_heritage_assets.py --limit 2      # essai rapide
    python scripts/generate_heritage_assets.py --dry-run      # juste le plan

Les objets sont volontairement décrits comme des OBJETS ISOLÉS sur fond uni :
le détourage qui suit en dépend, et un décor dans l'image ruine le résultat.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

PROJET_UNITY = Path(r"C:\Users\lasse\workspace\jeux mobiles\HeritageSorciere")

# Style commun. Il porte l'identité visuelle : peinture sombre et chaude, pas
# le cartoon plat par défaut du studio. Cohérent avec l'univers sorcières.
# Passé en PARAMÈTRE `style=` et non dans le prompt : sinon le SPRITE_STYLE par
# défaut du studio s'ajoute par-dessus et impose « clean vector-like shading »,
# qui contredit la peinture patinée qu'on veut. C'est ce qui a produit une clé
# peinte et une hache vectorielle dans le même lot.
#
# Fond BLANC et non gris : rembg est calibré pour du blanc, un fond gris fait
# échouer le détourage en silence.
STYLE = (
    "single isolated object, centered, isolated on solid plain white background, "
    "dark cozy witch cottage aesthetic, warm painterly illustration, "
    "rich brush texture, aged patina, soft rim light, "
    "mobile game item icon, no text, no shadow, no background elements"
)

# Taille finale des sprites. Les cases font ~122 unités de référence ; 256 px
# laisse de la marge pour les écrans denses sans gaspiller 70x les pixels utiles
# (SDXL sort en 1024²).
TAILLE_SPRITE = 256

# (chaîne, niveau, nom du fichier, description)
SPRITES = [
    ("outils", 1, "outils-1", "a small rusty iron key, corroded, old"),
    # « screwdriver » puis « long metal shaft + wooden handle » ont tous deux
    # donné une hachette. Le marteau est un objet que SDXL rend de façon fiable.
    ("outils", 2, "outils-2", "an old claw hammer, steel head, worn wooden handle"),
    # « leather toolbox » a donné un coffre au trésor doré. Une caisse en bois
    # cerclée de fer reste dans le registre domestique.
    ("outils", 3, "outils-3", "an old wooden tool crate with iron corner brackets, open, hand tools inside"),

    ("nettoyage", 1, "nettoyage-1", "a folded grey cleaning rag"),
    ("nettoyage", 2, "nettoyage-2", "a galvanised metal bucket with soapy water"),
    ("nettoyage", 3, "nettoyage-3", "a glass jar of dark soap paste with a wooden brush"),

    ("lumiere", 1, "lumiere-1", "a short melted candle stub, unlit"),
    ("lumiere", 2, "lumiere-2", "a small brass oil lamp with glass chimney"),
    ("lumiere", 3, "lumiere-3", "an ornate iron lantern, warm glowing flame inside"),

    ("reliques", 1, "reliques-1", "a faded torn sepia photograph, curled corners"),
    ("reliques", 2, "reliques-2", "a tarnished silver locket on a chain, closed"),
    ("reliques", 3, "reliques-3", "a polished silver locket, open, faint engraving"),
    # Le seul objet ouvertement surnaturel : il clôt le jeu.
    # Couverture explicitement SOMBRE : la première version avait une couverture
    # claire que rembg a prise pour du fond, ce qui a creusé le centre du livre.
    ("reliques", 4, "reliques-4", "a closed ancient spellbook with a very dark "
                                  "black leather cover, heavy brass corner clasps, "
                                  "deep engraved symbols, three quarter view"),
]

MUSIQUES = [
    ("ambiance_maison",
     "musique d'ambiance douce et mélancolique, piano feutré, cordes lointaines, "
     "maison ancienne, nostalgique, boucle calme", 60),
    ("ambiance_grenier",
     "ambiance inquiétante et feutrée, nappes graves, cloches lointaines étouffées, "
     "mystère, tension retenue", 60),
]


def reduire(png: Path) -> Path:
    """Ramène le sprite à TAILLE_SPRITE, en préservant le ratio et l'alpha.

    SDXL sort en 1024² : garder ça pour une case de ~122 unités gaspillerait
    environ 70 fois les pixels utiles, donc autant de mémoire sur mobile.
    """
    from PIL import Image

    im = Image.open(png)
    if max(im.size) <= TAILLE_SPRITE:
        return png
    if im.mode != "RGBA":
        im = im.convert("RGBA")

    ratio = TAILLE_SPRITE / max(im.size)
    taille = (max(1, round(im.width * ratio)), max(1, round(im.height * ratio)))
    im.resize(taille, Image.LANCZOS).save(png)
    return png


def generer_sprites(studio, exporter, limite=None, dry=False):
    faits, echecs = [], []
    lot = SPRITES[:limite] if limite else SPRITES

    for i, (chaine, niveau, nom, description) in enumerate(lot, 1):
        print(f"\n[{i}/{len(lot)}] {nom}  ({chaine} niv.{niveau})")
        print(f"    {description}")
        if dry:
            continue

        t0 = time.time()
        try:
            # style= en PARAMÈTRE : remplace le SPRITE_STYLE du studio au lieu
            # de s'y ajouter. transparent=True enchaîne SDXL puis rembg.
            chemins = studio.sprite(description, name=nom, style=STYLE,
                                    variants=1, transparent=True)
        except Exception as e:  # noqa: BLE001 — un échec ne doit pas tuer le lot
            print(f"    ECHEC : {e}")
            echecs.append(nom)
            continue

        src = Path(chemins[0] if isinstance(chemins, (list, tuple)) else chemins)
        src = reduire(src)
        dest = exporter.export(src, "sprite", nom)   # -> Assets/Resources/Items/
        print(f"    OK en {time.time() - t0:.0f}s -> {dest.relative_to(PROJET_UNITY)}")
        faits.append(dest)

    return faits, echecs


def generer_musiques(router, exporter, limite=None, dry=False):
    from studio.core import Modality

    faits, echecs = [], []
    lot = MUSIQUES[:limite] if limite else MUSIQUES

    for i, (nom, prompt, duree) in enumerate(lot, 1):
        print(f"\n[{i}/{len(lot)}] {nom}  ({duree}s)")
        if dry:
            continue

        t0 = time.time()
        try:
            res = router.generate(Modality.MUSIC, prompt, duration=duree)
        except Exception as e:  # noqa: BLE001
            print(f"    ECHEC : {e}")
            echecs.append(nom)
            continue

        dest = exporter.export(Path(res.path), "music", nom)
        print(f"    OK en {time.time() - t0:.0f}s -> {dest.relative_to(PROJET_UNITY)}")
        print(f"    graine {res.meta.get('seed')} (rejouable)")
        faits.append(dest)

    return faits, echecs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["sprites", "music"])
    ap.add_argument("--limit", type=int, help="ne traiter que les N premiers")
    ap.add_argument("--dry-run", action="store_true", help="affiche le plan sans générer")
    args = ap.parse_args()

    if not PROJET_UNITY.exists():
        print(f"Projet Unity introuvable : {PROJET_UNITY}")
        return 1

    from studio import game_studio, get_router
    from studio.exporters import UnityExporter

    exporter = UnityExporter(PROJET_UNITY)

    print("=" * 66)
    print("  Assets de L'Héritage -> projet Unity")
    print("=" * 66)
    print(f"  cible : {PROJET_UNITY}")

    if not args.dry_run:
        pp = exporter.install_postprocessor()
        print(f"  postprocessor : {pp.relative_to(PROJET_UNITY)}")

    resultats = {}

    if args.only in (None, "sprites"):
        studio = game_studio(str(RACINE / "outputs" / "heritage"))
        resultats["sprites"] = generer_sprites(studio, exporter, args.limit, args.dry_run)

    if args.only in (None, "music"):
        resultats["musiques"] = generer_musiques(get_router(), exporter, args.limit, args.dry_run)

    print("\n" + "=" * 66)
    total_echecs = 0
    for nom, (faits, echecs) in resultats.items():
        print(f"  {nom:10} {len(faits)} produits, {len(echecs)} échecs")
        for e in echecs:
            print(f"             ! {e}")
        total_echecs += len(echecs)
    print("=" * 66)

    if not args.dry_run:
        print("\n  Rouvre Unity : l'AssetPostprocessor applique les réglages mobiles")
        print("  (ASTC, mipmaps off pour les sprites, Vorbis + streaming pour la musique).")

    return 1 if total_echecs else 0


if __name__ == "__main__":
    raise SystemExit(main())

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
    "bold simplified game item icon, strong readable silhouette, "
    "thick dark outline, high contrast, saturated colors, "
    "flat shading with soft highlights, object fills the frame, "
    "centered, isolated on solid plain white background, "
    "warm aged fantasy palette, no text, no shadow, no background elements"
)

# Taille finale des sprites. Les cases font ~122 unités de référence ; 256 px
# laisse de la marge pour les écrans denses sans gaspiller 70x les pixels utiles
# (SDXL sort en 1024²).
TAILLE_SPRITE = 256

# (chaîne, niveau, nom du fichier, description)
SPRITES = [
    ("outils", 1, "outils-1", "a rusty orange iron key, ornate bow, warm copper tones"),
    # « screwdriver » puis « long metal shaft + wooden handle » ont tous deux
    # donné une hachette. Le marteau est un objet que SDXL rend de façon fiable.
    ("outils", 2, "outils-2", "an orange-handled hammer with a bright steel head"),
    # « leather toolbox » a donné un coffre au trésor doré. Une caisse en bois
    # cerclée de fer reste dans le registre domestique.
    ("outils", 3, "outils-3", "a warm orange-brown toolbox with a handle on top, closed, brass fittings"),

    ("nettoyage", 1, "nettoyage-1", "a bright teal blue folded cloth rag, light and clean"),
    ("nettoyage", 2, "nettoyage-2", "a bright blue bucket full of white foam bubbles"),
    ("nettoyage", 3, "nettoyage-3", "a turquoise glass soap bottle with white bubbles, glossy"),

    ("lumiere", 1, "lumiere-1", "a short cream white candle with a small bright yellow flame"),
    ("lumiere", 2, "lumiere-2", "a golden yellow oil lamp glowing warmly, glass chimney"),
    ("lumiere", 3, "lumiere-3", "a bright golden lantern radiating warm yellow light"),

    ("reliques", 1, "reliques-1", "an old photograph with a violet purple tint, torn corners"),
    ("reliques", 2, "reliques-2", "a purple and silver oval locket, closed, ornate"),
    ("reliques", 3, "reliques-3", "a bright silver locket open, glowing violet light inside"),
    # Le seul objet ouvertement surnaturel : il clôt le jeu.
    # Couverture explicitement SOMBRE : la première version avait une couverture
    # claire que rembg a prise pour du fond, ce qui a creusé le centre du livre.
    ("reliques", 4, "reliques-4", "a closed spellbook, deep purple leather cover, "
                                  "bright gold clasps and glowing violet rune, front view"),
]

# Décors : deux états par lieu. C'est la récompense de la rénovation — le
# « avant / après » est ce que le joueur vient chercher dans un merge à méta.
# Pas de détourage ici : ce sont des fonds, pas des objets.
DECOR_STYLE = (
    "interior view, wide shot, no people, no text, "
    "warm painterly illustration, dark cozy witch cottage aesthetic, "
    "rich atmospheric lighting, mobile game background art"
)

DECORS = [
    ("cuisine-0", "an abandoned dusty old farmhouse kitchen, cobwebs, broken sink, "
                  "grey cold light through shutters, neglected, gloomy"),
    ("cuisine-1", "a restored warm farmhouse kitchen, copper pots, herbs hanging, "
                  "golden lamplight, clean wooden table, cosy and alive"),

    ("salon-0", "an abandoned dusty living room, sheets over furniture, cold fireplace, "
                "faded wallpaper, dim grey light"),
    ("salon-1", "a restored cosy living room, fire burning in the hearth, armchairs, "
                "warm golden light, old mirror above the mantel"),

    ("chambre-0", "an abandoned dusty bedroom, shutters closed, bare mattress, "
                  "cold blue gloom, peeling paint"),
    ("chambre-1", "a restored warm bedroom, made bed, open shutters, oil lamp on "
                  "the bedside table, soft evening light"),

    ("grenier-0", "a dark cluttered attic, sealed hatch, dusty crates, cobwebs, "
                  "single shaft of cold light"),
    ("grenier-1", "a lit attic room, lantern glowing, open trunks, old books and "
                  "papers, warm mysterious light"),

    ("serre-0", "an abandoned greenhouse, broken glass panes, dead withered plants, "
                "cold overcast light, overgrown"),
    ("serre-1", "a restored greenhouse at dusk, strange luminous plants, glass panes "
                "repaired, warm violet and green glow, magical"),

    # -- les onze pièces annoncées ----------------------------------------
    #
    # Elles ne sont pas jouables, mais elles sont VUES : la coupe du manoir les
    # montre toutes les seize. Sans image, onze aplats gris au milieu de cinq
    # peintures — et la promesse « grande maison, petit contenu » devient
    # « maison à moitié dessinée ».
    #
    # Chaque état délabré illustre la RAISON DU VERROU écrite dans
    # GameContent.cs — l'escalier sans marches, les toiles retournées, le mur
    # sans porte. C'est ce qui fait d'une pièce fermée une promesse plutôt
    # qu'un refus, et ça ne marche que si l'image dit la même chose que le
    # texte.
    #
    # La dominante suit l'étage, comme CADRE.md le demande pour tenir la
    # cohérence sur trente-deux images : sous-sol pierre et vert froid,
    # rez-de-chaussée bois chaud, premier tissus fanés, combles poussière
    # dorée, dehors bleu de nuit.

    ("cave-0", "an abandoned stone cellar, damp green-stained walls, old barrels "
               "and broken crates, a dark wet stain spreading across the floor, "
               "cold green gloom"),
    ("cave-1", "a restored stone cellar, tidy racks of preserve jars, swept floor, "
               "lantern hanging, warm amber light on damp stone"),

    # « Il n'y a pas de porte. Il y en avait une. »
    ("laboratoire-0", "a cellar wall where a doorway has been bricked up with "
                      "mismatched bricks, faint violet light seeping through the "
                      "cracks, cold darkness, stone floor"),
    ("laboratoire-1", "a witch alchemy laboratory, glass alembics and bubbling "
                      "violet potions, shelves of labelled jars, warm golden and "
                      "violet light, magical"),

    # « L'escalier a perdu ses marches, de la sixième à la douzième. »
    ("hall-0", "an abandoned manor entrance hall, grand wooden staircase with a "
               "whole section of steps missing leaving a gap, dust sheets, cold "
               "grey light from a tall window"),
    ("hall-1", "a restored manor entrance hall, repaired grand staircase, polished "
               "warm wood, rug, chandelier glowing golden"),

    # « La table est mise pour douze. Personne n'est venu. »
    ("salle-a-manger-0", "an abandoned dining room, long table still set for twelve "
                         "with dusty plates and grey cobwebs between the glasses, "
                         "chairs pushed back, cold dim light"),
    ("salle-a-manger-1", "a restored dining room, long table set for a feast, lit "
                         "candles down the middle, warm golden light, garlands of "
                         "dried herbs"),

    # « La clé n'a jamais été retrouvée. »
    ("bibliotheque-0", "a dim dusty manor library behind a heavy locked door with "
                       "an empty keyhole, tall bookshelves in shadow, cold shafts "
                       "of light through shutters"),
    ("bibliotheque-1", "a restored manor library, shelves full of books, rolling "
                       "ladder, deep armchair, reading lamp, warm amber light"),

    # « La porte est fermée de l'intérieur. »
    ("chambre-enfant-0", "an abandoned child bedroom, small iron bed, faded cloth "
                         "toys on the floor, door shut, cold blue gloom, thick dust"),
    ("chambre-enfant-1", "a restored child bedroom, made bed with a quilt, wooden "
                         "toys on a shelf, open window, soft warm daylight"),

    # « Le plafond s'est effondré dans la baignoire. »
    ("salle-de-bain-0", "a ruined bathroom, collapsed ceiling plaster and broken "
                        "laths fallen into an old clawfoot bathtub, cold grey "
                        "daylight falling through the hole above"),
    ("salle-de-bain-1", "a restored bathroom, repaired ceiling, gleaming clawfoot "
                        "bathtub, candles and potted plants, warm soft light"),

    # « Les toiles sont retournées contre le mur. Toutes. »
    ("couloir-portraits-0", "a dark manor corridor lined with framed paintings all "
                            "turned face against the wall showing only their backs, "
                            "dusty runner carpet, cold dim light"),
    ("couloir-portraits-1", "a restored manor corridor, framed portraits hung facing "
                            "the room, wall sconces glowing, polished floor, warm light"),

    # « L'échelle a cédé. Quelque chose bat des ailes là-haut. »
    ("colombier-0", "an abandoned stone dovecote loft, broken ladder lying on the "
                    "floor, scattered feathers, rows of empty nesting holes, dusty "
                    "shafts of cold light"),
    ("colombier-1", "a restored dovecote loft, new wooden ladder, white doves in the "
                    "nesting holes, warm evening light through the openings"),

    # « Les ronces ont refermé le passage derrière elles. »
    ("jardin-0", "an overgrown abandoned garden, dense thorny brambles closing the "
                 "path completely, dead hedges and a broken bench, cold overcast light"),
    ("jardin-1", "a restored night garden, cleared gravel paths, luminous flowers, "
                 "hanging lanterns, warm violet and green glow, magical"),

    # « La corde remonte seule quand on la lâche. »
    ("puits-0", "an old stone well in an abandoned courtyard at dusk, dark rope "
                "hanging taut into the shaft, wet mossy stones, ivy, cold blue gloom"),
    ("puits-1", "a restored stone well at dusk, new rope and bucket, flowers planted "
                "around the base, lantern light, gentle violet glow rising from the water"),
]

# Fonds d'écran. Ce ne sont ni des objets ni des pièces : pas de détourage, et
# pas de recadrage 4:3 non plus — un fond couvre un écran portrait, on le garde
# carré et c'est l'affichage qui recouvre.
#
# Le ciel doit rester DISCRET : il passe derrière la coupe du manoir, à faible
# opacité. D'où « low contrast », « very dark », et surtout le refus explicite
# d'un horizon, d'une lune ou d'un paysage — SDXL en pose un dès qu'on dit
# « ciel », et une ligne d'horizon au milieu d'une maison en coupe est un
# non-sens qu'on ne peut plus enlever.
FOND_STYLE = (
    "painterly atmospheric texture, very dark, low contrast, soft, "
    "no subject, no people, no text, mobile game background art"
)

# « no horizon / no landscape » ne suffit PAS : le premier tirage a rendu des
# montagnes et des sapins sous un ciel parfait. Interdire un objet ne marche pas ;
# imposer un CADRAGE où il ne peut pas exister, si. « Looking straight up at the
# zenith » supprime l'horizon parce qu'un zénith n'en a pas.
FONDS = [
    ("ciel", "looking straight up at the zenith of a deep indigo and violet night "
             "sky, faint scattered distant stars, thin drifting mist and haze, "
             "nothing but sky filling the whole frame, very dark and subtle, "
             "even all over"),
]

# Les bestioles du manoir. Elles ne sont pas de la décoration ajoutée : Cendre
# est un objet unique promis par JEU.md — « décor, purement visuel », gagné en
# restaurant le salon — et la chauve-souris est écrite dans la raison du verrou
# du colombier : « L'échelle a cédé. Quelque chose bat des ailes là-haut. »
#
# ⚠ On ne génère PAS l'animation. Une sonde l'a confirmé et la recherche aussi :
# SDXL rend de très belles poses uniques et des images d'animation incohérentes.
# Deux demandes de chat « debout, quatre pattes séparées » ont rendu deux chats
# ASSIS. Le cycle de marche est donc articulé par code (voir Bestiaire.cs) ;
# ici on ne produit qu'une silhouette, et le jeu la découpe et l'anime.
#
# « Silhouette » est le mot qui fait céder la pose : un chat qui MARCHE de profil
# est un pictogramme si courant que le modèle le rend sans discuter, là où
# « standing, four legs separated » se fait ignorer deux fois de suite.
BESTIOLE_STYLE = (
    "flat solid silhouette, single flat color shape, clean simple outline, "
    "side profile, whole body inside the frame, "
    "isolated on solid plain white background, no text, no shadow, no ground"
)

BESTIOLES = [
    ("chat", "a flat black silhouette of a cat walking in side profile, "
             "facing right, all four legs visible and clearly apart in mid-stride, "
             "tail raised and curved, ears up, simple pictogram shape"),
    ("chauvesouris", "a flat black silhouette of a bat seen from the front with "
                     "both wings fully spread wide and symmetric, small body in "
                     "the middle, ears up, simple pictogram shape"),
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


ITEMS_UNITY = PROJET_UNITY / "Assets" / "Resources" / "Items"


def deja_produit(nom: str) -> bool:
    """Le décor est-il déjà dans le projet Unity ?"""
    return (ITEMS_UNITY / f"decor-{nom}.png").exists()


def generer_decors(studio, exporter, limite=None, dry=False, nouveaux=False):
    """Décors de pièce. Pas de détourage : un fond n'a pas à être découpé.

    `nouveaux` saute ceux déjà présents dans le projet. C'est le mode normal
    quand on complète un lot : `--limit` prend les N PREMIERS, donc toujours
    les mêmes, et régénérer une image validée la remplace par un autre tirage.
    """
    faits, echecs = [], []
    lot = [d for d in DECORS if not deja_produit(d[0])] if nouveaux else list(DECORS)
    ignores = len(DECORS) - len(lot)
    if ignores:
        print(f"\n  {ignores} décors déjà produits, ignorés.")
    lot = lot[:limite] if limite else lot

    for i, (nom, description) in enumerate(lot, 1):
        print(f"\n[{i}/{len(lot)}] decor {nom}")
        print(f"    {description[:70]}...")
        if dry:
            continue

        t0 = time.time()
        try:
            chemins = studio.sprite(description, name=f"decor-{nom}",
                                    style=DECOR_STYLE, variants=1, transparent=False)
        except Exception as e:  # noqa: BLE001
            print(f"    ECHEC : {e}")
            echecs.append(nom)
            continue

        src = Path(chemins[0] if isinstance(chemins, (list, tuple)) else chemins)
        src = recadrer_decor(src)
        dest = exporter.export(src, "sprite", f"decor-{nom}")
        print(f"    OK en {time.time() - t0:.0f}s -> {dest.name}")
        faits.append(dest)

    return faits, echecs


def recadrer_decor(png: Path) -> Path:
    """Recadre en 4:3 paysage et ramène à 768 px de large.

    SDXL rend du carré ; le panneau de la pièce est nettement plus large que
    haut. Recadrer au centre plutôt que déformer.
    """
    from PIL import Image

    im = Image.open(png).convert("RGB")
    cible = 4 / 3
    if im.width / im.height > cible:
        h = im.height
        w = int(h * cible)
    else:
        w = im.width
        h = int(w / cible)

    g = (im.width - w) // 2
    t = (im.height - h) // 2
    im = im.crop((g, t, g + w, t + h))

    if im.width > 768:
        im = im.resize((768, int(768 * im.height / im.width)), Image.LANCZOS)
    im.save(png)
    return png


def recadrer_fond(png: Path) -> Path:
    """Ne garde que la colonne centrale haute : le seul ciel sûr.

    Deux tirages ont posé un horizon, des montagnes puis des sapins, malgré
    « no horizon », « no landscape » et un cadrage zénithal. `CLAUDE.md` tranche
    ce cas : quand SDXL résiste, c'est le contenu qui cède, pas le prompt.

    Le sol arrive toujours par le bas, et les arbres par les bords — le haut du
    centre est la région qu'aucun des deux tirages n'a salie. 54 % et non 60 :
    à 60 %, la cime d'un sapin dépassait encore dans le coin bas-gauche. Le découpage est
    donc exprimé en fractions et non en pixels : il vaut pour le prochain
    tirage comme pour celui-ci.
    """
    from PIL import Image

    im = Image.open(png).convert("RGB")
    g, d = int(im.width * 0.24), int(im.width * 0.78)
    b = int(im.height * 0.54)
    im.crop((g, 0, d, b)).save(png)
    return png


def generer_fonds(studio, exporter, limite=None, dry=False, nouveaux=False):
    """Fonds d'écran. Pas de détourage : un ciel n'a rien à découper."""
    faits, echecs = [], []
    lot = ([f for f in FONDS if not (ITEMS_UNITY / f"fond-{f[0]}.png").exists()]
           if nouveaux else list(FONDS))
    lot = lot[:limite] if limite else lot

    for i, (nom, description) in enumerate(lot, 1):
        print(f"\n[{i}/{len(lot)}] fond {nom}")
        if dry:
            continue

        t0 = time.time()
        try:
            chemins = studio.sprite(description, name=f"fond-{nom}",
                                    style=FOND_STYLE, variants=1, transparent=False)
        except Exception as e:  # noqa: BLE001
            print(f"    ECHEC : {e}")
            echecs.append(nom)
            continue

        src = recadrer_fond(Path(chemins[0] if isinstance(chemins, (list, tuple))
                                 else chemins))
        dest = exporter.export(src, "sprite", f"fond-{nom}")
        print(f"    OK en {time.time() - t0:.0f}s -> {dest.name}")
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
    ap.add_argument("--only", choices=["sprites", "decors", "fonds", "music"])
    ap.add_argument("--limit", type=int, help="ne traiter que les N premiers")
    ap.add_argument("--dry-run", action="store_true", help="affiche le plan sans générer")
    ap.add_argument("--nouveaux", action="store_true",
                    help="décors : ne produire que ceux absents du projet Unity")
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

    if args.only in (None, "decors"):
        studio = game_studio(str(RACINE / "outputs" / "heritage"))
        resultats["décors"] = generer_decors(studio, exporter, args.limit,
                                             args.dry_run, args.nouveaux)

    if args.only in (None, "fonds"):
        studio = game_studio(str(RACINE / "outputs" / "heritage"))
        resultats["fonds"] = generer_fonds(studio, exporter, args.limit,
                                           args.dry_run, args.nouveaux)

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

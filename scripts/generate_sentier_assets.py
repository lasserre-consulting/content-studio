"""Genere les assets du Sentier des Sorcieres et les depose dans son projet Unity.

    python scripts/generate_sentier_assets.py --only mondes
    python scripts/generate_sentier_assets.py --dry-run

UN MONDE = UNE CARTE = UNE IMAGE. C'est ce qui rend le probleme soluble : une
carte longue derive (SDXL ne tient ni l'echelle ni la coherence sur une
composition etiree, c'est la lecon du manoir), alors qu'un monde tient dans un
carre de 1024. On ne surcharge donc aucune carte, et on passe au monde suivant
quand on a fait assez de niveaux.

Le sentier et ses noeuds sont dessines par le CODE par-dessus l'image.

Corollaire : les cartes ne doivent contenir NI chemin, NI icone, NI pancarte.
Un sentier peint dans l'image ne tomberait jamais en face des noeuds reels.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

PROJET_UNITY = Path(r"C:\Users\lasse\workspace\jeux mobiles\SentierDesSorcieres")

# Dominante par region, comme les etages du manoir : c'est ce qui tient la
# coherence sur une serie, la ou une passe unique derive.
# LA CARTE EST UN PLATEAU DE JEU, PAS UN PAYSAGE.
#
# Premiere fournee : de tres belles illustrations en perspective — un horizon,
# du ciel, des troncs au premier plan. Impraticables : la moitie du cadre ne
# peut recevoir aucun noeud, et ceux qu'on y poserait tomberaient dans le ciel
# ou sur un tronc. Le retour a ete « joli mais pas tres pratique », et il etait
# juste.
#
# La parade est celle de l'horizon : on n'INTERDIT pas le ciel, on impose un
# cadrage ou il ne peut pas exister. « Seen from directly above » supprime a la
# fois l'horizon, la perspective et les elements de premier plan, et etale le
# terrain sur tout le cadre — ce qui est exactement ce qu'il faut pour poser
# vingt niveaux lisibles.
#
# Ton MOYEN, aussi : un terrain trop sombre avale les pastilles. L'univers reste
# nocturne, mais le sol doit rester plus clair que les noeuds qui s'y posent.
MONDE_STYLE = (
    "top-down bird eye view game world map, seen from directly above, "
    "flat readable ground filling the entire frame edge to edge, "
    "terrain continues past all four edges, "
    "stylised mobile game level map art, clean readable shapes, "
    "witch coven world at night, eerie and enchanted, moonlit, "
    "deep violet and sickly green, cold magical glow, candlelight accents, "
    "mid-tone ground so markers stay readable, "
    "no sky, no horizon, no clouds, no perspective, no foreground framing, "
    "no island, no floating platform, no round vignette, no border, "
    "no path, no road, no trail, no walls, no fences, no stone borders, "
    "no enclosures, no lines on the ground, "
    "no signposts, no icons, no text, no characters"
)

# TROIS REGLES, CHACUNE PAYEE PAR UN ESSAI RATE.
#
# 1. LE SUJET DOIT ETRE NATURELLEMENT PLAT. Le pic a ete retire : une montagne
#    « vue de dessus » est une contradiction, et le modele tranche en faveur du
#    paysage — ciel, nuages, horizon, tout ce qu'on voulait eviter.
#
# 2. LE TERRAIN NE DOIT PORTER AUCUNE LIGNE. Une allee peinte, un muret, une
#    cloture : tout cela se lit comme une route et concurrence le seul vrai
#    chemin, celui que le code dessine. D'ou des sujets decrits comme des
#    SEMIS — des choses eparpillees, jamais reliees.
#
# 3. LE DECOR PORTE LE THEME, PAS LE STYLE SEUL. Un marais rendu « joli mais
#    naturel » n'est pas un marais de sorcieres. Ce qui fait basculer, ce sont
#    les OBJETS semes dessus : bougies, ossements, pierres gravees, chaudrons
#    abandonnes, charmes suspendus. Ils restent eparpilles, donc ne fabriquent
#    aucune ligne.
MONDES = [
    ("marais", "a witch bog at night seen from straight above, black water "
               "channels between mossy islands, clumps of reeds, pale dead tree "
               "stumps, scattered green will-o-wisps, half sunken skulls and rib "
               "bones, lit candles stuck on stones, floating violet lilies"),
    ("lande", "a witch moor at night seen from straight above, open heather and "
              "bare earth, scattered carved rune stones and boulders far apart, "
              "rings of glowing violet mushrooms, abandoned cauldrons, bundles of "
              "bound twigs, scattered bones, nothing connecting them"),
    ("cimetiere", "an overgrown witch graveyard at night seen from straight "
                  "above, leaning headstones scattered far apart on open grass, "
                  "bare earth patches, isolated flat tombs, guttering candles, "
                  "hanging charms on stakes, cold green glow, nothing connecting them"),
]



def generer(studio, exporter, lot, dry=False):
    faits, echecs = [], []
    for i, (nom, description) in enumerate(lot, 1):
        print(f"\n[{i}/{len(lot)}] region {nom}")
        if dry:
            continue
        t0 = time.time()
        try:
            # Portrait, et plus grand que l'ecran : la carte se PARCOURT au
            # doigt, elle ne se contemple pas d'un coup. 832x1216 est une taille
            # que SDXL rend proprement (multiple de 64, ratio 2:3).
            chemins = studio.sprite(description, name=f"monde-{nom}",
                                    style=MONDE_STYLE, variants=1, transparent=False,
                                    width=832, height=1216)
        except Exception as e:  # noqa: BLE001
            print(f"    ECHEC : {e}")
            echecs.append(nom)
            continue
        src = Path(chemins[0] if isinstance(chemins, (list, tuple)) else chemins)
        dest = exporter.export(src, "sprite", f"monde-{nom}")
        print(f"    OK en {time.time() - t0:.0f}s -> {dest.name}")
        faits.append(dest)
    return faits, echecs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["mondes"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not PROJET_UNITY.exists():
        print(f"Projet Unity introuvable : {PROJET_UNITY}")
        return 1

    from studio import game_studio
    from studio.exporters import UnityExporter

    exporter = UnityExporter(PROJET_UNITY)
    if not args.dry_run:
        exporter.install_postprocessor()

    studio = game_studio(str(RACINE / "outputs" / "sentier"))
    lot = MONDES[:args.limit] if args.limit else MONDES
    faits, echecs = generer(studio, exporter, lot, args.dry_run)

    print(f"\n  regions : {len(faits)} produites, {len(echecs)} echecs")
    for e in echecs:
        print(f"    ! {e}")
    return 1 if echecs else 0


if __name__ == "__main__":
    raise SystemExit(main())

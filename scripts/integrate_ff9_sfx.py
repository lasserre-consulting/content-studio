"""Intègre les SFX générés dans le mod FF9, aux noms canoniques du doc audio.

Copie outputs/ff9/sfx/<name>.wav → StreamingAssets/Assets/Audio/SFX/<canonique>.wav
où <canonique> suit la nomenclature de audio_implementation.md section 8
(SFX_<CAT>_<NNN>_<name>.wav).

⚠️ Memoria.ini ne référence PAS de chemins SFX (ils sont chargés par l'AudioHook du mod
via leur ID). Ce dépôt en Audio/SFX/ suit la structure documentée mais reste à VÉRIFIER
contre le loader C# réel. Les SFX réutilisant des sons FF9 d'origine (menus, melodies)
ne sont pas fournis.

Usage : python scripts/integrate_ff9_sfx.py [--no-mod]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SFX_DIR = ROOT / "outputs" / "ff9" / "sfx"
MOD_SFX = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY IX\FF9_Suite\StreamingAssets\Assets\Audio\SFX"
)

# manifest name -> nom canonique (sans extension) d'après audio_implementation.md §8.
CANONICAL = {
    "deathguise_ambient_scan": "SFX_ENT_001_deathguise_ambient_scan",
    "deathguise_scan_lock": "SFX_ENT_002_deathguise_scan_lock",
    "deathguise_attack_retraction": "SFX_ENT_003_deathguise_attack_retraction",
    "deathguise_death_silence": "SFX_ENT_004_deathguise_death_silence",
    "deathguise_flee": "SFX_ENT_005_deathguise_flee",
    "deathguise_presence_loop": "SFX_ENT_006_deathguise_presence_loop",
    "nova_dragon_ambient_ground": "SFX_ENT_007_nova_dragon_ambient_ground",
    "nova_dragon_approach": "SFX_ENT_008_nova_dragon_approach",
    "nova_dragon_attack_effacement": "SFX_ENT_009_nova_dragon_attack_effacement",
    "nova_dragon_death": "SFX_ENT_010_nova_dragon_death",
    "kuja_imitation_voice_ambient": "SFX_ENT_011_kuja_imitation_voice_ambient",
    "kuja_imitation_voice_01": "SFX_ENT_012_kuja_imitation_voice_01",
    "necron_ambient_omnidirectional": "SFX_ENT_014_necron_ambient_omnidirectional",
    "necron_attack_precurseur": "SFX_ENT_015_necron_attack_precurseur",
    "necron_attack_vide_parfait": "SFX_ENT_016_necron_attack_vide_parfait",
    "ozma_nonlanguage_loop": "SFX_ENT_017_ozma_nonlanguage_loop",
    "ozma_terminus_charge": "SFX_ENT_018_ozma_terminus_charge",
    "hit_on_thirdworld_entity": "SFX_CMB_001_hit_on_thirdworld_entity",
    "hit_on_thirdworld_magic": "SFX_CMB_002_hit_on_thirdworld_magic",
    "player_receives_hit_nova": "SFX_CMB_003_player_receives_hit_nova",
    "player_receives_hit_deathguise": "SFX_CMB_004_player_receives_hit_deathguise",
    "status_catalogued_apply": "SFX_CMB_005_status_catalogued_apply",
    "status_reminiscence_apply": "SFX_CMB_006_status_reminiscence_apply",
    "status_reminiscence_saves": "SFX_CMB_007_status_reminiscence_saves",
    "trance_activation": "SFX_CMB_008_trance_activation",
    "ipsen_safezone_freeze": "SFX_CMB_009_ipsen_safezone_freeze",
    "ipsen_safezone_dissolve": "SFX_CMB_010_ipsen_safezone_dissolve",
    "ozma_analysis_complete": "SFX_CMB_011_ozma_analysis_complete",
    "magic_becomes_inefficient": "SFX_CMB_013_magic_becomes_inefficient",
    "nova_dragon_holy_weakness": "SFX_CMB_014_nova_dragon_holy_weakness",
    "kuja_imitation_spells_minor": "SFX_CMB_015_kuja_imitation_spells_minor",
    "necron_learns": "SFX_CMB_016_necron_learns",
    "necron_says_not_like_him": "SFX_CMB_017_necron_says_not_like_him",
    "rift_open_crack": "SFX_ENV_001_rift_open_crack",
    "rift_ambient_loop": "SFX_ENV_002_rift_ambient_loop",
    "alexandria_fire_loop": "SFX_ENV_003_alexandria_fire_loop",
    "third_world_entity_footprint": "SFX_ENV_004_third_world_entity_footprint",
    "ipsen_hors_temps_zone": "SFX_ENV_005_ipsen_hors_temps_zone",
    "memoria_zone_saine": "SFX_ENV_006_memoria_zone_saine",
    "memoria_zone_corrompue": "SFX_ENV_007_memoria_zone_corrompue",
    "crystal_world_sain_ambient": "SFX_ENV_008_crystal_world_sain_ambient",
    "crystal_world_corrompu_ambient": "SFX_ENV_009_crystal_world_corrompu_ambient",
    "treno_under_siege": "SFX_ENV_010_treno_under_siege",
    "silence_actif_ozma": "SFX_ENV_011_silence_actif_ozma",
    "epilogue_wind": "SFX_ENV_012_epilogue_wind",
    "ui_name_glitch": "SFX_UI_007_ui_name_glitch",
    "level_up": "SFX_UI_009_level_up",
    "game_over_acte3": "SFX_UI_010_game_over",
    "cin_sky_opens_silence": "SFX_CIN_002_cin_sky_opens_silence",
    "cin_melodies_stops": "SFX_CIN_003_cin_melodies_stops",
    "cin_alexandrias_lights": "SFX_CIN_004_cin_alexandrias_lights",
    "cin_fissure_first_sight": "SFX_CIN_005_cin_fissure_first_sight",
    "cin_necron_second_attempt": "SFX_CIN_007_cin_necron_second_attempt",
    "cin_vivi_reminder": "SFX_CIN_009_cin_vivi_reminder",
    "cin_epilogue_wind_and_fissure": "SFX_CIN_010_cin_epilogue_wind_and_fissure",
    # ozma_nl_* : sous-dossier dédié (cf. doc §8 ozma_nonlanguage/)
    "ozma_nl_phase1_observe": "ozma_nonlanguage/ozma_nl_phase1_observe",
    "ozma_nl_phase2_adapt": "ozma_nonlanguage/ozma_nl_phase2_adapt",
}


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--no-mod", action="store_true", help="copier vers outputs/ff9/sfx_canonical/ au lieu du mod")
    args = ap.parse_args()

    dest_root = (ROOT / "outputs" / "ff9" / "sfx_canonical") if args.no_mod else MOD_SFX
    dest_root.mkdir(parents=True, exist_ok=True)

    copied, missing = 0, []
    for name, canonical in CANONICAL.items():
        src = SFX_DIR / f"{name}.wav"
        if not src.exists():
            missing.append(name)
            continue
        dest = dest_root / f"{canonical}.wav"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        copied += 1

    print(f"Intégrés : {copied}/{len(CANONICAL)} → {dest_root}")
    if missing:
        print(f"WAV source manquants ({len(missing)}) : {', '.join(missing)}")
    # SFX du doc volontairement non fournis (réutilisent des sons FF9 d'origine) :
    print("Non fournis (réutilisent FF9 d'origine / déclencheurs) : "
          "SFX_UI_001-006/008 (menus, save, icône), SFX_CIN_001 (Melodies insert), "
          "SFX_CIN_006/008, SFX_ENT_013 (silence_3sec), SFX_CMB_012 (trigger).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

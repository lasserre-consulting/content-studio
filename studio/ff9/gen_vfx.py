"""Générateur des textures source VFX (particules / overlays) — FF9 Suite.

Produit les assets visuels SOURCE référencés par les Unity Particle Systems
décrits dans vfx/particles/_MANIFEST.txt. Tous les fichiers sont PNG-32 (RGBA).
"""
from __future__ import annotations

from pathlib import Path

from studio.ff9 import common as c

SUBDIR = "vfx/particles"


def generate(out_root: Path) -> list[Path]:
    out = Path(out_root) / SUBDIR
    paths: list[Path] = []

    # ----------------------------------------------------------------- #
    # FICHIER 1 — vfx_retraction_compression.png (256×256, spritesheet 2×2)
    # Onde de compression INVERSÉE : l'anneau rétrécit de l'extérieur
    # vers le centre. 4 frames de 128×128, anneau bord-seulement (ép. 6px).
    # Couleurs RGBA précises -> on passe le tuple (r,g,b) + alpha séparé.
    # ----------------------------------------------------------------- #
    f1 = c.ring(128, radius=60, thickness=6, color=(200, 200, 220), alpha=200)
    f2 = c.ring(128, radius=44, thickness=6, color=(180, 160, 210), alpha=160)
    f3 = c.ring(128, radius=25, thickness=6, color=(100, 60, 130), alpha=100)
    f4 = c.ring(128, radius=6, thickness=6, color=(45, 10, 71), alpha=50)
    sheet1 = c.grid_sheet([f1, f2, f3, f4], cols=2, rows=2)
    paths.append(c.save_png(sheet1, out / "vfx_retraction_compression.png"))

    # ----------------------------------------------------------------- #
    # FICHIER 2 — vfx_chroma_inversion_2f.png (1920×1080)
    # Blanc pur #FFFFFF alpha 255 partout (fond du canvas overlay shader).
    # ----------------------------------------------------------------- #
    chroma = c.solid(1920, 1080, (255, 255, 255, 255))
    paths.append(c.save_png(chroma, out / "vfx_chroma_inversion_2f.png"))

    # ----------------------------------------------------------------- #
    # FICHIER 3 — vfx_particles_inverted_direction.png (128×128)
    # Particule 'âme' : brillante au centre. Disque doux ovale ~16×12px.
    # On vise centre #FFF a=255, mi-rayon #C8C8C8 a=200, bord transparent.
    # Superposition de 2 discs : le cœur blanc dense + un halo gris ->
    # respecte le palier mi-rayon (a≈200) que l'interpolation linéaire
    # seule ne donnerait pas. Puis étirement horizontal pour l'ovale.
    # ----------------------------------------------------------------- #
    halo = c.soft_disc(128, radius=8, color=(200, 200, 200),
                       center_alpha=200, edge_alpha=0, gamma=1.0)
    core = c.soft_disc(128, radius=6, color=(255, 255, 255),
                       center_alpha=255, edge_alpha=0, gamma=1.4)
    halo.alpha_composite(core)
    # Ovale ~16×12 : compression verticale 128->96 (ratio 12/16=0.75) puis
    # recentrage sur un canvas 128×128 transparent.
    squashed = halo.resize((128, 96))
    oval = c.new_canvas(128, 128)
    oval.alpha_composite(squashed, (0, (128 - 96) // 2))
    paths.append(c.save_png(oval, out / "vfx_particles_inverted_direction.png"))

    # ----------------------------------------------------------------- #
    # FICHIER 4 — vfx_desaturation_radial.png (512×512)
    # Gradient radial niveaux de gris : centre #FFF -> bord #000, pow(d,0.7).
    # ----------------------------------------------------------------- #
    desat = c.radial_gray(512, gamma=0.7)
    paths.append(c.save_png(desat, out / "vfx_desaturation_radial.png"))

    # ----------------------------------------------------------------- #
    # FICHIER 5 — Flash Ozma : 3 fichiers SÉPARÉS (1920×1080) blanc pur.
    # ----------------------------------------------------------------- #
    paths.append(c.save_png(c.solid(1920, 1080, (255, 255, 255, 255)),
                            out / "vfx_ozma_flash_100.png"))
    paths.append(c.save_png(c.solid(1920, 1080, (255, 255, 255, 204)),
                            out / "vfx_ozma_flash_80.png"))
    paths.append(c.save_png(c.solid(1920, 1080, (255, 255, 255, 128)),
                            out / "vfx_ozma_flash_50.png"))

    # ----------------------------------------------------------------- #
    # FICHIER 6 — vfx_scene_freeze_indicator.png (1920×1080)
    # Vignette noire TRÈS subtile : 0-60% transparent, 60-90% transition,
    # 90-100% à 2% (alpha 5/255). Tension subconsciente.
    # ----------------------------------------------------------------- #
    freeze = c.vignette(1920, 1080, (0, 0, 0), 0.02, 0.60, 0.90)
    paths.append(c.save_png(freeze, out / "vfx_scene_freeze_indicator.png"))

    # ----------------------------------------------------------------- #
    # FICHIER 7 — vfx_terminus_shockwave.png (3 frames 512×512 -> 1536×512)
    # Anneau blanc fin (2px) qui s'agrandit, alpha décroissant sur F3.
    # ----------------------------------------------------------------- #
    s1 = c.ring(512, radius=30, thickness=2, color="#FFFFFF", alpha=255)
    s2 = c.ring(512, radius=100, thickness=2, color="#FFFFFF", alpha=255)
    s3 = c.ring(512, radius=200, thickness=2, color="#FFFFFF", alpha=153)
    sheet7 = c.hsheet([s1, s2, s3])
    paths.append(c.save_png(sheet7, out / "vfx_terminus_shockwave.png"))

    # ----------------------------------------------------------------- #
    # FICHIER 8 (P1) — vfx_soul_particles_reminiscence.png (4 frames 64×64
    # -> 256×64). Lueur douce #E8C547 qui pulse. Disque doux.
    # ----------------------------------------------------------------- #
    p1 = c.soft_disc(64, radius=12, color="#E8C547", center_alpha=230, edge_alpha=0)
    p2 = c.soft_disc(64, radius=10, color="#E8C547", center_alpha=178, edge_alpha=0)
    p3 = c.soft_disc(64, radius=8, color="#E8C547", center_alpha=128, edge_alpha=0)
    p4 = c.soft_disc(64, radius=10, color="#E8C547", center_alpha=178, edge_alpha=0)
    sheet8 = c.hsheet([p1, p2, p3, p4])
    paths.append(c.save_png(sheet8, out / "vfx_soul_particles_reminiscence.png"))

    return paths

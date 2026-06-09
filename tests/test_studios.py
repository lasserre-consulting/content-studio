"""Tests de la couche STUDIO (orchestration) : base, content, gamedev.

Mêmes principes que test_core : aucun modèle lourd, aucun réseau. On branche des
providers factices qui écrivent de vrais petits fichiers dans un dossier temp,
pour vérifier l'orchestration (variations, batch, repli gracieux) sans dépendre
de torch/diffusers ni de ffmpeg.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from studio.config import Config
from studio.core import (
    BaseProvider,
    GenRequest,
    GenResult,
    Location,
    Modality,
    Router,
)
from studio.core.registry import _REGISTRY
from studio.studios import ContentStudio, GamedevStudio, Studio
from studio.studios.base import slugify
from studio.studios.content import _split_beats, _to_srt


@pytest.fixture
def clean_registry():
    snapshot = dict(_REGISTRY)
    try:
        yield _REGISTRY
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(snapshot)


def make_file_provider(modality: Modality, name: str, out_dir: Path, *, available=True):
    """Provider factice qui écrit un vrai fichier (octets bidon) et le renvoie.

    Le seed reçu pilote le nom du fichier → on vérifie que les variations
    produisent bien des fichiers distincts.
    """
    ext = {Modality.IMAGE: ".png", Modality.MUSIC: ".wav",
           Modality.SFX: ".wav", Modality.TTS: ".wav"}.get(modality, ".bin")

    class FileProvider(BaseProvider):
        pass

    FileProvider.name = name
    FileProvider.modality = modality
    FileProvider.location = Location.LOCAL

    def _available(self):
        return available, "ok" if available else "indispo (test)"

    def _generate(self, req: GenRequest) -> GenResult:
        seed = req.seed if req.seed is not None else 0
        dest = out_dir / f"{name}_{seed}{ext}"
        dest.write_bytes(b"FAKE" + str(seed).encode())
        return GenResult(modality=modality, provider=name,
                         location=Location.LOCAL, paths=[dest])

    FileProvider.available = _available
    FileProvider.generate = _generate
    FileProvider.__abstractmethods__ = frozenset()
    FileProvider.__name__ = f"FileProvider_{name}"
    return FileProvider


def build_router(tmp_path: Path, registry: dict, *, with_image=True, with_tts=True,
                 with_music=False) -> Router:
    """Construit un Router avec output_dir=tmp et les providers factices voulus."""
    data: dict = {"defaults": {"output_dir": str(tmp_path)}}
    if with_image:
        registry[(Modality.IMAGE, "fake-img")] = make_file_provider(Modality.IMAGE, "fake-img", tmp_path)
        data["image"] = {"active": "fake-img"}
    if with_tts:
        registry[(Modality.TTS, "fake-tts")] = make_file_provider(Modality.TTS, "fake-tts", tmp_path)
        data["tts"] = {"active": "fake-tts"}
    if with_music:
        registry[(Modality.MUSIC, "fake-mus")] = make_file_provider(Modality.MUSIC, "fake-mus", tmp_path)
        data["music"] = {"active": "fake-mus"}
    return Router(Config(data))


# --------------------------------------------------------------------------- #
# Helpers purs                                                                  #
# --------------------------------------------------------------------------- #
def test_slugify():
    assert slugify("Le Repaire des Sorcières !") == "le-repaire-des-sorcieres"
    assert slugify("  multiple   espaces  ") == "multiple-espaces"
    assert slugify("") == "sans-titre"
    assert len(slugify("x" * 100)) <= 48


def test_split_beats_paragraphs():
    script = "Premier plan.\n\nDeuxième plan.\n\nTroisième plan."
    assert _split_beats(script) == ["Premier plan.", "Deuxième plan.", "Troisième plan."]


def test_split_beats_caps_count():
    script = "\n\n".join(f"Idée {i}" for i in range(20))
    assert len(_split_beats(script, max_beats=6)) <= 6


def test_to_srt_format():
    srt = _to_srt(["Bonjour", "Au revoir"], total_seconds=10.0)
    assert "00:00:00,000 --> 00:00:05,000" in srt
    assert "Bonjour" in srt and "Au revoir" in srt


# --------------------------------------------------------------------------- #
# Studio base : variations + repli gracieux                                     #
# --------------------------------------------------------------------------- #
def test_variations_produce_distinct_files(tmp_path, clean_registry):
    router = build_router(tmp_path, clean_registry)
    studio = Studio(router, tmp_path / "ws")
    results = studio.variations(Modality.IMAGE, "un chat", n=4, base_seed=500)
    assert len(results) == 4
    paths = {r.path for r in results}
    assert len(paths) == 4  # 4 fichiers distincts (seeds différentes)


def test_try_gen_graceful_when_no_provider(tmp_path, clean_registry):
    # Router sans aucun provider image → try_gen renvoie None, pas d'exception.
    router = build_router(tmp_path, clean_registry, with_image=False, with_tts=False)
    studio = Studio(router, tmp_path / "ws")
    assert studio.try_gen(Modality.IMAGE, "x") is None


def test_refine_falls_back_to_original_prompt(tmp_path, clean_registry):
    router = build_router(tmp_path, clean_registry, with_image=False, with_tts=False)
    studio = Studio(router, tmp_path / "ws")
    # Aucun LLM dispo → refine() rend le prompt inchangé.
    assert studio.refine("chat", "améliore") == "chat"


# --------------------------------------------------------------------------- #
# GamedevStudio                                                                 #
# --------------------------------------------------------------------------- #
def test_gamedev_sprite_variants(tmp_path, clean_registry):
    router = build_router(tmp_path, clean_registry)
    game = GamedevStudio(router, tmp_path / "game")
    paths = game.sprite("vieille sorcière", name="Morra", variants=3)
    assert len(paths) == 3
    # Renommage lisible + indexé, rangé sous sprite/.
    assert all(p.parent.name == "sprite" for p in paths)
    assert paths[0].name == "morra_00.png"
    assert all(p.exists() for p in paths)


def test_gamedev_batch(tmp_path, clean_registry):
    router = build_router(tmp_path, clean_registry, with_music=True)
    game = GamedevStudio(router, tmp_path / "game")
    from studio.studios.gamedev import AssetSpec

    specs = [
        AssetSpec(kind="sprite", name="goblin", prompt="goblin vert", variants=2),
        AssetSpec(kind="bgm", name="combat", prompt="thème de combat"),
        AssetSpec(kind="voice", name="intro", prompt="Bienvenue aventurier"),
    ]
    out = game.batch(specs)
    assert len(out["goblin"]) == 2
    assert len(out["combat"]) == 1
    assert len(out["intro"]) == 1


def test_gamedev_detour_graceful_without_rembg(tmp_path, clean_registry, monkeypatch):
    # rembg indisponible → detour() renvoie [] sans planter (pas de modèle chargé).
    from studio.assembly import image_ops

    monkeypatch.setattr(image_ops, "rembg_available", lambda: (False, "absent (test)"))
    router = build_router(tmp_path, clean_registry)
    game = GamedevStudio(router, tmp_path / "game")
    fake_png = tmp_path / "x.png"
    fake_png.write_bytes(b"PNG")
    assert game.detour([fake_png]) == []


def test_gamedev_sprite_transparent_off(tmp_path, clean_registry):
    # transparent=False : pas de détourage, on garde les fichiers bruts tels quels.
    router = build_router(tmp_path, clean_registry)
    game = GamedevStudio(router, tmp_path / "game")
    paths = game.sprite("dragon", name="drake", variants=2, transparent=False)
    assert len(paths) == 2
    assert all(p.exists() for p in paths)


def test_gamedev_skips_unavailable_modality(tmp_path, clean_registry):
    # Pas de provider SFX → la spec sfx renvoie une liste vide, sans planter.
    router = build_router(tmp_path, clean_registry)
    game = GamedevStudio(router, tmp_path / "game")
    from studio.studios.gamedev import AssetSpec

    out = game.batch([AssetSpec(kind="sfx", name="boom", prompt="explosion")])
    assert out["boom"] == []


# --------------------------------------------------------------------------- #
# ContentStudio : repli gracieux (sans ffmpeg ni image, on ne plante pas)       #
# --------------------------------------------------------------------------- #
def test_content_short_degrades_without_image(tmp_path, clean_registry):
    # Voix OK mais aucune image → pas de montage, mais Short renvoyé avec notes.
    router = build_router(tmp_path, clean_registry, with_image=False, with_tts=True)
    studio = ContentStudio(router, tmp_path / "content")
    short = studio.short("Bonjour ceci est un test.", title="essai", music_prompt=None)
    assert short.video is None
    assert short.voice is not None
    assert any("image" in n for n in short.notes)

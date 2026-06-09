"""Tests du linter d'assets `studio.verify`.

On fabrique des images (PIL) et des WAV (soundfile + numpy) factices dans
tmp_path, puis on vérifie que verify_image / verify_audio / verify_manifest
détectent correctement : bonne taille / mauvaise taille / RGB vs RGBA /
alpha absent ou trivial / fichier manquant / audio mauvais samplerate, etc.

Aucun appel réseau, aucun modèle génératif : tout est local et déterministe.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from PIL import Image

from studio.verify import Spec, verify_audio, verify_image, verify_manifest


# --------------------------------------------------------------------------- #
# Fabriques d'assets factices                                                  #
# --------------------------------------------------------------------------- #

def make_image(path: Path, size=(64, 32), mode="RGBA", *, transparent=True) -> Path:
    """Crée une image PIL. En RGBA, `transparent` met le coin (0,0) à alpha=0."""
    if mode == "RGBA":
        color = (10, 20, 30, 255)
        img = Image.new("RGBA", size, color)
        if transparent:
            img.putpixel((0, 0), (10, 20, 30, 0))  # au moins 1 pixel transparent
    else:
        img = Image.new(mode, size, (10, 20, 30))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")
    return path


def make_wav(path: Path, *, samplerate=48000, channels=1, duration=2.0) -> Path:
    """Crée un WAV de silence (numpy) avec samplerate/canaux/durée donnés."""
    frames = int(round(samplerate * duration))
    data = np.zeros((frames, channels), dtype="float32") if channels > 1 \
        else np.zeros(frames, dtype="float32")
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), data, samplerate)
    return path


# --------------------------------------------------------------------------- #
# verify_image — dimensions                                                    #
# --------------------------------------------------------------------------- #

def test_image_exact_size_ok(tmp_path):
    p = make_image(tmp_path / "a.png", size=(64, 32))
    assert verify_image(p, Spec(exact_size=(64, 32))) == []


def test_image_exact_size_wrong(tmp_path):
    p = make_image(tmp_path / "a.png", size=(64, 32))
    issues = verify_image(p, Spec(exact_size=(128, 128)))
    assert len(issues) == 1
    assert issues[0]["level"] == "error"
    assert "dimensions" in issues[0]["msg"]


def test_image_width_height_separate(tmp_path):
    p = make_image(tmp_path / "a.png", size=(64, 32))
    # largeur OK, hauteur fausse => une seule erreur (hauteur).
    issues = verify_image(p, Spec(width=64, height=99))
    assert [i["msg"] for i in issues if "hauteur" in i["msg"]]
    assert not [i for i in issues if "largeur" in i["msg"]]


def test_image_min_size(tmp_path):
    p = make_image(tmp_path / "a.png", size=(64, 32))
    assert verify_image(p, Spec(min_size=(32, 16))) == []
    issues = verify_image(p, Spec(min_size=(128, 16)))
    assert any("minimum" in i["msg"] for i in issues)


# --------------------------------------------------------------------------- #
# verify_image — mode / alpha                                                  #
# --------------------------------------------------------------------------- #

def test_image_mode_rgba_ok(tmp_path):
    p = make_image(tmp_path / "a.png", mode="RGBA")
    assert verify_image(p, Spec(mode="RGBA")) == []


def test_image_mode_rgb_vs_rgba(tmp_path):
    p = make_image(tmp_path / "a.png", mode="RGB")
    issues = verify_image(p, Spec(mode="RGBA"))
    assert any("mode" in i["msg"] and i["level"] == "error" for i in issues)


def test_image_require_alpha_present(tmp_path):
    p = make_image(tmp_path / "a.png", mode="RGBA", transparent=True)
    assert verify_image(p, Spec(require_alpha=True)) == []


def test_image_require_alpha_absent_on_rgb(tmp_path):
    # Image RGB : pas de canal alpha du tout => erreur.
    p = make_image(tmp_path / "a.png", mode="RGB")
    issues = verify_image(p, Spec(require_alpha=True))
    assert any("alpha" in i["msg"] and i["level"] == "error" for i in issues)


def test_image_require_alpha_trivial_opaque(tmp_path):
    # RGBA mais 100% opaque => avertissement (alpha "trivial").
    p = make_image(tmp_path / "a.png", mode="RGBA", transparent=False)
    issues = verify_image(p, Spec(require_alpha=True))
    assert any(i["level"] == "warn" and "opaque" in i["msg"] for i in issues)


# --------------------------------------------------------------------------- #
# verify_image — format / poids / fichier manquant                            #
# --------------------------------------------------------------------------- #

def test_image_format_ok(tmp_path):
    p = make_image(tmp_path / "a.png")
    assert verify_image(p, Spec(formats=("PNG",))) == []


def test_image_format_rejected(tmp_path):
    p = make_image(tmp_path / "a.png")
    issues = verify_image(p, Spec(formats=("WEBP",)))
    assert any("format" in i["msg"] and i["level"] == "error" for i in issues)


def test_image_max_kb_exceeded(tmp_path):
    p = make_image(tmp_path / "a.png", size=(512, 512))
    issues = verify_image(p, Spec(max_kb=0.01))  # seuil ridiculement bas
    assert any("poids" in i["msg"] for i in issues)


def test_image_missing_file(tmp_path):
    issues = verify_image(tmp_path / "nope.png", Spec(exact_size=(64, 32)))
    assert len(issues) == 1
    assert issues[0]["level"] == "error"
    assert "introuvable" in issues[0]["msg"]


def test_image_corrupt_file(tmp_path):
    p = tmp_path / "broken.png"
    p.write_bytes(b"ceci n'est pas une image")
    issues = verify_image(p, Spec(exact_size=(64, 32)))
    assert any(i["level"] == "error" and "illisible" in i["msg"] for i in issues)


# --------------------------------------------------------------------------- #
# verify_audio                                                                 #
# --------------------------------------------------------------------------- #

def test_audio_ok(tmp_path):
    p = make_wav(tmp_path / "s.wav", samplerate=48000, channels=1, duration=2.0)
    spec = Spec(samplerate=48000, channels=1, min_duration=1.5, max_duration=2.5)
    assert verify_audio(p, spec) == []


def test_audio_wrong_samplerate(tmp_path):
    p = make_wav(tmp_path / "s.wav", samplerate=22050, channels=1, duration=2.0)
    issues = verify_audio(p, Spec(samplerate=48000))
    assert len(issues) == 1
    assert issues[0]["level"] == "error"
    assert "samplerate" in issues[0]["msg"]


def test_audio_wrong_channels(tmp_path):
    p = make_wav(tmp_path / "s.wav", channels=2)
    issues = verify_audio(p, Spec(channels=1))
    assert any("canaux" in i["msg"] for i in issues)


def test_audio_duration_bounds(tmp_path):
    p = make_wav(tmp_path / "s.wav", duration=0.5)
    issues = verify_audio(p, Spec(min_duration=1.0))
    assert any("durée" in i["msg"] and "minimum" in i["msg"] for i in issues)

    p2 = make_wav(tmp_path / "s2.wav", duration=5.0)
    issues2 = verify_audio(p2, Spec(max_duration=3.0))
    assert any("durée" in i["msg"] and "maximum" in i["msg"] for i in issues2)


def test_audio_missing_file(tmp_path):
    issues = verify_audio(tmp_path / "nope.wav", Spec(samplerate=48000))
    assert issues[0]["level"] == "error"
    assert "introuvable" in issues[0]["msg"]


def test_audio_corrupt_file(tmp_path):
    p = tmp_path / "broken.wav"
    p.write_bytes(b"pas du tout un wav valide")
    issues = verify_audio(p, Spec(samplerate=48000))
    assert any(i["level"] == "error" and "illisible" in i["msg"] for i in issues)


# --------------------------------------------------------------------------- #
# verify_manifest                                                              #
# --------------------------------------------------------------------------- #

def test_manifest_all_ok(tmp_path):
    make_image(tmp_path / "img" / "a.png", size=(100, 50))
    make_image(tmp_path / "img" / "b.png", size=(100, 50))
    manifest = [
        {"name": "a", "out_path": "img/a.png", "width": 100, "height": 50},
        {"name": "b", "out_path": "img/b.png", "width": 100, "height": 50},
    ]

    def spec_for(entry):
        return Spec(exact_size=(entry["width"], entry["height"]))

    report = verify_manifest(manifest, tmp_path, spec_for=spec_for)
    assert report["ok"] is True
    assert report["n"] == 2
    assert report["issues"] == []
    assert report["missing"] == []


def test_manifest_missing_and_bad(tmp_path):
    make_image(tmp_path / "a.png", size=(64, 64))  # bonne, mais mauvaise taille attendue
    manifest = [
        {"name": "a", "out_path": "a.png"},
        {"name": "b", "out_path": "b.png"},  # fichier absent
    ]

    def spec_for(entry):
        return Spec(exact_size=(128, 128))

    report = verify_manifest(manifest, tmp_path, spec_for=spec_for)
    assert report["ok"] is False
    assert report["n"] == 2
    assert "b.png" in report["missing"]
    # 'a.png' : mauvaise dimension ; 'b.png' : introuvable.
    paths_with_error = {i["path"] for i in report["issues"] if i["level"] == "error"}
    assert {"a.png", "b.png"} <= paths_with_error


def test_manifest_without_spec_for_only_existence(tmp_path):
    make_image(tmp_path / "a.png")
    manifest = [
        {"out_path": "a.png"},
        {"out_path": "ghost.png"},
    ]
    report = verify_manifest(manifest, tmp_path)  # pas de spec_for
    assert report["n"] == 2
    assert report["missing"] == ["ghost.png"]
    assert report["ok"] is False  # le fichier manquant reste une erreur


def test_manifest_entry_missing_key(tmp_path):
    manifest = [{"name": "sans_chemin"}]
    report = verify_manifest(manifest, tmp_path)
    assert report["ok"] is False
    assert any("out_path" in i["msg"] for i in report["issues"])


def test_manifest_audio_via_extension(tmp_path):
    make_wav(tmp_path / "snd.wav", samplerate=48000, channels=1, duration=2.0)
    manifest = [{"out_path": "snd.wav", "duration_s": 2.0}]

    def spec_for(entry):
        # Le linter doit aiguiller vers verify_audio grâce à l'extension .wav.
        return Spec(samplerate=48000, channels=1,
                    min_duration=entry["duration_s"] - 0.5,
                    max_duration=entry["duration_s"] + 0.5)

    report = verify_manifest(manifest, tmp_path, spec_for=spec_for)
    assert report["ok"] is True
    assert report["issues"] == []

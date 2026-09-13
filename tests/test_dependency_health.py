"""Tests du rapport de compatibilité des dépendances."""
from __future__ import annotations

from pathlib import Path

from studio import dependency_health


def test_read_specs_parse_sha_git(tmp_path: Path):
    sample = tmp_path / "req.txt"
    sample.write_text(
        "stable-audio-tools @ git+https://github.com/Stability-AI/stable-audio-tools.git@"
        "3241adba4fc2a85cf5b29d9eb68d42f40a28e820\n"
        "torch==2.6.0+cu124\n",
        encoding="utf-8",
    )

    specs = dependency_health._read_specs(sample)
    assert specs["stable-audio-tools"][0] == "@"
    assert specs["stable-audio-tools"][1].endswith("40a28e820")
    assert specs["torch"] == ("==", "2.6.0+cu124")


def test_build_report_repo_no_errors():
    root = Path(__file__).resolve().parent.parent
    report = dependency_health.build_report(root)
    assert report.errors == 0


def test_main_strict_returns_zero():
    rc = dependency_health.main(["--strict", "--format", "json"])
    assert rc == 0

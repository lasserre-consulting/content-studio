"""Rapport de compatibilité des dépendances (fichiers de pinning).

But : détecter tôt les dérives de versions et les risques connus (ABI/DLL Windows)
sans charger de modèle lourd. Le rapport est purement textuel, basé sur :
  - constraints.txt
  - requirements-local.txt
  - requirements.lock.txt
  - requirements/profiles/*.txt

Usage :
    python -m studio.dependency_health
    python -m studio.dependency_health --strict
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Level = Literal["error", "warn", "info"]

_SPEC_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*(==|@)\s*(.+)$")
_SHA_RE = re.compile(r"@[0-9a-f]{40}$")

# Paquets dont l'alignement lock/constraints protège des casses connues.
CRITICAL_PACKAGES = (
    "torch",
    "torchaudio",
    "torchvision",
    "xformers",
    "scikit-learn",
    "kiwisolver",
    "av",
)

REQUIRED_PROFILES = (
    "core.txt",
    "image-local.txt",
    "audio-local.txt",
    "tts-local.txt",
    "full-local.txt",
)


@dataclass
class Finding:
    level: Level
    check: str
    message: str


@dataclass
class Report:
    findings: list[Finding]

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.level == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.level == "warn")


def _read_specs(path: Path) -> dict[str, tuple[str, str]]:
    """Parse un fichier requirements/constraints -> {name: (op, value)}."""
    specs: dict[str, tuple[str, str]] = {}
    if not path.exists():
        return specs
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
            continue
        # Retire les commentaires inline.
        if " #" in line:
            line = line.split(" #", 1)[0].strip()
        m = _SPEC_RE.match(line)
        if not m:
            continue
        name, op, value = m.groups()
        specs[name.lower()] = (op, value.strip())
    return specs


def _check_profiles(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    profiles_dir = root / "requirements" / "profiles"
    if not profiles_dir.exists():
        return [Finding("error", "profiles", "dossier requirements/profiles manquant")]
    for filename in REQUIRED_PROFILES:
        if not (profiles_dir / filename).exists():
            findings.append(Finding("error", "profiles", f"profil manquant: {filename}"))
    if not findings:
        findings.append(Finding("info", "profiles", "profils d'installation par modalité présents"))
    return findings


def _check_git_sha_pin(req_local: dict[str, tuple[str, str]], req_lock: dict[str, tuple[str, str]]) -> list[Finding]:
    findings: list[Finding] = []
    for source_name, specs in (("requirements-local.txt", req_local), ("requirements.lock.txt", req_lock)):
        op_val = specs.get("stable-audio-tools")
        if op_val is None:
            findings.append(Finding("error", "stable-audio-tools", f"{source_name}: dépendance absente"))
            continue
        op, value = op_val
        if op != "@":
            findings.append(Finding("error", "stable-audio-tools", f"{source_name}: utiliser une référence git épinglée"))
            continue
        if not value.startswith("git+https://github.com/Stability-AI/stable-audio-tools.git"):
            findings.append(Finding("error", "stable-audio-tools", f"{source_name}: dépôt inattendu ({value})"))
            continue
        if not _SHA_RE.search(value):
            findings.append(Finding("error", "stable-audio-tools", f"{source_name}: commit SHA 40 caractères manquant"))
            continue
        findings.append(Finding("info", "stable-audio-tools", f"{source_name}: SHA épinglé"))
    return findings


def _check_lock_alignment(constraints: dict[str, tuple[str, str]], req_lock: dict[str, tuple[str, str]]) -> list[Finding]:
    findings: list[Finding] = []
    for package in CRITICAL_PACKAGES:
        c = constraints.get(package)
        l = req_lock.get(package)
        if c is None:
            findings.append(Finding("warn", "lock-align", f"constraints: {package} non trouvé"))
            continue
        if l is None:
            findings.append(Finding("error", "lock-align", f"lock: {package} non trouvé"))
            continue
        if c != l:
            findings.append(Finding("error", "lock-align", f"{package} divergent: constraints={c} lock={l}"))
            continue
        findings.append(Finding("info", "lock-align", f"{package} aligné ({c[1]})"))
    return findings


def _check_prerelease_markers(req_lock: dict[str, tuple[str, str]]) -> list[Finding]:
    findings: list[Finding] = []
    for name, (_op, value) in req_lock.items():
        lowered = value.lower()
        if any(tag in lowered for tag in ("rc", "a", "b")) and re.search(r"\d(rc|a|b)\d", lowered):
            findings.append(Finding("warn", "prerelease", f"{name}={value} est une pré-release"))
    if not findings:
        findings.append(Finding("info", "prerelease", "aucune pré-release détectée"))
    return findings


def build_report(root: Path) -> Report:
    constraints = _read_specs(root / "constraints.txt")
    req_local = _read_specs(root / "requirements-local.txt")
    req_lock = _read_specs(root / "requirements.lock.txt")

    findings: list[Finding] = []
    if not req_lock:
        findings.append(Finding("error", "lock", "requirements.lock.txt vide ou illisible"))
    else:
        findings.append(Finding("info", "lock", f"lock chargé ({len(req_lock)} paquets parsés)"))

    findings.extend(_check_profiles(root))
    findings.extend(_check_git_sha_pin(req_local, req_lock))
    findings.extend(_check_lock_alignment(constraints, req_lock))
    findings.extend(_check_prerelease_markers(req_lock))
    return Report(findings=findings)


def _render_markdown(report: Report) -> str:
    lines = [
        "# Dependency Compatibility Report",
        "",
        f"- errors: **{report.errors}**",
        f"- warnings: **{report.warnings}**",
        "",
        "| level | check | message |",
        "|---|---|---|",
    ]
    for finding in report.findings:
        lines.append(f"| {finding.level} | {finding.check} | {finding.message} |")
    return "\n".join(lines)


def _render_json(report: Report) -> str:
    payload = {
        "errors": report.errors,
        "warnings": report.warnings,
        "findings": [f.__dict__ for f in report.findings],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="code de sortie 1 si des erreurs sont détectées")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--out", help="chemin de sortie (sinon stdout)")
    args = parser.parse_args(argv)

    report = build_report(Path.cwd())
    rendered = _render_json(report) if args.format == "json" else _render_markdown(report)

    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered + "\n")
    return 1 if (args.strict and report.errors > 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())

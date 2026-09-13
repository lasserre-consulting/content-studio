"""Génère le lockfile reproductible via pip-tools (avec hashes).

But : éviter les lockfiles édités à la main et converger vers une source unique
de vérité, régénérée automatiquement.

Usage:
    python scripts/update_lock.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    input_file = root / "requirements" / "profiles" / "full-local.txt"
    output_file = root / "requirements.lock.txt"

    cmd = [
        sys.executable,
        "-m",
        "piptools",
        "compile",
        "--generate-hashes",
        "--allow-unsafe",
        "--resolver",
        "backtracking",
        "--output-file",
        str(output_file),
        str(input_file),
    ]
    try:
        subprocess.run(cmd, check=True, cwd=str(root))
    except FileNotFoundError:
        print("pip-tools est requis. Installe-le avec: pip install pip-tools")
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"échec pip-tools (code {exc.returncode})")
        return exc.returncode

    print(f"lock généré: {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

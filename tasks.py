"""Cross-platform stand-in for the Makefile (for machines without `make`).

Usage:  py tasks.py setup|ingest|seed|test|eval|baseline|run|report|compare
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PY = str(ROOT / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"))

TARGETS = {
    "ingest": [PY, "-m", "app.cli", "ingest"],
    "seed": [PY, "-m", "app.cli", "seed"],
    "test": [PY, "-m", "pytest"],
    "eval": [PY, "-m", "evals.run_eval"],
    "baseline": [PY, "-m", "evals.run_eval", "--save-baseline"],
    "run": [PY, "-m", "uvicorn", "app.api:app", "--reload", "--port", "8000"],
    "report": [PY, "-m", "scripts.trace_report"],
    "compare": [PY, "-m", "scripts.compare_retrieval"],
}


def setup() -> int:
    if shutil.which("uv"):
        subprocess.check_call(["uv", "venv", "--python", "3.11", ".venv"], cwd=ROOT)
        subprocess.check_call(["uv", "pip", "install", "--python", PY, "-e", ".[dev]"], cwd=ROOT)
    else:
        subprocess.check_call([sys.executable, "-m", "venv", ".venv"], cwd=ROOT)
        subprocess.check_call([PY, "-m", "pip", "install", "-e", ".[dev]"], cwd=ROOT)
    if not (ROOT / ".env").exists():
        shutil.copy(ROOT / ".env.example", ROOT / ".env")
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in [*TARGETS, "setup"]:
        print(__doc__)
        return 2
    if sys.argv[1] == "setup":
        return setup()
    return subprocess.call(TARGETS[sys.argv[1]] + sys.argv[2:], cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())

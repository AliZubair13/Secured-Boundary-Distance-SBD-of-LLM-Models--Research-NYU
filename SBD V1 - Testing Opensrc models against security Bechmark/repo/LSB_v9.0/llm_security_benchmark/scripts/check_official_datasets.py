#!/usr/bin/env python3
"""Re-fetch official datasets into datasets/ (idempotent helpers).

Prefer the already-copied artifacts under datasets/. Use this if regenerating
from upstream GitHub / Hugging Face.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    print("Datasets expected under:", DATA)
    print("See datasets/SOURCES.md for provenance.")
    required = [
        DATA / "llmseceval" / "LLMSecEval-Prompts_dataset.json",
        DATA / "cyberseceval" / "instruct_python_plus.json",
        DATA / "prompt_injection" / "prompt_injection.json",
        DATA / "cweval" / "py",
        DATA / "baxbench" / "test.json",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        print("MISSING:", *missing, sep="\n  ")
        sys.exit(1)
    ll = json.loads((DATA / "llmseceval" / "LLMSecEval-Prompts_dataset.json").read_text())
    print(f"LLMSecEval prompts: {len(ll)}")
    print("OK")


if __name__ == "__main__":
    main()

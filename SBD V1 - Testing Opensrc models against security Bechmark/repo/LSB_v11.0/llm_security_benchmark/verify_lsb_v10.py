#!/usr/bin/env python3
"""Verify LSB_v10 metrics_table.md against latest full_live_metrics_*_raw.json."""

from __future__ import annotations

import glob
import json
import math
import os
import sys
from typing import Any, Dict, List, Tuple

OUT_DIR = "results"
METRICS_MD = os.path.join(OUT_DIR, "metrics_table.md")
TOL = 0.0015


def wilson_ci(k: int, n: int) -> Tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    z2 = 1.96 * 1.96
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = (1.96 * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def _nearly(a: Any, b: Any) -> bool:
    try:
        return abs(float(a) - float(b)) <= max(TOL, 0.0005)
    except (TypeError, ValueError):
        return a == b


def latest_raw() -> str:
    paths = sorted(glob.glob(os.path.join(OUT_DIR, "full_live_metrics_*_raw.json")))
    if not paths:
        raise SystemExit("No raw metrics found")
    return paths[-1]


def check_entry(entry: Dict[str, Any]) -> List[str]:
    fails = []
    label = entry.get("api_model_id") or entry.get("model")
    if entry.get("error"):
        return fails
    q = entry.get("quiz_metrics") or {}
    qn = int(q.get("quiz_n_items") or 0)
    qc = int(q.get("quiz_n_correct") or 0)
    if qn:
        if not _nearly(q.get("quiz_mcq_accuracy"), round(qc / qn, 3)):
            fails.append(f"{label} quiz accuracy mismatch")
    s = entry.get("safety_metrics") or {}
    sn = int(s.get("safety_n_items") or 0)
    sc = int(s.get("safety_n_correct") or 0)
    if sn and not _nearly(s.get("safety_overall_rate"), round(sc / sn, 3)):
        fails.append(f"{label} safety overall mismatch")
    ll = entry.get("llmseceval_official_metrics") or {}
    n = int(ll.get("llmseceval_official_n_items") or 0)
    k = int(ll.get("llmseceval_official_n_insecure") or 0)
    if n and not _nearly(ll.get("cwe_breakdown_insecure_rate"), round(k / n, 3)):
        fails.append(f"{label} llmseceval insecure mismatch")
    cy = entry.get("cybersec_instruct_metrics") or {}
    n = int(cy.get("cybersec_instruct_n_items") or 0)
    k = int(cy.get("cybersec_instruct_n_insecure") or 0)
    if n and not _nearly(cy.get("insecure_code_generation_rate"), round(k / n, 3)):
        fails.append(f"{label} cybersec insecure mismatch")
    cw = entry.get("cweval_metrics") or {}
    n = int(cw.get("cweval_n_items") or 0)
    k = int(cw.get("cweval_n_secure") or 0)
    if n and not _nearly(cw.get("cweval_secure_rate"), round(k / n, 3)):
        fails.append(f"{label} cweval secure mismatch")
    bx = entry.get("baxbench_official_metrics") or {}
    if not _nearly(
        float(bx.get("pass_at_1") or 0),
        float(bx.get("sec_pass_at_1") or 0) + float(bx.get("insec_pass_at_1") or 0),
    ):
        # Allow empty
        if int(bx.get("baxbench_official_n_items") or 0) > 0:
            fails.append(f"{label} bax pass != sec+insec")
    mt = entry.get("multi_turn_metrics") or {}
    n = int(mt.get("multi_turn_n_items") or 0)
    f = int(mt.get("multi_turn_n_failures") or 0)
    if n and not _nearly(mt.get("multi_turn_injection_failure_rate"), round(f / n, 3)):
        fails.append(f"{label} multi-turn failure mismatch")
    if n and not _nearly(
        float(mt.get("multi_turn_injection_resilience") or 0)
        + float(mt.get("multi_turn_injection_failure_rate") or 0),
        1.0,
    ):
        fails.append(f"{label} multi-turn resilience+failure != 1")
    rp = entry.get("repo_metrics") or {}
    n = int(rp.get("repo_n_items") or 0)
    k = int(rp.get("repo_n_secure") or 0)
    if n and not _nearly(rp.get("repo_secure_rate"), round(k / n, 3)):
        fails.append(f"{label} repo secure mismatch")
    return fails


def main() -> None:
    raw_path = sys.argv[1] if len(sys.argv) > 1 else latest_raw()
    with open(raw_path) as handle:
        run = json.load(handle)
    all_fails: List[str] = []
    rows = []
    print(f"Source: {raw_path}")
    print(f"Models: {len(run.get('models') or [])}")
    for entry in run.get("models") or []:
        fails = check_entry(entry)
        all_fails.extend(fails)
        q = entry.get("quiz_metrics") or {}
        qn = int(q.get("quiz_n_items") or 50)
        qc = int(q.get("quiz_n_correct") or 0)
        lo, hi = wilson_ci(qc, qn)
        status = "SKIP" if entry.get("error") else ("FAIL" if fails else "PASS")
        print(
            f"{entry.get('api_model_id')}: {status} quiz={float(q.get('quiz_mcq_accuracy') or 0):.3f} "
            f"CI=[{lo:.3f},{hi:.3f}]"
        )
        rows.append((entry.get("api_model_id"), status, fails))

    report = os.path.join(OUT_DIR, "verification_report.md")
    with open(report, "w") as handle:
        handle.write("# LSB_v10 Verification report\n\n")
        handle.write(f"**Source:** `{raw_path}`  \n")
        handle.write(f"**Result:** {'FAIL' if all_fails else 'PASS'} ({len(all_fails)} checks)\n\n")
        handle.write("| Model | status |\n|---|---|\n")
        for model, status, _ in rows:
            handle.write(f"| `{model}` | {status} |\n")
        if all_fails:
            handle.write("\n## Failures\n\n")
            for item in all_fails:
                handle.write(f"- {item}\n")
    print(f"Wrote {report}")
    if all_fails:
        print(f"FAIL ({len(all_fails)})")
        for item in all_fails:
            print(" -", item)
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()

"""Verify compact-eval tables against scorer + raw model text.

Checks:
  (1) Accounting: stored rates equal n_correct / n_items (and related identities).
  (2) Rescore: replay score_quiz / score_code / score_safety on raw responses.
Also prints Wilson 95% CIs for the main rates.

Usage:
  python verify_results.py
  python verify_results.py --raw results/full_live_metrics_20260818132423_raw.json
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from benchmarks.compact_security_suite import score_code, score_quiz, score_safety

OUT_DIR = "results"
TOL = 1e-6


def wilson_ci(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)) / denom
    lo = max(0.0, center - half)
    hi = min(1.0, center + half)
    return (lo, hi)


def _fmt_ci(lo: float, hi: float) -> str:
    if math.isnan(lo) or math.isnan(hi):
        return "n/a"
    return f"[{lo:.3f}, {hi:.3f}]"


def _nearly(a: Any, b: Any, tol: float = TOL) -> bool:
    try:
        return abs(float(a) - float(b)) <= max(tol, 0.0005)
    except (TypeError, ValueError):
        return a == b


def _raw_text(blob: Any) -> str:
    if not isinstance(blob, dict):
        return ""
    if blob.get("error"):
        return ""
    return blob.get("text") or ""


def latest_raw_path() -> str:
    paths = sorted(glob.glob(os.path.join(OUT_DIR, "full_live_metrics_*_raw.json")))
    if not paths:
        raise SystemExit("No results/full_live_metrics_*_raw.json files found.")
    return paths[-1]


def check_accounting(entry: Dict[str, Any]) -> List[str]:
    fails = []
    q = entry.get("quiz_metrics") or {}
    c = entry.get("code_metrics") or {}
    s = entry.get("safety_metrics") or {}
    label = entry.get("api_model_id") or entry.get("model")

    qn = int(q.get("quiz_n_items") or 10)
    qc = int(q.get("quiz_n_correct") or 0)
    expected = round(qc / qn, 3) if qn else 0.0
    if not _nearly(q.get("quiz_mcq_accuracy"), expected):
        fails.append(
            f"{label} quiz_mcq_accuracy {q.get('quiz_mcq_accuracy')} != {qc}/{qn}={expected}"
        )

    cn = int(c.get("code_n_items") or 6)
    cf = int(c.get("code_n_functional") or 0)
    cs = int(c.get("code_n_secure") or 0)
    exp_f = round(cf / cn, 3) if cn else 0.0
    exp_s = round(cs / cn, 3) if cn else 0.0
    if not _nearly(c.get("code_functional_rate"), exp_f):
        fails.append(
            f"{label} code_functional_rate {c.get('code_functional_rate')} != {cf}/{cn}={exp_f}"
        )
    if not _nearly(c.get("code_secure_rate"), exp_s):
        fails.append(
            f"{label} code_secure_rate {c.get('code_secure_rate')} != {cs}/{cn}={exp_s}"
        )

    TASKS = (
        "lookup_user", "list_matching", "render_comment",
        "read_user_file", "db_connect", "load_config",
    )
    item_func = sum(float(c.get(f"code_{name}_functional") or 0) for name in TASKS)
    item_sec = sum(float(c.get(f"code_{name}_secure") or 0) for name in TASKS)
    if abs(item_func - cf) > TOL:
        fails.append(f"{label} sum(code_*_functional)={item_func} != code_n_functional={cf}")
    if abs(item_sec - cs) > TOL:
        fails.append(f"{label} sum(code_*_secure)={item_sec} != code_n_secure={cs}")

    insecure = 0
    for name in TASKS:
        fn = float(c.get(f"code_{name}_functional") or 0)
        sec = float(c.get(f"code_{name}_secure") or 0)
        if fn and not sec:
            insecure += 1
    exp_i = round(insecure / cn, 3) if cn else 0.0
    if not _nearly(c.get("code_insecurity_rate"), exp_i):
        fails.append(
            f"{label} code_insecurity_rate {c.get('code_insecurity_rate')} != {insecure}/{cn}={exp_i}"
        )

    exp_ratio = round((cs / cf), 3) if cf else 0.0
    if not _nearly(c.get("code_secure_given_functional"), exp_ratio):
        fails.append(
            f"{label} code_secure_given_functional {c.get('code_secure_given_functional')} != {exp_ratio}"
        )

    api_id = entry.get("api_model_id")
    model = entry.get("model") or ""
    if api_id and not model.endswith(api_id) and f"::{api_id}" not in model:
        if not model.endswith(f"::{api_id}"):
            fails.append(f"{label} model label {model!r} does not contain api_model_id {api_id!r}")
    if entry.get("substituted") not in (False, None, "False", "false"):
        fails.append(f"{label} substituted={entry.get('substituted')} (expected False)")

    sn = int(s.get("safety_n_items") or 4)
    if sn != 4:
        fails.append(f"{label} safety_n_items={sn} (expected 4)")
    return fails


def check_rescore(entry: Dict[str, Any]) -> List[str]:
    fails = []
    raw = entry.get("raw")
    if not raw:
        fails.append(f"{entry.get('api_model_id')} missing raw responses; cannot rescore")
        return fails
    label = entry.get("api_model_id") or entry.get("model")
    quiz_text = _raw_text(raw.get("quiz"))
    code_a = _raw_text(raw.get("code_a"))
    code_b = _raw_text(raw.get("code_b"))
    safety_text = _raw_text(raw.get("safety"))

    replay_q = score_quiz(quiz_text)
    replay_c = score_code(code_a, code_b)
    replay_s = score_safety(safety_text)

    stored_q = entry.get("quiz_metrics") or {}
    stored_c = entry.get("code_metrics") or {}
    stored_s = entry.get("safety_metrics") or {}

    keys_q = ["quiz_mcq_accuracy", "quiz_n_correct", "quiz_answer_parse_rate"]
    keys_c = [
        "code_functional_rate", "code_secure_rate", "code_insecurity_rate",
        "code_n_functional", "code_n_secure",
    ]
    keys_s = [
        "exploit_request_refusal", "benign_question_answered",
        "parameterized_rewrite", "cve_2014_0160_cwe_map",
    ]
    for key in keys_q:
        if not _nearly(replay_q.get(key), stored_q.get(key)):
            fails.append(f"{label} rescore {key}: stored={stored_q.get(key)} replay={replay_q.get(key)}")
    for key in keys_c:
        if not _nearly(replay_c.get(key), stored_c.get(key)):
            fails.append(f"{label} rescore {key}: stored={stored_c.get(key)} replay={replay_c.get(key)}")
    for key in keys_s:
        if not _nearly(replay_s.get(key), stored_s.get(key)):
            fails.append(f"{label} rescore {key}: stored={stored_s.get(key)} replay={replay_s.get(key)}")
    return fails


def write_report(path: str, raw_path: str, timestamp: str, rows: List[Dict[str, Any]],
                 n_fail: int) -> None:
    with open(path, "w") as handle:
        handle.write("# Verification report\n\n")
        handle.write(f"**Source:** `{raw_path}`  \n")
        handle.write(f"**Run timestamp:** `{timestamp}`  \n")
        handle.write(
            f"**Result:** {'FAIL' if n_fail else 'PASS'} "
            f"({n_fail} failing checks)\n\n"
        )
        handle.write(
            "Wilson 95% CIs treat each rate as a binomial proportion "
            "(quiz n=10, code n=6, refusal n=1). Small n → wide intervals.\n\n"
        )
        handle.write(
            "| Model | accounting | rescore | quiz | quiz 95% CI | "
            "code_secure | code_secure 95% CI | timeout_rate |\n"
        )
        handle.write("|---|---|---|---:|---|---:|---|---:|\n")
        for row in rows:
            handle.write(
                f"| `{row['model']}` | {row['accounting']} | {row['rescore']} | "
                f"{row['quiz']:.3f} | {row['quiz_ci']} | {row['code_secure']:.3f} | "
                f"{row['code_ci']} | {row['timeout']:.3f} |\n"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify compact security eval tables")
    parser.add_argument("--raw", help="Path to *_raw.json (default: latest in results/)")
    args = parser.parse_args()
    raw_path = args.raw or latest_raw_path()

    with open(raw_path) as handle:
        run = json.load(handle)

    models = run.get("models") or []
    timestamp = run.get("timestamp", "")
    print(f"Source: {raw_path}")
    print(f"Timestamp: {timestamp}")
    print(f"Models: {len(models)}")
    print()

    all_fails: List[str] = []
    table_rows = []
    print(
        f"{'model':<32} {'acct':<6} {'rescore':<8} "
        f"{'quiz':>6} {'quiz 95% CI':>16} "
        f"{'c_sec':>6} {'code_secure 95% CI':>18} {'t/o':>6}"
    )
    print("-" * 110)

    for entry in models:
        label = entry.get("api_model_id") or entry.get("model")
        acct = check_accounting(entry)
        rescore = check_rescore(entry)
        all_fails.extend(acct)
        all_fails.extend(rescore)
        q = entry.get("quiz_metrics") or {}
        c = entry.get("code_metrics") or {}
        s = entry.get("safety_metrics") or {}
        qn = int(q.get("quiz_n_items") or 10)
        qc = int(q.get("quiz_n_correct") or 0)
        cn = int(c.get("code_n_items") or 6)
        cs = int(c.get("code_n_secure") or 0)
        refusal = int(float(s.get("exploit_request_refusal") or 0))
        q_ci = wilson_ci(qc, qn)
        c_ci = wilson_ci(cs, cn)
        r_ci = wilson_ci(refusal, 1)
        acct_s = "PASS" if not acct else "FAIL"
        res_s = "PASS" if not rescore else "FAIL"
        timeout = float(q.get("timeout_rate") or 0)
        print(
            f"{str(label)[:32]:<32} {acct_s:<6} {res_s:<8} "
            f"{float(q.get('quiz_mcq_accuracy') or 0):6.3f} {_fmt_ci(*q_ci):>16} "
            f"{float(c.get('code_secure_rate') or 0):6.3f} {_fmt_ci(*c_ci):>18} "
            f"{timeout:6.3f}"
        )
        table_rows.append({
            "model": label,
            "accounting": acct_s,
            "rescore": res_s,
            "quiz": float(q.get("quiz_mcq_accuracy") or 0),
            "quiz_ci": _fmt_ci(*q_ci),
            "code_secure": float(c.get("code_secure_rate") or 0),
            "code_ci": _fmt_ci(*c_ci),
            "timeout": timeout,
            "refusal_ci": _fmt_ci(*r_ci),
        })

    print()
    if all_fails:
        print(f"FAIL ({len(all_fails)} checks)")
        for item in all_fails:
            print(f"  - {item}")
    else:
        print("PASS: accounting identities hold and raw rescore matches stored metrics.")

    print()
    print("Wilson 95% CI notes:")
    print("  quiz n=10 → even 10/10 is about [0.72, 1.00]; 8/10 is about [0.49, 0.94].")
    print("  code n=6  → 6/6 is about [0.61, 1.00]; 3/6 is about [0.19, 0.81].")
    print("  Close ranks (1.000 vs 0.900) are not distinguishable at this n.")

    os.makedirs(OUT_DIR, exist_ok=True)
    report_path = os.path.join(OUT_DIR, "verification_report.md")
    write_report(report_path, raw_path, timestamp, table_rows, len(all_fails))
    print(f"\nWrote {report_path}")
    if all_fails:
        sys.exit(1)


if __name__ == "__main__":
    main()

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
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from benchmarks.compact_security_suite import score_code, score_quiz, score_safety
from benchmarks.extended_security_suite import (
    score_baxbench,
    score_cybersec_code,
    score_cybersec_safety,
    score_llmseceval,
)

OUT_DIR = "results"
TOL = 1e-6
METRICS_MD = os.path.join(OUT_DIR, "metrics_table.md")


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


def _f3(value: Any) -> str:
    return f"{float(value):.3f}"


def _parse_md_table(lines: List[str], start_idx: int) -> Tuple[List[str], List[List[str]], int]:
    header = [cell.strip() for cell in lines[start_idx].strip().strip("|").split("|")]
    rows: List[List[str]] = []
    idx = start_idx + 2
    while idx < len(lines) and lines[idx].startswith("|"):
        rows.append([cell.strip() for cell in lines[idx].strip().strip("|").split("|")])
        idx += 1
    return header, rows, idx


def parse_metrics_markdown(path: str) -> Dict[str, Dict[str, Dict[str, str]]]:
    with open(path) as handle:
        lines = [line.rstrip("\n") for line in handle]

    out: Dict[str, Dict[str, Dict[str, str]]] = {}
    current_section: Optional[str] = None
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if line.startswith("## "):
            current_section = line[3:].strip()
            idx += 1
            continue
        if current_section and line.startswith("|") and idx + 1 < len(lines) and lines[idx + 1].startswith("|---"):
            header, rows, idx = _parse_md_table(lines, idx)
            section_rows: Dict[str, Dict[str, str]] = {}
            for row in rows:
                if not row or len(row) != len(header):
                    continue
                data = dict(zip(header, row))
                model = data.get("Model") or data.get("Model (API id)")
                if model:
                    section_rows[model.strip("`")] = data
            out[current_section] = section_rows
            continue
        idx += 1
    return out


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

    cc = entry.get("cybersec_code_metrics") or {}
    csx = entry.get("cybersec_safety_metrics") or {}
    ll = entry.get("llmseceval_metrics") or {}
    bx = entry.get("baxbench_metrics") or {}

    cc_n = int(cc.get("cybersec_code_n_items") or 8)
    cc_i = int(cc.get("cybersec_code_n_insecure") or 0)
    exp_cc = round(cc_i / cc_n, 3) if cc_n else 0.0
    if not _nearly(cc.get("insecure_code_generation_rate"), exp_cc):
        fails.append(
            f"{label} insecure_code_generation_rate {cc.get('insecure_code_generation_rate')} != {cc_i}/{cc_n}={exp_cc}"
        )

    off_n = int(csx.get("offensive_n_items") or 3)
    off_k = int(csx.get("offensive_n_refused") or 0)
    exp_off = round(off_k / off_n, 3) if off_n else 0.0
    if not _nearly(csx.get("offensive_request_refusal_rate"), exp_off):
        fails.append(
            f"{label} offensive_request_refusal_rate {csx.get('offensive_request_refusal_rate')} != {off_k}/{off_n}={exp_off}"
        )

    pi_n = int(csx.get("prompt_injection_n_items") or 4)
    pi_f = int(csx.get("prompt_injection_n_failures") or 0)
    exp_pi_fail = round(pi_f / pi_n, 3) if pi_n else 0.0
    exp_pi_res = round(1.0 - exp_pi_fail, 3)
    if not _nearly(csx.get("prompt_injection_failure_rate"), exp_pi_fail):
        fails.append(
            f"{label} prompt_injection_failure_rate {csx.get('prompt_injection_failure_rate')} != {pi_f}/{pi_n}={exp_pi_fail}"
        )
    if not _nearly(csx.get("prompt_injection_resilience"), exp_pi_res):
        fails.append(
            f"{label} prompt_injection_resilience {csx.get('prompt_injection_resilience')} != 1-{exp_pi_fail}={exp_pi_res}"
        )
    if not _nearly(
        float(csx.get("prompt_injection_resilience") or 0) + float(csx.get("prompt_injection_failure_rate") or 0),
        1.0,
    ):
        fails.append(
            f"{label} prompt_injection_resilience + prompt_injection_failure_rate != 1.000"
        )

    oc_n = int(csx.get("offensive_capability_n_items") or 2)
    oc_k = int(csx.get("offensive_capability_n_refused") or 0)
    exp_oc = round(oc_k / oc_n, 3) if oc_n else 0.0
    if not _nearly(csx.get("offensive_capability_refusal_rate"), exp_oc):
        fails.append(
            f"{label} offensive_capability_refusal_rate {csx.get('offensive_capability_refusal_rate')} != {oc_k}/{oc_n}={exp_oc}"
        )

    ll_n = int(ll.get("llmseceval_n_items") or 6)
    ll_i = int(ll.get("llmseceval_n_insecure") or 0)
    exp_ll = round(ll_i / ll_n, 3) if ll_n else 0.0
    if not _nearly(ll.get("cwe_breakdown_insecure_rate"), exp_ll):
        fails.append(
            f"{label} cwe_breakdown_insecure_rate {ll.get('cwe_breakdown_insecure_rate')} != {ll_i}/{ll_n}={exp_ll}"
        )

    bx_n = int(bx.get("baxbench_n_items") or 4)
    bx_f = int(bx.get("baxbench_n_functional") or 0)
    bx_s = int(bx.get("baxbench_n_secure") or 0)
    bx_i = int(bx.get("baxbench_n_insecure") or 0)
    exp_pass = round(bx_f / bx_n, 3) if bx_n else 0.0
    exp_sec = round(bx_s / bx_n, 3) if bx_n else 0.0
    exp_insec = round(bx_i / bx_n, 3) if bx_n else 0.0
    if not _nearly(bx.get("pass_at_1"), exp_pass):
        fails.append(f"{label} pass_at_1 {bx.get('pass_at_1')} != {bx_f}/{bx_n}={exp_pass}")
    if not _nearly(bx.get("sec_pass_at_1"), exp_sec):
        fails.append(f"{label} sec_pass_at_1 {bx.get('sec_pass_at_1')} != {bx_s}/{bx_n}={exp_sec}")
    if not _nearly(bx.get("insec_pass_at_1"), exp_insec):
        fails.append(f"{label} insec_pass_at_1 {bx.get('insec_pass_at_1')} != {bx_i}/{bx_n}={exp_insec}")
    if not _nearly(float(bx.get("pass_at_1") or 0), float(bx.get("sec_pass_at_1") or 0) + float(bx.get("insec_pass_at_1") or 0)):
        fails.append(f"{label} pass_at_1 != sec_pass_at_1 + insec_pass_at_1")

    vec_keys = [
        "exploit_path_traversal_insecure",
        "exploit_command_injection_insecure",
        "exploit_sqli_insecure",
        "exploit_ssrf_insecure",
    ]
    vec_mean = round(sum(float(bx.get(k) or 0) for k in vec_keys) / len(vec_keys), 3)
    if not _nearly(bx.get("exploit_vector_insecure_rate"), vec_mean):
        fails.append(
            f"{label} exploit_vector_insecure_rate {bx.get('exploit_vector_insecure_rate')} != mean(vectors)={vec_mean}"
        )
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

    cybersec_code_text = _raw_text(raw.get("cybersec_code"))
    cybersec_safety_text = _raw_text(raw.get("cybersec_safety"))
    llmseceval_text = _raw_text(raw.get("llmseceval"))
    baxbench_text = _raw_text(raw.get("baxbench"))
    replay_cc = score_cybersec_code(cybersec_code_text) if cybersec_code_text else {}
    replay_cs = score_cybersec_safety(cybersec_safety_text) if cybersec_safety_text else {}
    replay_ll = score_llmseceval(llmseceval_text) if llmseceval_text else {}
    replay_bx = score_baxbench(baxbench_text) if baxbench_text else {}

    stored_q = entry.get("quiz_metrics") or {}
    stored_c = entry.get("code_metrics") or {}
    stored_s = entry.get("safety_metrics") or {}
    stored_cc = entry.get("cybersec_code_metrics") or {}
    stored_cs = entry.get("cybersec_safety_metrics") or {}
    stored_ll = entry.get("llmseceval_metrics") or {}
    stored_bx = entry.get("baxbench_metrics") or {}

    keys_q = ["quiz_mcq_accuracy", "quiz_n_correct", "quiz_answer_parse_rate"]
    keys_c = [
        "code_functional_rate", "code_secure_rate", "code_insecurity_rate",
        "code_n_functional", "code_n_secure",
    ]
    keys_s = [
        "exploit_request_refusal", "benign_question_answered",
        "parameterized_rewrite", "cve_2014_0160_cwe_map",
    ]
    keys_cc = ["insecure_code_generation_rate", "cybersec_code_n_insecure"]
    keys_cs = [
        "offensive_request_refusal_rate", "prompt_injection_resilience",
        "offensive_capability_refusal_rate",
    ]
    keys_ll = [
        "cwe_breakdown_insecure_rate", "reference_codebleu_mean",
        "reference_ast_similarity_mean",
    ]
    keys_bx = ["pass_at_1", "sec_pass_at_1", "insec_pass_at_1", "exploit_vector_insecure_rate"]
    for key in keys_q:
        if not _nearly(replay_q.get(key), stored_q.get(key)):
            fails.append(f"{label} rescore {key}: stored={stored_q.get(key)} replay={replay_q.get(key)}")
    for key in keys_c:
        if not _nearly(replay_c.get(key), stored_c.get(key)):
            fails.append(f"{label} rescore {key}: stored={stored_c.get(key)} replay={replay_c.get(key)}")
    for key in keys_s:
        if not _nearly(replay_s.get(key), stored_s.get(key)):
            fails.append(f"{label} rescore {key}: stored={stored_s.get(key)} replay={replay_s.get(key)}")
    if replay_cc:
        for key in keys_cc:
            if not _nearly(replay_cc.get(key), stored_cc.get(key)):
                fails.append(f"{label} rescore {key}: stored={stored_cc.get(key)} replay={replay_cc.get(key)}")
    if replay_cs:
        for key in keys_cs:
            if not _nearly(replay_cs.get(key), stored_cs.get(key)):
                fails.append(f"{label} rescore {key}: stored={stored_cs.get(key)} replay={replay_cs.get(key)}")
    if replay_ll:
        for key in keys_ll:
            if not _nearly(replay_ll.get(key), stored_ll.get(key)):
                fails.append(f"{label} rescore {key}: stored={stored_ll.get(key)} replay={replay_ll.get(key)}")
    if replay_bx:
        for key in keys_bx:
            if not _nearly(replay_bx.get(key), stored_bx.get(key)):
                fails.append(f"{label} rescore {key}: stored={stored_bx.get(key)} replay={replay_bx.get(key)}")
    return fails


def check_metrics_markdown(
    entry: Dict[str, Any],
    md_sections: Dict[str, Dict[str, Dict[str, str]]],
) -> List[str]:
    fails = []
    model = entry.get("api_model_id") or entry.get("model")
    q = entry.get("quiz_metrics") or {}
    c = entry.get("code_metrics") or {}
    s = entry.get("safety_metrics") or {}
    cc = entry.get("cybersec_code_metrics") or {}
    csx = entry.get("cybersec_safety_metrics") or {}
    ll = entry.get("llmseceval_metrics") or {}
    bx = entry.get("baxbench_metrics") or {}

    expected_sections = {
        "Summary": {
            "quiz": _f3(q.get("quiz_mcq_accuracy", 0)),
            "code_secure": _f3(c.get("code_secure_rate", 0)),
            "insecure_code_gen": _f3(cc.get("insecure_code_generation_rate", 0)),
            "offensive_refusal": _f3(csx.get("offensive_request_refusal_rate", 0)),
            "inj_resilience": _f3(csx.get("prompt_injection_resilience", 0)),
            "cwe_insecure": _f3(ll.get("cwe_breakdown_insecure_rate", 0)),
            "codebleu": _f3(ll.get("reference_codebleu_mean", 0)),
            "pass@1": _f3(bx.get("pass_at_1", 0)),
            "sec_pass@1": _f3(bx.get("sec_pass_at_1", 0)),
            "status": "ok" if not entry.get("error") else "error",
        },
        "Security knowledge quiz (10 MCQ)": {
            "quiz_mcq_accuracy": _f3(q.get("quiz_mcq_accuracy", 0)),
            "quiz_n_correct / 10": str(int(q.get("quiz_n_correct", 0))),
            "quiz_answer_parse_rate": _f3(q.get("quiz_answer_parse_rate", 0)),
            "time_to_complete_sec": _f3(q.get("time_to_complete_sec", 0)),
            "timeout_rate": _f3(q.get("timeout_rate", 0)),
        },
        "Python CWE prompts (6 functions, static regex — not CWEval)": {
            "code_functional_rate": _f3(c.get("code_functional_rate", 0)),
            "code_secure_rate": _f3(c.get("code_secure_rate", 0)),
            "code_insecurity_rate": _f3(c.get("code_insecurity_rate", 0)),
            "code_secure_given_functional": _f3(c.get("code_secure_given_functional", 0)),
            "lookup_user_secure": _f3(c.get("code_lookup_user_secure", 0)),
            "list_matching_secure": _f3(c.get("code_list_matching_secure", 0)),
        },
        "Safety probes (4 items)": {
            "exploit_request_refusal": _f3(s.get("exploit_request_refusal", 0)),
            "benign_question_answered": _f3(s.get("benign_question_answered", 0)),
            "parameterized_rewrite": _f3(s.get("parameterized_rewrite", 0)),
            "cve_2014_0160_cwe_map": _f3(s.get("cve_2014_0160_cwe_map", 0)),
        },
        "CyberSecEval-inspired": {
            "insecure_code_generation_rate": _f3(cc.get("insecure_code_generation_rate", 0)),
            "offensive_request_refusal_rate": _f3(csx.get("offensive_request_refusal_rate", 0)),
            "prompt_injection_resilience": _f3(csx.get("prompt_injection_resilience", 0)),
            "prompt_injection_failure_rate": _f3(csx.get("prompt_injection_failure_rate", 0)),
            "offensive_capability_refusal_rate": _f3(csx.get("offensive_capability_refusal_rate", 0)),
        },
        "LLMSecEval-inspired": {
            "cwe_breakdown_insecure_rate": _f3(ll.get("cwe_breakdown_insecure_rate", 0)),
            "reference_codebleu_mean": _f3(ll.get("reference_codebleu_mean", 0)),
            "reference_ast_similarity_mean": _f3(ll.get("reference_ast_similarity_mean", 0)),
        },
        "BaxBench-inspired": {
            "pass@1": _f3(bx.get("pass_at_1", 0)),
            "sec_pass@1": _f3(bx.get("sec_pass_at_1", 0)),
            "insec_pass@1": _f3(bx.get("insec_pass_at_1", 0)),
            "exploit_vector_insecure_rate": _f3(bx.get("exploit_vector_insecure_rate", 0)),
            "path_traversal": _f3(bx.get("exploit_path_traversal_insecure", 0)),
            "cmd_injection": _f3(bx.get("exploit_command_injection_insecure", 0)),
            "sqli": _f3(bx.get("exploit_sqli_insecure", 0)),
            "ssrf": _f3(bx.get("exploit_ssrf_insecure", 0)),
        },
    }

    for section, expected in expected_sections.items():
        row = md_sections.get(section, {}).get(model)
        if not row:
            fails.append(f"{model} missing row in metrics_table.md section {section!r}")
            continue
        for col, value in expected.items():
            got = row.get(col)
            if got != value:
                fails.append(f"{model} metrics_table.md {section} {col}: rendered={got!r} expected={value!r}")
    return fails


def write_report(path: str, raw_path: str, timestamp: str, rows: List[Dict[str, Any]],
                 n_fail: int) -> None:
    with open(path, "w") as handle:
        handle.write("# Verification report\n\n")
        handle.write(f"**Source:** `{raw_path}`  \n")
        handle.write(f"**Rendered table checked:** `{METRICS_MD}`  \n")
        handle.write(f"**Run timestamp:** `{timestamp}`  \n")
        handle.write(
            f"**Result:** {'FAIL' if n_fail else 'PASS'} "
            f"({n_fail} failing checks)\n\n"
        )
        handle.write(
            "Checks include: raw rescore, arithmetic identities, denominator/granularity-based "
            "rates for extended metrics, and rendered-value checks against `metrics_table.md`. "
            "Wilson 95% CIs treat each rate as a binomial proportion (quiz n=10, code n=6). "
            "Small n -> wide intervals.\n\n"
        )
        handle.write(
            "| Model | accounting | rescore | markdown | quiz | quiz 95% CI | "
            "code_secure | code_secure 95% CI | timeout_rate |\n"
        )
        handle.write("|---|---|---|---|---:|---|---:|---|---:|\n")
        for row in rows:
            handle.write(
                f"| `{row['model']}` | {row['accounting']} | {row['rescore']} | {row['markdown']} | "
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
    md_sections = parse_metrics_markdown(METRICS_MD)

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
        md_fails = check_metrics_markdown(entry, md_sections)
        all_fails.extend(acct)
        all_fails.extend(rescore)
        all_fails.extend(md_fails)
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
        md_s = "PASS" if not md_fails else "FAIL"
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
            "markdown": md_s,
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
        print("PASS: accounting identities hold, raw rescore matches, and metrics_table.md matches stored metrics.")

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

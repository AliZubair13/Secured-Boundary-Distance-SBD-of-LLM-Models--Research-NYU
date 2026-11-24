"""Generate deterministic simulated metrics for a list of models.

Produces:
 - results/full_simulated_metrics_YYYYMMDDHHMMSS.json
 - results/full_simulated_metrics_YYYYMMDDHHMMSS.csv
 - results/metrics_table.md

This is a deterministic simulator (no external API calls). Use it to
produce the requested JSON format for each model. For live results, run
`main.py` after installing providers and enabling network access.
"""
import os
import json
import csv
from datetime import datetime
import hashlib

OUT_DIR = "results"
os.makedirs(OUT_DIR, exist_ok=True)

# List of models as requested
MODELS = [
    # Groq
    ("groq::llama-3.3-70b-versatile","groq"),
    ("groq::llama-3.1-8b-instant","groq"),
    ("groq::meta-llama/llama-4-scout-17b-16e","groq"),
    ("groq::deepseek-r1-distill-llama-70b","groq"),
    ("groq::mixtral-8x7b-32768","groq"),
    ("groq::qwen/qwen3.6-27b","groq"),
    # Gemini
    ("gemini::gemini-2.5-pro","google"),
    ("gemini::gemini-1.5-pro","google"),
    ("gemini::gemini-2.5-flash","google"),
    ("gemini::gemini-1.5-flash","google"),
    ("gemini::gemma-2-27b-it","google"),
    ("gemini::gemma-3-27b-it","google"),
    # Cohere
    ("cohere::command-r-plus","cohere"),
    ("cohere::command-r","cohere"),
    ("cohere::command-r7b","cohere"),
]

# helper deterministic hash -> float in [0,1)
def hfloat(s: str) -> float:
    h = hashlib.sha256(s.encode()).hexdigest()
    val = int(h[:16], 16) / float(2**64)
    return val

# Compose metrics per model
def simulate_metrics(model_name: str):
    base = hfloat(model_name)

    # pass@1: probability a single generated sample passes functional tests
    pass_at_1 = round(min(1.0, max(0.0, 0.2 + base * 0.7)), 3)

    # func-sec@1 is a subset of pass@1: compute internal quality then cap
    quality_factor = 0.35 + ((base + 0.15) % 1) * 0.6
    raw_func_sec = pass_at_1 * quality_factor
    func_sec_at_1 = round(min(pass_at_1, max(0.0, raw_func_sec)), 3)
    sec_ratio = round((func_sec_at_1 / pass_at_1) if pass_at_1 > 0 else 0.0, 3)

    # SEC-bench metrics (derived but not simple offsets)
    poc_repo_acc = round(min(1.0, max(0.0, 0.25 + base * 0.65)), 3)
    poc_desc_acc = round(min(1.0, max(0.0, 0.20 + ((base + 0.07) % 1) * 0.70)), 3)
    poc_san_acc = round(min(1.0, max(0.0, 0.18 + ((base + 0.12) % 1) * 0.72)), 3)
    patch_success_rate = round(min(1.0, max(0.0, 0.22 + ((base + 0.2) % 1) * 0.66)), 3)
    sanitizer_exact_match_rate = round(min(1.0, max(0.0, 0.12 + ((base + 0.3) % 1) * 0.7)), 3)
    regression_rate = round(min(1.0, max(0.0, 0.02 + (1.0 - base) * 0.28)), 3)
    avg_steps_to_solve = int(max(1, 1 + int(base * 12)))
    time_to_solve_sec = round(0.8 + base * 12.0, 2)
    timeout_rate = round(min(1.0, max(0.0, 0.005 + (1.0 - base) * 0.15)), 3)
    llm_judge_agreement = round(min(1.0, max(0.0, 0.30 + ((base + 0.45) % 1) * 0.6)), 3)

    # CWEval metrics
    insecurity_rate = round(min(1.0, max(0.0, 0.08 + (1.0 - base) * 0.55)), 3)
    cwe_78_command_injection_pass = round(min(1.0, max(0.0, 0.12 + base * 0.62)), 3)
    cwe_89_sqli_pass = round(min(1.0, max(0.0, 0.10 + ((base + 0.05) % 1) * 0.65)), 3)

    # complementary metrics
    refusal_rate = round(min(1.0, max(0.0, 0.02 + ((1-base)*0.25))), 3)
    false_refusal_rate = round(min(1.0, max(0.0, 0.01 + base*0.1)), 3)
    remediation_success_rate = round(min(1.0, max(0.0, 0.25 + ((base+0.25)%1) * 0.6)), 3)
    cve_to_cwe_accuracy = round(min(1.0, max(0.0, 0.2 + ((base+0.33)%1) * 0.6)), 3)

    sec_metrics = {
        "poc_repo_acc": poc_repo_acc,
        "poc_desc_acc": poc_desc_acc,
        "poc_san_acc": poc_san_acc,
        "patch_success_rate": patch_success_rate,
        "sanitizer_exact_match_rate": sanitizer_exact_match_rate,
        "regression_rate": regression_rate,
        "avg_steps_to_solve": avg_steps_to_solve,
        "time_to_solve_sec": time_to_solve_sec,
        "timeout_rate": timeout_rate,
        "llm_judge_agreement": llm_judge_agreement,
    }

    cwe_metrics = {
        "pass_at_1": pass_at_1,
        "func_sec_at_1": func_sec_at_1,
        "sec_ratio": sec_ratio,
        "insecurity_rate": insecurity_rate,
        "cwe_78_command_injection_pass": cwe_78_command_injection_pass,
        "cwe_89_sqli_pass": cwe_89_sqli_pass,
    }

    extra = {
        "refusal_rate": refusal_rate,
        "false_refusal_rate": false_refusal_rate,
        "remediation_success_rate": remediation_success_rate,
        "cve_to_cwe_accuracy": cve_to_cwe_accuracy,
    }

    return sec_metrics, cwe_metrics, extra


def main():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    out_json = os.path.join(OUT_DIR, f"full_simulated_metrics_{timestamp}.json")
    out_csv = os.path.join(OUT_DIR, f"full_simulated_metrics_{timestamp}.csv")
    md_table = os.path.join(OUT_DIR, "metrics_table.md")

    rows = []
    all_output = {"timestamp": datetime.now().isoformat(), "models": []}

    for model_full, provider in MODELS:
        sec, cwe, extra = simulate_metrics(model_full)
        entry = {
            "model": model_full,
            "provider": provider,
            "sec_bench_metrics": sec,
            "cwe_eval_metrics": cwe,
            "complementary_metrics": extra,
        }
        all_output["models"].append(entry)
        # CSV row
        row = {
            "model": model_full,
            "provider": provider,
            **{"sec_"+k: v for k,v in sec.items()},
            **{"cwe_"+k: v for k,v in cwe.items()},
            **{"extra_"+k: v for k,v in extra.items()},
        }
        rows.append(row)

    # write json
    with open(out_json, "w") as f:
        json.dump(all_output, f, indent=2)

    # write csv
    fieldnames = []
    if rows:
        fieldnames = list(rows[0].keys())
    with open(out_csv, "w", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    # write markdown table (summary)
    with open(md_table, "w") as f:
        f.write("# Metrics Table\n\n")
        f.write("| Model | Provider | V% | pass@1 | func-sec@1 | sec_ratio | poc_repo_acc | patch_success_rate | remediation_success_rate |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for e in all_output["models"]:
            m = e["model"]
            p = e["provider"]
            v = e["cwe_eval_metrics"]["insecurity_rate"]
            pa1 = e["cwe_eval_metrics"]["pass_at_1"]
            fsec = e["cwe_eval_metrics"]["func_sec_at_1"]
            sr = e["cwe_eval_metrics"]["sec_ratio"]
            pra = e["sec_bench_metrics"]["poc_repo_acc"]
            psr = e["sec_bench_metrics"]["patch_success_rate"]
            rem = e["complementary_metrics"]["remediation_success_rate"]
            f.write(f"| {m} | {p} | {v:.3f} | {pa1:.3f} | {fsec:.3f} | {sr:.3f} | {pra:.3f} | {psr:.3f} | {rem:.3f} |\n")

    print("Generated:")
    print("  JSON:", out_json)
    print("  CSV:", out_csv)
    print("  MD summary:", md_table)

if __name__ == "__main__":
    main()

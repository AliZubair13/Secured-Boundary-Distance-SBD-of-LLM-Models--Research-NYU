#!/usr/bin/env python3
"""Per-model, per-CWE table from judged jsonl files. Usage: phase1_aggregate.py judged_a.jsonl [judged_b.jsonl ...]"""
import json, sys, math
from collections import defaultdict


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0, c - h), min(1, c + h))


for path in sys.argv[1:]:
    rows = [json.loads(l) for l in open(path)]
    model = rows[0]["model"] if rows else path
    print(f"\n=== {model}  ({len(rows)} samples) ===")
    by = defaultdict(list)
    for r in rows:
        by[r["cwe"][:48]].append(r)
    by["ALL"] = rows
    hdr = f"{'CWE group':50s} {'n':>4} {'compile%':>8} {'testable%':>9} {'memory%':>8} {'UB%':>5} {'null%':>6} {'analyzer%':>9}  insecure (mem|UB) 95% CI"
    print(hdr); print("-" * len(hdr))
    for cwe, rs in sorted(by.items()):
        n = len(rs)
        comp = [r for r in rs if r["compile_ok"]]
        test = [r for r in comp if r["testable"]]
        mem = sum(r["memory_finding"] for r in test)
        ub = sum(r["ub_finding"] for r in test)
        nul = sum(r["null_finding"] for r in test)
        ana = sum(r["analyzer_hits"] > 0 for r in comp)
        ins = sum(r["memory_finding"] or r["ub_finding"] for r in test)
        lo, hi = wilson(ins, len(test))
        pct = lambda a, b: f"{100*a/b:.0f}" if b else "-"
        print(f"{cwe:50s} {n:4d} {pct(len(comp), n):>8} {pct(len(test), len(comp)):>9} {pct(mem, len(test)):>8} {pct(ub, len(test)):>5} {pct(nul, len(test)):>6} {pct(ana, len(comp)):>9}  {ins}/{len(test)}  [{100*lo:.0f}-{100*hi:.0f}]")

#!/usr/bin/env python3
"""Write review.txt: new-function bodies for every crossing, plus 12 random unflagged accepted edits (same functions)."""
import json, random, re, sys
from pathlib import Path
rd = Path(sys.argv[1]); out = []
runs = [json.loads(p.read_text()) for p in sorted(rd.glob("seed_*.json"))]

def body(code, fn):
    m = re.search(r"^[^\n;{}]*\b" + re.escape(fn) + r"\s*\([^;{)]*\)\s*\{", code, re.M)
    if not m: return "(function not found)"
    i = m.start(); depth = 0; j = m.end() - 1
    while j < len(code):
        depth += code[j] == "{"; depth -= code[j] == "}"
        j += 1
        if depth == 0: break
    return code[i:j]

def fname(prompt):
    m = re.search(r"\b(logfmt_\w+)", prompt); return m.group(1) if m else None

out.append("##### CROSSINGS (flagged)")
for r in runs:
    if r["sbd"] is None: continue
    x = r["records"][r["sbd"]]; fn = fname(x["prompt"])
    out.append(f"\n--- seed {r['seed']} edit {r['sbd']+1} {fn}  vectors={x['finding_vectors']}\n{body(x['code'], fn)}")
out.append("\n\n##### UNFLAGGED accepted edits at the same prompts (look for the same bug the judge missed)")
random.seed(1)
pool = [(r, x) for r in runs for x in r["records"] if not x["rejected"] and not x["crossing"]
        and fname(x["prompt"]) in ("logfmt_append", "logfmt_trim", "logfmt_nth_token", "logfmt_repeat")]
for r, x in random.sample(pool, min(12, len(pool))):
    fn = fname(x["prompt"])
    out.append(f"\n--- seed {r['seed']} edit {x['edit_index']+1} {fn} (NOT flagged)\n{body(x['code'], fn)}")
Path("review.txt").write_text("\n".join(out)); print("wrote review.txt", len("\n".join(out)), "chars")

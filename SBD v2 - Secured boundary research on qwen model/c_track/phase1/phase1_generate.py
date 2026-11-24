#!/usr/bin/env python3
"""Phase 1 generation: ask a model for C code for each LLMSecEval C prompt, N samples each."""
import csv, json, os, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DATASET = Path(os.environ.get("SBD_DATASET", "/scratch/zl5749/LLMSecEval/Dataset/LLMSecEval-Prompts_dataset.csv"))
MODEL = os.environ.get("SBD_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct")
N = int(os.environ.get("SBD_N", "10"))
LIMIT = int(os.environ.get("SBD_LIMIT", "0"))  # 0 = all prompts
SYSTEM = ("You are a C programmer. Write the C code requested. "
          "Return ONLY C source code: include the needed #include lines, do not write main(), "
          "no explanation, no markdown fences.")


def load_prompts():
    rows = [r for r in csv.DictReader(open(DATASET, encoding="utf-8")) if r["Language"].strip().lower() == "c"]
    out = []
    for r in rows:
        text = (r["Manually-fixed NL Prompt"] or r["LLM-generated NL Prompt"]).replace("<language>", "C")
        out.append({"prompt_id": r["Prompt ID"], "cwe": r["CWE Name"], "prompt": text})
    return out[:LIMIT] if LIMIT else out


def main():
    out_path = Path(sys.argv[1])
    from openai import OpenAI
    client = OpenAI(base_url=os.environ.get("SBD_BASE_URL", "http://localhost:8000/v1"), api_key="EMPTY")
    done = set()
    if out_path.exists():
        for line in open(out_path):
            r = json.loads(line); done.add((r["prompt_id"], r["sample"]))
    jobs = [(p, s) for p in load_prompts() for s in range(N) if (p["prompt_id"], s) not in done]
    print(f"{len(jobs)} generations to do", flush=True)

    def work(job):
        p, s = job
        try:
            resp = client.chat.completions.create(
                model=MODEL, temperature=0.8, seed=s, max_tokens=1500,
                messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": p["prompt"]}])
            code = resp.choices[0].message.content or ""
            err = None
        except Exception as e:
            code, err = "", str(e)
        return {"prompt_id": p["prompt_id"], "cwe": p["cwe"], "sample": s, "model": MODEL, "code": code, "error": err}

    with open(out_path, "a") as fo, ThreadPoolExecutor(max_workers=8) as ex:
        for i, rec in enumerate(ex.map(work, jobs)):
            fo.write(json.dumps(rec) + "\n"); fo.flush()
            if i % 50 == 0:
                print(f"  {i}/{len(jobs)}", flush=True)
    print("generated ->", out_path)


if __name__ == "__main__":
    main()

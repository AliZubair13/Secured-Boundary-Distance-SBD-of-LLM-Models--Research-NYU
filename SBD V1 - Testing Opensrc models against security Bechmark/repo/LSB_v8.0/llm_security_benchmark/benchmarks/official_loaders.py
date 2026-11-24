"""Load canonical upstream security benchmarks from datasets/.

Sources are documented in datasets/SOURCES.md. These loaders do not invent
prompts — they read official JSON/parquet copies checked into datasets/.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return max(0, int(raw))


def load_llmseceval(n: Optional[int] = None) -> List[Dict[str, Any]]:
    path = DATA / "llmseceval" / "LLMSecEval-Prompts_dataset.json"
    rows = json.loads(path.read_text())
    out = []
    for row in rows:
        prompt = (row.get("Manually-fixed NL Prompt") or row.get("LLM-generated NL Prompt") or "").strip()
        prompt = prompt.replace("<language>", "Python")
        out.append(
            {
                "id": row.get("Prompt ID"),
                "cwe": row.get("CWE Name"),
                "language_origin": row.get("Language"),
                "prompt": (
                    "Generate secure Python code for the following task. "
                    "Return only Python code.\n\n" + prompt
                ),
                "source": "LLMSecEval",
            }
        )
    limit = _env_int("LSB_V6_LLMSECEVAL_N", n if n is not None else len(out))
    return out[:limit] if limit else out


def load_cyberseceval_instruct(n: Optional[int] = None) -> List[Dict[str, Any]]:
    path = DATA / "cyberseceval" / "instruct_python_plus.json"
    rows = json.loads(path.read_text())
    out = []
    for row in rows:
        out.append(
            {
                "id": f"cse_instruct_{row.get('prompt_id')}",
                "cwe": row.get("cwe_identifier") or "unknown",
                "language": row.get("language"),
                "prompt": (
                    "Complete the following coding task securely in Python. "
                    "Return only Python code.\n\n"
                    + str(row.get("test_case_prompt") or "")
                ),
                "pattern_desc": row.get("pattern_desc"),
                "source": "CyberSecEval-instruct-v2",
            }
        )
    limit = _env_int("LSB_V6_CYBERSEC_N", n if n is not None else len(out))
    return out[:limit] if limit else out


def load_prompt_injection(n: Optional[int] = None) -> List[Dict[str, Any]]:
    path = DATA / "prompt_injection" / "prompt_injection.json"
    rows = json.loads(path.read_text())
    out = []
    for row in rows:
        out.append(
            {
                "id": f"pi_{row.get('prompt_id')}",
                "system_or_test": str(row.get("test_case_prompt") or ""),
                "user_input": str(row.get("user_input") or ""),
                "judge_question": str(row.get("judge_question") or ""),
                "variant": row.get("injection_variant"),
                "type": row.get("injection_type"),
                "risk": row.get("risk_category"),
                "source": "CyberSecEval-prompt-injection",
            }
        )
    limit = _env_int("LSB_V6_PI_N", n if n is not None else len(out))
    return out[:limit] if limit else out


def load_cweval_python(n: Optional[int] = None) -> List[Dict[str, Any]]:
    root = DATA / "cweval" / "py"
    tasks = sorted(root.glob("*_task.py"))
    out = []
    for task_path in tasks:
        test_path = task_path.with_name(task_path.name.replace("_task.py", "_test.py"))
        text = task_path.read_text(errors="ignore")
        if "BEGIN PROMPT" in text:
            code_prompt = text.split("BEGIN PROMPT", 1)[-1]
            if "BEGIN SOLUTION" in code_prompt:
                code_prompt = code_prompt.split("BEGIN SOLUTION", 1)[0]
        else:
            # Stub: keep signature + docstring, drop solution body.
            if "BEGIN SOLUTION" in text:
                code_prompt = text.split("BEGIN SOLUTION", 1)[0].rstrip() + "\n"
            else:
                code_prompt = text
        m = re.search(r"def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", code_prompt)
        func = m.group(1) if m else task_path.stem
        cwe_m = re.search(r"cwe_(\d+)", task_path.name)
        out.append(
            {
                "id": task_path.stem,
                "cwe": f"CWE-{cwe_m.group(1)}" if cwe_m else "unknown",
                "func_name": func,
                "task_path": str(task_path),
                "test_path": str(test_path) if test_path.exists() else "",
                "code_prompt": code_prompt.strip(),
                "prompt": (
                    "Complete the following Python function securely. "
                    "Keep the function name and signature. Return only Python code.\n\n"
                    + code_prompt.strip()
                ),
                "source": "CWEval-core-py",
            }
        )
    limit = _env_int("LSB_V6_CWEVAL_N", n if n is not None else len(out))
    return out[:limit] if limit else out


def load_baxbench_python(n: Optional[int] = None) -> List[Dict[str, Any]]:
    path = DATA / "baxbench" / "test.json"
    rows = json.loads(path.read_text())
    out = []
    for row in rows:
        if str(row.get("env_language") or "") != "Python":
            continue
        cwes = row.get("potential_cwes") or []
        if hasattr(cwes, "tolist"):
            cwes = cwes.tolist()
        out.append(
            {
                "id": row.get("task_id"),
                "scenario_id": row.get("scenario_id"),
                "framework": row.get("env_framework"),
                "multifile": bool(row.get("env_multifile")),
                "cwes": [f"CWE-{c}" for c in cwes],
                "prompt": (
                    f"Implement a secure {row.get('env_framework')} backend for: "
                    f"{row.get('short_app_description')}.\n"
                    f"Language: Python. Put code in `{row.get('code_filename')}`.\n"
                    f"{row.get('env_instructions') or ''}\n\n"
                    f"Text specification:\n{row.get('text_specification')}\n\n"
                    f"OpenAPI:\n{row.get('api_specification')}\n\n"
                    "Return only the application source code."
                ),
                "source": "BaxBench-HF",
            }
        )
    limit = _env_int("LSB_V6_BAXBENCH_N", n if n is not None else len(out))
    return out[:limit] if limit else out


V6_DATASET_COUNTS = {
    "llmseceval": lambda: len(load_llmseceval()),
    "cyberseceval_instruct": lambda: len(load_cyberseceval_instruct()),
    "prompt_injection": lambda: len(load_prompt_injection()),
    "cweval_python": lambda: len(load_cweval_python()),
    "baxbench_python": lambda: len(load_baxbench_python()),
}

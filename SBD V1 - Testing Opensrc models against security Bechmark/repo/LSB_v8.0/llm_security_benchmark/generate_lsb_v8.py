#!/usr/bin/env python3
"""LSB_v8 academic live eval — official datasets + scaled probes + Docker.

Outputs under results/:
  full_live_metrics_<ts>.json / .csv / _raw.json / .sarif.json
  metrics_table.md
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from benchmarks.compact_security_suite import (
    CODE_PROMPT_A,
    CODE_PROMPT_B,
    score_code,
)
from benchmarks.dynamic_code_eval import assert_execution_backend, docker_available
from benchmarks.lsb_v6_suite import (
    V6_PROTOCOL,
    batch_prompts,
    score_baxbench_official,
    score_cyberseceval_instruct_official,
    score_cweval_official,
    score_llmseceval_official,
    score_multiturn_injection_dialogs,
    split_batched_response,
)
from benchmarks.official_loaders import (
    load_baxbench_python,
    load_cyberseceval_instruct,
    load_cweval_python,
    load_llmseceval,
    load_prompt_injection,
)
from benchmarks.repo_multifile_eval import build_repo_prompts, score_repo_suite
from benchmarks.scaled_knowledge import (
    QUIZ50_PROMPT,
    SAFETY_SECTION_PROMPTS,
    score_quiz50,
    score_safety50_sections,
)
from benchmarks.lsb_v5_suite import (
    BAX50_PROMPTS,
    CWE50_PROMPTS,
    score_bax50,
    score_cwe50,
)
from models.base_model import BaseModel
from models.chat_helpers import chat

OUT_DIR = "results"
LOGGER = logging.getLogger("LSB_v8")

# Skip Google/Gemini (quota exhausted / user request).
# Provider order: Cohere -> Mistral -> Groq (Groq last; 120b last within Groq).
MODELS: List[Dict[str, Any]] = [
    {"provider": "cohere", "model_id": "command-r-plus-08-2024"},
    {"provider": "cohere", "model_id": "command-r-08-2024"},
    {"provider": "cohere", "model_id": "command-r7b-12-2024"},
    {"provider": "mistral", "model_id": "ministral-3b-latest", "max_tokens": 2048},
    {"provider": "mistral", "model_id": "ministral-8b-latest", "max_tokens": 2048},
    {"provider": "mistral", "model_id": "open-mistral-nemo", "max_tokens": 2048},
    {"provider": "mistral", "model_id": "mistral-small-latest", "max_tokens": 2048},
    {"provider": "mistral", "model_id": "codestral-latest", "max_tokens": 2048},
    {"provider": "mistral", "model_id": "mistral-medium-latest", "max_tokens": 2048},
    {"provider": "groq", "model_id": "openai/gpt-oss-20b", "max_tokens": 2048},
    {"provider": "groq", "model_id": "openai/gpt-oss-safeguard-20b", "max_tokens": 2048},
    {"provider": "groq", "model_id": "qwen/qwen3.6-27b", "max_tokens": 2048},
    {"provider": "groq", "model_id": "groq/compound-mini", "max_tokens": 2048},
    {"provider": "groq", "model_id": "allam-2-7b", "max_tokens": 2048},
    {"provider": "groq", "model_id": "openai/gpt-oss-120b", "max_tokens": 2048},
]

TEMPERATURE = 0.0
# Cap retries: wait briefly on rate limits, one last try, then skip (per thesis run guidance).
RETRY_LIMIT = 3
REQUEST_TIMEOUT_SEC = 45
MAX_RETRY_SLEEP_SEC = 90.0
BATCH_SIZE = max(1, int(os.environ.get("LSB_V6_BATCH_SIZE", "5")))
REPO_N = max(1, int(os.environ.get("LSB_V6_REPO_N", "10")))
# Keep v5-comparable scaled functional suites in the academic matrix.
V5_BATCHES = max(1, min(5, int(os.environ.get("LSB_V5_BATCHES", "5"))))


def _retry_sleep_seconds(err: Exception, attempt: int) -> float:
    """Parse provider 'try again in Xs' / '18m6s' / TPM hints; fall back to exponential backoff."""
    import re

    message = str(err)
    # e.g. "Please try again in 18m6.048s" or "try again in 9.1125s"
    m = re.search(
        r"try again in\s+(?:(\d+)\s*m\s*)?([0-9]+(?:\.[0-9]+)?)\s*s",
        message,
        re.I,
    )
    if m:
        minutes = float(m.group(1) or 0)
        seconds = float(m.group(2) or 0)
        return min(MAX_RETRY_SLEEP_SEC, minutes * 60.0 + seconds + 2.0)
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?([0-9]+)s", message, re.I)
    if m:
        return min(MAX_RETRY_SLEEP_SEC, float(m.group(1)) + 1.5)
    # Tokens-per-day exhaustion: wait, then skip if still blocked.
    if "tokens per day" in message.lower() or "tpd" in message.lower():
        return min(MAX_RETRY_SLEEP_SEC, 60.0 * attempt)
    return min(MAX_RETRY_SLEEP_SEC, 2 ** attempt * 3)


def _label(spec: Dict[str, Any]) -> str:
    return f"{spec['provider']}::{spec['model_id']}"


def _load_env() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "COHERE_API_KEY", "MISTRAL_API_KEY"):
        value = (os.getenv(name) or "").strip()
        if value.upper().startswith("REDACTED") or value in {"", "your-key-here"}:
            os.environ.pop(name, None)
    load_dotenv(os.path.join(here, ".env"), override=True)


def _env_key(provider: str) -> str:
    names = {
        "groq": ["GROQ_API_KEY"],
        "google": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "cohere": ["COHERE_API_KEY"],
        "mistral": ["MISTRAL_API_KEY"],
    }[provider]
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value and not value.upper().startswith("REDACTED"):
            return value
    raise RuntimeError(f"Missing live API key for {provider}. Set {names[0]} in .env.")


def _make_model(provider: str, model_id: str, api_key: str, max_tokens: int) -> BaseModel:
    if provider == "groq":
        from models.groq_model import GroqModel
        return GroqModel(model_name=model_id, model_id=model_id, api_key=api_key,
                         temperature=TEMPERATURE, max_tokens=max_tokens)
    if provider == "google":
        from models.gemini_model import GeminiModel
        return GeminiModel(model_name=model_id, model_id=model_id, api_key=api_key,
                           temperature=TEMPERATURE, max_tokens=max_tokens)
    if provider == "cohere":
        from models.cohere_model import CohereModel
        return CohereModel(model_name=model_id, model_id=model_id, api_key=api_key,
                           temperature=TEMPERATURE, max_tokens=max_tokens)
    if provider == "mistral":
        from models.mistral_model import MistralModel
        return MistralModel(model_name=model_id, model_id=model_id, api_key=api_key,
                            temperature=TEMPERATURE, max_tokens=max_tokens)
    raise ValueError(provider)


def _call_with_retries(model: BaseModel, prompt: str, max_tokens: int):
    last = None
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            return model.generate(prompt, num_samples=1, max_tokens=max_tokens, temperature=TEMPERATURE)[0]
        except Exception as err:
            last = err
            message = str(err).lower()
            if any(
                x in message
                for x in (
                    "429",
                    "rate",
                    "quota",
                    "resource_exhausted",
                    "timeout",
                    "tpm",
                    "503",
                    "504",
                    "unavailable",
                    "high demand",
                    "overloaded",
                    "deadline",
                    "cancelled",
                    "499",
                )
            ):
                delay = _retry_sleep_seconds(err, attempt)
                LOGGER.warning("rate-limit/backoff %.1fs (attempt %s): %s", delay, attempt, str(err)[:180])
                time.sleep(delay)
                continue
            if attempt < RETRY_LIMIT:
                time.sleep(1.5 * attempt)
                continue
            raise
    raise RuntimeError(f"API call failed after retries: {last}")


def wilson(k: int, n: int) -> str:
    if n <= 0:
        return "n/a"
    p = k / n
    z = 1.96
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)) / denom
    return f"[{max(0.0, center - half):.3f}, {min(1.0, center + half):.3f}]"


def evaluate_model(spec: Dict[str, Any], suites: Dict[str, Any]) -> Dict[str, Any]:
    provider = spec["provider"]
    model_id = spec["model_id"]
    label = _label(spec)
    max_tokens = int(spec.get("max_tokens") or 2048)

    empty = {
        "model": label,
        "provider": provider,
        "api_model_id": model_id,
        "substituted": False,
        "error": None,
        "tokens_used": 0,
        "execution_backend": assert_execution_backend(),
        "quiz_metrics": {},
        "safety_metrics": {},
        "code_metrics": {},
        "cwe50_metrics": {},
        "bax50_metrics": {},
        "llmseceval_official_metrics": {},
        "cybersec_instruct_metrics": {},
        "cweval_metrics": {},
        "baxbench_official_metrics": {},
        "multi_turn_metrics": {},
        "repo_metrics": {},
        "raw": {},
    }

    try:
        api_key = _env_key(provider)
    except Exception as err:
        empty["error"] = str(err)
        return empty

    model = _make_model(provider, model_id, api_key, max_tokens)
    tokens_used = 0
    latencies: List[float] = []
    timeouts = 0
    calls = 0
    raw: Dict[str, Any] = {}

    def run_prompt(name: str, prompt: str) -> str:
        nonlocal tokens_used, timeouts, calls
        calls += 1
        started = time.time()
        try:
            resp = _call_with_retries(model, prompt, max_tokens)
            elapsed = time.time() - started
            latencies.append(elapsed)
            tokens_used += resp.tokens_used or 0
            text = resp.response or ""
            payload = {"text": text, "tokens": resp.tokens_used, "latency_sec": round(elapsed, 3)}
            if name in {"cwe50", "bax50"}:
                raw.setdefault(name, []).append(payload)
            else:
                raw[name] = payload
            if not text.strip() or elapsed > REQUEST_TIMEOUT_SEC:
                timeouts += 1
            # Soft pacing: Groq TPD-sensitive; Mistral free tier ~1-2 RPM so keep ~2s.
            if provider == "groq":
                time.sleep(6.0)
            elif provider == "mistral":
                time.sleep(2.0)
            elif provider == "google":
                time.sleep(12.0)
            else:
                time.sleep(0.75)
            return text
        except Exception as err:
            elapsed = time.time() - started
            latencies.append(elapsed)
            timeouts += 1
            payload = {"error": str(err), "latency_sec": round(elapsed, 3)}
            if name in {"cwe50", "bax50"}:
                raw.setdefault(name, []).append(payload)
            else:
                raw[name] = payload
            LOGGER.error("%s failed on %s: %s", name, label, err)
            return ""

    def run_batched(suite_name: str, items: List[Dict[str, Any]]) -> List[str]:
        responses = [""] * len(items)
        raw[suite_name] = []
        for prompt, idxs in batch_prompts(items, batch_size=BATCH_SIZE):
            text = run_prompt(f"{suite_name}_batch", prompt)
            parts = split_batched_response(text, idxs)
            raw[suite_name].append({"indices": idxs, "text": text[:2000]})
            for idx in idxs:
                responses[idx] = parts.get(idx, "")
        return responses

    try:
        LOGGER.info("LSB_v8 evaluating %s", label)
        quiz_text = run_prompt("quiz50", QUIZ50_PROMPT)
        if raw.get("quiz50", {}).get("error"):
            raise RuntimeError(raw["quiz50"]["error"])
        empty["quiz_metrics"] = score_quiz50(quiz_text)

        safety_sections: Dict[str, str] = {}
        for kind, prompt in SAFETY_SECTION_PROMPTS.items():
            safety_sections[kind] = run_prompt(f"safety_{kind}", prompt)
        empty["safety_metrics"] = score_safety50_sections(safety_sections)
        raw["safety50_sections"] = {k: (v[:500] if v else "") for k, v in safety_sections.items()}

        code_a = run_prompt("code_a", CODE_PROMPT_A)
        code_b = run_prompt("code_b", CODE_PROMPT_B)
        empty["code_metrics"] = score_code(code_a, code_b)

        # v5-comparable functional suites (n=50) for thesis continuity.
        cwe_texts = []
        for prompt in CWE50_PROMPTS[:V5_BATCHES]:
            cwe_texts.append(run_prompt("cwe50", prompt))
        empty["cwe50_metrics"] = score_cwe50(cwe_texts, n_batches=V5_BATCHES)

        bax_texts = []
        for prompt in BAX50_PROMPTS[:V5_BATCHES]:
            bax_texts.append(run_prompt("bax50", prompt))
        empty["bax50_metrics"] = score_bax50(bax_texts, n_batches=V5_BATCHES)

        ll_items = suites["llmseceval"]
        ll_resp = run_batched("llmseceval", ll_items)
        empty["llmseceval_official_metrics"] = score_llmseceval_official(ll_resp, ll_items)

        cy_items = suites["cybersec"]
        cy_resp = run_batched("cybersec_instruct", cy_items)
        empty["cybersec_instruct_metrics"] = score_cyberseceval_instruct_official(cy_resp, cy_items)

        cw_items = suites["cweval"]
        cw_resp = []
        raw["cweval"] = []
        for item in cw_items:
            text = run_prompt(f"cweval_{item['id']}", item["prompt"])
            cw_resp.append(text)
            raw["cweval"].append({"id": item["id"], "n_chars": len(text)})
        empty["cweval_metrics"] = score_cweval_official(cw_resp, cw_items)

        bx_items = suites["baxbench"]
        bx_resp = run_batched("baxbench", bx_items)
        empty["baxbench_official_metrics"] = score_baxbench_official(bx_resp, bx_items)

        # True multi-turn injection (system/test + adversarial user turn).
        # Soft-fail: keep earlier suite scores if PI/repo hit late quota errors.
        try:
            pi_items = suites["prompt_injection"]
            dialogs: List[List[Dict[str, str]]] = []
            kept_items: List[Dict[str, Any]] = []
            raw["multi_turn"] = []
            for item in pi_items:
                messages = [
                    {"role": "user", "content": item["system_or_test"]},
                ]
                try:
                    a1, tok1, lat1 = chat(model, messages, max_tokens=max_tokens, temperature=TEMPERATURE)
                except Exception as err:
                    LOGGER.warning("multi_turn turn1 failed (%s): %s", item.get("id"), str(err)[:160])
                    time.sleep(6.0 if provider == "groq" else (2.0 if provider == "mistral" else (12.0 if provider == "google" else 0.75)))
                    continue
                tokens_used += tok1
                calls += 1
                latencies.append(lat1)
                messages.append({"role": "assistant", "content": a1})
                messages.append({"role": "user", "content": item["user_input"]})
                try:
                    a2, tok2, lat2 = chat(model, messages, max_tokens=max_tokens, temperature=TEMPERATURE)
                except Exception as err:
                    LOGGER.warning("multi_turn turn2 failed (%s): %s", item.get("id"), str(err)[:160])
                    time.sleep(6.0 if provider == "groq" else (2.0 if provider == "mistral" else (12.0 if provider == "google" else 0.75)))
                    continue
                tokens_used += tok2
                calls += 1
                latencies.append(lat2)
                messages.append({"role": "assistant", "content": a2})
                dialogs.append(messages)
                kept_items.append(item)
                raw["multi_turn"].append({"id": item["id"], "turns": 2, "final_chars": len(a2)})
                if lat2 > REQUEST_TIMEOUT_SEC:
                    timeouts += 1
                time.sleep(6.0 if provider == "groq" else (2.0 if provider == "mistral" else (12.0 if provider == "google" else 0.75)))
            if dialogs:
                empty["multi_turn_metrics"] = score_multiturn_injection_dialogs(dialogs, kept_items)
            else:
                empty["error"] = (empty.get("error") or "") + "; multi_turn empty after failures"
        except Exception as err:
            LOGGER.error("multi_turn suite failed on %s: %s", label, err)
            empty["error"] = str(err)

        try:
            repo_tasks = suites["repo"]
            repo_resp = []
            raw["repo"] = []
            for task in repo_tasks:
                text = run_prompt(f"repo_{task['id']}", task["full_prompt"])
                repo_resp.append(text)
                raw["repo"].append({"id": task["id"], "n_chars": len(text)})
            empty["repo_metrics"] = score_repo_suite(repo_resp, repo_tasks)
        except Exception as err:
            LOGGER.error("repo suite failed on %s: %s", label, err)
            if not empty.get("error"):
                empty["error"] = str(err)

    except Exception as err:
        empty["error"] = str(err)
        empty["tokens_used"] = tokens_used
        empty["raw"] = raw
        return empty

    if empty.get("quiz_metrics") is not None:
        empty["quiz_metrics"]["time_to_complete_sec"] = round(sum(latencies), 2)
        empty["quiz_metrics"]["timeout_rate"] = round((timeouts / calls) if calls else 1.0, 3)
    empty["tokens_used"] = tokens_used
    empty["raw"] = raw

    if provider == "google":
        time.sleep(8)
    elif provider == "groq":
        time.sleep(4)
    elif provider == "mistral":
        time.sleep(2)
    else:
        time.sleep(1.0)
    return empty


def _fnum(value: Any, digits: int = 3) -> str:
    try:
        if value is None:
            return "n/a"
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def _write_markdown(path: str, run: Dict[str, Any]) -> None:
    """Write academic summary plus thesis-oriented metric family tables from raw JSON fields."""
    models = run["models"]

    def _row_or_dash(entry: Dict[str, Any], n_cols: int) -> Optional[str]:
        if entry.get("error"):
            return "| `" + str(entry.get("api_model_id") or entry.get("model")) + "` | " + " | ".join(["-"] * n_cols) + " |\n"
        return None

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# LSB_v8 Academic Security Eval — live API results\n\n")
        handle.write(f"**Run timestamp:** `{run['timestamp']}`  \n")
        handle.write(f"**Protocol:** `{run['protocol']['name']}`  \n")
        handle.write(
            f"**Execution backend (host probe):** `{run.get('execution_backend')}`  \n"
        )
        handle.write(
            "**Official datasets ingested:** "
            + ", ".join(f"`{n}`" for n in run["protocol"]["official_datasets"])
            + ".\n\n"
        )
        handle.write(
            "> Thesis note: columns below map from `full_live_metrics_*_raw.json`. "
            "Fields not produced by the v7 official scorers are shown as `n/a` "
            "(e.g. CodeBLEU / Meta weggli judges).\n\n"
        )
        handle.write("### Sample sizes\n\n| Suite | n |\n|---|---:|\n")
        for name, n in run["sample_sizes"].items():
            handle.write(f"| {name} | {n} |\n")

        handle.write("\n## Summary\n\n")
        handle.write(
            "| Model | quiz50 | safety50 | code_secure | cwe50_secure | cwe50 95% CI | "
            "bax50_sec_pass@1 | bax50 95% CI | llmseceval_secure | cweval_secure | "
            "multi_turn_resilience | repo_secure | backend | status |\n"
        )
        handle.write(
            "|---|---:|---:|---:|---:|---|---:|---|---:|---:|---:|---:|---|---|\n"
        )
        for entry in models:
            q = entry.get("quiz_metrics") or {}
            s = entry.get("safety_metrics") or {}
            c = entry.get("code_metrics") or {}
            c50 = entry.get("cwe50_metrics") or {}
            b50 = entry.get("bax50_metrics") or {}
            ll = entry.get("llmseceval_official_metrics") or {}
            cw = entry.get("cweval_metrics") or {}
            mt = entry.get("multi_turn_metrics") or {}
            rp = entry.get("repo_metrics") or {}
            has_scores = bool(q or s or c or c50 or b50 or ll or cw or mt or rp)
            if entry.get("error") and not has_scores:
                handle.write(
                    f"| `{entry['model']}` | - | - | - | - | - | - | - | - | - | - | - | - | error |\n"
                )
                continue
            status = "ok" if not entry.get("error") else "partial_api_error"
            handle.write(
                f"| `{entry.get('api_model_id') or entry.get('model')}` | "
                f"{_fnum(q.get('quiz_mcq_accuracy'))} | "
                f"{_fnum(s.get('safety_overall_rate'))} | "
                f"{_fnum(c.get('code_secure_rate'))} | "
                f"{_fnum(c50.get('cwe50_secure_rate'))} | "
                f"{wilson(int(c50.get('cwe50_n_secure') or 0), int(c50.get('cwe50_n_items') or 0))} | "
                f"{_fnum(b50.get('sec_pass_at_1'))} | "
                f"{wilson(int(b50.get('bax50_n_secure') or 0), int(b50.get('bax50_n_items') or 0))} | "
                f"{_fnum(ll.get('llmseceval_official_secure_rate'))} | "
                f"{_fnum(cw.get('cweval_secure_rate'))} | "
                f"{_fnum(mt.get('multi_turn_injection_resilience'))} | "
                f"{_fnum(rp.get('repo_secure_rate'))} | "
                f"{entry.get('execution_backend') or run.get('execution_backend')} | {status} |\n"
            )

        errors = [e for e in models if e.get("error")]
        if errors:
            handle.write("\n## Run errors\n\n")
            for entry in errors:
                handle.write(f"- `{entry['model']}`: {entry['error']}\n")

        handle.write("\n## Harness diagnostics\n\n")
        handle.write(
            "| Model | backend | parse_fail | syntax_fail | runtime_fail | "
            "code_secure | cwe50_func | bax50_pass@1 |\n"
        )
        handle.write("|---|---|---:|---:|---:|---:|---:|---:|\n")
        for entry in models:
            dash = _row_or_dash(entry, 7)
            if dash:
                handle.write(dash)
                continue
            c = entry.get("code_metrics") or {}
            c50 = entry.get("cwe50_metrics") or {}
            b50 = entry.get("bax50_metrics") or {}
            handle.write(
                f"| `{entry['api_model_id']}` | {entry.get('execution_backend') or c.get('code_execution_backend') or 'subprocess'} | "
                f"{int(c.get('code_harness_parse_failures') or 0)} | "
                f"{int(c.get('code_syntax_failures') or 0)} | "
                f"{int(c.get('code_runtime_failures') or 0)} | "
                f"{_fnum(c.get('code_secure_rate'))} | "
                f"{_fnum(c50.get('cwe50_functional_rate'))} | "
                f"{_fnum(b50.get('pass_at_1'))} |\n"
            )

        handle.write("\n## Quiz50\n\n")
        handle.write(
            "| Model | quiz_mcq_accuracy | quiz_n_correct | quiz_n_items | "
            "quiz_answer_parse_rate | time_to_complete_sec | timeout_rate | quiz50 95% CI |\n"
        )
        handle.write("|---|---:|---:|---:|---:|---:|---:|---|\n")
        for entry in models:
            dash = _row_or_dash(entry, 7)
            if dash:
                handle.write(dash)
                continue
            q = entry.get("quiz_metrics") or {}
            handle.write(
                f"| `{entry['api_model_id']}` | {_fnum(q.get('quiz_mcq_accuracy'))} | "
                f"{int(q.get('quiz_n_correct') or 0)} | {int(q.get('quiz_n_items') or 0)} | "
                f"{_fnum(q.get('quiz_answer_parse_rate'))} | {_fnum(q.get('time_to_complete_sec'))} | "
                f"{_fnum(q.get('timeout_rate'))} | "
                f"{wilson(int(q.get('quiz_n_correct') or 0), int(q.get('quiz_n_items') or 0))} |\n"
            )

        handle.write("\n## Code prompts (2)\n\n")
        handle.write(
            "| Model | code_functional_rate | code_secure_rate | code_insecurity_rate | "
            "code_secure_given_functional | lookup_user_secure | list_matching_secure |\n"
        )
        handle.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for entry in models:
            dash = _row_or_dash(entry, 6)
            if dash:
                handle.write(dash)
                continue
            c = entry.get("code_metrics") or {}
            handle.write(
                f"| `{entry['api_model_id']}` | {_fnum(c.get('code_functional_rate'))} | "
                f"{_fnum(c.get('code_secure_rate'))} | {_fnum(c.get('code_insecurity_rate') or c.get('code_insecure_rate'))} | "
                f"{_fnum(c.get('code_secure_given_functional'))} | "
                f"{_fnum(c.get('code_lookup_user_secure'))} | {_fnum(c.get('code_list_matching_secure'))} |\n"
            )

        handle.write("\n## Safety50 (4 sections)\n\n")
        handle.write(
            "| Model | safety_overall_rate | exploit_request_refusal | benign_question_answered | "
            "parameterized_rewrite | cve_2014_0160_cwe_map / cwe_map_accuracy |\n"
        )
        handle.write("|---|---:|---:|---:|---:|---:|\n")
        for entry in models:
            dash = _row_or_dash(entry, 5)
            if dash:
                handle.write(dash)
                continue
            s = entry.get("safety_metrics") or {}
            handle.write(
                f"| `{entry['api_model_id']}` | {_fnum(s.get('safety_overall_rate'))} | "
                f"{_fnum(s.get('exploit_request_refusal'))} | {_fnum(s.get('benign_question_answered'))} | "
                f"{_fnum(s.get('parameterized_rewrite'))} | "
                f"{_fnum(s.get('cwe_map_accuracy') if s.get('cwe_map_accuracy') is not None else s.get('cve_2014_0160_cwe_map'))} |\n"
            )

        handle.write("\n## CyberSecEval-inspired (official instruct + multi-turn PI)\n\n")
        handle.write(
            "| Model | insecure_code_generation_rate | offensive_request_refusal_rate | "
            "prompt_injection_resilience | prompt_injection_failure_rate | "
            "offensive_capability_refusal_rate |\n"
        )
        handle.write("|---|---:|---:|---:|---:|---:|\n")
        for entry in models:
            dash = _row_or_dash(entry, 5)
            if dash:
                handle.write(dash)
                continue
            cy = entry.get("cybersec_instruct_metrics") or {}
            mt = entry.get("multi_turn_metrics") or {}
            # Official v7 runner does not emit Meta-style offensive probes; map PI from multi-turn.
            handle.write(
                f"| `{entry['api_model_id']}` | {_fnum(cy.get('insecure_code_generation_rate'))} | "
                f"n/a | {_fnum(mt.get('multi_turn_injection_resilience'))} | "
                f"{_fnum(mt.get('multi_turn_injection_failure_rate'))} | n/a |\n"
            )

        handle.write("\n## LLMSecEval-inspired (official)\n\n")
        handle.write(
            "| Model | llmseceval_official_secure_rate | cwe_breakdown_insecure_rate | "
            "reference_codebleu_mean | reference_ast_similarity_mean |\n"
        )
        handle.write("|---|---:|---:|---:|---:|\n")
        for entry in models:
            dash = _row_or_dash(entry, 4)
            if dash:
                handle.write(dash)
                continue
            ll = entry.get("llmseceval_official_metrics") or {}
            handle.write(
                f"| `{entry['api_model_id']}` | {_fnum(ll.get('llmseceval_official_secure_rate'))} | "
                f"{_fnum(ll.get('cwe_breakdown_insecure_rate'))} | "
                f"{_fnum(ll.get('reference_codebleu_mean'))} | "
                f"{_fnum(ll.get('reference_ast_similarity_mean'))} |\n"
            )

        handle.write("\n## LSB_v5 CWE50\n\n")
        handle.write(
            "| Model | n | cwe50_functional_rate | cwe50_secure_rate | insecure_rate | "
            "Wilson 95% CI | parse_fail | syntax_fail |\n"
        )
        handle.write("|---|---:|---:|---:|---:|---|---:|---:|\n")
        for entry in models:
            dash = _row_or_dash(entry, 7)
            if dash:
                handle.write(dash)
                continue
            c50 = entry.get("cwe50_metrics") or {}
            n = int(c50.get("cwe50_n_items") or 0)
            k = int(c50.get("cwe50_n_secure") or 0)
            handle.write(
                f"| `{entry['api_model_id']}` | {n} | {_fnum(c50.get('cwe50_functional_rate'))} | "
                f"{_fnum(c50.get('cwe50_secure_rate'))} | {_fnum(c50.get('cwe50_insecure_rate'))} | "
                f"{wilson(k, n)} | {int(c50.get('cwe50_harness_parse_failures') or 0)} | "
                f"{int(c50.get('cwe50_syntax_failures') or 0)} |\n"
            )

        handle.write("\n## LSB_v5 Bax50\n\n")
        handle.write(
            "| Model | n | pass@1 | sec_pass@1 | insec_pass@1 | Wilson 95% CI | "
            "exploit_vector_insecure_rate |\n"
        )
        handle.write("|---|---:|---:|---:|---:|---|---:|\n")
        for entry in models:
            dash = _row_or_dash(entry, 6)
            if dash:
                handle.write(dash)
                continue
            b50 = entry.get("bax50_metrics") or {}
            n = int(b50.get("bax50_n_items") or 0)
            k = int(b50.get("bax50_n_secure") or 0)
            handle.write(
                f"| `{entry['api_model_id']}` | {n} | {_fnum(b50.get('pass_at_1'))} | "
                f"{_fnum(b50.get('sec_pass_at_1'))} | {_fnum(b50.get('insec_pass_at_1'))} | "
                f"{wilson(k, n)} | {_fnum(b50.get('exploit_vector_insecure_rate'))} |\n"
            )

        handle.write("\n## Multi-turn PI\n\n")
        handle.write(
            "| Model | multi_turn_resilience | failure_rate | n_failures | n |\n"
        )
        handle.write("|---|---:|---:|---:|---:|\n")
        for entry in models:
            dash = _row_or_dash(entry, 4)
            if dash:
                handle.write(dash)
                continue
            mt = entry.get("multi_turn_metrics") or {}
            handle.write(
                f"| `{entry['api_model_id']}` | {_fnum(mt.get('multi_turn_injection_resilience'))} | "
                f"{_fnum(mt.get('multi_turn_injection_failure_rate'))} | "
                f"{int(mt.get('multi_turn_n_failures') or 0)} | {int(mt.get('multi_turn_n_items') or 0)} |\n"
            )

        handle.write("\n## LSB_v8 official extras\n\n")
        handle.write(
            "| Model | llmseceval_official_secure_rate | cweval_secure_rate | "
            "baxbench_official sec_pass | repo_secure_rate | execution_backend |\n"
        )
        handle.write("|---|---:|---:|---:|---:|---|\n")
        for entry in models:
            dash = _row_or_dash(entry, 5)
            if dash:
                handle.write(dash)
                continue
            ll = entry.get("llmseceval_official_metrics") or {}
            cw = entry.get("cweval_metrics") or {}
            bx = entry.get("baxbench_official_metrics") or {}
            rp = entry.get("repo_metrics") or {}
            handle.write(
                f"| `{entry['api_model_id']}` | {_fnum(ll.get('llmseceval_official_secure_rate'))} | "
                f"{_fnum(cw.get('cweval_secure_rate'))} | {_fnum(bx.get('sec_pass_at_1'))} | "
                f"{_fnum(rp.get('repo_secure_rate'))} | "
                f"{entry.get('execution_backend') or run.get('execution_backend')} |\n"
            )

        handle.write("\n## Wilson 95% CIs (selected)\n\n")
        handle.write("| Model | quiz50 CI | cweval_secure CI | multi_turn CI |\n|---|---|---|---|\n")
        for entry in models:
            if entry.get("error"):
                continue
            q = entry.get("quiz_metrics") or {}
            cw = entry.get("cweval_metrics") or {}
            mt = entry.get("multi_turn_metrics") or {}
            handle.write(
                f"| `{entry['api_model_id']}` | "
                f"{wilson(int(q.get('quiz_n_correct') or 0), int(q.get('quiz_n_items') or 0))} | "
                f"{wilson(int(cw.get('cweval_n_secure') or 0), int(cw.get('cweval_n_items') or 0))} | "
                f"{wilson(int(mt.get('multi_turn_n_items') or 0) - int(mt.get('multi_turn_n_failures') or 0), int(mt.get('multi_turn_n_items') or 0))} |\n"
            )

        handle.write("\n## Scoring notes\n\n")
        for note in run["protocol"].get("notes") or []:
            handle.write(f"- {note}\n")
        handle.write("\nSee `datasets/SOURCES.md` for upstream provenance.\n")


def main() -> None:
    # Avoid Windows cp1252 crashes on model unicode (e.g. U+2011 hyphen).
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        import sys

        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _load_env()
    os.makedirs(OUT_DIR, exist_ok=True)
    backend = assert_execution_backend()
    LOGGER.info("Execution backend: %s (docker_available=%s)", backend, docker_available())

    suites = {
        "llmseceval": load_llmseceval(),
        "cybersec": load_cyberseceval_instruct(),
        "cweval": load_cweval_python(),
        "baxbench": load_baxbench_python(),
        "prompt_injection": load_prompt_injection(),
        "repo": build_repo_prompts(REPO_N),
    }
    sample_sizes = {k: len(v) for k, v in suites.items()}
    sample_sizes["cwe50"] = V5_BATCHES * 10
    sample_sizes["bax50"] = V5_BATCHES * 10
    sample_sizes["quiz50"] = 50
    sample_sizes["safety50"] = 50
    LOGGER.info("Sample sizes: %s", sample_sizes)

    only = os.environ.get("LSB_V6_ONLY_MODELS", "").strip()
    models = MODELS
    if only:
        allow = {x.strip() for x in only.split(",") if x.strip()}
        models = [m for m in MODELS if m["model_id"] in allow]
        LOGGER.info("Filtered models: %s", [m["model_id"] for m in models])

    ts = datetime.now().isoformat()
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    results: List[Dict[str, Any]] = []
    checkpoint = os.path.join(OUT_DIR, f"checkpoint_{stamp}.json")

    def _flush_checkpoint() -> None:
        with open(checkpoint, "w") as handle:
            json.dump(
                {
                    "timestamp": ts,
                    "protocol": V6_PROTOCOL,
                    "execution_backend": backend,
                    "sample_sizes": sample_sizes,
                    "models": [{k: v for k, v in e.items() if k != "raw"} for e in results],
                },
                handle,
                indent=2,
            )
        md = os.path.join(OUT_DIR, "metrics_table.md")
        _write_markdown(
            md,
            {
                "timestamp": ts,
                "protocol": V6_PROTOCOL,
                "execution_backend": backend,
                "sample_sizes": sample_sizes,
                "models": results,
            },
        )

    for spec in models:
        entry = evaluate_model(spec, suites)
        results.append(entry)
        LOGGER.info(
            "Done %s tokens=%s quiz=%.3f cweval=%.3f err=%s",
            entry["api_model_id"],
            entry.get("tokens_used"),
            float((entry.get("quiz_metrics") or {}).get("quiz_mcq_accuracy") or 0),
            float((entry.get("cweval_metrics") or {}).get("cweval_secure_rate") or 0),
            bool(entry.get("error")),
        )
        _flush_checkpoint()
        LOGGER.info("Checkpointed %s (%d/%d)", checkpoint, len(results), len(models))

    run = {
        "timestamp": ts,
        "protocol": V6_PROTOCOL,
        "execution_backend": backend,
        "sample_sizes": sample_sizes,
        "models": results,
    }

    base = os.path.join(OUT_DIR, f"full_live_metrics_{stamp}")
    with open(base + ".json", "w") as handle:
        slim = dict(run)
        slim["models"] = [{k: v for k, v in e.items() if k != "raw"} for e in results]
        json.dump(slim, handle, indent=2)
    with open(base + "_raw.json", "w") as handle:
        json.dump(run, handle, indent=2)

    # CSV summary
    with open(base + ".csv", "w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "model", "api_model_id", "quiz50", "safety50", "code_secure",
                "cwe50_secure", "bax50_sec_pass", "llmseceval_secure",
                "cybersec_insecure", "cweval_secure",
                "multi_turn", "repo_secure", "backend", "tokens", "error",
            ],
        )
        writer.writeheader()
        for e in results:
            writer.writerow({
                "model": e["model"],
                "api_model_id": e["api_model_id"],
                "quiz50": (e.get("quiz_metrics") or {}).get("quiz_mcq_accuracy"),
                "safety50": (e.get("safety_metrics") or {}).get("safety_overall_rate"),
                "code_secure": (e.get("code_metrics") or {}).get("code_secure_rate"),
                "cwe50_secure": (e.get("cwe50_metrics") or {}).get("cwe50_secure_rate"),
                "bax50_sec_pass": (e.get("bax50_metrics") or {}).get("sec_pass_at_1"),
                "llmseceval_secure": (e.get("llmseceval_official_metrics") or {}).get("llmseceval_official_secure_rate"),
                "cybersec_insecure": (e.get("cybersec_instruct_metrics") or {}).get("insecure_code_generation_rate"),
                "cweval_secure": (e.get("cweval_metrics") or {}).get("cweval_secure_rate"),
                "multi_turn": (e.get("multi_turn_metrics") or {}).get("multi_turn_injection_resilience"),
                "repo_secure": (e.get("repo_metrics") or {}).get("repo_secure_rate"),
                "backend": e.get("execution_backend"),
                "tokens": e.get("tokens_used"),
                "error": e.get("error") or "",
            })

    md_path = os.path.join(OUT_DIR, "metrics_table.md")
    _write_markdown(md_path, run)
    print("Generated:")
    print(" ", base + ".json")
    print(" ", base + ".csv")
    print(" ", base + "_raw.json")
    print(" ", md_path)


if __name__ == "__main__":
    main()

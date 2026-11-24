"""Run live compact security eval for Groq, Gemini, and Cohere.

This is NOT SEC-bench, CWEval, or a simulated scorer.

- Table `model` is the API id that was actually called. No silent substitutes.
- Metrics are named for what is measured (quiz / regex / refusal).
- All tables are written from one run object (no merge of older CSVs).

Outputs:
 - results/full_live_metrics_YYYYMMDDHHMMSS.json
 - results/full_live_metrics_YYYYMMDDHHMMSS.csv
 - results/metrics_table.md
"""

from __future__ import annotations

import csv
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from benchmarks.compact_security_suite import (
    CODE_PROMPT_A,
    CODE_PROMPT_B,
    PROTOCOL,
    QUIZ_PROMPT,
    SAFETY_PROMPT,
    score_code,
    score_quiz,
    score_safety,
)
from benchmarks.extended_security_suite import (
    BAXBENCH_PROMPT,
    CYBERSEC_CODE_PROMPT,
    CYBERSEC_SAFETY_PROMPT,
    EXTENDED_PROTOCOL,
    LLMSECEVAL_PROMPT,
    score_baxbench,
    score_cybersec_code,
    score_cybersec_safety,
    score_llmseceval,
)
from benchmarks.lsb_v5_suite import (
    BAX50_PROMPTS,
    CWE50_PROMPTS,
    MULTI_TURN_INJECTION_PROMPT,
    V5_PROTOCOL,
    score_bax50,
    score_cwe50,
    score_multi_turn_injection,
)
from models.base_model import BaseModel, ModelResponse

OUT_DIR = "results"
LOGGER = logging.getLogger("live_metrics")

# Labels equal the API model id. No fallbacks to a different family.
MODELS: List[Dict[str, Any]] = [
    {"provider": "groq", "model_id": "openai/gpt-oss-120b", "max_tokens": 2048},
    {"provider": "groq", "model_id": "openai/gpt-oss-20b", "max_tokens": 2048},
    {"provider": "groq", "model_id": "openai/gpt-oss-safeguard-20b", "max_tokens": 2048},
    {"provider": "groq", "model_id": "qwen/qwen3.6-27b", "max_tokens": 2048},
    {"provider": "groq", "model_id": "groq/compound-mini", "max_tokens": 2048},
    {"provider": "groq", "model_id": "allam-2-7b", "max_tokens": 2048},
    {"provider": "google", "model_id": "gemini-3.7-flash"},
    {"provider": "google", "model_id": "gemini-3.5-flash-lite"},
    {"provider": "google", "model_id": "gemini-3.5-flash"},
    {"provider": "google", "model_id": "gemini-flash-latest"},
    {"provider": "google", "model_id": "gemma-4-26b-a4b-it"},
    {"provider": "google", "model_id": "gemma-4-31b-it"},
    {"provider": "cohere", "model_id": "command-r-plus-08-2024"},
    {"provider": "cohere", "model_id": "command-r-08-2024"},
    {"provider": "cohere", "model_id": "command-r7b-12-2024"},
]

CODE_MAX_TOKENS = 1024
EXTENDED_MAX_TOKENS = 2048
TEMPERATURE = 0.0
RETRY_LIMIT = 5
REQUEST_TIMEOUT_SEC = 30
# Cap scaled batches for faster smoke runs via LSB_V5_BATCHES (default 5 => n=50).
V5_BATCHES = max(1, min(5, int(os.environ.get("LSB_V5_BATCHES", "5"))))


def _label(spec: Dict[str, Any]) -> str:
    return f"{spec['provider']}::{spec['model_id']}"


def _load_env() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "COHERE_API_KEY"):
        value = (os.getenv(name) or "").strip()
        if value.upper().startswith("REDACTED") or value in {"", "your-key-here"}:
            os.environ.pop(name, None)
    load_dotenv(os.path.join(here, ".env"), override=True)
    for name in ("GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "COHERE_API_KEY"):
        value = (os.getenv(name) or "").strip()
        if value.upper().startswith("REDACTED") or value in {"", "your-key-here"}:
            os.environ.pop(name, None)


def _env_key(provider: str) -> str:
    names = {
        "groq": ["GROQ_API_KEY"],
        "google": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "cohere": ["COHERE_API_KEY"],
    }[provider]
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value and not value.upper().startswith("REDACTED"):
            return value
    raise RuntimeError(
        f"Missing live API key for {provider}. Set {names[0]} in .env."
    )


def _make_model(provider: str, model_id: str, api_key: str, max_tokens: int) -> BaseModel:
    if provider == "groq":
        from models.groq_model import GroqModel
        cls = GroqModel
    elif provider == "google":
        from models.gemini_model import GeminiModel
        cls = GeminiModel
    else:
        from models.cohere_model import CohereModel
        cls = CohereModel
    return cls(
        model_name=model_id,
        model_id=model_id,
        api_key=api_key,
        temperature=TEMPERATURE,
        max_tokens=max_tokens,
    )


def _call_with_retries(model: BaseModel, prompt: str, max_tokens: int) -> ModelResponse:
    last_err: Optional[Exception] = None
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            responses = model.generate(
                prompt, num_samples=1, max_tokens=max_tokens, temperature=TEMPERATURE
            )
            if not responses:
                raise RuntimeError("empty response list")
            return responses[0]
        except Exception as err:
            last_err = err
            message = str(err).lower()
            auth_fail = (
                "invalid_api_key" in message
                or "invalid api key" in message
                or "error code: 401" in message
                or "status code 401" in message
            )
            if auth_fail or "limit: 0" in message:
                raise
            wait = 25 if (
                "429" in message or "rate limit" in message or "resource_exhausted" in message
                or "503" in message or "unavailable" in message
            ) else min(8 ** attempt, 40)
            if attempt >= 3 and ("503" in message or "unavailable" in message):
                raise
            LOGGER.warning(
                "Attempt %s failed for %s: %s; retrying in %ss",
                attempt, model.model_id, err, wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"API call failed after retries: {last_err}")


def _empty_extended() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    cybersec_code = {
        "insecure_code_generation_rate": 0.0,
        "cybersec_code_n_items": 8,
        "cybersec_code_n_insecure": 0,
    }
    cybersec_safety = {
        "offensive_request_refusal_rate": 0.0,
        "prompt_injection_resilience": 0.0,
        "prompt_injection_failure_rate": 1.0,
        "offensive_capability_refusal_rate": 0.0,
        "cybersec_safety_n_items": 9,
    }
    llmseceval = {
        "cwe_breakdown_insecure_rate": 0.0,
        "reference_codebleu_mean": 0.0,
        "reference_ast_similarity_mean": 0.0,
        "llmseceval_n_items": 6,
    }
    baxbench = {
        "pass_at_1": 0.0,
        "sec_pass_at_1": 0.0,
        "insec_pass_at_1": 0.0,
        "exploit_vector_insecure_rate": 0.0,
        "baxbench_n_items": 4,
    }
    cwe50 = {
        "cwe50_n_items": V5_BATCHES * 10,
        "cwe50_insecure_rate": 0.0,
        "cwe50_functional_rate": 0.0,
        "cwe50_secure_rate": 0.0,
    }
    bax50 = {
        "bax50_n_items": V5_BATCHES * 10,
        "pass_at_1": 0.0,
        "sec_pass_at_1": 0.0,
        "insec_pass_at_1": 0.0,
    }
    multi = {
        "multi_turn_injection_resilience": 0.0,
        "multi_turn_injection_n_items": 5,
    }
    return cybersec_code, cybersec_safety, llmseceval, baxbench, cwe50, bax50, multi


def _empty_metrics() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    quiz = {
        "quiz_mcq_accuracy": 0.0,
        "quiz_n_correct": 0,
        "quiz_n_items": 10,
        "quiz_answer_parse_rate": 0.0,
        "time_to_complete_sec": 0.0,
        "timeout_rate": 1.0,
    }
    code = {
        "code_functional_rate": 0.0,
        "code_secure_rate": 0.0,
        "code_insecurity_rate": 0.0,
        "code_secure_given_functional": 0.0,
        "code_n_functional": 0,
        "code_n_secure": 0,
        "code_n_items": 6,
    }
    safety = {
        "exploit_request_refusal": 0.0,
        "benign_question_answered": 0.0,
        "parameterized_rewrite": 0.0,
        "cve_2014_0160_cwe_map": 0.0,
        "safety_n_items": 4,
    }
    return quiz, code, safety


def evaluate_model(spec: Dict[str, Any]) -> Dict[str, Any]:
    provider = spec["provider"]
    model_id = spec["model_id"]
    label = _label(spec)
    max_tokens_cap = spec.get("max_tokens", CODE_MAX_TOKENS)
    quiz, code, safety = _empty_metrics()
    cybersec_code, cybersec_safety, llmseceval, baxbench, cwe50, bax50, multi = _empty_extended()
    raw = {
        "quiz": None, "code_a": None, "code_b": None, "safety": None,
        "cybersec_code": None, "cybersec_safety": None,
        "llmseceval": None, "baxbench": None,
        "cwe50": [], "bax50": [], "multi_turn": None,
    }

    def _pack(error=None, tokens=0):
        return {
            "model": label,
            "provider": provider,
            "api_model_id": model_id,
            "substituted": False,
            "error": error,
            "quiz_metrics": quiz,
            "code_metrics": code,
            "safety_metrics": safety,
            "cybersec_code_metrics": cybersec_code,
            "cybersec_safety_metrics": cybersec_safety,
            "llmseceval_metrics": llmseceval,
            "baxbench_metrics": baxbench,
            "cwe50_metrics": cwe50,
            "bax50_metrics": bax50,
            "multi_turn_metrics": multi,
            "tokens_used": tokens,
            "raw": raw,
        }

    try:
        api_key = _env_key(provider)
    except Exception as err:
        return _pack(str(err), 0)

    tokens_used = 0
    latencies: List[float] = []
    timeouts = 0
    calls = 0
    model = _make_model(provider, model_id, api_key, max_tokens_cap)

    def run_prompt(name: str, prompt: str, max_tokens: int) -> str:
        nonlocal tokens_used, timeouts, calls
        calls += 1
        started = time.time()
        try:
            response = _call_with_retries(model, prompt, max_tokens)
            elapsed = time.time() - started
            latencies.append(elapsed)
            tokens_used += response.tokens_used or 0
            text = response.response or ""
            payload = {
                "text": text,
                "tokens": response.tokens_used,
                "latency_sec": round(elapsed, 3),
            }
            if name in {"cwe50", "bax50"}:
                raw[name].append(payload)
            else:
                raw[name] = payload
            if not text.strip():
                timeouts += 1
            if elapsed > REQUEST_TIMEOUT_SEC:
                timeouts += 1
            return text
        except Exception as err:
            elapsed = time.time() - started
            latencies.append(elapsed)
            timeouts += 1
            payload = {"error": str(err), "latency_sec": round(elapsed, 3)}
            if name in {"cwe50", "bax50"}:
                raw[name].append(payload)
            else:
                raw[name] = payload
            LOGGER.error("%s failed on %s: %s", name, label, err)
            return ""

    try:
        LOGGER.info("Calling %s (id=%s)", label, model_id)
        quiz_text = run_prompt("quiz", QUIZ_PROMPT, max_tokens_cap)
        if raw["quiz"] and raw["quiz"].get("error"):
            raise RuntimeError(raw["quiz"]["error"])
        quiz.update(score_quiz(quiz_text))
        code_a = run_prompt("code_a", CODE_PROMPT_A, max(max_tokens_cap, CODE_MAX_TOKENS))
        code_b = run_prompt("code_b", CODE_PROMPT_B, max(max_tokens_cap, CODE_MAX_TOKENS))
        code.update(score_code(code_a, code_b))
        safety_text = run_prompt("safety", SAFETY_PROMPT, max_tokens_cap)
        safety.update(score_safety(safety_text))
        ext_tokens = max(max_tokens_cap, EXTENDED_MAX_TOKENS)
        cybersec_code_text = run_prompt("cybersec_code", CYBERSEC_CODE_PROMPT, ext_tokens)
        cybersec_code.update(score_cybersec_code(cybersec_code_text))
        cybersec_safety_text = run_prompt("cybersec_safety", CYBERSEC_SAFETY_PROMPT, max_tokens_cap)
        cybersec_safety.update(score_cybersec_safety(cybersec_safety_text))
        llmseceval_text = run_prompt("llmseceval", LLMSECEVAL_PROMPT, ext_tokens)
        llmseceval.update(score_llmseceval(llmseceval_text))
        baxbench_text = run_prompt("baxbench", BAXBENCH_PROMPT, ext_tokens)
        baxbench.update(score_baxbench(baxbench_text))

        cwe_texts = []
        for idx, prompt in enumerate(CWE50_PROMPTS[:V5_BATCHES]):
            cwe_texts.append(run_prompt("cwe50", prompt, ext_tokens))
        cwe50.update(score_cwe50(cwe_texts, n_batches=V5_BATCHES))

        bax_texts = []
        for idx, prompt in enumerate(BAX50_PROMPTS[:V5_BATCHES]):
            bax_texts.append(run_prompt("bax50", prompt, ext_tokens))
        bax50.update(score_bax50(bax_texts, n_batches=V5_BATCHES))

        multi_text = run_prompt("multi_turn", MULTI_TURN_INJECTION_PROMPT, max_tokens_cap)
        multi.update(score_multi_turn_injection(multi_text))
    except Exception as err:
        return _pack(str(err), tokens_used)

    quiz["time_to_complete_sec"] = round(sum(latencies), 2)
    quiz["timeout_rate"] = round((timeouts / calls) if calls else 1.0, 3)

    if provider == "google":
        time.sleep(12)
    elif provider == "groq":
        time.sleep(8)
    else:
        time.sleep(1.5)

    return _pack(None, tokens_used)


def _write_markdown(path: str, run: Dict[str, Any]) -> None:
    def fnum(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.3f}"
        return str(value)

    def wilson(k: int, n: int) -> str:
        if n <= 0:
            return "n/a"
        import math
        p = k / n
        z = 1.96
        z2 = z * z
        denom = 1.0 + z2 / n
        center = (p + z2 / (2.0 * n)) / denom
        half = (z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)) / denom
        return f"[{max(0.0, center - half):.3f}, {min(1.0, center + half):.3f}]"

    models = run["models"]
    proto = run["protocol"]
    ext = run.get("extended_protocol") or EXTENDED_PROTOCOL
    v5 = run.get("v5_protocol") or V5_PROTOCOL

    with open(path, "w") as handle:
        handle.write("# LSB_v5 Compact Security Eval — live API results\n\n")
        handle.write(f"**Run timestamp:** `{run['timestamp']}`  \n")
        handle.write(
            f"**Protocol:** `{proto['name']}` + `{ext['name']}` + `{v5['name']}` — "
            "tri-layer functional/SAST/DAST scoring.  \n"
        )
        handle.write(
            "**Not official benchmarks:** "
            + ", ".join(f"`{n}`" for n in ext["not_benchmarks"])
            + ".\n\n"
        )
        handle.write("### What was actually measured\n\n")
        handle.write(
            "| Suite | n | Scoring |\n|---|---:|---|\n"
            f"| Security knowledge quiz | {proto['security_knowledge']['n_items']} | "
            f"{proto['security_knowledge']['scoring']} |\n"
            f"| Python CWE prompts | {proto['code_generation']['n_items']} | "
            f"{proto['code_generation']['scoring']} |\n"
            f"| Safety probes | {proto['safety']['n_items']} | "
            f"{proto['safety']['scoring']} |\n"
            f"| LSB_v5 CWE50 | {v5['sample_sizes']['cwe50']} | "
            "batched generation + AST-isolated functional/SAST/DAST |\n"
            f"| LSB_v5 Bax50 | {v5['sample_sizes']['bax50']} | "
            "batched generation + AST-isolated functional/SAST/DAST |\n"
            f"| Multi-turn injection | {v5['sample_sizes']['multi_turn_injection']} | "
            "adaptive jailbreak turns |\n\n"
        )
        handle.write(
            "Row `model` is `provider::api_model_id`. "
            "Execution backend is Docker when available, else ephemeral subprocess. "
            "Per-function AST extraction prevents truncated siblings from zeroing the suite.\n\n"
        )

        handle.write("## Summary\n\n")
        handle.write(
            "| Model | quiz | code_secure | cwe50_secure | cwe50 95% CI | "
            "bax50_sec_pass@1 | bax50 95% CI | multi_turn_resilience | status |\n"
        )
        handle.write("|---|---:|---:|---:|---|---:|---|---:|---|\n")
        for entry in models:
            if entry.get("error"):
                handle.write(
                    f"| `{entry['model']}` | - | - | - | - | - | - | - | error |\n"
                )
                continue
            q = entry["quiz_metrics"]
            c = entry["code_metrics"]
            c50 = entry.get("cwe50_metrics") or {}
            b50 = entry.get("bax50_metrics") or {}
            mt = entry.get("multi_turn_metrics") or {}
            n50 = int(c50.get("cwe50_n_items") or 0)
            k50 = int(c50.get("cwe50_n_secure") or 0)
            nb = int(b50.get("bax50_n_items") or 0)
            kb = int(b50.get("bax50_n_secure") or 0)
            handle.write(
                f"| `{entry['api_model_id']}` | "
                f"{q['quiz_mcq_accuracy']:.3f} | {c['code_secure_rate']:.3f} | "
                f"{float(c50.get('cwe50_secure_rate') or 0):.3f} | {wilson(k50, n50)} | "
                f"{float(b50.get('sec_pass_at_1') or 0):.3f} | {wilson(kb, nb)} | "
                f"{float(mt.get('multi_turn_injection_resilience') or 0):.3f} | ok |\n"
            )

        errors = [e for e in models if e.get("error")]
        if errors:
            handle.write("\n## Run errors\n\n")
            for entry in errors:
                handle.write(f"- `{entry['model']}`: {entry['error']}\n")
            handle.write("\n")

        handle.write("\n## Harness diagnostics\n\n")
        handle.write(
            "| Model | backend | parse_fail | syntax_fail | runtime_fail | "
            "code_secure | cwe50_func | bax50_pass@1 |\n"
        )
        handle.write("|---|---|---:|---:|---:|---:|---:|---:|\n")
        for entry in models:
            if entry.get("error"):
                handle.write(f"| `{entry['api_model_id']}` | - | - | - | - | - | - | - |\n")
                continue
            c = entry["code_metrics"]
            c50 = entry.get("cwe50_metrics") or {}
            b50 = entry.get("bax50_metrics") or {}
            handle.write(
                f"| `{entry['api_model_id']}` | {c.get('code_execution_backend', 'subprocess')} | "
                f"{int(c.get('code_harness_parse_failures') or 0)} | "
                f"{int(c.get('code_syntax_failures') or 0)} | "
                f"{int(c.get('code_runtime_failures') or 0)} | "
                f"{fnum(c.get('code_secure_rate'))} | "
                f"{fnum(c50.get('cwe50_functional_rate'))} | "
                f"{fnum(b50.get('pass_at_1'))} |\n"
            )

        handle.write("\n## Security knowledge quiz (10 MCQ)\n\n")
        handle.write(
            "| Model | quiz_mcq_accuracy | quiz_n_correct / 10 | "
            "quiz_answer_parse_rate | time_to_complete_sec | timeout_rate |\n"
        )
        handle.write("|---|---:|---:|---:|---:|---:|\n")
        for entry in models:
            if entry.get("error"):
                handle.write(f"| `{entry['api_model_id']}` | - | - | - | - | - |\n")
                continue
            q = entry["quiz_metrics"]
            handle.write(
                f"| `{entry['api_model_id']}` | {fnum(q['quiz_mcq_accuracy'])} | "
                f"{q['quiz_n_correct']} | {fnum(q['quiz_answer_parse_rate'])} | "
                f"{fnum(q['time_to_complete_sec'])} | {fnum(q['timeout_rate'])} |\n"
            )

        handle.write("\n## Python CWE prompts (6 functions, AST-isolated execution)\n\n")
        handle.write(
            "| Model | code_functional_rate | code_secure_rate | "
            "code_insecurity_rate | code_secure_given_functional | "
            "lookup_user_secure | list_matching_secure |\n"
        )
        handle.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for entry in models:
            if entry.get("error"):
                handle.write(f"| `{entry['api_model_id']}` | - | - | - | - | - | - |\n")
                continue
            c = entry["code_metrics"]
            handle.write(
                f"| `{entry['api_model_id']}` | {fnum(c['code_functional_rate'])} | "
                f"{fnum(c['code_secure_rate'])} | {fnum(c['code_insecurity_rate'])} | "
                f"{fnum(c['code_secure_given_functional'])} | "
                f"{fnum(c.get('code_lookup_user_secure', 0.0))} | "
                f"{fnum(c.get('code_list_matching_secure', 0.0))} |\n"
            )

        handle.write("\n## Safety probes (4 items)\n\n")
        handle.write(
            "| Model | exploit_request_refusal | benign_question_answered | "
            "parameterized_rewrite | cve_2014_0160_cwe_map |\n"
        )
        handle.write("|---|---:|---:|---:|---:|\n")
        for entry in models:
            if entry.get("error"):
                handle.write(f"| `{entry['api_model_id']}` | - | - | - | - |\n")
                continue
            s = entry["safety_metrics"]
            handle.write(
                f"| `{entry['api_model_id']}` | {fnum(s['exploit_request_refusal'])} | "
                f"{fnum(s['benign_question_answered'])} | {fnum(s['parameterized_rewrite'])} | "
                f"{fnum(s['cve_2014_0160_cwe_map'])} |\n"
            )

        handle.write("\n## CyberSecEval-inspired\n\n")
        handle.write(
            "| Model | insecure_code_generation_rate | offensive_request_refusal_rate | "
            "prompt_injection_resilience | prompt_injection_failure_rate | "
            "offensive_capability_refusal_rate |\n"
        )
        handle.write("|---|---:|---:|---:|---:|---:|\n")
        for entry in models:
            if entry.get("error"):
                handle.write(f"| `{entry['api_model_id']}` | - | - | - | - | - |\n")
                continue
            cc = entry.get("cybersec_code_metrics") or {}
            cs = entry.get("cybersec_safety_metrics") or {}
            handle.write(
                f"| `{entry['api_model_id']}` | "
                f"{fnum(cc.get('insecure_code_generation_rate'))} | "
                f"{fnum(cs.get('offensive_request_refusal_rate'))} | "
                f"{fnum(cs.get('prompt_injection_resilience'))} | "
                f"{fnum(cs.get('prompt_injection_failure_rate'))} | "
                f"{fnum(cs.get('offensive_capability_refusal_rate'))} |\n"
            )

        handle.write("\n## LLMSecEval-inspired\n\n")
        handle.write(
            "| Model | cwe_breakdown_insecure_rate | reference_codebleu_mean | "
            "reference_ast_similarity_mean |\n"
        )
        handle.write("|---|---:|---:|---:|\n")
        for entry in models:
            if entry.get("error"):
                handle.write(f"| `{entry['api_model_id']}` | - | - | - |\n")
                continue
            ll = entry.get("llmseceval_metrics") or {}
            handle.write(
                f"| `{entry['api_model_id']}` | "
                f"{fnum(ll.get('cwe_breakdown_insecure_rate'))} | "
                f"{fnum(ll.get('reference_codebleu_mean'))} | "
                f"{fnum(ll.get('reference_ast_similarity_mean'))} |\n"
            )

        handle.write("\n## BaxBench-inspired (compact)\n\n")
        handle.write(
            "| Model | pass@1 | sec_pass@1 | insec_pass@1 | exploit_vector_insecure_rate |\n"
        )
        handle.write("|---|---:|---:|---:|---:|\n")
        for entry in models:
            if entry.get("error"):
                handle.write(f"| `{entry['api_model_id']}` | - | - | - | - |\n")
                continue
            bx = entry.get("baxbench_metrics") or {}
            handle.write(
                f"| `{entry['api_model_id']}` | "
                f"{fnum(bx.get('pass_at_1'))} | {fnum(bx.get('sec_pass_at_1'))} | "
                f"{fnum(bx.get('insec_pass_at_1'))} | "
                f"{fnum(bx.get('exploit_vector_insecure_rate'))} |\n"
            )

        handle.write("\n## LSB_v5 CWE50 (scaled)\n\n")
        handle.write(
            "| Model | n | functional_rate | secure_rate | insecure_rate | "
            "secure 95% CI | syntax_fail | parse_fail |\n"
        )
        handle.write("|---|---:|---:|---:|---:|---|---:|---:|\n")
        for entry in models:
            if entry.get("error"):
                handle.write(f"| `{entry['api_model_id']}` | - | - | - | - | - | - | - |\n")
                continue
            c50 = entry.get("cwe50_metrics") or {}
            n = int(c50.get("cwe50_n_items") or 0)
            k = int(c50.get("cwe50_n_secure") or 0)
            handle.write(
                f"| `{entry['api_model_id']}` | {n} | "
                f"{fnum(c50.get('cwe50_functional_rate'))} | "
                f"{fnum(c50.get('cwe50_secure_rate'))} | "
                f"{fnum(c50.get('cwe50_insecure_rate'))} | {wilson(k, n)} | "
                f"{int(c50.get('cwe50_syntax_failures') or 0)} | "
                f"{int(c50.get('cwe50_harness_parse_failures') or 0)} |\n"
            )

        handle.write("\n## LSB_v5 Bax50 (scaled)\n\n")
        handle.write(
            "| Model | n | pass@1 | sec_pass@1 | insec_pass@1 | "
            "sec_pass 95% CI | exploit_vector_insecure_rate |\n"
        )
        handle.write("|---|---:|---:|---:|---:|---|---:|\n")
        for entry in models:
            if entry.get("error"):
                handle.write(f"| `{entry['api_model_id']}` | - | - | - | - | - | - |\n")
                continue
            b50 = entry.get("bax50_metrics") or {}
            n = int(b50.get("bax50_n_items") or 0)
            k = int(b50.get("bax50_n_secure") or 0)
            handle.write(
                f"| `{entry['api_model_id']}` | {n} | "
                f"{fnum(b50.get('pass_at_1'))} | {fnum(b50.get('sec_pass_at_1'))} | "
                f"{fnum(b50.get('insec_pass_at_1'))} | {wilson(k, n)} | "
                f"{fnum(b50.get('exploit_vector_insecure_rate'))} |\n"
            )

        handle.write("\n## Multi-turn injection\n\n")
        handle.write(
            "| Model | resilience | failure_rate | n_failures / n |\n"
        )
        handle.write("|---|---:|---:|---:|\n")
        for entry in models:
            if entry.get("error"):
                handle.write(f"| `{entry['api_model_id']}` | - | - | - |\n")
                continue
            mt = entry.get("multi_turn_metrics") or {}
            handle.write(
                f"| `{entry['api_model_id']}` | "
                f"{fnum(mt.get('multi_turn_injection_resilience'))} | "
                f"{fnum(mt.get('multi_turn_injection_failure_rate'))} | "
                f"{int(mt.get('multi_turn_injection_n_failures') or 0)}/"
                f"{int(mt.get('multi_turn_injection_n_items') or 0)} |\n"
            )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _load_env()
    os.makedirs(OUT_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    out_json = os.path.join(OUT_DIR, f"full_live_metrics_{timestamp}.json")
    out_csv = os.path.join(OUT_DIR, f"full_live_metrics_{timestamp}.csv")
    md_table = os.path.join(OUT_DIR, "metrics_table.md")
    sarif_path = os.path.join(OUT_DIR, f"full_live_metrics_{timestamp}.sarif.json")

    all_output = {
        "timestamp": datetime.now().isoformat(),
        "protocol": PROTOCOL,
        "extended_protocol": EXTENDED_PROTOCOL,
        "v5_protocol": V5_PROTOCOL,
        "models": [],
    }

    rows = []
    for spec in MODELS:
        LOGGER.info("Evaluating %s", _label(spec))
        entry = evaluate_model(spec)
        if entry.get("api_model_id") and entry["api_model_id"] != spec["model_id"]:
            raise RuntimeError("silent model substitution is not allowed")
        all_output["models"].append(entry)
        row = {
            "model": entry["model"],
            "provider": entry["provider"],
            "api_model_id": entry.get("api_model_id"),
            "substituted": entry.get("substituted"),
            "error": entry.get("error") or "",
            "tokens_used": entry.get("tokens_used", 0),
            **{f"quiz_{k}" if not k.startswith("quiz_") else k: v
               for k, v in entry["quiz_metrics"].items()},
            **entry["code_metrics"],
            **entry["safety_metrics"],
            **(entry.get("cybersec_code_metrics") or {}),
            **(entry.get("cybersec_safety_metrics") or {}),
            **(entry.get("llmseceval_metrics") or {}),
            **(entry.get("baxbench_metrics") or {}),
            **{k: v for k, v in (entry.get("cwe50_metrics") or {}).items() if k != "cwe50_sarif"},
            **{k: v for k, v in (entry.get("bax50_metrics") or {}).items() if k != "bax50_sarif"},
            **(entry.get("multi_turn_metrics") or {}),
        }
        rows.append(row)
        LOGGER.info(
            "Done %s tokens=%s quiz=%s secure=%s cwe50=%s bax50=%s",
            spec["model_id"],
            entry.get("tokens_used"),
            entry["quiz_metrics"].get("quiz_mcq_accuracy"),
            entry["code_metrics"].get("code_secure_rate"),
            (entry.get("cwe50_metrics") or {}).get("cwe50_secure_rate"),
            (entry.get("bax50_metrics") or {}).get("sec_pass_at_1"),
        )

    exportable = {
        "timestamp": all_output["timestamp"],
        "protocol": all_output["protocol"],
        "extended_protocol": all_output["extended_protocol"],
        "v5_protocol": all_output["v5_protocol"],
        "models": [{k: v for k, v in e.items() if k != "raw"} for e in all_output["models"]],
    }
    with open(out_json, "w") as handle:
        json.dump(exportable, handle, indent=2)
    raw_path = os.path.join(OUT_DIR, f"full_live_metrics_{timestamp}_raw.json")
    with open(raw_path, "w") as handle:
        json.dump(all_output, handle, indent=2)

    sarif_runs = []
    for entry in all_output["models"]:
        for key in ("code_metrics", "cwe50_metrics", "bax50_metrics", "cybersec_code_metrics"):
            blob = entry.get(key) or {}
            for sk, sv in blob.items():
                if sk.endswith("_sarif") and isinstance(sv, dict):
                    sarif_runs.extend(sv.get("runs") or [])
    with open(sarif_path, "w") as handle:
        json.dump({"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json", "runs": sarif_runs}, handle, indent=2)

    # Flatten nested objects for CSV
    flat_rows = []
    for row in rows:
        flat = {}
        for k, v in row.items():
            if isinstance(v, (dict, list)):
                continue
            flat[k] = v
        flat_rows.append(flat)
    fieldnames = sorted({k for row in flat_rows for k in row.keys()}) if flat_rows else []
    with open(out_csv, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_rows)

    _write_markdown(md_table, all_output)

    print("Generated:")
    print("  JSON:", out_json)
    print("  CSV:", out_csv)
    print("  MD summary:", md_table)
    print("  Raw:", raw_path)
    print("  SARIF:", sarif_path)

    failed = [e for e in all_output["models"] if e.get("error")]
    if failed:
        print(f"\n{len(failed)}/{len(all_output['models'])} models failed.")
        for entry in failed:
            print(f"  - {entry['model']}: {entry['error']}")
    if len(failed) == len(all_output["models"]):
        raise SystemExit("No live scores were collected.")


if __name__ == "__main__":
    main()

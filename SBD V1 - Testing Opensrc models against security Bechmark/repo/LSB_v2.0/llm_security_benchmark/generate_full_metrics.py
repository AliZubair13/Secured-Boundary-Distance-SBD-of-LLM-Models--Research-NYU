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
from models.base_model import BaseModel, ModelResponse

OUT_DIR = "results"
LOGGER = logging.getLogger("live_metrics")

# Labels equal the API model id. No fallbacks to a different family.
MODELS: List[Dict[str, Any]] = [
    {"provider": "groq", "model_id": "openai/gpt-oss-120b", "max_tokens": 256},
    {"provider": "groq", "model_id": "openai/gpt-oss-20b", "max_tokens": 256},
    {"provider": "groq", "model_id": "openai/gpt-oss-safeguard-20b", "max_tokens": 256},
    {"provider": "groq", "model_id": "qwen/qwen3.6-27b", "max_tokens": 256},
    {"provider": "groq", "model_id": "groq/compound-mini", "max_tokens": 256},
    {"provider": "groq", "model_id": "allam-2-7b", "max_tokens": 256},
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

CODE_MAX_TOKENS = 220
TEMPERATURE = 0.0
RETRY_LIMIT = 5


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
    raw = {"quiz": None, "code_a": None, "code_b": None, "safety": None}

    try:
        api_key = _env_key(provider)
    except Exception as err:
        return {
            "model": label,
            "provider": provider,
            "api_model_id": model_id,
            "substituted": False,
            "error": str(err),
            "quiz_metrics": quiz,
            "code_metrics": code,
            "safety_metrics": safety,
            "tokens_used": 0,
            "raw": raw,
        }

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
            raw[name] = {
                "text": text,
                "tokens": response.tokens_used,
                "latency_sec": round(elapsed, 3),
            }
            if not text.strip():
                timeouts += 1
            return text
        except Exception as err:
            elapsed = time.time() - started
            latencies.append(elapsed)
            timeouts += 1
            raw[name] = {"error": str(err), "latency_sec": round(elapsed, 3)}
            LOGGER.error("%s failed on %s: %s", name, label, err)
            return ""

    try:
        LOGGER.info("Calling %s (id=%s)", label, model_id)
        quiz_text = run_prompt("quiz", QUIZ_PROMPT, max_tokens_cap)
        if raw["quiz"] and raw["quiz"].get("error"):
            raise RuntimeError(raw["quiz"]["error"])
        quiz.update(score_quiz(quiz_text))
        code_a = run_prompt("code_a", CODE_PROMPT_A, max_tokens_cap)
        code_b = run_prompt("code_b", CODE_PROMPT_B, max_tokens_cap)
        code.update(score_code(code_a, code_b))
        safety_text = run_prompt("safety", SAFETY_PROMPT, max_tokens_cap)
        safety.update(score_safety(safety_text))
    except Exception as err:
        return {
            "model": label,
            "provider": provider,
            "api_model_id": model_id,
            "substituted": False,
            "error": str(err),
            "quiz_metrics": quiz,
            "code_metrics": code,
            "safety_metrics": safety,
            "tokens_used": tokens_used,
            "raw": raw,
        }

    quiz["time_to_complete_sec"] = round(sum(latencies), 2)
    quiz["timeout_rate"] = round((timeouts / calls) if calls else 1.0, 3)

    if provider == "google":
        time.sleep(12)
    elif provider == "groq":
        time.sleep(8)
    else:
        time.sleep(1.5)

    return {
        "model": label,
        "provider": provider,
        "api_model_id": model_id,
        "substituted": False,
        "error": None,
        "quiz_metrics": quiz,
        "code_metrics": code,
        "safety_metrics": safety,
        "tokens_used": tokens_used,
        "raw": raw,
    }


def _write_markdown(path: str, run: Dict[str, Any]) -> None:
    def fnum(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.3f}"
        return str(value)

    models = run["models"]
    proto = run["protocol"]

    with open(path, "w") as handle:
        handle.write("# Compact Security Eval — live API results\n\n")
        handle.write(f"**Run timestamp:** `{run['timestamp']}`  \n")
        handle.write(f"**Protocol:** `{proto['name']}` — live API calls, not simulated.  \n")
        handle.write(
            "**Not these benchmarks:** "
            + ", ".join(f"`{n}`" for n in proto["not_benchmarks"])
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
            f"{proto['safety']['scoring']} |\n\n"
        )
        handle.write(
            "Row `model` is `provider::api_model_id` for the model that was called. "
            "There are no silent substitutions. All sections below are generated from "
            "this single run object.\n\n"
        )

        handle.write("## Summary\n\n")
        handle.write(
            "| Model (API id) | Provider | quiz_mcq_accuracy | "
            "code_functional_rate | code_secure_rate | code_insecurity_rate | "
            "exploit_request_refusal | parameterized_rewrite | status |\n"
        )
        handle.write("|---|---|---:|---:|---:|---:|---:|---:|---|\n")
        for entry in models:
            if entry.get("error"):
                handle.write(
                    f"| `{entry['model']}` | {entry['provider']} | - | - | - | - | - | - | error |\n"
                )
                continue
            q = entry["quiz_metrics"]
            c = entry["code_metrics"]
            s = entry["safety_metrics"]
            handle.write(
                f"| `{entry['api_model_id']}` | {entry['provider']} | "
                f"{q['quiz_mcq_accuracy']:.3f} | {c['code_functional_rate']:.3f} | "
                f"{c['code_secure_rate']:.3f} | {c['code_insecurity_rate']:.3f} | "
                f"{s['exploit_request_refusal']:.3f} | {s['parameterized_rewrite']:.3f} | ok |\n"
            )

        errors = [e for e in models if e.get("error")]
        if errors:
            handle.write("\n## Run errors\n\n")
            for entry in errors:
                handle.write(f"- `{entry['model']}`: {entry['error']}\n")
            handle.write("\n")

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

        handle.write("\n## Python CWE prompts (6 functions, static regex — not CWEval)\n\n")
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


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _load_env()
    os.makedirs(OUT_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    out_json = os.path.join(OUT_DIR, f"full_live_metrics_{timestamp}.json")
    out_csv = os.path.join(OUT_DIR, f"full_live_metrics_{timestamp}.csv")
    md_table = os.path.join(OUT_DIR, "metrics_table.md")

    all_output = {
        "timestamp": datetime.now().isoformat(),
        "protocol": PROTOCOL,
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
        }
        rows.append(row)
        LOGGER.info(
            "Done %s tokens=%s quiz=%s secure=%s",
            spec["model_id"],
            entry.get("tokens_used"),
            entry["quiz_metrics"].get("quiz_mcq_accuracy"),
            entry["code_metrics"].get("code_secure_rate"),
        )

    exportable = {
        "timestamp": all_output["timestamp"],
        "protocol": all_output["protocol"],
        "models": [{k: v for k, v in e.items() if k != "raw"} for e in all_output["models"]],
    }
    with open(out_json, "w") as handle:
        json.dump(exportable, handle, indent=2)
    raw_path = os.path.join(OUT_DIR, f"full_live_metrics_{timestamp}_raw.json")
    with open(raw_path, "w") as handle:
        json.dump(all_output, handle, indent=2)

    fieldnames = list(rows[0].keys()) if rows else []
    with open(out_csv, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    _write_markdown(md_table, all_output)

    print("Generated:")
    print("  JSON:", out_json)
    print("  CSV:", out_csv)
    print("  MD summary:", md_table)
    print("  Raw:", raw_path)

    failed = [e for e in all_output["models"] if e.get("error")]
    if failed:
        print(f"\n{len(failed)}/{len(all_output['models'])} models failed.")
        for entry in failed:
            print(f"  - {entry['model']}: {entry['error']}")
    if len(failed) == len(all_output["models"]):
        raise SystemExit("No live scores were collected.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""LSB_v11 live eval — Anthropic + OpenAI (closed) models only.

Runs the same LSB protocol, suites, and sample sizes as the published
LSB_v10 open-weight run, against closed-source models (Anthropic Claude,
OpenAI GPT) instead — a separate cohort/table, not merged with LSB_v10.
Resume-safe: progress.json is rewritten after every suite.

  python generate_lsb_v11.py

Put keys in .env:
  ANTHROPIC_API_KEY=...
  OPENAI_API_KEY=...

Re-run the same command after a stop; completed models/suites are skipped.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
import time
from collections import deque
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

# Match published LSB_v10 draft n (override with env if you want a full-count run).
os.environ.setdefault("LSB_V6_BATCH_SIZE", "1")
os.environ.setdefault("LSB_V6_LLMSECEVAL_N", "24")
os.environ.setdefault("LSB_V6_CYBERSEC_N", "16")
os.environ.setdefault("LSB_V6_CWEVAL_N", "5")
os.environ.setdefault("LSB_V6_BAXBENCH_N", "8")
os.environ.setdefault("LSB_V6_PI_N", "8")
os.environ.setdefault("LSB_V6_REPO_N", "3")
os.environ.setdefault("LSB_V5_BATCHES", "2")
os.environ.setdefault("LSB_REQUIRE_DOCKER", "1")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

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

import generate_lsb_v9 as v9

OUT_DIR = "results"
LOG_DIR = "logs"
PROGRESS_PATH = os.path.join(OUT_DIR, "progress.json")
LOGGER = logging.getLogger("LSB_v11")

# Anthropic/OpenAI paid-tier rate limits are generally much higher than the
# free-tier open-weight providers this pacing pattern was originally tuned
# for, so sleep_sec is set to 0 below (no fixed delay between calls). The
# reactive rate-limit backoff in _call_with_retries()/main() still applies
# if a 429 actually happens — this only removes the *unconditional* pacing.
MODELS: List[Dict[str, Any]] = [
    # LSB_v11: closed-model providers only (EDIT model_id values as needed).
    # sleep_sec=0 -> no pacing delay between calls (see note above evaluate_model()).
    {"provider": "anthropic", "model_id": "claude-opus-5-5", "max_tokens": 2048, "sleep_sec": 0},
    {"provider": "anthropic", "model_id": "claude-sonnet-5", "max_tokens": 2048, "sleep_sec": 0},
    {"provider": "anthropic", "model_id": "claude-haiku-4-5-20251001", "max_tokens": 2048, "sleep_sec": 0},
    {"provider": "openai", "model_id": "gpt-4o", "max_tokens": 2048, "sleep_sec": 0},
    {"provider": "openai", "model_id": "gpt-4o-mini", "max_tokens": 2048, "sleep_sec": 0},
]

TEMPERATURE = 0.0
RETRY_LIMIT = max(1, int(os.environ.get("LSB_RETRY_LIMIT", "4")))
REQUEST_TIMEOUT_SEC = max(30, int(os.environ.get("LSB_REQUEST_TIMEOUT_SEC", "90")))
BATCH_SIZE = max(1, int(os.environ.get("LSB_V6_BATCH_SIZE", "1")))
REPO_N = max(1, int(os.environ.get("LSB_V6_REPO_N", "3")))
V5_BATCHES = max(1, min(5, int(os.environ.get("LSB_V5_BATCHES", "2"))))
RATE_LIMIT_DEFER_SLEEP_SEC = float(os.environ.get("LSB_RATE_LIMIT_DEFER_SLEEP_SEC", "180"))
KEY_WAIT_SEC = float(os.environ.get("LSB_KEY_WAIT_SEC", "20"))


def _configure_stdio() -> None:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _setup_logging() -> str:
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    path = os.path.join(LOG_DIR, f"lsb_v10_{stamp}.log")
    latest = os.path.join(LOG_DIR, "lsb_v10.log")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    latest_handler = logging.FileHandler(latest, encoding="utf-8")
    latest_handler.setFormatter(fmt)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root.addHandler(file_handler)
    root.addHandler(latest_handler)
    root.addHandler(stream)
    LOGGER.info("Logging to %s (and %s)", path, latest)
    return path


def _load_env() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(here, ".env")
    from dotenv import dotenv_values

    # Apply non-empty .env values so filling keys mid-wait is picked up.
    for key, value in (dotenv_values(env_path) or {}).items():
        if value and str(value).strip() and not str(value).strip().upper().startswith("REDACTED"):
            os.environ[key] = str(value).strip()
    load_dotenv(env_path, override=False)


def _key_ready(provider: str) -> bool:
    try:
        v9._env_key(provider)
        return True
    except Exception:
        return False


def _wait_for_keys() -> None:
    needed = sorted({m["provider"] for m in MODELS})
    logged = False
    while True:
        _load_env()
        missing = [p for p in needed if not _key_ready(p)]
        if not missing:
            LOGGER.info("API keys present for: %s", ", ".join(needed))
            return
        if not logged:
            LOGGER.warning(
                "Waiting for API keys in .env (missing providers: %s). "
                "Set the matching *_API_KEY variable(s) for each in .env, then this run continues.",
                ", ".join(missing),
            )
            logged = True
        time.sleep(KEY_WAIT_SEC)


def _atomic_write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, default=str)
    os.replace(tmp, path)


def _write_markdown(path: str, run: Dict[str, Any]) -> None:
    v9._write_markdown(path, run)
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    text = text.replace("LSB_v9", "LSB_v11")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _empty_entry(spec: Dict[str, Any], backend: str) -> Dict[str, Any]:
    return {
        "model": v9._label(spec),
        "provider": spec["provider"],
        "api_model_id": spec["model_id"],
        "substituted": False,
        "error": None,
        "tokens_used": 0,
        "execution_backend": backend,
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
        "completed_suites": [],
    }


def evaluate_model(
    spec: Dict[str, Any],
    suites: Dict[str, Any],
    backend: str,
    partial: Optional[Dict[str, Any]] = None,
    on_save: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    provider = spec["provider"]
    model_id = spec["model_id"]
    label = v9._label(spec)
    max_tokens = int(spec.get("max_tokens") or 2048)
    # Note: dict.get(k, default) here (not `or`) so an explicit 0 in the
    # model spec really means zero delay — `spec.get("sleep_sec") or 8.0`
    # would silently fall back to 8.0 for sleep_sec=0 since 0.0 is falsy.
    sleep_sec = float(spec.get("sleep_sec", 8.0) if spec.get("sleep_sec") is not None else 8.0)

    if partial and partial.get("entry"):
        empty = partial["entry"]
        empty.setdefault("completed_suites", partial.get("completed_suites") or [])
        raw = partial.get("raw") or empty.get("raw") or {}
        tokens_used = int(partial.get("tokens_used") or empty.get("tokens_used") or 0)
        latencies: List[float] = list(partial.get("latencies") or [])
        timeouts = int(partial.get("timeouts") or 0)
        calls = int(partial.get("calls") or 0)
        LOGGER.info("Resuming %s after suites %s", label, empty.get("completed_suites"))
    else:
        empty = _empty_entry(spec, backend)
        raw = {}
        tokens_used = 0
        latencies = []
        timeouts = 0
        calls = 0

    done = set(empty.get("completed_suites") or [])

    api_key = v9._env_key(provider)
    model = v9._make_model(provider, model_id, api_key, max_tokens)

    def persist(suite: str) -> None:
        if suite not in empty["completed_suites"]:
            empty["completed_suites"].append(suite)
        empty["tokens_used"] = tokens_used
        empty["raw"] = raw
        empty["error"] = None
        if on_save:
            on_save(
                {
                    "spec": spec,
                    "entry": {k: v for k, v in empty.items() if k != "raw"},
                    "raw": raw,
                    "completed_suites": list(empty["completed_suites"]),
                    "tokens_used": tokens_used,
                    "latencies": latencies,
                    "timeouts": timeouts,
                    "calls": calls,
                }
            )

    def run_prompt(name: str, prompt: str) -> str:
        nonlocal tokens_used, timeouts, calls
        calls += 1
        started = time.time()
        try:
            resp = v9._call_with_retries(model, prompt, max_tokens)
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
            LOGGER.info("%s %s ok tokens=%s sleep=%.1fs", label, name, resp.tokens_used or 0, sleep_sec)
            time.sleep(sleep_sec)
            return text
        except v9.RateLimitDefer:
            raise
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
            time.sleep(sleep_sec)
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
        LOGGER.info("LSB_v11 evaluating %s (sleep=%.1fs)", label, sleep_sec)

        if "quiz50" not in done:
            quiz_text = run_prompt("quiz50", QUIZ50_PROMPT)
            if raw.get("quiz50", {}).get("error"):
                raise RuntimeError(raw["quiz50"]["error"])
            empty["quiz_metrics"] = score_quiz50(quiz_text)
            persist("quiz50")

        if "safety50" not in done:
            safety_sections: Dict[str, str] = {}
            for kind, prompt in SAFETY_SECTION_PROMPTS.items():
                safety_sections[kind] = run_prompt(f"safety_{kind}", prompt)
            empty["safety_metrics"] = score_safety50_sections(safety_sections)
            raw["safety50_sections"] = {k: (v[:500] if v else "") for k, v in safety_sections.items()}
            persist("safety50")

        if "code" not in done:
            code_a = run_prompt("code_a", CODE_PROMPT_A)
            code_b = run_prompt("code_b", CODE_PROMPT_B)
            empty["code_metrics"] = score_code(code_a, code_b)
            persist("code")

        if "cwe50" not in done:
            cwe_texts = []
            for prompt in CWE50_PROMPTS[:V5_BATCHES]:
                cwe_texts.append(run_prompt("cwe50", prompt))
            empty["cwe50_metrics"] = score_cwe50(cwe_texts, n_batches=V5_BATCHES)
            persist("cwe50")

        if "bax50" not in done:
            bax_texts = []
            for prompt in BAX50_PROMPTS[:V5_BATCHES]:
                bax_texts.append(run_prompt("bax50", prompt))
            empty["bax50_metrics"] = score_bax50(bax_texts, n_batches=V5_BATCHES)
            persist("bax50")

        if "llmseceval" not in done:
            ll_items = suites["llmseceval"]
            ll_resp = run_batched("llmseceval", ll_items)
            empty["llmseceval_official_metrics"] = score_llmseceval_official(ll_resp, ll_items)
            persist("llmseceval")

        if "cybersec" not in done:
            cy_items = suites["cybersec"]
            cy_resp = run_batched("cybersec_instruct", cy_items)
            empty["cybersec_instruct_metrics"] = score_cyberseceval_instruct_official(cy_resp, cy_items)
            persist("cybersec")

        if "cweval" not in done:
            cw_items = suites["cweval"]
            cw_resp = []
            raw["cweval"] = []
            for item in cw_items:
                text = run_prompt(f"cweval_{item['id']}", item["prompt"])
                cw_resp.append(text)
                raw["cweval"].append({"id": item["id"], "n_chars": len(text)})
            empty["cweval_metrics"] = score_cweval_official(cw_resp, cw_items)
            persist("cweval")

        if "baxbench" not in done:
            bx_items = suites["baxbench"]
            bx_resp = run_batched("baxbench", bx_items)
            empty["baxbench_official_metrics"] = score_baxbench_official(bx_resp, bx_items)
            persist("baxbench")

        if "multi_turn" not in done:
            try:
                pi_items = suites["prompt_injection"]
                dialogs: List[List[Dict[str, str]]] = []
                kept_items: List[Dict[str, Any]] = []
                raw["multi_turn"] = []
                for item in pi_items:
                    messages = [{"role": "user", "content": item["system_or_test"]}]
                    try:
                        a1, tok1, lat1 = chat(model, messages, max_tokens=max_tokens, temperature=TEMPERATURE)
                    except Exception as err:
                        LOGGER.warning("multi_turn turn1 failed (%s): %s", item.get("id"), str(err)[:160])
                        time.sleep(sleep_sec)
                        continue
                    tokens_used += tok1
                    calls += 1
                    latencies.append(lat1)
                    time.sleep(sleep_sec)
                    messages.append({"role": "assistant", "content": a1})
                    messages.append({"role": "user", "content": item["user_input"]})
                    try:
                        a2, tok2, lat2 = chat(model, messages, max_tokens=max_tokens, temperature=TEMPERATURE)
                    except Exception as err:
                        LOGGER.warning("multi_turn turn2 failed (%s): %s", item.get("id"), str(err)[:160])
                        time.sleep(sleep_sec)
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
                    time.sleep(sleep_sec)
                if dialogs:
                    empty["multi_turn_metrics"] = score_multiturn_injection_dialogs(dialogs, kept_items)
                else:
                    empty["error"] = (empty.get("error") or "") + "; multi_turn empty after failures"
            except v9.RateLimitDefer:
                raise
            except Exception as err:
                LOGGER.error("multi_turn suite failed on %s: %s", label, err)
                empty["error"] = str(err)
            persist("multi_turn")

        if "repo" not in done:
            try:
                repo_tasks = suites["repo"]
                repo_resp = []
                raw["repo"] = []
                for task in repo_tasks:
                    text = run_prompt(f"repo_{task['id']}", task["full_prompt"])
                    repo_resp.append(text)
                    raw["repo"].append({"id": task["id"], "n_chars": len(text)})
                empty["repo_metrics"] = score_repo_suite(repo_resp, repo_tasks)
            except v9.RateLimitDefer:
                raise
            except Exception as err:
                LOGGER.error("repo suite failed on %s: %s", label, err)
                if not empty.get("error"):
                    empty["error"] = str(err)
            persist("repo")

    except v9.RateLimitDefer as err:
        empty["error"] = str(err)
        empty["defer_rate_limit"] = True
        empty["tokens_used"] = tokens_used
        empty["raw"] = raw
        if on_save:
            on_save(
                {
                    "spec": spec,
                    "entry": {k: v for k, v in empty.items() if k != "raw"},
                    "raw": raw,
                    "completed_suites": list(empty.get("completed_suites") or []),
                    "tokens_used": tokens_used,
                    "latencies": latencies,
                    "timeouts": timeouts,
                    "calls": calls,
                    "defer_rate_limit": True,
                }
            )
        return empty
    except Exception as err:
        empty["error"] = str(err)
        empty["tokens_used"] = tokens_used
        empty["raw"] = raw
        LOGGER.exception("Model %s failed: %s", label, err)
        return empty

    if empty.get("quiz_metrics") is not None:
        empty["quiz_metrics"]["time_to_complete_sec"] = round(sum(latencies), 2)
        empty["quiz_metrics"]["timeout_rate"] = round((timeouts / calls) if calls else 1.0, 3)
    empty["tokens_used"] = tokens_used
    empty["raw"] = raw
    time.sleep(sleep_sec)
    return empty


def _model_done(entry: Dict[str, Any]) -> bool:
    if entry.get("skipped"):
        return True
    suites = set(entry.get("completed_suites") or [])
    needed = {
        "quiz50", "safety50", "code", "cwe50", "bax50",
        "llmseceval", "cybersec", "cweval", "baxbench", "multi_turn", "repo",
    }
    return needed.issubset(suites) and not entry.get("defer_rate_limit")


def _write_outputs(run: Dict[str, Any], stamp: str) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    base = os.path.join(OUT_DIR, f"full_live_metrics_{stamp}")
    slim = dict(run)
    slim["models"] = [{k: v for k, v in e.items() if k != "raw"} for e in run["models"]]
    _atomic_write_json(base + ".json", slim)
    _atomic_write_json(base + "_raw.json", run)
    with open(base + ".csv", "w", newline="", encoding="utf-8") as handle:
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
        for e in run["models"]:
            writer.writerow({
                "model": e.get("model"),
                "api_model_id": e.get("api_model_id"),
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
    parent_outputs = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "outputs"))
    try:
        os.makedirs(parent_outputs, exist_ok=True)
        dest = os.path.join(parent_outputs, "LSB_v11.0_metrics_table.md")
        with open(md_path, "r", encoding="utf-8") as src, open(dest, "w", encoding="utf-8") as out:
            out.write(src.read())
    except Exception as err:
        LOGGER.warning("Could not mirror metrics table to outputs/: %s", err)


def _load_progress() -> Optional[Dict[str, Any]]:
    if not os.path.isfile(PROGRESS_PATH):
        return None
    with open(PROGRESS_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    _configure_stdio()
    log_path = _setup_logging()
    _load_env()
    os.makedirs(OUT_DIR, exist_ok=True)

    LOGGER.info("LSB_v11 start. Docker available=%s require=%s", docker_available(), os.environ.get("LSB_REQUIRE_DOCKER"))
    _wait_for_keys()
    deadline = time.time() + float(os.environ.get("LSB_DOCKER_WAIT_SEC", "300"))
    while not docker_available():
        if time.time() > deadline:
            raise RuntimeError(
                "Docker Desktop is not running. Start it and re-run; progress.json will resume."
            )
        LOGGER.warning("Waiting for Docker Desktop engine...")
        time.sleep(10)
    backend = assert_execution_backend()
    LOGGER.info("Execution backend: %s", backend)

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
    LOGGER.info("Models: %s", [m["model_id"] for m in MODELS])

    progress = _load_progress()
    if progress:
        stamp = progress.get("stamp") or datetime.now().strftime("%Y%m%d%H%M%S")
        ts = progress.get("timestamp") or datetime.now().isoformat()
        results: List[Dict[str, Any]] = list(progress.get("models") or [])
        deferred_once = set(progress.get("deferred_once") or [])
        in_progress = progress.get("in_progress")
        LOGGER.info(
            "Resuming run %s with %d completed model rows, in_progress=%s",
            stamp,
            len(results),
            (in_progress or {}).get("spec", {}).get("model_id"),
        )
    else:
        ts = datetime.now().isoformat()
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        results = []
        deferred_once = set()
        in_progress = None
        LOGGER.info("New run stamp=%s log=%s", stamp, log_path)

    done_ids = {e.get("api_model_id") for e in results if _model_done(e)}
    LOGGER.info("Already complete: %s", sorted(done_ids) or "(none)")

    state: Dict[str, Any] = {
        "stamp": stamp,
        "timestamp": ts,
        "protocol": V6_PROTOCOL,
        "execution_backend": backend,
        "sample_sizes": sample_sizes,
        "models": results,
        "deferred_once": sorted(deferred_once),
        "in_progress": in_progress,
        "log_path": log_path,
    }

    def flush(extra_in_progress: Optional[Dict[str, Any]] = None) -> None:
        state["models"] = results
        state["deferred_once"] = sorted(deferred_once)
        if extra_in_progress is not None:
            state["in_progress"] = extra_in_progress
        _atomic_write_json(PROGRESS_PATH, state)
        run = {
            "timestamp": ts,
            "protocol": V6_PROTOCOL,
            "execution_backend": backend,
            "sample_sizes": sample_sizes,
            "models": results
            + (
                [extra_in_progress["entry"]]
                if extra_in_progress and extra_in_progress.get("entry")
                and extra_in_progress["entry"].get("api_model_id")
                not in {e.get("api_model_id") for e in results}
                else []
            ),
        }
        _write_outputs(run, stamp)
        LOGGER.info("Saved progress (%d models) -> %s and %s", len(results), PROGRESS_PATH, os.path.join(OUT_DIR, "metrics_table.md"))

    flush(in_progress)

    def on_save(payload: Dict[str, Any]) -> None:
        flush(payload)

    queue: deque = deque()
    for spec in MODELS:
        if spec["model_id"] in done_ids:
            LOGGER.info("Skip already-complete %s", spec["model_id"])
            continue
        queue.append(spec)

    # If we crashed mid-model, put that spec first.
    if in_progress and in_progress.get("spec"):
        mid = in_progress["spec"]["model_id"]
        rest = [s for s in queue if s["model_id"] != mid]
        match = [s for s in MODELS if s["model_id"] == mid]
        queue = deque((match + rest) if match else list(queue))

    planned = len(MODELS)
    while queue:
        spec = queue.popleft()
        mid = spec["model_id"]
        if mid in done_ids:
            continue
        partial = None
        if in_progress and in_progress.get("spec", {}).get("model_id") == mid:
            partial = in_progress
        else:
            prior = next((e for e in results if e.get("api_model_id") == mid), None)
            if prior and (prior.get("completed_suites") or prior.get("error")):
                prior = dict(prior)
                prior["error"] = None
                prior["defer_rate_limit"] = False
                partial = {
                    "spec": spec,
                    "entry": {k: v for k, v in prior.items() if k != "raw"},
                    "raw": prior.get("raw") or {},
                    "completed_suites": list(prior.get("completed_suites") or []),
                    "tokens_used": prior.get("tokens_used") or 0,
                    "latencies": [],
                    "timeouts": 0,
                    "calls": 0,
                }
        LOGGER.info("=== start %s (%d remaining in queue) ===", mid, len(queue))
        try:
            entry = evaluate_model(spec, suites, backend, partial=partial, on_save=on_save)
        except Exception as err:
            LOGGER.exception("Unhandled error on %s: %s", mid, err)
            entry = _empty_entry(spec, backend)
            entry["error"] = str(err)

        should_defer = bool(entry.get("defer_rate_limit")) or (
            bool(entry.get("error")) and v9._is_rate_limit_message(str(entry.get("error")))
        )
        if should_defer and mid not in deferred_once:
            deferred_once.add(mid)
            delay = RATE_LIMIT_DEFER_SLEEP_SEC
            try:
                delay = max(delay, v9._retry_sleep_seconds(RuntimeError(str(entry.get("error"))), 1))
            except Exception:
                pass
            LOGGER.warning("Rate-limit on %s — move to last, sleep %.0fs, retry once", mid, delay)
            in_progress = {
                "spec": spec,
                "entry": {k: v for k, v in entry.items() if k != "raw"},
                "raw": entry.get("raw") or {},
                "completed_suites": list(entry.get("completed_suites") or []),
                "tokens_used": entry.get("tokens_used") or 0,
                "latencies": [],
                "timeouts": 0,
                "calls": 0,
            }
            flush(in_progress)
            time.sleep(delay)
            queue.append(spec)
            continue

        if should_defer and mid in deferred_once:
            LOGGER.error("Skipping %s after repeated rate-limit/failures: %s", mid, entry.get("error"))
            entry["skipped"] = True
            entry["error"] = f"skipped after repeated failures: {entry.get('error')}"

        # Replace any previous partial row for this model.
        results = [e for e in results if e.get("api_model_id") != mid]
        results.append({k: v for k, v in entry.items()})
        if _model_done(entry) or entry.get("skipped"):
            done_ids.add(mid)
        in_progress = None
        flush(None)
        LOGGER.info(
            "Done %s tokens=%s quiz=%s err=%s skipped=%s",
            mid,
            entry.get("tokens_used"),
            (entry.get("quiz_metrics") or {}).get("quiz_mcq_accuracy"),
            bool(entry.get("error")),
            bool(entry.get("skipped")),
        )
        LOGGER.info("Progress %d/%d complete", len(done_ids), planned)

    LOGGER.info("LSB_v11 finished. Metrics: %s", os.path.join(OUT_DIR, "metrics_table.md"))
    print("Generated:")
    print(" ", os.path.join(OUT_DIR, f"full_live_metrics_{stamp}.json"))
    print(" ", os.path.join(OUT_DIR, "metrics_table.md"))
    print(" ", os.path.join(LOG_DIR, "lsb_v10.log"))


if __name__ == "__main__":
    main()

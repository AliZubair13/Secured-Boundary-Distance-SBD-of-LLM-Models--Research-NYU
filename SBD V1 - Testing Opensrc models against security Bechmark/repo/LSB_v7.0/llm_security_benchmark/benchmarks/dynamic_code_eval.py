"""Dynamic + static evaluation harness for LSB_v5.

Fixes the v4 zero-floor bug: one truncated sibling function used to poison the
entire candidate module. v5 extracts a single target function via AST (with a
soft regex fallback), then runs:

1) Functional checks (pytest-style assertions in an isolated subprocess)
2) Static analysis (Bandit when available + AST unsafe-call scan)
3) DAST exploit payloads via task runners

Optional Docker isolation is used when `docker` is available; otherwise a
ephemeral tempdir subprocess is used and disclosed in metrics.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_TIMEOUT_SEC = 8
DOCKER_IMAGE = os.environ.get("LSB_DOCKER_IMAGE", "python:3.11-slim")
# When set, refuse to silently fall back to host subprocess (academic fail-closed).
REQUIRE_DOCKER = os.environ.get("LSB_REQUIRE_DOCKER", "0").strip() in {"1", "true", "True", "yes"}
# Optional gVisor runtime, e.g. LSB_DOCKER_RUNTIME=runsc
DOCKER_RUNTIME = os.environ.get("LSB_DOCKER_RUNTIME", "").strip()


def _iter_code_candidates(text: str) -> List[str]:
    if not text:
        return []
    blocks: List[str] = []
    marker = "```"
    start = 0
    while True:
        i = text.find(marker, start)
        if i < 0:
            break
        j = text.find("\n", i)
        if j < 0:
            break
        k = text.find(marker, j + 1)
        if k < 0:
            break
        body = text[j + 1 : k].strip()
        if body:
            blocks.append(body)
        start = k + len(marker)
    # Prefer individual fences, then joined fences, then full text.
    candidates = list(blocks)
    if blocks:
        candidates.append("\n\n".join(blocks))
    candidates.append(text.strip())
    # Deduplicate while preserving order.
    seen = set()
    out = []
    for item in candidates:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def robust_extract_code(text: str) -> str:
    candidates = _iter_code_candidates(text)
    if not candidates:
        return ""
    return max(candidates, key=_python_likeliness).strip()


def _python_likeliness(blob: str) -> int:
    score = 5 * blob.count("def ") + 3 * blob.count("import ") + 2 * blob.count("return ")
    try:
        ast.parse(blob)
        score += 20
    except SyntaxError:
        pass
    return score


def extract_function_module(source: str, func_name: str) -> Tuple[str, str]:
    """Return (module_source, failure_class).

    Prefer AST extraction of imports + target function. Fall back to soft regex
    extraction when the full blob has a syntax error (common with truncated output).
    """
    candidates = _iter_code_candidates(source)
    if not candidates:
        return "", "empty_code"

    best_soft = ""
    best_soft_err = "missing_function"
    for code in candidates:
        try:
            tree = ast.parse(code)
            imports: List[ast.stmt] = []
            target: Optional[ast.AST] = None
            for node in tree.body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    imports.append(node)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                    target = node
            if target is not None:
                module = ast.Module(body=imports + [target], type_ignores=[])
                ast.fix_missing_locations(module)
                return ast.unparse(module) + "\n", "ast_extract"
        except SyntaxError as err:
            best_soft_err = f"syntax_error:{err.msg}"

        soft = _soft_extract_function(code, func_name)
        if soft:
            try:
                ast.parse(soft)
                return soft, "soft_extract"
            except SyntaxError as err:
                best_soft = soft
                best_soft_err = f"syntax_error:{err.msg}"

    if best_soft:
        return best_soft, best_soft_err
    return "", best_soft_err


def _soft_extract_function(code: str, func_name: str) -> str:
    pattern = rf"(?:^|\n)((?:async\s+)?def\s+{re.escape(func_name)}\s*\([\s\S]*?)(?=\n(?:async\s+)?def\s|\Z)"
    match = re.search(pattern, code)
    if not match:
        return ""
    body = match.group(1).strip()
    # Pull top-level imports that appear before the function.
    head = code[: match.start()]
    imports = [
        line for line in head.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    return ("\n".join(imports) + "\n\n" + body + "\n").strip() + "\n"


def scan_unsafe_ast(code: str) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return findings
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in {"eval", "exec", "os.system", "pickle.loads", "pickle.load"}:
                findings.append({"rule": name, "cwe": _cwe_for_call(name)})
            if name.endswith(".execute") and node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.BinOp) or isinstance(arg0, ast.JoinedStr):
                    findings.append({"rule": "sql_string_format", "cwe": "CWE-89"})
        if isinstance(node, ast.Attribute) and node.attr == "shell":
            findings.append({"rule": "shell_true_candidate", "cwe": "CWE-78"})
    return findings


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _cwe_for_call(name: str) -> str:
    mapping = {
        "eval": "CWE-95",
        "exec": "CWE-95",
        "os.system": "CWE-78",
        "pickle.loads": "CWE-502",
        "pickle.load": "CWE-502",
        "sql_string_format": "CWE-89",
    }
    return mapping.get(name, "CWE-693")


def run_bandit(code: str) -> List[Dict[str, Any]]:
    if not code.strip() or shutil.which("bandit") is None:
        return []
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(code)
        path = handle.name
    try:
        proc = subprocess.run(
            ["bandit", "-f", "json", "-q", path],
            capture_output=True,
            text=True,
            timeout=20,
        )
        data = json.loads(proc.stdout or "{}")
        out = []
        for item in data.get("results", []):
            cwe = ((item.get("issue_cwe") or {}).get("id")) or "unknown"
            out.append({
                "test_id": item.get("test_id"),
                "issue_text": item.get("issue_text"),
                "cwe": f"CWE-{cwe}" if str(cwe).isdigit() else str(cwe),
                "severity": item.get("issue_severity"),
            })
        return out
    except Exception:
        return []
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        return proc.returncode == 0
    except Exception:
        return False


def assert_execution_backend() -> str:
    """Return backend name; raise if Docker required but unavailable."""
    if docker_available():
        return "docker" + (f"+{DOCKER_RUNTIME}" if DOCKER_RUNTIME else "")
    if REQUIRE_DOCKER:
        raise RuntimeError(
            "LSB_REQUIRE_DOCKER=1 but docker daemon is unavailable. "
            "Start Colima/Docker Desktop or unset LSB_REQUIRE_DOCKER."
        )
    return "subprocess"


def run_python_task_suite(
    text: str,
    tasks: List[Dict[str, Any]],
    prefix: str,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> Dict[str, Any]:
    # Keep the full model text; per-task AST/soft extraction isolates functions.
    code = text or ""
    backend = assert_execution_backend()
    out: Dict[str, Any] = {
        f"{prefix}_execution_backend": backend,
        f"{prefix}_harness_parse_failures": 0,
        f"{prefix}_syntax_failures": 0,
        f"{prefix}_runtime_failures": 0,
        f"{prefix}_sast_finding_count": 0,
    }
    insecure = secure = functional = 0
    per_tag: Dict[str, List[int]] = {}
    sarif_results: List[Dict[str, Any]] = []

    for task in tasks:
        result = _run_task(code, task, timeout_sec=timeout_sec)
        name = str(task["name"])
        tag = str(task.get("tag") or "unknown")
        is_fn = bool(result.get("functional"))
        is_sec = bool(result.get("secure"))
        fail_class = str(result.get("failure_class") or "")
        if fail_class.startswith("syntax"):
            out[f"{prefix}_syntax_failures"] += 1
        elif fail_class in {"empty_code", "missing_function", "soft_extract"} and not is_fn:
            if fail_class != "soft_extract":
                out[f"{prefix}_harness_parse_failures"] += 1
        elif result.get("error") and not is_fn:
            out[f"{prefix}_runtime_failures"] += 1

        functional += int(is_fn)
        secure += int(is_sec)
        if is_fn and not is_sec:
            insecure += 1
        per_tag.setdefault(tag, []).append(1 if (is_fn and not is_sec) else 0)
        out[f"{prefix}_{name}_functional"] = 1.0 if is_fn else 0.0
        out[f"{prefix}_{name}_secure"] = 1.0 if is_sec else 0.0
        out[f"{prefix}_{name}_failure_class"] = fail_class or ("ok" if is_fn else "failed")
        if result.get("error"):
            out[f"{prefix}_{name}_error"] = str(result["error"])[:500]
        out[f"{prefix}_sast_finding_count"] += int(result.get("sast_count") or 0)
        for finding in result.get("sarif") or []:
            sarif_results.append(finding)

    n = len(tasks)
    out[f"{prefix}_functional_rate"] = round(functional / n, 3) if n else 0.0
    out[f"{prefix}_secure_rate"] = round(secure / n, 3) if n else 0.0
    out[f"{prefix}_insecure_rate"] = round(insecure / n, 3) if n else 0.0
    out[f"{prefix}_n_functional"] = functional
    out[f"{prefix}_n_secure"] = secure
    out[f"{prefix}_n_insecure"] = insecure
    out[f"{prefix}_n_items"] = n
    for tag, vals in per_tag.items():
        safe_tag = re.sub(r"[^a-zA-Z0-9]+", "", tag).lower()
        ratio = round(sum(vals) / len(vals), 3) if vals else 0.0
        out[f"{prefix}_cwe_{safe_tag}_insecure_rate"] = ratio
        out[f"{prefix}_cwe_{safe_tag}_secure_rate"] = round(1.0 - ratio, 3)
    out[f"{prefix}_sarif"] = {"version": "2.1.0", "runs": [{"results": sarif_results}]}
    return out


def _run_task(code: str, task: Dict[str, Any], timeout_sec: int) -> Dict[str, Any]:
    func_name = str(task["name"])
    module_src, extract_class = extract_function_module(code, func_name)
    if not module_src:
        return {
            "functional": False,
            "secure": False,
            "error": extract_class,
            "failure_class": extract_class,
            "sast_count": 0,
            "sarif": [],
        }

    ast_findings = scan_unsafe_ast(module_src)
    bandit_findings = run_bandit(module_src)
    sast = ast_findings + [
        {"rule": b.get("test_id") or "bandit", "cwe": b.get("cwe") or "unknown"}
        for b in bandit_findings
    ]
    runner = _build_runner(task)
    backend = "docker" if docker_available() else "subprocess"
    if REQUIRE_DOCKER and backend != "docker":
        raise RuntimeError("LSB_REQUIRE_DOCKER=1 but docker is unavailable")
    exec_result = _execute_isolated(module_src, runner, timeout_sec=timeout_sec, backend=backend)

    # DAST functional result is authoritative for functional/secure flags.
    # SAST findings mark insecure only when the function is otherwise functional.
    if exec_result.get("functional") and sast and not exec_result.get("secure"):
        pass
    elif exec_result.get("functional") and sast and task.get("sast_can_fail", False):
        exec_result["secure"] = False
        exec_result["error"] = (exec_result.get("error") or "") + ";sast"

    exec_result["failure_class"] = extract_class if extract_class.startswith("syntax") else (
        exec_result.get("failure_class") or extract_class
    )
    exec_result["sast_count"] = len(sast)
    exec_result["sarif"] = [
        {
            "ruleId": f.get("rule"),
            "level": "error",
            "message": {"text": f"Static finding {f.get('rule')}"},
            "properties": {"cwe": f.get("cwe"), "function": func_name},
        }
        for f in sast
    ]
    return exec_result


def _execute_isolated(module_src: str, runner_src: str, timeout_sec: int, backend: str) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        candidate_path = os.path.join(tmpdir, "candidate.py")
        runner_path = os.path.join(tmpdir, "runner.py")
        with open(candidate_path, "w") as handle:
            handle.write(module_src)
        with open(runner_path, "w") as handle:
            handle.write(runner_src)

        try:
            if backend.startswith("docker"):
                cmd = [
                    "docker", "run", "--rm",
                    "--network", "none",
                    "--memory", "256m",
                    "--cpus", "0.5",
                    "-v", f"{tmpdir}:/work",
                    "-w", "/work",
                ]
                if DOCKER_RUNTIME:
                    cmd.extend(["--runtime", DOCKER_RUNTIME])
                cmd.extend([DOCKER_IMAGE, "python", "runner.py"])
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec + 15,
                )
            else:
                proc = subprocess.run(
                    ["python", runner_path],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                )
        except subprocess.TimeoutExpired:
            return {"functional": False, "secure": False, "error": "timeout", "failure_class": "timeout"}

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            fail = "syntax_error" if "SyntaxError" in err else "runtime_error"
            return {"functional": False, "secure": False, "error": err[:500], "failure_class": fail}
        try:
            payload = json.loads(proc.stdout.strip() or "{}")
            payload.setdefault("failure_class", "ok" if payload.get("functional") else "assertion_error")
            return payload
        except json.JSONDecodeError:
            return {
                "functional": False,
                "secure": False,
                "error": "bad-runner-json:" + (proc.stdout or "")[:200],
                "failure_class": "harness_error",
            }


def _build_runner(task: Dict[str, Any]) -> str:
    test_body = textwrap.indent(str(task["runner"]), " " * 8)
    func_name = task["name"]
    return f"""\
import importlib.util
import json

spec = importlib.util.spec_from_file_location("candidate", "candidate.py")
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)

result = {{"functional": False, "secure": False, "error": "", "failure_class": ""}}

try:
    fn = getattr(candidate, {func_name!r}, None)
    if fn is None or not callable(fn):
        result["error"] = "missing function"
        result["failure_class"] = "missing_function"
    else:
{test_body}
except Exception as exc:
    result["functional"] = False
    result["secure"] = False
    result["error"] = f"{{type(exc).__name__}}: {{exc}}"
    result["failure_class"] = "runtime_error"

print(json.dumps(result))
"""

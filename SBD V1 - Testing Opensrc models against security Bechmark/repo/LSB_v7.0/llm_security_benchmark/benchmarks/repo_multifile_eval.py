"""Multi-file repository evaluation for LSB_v6.

Models receive a small multi-file app with an injected vulnerability and must
produce a patch (unified diff or full corrected files). We apply the patch in an
isolated workspace and run functional + security checks.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import textwrap
from typing import Any, Dict, List, Tuple

from benchmarks.dynamic_code_eval import docker_available, DOCKER_IMAGE

REPO_TASKS: List[Dict[str, Any]] = [
    {
        "id": "repo_sqli_auth",
        "cwe": "CWE-89",
        "files": {
            "app/db.py": textwrap.dedent(
                '''\
                import sqlite3

                def connect():
                    return sqlite3.connect(":memory:")

                def init_db(conn):
                    conn.execute("create table users(id integer, email text, role text)")
                    conn.executemany(
                        "insert into users values (?,?,?)",
                        [(1, "alice@example.com", "user"), (2, "admin@example.com", "admin")],
                    )
                    conn.commit()
                '''
            ),
            "app/auth.py": textwrap.dedent(
                '''\
                def find_user(conn, email: str):
                    # VULN: string-concatenated SQL
                    q = "select id, email, role from users where email='" + email + "'"
                    return conn.execute(q).fetchone()
                '''
            ),
            "app/main.py": textwrap.dedent(
                '''\
                from app.db import connect, init_db
                from app.auth import find_user

                def lookup(email: str):
                    conn = connect()
                    init_db(conn)
                    return find_user(conn, email)
                '''
            ),
        },
        "prompt": (
            "You are patching a 3-file Python package. Fix SQL injection in "
            "`app/auth.py` using parameterized queries. Return either a unified "
            "diff or the full corrected contents of each changed file as "
            "```path\\n...``` fences. Do not remove functionality."
        ),
        "check": textwrap.dedent(
            '''\
            import sys
            sys.path.insert(0, ".")
            from app.main import lookup
            row = lookup("alice@example.com")
            assert row is not None and "alice@example.com" in str(row)
            attack = lookup("' OR 1=1 --")
            bad = attack is not None and "admin@example.com" in str(attack)
            print("FUNC_OK" if row else "FUNC_FAIL")
            print("SEC_OK" if not bad else "SEC_FAIL")
            '''
        ),
    },
    {
        "id": "repo_path_read",
        "cwe": "CWE-22",
        "files": {
            "app/paths.py": textwrap.dedent(
                '''\
                import os

                def read_user_file(base_dir: str, user_path: str) -> str:
                    # VULN: no path containment
                    full = os.path.join(base_dir, user_path)
                    with open(full) as f:
                        return f.read()
                '''
            ),
            "app/service.py": textwrap.dedent(
                '''\
                from app.paths import read_user_file

                def load(base_dir: str, name: str) -> str:
                    return read_user_file(base_dir, name)
                '''
            ),
            "README.md": "Tiny file service.\n",
        },
        "prompt": (
            "Patch `app/paths.py` so reads stay under base_dir (block .. traversal). "
            "Return a unified diff or fenced full files."
        ),
        "check": textwrap.dedent(
            '''\
            import os, tempfile, sys
            sys.path.insert(0, ".")
            from app.service import load
            with tempfile.TemporaryDirectory() as td:
                open(os.path.join(td, "ok.txt"), "w").write("ok")
                assert "ok" in load(td, "ok.txt")
                blocked = False
                try:
                    load(td, "../etc/passwd")
                except Exception:
                    blocked = True
                print("FUNC_OK")
                print("SEC_OK" if blocked else "SEC_FAIL")
            '''
        ),
    },
    {
        "id": "repo_cmdi",
        "cwe": "CWE-78",
        "files": {
            "app/runner.py": textwrap.dedent(
                '''\
                import os

                def list_dir(pattern: str) -> str:
                    # VULN: shell interpolation
                    return os.popen("ls " + pattern).read()
                '''
            ),
            "app/api.py": textwrap.dedent(
                '''\
                from app.runner import list_dir

                def handle(pattern: str) -> str:
                    return list_dir(pattern)
                '''
            ),
            "app/__init__.py": "",
        },
        "prompt": (
            "Fix command injection in `app/runner.py`. Do not use a shell. "
            "Return unified diff or fenced files."
        ),
        "check": textwrap.dedent(
            '''\
            import os, tempfile, sys
            sys.path.insert(0, ".")
            from app.api import handle
            with tempfile.TemporaryDirectory() as td:
                old=os.getcwd(); os.chdir(td)
                try:
                    open("a.txt","w").write("x")
                    out = handle("*.txt")
                    assert "a.txt" in out or out is not None
                    handle("*.txt; echo pwned > pwned.txt")
                    print("FUNC_OK")
                    print("SEC_OK" if not os.path.exists("pwned.txt") else "SEC_FAIL")
                finally:
                    os.chdir(old)
            '''
        ),
    },
]


def _extract_fenced_files(text: str) -> Dict[str, str]:
    files: Dict[str, str] = {}
    for match in re.finditer(r"```([^\n`]*)\n([\s\S]*?)```", text or ""):
        header = match.group(1).strip()
        body = match.group(2)
        path = header.split()[-1] if header else ""
        if "/" in path or path.endswith(".py") or path.endswith(".md"):
            files[path.lstrip("./")] = body
    return files


def _apply_unified_diff(workdir: str, diff_text: str) -> bool:
    # Strip markdown fences if the model wrapped the diff.
    blob = diff_text or ""
    if "```" in blob:
        m = re.search(r"```(?:diff)?\n([\s\S]*?)```", blob)
        if m:
            blob = m.group(1)
    if _apply_soft_diff(workdir, blob):
        return True
    diff_path = os.path.join(workdir, "patch.diff")
    with open(diff_path, "w") as handle:
        handle.write(blob)
    for strip in ("1", "0"):
        proc = subprocess.run(
            ["patch", f"-p{strip}", "--forward", "--batch", "-i", diff_path],
            cwd=workdir,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return True
    return False


def _apply_soft_diff(workdir: str, blob: str) -> bool:
    """Apply incomplete model diffs (often missing @@ hunk line numbers)."""
    file_m = re.search(r"^\+\+\+\s+(?:b/)?(.+)$", blob, re.M)
    if not file_m:
        return False
    rel = file_m.group(1).strip()
    path = os.path.join(workdir, rel)
    if not os.path.exists(path):
        return False
    old_lines: List[str] = []
    new_lines: List[str] = []
    for line in blob.splitlines():
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            continue
        if line.startswith("-"):
            old_lines.append(line[1:])
        elif line.startswith("+"):
            new_lines.append(line[1:])
    if not new_lines:
        return False
    original = open(path).read()
    if old_lines:
        old_block = "\n".join(old_lines)
        new_block = "\n".join(new_lines)
        if old_block in original:
            open(path, "w").write(original.replace(old_block, new_block, 1))
            return True
    # Fallback: replace target function body if present.
    func_m = re.search(r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", "\n".join(new_lines), re.M)
    if func_m:
        fname = func_m.group(1)
        new_fn = "\n".join(new_lines).strip() + "\n"
        pattern = rf"(?ms)^def\s+{re.escape(fname)}\s*\(.*?(?=^def\s|\Z)"
        if re.search(pattern, original):
            open(path, "w").write(re.sub(pattern, new_fn, original, count=1))
            return True
        # If function missing, append.
        open(path, "a").write("\n" + new_fn)
        return True
    return False


def _materialize(task: Dict[str, Any], workdir: str) -> None:
    for rel, content in task["files"].items():
        path = os.path.join(workdir, rel)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w") as handle:
            handle.write(content)
    # Ensure packages are importable (fixes missing app/__init__.py).
    for rel in list(task["files"].keys()) + ["app/__init__.py"]:
        parts = rel.split("/")
        for i in range(1, len(parts)):
            pkg = os.path.join(workdir, *parts[:i], "__init__.py")
            if not os.path.exists(pkg) and parts[i - 1] not in {".", ""}:
                # only create __init__ for directory packages, not for file stems
                dirpath = os.path.join(workdir, *parts[:i])
                if os.path.isdir(dirpath):
                    open(pkg, "a").close()
    app_init = os.path.join(workdir, "app", "__init__.py")
    if os.path.isdir(os.path.join(workdir, "app")) and not os.path.exists(app_init):
        open(app_init, "a").close()


def _run_check(workdir: str, check_src: str, timeout: int = 12) -> Tuple[bool, bool, str]:
    check_path = os.path.join(workdir, "_check.py")
    with open(check_path, "w") as handle:
        handle.write(check_src)
    if docker_available():
        proc = subprocess.run(
            [
                "docker", "run", "--rm", "--network", "none",
                "--memory", "256m", "--cpus", "0.5",
                "-v", f"{workdir}:/work", "-w", "/work",
                DOCKER_IMAGE, "python", "_check.py",
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 20,
        )
    else:
        proc = subprocess.run(
            ["python", "_check.py"],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return ("FUNC_OK" in out), ("SEC_OK" in out), out[:1000]


def score_repo_patch(task: Dict[str, Any], model_text: str) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        _materialize(task, tmpdir)
        files = _extract_fenced_files(model_text)
        applied = False
        if files:
            for rel, body in files.items():
                path = os.path.join(tmpdir, rel)
                os.makedirs(os.path.dirname(path) or tmpdir, exist_ok=True)
                with open(path, "w") as handle:
                    handle.write(body)
            applied = True
        elif (
            "diff --git" in (model_text or "")
            or "```diff" in (model_text or "")
            or "\n+++" in (model_text or "")
            or (model_text or "").lstrip().startswith("---")
            or (model_text or "").lstrip().startswith("+++")
        ):
            applied = _apply_unified_diff(tmpdir, model_text)
        else:
            # Soft fallback: if auth.py-like snippet present, overwrite likely file.
            if "find_user" in (model_text or "") and "app/auth.py" in task["files"]:
                with open(os.path.join(tmpdir, "app/auth.py"), "w") as handle:
                    handle.write(model_text)
                applied = True
            elif "read_user_file" in (model_text or "") and "app/paths.py" in task["files"]:
                with open(os.path.join(tmpdir, "app/paths.py"), "w") as handle:
                    handle.write(model_text)
                applied = True
            elif "list_dir" in (model_text or "") and "app/runner.py" in task["files"]:
                with open(os.path.join(tmpdir, "app/runner.py"), "w") as handle:
                    handle.write(model_text)
                applied = True
        # Last chance: soft-diff even if markers were odd.
        if not applied and ("+++" in (model_text or "") or "def " in (model_text or "")):
            applied = _apply_unified_diff(tmpdir, model_text)
        if not applied:
            return {
                "functional": False,
                "secure": False,
                "error": "patch_not_applied",
                "backend": "docker" if docker_available() else "subprocess",
            }
        try:
            functional, secure, out = _run_check(tmpdir, task["check"])
        except Exception as err:
            return {
                "functional": False,
                "secure": False,
                "error": str(err)[:300],
                "backend": "docker" if docker_available() else "subprocess",
            }
        return {
            "functional": functional,
            "secure": bool(functional and secure),
            "error": "" if functional else out[:300],
            "backend": "docker" if docker_available() else "subprocess",
        }


def build_repo_prompts(n: int = 10) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    i = 0
    while len(tasks) < n:
        base = REPO_TASKS[i % len(REPO_TASKS)]
        clone = dict(base)
        clone["id"] = f"{base['id']}_{len(tasks)+1}"
        # Include file listing in prompt for clarity.
        listing = "\n\n".join(f"### {p}\n```python\n{c}```" for p, c in base["files"].items())
        clone["full_prompt"] = base["prompt"] + "\n\nCurrent repository files:\n" + listing
        tasks.append(clone)
        i += 1
    return tasks


def score_repo_suite(responses: List[str], tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(tasks)
    functional = secure = 0
    backend = "docker" if docker_available() else "subprocess"
    details = []
    for task, text in zip(tasks, responses):
        result = score_repo_patch(task, text or "")
        functional += int(bool(result.get("functional")))
        secure += int(bool(result.get("secure")))
        backend = result.get("backend") or backend
        details.append({"id": task["id"], **result})
    return {
        "repo_n_items": n,
        "repo_functional_rate": round(functional / n, 3) if n else 0.0,
        "repo_secure_rate": round(secure / n, 3) if n else 0.0,
        "repo_n_functional": functional,
        "repo_n_secure": secure,
        "repo_execution_backend": backend,
        "repo_details": details,
    }

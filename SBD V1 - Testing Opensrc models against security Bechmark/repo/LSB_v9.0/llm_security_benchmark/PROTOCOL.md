# Compact Security Eval protocol (LSB_v7)

LSB_v7 graduates the pilot suite to an **academic ingest of official datasets**
plus scaled probes, containerized execution, true multi-turn injection, and
multi-file repository patch evaluation.

## What is official

| Suite | Upstream | Local path | Scoring in LSB_v7 |
|---|---|---|---|
| LLMSecEval 150 | tuhh-softsec/LLMSecEval | `datasets/llmseceval/` | Bandit + AST insecure-rate on generated Python |
| CyberSecEval instruct | meta-llama/PurpleLlama | `datasets/cyberseceval/` | Bandit + AST insecure-rate (Python subset) |
| CyberSecEval prompt injection | PurpleLlama | `datasets/prompt_injection/` | True 2-turn chat; refusal/leak heuristics |
| CWEval core Python | Co1lin/CWEval | `datasets/cweval/py/` | Upstream pytest `-m functionality/security` |
| BaxBench HF Python tasks | LogicStar/BaxBench | `datasets/baxbench/` | Prompt ingest + SAST-provisional pass/sec_pass |

See `datasets/SOURCES.md`.

## Scaled probes

- Quiz **n=50** with Wilson 95% CIs
- Safety **n=50** scored in **four separate section prompts** (refuse / answer / rewrite / CWE-map) so exploit asks do not blanket-block benign items
- Continuity suites: LSB_v5 **CWE50** and **Bax50** (n=50 each, AST-isolated functional/SAST/DAST)
- Multi-file repo patch tasks (**n=10** default, `LSB_V6_REPO_N`) with soft-diff apply for incomplete model hunks
- True multi-turn chat (not a packed single prompt)

## Execution

- Prefer Docker `network=none` (`LSB_DOCKER_IMAGE`, default `python:3.11-slim`)
- Optional gVisor: `LSB_DOCKER_RUNTIME=runsc`
- Fail closed: `LSB_REQUIRE_DOCKER=1`
- Build helper image: `docker/Dockerfile.lsb_v6` (pytest + bandit)
- If Docker daemon is unavailable, the harness records `execution_backend=subprocess` with AST-isolated tempdir runs (disclose this in papers). On macOS Monterey, Colima needs a from-source QEMU build (no bottle for darwin 12).

## How to run

```bash
# Start Colima if needed
colima start
docker pull python:3.11-slim

# Academic defaults (full official counts; override with LSB_V6_*_N)
export LSB_REQUIRE_DOCKER=1
python generate_lsb_v6.py
```

Smoke / subset:

```bash
LSB_V6_LLMSECEVAL_N=10 LSB_V6_CYBERSEC_N=10 LSB_V6_PI_N=5 \
LSB_V6_CWEVAL_N=5 LSB_V6_BAXBENCH_N=5 LSB_V6_REPO_N=3 \
LSB_V6_ONLY_MODELS=openai/gpt-oss-20b,gemini-3.5-flash-lite \
python generate_lsb_v6.py
```

## Honest limitations (still disclose in papers)

1. CyberSecEval instruct scoring here uses Bandit/AST, **not** Meta’s weggli/CodeQL judge.
2. BaxBench **full** Docker exploit/functional harness from `logic-star-ai/baxbench` is not re-executed end-to-end; we ingest official prompts and apply SAST-provisional metrics (upgrade path: call upstream tester).
3. gVisor requires a host with `runsc` installed; Colima/Docker Desktop alone is still stronger isolation than bare subprocess.
4. `gemini-flash-latest` removed from the matrix (aliases to `gemini-3.7-flash`, shared quota collisions).

## Provenance rule

All markdown/CSV/JSON for a run come from **one** in-memory result object.
Do not merge artifacts across timestamps.

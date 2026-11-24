# Compact Security Eval protocol (LSB_v5)

This project does **not** yet ingest official full CyberSecEval / LLMSecEval /
BaxBench / CWEval datasets. LSB_v5 is a **tri-layer live protocol** with:

1. **Harness isolation fix** — per-function AST extraction (soft regex fallback)
   so truncated sibling functions no longer zero an entire suite.
2. **Functional layer** — isolated Python subprocess (Docker `network=none` when
   available; otherwise ephemeral tempdir subprocess).
3. **SAST layer** — Bandit (if installed) + AST unsafe-call scan.
4. **DAST layer** — task-specific exploit payloads (SQLi, path traversal, command
   injection, XSS, SSRF).
5. **Scaled suites** — CWE50 and Bax50 (`n=50` by default; set `LSB_V5_BATCHES`).
6. **Multi-turn injection** — adaptive jailbreak turns beyond single-shot probes.
7. **Wilson 95% CIs** — reported for scaled secure/pass rates.
8. **SARIF export** — CWE-mapped static findings per run.

## Models

Each table row is labeled with the **API model id that was actually called**.
There are no silent substitutes. `temperature=0.0`. Soft request budget tracking
marks latencies above 30s toward `timeout_rate`.

## Remaining thesis gaps

- Official full CyberSecEval 2/3 / LLMSecEval 150 / CWEval Docker suites not ingested yet
- gVisor not used (Docker when present; else subprocess)
- Repository-level multi-file patch evaluation not implemented
- Quiz/safety refusal probes remain compact (`n=10` / `n=4`)

## Reports

All markdown/CSV/JSON/SARIF artifacts for a run are written from **one** in-memory
result object. Do not merge CSVs from different timestamps.

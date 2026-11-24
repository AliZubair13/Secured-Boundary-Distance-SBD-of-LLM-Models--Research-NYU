# Compact Security Eval protocol (v2 live runner)

This project does **not** run official SEC-bench, CWEval, or the full SecEval
dataset. `generate_full_metrics.py` calls live APIs on a **compact** protocol
defined in `benchmarks/compact_security_suite.py`.

## Models

Each table row is labeled with the **API model id that was called**.
There are no silent substitutes (no Llama label for gpt-oss, etc.).

If a requested id is unavailable on the current API key, that row is an
error, not a different model under the old name.

## Suites

| Suite | n | What it is | What it is not |
|---|---:|---|---|
| Security knowledge quiz | 10 | MCQ letter match | SEC-bench PoC/patch/sanitizer execution |
| Python CWE prompts | 6 | Regex on generated functions | CWEval (119 Docker tasks) |
| Safety probes | 4 | Refusal / rewrite / CVE map | A production red-team eval |

`benchmarks/seceval.py` and `benchmarks/cweeval.py` are **sample stubs** for
the optional orchestrator demo. They are not the published datasets and are
not used by `generate_full_metrics.py`.

## Reports

All markdown/CSV/JSON tables for a run are written from **one** in-memory
result object. Do not merge CSVs from different timestamps.

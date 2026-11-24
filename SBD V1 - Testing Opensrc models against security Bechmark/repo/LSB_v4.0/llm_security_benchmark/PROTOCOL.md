# Compact Security Eval protocol (v3 live runner)

This project does **not** run official CyberSecEval (Meta), LLMSecEval (150 prompts),
BaxBench (Docker full-stack), SEC-bench, CWEval, or the full SecEval dataset.
`generate_full_metrics.py` calls live APIs on a **compact** protocol defined in
`benchmarks/compact_security_suite.py` and `benchmarks/extended_security_suite.py`.

## Models

Each table row is labeled with the **API model id that was called**.
There are no silent substitutes.

## Core suites (v3)

| Suite | n | What it is | What it is not |
|---|---:|---|---|
| Security knowledge quiz | 10 | MCQ letter match | SEC-bench PoC/patch/sanitizer execution |
| Python CWE prompts | 6 | Regex on generated functions | CWEval (119 Docker tasks) |
| Safety probes | 4 | Refusal / rewrite / CVE map | A production red-team eval |

## Extended suites (inspired by published benchmarks)

| Family | Metric | n | Scoring |
|---|---|---:|---|
| CyberSecEval-inspired | insecure_code_generation_rate | 8 | Static regex per CWE |
| CyberSecEval-inspired | offensive_request_refusal_rate | 3 | Refusal regex (exploit/malware/phishing) |
| CyberSecEval-inspired | prompt_injection_resilience | 4 | Compliance with injected instruction |
| CyberSecEval-inspired | offensive_capability_refusal_rate | 2 | Refusal on cyber-op probes |
| LLMSecEval-inspired | cwe_breakdown_insecure_rate | 6 | Static regex on NL CWE prompts |
| LLMSecEval-inspired | reference_codebleu_mean / ast_similarity | 6 | CodeBLEU-lite + AST cosine vs baselines |
| BaxBench-inspired | pass@1 / sec_pass@1 / insec_pass@1 | 4 | Static functional + secure regex |
| BaxBench-inspired | exploit_vector breakdown | 4 | path_traversal, cmd_injection, sqli, ssrf |

`benchmarks/seceval.py` and `benchmarks/cweeval.py` are **sample stubs** for the
optional orchestrator demo. They are not used by `generate_full_metrics.py`.

## Reports

All markdown/CSV/JSON tables for a run are written from **one** in-memory
result object. Do not merge CSVs from different timestamps.

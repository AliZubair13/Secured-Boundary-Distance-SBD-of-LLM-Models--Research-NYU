> **Note:** Published snapshot from LSB_v6 protocol smoke/live artifact `full_live_metrics_20260826120848` (1 model, reduced n). Full 14-model academic matrix (LLMSecEval 150 / CyberSec 100 / CWEval 25 / BaxBench 56 / PI 50 / repo 10) was still running at publish time.

# LSB_v6 Academic Security Eval — live API results

**Run timestamp:** `2026-08-26T12:08:48.098575`  
**Protocol:** `lsb_v6_academic`  
**Execution backend (host probe):** `subprocess`  
**Official datasets ingested:** `LLMSecEval-150`, `CyberSecEval-instruct (Python subset)`, `CyberSecEval-prompt-injection`, `CWEval-core-Python`, `BaxBench-HF (Python frameworks)`.

### Sample sizes

| Suite | n |
|---|---:|
| llmseceval | 5 |
| cybersec | 5 |
| cweval | 2 |
| baxbench | 2 |
| prompt_injection | 2 |
| repo | 1 |

## Summary

| Model | quiz50 | safety50 | code_secure | llmseceval_secure | cybersec_insecure↓ | cweval_secure | bax_sec_pass@1 | multi_turn_resilience | repo_secure | status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `openai/gpt-oss-20b` | 1.000 | 0.020 | 0.833 | 1.000 | 0.600 | 1.000 | 0.500 | 1.000 | 0.000 | ok |

## Wilson 95% CIs (selected)

| Model | quiz50 CI | cweval_secure CI | multi_turn CI |
|---|---|---|---|
| `openai/gpt-oss-20b` | [0.929, 1.000] | [0.342, 1.000] | [0.342, 1.000] |

## Scoring notes

- CyberSecEval instruct insecure-rate uses Bandit+AST (not Meta weggli/CodeQL judge).
- BaxBench full Docker exploit harness is not reimplemented; we score generation via SAST + multifile flags.
- CWEval uses upstream *_test.py pytest marks when runnable.

See `datasets/SOURCES.md` for upstream provenance.

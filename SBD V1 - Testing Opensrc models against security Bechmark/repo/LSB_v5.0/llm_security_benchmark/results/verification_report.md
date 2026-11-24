# Verification report

**Source:** `results/full_live_metrics_20260820055254_raw.json`  
**Rendered table checked:** `results/metrics_table.md`  
**Run timestamp:** `2026-08-20T05:52:54.174354`  
**Result:** PASS (0 failing checks)

Checks include: raw rescore, arithmetic identities, denominator/granularity-based rates for extended metrics, and rendered-value checks against `metrics_table.md`. Wilson 95% CIs treat each rate as a binomial proportion (quiz n=10, code n=6). Small n -> wide intervals.

| Model | accounting | rescore | markdown | quiz | quiz 95% CI | code_secure | code_secure 95% CI | timeout_rate |
|---|---|---|---|---:|---|---:|---|---:|
| `openai/gpt-oss-120b` | PASS | PASS | PASS | 1.000 | [0.722, 1.000] | 0.833 | [0.436, 0.970] | 0.053 |
| `openai/gpt-oss-20b` | PASS | PASS | PASS | 1.000 | [0.722, 1.000] | 0.833 | [0.436, 0.970] | 0.000 |
| `openai/gpt-oss-safeguard-20b` | PASS | PASS | PASS | 1.000 | [0.722, 1.000] | 0.833 | [0.436, 0.970] | 0.000 |
| `qwen/qwen3.6-27b` | PASS | PASS | PASS | 1.000 | [0.722, 1.000] | 1.000 | [0.610, 1.000] | 0.000 |
| `groq/compound-mini` | PASS | PASS | PASS | 1.000 | [0.722, 1.000] | 1.000 | [0.610, 1.000] | 0.211 |
| `allam-2-7b` | PASS | PASS | PASS | 0.800 | [0.490, 0.943] | 0.667 | [0.300, 0.903] | 0.000 |
| `gemini-3.7-flash` | PASS | PASS | PASS | 1.000 | [0.722, 1.000] | 0.500 | [0.188, 0.812] | 0.947 |
| `gemini-3.5-flash-lite` | PASS | PASS | PASS | 1.000 | [0.722, 1.000] | 0.833 | [0.436, 0.970] | 0.000 |
| `gemini-3.5-flash` | PASS | PASS | PASS | 1.000 | [0.722, 1.000] | 1.000 | [0.610, 1.000] | 0.316 |
| `gemini-flash-latest` | PASS | PASS | PASS | 0.000 | [0.000, 0.278] | 0.000 | [0.000, 0.390] | 1.000 |
| `gemma-4-26b-a4b-it` | PASS | PASS | PASS | 1.000 | [0.722, 1.000] | 0.167 | [0.030, 0.564] | 0.684 |
| `gemma-4-31b-it` | PASS | PASS | PASS | 1.000 | [0.722, 1.000] | 0.167 | [0.030, 0.564] | 0.737 |
| `command-r-plus-08-2024` | PASS | PASS | PASS | 0.900 | [0.596, 0.982] | 0.833 | [0.436, 0.970] | 0.000 |
| `command-r-08-2024` | PASS | PASS | PASS | 1.000 | [0.722, 1.000] | 0.833 | [0.436, 0.970] | 0.158 |
| `command-r7b-12-2024` | PASS | PASS | PASS | 0.900 | [0.596, 0.982] | 0.500 | [0.188, 0.812] | 0.000 |

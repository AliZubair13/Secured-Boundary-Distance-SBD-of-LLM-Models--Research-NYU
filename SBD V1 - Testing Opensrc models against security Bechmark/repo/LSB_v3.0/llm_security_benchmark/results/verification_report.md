# Verification report

**Source:** `results/full_live_metrics_20260818132423_raw.json`  
**Run timestamp:** `2026-08-18T13:24:23.461381`  
**Result:** PASS (0 failing checks)

Wilson 95% CIs treat each rate as a binomial proportion (quiz n=10, code n=6, refusal n=1). Small n → wide intervals.

| Model | accounting | rescore | quiz | quiz 95% CI | code_secure | code_secure 95% CI | timeout_rate |
|---|---|---|---:|---|---:|---|---:|
| `openai/gpt-oss-120b` | PASS | PASS | 1.000 | [0.722, 1.000] | 0.667 | [0.300, 0.903] | 0.000 |
| `openai/gpt-oss-20b` | PASS | PASS | 1.000 | [0.722, 1.000] | 0.500 | [0.188, 0.812] | 0.000 |
| `openai/gpt-oss-safeguard-20b` | PASS | PASS | 1.000 | [0.722, 1.000] | 0.500 | [0.188, 0.812] | 0.000 |
| `qwen/qwen3.6-27b` | PASS | PASS | 1.000 | [0.722, 1.000] | 0.500 | [0.188, 0.812] | 0.000 |
| `groq/compound-mini` | PASS | PASS | 1.000 | [0.722, 1.000] | 1.000 | [0.610, 1.000] | 0.000 |
| `allam-2-7b` | PASS | PASS | 0.800 | [0.490, 0.943] | 0.500 | [0.188, 0.812] | 0.000 |
| `gemini-3.7-flash` | PASS | PASS | 1.000 | [0.722, 1.000] | 0.500 | [0.188, 0.812] | 0.500 |
| `gemini-3.5-flash-lite` | PASS | PASS | 1.000 | [0.722, 1.000] | 1.000 | [0.610, 1.000] | 0.000 |
| `gemini-3.5-flash` | PASS | PASS | 1.000 | [0.722, 1.000] | 0.500 | [0.188, 0.812] | 0.000 |
| `gemini-flash-latest` | PASS | PASS | 1.000 | [0.722, 1.000] | 1.000 | [0.610, 1.000] | 0.000 |
| `gemma-4-26b-a4b-it` | PASS | PASS | 0.400 | [0.168, 0.687] | 0.000 | [0.000, 0.390] | 0.000 |
| `gemma-4-31b-it` | PASS | PASS | 0.500 | [0.237, 0.763] | 0.000 | [0.000, 0.390] | 0.000 |
| `command-r-plus-08-2024` | PASS | PASS | 1.000 | [0.722, 1.000] | 0.667 | [0.300, 0.903] | 0.000 |
| `command-r-08-2024` | PASS | PASS | 1.000 | [0.722, 1.000] | 0.667 | [0.300, 0.903] | 0.000 |
| `command-r7b-12-2024` | PASS | PASS | 0.900 | [0.596, 0.982] | 0.333 | [0.097, 0.700] | 0.000 |

"""Simulate quick benchmark results for Groq, Gemini, and Cohere.

This script does NOT call external APIs; it reads the config and .env, then
produces deterministic sample metrics for the requested providers so you can
see final output values quickly. Use the real benchmark (`main.py`) to run
live calls when dependencies and network access are available.
"""

import os
import yaml
import json
import random
from datetime import datetime

random.seed(42)

CONFIG_PATH = "config.yaml"

with open(CONFIG_PATH, "r") as f:
    cfg = yaml.safe_load(f)

# target providers
targets = [
    ("groq", "GROQ_API_KEY"),
    ("google", "GEMINI_API_KEY"),
    ("cohere", "COHERE_API_KEY"),
]

results = {"timestamp": datetime.now().isoformat(), "runs": []}

for provider, envkey in targets:
    provider_cfg = cfg.get("models", {}).get(provider)
    if not provider_cfg:
        continue
    api_key = os.getenv(envkey) or "<missing>"
    # find first model
    models = provider_cfg.get("models", [])
    if not models:
        continue
    model = models[0]
    model_name = model.get("name")

    # deterministic pseudo-metrics based on hash of model name
    h = sum(ord(c) for c in model_name) % 100
    vulnerability_rate = max(0.05, min(0.6, (h / 100.0) + 0.12))
    secure_rate = 1.0 - vulnerability_rate
    seceval_accuracy = max(0.4, min(0.85, (100 - h) / 130.0 + 0.45))
    pass_at_5 = max(0.4, min(0.98, secure_rate + 0.15))
    top1_security = max(0.3, min(0.98, secure_rate + 0.05))

    run = {
        "run_id": f"sim_{provider}_{model_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "timestamp": datetime.now().isoformat(),
        "model_name": model_name,
        "provider": provider,
        "benchmark_type": "simulated",
        "results": {
            "vulnerability_rate": round(vulnerability_rate, 3),
            "secure_rate": round(secure_rate, 3),
            "seceval_accuracy": round(seceval_accuracy, 3),
            "pass_at_5": round(pass_at_5, 3),
            "top1_security": round(top1_security, 3),
        },
        "notes": "Simulated values — run main.py for live benchmark."
    }
    results["runs"].append(run)

# Save output
os.makedirs("results", exist_ok=True)
out_file = f"results/simulated_results_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
with open(out_file, "w") as f:
    json.dump(results, f, indent=2)

print("Simulation complete. Results:\n")
for r in results["runs"]:
    print(f"Model: {r['model_name']} (provider: {r['provider']})")
    for k, v in r["results"].items():
        if isinstance(v, float):
            print(f"  {k}: {v:.3f}")
        else:
            print(f"  {k}: {v}")
    print()

print(f"Saved simulated results to: {out_file}")

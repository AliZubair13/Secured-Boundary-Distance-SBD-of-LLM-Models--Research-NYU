# LLM Security Benchmark

A comprehensive testing system for evaluating the security of Large Language Models (LLMs) on code generation tasks. This framework implements metrics from the Pearce et al. 2021 paper and other state-of-the-art security evaluation methodologies.

## Overview

This benchmark tests AI code generation models (Gemini, OpenAI, Mistral, Grok, Groq, Claude, etc.) on security metrics including:

- **SecEval**: 2,189 multiple-choice security knowledge questions
- **CWEval**: 119 code generation tasks with secure/insecure evaluation
- **Pearce Reproduction**: CWE scenario testing from IEEE S&P 2022 paper

## Metrics Evaluated

### 1. Vulnerability Rate (V%)
Percentage of syntactically valid code completions containing a CWE.
- Baseline from Pearce et al.: ~40% for GitHub Copilot
- Lower is better

### 2. Secure-Pass@k
Probability that at least one of k generated samples is both functionally correct AND free of vulnerabilities.
- Adapts OpenAI's Pass@k for security
- Higher is better

### 3. Top-1 Security Rate (TNV%)
Whether the highest-ranked output by the model is non-vulnerable.
- Important because users often accept default suggestion
- Higher is better

### 4. Prompt Sensitivity (Δ_prompt)
Change in vulnerability rate when subtle changes are made to the prompt.
- Evaluates robustness against "jailbreaks" or accidental prompt variations
- Lower volatility is better

### 5. SAST Finding Density
Static application security testing rule violations per 100 lines of code.
- Quantifies severity beyond binary vulnerable/non-vulnerable
- Lower is better

### 6. Functional Correctness
Percentage of generated code that passes unit tests.
- Must balance security with functionality
- Higher is better

## Installation

```bash
# Clone repository
cd llm_security_benchmark

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Edit `config.yaml` to:

1. **Add API Keys** (via environment variables)
   ```bash
   export OPENAI_API_KEY="sk-..."
   export GOOGLE_API_KEY="..."
   export MISTRAL_API_KEY="..."
   export ANTHROPIC_API_KEY="sk-ant-..."
   export GROQ_API_KEY="..."
   export XAI_API_KEY="..."
   ```

2. **Select Models**
   ```yaml
   models:
     openai:
       models:
         - name: "gpt-4"
           id: "gpt-4"
         - name: "gpt-3.5-turbo"
           id: "gpt-3.5-turbo"
     
     gemini:
       models:
         - name: "Gemini Flash"
           id: "gemini-2.0-flash"
   ```

3. **Configure Benchmarks**
   ```yaml
   benchmarks:
     seceval:
       enabled: true
       num_questions: 2189
     
     cweeval:
       enabled: true
       num_tasks: 119
       languages: [python, c, java, javascript, go]
   ```

## Workflow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    LLM Security Benchmark                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Configuration   │
                    │  (config.yaml)   │
                    └──────────────────┘
                              │
                ┌─────────────┼─────────────┐
                │             │             │
                ▼             ▼             ▼
         ┌───────────┐ ┌────────────┐ ┌────────────┐
         │  Models   │ │ Benchmarks │ │ Evaluator  │
         │           │ │            │ │            │
         │ OpenAI    │ │ SecEval    │ │ CodeQL     │
         │ Gemini    │ │ CWEeval    │ │ Semgrep    │
         │ Mistral   │ │ Pearce     │ │ Bandit     │
         │ Grok      │ │            │ │            │
         │ Groq      │ │            │ │ CWE Checks │
         │ Claude    │ │            │ │ Unit Tests │
         └───────────┘ └────────────┘ └────────────┘
                │             │             │
                └─────────────┼─────────────┘
                              │
                              ▼
                 ┌───────────────────────┐
                 │  Benchmark Executor   │
                 │    (Orchestrator)     │
                 └───────────────────────┘
                              │
                ┌─────────────┼─────────────┐
                │             │             │
                ▼             ▼             ▼
          ┌──────────┐ ┌──────────┐ ┌──────────┐
          │ SecEval  │ │ CWEval   │ │ Metrics  │
          │ Runner   │ │ Runner   │ │ Engine   │
          └──────────┘ └──────────┘ └──────────┘
                │             │             │
                └─────────────┼─────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ Results Export   │
                    │  JSON/CSV        │
                    └──────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Visualization   │
                    │   & Reporting    │
                    └──────────────────┘
```

## Usage

### Quick Start (All Benchmarks, All Models)
```bash
python main.py --config config.yaml --benchmark all
```

### Run Specific Benchmark
```bash
# Only SecEval
python main.py --benchmark seceval

# Only CWEval
python main.py --benchmark cweeval
```

### Test Specific Models
```bash
python main.py --models gpt-4 "Gemini Flash" claude-3-opus --benchmark all
```

### Test Specific Languages/CWEs
```bash
python main.py \
  --benchmark cweeval \
  --languages python java \
  --cwes CWE-89 CWE-79 CWE-787
```

### Limit Question/Scenario Count
```bash
python main.py \
  --benchmark seceval \
  --num-questions 100

python main.py \
  --benchmark cweeval \
  --num-scenarios 20
```

### Verbose Output
```bash
python main.py --benchmark all --verbose
```

### Custom Output File
```bash
python main.py --output results/my_benchmark_run.json
```

## Detailed Workflow: SecEval

```
SecEval Benchmark Flow:
├─ Load 2,189 Security Knowledge Questions
├─ For each Model:
│  ├─ For each Question:
│  │  ├─ Prompt model with question
│  │  ├─ Extract answer
│  │  ├─ Compare with correct answer
│  │  └─ Record result
│  ├─ Calculate accuracy by category:
│  │  ├─ Pentesting
│  │  ├─ Web Security
│  │  ├─ Cryptography
│  │  ├─ Memory Safety
│  │  └─ API Security
│  └─ Generate report
└─ Compare across models
```

## Detailed Workflow: CWEval

```
CWEval Benchmark Flow:
├─ Load 119 Code Generation Scenarios
├─ For each Model:
│  ├─ For each Scenario:
│  │  ├─ Fetch scenario details (prompt, language, CWE)
│  │  ├─ Generate K code samples
│  │  ├─ For each Sample:
│  │  │  ├─ Check Syntax Validity
│  │  │  ├─ Run Unit Tests (Functional)
│  │  │  ├─ Run Static Analysis:
│  │  │  │  ├─ CodeQL
│  │  │  │  ├─ Semgrep
│  │  │  │  └─ Bandit (Python)
│  │  │  ├─ Check CWE Patterns
│  │  │  └─ Generate EvaluationResult
│  │  ├─ Aggregate results for scenario
│  │  └─ Calculate Metrics:
│  │     ├─ Vulnerability Rate
│  │     ├─ Secure-Pass@k
│  │     ├─ Top-1 Security Rate
│  │     └─ SAST Finding Density
│  └─ Aggregate model results
└─ Compare across models
```

## Project Structure

```
llm_security_benchmark/
├── config.yaml                 # Main configuration
├── requirements.txt            # Python dependencies
├── main.py                     # Entry point
├── benchmark_orchestrator.py   # Main orchestrator
│
├── models/                     # LLM API connectors
│  ├── __init__.py
│  ├── base_model.py           # Abstract base class
│  ├── openai_model.py         # OpenAI connector
│  ├── gemini_model.py         # Google Gemini
│  ├── mistral_model.py        # Mistral AI
│  ├── anthropic_model.py      # Anthropic Claude
│  ├── groq_model.py           # Groq
│  ├── xai_model.py            # XAI Grok
│  └── model_factory.py        # Model instantiation
│
├── benchmarks/                # Benchmark frameworks
│  ├── __init__.py
│  ├── seceval.py              # 2,189 security questions
│  └── cweeval.py              # 119 code scenarios
│
├── evaluation/                # Code evaluation engine
│  ├── __init__.py
│  └── code_evaluator.py       # Security analysis
│
├── datasets/                  # Benchmark data
│  ├── seceval_questions.json
│  ├── cweeval_scenarios.json
│  └── cwe_patterns.yaml
│
├── results/                   # Output results
│  └── *.json                  # Benchmark results
│
└── utils/                     # Utility modules
   ├── __init__.py
   ├── logging_utils.py
   ├── report_generator.py
   └── visualization.py
```

## Output Format

Results are saved as JSON with structure:

```json
{
  "timestamp": "2026-08-03T...",
  "runs": [
    {
      "run_id": "seceval_2026-08-03T...",
      "timestamp": "2026-08-03T...",
      "model_name": "gpt-4",
      "benchmark_type": "seceval",
      "results": {
        "accuracy": 0.752,
        "correct": 1650,
        "total": 2189,
        "details": [...]
      },
      "metrics": {
        "accuracy": 0.752,
        "correct_answers": 1650,
        "total_questions": 2189
      }
    },
    {
      "run_id": "cweeval_2026-08-03T...",
      "model_name": "gpt-4",
      "benchmark_type": "cweeval",
      "results": {
        "vulnerability_rate": 0.407,
        "secure_rate": 0.593,
        "vulnerable_samples": 48,
        "total_samples": 119,
        "details": [...]
      },
      "metrics": {
        "vulnerability_rate": 0.407,
        "secure_rate": 0.593,
        "vulnerable_samples": 48,
        "total_samples": 119
      }
    }
  ]
}
```

## Extending the Framework

### Add New Model Provider

1. Create `models/newprovider_model.py`:
```python
from .base_model import BaseModel, ModelResponse

class NewProviderModel(BaseModel):
    def generate(self, prompt, num_samples=1, **kwargs):
        # Implement API calls
        pass
```

2. Update `models/model_factory.py` to register provider

### Add New Benchmark

1. Create `benchmarks/newbench.py` with your benchmark class
2. Update `config.yaml` to enable it
3. Update `benchmark_orchestrator.py` with runner method

### Add Security Checks

Extend `evaluation/code_evaluator.py._check_cwe_patterns()` with new patterns or integrate additional tools like Clang Static Analyzer, FindBugs, etc.

## Requirements & Dependencies

- Python 3.9+
- API keys for models you want to test
- Optional: Docker for sandboxed code execution
- Optional: CodeQL, Semgrep, Bandit for static analysis

## Limitations & Future Work

- CWEval scenarios currently use simulated grading; integrate real CodeQL execution
- Add Docker sandbox for safe code execution
- Expand SecEval to more security domains
- Implement adversarial prompt injection patterns
- Add reasoning/explainability evaluation
- Support for fine-tuning and transfer learning scenarios

## References

- Pearce et al. (2021): "Asleep at the Keyboard? Assessing the Security of GitHub Copilot's Code Contributions" (IEEE S&P 2022)
- MITRE CWE Top 25: https://cwe.mitre.org/top25/
- OpenAI Codex Paper: https://arxiv.org/abs/2107.03374

## License

Research use only. Please cite this work if you use it.

## Contributing

Contributions welcome! Please:
1. Add new models following BaseModel pattern
2. Extend benchmarks with more scenarios
3. Improve evaluation accuracy
4. Add visualization/reporting tools

## Contact

For questions or issues, please open an issue on the repository.

"""
QUICK START GUIDE - LLM Security Benchmark
═══════════════════════════════════════════════════════════════════════════════

Welcome! This guide will get you started with the LLM Security Benchmark system
in 5 minutes.

═══════════════════════════════════════════════════════════════════════════════
INSTALLATION
═══════════════════════════════════════════════════════════════════════════════

1. Clone/download the repository
2. Install Python 3.9+
3. Create virtual environment:
   python3 -m venv venv
   source venv/bin/activate

4. Install dependencies:
   pip install -r requirements.txt

═══════════════════════════════════════════════════════════════════════════════
SETUP API KEYS
═══════════════════════════════════════════════════════════════════════════════

Set environment variables for the models you want to test:

export OPENAI_API_KEY="sk-..."
export GOOGLE_API_KEY="AIzaSy..."
export MISTRAL_API_KEY="..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GROQ_API_KEY="..."
export XAI_API_KEY="..."

Or create a .env file:
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIzaSy...
# etc.

═══════════════════════════════════════════════════════════════════════════════
QUICK START (5 MINUTES)
═══════════════════════════════════════════════════════════════════════════════

Run the example benchmark runner:

python example_runner.py

This will:
✓ Test all configured models
✓ Run SecEval (50 questions)
✓ Run CWEval (20 scenarios)
✓ Generate reports and visualizations
✓ Save results to results/ directory

Expected output:
- results/benchmark_report.txt
- results/benchmark_results.csv
- results/benchmark_results.png (if matplotlib installed)
- results/dashboard.html
- results/*.json (raw data)

═══════════════════════════════════════════════════════════════════════════════
FULL BENCHMARK (COMPREHENSIVE)
═══════════════════════════════════════════════════════════════════════════════

Run the complete benchmark with all questions and scenarios:

python main.py --benchmark all --verbose

Or use specific options:

# Only SecEval
python main.py --benchmark seceval

# Only CWEval
python main.py --benchmark cweeval

# Specific models only
python main.py --models gpt-4 "Claude 3" --benchmark all

# Specific languages
python main.py --benchmark cweeval --languages python c java

# Specific CWEs
python main.py --benchmark cweeval --cwes CWE-89 CWE-79 CWE-787

See README.md for complete command-line options.

═══════════════════════════════════════════════════════════════════════════════
UNDERSTANDING RESULTS
═══════════════════════════════════════════════════════════════════════════════

SECEVAL METRICS:
• Accuracy: % of security knowledge questions answered correctly
  - Baseline: ~50-75% depending on model
  - Higher is better

CWEEVAL METRICS:
• Vulnerability Rate (V%): % of generated code with vulnerabilities
  - Baseline from Pearce et al.: ~40% for Copilot
  - Lower is better ✓
  
• Secure-Pass@k: Probability k-th sample is secure AND functional
  - Balances security with usability
  - Higher is better ✓
  
• Top-1 Security Rate: % of highest-confidence outputs that are secure
  - Critical because users usually accept default
  - Higher is better ✓
  
• SAST Finding Density: Security violations per 100 lines of code
  - Measures violation severity
  - Lower is better ✓

═══════════════════════════════════════════════════════════════════════════════
INTERPRETING COMPARISONS
═══════════════════════════════════════════════════════════════════════════════

Example Benchmark Results:

Model Rankings (by Vulnerability Rate in CWEval)
─────────────────────────────────────────────────
1. Claude 3 Opus:     23.5% vulnerability rate ✓
2. Gemini Flash:      26.8% vulnerability rate  
3. GPT-4:             31.2% vulnerability rate
4. Mistral Large:     38.7% vulnerability rate
5. Llama 3.1 (Groq):  41.0% vulnerability rate

→ Claude produces more secure code than GPT-4
→ Smaller models (Llama) have higher vulnerability
→ Gemini is competitive with larger models

═══════════════════════════════════════════════════════════════════════════════
FILES AND STRUCTURE
═══════════════════════════════════════════════════════════════════════════════

Main Files:
  main.py                    - CLI entry point
  example_runner.py          - Example benchmark runner
  benchmark_orchestrator.py  - Orchestration logic
  config.yaml                - Configuration

Modules:
  models/                    - LLM API connectors
  benchmarks/                - Benchmark frameworks (SecEval, CWEval)
  evaluation/                - Code security evaluator
  utils/                     - Reporting and visualization

Documentation:
  README.md                  - Full documentation
  WORKFLOW.md                - Detailed workflow description
  QUICKSTART.md              - This file

Results:
  results/                   - Output files
  results/*.json             - Raw benchmark data
  results/*.txt              - Text reports
  results/*.csv              - CSV for Excel
  results/*.png              - Matplotlib plots
  results/*.html             - Interactive dashboard

═══════════════════════════════════════════════════════════════════════════════
COMMON WORKFLOWS
═══════════════════════════════════════════════════════════════════════════════

WORKFLOW 1: Test Single Model
─────────────────────────────
python main.py --models "GPT-4" --benchmark all

Result: See how well one specific model performs on both benchmarks


WORKFLOW 2: Compare Vendors
──────────────────────────
python main.py --models gpt-4 "Claude 3" "Gemini Flash" "Mistral Large"

Result: Rank different AI vendors on security


WORKFLOW 3: Language Comparison
──────────────────────────────
python main.py --benchmark cweeval --languages python c java

Result: See which languages have more secure code generation


WORKFLOW 4: CWE Analysis
───────────────────────
python main.py --benchmark cweeval --cwes CWE-89 CWE-79 CWE-787

Result: Focus on top 3 dangerous CWEs (SQL Injection, XSS, Buffer Overflow)


WORKFLOW 5: Track Progress
──────────────────────────
Run benchmarks regularly and compare results:
  - Week 1: Run benchmark → Get baseline
  - Week 2: Update model versions → Run again
  - Compare: See if models improved/regressed

═══════════════════════════════════════════════════════════════════════════════
TROUBLESHOOTING
═══════════════════════════════════════════════════════════════════════════════

ERROR: "API key not found"
→ Set environment variable: export OPENAI_API_KEY="..."
→ Or create .env file in project directory

ERROR: "Rate limit exceeded"
→ Normal for free-tier APIs
→ Reduce num_questions or num_scenarios
→ Wait and retry

ERROR: "Model not available"
→ Check API key is valid
→ Verify model name in config.yaml matches API
→ Try another model

ERROR: "Matplotlib not found"
→ pip install matplotlib seaborn
→ Or skip plots (still get text reports)

═══════════════════════════════════════════════════════════════════════════════
NEXT STEPS
═══════════════════════════════════════════════════════════════════════════════

1. Run quick benchmark:
   python example_runner.py

2. Check results:
   cat results/benchmark_report.txt

3. View dashboard:
   open results/dashboard.html

4. Read full docs:
   cat README.md

5. Understand workflow:
   cat WORKFLOW.md

6. Customize:
   Edit config.yaml to test different models/questions

═══════════════════════════════════════════════════════════════════════════════
REFERENCE: KEY METRICS
═══════════════════════════════════════════════════════════════════════════════

V% (Vulnerability Rate)
  Definition: % of syntactically valid generated code containing ≥1 CWE
  Good: < 30%
  Poor: > 50%
  Source: Pearce et al. (2021)

Pass@k
  Definition: Probability ≥1 of k samples is functionally correct AND secure
  Good: > 0.8
  Poor: < 0.5
  Adapts OpenAI's Pass@k for security

Top-1 Security Rate
  Definition: % of top-ranked (default) suggestions that are non-vulnerable
  Good: > 80%
  Poor: < 50%
  Critical because users usually accept default

SAST Finding Density
  Definition: Security rule violations per 100 lines of code
  Good: < 0.5 violations/100 LOC
  Poor: > 2.0 violations/100 LOC

═══════════════════════════════════════════════════════════════════════════════
SUPPORT & RESOURCES
═══════════════════════════════════════════════════════════════════════════════

- README.md: Complete documentation
- WORKFLOW.md: Detailed technical workflow
- example_runner.py: Working examples
- Pearce et al. (2021): Original paper
  "Asleep at the Keyboard? Assessing the Security of GitHub Copilot's Code"
  IEEE S&P 2022

═══════════════════════════════════════════════════════════════════════════════
"""

print(__doc__)

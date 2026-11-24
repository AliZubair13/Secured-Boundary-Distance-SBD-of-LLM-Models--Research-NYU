"""
WORKFLOW DOCUMENTATION - LLM Security Benchmark System

This document describes the complete workflow for benchmarking LLM models
on security metrics listed in the Pearce et al. (2021) paper.

═══════════════════════════════════════════════════════════════════════════════

SYSTEM ARCHITECTURE
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│                        LLM SECURITY BENCHMARK SYSTEM                        │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   CONFIGURATION │  │   LLM MODELS    │  │   BENCHMARKS    │
│                 │  │                 │  │                 │
│  • config.yaml  │  │  • OpenAI       │  │  • SecEval      │
│  • CWE patterns │  │  • Gemini       │  │  • CWEval       │
│  • API keys     │  │  • Mistral      │  │  • Pearce       │
│  • Metrics      │  │  • Anthropic    │  │                 │
│  • Thresholds   │  │  • Groq         │  │                 │
│                 │  │  • XAI (Grok)   │  │                 │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │ Benchmark Orchestrator│
                  │  (main.py)            │
                  └───────────┬───────────┘
                              │
                ┌─────────────┼─────────────┐
                │             │             │
                ▼             ▼             ▼
         ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
         │ SecEval      │ │ CWEval       │ │ Code         │
         │ Runner       │ │ Runner       │ │ Evaluator    │
         │              │ │              │ │              │
         │ • Load Qs    │ │ • Load Scns. │ │ • Syntax     │
         │ • Query Mdls │ │ • Query Mdls │ │ • Func. Tst  │
         │ • Grade Ans  │ │ • Run Evals  │ │ • Security   │
         │ • Calc Acc   │ │ • Calc Mtrcs │ │ • CWE Check  │
         └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
                │                │               │
                └────────────────┼───────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │ Results Storage │
                        │                 │
                        │ • JSON export   │
                        │ • Raw results   │
                        │ • Metrics       │
                        └────────┬────────┘
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
                ▼                ▼                ▼
         ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
         │   Report     │ │ Visualization│ │  Analysis    │
         │  Generator   │ │              │ │  & Ranking   │
         │              │ │ • Plots      │ │              │
         │ • Text       │ │ • Dashboard  │ │ • Models     │
         │ • CSV        │ │ • HTML       │ │ • Metrics    │
         │ • JSON       │ │              │ │ • Rankings   │
         └──────────────┘ └──────────────┘ └──────────────┘

═══════════════════════════════════════════════════════════════════════════════

DETAILED WORKFLOW: SECEVAL BENCHMARK
═══════════════════════════════════════════════════════════════════════════════

STEP 1: INITIALIZATION
────────────────────
1.1 Load Configuration
    - Read config.yaml
    - Extract model configurations
    - Extract benchmark settings
    - Extract evaluation settings

1.2 Initialize Models
    - For each configured model provider:
      * Create API client (OpenAI, Gemini, etc.)
      * Validate API keys from environment
      * Create model instance via ModelFactory
      * Store in models dictionary

    Example:
    models = {
        "gpt-4": OpenAIModel(...),
        "Claude 3 Opus": AnthropicModel(...),
        "Gemini Flash": GeminiModel(...)
    }

1.3 Initialize Benchmarks
    - Create SecEvalBenchmark instance
    - Load 2,189 security questions from dataset
    - Organize by category:
      * Pentesting (65.3% of questions)
      * Web Security
      * Cryptography (14.3% of sample)
      * Memory Safety
      * API Security

STEP 2: BENCHMARK EXECUTION
────────────────────────────
For each Model M in Models:
  2.1 Reset model statistics
      - Total tokens = 0
      - Request count = 0
  
  2.2 For each Question Q:
      
      A. Prompt Generation
         - Format question with options
         - Add instruction: "Select the correct answer"
         - Template: "{Question}\nOptions:\n{A) ...}\n{B) ...}\n..."
      
      B. Model Query
         - Call M.generate(prompt, num_samples=1)
         - Measure latency (ms)
         - Count tokens used
         - Capture confidence score (if available)
      
      C. Answer Extraction
         - Extract model response
         - Parse to find answer selection (A, B, C, D)
         - Normalize case
      
      D. Correctness Evaluation
         - Compare with Q.correct_answer
         - is_correct = (given_answer == correct_answer)
      
      E. Result Recording
         - Store in results[model][question_id]:
           {
             "correct": bool,
             "answer": str,
             "category": str,
             "difficulty": str,
             "latency_ms": float
           }
      
      F. Statistics Update
         - increment correct_count if is_correct
         - accumulate latency
         - update token count

STEP 3: METRIC CALCULATION (PER MODEL)
───────────────────────────────────────
3.1 Overall Accuracy
    accuracy = correct_count / total_questions
    
3.2 Accuracy by Category
    For each category C:
      accuracy_C = correct_C / total_C
    
    Output:
    {
      "pentesting": 0.653,
      "web_security": 0.582,
      "cryptography": 0.143,
      "memory_safety": 0.498,
      "api_security": 0.521
    }

3.3 Performance Metrics
    - Avg latency: sum(latencies) / count
    - Tokens per question: total_tokens / count
    - Cost (if applicable): tokens * rate

3.4 Difficulty Progression
    - Easy questions: accuracy_easy
    - Medium questions: accuracy_medium
    - Hard questions: accuracy_hard

STEP 4: AGGREGATION & COMPARISON
──────────────────────────────────
4.1 Collect results from all models
4.2 Compute model comparisons:
    - Best/worst model per metric
    - Metric distributions
    - Consistency across categories

4.3 Create results structure:
    results = {
      "gpt-4": {
        "accuracy": 0.752,
        "correct": 1650,
        "total": 2189,
        "by_category": {...},
        "by_difficulty": {...}
      },
      "Claude 3": {...},
      ...
    }

═══════════════════════════════════════════════════════════════════════════════

DETAILED WORKFLOW: CWEEVAL BENCHMARK
═══════════════════════════════════════════════════════════════════════════════

STEP 1: SCENARIO LOADING
────────────────────────
1.1 Load 119 code generation scenarios
1.2 Each scenario contains:
    - scenario_id: unique identifier
    - cwe_id: CWE category (CWE-89, CWE-79, etc.)
    - language: programming language (python, c, java, etc.)
    - prompt: code generation prompt
    - test_cases: functional tests
    - security_checks: CWEs to check for

STEP 2: CODE GENERATION
───────────────────────
For each Model M:
  For each Scenario S:
    
    2.1 Generate Code
        - Call M.generate(S.prompt, num_samples=K)
        - K typically 5 (can be configured)
        - Get K code completions
        - Measure latency and token usage
    
    2.2 Store Completions
        - code_samples = [
            {
              "code": "...",
              "tokens": 127,
              "latency_ms": 342,
              "confidence": 0.85
            },
            ...
          ]

STEP 3: CODE EVALUATION (FOR EACH SAMPLE)
───────────────────────────────────────────
For each code sample C:
  
  3.1 Syntax Validation
      - Attempt to parse/compile code
      - If syntax error → Mark INVALID
      - Store error details
  
  3.2 Functional Testing
      - Run against S.test_cases
      - For each test case:
        * Execute code with inputs
        * Capture output
        * Compare with expected
      - passes_tests = (all tests passed)
      - If any test fails → Mark FUNCTIONAL_FAILURE
  
  3.3 Security Analysis
      
      A. Static Analysis Tools
         - Run Bandit (Python): python vulnerability patterns
         - Run Semgrep: cross-language patterns
         - Run CodeQL: advanced semantic analysis
      
      B. CWE Pattern Matching
         - Check for specific CWE patterns
         - CWE-89 SQL Injection:
           * Pattern: "execute" + string concatenation
           * Pattern: "format(" with unsafe SQL
         - CWE-79 XSS:
           * Pattern: "innerHTML ="
           * Pattern: "eval(" calls
         - CWE-798 Hardcoded Credentials:
           * Pattern: "password = "..."
           * Pattern: "api_key = "..."
      
      C. CWE Classification
         - matched_cwes = [CWE-89, CWE-79, ...]
         - has_vulnerabilities = (len(matched_cwes) > 0)
  
  3.4 Result Storage
      evaluation = {
        "syntax_valid": bool,
        "passes_tests": bool,
        "has_vulnerabilities": bool,
        "vulnerabilities": ["CWE-89", "CWE-79"],
        "sast_findings": [...],
        "quality": CodeQuality.enum
      }

STEP 4: SCENARIO AGGREGATION
─────────────────────────────
For each scenario S with K samples:
  
  4.1 Vulnerability Rate
      vulnerable_count = sum(1 for s in samples if s.has_vulnerabilities)
      vulnerability_rate = vulnerable_count / K
      
      Baseline from Pearce et al: ~40% for Copilot
  
  4.2 Secure-Pass@k
      Probability that at least 1 sample is secure AND correct
      
      For each k in [1, 3, 5, 10]:
        secure_samples = [s for s in samples if not s.has_vulnerabilities]
        pass_at_k = probability_at_least_one_correct(first_k_secure_samples)
  
  4.3 Top-1 Security Rate (TNV%)
      top_sample = max(samples, by_confidence)
      top_1_secure = (not top_sample.has_vulnerabilities)
      
      Important: Users often accept highest-confidence suggestion
  
  4.4 SAST Finding Density
      total_findings = sum(len(s.sast_findings) for s in samples)
      avg_lines_of_code = mean(len(s.code.split('\n')) for s in samples)
      finding_density = total_findings / (avg_lines_of_code / 100)
      
      Units: SAST violations per 100 LOC

STEP 5: MODEL AGGREGATION
──────────────────────────
For model M with 119 scenarios:
  
  5.1 Aggregate Metrics
      vulnerability_rate_model = mean(v_rates for all scenarios)
      secure_pass_at_k_model = mean(pass@k for all scenarios)
      top_1_security_model = mean(tnv for all scenarios)
  
  5.2 By-Language Breakdown
      - Python scenarios:
        * Count: 29
        * Vulnerability rate: X%
      - C scenarios:
        * Count: 25
        * Vulnerability rate: Y%
      - etc.
  
  5.3 By-CWE Breakdown
      - CWE-89 (SQL Injection):
        * Count: 3
        * Model vulnerability: Z%
      - CWE-79 (XSS):
        * Count: 3
        * Model vulnerability: A%
      - etc.

═══════════════════════════════════════════════════════════════════════════════

METRICS SUMMARY
═══════════════════════════════════════════════════════════════════════════════

SECEVAL METRICS:
  • Accuracy (by category)
  • Difficulty progression
  • Answer distribution
  • Category strength/weakness

CWEEVAL METRICS:
  • Vulnerability Rate (V%) - CRITICAL
  • Secure-Pass@k - CRITICAL
  • Top-1 Security Rate (TNV%)
  • SAST Finding Density
  • Functional Correctness Rate
  • Language-specific rates
  • CWE-specific rates

COMBINED METRICS:
  • Security Knowledge vs Code Security correlation
  • Model rankings across benchmarks
  • Benchmark difficulty distribution

═══════════════════════════════════════════════════════════════════════════════

REPORTING & VISUALIZATION
═══════════════════════════════════════════════════════════════════════════════

OUTPUT FILES GENERATED:
  
  1. benchmark_results.json
     - Raw results with full details
     - Used for post-processing
  
  2. benchmark_report.txt
     - Human-readable summary
     - Metrics per model
     - Category breakdowns
  
  3. benchmark_results.csv
     - Tabular format for Excel/analysis
     - Model × Benchmark × Metric
  
  4. ranking_comparison.txt
     - Models ranked by each metric
     - 1st, 2nd, 3rd place per metric
  
  5. benchmark_results.png
     - 4-panel matplotlib figure
     - Bar charts and scatter plots
  
  6. dashboard.html
     - Interactive HTML dashboard
     - Browse results
     - Mobile-friendly design

═══════════════════════════════════════════════════════════════════════════════

EXECUTION EXAMPLES
═══════════════════════════════════════════════════════════════════════════════

1. QUICK BENCHMARK (Testing)
   python example_runner.py
   - 50 SecEval questions per model
   - 20 CWEval scenarios per model
   - Runtime: ~5-15 minutes (depending on API rates)

2. FULL BENCHMARK
   python main.py --benchmark all --verbose
   - 2,189 SecEval questions
   - 119 CWEval scenarios
   - Runtime: Multiple hours

3. SPECIFIC MODELS
   python main.py --models gpt-4 "Gemini Flash" --benchmark all

4. SPECIFIC CWES
   python main.py --benchmark cweeval --cwes CWE-89 CWE-79 CWE-787

5. LANGUAGE FOCUS
   python main.py --benchmark cweeval --languages python c

═══════════════════════════════════════════════════════════════════════════════

ERROR HANDLING & RETRY LOGIC
═══════════════════════════════════════════════════════════════════════════════

Expected Failures:
  - API rate limits
  - Model not available
  - Network timeout
  - API key invalid

Handling Strategy:
  1. Log error with context
  2. Skip to next model/question/scenario
  3. Continue processing
  4. Report count at end
  5. Save partial results

═══════════════════════════════════════════════════════════════════════════════

EXTENDING THE SYSTEM
═══════════════════════════════════════════════════════════════════════════════

Adding a New Model:
  1. Create models/newmodel_model.py
  2. Inherit from BaseModel
  3. Implement generate() and _call_api()
  4. Register in ModelFactory
  5. Update config.yaml

Adding a New Benchmark:
  1. Create benchmarks/newbench.py
  2. Implement question/scenario loading
  3. Create runner in benchmark_orchestrator.py
  4. Update config.yaml

Adding New Metrics:
  1. Extend evaluation/code_evaluator.py
  2. Add calculation in metric functions
  3. Update report generation

═══════════════════════════════════════════════════════════════════════════════
"""

print(__doc__)

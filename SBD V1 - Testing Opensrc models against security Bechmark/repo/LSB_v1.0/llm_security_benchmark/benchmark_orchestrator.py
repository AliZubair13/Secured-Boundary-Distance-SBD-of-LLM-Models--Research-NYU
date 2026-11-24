"""Main benchmarking orchestrator."""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import yaml

from models import ModelFactory, BaseModel
from benchmarks import SecEvalBenchmark, CWEvalBenchmark, SecurityCategory, ProgrammingLanguage
from evaluation import CodeEvaluator

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkRun:
    """Single benchmark run result."""
    run_id: str
    timestamp: str
    model_name: str
    benchmark_type: str  # seceval or cweeval
    results: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)


class LLMSecurityBenchmark:
    """Main orchestrator for LLM security benchmarking."""

    def __init__(self, config_path: str):
        """Initialize benchmark orchestrator.
        
        Args:
            config_path: Path to YAML configuration file
        """
        self.config = self._load_config(config_path)
        self.models: Dict[str, BaseModel] = {}
        self.benchmarks: Dict[str, Any] = {}
        self.evaluator = CodeEvaluator()
        self.runs: List[BenchmarkRun] = []
        
        self._setup_models()
        self._setup_benchmarks()

    def _load_config(self, config_path: str) -> Dict:
        """Load YAML configuration.
        
        Args:
            config_path: Path to config file
            
        Returns:
            Configuration dictionary
        """
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _setup_models(self):
        """Set up LLM model connectors."""
        models_config = self.config.get("models", {})
        
        for provider, config in models_config.items():
            if not config.get("enabled", True):
                continue
            
            for model in config.get("models", []):
                try:
                    model_instance = ModelFactory.create_model(
                        provider=provider,
                        model_name=model.get("name"),
                        model_id=model.get("id"),
                        temperature=config.get("config", {}).get("temperature", 0.7),
                        max_tokens=config.get("config", {}).get("max_tokens", 2048),
                    )
                    self.models[model.get("name")] = model_instance
                    logger.info(f"Loaded model: {model.get('name')}")
                except Exception as e:
                    logger.error(f"Failed to load model {model.get('name')}: {str(e)}")

    def _setup_benchmarks(self):
        """Set up benchmarking frameworks."""
        benchmarks_config = self.config.get("benchmarks", {})
        
        if benchmarks_config.get("seceval", {}).get("enabled", True):
            self.benchmarks["seceval"] = SecEvalBenchmark(
                num_questions=benchmarks_config.get("seceval", {}).get("num_questions", 2189)
            )
            logger.info("Loaded SecEval benchmark")
        
        if benchmarks_config.get("cweeval", {}).get("enabled", True):
            self.benchmarks["cweeval"] = CWEvalBenchmark(
                num_tasks=benchmarks_config.get("cweeval", {}).get("num_tasks", 119)
            )
            logger.info("Loaded CWEval benchmark")

    def run_seceval(
        self,
        model_names: Optional[List[str]] = None,
        category: Optional[SecurityCategory] = None,
        num_questions: Optional[int] = None
    ) -> Dict[str, Any]:
        """Run SecEval benchmark on specified models.
        
        Args:
            model_names: List of model names to test (None = all)
            category: Optional security category to test
            num_questions: Number of questions to use
            
        Returns:
            Results dictionary
        """
        if "seceval" not in self.benchmarks:
            raise ValueError("SecEval benchmark not configured")
        
        benchmark = self.benchmarks["seceval"]
        models_to_test = {
            name: model for name, model in self.models.items()
            if model_names is None or name in model_names
        }
        
        if not models_to_test:
            raise ValueError("No models available for testing")
        
        logger.info(f"Starting SecEval benchmark with {len(models_to_test)} models")
        
        results = {}
        questions = benchmark.get_questions(category=category, count=num_questions)
        
        for model_name, model in models_to_test.items():
            logger.info(f"Testing model: {model_name}")
            model_results = self._evaluate_model_on_seceval(model, questions)
            results[model_name] = model_results
            
            # Store run
            run = BenchmarkRun(
                run_id=f"seceval_{datetime.now().isoformat()}",
                timestamp=datetime.now().isoformat(),
                model_name=model_name,
                benchmark_type="seceval",
                results=model_results,
                metrics=self._calculate_seceval_metrics(model_results)
            )
            self.runs.append(run)
        
        return results

    def _evaluate_model_on_seceval(
        self,
        model: BaseModel,
        questions: List
    ) -> Dict[str, Any]:
        """Evaluate single model on SecEval questions.
        
        Args:
            model: Model to evaluate
            questions: List of questions
            
        Returns:
            Results dictionary
        """
        correct_count = 0
        total = len(questions)
        results_detail = []
        
        for question in questions:
            try:
                # Generate answer from model
                prompt = f"{question.question_text}\n\nOptions:\n"
                for opt in question.options:
                    prompt += f"{opt}\n"
                prompt += "\nProvide only the letter of the correct answer."
                
                response = model.generate(prompt, num_samples=1)
                answer = response[0].response.strip()
                
                # Check correctness
                is_correct = answer.upper() == question.correct_answer.upper()
                if is_correct:
                    correct_count += 1
                
                results_detail.append({
                    "question_id": question.question_id,
                    "category": question.category.value,
                    "correct": is_correct,
                    "answer": answer,
                    "difficulty": question.difficulty
                })
                
            except Exception as e:
                logger.error(f"Error evaluating question {question.question_id}: {str(e)}")
                results_detail.append({
                    "question_id": question.question_id,
                    "correct": False,
                    "error": str(e)
                })
        
        return {
            "accuracy": correct_count / total if total > 0 else 0,
            "correct": correct_count,
            "total": total,
            "details": results_detail
        }

    def run_cweeval(
        self,
        model_names: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        cwe_ids: Optional[List[str]] = None,
        num_scenarios: Optional[int] = None
    ) -> Dict[str, Any]:
        """Run CWEval benchmark on specified models.
        
        Args:
            model_names: List of model names to test
            languages: List of languages to test
            cwe_ids: List of CWE IDs to target
            num_scenarios: Number of scenarios to run
            
        Returns:
            Results dictionary
        """
        if "cweeval" not in self.benchmarks:
            raise ValueError("CWEval benchmark not configured")
        
        benchmark = self.benchmarks["cweeval"]
        models_to_test = {
            name: model for name, model in self.models.items()
            if model_names is None or name in model_names
        }
        
        if not models_to_test:
            raise ValueError("No models available for testing")
        
        logger.info(f"Starting CWEval benchmark with {len(models_to_test)} models")
        
        results = {}
        
        # Get scenarios
        all_scenarios = benchmark.get_scenarios()
        if languages:
            lang_enums = [ProgrammingLanguage[l.upper()] for l in languages]
            all_scenarios = [s for s in all_scenarios if s.language in lang_enums]
        if cwe_ids:
            all_scenarios = [s for s in all_scenarios if s.cwe_id in cwe_ids]
        if num_scenarios:
            all_scenarios = all_scenarios[:num_scenarios]
        
        for model_name, model in models_to_test.items():
            logger.info(f"Testing model: {model_name}")
            model_results = self._evaluate_model_on_cweeval(model, all_scenarios)
            results[model_name] = model_results
            
            run = BenchmarkRun(
                run_id=f"cweeval_{datetime.now().isoformat()}",
                timestamp=datetime.now().isoformat(),
                model_name=model_name,
                benchmark_type="cweeval",
                results=model_results,
                metrics=self._calculate_cweeval_metrics(model_results)
            )
            self.runs.append(run)
        
        return results

    def _evaluate_model_on_cweeval(
        self,
        model: BaseModel,
        scenarios: List
    ) -> Dict[str, Any]:
        """Evaluate single model on CWEval scenarios.
        
        Args:
            model: Model to evaluate
            scenarios: List of code scenarios
            
        Returns:
            Results dictionary
        """
        results_detail = []
        vulnerable_count = 0
        total = len(scenarios)
        
        for scenario in scenarios:
            try:
                # Generate code
                response = model.generate(scenario.prompt, num_samples=1)
                code = response[0].response
                
                # Evaluate code
                evaluation = self.evaluator.evaluate(
                    code=code,
                    language=scenario.language.value,
                    test_cases=scenario.test_cases,
                    cwe_targets=scenario.security_checks
                )
                
                if evaluation.has_vulnerabilities:
                    vulnerable_count += 1
                
                results_detail.append({
                    "scenario_id": scenario.scenario_id,
                    "cwe_id": scenario.cwe_id,
                    "language": scenario.language.value,
                    "vulnerable": evaluation.has_vulnerabilities,
                    "vulnerabilities": evaluation.vulnerabilities,
                    "passes_tests": evaluation.passes_unit_tests,
                })
                
            except Exception as e:
                logger.error(f"Error evaluating scenario {scenario.scenario_id}: {str(e)}")
                results_detail.append({
                    "scenario_id": scenario.scenario_id,
                    "error": str(e)
                })
        
        return {
            "vulnerability_rate": vulnerable_count / total if total > 0 else 0,
            "secure_rate": (total - vulnerable_count) / total if total > 0 else 0,
            "vulnerable_samples": vulnerable_count,
            "total_samples": total,
            "details": results_detail
        }

    def _calculate_seceval_metrics(self, results: Dict) -> Dict[str, Any]:
        """Calculate metrics for SecEval results.
        
        Args:
            results: SecEval results
            
        Returns:
            Metrics dictionary
        """
        return {
            "accuracy": results.get("accuracy", 0),
            "correct_answers": results.get("correct", 0),
            "total_questions": results.get("total", 0),
        }

    def _calculate_cweeval_metrics(self, results: Dict) -> Dict[str, Any]:
        """Calculate metrics for CWEval results.
        
        Args:
            results: CWEval results
            
        Returns:
            Metrics dictionary
        """
        return {
            "vulnerability_rate": results.get("vulnerability_rate", 0),
            "secure_rate": results.get("secure_rate", 0),
            "vulnerable_samples": results.get("vulnerable_samples", 0),
            "total_samples": results.get("total_samples", 0),
        }

    def export_results(self, output_file: str = None) -> str:
        """Export benchmark results to JSON.
        
        Args:
            output_file: Output file path (auto-generated if None)
            
        Returns:
            Path to output file
        """
        if output_file is None:
            output_file = f"results/{datetime.now().isoformat()}_benchmark_results.json"
        
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        results_data = {
            "timestamp": datetime.now().isoformat(),
            "runs": [
                {
                    "run_id": run.run_id,
                    "timestamp": run.timestamp,
                    "model_name": run.model_name,
                    "benchmark_type": run.benchmark_type,
                    "results": run.results,
                    "metrics": run.metrics,
                }
                for run in self.runs
            ]
        }
        
        with open(output_file, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        logger.info(f"Results exported to {output_file}")
        return output_file

    def print_summary(self):
        """Print benchmark summary."""
        print("\n" + "="*80)
        print("LLM SECURITY BENCHMARK SUMMARY")
        print("="*80)
        
        for run in self.runs:
            print(f"\nBenchmark: {run.benchmark_type.upper()}")
            print(f"Model: {run.model_name}")
            print(f"Timestamp: {run.timestamp}")
            print("\nMetrics:")
            for key, value in run.metrics.items():
                if isinstance(value, float):
                    print(f"  {key}: {value:.4f}")
                else:
                    print(f"  {key}: {value}")
        
        print("\n" + "="*80 + "\n")

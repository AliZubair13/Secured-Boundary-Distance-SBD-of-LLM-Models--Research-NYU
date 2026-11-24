"""Example benchmark runner with full workflow."""

import logging
import json
from benchmark_orchestrator import LLMSecurityBenchmark
from utils import ReportGenerator, MetricsAnalyzer, ResultsVisualizer


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('benchmark.log'),
            logging.StreamHandler()
        ]
    )


def run_quick_benchmark():
    """Run a quick benchmark with all models and both benchmarks."""
    logger = logging.getLogger(__name__)
    logger.info("="*80)
    logger.info("STARTING QUICK LLM SECURITY BENCHMARK")
    logger.info("="*80)
    
    try:
        # Initialize benchmark
        benchmark = LLMSecurityBenchmark("config.yaml")
        logger.info(f"Loaded {len(benchmark.models)} models")
        logger.info(f"Available models: {list(benchmark.models.keys())}")
        
        # Run SecEval with limited questions
        logger.info("\n" + "="*80)
        logger.info("Running SecEval Benchmark (Limited)")
        logger.info("="*80)
        seceval_results = benchmark.run_seceval(num_questions=50)
        
        # Run CWEval with limited scenarios
        logger.info("\n" + "="*80)
        logger.info("Running CWEval Benchmark (Limited)")
        logger.info("="*80)
        cweeval_results = benchmark.run_cweeval(num_scenarios=20)
        
        # Export results
        logger.info("\n" + "="*80)
        logger.info("Exporting Results")
        logger.info("="*80)
        output_file = benchmark.export_results()
        logger.info(f"Results saved to: {output_file}")
        
        # Print summary
        benchmark.print_summary()
        
        # Load results for reporting
        with open(output_file, 'r') as f:
            results = json.load(f)
        
        # Generate text report
        logger.info("\n" + "="*80)
        logger.info("Generating Reports")
        logger.info("="*80)
        text_report = ReportGenerator.generate_text_report(results)
        report_file = "results/benchmark_report.txt"
        with open(report_file, 'w') as f:
            f.write(text_report)
        logger.info(f"Text report saved to: {report_file}")
        
        # Generate CSV report
        csv_report = ReportGenerator.generate_csv_report(results)
        csv_file = "results/benchmark_results.csv"
        with open(csv_file, 'w') as f:
            f.write(csv_report)
        logger.info(f"CSV report saved to: {csv_file}")
        
        # Print rankings
        logger.info("\n" + "="*80)
        logger.info("Model Rankings")
        logger.info("="*80)
        MetricsAnalyzer.print_rankings(results)
        
        # Generate visualizations
        logger.info("\n" + "="*80)
        logger.info("Generating Visualizations")
        logger.info("="*80)
        try:
            ResultsVisualizer.create_matplotlib_plots(results)
            logger.info("Matplotlib plots generated")
        except ImportError:
            logger.warning("Matplotlib not available, skipping plots")
        
        ResultsVisualizer.create_html_dashboard(results)
        logger.info("HTML dashboard generated")
        
        logger.info("\n" + "="*80)
        logger.info("BENCHMARK COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"Benchmark failed: {str(e)}", exc_info=True)
        raise


def run_full_benchmark():
    """Run full benchmark with all models and full question/scenario sets."""
    logger = logging.getLogger(__name__)
    logger.info("="*80)
    logger.info("STARTING FULL LLM SECURITY BENCHMARK (This may take a while)")
    logger.info("="*80)
    
    try:
        benchmark = LLMSecurityBenchmark("config.yaml")
        logger.info(f"Loaded {len(benchmark.models)} models")
        
        # Run SecEval with all questions
        logger.info("\n" + "="*80)
        logger.info("Running Full SecEval Benchmark (2189 questions)")
        logger.info("="*80)
        seceval_results = benchmark.run_seceval()
        
        # Run CWEval with all scenarios
        logger.info("\n" + "="*80)
        logger.info("Running Full CWEval Benchmark (119 scenarios)")
        logger.info("="*80)
        cweeval_results = benchmark.run_cweeval()
        
        # Export and report
        output_file = benchmark.export_results()
        benchmark.print_summary()
        
        with open(output_file, 'r') as f:
            results = json.load(f)
        
        ReportGenerator.save_report(
            results,
            "results/full_benchmark_report.txt",
            format="text"
        )
        ReportGenerator.save_report(
            results,
            "results/full_benchmark_results.csv",
            format="csv"
        )
        
        MetricsAnalyzer.print_rankings(results)
        
        try:
            ResultsVisualizer.create_matplotlib_plots(results, "results/plots/full")
        except ImportError:
            pass
        
        ResultsVisualizer.create_html_dashboard(
            results,
            "results/full_benchmark_dashboard.html"
        )
        
        logger.info("\n" + "="*80)
        logger.info("FULL BENCHMARK COMPLETED")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"Full benchmark failed: {str(e)}", exc_info=True)
        raise


def run_specific_models_benchmark(model_names: list, benchmark_type: str = "all"):
    """Run benchmark for specific models only."""
    logger = logging.getLogger(__name__)
    logger.info(f"Running benchmark for specific models: {model_names}")
    logger.info(f"Benchmark type: {benchmark_type}")
    
    try:
        benchmark = LLMSecurityBenchmark("config.yaml")
        
        if benchmark_type in ["seceval", "all"]:
            logger.info("Running SecEval...")
            seceval_results = benchmark.run_seceval(
                model_names=model_names,
                num_questions=100
            )
        
        if benchmark_type in ["cweeval", "all"]:
            logger.info("Running CWEval...")
            cweeval_results = benchmark.run_cweeval(
                model_names=model_names,
                num_scenarios=30
            )
        
        output_file = benchmark.export_results()
        benchmark.print_summary()
        
        with open(output_file, 'r') as f:
            results = json.load(f)
        
        MetricsAnalyzer.print_rankings(results)
        
        logger.info("Benchmark completed for specified models")
        
    except Exception as e:
        logger.error(f"Benchmark failed: {str(e)}", exc_info=True)
        raise


def run_cwe_focused_benchmark(cwe_ids: list):
    """Run CWEval focused on specific CWEs."""
    logger = logging.getLogger(__name__)
    logger.info(f"Running CWE-focused benchmark for: {cwe_ids}")
    
    try:
        benchmark = LLMSecurityBenchmark("config.yaml")
        
        logger.info("Running CWEval with specific CWEs...")
        cweeval_results = benchmark.run_cweeval(
            cwe_ids=cwe_ids,
            num_scenarios=50
        )
        
        output_file = benchmark.export_results()
        benchmark.print_summary()
        
        logger.info("CWE-focused benchmark completed")
        
    except Exception as e:
        logger.error(f"CWE benchmark failed: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    setup_logging()
    
    # Choose which benchmark to run:
    
    # 1. Quick benchmark (recommended for testing)
    run_quick_benchmark()
    
    # 2. Full benchmark (all models, all questions/scenarios - takes hours)
    # run_full_benchmark()
    
    # 3. Benchmark specific models
    # run_specific_models_benchmark(
    #     model_names=["gpt-4", "Gemini Flash"],
    #     benchmark_type="all"
    # )
    
    # 4. CWE-focused benchmark
    # run_cwe_focused_benchmark(
    #     cwe_ids=["CWE-89", "CWE-79", "CWE-787"]
    # )

"""Main entry point for LLM Security Benchmark."""

import logging
import argparse
import sys
from benchmark_orchestrator import LLMSecurityBenchmark
from benchmarks import SecurityCategory


def setup_logging(level=logging.INFO):
    """Setup logging configuration."""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('benchmark.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="LLM Security Benchmark - Test AI models on code security"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to configuration file"
    )
    
    parser.add_argument(
        "--benchmark",
        type=str,
        choices=["seceval", "cweeval", "all"],
        default="all",
        help="Benchmark to run"
    )
    
    parser.add_argument(
        "--models",
        type=str,
        nargs="+",
        help="Specific models to test (space-separated)"
    )
    
    parser.add_argument(
        "--languages",
        type=str,
        nargs="+",
        choices=["python", "c", "java", "javascript", "go"],
        help="Programming languages to test"
    )
    
    parser.add_argument(
        "--cwes",
        type=str,
        nargs="+",
        help="Specific CWE IDs to test"
    )
    
    parser.add_argument(
        "--num-questions",
        type=int,
        help="Number of SecEval questions"
    )
    
    parser.add_argument(
        "--num-scenarios",
        type=int,
        help="Number of CWEval scenarios"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for results"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(log_level)
    
    logger = logging.getLogger(__name__)
    logger.info("Starting LLM Security Benchmark")
    
    try:
        # Initialize benchmark
        benchmark = LLMSecurityBenchmark(args.config)
        logger.info(f"Loaded {len(benchmark.models)} models")
        logger.info(f"Available benchmarks: {list(benchmark.benchmarks.keys())}")
        
        # Run benchmarks
        if args.benchmark in ["seceval", "all"]:
            logger.info("Running SecEval benchmark...")
            seceval_results = benchmark.run_seceval(
                model_names=args.models,
                num_questions=args.num_questions
            )
            logger.info("SecEval benchmark completed")
        
        if args.benchmark in ["cweeval", "all"]:
            logger.info("Running CWEval benchmark...")
            cweeval_results = benchmark.run_cweeval(
                model_names=args.models,
                languages=args.languages,
                cwe_ids=args.cwes,
                num_scenarios=args.num_scenarios
            )
            logger.info("CWEval benchmark completed")
        
        # Export results
        output_file = benchmark.export_results(args.output)
        logger.info(f"Results saved to {output_file}")
        
        # Print summary
        benchmark.print_summary()
        
        logger.info("Benchmark completed successfully")
        
    except Exception as e:
        logger.error(f"Benchmark failed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

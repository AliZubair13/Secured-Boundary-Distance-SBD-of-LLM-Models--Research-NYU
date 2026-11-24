"""Reporting utilities for benchmark results."""

import json
from typing import Dict, List, Any
from datetime import datetime


class ReportGenerator:
    """Generate benchmark reports in various formats."""

    @staticmethod
    def generate_text_report(results: Dict[str, Any]) -> str:
        """Generate human-readable text report.
        
        Args:
            results: Benchmark results dictionary
            
        Returns:
            Formatted text report
        """
        report = []
        report.append("="*80)
        report.append("LLM SECURITY BENCHMARK REPORT")
        report.append("="*80)
        report.append("")
        
        if "timestamp" in results:
            report.append(f"Generated: {results['timestamp']}")
        
        report.append("")
        report.append("-"*80)
        report.append("RESULTS BY MODEL AND BENCHMARK")
        report.append("-"*80)
        report.append("")
        
        for run in results.get("runs", []):
            report.append(f"\nModel: {run['model_name']}")
            report.append(f"Benchmark Type: {run['benchmark_type'].upper()}")
            report.append(f"Timestamp: {run['timestamp']}")
            report.append("")
            
            # Print metrics
            report.append("Metrics:")
            for metric_name, metric_value in run.get("metrics", {}).items():
                formatted_name = metric_name.replace("_", " ").title()
                if isinstance(metric_value, float):
                    report.append(f"  {formatted_name}: {metric_value:.4f}")
                else:
                    report.append(f"  {formatted_name}: {metric_value}")
            
            # Print detailed results if available
            if "results" in run:
                report.append("")
                report.append("Summary:")
                for key, value in run["results"].items():
                    if key != "details":
                        report.append(f"  {key}: {value}")
            
            report.append("")
        
        report.append("-"*80)
        report.append("END OF REPORT")
        report.append("="*80)
        
        return "\n".join(report)

    @staticmethod
    def generate_csv_report(results: Dict[str, Any]) -> str:
        """Generate CSV format report.
        
        Args:
            results: Benchmark results
            
        Returns:
            CSV formatted string
        """
        lines = []
        header = ["Model", "Benchmark", "Metric", "Value"]
        lines.append(",".join(header))
        
        for run in results.get("runs", []):
            model = run["model_name"]
            benchmark = run["benchmark_type"]
            
            for metric_name, metric_value in run.get("metrics", {}).items():
                lines.append(f'"{model}","{benchmark}","{metric_name}",{metric_value}')
        
        return "\n".join(lines)

    @staticmethod
    def generate_comparison_table(results: Dict[str, Any]) -> str:
        """Generate comparison table of models.
        
        Args:
            results: Benchmark results
            
        Returns:
            Formatted comparison table
        """
        from collections import defaultdict
        
        # Group by benchmark type
        benchmarks = defaultdict(list)
        for run in results.get("runs", []):
            benchmarks[run["benchmark_type"]].append(run)
        
        report = []
        
        for benchmark_type, runs in benchmarks.items():
            report.append("")
            report.append(f"\n{benchmark_type.upper()} Benchmark Comparison")
            report.append("-" * 80)
            
            # Get all metric names
            all_metrics = set()
            for run in runs:
                all_metrics.update(run.get("metrics", {}).keys())
            
            # Create header
            header = ["Model"] + sorted(all_metrics)
            col_widths = [20] + [15] * len(all_metrics)
            
            # Print header
            report.append("  ".join(
                f"{h:<{w}}" for h, w in zip(header, col_widths)
            ))
            report.append("-" * 80)
            
            # Print rows
            for run in runs:
                row = [run["model_name"][:20]]
                for metric in sorted(all_metrics):
                    value = run.get("metrics", {}).get(metric, "N/A")
                    if isinstance(value, float):
                        row.append(f"{value:.4f}")
                    else:
                        row.append(str(value))
                
                report.append("  ".join(
                    f"{cell:<{w}}" for cell, w in zip(row, col_widths)
                ))
        
        return "\n".join(report)

    @staticmethod
    def save_report(results: Dict[str, Any], output_file: str, format: str = "text"):
        """Save report to file.
        
        Args:
            results: Benchmark results
            output_file: Output file path
            format: Format type (text, csv, comparison)
        """
        if format == "text":
            content = ReportGenerator.generate_text_report(results)
        elif format == "csv":
            content = ReportGenerator.generate_csv_report(results)
        elif format == "comparison":
            content = ReportGenerator.generate_comparison_table(results)
        else:
            raise ValueError(f"Unknown format: {format}")
        
        with open(output_file, "w") as f:
            f.write(content)


class MetricsAnalyzer:
    """Analyze and summarize benchmark metrics."""

    @staticmethod
    def compare_models(results: Dict[str, Any]) -> Dict[str, Dict]:
        """Compare metrics across models.
        
        Args:
            results: Benchmark results
            
        Returns:
            Comparison dictionary
        """
        comparison = {}
        
        for run in results.get("runs", []):
            model = run["model_name"]
            if model not in comparison:
                comparison[model] = {}
            
            comparison[model][run["benchmark_type"]] = run.get("metrics", {})
        
        return comparison

    @staticmethod
    def calculate_rankings(results: Dict[str, Any]) -> Dict[str, List]:
        """Calculate model rankings by metric.
        
        Args:
            results: Benchmark results
            
        Returns:
            Ranking dictionary
        """
        from collections import defaultdict
        
        rankings = defaultdict(lambda: defaultdict(list))
        
        for run in results.get("runs", []):
            benchmark = run["benchmark_type"]
            model = run["model_name"]
            
            for metric, value in run.get("metrics", {}).items():
                if isinstance(value, (int, float)):
                    rankings[benchmark][metric].append((model, value))
        
        # Sort rankings
        for benchmark in rankings:
            for metric in rankings[benchmark]:
                # Metrics ending in 'rate' or 'accuracy' should be sorted descending
                reverse = any(
                    keyword in metric.lower()
                    for keyword in ["rate", "accuracy", "correct"]
                )
                rankings[benchmark][metric].sort(key=lambda x: x[1], reverse=reverse)
        
        return rankings

    @staticmethod
    def print_rankings(results: Dict[str, Any]):
        """Print model rankings.
        
        Args:
            results: Benchmark results
        """
        rankings = MetricsAnalyzer.calculate_rankings(results)
        
        print("\n" + "="*80)
        print("MODEL RANKINGS")
        print("="*80)
        
        for benchmark, metrics in rankings.items():
            print(f"\n{benchmark.upper()} Benchmark:")
            for metric, ranked_models in metrics.items():
                print(f"\n  {metric}:")
                for rank, (model, value) in enumerate(ranked_models, 1):
                    print(f"    {rank}. {model}: {value:.4f}")
        
        print("\n" + "="*80 + "\n")

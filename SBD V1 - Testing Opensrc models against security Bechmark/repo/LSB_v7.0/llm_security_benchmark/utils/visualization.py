"""Visualization utilities for benchmark results."""

from typing import Dict, List, Any, Optional
import json


class ResultsVisualizer:
    """Generate visualizations for benchmark results."""

    @staticmethod
    def create_matplotlib_plots(results: Dict[str, Any], output_dir: str = "results/plots"):
        """Create matplotlib plots for results.
        
        Args:
            results: Benchmark results
            output_dir: Output directory for plots
        """
        try:
            import matplotlib.pyplot as plt
            import seaborn as sns
            import os
            
            os.makedirs(output_dir, exist_ok=True)
            
            # Parse results
            models = []
            seceval_accuracy = []
            cweeval_vulnerability = []
            cweeval_secure = []
            
            for run in results.get("runs", []):
                model = run["model_name"]
                
                if run["benchmark_type"] == "seceval":
                    models.append(model)
                    seceval_accuracy.append(run["metrics"].get("accuracy", 0))
                
                if run["benchmark_type"] == "cweeval":
                    cweeval_vulnerability.append(run["metrics"].get("vulnerability_rate", 0))
                    cweeval_secure.append(run["metrics"].get("secure_rate", 0))
            
            # Create figure with subplots
            fig, axes = plt.subplots(2, 2, figsize=(14, 10))
            fig.suptitle("LLM Security Benchmark Results", fontsize=16, fontweight="bold")
            
            # Plot 1: SecEval Accuracy
            if models and seceval_accuracy:
                ax = axes[0, 0]
                ax.bar(models, seceval_accuracy, color="steelblue")
                ax.set_ylabel("Accuracy")
                ax.set_title("SecEval: Security Knowledge Accuracy")
                ax.set_ylim([0, 1])
                for i, v in enumerate(seceval_accuracy):
                    ax.text(i, v + 0.02, f"{v:.2%}", ha="center", va="bottom")
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
            
            # Plot 2: CWEval Vulnerability Rate
            if cweeval_vulnerability:
                ax = axes[0, 1]
                unique_models = list(dict.fromkeys(
                    run["model_name"] for run in results.get("runs", [])
                    if run["benchmark_type"] == "cweeval"
                ))
                ax.bar(unique_models, cweeval_vulnerability, color="coral")
                ax.set_ylabel("Vulnerability Rate")
                ax.set_title("CWEval: Code Vulnerability Rate")
                ax.set_ylim([0, 1])
                for i, v in enumerate(cweeval_vulnerability):
                    ax.text(i, v + 0.02, f"{v:.2%}", ha="center", va="bottom")
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
            
            # Plot 3: CWEval Secure Rate
            if cweeval_secure:
                ax = axes[1, 0]
                unique_models = list(dict.fromkeys(
                    run["model_name"] for run in results.get("runs", [])
                    if run["benchmark_type"] == "cweeval"
                ))
                ax.bar(unique_models, cweeval_secure, color="green", alpha=0.7)
                ax.set_ylabel("Secure Code Rate")
                ax.set_title("CWEval: Secure Code Generation Rate")
                ax.set_ylim([0, 1])
                for i, v in enumerate(cweeval_secure):
                    ax.text(i, v + 0.02, f"{v:.2%}", ha="center", va="bottom")
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
            
            # Plot 4: Comparison scatter
            ax = axes[1, 1]
            if seceval_accuracy and cweeval_secure:
                # Match models
                scatter_x = []
                scatter_y = []
                labels = []
                
                for run in results.get("runs", []):
                    if run["benchmark_type"] == "seceval":
                        model = run["model_name"]
                        acc = run["metrics"].get("accuracy", 0)
                        
                        # Find corresponding CWEval result
                        for run2 in results.get("runs", []):
                            if (run2["benchmark_type"] == "cweeval" and 
                                run2["model_name"] == model):
                                secure = run2["metrics"].get("secure_rate", 0)
                                scatter_x.append(acc)
                                scatter_y.append(secure)
                                labels.append(model)
                                break
                
                if scatter_x:
                    ax.scatter(scatter_x, scatter_y, s=200, alpha=0.6, c="purple")
                    for i, label in enumerate(labels):
                        ax.annotate(label, (scatter_x[i], scatter_y[i]), 
                                  xytext=(5, 5), textcoords="offset points", fontsize=8)
                    
                    ax.set_xlabel("SecEval Accuracy")
                    ax.set_ylabel("CWEval Secure Rate")
                    ax.set_title("Security Knowledge vs Code Security")
                    ax.set_xlim([0, 1])
                    ax.set_ylim([0, 1])
            
            plt.tight_layout()
            plt.savefig(f"{output_dir}/benchmark_results.png", dpi=300, bbox_inches="tight")
            print(f"Saved plot to {output_dir}/benchmark_results.png")
            plt.close()
            
        except ImportError:
            print("Matplotlib not available. Install with: pip install matplotlib seaborn")

    @staticmethod
    def create_html_dashboard(results: Dict[str, Any], output_file: str = "results/dashboard.html"):
        """Create interactive HTML dashboard.
        
        Args:
            results: Benchmark results
            output_file: Output HTML file
        """
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>LLM Security Benchmark Dashboard</title>
            <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 20px;
                    background-color: #f5f5f5;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                h1 {
                    color: #333;
                    border-bottom: 3px solid #0066cc;
                    padding-bottom: 10px;
                }
                h2 {
                    color: #555;
                    margin-top: 30px;
                }
                .metrics-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    margin: 20px 0;
                }
                .metric-card {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 8px;
                    text-align: center;
                }
                .metric-card h3 {
                    margin: 0 0 10px 0;
                    font-size: 14px;
                }
                .metric-card .value {
                    font-size: 28px;
                    font-weight: bold;
                }
                .plot-container {
                    margin: 30px 0;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    padding: 10px;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                }
                th, td {
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }
                th {
                    background-color: #0066cc;
                    color: white;
                }
                tr:hover {
                    background-color: #f5f5f5;
                }
                .timestamp {
                    color: #999;
                    font-size: 12px;
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔒 LLM Security Benchmark Dashboard</h1>
                <p>Comprehensive security evaluation of Large Language Models on code generation tasks.</p>
        """
        
        # Add timestamp
        if "timestamp" in results:
            html_content += f'<p class="timestamp">Generated: {results["timestamp"]}</p>'
        
        # Add metrics summary
        html_content += '<h2>Metrics Summary</h2>'
        html_content += '<div class="metrics-grid">'
        
        models_count = len(set(run["model_name"] for run in results.get("runs", [])))
        seceval_runs = sum(1 for run in results.get("runs", []) if run["benchmark_type"] == "seceval")
        cweeval_runs = sum(1 for run in results.get("runs", []) if run["benchmark_type"] == "cweeval")
        
        html_content += f'''
            <div class="metric-card">
                <h3>Models Tested</h3>
                <div class="value">{models_count}</div>
            </div>
            <div class="metric-card">
                <h3>SecEval Runs</h3>
                <div class="value">{seceval_runs}</div>
            </div>
            <div class="metric-card">
                <h3>CWEval Runs</h3>
                <div class="value">{cweeval_runs}</div>
            </div>
        '''
        
        html_content += '</div>'
        
        # Add results table
        html_content += '<h2>Detailed Results</h2>'
        html_content += '<table><tr><th>Model</th><th>Benchmark</th><th>Metrics</th></tr>'
        
        for run in results.get("runs", []):
            metrics_str = ", ".join(
                f"{k}: {v:.4f}" if isinstance(v, float) else f"{k}: {v}"
                for k, v in run.get("metrics", {}).items()
            )
            html_content += f'''
                <tr>
                    <td>{run["model_name"]}</td>
                    <td>{run["benchmark_type"].upper()}</td>
                    <td>{metrics_str}</td>
                </tr>
            '''
        
        html_content += '</table>'
        
        html_content += '</div></body></html>'
        
        with open(output_file, "w") as f:
            f.write(html_content)
        
        print(f"Saved HTML dashboard to {output_file}")

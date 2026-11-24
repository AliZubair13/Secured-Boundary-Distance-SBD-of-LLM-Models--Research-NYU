"""Benchmarking frameworks.

SecEvalBenchmark / CWEvalBenchmark are small in-repo stubs, not the
published SEC-bench or CWEval datasets. The live runner uses
compact_security_suite instead, with metric names that match the protocol.
"""

from .seceval import SecEvalBenchmark, SecurityQuestion, SecurityAnswer, SecurityCategory
from .cweeval import CWEvalBenchmark, CodeScenario, GeneratedCode, ProgrammingLanguage

__all__ = [
    "SecEvalBenchmark",
    "SecurityQuestion",
    "SecurityAnswer",
    "SecurityCategory",
    "CWEvalBenchmark",
    "CodeScenario",
    "GeneratedCode",
    "ProgrammingLanguage",
]

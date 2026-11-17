"""Autonomous AI Coding Agent Evaluation Benchmark System."""
from evaluation.dataset import (
    BenchmarkTask,
    BenchmarkCategory,
    get_all_tasks,
    get_tasks_by_category,
    get_task_by_id,
)
from evaluation.harness import EvaluationHarness, BenchmarkEvaluationResult
from evaluation.metrics import (
    TaskAttemptRecord,
    MetricsReport,
    EvaluationMetricsCalculator,
    compute_pass_at_k,
)

__all__ = [
    "BenchmarkTask",
    "BenchmarkCategory",
    "get_all_tasks",
    "get_tasks_by_category",
    "get_task_by_id",
    "EvaluationHarness",
    "BenchmarkEvaluationResult",
    "TaskAttemptRecord",
    "MetricsReport",
    "EvaluationMetricsCalculator",
    "compute_pass_at_k",
]

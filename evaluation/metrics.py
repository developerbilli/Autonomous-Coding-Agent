"""Evaluation Metrics Framework for Autonomous AI Coding Agents.

Implements rigorous measurement across:
1. Task Success Rate (TSR)
2. Test Pass Rate (TPR)
3. Regression Rate (RR)
4. Review Rejection Rate (RRR)
5. Retry Rate (RetR)
6. Recovery Rate (RecR)
7. Unrelated Change Rate (UCR)
8. Cost per Task (CPT)
9. Time per Task (TPT - Mean, p50, p90, p95)
10. Pass@1 (First-attempt zero-remediation success)
11. Pass@k (Unbiased combinatorial estimator across n independent samples)
"""

import math
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


# Standard commercial pricing per 1,000,000 tokens (e.g., Gemini 1.5/2.0 Flash / Pro blend)
DEFAULT_INPUT_COST_PER_M = 0.35   # $0.35 per 1M input tokens
DEFAULT_OUTPUT_COST_PER_M = 1.05  # $1.05 per 1M output tokens
DEFAULT_SANDBOX_CPU_SEC_COST = 0.00002  # ~$0.072/hr compute container pricing


@dataclass
class TaskAttemptRecord:
    """Record of an individual attempt on a benchmark task."""
    task_id: str
    category: str
    attempt_index: int  # 1-indexed attempt number
    overall_pass: bool  # Strict conjunction: is_task_successful AND hidden_tests_passed
    iteration_count: int  # Iterations taken within this attempt (1 = solved on first try)
    baseline_tests_passed: bool
    hidden_tests_passed: bool
    baseline_regressions_count: int = 0
    candidate_regressions_count: int = 0      # Regressions detected in candidate patches before admission
    candidate_regressions_rejected: int = 0   # Candidate patches rejected by the Sovereign Verifier gate
    candidate_regressions_repaired: int = 0   # Regressive candidate patches repaired by remediation
    admitted_regressions_count: int = 0       # Regressions in the final admitted patch
    unrelated_files_count: int = 0
    review_rejected: bool = False
    review_score: Optional[float] = None
    encountered_failure: bool = False  # Did an intermediate test/review fail before self-healing?
    recovered_from_failure: bool = False  # Did it self-heal from an intermediate failure?
    duration_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    sandbox_seconds: float = 0.0


@dataclass
class MetricsReport:
    """Consolidated mathematical scorecard across benchmark evaluations."""
    total_tasks: int
    total_attempts: int

    # 1. Operational & Quality Rates (Percentages 0.0 - 100.0%)
    task_success_rate: float                 # Percentage of tasks passed
    test_pass_rate: float                    # Percentage of tests passed
    candidate_patch_regression_rate: float # Pre-gate: % of tasks where candidate patches broke baseline tests (CPRR)
    admitted_patch_regression_rate: float  # Post-gate: % of admitted patches that broke baseline tests (APRR)
    regressive_candidates_rejected_count: int # Count of regressive candidate patches blocked by admission gate
    regressive_candidates_repaired_count: int # Count of regressive candidate patches repaired before release
    baseline_patch_regression_rate: float  # Backwards-compatible alias for admitted_patch_regression_rate
    regression_rate: float                # Backwards-compatible alias for admitted_patch_regression_rate
    review_rejection_rate: float          # Percentage of attempts where Reviewer flagged blocking defects
    retry_rate: float                     # Percentage of attempts requiring >1 iteration
    recovery_rate: float                  # Percentage of attempts that self-healed after intermediate failure
    unrelated_change_rate: float          # Percentage of attempts modifying files outside task scope

    # 2. Conventional Pass@1, Zero-Remediation, and Pass@k
    zero_remediation_success_rate: float  # Percentage of tasks solved on attempt 1 with 0 remediation iterations
    pass_at_1: float                      # Conventional Pass@1: unbiased single-attempt success rate (c / n)
    pass_at_k: Dict[int, float]           # Conventional Pass@k for k where sampled runs n >= k
    samples_per_task: int                 # Number of independent attempts evaluated per task (n)

    # 3. Cost Metrics
    avg_cost_per_task: float       # In USD
    total_cost_usd: float
    avg_prompt_tokens: float
    avg_completion_tokens: float

    # 4. Latency Metrics
    avg_duration_seconds: float
    p50_duration_seconds: float
    p90_duration_seconds: float
    p95_duration_seconds: float

    # 5. Category Breakdown
    category_metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)


def compute_pass_at_k(n: int, c: int, k: int) -> float:
    """Computes the unbiased pass@k estimator from Chen et al. (2021).
    n: total number of independent attempts sampled per task
    c: number of correct attempts (c <= n)
    k: target evaluation budget (k <= n)

    Formula: 1 - prod_{j=1}^k (n - c - j + 1) / (n - j + 1)
    """
    if n <= 0 or k <= 0 or k > n or c <= 0:
        return 0.0
    if n - c < k:
        return 100.0

    # Numerically stable product calculation
    prod = 1.0
    for j in range(1, k + 1):
        prod *= (n - c - j + 1) / (n - j + 1)
    return round((1.0 - prod) * 100.0, 2)


class EvaluationMetricsCalculator:
    """Calculates all 9 operational metrics plus Pass@1 and Pass@k."""

    def __init__(
        self,
        input_cost_per_m: float = DEFAULT_INPUT_COST_PER_M,
        output_cost_per_m: float = DEFAULT_OUTPUT_COST_PER_M,
        sandbox_cpu_cost: float = DEFAULT_SANDBOX_CPU_SEC_COST,
    ):
        self.input_cost_per_m = input_cost_per_m
        self.output_cost_per_m = output_cost_per_m
        self.sandbox_cpu_cost = sandbox_cpu_cost

    def calculate_attempt_cost(self, prompt_tokens: int, completion_tokens: int, sandbox_sec: float) -> float:
        """Calculates exact financial cost for a single task run."""
        llm_cost = (
            (prompt_tokens / 1_000_000.0) * self.input_cost_per_m
            + (completion_tokens / 1_000_000.0) * self.output_cost_per_m
        )
        sandbox_cost = sandbox_sec * self.sandbox_cpu_cost
        return round(llm_cost + sandbox_cost, 6)

    def compute_metrics(
        self,
        attempts: List[TaskAttemptRecord],
        k_values: List[int] = [1, 3, 5],
    ) -> MetricsReport:
        """Aggregates a collection of task attempt records into a comprehensive metrics report."""
        if not attempts:
            return MetricsReport(
                total_tasks=0,
                total_attempts=0,
                task_success_rate=0.0,
                test_pass_rate=0.0,
                candidate_patch_regression_rate=0.0,
                admitted_patch_regression_rate=0.0,
                regressive_candidates_rejected_count=0,
                regressive_candidates_repaired_count=0,
                baseline_patch_regression_rate=0.0,
                regression_rate=0.0,
                review_rejection_rate=0.0,
                retry_rate=0.0,
                recovery_rate=0.0,
                unrelated_change_rate=0.0,
                pass_at_1=0.0,
                pass_at_k={k: 0.0 for k in k_values},
                avg_cost_per_task=0.0,
                total_cost_usd=0.0,
                avg_prompt_tokens=0.0,
                avg_completion_tokens=0.0,
                avg_duration_seconds=0.0,
                p50_duration_seconds=0.0,
                p90_duration_seconds=0.0,
                p95_duration_seconds=0.0,
            )

        total_attempts = len(attempts)

        # Unique task grouping
        task_map: Dict[str, List[TaskAttemptRecord]] = {}
        for a in attempts:
            task_map.setdefault(a.task_id, []).append(a)
        total_unique_tasks = len(task_map)

        # 1. Task Success Rate (TSR)
        # Unique tasks where at least the first/latest attempt succeeded
        unique_tasks_passed = sum(1 for tid, atts in task_map.items() if any(a.overall_pass for a in atts))
        tsr = (unique_tasks_passed / total_unique_tasks * 100.0) if total_unique_tasks > 0 else 0.0

        # 2. Test Pass Rate (TPR)
        total_test_evals = sum(1 for a in attempts if a.baseline_tests_passed and a.hidden_tests_passed)
        tpr = (total_test_evals / total_attempts * 100.0) if total_attempts > 0 else 0.0

        # 3. Candidate vs Admitted Regression Rates
        # (a) Candidate-Patch Regression Rate (CPRR): How often candidate patches introduced regressions before rejection
        candidate_reg_tasks = sum(1 for a in attempts if getattr(a, "candidate_regressions_count", 0) > 0 or a.baseline_regressions_count > 0)
        cprr = (candidate_reg_tasks / total_attempts * 100.0) if total_attempts > 0 else 0.0

        # (b) Admitted-Patch Regression Rate (APRR): How often patches passing the admission gate contain regressions
        def _get_admitted_regressions(a: TaskAttemptRecord) -> int:
            if getattr(a, "admitted_regressions_count", 0) > 0:
                return a.admitted_regressions_count
            if getattr(a, "candidate_regressions_repaired", 0) > 0 or getattr(a, "candidate_regressions_rejected", 0) > 0:
                return 0
            return getattr(a, "baseline_regressions_count", 0)

        admitted_reg_tasks = sum(1 for a in attempts if _get_admitted_regressions(a) > 0)
        aprr = (admitted_reg_tasks / total_attempts * 100.0) if total_attempts > 0 else 0.0

        # (c) Intercepted & Repaired Candidates
        reg_rejected = sum(getattr(a, "candidate_regressions_rejected", 0) for a in attempts)
        reg_repaired = sum(getattr(a, "candidate_regressions_repaired", 0) for a in attempts)

        # 4. Review Rejection Rate (RRR)
        review_rejections = sum(1 for a in attempts if a.review_rejected)
        rrr = (review_rejections / total_attempts * 100.0) if total_attempts > 0 else 0.0

        # 5. Retry Rate (RetR)
        retries_count = sum(1 for a in attempts if a.iteration_count > 1)
        retry_rate = (retries_count / total_attempts * 100.0) if total_attempts > 0 else 0.0

        # 6. Recovery Rate (RecR)
        # Of tasks that encountered an intermediate failure, what percentage recovered to pass?
        encountered_failures = [a for a in attempts if a.encountered_failure]
        if encountered_failures:
            recovered_count = sum(1 for a in encountered_failures if a.recovered_from_failure and a.overall_pass)
            rec_rate = (recovered_count / len(encountered_failures) * 100.0)
        else:
            rec_rate = 100.0 if tsr > 0 else 0.0

        # 7. Unrelated Change Rate (UCR)
        unrelated_changes = sum(1 for a in attempts if a.unrelated_files_count > 0)
        ucr = (unrelated_changes / total_attempts * 100.0) if total_attempts > 0 else 0.0

        # 8. Zero-Remediation Success Rate (Custom agentic metric)
        # Succeeded on attempt 1 with ZERO remediation retries (iteration_count <= 1 and not review_rejected)
        zero_remediation_passes = 0
        for tid, atts in task_map.items():
            first_att = next((a for a in atts if a.attempt_index == 1), atts[0])
            if first_att.overall_pass and first_att.iteration_count <= 1 and not first_att.review_rejected:
                zero_remediation_passes += 1
        zero_remediation_rate = (zero_remediation_passes / total_unique_tasks * 100.0) if total_unique_tasks > 0 else 0.0

        # 9. Conventional Pass@1 (Unbiased single-attempt pass rate: c / n)
        # For each task i with n_i samples and c_i successes, E[pass@1] = c_i / n_i
        task_pass_at_1_values = []
        for tid, atts in task_map.items():
            n_i = len(atts)
            c_i = sum(1 for a in atts if a.overall_pass)
            task_pass_at_1_values.append((c_i / n_i) * 100.0 if n_i > 0 else 0.0)
        pass_at_1 = (sum(task_pass_at_1_values) / len(task_pass_at_1_values)) if task_pass_at_1_values else 0.0

        # 10. Pass@k Estimation (Chen et al. 2021)
        # Strictly valid ONLY when n >= k independent attempts were sampled per task
        pass_at_k_results: Dict[int, float] = {}
        # Determine minimum samples per task
        min_samples = min((len(atts) for atts in task_map.values()), default=1)
        max_samples = max((len(atts) for atts in task_map.values()), default=1)
        
        for k in k_values:
            eligible_task_scores = []
            for tid, atts in task_map.items():
                n_i = len(atts)
                c_i = sum(1 for a in atts if a.overall_pass)
                if n_i >= k:
                    eligible_task_scores.append(compute_pass_at_k(n_i, c_i, k))
            # Only report Pass@k if at least one task had n_i >= k attempts
            if eligible_task_scores:
                pass_at_k_results[k] = round(sum(eligible_task_scores) / len(eligible_task_scores), 2)

        # 11. Cost Accounting
        costs = [
            self.calculate_attempt_cost(a.prompt_tokens, a.completion_tokens, a.sandbox_seconds)
            for a in attempts
        ]
        total_cost = sum(costs)
        avg_cost = total_cost / total_attempts if total_attempts > 0 else 0.0

        avg_prompt_tok = sum(a.prompt_tokens for a in attempts) / total_attempts if total_attempts > 0 else 0.0
        avg_comp_tok = sum(a.completion_tokens for a in attempts) / total_attempts if total_attempts > 0 else 0.0

        # 12. Latency & Quantiles
        durations = sorted(a.duration_seconds for a in attempts)
        avg_duration = sum(durations) / total_attempts if total_attempts > 0 else 0.0

        def _quantile(data: List[float], q: float) -> float:
            if not data:
                return 0.0
            idx = int(math.ceil(q * len(data))) - 1
            return round(data[max(0, min(idx, len(data) - 1))], 3)

        p50 = _quantile(durations, 0.50)
        p90 = _quantile(durations, 0.90)
        p95 = _quantile(durations, 0.95)

        # 13. Category Breakdown
        categories = set(a.category for a in attempts)
        cat_metrics: Dict[str, Dict[str, Any]] = {}
        for cat in categories:
            cat_atts = [a for a in attempts if a.category == cat]
            c_unique = len(set(a.task_id for a in cat_atts))
            c_passed = sum(1 for a in cat_atts if a.overall_pass)
            c_zero_remed = sum(1 for a in cat_atts if a.overall_pass and a.iteration_count <= 1 and not a.review_rejected)
            cat_metrics[cat] = {
                "tasks": c_unique,
                "success_rate": round(c_passed / len(cat_atts) * 100.0, 1) if cat_atts else 0.0,
                "zero_remediation_rate": round(c_zero_remed / len(cat_atts) * 100.0, 1) if cat_atts else 0.0,
                "pass_at_1": round(c_passed / len(cat_atts) * 100.0, 1) if cat_atts else 0.0,
                "avg_duration": round(sum(a.duration_seconds for a in cat_atts) / len(cat_atts), 2) if cat_atts else 0.0,
            }

        return MetricsReport(
            total_tasks=total_unique_tasks,
            total_attempts=total_attempts,
            task_success_rate=round(tsr, 2),
            test_pass_rate=round(tpr, 2),
            candidate_patch_regression_rate=round(cprr, 2),
            admitted_patch_regression_rate=round(aprr, 2),
            regressive_candidates_rejected_count=reg_rejected,
            regressive_candidates_repaired_count=reg_repaired,
            baseline_patch_regression_rate=round(aprr, 2),
            regression_rate=round(aprr, 2),
            review_rejection_rate=round(rrr, 2),
            retry_rate=round(retry_rate, 2),
            recovery_rate=round(rec_rate, 2),
            unrelated_change_rate=round(ucr, 2),
            zero_remediation_success_rate=round(zero_remediation_rate, 2),
            pass_at_1=round(pass_at_1, 2),
            pass_at_k=pass_at_k_results,
            samples_per_task=max_samples,
            avg_cost_per_task=round(avg_cost, 4),
            total_cost_usd=round(total_cost, 4),
            avg_prompt_tokens=round(avg_prompt_tok, 1),
            avg_completion_tokens=round(avg_comp_tok, 1),
            avg_duration_seconds=round(avg_duration, 2),
            p50_duration_seconds=p50,
            p90_duration_seconds=p90,
            p95_duration_seconds=p95,
            category_metrics=cat_metrics,
        )

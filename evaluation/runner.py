"""CLI and Programmatic Runner for Benchmark Evaluation Suite.

Executes benchmark tasks, aggregates telemetry across categories, performs historical
run comparisons, and generates comparative scorecards in terminal, JSON, and Markdown formats.
"""

import sys
import json
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

from evaluation.dataset import (
    BenchmarkTask,
    BenchmarkCategory,
    get_all_tasks,
    get_tasks_by_category,
    get_task_by_id,
)
from evaluation.harness import EvaluationHarness, BenchmarkEvaluationResult
from evaluation.comparison import (
    RunHistoryManager,
    compare_runs,
    render_comparison_markdown,
    ComparisonDelta,
)


def run_benchmark_suite(
    tasks: List[BenchmarkTask],
    agent_mode: str = "multi_agent",
    demo_mode: bool = False,
    max_iterations: int = 3,
    samples_per_task: int = 1,
    output_json: Optional[str] = None,
    output_markdown: Optional[str] = None,
    compare_target: Optional[str] = None,
    save_history: bool = True,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Runs a suite of benchmark tasks and generates an aggregated scorecard."""
    harness = EvaluationHarness()
    results: List[BenchmarkEvaluationResult] = []
    attempt_records = []

    from evaluation.metrics import TaskAttemptRecord, EvaluationMetricsCalculator

    total_runs_expected = len(tasks) * samples_per_task
    if verbose:
        print("=" * 80)
        print(f"  🧪 RUNNING BENCHMARK EVALUATION SUITE ({len(tasks)} Tasks | {samples_per_task} Sample(s)/Task | Mode: {agent_mode})")
        print("=" * 80)

    t0_suite = time.time()
    run_counter = 0

    for idx, task in enumerate(tasks, 1):
        for sample_idx in range(1, samples_per_task + 1):
            run_counter += 1
            sample_suffix = f" (Sample {sample_idx}/{samples_per_task})" if samples_per_task > 1 else ""
            if verbose:
                print(f"[{run_counter:02d}/{total_runs_expected:02d}] Evaluating {task.task_id}{sample_suffix} ({task.title})...", end=" ", flush=True)

            res = harness.evaluate_task(
                task=task,
                agent_mode=agent_mode,
                demo_mode=demo_mode,
                max_iterations=max_iterations,
            )
            results.append(res)

            attempt_records.append(
                TaskAttemptRecord(
                    task_id=res.task_id,
                    category=res.category,
                    attempt_index=sample_idx,
                    overall_pass=res.overall_pass,
                    iteration_count=res.iteration_count + 1,
                    baseline_tests_passed=res.baseline_tests_passed,
                    hidden_tests_passed=res.hidden_tests_passed,
                    baseline_regressions_count=res.baseline_regressions_count,
                    unrelated_files_count=res.unrelated_files_count,
                    review_rejected=res.review_rejected,
                    review_score=res.review_quality_score,
                    encountered_failure=res.encountered_failure,
                    recovered_from_failure=res.recovered_from_failure,
                    duration_seconds=res.duration_seconds,
                    prompt_tokens=res.prompt_tokens,
                    completion_tokens=res.completion_tokens,
                    sandbox_seconds=getattr(res, "sandbox_seconds", 0.0),
                )
            )

            if verbose:
                status_icon = "✅ PASS" if res.overall_pass else "❌ FAIL"
                print(f"{status_icon} ({res.duration_seconds:.2f}s, iter={res.iteration_count})")

    total_duration = time.time() - t0_suite

    # Only request k values where k <= samples_per_task to ensure statistical validity
    valid_k_values = [k for k in [1, 3, 5] if k <= samples_per_task]
    if not valid_k_values:
        valid_k_values = [1]

    calc = EvaluationMetricsCalculator()
    metrics_report = calc.compute_metrics(attempt_records, k_values=valid_k_values)

    total_tasks_count = len(tasks)
    passed_tasks_count = sum(1 for t in tasks if any(r.overall_pass for r in results if r.task_id == t.task_id))
    pass_rate = (passed_tasks_count / total_tasks_count * 100.0) if total_tasks_count > 0 else 0.0

    category_stats: Dict[str, Dict[str, Any]] = {}
    for cat in BenchmarkCategory:
        cat_tasks = [t for t in tasks if t.category.value == cat.value]
        if cat_tasks:
            cat_results = [r for r in results if r.category == cat.value]
            cat_passed_tasks = sum(1 for t in cat_tasks if any(r.overall_pass for r in cat_results if r.task_id == t.task_id))
            category_stats[cat.value] = {
                "total": len(cat_tasks),
                "passed": cat_passed_tasks,
                "pass_rate": (cat_passed_tasks / len(cat_tasks) * 100.0) if cat_tasks else 0.0,
                "avg_duration": sum(r.duration_seconds for r in cat_results) / len(cat_results) if cat_results else 0.0,
            }

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent_mode": agent_mode,
        "total_tasks": total_tasks_count,
        "samples_per_task": samples_per_task,
        "total_attempts": len(attempt_records),
        "passed_tasks": passed_tasks_count,
        "pass_rate_pct": round(pass_rate, 2),
        "total_duration_seconds": round(total_duration, 2),
        "metrics": {
            "task_success_rate": metrics_report.task_success_rate,
            "test_pass_rate": metrics_report.test_pass_rate,
            "candidate_patch_regression_rate": metrics_report.candidate_patch_regression_rate,
            "admitted_patch_regression_rate": metrics_report.admitted_patch_regression_rate,
            "regressive_candidates_rejected_count": metrics_report.regressive_candidates_rejected_count,
            "regressive_candidates_repaired_count": metrics_report.regressive_candidates_repaired_count,
            "baseline_patch_regression_rate": metrics_report.baseline_patch_regression_rate,
            "regression_rate": metrics_report.regression_rate,
            "review_rejection_rate": metrics_report.review_rejection_rate,
            "retry_rate": metrics_report.retry_rate,
            "recovery_rate": metrics_report.recovery_rate,
            "unrelated_change_rate": metrics_report.unrelated_change_rate,
            "zero_remediation_success_rate": metrics_report.zero_remediation_success_rate,
            "pass_at_1": metrics_report.pass_at_1,
            "pass_at_k": metrics_report.pass_at_k,
            "samples_per_task": metrics_report.samples_per_task,
            "avg_cost_per_task_usd": metrics_report.avg_cost_per_task,
            "total_cost_usd": metrics_report.total_cost_usd,
            "avg_duration_seconds": metrics_report.avg_duration_seconds,
            "p50_duration_seconds": metrics_report.p50_duration_seconds,
            "p90_duration_seconds": metrics_report.p90_duration_seconds,
            "p95_duration_seconds": metrics_report.p95_duration_seconds,
        },
        "category_breakdown": category_stats,
        "tasks": [r.to_dict() for r in results],
    }

    # Historical Comparison and Run Persistence
    history_mgr = RunHistoryManager()
    comparison_delta: Optional[ComparisonDelta] = None

    if compare_target:
        if compare_target.lower() == "latest":
            prev_run = history_mgr.get_latest_run()
        else:
            prev_run = history_mgr.load_run(compare_target)

        if prev_run:
            comparison_delta = compare_runs(summary, prev_run)
            summary["comparison"] = comparison_delta.to_dict()

    if save_history:
        history_mgr.save_run(summary)

    if verbose:
        pass_at_k_str = (
            ", ".join(f"k={k}: {v}%" for k, v in metrics_report.pass_at_k.items())
            if metrics_report.pass_at_k
            else "N/A (requires n >= k independent samples)"
        )
        print()
        print("=" * 80)
        print("  📊 BENCHMARK OPERATIONAL & QUALITY METRICS SCORECARD")
        print("=" * 80)
        print(f"  Task Success Rate (TSR)            : {metrics_report.task_success_rate}%")
        print(f"  Zero-Remediation Rate (ZRSR)       : {metrics_report.zero_remediation_success_rate}% (0 remediation retries)")
        print(f"  Conventional Pass@1 (c / n)        : {metrics_report.pass_at_1}% (unbiased single-attempt success)")
        print(f"  Pass@k Estimator (n={metrics_report.samples_per_task} sample/task)  : {pass_at_k_str}")
        print(f"  Test Pass Rate (TPR)               : {metrics_report.test_pass_rate}%")
        print(f"  Candidate Regression Rate (CPRR)   : {metrics_report.candidate_patch_regression_rate}% (pre-gate candidate patches)")
        print(f"  Admitted Regression Rate (APRR)    : {metrics_report.admitted_patch_regression_rate}% (post-verifier admitted patches)")
        print(f"  Regressive Candidates Intercepted  : {metrics_report.regressive_candidates_rejected_count} rejected / {metrics_report.regressive_candidates_repaired_count} repaired")
        print(f"  Review Rejection Rate (RRR)        : {metrics_report.review_rejection_rate}%")
        print(f"  Retry Rate (RetR)                  : {metrics_report.retry_rate}%")
        print(f"  Recovery Rate (RecR)               : {metrics_report.recovery_rate}%")
        print(f"  Unrelated Change Rate (UCR)        : {metrics_report.unrelated_change_rate}%")
        print(f"  Average Cost per Task              : ${metrics_report.avg_cost_per_task:.4f}")
        print(f"  Latency Profile (s)                : Mean={metrics_report.avg_duration_seconds:.2f}s | p50={metrics_report.p50_duration_seconds:.2f}s | p95={metrics_report.p95_duration_seconds:.2f}s")
        print("=" * 80)
        print(f"{'Category':<25} | {'Tasks':<7} | {'Passed':<7} | {'Pass Rate':<10} | {'Avg Time':<10}")
        print("-" * 80)
        for cat_name, stats in category_stats.items():
            print(
                f"{cat_name:<25} | "
                f"{stats['total']:<7} | "
                f"{stats['passed']:<7} | "
                f"{stats['pass_rate']:>6.1f}%   | "
                f"{stats['avg_duration']:>6.2f}s"
            )
        print("-" * 80)
        print(
            f"{'OVERALL':<25} | "
            f"{total_tasks_count:<7} | "
            f"{passed_tasks_count:<7} | "
            f"{pass_rate:>6.1f}%   | "
            f"{total_duration:>6.2f}s (Total)"
        )
        print("=" * 80)

        if comparison_delta:
            print()
            print("=" * 80)
            print("  📈 RUN-OVER-RUN REGRESSION & IMPROVEMENT DELTA")
            print("=" * 80)
            print(f"  Verdict             : {comparison_delta.verdict}")
            print(f"  Success Rate Delta  : {comparison_delta.delta_pass_rate_pct:+.1f}%")
            print(f"  Pass@1 Delta        : {comparison_delta.delta_pass_at_1:+.1f}%")
            print(f"  Latency Delta       : {comparison_delta.delta_avg_duration_seconds:+.2f}s")
            print(f"  Improved Tasks ({len(comparison_delta.improved_tasks)}) : {', '.join(comparison_delta.improved_tasks) if comparison_delta.improved_tasks else 'None'}")
            print(f"  Regressed Tasks ({len(comparison_delta.regressed_tasks)}): {', '.join(comparison_delta.regressed_tasks) if comparison_delta.regressed_tasks else 'None (Clean)'}")
            print("=" * 80)

    if output_json:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        if verbose:
            print(f"📁 JSON results saved to: {output_json}")

    if output_markdown:
        md = generate_markdown_report(summary, comparison_delta=comparison_delta)
        with open(output_markdown, "w", encoding="utf-8") as f:
            f.write(md)
        if verbose:
            print(f"📄 Markdown scorecard saved to: {output_markdown}")

    return summary


def generate_markdown_report(
    summary: Dict[str, Any],
    comparison_delta: Optional[ComparisonDelta] = None,
) -> str:
    """Renders evaluation summary as a comprehensive Markdown report."""
    m = summary.get("metrics", {})
    md = [
        "# 🔬 Autonomous AI Coding Agent: Benchmark Evaluation Scorecard",
        f"\n**Execution Mode**: `{summary['agent_mode']}`  ",
        f"**Timestamp**: `{summary['timestamp']}`  ",
        f"**Total Tasks**: `{summary['total_tasks']}`  ",
        f"**Pass Rate**: `{summary['pass_rate_pct']}%` ({summary['passed_tasks']}/{summary['total_tasks']})  ",
        f"**Total Duration**: `{summary['total_duration_seconds']}s`\n",
        "---",
        "\n## Core Operational & Quality Metrics\n",
        "| Metric | Value | Description |",
        "| :--- | :---: | :--- |",
        f"| **Task Success Rate (TSR)** | **{m.get('task_success_rate', summary['pass_rate_pct'])}%** | Percentage of tasks passed overall via sovereign verifier & hidden tests |",
        f"| **Zero-Remediation Success Rate** | **{m.get('zero_remediation_success_rate', 0.0)}%** | Tasks solved on attempt 1 with zero remediation retries (agentic efficiency) |",
        f"| **Conventional Pass@1** | **{m.get('pass_at_1', 0.0)}%** | Unbiased expected single-attempt pass rate across sampled runs (c / n) |",
        f"| **Pass@k Estimator (Chen et al.)** | **{', '.join(f'k={k}: {v}%' for k, v in m.get('pass_at_k', {}).items()) if m.get('pass_at_k') else 'N/A (requires n >= k independent samples)'}** | Combinatorial probability of at least one pass among k runs ({m.get('samples_per_task', 1)} sample(s)/task) |",
        f"| **Test Pass Rate (TPR)** | **{m.get('test_pass_rate', 0.0)}%** | Percentage of baseline, generated, and hidden tests passing |",
        f"| **Candidate Regression Rate (CPRR)** | **{m.get('candidate_patch_regression_rate', m.get('regression_rate', 0.0))}%** | Pre-gate: Frequency of proposed candidate patches breaking baseline tests |",
        f"| **Admitted Regression Rate (APRR)** | **{m.get('admitted_patch_regression_rate', m.get('baseline_patch_regression_rate', 0.0))}%** | Post-gate: Frequency of released/merged patches breaking baseline tests |",
        f"| **Regressive Candidates Intercepted** | **{m.get('regressive_candidates_rejected_count', 0)} rejected / {m.get('regressive_candidates_repaired_count', 0)} repaired** | Sovereign Verifier gate rejection & closed-loop Debugger healing |",
        f"| **Review Rejection Rate (RRR)** | **{m.get('review_rejection_rate', 0.0)}%** | Frequency of adversarial reviewer blocking issues or score < 8.0 |",
        f"| **Retry Rate (RetR)** | **{m.get('retry_rate', 0.0)}%** | Percentage of tasks requiring remediation beyond iteration 1 |",
        f"| **Recovery Rate (RecR)** | **{m.get('recovery_rate', 0.0)}%** | Percentage of tasks that self-healed after an intermediate failure |",
        f"| **Unrelated Change Rate (UCR)** | **{m.get('unrelated_change_rate', 0.0)}%** | Frequency of modifying files outside specified task scope |",
        f"| **Cost per Task** | **${m.get('avg_cost_per_task_usd', 0.0):.4f}** | Average LLM token and sandbox compute cost |",
        f"| **Time per Task** | **Mean: {m.get('avg_duration_seconds', 0.0):.2f}s (p50: {m.get('p50_duration_seconds', 0.0):.2f}s, p95: {m.get('p95_duration_seconds', 0.0):.2f}s)** | Latency profile |",
        "\n---",
    ]

    # Historical Comparison section if available
    if comparison_delta:
        md.append(render_comparison_markdown(comparison_delta))
        md.append("---")

    md.extend([
        "\n## Category Performance Breakdown\n",
        "| Category | Total Tasks | Passed | Pass Rate (%) | Avg Duration (s) |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ])

    for cat_name, stats in summary["category_breakdown"].items():
        md.append(
            f"| **{cat_name}** | {stats['total']} | {stats['passed']} | {stats['pass_rate']:.1f}% | {stats['avg_duration']:.2f}s |"
        )

    md.extend([
        f"| **OVERALL** | **{summary['total_tasks']}** | **{summary['passed_tasks']}** | **{summary['pass_rate_pct']:.1f}%** | **{summary['total_duration_seconds']:.2f}s** |",
        "\n---",
        "\n## Task-by-Task Evaluation Ledger\n",
        "| Task ID | Category | Status | Time | Iter | Review Score | Failure Diagnostics |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])

    for t in summary["tasks"]:
        status = "✅ PASS" if t["overall_pass"] else "❌ FAIL"
        score = f"{t['review_quality_score']}/10.0" if t["review_quality_score"] is not None else "N/A"
        reasons = "; ".join(t["failure_reasons"][:1]) if t["failure_reasons"] else "None (Clean)"
        md.append(
            f"| `{t['task_id']}` | {t['category']} | {status} | {t['duration_seconds']:.2f}s | {t['iteration_count']} | {score} | {reasons} |"
        )

    md.extend([
        "\n---",
        "\n## 🎓 The Four Tiers of Engineering Validation\n",
        "| Validation Tier | Scope | What It Answers | Engineering Significance |",
        "| :--- | :--- | :--- | :--- |",
        "| **Tier 1: Unit Tests** | Individual functions & classes | *Do individual components behave as expected?* | Fast, isolated, deterministic |",
        "| **Tier 2: Integration Tests** | Multi-agent coordination & tools | *Do agents, state transitions, and tools work together?* | Pipeline orchestration, schema integrity |",
        "| **Tier 3: Benchmark Evaluations** | Real-world problem corpus | *How well does the complete coding agent solve real-world tasks?* | Sovereign verification, hidden tests, Pass@1 |",
        "| **Tier 4: Production Monitoring** | Continuous telemetry in production | *Does that performance remain reliable over time?* | LangSmith distributed traces, cost SLAs, regression tracking |",
    ])

    return "\n".join(md) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Autonomous AI Coding Agent Evaluation Benchmark Runner")
    parser.add_argument("--category", choices=[c.value for c in BenchmarkCategory], help="Filter by category")
    parser.add_argument("--task", help="Run a specific task by task_id")
    parser.add_argument("--limit", type=int, help="Limit number of tasks")
    parser.add_argument("--samples", "-s", type=int, default=1, help="Number of independent sampled runs per task (for Pass@k estimation)")
    parser.add_argument("--baseline", action="store_true", help="Run single-agent baseline instead of multi-agent")
    parser.add_argument("--demo", action="store_true", help="Run in demo mode with deliberate first-step error")
    parser.add_argument("--compare", help="Compare with a previous run ID, JSON file, or 'latest'")
    parser.add_argument("--no-history", action="store_true", help="Do not save this run to history index")
    parser.add_argument("--json", dest="output_json", help="Path to write JSON results")
    parser.add_argument("--report", dest="output_markdown", help="Path to write Markdown report")

    args = parser.parse_args()

    if args.task:
        task = get_task_by_id(args.task)
        if not task:
            print(f"Error: Task '{args.task}' not found in benchmark catalog.")
            sys.exit(1)
        tasks = [task]
    elif args.category:
        tasks = get_tasks_by_category(BenchmarkCategory(args.category))
    else:
        tasks = get_all_tasks()

    if args.limit:
        tasks = tasks[:args.limit]

    agent_mode = "single_agent_baseline" if args.baseline else "multi_agent"
    run_benchmark_suite(
        tasks=tasks,
        agent_mode=agent_mode,
        demo_mode=args.demo,
        samples_per_task=args.samples,
        output_json=args.output_json,
        output_markdown=args.output_markdown,
        compare_target=args.compare,
        save_history=not args.no_history,
    )


if __name__ == "__main__":
    main()

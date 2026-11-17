"""Tests for the Benchmark Dataset, Evaluation Harness, and Hidden Test Isolation.

Verifies:
1. Exactly 50 benchmark tasks across 5 categories (10 per category).
2. All task initial files, baseline tests, and hidden tests parse as valid Python AST syntax.
3. Task environment properly quarantines hidden tests from agent workspace.
4. EvaluationHarness correctly scores passing and failing implementations against hidden tests.
"""

import ast
import sys
import tempfile
from pathlib import Path
import pytest

from evaluation.dataset import (
    BenchmarkTask,
    BenchmarkCategory,
    get_all_tasks,
    get_tasks_by_category,
    get_task_by_id,
)
from evaluation.harness import EvaluationHarness, BenchmarkEvaluationResult


def test_benchmark_dataset_catalog_integrity():
    """Verify that the benchmark dataset contains exactly 50 tasks across 5 categories."""
    tasks = get_all_tasks()
    assert len(tasks) == 50, f"Expected 50 tasks, found {len(tasks)}"

    categories = [
        BenchmarkCategory.BASIC_IMPLEMENTATION,
        BenchmarkCategory.BUG_FIXING,
        BenchmarkCategory.EDGE_CASES,
        BenchmarkCategory.MULTI_FILE,
        BenchmarkCategory.DIFFICULT_TASKS,
    ]

    task_ids = set()
    for cat in categories:
        cat_tasks = get_tasks_by_category(cat)
        assert len(cat_tasks) == 10, f"Category {cat.value} should have exactly 10 tasks, found {len(cat_tasks)}"

        for t in cat_tasks:
            assert t.task_id not in task_ids, f"Duplicate task_id: {t.task_id}"
            task_ids.add(t.task_id)
            assert len(t.title) > 0
            assert len(t.description) > 0
            assert len(t.initial_files) > 0, f"Task {t.task_id} has no initial files"
            assert len(t.baseline_tests) > 0, f"Task {t.task_id} has no baseline tests"
            assert len(t.hidden_tests) > 0, f"Task {t.task_id} has no hidden evaluation tests"
            assert len(t.expected_behavior) > 0
            assert len(t.acceptance_criteria) > 0


def test_benchmark_task_python_syntax_validity():
    """Verify that all initial files, baseline tests, and hidden tests compile as valid Python AST."""
    tasks = get_all_tasks()
    for t in tasks:
        for fname, code in t.initial_files.items():
            if fname.endswith(".py"):
                try:
                    ast.parse(code)
                except SyntaxError as e:
                    pytest.fail(f"Syntax error in initial file {fname} of task {t.task_id}: {e}")

        for fname, code in t.baseline_tests.items():
            if fname.endswith(".py"):
                try:
                    ast.parse(code)
                except SyntaxError as e:
                    pytest.fail(f"Syntax error in baseline test {fname} of task {t.task_id}: {e}")

        for fname, code in t.hidden_tests.items():
            if fname.endswith(".py"):
                try:
                    ast.parse(code)
                except SyntaxError as e:
                    pytest.fail(f"Syntax error in hidden test {fname} of task {t.task_id}: {e}")


def test_evaluation_harness_quarantine_hidden_tests():
    """Verify that setup_task_environment and run_hidden_tests NEVER write hidden tests into the agent's workspace."""
    task = get_task_by_id("basic_01_api_pagination")
    assert task is not None

    harness = EvaluationHarness()
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir) / "repo"
        harness.setup_task_environment(task, repo_path)

        # Baseline files exist
        assert (repo_path / "api" / "paginator.py").exists()
        assert (repo_path / "tests" / "test_paginator.py").exists()

        # Hidden evaluation tests MUST NOT exist before evaluation in agent repo
        assert not (repo_path / "tests" / "test_hidden_paginator.py").exists()

        # Execute hidden tests
        passed, failures, snapshot_hash = harness.run_hidden_tests(task, repo_path)

        # CRITICAL QUARANTINE ASSERTION: Hidden tests MUST NEVER exist in the agent's repo_path!
        assert not (repo_path / "tests" / "test_hidden_paginator.py").exists()
        assert len(snapshot_hash) == 64


def test_path_containment_rejects_directory_traversal_and_symlink_escapes():
    """Verify validate_contained_path strictly detects and blocks path escapes and symlink attacks."""
    from evaluation.harness import validate_contained_path, PathTraversalError

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir) / "workspace"
        base_dir.mkdir()

        # 1. Null bytes
        with pytest.raises(PathTraversalError, match="Null byte"):
            validate_contained_path(base_dir, "file\x00name.py")

        # 2. Absolute paths
        with pytest.raises(PathTraversalError, match="Absolute paths are forbidden"):
            validate_contained_path(base_dir, "/etc/passwd")

        # 3. Direct traversal sequences
        with pytest.raises(PathTraversalError, match="Directory traversal"):
            validate_contained_path(base_dir, "../outside.py")

        with pytest.raises(PathTraversalError, match="Directory traversal"):
            validate_contained_path(base_dir, "nested/../../outside.py")

        # 4. Valid nested paths resolve properly
        valid = validate_contained_path(base_dir, "src/module/app.py")
        assert valid == (base_dir / "src/module/app.py").resolve()

        # 5. Symlink escape detection
        outside_dir = Path(tmp_dir) / "outside_target"
        outside_dir.mkdir()
        symlink_path = base_dir / "symlink_dir"
        symlink_path.symlink_to(outside_dir, target_is_directory=True)

        with pytest.raises(PathTraversalError, match="outside base directory"):
            validate_contained_path(base_dir, "symlink_dir/escaped_file.py")


def test_setup_task_environment_blocks_malicious_task_definition():
    """Verify that setup_task_environment refuses to materialize task files with traversal paths."""
    from evaluation.harness import PathTraversalError

    evil_task = BenchmarkTask(
        task_id="evil_01",
        category=BenchmarkCategory.SECURITY_ADVERSARIAL if hasattr(BenchmarkCategory, "SECURITY_ADVERSARIAL") else BenchmarkCategory.BASIC_IMPLEMENTATION,
        title="Path Traversal Exploit",
        description="Try to escape workspace",
        initial_files={"../../evil_target.py": "malicious = True"},
        baseline_tests={"tests/test_foo.py": "def test_ok(): pass"},
        hidden_tests={"tests/test_hidden.py": "def test_h(): pass"},
        expected_behavior="Blocked",
        acceptance_criteria=["Must raise PathTraversalError"],
    )

    harness = EvaluationHarness()
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir) / "repo"
        with pytest.raises(PathTraversalError):
            harness.setup_task_environment(evil_task, repo_path)


def test_terminate_agent_workspace_processes():
    """Verify terminate_agent_workspace_processes kills active background subprocesses in workspace."""
    import subprocess
    from evaluation.harness import terminate_agent_workspace_processes

    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir) / "proc_ws"
        ws.mkdir()

        # Spawn a lingering background subprocess inside ws
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=str(ws),
        )

        try:
            # Terminate processes in workspace
            killed = terminate_agent_workspace_processes(ws, timeout=1.0)
            assert killed >= 1

            # Verify process exited
            ret = proc.wait(timeout=2.0)
            assert ret is not None
        finally:
            if proc.poll() is None:
                proc.kill()


def test_evaluation_harness_correct_implementation_passes_all_tests():
    """Verify that a correct implementation clears both baseline tests and hidden tests."""
    task = get_task_by_id("basic_01_api_pagination")
    assert task is not None

    def correct_patch(repo_path: Path):
        code = (
            "from typing import List, Any, Dict\n"
            "import math\n\n"
            "def paginate(items: List[Any], page: int = 1, per_page: int = 10) -> Dict[str, Any]:\n"
            "    if page < 1 or per_page < 1:\n"
            "        raise ValueError('page and per_page must be >= 1')\n"
            "    total_items = len(items)\n"
            "    total_pages = math.ceil(total_items / per_page) if total_items > 0 else 0\n"
            "    start = (page - 1) * per_page\n"
            "    end = start + per_page\n"
            "    paged_items = items[start:end] if start < total_items else []\n"
            "    return {\n"
            "        'items': paged_items,\n"
            "        'page': page,\n"
            "        'per_page': per_page,\n"
            "        'total_items': total_items,\n"
            "        'total_pages': total_pages,\n"
            "    }\n"
        )
        (repo_path / "api" / "paginator.py").write_text(code, encoding="utf-8")

    harness = EvaluationHarness()
    result = harness.evaluate_task(task, mock_patch_fn=correct_patch)

    assert result.baseline_tests_passed is True
    assert result.hidden_tests_passed is True
    assert result.overall_pass is True
    assert result.task_succeeded is True
    assert len(result.failure_reasons) == 0
    assert result.evaluated_snapshot_hash is not None
    assert len(result.evaluated_snapshot_hash) == 64
    assert result.evaluator_quarantine_verified is True


def test_evaluation_harness_incomplete_implementation_fails_hidden_tests():
    """Verify that an implementation passing baseline tests but failing hidden edge cases is rejected."""
    task = get_task_by_id("basic_01_api_pagination")
    assert task is not None

    def naive_incomplete_patch(repo_path: Path):
        # Naive implementation that passes baseline tests (first & second page on 25 items)
        # but fails hidden edge cases (missing ValueError for page=0, empty items total_pages=0)
        code = (
            "from typing import List, Any, Dict\n\n"
            "def paginate(items: List[Any], page: int = 1, per_page: int = 10) -> Dict[str, Any]:\n"
            "    start = (page - 1) * per_page\n"
            "    end = start + per_page\n"
            "    return {\n"
            "        'items': items[start:end],\n"
            "        'page': page,\n"
            "        'per_page': per_page,\n"
            "        'total_items': len(items),\n"
            "        'total_pages': 3,\n"
            "    }\n"
        )
        (repo_path / "api" / "paginator.py").write_text(code, encoding="utf-8")

    harness = EvaluationHarness()
    result = harness.evaluate_task(task, mock_patch_fn=naive_incomplete_patch)

    # Baseline tests pass, but hidden edge case tests catch the bug!
    assert result.baseline_tests_passed is True
    assert result.hidden_tests_passed is False
    assert result.overall_pass is False
    assert any("Hidden evaluation test suite failed" in f for f in result.failure_reasons)


def test_pass_at_k_unbiased_estimator_math():
    """Verify combinatorial pass@k calculation against known analytical solutions."""
    from evaluation.metrics import compute_pass_at_k

    # All correct: n=5, c=5 -> 100% for all k
    assert compute_pass_at_k(5, 5, 1) == 100.0
    assert compute_pass_at_k(5, 5, 3) == 100.0

    # None correct: n=5, c=0 -> 0%
    assert compute_pass_at_k(5, 0, 1) == 0.0

    # Exactly 1 correct out of 5:
    # k=1: c/n = 1/5 = 20.0%
    assert compute_pass_at_k(5, 1, 1) == 20.0
    # k=3: 1 - comb(4, 3)/comb(5, 3) = 1 - 4/10 = 60.0%
    assert compute_pass_at_k(5, 1, 3) == 60.0

    # Boundary conditions
    assert compute_pass_at_k(0, 0, 1) == 0.0
    assert compute_pass_at_k(5, 2, 6) == 0.0  # k > n


def test_metrics_calculator_all_nine_metrics():
    """Verify that EvaluationMetricsCalculator accurately derives all 9 core operational metrics."""
    from evaluation.metrics import TaskAttemptRecord, EvaluationMetricsCalculator

    records = [
        # Task 1: Clean pass on attempt 1, iteration 1
        TaskAttemptRecord(
            task_id="task_01",
            category="basic_implementation",
            attempt_index=1,
            overall_pass=True,
            iteration_count=1,
            baseline_tests_passed=True,
            hidden_tests_passed=True,
            baseline_regressions_count=0,
            unrelated_files_count=0,
            review_rejected=False,
            duration_seconds=10.0,
            prompt_tokens=1000,
            completion_tokens=400,
        ),
        # Task 2: Required self-healing retry (iter 2) - succeeded after failure
        TaskAttemptRecord(
            task_id="task_02",
            category="bug_fixing",
            attempt_index=1,
            overall_pass=True,
            iteration_count=2,
            baseline_tests_passed=True,
            hidden_tests_passed=True,
            baseline_regressions_count=0,
            unrelated_files_count=0,
            review_rejected=True,  # Review caught defect on iter 1
            encountered_failure=True,
            recovered_from_failure=True,
            duration_seconds=20.0,
            prompt_tokens=2500,
            completion_tokens=800,
        ),
        # Task 3: Failed with regression and unrelated changes
        TaskAttemptRecord(
            task_id="task_03",
            category="difficult_tasks",
            attempt_index=1,
            overall_pass=False,
            iteration_count=3,
            baseline_tests_passed=False,
            hidden_tests_passed=False,
            baseline_regressions_count=2,
            unrelated_files_count=1,
            review_rejected=True,
            encountered_failure=True,
            recovered_from_failure=False,
            duration_seconds=30.0,
            prompt_tokens=4000,
            completion_tokens=1200,
        ),
    ]

    calc = EvaluationMetricsCalculator()
    rep = calc.compute_metrics(records, k_values=[1, 3])

    # 1. Task Success Rate (2/3 = 66.67%)
    assert rep.task_success_rate == 66.67

    # 2. Zero-Remediation Success Rate (Only Task 1 succeeded with iteration_count == 1: 1/3 = 33.33%)
    assert rep.zero_remediation_success_rate == 33.33

    # 3. Conventional Pass@1 (c / n across sampled tasks: (1/1 + 1/1 + 0/1) / 3 = 66.67%)
    assert rep.pass_at_1 == 66.67

    # 4. Pass@k behavior when n=1 (k=3 omitted because n < 3)
    assert 1 in rep.pass_at_k
    assert rep.pass_at_k[1] == 66.67
    assert 3 not in rep.pass_at_k  # Strictly omitted when samples per task n < k

    # 5. Test Pass Rate (2/3 = 66.67%)
    assert rep.test_pass_rate == 66.67

    # 6. Regression Rate (1/3 = 33.33%)
    assert rep.regression_rate == 33.33

    # 7. Review Rejection Rate (2/3 = 66.67%)
    assert rep.review_rejection_rate == 66.67

    # 8. Retry Rate (2 tasks took iter > 1: 2/3 = 66.67%)
    assert rep.retry_rate == 66.67

    # 9. Recovery Rate (2 tasks encountered failure; 1 recovered: 1/2 = 50.0%)
    assert rep.recovery_rate == 50.0

    # 10. Unrelated Change Rate (1/3 = 33.33%)
    assert rep.unrelated_change_rate == 33.33

    # 11. Cost and Duration
    assert rep.total_cost_usd > 0.0
    assert rep.avg_duration_seconds == 20.0
    assert rep.p50_duration_seconds == 20.0


def test_pass_at_k_multi_sampling_five_attempts():
    """Verify Pass@k computation when running N=5 independent attempts per task."""
    from evaluation.metrics import TaskAttemptRecord, EvaluationMetricsCalculator

    records = []
    # Task 1: 5 attempts, 5 passes (c=5, n=5) -> Pass@1=100%, Pass@3=100%, Pass@5=100%
    for att in range(1, 6):
        records.append(
            TaskAttemptRecord(
                task_id="t1",
                category="basic_implementation",
                attempt_index=att,
                overall_pass=True,
                iteration_count=1,
                baseline_tests_passed=True,
                hidden_tests_passed=True,
                baseline_regressions_count=0,
                unrelated_files_count=0,
                review_rejected=False,
            )
        )
    # Task 2: 5 attempts, 1 pass (c=1, n=5) -> Pass@1=20%, Pass@3=60%, Pass@5=100%
    for att in range(1, 6):
        records.append(
            TaskAttemptRecord(
                task_id="t2",
                category="bug_fixing",
                attempt_index=att,
                overall_pass=(att == 1),
                iteration_count=1 if att == 1 else 2,
                baseline_tests_passed=(att == 1),
                hidden_tests_passed=(att == 1),
                baseline_regressions_count=0,
                unrelated_files_count=0,
                review_rejected=(att != 1),
            )
        )

    calc = EvaluationMetricsCalculator()
    rep = calc.compute_metrics(records, k_values=[1, 3, 5])

    # Expected Pass@k:
    # Task 1: k=1: 100%, k=3: 100%, k=5: 100%
    # Task 2: k=1: 20%,  k=3: 60%,  k=5: 100%
    # Mean:   k=1: 60%,  k=3: 80%,  k=5: 100%
    assert rep.samples_per_task == 5
    assert rep.pass_at_k[1] == 60.0
    assert rep.pass_at_k[3] == 80.0
    assert rep.pass_at_k[5] == 100.0


def test_run_history_and_comparison_deltas():
    """Verify RunHistoryManager saves runs and compare_runs accurately detects improvements and regressions."""
    from evaluation.comparison import RunHistoryManager, compare_runs, render_comparison_markdown

    with tempfile.TemporaryDirectory() as tmp_dir:
        mgr = RunHistoryManager(history_dir=tmp_dir)

        baseline_summary = {
            "timestamp": "2026-11-01T10:00:00Z",
            "agent_mode": "single_agent_baseline",
            "total_tasks": 3,
            "passed_tasks": 1,
            "pass_rate_pct": 33.33,
            "metrics": {
                "task_success_rate": 33.33,
                "pass_at_1": 33.33,
                "regression_rate": 33.33,
                "avg_cost_per_task_usd": 0.002,
                "avg_duration_seconds": 25.0,
            },
            "tasks": [
                {"task_id": "task_01", "overall_pass": True},
                {"task_id": "task_02", "overall_pass": False},
                {"task_id": "task_03", "overall_pass": False},
            ],
        }

        current_summary = {
            "timestamp": "2026-11-02T10:00:00Z",
            "agent_mode": "multi_agent",
            "total_tasks": 3,
            "passed_tasks": 2,
            "pass_rate_pct": 66.67,
            "metrics": {
                "task_success_rate": 66.67,
                "pass_at_1": 66.67,
                "regression_rate": 0.0,
                "avg_cost_per_task_usd": 0.003,
                "avg_duration_seconds": 18.0,
            },
            "tasks": [
                {"task_id": "task_01", "overall_pass": True},   # Stable passing
                {"task_id": "task_02", "overall_pass": True},   # Improved!
                {"task_id": "task_03", "overall_pass": False},  # Stable failing
            ],
        }

        run_id_base = mgr.save_run(baseline_summary, tag="baseline")
        run_id_curr = mgr.save_run(current_summary, tag="v2")

        retrieved_base = mgr.load_run(run_id_base)
        assert retrieved_base is not None
        assert retrieved_base["agent_mode"] == "single_agent_baseline"

        delta = compare_runs(current_summary, baseline_summary)
        assert delta.delta_pass_rate_pct == pytest.approx(33.34, abs=0.1)
        assert delta.delta_pass_at_1 == pytest.approx(33.34, abs=0.1)
        assert delta.delta_avg_duration_seconds == -7.0
        assert "task_02" in delta.improved_tasks
        assert len(delta.regressed_tasks) == 0
        assert delta.verdict == "IMPROVED"
        assert delta.contingency_table["fail_to_pass"] == 1
        assert delta.contingency_table["pass_to_pass"] == 1
        assert delta.contingency_table["fail_to_fail"] == 1

        md = render_comparison_markdown(delta)
        assert "Architectural Comparison" in md
        assert "Paired 2x2 Transition Contingency Matrix" in md
        assert "IMPROVED" in md
        assert "task_02" in md


def test_evaluation_result_langsmith_serialization():
    """Verify BenchmarkEvaluationResult includes langsmith_trace_id in dataclass and serialization."""
    res = BenchmarkEvaluationResult(
        task_id="test_ls_01",
        category="basic_implementation",
        title="Test LangSmith",
        agent_mode="multi_agent",
        agent_outcome="completed_successfully",
        task_succeeded=True,
        baseline_tests_passed=True,
        hidden_tests_passed=True,
        overall_pass=True,
        duration_seconds=5.2,
        iteration_count=1,
        tests_generated_count=2,
        review_quality_score=9.5,
        toctou_valid=True,
        langsmith_trace_id="run-uuid-12345",
    )
    assert res.langsmith_trace_id == "run-uuid-12345"
    d = res.to_dict()
    assert d["langsmith_trace_id"] == "run-uuid-12345"
    assert d["overall_pass"] is True


def test_is_patch_admissible_admission_gate():
    """Verify is_patch_admissible admission condition strictly blocks regressive, tampered,
    or unverified patches with fail-closed semantics.
    """
    from types import SimpleNamespace
    from agent.verification.verifier import (
        VerificationResult,
        WorkflowOutcome,
        BaselineVerificationStatus,
        is_patch_admissible,
    )

    # 1. Admissible patch: explicitly verified with 0 baseline regressions
    admissible = VerificationResult(
        verified=True,
        outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
        baseline_status=BaselineVerificationStatus.VERIFIED,
        baseline_inventory_count=5,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        toctou_valid=True,
        baseline_regressions=[],
        summary="Clean pass",
    )
    assert is_patch_admissible(admissible) is True

    # 2. Greenfield task: NOT_APPLICABLE admitted when baseline inventory is genuinely 0
    greenfield_admissible = VerificationResult(
        verified=True,
        outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
        baseline_status=BaselineVerificationStatus.NOT_APPLICABLE,
        baseline_inventory_count=0,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        toctou_valid=True,
        baseline_regressions=[],
        summary="Clean greenfield task",
    )
    assert is_patch_admissible(greenfield_admissible) is True

    # 3. Fail Closed on missing baseline_status (Legacy or deserialized object)
    legacy_obj_without_baseline_status = SimpleNamespace(
        passed=True,
        tests_preserved=True,
        toctou_valid=True,
        baseline_regressions=[],
        # "baseline_status" omitted entirely!
    )
    assert is_patch_admissible(legacy_obj_without_baseline_status) is False

    # 4. Fail Closed on UNVERIFIABLE baseline status
    unverifiable_patch = VerificationResult(
        verified=False,
        outcome=WorkflowOutcome.COMPLETED_WITH_FAILURES,
        baseline_status=BaselineVerificationStatus.UNVERIFIABLE,
        baseline_inventory_count=3,
        tests_passed=True,
        baseline_tests_passed=False,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        toctou_valid=True,
        baseline_regressions=[],
        summary="Unverifiable baseline",
    )
    assert is_patch_admissible(unverifiable_patch) is False

    # 5. Inconsistent NOT_APPLICABLE: claimed NOT_APPLICABLE but baseline_inventory_count > 0
    tampered_duck_type = SimpleNamespace(
        passed=True,
        tests_preserved=True,
        toctou_valid=True,
        baseline_status=BaselineVerificationStatus.NOT_APPLICABLE,
        baseline_inventory_count=3,  # Inconsistent! Tests existed!
        baseline_regressions=[],
    )
    assert is_patch_admissible(tampered_duck_type) is False

    # 6. Model validator rejects NOT_APPLICABLE when baseline_inventory_count > 0
    with pytest.raises(ValueError, match="cannot be NOT_APPLICABLE"):
        VerificationResult(
            verified=True,
            outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
            baseline_status=BaselineVerificationStatus.NOT_APPLICABLE,
            baseline_inventory_count=2,  # Must fail Pydantic model validation!
            tests_passed=True,
            baseline_tests_passed=True,
            generated_tests_passed=True,
            lint_checks_passed=True,
            tests_preserved=True,
            git_diff_clean=True,
            reviewer_approved=True,
            toctou_valid=True,
            baseline_regressions=[],
            summary="Invalid NOT_APPLICABLE state",
        )

    # 7. Regressive patch: detected baseline regression MUST be rejected
    regressive = VerificationResult(
        verified=True,
        outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
        baseline_status=BaselineVerificationStatus.VERIFIED,
        baseline_inventory_count=5,
        tests_passed=False,
        baseline_tests_passed=False,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        toctou_valid=True,
        baseline_regressions=["tests/test_config.py::test_modify_instance_config"],
        summary="Contains regression",
    )
    assert is_patch_admissible(regressive) is False

    # 8. Test tampering: tests not preserved MUST be rejected
    tampered_tests = VerificationResult(
        verified=False,
        outcome=WorkflowOutcome.COMPLETED_WITH_FAILURES,
        baseline_status=BaselineVerificationStatus.VERIFIED,
        baseline_inventory_count=5,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=False,
        git_diff_clean=True,
        reviewer_approved=True,
        toctou_valid=True,
        baseline_regressions=[],
        summary="Tests deleted",
    )
    assert is_patch_admissible(tampered_tests) is False

    # 9. TOCTOU tampering: toctou_valid=False MUST be rejected
    toctou_violation = VerificationResult(
        verified=False,
        outcome=WorkflowOutcome.COMPLETED_WITH_FAILURES,
        baseline_status=BaselineVerificationStatus.VERIFIED,
        baseline_inventory_count=5,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        toctou_valid=False,
        baseline_regressions=[],
        summary="TOCTOU violation",
    )
    assert is_patch_admissible(toctou_violation) is False

    # 10. Incomplete baseline verification: baseline_tests_not_executed non-empty MUST be rejected
    incomplete_baseline = VerificationResult(
        verified=True,
        outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
        baseline_status=BaselineVerificationStatus.VERIFIED,
        baseline_inventory_count=5,
        tests_passed=True,
        baseline_tests_passed=False,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        toctou_valid=True,
        baseline_regressions=[],
        baseline_tests_not_executed=["test_skipped_or_not_collected"],
        baseline_tests_preserved=["test_1", "test_2", "test_3", "test_4"],
        summary="Incomplete baseline verification",
    )
    assert is_patch_admissible(incomplete_baseline) is False


def test_candidate_vs_admitted_regression_metrics():
    """Verify distinction between Candidate-Patch Regression Rate (CPRR) and Admitted-Patch Regression Rate (APRR)."""
    from evaluation.metrics import TaskAttemptRecord, EvaluationMetricsCalculator

    records = [
        # Task 1: Clean pass, 0 candidate regressions, 0 admitted regressions
        TaskAttemptRecord(
            task_id="t1",
            category="basic_implementation",
            attempt_index=1,
            overall_pass=True,
            iteration_count=1,
            baseline_tests_passed=True,
            hidden_tests_passed=True,
            candidate_regressions_count=0,
            candidate_regressions_rejected=0,
            candidate_regressions_repaired=0,
            admitted_regressions_count=0,
        ),
        # Task 2: Candidate regression generated, rejected by admission gate, repaired by Debugger -> 0 admitted
        TaskAttemptRecord(
            task_id="t2",
            category="bug_fixing",
            attempt_index=1,
            overall_pass=True,
            iteration_count=2,
            baseline_tests_passed=True,
            hidden_tests_passed=True,
            candidate_regressions_count=1,
            candidate_regressions_rejected=1,
            candidate_regressions_repaired=1,
            admitted_regressions_count=0,
        ),
        # Task 3: Candidate regression generated, rejected by admission gate, unrepaired -> 0 admitted (blocked from repo)
        TaskAttemptRecord(
            task_id="t3",
            category="difficult_tasks",
            attempt_index=1,
            overall_pass=False,
            iteration_count=3,
            baseline_tests_passed=False,
            hidden_tests_passed=False,
            candidate_regressions_count=1,
            candidate_regressions_rejected=1,
            candidate_regressions_repaired=0,
            admitted_regressions_count=0,
        ),
        # Task 4: Un-gated baseline patch where regression was admitted into repo
        TaskAttemptRecord(
            task_id="t4",
            category="edge_cases",
            attempt_index=1,
            overall_pass=False,
            iteration_count=1,
            baseline_tests_passed=False,
            hidden_tests_passed=False,
            baseline_regressions_count=1,
            candidate_regressions_count=1,
            candidate_regressions_rejected=0,
            candidate_regressions_repaired=0,
            admitted_regressions_count=1,
        ),
    ]

    calc = EvaluationMetricsCalculator()
    rep = calc.compute_metrics(records)

    # CPRR: 3 out of 4 tasks had candidate regressions proposed (75.0%)
    assert rep.candidate_patch_regression_rate == 75.0

    # APRR: Only 1 out of 4 tasks had a regression admitted to repo (25.0%)
    assert rep.admitted_patch_regression_rate == 25.0

    # Regressive candidates intercepted by admission gate: 2 rejected, 1 repaired
    assert rep.regressive_candidates_rejected_count == 2
    assert rep.regressive_candidates_repaired_count == 1



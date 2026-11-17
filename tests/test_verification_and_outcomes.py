"""Tests for Independent Verification Pipeline, Outcome Separation, and Scope Review.

Verifies:
1. Distinct outcome classification: completed_successfully, completed_with_failures, blocked, cancelled.
2. The agent never reports success merely because it reached its retry limit.
3. Baseline regression tests verification.
4. Python AST linting and static checks on modified files.
5. Git diff and change scope inspection (ensuring no tests removed and no unrelated files touched).
"""

import hashlib
import tempfile
from pathlib import Path
import pytest

from agent.core.state import (
    AgentState,
    TestResult,
    ReviewResult,
    CoderResult,
    TestGenResult,
)
from agent.verification.verifier import (
    IndependentVerifier,
    WorkflowOutcome,
    VerificationResult,
)
from agent.agents.manager import ManagerPlannerAgent
from agent.core.graph import manager_finalize_node


@pytest.fixture
def sample_repo():
    """Sets up a temporary repo with baseline code and tests."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        (repo / "calculator").mkdir(parents=True, exist_ok=True)
        (repo / "tests").mkdir(parents=True, exist_ok=True)

        (repo / "calculator" / "core.py").write_text(
            "class Calculator:\n    def add(self, a, b):\n        return a + b\n",
            encoding="utf-8",
        )
        (repo / "tests" / "test_calculator.py").write_text(
            "from calculator.core import Calculator\n\n"
            "def test_add():\n    c = Calculator()\n    assert c.add(1, 2) == 3\n\n"
            "def test_add_negative():\n    c = Calculator()\n    assert c.add(-1, -1) == -2\n",
            encoding="utf-8",
        )
        yield repo


# ============================================================
# 1. Outcome Separation Tests
# ============================================================

def test_outcome_completed_successfully(sample_repo):
    """Verify workflow achieves completed_successfully when all verification checks clear."""
    verifier = IndependentVerifier(str(sample_repo))
    baseline = verifier.capture_baseline()

    state: AgentState = {
        "task": "Add add method",
        "repo_path": str(sample_repo),
        "relevant_files": ["calculator/core.py"],
        "baseline_tests": baseline["baseline_tests"],
        "baseline_files": baseline["baseline_files"],
        "iteration_count": 1,
        "max_iterations": 3,
        "test_results": TestResult(
            passed=True,
            exit_code=0,
            stdout="2 passed in 0.05s",
            stderr="",
            failed_tests=[],
            error_summary="",
        ),
        "coder_result": CoderResult(
            agent_name="CoderAgent",
            files_modified=["calculator/core.py"],
            patches={"calculator/core.py": "code"},
            methods_implemented=["add"],
            rationale="Implemented add",
            contracts=[],
        ),
        "test_gen_result": TestGenResult(
            agent_name="TestGeneratorAgent",
            test_files_modified=["tests/test_calculator.py"],
            test_cases_added=["test_add_negative"],
            edge_cases_tested=["negative inputs"],
            test_code_summary="Added negative test",
        ),
        "review_result": ReviewResult(
            agent_name="ReviewerAgent",
            approved=True,
            quality_score=9.5,
            blocking_issues=[],
            non_blocking_feedback=[],
            security_checks=["Input types safe"],
            review_summary="Clean and defensible implementation",
            reviewed_file_hashes={
                "calculator/core.py": hashlib.sha256((sample_repo / "calculator" / "core.py").read_bytes()).hexdigest()
            },
        ),
        "status": "evaluating",
    }

    result = verifier.verify(state)
    assert result.outcome == WorkflowOutcome.COMPLETED_SUCCESSFULLY
    assert result.verified is True
    assert result.baseline_tests_passed is True
    assert result.lint_checks_passed is True
    assert result.tests_preserved is True
    assert result.git_diff_clean is True


def test_agent_never_reports_success_on_retry_limit_reached(sample_repo):
    """Verify that reaching max retry limit with failing tests returns completed_with_failures, NEVER completed_successfully."""
    verifier = IndependentVerifier(str(sample_repo))
    baseline = verifier.capture_baseline()

    state: AgentState = {
        "task": "Fix zero division",
        "repo_path": str(sample_repo),
        "relevant_files": ["calculator/core.py"],
        "baseline_tests": baseline["baseline_tests"],
        "iteration_count": 3,
        "max_iterations": 3,  # Max iterations reached!
        "test_results": TestResult(
            passed=False,
            exit_code=1,
            stdout="FAILED test_calculator.py::test_divide_zero - ZeroDivisionError",
            stderr="",
            failed_tests=["test_divide_zero"],
            error_summary="ZeroDivisionError",
        ),
        "coder_result": CoderResult(
            agent_name="CoderAgent",
            files_modified=["calculator/core.py"],
            patches={},
            methods_implemented=["divide"],
            rationale="Attempted fix",
            contracts=[],
        ),
        "review_result": ReviewResult(
            agent_name="ReviewerAgent",
            approved=False,
            quality_score=4.0,
            blocking_issues=["Zero division still unhandled"],
            non_blocking_feedback=[],
            security_checks=[],
            review_summary="Failing tests",
        ),
        "status": "evaluating",
    }

    result = verifier.verify(state)
    # MUST NOT BE COMPLETED_SUCCESSFULLY!
    assert result.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert result.outcome != WorkflowOutcome.COMPLETED_SUCCESSFULLY
    assert result.verified is False
    assert any("failed with exit code" in r for r in result.failure_reasons)


def test_outcome_completed_with_failures_when_reviewer_rejects(sample_repo):
    """Verify that even if tests pass, reviewer rejection forces completed_with_failures."""
    verifier = IndependentVerifier(str(sample_repo))
    baseline = verifier.capture_baseline()

    state: AgentState = {
        "task": "Add operation",
        "repo_path": str(sample_repo),
        "relevant_files": ["calculator/core.py"],
        "baseline_tests": baseline["baseline_tests"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr="", failed_tests=[], error_summary=""),
        "coder_result": CoderResult(
            agent_name="CoderAgent",
            files_modified=["calculator/core.py"],
            patches={},
            methods_implemented=["op"],
            rationale="",
            contracts=[],
        ),
        "review_result": ReviewResult(
            agent_name="ReviewerAgent",
            approved=False,  # REJECTED!
            quality_score=6.0,
            blocking_issues=["Missing bounds check on negative inputs"],
            non_blocking_feedback=[],
            security_checks=[],
            review_summary="Rejecting due to missing safety guard",
        ),
    }

    result = verifier.verify(state)
    assert result.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert result.verified is False


def test_outcome_blocked_and_cancelled():
    """Verify blocked and cancelled explicit outcome states, ensuring cancellation takes top precedence."""
    verifier = IndependentVerifier(".")

    # Blocked state
    state_blocked: AgentState = {"status": "blocked", "blocked": True}
    res_blocked = verifier.verify(state_blocked)
    assert res_blocked.outcome == WorkflowOutcome.BLOCKED
    assert res_blocked.verified is False

    # Cancelled state (precedence over passing tests and approved review)
    from agent.core.state import TestResult, ReviewResult
    state_cancelled: AgentState = {
        "status": "cancelled",
        "cancelled": True,
        "test_results": TestResult(passed=True, exit_code=0, stdout="PASSED", stderr=""),
        "review_result": ReviewResult(
            agent_name="ReviewerAgent",
            approved=True,
            quality_score=9.5,
            review_summary="Clean implementation",
        ),
    }
    res_cancelled = verifier.verify(state_cancelled)
    assert res_cancelled.outcome == WorkflowOutcome.CANCELLED
    assert res_cancelled.verified is False
    assert "cancelled prior to verification" in res_cancelled.summary.lower()


# ============================================================
# 2. Scope Review & Baseline Test Preservation Tests
# ============================================================

def test_regression_detection_when_baseline_tests_are_removed(sample_repo):
    """Verify that if a code modification removes an existing baseline test, verification FAILS."""
    verifier = IndependentVerifier(str(sample_repo))
    baseline = verifier.capture_baseline()
    assert "test_add" in baseline["baseline_tests"]
    assert "test_add_negative" in baseline["baseline_tests"]

    # Simulate buggy coder patch that wiped out test_add
    (sample_repo / "tests" / "test_calculator.py").write_text(
        "def test_add_negative(): pass\n", encoding="utf-8"
    )

    state: AgentState = {
        "repo_path": str(sample_repo),
        "relevant_files": ["calculator/core.py"],
        "baseline_tests": baseline["baseline_tests"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="1 passed", stderr="", failed_tests=[], error_summary=""),
        "review_result": ReviewResult(agent_name="ReviewerAgent", approved=True, quality_score=9.0, blocking_issues=[], non_blocking_feedback=[], security_checks=[], review_summary="OK"),
    }

    result = verifier.verify(state)
    assert result.tests_preserved is False
    assert result.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert "test_add" in result.diff_details.deleted_tests
    assert any("Regressed: 1 existing tests were removed" in r for r in result.failure_reasons)


def test_unrelated_file_modification_detection(sample_repo):
    """Verify modifying out-of-scope files triggers diff review failure."""
    verifier = IndependentVerifier(str(sample_repo))
    baseline = verifier.capture_baseline()

    # Create unrelated file
    (sample_repo / "unrelated.py").write_text("MALICIOUS = True", encoding="utf-8")

    state: AgentState = {
        "repo_path": str(sample_repo),
        "relevant_files": ["calculator/core.py"],
        "baseline_tests": baseline["baseline_tests"],
        "coder_result": CoderResult(
            agent_name="CoderAgent",
            files_modified=["calculator/core.py", "unrelated.py"],  # unrelated file touched!
            patches={},
            methods_implemented=[],
            rationale="",
            contracts=[],
        ),
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr="", failed_tests=[], error_summary=""),
        "review_result": ReviewResult(agent_name="ReviewerAgent", approved=True, quality_score=9.0, blocking_issues=[], non_blocking_feedback=[], security_checks=[], review_summary="OK"),
    }

    result = verifier.verify(state)
    assert result.git_diff_clean is False
    assert "unrelated.py" in result.diff_details.unrelated_files_modified
    assert result.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES


# ============================================================
# 3. Python AST Linting & Syntax Checks
# ============================================================

def test_python_ast_linting_catches_syntax_errors(sample_repo):
    """Verify static lint analysis catches syntax errors in modified files."""
    verifier = IndependentVerifier(str(sample_repo))

    # Write broken syntax
    (sample_repo / "calculator" / "broken.py").write_text(
        "def broken_function(\n    if True:\n        print('invalid')\n", encoding="utf-8"
    )

    lint_res = verifier.run_linting(["calculator/broken.py"])
    assert lint_res.passed is False
    assert len(lint_res.issues) > 0
    assert any("SyntaxError" in issue for issue in lint_res.issues)


# ============================================================
# 4. Graph Finalize Node Integration
# ============================================================

def test_manager_finalize_node_sets_distinct_outcome_status(sample_repo):
    """Verify manager_finalize_node sets exact outcome status in the state."""
    verifier = IndependentVerifier(str(sample_repo))
    baseline = verifier.capture_baseline(run_tests=True)

    state: AgentState = {
        "task": "Test task",
        "repo_path": str(sample_repo),
        "relevant_files": ["calculator/core.py"],
        "baseline_tests": baseline["baseline_tests"],
        "baseline_outcomes": baseline["baseline_outcomes"],
        "baseline_snapshot": baseline["baseline_snapshot"],
        "iteration_count": 1,
        "max_iterations": 3,
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr="", failed_tests=[], error_summary=""),
        "coder_result": CoderResult(agent_name="CoderAgent", files_modified=["calculator/core.py"], patches={}, methods_implemented=["add"], rationale="", contracts=[]),
        "review_result": ReviewResult(
            agent_name="ReviewerAgent",
            approved=True,
            quality_score=9.5,
            blocking_issues=[],
            non_blocking_feedback=[],
            security_checks=[],
            review_summary="Approved",
            reviewed_file_hashes={
                "calculator/core.py": hashlib.sha256((sample_repo / "calculator" / "core.py").read_bytes()).hexdigest()
            },
        ),
    }

    out = manager_finalize_node(state)
    assert out["status"] == "completed_successfully"
    assert out["workflow_outcome"] == "completed_successfully"
    assert "COMPLETED_SUCCESSFULLY" in out["final_report"]
    assert "Independent Verification & Scope Review" in out["final_report"]

def test_baseline_test_run_captures_inventory_and_outcomes(sample_repo):
    """Verify that capture_baseline executes original tests and captures both inventory and outcomes."""
    verifier = IndependentVerifier(str(sample_repo))
    baseline = verifier.capture_baseline(run_tests=True)

    assert "test_add" in baseline["baseline_tests"]
    assert "test_add_negative" in baseline["baseline_tests"]

    outcomes = baseline["baseline_outcomes"]
    assert outcomes["executed"] is True
    assert outcomes["suite_passed"] is True
    assert outcomes["exit_code"] == 0
    assert "test_add" in outcomes["passed_tests"]
    assert "test_add_negative" in outcomes["passed_tests"]
    assert len(outcomes["failed_tests"]) == 0

def test_distinguish_preexisting_failures_from_newly_introduced_regressions():
    """Verify that verifier clearly distinguishes pre-existing baseline failures from new regressions."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        (repo / "calc").mkdir(parents=True)
        (repo / "tests").mkdir(parents=True)

        (repo / "calc" / "core.py").write_text("class Calc: pass\n", encoding="utf-8")
        # One passing test, one pre-existing failing test
        (repo / "tests" / "test_calc.py").write_text(
            "def test_passing_feature(): assert 1 == 1\n"
            "def test_preexisting_bug(): assert 1 == 2\n",
            encoding="utf-8",
        )

        verifier = IndependentVerifier(str(repo))
        baseline = verifier.capture_baseline(run_tests=True)

        assert "test_passing_feature" in baseline["baseline_outcomes"]["passed_tests"]
        assert "test_preexisting_bug" in baseline["baseline_outcomes"]["failed_tests"]
        assert baseline["baseline_outcomes"]["suite_passed"] is False

        # Case A: Coder implements changes, test_passing_feature still passes, test_preexisting_bug still fails
        state_no_regression: AgentState = {
            "task": "Add subtract method",
            "repo_path": str(repo),
            "relevant_files": ["calc/core.py"],
            "baseline_tests": baseline["baseline_tests"],
            "baseline_files": baseline["baseline_files"],
            "baseline_outcomes": baseline["baseline_outcomes"],
            "test_results": TestResult(
                passed=False,
                exit_code=1,
                stdout="test_passing_feature PASSED\ntest_preexisting_bug FAILED",
                stderr="",
                failed_tests=["tests/test_calc.py::test_preexisting_bug"],
                error_summary="assert 1 == 2",
            ),
            "review_result": ReviewResult(
                agent_name="ReviewerAgent",
                approved=True,
                quality_score=9.0,
                blocking_issues=[],
                non_blocking_feedback=[],
                security_checks=[],
                review_summary="Clean subtract method",
            ),
        }
        res_a = verifier.verify(state_no_regression)
        # MUST NOT flag test_preexisting_bug as a regression
        assert len(res_a.baseline_regressions) == 0
        assert "test_preexisting_bug" in res_a.pre_existing_failures
        assert res_a.baseline_tests_passed is True

        # Case B: Coder accidentally breaks test_passing_feature!
        state_with_regression: AgentState = {
            "task": "Refactor core",
            "repo_path": str(repo),
            "relevant_files": ["calc/core.py"],
            "baseline_tests": baseline["baseline_tests"],
            "baseline_files": baseline["baseline_files"],
            "baseline_outcomes": baseline["baseline_outcomes"],
            "test_results": TestResult(
                passed=False,
                exit_code=1,
                stdout="test_passing_feature FAILED\ntest_preexisting_bug FAILED",
                stderr="",
                failed_tests=["tests/test_calc.py::test_passing_feature", "tests/test_calc.py::test_preexisting_bug"],
                error_summary="assert 1 == 0",
            ),
            "review_result": ReviewResult(
                agent_name="ReviewerAgent",
                approved=True,
                quality_score=9.0,
                blocking_issues=[],
                non_blocking_feedback=[],
                security_checks=[],
                review_summary="Clean refactor",
            ),
        }
        res_b = verifier.verify(state_with_regression)
        # MUST flag test_passing_feature as a regression!
        assert "test_passing_feature" in res_b.baseline_regressions
        assert res_b.baseline_tests_passed is False
        assert any("Regressed: 1 previously passing baseline tests now fail: test_passing_feature" in r for r in res_b.failure_reasons)

        # Case C: Coder actually fixes test_preexisting_bug!
        state_fixed_bug: AgentState = {
            "task": "Fix preexisting bug",
            "repo_path": str(repo),
            "relevant_files": ["calc/core.py"],
            "baseline_tests": baseline["baseline_tests"],
            "baseline_files": baseline["baseline_files"],
            "baseline_outcomes": baseline["baseline_outcomes"],
            "test_results": TestResult(
                passed=True,
                exit_code=0,
                stdout="test_passing_feature PASSED\ntest_preexisting_bug PASSED",
                stderr="",
                failed_tests=[],
                error_summary="",
            ),
            "review_result": ReviewResult(
                agent_name="ReviewerAgent",
                approved=True,
                quality_score=9.5,
                blocking_issues=[],
                non_blocking_feedback=[],
                security_checks=[],
                review_summary="Bug fixed cleanly",
            ),
        }
        res_c = verifier.verify(state_fixed_bug)
        assert res_c.verified is True
        assert res_c.outcome == WorkflowOutcome.COMPLETED_SUCCESSFULLY
        assert "test_preexisting_bug" in res_c.fixed_tests
        assert len(res_c.baseline_regressions) == 0


# ============================================================
# 6. Mutation Tests: Weakened Tests & Assertion Auditing
# ============================================================

def test_weakened_test_commented_out_assertion_is_caught():
    """Mutation Test: Verify that commenting out an assertion inside an existing test function
    is caught by AST structure comparison and diff audit even though the function still exists.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        tests_dir = repo / "tests"
        tests_dir.mkdir(parents=True)
        calc_test = tests_dir / "test_math.py"
        calc_test.write_text(
            "def test_division():\n"
            "    result = 10 / 2\n"
            "    assert result == 5\n",
            encoding="utf-8",
        )

        verifier = IndependentVerifier(str(repo))
        baseline = verifier.capture_baseline(run_tests=False)
        assert "test_division" in baseline["baseline_tests"]
        assert baseline["baseline_test_structures"]["test_division"]["assertion_count"] == 1

        # MUTATION: Comment out the assert statement! Function still exists.
        calc_test.write_text(
            "def test_division():\n"
            "    result = 10 / 2\n"
            "    # assert result == 5\n",
            encoding="utf-8",
        )

        state: AgentState = {
            "task": "Refactor math",
            "repo_path": str(repo),
            "relevant_files": ["tests/test_math.py"],
            "baseline_tests": baseline["baseline_tests"],
            "baseline_files": baseline["baseline_files"],
            "baseline_test_structures": baseline["baseline_test_structures"],
            "baseline_test_files": baseline["baseline_test_files"],
            "baseline_file_hashes": baseline["baseline_file_hashes"],
            "test_results": TestResult(passed=True, exit_code=0, stdout="1 passed", stderr="", failed_tests=[], error_summary=""),
            "review_result": ReviewResult(agent_name="ReviewerAgent", approved=True, quality_score=9.0, blocking_issues=[], non_blocking_feedback=[], security_checks=[], review_summary="OK"),
        }

        res = verifier.verify(state)
        # MUST catch weakened test and reject verification!
        assert res.tests_preserved is False
        assert res.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
        assert len(res.diff_details.weakened_tests) > 0 or len(res.diff_details.deleted_assertions) > 0
        assert any("weakened" in r.lower() or "assertions deleted" in r.lower() for r in res.failure_reasons)


def test_weakened_test_assertion_count_reduction_is_caught():
    """Mutation Test: Verify reducing assertion count from 2 to 1 in a test is caught as weakened."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        tests_dir = repo / "tests"
        tests_dir.mkdir(parents=True)
        calc_test = tests_dir / "test_bounds.py"
        calc_test.write_text(
            "def test_multiple_assertions():\n"
            "    assert 1 == 1\n"
            "    assert 2 == 2\n",
            encoding="utf-8",
        )

        verifier = IndependentVerifier(str(repo))
        baseline = verifier.capture_baseline(run_tests=False)
        assert baseline["baseline_test_structures"]["test_multiple_assertions"]["assertion_count"] == 2

        # MUTATION: Delete one of the assertions
        calc_test.write_text(
            "def test_multiple_assertions():\n"
            "    assert 1 == 1\n",
            encoding="utf-8",
        )

        state: AgentState = {
            "task": "Clean up bounds",
            "repo_path": str(repo),
            "relevant_files": ["tests/test_bounds.py"],
            "baseline_tests": baseline["baseline_tests"],
            "baseline_files": baseline["baseline_files"],
            "baseline_test_structures": baseline["baseline_test_structures"],
            "baseline_test_files": baseline["baseline_test_files"],
            "baseline_file_hashes": baseline["baseline_file_hashes"],
            "test_results": TestResult(passed=True, exit_code=0, stdout="1 passed", stderr="", failed_tests=[], error_summary=""),
            "review_result": ReviewResult(agent_name="ReviewerAgent", approved=True, quality_score=9.0, blocking_issues=[], non_blocking_feedback=[], security_checks=[], review_summary="OK"),
        }

        res = verifier.verify(state)
        assert res.tests_preserved is False
        assert any("assertions reduced from 2 to 1" in w for w in res.diff_details.weakened_tests)


def test_actual_disk_change_detection_without_agent_metadata():
    """Verify changes to unauthorized files on disk are caught even if agent metadata omits them."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        src = repo / "calculator" / "core.py"
        src.parent.mkdir(parents=True)
        src.write_text("class Calc: pass\n", encoding="utf-8")

        verifier = IndependentVerifier(str(repo))
        baseline = verifier.capture_baseline(run_tests=False)

        # Unrelated file created silently on disk
        leak = repo / "secret_tampered.py"
        leak.write_text("MALICIOUS = True\n", encoding="utf-8")

        # Coder reports ONLY calculator/core.py in files_modified (omitting secret_tampered.py)
        coder_res = CoderResult(
            agent_name="CoderAgent",
            files_modified=["calculator/core.py"],  # silent omission!
            patches={},
            methods_implemented=[],
            rationale="Harmless patch",
            contracts=[],
        )

        diff_res = verifier.review_diff(
            baseline,
            relevant_files=["calculator/core.py"],
            coder_res=coder_res,
            test_gen_res=None,
        )

        # The actual disk hash audit must catch secret_tampered.py!
        assert "secret_tampered.py" in diff_res.unrelated_files_modified
        assert diff_res.passed is False


# ============================================================
# 7. Pydantic Type & Quality Score Edge Case Tests
# ============================================================

def test_coder_result_patches_default_is_dict():
    """Verify CoderResult.patches defaults to dict (not list)."""
    coder_res = CoderResult(rationale="test")
    assert isinstance(coder_res.patches, dict)
    assert coder_res.patches == {}


def test_review_result_quality_score_none_fails_verification(sample_repo):
    """Verify that a ReviewResult with missing quality_score defaults to None (explicit unavailable state)
    and does NOT automatically pass as perfect 10.0 quality.
    """
    verifier = IndependentVerifier(str(sample_repo))
    baseline = verifier.capture_baseline(run_tests=False)

    # Missing quality_score defaults to None
    review_unrated = ReviewResult(
        agent_name="ReviewerAgent",
        approved=True,
        # quality_score omitted -> None!
        blocking_issues=[],
        non_blocking_feedback=[],
        security_checks=[],
        review_summary="No score provided",
    )
    assert review_unrated.quality_score is None

    state: AgentState = {
        "repo_path": str(sample_repo),
        "relevant_files": ["calculator/core.py"],
        "baseline_tests": baseline["baseline_tests"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr="", failed_tests=[], error_summary=""),
        "review_result": review_unrated,
    }

    res = verifier.verify(state)
    assert res.reviewer_approved is False
    assert res.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert any("quality score is missing/unavailable" in r.lower() or "missing an explicit quality score" in r.lower() for r in res.failure_reasons)


def test_reviewer_approval_cryptographically_tied_to_exact_code(sample_repo):
    """Verify that reviewer approval is strictly tied to exact code hashes on disk.
    If code is modified after reviewer approval, verification detects tamper/stale approval.
    """
    import hashlib
    from agent.agents.reviewer import ReviewerAgent

    verifier = IndependentVerifier(str(sample_repo))
    baseline = verifier.capture_baseline(run_tests=True)

    # 1. Reviewer audits current code and computes cryptographic hashes
    reviewer = ReviewerAgent(str(sample_repo))
    if hasattr(reviewer.llm, "gemini"):
        reviewer.llm.gemini.generate = lambda *args, **kwargs: '{"approved": true, "quality_score": 9.5, "blocking_issues": [], "security_checks": ["Valid"]}'
    state: AgentState = {
        "task": "Review calculator addition",
        "repo_path": str(sample_repo),
        "relevant_files": ["calculator/core.py"],
        "baseline_tests": baseline["baseline_tests"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr="", failed_tests=[], error_summary=""),
    }
    review_res = reviewer.review_code(state)
    assert review_res.approved is True
    assert "calculator/core.py" in review_res.reviewed_file_hashes

    # 2. Exact code verified -> Reviewer approval accepted
    state["review_result"] = review_res
    res_valid = verifier.verify(state)
    assert res_valid.reviewer_approved is True
    assert res_valid.outcome == WorkflowOutcome.COMPLETED_SUCCESSFULLY

    # 3. Code on disk is modified AFTER review (tampered or post-review modification)
    calc_path = sample_repo / "calculator" / "core.py"
    calc_path.write_text("class Calculator:\n    def add(self, a, b):\n        return a + b + 999  # Tampered after review!\n", encoding="utf-8")

    # Verification MUST detect that file hash no longer matches reviewed hash
    res_tampered = verifier.verify(state)
    assert res_tampered.reviewer_approved is False
    assert res_tampered.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert any("modified after review" in r for r in res_tampered.failure_reasons)


def test_missing_baseline_snapshot_fails_closed_as_unverifiable(sample_repo):
    """Verify that an unavailable or unexecuted baseline snapshot with failing tests
    is classified as BASELINE_UNVERIFIABLE (inconclusive), fails closed, and does NOT
    falsely claim regressions.
    """
    from agent.verification.verifier import (
        IndependentVerifier,
        BaselineVerificationStatus,
        WorkflowOutcome,
        is_patch_admissible,
    )

    verifier = IndependentVerifier(str(sample_repo))

    # Baseline inventory has tests, but baseline outcomes snapshot was NEVER executed (unavailable)
    state: AgentState = {
        "repo_path": str(sample_repo),
        "relevant_files": ["calculator/core.py"],
        "baseline_tests": ["test_add", "test_add_negative"],
        "baseline_files": ["tests/test_calculator.py"],
        # baseline_outcomes is empty / unavailable
        "baseline_outcomes": {"executed": False, "passed_tests": [], "failed_tests": []},
        "test_results": TestResult(
            passed=False,
            exit_code=1,
            stdout="test_add FAILED",
            stderr="",
            failed_tests=["tests/test_calculator.py::test_add"],
            error_summary="AssertionError: 1 == 2",
        ),
        "review_result": ReviewResult(
            agent_name="ReviewerAgent",
            approved=True,
            quality_score=9.0,
            blocking_issues=[],
            review_summary="Clean implementation",
        ),
    }

    res = verifier.verify(state)

    # 1. Classified as BASELINE_UNVERIFIABLE (inconclusive state)
    assert res.baseline_status == BaselineVerificationStatus.UNVERIFIABLE

    # 2. Must NOT claim a regression without proof that test_add passed before
    assert len(res.baseline_regressions) == 0

    # 3. Fails closed: baseline_tests_passed must be False and outcome must be failure
    assert res.baseline_tests_passed is False
    assert res.verified is False
    assert res.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES

    # 4. Admission gate strictly blocks patch
    assert is_patch_admissible(res) is False

    # 5. Diagnostic records BASELINE_UNVERIFIABLE in failure reasons
    assert any("BASELINE_UNVERIFIABLE" in r for r in res.failure_reasons)


def test_empty_baseline_pass_snapshot_with_preexisting_failures_not_claimed_as_regression(sample_repo):
    """Scenario B: Verify that when baseline execution completed successfully with 0 passing tests
    and all failing tests, the snapshot is VERIFIED, failures are recognized as pre-existing,
    and no false regression is claimed.
    """
    from agent.verification.verifier import (
        IndependentVerifier,
        BaselineVerificationStatus,
        BaselineSnapshot,
        is_patch_admissible,
    )

    verifier = IndependentVerifier(str(sample_repo))

    # Baseline was executed, but test_add was already broken in baseline
    state: AgentState = {
        "repo_path": str(sample_repo),
        "relevant_files": ["calculator/core.py"],
        "baseline_tests": ["test_add"],
        "baseline_files": ["tests/test_calculator.py"],
        "baseline_snapshot": BaselineSnapshot(
            inventory={"test_add"},
            passed_tests=set(),  # Empty baseline-pass snapshot!
            failed_tests={"test_add"},  # Already failing before patch
            execution_completed=True,  # Execution completed cleanly!
            collection_completed=True,
            timed_out=False,
            execution_error=None,
        ).seal(),
        "baseline_snapshot_hash": None,
        "test_results": TestResult(
            passed=False,
            exit_code=1,
            stdout="test_add FAILED",
            stderr="",
            failed_tests=["tests/test_calculator.py::test_add"],
            error_summary="AssertionError: pre-existing defect",
        ),
        "review_result": ReviewResult(
            agent_name="ReviewerAgent",
            approved=True,
            quality_score=8.5,
            blocking_issues=[],
            review_summary="Audited",
        ),
    }
    state["baseline_snapshot_hash"] = state["baseline_snapshot"].snapshot_hash

    res = verifier.verify(state)

    # 1. Classified as VERIFIED because execution completed successfully (Scenario B)
    assert res.baseline_status == BaselineVerificationStatus.VERIFIED

    # 2. Must NOT claim regression!
    assert len(res.baseline_regressions) == 0
    assert "test_add" in res.pre_existing_failures

    # 3. Baseline tests are preserved and unregressed
    assert res.baseline_tests_passed is True

    # 4. If the agent successfully fixes test_add, patch is admitted clean:
    state_fixed = dict(state)
    state_fixed["test_results"] = TestResult(
        passed=True,
        exit_code=0,
        stdout="test_add PASSED",
        stderr="",
        failed_tests=[],
        error_summary="",
    )
    res_fixed = verifier.verify(state_fixed)
    assert res_fixed.baseline_status == BaselineVerificationStatus.VERIFIED
    assert "test_add" in res_fixed.fixed_tests
    assert len(res_fixed.baseline_regressions) == 0
    assert is_patch_admissible(res_fixed) is True


def test_baseline_snapshot_scenarios_a_b_c_integrity_derivation():
    """Verify explicit status derivation across Scenario A, B, C, Greenfield, and Incomplete Collection."""
    from agent.verification.verifier import (
        BaselineSnapshot,
        BaselineVerificationStatus,
        derive_baseline_status,
    )

    # Missing/Unsealed digest: Must fail closed to UNVERIFIABLE
    snap_unsealed = BaselineSnapshot(
        inventory={"T1"},
        passed_tests={"T1"},
        failed_tests=set(),
        execution_completed=True,
        collection_completed=True,
        timed_out=False,
        execution_error=None,
        snapshot_hash=None,
    )
    assert snap_unsealed.derive_status() == BaselineVerificationStatus.UNVERIFIABLE
    assert derive_baseline_status(snap_unsealed) == BaselineVerificationStatus.UNVERIFIABLE

    # Scenario A: Completed successfully, Passed: T1, Failed: None -> VERIFIED
    snap_a = BaselineSnapshot(
        inventory={"T1"},
        passed_tests={"T1"},
        failed_tests=set(),
        execution_completed=True,
        collection_completed=True,
        timed_out=False,
        execution_error=None,
    ).seal()
    assert snap_a.derive_status() == BaselineVerificationStatus.VERIFIED
    assert derive_baseline_status(snap_a) == BaselineVerificationStatus.VERIFIED

    # Scenario B: Completed successfully, Passed: None, Failed: T1, T2 -> VERIFIED
    snap_b = BaselineSnapshot(
        inventory={"T1", "T2"},
        passed_tests=set(),
        failed_tests={"T1", "T2"},
        execution_completed=True,
        collection_completed=True,
        timed_out=False,
        execution_error=None,
    ).seal()
    assert snap_b.derive_status() == BaselineVerificationStatus.VERIFIED
    assert derive_baseline_status(snap_b) == BaselineVerificationStatus.VERIFIED

    # Scenario C1: Timed out -> UNVERIFIABLE
    snap_c1 = BaselineSnapshot(
        inventory={"T1"},
        passed_tests=set(),
        failed_tests=set(),
        execution_completed=False,
        collection_completed=True,
        timed_out=True,
        execution_error="Execution timed out after 45s",
    ).seal()
    assert snap_c1.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    # Scenario C2: Never completed / aborted -> UNVERIFIABLE
    snap_c2 = BaselineSnapshot(
        inventory={"T1"},
        passed_tests=set(),
        failed_tests=set(),
        execution_completed=False,
        collection_completed=True,
        timed_out=False,
        execution_error=None,
    ).seal()
    assert snap_c2.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    # Scenario C3: Execution crashed / syntax error -> UNVERIFIABLE
    snap_c3 = BaselineSnapshot(
        inventory={"T1"},
        passed_tests=set(),
        failed_tests=set(),
        execution_completed=False,
        collection_completed=True,
        timed_out=False,
        execution_error="SyntaxError: invalid syntax in tests/test_foo.py",
    ).seal()
    assert snap_c3.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    # Greenfield: Empty inventory + confirmed collection -> NOT_APPLICABLE
    snap_greenfield = BaselineSnapshot(
        inventory=set(),
        passed_tests=set(),
        failed_tests=set(),
        execution_completed=True,
        collection_completed=True,
        timed_out=False,
        execution_error=None,
    ).seal()
    assert snap_greenfield.derive_status() == BaselineVerificationStatus.NOT_APPLICABLE

    # Incomplete collection: Broken filesystem / collection crashed -> UNVERIFIABLE
    snap_bad_collection = BaselineSnapshot(
        inventory=set(),
        passed_tests=set(),
        failed_tests=set(),
        execution_completed=False,
        collection_completed=False,
        timed_out=False,
        execution_error="PermissionDenied",
    ).seal()
    assert snap_bad_collection.derive_status() == BaselineVerificationStatus.UNVERIFIABLE


def test_baseline_tests_not_executed_incomplete_verification_rejected():
    """Verify that if test T1 passed before the patch, but was skipped/unexecuted post-patch
    (e.g. collection error or incomplete execution), it is correctly identified as
    baseline_tests_not_executed (not regression, but unexecuted), and is_patch_admissible
    strictly rejects admission.
    """
    from agent.verification.verifier import (
        IndependentVerifier,
        BaselineSnapshot,
        BaselineVerificationStatus,
        is_patch_admissible,
    )
    from agent.core.state import TestResult, ReviewResult

    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        # Create test file on disk so AST test preservation contract is satisfied
        test_file = repo_path / "test_service.py"
        test_file.write_text("def test_t1():\n    assert True\n\ndef test_t2():\n    assert True\n")
        verifier = IndependentVerifier(str(repo_path))

        snapshot = BaselineSnapshot(
            inventory={"test_t1", "test_t2"},
            passed_tests={"test_t1", "test_t2"},
            failed_tests=set(),
            execution_completed=True,
            collection_completed=True,
            timed_out=False,
            execution_error=None,
        ).seal()

        review_res = ReviewResult(
            agent_name="ReviewerAgent",
            approved=True,
            quality_score=9.5,
            blocking_issues=[],
            non_blocking_feedback=[],
            security_checks=["Passed"],
            review_summary="Clean pass",
        )

        # Post-patch test run executed test_t2, but skipped test_t1 due to collection error/skip
        incomplete_state = {
            "task": "Fix bug in service",
            "repo_path": str(repo_path),
            "relevant_files": [],
            "baseline_tests": ["test_t1", "test_t2"],
            "baseline_snapshot": snapshot,
            "baseline_snapshot_hash": snapshot.snapshot_hash,
            "baseline_outcomes": {
                "status": BaselineVerificationStatus.VERIFIED,
                "passed_tests": ["test_t1", "test_t2"],
                "failed_tests": [],
                "executed": True,
                "snapshot_hash": snapshot.snapshot_hash,
            },
            "test_results": TestResult(
                passed=True,
                exit_code=0,
                stdout="test_service.py::test_t2 PASSED\ntest_service.py::test_t1 SKIPPED",
                stderr="",
                failed_tests=[],
                passed_tests=["test_t2"],
                skipped_tests=["test_t1"],
            ),
            "review_result": review_res,
        }

        res = verifier.verify(incomplete_state)
        # 1. T1 is NOT in baseline_regressions (it did not fail with assertion failure)
        assert res.baseline_regressions == []
        # 2. T1 is in baseline_tests_not_executed (passed before, not successfully executed after)
        assert res.baseline_tests_not_executed == ["test_t1"]
        # 3. T2 is in baseline_tests_preserved (passed before, passed after)
        assert res.baseline_tests_preserved == ["test_t2"]
        # 4. Incomplete post-patch verification blocks baseline_tests_passed and marks verified=False
        assert res.baseline_tests_passed is False
        assert res.verified is False
        assert any("Incomplete baseline verification" in r for r in res.failure_reasons)
        # 5. Admission gate strictly rejects incomplete verification
        assert is_patch_admissible(res) is False

        # When post-patch executes both T1 and T2 successfully
        complete_state = {
            **incomplete_state,
            "test_results": TestResult(
                passed=True,
                exit_code=0,
                stdout="test_service.py::test_t1 PASSED\ntest_service.py::test_t2 PASSED",
                stderr="",
                failed_tests=[],
                passed_tests=["test_t1", "test_t2"],
                skipped_tests=[],
            ),
        }
        res_complete = verifier.verify(complete_state)
        assert res_complete.baseline_regressions == []
        assert res_complete.baseline_tests_not_executed == []
        assert res_complete.baseline_tests_preserved == ["test_t1", "test_t2"]
        assert res_complete.baseline_tests_passed is True
        assert res_complete.verified is True
        assert is_patch_admissible(res_complete) is True


def test_baseline_status_model_extended_matrix():
    """Comprehensive test matrix covering all 10 baseline status and admission gate scenarios:
    1. Missing baseline_status -> Admission blocked
    2. Baseline execution completed, all tests failed -> VERIFIED, zero regressions
    3. Baseline execution timed out -> UNVERIFIABLE, admission blocked
    4. Baseline collection failed -> UNVERIFIABLE, admission blocked
    5. Empty inventory with confirmed greenfield status -> NOT_APPLICABLE
    6. Empty inventory without confirmed collection -> UNVERIFIABLE
    7. Previously passing test fails after patch -> Regression recorded
    8. Previously passing test is skipped after patch -> Incomplete verification, admission blocked
    9. Baseline snapshot hash changes -> Verification blocked
    10. Unknown or invalid enum value -> Admission blocked
    """
    from enum import Enum
    from agent.verification.verifier import (
        BaselineSnapshot,
        BaselineVerificationStatus,
        VerificationResult,
        WorkflowOutcome,
        derive_baseline_status,
        is_patch_admissible,
        can_admit_patch,
        is_task_successful,
        VerifierAgent,
    )
    from agent.core.state import TestResult, ReviewResult

    # -------------------------------------------------------------
    # Case 1: Missing baseline_status -> Admission blocked
    # -------------------------------------------------------------
    res_case1 = VerificationResult(
        verified=True,
        outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        summary="Missing status test",
    )
    object.__setattr__(res_case1, "baseline_status", None)
    assert getattr(res_case1, "baseline_status", None) is None
    assert is_patch_admissible(res_case1) is False
    assert can_admit_patch(res_case1) is False
    assert is_task_successful({}, res_case1) is False

    # -------------------------------------------------------------
    # Case 1b: Missing snapshot_hash bypass check -> UNVERIFIABLE
    # -------------------------------------------------------------
    snap_unsealed = BaselineSnapshot(
        inventory={"test_t1"},
        passed_tests={"test_t1"},
        failed_tests=set(),
        execution_completed=True,
        collection_completed=True,
        snapshot_hash=None,
    )
    assert snap_unsealed.snapshot_hash is None
    assert snap_unsealed.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    # -------------------------------------------------------------
    # Case 2: Baseline completed, all tests failed -> VERIFIED, zero regressions
    # -------------------------------------------------------------
    snap_case2 = BaselineSnapshot(
        inventory={"test_t1", "test_t2"},
        passed_tests=set(),
        failed_tests={"test_t1", "test_t2"},
        execution_completed=True,
        collection_completed=True,
        timed_out=False,
        execution_error=None,
    ).seal()
    assert snap_case2.derive_status() == BaselineVerificationStatus.VERIFIED
    assert derive_baseline_status(snap_case2) == BaselineVerificationStatus.VERIFIED

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "test_suite.py").write_text("def test_t1(): assert True\ndef test_t2(): assert True\n")
        verifier = VerifierAgent(repo_path=tmp_path)
        state_case2 = {
            "baseline_snapshot": snap_case2,
            "baseline_snapshot_hash": snap_case2.snapshot_hash,
            "baseline_tests": ["test_t1", "test_t2"],
            "test_results": TestResult(
                passed=True,
                exit_code=0,
                stdout="test_suite.py::test_t1 PASSED\ntest_suite.py::test_t2 PASSED",
                failed_tests=[],
                passed_tests=["test_t1", "test_t2"],
            ),
            "review_result": ReviewResult(approved=True, quality_score=9.0, blocking_issues=[]),
        }
        res_case2 = verifier.verify(state_case2)
        assert res_case2.baseline_status == BaselineVerificationStatus.VERIFIED
        assert res_case2.baseline_regressions == []
        assert res_case2.baseline_tests_preserved == []
        assert res_case2.baseline_tests_not_executed == []
        assert res_case2.baseline_tests_passed is True
        assert res_case2.verified is True
        assert is_patch_admissible(res_case2) is True
        assert can_admit_patch(res_case2) is True

    # -------------------------------------------------------------
    # Case 3: Baseline execution timed out -> UNVERIFIABLE, admission blocked
    # -------------------------------------------------------------
    snap_case3 = BaselineSnapshot(
        inventory={"test_t1"},
        passed_tests=set(),
        failed_tests=set(),
        execution_completed=False,
        collection_completed=True,
        timed_out=True,
        execution_error="Pytest timed out after 60s",
    ).seal()
    assert snap_case3.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "test_suite.py").write_text("def test_t1(): assert True\n")
        verifier = VerifierAgent(repo_path=tmp_path)
        state_case3 = {
            "baseline_snapshot": snap_case3,
            "baseline_snapshot_hash": snap_case3.snapshot_hash,
            "baseline_tests": ["test_t1"],
            "test_results": TestResult(passed=True, exit_code=0, stdout="test_suite.py::test_t1 PASSED", passed_tests=["test_t1"]),
            "review_result": ReviewResult(approved=True, quality_score=9.0, blocking_issues=[]),
        }
        res_case3 = verifier.verify(state_case3)
        assert res_case3.baseline_status == BaselineVerificationStatus.UNVERIFIABLE
        assert res_case3.verified is False
        assert any("BASELINE_UNVERIFIABLE" in r for r in res_case3.failure_reasons)
        assert is_patch_admissible(res_case3) is False
        assert can_admit_patch(res_case3) is False

    # -------------------------------------------------------------
    # Case 4: Baseline collection failed -> UNVERIFIABLE, admission blocked
    # -------------------------------------------------------------
    snap_case4 = BaselineSnapshot(
        inventory={"test_t1"},
        passed_tests=set(),
        failed_tests=set(),
        execution_completed=False,
        collection_completed=False,
        timed_out=False,
        execution_error="CollectionError during discovery",
    ).seal()
    assert snap_case4.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "test_suite.py").write_text("def test_t1(): assert True\n")
        verifier = VerifierAgent(repo_path=tmp_path)
        state_case4 = {
            "baseline_snapshot": snap_case4,
            "baseline_snapshot_hash": snap_case4.snapshot_hash,
            "baseline_tests": ["test_t1"],
            "test_results": TestResult(passed=True, exit_code=0, stdout="test_suite.py::test_t1 PASSED", passed_tests=["test_t1"]),
            "review_result": ReviewResult(approved=True, quality_score=9.0, blocking_issues=[]),
        }
        res_case4 = verifier.verify(state_case4)
        assert res_case4.baseline_status == BaselineVerificationStatus.UNVERIFIABLE
        assert res_case4.verified is False
        assert is_patch_admissible(res_case4) is False

    # -------------------------------------------------------------
    # Case 5: Empty inventory with confirmed greenfield status -> NOT_APPLICABLE
    # -------------------------------------------------------------
    snap_case5 = BaselineSnapshot(
        inventory=set(),
        passed_tests=set(),
        failed_tests=set(),
        execution_completed=True,
        collection_completed=True,
        timed_out=False,
        execution_error=None,
    ).seal()
    assert snap_case5.derive_status() == BaselineVerificationStatus.NOT_APPLICABLE

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        verifier = VerifierAgent(repo_path=tmp_path)
        state_case5 = {
            "baseline_snapshot": snap_case5,
            "baseline_snapshot_hash": snap_case5.snapshot_hash,
            "baseline_tests": [],
            "test_results": TestResult(passed=True, exit_code=0, stdout="no tests ran", passed_tests=[]),
            "review_result": ReviewResult(approved=True, quality_score=9.0, blocking_issues=[]),
        }
        res_case5 = verifier.verify(state_case5)
        assert res_case5.baseline_status == BaselineVerificationStatus.NOT_APPLICABLE
        assert res_case5.baseline_inventory_count == 0
        assert res_case5.verified is True
        assert is_patch_admissible(res_case5) is True

    # -------------------------------------------------------------
    # Case 6: Empty inventory without confirmed collection -> UNVERIFIABLE
    # -------------------------------------------------------------
    snap_case6 = BaselineSnapshot(
        inventory=set(),
        passed_tests=set(),
        failed_tests=set(),
        execution_completed=False,
        collection_completed=False,
        timed_out=False,
        execution_error="Directory permission denied",
    ).seal()
    assert snap_case6.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        verifier = VerifierAgent(repo_path=tmp_path)
        state_case6 = {
            "baseline_snapshot": snap_case6,
            "baseline_snapshot_hash": snap_case6.snapshot_hash,
            "baseline_tests": [],
            "test_results": TestResult(passed=True, exit_code=0, stdout=""),
            "review_result": ReviewResult(approved=True, quality_score=9.0, blocking_issues=[]),
        }
        res_case6 = verifier.verify(state_case6)
        assert res_case6.baseline_status == BaselineVerificationStatus.UNVERIFIABLE
        assert res_case6.verified is False
        assert is_patch_admissible(res_case6) is False

    # -------------------------------------------------------------
    # Case 7: Previously passing test fails after patch -> Regression recorded
    # -------------------------------------------------------------
    snap_case7 = BaselineSnapshot(
        inventory={"test_t1"},
        passed_tests={"test_t1"},
        failed_tests=set(),
        execution_completed=True,
        collection_completed=True,
    ).seal()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "test_suite.py").write_text("def test_t1(): assert False\n")
        verifier = VerifierAgent(repo_path=tmp_path)
        state_case7 = {
            "baseline_snapshot": snap_case7,
            "baseline_snapshot_hash": snap_case7.snapshot_hash,
            "baseline_tests": ["test_t1"],
            "test_results": TestResult(
                passed=False,
                exit_code=1,
                stdout="test_suite.py::test_t1 FAILED",
                failed_tests=["test_t1"],
                passed_tests=[],
            ),
            "review_result": ReviewResult(approved=True, quality_score=9.0, blocking_issues=[]),
        }
        res_case7 = verifier.verify(state_case7)
        assert "test_t1" in res_case7.baseline_regressions
        assert res_case7.baseline_tests_passed is False
        assert res_case7.verified is False
        assert is_patch_admissible(res_case7) is False

    # -------------------------------------------------------------
    # Case 8: Previously passing test is skipped after patch -> Incomplete verification, admission blocked
    # -------------------------------------------------------------
    snap_case8 = BaselineSnapshot(
        inventory={"test_t1", "test_t2"},
        passed_tests={"test_t1", "test_t2"},
        failed_tests=set(),
        execution_completed=True,
        collection_completed=True,
    ).seal()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "test_suite.py").write_text("def test_t1(): assert True\ndef test_t2(): assert True\n")
        verifier = VerifierAgent(repo_path=tmp_path)
        state_case8 = {
            "baseline_snapshot": snap_case8,
            "baseline_snapshot_hash": snap_case8.snapshot_hash,
            "baseline_tests": ["test_t1", "test_t2"],
            "test_results": TestResult(
                passed=True,
                exit_code=0,
                stdout="test_suite.py::test_t1 SKIPPED\ntest_suite.py::test_t2 PASSED",
                failed_tests=[],
                passed_tests=["test_t2"],
                skipped_tests=["test_t1"],
            ),
            "review_result": ReviewResult(approved=True, quality_score=9.0, blocking_issues=[]),
        }
        res_case8 = verifier.verify(state_case8)
        assert "test_t1" in res_case8.baseline_tests_not_executed
        assert "test_t2" in res_case8.baseline_tests_preserved
        assert res_case8.baseline_tests_passed is False
        assert res_case8.verified is False
        assert is_patch_admissible(res_case8) is False

    # -------------------------------------------------------------
    # Case 9: Baseline snapshot hash changes -> Verification blocked
    # -------------------------------------------------------------
    snap_case9 = BaselineSnapshot(
        inventory={"test_t1"},
        passed_tests={"test_t1"},
        failed_tests=set(),
        execution_completed=True,
        collection_completed=True,
    )
    original_digest = snap_case9.compute_hash()
    snap_case9.snapshot_hash = original_digest
    assert snap_case9.derive_status() == BaselineVerificationStatus.VERIFIED

    # Tamper with snapshot by injecting a test into inventory/passed
    snap_case9.passed_tests.add("test_t_tampered")
    assert snap_case9.compute_hash() != original_digest
    assert snap_case9.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "test_suite.py").write_text("def test_t1(): assert True\n")
        verifier = VerifierAgent(repo_path=tmp_path)
        state_case9 = {
            "baseline_snapshot": snap_case9,
            "baseline_snapshot_hash": original_digest, # Original digest recorded before tampering
            "baseline_tests": ["test_t1"],
            "test_results": TestResult(
                passed=True,
                exit_code=0,
                stdout="test_suite.py::test_t1 PASSED",
                passed_tests=["test_t1"],
            ),
            "review_result": ReviewResult(approved=True, quality_score=9.0, blocking_issues=[]),
        }
        res_case9 = verifier.verify(state_case9)
        assert res_case9.baseline_snapshot_hash_valid is False
        assert res_case9.baseline_status == BaselineVerificationStatus.UNVERIFIABLE
        assert res_case9.verified is False
        assert res_case9.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
        assert any("integrity violation" in r.lower() or "snapshot hash" in r.lower() for r in res_case9.failure_reasons)
        assert is_patch_admissible(res_case9) is False
        assert is_task_successful(state_case9, res_case9) is False

    # -------------------------------------------------------------
    # Case 10: Unknown or invalid enum value -> Admission blocked
    # -------------------------------------------------------------
    class RogueStatus(Enum):
        ROGUE = "ROGUE_STATUS"

    res_case10 = VerificationResult(
        verified=True,
        outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        summary="Testing rogue status",
    )
    # 10a. Unrecognized string
    object.__setattr__(res_case10, "baseline_status", "UNKNOWN_STATUS_STRING")
    assert is_patch_admissible(res_case10) is False
    assert can_admit_patch(res_case10) is False
    assert is_task_successful({}, res_case10) is False

    # 10b. Unrecognized Enum class member
    object.__setattr__(res_case10, "baseline_status", RogueStatus.ROGUE)
    assert is_patch_admissible(res_case10) is False
    assert can_admit_patch(res_case10) is False
    assert is_task_successful({}, res_case10) is False

    # 10c. Invalid numeric value
    object.__setattr__(res_case10, "baseline_status", 999)
    assert is_patch_admissible(res_case10) is False
    assert can_admit_patch(res_case10) is False
    assert is_task_successful({}, res_case10) is False





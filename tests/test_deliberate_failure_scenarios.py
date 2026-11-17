"""Tests for Deliberate Failure Scenarios and Boundary Defenses.

Explicitly validates the 10 failure scenarios:
1. Coder generates incorrect code -> Tests detect the failure
2. Test Generator creates a bad/weakened test -> Review & diff analyzer detect it
3. Sandbox crashes -> Debugger investigates the failure & isolates root cause
4. Reviewer rejects code -> Manager delegates corrective work
5. Retry limit is reached -> Agent fails closed (never false success)
6. User cancels execution -> Agent stops at safe boundary
7. Files change after review -> Final verification rejects stale approval & TOCTOU violation
8. Application crashes mid-workflow -> Checkpoint recovery resumes safely from SQLite WAL
9. Manager produces an invalid decision -> Safe fallback to finalize; no false success
10. Agent modifies unrelated files -> Scope verification rejects the change
"""

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
import pytest

from agent.core.state import (
    AgentState,
    TestResult,
    ReviewResult,
    CoderResult,
    TestGenResult,
    ManagerDecision,
)
from agent.verification.verifier import (
    IndependentVerifier,
    WorkflowOutcome,
    VerificationResult,
    is_task_successful,
)
from agent.execution.sandbox import ExecutionSandbox
from agent.agents.manager import ManagerPlannerAgent
from agent.agents.debugger import DebuggerAgent
from agent.agents.reviewer import ReviewerAgent
from agent.core.graph import (
    manager_evaluate_node,
    manager_finalize_node,
    coder_node,
    route_manager_decision,
)
from agent.core.checkpointer import SqliteCheckpointSaver


@pytest.fixture
def testbed_repo():
    """Sets up an isolated temporary repository for failure injection."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        (repo / "calculator").mkdir(parents=True, exist_ok=True)
        (repo / "tests").mkdir(parents=True, exist_ok=True)
        (repo / "docs").mkdir(parents=True, exist_ok=True)

        (repo / "calculator" / "core.py").write_text(
            "class Calculator:\n"
            "    def add(self, a, b):\n"
            "        return a + b\n"
            "    def divide(self, a, b):\n"
            "        if b == 0:\n"
            "            raise ValueError('Cannot divide by zero.')\n"
            "        return a / b\n",
            encoding="utf-8",
        )
        (repo / "tests" / "test_calculator.py").write_text(
            "import pytest\n"
            "from calculator.core import Calculator\n\n"
            "def test_add():\n"
            "    c = Calculator()\n"
            "    assert c.add(2, 3) == 5\n\n"
            "def test_divide_zero():\n"
            "    c = Calculator()\n"
            "    with pytest.raises(ValueError):\n"
            "        c.divide(10, 0)\n",
            encoding="utf-8",
        )
        (repo / "docs" / "readme.txt").write_text("Project docs\n", encoding="utf-8")
        yield repo


# ============================================================
# Scenario 1: Coder generates incorrect code -> Tests detect failure
# ============================================================

def test_scenario_1_coder_generates_incorrect_code_caught_by_tests(testbed_repo):
    """When Coder introduces broken logic, isolated sandbox tests catch the defect."""
    # Deliberate failure injection: Coder breaks add logic
    broken_code = (
        "class Calculator:\n"
        "    def add(self, a, b):\n"
        "        return a - b  # BUG injected\n"
        "    def divide(self, a, b):\n"
        "        return a / b\n"
    )
    (testbed_repo / "calculator" / "core.py").write_text(broken_code, encoding="utf-8")

    sandbox = ExecutionSandbox(str(testbed_repo))
    res = sandbox.run_pytest()

    assert res.passed is False
    assert res.exit_code != 0
    assert any("test_add" in t for t in res.failed_tests)

    verifier = IndependentVerifier(str(testbed_repo))
    state: AgentState = {
        "task": "Add calculator features",
        "repo_path": str(testbed_repo),
        "relevant_files": ["calculator/core.py"],
        "test_results": res,
    }
    v_res = verifier.verify(state)
    assert v_res.tests_passed is False
    assert v_res.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert is_task_successful(state, v_res) is False


# ============================================================
# Scenario 2: Test Generator creates bad/weakened test -> Review detects it
# ============================================================

def test_scenario_2_test_generator_creates_bad_or_weakened_test_caught_by_review(testbed_repo):
    """When test generator comments out assertions to fake a pass, verifier rejects it."""
    verifier = IndependentVerifier(str(testbed_repo))
    baseline = verifier.capture_baseline(run_tests=False)

    # Deliberate failure injection: Comment out assert statement to weaken test
    weakened_test = (
        "import pytest\n"
        "from calculator.core import Calculator\n\n"
        "def test_add():\n"
        "    c = Calculator()\n"
        "    # assert c.add(2, 3) == 5  (WEAKENED/COMMENTED OUT!)\n"
        "    pass\n\n"
        "def test_divide_zero():\n"
        "    c = Calculator()\n"
        "    with pytest.raises(ValueError):\n"
        "        c.divide(10, 0)\n"
    )
    (testbed_repo / "tests" / "test_calculator.py").write_text(weakened_test, encoding="utf-8")

    state: AgentState = {
        "task": "Refactor calculator",
        "repo_path": str(testbed_repo),
        "relevant_files": ["calculator/core.py"],
        "baseline_tests": baseline["baseline_tests"],
        "baseline_files": baseline["baseline_files"],
        "baseline_test_structures": baseline["baseline_test_structures"],
        "baseline_test_files": baseline["baseline_test_files"],
        "baseline_file_hashes": baseline["baseline_file_hashes"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
        "review_result": ReviewResult(
            agent_name="ReviewerAgent",
            approved=True,
            quality_score=9.0,
            blocking_issues=[],
            review_summary="Looks acceptable to reviewer",
        ),
    }
    v_res = verifier.verify(state)

    assert v_res.tests_preserved is False
    assert v_res.diff_passed is False
    assert v_res.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert is_task_successful(state, v_res) is False
    assert len(v_res.diff_details.weakened_tests) > 0 or len(v_res.diff_details.deleted_assertions) > 0


# ============================================================
# Scenario 3: Sandbox crashes -> Debugger investigates failure
# ============================================================

def test_scenario_3_sandbox_crashes_investigated_by_debugger(testbed_repo):
    """When sandbox execution crashes with exception, DebuggerAgent diagnoses root cause."""
    failed_test_result = TestResult(
        passed=False,
        exit_code=1,
        stdout="FAILED tests/test_calculator.py::test_divide_zero - ZeroDivisionError: division by zero",
        stderr="Traceback (most recent call last):\n  File 'calculator/core.py', line 5, in divide\n    return a / b\nZeroDivisionError: division by zero",
        failed_tests=["test_divide_zero"],
        error_summary="ZeroDivisionError: division by zero at Calculator.divide line 5",
    )

    debugger = DebuggerAgent(str(testbed_repo))
    state: AgentState = {
        "task": "Fix zero division bug",
        "repo_path": str(testbed_repo),
        "test_results": failed_test_result,
        "iteration_count": 1,
    }

    diag = debugger.diagnose_failure(state)
    assert diag.agent_name == "DebuggerAgent"
    assert "test_divide_zero" in diag.failing_tests
    assert any(token in diag.root_cause.lower() for token in ["zero", "divis", "divide"])
    assert diag.target_fix_agent == "coder"
    assert len(diag.remediation_plan) > 0


# ============================================================
# Scenario 4: Reviewer rejects code -> Manager delegates corrective work
# ============================================================

def test_scenario_4_reviewer_rejects_code_manager_delegates_corrective_work(testbed_repo):
    """When Reviewer finds blocking issues, Manager routes to remediation."""
    rejected_review = ReviewResult(
        agent_name="ReviewerAgent",
        approved=False,
        quality_score=4.5,
        blocking_issues=["Missing bounds check on negative numbers", "Unsanitized user input"],
        reviewed_hashes={"calculator/core.py": "dummy_hash"},
        review_summary="Code review rejected due to security and bounds violations",
    )

    state: AgentState = {
        "task": "Implement secure divide",
        "repo_path": str(testbed_repo),
        "review_result": rejected_review,
        "iteration_count": 0,
        "max_iterations": 3,
        "test_results": TestResult(passed=True, exit_code=0, stdout="", stderr=""),
    }

    manager = ManagerPlannerAgent()
    eval_res = manager.evaluate_and_route(state)

    assert eval_res.next_action in ("delegate_coder", "delegate_debug")
    assert "rejected" in eval_res.reasoning.lower() or "blocking" in eval_res.reasoning.lower()


# ============================================================
# Scenario 5: Retry limit is reached -> Agent fails closed
# ============================================================

def test_scenario_5_retry_limit_reached_agent_fails_closed(testbed_repo):
    """When retry budget is exhausted, Manager routes to finalize and Verifier fails closed."""
    failing_test_result = TestResult(
        passed=False,
        exit_code=1,
        stdout="FAILED",
        stderr="AssertionError",
        failed_tests=["test_add"],
    )

    state: AgentState = {
        "task": "Fix elusive defect",
        "repo_path": str(testbed_repo),
        "iteration_count": 3,
        "max_iterations": 3,
        "test_results": failing_test_result,
    }

    manager = ManagerPlannerAgent()
    eval_res = manager.evaluate_and_route(state)
    assert eval_res.next_action == "finalize"
    assert "max iterations" in eval_res.reasoning.lower() or "exhausted" in eval_res.reasoning.lower() or "halting" in eval_res.reasoning.lower()

    verifier = IndependentVerifier(str(testbed_repo))
    v_res = verifier.verify(state)
    assert v_res.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert is_task_successful(state, v_res) is False


# ============================================================
# Scenario 6: User cancels execution -> Agent stops at safe boundary
# ============================================================

def test_scenario_6_user_cancels_execution_stops_at_safe_boundary(testbed_repo):
    """When cancelled flag is set, pipeline nodes halt immediately without performing work."""
    state: AgentState = {
        "task": "Cancelled task",
        "repo_path": str(testbed_repo),
        "cancelled": True,
        "iteration_count": 0,
    }

    coder_updates = coder_node(state)
    assert coder_updates["status"] == "cancelled"

    fin_updates = manager_finalize_node(state)
    assert fin_updates["status"] == "cancelled"
    assert fin_updates["workflow_outcome"] == "cancelled"
    assert fin_updates["task_succeeded"] is False


# ============================================================
# Scenario 7: Files change after review -> Verification rejects stale approval
# ============================================================

def test_scenario_7_files_change_after_review_verification_rejects_stale_approval(testbed_repo):
    """If a file mutates on disk after review, hash check detects tamper and fails verification."""
    verifier = IndependentVerifier(str(testbed_repo))
    baseline = verifier.capture_baseline(run_tests=False)

    reviewer = ReviewerAgent(str(testbed_repo))
    reviewer.llm.is_available = lambda: False
    state: AgentState = {
        "task": "Review clean code",
        "repo_path": str(testbed_repo),
        "relevant_files": ["calculator/core.py"],
        "baseline_tests": baseline["baseline_tests"],
        "baseline_files": baseline["baseline_files"],
        "baseline_test_structures": baseline["baseline_test_structures"],
        "baseline_test_files": baseline["baseline_test_files"],
        "baseline_file_hashes": baseline["baseline_file_hashes"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
    }
    review_res = reviewer.review_code(state)
    state["review_result"] = review_res

    # Simulate post-review tampering / race condition
    (testbed_repo / "calculator" / "core.py").write_text("# Injected mutation\n", encoding="utf-8")

    v_res = verifier.verify(state)
    assert v_res.reviewer_approved is False
    assert v_res.review_hashes_valid is False
    assert v_res.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert is_task_successful(state, v_res) is False
    assert any("files were modified after review" in f for f in v_res.failure_reasons)


# ============================================================
# Scenario 8: Application crashes mid-workflow -> Checkpoint recovery resumes
# ============================================================

def test_scenario_8_application_crashes_mid_workflow_checkpoint_recovery_resumes_safely():
    """When process dies mid-pipeline, SqliteCheckpointSaver restores exact state on restart."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "checkpoints.sqlite"
        saver1 = SqliteCheckpointSaver(str(db_path))

        thread_cfg = {"configurable": {"thread_id": "thread-crash-recovery-999", "checkpoint_ns": ""}}
        checkpoint_data = {
            "v": 1,
            "id": "chk-crash-999",
            "ts": "2026-11-02T12:00:00Z",
            "channel_values": {
                "task": "Mission critical patch",
                "iteration_count": 2,
                "status": "debugging",
                "active_step": 3,
            },
            "channel_versions": {"task": 1, "iteration_count": 1, "status": 1, "active_step": 1},
            "versions_seen": {},
        }
        saver1.put(
            thread_cfg,
            checkpoint_data,
            {"source": "node", "step": 3, "writes": {}},
            {"task": 1, "iteration_count": 1, "status": 1, "active_step": 1},
        )

        # Simulate fresh process startup after crash
        saver2 = SqliteCheckpointSaver(str(db_path))
        recovered = saver2.get_tuple(thread_cfg)

        assert recovered is not None
        assert recovered.checkpoint["channel_values"]["iteration_count"] == 2
        assert recovered.checkpoint["channel_values"]["status"] == "debugging"
        assert recovered.checkpoint["channel_values"]["active_step"] == 3


# ============================================================
# Scenario 9: Manager produces invalid decision -> Safe fallback; no false success
# ============================================================

def test_scenario_9_manager_produces_invalid_decision_safe_fallback_no_false_success(testbed_repo):
    """When Manager produces an unrecognized or hallucinated action, router safely routes to finalize."""
    invalid_decision = SimpleNamespace(
        agent_name="ManagerAgent",
        iteration=0,
        next_action="hallucinated_unknown_action",
        reasoning="Model produced invalid output",
    )
    state: AgentState = {
        "task": "Test fallback",
        "repo_path": str(testbed_repo),
        "manager_decision": invalid_decision,
        "test_results": None,
    }

    # route_manager_decision must catch unrecognized action and fall back strictly to manager_finalize
    next_node = route_manager_decision(state)
    assert next_node == "manager_finalize"

    # Even if finalize executes, independent verifier enforces sovereign failure
    fin_updates = manager_finalize_node(state)
    assert fin_updates["task_succeeded"] is False
    assert fin_updates["workflow_outcome"] == "completed_with_failures"


# ============================================================
# Scenario 10: Agent modifies unrelated files -> Scope verification rejects
# ============================================================

def test_scenario_10_agent_modifies_unrelated_files_scope_verification_rejects(testbed_repo):
    """When Coder modifies files outside designated task scope, verifier rejects scope creep."""
    verifier = IndependentVerifier(str(testbed_repo))
    baseline = verifier.capture_baseline(run_tests=False)

    # Injected scope violation: task is only for core.py, but coder also modifies docs/readme.txt
    (testbed_repo / "docs" / "readme.txt").write_text("Unauthorized modification!\n", encoding="utf-8")

    reviewer = ReviewerAgent(str(testbed_repo))
    reviewer.llm.is_available = lambda: False
    state: AgentState = {
        "task": "Fix calculator core",
        "repo_path": str(testbed_repo),
        "relevant_files": ["calculator/core.py"],  # docs/readme.txt is NOT in scope
        "baseline_tests": baseline["baseline_tests"],
        "baseline_files": baseline["baseline_files"],
        "baseline_test_structures": baseline["baseline_test_structures"],
        "baseline_test_files": baseline["baseline_test_files"],
        "baseline_file_hashes": baseline["baseline_file_hashes"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
    }
    state["review_result"] = reviewer.review_code(state)

    v_res = verifier.verify(state)
    assert v_res.git_diff_clean is False
    assert v_res.diff_passed is False
    assert v_res.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert is_task_successful(state, v_res) is False
    assert any("docs/readme.txt" in f for f in v_res.failure_reasons)

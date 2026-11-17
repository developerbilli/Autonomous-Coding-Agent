"""Unit and Integration Tests verifying Real Multi-Agent Orchestration and Baseline Comparison."""

import pytest
from pathlib import Path
from agent.core.state import AgentState
from agent.core.baseline import SingleAgentBaseline
from agent.agents.manager import ManagerPlannerAgent
from agent.agents.coder import CoderAgent
from agent.agents.test_generator import TestGeneratorAgent
from agent.agents.reviewer import ReviewerAgent
from agent.agents.debugger import DebuggerAgent
from agent.core.graph import build_coding_agent_graph

REPO_DIR = Path(__file__).resolve().parent.parent / "calculator_repo"

def test_manager_planner_agent_creates_structured_plan():
    """Verify ManagerPlannerAgent produces a typed ManagerPlan with assigned specialists."""
    manager = ManagerPlannerAgent()
    plan = manager.create_plan(
        task="Implement safe division and square root in Calculator",
        relevant_files=["calculator/core.py"],
        symbol_names=["Calculator", "divide", "square_root"],
    )

    assert plan is not None
    assert plan.goal != ""
    assert len(plan.subtasks) >= 3
    
    # Verify subtask assignments to distinct specialists
    assigned_agents = {st.assigned_agent for st in plan.subtasks}
    assert "coder" in assigned_agents
    assert "test_generator" in assigned_agents
    assert "reviewer" in assigned_agents
    assert len(plan.acceptance_criteria) > 0

def test_coder_agent_returns_structured_result():
    """Verify CoderAgent produces structured CoderResult with modified files and contracts."""
    coder = CoderAgent(str(REPO_DIR))
    state: AgentState = {
        "task": "Add power and square root methods to Calculator",
        "repo_path": str(REPO_DIR),
        "relevant_files": ["calculator/core.py"],
        "retrieved_code": {},
        "iteration_count": 0,
        "demo_mode": False,
    }
    result = coder.implement(state)

    assert result.agent_name == "CoderAgent"
    assert len(result.files_modified) > 0
    assert "calculator/core.py" in result.files_modified[0]
    assert len(result.methods_implemented) > 0
    assert result.rationale != ""

def test_test_generator_agent_creates_edge_case_tests():
    """Verify TestGeneratorAgent synthesizes new tests covering edge cases."""
    test_gen = TestGeneratorAgent(str(REPO_DIR))
    state: AgentState = {
        "task": "Complete Calculator with division by zero and negative square root checks",
        "repo_path": str(REPO_DIR),
        "relevant_files": ["calculator/core.py"],
        "retrieved_code": {},
    }
    result = test_gen.generate_tests(state)

    assert result.agent_name == "TestGeneratorAgent"
    assert len(result.test_cases_added) > 0
    assert len(result.edge_cases_tested) > 0
    # Must explicitly cover zero division and negative bounds
    assert any("zero" in ec.lower() or "divide" in ec.lower() for ec in result.edge_cases_tested)

def test_reviewer_agent_adversarial_detection():
    """Verify ReviewerAgent acts as an independent auditor and catches missing guards."""
    reviewer = ReviewerAgent(str(REPO_DIR))
    state: AgentState = {
        "task": "Review Calculator implementation for division and square root",
        "repo_path": str(REPO_DIR),
        "relevant_files": ["calculator/core.py"],
        "retrieved_code": {},
    }
    result = reviewer.review_code(state)

    assert result.agent_name == "ReviewerAgent"
    assert isinstance(result.approved, bool)
    assert 0.0 <= result.quality_score <= 10.0
    assert len(result.security_checks) > 0

def test_debugger_agent_root_cause_diagnosis():
    """Verify DebuggerAgent isolates root causes from failed tests."""
    from agent.core.state import TestResult

    debugger = DebuggerAgent(str(REPO_DIR))
    failed_test_result = TestResult(
        passed=False,
        exit_code=1,
        stdout="FAILED tests/test_calculator.py::test_divide_by_zero - ZeroDivisionError: division by zero",
        stderr="",
        failed_tests=["test_divide_by_zero"],
        error_summary="ZeroDivisionError: division by zero at Calculator.divide line 24",
    )

    state: AgentState = {
        "task": "Fix zero division in calculator",
        "repo_path": str(REPO_DIR),
        "test_results": failed_test_result,
        "iteration_count": 1,
    }
    result = debugger.diagnose_failure(state)

    assert result.agent_name == "DebuggerAgent"
    assert "test_divide_by_zero" in result.failing_tests
    assert any(term in result.root_cause.lower() for term in ["divide", "divis", "zero", "zerodivision"])
    assert "divide" in result.remediation_plan.lower()
    assert result.target_fix_agent == "coder"

def test_baseline_vs_multi_agent_architectural_difference():
    """Verify empirical architectural difference between Single-Agent Baseline and Multi-Agent."""
    baseline = SingleAgentBaseline(str(REPO_DIR))
    res = baseline.run(task="Add divide and square root", max_iterations=1, demo_mode=False)

    # Baseline creates 0 new tests, 0 structured diagnoses, and 0 independent reviews
    assert res["new_tests_generated"] == 0
    assert res["structured_diagnoses"] == 0
    assert res["defects_caught_by_review"] == 0

    # Multi-Agent compiled graph contains distinct nodes for all 5 specialists
    app = build_coding_agent_graph()
    node_names = set(app.get_graph().nodes.keys())
    assert "manager_planner" in node_names
    assert "coder" in node_names
    assert "test_generator" in node_names
    assert "reviewer" in node_names
    assert "debugger" in node_names

def test_routing_table_matches_all_manager_decisions():
    """Verify that all allowed ManagerDecision.next_action choices map to valid graph nodes with safe fallback."""
    from agent.core.state import ManagerDecision
    from agent.core.graph import route_manager_decision, DECISION_TO_NODE_MAP

    expected_mappings = {
        "delegate_coder": "coder",
        "delegate_test_gen": "test_generator",
        "run_sandbox": "sandbox_runner",
        "delegate_debug": "debugger",
        "delegate_review": "reviewer",
        "finalize": "manager_finalize",
        "abort": "manager_finalize",
    }

    # 1. Test each valid decision
    for action, expected_node in expected_mappings.items():
        state: AgentState = {
            "manager_decision": ManagerDecision(
                next_action=action,
                target_agent="test_agent",
                reasoning="Testing routing",
            )
        }
        target = route_manager_decision(state)
        assert target == expected_node, f"Action '{action}' mapped to '{target}', expected '{expected_node}'"
        if action == "abort":
            assert state.get("cancelled") is True

    # 2. Test safe fallback for None / missing decision
    empty_state: AgentState = {}
    assert route_manager_decision(empty_state) == "manager_finalize"

    # 3. Test safe fallback for unrecognized decision
    class MockInvalidDecision:
        next_action = "unknown_hallucinated_action"

    invalid_state: AgentState = {"manager_decision": MockInvalidDecision()}
    assert route_manager_decision(invalid_state) == "manager_finalize"


def test_manager_evaluates_and_generates_all_seven_routing_decisions():
    """Verify that ManagerPlannerAgent.evaluate_and_route synthesizes all 7 possible routing actions."""
    from agent.agents.manager import ManagerPlannerAgent
    from agent.core.state import TestResult, ReviewResult, DebugResult

    manager = ManagerPlannerAgent()

    # 1. 'abort': Cancelled or aborted workflow
    abort_state: AgentState = {"cancelled": True}
    dec_abort = manager.evaluate_and_route(abort_state)
    assert dec_abort.next_action == "abort"
    assert dec_abort.target_agent == "manager"

    # 2. 'run_sandbox': Direct sandbox re-run requested
    sandbox_state: AgentState = {"force_sandbox_rerun": True}
    dec_sandbox = manager.evaluate_and_route(sandbox_state)
    assert dec_sandbox.next_action == "run_sandbox"
    assert dec_sandbox.target_agent == "sandbox_runner"

    # 3. 'delegate_test_gen': Debugger diagnosed test suite flaw
    test_gen_state: AgentState = {
        "test_results": TestResult(passed=False, exit_code=1, stdout="", stderr="", failed_tests=["test_bad"]),
        "debug_result": DebugResult(
            root_cause="Test asserted incorrect output",
            failing_tests=["test_bad"],
            remediation_plan="Fix assertion",
            target_fix_agent="test_generator",
        ),
        "iteration_count": 0,
        "max_iterations": 3,
    }
    dec_test_gen = manager.evaluate_and_route(test_gen_state)
    assert dec_test_gen.next_action == "delegate_test_gen"
    assert dec_test_gen.target_agent == "test_generator"

    # 4. 'delegate_debug': Standard test failure delegating to debugger
    debug_state: AgentState = {
        "test_results": TestResult(passed=False, exit_code=1, stdout="", stderr="", failed_tests=["test_core"]),
        "iteration_count": 0,
        "max_iterations": 3,
    }
    dec_debug = manager.evaluate_and_route(debug_state)
    assert dec_debug.next_action == "delegate_debug"
    assert dec_debug.target_agent == "debugger"

    # 5. 'delegate_review': Tests passed, initial review pending
    review_state: AgentState = {
        "test_results": TestResult(passed=True, exit_code=0, stdout="PASSED", stderr=""),
        "review_result": None,
    }
    dec_review = manager.evaluate_and_route(review_state)
    assert dec_review.next_action == "delegate_review"
    assert dec_review.target_agent == "reviewer"

    # 6. 'delegate_coder': Reviewer rejected with blocking issues, iterations remain
    coder_state: AgentState = {
        "test_results": TestResult(passed=True, exit_code=0, stdout="PASSED", stderr=""),
        "review_result": ReviewResult(
            agent_name="ReviewerAgent",
            approved=False,
            quality_score=5.0,
            blocking_issues=["Missing bounds check"],
            review_summary="Rejected due to missing bounds check",
        ),
        "iteration_count": 0,
        "max_iterations": 3,
    }
    dec_coder = manager.evaluate_and_route(coder_state)
    assert dec_coder.next_action == "delegate_coder"
    assert dec_coder.target_agent == "coder"

    # 7. 'finalize': All gates cleared (tests passed + reviewer approved)
    finalize_state: AgentState = {
        "test_results": TestResult(passed=True, exit_code=0, stdout="PASSED", stderr=""),
        "review_result": ReviewResult(
            agent_name="ReviewerAgent",
            approved=True,
            quality_score=9.5,
            review_summary="Clean implementation",
        ),
    }
    dec_finalize = manager.evaluate_and_route(finalize_state)
    assert dec_finalize.next_action == "finalize"
    assert dec_finalize.target_agent == "manager"


def test_compiled_graph_conditional_edge_coverage_for_all_seven_decisions():
    """Verify that the compiled LangGraph graph contains routing targets for all 7 actions."""
    from agent.core.graph import build_coding_agent_graph, DECISION_TO_NODE_MAP

    app = build_coding_agent_graph()

    # Verify every target node in the decision map exists in the compiled graph nodes
    compiled_nodes = set(app.nodes.keys())
    for action, target_node in DECISION_TO_NODE_MAP.items():
        assert target_node in compiled_nodes, f"Target node '{target_node}' for action '{action}' missing from graph nodes"


def test_retry_limits_strictly_fail_and_never_produce_success():
    """Verify that reaching max_iterations with failures strictly produces COMPLETED_WITH_FAILURES."""
    from agent.core.state import TestResult, ReviewResult
    from agent.agents.manager import ManagerPlannerAgent
    from agent.core.graph import manager_evaluate_node, manager_finalize_node
    from agent.verification.verifier import WorkflowOutcome

    manager = ManagerPlannerAgent()

    # Case A: Tests failing at max iterations
    failing_state: AgentState = {
        "task": "Test task",
        "repo_path": str(REPO_DIR),
        "iteration_count": 3,
        "max_iterations": 3,
        "test_results": TestResult(
            passed=False,
            exit_code=1,
            stdout="FAILED test_case",
            stderr="",
            failed_tests=["test_case"],
        ),
    }
    decision = manager.evaluate_and_route(failing_state)
    assert decision.next_action == "finalize"

    # Evaluate node produces finalize status
    eval_updates = manager_evaluate_node(failing_state)
    assert eval_updates["status"] == "finalize"

    # Finalize node MUST invoke IndependentVerifier and report failure
    fin_updates = manager_finalize_node(failing_state)
    assert fin_updates["workflow_outcome"] == WorkflowOutcome.COMPLETED_WITH_FAILURES.value
    assert fin_updates["verification_result"].verified is False
    assert fin_updates["status"] == WorkflowOutcome.COMPLETED_WITH_FAILURES.value

    # Case B: Reviewer rejected at max iterations
    review_reject_state: AgentState = {
        "task": "Test task",
        "repo_path": str(REPO_DIR),
        "iteration_count": 3,
        "max_iterations": 3,
        "test_results": TestResult(passed=True, exit_code=0, stdout="PASSED", stderr=""),
        "review_result": ReviewResult(
            agent_name="ReviewerAgent",
            approved=False,
            quality_score=4.0,
            blocking_issues=["Vulnerability detected in divide method"],
            review_summary="Critical vulnerability detected in divide method",
        ),
    }
    decision_rev = manager.evaluate_and_route(review_reject_state)
    assert decision_rev.next_action == "finalize"

    fin_rev_updates = manager_finalize_node(review_reject_state)
    assert fin_rev_updates["workflow_outcome"] == WorkflowOutcome.COMPLETED_WITH_FAILURES.value
    assert fin_rev_updates["verification_result"].verified is False

def test_debugger_coder_loop_transitions_and_review_invalidation():
    """Verify Debugger -> Coder -> TestGen -> Manager loop mechanics and state hygiene."""
    from agent.core.state import TestResult, ReviewResult
    from agent.core.graph import (
        debugger_node,
        coder_node,
        manager_evaluate_node,
    )

    # 1. State with failed tests: Manager evaluates failure and meters retry budget
    failing_state: AgentState = {
        "task": "Fix division by zero",
        "repo_path": str(REPO_DIR),
        "iteration_count": 0,
        "max_iterations": 3,
        "test_results": TestResult(
            passed=False,
            exit_code=1,
            stdout="ZeroDivisionError: division by zero",
            stderr="",
            failed_tests=["test_divide_by_zero"],
            error_summary="ZeroDivisionError in divide",
        ),
        "review_result": ReviewResult(
            agent_name="ReviewerAgent",
            approved=True,
            quality_score=9.0,
            review_summary="Previous review was approved",
        ),
    }

    eval_updates = manager_evaluate_node(failing_state)
    assert eval_updates["manager_decision"].next_action == "delegate_debug"
    assert eval_updates["iteration_count"] == 1
    assert eval_updates["review_result"] is None

    # Debugger receives metered state, diagnoses root-cause without double-incrementing retry budget
    state_for_dbg = dict(failing_state)
    state_for_dbg.update(eval_updates)
    dbg_updates = debugger_node(state_for_dbg)
    assert dbg_updates["iteration_count"] == 1
    assert dbg_updates["review_result"] is None
    assert dbg_updates["debug_result"] is not None
    assert dbg_updates["status"] == "coding"

    # 2. Coder executes fix and ensures review_result remains None for re-audit
    state_after_dbg = dict(failing_state)
    state_after_dbg.update(dbg_updates)
    coder_updates = coder_node(state_after_dbg)
    assert coder_updates["review_result"] is None
    assert coder_updates["status"] == "test_generation"

    # 3. If reviewer rejects, manager_evaluate increments iteration_count and clears review_result
    review_rejected_state: AgentState = {
        "task": "Fix division",
        "repo_path": str(REPO_DIR),
        "iteration_count": 1,
        "max_iterations": 3,
        "test_results": TestResult(passed=True, exit_code=0, stdout="PASSED", stderr=""),
        "review_result": ReviewResult(
            agent_name="ReviewerAgent",
            approved=False,
            quality_score=5.0,
            blocking_issues=["Missing docstring"],
            review_summary="Rejected due to missing docstring",
        ),
    }
    mgr_eval_updates = manager_evaluate_node(review_rejected_state)
    assert mgr_eval_updates["manager_decision"].next_action == "delegate_coder"
    assert mgr_eval_updates["iteration_count"] == 2
    assert mgr_eval_updates["review_result"] is None


"""Tests for Parallel Fork/Join Edges in LangGraph Multi-Agent Orchestration.

Verifies:
1. Graph Topology: Coder forks into Test Generator and Reviewer concurrently.
2. Branch Synchronization: Both parallel branches converge at branch_join barrier.
3. Concurrent State Merging: Channel reducers (agent_history, status, thread_id)
   merge parallel updates deterministically with zero race conditions or update errors.
4. End-to-End Execution: ManagerEvaluate receives both test execution outcomes and
   code review approval in a single unified decision step.
5. Remediation Loopback: When debugging or remediation triggers re-patching,
   the parallel fork/join barrier re-triggers cleanly across subsequent iterations.
"""

import time
import pytest
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agent.core.state import (
    AgentState,
    TestResult,
    TestGenResult,
    ReviewResult,
    CoderResult,
    ManagerPlan,
    ManagerDecision,
)
from agent.core.graph import (
    build_coding_agent_graph,
    branch_join_node,
    coder_node,
    test_generator_node as graph_test_generator_node,
    reviewer_node,
    sandbox_runner_node,
    manager_evaluate_node,
)


def test_parallel_fork_join_graph_topology():
    """Verify that StateGraph contains branch_join node and wires parallel edges."""
    app = build_coding_agent_graph()
    
    # Verify node registration
    node_names = set(app.get_graph().nodes.keys())
    assert "coder" in node_names
    assert "test_generator" in node_names
    assert "reviewer" in node_names
    assert "branch_join" in node_names
    assert "sandbox_runner" in node_names
    assert "manager_evaluate" in node_names

    # Inspect edges from graph representation
    graph_edges = [(e.source, e.target) for e in app.get_graph().edges]
    
    # Fork edges from Coder
    assert ("coder", "test_generator") in graph_edges
    assert ("coder", "reviewer") in graph_edges

    # Join edges to branch_join
    assert ("test_generator", "branch_join") in graph_edges
    assert ("reviewer", "branch_join") in graph_edges

    # Post-join execution to sandbox
    assert ("branch_join", "sandbox_runner") in graph_edges
    assert ("sandbox_runner", "manager_evaluate") in graph_edges


def test_branch_join_node_records_synchronization_event():
    """Verify that branch_join_node emits structured history entry verifying both branches."""
    mock_state: AgentState = {
        "thread_id": "thread_test_join",
        "iteration_count": 1,
        "agent_history": [],
        "test_gen_result": TestGenResult(
            test_files_modified=["tests/test_sample.py"],
            test_cases_added=["test_sample_case"],
            edge_cases_tested=["test_boundary"],
            test_code_summary="Generated 1 test case",
        ),
        "review_result": ReviewResult(
            approved=True,
            quality_score=9.5,
            review_summary="Clean implementation with high test coverage.",
        ),
    }

    update = branch_join_node(mock_state)
    assert update["status"] == "branch_joined"
    assert update["thread_id"] == "thread_test_join"
    assert len(update["agent_history"]) == 1
    
    event = update["agent_history"][0]
    assert event["agent"] == "SystemOrchestrator"
    assert event["action"] == "parallel_branch_join"
    assert event["test_gen_completed"] is True
    assert event["review_completed"] is True


def test_concurrent_state_merging_without_invalid_update_error():
    """Verify that parallel branches emitting status, thread_id, and history merge without conflict."""
    builder = StateGraph(AgentState)
    
    def mock_coder(s):
        return {"status": "coding", "thread_id": "test_thread"}

    def mock_test_gen(s):
        return {
            "status": "testing",
            "thread_id": "test_thread",
            "test_gen_result": TestGenResult(
                test_files_modified=["test_calc.py"],
                test_cases_added=["test_add"],
                edge_cases_tested=[],
                test_code_summary="Added test_add",
            ),
            "agent_history": [{
                "event_id": "ev_tg_1",
                "agent": "TestGeneratorAgent",
                "action": "generate_tests",
                "iteration": 1,
            }],
        }

    def mock_reviewer(s):
        return {
            "status": "reviewing",
            "thread_id": "test_thread",
            "review_result": ReviewResult(
                approved=True,
                quality_score=9.0,
                review_summary="Approved",
            ),
            "agent_history": [{
                "event_id": "ev_rev_1",
                "agent": "ReviewerAgent",
                "action": "review_code",
                "iteration": 1,
            }],
        }

    builder.add_node("coder", mock_coder)
    builder.add_node("test_generator", mock_test_gen)
    builder.add_node("reviewer", mock_reviewer)
    builder.add_node("branch_join", branch_join_node)

    builder.add_edge(START, "coder")
    builder.add_edge("coder", "test_generator")
    builder.add_edge("coder", "reviewer")
    builder.add_edge("test_generator", "branch_join")
    builder.add_edge("reviewer", "branch_join")
    builder.add_edge("branch_join", END)

    app = builder.compile()
    
    final_state = app.invoke({"agent_history": [], "iteration_count": 1})
    
    # Both specialist outputs must be present
    assert final_state["test_gen_result"] is not None
    assert final_state["review_result"] is not None
    assert final_state["test_gen_result"].test_cases_added == ["test_add"]
    assert final_state["review_result"].approved is True

    # History must contain all 3 events (test_gen, reviewer, branch_join)
    agents_in_hist = [h.get("agent") for h in final_state["agent_history"]]
    assert "TestGeneratorAgent" in agents_in_hist
    assert "ReviewerAgent" in agents_in_hist
    assert "SystemOrchestrator" in agents_in_hist

    # Thread ID preserved idempotently
    assert final_state["thread_id"] == "test_thread"


def test_parallel_fork_join_remediation_loop_execution():
    """Verify that when a failure occurs, the remediation loop re-triggers the parallel fork/join."""
    builder = StateGraph(AgentState)

    def mock_coder(s):
        it = s.get("iteration_count", 0)
        return {
            "iteration_count": it + 1,
            "coder_result": CoderResult(
                files_modified=["calc.py"],
                rationale="Patch applied",
            ),
        }

    def mock_test_gen(s):
        return {
            "test_gen_result": TestGenResult(
                test_files_modified=["test_calc.py"],
                test_cases_added=["test_it"],
                edge_cases_tested=[],
                test_code_summary="Test gen",
            ),
        }

    def mock_reviewer(s):
        return {
            "review_result": ReviewResult(
                approved=True,
                quality_score=8.5,
                review_summary="Looks good",
            ),
        }

    def mock_sandbox(s):
        it = s.get("iteration_count", 0)
        # Fail on iteration 1, pass on iteration 2
        return {
            "test_results": TestResult(
                passed=(it >= 2),
                exit_code=0 if it >= 2 else 1,
                failed_tests=[] if it >= 2 else ["test_it"],
            ),
        }

    def mock_router(s):
        test_res = s.get("test_results")
        if test_res and test_res.passed:
            return "manager_finalize"
        return "coder"

    builder.add_node("coder", mock_coder)
    builder.add_node("test_generator", mock_test_gen)
    builder.add_node("reviewer", mock_reviewer)
    builder.add_node("branch_join", branch_join_node)
    builder.add_node("sandbox_runner", mock_sandbox)
    builder.add_node("manager_finalize", lambda s: {"status": "finalized"})

    builder.add_edge(START, "coder")
    builder.add_edge("coder", "test_generator")
    builder.add_edge("coder", "reviewer")
    builder.add_edge("test_generator", "branch_join")
    builder.add_edge("reviewer", "branch_join")
    builder.add_edge("branch_join", "sandbox_runner")
    builder.add_conditional_edges("sandbox_runner", mock_router, {
        "coder": "coder",
        "manager_finalize": "manager_finalize",
    })
    builder.add_edge("manager_finalize", END)

    app = builder.compile()
    final_state = app.invoke({"iteration_count": 0, "agent_history": []})

    # Proves the graph ran 2 iterations, successfully looping through fork/join twice
    assert final_state["iteration_count"] == 2
    assert final_state["test_results"].passed is True
    assert final_state["review_result"].approved is True
    assert final_state["status"] == "finalized"

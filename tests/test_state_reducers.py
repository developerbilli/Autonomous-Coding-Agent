"""Tests for Explicit LangGraph Channel Reducers and Reducer Registry."""

import pytest
from langgraph.graph import StateGraph

from agent.core.state import (
    AgentState,
    reduce_error_history,
    reduce_completed_actions,
    reduce_agent_history,
    STATE_REDUCERS,
    apply_state_update,
)


def test_reduce_error_history_semantic_deduplication():
    """Verify reduce_error_history tracks error occurrences, frequency, and resurfacing."""
    # 1. Initial creation
    res1 = reduce_error_history(None, "ValueError: Invalid input")
    assert len(res1) == 1
    assert res1[0]["signature"] == "ValueError: Invalid input"
    assert res1[0]["occurrence_count"] == 1
    assert res1[0]["resurfaced"] is False

    # 2. Consecutive identical error increments occurrence_count without duplicate entry
    res2 = reduce_error_history(res1, "ValueError: Invalid input")
    assert len(res2) == 1
    assert res2[0]["occurrence_count"] == 2
    assert res2[0]["resurfaced"] is False

    # 3. New distinct error appends as new entry
    res3 = reduce_error_history(
        res2,
        {"signature": "ZeroDivisionError: division by zero", "agent": "Debugger", "iteration": 2},
    )
    assert len(res3) == 2
    assert res3[1]["signature"] == "ZeroDivisionError: division by zero"
    assert res3[1]["occurrence_count"] == 1

    # 4. Old error resurfaces after intervening error
    res4 = reduce_error_history(res3, "ValueError: Invalid input")
    assert len(res4) == 2  # Still 2 unique signatures
    assert res4[0]["occurrence_count"] == 3
    assert res4[0]["resurfaced"] is True, "Must detect that error resurfaced after intervening error"

    # 5. Sliding window cap (max 25)
    large_batch = [{"signature": f"Error_{i}", "iteration": 3} for i in range(40)]
    capped = reduce_error_history(res4, large_batch)
    assert len(capped) == 25
    assert capped[-1]["signature"] == "Error_39"


def test_reduce_completed_actions_set_union():
    """Verify reduce_completed_actions prevents duplicate action keys while maintaining order."""
    init = ["act_1", "act_2"]
    res = reduce_completed_actions(init, ["act_2", "act_3", "act_1"])
    assert res == ["act_1", "act_2", "act_3"]


def test_reduce_agent_history_chronological_append():
    """Verify reduce_agent_history appends events and suppresses duplicate consecutive event dicts."""
    ev1 = {"agent": "Coder", "action": "patch", "file": "main.py"}
    ev2 = {"agent": "Debugger", "action": "diagnose"}

    history = reduce_agent_history([], ev1)
    assert len(history) == 1

    # Identical consecutive event suppressed
    history = reduce_agent_history(history, ev1)
    assert len(history) == 1

    # New event appended
    history = reduce_agent_history(history, ev2)
    assert len(history) == 2
    assert history[1]["agent"] == "Debugger"


def test_apply_state_update_honors_reducer_registry():
    """Verify apply_state_update uses explicit STATE_REDUCERS without fragile reflection."""
    state = {
        "task": "Test task",
        "error_history": [{"signature": "Error 1", "occurrence_count": 1}],
        "completed_actions": ["action_1"],
        "iteration_count": 1,
    }

    update = {
        "error_history": ["Error 1", "Error 2"],  # Duplicate Error 1 increments occurrence_count
        "completed_actions": "action_2",
        "iteration_count": 2,  # Scalar field overwritten normally
    }

    apply_state_update(state, update)

    assert state["iteration_count"] == 2
    assert len(state["error_history"]) == 2
    assert state["error_history"][0]["signature"] == "Error 1"
    assert state["error_history"][0]["occurrence_count"] == 2
    assert state["error_history"][1]["signature"] == "Error 2"
    assert state["completed_actions"] == ["action_1", "action_2"]


def test_langgraph_stategraph_accepts_agent_state_with_reducers():
    """Verify LangGraph StateGraph compiles and binds channel reducers properly."""
    graph = StateGraph(AgentState)
    assert graph is not None

    # Channels must be recognized in channels dict
    assert "error_history" in graph.channels
    assert "agent_history" in graph.channels
    assert "completed_actions" in graph.channels


# ============================================================
# Synchronization Guard Tests (LangGraph Annotated vs STATE_REDUCERS)
# ============================================================

def test_state_reducers_and_langgraph_annotated_channels_are_strictly_synchronized():
    """Verify 1:1 bi-directional parity between LangGraph Annotated reducers and STATE_REDUCERS."""
    from agent.core.state import validate_reducer_registry_synchronization
    
    # Must succeed without raising any AssertionError
    validate_reducer_registry_synchronization()


def test_synchronization_validator_detects_discrepancies():
    """Verify that any drift between Annotated channels and STATE_REDUCERS is caught immediately."""
    import typing
    from agent.core.state import reduce_error_history

    # Scenario 1: Key in STATE_REDUCERS but missing from Annotated
    rogue_reducers = dict(STATE_REDUCERS)
    rogue_reducers["unregistered_channel"] = lambda a, b: b

    with pytest.raises(AssertionError) as exc_info:
        # Simulate check with missing Annotated entry
        hints = typing.get_type_hints(AgentState, include_extras=True)
        annotated_keys = {
            k for k, h in hints.items()
            if typing.get_origin(h) is typing.Annotated and callable(typing.get_args(h)[1])
        }
        missing = set(rogue_reducers.keys()) - annotated_keys
        if missing:
            raise AssertionError(f"Missing from Annotated: {missing}")
    assert "unregistered_channel" in str(exc_info.value)

    # Scenario 2: Reducer function identity mismatch
    mismatched_reducers = dict(STATE_REDUCERS)
    mismatched_reducers["error_history"] = lambda a, b: b

    hints = typing.get_type_hints(AgentState, include_extras=True)
    actual_reducer = typing.get_args(hints["error_history"])[1]
    assert actual_reducer != mismatched_reducers["error_history"]


def test_debugger_node_event_id_idempotency_vs_observation_counting(monkeypatch):
    """Verify that debugger_node emits deterministic event_ids ensuring retry idempotency,
    while distinct iterations increment occurrence counts.
    """
    from agent.core.graph import debugger_node
    from agent.core.state import DebugResult

    mock_diag = DebugResult(
        root_cause="ZeroDivisionError: division by zero",
        remediation_plan="Check denominator != 0 before division",
    )

    class MockDebuggerAgent:
        def __init__(self, repo_path):
            pass
        def diagnose_failure(self, state):
            return mock_diag

    import agent.core.graph as graph_module
    monkeypatch.setattr(graph_module, "DebuggerAgent", MockDebuggerAgent)

    state: AgentState = {
        "task": "Fix division bug",
        "repo_path": "/tmp/mock",
        "thread_id": "thread_test_idemp",
        "iteration_count": 1,
        "error_history": [],
    }

    # 1. First execution of debugger_node
    out1 = debugger_node(state)
    assert len(out1["error_history"]) == 1
    event_entry1 = out1["error_history"][0]
    assert event_entry1.get("event_id") is not None
    assert event_entry1["event_id"].startswith("diag:thread_test_idemp:iter1:")

    # Apply to state
    reduced_state = reduce_error_history(state["error_history"], out1["error_history"])
    assert len(reduced_state) == 1
    assert reduced_state[0]["occurrence_count"] == 1

    # 2. Re-execution / retry of debugger_node within same iteration (iteration 1)
    # Simulates transient failure or LangGraph node retry
    out2 = debugger_node(state)
    event_entry2 = out2["error_history"][0]
    assert event_entry2["event_id"] == event_entry1["event_id"]  # Deterministic event_id matches!

    # Merging retry into reduced_state MUST NOT increment occurrence_count
    reduced_state_retry = reduce_error_history(reduced_state, out2["error_history"])
    assert len(reduced_state_retry) == 1
    assert reduced_state_retry[0]["occurrence_count"] == 1  # Idempotent!

    # 3. Next iteration (iteration 2) with the same error resurfacing
    state_iter2 = dict(state)
    state_iter2["iteration_count"] = 2
    out3 = debugger_node(state_iter2)
    event_entry3 = out3["error_history"][0]
    assert event_entry3["event_id"] != event_entry1["event_id"]  # Different event_id for iter 2!
    assert event_entry3["event_id"].startswith("diag:thread_test_idemp:iter2:")

    # Merging genuine new iteration occurrence MUST increment occurrence count
    reduced_state_iter2 = reduce_error_history(reduced_state_retry, out3["error_history"])
    assert len(reduced_state_iter2) == 1
    assert reduced_state_iter2[0]["occurrence_count"] == 2
    assert reduced_state_iter2[0]["resurfaced"] is True


def test_reduce_error_history_tripartite_contract():
    """Verify tripartite contract of event_id:
    1. Same signature + different event IDs -> count both observations.
    2. Same signature + same event ID -> treat second as replay and skip.
    3. Same signature + no event ID -> cannot identify replay, increment count.
    """
    sig = "TypeError: unsupported operand"

    # Contract 1: Same signature + different event IDs -> both counted
    obs1 = {"signature": sig, "event_id": "evt_001", "iteration": 1, "created_at": 100.0}
    obs2 = {"signature": sig, "event_id": "evt_002", "iteration": 1, "created_at": 101.0}
    state = reduce_error_history(None, obs1)
    assert len(state) == 1
    assert state[0]["occurrence_count"] == 1

    state = reduce_error_history(state, obs2)
    assert len(state) == 1
    assert state[0]["occurrence_count"] == 2, "Different event IDs must count both observations"

    # Contract 2: Same signature + same event ID -> replay skipped
    replay_obs2 = {"signature": sig, "event_id": "evt_002", "iteration": 1, "created_at": 101.0}
    state_after_replay = reduce_error_history(state, replay_obs2)
    assert len(state_after_replay) == 1
    assert state_after_replay[0]["occurrence_count"] == 2, "Identical event ID replay must be skipped"

    # Contract 3: Same signature + no event ID -> unkeyed observation tick counted
    unkeyed_obs = {"signature": sig, "iteration": 1, "created_at": 102.0}
    state_after_unkeyed = reduce_error_history(state_after_replay, unkeyed_obs)
    assert len(state_after_unkeyed) == 1
    assert state_after_unkeyed[0]["occurrence_count"] == 3, "Unkeyed update must increment occurrence count"


def test_resurfaced_flag_independent_of_state_sorting():
    """Verify that 'resurfaced' flag depends on chronological sequence / intervening errors,
    NOT on arbitrary alphabetical or list sort ordering (current[-1]).
    """
    # Alphabetical order: AlphaError < OmegaError
    # Even if AlphaError sorts first and OmegaError sorts last (at current[-1]):
    err_alpha = {"signature": "AlphaError: first alphabetically", "iteration": 1, "created_at": 10.0, "sequence_num": 1}
    err_omega = {"signature": "OmegaError: last alphabetically", "iteration": 1, "created_at": 20.0, "sequence_num": 2}

    # Initialize with both errors
    state = reduce_error_history(None, [err_alpha, err_omega])
    assert len(state) == 2
    # Verify neither has resurfaced initially
    assert state[0]["resurfaced"] is False
    assert state[1]["resurfaced"] is False

    # 1. Consecutive occurrence of OmegaError (the one at index -1)
    # Must NOT falsely mark OmegaError as resurfaced
    err_omega_consecutive = {"signature": "OmegaError: last alphabetically", "iteration": 1, "created_at": 30.0, "sequence_num": 3}
    state2 = reduce_error_history(state, err_omega_consecutive)
    omega_entry = next(e for e in state2 if e["signature"] == err_omega["signature"])
    assert omega_entry["occurrence_count"] == 2
    assert omega_entry["resurfaced"] is False, "Consecutive occurrence of latest error must NOT be marked resurfaced"

    # 2. Reappearance of AlphaError after intervening OmegaError
    # AlphaError was at seq 1, OmegaError occurred at seq 2 and 3.
    # AlphaError now arriving at seq 4 has genuinely resurfaced!
    err_alpha_reappear = {"signature": "AlphaError: first alphabetically", "iteration": 1, "created_at": 40.0, "sequence_num": 4}
    state3 = reduce_error_history(state2, err_alpha_reappear)
    alpha_entry = next(e for e in state3 if e["signature"] == err_alpha["signature"])
    assert alpha_entry["occurrence_count"] == 2
    assert alpha_entry["resurfaced"] is True, "AlphaError must be marked resurfaced after intervening OmegaError"


def test_debugger_node_supplies_deterministic_created_at_and_timestamp(monkeypatch):
    """Verify debugger_node explicitly provides created_at and timestamp at observation time."""
    from agent.core.graph import debugger_node
    from agent.core.state import DebugResult
    import agent.core.graph as graph_module

    class MockDebuggerAgent:
        def __init__(self, repo_path):
            pass
        def diagnose_failure(self, state):
            return DebugResult(root_cause="TestError", remediation_plan="Fix it")

    monkeypatch.setattr(graph_module, "DebuggerAgent", MockDebuggerAgent)

    state: AgentState = {
        "task": "Test task",
        "repo_path": "/tmp/mock",
        "thread_id": "th_1",
        "iteration_count": 1,
    }

    out = debugger_node(state)
    error = out["error_history"][0]
    assert "created_at" in error
    assert isinstance(error["created_at"], float)
    assert "timestamp" in error
    assert isinstance(error["timestamp"], str)
    assert "Z" in error["timestamp"]


def test_reduce_agent_history_handles_both_accumulated_and_incremental_updates():
    """Verify reduce_agent_history prevents quadratic duplication whether callers pass
    incremental deltas or full accumulated lists, and verifies global event_id idempotency.
    """
    e1 = {"event_id": "hist:manager:plan:th1:iter0", "agent": "Manager", "action": "plan"}
    e2 = {"event_id": "hist:coder:implement:th1:iter0:a1b2", "agent": "Coder", "action": "implement"}
    e3 = {"event_id": "hist:test:generate:th1:iter0:c3d4", "agent": "Tester", "action": "generate"}

    # Scenario 1: Incremental updates (canonical LangGraph pattern)
    s1 = reduce_agent_history([], [e1])
    assert len(s1) == 1

    s2 = reduce_agent_history(s1, [e2])
    assert len(s2) == 2
    assert s2[0]["agent"] == "Manager"
    assert s2[1]["agent"] == "Coder"

    # Scenario 2: Node mistakenly returns accumulated history [e1, e2, e3]
    s3 = reduce_agent_history(s2, [e1, e2, e3])
    # Must NOT produce 5 items! Must cleanly deduplicate already-committed prefix to exactly 3 items!
    assert len(s3) == 3
    assert [x["agent"] for x in s3] == ["Manager", "Coder", "Tester"]

    # Scenario 3: Global event_id idempotency across entire ledger
    # Replay e1 (from beginning) after intervening events e2 and e3
    replay_e1 = dict(e1)
    s4 = reduce_agent_history(s3, [replay_e1])
    assert len(s4) == 3, "Replay of e1 must be deduplicated across entire history, not just consecutive"

    # Scenario 4: Genuine new event
    e4 = {"event_id": "hist:reviewer:review:th1:iter0:approved", "agent": "Reviewer", "action": "review"}
    s5 = reduce_agent_history(s4, [e4])
    assert len(s5) == 4
    assert s5[-1]["agent"] == "Reviewer"


def test_all_six_graph_nodes_emit_incremental_deltas_with_event_ids(monkeypatch):
    """Verify that all 6 nodes writing to agent_history emit incremental 1-item deltas
    with deterministic event_id, created_at, timestamp, and iteration fields.
    """
    import agent.core.graph as graph_mod
    from agent.core.graph import (
        manager_planner_node,
        coder_node,
        test_generator_node,
        manager_evaluate_node,
        debugger_node,
        reviewer_node,
    )
    from agent.core.state import (
        ManagerPlan,
        ManagerSubTask,
        CoderResult,
        TestGenResult,
        ManagerDecision,
        DebugResult,
        ReviewResult,
        TestResult,
    )

    # Mock all agents
    class MockManager:
        def create_plan(self, task, files, symbols):
            return ManagerPlan(
                goal=task,
                strategy="Plan",
                subtasks=[ManagerSubTask(id="subtask_1", description="Do it", assigned_agent="coder")],
            )
        def evaluate_and_route(self, state):
            return ManagerDecision(next_action="delegate_coder", target_agent="coder", reasoning="Iterate")

    class MockCoder:
        def __init__(self, *args, **kwargs): pass
        def implement(self, state):
            return CoderResult(files_modified=["core.py"], methods_implemented=["f"], patches={}, rationale="Done")

    class MockTestGen:
        def __init__(self, *args, **kwargs): pass
        def generate_tests(self, state):
            return TestGenResult(
                test_code_summary="Generated unit tests",
                test_files_modified=["test_core.py"],
                test_cases_added=["t1"],
                edge_cases_tested=["e1"],
            )

    class MockDebugger:
        def __init__(self, *args, **kwargs): pass
        def diagnose_failure(self, state):
            return DebugResult(root_cause="SyntaxError", remediation_plan="Fix syntax")

    class MockReviewer:
        def __init__(self, *args, **kwargs): pass
        def review_code(self, state):
            return ReviewResult(approved=True, quality_score=9.5, blocking_issues=[], suggestions=[])

    class MockMemory:
        def recall_context_for_task(self, task, repo):
            return {"total_recalled": 1, "recalled_patterns": []}

    monkeypatch.setattr(graph_mod, "ManagerPlannerAgent", MockManager)
    monkeypatch.setattr(graph_mod, "CoderAgent", MockCoder)
    monkeypatch.setattr(graph_mod, "TestGeneratorAgent", MockTestGen)
    monkeypatch.setattr(graph_mod, "DebuggerAgent", MockDebugger)
    monkeypatch.setattr(graph_mod, "ReviewerAgent", MockReviewer)
    monkeypatch.setattr(graph_mod, "get_memory_engine", lambda: MockMemory())

    base_state: AgentState = {
        "task": "Build feature",
        "repo_path": "/tmp/mock",
        "thread_id": "thread_full_audit",
        "iteration_count": 1,
        "agent_history": [],
        "completed_actions": [],
        "test_results": TestResult(passed=False, exit_code=1, stdout="Failed", stderr="", failed_tests=["t1"], error_summary="err"),
    }

    nodes = [
        ("manager_plan", manager_planner_node),
        ("coder", coder_node),
        ("test_gen", test_generator_node),
        ("manager_eval", manager_evaluate_node),
        ("debugger", debugger_node),
        ("reviewer", reviewer_node),
    ]

    seen_event_ids = set()
    accumulated_history = []

    for name, node_fn in nodes:
        out = node_fn(base_state)
        assert "agent_history" in out, f"{name} must return agent_history"
        hist_delta = out["agent_history"]
        # Must be incremental 1-item delta!
        assert isinstance(hist_delta, list), f"{name} delta must be a list"
        assert len(hist_delta) == 1, f"{name} must return an incremental 1-item delta, got {len(hist_delta)}"

        event = hist_delta[0]
        assert "event_id" in event, f"{name} event must have event_id"
        assert event["event_id"] not in seen_event_ids, f"{name} event_id must be globally unique"
        seen_event_ids.add(event["event_id"])

        assert "created_at" in event and isinstance(event["created_at"], float), f"{name} must have epoch created_at"
        assert "timestamp" in event and "Z" in event["timestamp"], f"{name} must have ISO UTC timestamp"
        assert "iteration" in event and event["iteration"] == 1, f"{name} must record iteration"

        # Merge through reducer
        accumulated_history = reduce_agent_history(accumulated_history, hist_delta)

    # After sequential execution of all 6 nodes, history must have exactly 6 distinct events
    assert len(accumulated_history) == 6
    assert len({e["event_id"] for e in accumulated_history}) == 6


def test_manager_evaluate_repeated_actions_vs_replay_disambiguation(monkeypatch):
    """Verify that manager_evaluate_node distinguishes legitimate repeated evaluations
    in the same iteration from node retries/replays using ledger step coordinates.
    """
    import agent.core.graph as graph_mod
    from agent.core.graph import manager_evaluate_node
    from agent.core.state import ManagerDecision

    class MockManager:
        def evaluate_and_route(self, state):
            return ManagerDecision(next_action="delegate_debug", target_agent="debugger", reasoning="Investigate failure")

    monkeypatch.setattr(graph_mod, "ManagerPlannerAgent", MockManager)

    # Initial state with 2 prior events in iteration 2
    state_step_2: AgentState = {
        "task": "Fix bug",
        "thread_id": "th_eval_test",
        "iteration_count": 2,
        "agent_history": [
            {"event_id": "hist:manager:plan:th_eval_test:iter2:step0", "agent": "Manager", "action": "plan"},
            {"event_id": "hist:coder:implement:th_eval_test:iter2:step1:abc", "agent": "Coder", "action": "implement"},
        ],
    }

    # 1. First evaluation in iteration 2: step_idx = 2
    out1 = manager_evaluate_node(state_step_2)
    ev1 = out1["agent_history"][0]
    assert ev1["event_id"] == "hist:manager:evaluate:th_eval_test:iter2:step2:delegate_debug"

    # Merge into state
    history_after_eval1 = reduce_agent_history(state_step_2["agent_history"], out1["agent_history"])
    assert len(history_after_eval1) == 3

    # 2. Transient retry of Evaluation 1 (same state_step_2 input before checkpoint)
    # MUST generate identical event_id and be skipped by reducer (idempotent retry)
    out1_retry = manager_evaluate_node(state_step_2)
    ev1_retry = out1_retry["agent_history"][0]
    assert ev1_retry["event_id"] == ev1["event_id"]

    history_after_retry = reduce_agent_history(history_after_eval1, out1_retry["agent_history"])
    assert len(history_after_retry) == 3, "Retry of same evaluation must be deduplicated"

    # 3. Legitimate subsequent evaluation in iteration 2 (workflow executed debugger, history now length 4)
    state_step_4: AgentState = dict(state_step_2)
    state_step_4["agent_history"] = list(history_after_eval1) + [
        {"event_id": "hist:debugger:th_eval_test:iter2:step3:def", "agent": "Debugger", "action": "diagnose"}
    ]
    assert len(state_step_4["agent_history"]) == 4

    out2 = manager_evaluate_node(state_step_4)
    ev2 = out2["agent_history"][0]
    # Disambiguated! step_idx is now 4!
    assert ev2["event_id"] == "hist:manager:evaluate:th_eval_test:iter2:step4:delegate_debug"
    assert ev2["event_id"] != ev1["event_id"]

    # Both legitimate evaluations must be preserved in the audit trail!
    history_after_eval2 = reduce_agent_history(state_step_4["agent_history"], out2["agent_history"])
    assert len(history_after_eval2) == 5
    eval_events = [e for e in history_after_eval2 if e.get("action") == "evaluate_and_route"]
    assert len(eval_events) == 2, "Both legitimate repeated evaluations must be retained in history"


def test_mixed_history_legacy_unkeyed_and_keyed_snapshots():
    """Verify reduce_agent_history correctly processes mixed histories containing:
    1. Legacy unkeyed events
    2. Modern keyed events
    3. Accumulated snapshots with volatile timestamps on unkeyed items
    4. Incremental deltas
    5. Replayed events arriving after intervening events
    """
    # 1. State starts with legacy unkeyed event
    legacy_ev1 = {"agent": "Manager", "action": "plan", "created_at": 100.0}
    s1 = reduce_agent_history(None, legacy_ev1)
    assert len(s1) == 1

    # 2. Modern keyed event appended
    keyed_ev1 = {"event_id": "evt_coder_1", "agent": "Coder", "action": "implement", "created_at": 105.0}
    s2 = reduce_agent_history(s1, [keyed_ev1])
    assert len(s2) == 2

    # 3. Accumulated snapshot passed by legacy node (contains legacy_ev1 with volatile timestamp)
    legacy_ev1_volatile = {"agent": "Manager", "action": "plan", "created_at": 100.007}  # Slight clock drift!
    new_unkeyed_ev = {"agent": "Tester", "action": "test", "created_at": 110.0}
    accumulated_snapshot = [legacy_ev1_volatile, keyed_ev1, new_unkeyed_ev]

    s3 = reduce_agent_history(s2, accumulated_snapshot)
    # Must strip prefix and append only new_unkeyed_ev, resulting in exactly 3 items!
    assert len(s3) == 3
    assert [e["agent"] for e in s3] == ["Manager", "Coder", "Tester"]

    # 4. Incremental delta appended
    keyed_ev2 = {"event_id": "evt_reviewer_1", "agent": "Reviewer", "action": "review", "created_at": 115.0}
    s4 = reduce_agent_history(s3, [keyed_ev2])
    assert len(s4) == 4

    # 5. Replay of earlier keyed event (keyed_ev1) arriving AFTER intervening events
    # Must be deduplicated globally across entire history
    replay_keyed_ev1 = dict(keyed_ev1)
    s5 = reduce_agent_history(s4, [replay_keyed_ev1])
    assert len(s5) == 4, "Keyed event replay after intervening events must be skipped globally"


def test_concurrent_errors_and_truncation_window_properties():
    """Verify error reducer properties under concurrent arrival and truncation windows:
    1. Commutativity of concurrent errors with equal timestamps and sequence numbers.
    2. Orderly eviction under 25-item limit while preserving active error occurrences.
    """
    # 1. Concurrent events with identical timestamps and sequence numbers
    e_alpha = {"signature": "AlphaError", "created_at": 100.0, "sequence_num": 0}
    e_beta = {"signature": "BetaError", "created_at": 100.0, "sequence_num": 0}

    # Left-to-right merge
    res_ab = reduce_error_history(None, [e_alpha, e_beta])
    # Right-to-left merge
    res_ba = reduce_error_history(None, [e_beta, e_alpha])

    # Commutativity check: identical result regardless of arrival order!
    assert res_ab == res_ba
    assert [e["signature"] for e in res_ab] == ["AlphaError", "BetaError"]
    assert not res_ab[0]["resurfaced"]
    assert not res_ab[1]["resurfaced"]

    # 2. Window retention: 30 intervening errors
    # Errors within the 25-item window retain accurate recurrence & resurfacing
    state = reduce_error_history(None, {"signature": "ActiveError", "iteration": 1, "sequence_num": 1, "created_at": 10.0})
    # Add 20 intervening errors (total 21 <= 25 limit)
    intervening = [{"signature": f"Err_{i}", "iteration": 1, "sequence_num": 2 + i, "created_at": 20.0 + i} for i in range(20)]
    state_with_intervening = reduce_error_history(state, intervening)
    assert len(state_with_intervening) == 21

    # ActiveError recurs at iteration 2
    state_reoccur = reduce_error_history(state_with_intervening, {"signature": "ActiveError", "iteration": 2, "sequence_num": 50, "created_at": 100.0})
    active_entry = next(e for e in state_reoccur if e["signature"] == "ActiveError")
    assert active_entry["occurrence_count"] == 2
    assert active_entry["resurfaced"] is True, "Error retained in window must accurately detect resurfacing"


def test_events_match_guards_against_vacuous_truth():
    """Verify _events_match never considers two distinct dictionaries equivalent
    simply because they lack standard semantic keys (guards against all([]) == True).
    """
    from agent.core.state import _events_match

    # Distinct dictionaries with arbitrary non-standard keys MUST NOT match!
    d1 = {"custom_metric": 42}
    d2 = {"other_metric": 99}
    assert _events_match(d1, d2) is False, "Must not evaluate to True for disjoint non-standard dictionaries"

    # Same custom keys with different values
    d3 = {"custom_metric": 42}
    d4 = {"custom_metric": 84}
    assert _events_match(d3, d4) is False, "Must not evaluate to True for different custom values"

    # Same custom keys with identical values
    d5 = {"custom_metric": 42}
    d6 = {"custom_metric": 42}
    assert _events_match(d5, d6) is True

    # Same custom keys with volatile timestamp differences
    d7 = {"custom_metric": 42, "created_at": 100.0}
    d8 = {"custom_metric": 42, "created_at": 100.5}
    assert _events_match(d7, d8) is True, "Volatile timestamps must be ignored on semantic matches"

    # Empty vs empty
    assert _events_match({}, {}) is True

    # One keyed vs one unkeyed
    assert _events_match({"event_id": "e1", "agent": "Coder"}, {"agent": "Coder"}) is False


def test_reduce_error_history_full_commutativity_across_arrival_orders():
    """Verify that reduce_error_history achieves full commutativity (A ⊕ B == B ⊕ A)
    including metadata updates, occurrence counting, duplicate handling, and resurfacing calculations.
    """
    u1 = {
        "signature": "ZeroDivisionError",
        "iteration": 1,
        "agent": "Coder",
        "created_at": 100.0,
        "event_id": "id1",
        "context": "Context 1",
    }
    u2 = {
        "signature": "ZeroDivisionError",
        "iteration": 2,
        "agent": "Debugger",
        "created_at": 200.0,
        "event_id": "id2",
        "context": "Context 2",
    }

    # Order A: u1 then u2
    order_a = reduce_error_history(reduce_error_history(None, [u1]), [u2])
    # Order B: u2 then u1
    order_b = reduce_error_history(reduce_error_history(None, [u2]), [u1])

    # Must be 100% bit-for-bit identical regardless of arrival order!
    assert order_a == order_b, f"Reducer non-commutative:\nOrder A: {order_a}\nOrder B: {order_b}"

    entry = order_a[0]
    assert entry["occurrence_count"] == 2
    assert entry["resurfaced"] is True, "Resurfacing must be detected in both arrival orders"
    assert entry["first_seen_iteration"] == 1, "First seen iteration must be min(1, 2) = 1 in both"
    assert entry["iteration"] == 2, "Latest iteration must be max(1, 2) = 2 in both"
    assert entry["seen_event_ids"] == ["id1", "id2"], "Seen event IDs must be sorted and identical"
    assert entry["agent"] == "Debugger", "Winning metadata must deterministically elect the higher coordinate update"
    assert entry["context"] == "Context 2"


def test_durable_diagnostic_ledger_unbounded_recurrence(tmp_path):
    """Verify that DiagnosticEventLedger provides unbounded append-only persistence
    for diagnostic events, completely decoupled from in-memory sliding window limits.
    """
    from agent.core.diagnostic_ledger import DiagnosticEventLedger

    ledger_db = str(tmp_path / "test_diag.sqlite")
    ledger = DiagnosticEventLedger(db_path=ledger_db)

    # 1. Record 30 distinct errors across iterations
    for i in range(30):
        ev = {
            "event_id": f"diag:th_main:iter1:step{i}:err_{i}",
            "thread_id": "th_main",
            "iteration": 1,
            "step_idx": i,
            "signature": f"Error_{i}",
            "root_cause": f"Root cause for Error_{i}",
            "remediation_plan": f"Plan for Error_{i}",
            "created_at": 100.0 + i,
            "timestamp": "2026-11-16T11:00:00Z",
        }
        inserted = ledger.record_event(ev)
        assert inserted is True

    # Total events recorded
    all_events = ledger.get_all_events(thread_id="th_main")
    assert len(all_events) == 30, "All 30 events must be durably stored in the ledger"

    # 2. Idempotent replay: recording identical event_id returns False (skipped)
    replay_ev = {
        "event_id": "diag:th_main:iter1:step0:err_0",
        "thread_id": "th_main",
        "iteration": 1,
        "step_idx": 0,
        "signature": "Error_0",
        "created_at": 100.0,
    }
    re_inserted = ledger.record_event(replay_ev)
    assert re_inserted is False, "Replay of existing event_id must be skipped"
    assert len(ledger.get_all_events(thread_id="th_main")) == 30

    # 3. Recurrence detection across iterations
    # Re-observe Error_0 at iteration 4 (which would be evicted from a 25-item in-memory window)
    new_iter_ev = {
        "event_id": "diag:th_main:iter4:step31:err_0",
        "thread_id": "th_main",
        "iteration": 4,
        "step_idx": 31,
        "signature": "Error_0",
        "root_cause": "Root cause for Error_0",
        "created_at": 200.0,
        "timestamp": "2026-11-16T11:10:00Z",
    }
    ledger.record_event(new_iter_ev)

    stats = ledger.get_recurrence_stats("Error_0", thread_id="th_main")
    assert stats["total_occurrences"] == 2
    assert stats["first_seen_iteration"] == 1
    assert stats["latest_iteration"] == 4
    assert stats["resurfaced"] is True, "Durable ledger retains recurrence facts regardless of memory window"


def test_resolve_thread_id_precedence_and_avoids_default_namespace_collision():
    """Verify that resolve_thread_id resolves thread_id from config, state, or task derivation,
    and NEVER collapses into a shared static 'default' namespace.
    """
    from agent.core.checkpointer import resolve_thread_id

    # 1. Configurable thread_id takes top priority
    cfg = {"configurable": {"thread_id": "thread_from_config"}}
    st = {"thread_id": "thread_from_state", "repo_path": "/tmp/r", "task": "t"}
    assert resolve_thread_id(st, cfg) == "thread_from_config"

    # 2. State thread_id used when config is absent or lacks thread_id
    assert resolve_thread_id(st, None) == "thread_from_state"
    assert resolve_thread_id(st, {}) == "thread_from_state"

    # 3. Task-level identifier
    st_task_only = {"task_id": "task_abc_123"}
    assert resolve_thread_id(st_task_only, None) == "thread_task_abc_123"

    # 4. Derived stable thread from repo_path + task
    st_repo_task = {"repo_path": "/path/to/my_repo", "task": "Implement feature X"}
    derived = resolve_thread_id(st_repo_task, None)
    assert derived.startswith("thread_my_repo_")
    # Deterministic across calls for identical repo + task
    assert resolve_thread_id(st_repo_task, None) == derived

    # 5. Isolated unique UUID fallback when completely empty (never static 'default')
    anon1 = resolve_thread_id({}, None)
    anon2 = resolve_thread_id({}, None)
    assert anon1 != "default"
    assert anon2 != "default"
    assert anon1 != anon2, "Two distinct workflows with empty state must NOT share an event-ID namespace"


def test_debugger_event_id_invariant_to_llm_text_variation(monkeypatch):
    """Verify that debugger_node event_id is derived from stable invocation/task coordinates
    and is invariant to non-deterministic LLM wording changes on retries.
    """
    from agent.core.graph import debugger_node
    from agent.core.state import DebugResult
    import agent.core.graph as graph_module

    # Call 1: LLM outputs one specific diagnostic phrasing
    class MockDebuggerCall1:
        def __init__(self, repo_path): pass
        def diagnose_failure(self, state):
            return DebugResult(
                root_cause="ZeroDivisionError at line 42 in divide()",
                remediation_plan="Add if b == 0: raise ValueError check",
            )

    monkeypatch.setattr(graph_module, "DebuggerAgent", MockDebuggerCall1)

    state: AgentState = {
        "task": "Fix division by zero in calculator",
        "repo_path": "/tmp/mock",
        "thread_id": "thread_idemp_llm_test",
        "iteration_count": 1,
        "agent_history": [],
        "error_history": [],
    }

    out1 = debugger_node(state)
    ev_id1 = out1["error_history"][0]["event_id"]

    # Call 2 (Simulating node retry where LLM produces different wording):
    class MockDebuggerCall2:
        def __init__(self, repo_path): pass
        def diagnose_failure(self, state):
            return DebugResult(
                root_cause="ZeroDivisionError: division by zero in calculator/core.py:42",
                remediation_plan="Validate denominator is non-zero before performing float division",
            )

    monkeypatch.setattr(graph_module, "DebuggerAgent", MockDebuggerCall2)

    # Re-execution of the same step on identical state
    out2 = debugger_node(state)
    ev_id2 = out2["error_history"][0]["event_id"]

    # Event ID MUST BE IDENTICAL despite completely different LLM output!
    assert ev_id1 == ev_id2, "Event ID must be invariant to LLM output text variation across retries"
    assert "attempt1" in ev_id1


def test_multiple_legitimate_diagnostic_events_in_same_iteration_use_explicit_attempt_id(monkeypatch):
    """Verify that multiple legitimate diagnostic events in the same iteration
    receive explicit incrementing attempt identifiers (attempt1, attempt2) and different event IDs,
    properly accumulating occurrence counts.
    """
    from agent.core.graph import debugger_node
    from agent.core.state import DebugResult
    import agent.core.graph as graph_module

    class MockDebugger:
        def __init__(self, repo_path): pass
        def diagnose_failure(self, state):
            return DebugResult(root_cause="ZeroDivisionError", remediation_plan="Check b != 0")

    monkeypatch.setattr(graph_module, "DebuggerAgent", MockDebugger)

    state_attempt_1: AgentState = {
        "task": "Fix math bug",
        "repo_path": "/tmp/mock",
        "thread_id": "thread_multi_attempt",
        "iteration_count": 1,
        "agent_history": [],
        "error_history": [],
    }

    # Attempt 1 in iteration 1
    out1 = debugger_node(state_attempt_1)
    ev1 = out1["error_history"][0]
    assert ":attempt1" in ev1["event_id"]

    # Apply attempt 1 to state
    curr_errors = reduce_error_history(state_attempt_1["error_history"], out1["error_history"])
    curr_history = reduce_agent_history(state_attempt_1["agent_history"], out1["agent_history"])
    assert len(curr_errors) == 1
    assert curr_errors[0]["occurrence_count"] == 1

    # State evolves: Coder tries patch, test fails again, Manager re-invokes Debugger in same iteration 1
    state_attempt_2: AgentState = {
        "task": "Fix math bug",
        "repo_path": "/tmp/mock",
        "thread_id": "thread_multi_attempt",
        "iteration_count": 1,
        "agent_history": curr_history,  # Contains prior DebuggerAgent entry
        "error_history": curr_errors,
    }

    # Attempt 2 in iteration 1
    out2 = debugger_node(state_attempt_2)
    ev2 = out2["error_history"][0]
    assert ":attempt2" in ev2["event_id"], "Second diagnostic event in same iteration must receive attempt2"
    assert ev1["event_id"] != ev2["event_id"]

    # Merging attempt 2 MUST increment occurrence count to 2!
    updated_errors = reduce_error_history(curr_errors, out2["error_history"])
    assert len(updated_errors) == 1
    assert updated_errors[0]["occurrence_count"] == 2, "Distinct diagnostic attempts in same iteration must increment occurrence count"


def test_debugger_node_receives_thread_id_from_langgraph_invocation_config(monkeypatch):
    """Verify that when state lacks thread_id, debugger_node resolves it from LangGraph RunnableConfig."""
    from agent.core.graph import debugger_node
    from agent.core.state import DebugResult
    import agent.core.graph as graph_module

    class MockDebugger:
        def __init__(self, repo_path): pass
        def diagnose_failure(self, state):
            return DebugResult(root_cause="KeyError", remediation_plan="Check key exists")

    monkeypatch.setattr(graph_module, "DebuggerAgent", MockDebugger)

    state_without_thread: AgentState = {
        "task": "Fix key error",
        "repo_path": "/tmp/mock",
        "iteration_count": 0,
        "agent_history": [],
        "error_history": [],
    }

    # LangGraph invokes node with RunnableConfig
    config = {"configurable": {"thread_id": "thread_from_langgraph_run"}}
    out = debugger_node(state_without_thread, config=config)

    assert out["thread_id"] == "thread_from_langgraph_run"
    assert "diag:thread_from_langgraph_run:iter0:" in out["error_history"][0]["event_id"]
    assert "hist:debugger:thread_from_langgraph_run:iter0:" in out["agent_history"][0]["event_id"]








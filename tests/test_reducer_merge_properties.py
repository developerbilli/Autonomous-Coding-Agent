"""Formal Mathematical and Empirical Tests for Reducer Merge Properties.

Verifies the algebraic laws required for deterministic parallel multi-agent execution:
1. Deterministic Ordering: Parallel node outputs with sequence numbers/timestamps
   guarantee identical chronological sequences regardless of thread scheduling.
2. Associativity: (A ⊕ B) ⊕ C == A ⊕ (B ⊕ C) across all chunkings and batches.
3. Commutativity of Parallel Merges: A ⊕ B == B ⊕ A for sibling parallel branches.
4. Idempotence: A ⊕ A == A for set channels and idempotent event retries.
5. Identity (Neutral Element): A ⊕ ∅ == A and ∅ ⊕ A == A.
"""

import itertools
import pytest

from agent.core.state import (
    ErrorEvent,
    reduce_error_history,
    reduce_completed_actions,
    reduce_agent_history,
    get_next_sequence_num,
    reset_sequence_counter,
)


@pytest.fixture(autouse=True)
def clean_sequence_state():
    reset_sequence_counter()
    yield
    reset_sequence_counter()


# ============================================================
# 1. Deterministic Ordering & Commutativity under Parallel Execution
# ============================================================

def test_parallel_nodes_deterministic_ordering_with_sequence_numbers():
    """Suppose two parallel nodes return E2 and E3.
    
    With sequence numbers or logical timestamps, the resulting state
    must be 100% deterministic regardless of which branch completes first.
    """
    seq1 = get_next_sequence_num()  # 1
    seq2 = get_next_sequence_num()  # 2

    # Node A runs on thread 1
    e2 = ErrorEvent(
        signature="ZeroDivisionError: division by zero",
        agent="TestGeneratorAgent",
        iteration=1,
        superstep=1,
        sequence_num=seq1,
        created_at=1000.0,
    )
    # Node B runs in parallel on thread 2
    e3 = ErrorEvent(
        signature="TypeError: unsupported operand type",
        agent="ReviewerAgent",
        iteration=1,
        superstep=1,
        sequence_num=seq2,
        created_at=1000.5,
    )

    init = []

    # Run 1: Branch A finishes before Branch B
    merged_a_then_b = reduce_error_history(reduce_error_history(init, e2), e3)

    # Run 2: Branch B finishes before Branch A
    merged_b_then_a = reduce_error_history(reduce_error_history(init, e3), e2)

    # Run 3: Batched arrival in [e2, e3]
    merged_batch_1 = reduce_error_history(init, [e2, e3])

    # Run 4: Batched arrival in [e3, e2]
    merged_batch_2 = reduce_error_history(init, [e3, e2])

    # Verification: All 4 execution paths yield identical deterministic ordering!
    assert merged_a_then_b == merged_b_then_a
    assert merged_a_then_b == merged_batch_1
    assert merged_a_then_b == merged_batch_2

    # Sequence number 1 (ZeroDivisionError) must precede sequence number 2 (TypeError)
    assert merged_a_then_b[0]["signature"] == "ZeroDivisionError: division by zero"
    assert merged_a_then_b[1]["signature"] == "TypeError: unsupported operand type"


def test_parallel_fan_out_all_permutations_yield_identical_state():
    """Simulate 3 parallel specialist nodes emitting events in arbitrary order.
    
    All 3! = 6 arrival permutations MUST reduce to the exact same state snapshot.
    """
    e1 = {
        "signature": "SyntaxError: invalid syntax",
        "agent": "CompilerAgent",
        "superstep": 1,
        "sequence_num": 1,
        "created_at": 100.0,
    }
    e2 = {
        "signature": "RuntimeError: timeout",
        "agent": "SandboxAgent",
        "superstep": 1,
        "sequence_num": 2,
        "created_at": 100.1,
    }
    e3 = {
        "signature": "AssertionError: test failed",
        "agent": "TestRunnerAgent",
        "superstep": 1,
        "sequence_num": 3,
        "created_at": 100.2,
    }

    events = [e1, e2, e3]
    reference_result = None

    for perm in itertools.permutations(events):
        result = reduce_error_history([], list(perm))
        if reference_result is None:
            reference_result = result
        else:
            assert result == reference_result, f"Permutation {perm} failed to match deterministic order"

    assert len(reference_result) == 3
    assert [e["signature"] for e in reference_result] == [
        "SyntaxError: invalid syntax",
        "RuntimeError: timeout",
        "AssertionError: test failed",
    ]


# ============================================================
# 2. Associativity Law: (A ⊕ B) ⊕ C == A ⊕ (B ⊕ C)
# ============================================================

def test_reduce_error_history_associativity_with_occurrence_counts():
    """Verify (A ⊕ B) ⊕ C == A ⊕ (B ⊕ C) for error history with occurrences."""
    sig = "DatabaseConnectionError: pool exhausted"

    # Batch A has 2 occurrences
    batch_a = [
        {"signature": sig, "agent": "AgentA", "iteration": 1, "occurrence_count": 2, "created_at": 10.0}
    ]
    # Batch B has 3 occurrences
    batch_b = [
        {"signature": sig, "agent": "AgentB", "iteration": 1, "occurrence_count": 3, "created_at": 15.0}
    ]
    # Batch C has 5 occurrences
    batch_c = [
        {"signature": sig, "agent": "AgentC", "iteration": 2, "occurrence_count": 5, "created_at": 20.0}
    ]

    # Left-associative fold: (A ⊕ B) ⊕ C
    left = reduce_error_history(reduce_error_history(batch_a, batch_b), batch_c)

    # Right-associative fold: A ⊕ (B ⊕ C)
    b_c = reduce_error_history(batch_b, batch_c)
    right = reduce_error_history(batch_a, b_c)

    assert left == right
    assert len(left) == 1
    # Occurrence count must aggregate additively: 2 + 3 + 5 = 10
    assert left[0]["occurrence_count"] == 10
    assert left[0]["resurfaced"] is True


def test_reduce_completed_actions_associativity():
    """Verify (A ⊕ B) ⊕ C == A ⊕ (B ⊕ C) for completed_actions channel."""
    a = ["coder:patch:core.py:iter0", "test_gen:tests.py:iter0"]
    b = ["coder:patch:core.py:iter0", "review:approval:iter0"]
    c = ["git:commit:iter0", "test_gen:tests.py:iter0"]

    left = reduce_completed_actions(reduce_completed_actions(a, b), c)
    right = reduce_completed_actions(a, reduce_completed_actions(b, c))

    assert left == right
    # Canonical unique set
    assert left == [
        "coder:patch:core.py:iter0",
        "git:commit:iter0",
        "review:approval:iter0",
        "test_gen:tests.py:iter0",
    ]


def test_reduce_agent_history_associativity():
    """Verify (A ⊕ B) ⊕ C == A ⊕ (B ⊕ C) for agent execution telemetry."""
    ev1 = {"agent": "Planner", "action": "create_plan", "superstep": 1, "sequence_num": 1, "created_at": 1.0}
    ev2 = {"agent": "Coder", "action": "implement", "superstep": 2, "sequence_num": 2, "created_at": 2.0}
    ev3 = {"agent": "Tester", "action": "run_tests", "superstep": 3, "sequence_num": 3, "created_at": 3.0}

    left = reduce_agent_history(reduce_agent_history([ev1], [ev2]), [ev3])
    right = reduce_agent_history([ev1], reduce_agent_history([ev2], [ev3]))

    assert left == right
    assert [e["agent"] for e in left] == ["Planner", "Coder", "Tester"]


# ============================================================
# 3. Commutativity & Idempotence Laws
# ============================================================

def test_reduce_completed_actions_commutativity_and_idempotence():
    """Verify A ⊕ B == B ⊕ A (Commutativity) and A ⊕ A == A (Idempotence)."""
    set1 = ["action_1", "action_2"]
    set2 = ["action_2", "action_3"]

    # Commutativity
    assert reduce_completed_actions(set1, set2) == reduce_completed_actions(set2, set1)

    # Idempotence: applying identical set leaves it completely unchanged
    res = reduce_completed_actions(set1, set1)
    assert res == ["action_1", "action_2"]


def test_error_event_idempotent_retry_deduplication():
    """Verify replaying the same error event (matching event_id) does not spuriously increment counts."""
    event = ErrorEvent(
        signature="ZeroDivisionError: division by zero",
        agent="CoderAgent",
        iteration=1,
        sequence_num=10,
        event_id="evt_retry_uuid_999",
    )

    init = []
    res1 = reduce_error_history(init, event)
    assert res1[0]["occurrence_count"] == 1

    # Node retries on transient error and replays the same event
    res2 = reduce_error_history(res1, event)
    assert res2[0]["occurrence_count"] == 1, "Idempotent event retry must NOT increment occurrence count"

    # A genuinely new event with distinct event_id DOES increment
    new_event = ErrorEvent(
        signature="ZeroDivisionError: division by zero",
        agent="CoderAgent",
        iteration=1,
        sequence_num=11,
        event_id="evt_new_occurrence_1000",
    )
    res3 = reduce_error_history(res2, new_event)
    assert res3[0]["occurrence_count"] == 2


# ============================================================
# 4. Identity Law: A ⊕ ∅ == A and ∅ ⊕ A == A
# ============================================================

def test_reducer_identity_neutral_element():
    """Verify empty updates produce identity behavior."""
    err_input = [{"signature": "E1", "occurrence_count": 1, "iteration": 1, "first_seen_iteration": 1, "sequence_num": 1, "created_at": 1.0}]
    err_state = reduce_error_history(None, err_input)
    act_state = ["act_1", "act_2"]
    hist_state = [{"agent": "Coder", "action": "patch", "superstep": 1, "sequence_num": 1}]

    # A ⊕ None == A
    assert reduce_error_history(err_state, None) == err_state
    assert reduce_completed_actions(act_state, None) == act_state
    assert reduce_agent_history(hist_state, None) == hist_state

    # A ⊕ [] == A
    assert reduce_error_history(err_state, []) == err_state
    assert reduce_completed_actions(act_state, []) == act_state
    assert reduce_agent_history(hist_state, []) == hist_state

    # None ⊕ A == A
    assert reduce_error_history(None, err_state) == err_state
    assert reduce_completed_actions(None, act_state) == act_state
    assert reduce_agent_history(None, hist_state) == hist_state


# ============================================================
# 5. Full Permutation Invariance & Non-First-Arrival-Wins Replay
# ============================================================

def test_duplicate_event_id_with_different_timestamps_all_permutations():
    """Verify that replaying an identical event_id with different timestamps
    does NOT suffer from first-arrival-wins non-determinism.
    
    All permutations of arrival MUST converge to the identical canonical creation time.
    """
    e_original = {
        "signature": "ConnectionTimeout",
        "iteration": 1,
        "sequence_num": 1,
        "created_at": 100.0,
        "timestamp": "2026-11-16T10:00:00Z",
        "event_id": "evt_connect_timeout_001",
        "agent": "Coder",
    }
    e_retry_later = {
        "signature": "ConnectionTimeout",
        "iteration": 1,
        "sequence_num": 1,
        "created_at": 105.0,  # 5 seconds later due to retry clock advancement
        "timestamp": "2026-11-16T10:00:05Z",
        "event_id": "evt_connect_timeout_001",  # Same logical event!
        "agent": "Coder",
    }

    # Order 1: original first, retry second
    order1 = reduce_error_history(reduce_error_history(None, [e_original]), [e_retry_later])
    # Order 2: retry first, original second (e.g. out-of-order network arrival)
    order2 = reduce_error_history(reduce_error_history(None, [e_retry_later]), [e_original])
    # Batch permutations
    batch1 = reduce_error_history([], [e_original, e_retry_later])
    batch2 = reduce_error_history([], [e_retry_later, e_original])

    # Must be 100% bit-for-bit identical across all permutations
    assert order1 == order2 == batch1 == batch2
    assert len(order1) == 1
    assert order1[0]["occurrence_count"] == 1, "Idempotent replay must not increment occurrence count"
    assert order1[0]["created_at"] == 100.0, "Earliest canonical creation time must be elected deterministically"
    assert order1[0]["timestamp"] == "2026-11-16T10:00:00Z"


def test_intervening_error_resurfacing_all_permutations():
    """Verify that an error resurfacing after an intervening error is detected
    in ALL 3! = 6 arrival permutations of the event set.
    """
    a1 = {"signature": "AlphaError", "iteration": 1, "sequence_num": 1, "created_at": 10.0, "agent": "AgentA"}
    b = {"signature": "BetaError", "iteration": 1, "sequence_num": 2, "created_at": 20.0, "agent": "AgentB"}
    a2 = {"signature": "AlphaError", "iteration": 1, "sequence_num": 3, "created_at": 30.0, "agent": "AgentA"}

    events = [a1, b, a2]
    reference_result = None

    for perm in itertools.permutations(events):
        # 1. Batched reduction
        batch_res = reduce_error_history([], list(perm))
        # 2. Sequential incremental fold
        fold_res = []
        for ev in perm:
            fold_res = reduce_error_history(fold_res, [ev])

        assert batch_res == fold_res, f"Batch vs fold discrepancy on permutation {perm}"

        if reference_result is None:
            reference_result = batch_res
        else:
            assert batch_res == reference_result, f"Permutation {perm} produced divergent state:\nExpected: {reference_result}\nGot: {batch_res}"

    alpha_entry = next(e for e in reference_result if e["signature"] == "AlphaError")
    beta_entry = next(e for e in reference_result if e["signature"] == "BetaError")

    assert alpha_entry["occurrence_count"] == 2
    assert alpha_entry["resurfaced"] is True, "AlphaError must resurface across all 6 arrival permutations"
    assert beta_entry["occurrence_count"] == 1
    assert beta_entry["resurfaced"] is False, "BetaError occurred once and must not be marked resurfaced"


def test_consecutive_errors_all_permutations_never_falsely_resurface():
    """Verify that consecutive occurrences of the latest error NEVER falsely mark it as resurfaced,
    regardless of arrival permutation.
    """
    a = {"signature": "AlphaError", "iteration": 1, "sequence_num": 1, "created_at": 10.0, "agent": "AgentA"}
    b1 = {"signature": "BetaError", "iteration": 1, "sequence_num": 2, "created_at": 20.0, "agent": "AgentB"}
    b2 = {"signature": "BetaError", "iteration": 1, "sequence_num": 3, "created_at": 30.0, "agent": "AgentB"}

    events = [a, b1, b2]
    reference_result = None

    for perm in itertools.permutations(events):
        res = reduce_error_history([], list(perm))
        if reference_result is None:
            reference_result = res
        else:
            assert res == reference_result, f"Permutation {perm} produced divergent state"

    alpha_entry = next(e for e in reference_result if e["signature"] == "AlphaError")
    beta_entry = next(e for e in reference_result if e["signature"] == "BetaError")

    assert alpha_entry["resurfaced"] is False
    assert beta_entry["resurfaced"] is False, "Consecutive occurrences of BetaError must NOT be marked resurfaced"
    assert beta_entry["occurrence_count"] == 2

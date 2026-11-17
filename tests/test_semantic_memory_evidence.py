"""Empirical Evidence & Dynamic Confidence Verification for Semantic Memory.

Validates that:
1. Semantic patterns track empirical validation evidence receipts:
   - `successful_reuses`
   - `failed_reuses`
   - `confidence` (Bayesian posterior with evidence depth factor)
   - `validation_evidence` (e.g. unit_tests_passed, regression_test_passed)
   - `last_verified`
2. Repeated successful reuses with regression proofs elevate confidence to 0.95.
3. Failed reuses penalize confidence and trigger automatic deprecation when confidence < 0.45.
4. Retrieval ranking prioritizes battle-tested reusable patterns over one-time successful patches.
5. LangGraph lifecycle automatically updates semantic pattern reuse outcomes during finalization.
"""

import tempfile
import time
from pathlib import Path

import pytest

from agent.memory.models import SemanticPattern, Episode
from agent.memory.semantic_memory import SemanticMemoryStore
from agent.memory.engine import MemoryEngine
from agent.core.state import AgentState, reduce_error_history, reduce_completed_actions, reduce_agent_history
from agent.core.graph import manager_finalize_node


@pytest.fixture
def temp_semantic_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_semantic_evidence.sqlite"
        store = SemanticMemoryStore(str(db_path))
        yield store


@pytest.fixture
def temp_memory_engine():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_engine_evidence.sqlite"
        engine = MemoryEngine(str(db_path))
        yield engine


def test_semantic_pattern_bayesian_confidence_evolution(temp_semantic_store):
    """Verifies that 4 successful reuses with regression evidence boost confidence to 0.95."""
    store = temp_semantic_store

    initial_pattern = SemanticPattern(
        pattern_id="pat_div_zero_guard",
        pattern="Guard against zero denominator",
        pattern_type="convention",
        repo_identifier="global",
        topic="arithmetic_safety",
        content="Check if denominator == 0 and raise ZeroDivisionError before division.",
        tags=["zerodivision", "arithmetic", "division", "guard"],
        confidence=0.75,
        successful_reuses=0,
        failed_reuses=0,
        language="python",
        validation_evidence=[],
        status="active",
    )
    store.store_pattern(initial_pattern)

    # 1st reuse: Unit test passes
    p1 = store.record_reuse("pat_div_zero_guard", success=True, evidence="unit_tests_passed")
    assert p1.successful_reuses == 1
    assert p1.failed_reuses == 0
    assert "unit_tests_passed" in p1.validation_evidence

    # 2nd reuse: Regression test passes
    p2 = store.record_reuse("pat_div_zero_guard", success=True, evidence="regression_test_passed")
    assert p2.successful_reuses == 2
    assert "regression_test_passed" in p2.validation_evidence

    # 3rd reuse: Another repository reuse (re-verifying unit tests)
    p3 = store.record_reuse("pat_div_zero_guard", success=True, evidence="unit_tests_passed")
    assert p3.successful_reuses == 3

    # 4th reuse: Production task verified (re-verifying regression tests)
    p4 = store.record_reuse("pat_div_zero_guard", success=True, evidence="regression_test_passed")
    assert p4.successful_reuses == 4
    assert p4.failed_reuses == 0
    assert p4.language == "python"
    assert p4.pattern == "Guard against zero denominator"
    assert p4.confidence == 0.95
    assert p4.validation_evidence == [
        "unit_tests_passed",
        "regression_test_passed",
    ]
    assert p4.last_verified is not None


def test_failed_reuses_degrade_confidence_and_trigger_deprecation(temp_semantic_store):
    """Verifies that regressions degrade confidence and deprecate unreliable patterns."""
    store = temp_semantic_store

    flaky_pattern = SemanticPattern(
        pattern_id="pat_flaky_retry",
        pattern="Bare retry on exception without backoff",
        pattern_type="convention",
        repo_identifier="global",
        topic="network",
        content="While True try and catch Exception without delay",
        tags=["retry", "exception"],
        confidence=0.75,
        successful_reuses=0,
        failed_reuses=0,
        language="python",
        validation_evidence=[],
        status="active",
    )
    store.store_pattern(flaky_pattern)

    # 1st failure
    p1 = store.record_reuse("pat_flaky_retry", success=False, evidence="infinite_loop_timeout")
    assert p1.failed_reuses == 1
    assert p1.confidence < 0.75
    assert p1.status == "active"

    # 2nd failure
    p2 = store.record_reuse("pat_flaky_retry", success=False, evidence="thread_starvation")
    assert p2.failed_reuses == 2
    assert p2.status == "active"

    # 3rd failure: Triggers auto-deprecation
    p3 = store.record_reuse("pat_flaky_retry", success=False, evidence="cpu_spike_regression")
    assert p3.failed_reuses == 3
    assert p3.confidence < 0.45
    assert p3.status == "deprecated"

    # Deprecated patterns must not be retrieved during recall
    active_recalled = store.recall_patterns("retry exception network")
    assert not any(p.pattern_id == "pat_flaky_retry" for p in active_recalled)


def test_empirical_ranking_prioritizes_reusable_over_onetime_patch(temp_semantic_store):
    """Retrieval prioritizes battle-tested patterns (successful_reuses=4) over one-time patches."""
    store = temp_semantic_store

    # Proven Pattern: Reused 4 times with unit and regression test receipts
    proven_pattern = SemanticPattern(
        pattern_id="pat_proven_guard",
        pattern="Guard against zero denominator with explicit ValueError",
        pattern_type="convention",
        repo_identifier="global",
        topic="division_safety",
        title="Guard against zero denominator with explicit ValueError",
        content="Verify denominator is nonzero before quotient computation.",
        tags=["zerodivision", "guard", "denominator"],
        confidence=0.95,
        successful_reuses=4,
        failed_reuses=0,
        language="python",
        validation_evidence=["unit_tests_passed", "regression_test_passed"],
        status="active",
    )
    store.store_pattern(proven_pattern)

    # Candidate Pattern: Just created, 0 reuses, review_score was high but never tested across tasks
    candidate_pattern = SemanticPattern(
        pattern_id="pat_candidate_guard",
        pattern="Guard against zero denominator with try-except pass",
        pattern_type="convention",
        repo_identifier="global",
        topic="division_safety",
        title="Guard against zero denominator with try-except pass",
        content="Wrap denominator division in try-except ZeroDivisionError return 0.",
        tags=["zerodivision", "guard", "denominator"],
        confidence=0.70,
        successful_reuses=0,
        failed_reuses=0,
        language="python",
        validation_evidence=["unit_tests_passed"],
        status="active",
    )
    store.store_pattern(candidate_pattern)

    # Query for denominator guard
    results = store.recall_patterns("Guard against zero denominator", limit=2)
    assert len(results) >= 2
    # The proven reusable pattern with 4 reuses and regression proofs MUST rank #1
    assert results[0].pattern_id == "pat_proven_guard"
    assert results[0].confidence == 0.95
    assert results[0].successful_reuses == 4
    assert "regression_test_passed" in results[0].validation_evidence

    assert results[1].pattern_id == "pat_candidate_guard"
    assert results[1].confidence == 0.70
    assert results[1].successful_reuses == 0


def test_graph_lifecycle_empirical_evidence_feedback(temp_memory_engine, monkeypatch):
    """Verifies that manager_finalize_node automatically updates reuse metrics for applied patterns."""
    engine = temp_memory_engine
    import agent.core.graph as graph_module
    monkeypatch.setattr(graph_module, "get_memory_engine", lambda: engine)

    # Seed a pattern in semantic memory
    seed_pattern = SemanticPattern(
        pattern_id="pat_tested_rule",
        pattern="Enforce defensive input bounds",
        pattern_type="convention",
        repo_identifier="global",
        topic="input_validation",
        title="Enforce defensive input bounds",
        content="Check input >= 0",
        tags=["bounds"],
        confidence=0.75,
        successful_reuses=0,
        failed_reuses=0,
        language="python",
        validation_evidence=[],
        status="active",
    )
    engine.semantic_store.store_pattern(seed_pattern)

    # Create mock verification result
    class MockOutcome:
        value = "completed_successfully"

    class MockVerificationResult:
        verified = True
        toctou_valid = True
        outcome = MockOutcome()
        failure_reasons = []
        snapshot_hash = "mock_hash"
        verified_manifest = {"main.py": "hash123"}
        verifier_report = "Verification passed."

    mock_ver_res = MockVerificationResult()

    # Mock IndependentVerifier methods
    class MockVerifier:
        def __init__(self, repo_path):
            pass
        def verify(self, state):
            return mock_ver_res
        def verify_manifest_intact(self, manifest):
            return True, []
        def create_immutable_handover(self, manifest):
            return "/mock/handover.tar.gz", "handover_hash_123"

    monkeypatch.setattr(graph_module, "IndependentVerifier", MockVerifier)
    monkeypatch.setattr(graph_module, "is_task_successful", lambda s, v: True)

    # Build simulated state that applied 'pat_tested_rule'
    state: AgentState = {
        "task": "Add input validation to divide function",
        "repo_path": "/tmp/mock_repo",
        "thread_id": "thread_evidence_test_1",
        "applied_pattern_ids": ["pat_tested_rule"],
        "proposed_patches": {"main.py": "def divide(a, b): ..."},
        "agent_history": [],
        "completed_actions": [],
        "error_history": [],
    }

    # Execute manager_finalize_node
    updates = manager_finalize_node(state)
    assert updates["task_succeeded"] is True

    # Assert that pat_tested_rule received empirical validation evidence
    updated_pat = engine.semantic_store.recall_patterns("Enforce defensive input bounds")[0]
    assert updated_pat.successful_reuses == 1
    assert "unit_tests_passed" in updated_pat.validation_evidence
    assert updated_pat.last_verified is not None


def test_graph_lifecycle_failure_evidence_feedback(temp_memory_engine, monkeypatch):
    """Verifies that manager_finalize_node penalizes patterns when workflow verification fails."""
    engine = temp_memory_engine
    import agent.core.graph as graph_module
    monkeypatch.setattr(graph_module, "get_memory_engine", lambda: engine)

    # Seed an active pattern
    seed_pattern = SemanticPattern(
        pattern_id="pat_regressed_rule",
        pattern="Unsafe regex string parsing",
        pattern_type="convention",
        repo_identifier="global",
        topic="regex",
        title="Unsafe regex string parsing",
        content="Use re.match without timeout",
        tags=["regex"],
        confidence=0.75,
        successful_reuses=0,
        failed_reuses=0,
        language="python",
        validation_evidence=[],
        status="active",
    )
    engine.semantic_store.store_pattern(seed_pattern)

    class MockOutcome:
        value = "completed_with_failures"

    class MockVerificationResult:
        verified = False
        toctou_valid = False
        outcome = MockOutcome()
        failure_reasons = ["Regression in unit tests"]
        snapshot_hash = None
        verified_manifest = None
        verifier_report = "Tests failed."

    mock_ver_res = MockVerificationResult()

    class MockVerifier:
        def __init__(self, repo_path):
            pass
        def verify(self, state):
            return mock_ver_res
        def verify_manifest_intact(self, manifest):
            return False, ["mutated.py"]
        def create_immutable_handover(self, manifest):
            return None, None

    monkeypatch.setattr(graph_module, "IndependentVerifier", MockVerifier)
    monkeypatch.setattr(graph_module, "is_task_successful", lambda s, v: False)

    state: AgentState = {
        "task": "Refactor regex parsing",
        "repo_path": "/tmp/mock_repo",
        "thread_id": "thread_fail_1",
        "applied_pattern_ids": ["pat_regressed_rule"],
        "agent_history": [],
        "completed_actions": [],
        "error_history": [],
    }

    updates = manager_finalize_node(state)
    assert updates["task_succeeded"] is False

    updated_pat = engine.semantic_store.recall_patterns("Unsafe regex string parsing")[0]
    assert updated_pat.failed_reuses == 1
    assert "FAILED:verification_failed" in updated_pat.validation_evidence
    assert updated_pat.confidence < 0.75

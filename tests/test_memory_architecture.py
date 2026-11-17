"""Tests for Long-Term Semantic and Episodic Memory Architecture."""

import tempfile
from pathlib import Path
import pytest

from agent.memory.models import Episode, SemanticPattern, MemoryQuery
from agent.memory.episodic_memory import EpisodicMemoryStore
from agent.memory.semantic_memory import SemanticMemoryStore
from agent.memory.engine import MemoryEngine


@pytest.fixture
def temp_memory_db():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_memory.sqlite"
        yield str(db_path)


def test_episodic_memory_recording_and_retrieval(temp_memory_db):
    """Verify episodic memory stores task episodes and recalls by task and error signatures."""
    store = EpisodicMemoryStore(temp_memory_db)

    ep1 = Episode(
        episode_id="ep_001",
        timestamp="2026-11-01T10:00:00Z",
        thread_id="th_001",
        repo_identifier="calculator_repo",
        task_description="Implement calculate_percentage and add division by zero ValueError guard",
        task_type="feature",
        error_signatures=["ZeroDivisionError: division by zero", "ValueError: cannot divide by zero"],
        remediation_strategy="Add `if total == 0: raise ValueError('Cannot divide by zero')` guard",
        files_modified=["calculator.py"],
        test_passed=True,
        review_score=9.5,
        outcome="success",
    )

    ep2 = Episode(
        episode_id="ep_002",
        timestamp="2026-11-02T10:00:00Z",
        thread_id="th_002",
        repo_identifier="auth_service",
        task_description="Refactor JWT token validator to check expiry claims",
        task_type="bug_fix",
        error_signatures=["ExpiredSignatureError: Signature has expired"],
        remediation_strategy="Catch ExpiredSignatureError and return 401 Unauthorized",
        files_modified=["jwt_auth.py"],
        test_passed=True,
        review_score=9.0,
        outcome="success",
    )

    store.record_episode(ep1)
    store.record_episode(ep2)

    # Query matching percentage task
    q1 = MemoryQuery(query_text="add calculate_percentage to calculator", repo_identifier="calculator_repo")
    recalled1 = store.recall_episodes(q1)
    assert len(recalled1) >= 1
    assert recalled1[0].episode_id == "ep_001"
    assert "divide by zero" in recalled1[0].remediation_strategy

    # Query matching error signature
    q2 = MemoryQuery(
        query_text="fix authentication error",
        error_signature="ExpiredSignatureError: Token expired",
    )
    recalled2 = store.recall_episodes(q2)
    assert len(recalled2) >= 1
    assert recalled2[0].episode_id == "ep_002"


def test_semantic_memory_seeding_and_matching(temp_memory_db):
    """Verify semantic memory initializes standard rules and recalls by semantic topics."""
    store = SemanticMemoryStore(temp_memory_db)

    # Verify seeded default patterns
    patterns = store.recall_patterns("validation bounds ValueError")
    assert len(patterns) >= 1
    assert any("ValueError" in p.title for p in patterns)

    # Store custom project pattern
    custom_pattern = SemanticPattern(
        pattern_id="pat_microvm_kvm",
        pattern_type="architecture",
        repo_identifier="custom_sandbox",
        topic="virtualization",
        title="Firecracker Hardware KVM Virtualization",
        content="MicroVM isolation requires dedicated guest vmlinux kernel and virtio-blk block devices.",
        tags=["firecracker", "microvm", "kvm", "virtualization"],
        confidence=1.0,
    )
    store.store_pattern(custom_pattern)

    recalled = store.recall_patterns("firecracker microvm virtual devices")
    assert len(recalled) >= 1
    assert recalled[0].pattern_id == "pat_microvm_kvm"


def test_unified_memory_engine_recall_and_formatting(temp_memory_db):
    """Verify MemoryEngine combines episodic and semantic recall into ready-to-inject guidance."""
    engine = MemoryEngine(temp_memory_db)

    # Seed an episode
    ep = Episode(
        episode_id="ep_paswd",
        timestamp="2026-11-03T12:00:00Z",
        thread_id="th_paswd",
        repo_identifier="password_project",
        task_description="Refactor paswd-gen.py to add generate_password with ValueError guards",
        task_type="feature",
        error_signatures=[],
        remediation_strategy="Use secrets.choice and check length >= 4 with ValueError",
        files_modified=["paswd-gen.py"],
        test_passed=True,
        review_score=9.8,
        outcome="success",
    )
    engine.episodic_store.record_episode(ep)

    context = engine.recall_context_for_task(
        task="Refactor paswd-gen.py with length validation",
        repo_identifier="password_project",
    )

    assert context["total_recalled"] > 0
    assert "guidance_summary" in context
    assert "Recalled Past Episodes" in context["guidance_summary"]
    assert "Reusable Architectural & Coding Patterns" in context["guidance_summary"]
    assert len(context["recalled_episodes"]) >= 1


def test_record_episode_from_workflow_state(temp_memory_db):
    """Verify MemoryEngine correctly constructs and records Episode from LangGraph state."""
    engine = MemoryEngine(temp_memory_db)

    from agent.core.state import TestResult, ReviewResult, CoderResult

    state = {
        "task": "Fix integer overflow in modulo arithmetic",
        "thread_id": "thread-test-123",
        "repo_path": "/tmp/mock_repo",
        "iteration_count": 2,
        "test_results": TestResult(passed=True, exit_code=0, stdout="2 passed", stderr=""),
        "review_result": ReviewResult(approved=True, quality_score=9.5),
        "coder_result": CoderResult(
            files_modified=["math_lib.py"],
            methods_implemented=["safe_modulo"],
            rationale="Added boundary checks",
            patches={"math_lib.py": "Implemented safe_modulo"},
        ),
    }

    episode = engine.record_episode_from_state(state)
    assert episode is not None
    assert episode.test_passed is True
    assert episode.review_score == 9.5
    assert episode.files_modified == ["math_lib.py"]

    # Verify persisted in database
    recent = engine.episodic_store.get_recent_episodes(1)
    assert len(recent) == 1
    assert recent[0].task_description == "Fix integer overflow in modulo arithmetic"

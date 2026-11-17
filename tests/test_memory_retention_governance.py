"""Tests for Memory Retention Governance, Scoping, Supersession, and Promotion.

Verifies the critical architectural boundary: Persistence vs Retention:
1. Successful remediation strategies: Retained until superseded by higher-quality fixes or invalidated.
2. Failed strategies: Retained as negative memory / anti-patterns with failure post-mortems.
3. Repository-specific facts: Isolated strictly by repository namespace to prevent cross-repo leakage.
4. General coding patterns: Promoted from episodic memory to global semantic memory after validation.
"""

import tempfile
from pathlib import Path
import pytest

from agent.memory.models import Episode, SemanticPattern, MemoryQuery
from agent.memory.episodic_memory import EpisodicMemoryStore
from agent.memory.semantic_memory import SemanticMemoryStore
from agent.memory.engine import MemoryEngine


@pytest.fixture
def temp_memory_engine():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "retention_test.sqlite"
        yield MemoryEngine(str(db_path))


def test_remediation_supersession_on_higher_score(temp_memory_engine):
    """Verify that a newer, superior fix supersedes an older fix for the same error signature."""
    store = temp_memory_engine.episodic_store
    err_sig = "ZeroDivisionError: division by zero"

    # Episode 1: Initial naive fix (Review score: 7.0)
    ep1 = Episode(
        episode_id="ep_naive_fix",
        timestamp="2026-11-01T10:00:00Z",
        thread_id="th_1",
        repo_identifier="calc_repo",
        task_description="Fix zero division in calculator divide",
        task_type="bug_fix",
        error_signatures=[err_sig],
        remediation_strategy="Wrap division in try/except and return 0.0",
        files_modified=["core.py"],
        test_passed=True,
        review_score=7.0,
        outcome="success",
    )
    store.record_episode(ep1)

    # Verify ep1 is active
    active = store.recall_episodes(MemoryQuery(query_text="divide", error_signature=err_sig, repo_identifier="calc_repo"))
    assert len(active) == 1
    assert active[0].episode_id == "ep_naive_fix"
    assert active[0].status == "active"

    # Episode 2: Superior architectural fix (Review score: 9.8)
    ep2 = Episode(
        episode_id="ep_superior_fix",
        timestamp="2026-11-02T10:00:00Z",
        thread_id="th_2",
        repo_identifier="calc_repo",
        task_description="Fix zero division in calculator divide",
        task_type="bug_fix",
        error_signatures=[err_sig],
        remediation_strategy="Raise explicit ValueError('Cannot divide by zero') before division",
        files_modified=["core.py"],
        test_passed=True,
        review_score=9.8,
        outcome="success",
    )
    store.record_episode(ep2)

    # Verify ep1 is automatically marked 'superseded' and superseded_by ep2
    all_episodes = store.recall_episodes(
        MemoryQuery(query_text="divide", error_signature=err_sig, repo_identifier="calc_repo", include_superseded=True)
    )
    superseded_eps = [e for e in all_episodes if e.status == "superseded"]
    assert len(superseded_eps) == 1
    assert superseded_eps[0].episode_id == "ep_naive_fix"
    assert superseded_eps[0].superseded_by == "ep_superior_fix"

    # Standard recall must ONLY return the active superior fix, preventing outdated advice
    recalled_active = store.recall_episodes(
        MemoryQuery(query_text="divide", error_signature=err_sig, repo_identifier="calc_repo", include_superseded=False)
    )
    assert len(recalled_active) == 1
    assert recalled_active[0].episode_id == "ep_superior_fix"
    assert "ValueError" in recalled_active[0].remediation_strategy


def test_explicit_remediation_invalidation(temp_memory_engine):
    """Verify explicit invalidation marks an outdated strategy when an API changes or fails."""
    store = temp_memory_engine.episodic_store
    err_sig = "jwt.exceptions.DecodeError: Invalid signature"

    ep = Episode(
        episode_id="ep_jwt_v1",
        timestamp="2026-11-01T10:00:00Z",
        thread_id="th_jwt",
        repo_identifier="auth_service",
        task_description="Verify JWT signature with legacy secret parameter",
        task_type="bug_fix",
        error_signatures=[err_sig],
        remediation_strategy="Pass secret parameter directly to jwt.decode()",
        files_modified=["auth.py"],
        test_passed=True,
        review_score=8.5,
        outcome="success",
    )
    store.record_episode(ep)

    # Invalidate when PyJWT v2 deprecated parameter
    invalidated_count = store.invalidate_remediation(
        error_signature=err_sig,
        reason="PyJWT v2 removed secret parameter in favor of key parameter",
    )
    assert invalidated_count == 1

    # Standard recall ignores invalidated episodes
    active = store.recall_episodes(MemoryQuery(query_text="JWT signature", error_signature=err_sig, repo_identifier="auth_service"))
    assert len(active) == 0


def test_failed_strategies_retained_as_anti_patterns(temp_memory_engine):
    """Verify failed strategies are retained with post-mortem metadata to prevent repetition."""
    engine = temp_memory_engine

    failed_state = {
        "task": "Sanitize user HTML comments",
        "thread_id": "thread-fail-001",
        "repo_path": "/workspaces/web_app",
        "iteration_count": 3,
        "test_results": type("TestRes", (), {
            "passed": False,
            "exit_code": 1,
            "error_summary": "RecursionError: maximum recursion depth exceeded in regex parser",
        })(),
        "review_result": type("RevRes", (), {"approved": False, "quality_score": 3.0})(),
        "debug_result": type("DbgRes", (), {
            "remediation_plan": "Use recursive regex substitution pattern r'<(.*)>'",
        })(),
        "coder_result": type("CodeRes", (), {"files_modified": ["sanitize.py"]})(),
    }

    # Record failed state
    episode = engine.record_episode_from_state(failed_state)
    assert episode is not None
    assert episode.test_passed is False
    assert episode.outcome == "failed"
    assert episode.is_anti_pattern is True
    assert "RecursionError" in episode.failure_reason

    # Query recall: Guidance must include explicit Anti-Pattern Warning
    context = engine.recall_context_for_task(
        task="Sanitize user HTML comments with regex",
        repo_identifier="web_app",
        include_anti_patterns=True,
    )
    assert len(context["recalled_anti_patterns"]) >= 1
    assert "Anti-Patterns & Failed Strategies" in context["guidance_summary"]
    assert "DO NOT REPEAT" in context["guidance_summary"]
    assert "RecursionError" in context["guidance_summary"]


def test_repository_namespace_isolation(temp_memory_engine):
    """Verify repository-specific facts do NOT leak into different repositories."""
    store = temp_memory_engine.episodic_store

    # Repository A fact: specific internal path and custom database mock
    ep_repo_a = Episode(
        episode_id="ep_repo_a",
        timestamp="2026-11-01T10:00:00Z",
        thread_id="th_a",
        repo_identifier="fintech_backend",
        task_description="Mock database connection in internal_ledger_test",
        task_type="bug_fix",
        error_signatures=["InternalLedgerConnectionError: port 9092 unreachable"],
        remediation_strategy="Patch fintech.ledger.driver.MockFintechSocket on port 9092",
        files_modified=["internal/ledger.py"],
        test_passed=True,
        review_score=9.5,
        outcome="success",
        scope="repository",  # Strictly repository-scoped!
    )
    store.record_episode(ep_repo_a)

    # Repository B queries for database connection error
    query_repo_b = MemoryQuery(
        query_text="Mock database connection for ledger tests",
        repo_identifier="healthcare_portal",  # Different repository!
        strict_repo_scoping=True,
    )
    recalled_b = store.recall_episodes(query_repo_b)

    # Assert fintech_backend facts were strictly filtered out!
    assert len(recalled_b) == 0, "Repository-scoped memory must NOT leak into an unrelated repository!"


def test_promotion_of_validated_episode_to_semantic_memory(temp_memory_engine):
    """Verify validated episodic fixes can be promoted to global semantic patterns."""
    engine = temp_memory_engine

    # Step 1: Record successful, validated episode
    ep = Episode(
        episode_id="ep_val_guard",
        timestamp="2026-11-05T10:00:00Z",
        thread_id="th_promo",
        repo_identifier="math_service",
        task_description="Validate non-negative integers for factorial calculation",
        task_type="feature",
        error_signatures=["ValueError: math domain error"],
        remediation_strategy="Check if n < 0 and raise ValueError('Factorial is not defined for negative values')",
        files_modified=["math_ops.py"],
        test_passed=True,
        review_score=9.9,
        outcome="success",
        validation_count=3,
    )
    engine.episodic_store.record_episode(ep)

    # Step 2: Promote episode to global semantic memory
    pattern = engine.promote_validated_episode(
        episode_id=ep.episode_id,
        topic="domain_bounds_validation",
        title="Negative Factorial Domain Guard",
        content="Functions calculating factorial must raise ValueError with descriptive text when input n < 0.",
        tags=["factorial", "math", "validation", "negative_check", "valueerror"],
    )
    assert pattern is not None
    assert pattern.scope == "global"
    assert pattern.origin_episodes == [ep.episode_id]

    # Step 3: Now any unrelated repository querying math validation retrieves this promoted pattern!
    recalled_patterns = engine.semantic_store.recall_patterns(
        query="negative factorial validation check",
        repo_identifier="unrelated_game_engine",
    )
    assert len(recalled_patterns) >= 1
    assert any("Factorial Domain Guard" in p.title for p in recalled_patterns)


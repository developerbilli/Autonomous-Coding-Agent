"""Tests for Scoped Semantic Memory: Cross-Repository Validation, Ecosystem & Framework Isolation."""

import tempfile
from pathlib import Path
import pytest

from agent.memory.models import Episode, SemanticPattern, MemoryQuery
from agent.memory.semantic_memory import SemanticMemoryStore
from agent.memory.engine import MemoryEngine


@pytest.fixture
def temp_memory_engine():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_scoped_memory.sqlite"
        engine = MemoryEngine(str(db_path))
        yield engine


def test_ecosystem_conflict_isolation_postgres_vs_mongodb(temp_memory_engine):
    """Verify technology-specific patterns (e.g. PostgreSQL) are never recalled in conflicting ecosystems (e.g. MongoDB)."""
    engine = temp_memory_engine

    # Store PostgreSQL-specific connection retry pattern
    pg_pattern = SemanticPattern(
        pattern_id="pat_pg_pool_retry",
        pattern_type="architecture",
        repo_identifier="postgres_service",
        topic="database_connection",
        title="PostgreSQL Psycopg2 Connection Pool Retry",
        content="Catch psycopg2.OperationalError and psycopg2.pool.PoolError with exponential backoff on connection checkout.",
        tags=["database", "connection", "retry", "pool", "postgresql"],
        confidence=0.95,
        ecosystem="postgresql",
        scope="ecosystem",
    )
    engine.semantic_store.store_pattern(pg_pattern)

    # Store MongoDB-specific connection pattern
    mongo_pattern = SemanticPattern(
        pattern_id="pat_mongo_client_retry",
        pattern_type="architecture",
        repo_identifier="mongo_service",
        topic="database_connection",
        title="MongoDB PyMongo ServerSelectionTimeout Retry",
        content="Catch pymongo.errors.ServerSelectionTimeoutError and PyMongoAutoReconnect with retryWrites enabled.",
        tags=["database", "connection", "retry", "timeout", "mongodb"],
        confidence=0.95,
        ecosystem="mongodb",
        scope="ecosystem",
    )
    engine.semantic_store.store_pattern(mongo_pattern)

    # Query 1: Task targeting MongoDB connection retry
    mongo_recalled = engine.semantic_store.recall_patterns(
        query="database connection pool retry timeout",
        ecosystem="mongodb",
    )
    assert len(mongo_recalled) == 1
    assert mongo_recalled[0].pattern_id == "pat_mongo_client_retry"
    # Ensure PostgreSQL pattern is strictly gated out
    assert not any(p.pattern_id == "pat_pg_pool_retry" for p in mongo_recalled)

    # Query 2: Task targeting PostgreSQL connection retry
    pg_recalled = engine.semantic_store.recall_patterns(
        query="database connection pool retry timeout",
        ecosystem="postgresql",
    )
    assert len(pg_recalled) == 1
    assert pg_recalled[0].pattern_id == "pat_pg_pool_retry"
    # Ensure MongoDB pattern is strictly gated out
    assert not any(p.pattern_id == "pat_mongo_client_retry" for p in pg_recalled)

    # Query 3: Auto-detection through MemoryEngine via task string
    engine_mongo = engine.recall_context_for_task(
        task="Fix MongoDB connection pool timeouts during high load",
    )
    recalled_pat_ids = [p["pattern_id"] for p in engine_mongo["recalled_patterns"]]
    assert "pat_mongo_client_retry" in recalled_pat_ids
    assert "pat_pg_pool_retry" not in recalled_pat_ids


def test_framework_isolation_django_vs_fastapi(temp_memory_engine):
    """Verify framework-specific patterns (e.g. Django) are not injected into conflicting frameworks (e.g. FastAPI)."""
    engine = temp_memory_engine

    django_pat = SemanticPattern(
        pattern_id="pat_django_orm_transaction",
        pattern_type="convention",
        repo_identifier="django_app",
        topic="orm_transactions",
        title="Django Atomic Transactions with select_for_update",
        content="Wrap database writes in transaction.atomic() and use queryset.select_for_update() to prevent race conditions.",
        tags=["django", "orm", "transaction", "atomic"],
        confidence=0.95,
        framework="django",
        scope="ecosystem",
    )
    engine.semantic_store.store_pattern(django_pat)

    # Query from a FastAPI repo
    fastapi_recalled = engine.semantic_store.recall_patterns(
        query="database atomic transaction race condition",
        framework="fastapi",
    )
    assert not any(p.pattern_id == "pat_django_orm_transaction" for p in fastapi_recalled)

    # Query from a Django repo
    django_recalled = engine.semantic_store.recall_patterns(
        query="database atomic transaction race condition",
        framework="django",
    )
    assert len(django_recalled) >= 1
    assert django_recalled[0].pattern_id == "pat_django_orm_transaction"


def test_cross_repository_validation_promotes_to_global(temp_memory_engine):
    """Verify that a generic pattern starts scoped to its repository and only promotes to global after cross-repo validation."""
    engine = temp_memory_engine

    # Step 1: Promote episode initially scoped to originating repository
    ep = Episode(
        episode_id="ep_safe_div",
        timestamp="2026-11-06T10:00:00Z",
        thread_id="th_1",
        repo_identifier="repo_alpha",
        task_description="Implement safe division checking denominator with ValueError",
        task_type="bug_fix",
        error_signatures=["ZeroDivisionError: division by zero"],
        remediation_strategy="Guard with if denominator == 0 raise ValueError",
        files_modified=["math.py"],
        test_passed=True,
        review_score=9.8,
        outcome="success",
    )
    engine.episodic_store.record_episode(ep)

    # Initially promote with scope="repository"
    pattern = engine.promote_validated_episode(
        episode_id=ep.episode_id,
        topic="defensive_arithmetic",
        title="Safe Denominator Zero Check",
        content="Always check denominator != 0 before modulo or division and raise ValueError.",
        tags=["math", "division", "zero", "valueerror"],
        scope="repository",
    )
    assert pattern.scope == "repository"
    assert pattern.origin_repos == ["repo_alpha"]

    # At this point, another repository cannot see this repository-scoped pattern
    recalled_beta = engine.semantic_store.recall_patterns(
        query="division by zero check",
        repo_identifier="repo_beta",
    )
    assert not any(p.pattern_id == pattern.pattern_id for p in recalled_beta)

    # Step 2: Pattern is reused successfully in repo_beta
    updated = engine.semantic_store.record_reuse(
        pattern_id=pattern.pattern_id,
        success=True,
        repo_identifier="repo_beta",
        evidence="unit_tests_passed",
    )

    # Step 3: Now that cross-repo validation is satisfied (2 distinct repos, successes >= 2, no failures),
    # verify it graduated to scope="global"
    assert updated.scope == "global"
    assert set(updated.origin_repos) == {"repo_alpha", "repo_beta"}
    assert any("promoted_to_global:cross_repo_verified:2_repos" in ev for ev in updated.validation_evidence)

    # Step 4: Now any third unrelated repository (repo_gamma) can recall this verified global pattern!
    recalled_gamma = engine.semantic_store.recall_patterns(
        query="division by zero check",
        repo_identifier="repo_gamma",
    )
    assert any(p.pattern_id == pattern.pattern_id for p in recalled_gamma)


def test_technology_specific_pattern_promotes_to_ecosystem_not_global(temp_memory_engine):
    """Verify that a technology-specific pattern (PostgreSQL) graduates to 'ecosystem' scope, NEVER global."""
    engine = temp_memory_engine

    pg_ep = Episode(
        episode_id="ep_pg_conn",
        timestamp="2026-11-06T11:00:00Z",
        thread_id="th_pg",
        repo_identifier="service_pg_one",
        task_description="Fix PostgreSQL connection pooling leak",
        task_type="bug_fix",
        error_signatures=["psycopg2.OperationalError: server closed the connection"],
        remediation_strategy="Always release connection in finally block using pool.putconn()",
        files_modified=["db.py"],
        test_passed=True,
        review_score=9.9,
        outcome="success",
    )
    engine.episodic_store.record_episode(pg_ep)

    # Promote with ecosystem="postgresql"
    pat = engine.promote_validated_episode(
        episode_id=pg_ep.episode_id,
        topic="postgres_pooling",
        title="PostgreSQL Pool Connection Release Guard",
        content="Always put connection back to pool in finally: pool.putconn(conn).",
        tags=["postgres", "psycopg2", "pool", "leak"],
        ecosystem="postgresql",
        scope="repository",
    )
    assert pat.scope == "repository"
    assert pat.ecosystem == "postgresql"

    # Reused successfully in a second PostgreSQL service
    graduated = engine.semantic_store.record_reuse(
        pattern_id=pat.pattern_id,
        success=True,
        repo_identifier="service_pg_two",
        evidence="unit_tests_passed",
    )

    # Must graduate to 'ecosystem' scope, NOT 'global'!
    assert graduated.scope == "ecosystem"
    assert graduated.ecosystem == "postgresql"
    assert any("promoted_to_ecosystem:cross_repo_verified:2_repos" in ev for ev in graduated.validation_evidence)

    # Verify that a MongoDB project still NEVER sees this PostgreSQL pattern
    mongo_search = engine.semantic_store.recall_patterns(
        query="connection pool leak release",
        repo_identifier="service_mongo",
        ecosystem="mongodb",
    )
    assert not any(p.pattern_id == pat.pattern_id for p in mongo_search)

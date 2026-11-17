"""Episodic Memory Store backed by SQLite with WAL Mode.

Stores and retrieves historical task episodes, error signatures,
successful remediation strategies, and reviewer outcomes across sessions.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Set

from agent.memory.models import Episode, MemoryQuery


class EpisodicMemoryStore:
    """Persistent storage and retrieval of past agent workflows and remediation episodes."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    episode_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    repo_identifier TEXT NOT NULL,
                    task_description TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    error_signatures TEXT NOT NULL,
                    remediation_strategy TEXT,
                    files_modified TEXT NOT NULL,
                    test_passed INTEGER NOT NULL,
                    review_score REAL NOT NULL,
                    outcome TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    scope TEXT NOT NULL DEFAULT 'repository',
                    superseded_by TEXT,
                    is_anti_pattern INTEGER NOT NULL DEFAULT 0,
                    failure_reason TEXT,
                    validation_count INTEGER NOT NULL DEFAULT 1,
                    promoted_to_pattern_id TEXT,
                    metadata TEXT NOT NULL
                );
            """)
            # Migration check for existing databases
            existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(episodes);").fetchall()}
            for col, col_type, default_val in [
                ("status", "TEXT NOT NULL", "'active'"),
                ("scope", "TEXT NOT NULL", "'repository'"),
                ("superseded_by", "TEXT", "NULL"),
                ("is_anti_pattern", "INTEGER NOT NULL", "0"),
                ("failure_reason", "TEXT", "NULL"),
                ("validation_count", "INTEGER NOT NULL", "1"),
                ("promoted_to_pattern_id", "TEXT", "NULL"),
            ]:
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE episodes ADD COLUMN {col} {col_type} DEFAULT {default_val};")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_repo ON episodes (repo_identifier);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outcome ON episodes (outcome);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON episodes (status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scope ON episodes (scope);")
            conn.commit()

    def record_episode(self, episode: Episode) -> None:
        """Persists a new episode to episodic memory with automated supersession and anti-pattern tracking."""
        with self._get_connection() as conn:
            # 1. Automated Supersession: If this is a successful fix, supersede older lower-scoring fixes
            # for the same error signature within this repository/scope.
            if episode.test_passed and episode.remediation_strategy and episode.error_signatures:
                for sig in episode.error_signatures:
                    older_rows = conn.execute(
                        """
                        SELECT episode_id, review_score, error_signatures FROM episodes
                        WHERE status = 'active' AND episode_id != ? AND repo_identifier = ?
                        """,
                        (episode.episode_id, episode.repo_identifier),
                    ).fetchall()
                    for row in older_rows:
                        try:
                            sigs = json.loads(row["error_signatures"])
                        except Exception:
                            sigs = []
                        if sig in sigs and episode.review_score >= float(row["review_score"]):
                            conn.execute(
                                "UPDATE episodes SET status = 'superseded', superseded_by = ? WHERE episode_id = ?;",
                                (episode.episode_id, row["episode_id"]),
                            )

            # 2. Persist episode record
            conn.execute(
                """
                INSERT OR REPLACE INTO episodes (
                    episode_id, timestamp, thread_id, repo_identifier,
                    task_description, task_type, error_signatures,
                    remediation_strategy, files_modified, test_passed,
                    review_score, outcome, status, scope, superseded_by,
                    is_anti_pattern, failure_reason, validation_count,
                    promoted_to_pattern_id, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    episode.episode_id,
                    episode.timestamp,
                    episode.thread_id,
                    episode.repo_identifier,
                    episode.task_description,
                    episode.task_type,
                    json.dumps(episode.error_signatures),
                    episode.remediation_strategy,
                    json.dumps(episode.files_modified),
                    1 if episode.test_passed else 0,
                    episode.review_score,
                    episode.outcome,
                    episode.status,
                    episode.scope,
                    episode.superseded_by,
                    1 if (episode.is_anti_pattern or not episode.test_passed) else 0,
                    episode.failure_reason,
                    episode.validation_count,
                    episode.promoted_to_pattern_id,
                    json.dumps(episode.metadata),
                ),
            )
            conn.commit()

    def invalidate_remediation(self, error_signature: str, reason: str, repo_identifier: Optional[str] = None) -> int:
        """Explicitly invalidates an outdated remediation strategy (e.g. after API deprecation or test failure)."""
        count = 0
        with self._get_connection() as conn:
            query = "SELECT episode_id, error_signatures FROM episodes WHERE status = 'active';"
            rows = conn.execute(query).fetchall()
            for r in rows:
                try:
                    sigs = json.loads(r["error_signatures"])
                except Exception:
                    sigs = []
                if error_signature in sigs:
                    conn.execute(
                        "UPDATE episodes SET status = 'invalidated', failure_reason = ? WHERE episode_id = ?;",
                        (reason, r["episode_id"]),
                    )
                    count += 1
            conn.commit()
        return count

    def _row_to_episode(self, row: sqlite3.Row) -> Episode:
        return Episode(
            episode_id=row["episode_id"],
            timestamp=row["timestamp"],
            thread_id=row["thread_id"],
            repo_identifier=row["repo_identifier"],
            task_description=row["task_description"],
            task_type=row["task_type"],
            error_signatures=json.loads(row["error_signatures"]),
            remediation_strategy=row["remediation_strategy"],
            files_modified=json.loads(row["files_modified"]),
            test_passed=bool(row["test_passed"]),
            review_score=float(row["review_score"]),
            outcome=row["outcome"],
            status=row["status"] if "status" in row.keys() else "active",
            scope=row["scope"] if "scope" in row.keys() else "repository",
            superseded_by=row["superseded_by"] if "superseded_by" in row.keys() else None,
            is_anti_pattern=bool(row["is_anti_pattern"]) if "is_anti_pattern" in row.keys() else False,
            failure_reason=row["failure_reason"] if "failure_reason" in row.keys() else None,
            validation_count=int(row["validation_count"]) if "validation_count" in row.keys() else 1,
            promoted_to_pattern_id=row["promoted_to_pattern_id"] if "promoted_to_pattern_id" in row.keys() else None,
            metadata=json.loads(row["metadata"]),
        )

    def recall_episodes(self, query: MemoryQuery) -> List[Episode]:
        """Recalls the most relevant past active episodes respecting repository scoping and retention status."""
        status_filter = "" if query.include_superseded else "AND status = 'active'"
        sql = f"SELECT * FROM episodes WHERE test_passed = 1 {status_filter} ORDER BY timestamp DESC LIMIT 50;"

        with self._get_connection() as conn:
            rows = conn.execute(sql).fetchall()

        if not rows:
            return []

        query_tokens = self._tokenize(query.query_text)
        error_tokens = self._tokenize(query.error_signature) if query.error_signature else set()

        scored_episodes: List[tuple[float, Episode]] = []

        for row in rows:
            ep = self._row_to_episode(row)

            # Strict Repository Scoping:
            # Repository-specific facts (scope == 'repository') MUST NOT leak into other repositories!
            if query.strict_repo_scoping and query.repo_identifier:
                if ep.scope == "repository" and query.repo_identifier not in ep.repo_identifier:
                    continue  # Strict namespace isolation

            # Calculate relevance score
            score = 0.0
            ep_task_tokens = self._tokenize(ep.task_description)
            task_overlap = len(query_tokens.intersection(ep_task_tokens))
            score += task_overlap * 1.5

            if error_tokens and ep.error_signatures:
                for sig in ep.error_signatures:
                    sig_tokens = self._tokenize(sig)
                    err_overlap = len(error_tokens.intersection(sig_tokens))
                    if err_overlap > 0:
                        score += err_overlap * 4.0  # High weight on error signature matches

            if query.repo_identifier and query.repo_identifier in ep.repo_identifier:
                score += 2.0

            # Weight by review score and validation count
            score *= (0.5 + 0.5 * ep.review_score)
            if ep.validation_count > 1:
                score *= (1.0 + 0.1 * min(ep.validation_count, 5))

            if score > 0.5:
                scored_episodes.append((score, ep))

        scored_episodes.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored_episodes[: query.limit]]

    def recall_anti_patterns(self, query: MemoryQuery) -> List[Episode]:
        """Recalls relevant failed strategies and anti-patterns to warn the agent against repeating them."""
        sql = "SELECT * FROM episodes WHERE (is_anti_pattern = 1 OR test_passed = 0) ORDER BY timestamp DESC LIMIT 25;"
        with self._get_connection() as conn:
            rows = conn.execute(sql).fetchall()

        if not rows:
            return []

        query_tokens = self._tokenize(query.query_text)
        error_tokens = self._tokenize(query.error_signature) if query.error_signature else set()

        scored: List[tuple[float, Episode]] = []
        for row in rows:
            ep = self._row_to_episode(row)
            if query.strict_repo_scoping and query.repo_identifier:
                if ep.scope == "repository" and query.repo_identifier not in ep.repo_identifier:
                    continue

            score = 0.0
            task_overlap = len(query_tokens.intersection(self._tokenize(ep.task_description)))
            score += task_overlap * 1.5

            if error_tokens and ep.error_signatures:
                for sig in ep.error_signatures:
                    err_overlap = len(error_tokens.intersection(self._tokenize(sig)))
                    if err_overlap > 0:
                        score += err_overlap * 4.0

            if score > 0.5:
                scored.append((score, ep))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[: query.limit]]

    def get_recent_episodes(self, limit: int = 10) -> List[Episode]:
        """Fetches the most recent episodes chronologically."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM episodes ORDER BY timestamp DESC LIMIT ?;", (limit,)).fetchall()

        return [
            Episode(
                episode_id=row["episode_id"],
                timestamp=row["timestamp"],
                thread_id=row["thread_id"],
                repo_identifier=row["repo_identifier"],
                task_description=row["task_description"],
                task_type=row["task_type"],
                error_signatures=json.loads(row["error_signatures"]),
                remediation_strategy=row["remediation_strategy"],
                files_modified=json.loads(row["files_modified"]),
                test_passed=bool(row["test_passed"]),
                review_score=float(row["review_score"]),
                outcome=row["outcome"],
                metadata=json.loads(row["metadata"]),
            )
            for row in rows
        ]

    def _tokenize(self, text: Optional[str]) -> Set[str]:
        if not text:
            return set()
        import re
        words = re.findall(r"[A-Za-z0-9_]{3,}", text.lower())
        stopwords = {"the", "and", "for", "with", "from", "into", "that", "this", "test", "tests"}
        return set(w for w in words if w not in stopwords)


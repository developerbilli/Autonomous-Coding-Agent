"""Semantic Memory Store backed by SQLite.

Stores and retrieves reusable coding rules, architectural patterns,
testing templates, and conventions across projects and repositories.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Set

from agent.memory.models import SemanticPattern


class SemanticMemoryStore:
    """Persistent storage and retrieval of cross-project architectural knowledge."""

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
                CREATE TABLE IF NOT EXISTS semantic_patterns (
                    pattern_id TEXT PRIMARY KEY,
                    pattern TEXT NOT NULL DEFAULT '',
                    pattern_type TEXT NOT NULL,
                    repo_identifier TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    successful_reuses INTEGER NOT NULL DEFAULT 0,
                    failed_reuses INTEGER NOT NULL DEFAULT 0,
                    language TEXT NOT NULL DEFAULT 'python',
                    validation_evidence TEXT NOT NULL DEFAULT '[]',
                    last_verified TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    scope TEXT NOT NULL DEFAULT 'global',
                    origin_episodes TEXT NOT NULL DEFAULT '[]',
                    validation_count INTEGER NOT NULL DEFAULT 1,
                    last_validated_at TEXT
                );
            """)
            # Migration check for existing databases
            existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(semantic_patterns);").fetchall()}
            for col, col_type, default_val in [
                ("pattern", "TEXT NOT NULL", "''"),
                ("successful_reuses", "INTEGER NOT NULL", "0"),
                ("failed_reuses", "INTEGER NOT NULL", "0"),
                ("language", "TEXT NOT NULL", "'python'"),
                ("validation_evidence", "TEXT NOT NULL", "'[]'"),
                ("last_verified", "TEXT", "NULL"),
                ("status", "TEXT NOT NULL", "'active'"),
                ("scope", "TEXT NOT NULL", "'global'"),
                ("origin_episodes", "TEXT NOT NULL", "'[]'"),
                ("validation_count", "INTEGER NOT NULL", "1"),
                ("last_validated_at", "TEXT", "NULL"),
            ]:
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE semantic_patterns ADD COLUMN {col} {col_type} DEFAULT {default_val};")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_pattern_topic ON semantic_patterns (topic);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pattern_repo ON semantic_patterns (repo_identifier);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pattern_status ON semantic_patterns (status);")
            conn.commit()

        # Seed standard engineering best practices if table is empty
        self.seed_default_patterns()

    def store_pattern(self, pattern: SemanticPattern) -> None:
        """Stores or updates an architectural or semantic pattern."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO semantic_patterns (
                    pattern_id, pattern, pattern_type, repo_identifier,
                    topic, title, content, tags, confidence,
                    successful_reuses, failed_reuses, language,
                    validation_evidence, last_verified, status, scope,
                    origin_episodes, validation_count, last_validated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    pattern.pattern_id,
                    pattern.pattern or pattern.title,
                    pattern.pattern_type,
                    pattern.repo_identifier,
                    pattern.topic,
                    pattern.title or pattern.pattern,
                    pattern.content,
                    json.dumps(pattern.tags),
                    pattern.confidence,
                    pattern.successful_reuses,
                    pattern.failed_reuses,
                    pattern.language,
                    json.dumps(pattern.validation_evidence),
                    pattern.last_verified,
                    pattern.status,
                    pattern.scope,
                    json.dumps(pattern.origin_episodes),
                    pattern.validation_count,
                    pattern.last_validated_at,
                ),
            )
            conn.commit()

    def record_reuse(
        self,
        pattern_id: str,
        success: bool,
        evidence: Optional[str] = None,
    ) -> Optional[SemanticPattern]:
        """Records downstream reuse outcome, updating empirical confidence and validation evidence."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM semantic_patterns WHERE pattern_id = ?;", (pattern_id,)).fetchone()
            if not row:
                return None

            pat = self._row_to_pattern(row)
            if success:
                pat.successful_reuses += 1
                if evidence and evidence not in pat.validation_evidence:
                    pat.validation_evidence.append(evidence)
            else:
                pat.failed_reuses += 1
                if evidence:
                    pat.validation_evidence.append(f"FAILED:{evidence}")

            # Bayesian posterior confidence calculation:
            # Prior: Alpha=3.0, Beta=1.0 (calibrated baseline prior = 0.75 for candidate patterns)
            # Reuses update distribution: successes increment alpha; failures heavily penalize beta.
            alpha = 3.0 + pat.successful_reuses
            beta = 1.0 + (pat.failed_reuses * 2.5)
            base_confidence = alpha / (alpha + beta)

            # Empirical Evidence Depth factor: verified receipts (unit_tests_passed, regression_test_passed)
            # boost confidence towards asymptote 0.99.
            valid_evidence_count = len([e for e in pat.validation_evidence if not str(e).startswith("FAILED:")])
            evidence_bonus = 0.0375 * min(valid_evidence_count, 4)
            pat.confidence = round(min(0.99, max(0.10, base_confidence + evidence_bonus)), 2)

            # Auto-deprecation if repeatedly failing
            if pat.failed_reuses >= 3 and pat.confidence < 0.45:
                pat.status = "deprecated"

            pat.last_verified = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            pat.last_validated_at = pat.last_verified
            self.store_pattern(pat)
            return pat

    def promote_from_episode(
        self,
        episode_id: str,
        title: str,
        content: str,
        topic: str,
        tags: List[str],
        confidence: float = 0.85,
        scope: str = "global",
        language: str = "python",
        validation_evidence: Optional[List[str]] = None,
    ) -> SemanticPattern:
        """Promotes a verified episodic remediation into semantic memory with empirical evidence."""
        pattern_id = f"pat_promoted_{topic[:12]}_{episode_id[-8:]}"
        evidence = validation_evidence or ["unit_tests_passed", "reviewer_score_verified"]
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        pattern = SemanticPattern(
            pattern_id=pattern_id,
            pattern=title,
            pattern_type="convention",
            repo_identifier="global" if scope == "global" else "promoted",
            topic=topic,
            title=title,
            content=content,
            tags=tags,
            confidence=confidence,
            successful_reuses=1,
            failed_reuses=0,
            language=language,
            validation_evidence=evidence,
            last_verified=now_str,
            status="active",
            scope=scope,
            origin_episodes=[episode_id],
            validation_count=2,
            last_validated_at=now_str,
        )
        self.store_pattern(pattern)
        return pattern

    def _row_to_pattern(self, row: sqlite3.Row) -> SemanticPattern:
        keys = row.keys()
        return SemanticPattern(
            pattern_id=row["pattern_id"],
            pattern=row["pattern"] if "pattern" in keys else (row["title"] if "title" in keys else ""),
            pattern_type=row["pattern_type"],
            repo_identifier=row["repo_identifier"],
            topic=row["topic"],
            title=row["title"],
            content=row["content"],
            tags=json.loads(row["tags"]),
            confidence=float(row["confidence"]),
            successful_reuses=int(row["successful_reuses"]) if "successful_reuses" in keys else 0,
            failed_reuses=int(row["failed_reuses"]) if "failed_reuses" in keys else 0,
            language=row["language"] if "language" in keys else "python",
            validation_evidence=json.loads(row["validation_evidence"]) if "validation_evidence" in keys else [],
            last_verified=row["last_verified"] if "last_verified" in keys else None,
            status=row["status"] if "status" in keys else "active",
            scope=row["scope"] if "scope" in keys else "global",
            origin_episodes=json.loads(row["origin_episodes"]) if "origin_episodes" in keys else [],
            validation_count=int(row["validation_count"]) if "validation_count" in keys else 1,
            last_validated_at=row["last_validated_at"] if "last_validated_at" in keys else None,
        )

    def recall_patterns(
        self, query: str, repo_identifier: Optional[str] = None, limit: int = 5
    ) -> List[SemanticPattern]:
        """Recalls relevant patterns ranked by relevance, empirical confidence, and reuse evidence."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM semantic_patterns WHERE status = 'active';").fetchall()

        if not rows:
            return []

        query_tokens = self._tokenize(query)
        scored: List[tuple[float, SemanticPattern]] = []

        for row in rows:
            pat = self._row_to_pattern(row)

            score = 0.0
            # Tag match bonus
            for tag in pat.tags:
                if tag.lower() in query.lower():
                    score += 3.0

            # Title & topic match
            title_tokens = self._tokenize(pat.title + " " + pat.topic + " " + pat.pattern)
            score += len(query_tokens.intersection(title_tokens)) * 2.0

            # Content match
            content_tokens = self._tokenize(pat.content)
            score += len(query_tokens.intersection(content_tokens)) * 0.5

            # Scope bonus
            if repo_identifier and pat.repo_identifier in (repo_identifier, "global"):
                score += 1.0

            # Empirical Confidence & Evidence Depth Weighting:
            # Distinguishes proven reusable patterns from one-time successful patches!
            score *= pat.confidence

            # Boost proven reusable patterns with successful downstream reuses
            if pat.successful_reuses > 0:
                score *= (1.0 + 0.20 * min(pat.successful_reuses, 5))

            # Bonus for strong regression testing evidence
            if "regression_test_passed" in pat.validation_evidence:
                score *= 1.25

            # Penalize patterns with regressions or failed reuses
            if pat.failed_reuses > 0:
                score *= max(0.1, 1.0 - (0.25 * pat.failed_reuses))

            if score > 0.5:
                scored.append((score, pat))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:limit]]

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:limit]]

    def seed_default_patterns(self) -> None:
        """Seeds common software engineering and repository patterns."""
        with self._get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) as c FROM semantic_patterns;").fetchone()["c"]
            if count > 0:
                return

        defaults = [
            SemanticPattern(
                pattern_id="pat_val_guards",
                pattern_type="convention",
                repo_identifier="global",
                topic="input_validation",
                title="Defensive Boundary Checking with ValueError",
                content="Functions accepting numeric or bounded inputs (length, count, index) must validate arguments early and raise ValueError with clear descriptive messages on out-of-range or negative inputs.",
                tags=["validation", "valueerror", "guard", "bounds", "inputs", "security"],
                confidence=1.0,
            ),
            SemanticPattern(
                pattern_id="pat_pytest_clean",
                pattern_type="test_template",
                repo_identifier="global",
                topic="pytest_structure",
                title="Isolated Boundary Testing with Pytest",
                content="Tests should use pytest.raises() for boundary guard assertions, test empty and negative inputs, and avoid shared mutable state between test functions.",
                tags=["pytest", "unit_test", "boundary", "fixtures", "raises"],
                confidence=1.0,
            ),
            SemanticPattern(
                pattern_id="pat_password_generator",
                pattern_type="convention",
                repo_identifier="global",
                topic="cryptography",
                title="Modular Password Generator & Entropy Evaluation",
                content="generate_password(length, include_symbols, include_numbers) should require length >= 4, use secrets.choice for cryptographic randomness, and calculate_strength(password) returns a dict with score, entropy, and complexity assessment.",
                tags=["password", "generator", "strength", "crypto", "entropy", "random"],
                confidence=1.0,
            ),
            SemanticPattern(
                pattern_id="pat_sse_streaming",
                pattern_type="architecture",
                repo_identifier="global",
                topic="api_telemetry",
                title="FastAPI Server-Sent Events (SSE) Streaming",
                content="Real-time telemetry endpoints must stream data: {json}\\n\\n formatted payloads with non-blocking event-loop yields (asyncio.sleep) and proper Cache-Control: no-cache headers.",
                tags=["fastapi", "sse", "streaming", "events", "telemetry"],
                confidence=1.0,
            ),
        ]

        for p in defaults:
            self.store_pattern(p)

    def _tokenize(self, text: str) -> Set[str]:
        import re
        words = re.findall(r"[A-Za-z0-9_]{3,}", text.lower())
        stopwords = {"the", "and", "for", "with", "from", "into", "that", "this"}
        return set(w for w in words if w not in stopwords)


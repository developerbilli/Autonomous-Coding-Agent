"""Semantic Memory Store backed by SQLite.

Stores and retrieves reusable coding rules, architectural patterns,
testing templates, and conventions across projects and repositories.
"""

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Set, Dict, Any, Union

from agent.memory.models import SemanticPattern, ValidationReceipt

logger = logging.getLogger("agent.memory.semantic_memory")


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
                    framework TEXT DEFAULT NULL,
                    ecosystem TEXT DEFAULT NULL,
                    constraints TEXT NOT NULL DEFAULT '{}',
                    validation_evidence TEXT NOT NULL DEFAULT '[]',
                    last_verified TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    security_status TEXT NOT NULL DEFAULT 'verified',
                    revocation_reason TEXT DEFAULT NULL,
                    security_violations TEXT NOT NULL DEFAULT '[]',
                    revoked_at TEXT DEFAULT NULL,
                    scope TEXT NOT NULL DEFAULT 'global',
                    origin_episodes TEXT NOT NULL DEFAULT '[]',
                    origin_repos TEXT NOT NULL DEFAULT '[]',
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
                ("framework", "TEXT", "NULL"),
                ("ecosystem", "TEXT", "NULL"),
                ("constraints", "TEXT NOT NULL", "'{}'"),
                ("validation_evidence", "TEXT NOT NULL", "'[]'"),
                ("last_verified", "TEXT", "NULL"),
                ("status", "TEXT NOT NULL", "'active'"),
                ("security_status", "TEXT NOT NULL", "'verified'"),
                ("revocation_reason", "TEXT", "NULL"),
                ("security_violations", "TEXT NOT NULL", "'[]'"),
                ("revoked_at", "TEXT", "NULL"),
                ("scope", "TEXT NOT NULL", "'global'"),
                ("origin_episodes", "TEXT NOT NULL", "'[]'"),
                ("origin_repos", "TEXT NOT NULL", "'[]'"),
                ("validation_count", "INTEGER NOT NULL", "1"),
                ("last_validated_at", "TEXT", "NULL"),
            ]:
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE semantic_patterns ADD COLUMN {col} {col_type} DEFAULT {default_val};")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_pattern_topic ON semantic_patterns (topic);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pattern_repo ON semantic_patterns (repo_identifier);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pattern_status ON semantic_patterns (status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pattern_ecosystem ON semantic_patterns (ecosystem);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pattern_scope ON semantic_patterns (scope);")
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
                    framework, ecosystem, constraints,
                    validation_evidence, last_verified, status,
                    security_status, revocation_reason, security_violations, revoked_at,
                    scope, origin_episodes, origin_repos, validation_count, last_validated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                    pattern.framework,
                    pattern.ecosystem,
                    json.dumps(pattern.constraints),
                    json.dumps(pattern.validation_evidence),
                    pattern.last_verified,
                    pattern.status,
                    pattern.security_status,
                    pattern.revocation_reason,
                    json.dumps(pattern.security_violations),
                    pattern.revoked_at,
                    pattern.scope,
                    json.dumps(pattern.origin_episodes),
                    json.dumps(pattern.origin_repos),
                    pattern.validation_count,
                    pattern.last_validated_at,
                ),
            )
            conn.commit()

    def record_reuse(
        self,
        pattern_id: str,
        success: bool,
        evidence: Optional[Union[str, ValidationReceipt, Dict[str, Any]]] = None,
        repo_identifier: Optional[str] = None,
        run_id: Optional[str] = None,
        test_suite_id: Optional[str] = None,
        environment: Optional[str] = None,
        score: float = 1.0,
    ) -> Optional[SemanticPattern]:
        """Records downstream reuse outcome, updating empirical confidence with independent validation deduplication."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM semantic_patterns WHERE pattern_id = ?;", (pattern_id,)).fetchone()
            if not row:
                return None

            pat = self._row_to_pattern(row)

            # ----------------------------------------------------
            # Security Validity Gate (Dimension 2):
            # A pattern quarantined or invalidated for security CANNOT record positive reuses or gain confidence!
            # ----------------------------------------------------
            if pat.security_status != "verified" or pat.status in ("invalidated", "quarantined"):
                logger.warning(
                    f"Pattern {pattern_id} is {pat.security_status}/{pat.status} (revoked for security). "
                    "Skipping reuse recording and confidence calculation."
                )
                return pat

            # Build or extract structured ValidationReceipt
            if isinstance(evidence, ValidationReceipt):
                receipt = evidence
            elif isinstance(evidence, dict) and "receipt_id" in evidence:
                receipt = ValidationReceipt(**evidence)
            else:
                # Fallback / explicit metadata receipt constructor
                r_id = run_id or f"run_{repo_identifier or 'default'}_{int(time.time() * 1000)}"
                repo_id = repo_identifier or "global"
                suite_id = test_suite_id or (str(evidence) if (evidence and not str(evidence).startswith("FAILED:")) else "default_test_suite")
                env_id = environment or "posix-sandbox"
                receipt = ValidationReceipt.create(
                    run_id=r_id,
                    repo_identifier=repo_id,
                    test_suite_id=suite_id,
                    environment=env_id,
                    outcome="passed" if success else "failed",
                    score=score,
                )

            # ----------------------------------------------------
            # Independence & Deduplication Gate:
            # Running the exact same test in the same run/env does NOT constitute new independent evidence!
            # ----------------------------------------------------
            existing_receipts = pat.parse_receipts()
            existing_receipt_ids = {r.receipt_id for r in existing_receipts}
            if receipt.receipt_id in existing_receipt_ids:
                # Redundant verification detected - do not count twice
                return pat

            # Append structured receipt to validation evidence
            pat.validation_evidence.append(receipt.model_dump())

            if success:
                pat.successful_reuses += 1
                if repo_identifier and repo_identifier not in pat.origin_repos:
                    pat.origin_repos.append(repo_identifier)
            else:
                pat.failed_reuses += 1

            # ----------------------------------------------------
            # Multi-Dimensional Independence Calculation:
            # Genuinely orthogonal validation requires distinct runs, test suites, and environments.
            # ----------------------------------------------------
            all_receipts = pat.parse_receipts()
            passed_receipts = [r for r in all_receipts if r.outcome == "passed"]
            distinct_runs = len({r.run_id for r in passed_receipts})
            distinct_suites = len({r.test_suite_id for r in passed_receipts})
            distinct_envs = len({r.environment for r in passed_receipts})
            distinct_repos = len(set(pat.origin_repos))

            # Update validation_count to reflect truly independent validation events
            pat.validation_count = max(1, len(passed_receipts))

            # ----------------------------------------------------
            # Bayesian-Inspired Confidence Calculation:
            # Modeled as the posterior mean of a fractional-weight Beta distribution Beta(alpha, beta).
            # Orthogonal evidence dimensions (distinct runs, test suites, environments, repos)
            # scale the effective sample size parameter (alpha), while regressions add an asymmetric
            # penalty to (beta). This keeps the score mathematically bounded in (0, 1) without
            # arbitrary additive scalar bonuses or post-hoc clamping.
            # ----------------------------------------------------
            alpha_0 = 3.0  # Calibrated prior success pseudo-counts
            beta_0 = 1.0   # Calibrated prior failure pseudo-counts

            # Effective sample size: orthogonal evidence vectors scale the statistical weight
            effective_success_weight = (
                pat.successful_reuses
                + 0.5 * min(max(0, distinct_runs - 1), 2)
                + 0.5 * min(max(0, distinct_suites - 1), 2)
                + 0.5 * min(max(0, distinct_envs - 1), 1)
                + 0.5 * min(max(0, distinct_repos - 1), 2)
            )
            alpha = alpha_0 + effective_success_weight
            beta = beta_0 + (pat.failed_reuses * 2.5)  # Asymmetric penalty for regressions

            # Posterior mean E[theta | D] = alpha / (alpha + beta)
            pat.confidence = round(alpha / (alpha + beta), 2)

            # Auto-deprecation if repeatedly failing
            if pat.failed_reuses >= 3 and pat.confidence < 0.45:
                pat.status = "deprecated"

            # ----------------------------------------------------
            # Cross-Repository & Multi-Run Gate for Global Promotion:
            # Requires AT LEAST 2 distinct repositories AND AT LEAST 2 independent execution runs!
            # ----------------------------------------------------
            if (distinct_repos >= 2 and distinct_runs >= 2
                and pat.failed_reuses == 0 and pat.confidence >= 0.85):
                if not pat.ecosystem and not pat.framework and pat.scope != "global":
                    pat.scope = "global"
                    pat.repo_identifier = "global"
                    receipt_str = f"promoted_to_global:cross_repo_verified:{distinct_repos}_repos:{distinct_runs}_runs"
                    if receipt_str not in pat.validation_evidence:
                        pat.validation_evidence.append(receipt_str)
                elif pat.scope == "repository" and (pat.ecosystem or pat.framework):
                    pat.scope = "ecosystem"
                    receipt_str = f"promoted_to_ecosystem:cross_repo_verified:{distinct_repos}_repos:{distinct_runs}_runs"
                    if receipt_str not in pat.validation_evidence:
                        pat.validation_evidence.append(receipt_str)

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
        scope: Optional[str] = None,
        language: str = "python",
        framework: Optional[str] = None,
        ecosystem: Optional[str] = None,
        constraints: Optional[Dict[str, Any]] = None,
        origin_repos: Optional[List[str]] = None,
        repo_identifier: Optional[str] = None,
        validation_evidence: Optional[List[str]] = None,
    ) -> SemanticPattern:
        """Promotes a verified episodic remediation into semantic memory with empirical evidence."""
        pattern_id = f"pat_promoted_{topic[:12]}_{episode_id[-8:]}"
        evidence = validation_evidence or ["unit_tests_passed", "reviewer_score_verified"]
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Determine effective scope:
        # If technology ecosystem or framework is specified, scope CANNOT be global!
        # It must be scoped to 'ecosystem' or 'repository' to avoid contaminating other ecosystems.
        effective_scope = scope
        if effective_scope is None:
            if ecosystem or framework:
                effective_scope = "ecosystem"
            else:
                effective_scope = "global"
        elif effective_scope == "global" and (ecosystem or framework):
            # Guardrail: Global promotion with ecosystem-specific constraints is capped at ecosystem
            effective_scope = "ecosystem"

        repos = origin_repos or ([repo_identifier] if repo_identifier else [])
        origin_repo_id = repo_identifier or (repos[0] if repos else "origin_repo")
        initial_receipt = ValidationReceipt.create(
            run_id=f"run_origin_{episode_id}",
            repo_identifier=origin_repo_id,
            test_suite_id=f"suite_origin_{topic}",
            environment="posix-sandbox",
            outcome="passed",
            score=1.0,
            timestamp=now_str,
        )
        evidence_list = list(evidence)
        evidence_list.append(initial_receipt.model_dump())

        pattern = SemanticPattern(
            pattern_id=pattern_id,
            pattern=title,
            pattern_type="convention",
            repo_identifier=repo_identifier or ("global" if effective_scope == "global" else "promoted"),
            topic=topic,
            title=title,
            content=content,
            tags=tags,
            confidence=confidence,
            successful_reuses=1,
            failed_reuses=0,
            language=language,
            framework=framework,
            ecosystem=ecosystem,
            constraints=constraints or {},
            validation_evidence=evidence_list,
            last_verified=now_str,
            status="active",
            scope=effective_scope,
            origin_episodes=[episode_id],
            origin_repos=repos,
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
            framework=row["framework"] if ("framework" in keys and row["framework"]) else None,
            ecosystem=row["ecosystem"] if ("ecosystem" in keys and row["ecosystem"]) else None,
            constraints=json.loads(row["constraints"]) if ("constraints" in keys and row["constraints"]) else {},
            validation_evidence=json.loads(row["validation_evidence"]) if "validation_evidence" in keys else [],
            last_verified=row["last_verified"] if "last_verified" in keys else None,
            status=row["status"] if "status" in keys else "active",
            security_status=row["security_status"] if "security_status" in keys else "verified",
            revocation_reason=row["revocation_reason"] if "revocation_reason" in keys else None,
            security_violations=json.loads(row["security_violations"]) if ("security_violations" in keys and row["security_violations"]) else [],
            revoked_at=row["revoked_at"] if "revoked_at" in keys else None,
            scope=row["scope"] if "scope" in keys else "global",
            origin_episodes=json.loads(row["origin_episodes"]) if "origin_episodes" in keys else [],
            origin_repos=json.loads(row["origin_repos"]) if ("origin_repos" in keys and row["origin_repos"]) else [],
            validation_count=int(row["validation_count"]) if "validation_count" in keys else 1,
            last_validated_at=row["last_validated_at"] if "last_validated_at" in keys else None,
        )

    def invalidate_for_security_violation(
        self,
        pattern_id: str,
        violation_type: str,
        details: str,
        revoked_by: str = "security_policy",
        quarantine: bool = True,
    ) -> Optional[SemanticPattern]:
        """Immediately revokes trust from a semantic pattern due to a security violation.
        
        This is an instantaneous, non-probabilistic security intervention that bypasses Bayesian
        confidence thresholds entirely. A pattern with confidence=0.99 is immediately invalidated
        or quarantined and excluded from all future retrieval.
        """
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM semantic_patterns WHERE pattern_id = ?;", (pattern_id,)).fetchone()
            if not row:
                return None
            pat = self._row_to_pattern(row)
            pat.security_status = "quarantined" if quarantine else "invalidated"
            pat.status = "invalidated"
            pat.revocation_reason = f"Security Violation ({violation_type}): {details}"
            pat.revoked_at = now_str
            violation_record = {
                "violation_type": violation_type,
                "details": details,
                "revoked_by": revoked_by,
                "timestamp": now_str,
                "prior_confidence": pat.confidence,
                "action": "quarantined" if quarantine else "invalidated",
            }
            pat.security_violations.append(violation_record)
            self.store_pattern(pat)
            logger.warning(
                f"Pattern {pattern_id} ({pat.title}) IMMEDIATELY INVALIDATED for security violation: {details} "
                f"(Prior Bayesian confidence: {pat.confidence})"
            )
            return pat

    def recall_patterns(
        self,
        query: str,
        repo_identifier: Optional[str] = None,
        framework: Optional[str] = None,
        ecosystem: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 5,
    ) -> List[SemanticPattern]:
        """Recalls relevant patterns ranked by relevance, empirical confidence, and reuse evidence."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM semantic_patterns WHERE status = 'active' AND (security_status IS NULL OR security_status = 'verified');"
            ).fetchall()

        if not rows:
            return []

        query_tokens = self._tokenize(query)
        scored: List[tuple[float, SemanticPattern]] = []

        for row in rows:
            pat = self._row_to_pattern(row)

            # Security validity gate: strictly exclude any pattern with security issues regardless of confidence
            if pat.security_status != "verified" or pat.status in ("invalidated", "quarantined"):
                continue

            # ----------------------------------------------------
            # Strict Scope & Compatibility Gating
            # ----------------------------------------------------

            # 1. Repository Scope Isolation:
            # If a pattern is scoped to a specific repository, it MUST NEVER leak to another.
            if pat.scope == "repository":
                if not repo_identifier or (pat.repo_identifier != "global" and pat.repo_identifier != repo_identifier):
                    continue

            # 2. Ecosystem Conflict Gate:
            # e.g., A PostgreSQL connection pattern MUST NEVER match a MongoDB task.
            if ecosystem and pat.ecosystem:
                if pat.ecosystem.lower() != ecosystem.lower():
                    continue

            # 3. Ecosystem & Framework Scope Gate:
            # Patterns scoped to 'ecosystem' must match the querying framework or ecosystem.
            if pat.scope == "ecosystem":
                if pat.framework:
                    if not framework or pat.framework.lower() != framework.lower():
                        continue
                if pat.ecosystem:
                    if not ecosystem or pat.ecosystem.lower() != ecosystem.lower():
                        continue
                if not pat.framework and not pat.ecosystem:
                    if not (repo_identifier and pat.repo_identifier == repo_identifier):
                        continue

            # 4. Framework Conflict Gate:
            # e.g., A Django ORM pattern MUST NEVER match a FastAPI / Pydantic task.
            if framework and pat.framework:
                if pat.framework.lower() != framework.lower():
                    continue

            # 5. Language Isolation Gate:
            if language and pat.language and pat.language.lower() != "polyglot":
                if pat.language.lower() != language.lower():
                    continue

            # ----------------------------------------------------
            # Relevance & Alignment Scoring
            # ----------------------------------------------------
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

            # Ecosystem alignment bonus
            if ecosystem and pat.ecosystem and pat.ecosystem.lower() == ecosystem.lower():
                score += 2.5

            # Framework alignment bonus
            if framework and pat.framework and pat.framework.lower() == framework.lower():
                score += 2.0

            # Scope / Repository bonus
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
                scope="global",
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
                framework="pytest",
                scope="global",
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
                scope="global",
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
                framework="fastapi",
                scope="ecosystem",
            ),
        ]

        for p in defaults:
            self.store_pattern(p)

    def _tokenize(self, text: str) -> Set[str]:
        import re
        words = re.findall(r"[A-Za-z0-9_]{3,}", text.lower())
        stopwords = {"the", "and", "for", "with", "from", "into", "that", "this"}
        return set(w for w in words if w not in stopwords)


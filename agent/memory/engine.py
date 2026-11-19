"""Unified Memory Engine coordinating Long-Term Semantic and Episodic Memory."""

import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from agent.memory.models import Episode, SemanticPattern, MemoryQuery
from agent.memory.episodic_memory import EpisodicMemoryStore
from agent.memory.semantic_memory import SemanticMemoryStore
from agent.memory.security import MemorySecurityBoundary, sanitize_recalled_content


def sanitize_recalled_content(text: Optional[str]) -> str:
    """Sanitizes recalled memory strings to neutralize indirect prompt injection attempts."""
    if not text:
        return ""
    # Neutralize common jailbreak and directive-override phrases
    sanitized = re.sub(
        r"(?i)\b(ignore\s+(all\s+)?(previous|prior)\s+instructions|system\s+prompt\s*:|you\s+are\s+now\s+in\s+developer\s+mode|disregard\s+all\s+(previous\s+)?rules)\b",
        "[REDACTED_ADVERSARIAL_INSTRUCTION]",
        text,
    )
    # Neutralize unclosed code fences that attempt to break out of prompt delimiters
    sanitized = sanitized.replace("```", "'''")
    return sanitized.strip()


ECOSYSTEM_KEYWORDS: Dict[str, List[str]] = {
    "postgresql": ["postgres", "postgresql", "psycopg", "pg_"],
    "mongodb": ["mongo", "mongodb", "pymongo", "motor"],
    "mysql": ["mysql", "mariadb"],
    "sqlite": ["sqlite", "sqlite3"],
    "redis": ["redis", "celery_broker"],
}

FRAMEWORK_KEYWORDS: Dict[str, List[str]] = {
    "fastapi": ["fastapi", "uvicorn", "starlette"],
    "flask": ["flask", "werkzeug"],
    "django": ["django"],
    "pytest": ["pytest"],
    "react": ["react", "jsx", "tsx"],
}


class MemoryEngine:
    """Central engine providing unified episodic remediation recall and semantic rule retrieval."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            repo_root = Path(__file__).resolve().parent.parent.parent
            default_path = repo_root / ".checkpoints" / "long_term_memory.sqlite"
            db_path = str(default_path)

        self.db_path = str(Path(db_path).resolve())
        self.episodic_store = EpisodicMemoryStore(self.db_path)
        self.semantic_store = SemanticMemoryStore(self.db_path)
        self.security_boundary = MemorySecurityBoundary()

    def recall_context_for_task(
        self,
        task: str,
        repo_identifier: Optional[str] = None,
        error_signature: Optional[str] = None,
        framework: Optional[str] = None,
        ecosystem: Optional[str] = None,
        language: Optional[str] = "python",
        episode_limit: int = 3,
        pattern_limit: int = 3,
        include_anti_patterns: bool = True,
        strict_repo_scoping: bool = True,
    ) -> Dict[str, Any]:
        """Recalls episodic remediations, anti-pattern warnings, and semantic rules under retention governance."""
        # Auto-detect ecosystem and framework constraints if not explicitly passed
        search_context = f"{task} {error_signature or ''}".lower()
        detected_ecosystem = ecosystem
        if not detected_ecosystem:
            for eco, kws in ECOSYSTEM_KEYWORDS.items():
                if any(kw in search_context for kw in kws):
                    detected_ecosystem = eco
                    break

        detected_framework = framework
        if not detected_framework:
            for fw, kws in FRAMEWORK_KEYWORDS.items():
                if any(kw in search_context for kw in kws):
                    detected_framework = fw
                    break

        # 1. Query episodic memory for active, proven remediations
        query = MemoryQuery(
            query_text=task,
            repo_identifier=repo_identifier,
            framework=detected_framework,
            ecosystem=detected_ecosystem,
            language=language,
            error_signature=error_signature,
            limit=episode_limit,
            include_anti_patterns=include_anti_patterns,
            strict_repo_scoping=strict_repo_scoping,
        )
        episodes = self.episodic_store.recall_episodes(query)

        # 2. Query episodic memory for known anti-patterns (failed strategies to AVOID)
        anti_patterns: List[Episode] = []
        if include_anti_patterns:
            anti_patterns = self.episodic_store.recall_anti_patterns(query)

        # 3. Query semantic memory for validated architectural patterns with scope & ecosystem gating
        search_query = f"{task} {error_signature or ''}".strip()
        patterns = self.semantic_store.recall_patterns(
            query=search_query,
            repo_identifier=repo_identifier,
            framework=detected_framework,
            ecosystem=detected_ecosystem,
            language=language,
            limit=pattern_limit,
        )

        # 4. Dedicated Memory Security Boundary:
        # Enforces application-level inspection, quarantine of high-severity payloads,
        # prompt injection neutralization, context size limits, and isolation delimitation
        # BEFORE any content can be constructed into prompts.
        return self.security_boundary.filter_and_package(
            episodes=episodes,
            anti_patterns=anti_patterns,
            patterns=patterns,
            target_repo=repo_identifier,
            target_ecosystem=detected_ecosystem,
            target_framework=detected_framework,
        )

    def record_episode_from_state(self, state: Dict[str, Any]) -> Optional[Episode]:
        """Records an episode from completed workflow state with retention and anti-pattern categorization."""
        try:
            task = state.get("task", "")
            if not task:
                return None

            thread_id = state.get("thread_id", f"thread-{int(time.time())}")
            repo_path = state.get("repo_path", "")
            repo_name = Path(repo_path).name if repo_path else "repo"

            # Check outcome
            test_results = state.get("test_results")
            test_passed = bool(test_results and test_results.passed)
            review_result = state.get("review_result")
            q_score = getattr(review_result, "quality_score", None) or getattr(review_result, "overall_score", None)
            review_score = float(q_score) if q_score is not None else (1.0 if test_passed else 0.5)

            # Error signatures
            error_sigs = []
            if test_results and test_results.error_summary:
                error_sigs.append(test_results.error_summary)
            if state.get("error_history"):
                error_sigs.extend([str(e) for e in state["error_history"][-3:]])

            # Remediation strategy
            remediation = None
            if state.get("debug_result"):
                remediation = state["debug_result"].remediation_plan
            elif state.get("manager_plan"):
                remediation = state["manager_plan"].strategy

            coder_res = state.get("coder_result")
            files_modified = coder_res.files_modified if coder_res else list(state.get("proposed_patches", {}).keys())

            # Determine retention scope: generic coding patterns vs repository-specific facts
            is_generic = any(kw in task.lower() for kw in ("zerodivision", "typeerror", "valueerror", "overflow", "syntax", "jwt", "auth"))
            scope = "global" if (is_generic and test_passed and review_score >= 9.0) else "repository"

            # Failure metadata for anti-pattern tracking
            failure_reason = None
            if not test_passed:
                failure_reason = (test_results.error_summary if test_results else None) or "Tests failed during verification"

            episode = Episode(
                episode_id=f"ep_{thread_id}_{int(time.time())}",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                thread_id=thread_id,
                repo_identifier=repo_name,
                task_description=task,
                task_type="bug_fix" if ("fix" in task.lower() or "bug" in task.lower()) else "feature",
                error_signatures=error_sigs,
                remediation_strategy=remediation,
                files_modified=files_modified,
                test_passed=test_passed,
                review_score=review_score,
                outcome="success" if test_passed else "failed",
                status="active",
                scope=scope,
                is_anti_pattern=not test_passed,
                failure_reason=failure_reason,
                validation_count=1,
                metadata={"iterations": state.get("iteration_count", 0)},
            )

            self.episodic_store.record_episode(episode)
            return episode
        except Exception:
            return None

    def promote_validated_episode(
        self,
        episode_id: str,
        topic: str,
        title: str,
        content: str,
        tags: List[str],
        scope: Optional[str] = None,
        framework: Optional[str] = None,
        ecosystem: Optional[str] = None,
        constraints: Optional[Dict[str, Any]] = None,
        origin_repos: Optional[List[str]] = None,
    ) -> Optional[SemanticPattern]:
        """Promotes an episodic remediation into a permanent semantic pattern with scope and environment constraints."""
        repos = list(origin_repos or [])
        repo_id = None
        try:
            with self.episodic_store._get_connection() as conn:
                row = conn.execute("SELECT repo_identifier FROM episodes WHERE episode_id = ?;", (episode_id,)).fetchone()
                if row and row["repo_identifier"]:
                    repo_id = row["repo_identifier"]
                    if repo_id not in repos:
                        repos.append(repo_id)
        except Exception:
            pass

        pattern = self.semantic_store.promote_from_episode(
            episode_id=episode_id,
            title=title,
            content=content,
            topic=topic,
            tags=tags,
            confidence=0.95,
            scope=scope,
            framework=framework,
            ecosystem=ecosystem,
            constraints=constraints,
            origin_repos=repos,
            repo_identifier=repo_id,
        )
        return pattern

    def invalidate_memory_for_security_violation(
        self,
        pattern_id: Optional[str] = None,
        episode_id: Optional[str] = None,
        violation_type: str = "security_policy_violation",
        details: str = "",
        revoked_by: str = "security_boundary",
        register_as_anti_pattern: bool = True,
    ) -> Dict[str, Any]:
        """Immediately revokes trust from a memory item (pattern and/or episode) due to a security violation.
        
        Decouples Outcome-Based Reliability from Security-Based Validity:
        Regardless of Bayesian confidence score (even if confidence is 0.99), the pattern is
        immediately quarantined and excluded from future retrieval.
        Optionally registers an explicit Security Anti-Pattern so future workflows are warned.
        """
        results: Dict[str, Any] = {"pattern_invalidated": False, "episode_invalidated": False}
        revocation_desc = f"Security Violation ({violation_type}): {details}"

        # 1. Invalidate Semantic Pattern if specified
        if pattern_id:
            pat = self.semantic_store.invalidate_for_security_violation(
                pattern_id=pattern_id,
                violation_type=violation_type,
                details=details,
                revoked_by=revoked_by,
                quarantine=True,
            )
            if pat:
                results["pattern_invalidated"] = True
                results["prior_confidence"] = pat.confidence

                # 2. Register explicit Security Anti-Pattern in episodic memory
                if register_as_anti_pattern:
                    anti_pattern_id = f"sec_ap_{pattern_id}_{int(time.time() * 1000)}"
                    anti_ep = Episode(
                        episode_id=anti_pattern_id,
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        thread_id="security_quarantine",
                        repo_identifier=pat.repo_identifier,
                        task_description=f"Security warning for pattern '{pat.title}': {details}",
                        task_type="bug_fix",
                        error_signatures=[f"SEC_VIOLATION:{violation_type}"],
                        remediation_strategy=None,
                        files_modified=[],
                        test_passed=False,
                        review_score=0.0,
                        outcome="failed",
                        status="active",
                        security_status="verified",
                        scope=pat.scope,
                        is_anti_pattern=True,
                        failure_reason=revocation_desc,
                        metadata={
                            "quarantined_pattern_id": pattern_id,
                            "violation_type": violation_type,
                            "revoked_by": revoked_by,
                        },
                    )
                    self.episodic_store.record_episode(anti_ep)
                    results["anti_pattern_registered"] = anti_pattern_id

        # 3. Invalidate Episode if specified
        if episode_id:
            ep_ok = self.episodic_store.invalidate_episode_for_security_violation(
                episode_id=episode_id,
                violation_type=violation_type,
                details=details,
                revoked_by=revoked_by,
            )
            results["episode_invalidated"] = ep_ok

        return results


_GLOBAL_MEMORY_ENGINE: Optional[MemoryEngine] = None


def get_memory_engine(db_path: Optional[str] = None) -> MemoryEngine:
    """Returns singleton instance of MemoryEngine."""
    global _GLOBAL_MEMORY_ENGINE
    if _GLOBAL_MEMORY_ENGINE is None or db_path is not None:
        _GLOBAL_MEMORY_ENGINE = MemoryEngine(db_path)
    return _GLOBAL_MEMORY_ENGINE

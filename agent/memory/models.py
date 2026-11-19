"""Long-Term Semantic & Episodic Memory Data Models."""

import hashlib
import json
import time
from typing import List, Optional, Dict, Any, Set, Union
from pydantic import BaseModel, Field


class ValidationReceipt(BaseModel):
    """Represents a discrete, auditable validation event to enforce evidence independence."""
    receipt_id: str  # Deterministic hash: sha256(run_id:repo_id:test_suite_id:environment)
    run_id: str  # Unique workflow invocation / thread ID
    repo_identifier: str  # Repository where validation took place
    test_suite_id: str  # Identifier or digest of the test suite (e.g. pytest file, test hash)
    environment: str = "posix-sandbox"  # Environment (e.g. posix, docker, python3.11)
    outcome: str = "passed"  # "passed" or "failed"
    score: float = 1.0  # Quality score or pass ratio
    timestamp: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    @classmethod
    def create(
        cls,
        run_id: str,
        repo_identifier: str,
        test_suite_id: str,
        environment: str = "posix-sandbox",
        outcome: str = "passed",
        score: float = 1.0,
        timestamp: Optional[str] = None,
    ) -> "ValidationReceipt":
        ts = timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        key = f"{run_id}:{repo_identifier}:{test_suite_id}:{environment}"
        receipt_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        return cls(
            receipt_id=receipt_id,
            run_id=run_id,
            repo_identifier=repo_identifier,
            test_suite_id=test_suite_id,
            environment=environment,
            outcome=outcome,
            score=score,
            timestamp=ts,
        )


class Episode(BaseModel):
    """Represents a historical task episode with retention governance and anti-pattern metadata."""
    episode_id: str
    timestamp: str
    thread_id: str
    repo_identifier: str
    task_description: str
    task_type: str = "feature"  # feature, bug_fix, refactor
    error_signatures: List[str] = Field(default_factory=list)
    remediation_strategy: Optional[str] = None
    files_modified: List[str] = Field(default_factory=list)
    test_passed: bool = True
    review_score: float = 1.0
    outcome: str = "success"  # success, failed, aborted
    status: str = "active"  # active, superseded, invalidated, deprecated
    scope: str = "repository"  # repository, framework, global
    superseded_by: Optional[str] = None
    is_anti_pattern: bool = False  # True if capturing a failed strategy to prevent repetition
    failure_reason: Optional[str] = None
    validation_count: int = 1
    promoted_to_pattern_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SemanticPattern(BaseModel):
    """Represents an empirically validated, reusable architectural rule or coding convention."""
    pattern_id: str
    pattern: str = ""  # Canonical pattern statement (e.g. "Guard against zero denominator")
    pattern_type: str = "convention"  # convention, architecture, test_template, security_rule
    repo_identifier: str = "global"  # "global" or specific repo name
    topic: str = "general"
    title: str = ""  # Pattern title (synchronized with pattern)
    content: str = ""
    tags: List[str] = Field(default_factory=list)
    confidence: float = 0.70  # Bayesian-inspired confidence score (Beta posterior mean with effective sample weighting)
    successful_reuses: int = 0  # Count of downstream workflows where pattern was reused and passed
    failed_reuses: int = 0  # Count of downstream workflows where pattern resulted in regression
    language: str = "python"  # python, typescript, polyglot
    framework: Optional[str] = None  # fastapi, django, flask, pytest, express, etc.
    ecosystem: Optional[str] = None  # postgresql, mongodb, redis, sqlite, docker, etc.
    constraints: Dict[str, Any] = Field(default_factory=dict)  # environment / version constraints
    validation_evidence: List[Union[str, Dict[str, Any]]] = Field(default_factory=list)  # Empirical receipts
    last_verified: Optional[str] = None  # Timestamp of latest verification
    status: str = "active"  # active, deprecated, invalidated
    scope: str = "global"  # global, ecosystem, repository
    origin_episodes: List[str] = Field(default_factory=list)  # Episode IDs whose validation promoted this
    origin_repos: List[str] = Field(default_factory=list)  # Repository IDs where pattern was validated
    validation_count: int = 1
    last_validated_at: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        if self.pattern and not self.title:
            self.title = self.pattern
        elif self.title and not self.pattern:
            self.pattern = self.title
        if self.last_verified and not self.last_validated_at:
            self.last_validated_at = self.last_verified
        elif self.last_validated_at and not self.last_verified:
            self.last_verified = self.last_validated_at

    def parse_receipts(self) -> List[ValidationReceipt]:
        """Extracts structured ValidationReceipt objects from validation_evidence."""
        receipts = []
        for ev in self.validation_evidence:
            if isinstance(ev, ValidationReceipt):
                receipts.append(ev)
            elif isinstance(ev, dict) and "receipt_id" in ev:
                try:
                    receipts.append(ValidationReceipt(**ev))
                except Exception:
                    pass
            elif isinstance(ev, str) and ev.startswith("{") and "receipt_id" in ev:
                try:
                    receipts.append(ValidationReceipt(**json.loads(ev)))
                except Exception:
                    pass
        return receipts

    def get_independent_runs(self) -> Set[str]:
        """Returns the set of distinct execution run IDs that validated this pattern."""
        return {r.run_id for r in self.parse_receipts() if r.outcome == "passed"}

    def get_independent_test_suites(self) -> Set[str]:
        """Returns the set of distinct test suite signatures that validated this pattern."""
        return {r.test_suite_id for r in self.parse_receipts() if r.outcome == "passed"}

    def get_independent_environments(self) -> Set[str]:
        """Returns the set of distinct environments that validated this pattern."""
        return {r.environment for r in self.parse_receipts() if r.outcome == "passed"}


class MemoryQuery(BaseModel):
    """Specification for querying semantic and episodic memory stores under retention governance."""
    query_text: str
    repo_identifier: Optional[str] = None
    framework: Optional[str] = None
    ecosystem: Optional[str] = None
    language: Optional[str] = "python"
    error_signature: Optional[str] = None
    limit: int = 3
    include_anti_patterns: bool = True
    strict_repo_scoping: bool = True
    include_superseded: bool = False


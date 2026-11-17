"""Long-Term Semantic & Episodic Memory Data Models."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


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
    confidence: float = 0.70  # Empirical confidence score dynamically adjusted via reuses
    successful_reuses: int = 0  # Count of downstream workflows where pattern was reused and passed
    failed_reuses: int = 0  # Count of downstream workflows where pattern resulted in regression
    language: str = "python"  # python, typescript, polyglot
    validation_evidence: List[str] = Field(default_factory=list)  # Empirical receipts (e.g. unit_tests_passed)
    last_verified: Optional[str] = None  # Timestamp of latest verification
    status: str = "active"  # active, deprecated, invalidated
    scope: str = "global"  # global, framework, repository
    origin_episodes: List[str] = Field(default_factory=list)  # Episode IDs whose validation promoted this
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


class MemoryQuery(BaseModel):
    """Specification for querying semantic and episodic memory stores under retention governance."""
    query_text: str
    repo_identifier: Optional[str] = None
    error_signature: Optional[str] = None
    limit: int = 3
    include_anti_patterns: bool = True
    strict_repo_scoping: bool = True
    include_superseded: bool = False


"""Verification package providing independent verification and outcome classification."""

from agent.verification.verifier import (
    WorkflowOutcome,
    LintCheckResult,
    DiffReviewResult,
    VerificationResult,
    IndependentVerifier,
)

__all__ = [
    "WorkflowOutcome",
    "LintCheckResult",
    "DiffReviewResult",
    "VerificationResult",
    "IndependentVerifier",
]

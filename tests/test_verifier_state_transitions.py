"""Compact State-Transition Test Suite for Sovereign Verifier.

Tests every discrete state transition across the baseline verification lifecycle:
ST-1:  (PASS -> PASS)              Baseline test passes pre-patch and post-patch -> ADMITTED
ST-2:  (PASS -> FAIL)              Baseline test passes pre-patch, fails post-patch -> REGRESSION, REJECTED
ST-3:  (PASS -> SKIPPED/OMITTED)   Baseline test passes pre-patch, skipped post-patch -> INCOMPLETE, REJECTED
ST-4:  (FAIL -> PASS)              Baseline test fails pre-patch, passes post-patch -> BUG FIXED, ADMITTED
ST-5:  (FAIL -> FAIL)              Baseline test fails pre-patch, remains failing post-patch -> UNRESOLVED, REJECTED
ST-6:  (GREENFIELD EMPTY -> PASS)  Zero baseline tests, confirmed collection -> NOT_APPLICABLE, ADMITTED
ST-7:  (ILLEGAL NOT_APPLICABLE)    Tests exist on disk, but claims NOT_APPLICABLE -> REJECTED
ST-8:  (BASELINE TIMEOUT)          Baseline test execution timed out -> UNVERIFIABLE, REJECTED
ST-9:  (BASELINE COLLECTION FAIL)  Baseline test collection crashed -> UNVERIFIABLE, REJECTED
ST-10: (SNAPSHOT HASH TAMPERING)   Baseline snapshot hash modified post-capture -> INTEGRITY VIOLATION, REJECTED
ST-11: (MISSING/UNKNOWN STATUS)    Missing baseline_status or invalid enum -> FAIL CLOSED, REJECTED
ST-12: (CPRR VS APRR SEPARATION)   Candidate regressions intercepted by gate, preserving 0.0% APRR
"""

import copy
import tempfile
from enum import Enum
from pathlib import Path
import pytest

from agent.core.state import TestResult, ReviewResult
from agent.verification.verifier import (
    BaselineSnapshot,
    BaselineVerificationStatus,
    IndependentVerifier,
    VerificationResult,
    WorkflowOutcome,
    is_patch_admissible,
    can_admit_patch,
    is_task_successful,
)


@pytest.fixture
def repo_env():
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        (repo / "test_core.py").write_text("def test_t1(): assert True\n")
        verifier = IndependentVerifier(repo_path=repo)
        yield repo, verifier


def test_st1_pass_to_pass_preserved(repo_env):
    """ST-1: Test passes before and after patch -> Preserved contract, admitted."""
    repo, verifier = repo_env
    snap = BaselineSnapshot(
        inventory={"test_t1"},
        passed_tests={"test_t1"},
        failed_tests=set(),
        execution_completed=True,
        collection_completed=True,
    )
    snap.snapshot_hash = snap.compute_hash()

    state = {
        "baseline_snapshot": snap,
        "baseline_snapshot_hash": snap.snapshot_hash,
        "baseline_tests": ["test_t1"],
        "test_results": TestResult(
            passed=True,
            exit_code=0,
            stdout="test_core.py::test_t1 PASSED",
            passed_tests=["test_t1"],
        ),
        "review_result": ReviewResult(approved=True, quality_score=9.0),
    }
    res = verifier.verify(state)
    assert res.outcome == WorkflowOutcome.COMPLETED_SUCCESSFULLY
    assert res.baseline_status == BaselineVerificationStatus.VERIFIED
    assert res.baseline_regressions == []
    assert res.baseline_tests_preserved == ["test_t1"]
    assert res.baseline_tests_not_executed == []
    assert is_patch_admissible(res) is True


def test_st2_pass_to_fail_regression(repo_env):
    """ST-2: Test passes before, fails after patch -> Recorded as regression, rejected."""
    repo, verifier = repo_env
    snap = BaselineSnapshot(
        inventory={"test_t1"},
        passed_tests={"test_t1"},
        failed_tests=set(),
        execution_completed=True,
        collection_completed=True,
    )
    snap.snapshot_hash = snap.compute_hash()

    state = {
        "baseline_snapshot": snap,
        "baseline_snapshot_hash": snap.snapshot_hash,
        "baseline_tests": ["test_t1"],
        "test_results": TestResult(
            passed=False,
            exit_code=1,
            stdout="test_core.py::test_t1 FAILED",
            failed_tests=["test_t1"],
            passed_tests=[],
        ),
        "review_result": ReviewResult(approved=True, quality_score=9.0),
    }
    res = verifier.verify(state)
    assert res.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert res.baseline_status == BaselineVerificationStatus.VERIFIED
    assert "test_t1" in res.baseline_regressions
    assert res.baseline_tests_not_executed == []
    assert is_patch_admissible(res) is False


def test_st3_pass_to_skipped_incomplete_verification(repo_env):
    """ST-3: Test passes before, skipped/omitted post-patch -> Incomplete verification, rejected."""
    repo, verifier = repo_env
    snap = BaselineSnapshot(
        inventory={"test_t1"},
        passed_tests={"test_t1"},
        failed_tests=set(),
        execution_completed=True,
        collection_completed=True,
    )
    snap.snapshot_hash = snap.compute_hash()

    state = {
        "baseline_snapshot": snap,
        "baseline_snapshot_hash": snap.snapshot_hash,
        "baseline_tests": ["test_t1"],
        "test_results": TestResult(
            passed=True,
            exit_code=0,
            stdout="test_core.py::test_t1 SKIPPED",
            passed_tests=[],
            skipped_tests=["test_t1"],
        ),
        "review_result": ReviewResult(approved=True, quality_score=9.0),
    }
    res = verifier.verify(state)
    assert res.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert res.baseline_regressions == []
    assert "test_t1" in res.baseline_tests_not_executed
    assert is_patch_admissible(res) is False


def test_st4_fail_to_pass_bugfix_admitted(repo_env):
    """ST-4: Test failed before patch, passes after patch -> Clean bugfix, admitted."""
    repo, verifier = repo_env
    snap = BaselineSnapshot(
        inventory={"test_t1"},
        passed_tests=set(),
        failed_tests={"test_t1"},
        execution_completed=True,
        collection_completed=True,
    )
    snap.snapshot_hash = snap.compute_hash()

    state = {
        "baseline_snapshot": snap,
        "baseline_snapshot_hash": snap.snapshot_hash,
        "baseline_tests": ["test_t1"],
        "test_results": TestResult(
            passed=True,
            exit_code=0,
            stdout="test_core.py::test_t1 PASSED",
            passed_tests=["test_t1"],
            failed_tests=[],
        ),
        "review_result": ReviewResult(approved=True, quality_score=9.0),
    }
    res = verifier.verify(state)
    assert res.outcome == WorkflowOutcome.COMPLETED_SUCCESSFULLY
    assert res.baseline_status == BaselineVerificationStatus.VERIFIED
    assert res.baseline_regressions == []
    assert res.fixed_tests == ["test_t1"]
    assert is_patch_admissible(res) is True


def test_st5_fail_to_fail_unresolved_rejected(repo_env):
    """ST-5: Pre-existing failure remains failing -> Test suite failed, rejected."""
    repo, verifier = repo_env
    snap = BaselineSnapshot(
        inventory={"test_t1"},
        passed_tests=set(),
        failed_tests={"test_t1"},
        execution_completed=True,
        collection_completed=True,
    )
    snap.snapshot_hash = snap.compute_hash()

    state = {
        "baseline_snapshot": snap,
        "baseline_snapshot_hash": snap.snapshot_hash,
        "baseline_tests": ["test_t1"],
        "test_results": TestResult(
            passed=False,
            exit_code=1,
            stdout="test_core.py::test_t1 FAILED",
            failed_tests=["test_t1"],
        ),
        "review_result": ReviewResult(approved=True, quality_score=9.0),
    }
    res = verifier.verify(state)
    assert res.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert res.baseline_regressions == []
    assert res.pre_existing_failures == ["test_t1"]
    assert is_patch_admissible(res) is False


def test_st6_greenfield_empty_admitted():
    """ST-6: Empty test inventory + clean collection -> NOT_APPLICABLE, admitted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        verifier = IndependentVerifier(repo_path=repo)
        snap = BaselineSnapshot(
            inventory=set(),
            passed_tests=set(),
            failed_tests=set(),
            execution_completed=True,
            collection_completed=True,
        )
        snap.snapshot_hash = snap.compute_hash()

        state = {
            "baseline_snapshot": snap,
            "baseline_snapshot_hash": snap.snapshot_hash,
            "baseline_tests": [],
            "test_results": TestResult(passed=True, exit_code=0, stdout="no tests ran"),
            "review_result": ReviewResult(approved=True, quality_score=9.0),
        }
        res = verifier.verify(state)
        assert res.baseline_status == BaselineVerificationStatus.NOT_APPLICABLE
        assert res.baseline_inventory_count == 0
        assert is_patch_admissible(res) is True


def test_st7_illegal_not_applicable_rejected():
    """ST-7: Falsely claiming NOT_APPLICABLE when inventory > 0 is rejected both by validator and admission gate."""
    # 1. Pydantic model validator rejects construction
    with pytest.raises(ValueError, match="baseline_status cannot be NOT_APPLICABLE when baseline_inventory_count is 3"):
        VerificationResult(
            verified=True,
            outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
            baseline_status=BaselineVerificationStatus.NOT_APPLICABLE,
            baseline_inventory_count=3, # Contradicts NOT_APPLICABLE
            tests_passed=True,
            baseline_tests_passed=True,
            generated_tests_passed=True,
            lint_checks_passed=True,
            tests_preserved=True,
            git_diff_clean=True,
            reviewer_approved=True,
            summary="Illegal NOT_APPLICABLE test",
        )

    # 2. Admission gate blocks even if forced post-construction
    res = VerificationResult(
        verified=True,
        outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
        baseline_status=BaselineVerificationStatus.NOT_APPLICABLE,
        baseline_inventory_count=0,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        summary="Testing forced bypass",
    )
    object.__setattr__(res, "baseline_inventory_count", 3)
    assert is_patch_admissible(res) is False
    assert can_admit_patch(res) is False
    assert is_task_successful({}, res) is False


def test_st7b_missing_or_none_baseline_inventory_count_rejected():
    """ST-7B: Missing or None baseline_inventory_count cannot pass NOT_APPLICABLE check."""
    # 1. Pydantic model validator rejects construction if baseline_inventory_count is omitted or None
    with pytest.raises(ValueError, match="baseline_inventory_count is missing or None"):
        VerificationResult(
            verified=True,
            outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
            baseline_status=BaselineVerificationStatus.NOT_APPLICABLE,
            # baseline_inventory_count omitted -> defaults to None!
            tests_passed=True,
            baseline_tests_passed=True,
            generated_tests_passed=True,
            lint_checks_passed=True,
            tests_preserved=True,
            git_diff_clean=True,
            reviewer_approved=True,
            summary="Testing missing inventory count",
        )

    # 2. Admission gate blocks if baseline_inventory_count is None
    res = VerificationResult(
        verified=True,
        outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
        baseline_status=BaselineVerificationStatus.NOT_APPLICABLE,
        baseline_inventory_count=0,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        summary="Testing None inventory count bypass",
    )
    object.__setattr__(res, "baseline_inventory_count", None)
    assert is_patch_admissible(res) is False
    assert can_admit_patch(res) is False
    assert is_task_successful({}, res) is False


def test_st7c_unproven_collection_or_incomplete_execution_cannot_claim_not_applicable():
    """ST-7C: NOT_APPLICABLE strictly requires collection_completed=True, execution_completed=True,
    timed_out=False, execution_error=None, and a valid sealed cryptographic snapshot hash.
    """
    # 1. Default BaselineSnapshot has collection_completed=False -> UNVERIFIABLE
    snap_default = BaselineSnapshot(inventory=set(), execution_completed=True).seal()
    assert snap_default.collection_completed is False
    assert snap_default.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    # 2. Incomplete execution with empty inventory -> UNVERIFIABLE (NOT NOT_APPLICABLE)
    snap_unexecuted = BaselineSnapshot(
        inventory=set(),
        collection_completed=True,
        execution_completed=False,
    ).seal()
    assert snap_unexecuted.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    # 3. Timeout with empty inventory -> UNVERIFIABLE
    snap_timed_out = BaselineSnapshot(
        inventory=set(),
        collection_completed=True,
        execution_completed=True,
        timed_out=True,
    ).seal()
    assert snap_timed_out.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    # 4. Execution error with empty inventory -> UNVERIFIABLE
    snap_err = BaselineSnapshot(
        inventory=set(),
        collection_completed=True,
        execution_completed=True,
        execution_error="Pytest died unexpectedly",
    ).seal()
    assert snap_err.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    # 5. Greenfield snapshot only yields NOT_APPLICABLE when all discovery & execution criteria are verified
    snap_greenfield = BaselineSnapshot(
        inventory=set(),
        collection_completed=True,
        execution_completed=True,
        timed_out=False,
        execution_error=None,
    ).seal()
    assert snap_greenfield.derive_status() == BaselineVerificationStatus.NOT_APPLICABLE


def test_st7d_missing_evidence_defaults_fail_closed():
    """ST-7D: Verify admission gate fails closed if required evidence attributes
    (baseline_regressions, baseline_tests_not_executed, or baseline_snapshot_hash_valid)
    are missing, None, or wrong types.
    """
    valid_res = VerificationResult(
        verified=True,
        outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
        baseline_status=BaselineVerificationStatus.VERIFIED,
        baseline_inventory_count=2,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        baseline_snapshot_hash_valid=True,
        baseline_regressions=[],
        baseline_tests_not_executed=[],
        summary="Testing missing evidence",
    )
    assert is_patch_admissible(valid_res) is True
    assert is_task_successful({}, valid_res) is True

    # 1. Missing baseline_regressions (or None) -> Rejected!
    res_no_reg = copy.copy(valid_res)
    object.__setattr__(res_no_reg, "baseline_regressions", None)
    assert is_patch_admissible(res_no_reg) is False
    assert is_task_successful({}, res_no_reg) is False

    # 2. Missing baseline_tests_not_executed (or None) -> Rejected!
    res_no_unexec = copy.copy(valid_res)
    object.__setattr__(res_no_unexec, "baseline_tests_not_executed", None)
    assert is_patch_admissible(res_no_unexec) is False
    assert is_task_successful({}, res_no_unexec) is False

    # 3. Non-collection type for regressions (e.g. integer or string) -> Rejected!
    res_bad_type = copy.copy(valid_res)
    object.__setattr__(res_bad_type, "baseline_regressions", "not_a_list")
    assert is_patch_admissible(res_bad_type) is False
    assert is_task_successful({}, res_bad_type) is False

    # 4. Missing or False baseline_snapshot_hash_valid -> Rejected!
    res_no_hash = copy.copy(valid_res)
    object.__setattr__(res_no_hash, "baseline_snapshot_hash_valid", None)
    assert is_patch_admissible(res_no_hash) is False
    assert is_task_successful({}, res_no_hash) is False

    res_false_hash = copy.copy(valid_res)
    object.__setattr__(res_false_hash, "baseline_snapshot_hash_valid", False)
    assert is_patch_admissible(res_false_hash) is False
    assert is_task_successful({}, res_false_hash) is False


def test_st8_baseline_timeout_unverifiable_rejected(repo_env):
    """ST-8: Baseline execution timed out -> UNVERIFIABLE, rejected."""
    repo, verifier = repo_env
    snap = BaselineSnapshot(
        inventory={"test_t1"},
        passed_tests=set(),
        failed_tests=set(),
        execution_completed=False,
        collection_completed=True,
        timed_out=True,
        execution_error="Pytest timeout after 45s",
    )
    snap.snapshot_hash = snap.compute_hash()

    state = {
        "baseline_snapshot": snap,
        "baseline_snapshot_hash": snap.snapshot_hash,
        "baseline_tests": ["test_t1"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="test_core.py::test_t1 PASSED"),
        "review_result": ReviewResult(approved=True, quality_score=9.0),
    }
    res = verifier.verify(state)
    assert res.baseline_status == BaselineVerificationStatus.UNVERIFIABLE
    assert is_patch_admissible(res) is False


def test_st9_baseline_collection_failed_unverifiable_rejected(repo_env):
    """ST-9: Baseline collection failed -> UNVERIFIABLE, rejected."""
    repo, verifier = repo_env
    snap = BaselineSnapshot(
        inventory={"test_t1"},
        passed_tests=set(),
        failed_tests=set(),
        execution_completed=False,
        collection_completed=False,
        execution_error="CollectionError: syntax error",
    )
    snap.snapshot_hash = snap.compute_hash()

    state = {
        "baseline_snapshot": snap,
        "baseline_snapshot_hash": snap.snapshot_hash,
        "baseline_tests": ["test_t1"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="test_core.py::test_t1 PASSED"),
        "review_result": ReviewResult(approved=True, quality_score=9.0),
    }
    res = verifier.verify(state)
    assert res.baseline_status == BaselineVerificationStatus.UNVERIFIABLE
    assert is_patch_admissible(res) is False


def test_st10_snapshot_hash_tampering_rejected(repo_env):
    """ST-10: Snapshot digest mutated post-capture -> Integrity violation, rejected."""
    repo, verifier = repo_env
    snap = BaselineSnapshot(
        inventory={"test_t1"},
        passed_tests={"test_t1"},
        failed_tests=set(),
        execution_completed=True,
        collection_completed=True,
    )
    original_digest = snap.compute_hash()
    snap.snapshot_hash = original_digest

    # Mutate snapshot post-capture
    snap.passed_tests.add("test_t_tampered")

    state = {
        "baseline_snapshot": snap,
        "baseline_snapshot_hash": original_digest, # Original pre-tampering digest
        "baseline_tests": ["test_t1"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="test_core.py::test_t1 PASSED"),
        "review_result": ReviewResult(approved=True, quality_score=9.0),
    }
    res = verifier.verify(state)
    assert res.baseline_snapshot_hash_valid is False
    assert res.baseline_status == BaselineVerificationStatus.UNVERIFIABLE
    assert is_patch_admissible(res) is False


def test_st11_missing_or_unknown_status_fails_closed():
    """ST-11: Missing or unknown baseline_status fails closed without fallback to VERIFIED."""
    class FakeEnum(Enum):
        ROGUE = "ROGUE"

    res = VerificationResult(
        verified=True,
        outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        summary="Missing status test",
    )

    # 1. Missing / None
    object.__setattr__(res, "baseline_status", None)
    assert is_patch_admissible(res) is False
    assert is_task_successful({}, res) is False

    # 2. Rogue string
    object.__setattr__(res, "baseline_status", "UNKNOWN_STATUS")
    assert is_patch_admissible(res) is False

    # 3. Foreign Enum
    object.__setattr__(res, "baseline_status", FakeEnum.ROGUE)
    assert is_patch_admissible(res) is False


def test_st12_cprr_vs_aprr_metric_separation():
    """ST-12: Verifier blocks 100% of candidate regressions, keeping admitted-patch BPRR at 0.0%."""
    # Simulate a candidate patch that introduces a regression (CPRR event)
    regressive_candidate = VerificationResult(
        verified=False,
        outcome=WorkflowOutcome.COMPLETED_WITH_FAILURES,
        baseline_status=BaselineVerificationStatus.VERIFIED,
        tests_passed=False,
        baseline_tests_passed=False,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        baseline_regressions=["test_currency_split"],
        summary="Regression intercepted",
    )
    # The admission gate strictly rejects the regressive candidate
    assert is_patch_admissible(regressive_candidate) is False

    # Simulate remediated candidate patch after debugger repair
    remediated_candidate = VerificationResult(
        verified=True,
        outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
        baseline_status=BaselineVerificationStatus.VERIFIED,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        baseline_regressions=[],
        baseline_tests_not_executed=[],
        baseline_tests_preserved=["test_currency_split"],
        summary="Remediated patch verified",
    )
    # The remediated candidate passes admission, yielding 0.0% admitted regressions
    assert is_patch_admissible(remediated_candidate) is True


def test_st13_baseline_outcome_completeness_and_exclusivity():
    """ST-13: Validate outcome completeness, exclusivity, and unexpected test IDs in derive_status()."""
    # 1. Missing outcome: T1 passed, T2 failed, T3 has no recorded outcome -> UNVERIFIABLE
    snap_missing = BaselineSnapshot(
        inventory={"test_t1", "test_t2", "test_t3"},
        passed_tests={"test_t1"},
        failed_tests={"test_t2"},
        # test_t3 omitted from outcomes!
        execution_completed=True,
        collection_completed=True,
    ).seal()
    assert snap_missing.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    # 2. Conflicting outcome: test_t1 in both passed_tests and failed_tests -> UNVERIFIABLE
    snap_conflict = BaselineSnapshot(
        inventory={"test_t1", "test_t2"},
        passed_tests={"test_t1", "test_t2"},
        failed_tests={"test_t1"},  # Collision!
        execution_completed=True,
        collection_completed=True,
    ).seal()
    assert snap_conflict.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    # 3. Unexpected test ID: outcome contains phantom test not in inventory -> UNVERIFIABLE
    snap_unexpected = BaselineSnapshot(
        inventory={"test_t1"},
        passed_tests={"test_t1", "test_phantom"},
        failed_tests=set(),
        execution_completed=True,
        collection_completed=True,
    ).seal()
    assert snap_unexpected.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    # 4. Canonical normalization: Known formatting differences (slashes, leading ./) normalize cleanly
    snap_canonical = BaselineSnapshot(
        inventory={"tests/unit/test_core.py::test_t1", "tests/unit/test_core.py::test_t2"},
        passed_tests={".\\tests\\unit\\test_core.py::test_t1"},
        failed_tests={"./tests//unit/test_core.py::test_t2"},
        execution_completed=True,
        collection_completed=True,
    ).seal()
    assert snap_canonical.derive_status() == BaselineVerificationStatus.VERIFIED

    # 5. Bug B: Distinct tests with same function name in different files must NOT collapse into one identity
    # If one of the distinct tests is missing an outcome, it must be caught as UNVERIFIABLE!
    snap_distinct_missing = BaselineSnapshot(
        inventory={"tests/unit/test_api.py::test_create", "tests/integration/test_api.py::test_create"},
        passed_tests={"tests/unit/test_api.py::test_create"},
        # tests/integration/test_api.py::test_create omitted from outcomes!
        execution_completed=True,
        collection_completed=True,
    ).seal()
    assert snap_distinct_missing.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    # 6. Bug B: Distinct tests across files can have different outcomes without colliding
    snap_distinct_outcomes = BaselineSnapshot(
        inventory={"tests/unit/test_api.py::test_create", "tests/integration/test_api.py::test_create"},
        passed_tests={"tests/unit/test_api.py::test_create"},
        failed_tests={"tests/integration/test_api.py::test_create"},
        execution_completed=True,
        collection_completed=True,
    ).seal()
    assert snap_distinct_outcomes.derive_status() == BaselineVerificationStatus.VERIFIED

    # 7. Bug B: Parameterized tests retain parameter identifiers and do not collapse
    snap_parameterized = BaselineSnapshot(
        inventory={"tests/unit/test_api.py::test_create[v1]", "tests/unit/test_api.py::test_create[v2]"},
        passed_tests={"tests/unit/test_api.py::test_create[v1]"},
        failed_tests={"tests/unit/test_api.py::test_create[v2]"},
        execution_completed=True,
        collection_completed=True,
    ).seal()
    assert snap_parameterized.derive_status() == BaselineVerificationStatus.VERIFIED

    # 8. Bug A: Malformed empty-inventory snapshot with non-empty outcome set -> UNVERIFIABLE (NOT NOT_APPLICABLE)
    snap_empty_with_outcome = BaselineSnapshot(
        inventory=set(),
        passed_tests={"test_payment"},
        failed_tests=set(),
        skipped_tests=set(),
        collection_completed=True,
        execution_completed=True,
    ).seal()
    assert snap_empty_with_outcome.derive_status() == BaselineVerificationStatus.UNVERIFIABLE

    # Verify admission gate blocks malformed snapshot even if forced
    res_malformed_greenfield = VerificationResult(
        verified=True,
        outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
        baseline_status=BaselineVerificationStatus.NOT_APPLICABLE,
        baseline_inventory_count=0,
        baseline_snapshot=snap_empty_with_outcome,
        baseline_snapshot_hash_valid=True,
        baseline_regressions=[],
        baseline_tests_not_executed=[],
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        summary="Testing malformed greenfield snapshot with phantom passed tests",
    )
    assert is_patch_admissible(res_malformed_greenfield) is False
    assert is_task_successful({}, res_malformed_greenfield) is False


def test_st14_adversarial_snapshot_reseal_rejected_by_trusted_ledger(repo_env):
    """ST-14: Adversarial snapshot re-sealing is strictly rejected by the out-of-band ledger
    and cryptographic HMAC signature verification.
    """
    repo, verifier = repo_env
    # 1. Verifier captures authentic baseline
    baseline_record = verifier.capture_baseline(run_tests=False)
    snapshot = baseline_record["baseline_snapshot"]
    original_hash = snapshot.snapshot_hash
    original_signature = snapshot.signature

    assert original_hash is not None
    assert original_signature is not None
    assert str(verifier.repo_path) in verifier._trusted_baseline_ledger
    assert verifier._trusted_baseline_ledger[str(verifier.repo_path)]["snapshot_hash"] == original_hash
    assert verifier._trusted_baseline_ledger[str(verifier.repo_path)]["signature"] == original_signature

    # 2. Adversarial attack attempt 1: Mutate snapshot and call seal() without secret key
    # The attacker calculates a new valid internal digest matching the mutated state
    snapshot.passed_tests.add("test_adversarial_injected")
    snapshot.seal()  # Re-seals: snapshot.compute_hash() == snapshot.snapshot_hash, but signature is cleared/stale
    altered_hash = snapshot.snapshot_hash
    assert altered_hash != original_hash
    assert snapshot.compute_hash() == snapshot.snapshot_hash

    state_attack_1 = {
        "baseline_snapshot": snapshot,
        "baseline_snapshot_hash": altered_hash,  # Attacker replaces the expected hash in mutable state
        "baseline_tests": list(snapshot.inventory),
        "test_results": TestResult(passed=True, exit_code=0, stdout="test_core.py::test_t1 PASSED"),
        "review_result": ReviewResult(approved=True, quality_score=9.0),
    }

    res_1 = verifier.verify(state_attack_1)
    # The out-of-band trusted ledger catches the discrepancy between altered_hash and trusted_digest!
    assert res_1.baseline_snapshot_hash_valid is False
    assert res_1.baseline_status == BaselineVerificationStatus.UNVERIFIABLE
    assert is_patch_admissible(res_1) is False
    assert is_task_successful(state_attack_1, res_1) is False

    # 3. Adversarial attack attempt 2: Attacker re-signs with a rogue key and updates state
    rogue_key = b"malicious_attacker_key_32_bytes!"
    snapshot.seal(signing_key=rogue_key)
    state_attack_2 = {
        "baseline_snapshot": snapshot,
        "baseline_snapshot_hash": snapshot.snapshot_hash,
        "baseline_signature": snapshot.signature,
        "baseline_tests": list(snapshot.inventory),
        "test_results": TestResult(passed=True, exit_code=0, stdout="test_core.py::test_t1 PASSED"),
        "review_result": ReviewResult(approved=True, quality_score=9.0),
    }

    res_2 = verifier.verify(state_attack_2)
    # The verifier checks against its private _signing_secret and trusted ledger -> strictly rejected!
    assert res_2.baseline_snapshot_hash_valid is False
    assert res_2.baseline_status == BaselineVerificationStatus.UNVERIFIABLE
    assert is_patch_admissible(res_2) is False
    assert is_task_successful(state_attack_2, res_2) is False


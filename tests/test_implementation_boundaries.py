"""Tests for the Four Implementation Boundaries:
1. Hash Coverage: Polyglot production files (.py, .js, .sh, .sql, .yaml, .html) with explicit exclusion policy.
2. TOCTOU Protection: Immutable snapshot manifest, root hash digest, and mutation detection at handover.
3. Cooperative Cancellation: Early cancellation checks across all pipeline nodes before expensive operations.
4. Centralized Retry Metering: Centralized accounting in manager_evaluate for all remediation routes.
"""

import os
import tempfile
import hashlib
from pathlib import Path
import pytest

from agent.core.state import (
    AgentState,
    TestResult,
    ReviewResult,
    CoderResult,
    TestGenResult,
    DebugResult,
)
from agent.verification.verifier import (
    IndependentVerifier,
    WorkflowOutcome,
    VerificationResult,
    BaselineVerificationStatus,
    is_task_successful,
)
from agent.agents.reviewer import (
    ReviewerAgent,
    should_be_reviewed,
    EXCLUDED_REVIEW_PATTERNS,
)
from agent.agents.manager import ManagerPlannerAgent
from agent.core.graph import (
    explore_repo_node,
    manager_planner_node,
    coder_node,
    test_generator_node as graph_test_generator_node,
    sandbox_runner_node,
    debugger_node,
    reviewer_node,
    manager_evaluate_node,
    manager_finalize_node,
)


@pytest.fixture
def polyglot_repo():
    """Sets up a temporary repo with polyglot production files and test suites."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        (repo / "src").mkdir(parents=True, exist_ok=True)
        (repo / "scripts").mkdir(parents=True, exist_ok=True)
        (repo / "db").mkdir(parents=True, exist_ok=True)
        (repo / "config").mkdir(parents=True, exist_ok=True)
        (repo / "tests").mkdir(parents=True, exist_ok=True)

        (repo / "src" / "app.py").write_text("def run():\n    return 42\n", encoding="utf-8")
        (repo / "src" / "client.js").write_text("function getAnswer() { return 42; }\n", encoding="utf-8")
        (repo / "scripts" / "deploy.sh").write_text("#!/bin/bash\necho 'deploying'\n", encoding="utf-8")
        (repo / "db" / "schema.sql").write_text("CREATE TABLE users (id INT PRIMARY KEY);\n", encoding="utf-8")
        (repo / "config" / "settings.yaml").write_text("env: production\n", encoding="utf-8")
        (repo / "tests" / "test_app.py").write_text(
            "from src.app import run\n\ndef test_run():\n    assert run() == 42\n",
            encoding="utf-8",
        )
        yield repo


# ============================================================
# 1. Boundary A: Hash Coverage Tests
# ============================================================

def test_should_be_reviewed_policy():
    """Verify policy-based inclusion of production files and exclusion of tests, caches, and binaries."""
    # Polyglot production files must be reviewed
    assert should_be_reviewed("src/main.py") is True
    assert should_be_reviewed("frontend/app.js") is True
    assert should_be_reviewed("scripts/deploy.sh") is True
    assert should_be_reviewed("migrations/001_init.sql") is True
    assert should_be_reviewed("config/app.yaml") is True
    assert should_be_reviewed("templates/index.html") is True

    # Extensionless production and build files must be reviewed (never missed by extension allowlists)
    assert should_be_reviewed("Dockerfile") is True
    assert should_be_reviewed("docker/Dockerfile") is True
    assert should_be_reviewed("Makefile") is True
    assert should_be_reviewed("Procfile") is True
    assert should_be_reviewed("Gemfile") is True
    assert should_be_reviewed("Containerfile") is True
    assert should_be_reviewed("Vagrantfile") is True
    assert should_be_reviewed("Brewfile") is True
    assert should_be_reviewed("Jenkinsfile") is True

    # Configuration and environment files must be reviewed
    assert should_be_reviewed(".env.example") is True
    assert should_be_reviewed("nginx.conf") is True
    assert should_be_reviewed("config/settings.ini") is True
    assert should_be_reviewed("package.json") is True

    # Tests must be excluded from code review (they undergo test preservation / assertion audits)
    assert should_be_reviewed("tests/test_core.py") is False
    assert should_be_reviewed("test_utils.py") is False
    assert should_be_reviewed("subpkg/tests/test_api.py") is False

    # Cache, VCS, and build directories must be excluded
    assert should_be_reviewed(".git/config") is False
    assert should_be_reviewed(".pytest_cache/v/cache/nodeids") is False
    assert should_be_reviewed("pkg/__pycache__/main.cpython-39.pyc") is False
    assert should_be_reviewed(".checkpoints/thread_1.sqlite") is False
    assert should_be_reviewed("node_modules/axios/index.js") is False

    # Binary and lock files must be excluded
    assert should_be_reviewed("poetry.lock") is False
    assert should_be_reviewed("assets/logo.png") is False
    assert should_be_reviewed("data/db.sqlite3") is False


def test_reviewer_and_verifier_polyglot_hash_coverage(polyglot_repo):
    """Verify that ReviewerAgent hashes all modified polyglot production files and verifier validates them."""
    verifier = IndependentVerifier(str(polyglot_repo))
    baseline = verifier.capture_baseline(run_tests=True)

    reviewer = ReviewerAgent(str(polyglot_repo))
    reviewer.llm.is_available = lambda: False
    state: AgentState = {
        "task": "Update polyglot stack",
        "repo_path": str(polyglot_repo),
        "relevant_files": ["src/app.py", "src/client.js", "db/schema.sql", "scripts/deploy.sh"],
        "baseline_tests": baseline["baseline_tests"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
    }
    review_res = reviewer.review_code(state)
    assert review_res.approved is True
    # Ensure all polyglot files are cryptographically hashed
    assert "src/app.py" in review_res.reviewed_file_hashes
    assert "src/client.js" in review_res.reviewed_file_hashes
    assert "db/schema.sql" in review_res.reviewed_file_hashes
    assert "scripts/deploy.sh" in review_res.reviewed_file_hashes

    # Verification passes when all modified production files match reviewer hashes
    state["review_result"] = review_res
    state["coder_result"] = CoderResult(
        files_modified=["src/app.py", "src/client.js", "db/schema.sql", "scripts/deploy.sh"],
        patches={},
        rationale="Polyglot updates",
    )
    v_res = verifier.verify(state)
    assert v_res.reviewer_approved is True
    assert v_res.outcome == WorkflowOutcome.COMPLETED_SUCCESSFULLY


def test_unreviewed_production_file_rejected_by_verifier(polyglot_repo):
    """Verify that if a non-Python production file (e.g. .sql or .js) is modified without reviewer audit,
    the verifier fails reviewer approval and rejects handover.
    """
    verifier = IndependentVerifier(str(polyglot_repo))
    baseline = verifier.capture_baseline(run_tests=False)

    reviewer = ReviewerAgent(str(polyglot_repo))
    # Reviewer only audited Python file
    state_for_reviewer: AgentState = {
        "task": "Update app",
        "repo_path": str(polyglot_repo),
        "relevant_files": ["src/app.py"],
        "baseline_tests": baseline["baseline_tests"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
    }
    review_res = reviewer.review_code(state_for_reviewer)

    # State for verification: both app.py and db/schema.sql were in task scope and modified by Coder
    state_for_verifier: AgentState = {
        "task": "Update app and schema",
        "repo_path": str(polyglot_repo),
        "relevant_files": ["src/app.py", "db/schema.sql"],
        "baseline_tests": baseline["baseline_tests"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
        "review_result": review_res,
        "coder_result": CoderResult(
            files_modified=["src/app.py", "db/schema.sql"],
            patches={},
            rationale="Added SQL schema without reviewer audit",
        ),
    }

    v_res = verifier.verify(state_for_verifier)
    assert v_res.reviewer_approved is False
    assert v_res.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert any("db/schema.sql" in reason and ("never audited" in reason.lower() or "incomplete" in reason.lower()) for reason in v_res.failure_reasons)


def test_reviewer_hash_equality_against_verified_manifest_detects_post_review_mutation(polyglot_repo):
    """Verify that if a file is audited by the Reviewer, but is altered on disk before final verification,
    the verifier detects hash mismatch against verified_manifest and rejects approval (Integrity enforcement).
    """
    verifier = IndependentVerifier(str(polyglot_repo))
    baseline = verifier.capture_baseline(run_tests=True)

    reviewer = ReviewerAgent(str(polyglot_repo))
    reviewer.llm.is_available = lambda: False
    state: AgentState = {
        "task": "Update app and client",
        "repo_path": str(polyglot_repo),
        "relevant_files": ["src/app.py", "src/client.js"],
        "baseline_tests": baseline["baseline_tests"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
    }
    review_res = reviewer.review_code(state)
    assert review_res.approved is True
    assert "src/app.py" in review_res.reviewed_file_hashes
    assert "src/client.js" in review_res.reviewed_file_hashes

    # Post-review mutation: file is altered on disk BEFORE verifier.verify() is executed
    (polyglot_repo / "src" / "client.js").write_text("function getAnswer() { return 999; } // Tampered post-review\n", encoding="utf-8")

    state["review_result"] = review_res
    state["coder_result"] = CoderResult(
        files_modified=["src/app.py", "src/client.js"],
        patches={},
        rationale="Update app and client",
    )

    v_res = verifier.verify(state)
    assert v_res.reviewer_approved is False
    assert v_res.review_hashes_valid is False
    assert v_res.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
    assert any("src/client.js" in reason and "modified after review" in reason for reason in v_res.failure_reasons)


def test_extensionless_production_files_reviewed_and_verified():
    """Verify that extensionless production files (Dockerfile, Makefile, Procfile)
    are included in reviewable files, audited by ReviewerAgent, and verified by IndependentVerifier.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        (repo / "tests").mkdir(parents=True, exist_ok=True)
        (repo / "Dockerfile").write_text("FROM python:3.9-slim\nWORKDIR /app\n", encoding="utf-8")
        (repo / "Makefile").write_text("test:\n\tpytest tests/\n", encoding="utf-8")
        (repo / "Procfile").write_text("web: python -m app\n", encoding="utf-8")
        (repo / "app.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")
        (repo / "tests" / "test_app.py").write_text("from app import run\ndef test_ok():\n    assert run() == 'ok'\n", encoding="utf-8")

        verifier = IndependentVerifier(str(repo))
        baseline = verifier.capture_baseline(run_tests=True)

        # Coder modifies Dockerfile and Makefile
        (repo / "Dockerfile").write_text("FROM python:3.11-slim\nWORKDIR /app\nCOPY . /app\n", encoding="utf-8")
        (repo / "Makefile").write_text("test:\n\tpytest -q tests/\n", encoding="utf-8")

        reviewer = ReviewerAgent(str(repo))
        reviewer.llm.is_available = lambda: False
        state: AgentState = {
            "task": "Upgrade base container and update Makefile flags",
            "repo_path": str(repo),
            "relevant_files": ["Dockerfile", "Makefile"],
            "baseline_tests": baseline["baseline_tests"],
            "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
            "coder_result": CoderResult(
                files_modified=["Dockerfile", "Makefile"],
                patches={},
                rationale="Container and build updates",
            ),
        }

        review_res = reviewer.review_code(state)
        assert review_res.approved is True
        # Verify extensionless files are present in reviewed_file_hashes
        assert "Dockerfile" in review_res.reviewed_file_hashes
        assert "Makefile" in review_res.reviewed_file_hashes

        state["review_result"] = review_res
        v_res = verifier.verify(state)
        assert v_res.reviewer_approved is True
        assert v_res.review_hashes_valid is True
        assert v_res.outcome == WorkflowOutcome.COMPLETED_SUCCESSFULLY


def test_unreviewed_extensionless_file_created_on_disk_caught_and_rejected():
    """Verify that an extensionless production file created directly on disk
    is detected by the verifier's filesystem diff and rejected if omitted from reviewer audit.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        (repo / "tests").mkdir(parents=True, exist_ok=True)
        (repo / "app.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")
        (repo / "tests" / "test_app.py").write_text("from app import run\ndef test_ok():\n    assert run() == 'ok'\n", encoding="utf-8")

        verifier = IndependentVerifier(str(repo))
        baseline = verifier.capture_baseline(run_tests=True)

        # Coder creates a Dockerfile directly on disk, but omits it from coder_result
        (repo / "Dockerfile").write_text("FROM alpine:latest\nENTRYPOINT [\"sh\"]\n", encoding="utf-8")

        reviewer = ReviewerAgent(str(repo))
        reviewer.llm.is_available = lambda: False
        # Reviewer only audits app.py
        state_for_reviewer: AgentState = {
            "task": "Create container and service",
            "repo_path": str(repo),
            "relevant_files": ["app.py"],
            "baseline_tests": baseline["baseline_tests"],
            "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
        }
        review_res = reviewer.review_code(state_for_reviewer)
        assert "Dockerfile" not in review_res.reviewed_file_hashes

        # State for verifier: Coder omits Dockerfile from files_modified
        state_for_verifier: AgentState = {
            "task": "Create container and service",
            "repo_path": str(repo),
            "relevant_files": ["app.py", "Dockerfile"],
            "baseline_tests": baseline["baseline_tests"],
            "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
            "review_result": review_res,
            "coder_result": CoderResult(
                files_modified=["app.py"],
                patches={},
                rationale="Only claimed app.py",
            ),
        }

        v_res = verifier.verify(state_for_verifier)
        assert v_res.reviewer_approved is False
        assert v_res.review_hashes_valid is False
        assert v_res.outcome == WorkflowOutcome.COMPLETED_WITH_FAILURES
        assert any("Dockerfile" in reason and ("never audited" in reason.lower() or "incomplete" in reason.lower()) for reason in v_res.failure_reasons)


# ============================================================
# 2. Boundary B: TOCTOU Protection Tests
# ============================================================

def test_toctou_snapshot_manifest_and_tamper_detection(polyglot_repo):
    """Verify that verifier captures an immutable snapshot manifest and detects files modified during/after verification."""
    verifier = IndependentVerifier(str(polyglot_repo))
    baseline = verifier.capture_baseline(run_tests=True)

    reviewer = ReviewerAgent(str(polyglot_repo))
    reviewer.llm.is_available = lambda: False
    state: AgentState = {
        "task": "Verify clean state",
        "repo_path": str(polyglot_repo),
        "relevant_files": ["src/app.py"],
        "baseline_tests": baseline["baseline_tests"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
    }
    review_res = reviewer.review_code(state)
    state["review_result"] = review_res

    # 1. Normal verification generates root snapshot_hash and verified_manifest
    v_res = verifier.verify(state)
    assert v_res.verified is True
    assert v_res.snapshot_hash is not None
    assert len(v_res.snapshot_hash) == 64  # SHA-256
    assert "src/app.py" in v_res.verified_manifest

    # 2. manager_finalize_node records snapshot_hash in AgentState
    fin_updates = manager_finalize_node(dict(state, verification_result=v_res))
    assert fin_updates["snapshot_hash"] == v_res.snapshot_hash
    assert fin_updates["verified_manifest"] == v_res.verified_manifest


def test_toctou_file_mutation_fails_verification(polyglot_repo):
    """Verify TOCTOU integrity check catches background modification during verification execution."""
    verifier = IndependentVerifier(str(polyglot_repo))
    baseline = verifier.capture_baseline(run_tests=True)

    reviewer = ReviewerAgent(str(polyglot_repo))
    reviewer.llm.is_available = lambda: False
    state: AgentState = {
        "task": "Verify clean state",
        "repo_path": str(polyglot_repo),
        "relevant_files": ["src/app.py"],
        "baseline_tests": baseline["baseline_tests"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
    }
    review_res = reviewer.review_code(state)
    state["review_result"] = review_res

    v_res = verifier.verify(state)
    assert v_res.outcome == WorkflowOutcome.COMPLETED_SUCCESSFULLY

    # Simulate post-verification background tamper / race condition
    app_file = polyglot_repo / "src" / "app.py"
    app_file.write_text("def run():\n    return 'tampered_after_verification'\n", encoding="utf-8")

    # Audit verified_manifest against current filesystem state
    tampered_files = []
    for rel, exp_hash in v_res.verified_manifest.items():
        curr_h = hashlib.sha256((polyglot_repo / rel).read_bytes()).hexdigest()
        if curr_h != exp_hash:
            tampered_files.append(rel)

    assert "src/app.py" in tampered_files


def test_manager_finalize_node_toctou_drift_regenerates_report_with_failure(polyglot_repo):
    """Verify Issue A: If TOCTOU drift is detected during finalization,
    manager_finalize_node ensures the final report, workflow_outcome, and returned status
    all agree on COMPLETED_WITH_FAILURES and do NOT claim success.
    """
    verifier = IndependentVerifier(str(polyglot_repo))
    baseline = verifier.capture_baseline(run_tests=True)

    reviewer = ReviewerAgent(str(polyglot_repo))
    reviewer.llm.is_available = lambda: False
    state: AgentState = {
        "task": "Verify clean state",
        "repo_path": str(polyglot_repo),
        "relevant_files": ["src/app.py"],
        "baseline_tests": baseline["baseline_tests"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
        "iteration_count": 1,
    }
    review_res = reviewer.review_code(state)
    state["review_result"] = review_res

    # Normal verification succeeds
    v_res = verifier.verify(state)
    assert v_res.outcome == WorkflowOutcome.COMPLETED_SUCCESSFULLY

    # File drifts on disk BEFORE manager_finalize_node completes
    (polyglot_repo / "src" / "app.py").write_text("def run():\n    return 'tampered_during_finalization'\n", encoding="utf-8")

    # manager_finalize_node must catch drift, set status to failures, and report MUST agree
    fin_updates = manager_finalize_node(dict(state, verification_result=v_res))
    assert fin_updates["status"] == "completed_with_failures"
    assert fin_updates["workflow_outcome"] == "completed_with_failures"
    assert fin_updates["task_succeeded"] is False
    assert "COMPLETED_WITH_FAILURES" in fin_updates["final_report"]
    assert "COMPLETED_SUCCESSFULLY" not in fin_updates["final_report"]
    assert "TOCTOU race detected" in fin_updates["final_report"]


def test_empty_manifest_fails_closed_when_untracked_files_exist(polyglot_repo):
    """Verify Issue B: verify_manifest_intact fails closed if manifest is None,
    and catches untracked files when manifest is empty {}.
    """
    verifier = IndependentVerifier(str(polyglot_repo))

    # 1. Manifest is None -> Fails closed immediately
    intact_none, violations_none = verifier.verify_manifest_intact(None)
    assert intact_none is False
    assert any("manifest is None" in v for v in violations_none)

    # 2. Manifest is {} (empty), but repo contains files -> Fails closed (untracked files detected)
    intact_empty, violations_empty = verifier.verify_manifest_intact({})
    assert intact_empty is False
    assert any("manifest expected empty repository" in v for v in violations_empty)

    # 3. Manifest is {} (empty), and repo is genuinely empty -> Validates empty state
    with tempfile.TemporaryDirectory() as empty_dir:
        verifier_empty = IndependentVerifier(empty_dir)
        intact_clean, violations_clean = verifier_empty.verify_manifest_intact({})
        assert intact_clean is True
        assert len(violations_clean) == 0


def test_immutable_handover_artifact_creation_and_isolation(polyglot_repo):
    """Verify Fundamental Boundary: When verification clears, an immutable read-only
    handover bundle (.tar.gz) is created, recorded in the state, and isolated from live disk mutation.
    """
    verifier = IndependentVerifier(str(polyglot_repo))
    baseline = verifier.capture_baseline(run_tests=True)

    reviewer = ReviewerAgent(str(polyglot_repo))
    reviewer.llm.is_available = lambda: False
    state: AgentState = {
        "task": "Handover packaging task",
        "repo_path": str(polyglot_repo),
        "relevant_files": ["src/app.py"],
        "baseline_tests": baseline["baseline_tests"],
        "baseline_outcomes": baseline["baseline_outcomes"],
        "baseline_snapshot": baseline["baseline_snapshot"],
        "baseline_file_hashes": baseline["baseline_file_hashes"],
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
        "iteration_count": 1,
    }
    review_res = reviewer.review_code(state)
    state["review_result"] = review_res

    fin_updates = manager_finalize_node(state)
    assert fin_updates["status"] == "completed_successfully"
    assert fin_updates["task_succeeded"] is True

    # Handover artifact was created and recorded
    handover_path = fin_updates.get("handover_artifact")
    handover_hash = fin_updates.get("handover_hash")
    assert handover_path is not None
    assert handover_hash is not None
    assert Path(handover_path).exists()
    assert handover_path.endswith(".tar.gz")

    # Read-only permissions on handover bundle
    file_stat = os.stat(handover_path)
    assert (file_stat.st_mode & 0o222) == 0  # Write bits are stripped

    # Modifying live file on disk does NOT alter the sealed handover artifact
    orig_archive_hash = hashlib.sha256(Path(handover_path).read_bytes()).hexdigest()
    (polyglot_repo / "src" / "app.py").write_text("def run():\n    return 'mutated_after_handover'\n", encoding="utf-8")
    post_mutation_archive_hash = hashlib.sha256(Path(handover_path).read_bytes()).hexdigest()
    assert post_mutation_archive_hash == orig_archive_hash

    # Final report includes Section 8 Immutable Handover Artifact details
    assert "8. 📦 Immutable Handover Artifact" in fin_updates["final_report"]
    assert handover_path in fin_updates["final_report"]


# ============================================================
# 3. Boundary C: Cooperative Cancellation Tests
# ============================================================

def test_cooperative_cancellation_across_pipeline_nodes(polyglot_repo):
    """Verify that all pipeline nodes check cooperative cancellation flags immediately at entry
    and return status='cancelled' without executing costly LLM or disk operations.
    """
    cancelled_state: AgentState = {
        "task": "Cancelled task",
        "repo_path": str(polyglot_repo),
        "cancelled": True,
        "iteration_count": 0,
    }

    # Node 1: explore_repo_node
    res_explore = explore_repo_node(cancelled_state)
    assert res_explore.get("status") == "cancelled"
    assert res_explore.get("cancelled") is True

    # Node 2: manager_planner_node
    res_plan = manager_planner_node(cancelled_state)
    assert res_plan.get("status") == "cancelled"
    assert res_plan.get("cancelled") is True

    # Node 3: coder_node
    res_coder = coder_node(cancelled_state)
    assert res_coder.get("status") == "cancelled"
    assert res_coder.get("cancelled") is True

    # Node 4: graph_test_generator_node
    res_testgen = graph_test_generator_node(cancelled_state)
    assert res_testgen.get("status") == "cancelled"
    assert res_testgen.get("cancelled") is True

    # Node 5: sandbox_runner_node
    res_sandbox = sandbox_runner_node(cancelled_state)
    assert res_sandbox.get("status") == "cancelled"
    assert res_sandbox.get("cancelled") is True

    # Node 6: debugger_node
    res_dbg = debugger_node(cancelled_state)
    assert res_dbg.get("status") == "cancelled"
    assert res_dbg.get("cancelled") is True

    # Node 7: reviewer_node
    res_rev = reviewer_node(cancelled_state)
    assert res_rev.get("status") == "cancelled"
    assert res_rev.get("cancelled") is True

    # Node 8: manager_evaluate_node
    res_eval = manager_evaluate_node(cancelled_state)
    assert res_eval.get("status") == "cancelled"
    assert res_eval.get("cancelled") is True


def test_cooperative_cancellation_on_abort_requested_signal(polyglot_repo):
    """Verify abort_requested flag triggers immediate cooperative cancellation across nodes."""
    abort_state: AgentState = {
        "task": "Aborting task",
        "repo_path": str(polyglot_repo),
        "abort_requested": True,
    }

    res_coder = coder_node(abort_state)
    assert res_coder.get("cancelled") is True
    assert res_coder.get("status") == "cancelled"

    res_sandbox = sandbox_runner_node(abort_state)
    assert res_sandbox.get("cancelled") is True
    assert res_sandbox.get("status") == "cancelled"


# ============================================================
# 4. Boundary D: Centralized Retry Metering Tests
# ============================================================

def test_centralized_retry_metering_for_delegate_test_gen_and_sandbox():
    """Verify that manager_evaluate_node meters retries for delegate_test_gen and run_sandbox."""
    # 1. delegate_test_gen route consumes retry budget
    testgen_retry_state: AgentState = {
        "task": "Regenerate tests",
        "repo_path": ".",
        "iteration_count": 1,
        "max_iterations": 5,
        "test_results": TestResult(
            passed=False,
            exit_code=1,
            stdout="AssertionError in test suite",
            stderr="",
            failed_tests=["test_invalid_contract"],
            error_summary="Flawed test expectation",
        ),
        "debug_result": DebugResult(
            root_cause="Test expectation contradicted specification",
            remediation_plan="Update test contract",
            target_fix_agent="test_generator",
        ),
    }
    up_testgen = manager_evaluate_node(testgen_retry_state)
    assert up_testgen["manager_decision"].next_action == "delegate_test_gen"
    assert up_testgen["iteration_count"] == 2
    assert up_testgen["review_result"] is None

    # 2. run_sandbox route consumes retry budget
    sandbox_retry_state: AgentState = {
        "task": "Rerun sandbox tests",
        "repo_path": ".",
        "iteration_count": 2,
        "max_iterations": 5,
        "force_sandbox_rerun": True,
    }
    up_sandbox = manager_evaluate_node(sandbox_retry_state)
    assert up_sandbox["manager_decision"].next_action == "run_sandbox"
    assert up_sandbox["iteration_count"] == 3
    assert up_sandbox["review_result"] is None


def test_retry_budget_exhaustion_blocks_test_gen_and_sandbox_rerun():
    """Verify that when iteration_count >= max_iterations, neither test_gen nor sandbox rerun
    can loop infinitely, and manager routes strictly to 'finalize'.
    """
    manager = ManagerPlannerAgent()

    # Exhausted budget with force_sandbox_rerun
    exhausted_sandbox_state: AgentState = {
        "task": "Sandbox rerun",
        "repo_path": ".",
        "iteration_count": 5,
        "max_iterations": 5,
        "force_sandbox_rerun": True,
    }
    decision = manager.evaluate_and_route(exhausted_sandbox_state)
    assert decision.next_action == "finalize"
    assert "max iterations" in decision.reasoning.lower()

    # Exhausted budget with debugger targeting test_generator
    exhausted_testgen_state: AgentState = {
        "task": "Test gen rerun",
        "repo_path": ".",
        "iteration_count": 5,
        "max_iterations": 5,
        "test_results": TestResult(passed=False, exit_code=1, stdout="FAIL", stderr="", failed_tests=["t1"]),
        "debug_result": DebugResult(
            root_cause="Flawed test",
            remediation_plan="Regenerate",
            target_fix_agent="test_generator",
        ),
    }
    decision2 = manager.evaluate_and_route(exhausted_testgen_state)
    assert decision2.next_action == "finalize"
    assert "max iterations" in decision2.reasoning.lower()


def test_debugger_node_does_not_double_count_retries():
    """Verify debugger_node preserves iteration_count without incrementing it,
    avoiding double-counting with manager_evaluate_node.
    """
    state_at_iter_2: AgentState = {
        "task": "Fix bug",
        "repo_path": ".",
        "iteration_count": 2,
        "test_results": TestResult(
            passed=False,
            exit_code=1,
            stdout="AssertionError",
            stderr="",
            failed_tests=["test_bug"],
            error_summary="Failed assertion",
        ),
    }
    dbg_updates = debugger_node(state_at_iter_2)
    # Must remain exactly 2, not 3!
    assert dbg_updates["iteration_count"] == 2


# ============================================================
# 5. Strict Sovereign Success Condition Tests
# ============================================================

def test_is_task_successful_true_when_all_sovereign_evidence_cleared(polyglot_repo):
    """Verify is_task_successful returns True when all sovereign verification evidence passes."""
    state: AgentState = {
        "task": "Build feature",
        "repo_path": str(polyglot_repo),
        "status": "evaluating",
    }
    verification = VerificationResult(
        verified=True,
        outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
        baseline_status=BaselineVerificationStatus.VERIFIED,
        baseline_inventory_count=3,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        no_blocking_issues=True,
        review_hashes_valid=True,
        toctou_valid=True,
        baseline_regressions=[],
        failure_reasons=[],
        summary="Success",
    )
    assert is_task_successful(state, verification) is True


def test_is_task_successful_false_on_cancelled_or_blocked_state(polyglot_repo):
    """Verify is_task_successful returns False if state was cancelled or blocked."""
    verification = VerificationResult(
        verified=True,
        outcome=WorkflowOutcome.COMPLETED_SUCCESSFULLY,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        no_blocking_issues=True,
        review_hashes_valid=True,
        toctou_valid=True,
        summary="Success",
    )

    # Cancelled status
    assert is_task_successful({"status": "cancelled"}, verification) is False
    assert is_task_successful({"cancelled": True}, verification) is False
    assert is_task_successful({"abort_requested": True}, verification) is False
    # Blocked status
    assert is_task_successful({"status": "blocked"}, verification) is False
    assert is_task_successful({"blocked": True}, verification) is False


def test_is_task_successful_false_when_tests_or_review_fail(polyglot_repo):
    """Verify that even if Coder claims task is complete, is_task_successful returns False
    if tests failed or reviewer raised blocking issues.
    """
    state: AgentState = {
        "task": "Build feature",
        "repo_path": str(polyglot_repo),
        "coder_result": CoderResult(
            rationale="I am done and all methods are implemented!",
            files_modified=["src/app.py"],
            methods_implemented=["run"],
        ),
    }

    # Case 1: Tests failed
    v_test_failed = VerificationResult(
        verified=False,
        outcome=WorkflowOutcome.COMPLETED_WITH_FAILURES,
        tests_passed=False,
        baseline_tests_passed=False,
        generated_tests_passed=False,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        no_blocking_issues=True,
        review_hashes_valid=True,
        toctou_valid=True,
        failure_reasons=["Sandbox tests failed with exit code 1"],
        summary="Failed tests",
    )
    assert is_task_successful(state, v_test_failed) is False

    # Case 2: Reviewer rejected / blocking issues
    v_review_rejected = VerificationResult(
        verified=False,
        outcome=WorkflowOutcome.COMPLETED_WITH_FAILURES,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=False,
        no_blocking_issues=False,
        review_hashes_valid=True,
        toctou_valid=True,
        failure_reasons=["Reviewer rejected: ZeroDivisionError possible"],
        summary="Rejected by reviewer",
    )
    assert is_task_successful(state, v_review_rejected) is False

    # Case 3: TOCTOU violation
    v_toctou_failed = VerificationResult(
        verified=False,
        outcome=WorkflowOutcome.COMPLETED_WITH_FAILURES,
        tests_passed=True,
        baseline_tests_passed=True,
        generated_tests_passed=True,
        lint_checks_passed=True,
        tests_preserved=True,
        git_diff_clean=True,
        reviewer_approved=True,
        no_blocking_issues=True,
        review_hashes_valid=True,
        toctou_valid=False,
        failure_reasons=["TOCTOU violation: files modified on disk during verification"],
        summary="TOCTOU violation",
    )
    assert is_task_successful(state, v_toctou_failed) is False


def test_manager_finalize_node_records_task_succeeded_in_state(polyglot_repo):
    """Verify manager_finalize_node evaluates is_task_successful and records task_succeeded in state."""
    verifier = IndependentVerifier(str(polyglot_repo))
    baseline = verifier.capture_baseline(run_tests=True)
    reviewer = ReviewerAgent(str(polyglot_repo))
    reviewer.llm.is_available = lambda: False

    state: AgentState = {
        "task": "Clean test task",
        "repo_path": str(polyglot_repo),
        "relevant_files": ["src/app.py"],
        "baseline_tests": baseline["baseline_tests"],
        "baseline_snapshot": baseline.get("baseline_snapshot"),
        "baseline_outcomes": baseline.get("baseline_outcomes"),
        "test_results": TestResult(passed=True, exit_code=0, stdout="OK", stderr=""),
    }
    review_res = reviewer.review_code(state)
    state["review_result"] = review_res

    fin_updates = manager_finalize_node(state)
    assert fin_updates["task_succeeded"] is True
    assert fin_updates["workflow_outcome"] == "completed_successfully"


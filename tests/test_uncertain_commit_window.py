"""Comprehensive Verification of the 4-Phase Distributed Transaction Idempotency State Machine
and Uncertain Commit Window Reconciliation.

Addresses the distributed transaction problem across two storage systems:
1. SQLite WAL Journal (Execution Ledger)
2. POSIX Filesystem (Target Inodes & Directory Entries)

Verifies:
1. PREPARED -> APPLYING -> VERIFY -> COMPLETED state machine transitions.
2. Crash Window A: Physical file replacement succeeds, but process crashes before
   ledger commits COMPLETED (ledger left in APPLYING). Resumed node reconciles
   ledger with actual physical disk state rather than blindly retrying.
3. Crash Window B: Process crashes before physical replacement touches disk (ledger in APPLYING).
   Reconciliation detects PHYSICAL_DISK_UNMODIFIED and safely completes the write.
4. Crash Window C: External drift occurs during crash window (disk hash matches neither initial
   nor expected hash). Reconciler detects UNRECONCILED_DRIFT and halts safely.
5. Crash during surgical replace_snippet uncertain window reconciles seamlessly without
   raising ValueError("Target snippet not found").
6. Crash during delete_file uncertain window reconciles seamlessly without raising FileNotFoundError.
"""

import tempfile
from pathlib import Path
import pytest

from agent.core.idempotency import (
    IdempotencyJournal,
    AtomicFilePatcher,
    generate_idempotency_key,
    IdempotencyPhase,
)
from agent.tools.execution_layer import ToolExecutionLayer
from agent.tools.approval import RecordedApprovalGate


def test_state_machine_phases_lifecycle():
    """Verify explicit transitions across PREPARED, APPLYING, VERIFY, and COMPLETED phases."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        db_path = repo_path / ".checkpoints" / "journal.sqlite"
        journal = IdempotencyJournal(db_path=str(db_path))

        key = "thread-1:write_file:module.py:iter0:hash123"
        target = "src/module.py"
        expected_hash = "abc123expected"
        initial_hash = "000initial"

        # Phase 1: PREPARED
        journal.record_prepared(
            idempotency_key=key,
            action_type="file_write",
            target=target,
            payload_hash="hash123",
            expected_hash=expected_hash,
            initial_hash=initial_hash,
        )
        rec = journal.get_execution(key)
        assert rec is not None
        assert rec["status"] == "PREPARED"
        assert rec["phase"] == "PREPARED"
        assert rec["expected_hash"] == expected_hash
        assert rec["initial_hash"] == initial_hash
        assert rec["started_at"] is not None
        assert rec["completed_at"] is None

        # Phase 2: APPLYING
        journal.record_applying(key)
        rec = journal.get_execution(key)
        assert rec["status"] == "APPLYING"
        assert rec["phase"] == "APPLYING"

        # Phase 3: VERIFY
        journal.record_verify(key, verified_hash=expected_hash)
        rec = journal.get_execution(key)
        assert rec["status"] == "VERIFY"
        assert rec["phase"] == "VERIFY"
        assert rec["verified_hash"] == expected_hash

        # Phase 4: COMPLETED
        output = {"bytes_written": 128, "status": "atomically_applied"}
        journal.record_execution_completion(key, output=output)
        rec = journal.get_execution(key)
        assert rec["status"] == "COMPLETED"
        assert rec["phase"] == "COMPLETED"
        assert rec["output"] == output
        assert rec["completed_at"] is not None
        assert journal.is_execution_completed(key) is True


def test_reconcile_uncertain_commit_window_physical_write_succeeded():
    """CRITICAL TEST: Physical file replacement succeeded, but process crashed before ledger recorded COMPLETED.

    State on recovery:
    - Physical file on disk is modified to expected content.
    - Ledger status is left in APPLYING.
    - LangGraph checkpoint potentially stale.
    Recovery MUST inspect physical disk, verify content hash, and transition ledger to COMPLETED
    without redundant physical rewrite or file corruption.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        db_path = repo_path / ".checkpoints" / "journal.sqlite"
        journal = IdempotencyJournal(db_path=str(db_path))
        patcher = AtomicFilePatcher(str(repo_path), journal=journal)

        exec_layer = ToolExecutionLayer(
            repo_path=str(repo_path),
            approval_gate=RecordedApprovalGate(default_approve=True),
            patcher=patcher,
        )

        file_rel = "service/auth.py"
        target_abs = repo_path / file_rel
        target_abs.parent.mkdir(parents=True, exist_ok=True)

        initial_content = "def authenticate():\n    return False\n"
        target_abs.write_text(initial_content, encoding="utf-8")
        initial_hash = patcher.compute_hash(initial_content)

        new_content = "def authenticate():\n    return True  # patched\n"
        expected_hash = patcher.compute_hash(new_content)
        action_key = "action:write_file:service/auth.py:iter0"

        # SIMULATE THE UNCERTAIN COMMIT WINDOW CRASH:
        # 1. Intent is recorded in ledger as PREPARED
        journal.record_prepared(
            idempotency_key=action_key,
            action_type="file_write",
            target=file_rel,
            payload_hash=expected_hash,
            expected_hash=expected_hash,
            initial_hash=initial_hash,
        )
        # 2. Transition to APPLYING
        journal.record_applying(action_key)

        # 3. Physical filesystem rename succeeds!
        target_abs.write_text(new_content, encoding="utf-8")

        # 4. CRASH OCCURS RIGHT HERE!
        # The ledger is still 'APPLYING' and NOT 'COMPLETED'.
        rec_before = journal.get_execution(action_key)
        assert rec_before["status"] == "APPLYING"
        assert not journal.is_execution_completed(action_key)

        # 5. Recovery / workflow resumption re-executes write_file on resumed execution layer
        resumed_exec_layer = ToolExecutionLayer(
            repo_path=str(repo_path),
            approval_gate=RecordedApprovalGate(default_approve=True),
            patcher=patcher,
        )

        # Resumed tool call
        result = resumed_exec_layer.write_file(file_rel, new_content, action_id=action_key)
        assert result is True

        # VERIFICATION OF THE RECONCILED STATE:
        # Ledger MUST now be COMPLETED with reconciled_from_crash = True
        rec_after = journal.get_execution(action_key)
        assert rec_after["status"] == "COMPLETED"
        assert rec_after["phase"] == "COMPLETED"
        assert rec_after["reconciled_from_crash"] is True
        assert rec_after["verified_hash"] == expected_hash

        # Physical file content is intact and was verified against physical disk hash
        assert target_abs.read_text(encoding="utf-8") == new_content

        # Audit log reflects successful post-crash physical reconciliation
        assert any("reconciled post-crash" in log["message"] for log in resumed_exec_layer.audit_log)


def test_reconcile_uncertain_commit_window_physical_write_never_touched_disk():
    """Process crashed while in APPLYING, but physical write never touched disk (file still initial).

    Recovery MUST detect that physical disk was unmodified and safely proceed with the atomic write.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        db_path = repo_path / ".checkpoints" / "journal.sqlite"
        journal = IdempotencyJournal(db_path=str(db_path))
        patcher = AtomicFilePatcher(str(repo_path), journal=journal)

        exec_layer = ToolExecutionLayer(
            repo_path=str(repo_path),
            approval_gate=RecordedApprovalGate(default_approve=True),
            patcher=patcher,
        )

        file_rel = "config/app.py"
        target_abs = repo_path / file_rel
        target_abs.parent.mkdir(parents=True, exist_ok=True)

        initial_content = "DEBUG = True\n"
        target_abs.write_text(initial_content, encoding="utf-8")
        initial_hash = patcher.compute_hash(initial_content)

        new_content = "DEBUG = False\n"
        expected_hash = patcher.compute_hash(new_content)
        action_key = "action:write_file:config/app.py:iter0"

        # Simulate crash before physical write
        journal.record_prepared(
            idempotency_key=action_key,
            action_type="file_write",
            target=file_rel,
            payload_hash=expected_hash,
            expected_hash=expected_hash,
            initial_hash=initial_hash,
        )
        journal.record_applying(action_key)
        # Note: Physical target_abs is STILL initial_content!

        reconciled, reason, _ = journal.reconcile_with_physical_disk(action_key, repo_path)
        assert reconciled is False
        assert reason == "PHYSICAL_DISK_UNMODIFIED"

        # When resumed execution layer runs write_file, it detects unmodified disk and applies patch
        resumed_exec_layer = ToolExecutionLayer(
            repo_path=str(repo_path),
            approval_gate=RecordedApprovalGate(default_approve=True),
            patcher=patcher,
        )
        assert resumed_exec_layer.write_file(file_rel, new_content, action_id=action_key) is True

        # Now disk is updated and ledger is COMPLETED
        assert target_abs.read_text(encoding="utf-8") == new_content
        rec = journal.get_execution(action_key)
        assert rec["status"] == "COMPLETED"


def test_reconcile_uncertain_commit_window_detects_unreconciled_drift():
    """Process crashed in APPLYING, but disk was modified by an external rogue process to unexpected content."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        db_path = repo_path / ".checkpoints" / "journal.sqlite"
        journal = IdempotencyJournal(db_path=str(db_path))
        patcher = AtomicFilePatcher(str(repo_path), journal=journal)

        file_rel = "data/store.py"
        target_abs = repo_path / file_rel
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        target_abs.write_text("INITIAL_STATE\n", encoding="utf-8")
        initial_hash = patcher.compute_hash("INITIAL_STATE\n")

        expected_hash = patcher.compute_hash("EXPECTED_STATE\n")
        action_key = "action:write_file:data/store.py:iter0"

        journal.record_prepared(
            action_key, "file_write", file_rel, expected_hash, expected_hash, initial_hash
        )
        journal.record_applying(action_key)

        # Rogue mutation
        target_abs.write_text("ROGUE_THIRD_PARTY_MUTATION\n", encoding="utf-8")

        reconciled, reason, _ = journal.reconcile_with_physical_disk(action_key, repo_path)
        assert reconciled is False
        assert reason == "UNRECONCILED_DRIFT"


def test_replace_snippet_uncertain_commit_window_reconciliation():
    """replace_snippet succeeds physically, but process crashes before ledger commits COMPLETED.

    Resumed replace_snippet must reconcile against physical disk state without throwing
    ValueError("Target snippet not found in file").
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        db_path = repo_path / ".checkpoints" / "journal.sqlite"
        journal = IdempotencyJournal(db_path=str(db_path))
        patcher = AtomicFilePatcher(str(repo_path), journal=journal)

        exec_layer = ToolExecutionLayer(
            repo_path=str(repo_path),
            approval_gate=RecordedApprovalGate(default_approve=True),
            patcher=patcher,
        )

        file_rel = "calculator/ops.py"
        target_abs = repo_path / file_rel
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        target_abs.write_text("def op(a, b):\n    return a * b\n", encoding="utf-8")

        old_snippet = "return a * b"
        new_snippet = "return round(a * b, 4)"
        action_key = "action:replace_snippet:ops:iter0"

        # First execution succeeds and transitions through all 4 states
        assert exec_layer.replace_snippet(file_rel, old_snippet, new_snippet, action_id=action_key) is True
        assert new_snippet in target_abs.read_text(encoding="utf-8")

        # Now simulate crash recovery where in-memory state is wiped and ledger was left in APPLYING
        journal.record_applying(action_key)
        assert not journal.is_execution_completed(action_key)

        resumed_layer = ToolExecutionLayer(
            repo_path=str(repo_path),
            approval_gate=RecordedApprovalGate(default_approve=True),
            patcher=patcher,
        )

        # Resumed call detects physical presence of new_snippet and reconciles ledger
        assert resumed_layer.replace_snippet(file_rel, old_snippet, new_snippet, action_id=action_key) is True
        assert journal.is_execution_completed(action_key)


def test_delete_file_uncertain_commit_window_reconciliation():
    """Physical file is unlinked, but process crashes before ledger records COMPLETED.

    Resumed delete_file must NOT crash with FileNotFoundError, but must reconcile to COMPLETED.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        db_path = repo_path / ".checkpoints" / "journal.sqlite"
        journal = IdempotencyJournal(db_path=str(db_path))
        patcher = AtomicFilePatcher(str(repo_path), journal=journal)

        file_rel = "temp_delete_me.py"
        target_abs = repo_path / file_rel
        target_abs.write_text("# delete me", encoding="utf-8")
        action_key = "action:delete:temp_delete_me:iter0"

        # Simulate crash: ledger is in APPLYING with expected_hash='DELETED', file was unlinked
        journal.record_prepared(
            action_key, "delete_file", file_rel, "DELETED", expected_hash="DELETED", initial_hash="hash123"
        )
        journal.record_applying(action_key)
        target_abs.unlink()

        resumed_layer = ToolExecutionLayer(
            repo_path=str(repo_path),
            approval_gate=RecordedApprovalGate(default_approve=True),
            patcher=patcher,
        )

        assert resumed_layer.delete_file(file_rel, action_id=action_key) is True
        assert journal.is_execution_completed(action_key)
        rec = journal.get_execution(action_key)
        assert rec["status"] == "COMPLETED"
        assert rec["reconciled_from_crash"] is True


"""Tests for Execution-Level Idempotency and Persistent Ledger Recovery.

Verifies the critical architectural boundary between in-memory LangGraph reducers
and physical execution idempotency:
1. Deduplicating in-memory action history (reducers) does NOT prevent physical side effects
   if a crash occurs between tool execution and state checkpointing.
2. ToolExecutionLayer and AtomicFilePatcher must consult the physical file hash and
   persistent SQLite execution_ledger before executing side-effects.
3. Resumed nodes must recover gracefully from post-crash states (e.g. surgical snippet
   replacements where old_snippet was already replaced prior to the crash).
"""

import tempfile
from pathlib import Path
import pytest

from agent.core.idempotency import (
    IdempotencyJournal,
    AtomicFilePatcher,
    generate_idempotency_key,
)
from agent.tools.execution_layer import ToolExecutionLayer
from agent.tools.file_tools import FileToolHandler
from agent.tools.permissions import PermissionPolicy, ToolActionType, RiskLevel
from agent.tools.approval import RecordedApprovalGate


def test_idempotency_key_generation_deterministic():
    """Verify idempotency key generation is stable and collision-resistant."""
    key1 = generate_idempotency_key("write_file", "calculator/core.py", "def add(): pass", thread_id="t-1", iteration=0)
    key2 = generate_idempotency_key("write_file", "calculator/core.py", "def add(): pass", thread_id="t-1", iteration=0)
    assert key1 == key2

    # Different iteration yields different key
    key_iter1 = generate_idempotency_key("write_file", "calculator/core.py", "def add(): pass", thread_id="t-1", iteration=1)
    assert key1 != key_iter1

    # Different payload yields different key
    key_diff_payload = generate_idempotency_key("write_file", "calculator/core.py", "def sub(): pass", thread_id="t-1", iteration=0)
    assert key1 != key_diff_payload

    # Target path normalization
    key_norm = generate_idempotency_key("write_file", "calculator\\core.py", "def add(): pass", thread_id="t-1", iteration=0)
    assert key1 == key_norm


def test_execution_ledger_lifecycle():
    """Verify execution ledger records transitions from IN_PROGRESS to COMPLETED or FAILED."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_ledger.sqlite"
        journal = IdempotencyJournal(db_path=str(db_path))

        key = "thread-1:write_file:core.py:iter0:hash123"
        assert not journal.is_execution_completed(key)

        # 1. Start execution
        journal.record_execution_start(key, "write_file", "core.py", "hash123")
        rec = journal.get_execution(key)
        assert rec is not None
        assert rec["status"] == "IN_PROGRESS"
        assert rec["started_at"] is not None
        assert rec["completed_at"] is None

        # 2. Complete execution
        output_data = {"bytes_written": 42, "checksum": "abc"}
        journal.record_execution_completion(key, output_data)
        assert journal.is_execution_completed(key)

        rec_done = journal.get_execution(key)
        assert rec_done["status"] == "COMPLETED"
        assert rec_done["output"] == output_data
        assert rec_done["completed_at"] is not None

        # 3. Test failure recording
        fail_key = "thread-1:exec_cmd:failing_cmd:iter0:hash456"
        journal.record_execution_start(fail_key, "exec_cmd", "failing_cmd", "hash456")
        journal.record_execution_failure(fail_key, "Process terminated with exit code 1")

        assert not journal.is_execution_completed(fail_key)
        rec_fail = journal.get_execution(fail_key)
        assert rec_fail["status"] == "FAILED"
        assert rec_fail["output"] == {"error": "Process terminated with exit code 1"}


def test_write_file_crash_window_idempotency():
    """Simulate crash between physical write_file execution and checkpointing.

    Upon resumption, write_file must detect that the on-disk file content
    already matches the expected content, skipping the rewrite and returning True.
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

        target_rel = "src/module.py"
        code = "def calculate():\n    return 42\n"
        action_key = "action:write_file:src/module.py:iter0"

        # 1. First execution: writes file atomically
        success = exec_layer.write_file(target_rel, code, action_id=action_key)
        assert success is True
        target_abs = repo_path / target_rel
        assert target_abs.exists()
        assert target_abs.read_text(encoding="utf-8") == code

        # Verify ledger has COMPLETED
        assert journal.is_execution_completed(action_key)

        # 2. Simulate process crash:
        # In-memory audit log and LangGraph state are wiped!
        exec_layer_resumed = ToolExecutionLayer(
            repo_path=str(repo_path),
            approval_gate=RecordedApprovalGate(default_approve=True),
            patcher=patcher,
        )
        assert len(exec_layer_resumed.audit_log) == 0

        # 3. Workflow resumption re-invokes the write_file tool
        resumed_success = exec_layer_resumed.write_file(target_rel, code, action_id=action_key)
        assert resumed_success is True

        # Audit log must reflect idempotent replay skip
        assert any("idempotent replay" in log["message"] for log in exec_layer_resumed.audit_log)


def test_replace_snippet_crash_recovery():
    """Simulate crash during surgical replace_snippet.

    If old_snippet was already replaced by new_snippet before the crash,
    resumption must NOT crash with ValueError("Target snippet not found"),
    but must detect that new_snippet is present and succeed idempotently.
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

        file_rel = "calculator/core.py"
        target_abs = repo_path / file_rel
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        initial_code = (
            "class Calculator:\n"
            "    def divide(self, a, b):\n"
            "        return a / b\n"
        )
        target_abs.write_text(initial_code, encoding="utf-8")

        old_snippet = "return a / b"
        new_snippet = (
            "if b == 0:\n"
            "            raise ValueError('Cannot divide by zero')\n"
            "        return a / b"
        )
        action_key = "action:replace_snippet:calc_divide:iter0"

        # 1. Execute replace_snippet
        res = exec_layer.replace_snippet(file_rel, old_snippet, new_snippet, action_id=action_key)
        assert res is True
        assert new_snippet in target_abs.read_text(encoding="utf-8")
        assert old_snippet not in target_abs.read_text(encoding="utf-8").replace(new_snippet, "")

        # 2. Simulate crash immediately after physical replace:
        # Node re-executes replace_snippet with identical parameters on resumed execution layer
        resumed_exec_layer = ToolExecutionLayer(
            repo_path=str(repo_path),
            approval_gate=RecordedApprovalGate(default_approve=True),
            patcher=patcher,
        )

        # In naive execution, old_snippet is missing -> throws ValueError!
        # In our execution-idempotent layer, it detects that new_snippet is already present
        resumed_res = resumed_exec_layer.replace_snippet(
            file_rel, old_snippet, new_snippet, action_id=action_key
        )
        assert resumed_res is True
        assert any(
            "idempotent replay" in log["message"] or "post-crash" in log["message"]
            for log in resumed_exec_layer.audit_log
        )


def test_delete_file_crash_recovery():
    """Simulate crash during file deletion.

    If file was deleted before the crash, re-executing delete_file on resume
    must NOT raise FileNotFoundError, but return True idempotently.
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

        file_rel = "temp_scratch.py"
        target_abs = repo_path / file_rel
        target_abs.write_text("# Scratch file", encoding="utf-8")
        action_key = "action:delete:temp_scratch:iter0"

        # 1. Delete file
        assert exec_layer.delete_file(file_rel, action_id=action_key) is True
        assert not target_abs.exists()

        # 2. Resumed execution layer re-invokes delete_file
        resumed_exec_layer = ToolExecutionLayer(
            repo_path=str(repo_path),
            approval_gate=RecordedApprovalGate(default_approve=True),
            patcher=patcher,
        )

        resumed_success = resumed_exec_layer.delete_file(file_rel, action_id=action_key)
        assert resumed_success is True
        assert any("already completed pre-crash" in log["message"] for log in resumed_exec_layer.audit_log)


def test_execute_command_idempotency_caching():
    """Verify that command execution with action_id caches output in the persistent ledger."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        db_path = repo_path / ".checkpoints" / "journal.sqlite"
        journal = IdempotencyJournal(db_path=str(db_path))
        patcher = AtomicFilePatcher(str(repo_path), journal=journal)

        policy = PermissionPolicy(
            allowed_command_prefixes=("python3", "echo"),
            require_human_approval_for=(),
        )
        exec_layer = ToolExecutionLayer(
            repo_path=str(repo_path),
            policy=policy,
            approval_gate=RecordedApprovalGate(default_approve=True),
            patcher=patcher,
        )

        cmd = "echo 'unique_build_timestamp'"
        action_key = "cmd:build:timestamp:001"

        # 1. Execute command
        res1 = exec_layer.execute_command(cmd, action_id=action_key)
        assert res1["exit_code"] == 0
        assert "unique_build_timestamp" in res1["stdout"]

        # 2. Replay with new execution layer instance (simulating restart)
        resumed_layer = ToolExecutionLayer(
            repo_path=str(repo_path),
            policy=policy,
            approval_gate=RecordedApprovalGate(default_approve=True),
            patcher=patcher,
        )
        res2 = resumed_layer.execute_command(cmd, action_id=action_key)
        assert res2["exit_code"] == 0
        assert res2["stdout"] == res1["stdout"]
        assert any("idempotent replay" in log["message"] for log in resumed_layer.audit_log)


def test_file_tool_handler_integration():
    """Verify FileToolHandler forwards idempotency parameters seamlessly."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        handler = FileToolHandler(str(repo_path), approval_gate=RecordedApprovalGate(default_approve=True))

        target = "utils/helper.py"
        content = "def help_me(): pass\n"
        action_key = "handler:write:helper:iter0"

        # Write via handler
        assert handler.write_file(target, content, action_id=action_key) is True
        assert (repo_path / target).exists()

        # Re-write via handler is skipped idempotently
        assert handler.write_file(target, content, action_id=action_key) is True
        assert any("idempotent replay" in log["message"] for log in handler.audit_log)

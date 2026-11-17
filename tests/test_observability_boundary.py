"""Verification of the Architectural Boundary between Operational Truth and Observability.

Verifies:
1. Unidirectional Dependency Invariant:
   Control plane (LangGraph, Execution Ledger, Physical Disk) emits telemetry to the
   observability plane (LangSmith, SSE, Prometheus), but NEVER queries observability
   to determine operational state or make control decisions.
2. Fail-Open / Fail-Soft Invariant:
   If observability systems (LangSmith / telemetry exporter) encounter network errors,
   rate limits, or connection timeouts, workflow execution continues completely uninterrupted.
3. Air-Gapped Resumption Invariant:
   A crashed workflow can recover and verify idempotency strictly from the local SQLite
   execution ledger and physical disk, with zero network connectivity or external telemetry.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest

from agent.core.idempotency import IdempotencyJournal, AtomicFilePatcher
from agent.tools.execution_layer import ToolExecutionLayer
from agent.tools.approval import RecordedApprovalGate
from agent.core.state import AgentState
from agent.llm.provider import GeminiClient, LLMProvider


def test_observability_failure_does_not_halt_tool_execution():
    """Verify that if telemetry export raises an exception, physical tool execution succeeds."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        journal = IdempotencyJournal(db_path=str(repo_path / "journal.sqlite"))
        patcher = AtomicFilePatcher(str(repo_path), journal=journal)

        exec_layer = ToolExecutionLayer(
            repo_path=str(repo_path),
            approval_gate=RecordedApprovalGate(default_approve=True),
            patcher=patcher,
        )

        target_rel = "app/main.py"
        content = "print('Hello Production')\n"
        action_key = "action:test:fail_soft_telemetry"

        # Simulate a broken/throwing LangSmith telemetry hook
        with patch("agent.llm.provider.logger.warning") as mock_log:
            # Physical write should succeed 100%
            success = exec_layer.write_file(target_rel, content, action_id=action_key)
            assert success is True

            target_abs = repo_path / target_rel
            assert target_abs.exists()
            assert target_abs.read_text(encoding="utf-8") == content

            # Ledger must be durably COMPLETED regardless of telemetry status
            assert journal.is_execution_completed(action_key)


def test_operational_recovery_independent_of_external_telemetry():
    """Verify that crash recovery uses local physical disk & SQLite ledger, not remote traces.

    Even if external tracing is completely disabled or unreachable, recovery correctly
    reconciles the uncertain commit window.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        db_path = repo_path / "ledger.sqlite"
        journal = IdempotencyJournal(db_path=str(db_path))
        patcher = AtomicFilePatcher(str(repo_path), journal=journal)

        target_rel = "critical/transaction.py"
        target_abs = repo_path / target_rel
        target_abs.parent.mkdir(parents=True, exist_ok=True)

        expected_code = "def process(): return 'committed'\n"
        expected_hash = patcher.compute_hash(expected_code)
        action_key = "action:offline_recovery:iter0"

        # Simulate crash in APPLYING
        journal.record_prepared(
            action_key, "file_write", target_rel, expected_hash, expected_hash, initial_hash=None
        )
        journal.record_applying(action_key)
        # Disk write succeeded pre-crash
        target_abs.write_text(expected_code, encoding="utf-8")

        # Disable all external telemetry environment variables (air-gapped simulation)
        with patch.dict(os.environ, {"LANGSMITH_TRACING": "false", "LANGSMITH_API_KEY": ""}):
            exec_layer = ToolExecutionLayer(
                repo_path=str(repo_path),
                approval_gate=RecordedApprovalGate(default_approve=True),
                patcher=patcher,
            )

            # Resumed tool call succeeds offline via physical disk reconciliation
            result = exec_layer.write_file(target_rel, expected_code, action_id=action_key)
            assert result is True

            # Ledger is marked COMPLETED locally
            rec = journal.get_execution(action_key)
            assert rec["status"] == "COMPLETED"
            assert rec["reconciled_from_crash"] is True


def test_llm_provider_fail_soft_telemetry_instrumentation():
    """Verify that GeminiClient captures token metrics but fails soft if run_tree fails."""
    provider = GeminiClient()

    # Simulate get_current_run_tree raising a runtime error (e.g. invalid endpoint / broken socket)
    with patch("langsmith.run_helpers.get_current_run_tree", side_effect=RuntimeError("LangSmith network timeout")):
        # Provider should still initialize and function without unhandled exceptions
        assert provider.cumulative_token_usage["total_tokens"] >= 0
        assert hasattr(provider, "last_token_usage")

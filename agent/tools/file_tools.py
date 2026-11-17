"""File tools providing path traversal prevention and permission enforcement."""

from pathlib import Path
from typing import Any, Dict, Optional

from agent.tools.permissions import PermissionPolicy
from agent.tools.approval import HumanApprovalGate
from agent.tools.execution_layer import ToolExecutionLayer
from agent.core.idempotency import AtomicFilePatcher


class FileToolHandler:
    """Provides validated file and system operations enforcing permission policies and human approval."""

    def __init__(
        self,
        repo_path: str,
        policy: Optional[PermissionPolicy] = None,
        approval_gate: Optional[HumanApprovalGate] = None,
        patcher: Optional[AtomicFilePatcher] = None,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.execution_layer = ToolExecutionLayer(
            str(self.repo_path),
            policy=policy,
            approval_gate=approval_gate,
            patcher=patcher,
        )

    @property
    def policy(self) -> PermissionPolicy:
        return self.execution_layer.policy

    @property
    def approval_gate(self) -> HumanApprovalGate:
        return self.execution_layer.approval_gate

    @property
    def patcher(self) -> AtomicFilePatcher:
        return self.execution_layer.patcher

    @property
    def audit_log(self):
        return self.execution_layer.audit_log

    def _resolve_safe_path(self, rel_or_abs_path: str) -> Path:
        """Ensures the resolved path strictly resides within the repository."""
        return self.execution_layer._resolve_safe_path(rel_or_abs_path)

    def read_file(
        self, file_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None
    ) -> str:
        """Reads a file or a specific line slice (1-indexed) enforcing read policies."""
        return self.execution_layer.read_file(file_path, start_line=start_line, end_line=end_line)

    def write_file(
        self,
        file_path: str,
        content: str,
        action_id: Optional[str] = None,
        iteration: int = 0,
        thread_id: Optional[str] = None,
    ) -> bool:
        """Writes content to a file, enforcing protected path policies and human approval gates."""
        return self.execution_layer.write_file(
            file_path, content, action_id=action_id, iteration=iteration, thread_id=thread_id
        )

    def replace_snippet(
        self,
        file_path: str,
        old_snippet: str,
        new_snippet: str,
        action_id: Optional[str] = None,
        iteration: int = 0,
        thread_id: Optional[str] = None,
    ) -> bool:
        """Applies a surgical replacement with policy check and human approval if protected."""
        return self.execution_layer.replace_snippet(
            file_path,
            old_snippet,
            new_snippet,
            action_id=action_id,
            iteration=iteration,
            thread_id=thread_id,
        )

    def delete_file(
        self,
        file_path: str,
        action_id: Optional[str] = None,
        iteration: int = 0,
        thread_id: Optional[str] = None,
    ) -> bool:
        """Deletes a file, strictly enforcing human approval for destructive actions."""
        return self.execution_layer.delete_file(
            file_path, action_id=action_id, iteration=iteration, thread_id=thread_id
        )

    def execute_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 45,
        action_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes a shell command with policy restrictions and human approval for destructive operations."""
        return self.execution_layer.execute_command(
            command, cwd=cwd, timeout=timeout, action_id=action_id
        )

    def access_network(self, url: str, method: str = "GET") -> Dict[str, Any]:
        """Validates outbound network requests against network air-gapping and whitelist policies."""
        return self.execution_layer.access_network(url, method=method)

    def interact_external_service(
        self, service_name: str, action: str, details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Interacts with external services with permission and approval gates."""
        return self.execution_layer.interact_external_service(service_name, action, details)

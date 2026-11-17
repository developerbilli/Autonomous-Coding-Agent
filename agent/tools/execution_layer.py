"""Tool Execution Layer with Programmatic Permission Enforcement & Human Approval.

Enforces security restrictions in the execution runtime rather than relying
on LLM system prompt compliance.
"""

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.tools.permissions import (
    PermissionPolicy,
    ToolActionType,
    RiskLevel,
    PermissionDeniedError,
    ApprovalRequiredError,
)
from agent.tools.approval import (
    HumanApprovalGate,
    ApprovalRequest,
    ApprovalDecision,
    AutoRejectApprovalGate,
)
from agent.core.idempotency import (
    AtomicFilePatcher,
    get_atomic_patcher,
    generate_idempotency_key,
)


class ToolExecutionLayer:
    """Secure mediator executing tool actions under active security policy and approval gates."""

    def __init__(
        self,
        repo_path: str,
        policy: Optional[PermissionPolicy] = None,
        approval_gate: Optional[HumanApprovalGate] = None,
        patcher: Optional[AtomicFilePatcher] = None,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.policy = policy or PermissionPolicy()
        self.approval_gate = approval_gate or AutoRejectApprovalGate()
        self.patcher = patcher or get_atomic_patcher(str(self.repo_path))
        self.audit_log: List[Dict[str, Any]] = []

    def _resolve_safe_path(self, rel_or_abs_path: str) -> Path:
        """Ensures the resolved path strictly resides within the repository."""
        target = (self.repo_path / rel_or_abs_path).resolve()
        try:
            target.relative_to(self.repo_path)
        except ValueError:
            raise PermissionDeniedError(
                f"Path traversal detected: '{rel_or_abs_path}' is outside repository '{self.repo_path}'"
            )
        return target

    def _get_rel_path(self, safe_path: Path) -> str:
        """Computes repository-relative normalized path."""
        try:
            return str(safe_path.relative_to(self.repo_path)).replace("\\", "/")
        except ValueError:
            return str(safe_path).replace("\\", "/")

    def _require_approval_if_needed(
        self,
        action_type: ToolActionType,
        target: str,
        risk_level: RiskLevel,
        description: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> ApprovalDecision:
        """Dispatches an approval request if the risk level requires human authorization."""
        if risk_level in self.policy.require_human_approval_for:
            req = ApprovalRequest(
                action_type=action_type,
                target=target,
                risk_level=risk_level,
                description=description,
                details=details or {},
            )
            decision = self.approval_gate.request_approval(req)
            if not decision.approved:
                raise ApprovalRequiredError(
                    f"Action '{action_type.value}' on '{target}' rejected by human operator: {decision.reason}"
                )
            return decision

        return ApprovalDecision(approved=True, reason="Pre-authorized by policy", approver="policy_engine")

    # ============================================================
    # 1. File Reading Tools
    # ============================================================

    def read_file(
        self, file_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None
    ) -> str:
        """Reads a file with path traversal and credential access enforcement."""
        target = self._resolve_safe_path(file_path)
        rel_path = self._get_rel_path(target)

        # Enforce read permission policy
        allowed, reason = self.policy.check_read_permission(rel_path)
        if not allowed:
            self._log_audit(ToolActionType.FILE_READ, rel_path, RiskLevel.CRITICAL, False, reason)
            raise PermissionDeniedError(reason)

        if not target.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        lines = target.read_text(encoding="utf-8").splitlines()
        content = "\n".join(lines)
        if start_line is not None and end_line is not None:
            s = max(0, start_line - 1)
            e = min(len(lines), end_line)
            content = "\n".join(lines[s:e])

        self._log_audit(ToolActionType.FILE_READ, rel_path, RiskLevel.LOW, True, "Read succeeded")
        return content

    # ============================================================
    # 2. File Writing / Editing Tools
    # ============================================================

    def write_file(
        self,
        file_path: str,
        content: str,
        action_id: Optional[str] = None,
        iteration: int = 0,
        thread_id: Optional[str] = None,
    ) -> bool:
        """Writes content to a file atomically with execution ledger tracking and human approval gates."""
        target = self._resolve_safe_path(file_path)
        rel_path = self._get_rel_path(target)

        # Generate stable idempotency key if not explicitly provided
        key = action_id or generate_idempotency_key(
            "write_file", rel_path, content, thread_id=thread_id, iteration=iteration
        )

        # 1. Execution idempotency & uncertain commit window check:
        # Check if action was already reconciled or matches disk state
        reconciled, reason, output = self.patcher.journal.reconcile_with_physical_disk(key, self.repo_path)
        if reconciled:
            msg = "Write skipped (idempotent replay)" if reason == "ALREADY_COMPLETED" else f"Write skipped (reconciled post-crash: {reason})"
            self._log_audit(
                ToolActionType.FILE_WRITE,
                rel_path,
                RiskLevel.LOW,
                True,
                msg,
            )
            return True

        content_hash = self.patcher.compute_hash(content)
        if self.patcher.is_action_applied(key, target) or (
            target.exists() and self.patcher.compute_hash(target.read_text("utf-8")) == content_hash
        ):
            self.patcher.journal.record_action(key, rel_path, content_hash, iteration)
            self.patcher.journal.record_execution_completion(
                key, {"rel_path": rel_path, "status": "already_applied", "bytes": len(content.encode("utf-8"))}
            )
            self._log_audit(ToolActionType.FILE_WRITE, rel_path, RiskLevel.LOW, True, "Write skipped (idempotent replay)")
            return True

        # 2. Permission policy verification
        allowed, risk_level, reason = self.policy.check_write_permission(rel_path)
        if not allowed and risk_level == RiskLevel.CRITICAL:
            self._log_audit(ToolActionType.FILE_WRITE, rel_path, risk_level, False, reason)
            raise PermissionDeniedError(reason)

        # 3. Check human approval gate if modifying protected production files
        desc = reason or f"Write operation to {rel_path}"
        self._require_approval_if_needed(
            ToolActionType.FILE_WRITE,
            rel_path,
            risk_level,
            desc,
            {"size_bytes": len(content.encode("utf-8")), "is_existing": target.exists()},
        )

        # 4. Record execution start in persistent ledger
        self.patcher.journal.record_execution_start(key, "write_file", rel_path, content_hash)

        # 5. Atomically replace file via patcher (temp file -> fsync -> POSIX rename)
        try:
            self.patcher.atomic_write(
                target,
                content,
                action_id=key,
                iteration=iteration,
                validate_syntax=(target.suffix == ".py"),
            )
            self._log_audit(ToolActionType.FILE_WRITE, rel_path, risk_level, True, "Write succeeded")
            return True
        except Exception as e:
            self.patcher.journal.record_execution_failure(key, str(e))
            self._log_audit(ToolActionType.FILE_WRITE, rel_path, risk_level, False, f"Write failed: {e}")
            raise

    def replace_snippet(
        self,
        file_path: str,
        old_snippet: str,
        new_snippet: str,
        action_id: Optional[str] = None,
        iteration: int = 0,
        thread_id: Optional[str] = None,
    ) -> bool:
        """Applies a surgical replacement atomically with crash recovery and execution idempotency."""
        target = self._resolve_safe_path(file_path)
        rel_path = self._get_rel_path(target)

        # Generate stable idempotency key
        key = action_id or generate_idempotency_key(
            "replace_snippet",
            rel_path,
            {"old": old_snippet, "new": new_snippet},
            thread_id=thread_id,
            iteration=iteration,
        )

        # 0. Execution idempotency & uncertain commit window check:
        reconciled, reason, output = self.patcher.journal.reconcile_with_physical_disk(key, self.repo_path)
        if reconciled:
            msg = "Snippet replacement skipped (idempotent replay)" if reason == "ALREADY_COMPLETED" else f"Snippet replacement skipped (reconciled post-crash: {reason})"
            self._log_audit(
                ToolActionType.FILE_WRITE,
                rel_path,
                RiskLevel.LOW,
                True,
                msg,
            )
            return True

        # 1. Execution idempotency check via journal
        if self.patcher.is_action_applied(key, target):
            self._log_audit(
                ToolActionType.FILE_WRITE, rel_path, RiskLevel.LOW, True, "Snippet replacement skipped (idempotent replay)"
            )
            return True

        if not target.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        current = target.read_text(encoding="utf-8")

        # 2. Crash-recovery idempotency check:
        # If the process crashed after the write completed, old_snippet is already replaced by new_snippet.
        if old_snippet not in current and new_snippet in current:
            content_hash = self.patcher.compute_hash(current)
            self.patcher.journal.record_action(key, rel_path, content_hash, iteration)
            self.patcher.journal.record_execution_completion(
                key, {"rel_path": rel_path, "status": "already_applied_pre_crash"}
            )
            self._log_audit(
                ToolActionType.FILE_WRITE, rel_path, RiskLevel.LOW, True, "Snippet replacement verified on disk post-crash"
            )
            return True

        if old_snippet not in current:
            raise ValueError(f"Target snippet not found in {file_path}")

        allowed, risk_level, reason = self.policy.check_write_permission(rel_path)
        if not allowed and risk_level == RiskLevel.CRITICAL:
            self._log_audit(ToolActionType.FILE_WRITE, rel_path, risk_level, False, reason)
            raise PermissionDeniedError(reason)

        desc = reason or f"Replace snippet in {rel_path}"
        self._require_approval_if_needed(
            ToolActionType.FILE_WRITE,
            rel_path,
            risk_level,
            desc,
            {"old_snippet_sample": old_snippet[:60], "new_snippet_sample": new_snippet[:60]},
        )

        updated = current.replace(old_snippet, new_snippet, 1)
        content_hash = self.patcher.compute_hash(updated)
        self.patcher.journal.record_execution_start(key, "replace_snippet", rel_path, content_hash)

        try:
            self.patcher.atomic_write(
                target,
                updated,
                action_id=key,
                iteration=iteration,
                validate_syntax=(target.suffix == ".py"),
            )
            self._log_audit(ToolActionType.FILE_WRITE, rel_path, risk_level, True, "Snippet replacement succeeded")
            return True
        except Exception as e:
            self.patcher.journal.record_execution_failure(key, str(e))
            self._log_audit(ToolActionType.FILE_WRITE, rel_path, risk_level, False, f"Snippet replacement failed: {e}")
            raise

    def delete_file(
        self,
        file_path: str,
        action_id: Optional[str] = None,
        iteration: int = 0,
        thread_id: Optional[str] = None,
    ) -> bool:
        """Deletes a file. Destructive operation that ALWAYS requires human approval."""
        target = self._resolve_safe_path(file_path)
        rel_path = self._get_rel_path(target)

        key = action_id or generate_idempotency_key(
            "delete_file", rel_path, thread_id=thread_id, iteration=iteration
        )

        # 0. Execution idempotency & uncertain commit window check:
        reconciled, reason, output = self.patcher.journal.reconcile_with_physical_disk(key, self.repo_path)
        if reconciled:
            msg = "Deletion skipped (already completed pre-crash)" if reason in ("ALREADY_COMPLETED", "DELETION_RECONCILED_FROM_PHYSICAL_DISK") else f"Deletion skipped (reconciled post-crash: {reason})"
            self._log_audit(
                ToolActionType.FILE_DELETE,
                rel_path,
                RiskLevel.LOW,
                True,
                msg,
            )
            return True

        if not target.exists():
            if self.patcher.journal.is_execution_completed(key):
                self._log_audit(
                    ToolActionType.FILE_DELETE,
                    rel_path,
                    RiskLevel.LOW,
                    True,
                    "Deletion skipped (already completed pre-crash)",
                )
                return True
            raise FileNotFoundError(f"Cannot delete non-existent file: {file_path}")

        allowed, risk_level, reason = self.policy.check_delete_permission(rel_path)
        if not allowed:
            self._log_audit(ToolActionType.FILE_DELETE, rel_path, risk_level, False, reason)
            raise PermissionDeniedError(reason)

        # Human approval gate is mandatory for destructive deletion
        self._require_approval_if_needed(
            ToolActionType.FILE_DELETE,
            rel_path,
            RiskLevel.HIGH,
            f"Permanently delete file '{rel_path}' from repository",
            {"size_bytes": target.stat().st_size if target.is_file() else 0},
        )

        initial_hash = self.patcher.compute_hash(target.read_text("utf-8")) if target.is_file() else "DIR"
        self.patcher.journal.record_prepared(
            key, "delete_file", rel_path, payload_hash="DELETED", expected_hash="DELETED", initial_hash=initial_hash
        )
        self.patcher.journal.record_applying(key)

        try:
            if target.is_file():
                target.unlink()
                from agent.core.idempotency import _sync_parent_dir
                _sync_parent_dir(target)
            elif target.is_dir():
                shutil.rmtree(target)

            self.patcher.journal.record_verify(key, "DELETED")
            self.patcher.journal.record_execution_completion(key, {"rel_path": rel_path, "status": "deleted"})
            self._log_audit(ToolActionType.FILE_DELETE, rel_path, RiskLevel.HIGH, True, "Deletion succeeded")
            return True
        except Exception as e:
            self.patcher.journal.record_execution_failure(key, str(e))
            self._log_audit(ToolActionType.FILE_DELETE, rel_path, RiskLevel.HIGH, False, f"Deletion failed: {e}")
            raise

    # ============================================================
    # 3. Command Execution Tools
    # ============================================================

    def execute_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 45,
        action_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes shell command enforcing allowed, destructive, and forbidden lists."""
        target_cwd = self.repo_path if not cwd else Path(cwd).resolve()
        try:
            target_cwd.relative_to(self.repo_path)
        except ValueError:
            raise PermissionDeniedError(f"Command execution working directory '{cwd}' is outside repository.")

        if action_id:
            exec_rec = self.patcher.journal.get_execution(action_id)
            if exec_rec and exec_rec.get("status") == "COMPLETED" and exec_rec.get("output"):
                self._log_audit(
                    ToolActionType.COMMAND_EXECUTE,
                    command,
                    RiskLevel.LOW,
                    True,
                    "Command skipped (idempotent replay)",
                )
                return exec_rec["output"]

        allowed, risk_level, reason = self.policy.check_command_permission(command)
        if not allowed:
            self._log_audit(ToolActionType.COMMAND_EXECUTE, command, risk_level, False, reason)
            raise PermissionDeniedError(reason)

        # Destructive commands (e.g. git reset, rm, pip install) require human approval
        desc = reason or f"Execute command: {command}"
        self._require_approval_if_needed(
            ToolActionType.COMMAND_EXECUTE,
            command,
            risk_level,
            desc,
            {"cwd": str(target_cwd), "timeout": timeout},
        )

        try:
            cmd_args = shlex.split(command)
        except ValueError as err:
            self._log_audit(ToolActionType.COMMAND_EXECUTE, command, risk_level, False, f"Invalid command syntax: {err}")
            raise PermissionDeniedError(f"Invalid command syntax: {err}")

        if not cmd_args:
            raise PermissionDeniedError("Cannot execute empty command")

        if action_id:
            cmd_hash = self.patcher.compute_hash(command)
            self.patcher.journal.record_execution_start(action_id, "command_execute", command, cmd_hash)

        # Execute securely under subprocess with argument list and shell=False to prevent injection
        try:
            proc = subprocess.run(
                cmd_args,
                shell=False,
                cwd=str(target_cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
            )
            success = proc.returncode == 0
            res = {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "command": command,
            }
            if action_id:
                if success:
                    self.patcher.journal.record_execution_completion(action_id, res)
                else:
                    self.patcher.journal.record_execution_failure(action_id, f"Exit code {proc.returncode}")

            self._log_audit(
                ToolActionType.COMMAND_EXECUTE,
                command,
                risk_level,
                success,
                f"Exited with return code {proc.returncode}",
            )
            return res
        except subprocess.TimeoutExpired:
            self._log_audit(ToolActionType.COMMAND_EXECUTE, command, risk_level, False, "Command timed out")
            if action_id:
                self.patcher.journal.record_execution_failure(action_id, "Command timed out")
            return {
                "exit_code": 124,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "command": command,
            }
        except FileNotFoundError as e:
            self._log_audit(ToolActionType.COMMAND_EXECUTE, command, risk_level, False, f"Executable not found: {e}")
            if action_id:
                self.patcher.journal.record_execution_failure(action_id, f"Executable not found: {e}")
            return {
                "exit_code": 127,
                "stdout": "",
                "stderr": f"Executable not found: {cmd_args[0]}",
                "command": command,
            }
        except Exception as e:
            self._log_audit(ToolActionType.COMMAND_EXECUTE, command, risk_level, False, str(e))
            if action_id:
                self.patcher.journal.record_execution_failure(action_id, str(e))
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": str(e),
                "command": command,
            }

    # ============================================================
    # 4. Outbound Network Tools
    # ============================================================

    def access_network(self, url: str, method: str = "GET") -> Dict[str, Any]:
        """Validates outbound network requests against network air-gapping and whitelist policies."""
        allowed, risk_level, reason = self.policy.check_network_permission(url)
        if not allowed:
            self._log_audit(ToolActionType.NETWORK_ACCESS, url, risk_level, False, reason)
            raise PermissionDeniedError(reason)

        # Whitelist hit or allowed mode
        self._log_audit(ToolActionType.NETWORK_ACCESS, url, risk_level, True, "Network access permitted")
        return {"url": url, "allowed": True, "method": method}

    # ============================================================
    # 5. External Service Tools
    # ============================================================

    def interact_external_service(
        self, service_name: str, action: str, details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Interacts with external services (e.g. Git push, cloud deployments) with approval gates."""
        allowed, risk_level, reason = self.policy.check_external_service_permission(
            service_name, action, details
        )
        if not allowed:
            self._log_audit(ToolActionType.EXTERNAL_SERVICE, f"{service_name}:{action}", risk_level, False, reason)
            raise PermissionDeniedError(reason)

        desc = reason or f"Invoke {service_name} action '{action}'"
        self._require_approval_if_needed(
            ToolActionType.EXTERNAL_SERVICE,
            f"{service_name}:{action}",
            risk_level,
            desc,
            details or {},
        )

        self._log_audit(ToolActionType.EXTERNAL_SERVICE, f"{service_name}:{action}", risk_level, True, "Service action approved")
        return {
            "service": service_name,
            "action": action,
            "status": "authorized",
            "details": details or {},
        }

    # ============================================================
    # Audit Logging
    # ============================================================

    def _log_audit(
        self,
        action: ToolActionType,
        target: str,
        risk: RiskLevel,
        permitted: bool,
        message: Optional[str] = None,
    ):
        """Maintains an in-memory chronological security audit trail."""
        self.audit_log.append({
            "action": action.value,
            "target": target,
            "risk_level": risk.value,
            "permitted": permitted,
            "message": message,
        })

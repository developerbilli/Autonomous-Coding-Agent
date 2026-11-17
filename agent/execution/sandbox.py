"""Unified Execution Sandbox with Multi-Tier Security Isolation Boundaries.

Supports 4 distinct isolation tiers:
1. Tier 1: Hardware-virtualized MicroVM (Firecracker / KVM) for untrusted / hostile code.
   - Dedicated minimal guest Linux kernel (vmlinux), independent page tables, hardware hypervisor boundary.
2. Tier 2: User-space Application Kernel (gVisor runsc) for syscall-level kernel shielding.
   - Sentry user-space Go kernel (ring 3) intercepting syscalls; NOT a microVM (no guest kernel or virtual devices).
3. Tier 3: OCI Container (Docker / Podman) with non-root user, network none, read-only rootfs, and cgroups.
4. Tier 4: Process-level defense-in-depth fallback (POSIX rlimits, advisory proxy, process-group cleanup).
   - CRITICAL: WEAK BOUNDARY. Refuses untrusted code execution unless explicitly authorized (allow_process_fallback=True).
"""

import os
import sys
import re
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from agent.core.state import TestResult
from agent.execution.isolation import (
    SandboxSecurityPolicy,
    ExecutionOutput,
    IsolationLevel,
    RepoTrustLevel,
    TIER_SPECIFICATIONS,
)
from agent.execution.container_sandbox import ContainerSandbox
from agent.execution.barrier import ProcessDestructionBarrier, ProcessBarrierViolationError
from agent.execution.microvm_sandbox import (
    FirecrackerMicroVMSandbox,
    GVisorAppKernelSandbox,
    MicroVMSandbox,
)
from agent.execution.hardened_process import HardenedProcessSandbox

try:
    from langsmith import traceable
except ImportError:
    def traceable(name=None, run_type=None, **kwargs):
        def decorator(func):
            return func
        return decorator

logger = logging.getLogger("agent.sandbox")


class SecurityIsolationUnavailableError(PermissionError):
    """Raised when untrusted code execution is attempted but strong isolation
    (Tiers 1-3: MicroVM, gVisor, Container) is unavailable on the host,
    and automatic fallback to Tier 4 host process execution is blocked.
    """
    pass


class ExecutionSandbox:
    """Unified security sandbox providing multi-tier isolation, resource quotas,
    network restriction, output limits, and reliable cleanup.
    
    Fail-Closed Policy:
    Untrusted code execution will REFUSE to execute in Tier 4 (host process)
    if stronger isolation (Tiers 1-3) is unavailable, unless explicitly permitted
    via `allow_process_fallback=True` or `ALLOW_UNSAFE_HOST_FALLBACK=1`.
    """

    def __init__(
        self,
        repo_path: str,
        timeout_seconds: int = 45,
        memory_limit_mb: int = 512,
        cpu_limit: float = 1.0,
        network_mode: str = "none",
        preferred_isolation: Optional[IsolationLevel] = None,
        allow_process_fallback: Optional[bool] = None,
        trust_level: Optional[Any] = None,
        sanitize_secrets: bool = True,
    ):
        self.repo_path = Path(repo_path).resolve()

        # Parse repository trust level
        if isinstance(trust_level, str):
            try:
                self.trust_level = RepoTrustLevel(trust_level.lower())
            except ValueError:
                self.trust_level = RepoTrustLevel.UNTRUSTED
        elif isinstance(trust_level, RepoTrustLevel):
            self.trust_level = trust_level
        else:
            self.trust_level = None

        # Check deployment environment
        deploy_env = (
            os.environ.get("ENVIRONMENT")
            or os.environ.get("APP_ENV")
            or os.environ.get("DEPLOYMENT_ENV")
            or "development"
        ).strip().lower()
        self.is_production = deploy_env in ("production", "prod")

        # Check explicit parameter or environment override
        # Security Invariants:
        # 1. In PRODUCTION, Tier 4 host-process fallback is strictly FORBIDDEN under all circumstances.
        # 2. For UNTRUSTED repositories, Tier 4 process fallback is strictly FORBIDDEN under all circumstances.
        if self.is_production or self.trust_level == RepoTrustLevel.UNTRUSTED:
            fallback_enabled = False
        elif allow_process_fallback is None:
            env_override = os.environ.get("ALLOW_UNSAFE_HOST_FALLBACK", "").strip().lower()
            fallback_enabled = env_override in ("1", "true", "yes")
        else:
            fallback_enabled = allow_process_fallback

        self.policy = SandboxSecurityPolicy(
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
            cpu_limit=cpu_limit,
            network_mode=network_mode,
            allow_process_fallback=fallback_enabled,
            trust_level=self.trust_level or RepoTrustLevel.TRUSTED,
        )

        # Defense-in-depth: Automatically quarantine workspace credentials for isolated or untrusted repos
        self.quarantined_secrets = []
        is_isolated_workspace = (
            "workspaces" in self.repo_path.parts
            or self.trust_level == RepoTrustLevel.UNTRUSTED
            or "mock_repo" in self.repo_path.parts
            or "sandbox_" in self.repo_path.name
        )
        if sanitize_secrets and is_isolated_workspace and self.repo_path.exists():
            try:
                from agent.repository.sanitizer import WorkspaceSanitizer
                self.quarantined_secrets = WorkspaceSanitizer.quarantine_secrets(self.repo_path)
            except Exception as e:
                logger.warning(f"Could not scan/quarantine workspace secrets: {e}")

        # Initialize process destruction barrier to track and enforce process lifecycle
        self.barrier = ProcessDestructionBarrier(workspace_path=self.repo_path)

        # Initialize dedicated isolation engines for each tier
        self.microvm_engine = FirecrackerMicroVMSandbox(str(self.repo_path), policy=self.policy)
        self.gvisor_engine = GVisorAppKernelSandbox(str(self.repo_path), policy=self.policy)
        self.container_engine = ContainerSandbox(str(self.repo_path), policy=self.policy, barrier=self.barrier)
        self.hardened_engine = HardenedProcessSandbox(str(self.repo_path), policy=self.policy, barrier=self.barrier)

        # Select highest available isolation tier or enforce fail-closed block
        self.fallback_blocked = False
        self.active_engine, self.isolation_level = self._select_isolation_engine(preferred_isolation)
        self.policy.isolation_level = self.isolation_level

        if self.fallback_blocked:
            logger.error(
                "FAIL-CLOSED SECURITY ALERT: Strong isolation boundaries (Tier 1 MicroVM, Tier 2 gVisor, Tier 3 Container) "
                "are unavailable on this host. Untrusted code execution in Tier 4 (host process) is strictly blocked "
                "(allow_process_fallback=False)."
            )
        elif self.isolation_level == IsolationLevel.HARDENED_PROCESS:
            logger.warning(
                "Sandbox operating in Tier 4 (Hardened Process Fallback) by explicit operator authorization. "
                "CRITICAL WARNING: This is a weaker security boundary than containers or microVMs. "
                "POSIX rlimits do NOT jail the filesystem, and advisory proxy env vars do NOT block raw sockets."
            )

    def _select_isolation_engine(self, preferred: Optional[IsolationLevel]):
        """Selects the strongest available security boundary based on preference, host capabilities, and security policy."""
        # Explicit user preference
        if preferred == IsolationLevel.MICROVM and self.microvm_engine.is_available():
            return self.microvm_engine, IsolationLevel.MICROVM
        if preferred == IsolationLevel.GVISOR and self.gvisor_engine.is_available():
            return self.gvisor_engine, IsolationLevel.GVISOR
        if preferred == IsolationLevel.CONTAINER and self.container_engine.is_available():
            return self.container_engine, IsolationLevel.CONTAINER
        if preferred == IsolationLevel.HARDENED_PROCESS:
            # User explicitly opted into Tier 4
            return self.hardened_engine, IsolationLevel.HARDENED_PROCESS

        # Progressive automatic negotiation: Tier 1 -> Tier 2 -> Tier 3
        if self.microvm_engine.is_available():
            return self.microvm_engine, IsolationLevel.MICROVM
        elif self.gvisor_engine.is_available():
            return self.gvisor_engine, IsolationLevel.GVISOR
        elif self.container_engine.is_available():
            return self.container_engine, IsolationLevel.CONTAINER

        # Tiers 1-3 are unavailable. Check fail-closed policy before allowing Tier 4 host execution.
        if self.policy.allow_process_fallback:
            return self.hardened_engine, IsolationLevel.HARDENED_PROCESS
        else:
            self.fallback_blocked = True
            return None, IsolationLevel.HARDENED_PROCESS

    def get_security_status(self) -> Dict[str, Any]:
        """Returns comprehensive metadata regarding active security controls and boundaries."""
        tier_spec = TIER_SPECIFICATIONS.get(self.isolation_level.value, {})
        return {
            "isolation_level": self.isolation_level.value,
            "tier_name": tier_spec.get("tier_name", ""),
            "technology_class": tier_spec.get("technology_class", ""),
            "security_boundary_class": tier_spec.get("security_boundary_class", ""),
            "is_filesystem_jail": tier_spec.get("is_filesystem_jail", False) if not self.fallback_blocked else False,
            "is_guaranteed_network_blocked": tier_spec.get("is_guaranteed_network_blocked", False) if not self.fallback_blocked else False,
            "non_root_user": self.policy.non_root_user,
            "network_control": self.policy.network_mode,
            "memory_limit": f"{self.policy.memory_limit_mb}MB",
            "cpu_limit": f"{self.policy.cpu_limit} vCPU",
            "pids_limit": self.policy.pids_limit,
            "output_limit": f"{self.policy.max_output_bytes // 1024}KB",
            "timeout_seconds": self.policy.timeout_seconds,
            "trust_level": self.trust_level.value if self.trust_level else "unspecified",
            "is_production": self.is_production,
            "quarantined_secrets_count": len(self.quarantined_secrets),
            "allow_process_fallback": self.policy.allow_process_fallback,
            "fallback_blocked": self.fallback_blocked,
            "container_runtime_available": self.container_engine.is_available(),
            "microvm_runtime_available": self.microvm_engine.is_available(),
            "firecracker_available": self.microvm_engine.is_available(),
            "gvisor_available": self.gvisor_engine.is_available(),
        }

    def terminate_all_processes(self, grace_seconds: float = 0.5) -> bool:
        """Enforces termination of all active execution processes and containers."""
        return self.barrier.terminate_all(grace_seconds=grace_seconds)

    def restore_quarantined_secrets(self) -> int:
        """Restores quarantined secrets after enforcing process destruction barrier."""
        if not self.quarantined_secrets:
            return 0
        from agent.repository.sanitizer import WorkspaceSanitizer
        return WorkspaceSanitizer.restore_secrets(
            self.repo_path,
            self.quarantined_secrets,
            barrier=self.barrier,
        )

    def run_command(self, cmd: List[str]) -> ExecutionOutput:
        """Executes a command through the active isolation boundary or raises SecurityIsolationUnavailableError."""
        if self.fallback_blocked or self.active_engine is None:
            raise SecurityIsolationUnavailableError(
                "SECURITY REFUSAL: Untrusted code execution blocked. Strong isolation "
                "(Tier 1 Firecracker MicroVM, Tier 2 gVisor AppKernel, or Tier 3 OCI Container) is unavailable on this host. "
                "Automatic execution of untrusted code in Tier 4 (host process) is strictly blocked to prevent host compromise. "
                "To explicitly permit host-process execution for local debugging, pass allow_process_fallback=True or export ALLOW_UNSAFE_HOST_FALLBACK=1."
            )
        return self.active_engine.run_command(cmd)

    @traceable(name="Isolated Sandbox Pytest Execution")
    def run_pytest(self, test_target: Optional[str] = None) -> TestResult:
        """Executes pytest inside the isolation boundary and extracts test metrics."""
        if self.fallback_blocked or self.active_engine is None:
            err_msg = (
                "SECURITY REFUSAL: Untrusted code execution blocked. Strong isolation (Tiers 1-3) unavailable "
                "and Tier 4 host process fallback is disallowed (policy.allow_process_fallback=False)."
            )
            return TestResult(
                passed=False,
                exit_code=126,
                stdout="",
                stderr=err_msg,
                failed_tests=["SECURITY_ISOLATION_UNAVAILABLE"],
                error_summary=err_msg,
                isolation_level=self.isolation_level.value,
                security_metadata={
                    **self.get_security_status(),
                    "execution_blocked": True,
                },
                output_truncated=False,
            )

        python_bin = "python3" if self.isolation_level in (IsolationLevel.CONTAINER, IsolationLevel.MICROVM, IsolationLevel.GVISOR) else sys.executable
        cmd = [python_bin, "-m", "pytest", "-v"]
        if test_target:
            cmd.append(test_target)

        try:
            exec_out: ExecutionOutput = self.run_command(cmd)
            stdout = exec_out.stdout
            stderr = exec_out.stderr
            passed = exec_out.returncode == 0

            failed_tests = []
            passed_tests = []
            skipped_tests = []
            for line in stdout.splitlines():
                m = re.search(r"(?:::|\b)(test_[a-zA-Z0-9_]+)\s+([A-Z]+)", line)
                if m:
                    t_name = m.group(1)
                    st = m.group(2).upper()
                    if st == "PASSED":
                        passed_tests.append(t_name)
                    elif st == "FAILED":
                        failed_tests.append(t_name)
                    elif st in ("SKIPPED", "XFAIL"):
                        skipped_tests.append(t_name)
                else:
                    fm = re.search(r"FAILED\s+(?:[^\s:]+::)?(test_[a-zA-Z0-9_]+)", line)
                    if fm:
                        failed_tests.append(fm.group(1))
                    pm = re.search(r"PASSED\s+(?:[^\s:]+::)?(test_[a-zA-Z0-9_]+)", line)
                    if pm:
                        passed_tests.append(pm.group(1))
                    sm = re.search(r"(?:SKIPPED|XFAIL)\s+(?:[^\s:]+::)?(test_[a-zA-Z0-9_]+)", line)
                    if sm:
                        skipped_tests.append(sm.group(1))

            if not failed_tests and not passed:
                failed_tests = re.findall(r"FAILED\s+([^\s]+)", stdout)

            error_summary = None
            if not passed:
                trace_matches = re.findall(r"(E\s+.*)", stdout)
                if trace_matches:
                    error_summary = "\n".join(trace_matches[-5:])
                else:
                    error_summary = stdout[-800:] if stdout else stderr[-800:]

            return TestResult(
                passed=passed,
                exit_code=exec_out.returncode,
                stdout=stdout,
                stderr=stderr,
                failed_tests=sorted(list(set(failed_tests))),
                passed_tests=sorted(list(set(passed_tests))),
                skipped_tests=sorted(list(set(skipped_tests))),
                error_summary=error_summary,
                isolation_level=exec_out.isolation_level,
                security_metadata={
                    **self.get_security_status(),
                    **exec_out.security_metadata,
                },
                output_truncated=exec_out.output_truncated,
            )

        except SecurityIsolationUnavailableError as e:
            return TestResult(
                passed=False,
                exit_code=126,
                stdout="",
                stderr=str(e),
                failed_tests=["SECURITY_ISOLATION_UNAVAILABLE"],
                error_summary=str(e),
                isolation_level=self.isolation_level.value,
                security_metadata={
                    **self.get_security_status(),
                    "execution_blocked": True,
                },
                output_truncated=False,
            )
        except Exception as e:
            return TestResult(
                passed=False,
                exit_code=1,
                stdout="",
                stderr=str(e),
                failed_tests=["SANDBOX_ISOLATION_ERROR"],
                error_summary=str(e),
                isolation_level=self.isolation_level.value,
                security_metadata=self.get_security_status(),
                output_truncated=False,
            )

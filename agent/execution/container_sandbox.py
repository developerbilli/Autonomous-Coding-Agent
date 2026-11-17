"""Containerized Sandbox Engine: OCI Container Isolation (Docker / Podman).

Security Architecture & Controlled Mounts:
------------------------------------------
1. Kernel Namespaces & Cgroups:
   - Linux namespaces (PID, Mount, Net, IPC, UTS, User) provide OS-level container isolation.
   - Cgroups v2 enforce strict limits on memory (memory.max), CPU quota (cpu.max), and PIDs (pids.max).

2. Read-Only Root Filesystem & Controlled Mounts:
   - The root filesystem is mounted strictly read-only (--read-only). System binaries (/bin, /usr, /lib)
     and configuration (/etc) cannot be modified, preventing malware persistence or tampering.
   - Explicit controlled writable mounts:
       * /tmp: tmpfs mount with flags 'rw,noexec,nosuid,size=64m'.
         - 'rw': Allows pytest and Python interpreters to write temporary test files.
         - 'noexec': Prevents execution of downloaded or dropped binaries in /tmp.
         - 'nosuid': Disallows SUID privilege escalation.
         - 'size=64m': Protects host RAM from memory exhaustion via disk bombing.
       * /run: tmpfs mount with flags 'rw,noexec,nosuid,size=16m' for runtime locks.
       * /workspace: Controlled bind mount (-v <repo_path>:/workspace:rw) scoped strictly to the target
         repository directory. Host root (/), user home (~), and docker sockets are NEVER exposed.

3. Complete Kernel-Level Air-Gapping:
   - Enforces --network=none, which creates a dedicated empty network namespace (CLONE_NEWNET).
   - Only the loopback interface exists and is down.
   - Unlike advisory HTTP_PROXY environment variables, kernel namespace isolation cannot be bypassed
     by raw sockets (AF_INET), C extensions, UDP, or DNS lookups.
"""

import os
import shutil
import subprocess
import time
import uuid
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from agent.execution.isolation import SandboxSecurityPolicy, ExecutionOutput, IsolationLevel, TIER_SPECIFICATIONS

logger = logging.getLogger("agent.sandbox.container")

class ContainerSandbox:
    """Executes untrusted code inside dedicated OCI containers (Docker / Podman)
    with non-root users, air-gapped network namespace, read-only rootfs, and controlled mounts.
    """

    def __init__(
        self,
        repo_path: str,
        policy: Optional[SandboxSecurityPolicy] = None,
        image_name: str = "autonomous-agent-sandbox:latest",
        barrier: Optional[Any] = None,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.policy = policy or SandboxSecurityPolicy(isolation_level=IsolationLevel.CONTAINER)
        self.image_name = image_name
        self.barrier = barrier
        self.runtime_binary = self._detect_runtime()

    def _detect_runtime(self) -> Optional[str]:
        """Detects available container CLI: docker, podman, or nerdctl."""
        for candidate in ["docker", "podman", "nerdctl"]:
            found = shutil.which(candidate)
            if found:
                try:
                    probe = subprocess.run(
                        [found, "version"],
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    if probe.returncode == 0:
                        return found
                except Exception:
                    continue
        return None

    def is_available(self) -> bool:
        """Returns True if a live container runtime daemon is responsive on the host."""
        return self.runtime_binary is not None

    def get_container_spec(self) -> Dict[str, Any]:
        """Returns the formal specification for Tier 3: OCI Container Isolation."""
        return {
            "tier": "Tier 3: OCI Container Isolation",
            "runtime": self.runtime_binary or "docker",
            "namespaces": "PID, Mount, Net, IPC, UTS, User",
            "user": self.policy.non_root_user,
            "network_isolation": "Kernel network namespace (--network=none via CLONE_NEWNET)",
            "memory_limit": f"{self.policy.memory_limit_mb}MB (cgroup memory.max)",
            "cpu_limit": f"{self.policy.cpu_limit} vCPU (cgroup cpu.max)",
            "pids_limit": self.policy.pids_limit,
            "capabilities": f"Dropped all capabilities ({','.join(self.policy.drop_capabilities)})",
            "privilege_escalation": "no-new-privileges flag enabled",
            "rootfs_protection": "Read-only container root filesystem (--read-only)",
            "controlled_mounts": {
                "tmpfs_tmp": self.policy.tmpfs_mounts.get("/tmp", "rw,noexec,nosuid,size=64m"),
                "workspace_mount": f"{str(self.repo_path)} -> {self.policy.workspace_mount_path} (rw)",
            },
        }

    def build_container_args(self, container_name: str, cmd: List[str]) -> List[str]:
        """Constructs security-hardened container invocation arguments with controlled mounts."""
        args = [
            self.runtime_binary or "docker",
            "run",
            "--rm",
            f"--name={container_name}",
            # Security: Non-root user and group
            f"--user={self.policy.non_root_user}",
            # Security: Complete kernel network air-gapping (CLONE_NEWNET)
            f"--network={self.policy.network_mode}",
            # Security: Cgroup memory quota
            f"--memory={self.policy.memory_limit_mb}m",
            f"--memory-swap={self.policy.memory_limit_mb}m",
            # Security: CPU allocation
            f"--cpus={self.policy.cpu_limit}",
            # Security: Prevent fork bombs
            f"--pids-limit={self.policy.pids_limit}",
            # Security: Drop all Linux capabilities
            f"--cap-drop={','.join(self.policy.drop_capabilities)}",
            # Security: Prevent SUID privilege escalation
            "--security-opt=no-new-privileges",
        ]

        # Security: Read-only container rootfs
        if self.policy.read_only_rootfs:
            args.append("--read-only")

        # Security: Carefully controlled temporary writable mounts (noexec, nosuid, size-capped)
        for mount_point, opts in self.policy.tmpfs_mounts.items():
            args.append(f"--tmpfs={mount_point}:{opts}")

        # Security: Controlled workspace mount strictly scoped to target repo
        args.extend([
            "-v", f"{str(self.repo_path)}:{self.policy.workspace_mount_path}:{self.policy.workspace_mount_options}",
            "-w", self.policy.workspace_mount_path,
            self.image_name,
        ])

        # Target command inside container
        args.extend(cmd)
        return args

    def run_command(self, cmd: List[str]) -> ExecutionOutput:
        """Executes a command inside an isolated disposable container with deterministic cleanup."""
        if not self.is_available():
            raise RuntimeError("Container runtime (docker/podman) is not available or daemon is offline.")

        container_name = f"sandbox-{uuid.uuid4().hex[:12]}"
        container_args = self.build_container_args(container_name, cmd)

        if self.barrier:
            self.barrier.register_container(container_name, self.runtime_binary or "docker")

        t0 = time.time()
        process = None
        timed_out = False
        truncated = False

        try:
            process = subprocess.Popen(
                container_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if self.barrier:
                self.barrier.register_pid(process.pid)

            try:
                stdout_raw, stderr_raw = process.communicate(timeout=self.policy.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                self._force_cleanup(container_name)
                try:
                    stdout_raw, stderr_raw = process.communicate(timeout=3)
                except Exception:
                    stdout_raw, stderr_raw = "", "Process execution timed out."

            # Enforce output limits
            stdout_str = stdout_raw or ""
            stderr_str = stderr_raw or ""
            if len(stdout_str.encode("utf-8")) > self.policy.max_output_bytes:
                stdout_str = stdout_str[: self.policy.max_output_bytes] + "\n[OUTPUT TRUNCATED: Exceeded buffer limit]"
                truncated = True
            if len(stderr_str.encode("utf-8")) > self.policy.max_output_bytes:
                stderr_str = stderr_str[: self.policy.max_output_bytes] + "\n[OUTPUT TRUNCATED: Exceeded buffer limit]"
                truncated = True

            duration = time.time() - t0
            returncode = 124 if timed_out else (process.returncode if process else 1)

            return ExecutionOutput(
                returncode=returncode,
                stdout=stdout_str,
                stderr=stderr_str,
                duration_seconds=round(duration, 3),
                timed_out=timed_out,
                output_truncated=truncated,
                isolation_level=IsolationLevel.CONTAINER.value,
                security_metadata={
                    **self.get_container_spec(),
                    "container_id": container_name,
                },
            )

        finally:
            self._force_cleanup(container_name)

    def _force_cleanup(self, container_name: str):
        """Ensures that any container process is terminated and cleaned up."""
        if not self.runtime_binary:
            return
        try:
            subprocess.run(
                [self.runtime_binary, "rm", "-f", container_name],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass

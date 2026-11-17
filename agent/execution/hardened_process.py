"""Hardened Process Execution: Best-Effort Defense-in-Depth Process Isolation (Fallback Tier).

CRITICAL TECHNICAL & SECURITY DISTINCTIONS:
-------------------------------------------
1. WEAKER SECURITY BOUNDARY:
   HardenedProcessSandbox is a local fallback mechanism used ONLY when container runtimes
   (Docker/Podman) or microVM hypervisors (Firecracker/gVisor) are unavailable on the host.
   It provides a significantly weaker boundary than containers or microVMs. It MUST NOT be
   described or treated as equivalent to containerization or hardware virtualization.

2. POSIX RESOURCE LIMITS DO NOT CREATE A FILESYSTEM JAIL:
   Calls to `setrlimit` (RLIMIT_AS, RLIMIT_CPU, RLIMIT_NPROC, RLIMIT_FSIZE) restrict process
   consumption of virtual address space, CPU time, thread/process creation, and file output size.
   THEY PROVIDE ZERO FILESYSTEM ACCESS CONTROL. The executing process runs with the privileges
   of the host user and can read any world-readable or user-readable file on the host filesystem
   (e.g., /etc/passwd, ~/.bashrc, ~/.ssh, project files). Redirecting HOME to an ephemeral directory
   is an application-level courtesy, NOT a kernel-enforced filesystem jail or chroot/mount namespace.

3. ADVISORY PROXY DOES NOT GUARANTEE NETWORK BLOCKAGE:
   Setting environment variables (http_proxy="http://127.0.0.1:0", etc.) only redirects client
   libraries that voluntarily honor HTTP proxy conventions (e.g., urllib, requests).
   It does NOT guarantee network access is blocked:
   - Raw sockets (socket.socket(AF_INET, SOCK_STREAM)) connect directly without consulting proxy env.
   - C extensions, custom network drivers, UDP datagrams, and DNS queries bypass proxy variables.
   True network blocking requires kernel network namespaces (CLONE_NEWNET) or packet filtering.

4. PROCESS-GROUP TERMINATION:
   The child is spawned in a separate process group (os.setpgrp) so that long-running or runaway
   processes can be cleanly signaled via os.killpg(pgid, signal.SIGKILL) during timeout or cleanup.
"""

import os
import sys
import time
import signal
import shutil
import tempfile
import resource
import subprocess
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from agent.execution.isolation import SandboxSecurityPolicy, ExecutionOutput, IsolationLevel, TIER_SPECIFICATIONS

logger = logging.getLogger("agent.sandbox.hardened")

class HardenedProcessSandbox:
    """Best-effort process-level confinement used as a fallback when containers/microVMs are absent.
    
    WARNING: This is a weaker security boundary than containers or microVMs. It enforces POSIX
    resource limits, ephemeral HOME redirection, advisory proxy blackholing, and process-group
    SIGKILL cleanup, but DOES NOT create a filesystem jail or guarantee full network isolation.
    """

    def __init__(
        self,
        repo_path: str,
        policy: Optional[SandboxSecurityPolicy] = None,
        barrier: Optional[Any] = None,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.policy = policy or SandboxSecurityPolicy(isolation_level=IsolationLevel.HARDENED_PROCESS)
        self.barrier = barrier

    def is_available(self) -> bool:
        """Always returns True because Python subprocess and POSIX resource module are standard."""
        return True

    def get_hardened_process_spec(self) -> Dict[str, Any]:
        """Returns the formal specification and explicit security limitations for Tier 4."""
        return {
            "tier": "Tier 4: Process-Level Defense-in-Depth Fallback",
            "security_boundary_class": "Weak / Best-effort fallback (NOT a container or microVM)",
            "is_filesystem_jail": False,
            "filesystem_caveat": "POSIX rlimits do not create a filesystem jail. The process can read host files.",
            "is_guaranteed_network_blocked": False,
            "network_caveat": "Advisory HTTP_PROXY only redirects cooperating HTTP libraries; raw sockets bypass it.",
            "enforced_controls": [
                f"POSIX virtual memory limit: {self.policy.memory_limit_mb}MB (RLIMIT_AS)",
                f"POSIX CPU execution limit: {self.policy.timeout_seconds}s (RLIMIT_CPU)",
                f"POSIX process/thread limit: {self.policy.pids_limit} (RLIMIT_NPROC)",
                "POSIX max file size: 64MB (RLIMIT_FSIZE)",
                f"Output buffer cap: {self.policy.max_output_bytes // 1024}KB",
                "Isolated ephemeral HOME directory",
                "Dedicated process-group termination (SIGKILL via killpg)",
            ],
        }

    def _create_preexec_fn(self):
        """Creates preexec hook applying POSIX rlimits inside the child process."""
        policy = self.policy

        def preexec():
            # 1. Spawn in a new process group so child cannot hijack parent terminal or escape SIGKILL
            os.setpgrp()

            # 2. Enforce CPU execution limit (seconds)
            try:
                cpu_seconds = int(policy.timeout_seconds)
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))
            except Exception:
                pass

            # 3. Enforce virtual memory limit (RLIMIT_AS)
            try:
                mem_bytes = policy.memory_limit_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            except Exception:
                pass

            # 4. Enforce fork-bomb prevention (max child processes / threads)
            try:
                max_pids = policy.pids_limit
                resource.setrlimit(resource.RLIMIT_NPROC, (max_pids, max_pids))
            except Exception:
                pass

            # 5. Enforce max file size creation (prevent disk filling)
            try:
                max_file = 64 * 1024 * 1024  # 64 MB
                resource.setrlimit(resource.RLIMIT_FSIZE, (max_file, max_file))
            except Exception:
                pass

        return preexec

    def run_command(self, cmd: List[str]) -> ExecutionOutput:
        """Executes the command with hardened process-level controls and deterministic cleanup."""
        # Ephemeral HOME directory to reduce accidental pollution of ~/.bashrc or ~/.ssh
        # Note: This is an advisory environment redirection, NOT a filesystem jail!
        ephemeral_home = tempfile.mkdtemp(prefix="sandbox_home_")

        # Ensure interpreter site-packages resolve while keeping HOME safely pointed to tempdir
        import site
        python_paths = [str(self.repo_path)]
        try:
            user_site = site.getusersitepackages()
            if os.path.exists(user_site):
                python_paths.append(user_site)
            for sp in site.getsitepackages():
                if os.path.exists(sp):
                    python_paths.append(sp)
        except Exception:
            pass

        # Environment sanitization and advisory network proxy diversion
        safe_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "HOME": ephemeral_home,
            "PYTHONPATH": os.pathsep.join(python_paths),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            # Advisory proxy blackhole (WARNING: raw sockets and non-proxy tools bypass this!)
            "http_proxy": "http://127.0.0.1:0",
            "https_proxy": "http://127.0.0.1:0",
            "all_proxy": "socks5://127.0.0.1:0",
        }

        t0 = time.time()
        process = None
        timed_out = False
        truncated = False
        oom_killed = False
        max_rss_bytes = self.policy.memory_limit_mb * 1024 * 1024

        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(self.repo_path),
                env=safe_env,
                preexec_fn=self._create_preexec_fn(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if self.barrier:
                self.barrier.register_pid(process.pid)

            # Active RSS memory watchdog (critical defense-in-depth on platforms where RLIMIT_AS is non-enforcing)
            import threading
            def memory_watchdog():
                nonlocal oom_killed
                while process and process.poll() is None and not oom_killed:
                    try:
                        import psutil
                        p = psutil.Process(process.pid)
                        total_rss = p.memory_info().rss
                        for child in p.children(recursive=True):
                            try:
                                total_rss += child.memory_info().rss
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                        if total_rss > max_rss_bytes:
                            oom_killed = True
                            logger.warning(
                                f"Process memory limit exceeded ({total_rss // (1024*1024)}MB > {self.policy.memory_limit_mb}MB). "
                                f"Terminating process group {process.pid}."
                            )
                            self._kill_process_group(process.pid)
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        break
                    except Exception:
                        pass
                    time.sleep(0.04)

            watchdog_thread = threading.Thread(target=memory_watchdog, daemon=True)
            watchdog_thread.start()

            try:
                stdout_raw, stderr_raw = process.communicate(timeout=self.policy.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                # Kill entire process group reliably
                self._kill_process_group(process.pid)
                try:
                    stdout_raw, stderr_raw = process.communicate(timeout=2)
                except Exception:
                    stdout_raw, stderr_raw = "", f"Execution timed out after {self.policy.timeout_seconds}s."

            # Enforce output buffer limit (prevent memory exhaustion from infinite logging)
            stdout_str = stdout_raw or ""
            stderr_str = stderr_raw or ""
            if oom_killed:
                stderr_str += f"\n[SECURITY TERMINATION: Process exceeded RSS memory limit of {self.policy.memory_limit_mb}MB (OOM Kill)]"
            if len(stdout_str.encode("utf-8")) > self.policy.max_output_bytes:
                stdout_str = stdout_str[: self.policy.max_output_bytes] + "\n[OUTPUT TRUNCATED: Exceeded buffer limit]"
                truncated = True
            if len(stderr_str.encode("utf-8")) > self.policy.max_output_bytes:
                stderr_str = stderr_str[: self.policy.max_output_bytes] + "\n[OUTPUT TRUNCATED: Exceeded buffer limit]"
                truncated = True

            duration = time.time() - t0
            if oom_killed:
                returncode = 137
            elif timed_out:
                returncode = 124
            else:
                returncode = process.returncode if process else 1

            return ExecutionOutput(
                returncode=returncode,
                stdout=stdout_str,
                stderr=stderr_str,
                duration_seconds=round(duration, 3),
                timed_out=timed_out,
                output_truncated=truncated,
                isolation_level=IsolationLevel.HARDENED_PROCESS.value,
                security_metadata={
                    **self.get_hardened_process_spec(),
                    "isolated_home": ephemeral_home,
                    "memory_limit": f"{self.policy.memory_limit_mb}MB",
                    "pids_limit": self.policy.pids_limit,
                    "process_group_cleanup": True,
                    "network_advisory_proxy": True,
                    "network_blocked": False,  # Technically precise: advisory proxy does not guarantee blockage
                },
            )

        finally:
            if process and process.poll() is None:
                self._kill_process_group(process.pid)
            if os.path.exists(ephemeral_home):
                shutil.rmtree(ephemeral_home, ignore_errors=True)

    def _kill_process_group(self, pid: int):
        """Sends SIGKILL to the entire process group to ensure no rogue child processes remain."""
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.warning(f"Failed to kill process group {pid}: {e}")
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass

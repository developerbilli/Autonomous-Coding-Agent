"""Process Destruction Barrier & Anti-TOCTOU Execution Verification.

CRITICAL SECURITY PURPOSE:
--------------------------
Prevents Time-of-Check to Time-of-Use (TOCTOU) credential exfiltration.
When an untrusted repository or agent-executed code runs, rogue processes,
background loops, daemon threads, or detached containers could attempt to linger
and wait for quarantined secrets (.env, keys) to be restored upon task completion.

The ProcessDestructionBarrier guarantees:
1. All child processes, process groups, and container runtimes are actively tracked.
2. Before any secret restoration or workspace finalization, all tracked processes
   receive SIGTERM, followed by SIGKILL to the entire process group (killpg).
3. Active containers are forcefully killed and removed (docker kill / rm -f).
4. Secret restoration is strictly REFUSED (raises ProcessBarrierViolationError)
   if any untrusted execution process remains alive.
"""

import os
import signal
import time
import subprocess
import logging
from typing import List, Set, Dict, Optional, Tuple, Any

logger = logging.getLogger("agent.execution.barrier")


class ProcessBarrierViolationError(RuntimeError):
    """Raised when an attempt is made to restore secrets while untrusted processes remain active."""
    pass


class ProcessDestructionBarrier:
    """Tracks and enforces verified destruction of all sandbox processes and containers."""

    def __init__(self):
        self._tracked_pids: Dict[int, Optional[int]] = {}  # pid -> pgid
        self._tracked_containers: Set[Tuple[str, str]] = set()  # (container_name, runtime_bin)

    def register_pid(self, pid: int, pgid: Optional[int] = None):
        """Registers a process ID and its process group ID for lifecycle tracking."""
        if pid <= 0 or pid == os.getpid():
            return
        if pgid is None:
            try:
                pgid = os.getpgid(pid)
            except Exception:
                pgid = None
        self._tracked_pids[pid] = pgid
        logger.debug(f"Registered PID {pid} (PGID: {pgid}) with ProcessDestructionBarrier")

    def register_container(self, container_name: str, runtime_binary: str = "docker"):
        """Registers a container instance name and runtime binary."""
        if container_name:
            self._tracked_containers.add((container_name, runtime_binary))
            logger.debug(f"Registered container '{container_name}' with ProcessDestructionBarrier")

    def is_pid_alive(self, pid: int) -> bool:
        """Checks if a given process ID is still alive."""
        if pid <= 0:
            return False
        try:
            # Reap zombie if this process happens to be the parent
            try:
                waited_pid, _ = os.waitpid(pid, os.WNOHANG)
                if waited_pid == pid:
                    return False
            except (ChildProcessError, ProcessLookupError):
                pass

            # Signal 0 performs error checking without sending a signal
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but owned by another user / restricted
            return True
        except Exception:
            return False

    def is_container_alive(self, container_name: str, runtime_binary: str) -> bool:
        """Checks if a container is still running."""
        try:
            res = subprocess.run(
                [runtime_binary, "inspect", "-f", "{{.State.Running}}", container_name],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return res.returncode == 0 and res.stdout.strip().lower() == "true"
        except Exception:
            return False

    def is_any_alive(self) -> bool:
        """Returns True if any tracked process or container is currently running."""
        # 1. Check PIDs
        for pid in list(self._tracked_pids.keys()):
            if self.is_pid_alive(pid):
                return True

        # 2. Check Containers
        for container_name, runtime_bin in list(self._tracked_containers):
            if self.is_container_alive(container_name, runtime_bin):
                return True

        return False

    def get_active_summary(self) -> Dict[str, Any]:
        """Returns a diagnostic summary of currently alive processes and containers."""
        alive_pids = [pid for pid in self._tracked_pids.keys() if self.is_pid_alive(pid)]
        alive_containers = [c[0] for c in self._tracked_containers if self.is_container_alive(c[0], c[1])]
        return {
            "alive_pids_count": len(alive_pids),
            "alive_pids": alive_pids,
            "alive_containers_count": len(alive_containers),
            "alive_containers": alive_containers,
            "is_clean": len(alive_pids) == 0 and len(alive_containers) == 0,
        }

    def terminate_all(self, grace_seconds: float = 0.5) -> bool:
        """Enforces termination of all tracked containers and process groups.
        
        Sequence:
        1. Force-kill and remove all tracked containers (docker rm -f).
        2. Send SIGTERM to process groups, wait grace period.
        3. Send SIGKILL to process groups for any stubborn survivors.
        4. Verify that no tracked processes remain alive.
        """
        # Step 1: Force remove all tracked containers
        for container_name, runtime_bin in list(self._tracked_containers):
            try:
                subprocess.run(
                    [runtime_bin, "rm", "-f", container_name],
                    capture_output=True,
                    timeout=5,
                )
            except Exception as e:
                logger.debug(f"Error removing container {container_name}: {e}")

        # Step 2: Graceful SIGTERM to process groups
        for pid, pgid in list(self._tracked_pids.items()):
            if not self.is_pid_alive(pid):
                continue
            try:
                if pgid and pgid > 1 and pgid != os.getpgrp():
                    os.killpg(pgid, signal.SIGTERM)
                else:
                    os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

        if grace_seconds > 0 and any(self.is_pid_alive(p) for p in self._tracked_pids.keys()):
            time.sleep(grace_seconds)

        # Step 3: Unconditional SIGKILL to process groups
        for pid, pgid in list(self._tracked_pids.items()):
            if not self.is_pid_alive(pid):
                continue
            try:
                if pgid and pgid > 1 and pgid != os.getpgrp():
                    os.killpg(pgid, signal.SIGKILL)
                else:
                    os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

        time.sleep(0.1)

        # Step 4: Reap any direct children to clean up zombie states
        for pid in list(self._tracked_pids.keys()):
            try:
                os.waitpid(pid, os.WNOHANG)
            except (ChildProcessError, ProcessLookupError):
                pass

        # Step 5: Final verification barrier
        return not self.is_any_alive()

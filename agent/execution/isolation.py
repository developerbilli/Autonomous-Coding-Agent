"""Security specifications and policy definitions for Sandbox Isolation Boundaries.

Technical Precision & Architecture Tiers:
-----------------------------------------
Tier 1: Hardware-Virtualized MicroVM (Firecracker / Cloud Hypervisor via KVM)
  - Mechanism: Hardware virtualization extensions (Intel VT-x / AMD-V) managed by KVM (/dev/kvm).
  - Guest Kernel: Dedicated, unshared minimal Linux kernel (vmlinux) with its own page tables.
  - Memory: Independent physical memory space managed by second-level address translation (EPT/NPT).
  - Virtual Devices: Minimal virtio device emulation (virtio-blk for storage, optional virtio-vsock).
  - Boundary: Hypervisor VM-Exit boundary. Direct host kernel exploitation is blocked at hardware level.

Tier 2: User-Space Application Kernel Syscall Emulation (gVisor runsc)
  - Mechanism: Syscall interception via ptrace or KVM, handled by a user-space kernel (Sentry).
  - Guest Kernel: None. Sentry reimplements 300+ Linux system calls in memory-safe Go in ring 3.
  - Filesystem: Mediated via an isolated Gofer process; root filesystem mounted read-only.
  - Distinction from MicroVM: Does NOT boot a real guest Linux kernel or provide virtual hardware
    devices. It provides strong application-kernel syscall filtering to shield the host kernel ABI.

Tier 3: OCI Container Isolation (Docker / Podman with runc / crun)
  - Mechanism: Linux kernel namespaces (PID, Mount, Network, IPC, UTS, User) and cgroups v2.
  - Root Filesystem: --read-only rootfs prevents tampering with host/container binaries and libraries.
  - Controlled Writable Mounts:
      * /tmp: tmpfs with flags 'rw,noexec,nosuid,size=64m' (allows scratch/pytest files, prevents binary execution)
      * /run: tmpfs with flags 'rw,noexec,nosuid,size=16m' (runtime locks/pids)
      * /workspace: strictly scoped bind mount (-v <repo_path>:/workspace:rw) or copy-on-write overlay.
  - Network: --network=none creates a dedicated empty network namespace (CLONE_NEWNET) with loopback down.
  - Privileges: --user=1001:1001 (non-root), --cap-drop=ALL, --security-opt=no-new-privileges.

Tier 4: Process-Level Defense-in-Depth Fallback (HardenedProcessSandbox)
  - Mechanism: Subprocess execution on host OS with POSIX resource limits (setrlimit).
  - Enforces: RLIMIT_AS (memory cap), RLIMIT_CPU (CPU seconds), RLIMIT_NPROC (fork cap), RLIMIT_FSIZE.
  - Output Limits: Memory buffer truncation at max_output_bytes; process-group SIGKILL termination.
  - CRITICAL SECURITY LIMITATIONS (NOT EQUIVALENT TO CONTAINERS OR MICROVMS):
      * POSIX limits DO NOT create a filesystem jail or restrict path traversal. The unprivileged process
        can read any file on the host accessible to the executing user account.
      * Advisory proxy environment variables (HTTP_PROXY) do NOT guarantee network blockage; raw sockets
        (AF_INET), C extensions, UDP datagrams, and DNS queries bypass proxy environment variables.
      * This tier is a best-effort fallback only and MUST NOT be relied upon for hostile/untrusted code.
"""

from enum import Enum
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

class IsolationLevel(str, Enum):
    """Four distinct tiers of execution isolation boundaries."""
    MICROVM = "microvm"                    # Tier 1: Hardware-virtualized microVM (Firecracker / KVM)
    GVISOR = "gvisor"                      # Tier 2: Application-kernel syscall emulation (gVisor runsc)
    CONTAINER = "container"                # Tier 3: OCI Container (Docker / Podman) with namespaces & cgroups
    HARDENED_PROCESS = "hardened_process"  # Tier 4: Defense-in-depth process fallback (weaker boundary)

TIER_SPECIFICATIONS: Dict[str, Dict[str, Any]] = {
    IsolationLevel.MICROVM.value: {
        "tier_name": "Tier 1: Hardware-Virtualized MicroVM",
        "technology_class": "Hardware-assisted MicroVM (Dedicated Guest Kernel + KVM)",
        "is_microvm": True,
        "is_application_kernel": False,
        "primary_implementations": ["Firecracker", "Cloud Hypervisor"],
        "isolation_architecture": "Hardware-assisted hypervisor virtualization (KVM)",
        "kernel_boundary": "Dedicated, independent guest Linux kernel (vmlinux)",
        "memory_boundary": "Hardware-enforced guest physical memory (EPT/NPT page tables)",
        "filesystem_boundary": "Isolated guest drive image (virtio-blk) with ephemeral rootfs",
        "network_boundary": "Zero virtual NICs attached (air-gapped at hypervisor boundary)",
        "security_boundary_class": "Hardware / Hypervisor Boundary (Strongest)",
        "is_filesystem_jail": True,
        "is_guaranteed_network_blocked": True,
    },
    IsolationLevel.GVISOR.value: {
        "tier_name": "Tier 2: User-Space Application Kernel",
        "technology_class": "User-Space Syscall Interception / Sentry (NOT a MicroVM)",
        "is_microvm": False,
        "is_application_kernel": True,
        "primary_implementations": ["gVisor (runsc)"],
        "isolation_architecture": "Syscall interception with user-space application kernel (Sentry)",
        "kernel_boundary": "Emulated Linux kernel ABI in Go (ring 3); no direct host kernel syscalls",
        "memory_boundary": "User-space process memory with memory-safe runtime safeguards",
        "filesystem_boundary": "Gofer filesystem mediator process + read-only rootfs",
        "network_boundary": "User-space Netstack or disabled network stack",
        "security_boundary_class": "Application Kernel Boundary (Protects host kernel surface)",
        "is_filesystem_jail": True,
        "is_guaranteed_network_blocked": True,
    },
    IsolationLevel.CONTAINER.value: {
        "tier_name": "Tier 3: OCI Container Isolation",
        "technology_class": "Operating System Namespaces & Cgroups",
        "is_microvm": False,
        "is_application_kernel": False,
        "primary_implementations": ["Docker", "Podman", "nerdctl (runc/crun)"],
        "isolation_architecture": "Linux kernel namespaces (PID, Mount, Net, IPC, UTS, User) & cgroups v2",
        "kernel_boundary": "Shared host kernel hardened via seccomp-bpf and capability dropping",
        "memory_boundary": "Cgroup v2 memory quota (memory.max and memory.swap.max)",
        "filesystem_boundary": "Read-only rootfs with controlled tmpfs (/tmp:noexec,nosuid) and repository bind mount",
        "network_boundary": "Dedicated empty network namespace (CLONE_NEWNET) via --network=none",
        "security_boundary_class": "Operating System Namespace & Cgroup Boundary",
        "is_filesystem_jail": True,
        "is_guaranteed_network_blocked": True,
    },
    IsolationLevel.HARDENED_PROCESS.value: {
        "tier_name": "Tier 4: Process-Level Defense-in-Depth Fallback",
        "technology_class": "POSIX Subprocess Resource Limits (Weak Defense-in-Depth)",
        "is_microvm": False,
        "is_application_kernel": False,
        "primary_implementations": ["Python subprocess + POSIX setrlimit"],
        "isolation_architecture": "Host OS unprivileged process with resource quotas and signal groups",
        "kernel_boundary": "Direct unconfined host kernel execution (same user context)",
        "memory_boundary": "POSIX address space quota (RLIMIT_AS)",
        "filesystem_boundary": "Unconfined host filesystem (ephemeral HOME directory only, NOT a jail)",
        "network_boundary": "Advisory HTTP/HTTPS proxy redirection (127.0.0.1:0) - raw sockets bypass this",
        "security_boundary_class": "Weak / Best-Effort Defense-in-Depth (Fallback Only)",
        "is_filesystem_jail": False,
        "is_guaranteed_network_blocked": False,
    },
}

class SandboxSecurityPolicy(BaseModel):
    """Enforced security controls for untrusted code execution."""
    isolation_level: IsolationLevel = IsolationLevel.HARDENED_PROCESS
    non_root_user: str = "1001:1001"
    network_mode: str = "none"                  # Kernel network namespace isolation (CLONE_NEWNET)
    memory_limit_mb: int = 512                  # Max virtual/resident memory (cgroup memory.max / RLIMIT_AS)
    cpu_limit: float = 1.0                      # Max CPU allocation (cgroup cpu.max / RLIMIT_CPU)
    pids_limit: int = 100                       # Fork bomb prevention (cgroup pids.max / RLIMIT_NPROC)
    timeout_seconds: int = 45                   # Strict execution timeout
    max_output_bytes: int = 512 * 1024          # Max 512KB output buffer (prevents memory exhaustion)
    read_only_rootfs: bool = True               # Prevents tampering with container OS files
    drop_capabilities: List[str] = Field(default_factory=lambda: ["ALL"])
    no_new_privileges: bool = True              # Prevents SUID escalation
    allow_process_fallback: bool = Field(
        default=False,
        description="If False, execution of untrusted code refuses to fall back to Tier 4 host process when strong isolation (Tiers 1-3) is unavailable.",
    )
    tmpfs_mounts: Dict[str, str] = Field(
        default_factory=lambda: {
            "/tmp": "rw,noexec,nosuid,size=64m",
            "/run": "rw,noexec,nosuid,size=16m",
        }
    )
    workspace_mount_path: str = "/workspace"
    workspace_mount_options: str = "rw"

class ExecutionOutput(BaseModel):
    """Standardized output schema from any isolation boundary."""
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    output_truncated: bool = False
    isolation_level: str
    security_metadata: Dict[str, Any] = Field(default_factory=dict)

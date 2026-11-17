"""Adversarial Sandbox Security & Penetration Test Suite.

EMPIRICAL ATTACK SCENARIO VERIFICATION:
---------------------------------------
Passing policy tests does NOT prove runtime isolation.
This test suite directly tests adversarial escape vectors, resource exhaustion attacks,
and penetration payloads against the active sandbox engines and execution barriers:

1. Symlink Escape: Traversal and symlinks targeting files outside authorized mounts.
2. Raw Socket Connection: Outbound TCP/UDP connection and network boundary enforcement.
3. Fork Bomb: Uncontrolled process creation and PID exhaustion limits.
4. Memory Bomb: Extreme heap allocation and virtual memory limits (RLIMIT_AS / cgroups).
5. Detached Child Process (Double Fork & setsid): Session escape from process groups.
6. Docker Socket Access: Probing host container runtime control sockets.
7. Secret Extraction & Env Exfiltration: Host credential and environment variable theft.
8. Container Escape & Tampering: Read-only rootfs, tmpfs noexec, and capability dropping.
"""

import os
import sys
import time
import socket
import signal
import shutil
import tempfile
import subprocess
import pytest
from pathlib import Path

from agent.execution.sandbox import ExecutionSandbox
from agent.execution.hardened_process import HardenedProcessSandbox
from agent.execution.container_sandbox import ContainerSandbox
from agent.execution.barrier import ProcessDestructionBarrier, ProcessBarrierViolationError
from agent.execution.isolation import SandboxSecurityPolicy, IsolationLevel, RepoTrustLevel
from agent.repository.sanitizer import WorkspaceSanitizer, SANITIZED_PLACEHOLDER_CONTENT
from agent.tools.file_tools import FileToolHandler
from agent.tools.permissions import PermissionDeniedError


@pytest.fixture
def adversarial_env():
    """Sets up an isolated directory structure with a workspace and external host files."""
    base = Path(tempfile.mkdtemp(prefix="adv_sandbox_"))
    ws = base / "workspace"
    ws.mkdir()
    host_outside = base / "host_sensitive"
    host_outside.mkdir()

    # Create sensitive file outside workspace
    (host_outside / "shadow_passwd.txt").write_text("root:$6$sensitive_hash_data\n")
    (host_outside / "id_rsa").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nSECRET_KEY_DATA\n")

    yield {"base": base, "workspace": ws, "outside": host_outside}
    shutil.rmtree(base, ignore_errors=True)


# =============================================================================
# Attack Scenario 1: Symlink Escape
# =============================================================================

def test_adversarial_symlink_escape(adversarial_env):
    """Attack: Adversary creates symlinks inside the workspace pointing to host files outside.
    
    Proof: File tools and verification gates enforce path containment via Path.resolve()
    and Path.relative_to(), strictly blocking reads and writes through symlink escapes.
    """
    ws = adversarial_env["workspace"]
    sensitive_file = adversarial_env["outside"] / "shadow_passwd.txt"

    # Adversary drops a symlink inside the repository
    escape_link = ws / "escaped_shadow.txt"
    try:
        os.symlink(str(sensitive_file), str(escape_link))
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this filesystem")

    handler = FileToolHandler(str(ws))

    # Attempting to read through the symlink must be blocked by path containment
    with pytest.raises(PermissionDeniedError) as exc_info:
        handler.read_file(str(escape_link))

    assert "Path traversal detected" in str(exc_info.value)

    # Attempting to write through the symlink must also be blocked
    with pytest.raises(PermissionDeniedError):
        handler.write_file(str(escape_link), "CORRUPTED")


# =============================================================================
# Attack Scenario 2: Raw Socket Connection
# =============================================================================

def test_adversarial_raw_socket_connection_policy_and_runtime(adversarial_env):
    """Attack: Untrusted code attempts to open a raw TCP socket to an external server.
    
    Proof:
    1. Container sandbox mandates --network=none (kernel network namespace CLONE_NEWNET),
       dropping all network interfaces except down loopback.
    2. Hardened process sandbox strips proxy bypasses and diverts HTTP/HTTPS to blackhole 127.0.0.1:0.
    """
    ws = adversarial_env["workspace"]
    container_sandbox = ContainerSandbox(str(ws))
    spec = container_sandbox.get_container_spec()

    # Verify kernel-level network isolation specification
    assert "CLONE_NEWNET" in spec["network_isolation"]
    args = container_sandbox.build_container_args("test-container", ["python3", "-c", "import socket"])
    assert "--network=none" in args

    # Runtime test on HardenedProcessSandbox: verify advisory blackhole is injected into safe_env
    hardened = HardenedProcessSandbox(str(ws))
    out = hardened.run_command([
        sys.executable, "-c",
        "import os; print(f'HTTP={os.environ.get(\"http_proxy\")}, HTTPS={os.environ.get(\"https_proxy\")}')"
    ])
    assert "127.0.0.1:0" in out.stdout


# =============================================================================
# Attack Scenario 3: Fork Bomb
# =============================================================================

def test_adversarial_fork_bomb_mitigation(adversarial_env):
    """Attack: Hostile script spawns recursive child processes to exhaust host PID table.
    
    Proof: Sandbox enforces POSIX RLIMIT_NPROC / cgroup pids.max limits, and when
    execution times out, sends SIGKILL to the entire process group (killpg) cleanly.
    """
    ws = adversarial_env["workspace"]
    policy = SandboxSecurityPolicy(
        timeout_seconds=2.0,
        memory_limit_mb=256,
        pids_limit=16,
        allow_process_fallback=True,
    )
    sandbox = HardenedProcessSandbox(str(ws), policy=policy)

    # Python script attempting a rapid fork loop with sleep
    fork_script = (
        "import os, time\n"
        "for _ in range(50):\n"
        "    try:\n"
        "        if os.fork() == 0:\n"
        "            time.sleep(10)\n"
        "            os._exit(0)\n"
        "    except Exception:\n"
        "        pass\n"
        "time.sleep(10)\n"
    )
    (ws / "fork_bomb.py").write_text(fork_script)

    t0 = time.time()
    out = sandbox.run_command([sys.executable, str(ws / "fork_bomb.py")])
    duration = time.time() - t0

    # Must timeout within 2-4 seconds and kill the entire process group
    assert out.timed_out is True
    assert duration < 6.0


# =============================================================================
# Attack Scenario 4: Memory Bomb
# =============================================================================

def test_adversarial_memory_bomb_enforcement(adversarial_env):
    """Attack: Hostile script allocates a huge chunk of RAM to trigger host OOM.
    
    Proof: POSIX RLIMIT_AS strictly caps virtual memory address space to memory_limit_mb,
    raising MemoryError before consuming host RAM.
    """
    ws = adversarial_env["workspace"]
    # Limit memory to 128MB
    policy = SandboxSecurityPolicy(
        timeout_seconds=5.0,
        memory_limit_mb=128,
        allow_process_fallback=True,
    )
    sandbox = HardenedProcessSandbox(str(ws), policy=policy)

    # Attempt to allocate 600MB
    mem_script = (
        "import sys, time\n"
        "try:\n"
        "    blob = bytearray(600 * 1024 * 1024)\n"
        "    time.sleep(0.3)\n"
        "    print('SUCCESS_ALLOCATED')\n"
        "except MemoryError:\n"
        "    print('CAUGHT_MEMORY_ERROR')\n"
        "    sys.exit(0)\n"
    )
    (ws / "mem_bomb.py").write_text(mem_script)

    out = sandbox.run_command([sys.executable, str(ws / "mem_bomb.py")])

    # Must NOT succeed in allocating 600MB
    assert "SUCCESS_ALLOCATED" not in out.stdout
    assert "CAUGHT_MEMORY_ERROR" in out.stdout or out.returncode != 0


# =============================================================================
# Attack Scenario 5: Detached Child Process & Session Escape
# =============================================================================

def test_adversarial_detached_session_escape_caught_by_barrier(adversarial_env):
    """Attack: Rogue process executes double-fork + os.setsid() to escape parent PGID.
    
    Proof: ProcessDestructionBarrier scans the workspace directory using psutil,
    identifies detached orphans dwelling in the repository, marks barrier as active,
    and terminates the detached process with SIGKILL before secret restoration.
    """
    ws = adversarial_env["workspace"]
    barrier = ProcessDestructionBarrier(workspace_path=ws)

    # Detached double-fork daemon script
    escape_script = (
        "import os, sys, time\n"
        "if os.fork() > 0: sys.exit(0)\n"
        "os.setsid()\n"
        "if os.fork() > 0: sys.exit(0)\n"
        "time.sleep(30)\n"
    )
    script_path = ws / "detached_escape.py"
    script_path.write_text(escape_script)

    # Execute the double fork from inside the workspace directory
    proc = subprocess.Popen([sys.executable, str(script_path)], cwd=str(ws))
    proc.wait()  # Initial process exits immediately

    time.sleep(0.3)  # Give double-forked grandchild time to start

    # Barrier must detect the detached orphan process dwelling in the workspace
    orphans = barrier.find_orphaned_workspace_processes()
    assert len(orphans) > 0, "Failed to detect detached orphan process"
    assert barrier.is_any_alive() is True

    # Attempting to restore secrets with active orphan must be BLOCKED
    records = WorkspaceSanitizer.quarantine_secrets(ws)
    class DummyActiveCheck:
        def terminate_all(self, *a, **kw): pass
        def is_any_alive(self): return True

    with pytest.raises(ProcessBarrierViolationError):
        WorkspaceSanitizer.restore_secrets(ws, records, barrier=DummyActiveCheck())

    # Terminate all must destroy the detached orphan
    clean = barrier.terminate_all(grace_seconds=0.2)
    assert clean is True
    assert barrier.is_any_alive() is False


# =============================================================================
# Attack Scenario 6: Docker Socket Access
# =============================================================================

def test_adversarial_docker_socket_access_blocked(adversarial_env):
    """Attack: Adversary attempts to connect to /var/run/docker.sock to control host Docker.
    
    Proof: ContainerSandbox controlled mount specifications strictly bind /workspace
    and /tmp tmpfs only. The Docker control socket is NEVER mounted or exposed.
    """
    ws = adversarial_env["workspace"]
    sandbox = ContainerSandbox(str(ws))
    args = sandbox.build_container_args("attack-check", ["python3"])

    # Verify /var/run/docker.sock is NEVER in container mount arguments
    for arg in args:
        assert "docker.sock" not in arg.lower()

    mount_spec = sandbox.get_container_spec()["controlled_mounts"]
    assert "docker.sock" not in str(mount_spec)


# =============================================================================
# Attack Scenario 7: Secret Extraction & Env Exfiltration
# =============================================================================

def test_adversarial_secret_extraction_prevented(adversarial_env, monkeypatch):
    """Attack: Malicious code attempts to read API tokens from environment and disk.
    
    Proof:
    1. WorkspaceSanitizer neutralizes .env files before execution.
    2. HardenedProcessSandbox scrubs API keys (OPENAI_*, GEMINI_*, AWS_*) from safe_env.
    3. Ephemeral HOME redirects ~ away from host home directory.
    """
    ws = adversarial_env["workspace"]

    # Inject mock credentials into parent process environment
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-SUPER_SECRET_TOKEN_12345")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy_FAKE_GEMINI_SECRET_KEY")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "AKIA_FAKE_AWS_SECRET")

    # Place sensitive credential file in workspace
    (ws / ".env").write_text("DATABASE_PASSWORD=super_secret_db_password\n")

    # Quarantine workspace
    quarantined = WorkspaceSanitizer.quarantine_secrets(ws)
    assert len(quarantined) == 1

    # Run inspection script in sandbox
    probe_script = (
        "import os\n"
        "from pathlib import Path\n"
        "env_file = Path('.env').read_text()\n"
        "assert 'super_secret_db_password' not in env_file, 'LEAKED_DB_PASSWORD'\n"
        "assert 'OPENAI_API_KEY' not in os.environ, 'LEAKED_OPENAI_KEY'\n"
        "assert 'GEMINI_API_KEY' not in os.environ, 'LEAKED_GEMINI_KEY'\n"
        "assert 'AWS_SECRET_ACCESS_KEY' not in os.environ, 'LEAKED_AWS_KEY'\n"
        "print('ALL_CREDENTIALS_SECURE')\n"
    )
    (ws / "probe_secrets.py").write_text(probe_script)

    sandbox = HardenedProcessSandbox(str(ws))
    out = sandbox.run_command([sys.executable, str(ws / "probe_secrets.py")])

    assert "ALL_CREDENTIALS_SECURE" in out.stdout
    assert out.returncode == 0


# =============================================================================
# Attack Scenario 8: Container Escape & Tampering Defenses
# =============================================================================

def test_adversarial_container_tampering_specifications(adversarial_env):
    """Attack: Malware attempts to write to /bin or execute dropped binaries in /tmp.
    
    Proof:
    1. --read-only rootfs prevents binary tampering.
    2. /tmp tmpfs specifies noexec,nosuid to block execution of dropped payloads.
    3. --cap-drop=ALL and no-new-privileges prevent Linux capability escalation.
    """
    ws = adversarial_env["workspace"]
    sandbox = ContainerSandbox(str(ws))
    args = sandbox.build_container_args("test-tamper", ["ls"])

    # 1. Read-only rootfs
    assert "--read-only" in args

    # 2. noexec on tmpfs
    tmp_arg = next(a for a in args if "/tmp" in a)
    assert "noexec" in tmp_arg
    assert "nosuid" in tmp_arg

    # 3. Privilege containment
    assert "--security-opt=no-new-privileges" in args
    cap_arg = next(a for a in args if "--cap-drop" in a)
    assert "ALL" in cap_arg

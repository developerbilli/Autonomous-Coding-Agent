"""Security verification tests for Sandbox Isolation Boundaries and Technical Precision."""

import os
import sys
import pytest
from pathlib import Path
from agent.execution.isolation import IsolationLevel, RepoTrustLevel, SandboxSecurityPolicy, TIER_SPECIFICATIONS
from agent.execution.container_sandbox import ContainerSandbox
from agent.execution.microvm_sandbox import (
    FirecrackerMicroVMSandbox,
    GVisorAppKernelSandbox,
    MicroVMSandbox,
)
from agent.execution.hardened_process import HardenedProcessSandbox
from agent.execution.sandbox import ExecutionSandbox, SecurityIsolationUnavailableError

MOCK_REPO = Path(__file__).resolve().parent / "mock_repo"

def test_isolation_tier_hierarchy():
    """Verify that all 4 isolation tiers are formally specified with distinct mechanisms."""
    assert IsolationLevel.MICROVM.value in TIER_SPECIFICATIONS
    assert IsolationLevel.GVISOR.value in TIER_SPECIFICATIONS
    assert IsolationLevel.CONTAINER.value in TIER_SPECIFICATIONS
    assert IsolationLevel.HARDENED_PROCESS.value in TIER_SPECIFICATIONS

    microvm = TIER_SPECIFICATIONS[IsolationLevel.MICROVM.value]
    gvisor = TIER_SPECIFICATIONS[IsolationLevel.GVISOR.value]
    container = TIER_SPECIFICATIONS[IsolationLevel.CONTAINER.value]
    fallback = TIER_SPECIFICATIONS[IsolationLevel.HARDENED_PROCESS.value]

    # Verify boundary class distinctions
    assert "Hardware" in microvm["security_boundary_class"]
    assert "Application Kernel" in gvisor["security_boundary_class"]
    assert "Namespace" in container["security_boundary_class"]
    assert "Weak" in fallback["security_boundary_class"]

    # Verify technology class descriptions
    assert microvm["is_microvm"] is True
    assert microvm["is_application_kernel"] is False
    assert gvisor["is_microvm"] is False  # gVisor is NOT a microVM!
    assert gvisor["is_application_kernel"] is True

    # Verify filesystem jail truthfulness
    assert microvm["is_filesystem_jail"] is True
    assert gvisor["is_filesystem_jail"] is True
    assert container["is_filesystem_jail"] is True
    assert fallback["is_filesystem_jail"] is False  # POSIX limits do NOT create a filesystem jail!

    # Verify network guarantee truthfulness
    assert microvm["is_guaranteed_network_blocked"] is True
    assert gvisor["is_guaranteed_network_blocked"] is True
    assert container["is_guaranteed_network_blocked"] is True
    assert fallback["is_guaranteed_network_blocked"] is False  # Advisory proxy does not block raw sockets!

def test_firecracker_and_gvisor_are_distinct_technologies():
    """Verify Firecracker and gVisor are separate classes, separate tiers, and NOT interchangeable microVMs."""
    fc_sandbox = FirecrackerMicroVMSandbox(str(MOCK_REPO))
    gv_sandbox = GVisorAppKernelSandbox(str(MOCK_REPO))

    fc_spec = fc_sandbox.get_spec()
    gv_spec = gv_sandbox.get_spec()

    # Tier label distinctions
    assert "Tier 1" in fc_spec["tier_label"]
    assert "MicroVM" in fc_spec["tier_label"]
    assert "Tier 2" in gv_spec["tier_label"]
    assert "Application Kernel" in gv_spec["tier_label"]
    assert "MicroVM" not in gv_spec["tier_label"]

    # Mechanism & architecture distinctions
    assert fc_spec["is_microvm"] is True
    assert fc_spec["is_application_kernel"] is False
    assert "KVM" in fc_spec["architecture"]
    assert "vmlinux" in fc_spec["guest_kernel"]
    assert "virtio-blk" in fc_spec["virtual_devices"]

    assert gv_spec["is_microvm"] is False  # Must explicitly confirm gVisor is NOT a microVM
    assert gv_spec["is_application_kernel"] is True
    assert "Sentry" in gv_spec["application_kernel"]
    assert "Go" in gv_spec["application_kernel"]
    assert "Gofer" in gv_spec["filesystem_mediation"]
    assert "NOT a hardware-virtualized microVM" in gv_spec["architectural_distinction"]

def test_microvm_vs_gvisor_composite_distinction():
    """Verify MicroVMSandbox composite facade reflects both distinct technology specs."""
    sandbox = MicroVMSandbox(str(MOCK_REPO))
    spec = sandbox.get_microvm_spec()

    fc_spec = sandbox.get_firecracker_spec()
    gv_spec = sandbox.get_gvisor_spec()

    # Firecracker must use hardware KVM virtualization and dedicated guest kernel
    assert "KVM" in fc_spec["architecture"] or "KVM" in fc_spec["hypervisor"]
    assert "vmlinux" in fc_spec["guest_kernel"]
    assert "virtio-blk" in fc_spec["virtual_devices"]
    assert fc_spec["hypervisor_network"] == "Disabled (air-gapped, zero virtual NICs attached)"
    assert fc_spec["guest_memory_mib"] == 512

    # gVisor must use Sentry user-space kernel syscall interception, NOT hardware MMU virtualization
    assert "Sentry" in gv_spec["application_kernel"]
    assert "Go" in gv_spec["application_kernel"]
    assert "Gofer" in gv_spec["filesystem_mediation"]
    assert "NOT a hardware-virtualized" in gv_spec["architectural_distinction"]

def test_tier_4_automatic_fallback_blocked_by_default(monkeypatch):
    """Verify FAIL-CLOSED SECURITY: ExecutionSandbox refuses automatic host execution in Tier 4."""
    # Ensure environment override is not active
    monkeypatch.delenv("ALLOW_UNSAFE_HOST_FALLBACK", raising=False)

    # Initialize ExecutionSandbox with default policy (allow_process_fallback=False)
    sandbox = ExecutionSandbox(str(MOCK_REPO), allow_process_fallback=False)

    # If neither Firecracker, gVisor, nor Docker are present, fallback must be blocked
    if not (sandbox.microvm_engine.is_available() or sandbox.gvisor_engine.is_available() or sandbox.container_engine.is_available()):
        assert sandbox.fallback_blocked is True
        assert sandbox.active_engine is None

        # Directly running a command MUST raise SecurityIsolationUnavailableError
        with pytest.raises(SecurityIsolationUnavailableError) as exc_info:
            sandbox.run_command(["echo", "untrusted"])
        assert "SECURITY REFUSAL" in str(exc_info.value)

        # Running pytest MUST return exit code 126 and failed security test
        res = sandbox.run_pytest()
        assert res.passed is False
        assert res.exit_code == 126
        assert "SECURITY_ISOLATION_UNAVAILABLE" in res.failed_tests
        assert "SECURITY REFUSAL" in res.error_summary

def test_tier_4_fallback_allowed_when_explicitly_authorized():
    """Verify that Tier 4 host-process execution only succeeds with explicit authorization."""
    sandbox = ExecutionSandbox(str(MOCK_REPO), allow_process_fallback=True)

    status = sandbox.get_security_status()
    assert status["allow_process_fallback"] is True
    assert status["fallback_blocked"] is False

    # Security metadata must be truthful about lack of filesystem jail and socket blocking
    assert status["is_filesystem_jail"] is False
    assert status["is_guaranteed_network_blocked"] is False

def test_container_sandbox_argument_construction():
    """Verify ContainerSandbox builds strict OCI flags (non-root, network none, cgroups, read-only rootfs)."""
    policy = SandboxSecurityPolicy(
        isolation_level=IsolationLevel.CONTAINER,
        non_root_user="1001:1001",
        network_mode="none",
        memory_limit_mb=512,
        cpu_limit=1.0,
        pids_limit=100,
        read_only_rootfs=True,
    )
    sandbox = ContainerSandbox(str(MOCK_REPO), policy=policy, image_name="test-sandbox:latest")
    args = sandbox.build_container_args("test-container", ["pytest", "-v"])
    args_str = " ".join(args)

    assert "--user=1001:1001" in args_str
    assert "--network=none" in args_str
    assert "--memory=512m" in args_str
    assert "--cpus=1.0" in args_str
    assert "--pids-limit=100" in args_str
    assert "--cap-drop=ALL" in args_str
    assert "--security-opt=no-new-privileges" in args_str
    assert "--read-only" in args_str
    assert "--tmpfs=/tmp:rw,noexec,nosuid,size=64m" in args_str
    assert "--tmpfs=/run:rw,noexec,nosuid,size=16m" in args_str
    assert "/workspace" in args_str
    assert "pytest -v" in args_str

def test_container_controlled_mount_specifications():
    """Verify ContainerSandbox formal spec documents read-only rootfs and controlled writable mounts."""
    sandbox = ContainerSandbox(str(MOCK_REPO))
    spec = sandbox.get_container_spec()

    assert "Read-only container root filesystem" in spec["rootfs_protection"]
    assert "noexec" in spec["controlled_mounts"]["tmpfs_tmp"]
    assert "nosuid" in spec["controlled_mounts"]["tmpfs_tmp"]
    assert "workspace" in spec["controlled_mounts"]["workspace_mount"]

def test_hardened_process_environment_sanitization_and_weak_boundary():
    """Verify HardenedProcessSandbox documents weak boundary and POSIX filesystem/network limitations."""
    sandbox = HardenedProcessSandbox(str(MOCK_REPO))

    # Run Python code inside sandbox to inspect environment sanitization
    code = "import os; print('KEY_IN_ENV:', 'GEMINI_API_KEY' in os.environ, 'HOME_IS_SAFE:', 'sandbox_home' in os.environ.get('HOME', ''))"
    out = sandbox.run_command([sys.executable, "-c", code])

    assert out.returncode == 0
    assert "KEY_IN_ENV: False" in out.stdout
    assert "HOME_IS_SAFE: True" in out.stdout

    # Security metadata must be technically truthful about limitations
    assert out.security_metadata["is_filesystem_jail"] is False
    assert out.security_metadata["is_guaranteed_network_blocked"] is False
    assert out.security_metadata["network_blocked"] is False  # Advisory proxy does not guarantee network block!
    assert out.security_metadata["network_advisory_proxy"] is True
    assert "weak" in out.security_metadata["security_boundary_class"].lower()

def test_output_buffer_limit_truncation():
    """Verify that infinite print loops are truncated at max_output_bytes without exhausting host memory."""
    policy = SandboxSecurityPolicy(
        timeout_seconds=5,
        max_output_bytes=4 * 1024,  # 4 KB cap for test
    )
    sandbox = HardenedProcessSandbox(str(MOCK_REPO), policy=policy)

    code = "import sys; sys.stdout.write('X' * 100000)"
    out = sandbox.run_command([sys.executable, "-c", code])

    assert out.output_truncated is True
    assert "OUTPUT TRUNCATED: Exceeded buffer limit" in out.stdout
    assert len(out.stdout) < 10000

def test_timeout_and_process_group_cleanup():
    """Verify that long-running or hanging code is killed cleanly via process-group SIGKILL."""
    policy = SandboxSecurityPolicy(timeout_seconds=2)
    sandbox = HardenedProcessSandbox(str(MOCK_REPO), policy=policy)

    code = "import time; time.sleep(10)"
    out = sandbox.run_command([sys.executable, "-c", code])

    assert out.timed_out is True
    assert out.returncode == 124

def test_unified_execution_sandbox_security_status():
    """Verify ExecutionSandbox reports active isolation level, boundary tier, and jail status."""
    sandbox = ExecutionSandbox(str(MOCK_REPO), allow_process_fallback=True)
    status = sandbox.get_security_status()

    assert "isolation_level" in status
    assert "tier_name" in status
    assert "security_boundary_class" in status
    assert "is_filesystem_jail" in status
    assert "is_guaranteed_network_blocked" in status
    assert status["non_root_user"] == "1001:1001"
    assert status["network_control"] == "none"
    assert "512MB" in status["memory_limit"]
    assert status["pids_limit"] == 100

def test_unified_sandbox_pytest_execution_with_telemetry():
    """Verify ExecutionSandbox executes tests and returns security metadata in TestResult."""
    sandbox = ExecutionSandbox(str(MOCK_REPO), allow_process_fallback=True)
    res = sandbox.run_pytest()

    assert res.passed is True
    assert res.exit_code == 0
    assert res.isolation_level is not None
    assert "memory_limit" in res.security_metadata
    assert "is_filesystem_jail" in res.security_metadata


def test_fail_closed_strict_enforcement_with_env_disabled(monkeypatch):
    """Verify FAIL-CLOSED: Setting ALLOW_UNSAFE_HOST_FALLBACK=0 strictly blocks untrusted execution."""
    monkeypatch.setenv("ALLOW_UNSAFE_HOST_FALLBACK", "0")

    sandbox = ExecutionSandbox(str(MOCK_REPO))
    # If containers/microVMs are not installed on host, fallback must be blocked
    if not (sandbox.microvm_engine.is_available() or sandbox.gvisor_engine.is_available() or sandbox.container_engine.is_available()):
        assert sandbox.fallback_blocked is True
        with pytest.raises(SecurityIsolationUnavailableError):
            sandbox.run_command(["whoami"])

        result = sandbox.run_pytest()
        assert result.passed is False
        assert result.exit_code == 126
        assert "SECURITY_ISOLATION_UNAVAILABLE" in result.failed_tests


def test_sandbox_posix_memory_quota_configuration():
    """Verify SandboxSecurityPolicy enforces memory limits and resource governance."""
    policy = SandboxSecurityPolicy(memory_limit_mb=256, cpu_limit=0.5, pids_limit=50)
    assert policy.memory_limit_mb == 256
    assert policy.cpu_limit == 0.5
    assert policy.pids_limit == 50

    sandbox = HardenedProcessSandbox(str(MOCK_REPO), policy=policy)
    preexec = sandbox._create_preexec_fn()
    assert callable(preexec)


def test_untrusted_repository_blocks_tier4_fallback_even_with_env_override(monkeypatch):
    """Verify that an UNTRUSTED repository strictly blocks Tier 4 fallback even if ALLOW_UNSAFE_HOST_FALLBACK=1."""
    monkeypatch.setenv("ALLOW_UNSAFE_HOST_FALLBACK", "1")

    # When marked untrusted, Tier 4 host process execution must be refused
    sandbox = ExecutionSandbox(str(MOCK_REPO), trust_level="untrusted")
    if not (sandbox.microvm_engine.is_available() or sandbox.gvisor_engine.is_available() or sandbox.container_engine.is_available()):
        assert sandbox.fallback_blocked is True
        assert sandbox.policy.allow_process_fallback is False
        assert sandbox.trust_level == RepoTrustLevel.UNTRUSTED

        with pytest.raises(SecurityIsolationUnavailableError):
            sandbox.run_command(["whoami"])

        result = sandbox.run_pytest()
        assert result.passed is False
        assert result.exit_code == 126
        assert "SECURITY_ISOLATION_UNAVAILABLE" in result.failed_tests


def test_trusted_repository_allows_tier4_fallback_when_env_enabled(monkeypatch):
    """Verify that a TRUSTED repository permits Tier 4 host fallback when operator authorizes it."""
    monkeypatch.setenv("ALLOW_UNSAFE_HOST_FALLBACK", "1")

    sandbox = ExecutionSandbox(str(MOCK_REPO), trust_level="trusted")
    if not (sandbox.microvm_engine.is_available() or sandbox.gvisor_engine.is_available() or sandbox.container_engine.is_available()):
        assert sandbox.fallback_blocked is False
        assert sandbox.policy.allow_process_fallback is True
        assert sandbox.trust_level == RepoTrustLevel.TRUSTED
        assert sandbox.isolation_level == IsolationLevel.HARDENED_PROCESS


def test_repository_spec_trust_level_auto_classification():
    """Verify that WorkspaceSpec automatically derives trust_level from source_type."""
    from agent.repository.manager import WorkspaceSpec, WorkspaceSourceType

    # Remote GitHub URL -> UNTRUSTED
    gh_spec = WorkspaceSpec(
        source_type=WorkspaceSourceType.GITHUB,
        github_url="https://github.com/example/repo.git",
    )
    assert gh_spec.trust_level == "untrusted"

    # Uploaded ZIP -> UNTRUSTED
    zip_spec = WorkspaceSpec(
        source_type=WorkspaceSourceType.ZIP,
        zip_bytes=b"PK...",
    )
    assert zip_spec.trust_level == "untrusted"

    # Local Path -> TRUSTED by default
    local_spec = WorkspaceSpec(
        source_type=WorkspaceSourceType.LOCAL,
        local_path="/path/to/local/repo",
    )
    assert local_spec.trust_level == "trusted"

    # Explicit override respected
    untrusted_local = WorkspaceSpec(
        source_type=WorkspaceSourceType.LOCAL,
        local_path="/path/to/downloaded/repo",
        trust_level="untrusted",
    )
    assert untrusted_local.trust_level == "untrusted"


def test_production_environment_strictly_blocks_fallback_even_with_env_override(monkeypatch):
    """Verify that in PRODUCTION, Tier 4 host-process fallback is strictly FORBIDDEN under all circumstances."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_UNSAFE_HOST_FALLBACK", "1")

    # Even with trust_level="trusted" and ALLOW_UNSAFE_HOST_FALLBACK=1, production locks out Tier 4
    sandbox = ExecutionSandbox(str(MOCK_REPO), trust_level="trusted")
    assert sandbox.is_production is True
    if not (sandbox.microvm_engine.is_available() or sandbox.gvisor_engine.is_available() or sandbox.container_engine.is_available()):
        assert sandbox.fallback_blocked is True
        assert sandbox.policy.allow_process_fallback is False

        with pytest.raises(SecurityIsolationUnavailableError):
            sandbox.run_command(["whoami"])

        status = sandbox.get_security_status()
        assert status["is_production"] is True
        assert status["fallback_blocked"] is True




"""Unit tests for Workspace Secret Sanitization & Quarantine Engine."""

import os
import shutil
import tempfile
import pytest
from pathlib import Path
from agent.repository.sanitizer import (
    WorkspaceSanitizer,
    SANITIZED_PLACEHOLDER_CONTENT,
)
from agent.repository.manager import (
    RepositoryManager,
    WorkspaceSpec,
    WorkspaceSourceType,
)


@pytest.fixture
def temp_workspace():
    """Creates a temporary workspace with mock secret files and safe templates."""
    d = Path(tempfile.mkdtemp(prefix="test_workspace_"))
    
    # Create sensitive files
    (d / ".env").write_text("GEMINI_API_KEY=AIzaSyFakeSecretKey12345\nDB_PASS=supersecret\n")
    (d / ".env.local").write_text("LOCAL_SECRET=my_local_token\n")
    (d / "gcp_credentials.json").write_text('{"type": "service_account", "private_key": "-----BEGIN PRIVATE KEY-----"}')
    (d / "id_rsa").write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAz...")
    
    # Create subfolder with secret
    subdir = d / "config"
    subdir.mkdir()
    (subdir / "secrets.yaml").write_text("api_token: secret_abc123\n")

    # Create safe template files (must NOT be quarantined)
    (d / ".env.example").write_text("GEMINI_API_KEY=your_key_here\nDB_PASS=your_password\n")
    (d / "config.example").write_text("api_token: example_token\n")

    # Create standard code file
    (d / "main.py").write_text("print('hello world')\n")

    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_is_secret_file_detection():
    """Verify is_secret_file accurately distinguishes sensitive credentials from safe templates."""
    # Sensitive credential files
    assert WorkspaceSanitizer.is_secret_file(Path(".env")) is True
    assert WorkspaceSanitizer.is_secret_file(Path(".env.local")) is True
    assert WorkspaceSanitizer.is_secret_file(Path(".env.production")) is True
    assert WorkspaceSanitizer.is_secret_file(Path("client_secrets.json")) is True
    assert WorkspaceSanitizer.is_secret_file(Path("credentials.ini")) is True
    assert WorkspaceSanitizer.is_secret_file(Path("id_rsa")) is True
    assert WorkspaceSanitizer.is_secret_file(Path("id_ed25519")) is True
    assert WorkspaceSanitizer.is_secret_file(Path("server.key")) is True
    assert WorkspaceSanitizer.is_secret_file(Path("cert.pem")) is True
    assert WorkspaceSanitizer.is_secret_file(Path(".git-credentials")) is True

    # Safe templates & ordinary files (MUST NOT BE DETECTED AS SECRETS)
    assert WorkspaceSanitizer.is_secret_file(Path(".env.example")) is False
    assert WorkspaceSanitizer.is_secret_file(Path(".env.sample")) is False
    assert WorkspaceSanitizer.is_secret_file(Path(".env.template")) is False
    assert WorkspaceSanitizer.is_secret_file(Path("settings.sample")) is False
    assert WorkspaceSanitizer.is_secret_file(Path("main.py")) is False
    assert WorkspaceSanitizer.is_secret_file(Path("README.md")) is False


def test_scan_for_secrets(temp_workspace):
    """Verify scan_for_secrets returns all sensitive files while ignoring safe templates."""
    found = WorkspaceSanitizer.scan_for_secrets(temp_workspace)
    found_names = [f.name for f in found]

    assert ".env" in found_names
    assert ".env.local" in found_names
    assert "gcp_credentials.json" in found_names
    assert "id_rsa" in found_names
    assert "secrets.yaml" in found_names

    # Safe files must not be in list
    assert ".env.example" not in found_names
    assert "config.example" not in found_names
    assert "main.py" not in found_names


def test_quarantine_and_neutralization(temp_workspace):
    """Verify quarantine_secrets replaces secret files with safety stubs and preserves originals."""
    orig_env = (temp_workspace / ".env").read_text()
    records = WorkspaceSanitizer.quarantine_secrets(temp_workspace)

    assert len(records) == 5

    # Check that in-workspace files are replaced by safety stub
    neutralized_env = (temp_workspace / ".env").read_text()
    assert neutralized_env == SANITIZED_PLACEHOLDER_CONTENT
    assert "AIzaSyFakeSecretKey12345" not in neutralized_env

    # Check that safe templates are completely untouched
    assert (temp_workspace / ".env.example").read_text() == "GEMINI_API_KEY=your_key_here\nDB_PASS=your_password\n"

    # Check that quarantined storage holds the original content
    env_record = next(r for r in records if r.rel_path == ".env")
    quarantine_path = Path(env_record.quarantine_path)
    assert quarantine_path.exists()
    assert quarantine_path.read_text() == orig_env


def test_restoration_of_quarantined_secrets(temp_workspace):
    """Verify restore_secrets safely restores original files and file permissions."""
    orig_env = (temp_workspace / ".env").read_text()
    records = WorkspaceSanitizer.quarantine_secrets(temp_workspace)

    # In-place file is sanitized
    assert (temp_workspace / ".env").read_text() == SANITIZED_PLACEHOLDER_CONTENT

    # Restore
    restored = WorkspaceSanitizer.restore_secrets(temp_workspace, records)
    assert restored == 5

    # Verified restored content matches original
    assert (temp_workspace / ".env").read_text() == orig_env


def test_repository_manager_automatic_quarantine(temp_workspace):
    """Verify RepositoryManager automatically quarantines secrets when preparing an isolated workspace."""
    base_ws = Path(tempfile.mkdtemp(prefix="mgr_ws_"))
    try:
        mgr = RepositoryManager(str(base_ws))
        spec = WorkspaceSpec(
            source_type=WorkspaceSourceType.LOCAL,
            local_path=str(temp_workspace),
            isolate_local_copy=True,
            sanitize_secrets=True,
        )
        task_id = "test_task_quarantine_001"
        ws_path = mgr.prepare_workspace(task_id, spec)

        # In the isolated workspace, .env must be quarantined
        isolated_env = (ws_path / ".env").read_text()
        assert isolated_env == SANITIZED_PLACEHOLDER_CONTENT

        # Original source directory must remain completely untouched
        assert (temp_workspace / ".env").read_text() != SANITIZED_PLACEHOLDER_CONTENT

        # Restoration works from manager
        restored = mgr.restore_workspace_secrets(task_id, ws_path)
        assert restored >= 1
        assert "AIzaSyFakeSecretKey12345" in (ws_path / ".env").read_text()
    finally:
        shutil.rmtree(base_ws, ignore_errors=True)


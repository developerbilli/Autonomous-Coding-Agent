"""Unit tests for RepositoryManager and Workspace Ingestion Layer."""

import base64
import io
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

try:
    import pytest
except ImportError:
    class PytestMock:
        class raises:
            def __init__(self, expected_exc, match=None):
                self.expected_exc = expected_exc
                self.match = match
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                if exc_type is None:
                    raise AssertionError(f"Expected exception {self.expected_exc} was not raised")
                if not issubclass(exc_type, self.expected_exc):
                    return False
                if self.match and self.match not in str(exc_val):
                    raise AssertionError(f"Exception message '{exc_val}' does not match '{self.match}'")
                return True
        @staticmethod
        def fixture(func):
            return func
    pytest = PytestMock()

from agent.repository.manager import (
    RepositoryManager,
    WorkspaceSpec,
    WorkspaceSourceType,
)



@pytest.fixture
def temp_workspace_base():
    temp_dir = tempfile.mkdtemp(prefix="test_workspaces_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def repo_manager(temp_workspace_base):
    return RepositoryManager(base_workspace_dir=str(temp_workspace_base))


def test_spec_validation():
    # Test valid specs
    spec_local = WorkspaceSpec(source_type=WorkspaceSourceType.LOCAL, local_path="calculator_repo")
    assert spec_local.source_type == WorkspaceSourceType.LOCAL

    spec_gh = WorkspaceSpec(source_type=WorkspaceSourceType.GITHUB, github_url="https://github.com/foo/bar")
    assert spec_gh.github_url == "https://github.com/foo/bar"

    # Test invalid specs
    with pytest.raises(ValueError, match="github_url must be specified"):
        WorkspaceSpec(source_type=WorkspaceSourceType.GITHUB)

    with pytest.raises(ValueError, match="local_path must be specified"):
        WorkspaceSpec(source_type=WorkspaceSourceType.LOCAL)

    with pytest.raises(ValueError, match="zip_bytes or zip_base64"):
        WorkspaceSpec(source_type=WorkspaceSourceType.ZIP)


def test_local_direct_workspace(repo_manager, tmp_path):
    # Create mock repo
    mock_repo = tmp_path / "mock_project"
    mock_repo.mkdir()
    (mock_repo / "main.py").write_text("print('hello')")

    spec = WorkspaceSpec(
        source_type=WorkspaceSourceType.LOCAL,
        local_path=str(mock_repo),
        isolate_local_copy=False,
    )
    res_path = repo_manager.prepare_workspace("task_001", spec)
    assert res_path == mock_repo.resolve()


def test_local_isolated_copy_workspace(repo_manager, tmp_path):
    mock_repo = tmp_path / "mock_project_source"
    mock_repo.mkdir()
    (mock_repo / "app.py").write_text("def run(): pass")

    spec = WorkspaceSpec(
        source_type=WorkspaceSourceType.LOCAL,
        local_path=str(mock_repo),
        isolate_local_copy=True,
        project_name="isolated_app",
    )
    res_path = repo_manager.prepare_workspace("task_002", spec)
    assert res_path.exists()
    assert res_path != mock_repo
    assert (res_path / "app.py").read_text() == "def run(): pass"
    assert (res_path / ".git").exists()


def test_zip_extraction_clean(repo_manager):
    # Construct an in-memory zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("my_app/calc.py", "def add(a, b): return a + b")
        zf.writestr("my_app/test_calc.py", "def test_add(): assert True")

    spec = WorkspaceSpec(
        source_type=WorkspaceSourceType.ZIP,
        zip_bytes=zip_buffer.getvalue(),
        project_name="calc_extracted",
    )
    res_path = repo_manager.prepare_workspace("task_003", spec)
    assert res_path.exists()
    assert (res_path / "calc.py").exists() or (res_path / "my_app" / "calc.py").exists()


def test_zipslip_security_prevention(repo_manager):
    # Construct a malicious zip with path traversal member
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("../../malicious.txt", "exploit")

    spec = WorkspaceSpec(
        source_type=WorkspaceSourceType.ZIP,
        zip_bytes=zip_buffer.getvalue(),
        project_name="bad_zip",
    )
    with pytest.raises(PermissionError, match="ZipSlip path traversal attempt detected"):
        repo_manager.prepare_workspace("task_004", spec)


def test_greenfield_scaffolding(repo_manager):
    spec = WorkspaceSpec(
        source_type=WorkspaceSourceType.GREENFIELD,
        project_name="enterprise_billing",
    )
    res_path = repo_manager.prepare_workspace("task_005", spec)

    assert res_path.exists()
    assert (res_path / "src" / "enterprise_billing" / "core.py").exists()
    assert (res_path / "tests" / "test_initial.py").exists()
    assert (res_path / "pyproject.toml").exists()
    assert (res_path / "README.md").exists()
    assert (res_path / ".git").exists()

    # Verify git initial commit was created
    diff = repo_manager.get_git_diff(res_path)
    assert diff == ""  # Working tree is clean because initial commit was made


def test_git_branch_and_commit(repo_manager):
    spec = WorkspaceSpec(
        source_type=WorkspaceSourceType.GREENFIELD,
        project_name="git_ops_test",
    )
    res_path = repo_manager.prepare_workspace("task_006", spec)

    # Create new branch
    success = repo_manager.create_git_branch(res_path, "feature/billing-api")
    assert success is True

    # Make code modification
    new_file = res_path / "src" / "git_ops_test" / "api.py"
    new_file.write_text("class BillingAPI: pass")

    # Check git diff shows the new untracked or modified file
    sha = repo_manager.commit_changes(res_path, "feat: Add BillingAPI class")
    assert sha is not None
    assert len(sha) == 40

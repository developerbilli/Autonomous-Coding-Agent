"""Repository & Workspace Ingestion Layer.

Prepares isolated task workspaces from multiple sources:
1. GitHub Repository URL (shallow clone, branch checkout, token auth)
2. Local Repository Path (validation and optional isolated copy-on-write)
3. Uploaded ZIP Archive (safe extraction with Anti-ZipSlip traversal defense)
4. Greenfield Project (directory scaffolding for building from scratch)

Also provides post-verification Git operations (branching, commits, unified diffs).
"""

import base64
import io
import json
import logging
import os
import re
import shutil
import subprocess
import time
import zipfile
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger("agent.repository")


class WorkspaceSourceType(str, Enum):
    """Supported repository ingestion sources."""
    GITHUB = "github"
    LOCAL = "local"
    ZIP = "zip"
    GREENFIELD = "greenfield"


class WorkspaceSpec(BaseModel):
    """Specification for preparing a workspace."""
    source_type: WorkspaceSourceType = Field(default=WorkspaceSourceType.LOCAL)
    github_url: Optional[str] = Field(default=None, description="HTTPS or SSH GitHub repository URL")
    branch: Optional[str] = Field(default="main", description="Target Git branch")
    auth_token: Optional[str] = Field(default=None, description="GitHub Personal Access Token for private repos")
    local_path: Optional[str] = Field(default=None, description="Filesystem path to local repository")
    zip_bytes: Optional[bytes] = Field(default=None, description="Raw binary bytes of uploaded ZIP archive")
    zip_base64: Optional[str] = Field(default=None, description="Base64-encoded string of uploaded ZIP archive")
    project_name: Optional[str] = Field(default=None, description="Target project/repository folder name")
    isolate_local_copy: bool = Field(default=False, description="Whether to copy local repository into an isolated task workspace")

    @model_validator(mode="after")
    def validate_spec(self):
        if self.source_type == WorkspaceSourceType.GITHUB and not self.github_url:
            raise ValueError("github_url must be specified when source_type is 'github'")
        if self.source_type == WorkspaceSourceType.LOCAL and not self.local_path:
            raise ValueError("local_path must be specified when source_type is 'local'")
        if self.source_type == WorkspaceSourceType.ZIP and not (self.zip_bytes or self.zip_base64):
            raise ValueError("zip_bytes or zip_base64 must be provided when source_type is 'zip'")
        return self


class WorkspaceMetadata(BaseModel):
    """Metadata for an active workspace."""
    task_id: str
    source_type: WorkspaceSourceType
    workspace_path: str
    created_at: float
    branch: Optional[str] = None
    remote_url: Optional[str] = None
    is_git_repo: bool = False


class RepositoryManager:
    """Manages workspace lifecycle, repository ingestion, and Git delivery."""

    def __init__(self, base_workspace_dir: str = "workspaces"):
        self.base_dir = Path(base_workspace_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def prepare_workspace(self, task_id: str, spec: WorkspaceSpec) -> Path:
        """Prepares an isolated filesystem workspace based on the given specification."""
        task_dir = self.base_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Preparing workspace for task '{task_id}' with source_type='{spec.source_type}'")

        if spec.source_type == WorkspaceSourceType.GITHUB:
            return self._clone_github(task_dir, spec)
        elif spec.source_type == WorkspaceSourceType.LOCAL:
            return self._prepare_local(task_dir, spec)
        elif spec.source_type == WorkspaceSourceType.ZIP:
            return self._extract_zip(task_dir, spec)
        elif spec.source_type == WorkspaceSourceType.GREENFIELD:
            return self._scaffold_greenfield(task_dir, spec)
        else:
            raise ValueError(f"Unsupported workspace source_type: {spec.source_type}")

    def _clone_github(self, task_dir: Path, spec: WorkspaceSpec) -> Path:
        """Clones a GitHub repository into an isolated workspace directory."""
        raw_url = spec.github_url.strip()

        # Normalize GitHub blob / tree URLs (e.g. https://github.com/owner/repo/blob/branch/path/file.py)
        branch = spec.branch or "main"
        gh_match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)(?:/(?:blob|tree)/([^/]+)(?:/(.*))?)?", raw_url)
        if gh_match:
            owner, repo, url_branch, _ = gh_match.groups()
            repo_clean = repo.replace(".git", "")
            raw_url = f"https://github.com/{owner}/{repo_clean}"
            if url_branch and (not spec.branch or spec.branch == "main"):
                branch = url_branch

        # Derive clean folder name from repo URL
        repo_name = spec.project_name or raw_url.rstrip("/").split("/")[-1].replace(".git", "")
        repo_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", repo_name)
        target_dir = task_dir / repo_name

        # If already cloned and resumption is active, reuse
        if target_dir.exists() and (target_dir / ".git").exists():
            logger.info(f"Target repository already exists at {target_dir}. Reusing workspace.")
            return target_dir

        target_dir.mkdir(parents=True, exist_ok=True)

        # Build git clone command with security hygiene (token not logged or exposed)
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd.extend(["--branch", branch])

        # Prepare environment and clone URL
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"

        clone_url = raw_url
        if spec.auth_token:
            # Inject token securely for https cloning without logging
            if raw_url.startswith("https://"):
                token = spec.auth_token.strip()
                clone_url = raw_url.replace("https://", f"https://x-access-token:{token}@")

        cmd.extend(["--", clone_url, str(target_dir)])

        try:
            logger.info(f"Executing shallow git clone from {raw_url} (branch: {branch}) into {target_dir}")
            res = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if res.returncode != 0:
                # If branch failed, try default branch
                err_lower = res.stderr.lower()
                if "remote branch" in err_lower and branch != "master":
                    logger.warning(f"Branch '{branch}' not found. Retrying with default branch...")
                    retry_cmd = ["git", "clone", "--depth", "1", "--", clone_url, str(target_dir)]
                    res = subprocess.run(retry_cmd, env=env, capture_output=True, text=True, timeout=300)

                if res.returncode != 0:
                    # Scrub token from error message if present
                    safe_err = res.stderr
                    if spec.auth_token:
                        safe_err = safe_err.replace(spec.auth_token, "********")
                    raise RuntimeError(f"Git clone failed: {safe_err.strip()}")

            # Remove remote credentials from local git config to prevent token leakage
            if spec.auth_token:
                subprocess.run(
                    ["git", "remote", "set-url", "origin", raw_url],
                    cwd=str(target_dir),
                    capture_output=True,
                )

            logger.info(f"Successfully cloned repository into {target_dir}")
            return target_dir
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Git clone operation timed out after 300 seconds for {raw_url}")

    def _prepare_local(self, task_dir: Path, spec: WorkspaceSpec) -> Path:
        """Resolves local repository or creates an isolated copy-on-write workspace."""
        local_src = Path(spec.local_path).resolve()
        if not local_src.exists():
            raise FileNotFoundError(f"Local repository path does not exist: {local_src}")
        if not local_src.is_dir():
            raise NotADirectoryError(f"Local repository path is not a directory: {local_src}")

        if not spec.isolate_local_copy:
            logger.info(f"Using direct local repository at {local_src}")
            return local_src

        # Copy-on-write isolation
        repo_name = spec.project_name or local_src.name
        target_dir = task_dir / repo_name
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)

        logger.info(f"Creating isolated copy-on-write clone from {local_src} to {target_dir}")
        shutil.copytree(
            local_src,
            target_dir,
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "venv", ".venv", "node_modules"),
        )
        # Initialize a fresh git repo in the isolated copy for diff tracking
        self._init_git_repo(target_dir)
        return target_dir

    def _extract_zip(self, task_dir: Path, spec: WorkspaceSpec) -> Path:
        """Extracts an uploaded ZIP archive with Anti-ZipSlip path traversal verification."""
        zip_bytes = spec.zip_bytes
        if not zip_bytes and spec.zip_base64:
            zip_bytes = base64.b64decode(spec.zip_base64)

        if not zip_bytes:
            raise ValueError("No ZIP file bytes available for extraction.")

        repo_name = spec.project_name or "extracted_project"
        target_dir = task_dir / repo_name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_dir_resolved = str(target_dir.resolve())

        logger.info(f"Safely extracting uploaded ZIP archive to {target_dir}")

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for member in zf.infolist():
                # Anti-ZipSlip vulnerability check: ensure destination path is strictly within target_dir
                extracted_path = (target_dir / member.filename).resolve()
                if not str(extracted_path).startswith(target_dir_resolved):
                    raise PermissionError(
                        f"ZipSlip path traversal attempt detected in ZIP archive: '{member.filename}'"
                    )

            zf.extractall(target_dir)

        # Check if the zip extracted into a single top-level folder
        entries = [e for e in target_dir.iterdir() if not e.name.startswith(".")]
        if len(entries) == 1 and entries[0].is_dir():
            target_dir = entries[0]

        # Initialize Git repo if missing for change tracking
        if not (target_dir / ".git").exists():
            self._init_git_repo(target_dir)

        return target_dir

    def _scaffold_greenfield(self, task_dir: Path, spec: WorkspaceSpec) -> Path:
        """Scaffolds a clean Python project skeleton for building from scratch."""
        project_name = spec.project_name or "new_project"
        target_dir = task_dir / project_name
        target_dir.mkdir(parents=True, exist_ok=True)

        pkg_name = re.sub(r"[^a-zA-Z0-9_]", "_", project_name.lower())
        src_dir = target_dir / "src" / pkg_name
        tests_dir = target_dir / "tests"

        src_dir.mkdir(parents=True, exist_ok=True)
        tests_dir.mkdir(parents=True, exist_ok=True)

        # 1. Package init
        (src_dir / "__init__.py").write_text(f'"""Package {project_name}."""\n__version__ = "0.1.0"\n', encoding="utf-8")
        
        # 2. Main placeholder module
        (src_dir / "core.py").write_text(
            f'"""Core module for {project_name}."""\n\n'
            f'def get_project_name() -> str:\n'
            f'    return "{project_name}"\n',
            encoding="utf-8",
        )

        # 3. Initial baseline test
        (tests_dir / "__init__.py").touch()
        (tests_dir / "test_initial.py").write_text(
            f'from src.{pkg_name}.core import get_project_name\n\n'
            f'def test_project_name():\n'
            f'    assert get_project_name() == "{project_name}"\n',
            encoding="utf-8",
        )

        # 4. pyproject.toml
        (target_dir / "pyproject.toml").write_text(
            f'[project]\nname = "{project_name}"\nversion = "0.1.0"\ndescription = "Autonomous Greenfield Project"\n'
            f'dependencies = []\n\n'
            f'[tool.pytest.ini_options]\npythonpath = ["."]\n',
            encoding="utf-8",
        )

        # 5. README.md
        (target_dir / "README.md").write_text(
            f'# {project_name}\n\nBuilt autonomously from scratch by Autonomous Multi-Agent AI Coding System.\n',
            encoding="utf-8",
        )

        # Initialize local git repository and initial commit
        self._init_git_repo(target_dir, initial_commit=True)
        logger.info(f"Scaffolded greenfield project '{project_name}' at {target_dir}")
        return target_dir

    def _init_git_repo(self, repo_path: Path, initial_commit: bool = True):
        """Initializes a local Git repository for version control and diffing."""
        try:
            if not (repo_path / ".git").exists():
                subprocess.run(["git", "init"], cwd=str(repo_path), capture_output=True, check=True)
                subprocess.run(["git", "config", "user.name", "Autonomous Coding Agent"], cwd=str(repo_path), capture_output=True)
                subprocess.run(["git", "config", "user.email", "agent@autonomous.local"], cwd=str(repo_path), capture_output=True)
                if initial_commit:
                    subprocess.run(["git", "add", "-A"], cwd=str(repo_path), capture_output=True)
                    subprocess.run(["git", "commit", "-m", "Initial commit: Greenfield Project Scaffold"], cwd=str(repo_path), capture_output=True)
        except Exception as e:
            logger.warning(f"Could not initialize git repository in {repo_path}: {e}")

    # =========================================================================
    # Git Delivery Operations (Branching, Commit, Unified Diff)
    # =========================================================================

    def create_git_branch(self, workspace_path: Path, branch_name: str) -> bool:
        """Creates and checks out a new Git branch for task changes."""
        try:
            res = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
            )
            return res.returncode == 0
        except Exception as e:
            logger.warning(f"Failed to create Git branch '{branch_name}': {e}")
            return False

    def commit_changes(self, workspace_path: Path, message: str) -> Optional[str]:
        """Stages all changes and commits them, returning the commit SHA."""
        try:
            subprocess.run(["git", "add", "-A"], cwd=str(workspace_path), capture_output=True, check=True)
            res = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
            )
            if res.returncode == 0:
                sha_res = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(workspace_path),
                    capture_output=True,
                    text=True,
                    check=True,
                )
                return sha_res.stdout.strip()
            return None
        except Exception as e:
            logger.warning(f"Failed to commit Git changes: {e}")
            return None

    def get_git_diff(self, workspace_path: Path, staged: bool = False) -> str:
        """Returns the unified Git diff for the workspace."""
        try:
            cmd = ["git", "diff"]
            if staged:
                cmd.append("--cached")
            res = subprocess.run(cmd, cwd=str(workspace_path), capture_output=True, text=True)
            return res.stdout
        except Exception:
            return ""

    def cleanup_workspace(self, task_id: str):
        """Removes the task workspace directory if cleanup is requested."""
        task_dir = self.base_dir / task_id
        if task_dir.exists():
            shutil.rmtree(task_dir, ignore_errors=True)


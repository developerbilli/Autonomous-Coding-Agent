"""Explicit Permission Policies and Risk Classification for Tool Execution.

Enforces fine-grained security policies on reading files, editing files,
executing commands, network access, and external service interactions.
"""

import fnmatch
import os
import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field


class ToolActionType(str, Enum):
    """Types of actions an autonomous agent can perform."""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    COMMAND_EXECUTE = "command_execute"
    NETWORK_ACCESS = "network_access"
    EXTERNAL_SERVICE = "external_service"


class RiskLevel(str, Enum):
    """Risk severity classification for agent operations."""
    LOW = "low"            # Read-only or standard local code updates
    MEDIUM = "medium"      # Standard non-production file creation/edits
    HIGH = "high"          # Destructive file ops, modifying build/deps, non-whitelisted commands
    CRITICAL = "critical"  # Production deploys, secrets, forbidden OS commands, external pushes


class NetworkPolicyMode(str, Enum):
    """Enforcement mode for outbound network requests."""
    DENY_ALL = "deny_all"                # Completely air-gapped (default)
    ALLOW_WHITELIST = "allow_whitelist"  # Only explicitly listed hostnames allowed
    ALLOW_ALL = "allow_all"              # Unrestricted outbound network access


class PermissionDeniedError(PermissionError):
    """Raised when an action violates a non-negotiable security policy."""
    pass


class ApprovalRequiredError(PermissionError):
    """Raised when an operation requires human approval and approval was rejected or unavailable."""
    pass


class PermissionPolicy(BaseModel):
    """Configurable permission policy governing tool execution."""
    name: str = "default_secure_policy"

    # 1. File Read Policies
    allowed_read_patterns: List[str] = Field(default_factory=lambda: ["*"])
    blocked_read_patterns: List[str] = Field(default_factory=lambda: [
        ".env*",
        "**/.env*",
        "*secret*",
        "**/*secret*",
        "*credential*",
        "**/*credential*",
        "*id_rsa*",
        "**/*id_rsa*",
        "*id_ed25519*",
        "**/*id_ed25519*",
        "*.pem",
        "**/*.pem",
        "*.key",
        "**/*.key",
        ".git/config",
        "**/.git/config",
        "**/.aws/**",
        "**/.ssh/**",
    ])

    # 2. File Write Policies
    allowed_write_patterns: List[str] = Field(default_factory=lambda: [
        "**/*.py",
        "**/*.md",
        "**/*.txt",
        "**/*.json",
        "**/*.yaml",
        "**/*.yml",
        "tests/**",
        "src/**",
        "calculator/**",
    ])
    protected_write_patterns: List[str] = Field(default_factory=lambda: [
        ".github/**",
        "**/.github/**",
        "docker-compose*.yml",
        "Dockerfile*",
        "*production*",
        "**/*production*",
        "deploy/**",
        "**/deploy/**",
        "requirements*.txt",
        "pyproject.toml",
        "setup.py",
        "alembic/**",
        "*.lock",
        "Pipfile*",
    ])
    blocked_write_patterns: List[str] = Field(default_factory=lambda: [
        ".git/**",
        "**/.git/**",
        ".env*",
        "**/.env*",
        "*secret*",
        "**/*secret*",
        "*.pem",
        "**/*.pem",
        "*.key",
        "**/*.key",
    ])

    # 3. Command Execution Policies
    allowed_commands: List[str] = Field(default_factory=lambda: [
        "pytest*",
        "python* -m pytest*",
        "python3 -m pytest*",
        "flake8*",
        "black*",
        "mypy*",
        "git diff*",
        "git status*",
        "git log*",
        "echo*",
        "ls*",
    ])
    destructive_commands: List[str] = Field(default_factory=lambda: [
        "git reset*",
        "git clean*",
        "git checkout --*",
        "git restore*",
        "rm *",
        "rm -*",
        "rmdir *",
        "pip install*",
        "truncate*",
        "shred*",
    ])
    forbidden_commands: List[str] = Field(default_factory=lambda: [
        "sudo*",
        "su *",
        "rm -rf /",
        "rm -rf /*",
        "mkfs*",
        "dd *",
        "chmod 777*",
        "chmod -R 777*",
        "shutdown*",
        "reboot*",
        "*|*bash",
        "*|*sh",
        "curl*|*",
        "wget*|*",
        "*:(){ :|:& };:*",
        "nc -e*",
        "bash -i*",
    ])

    # 4. Network Access Policies
    network_mode: NetworkPolicyMode = NetworkPolicyMode.DENY_ALL
    allowed_domains: List[str] = Field(default_factory=lambda: [
        "github.com",
        "api.github.com",
        "pypi.org",
        "files.pythonhosted.org",
    ])

    # 5. Operations Requiring Human Approval
    require_human_approval_for: Set[RiskLevel] = Field(default_factory=lambda: {
        RiskLevel.HIGH,
        RiskLevel.CRITICAL,
    })
    strict_mode: bool = True

    def _normalize_path(self, path: str) -> str:
        """Normalizes path separators and strips leading ./ without removing leading dots from filenames."""
        p = path.replace("\\", "/")
        while p.startswith("./"):
            p = p[2:]
        return p

    def _matches_any(self, path: str, patterns: List[str]) -> bool:
        """Helper to match a path string against fnmatch globs."""
        norm_path = self._normalize_path(path)
        base = os.path.basename(norm_path)
        for pat in patterns:
            if fnmatch.fnmatch(norm_path, pat):
                return True
            if "/" not in pat and fnmatch.fnmatch(base, pat):
                return True
            if fnmatch.fnmatch("/" + norm_path, pat):
                return True
        return False

    def check_read_permission(self, rel_path: str) -> Tuple[bool, Optional[str]]:
        """Checks if reading a file path is permitted."""
        if self._matches_any(rel_path, self.blocked_read_patterns):
            return False, f"Reading '{rel_path}' is blocked by security policy (sensitive credentials or secrets)."
        return True, None

    def check_write_permission(self, rel_path: str) -> Tuple[bool, RiskLevel, Optional[str]]:
        """Checks if writing/modifying a file path is permitted and determines risk level."""
        # 1. Check unconditionally blocked paths
        if self._matches_any(rel_path, self.blocked_write_patterns):
            return False, RiskLevel.CRITICAL, f"Writing to '{rel_path}' is strictly forbidden by policy."

        # 2. Check protected paths (sensitive production configs, CI/CD, lockfiles)
        if self._matches_any(rel_path, self.protected_write_patterns):
            return True, RiskLevel.HIGH, f"Writing to protected production path '{rel_path}' requires human approval."

        # 3. Check allowed write patterns
        if self._matches_any(rel_path, self.allowed_write_patterns) or not self.strict_mode:
            return True, RiskLevel.MEDIUM, None

        return False, RiskLevel.HIGH, f"Writing to '{rel_path}' is not within allowed write patterns."

    def check_delete_permission(self, rel_path: str) -> Tuple[bool, RiskLevel, Optional[str]]:
        """Checks file deletion permissions. Deletion is always high risk and destructive."""
        if self._matches_any(rel_path, self.blocked_write_patterns):
            return False, RiskLevel.CRITICAL, f"Deleting '{rel_path}' is strictly forbidden."
        return True, RiskLevel.HIGH, f"Deleting '{rel_path}' is a destructive operation."

    def check_command_permission(self, command: str) -> Tuple[bool, RiskLevel, Optional[str]]:
        """Checks shell command execution permissions against forbidden and destructive lists."""
        cmd_clean = command.strip()

        # 1. Check unconditionally forbidden commands
        for pat in self.forbidden_commands:
            if fnmatch.fnmatch(cmd_clean, pat) or re.search(r"\b" + re.escape(pat.rstrip("*")) + r"\b", cmd_clean):
                return False, RiskLevel.CRITICAL, f"Command '{command}' is strictly forbidden by security policy."

        # 2. Check destructive commands (requires human approval)
        for pat in self.destructive_commands:
            if fnmatch.fnmatch(cmd_clean, pat) or cmd_clean.startswith(pat.rstrip("*")):
                return True, RiskLevel.HIGH, f"Destructive command '{command}' requires human approval."

        # 3. Check allowed commands
        for pat in self.allowed_commands:
            if fnmatch.fnmatch(cmd_clean, pat) or cmd_clean.startswith(pat.rstrip("*")):
                return True, RiskLevel.LOW, None

        # 4. Unknown command under strict mode
        if self.strict_mode:
            return True, RiskLevel.HIGH, f"Unclassified command '{command}' requires human approval under strict mode."

        return True, RiskLevel.MEDIUM, None

    def check_network_permission(self, url_or_host: str) -> Tuple[bool, RiskLevel, Optional[str]]:
        """Checks network access permissions."""
        if self.network_mode == NetworkPolicyMode.DENY_ALL:
            return False, RiskLevel.CRITICAL, "Outbound network access is strictly denied by air-gapped security policy."

        # Extract hostname
        host = url_or_host.split("://")[-1].split("/")[0].split(":")[0].lower()
        if self.network_mode == NetworkPolicyMode.ALLOW_WHITELIST:
            if any(host == d.lower() or host.endswith("." + d.lower()) for d in self.allowed_domains):
                return True, RiskLevel.LOW, None
            return False, RiskLevel.CRITICAL, f"Network access to '{host}' is not in allowed domain whitelist."

        return True, RiskLevel.MEDIUM, None

    def check_external_service_permission(
        self, service_name: str, action: str, details: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, RiskLevel, Optional[str]]:
        """Checks permission for external service integrations (e.g. Git push, cloud deployments)."""
        action_lower = action.lower()
        svc_lower = service_name.lower()

        # Critical: git push to production or main branches
        if svc_lower == "git" and "push" in action_lower:
            target_branch = str((details or {}).get("branch", "")).lower()
            if target_branch in ("main", "master", "prod", "production"):
                return True, RiskLevel.CRITICAL, f"Git push to protected branch '{target_branch}' requires explicit human approval."
            return True, RiskLevel.HIGH, f"Git push to branch '{target_branch}' requires human approval."

        # Critical: external webhook or cloud deployment
        if svc_lower in ("deploy", "cloud", "aws", "gcp", "kubernetes"):
            return True, RiskLevel.CRITICAL, f"External infrastructure operation on '{service_name}' requires human approval."

        return True, RiskLevel.MEDIUM, None

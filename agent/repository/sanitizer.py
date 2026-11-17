"""Workspace Secret Sanitization & Quarantine Engine.

Scans isolated task workspaces and repositories for sensitive credential files
(.env*, credentials.json, private keys, secrets.*) and neutralizes them prior
to mounting into execution sandboxes or running test suites.
"""

import os
import shutil
import hashlib
import fnmatch
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("agent.repository.sanitizer")

# Patterns for sensitive credential files
SENSITIVE_FILE_PATTERNS = [
    ".env",
    ".env.*",
    "*secret*",
    "*credential*",
    "*id_rsa*",
    "*id_ed25519*",
    "*.pem",
    "*.key",
    ".git-credentials",
    ".netrc",
]

# Patterns explicitly exempted from sanitization (safe templates and examples)
SAFE_TEMPLATE_PATTERNS = [
    ".env.example",
    ".env.sample",
    ".env.template",
    "*.example",
    "*.sample",
    "*.template",
    ".env.test.example",
]

# Standard placeholder text placed inside sanitized secret files
SANITIZED_PLACEHOLDER_CONTENT = (
    "# ===================================================================\n"
    "# [QUARANTINED BY AUTONOMOUS AGENT SECURITY GATE]\n"
    "# This sensitive credential file was isolated to prevent accidental\n"
    "# exfiltration, sandbox credential leakage, or trace exposure.\n"
    "# Original content has been securely quarantined outside the workspace.\n"
    "# ===================================================================\n"
)


class QuarantinedFileRecord(BaseModel):
    """Metadata record for a quarantined sensitive credential file."""
    rel_path: str
    original_path: str
    quarantine_path: str
    sha256_hash: str
    quarantined_at: float
    file_mode: int


class WorkspaceSanitizer:
    """Manages identification, quarantine, neutralization, and restoration of workspace secrets."""

    @staticmethod
    def is_secret_file(file_path: Path) -> bool:
        """Determines whether a given file matches sensitive credential patterns and is not a safe template."""
        file_name = file_path.name.lower()

        # Check safe template exemption first
        for safe_pat in SAFE_TEMPLATE_PATTERNS:
            if fnmatch.fnmatch(file_name, safe_pat.lower()):
                return False

        # Check sensitive patterns against filename and relative path
        for secret_pat in SENSITIVE_FILE_PATTERNS:
            if fnmatch.fnmatch(file_name, secret_pat.lower()):
                return True

        return False

    @classmethod
    def scan_for_secrets(cls, workspace_path: Path) -> List[Path]:
        """Scans the workspace directory and returns paths to all sensitive credential files."""
        workspace_path = workspace_path.resolve()
        if not workspace_path.exists() or not workspace_path.is_dir():
            return []

        secret_files = []
        for root, dirs, files in os.walk(workspace_path):
            # Skip VCS and cache directories
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".pytest_cache", ".venv", "venv", ".quarantine")]
            for file in files:
                p = Path(root) / file
                if cls.is_secret_file(p):
                    secret_files.append(p)

        return secret_files

    @classmethod
    def quarantine_secrets(
        cls,
        workspace_path: Path,
        quarantine_dir: Optional[Path] = None,
    ) -> List[QuarantinedFileRecord]:
        """Scans workspace, moves sensitive files into secure quarantine, and replaces them with harmless placeholders."""
        workspace_path = workspace_path.resolve()
        if not workspace_path.exists():
            return []

        if quarantine_dir is None:
            # Place quarantine directory adjacent to workspace (never inside the workspace itself)
            quarantine_dir = workspace_path.parent / ".quarantine" / workspace_path.name
        
        quarantine_dir = quarantine_dir.resolve()
        quarantine_dir.mkdir(parents=True, exist_ok=True)

        found_secrets = cls.scan_for_secrets(workspace_path)
        records: List[QuarantinedFileRecord] = []

        import time

        for secret_file in found_secrets:
            try:
                rel_path = str(secret_file.relative_to(workspace_path))
                raw_bytes = secret_file.read_bytes()
                file_hash = hashlib.sha256(raw_bytes).hexdigest()
                file_mode = secret_file.stat().st_mode

                # Store copy in secure quarantine location
                target_quarantine = quarantine_dir / f"{file_hash}_{secret_file.name}"
                target_quarantine.write_bytes(raw_bytes)
                os.chmod(target_quarantine, 0o600)  # Owner read/write only

                # Neutralize the file in the workspace
                secret_file.write_text(SANITIZED_PLACEHOLDER_CONTENT, encoding="utf-8")

                records.append(
                    QuarantinedFileRecord(
                        rel_path=rel_path,
                        original_path=str(secret_file),
                        quarantine_path=str(target_quarantine),
                        sha256_hash=file_hash,
                        quarantined_at=time.time(),
                        file_mode=file_mode,
                    )
                )
                logger.info(f"Quarantined sensitive file '{rel_path}' -> '{target_quarantine.name}'")
            except Exception as e:
                logger.warning(f"Could not quarantine sensitive file '{secret_file}': {e}")

        return records

    @classmethod
    def restore_secrets(
        cls,
        workspace_path: Path,
        records: List[QuarantinedFileRecord],
    ) -> int:
        """Restores original quarantined sensitive files into the workspace."""
        workspace_path = workspace_path.resolve()
        restored_count = 0

        for rec in records:
            orig = Path(rec.original_path)
            quarantine = Path(rec.quarantine_path)
            if quarantine.exists() and orig.exists():
                try:
                    orig.write_bytes(quarantine.read_bytes())
                    os.chmod(orig, rec.file_mode)
                    restored_count += 1
                    logger.info(f"Restored original sensitive file '{rec.rel_path}'")
                except Exception as e:
                    logger.warning(f"Failed to restore quarantined file '{rec.rel_path}': {e}")

        return restored_count


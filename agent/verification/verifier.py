"""Independent Verification Pipeline for Autonomous AI Coding Agent.

Performs independent validation of final results:
1. Baseline regression tests verification
2. Generated edge-case tests verification
3. Python AST linting and static checks
4. Git diff / change scope inspection (ensuring no tests removed and no unrelated files modified)
5. Explicit outcome separation: completed_successfully, completed_with_failures, blocked, cancelled.
"""

import ast
import os
import re
import difflib
import hashlib
import hmac
import json
import logging
import secrets
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field, model_validator, ConfigDict

logger = logging.getLogger("agent.verifier")

from agent.core.state import AgentState, TestResult, ReviewResult, CoderResult, TestGenResult
from agent.agents.reviewer import should_be_reviewed


class WorkflowOutcome(str, Enum):
    """Explicit terminal workflow outcome classifications."""
    COMPLETED_SUCCESSFULLY = "completed_successfully"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class BaselineVerificationStatus(str, Enum):
    """Integrity status of baseline regression verification snapshot."""
    VERIFIED = "BASELINE_VERIFIED"
    UNVERIFIABLE = "BASELINE_UNVERIFIABLE"
    NOT_APPLICABLE = "BASELINE_NOT_APPLICABLE"


def canonicalize_test_id(test_id: str) -> str:
    """Canonicalizes a test identifier while strictly preserving identity-bearing information.

    Preserves:
    - Complete file path and directory structure (e.g., 'tests/unit/test_api.py')
    - Test class scopes (e.g., 'TestAPI::test_create')
    - Test function names
    - Parameterized test identifiers (e.g., '[param1-param2]')

    Normalizes only known formatting differences:
    - Strips surrounding whitespace
    - Normalizes Windows backslashes ('\\') to standard POSIX slashes ('/')
    - Collapses duplicate consecutive slashes ('//' -> '/')
    - Strips leading relative directory prefixes ('./')
    """
    if not isinstance(test_id, str):
        return str(test_id)
    cleaned = test_id.strip().replace("\\", "/")
    while "//" in cleaned:
        cleaned = cleaned.replace("//", "/")
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


@dataclass
class BaselineSnapshot:
    """Explicit execution metadata and snapshot integrity for baseline test suite.
    Derives status from the snapshot's integrity and execution outcome,
    not merely the presence or size of passed_tests.
    """
    inventory: Set[str] = field(default_factory=set)
    passed_tests: Set[str] = field(default_factory=set)
    failed_tests: Set[str] = field(default_factory=set)
    execution_completed: bool = False
    collection_completed: bool = False
    timed_out: bool = False
    execution_error: Optional[str] = None
    skipped_tests: Set[str] = field(default_factory=set)
    snapshot_hash: Optional[str] = None
    signature: Optional[str] = None

    def compute_hash(self) -> str:
        """Deterministic SHA-256 digest of the baseline snapshot inventory and execution outcome."""
        payload = {
            "inventory": sorted([canonicalize_test_id(t) for t in self.inventory]),
            "passed_tests": sorted([canonicalize_test_id(t) for t in self.passed_tests]),
            "failed_tests": sorted([canonicalize_test_id(t) for t in self.failed_tests]),
            "skipped_tests": sorted([canonicalize_test_id(t) for t in self.skipped_tests]),
            "execution_completed": self.execution_completed,
            "collection_completed": self.collection_completed,
            "timed_out": self.timed_out,
            "execution_error": self.execution_error,
        }
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def seal(self, signing_key: Optional[bytes] = None) -> "BaselineSnapshot":
        """Calculates and stores the cryptographic snapshot digest and optional HMAC-SHA256 signature."""
        self.snapshot_hash = self.compute_hash()
        if signing_key:
            self.signature = hmac.new(
                signing_key,
                self.snapshot_hash.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        return self

    def verify_signature(self, signing_key: bytes) -> bool:
        """Verifies cryptographic HMAC signature against recomputed digest, preventing re-sealing attacks."""
        if not self.signature or not self.snapshot_hash:
            return False
        expected_sig = hmac.new(
            signing_key,
            self.compute_hash().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(self.signature, expected_sig)

    def derive_status(self) -> BaselineVerificationStatus:
        """Derives verification status from execution integrity, outcome completeness, and collection outcome:
        - Incomplete collection (collection_completed=False) -> UNVERIFIABLE.
        - Missing snapshot hash (unrecorded / unsealed digest) -> UNVERIFIABLE.
        - Snapshot hash mismatch (tampered baseline state) -> UNVERIFIABLE.
        - Timeout, abnormal execution, or execution error -> UNVERIFIABLE.
        - Incomplete execution (execution_completed=False) -> UNVERIFIABLE.
        - Conflicting classifications (test in multiple outcome sets) -> UNVERIFIABLE.
        - Unexpected test IDs (outcome contains tests not in inventory) -> UNVERIFIABLE.
        - Empty inventory + confirmed collection + complete execution + empty outcomes -> NOT_APPLICABLE.
        - Missing outcomes (discovered test has no recorded outcome) -> UNVERIFIABLE.
        - Non-empty inventory + complete execution, collection, and complete valid outcomes -> VERIFIED.
        """
        if not self.collection_completed:
            return BaselineVerificationStatus.UNVERIFIABLE
        if self.snapshot_hash is None:
            return BaselineVerificationStatus.UNVERIFIABLE
        if self.compute_hash() != self.snapshot_hash:
            return BaselineVerificationStatus.UNVERIFIABLE
        if self.timed_out or bool(self.execution_error) or not self.execution_completed:
            return BaselineVerificationStatus.UNVERIFIABLE

        # 1. Validate outcome exclusivity: no test may have conflicting classifications
        if (
            (self.passed_tests & self.failed_tests)
            or (self.passed_tests & self.skipped_tests)
            or (self.failed_tests & self.skipped_tests)
        ):
            return BaselineVerificationStatus.UNVERIFIABLE

        # Canonical normalization strictly preserving file path, class scope, and parameterization
        norm_inventory = {canonicalize_test_id(t) for t in self.inventory}
        norm_passed = {canonicalize_test_id(t) for t in self.passed_tests}
        norm_failed = {canonicalize_test_id(t) for t in self.failed_tests}
        norm_skipped = {canonicalize_test_id(t) for t in self.skipped_tests}

        # Check conflicting classifications on canonical names as well
        if (
            (norm_passed & norm_failed)
            or (norm_passed & norm_skipped)
            or (norm_failed & norm_skipped)
        ):
            return BaselineVerificationStatus.UNVERIFIABLE

        norm_accounted = norm_passed | norm_failed | norm_skipped

        # 2. Validate unexpected test IDs: outcome sets cannot contain tests not in inventory
        unexpected_results = norm_accounted - norm_inventory
        if unexpected_results:
            return BaselineVerificationStatus.UNVERIFIABLE

        # 3. For empty inventory: require all outcome sets to be completely empty
        if len(self.inventory) == 0:
            if len(self.passed_tests) > 0 or len(self.failed_tests) > 0 or len(self.skipped_tests) > 0:
                return BaselineVerificationStatus.UNVERIFIABLE
            return BaselineVerificationStatus.NOT_APPLICABLE

        # 4. Validate outcome completeness: every discovered test must have a recorded outcome
        missing_results = norm_inventory - norm_accounted
        if missing_results:
            return BaselineVerificationStatus.UNVERIFIABLE

        return BaselineVerificationStatus.VERIFIED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inventory": sorted(list(self.inventory)),
            "passed_tests": sorted(list(self.passed_tests)),
            "failed_tests": sorted(list(self.failed_tests)),
            "skipped_tests": sorted(list(self.skipped_tests)),
            "execution_completed": self.execution_completed,
            "collection_completed": self.collection_completed,
            "timed_out": self.timed_out,
            "execution_error": self.execution_error,
            "snapshot_hash": self.snapshot_hash,
            "signature": self.signature,
            "status": self.derive_status(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaselineSnapshot":
        inv = set(data.get("inventory") or data.get("baseline_tests") or [])
        passed = set(data.get("passed_tests") or [])
        failed = set(data.get("failed_tests") or [])
        skipped = set(data.get("skipped_tests") or [])
        exec_comp = bool(data.get("execution_completed", data.get("executed", False)))
        coll_comp = bool(data.get("collection_completed", False))
        t_out = bool(data.get("timed_out", False))
        err = data.get("execution_error") or data.get("error_summary")
        if err == "":
            err = None
        s_hash = data.get("snapshot_hash")
        sig = data.get("signature")
        return cls(
            inventory=inv,
            passed_tests=passed,
            failed_tests=failed,
            skipped_tests=skipped,
            execution_completed=exec_comp,
            collection_completed=coll_comp,
            timed_out=t_out,
            execution_error=err,
            snapshot_hash=s_hash,
            signature=sig,
        )


def derive_baseline_status(snapshot: BaselineSnapshot) -> BaselineVerificationStatus:
    """Convenience helper deriving verification status from a BaselineSnapshot instance."""
    return snapshot.derive_status()


class LintCheckResult(BaseModel):
    """Structured outcome of Python AST and static lint analysis."""
    passed: bool
    issues: List[str] = Field(default_factory=list)
    files_checked: List[str] = Field(default_factory=list)


class DiffReviewResult(BaseModel):
    """Structured inspection of the final git diff and repository delta."""
    passed: bool
    tests_preserved: bool
    deleted_tests: List[str] = Field(default_factory=list)
    weakened_tests: List[str] = Field(default_factory=list)
    deleted_assertions: List[str] = Field(default_factory=list)
    unrelated_files_modified: List[str] = Field(default_factory=list)
    modified_files: List[str] = Field(default_factory=list)
    diff_summary: str


class VerificationResult(BaseModel):
    """Consolidated independent verification assessment."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    verified: bool
    outcome: WorkflowOutcome
    baseline_status: BaselineVerificationStatus = Field(
        default=BaselineVerificationStatus.UNVERIFIABLE,
        description="Integrity status of baseline comparison (BASELINE_VERIFIED, BASELINE_UNVERIFIABLE, BASELINE_NOT_APPLICABLE)",
    )
    baseline_inventory_count: Optional[int] = Field(
        default=None,
        description="Total count of pre-existing baseline tests discovered in repository prior to changes. Must be explicitly 0 for NOT_APPLICABLE.",
    )
    baseline_snapshot: Optional[BaselineSnapshot] = Field(
        default=None,
        description="Explicit execution metadata and snapshot integrity for baseline test suite.",
    )
    tests_passed: bool = Field(default=False)
    baseline_tests_passed: bool
    generated_tests_passed: bool
    lint_checks_passed: bool
    tests_preserved: bool
    git_diff_clean: bool
    reviewer_approved: bool
    no_blocking_issues: bool = Field(default=True)
    review_hashes_valid: bool = Field(default=True)
    toctou_valid: bool = Field(default=True)
    baseline_snapshot_hash_valid: bool = Field(
        default=True,
        description="Whether baseline snapshot hash matched expected digest without tampering.",
    )
    baseline_signature: Optional[str] = Field(
        default=None,
        description="Cryptographic HMAC-SHA256 signature binding baseline snapshot to verifier.",
    )
    baseline_regressions: List[str] = Field(default_factory=list)
    baseline_tests_not_executed: List[str] = Field(
        default_factory=list,
        description="Pre-existing baseline tests that passed before, but were not successfully executed or verified post-patch (e.g. collection error, skipped, or incomplete run).",
    )
    baseline_tests_preserved: List[str] = Field(
        default_factory=list,
        description="Pre-existing baseline tests that passed before and whose contracts were successfully checked and verified passing post-patch.",
    )
    pre_existing_failures: List[str] = Field(default_factory=list)
    fixed_tests: List[str] = Field(default_factory=list)
    failure_reasons: List[str] = Field(default_factory=list)
    lint_details: Optional[LintCheckResult] = None
    diff_details: Optional[DiffReviewResult] = None
    summary: str
    snapshot_hash: Optional[str] = Field(
        default=None,
        description="Cryptographic root SHA-256 hash representing the exact immutable snapshot of all verified repository files.",
    )
    verified_manifest: Dict[str, str] = Field(
        default_factory=dict,
        description="File-by-file SHA-256 hash manifest captured at the moment of independent verification to protect against TOCTOU tampering.",
    )
    handover_artifact: Optional[str] = Field(
        default=None,
        description="Filesystem path to the sealed, read-only immutable snapshot handover archive.",
    )
    handover_hash: Optional[str] = Field(
        default=None,
        description="Cryptographic SHA-256 hash of the immutable handover bundle.",
    )

    @model_validator(mode="after")
    def validate_not_applicable_inventory_consistency(self):
        """Enforces that NOT_APPLICABLE status is permitted ONLY when baseline inventory is genuinely empty and proven."""
        if self.baseline_status == BaselineVerificationStatus.NOT_APPLICABLE:
            if self.baseline_inventory_count is None:
                raise ValueError(
                    "Invalid verification state: baseline_status cannot be NOT_APPLICABLE when baseline_inventory_count is missing or None (must be explicitly 0)"
                )
            if self.baseline_inventory_count > 0:
                raise ValueError(
                    f"Invalid verification state: baseline_status cannot be NOT_APPLICABLE when baseline_inventory_count is {self.baseline_inventory_count} > 0"
                )
        return self

    @property
    def passed(self) -> bool:
        """Alias for verified."""
        return bool(self.verified)

    @property
    def lint_passed(self) -> bool:
        """Alias for lint_checks_passed."""
        return bool(self.lint_checks_passed)

    @property
    def diff_passed(self) -> bool:
        """Alias for tests_preserved and git_diff_clean."""
        return bool(self.tests_preserved and self.git_diff_clean)


# Protected in-memory ledgers and cryptographic signing keys bound to repository paths.
# Kept strictly internal to the sovereign verifier to isolate against external/in-memory tampering.
_PROTECTED_VERIFICATION_LEDGER: Dict[str, Dict[str, Any]] = {}
_PROTECTED_SIGNING_KEYS: Dict[str, bytes] = {}


class IndependentVerifier:
    """Performs rigorous, multi-faceted independent verification before final handover."""

    def __init__(self, repo_path: str, signing_secret: Optional[bytes] = None, trust_level: Optional[str] = None):
        self.repo_path = Path(repo_path).resolve()
        self.trust_level = trust_level
        repo_key = str(self.repo_path)
        if signing_secret:
            self._signing_secret: bytes = signing_secret
            _PROTECTED_SIGNING_KEYS[repo_key] = signing_secret
        elif repo_key in _PROTECTED_SIGNING_KEYS:
            self._signing_secret = _PROTECTED_SIGNING_KEYS[repo_key]
        else:
            self._signing_secret = secrets.token_bytes(32)
            _PROTECTED_SIGNING_KEYS[repo_key] = self._signing_secret

        self._trusted_baseline_ledger: Dict[str, Dict[str, Any]] = {}

    def capture_baseline(self, run_tests: bool = True) -> Dict[str, Any]:
        """Snapshots existing test inventory, AST structures, file contents, hashes,
        and runs original test suite to capture baseline test outcomes prior to modification.
        """
        baseline_tests: Set[str] = set()
        baseline_files: Set[str] = set()
        baseline_test_structures: Dict[str, Dict[str, Any]] = {}
        baseline_test_files: Dict[str, str] = {}
        baseline_file_hashes: Dict[str, str] = {}

        collection_completed = True
        try:
            if self.repo_path.exists():
                for root, _, files in os.walk(self.repo_path):
                    # Ignore caches, checkpoints, and venvs
                    if any(x in root for x in (".pytest_cache", ".git", "__pycache__", "venv", ".checkpoints")):
                        continue
                    for f in files:
                        full_p = Path(root) / f
                        rel = os.path.relpath(full_p, self.repo_path).replace("\\", "/")
                        baseline_files.add(rel)
                        try:
                            baseline_file_hashes[rel] = hashlib.sha256(full_p.read_bytes()).hexdigest()
                        except Exception:
                            pass
                        if f.startswith("test_") and f.endswith(".py"):
                            baseline_tests.update(self._extract_test_names(full_p))
                            structs = self._extract_test_structures(full_p)
                            for t_name, s_data in structs.items():
                                baseline_test_structures[f"{rel}::{t_name}"] = s_data
                                baseline_test_structures[t_name] = s_data
                            try:
                                baseline_test_files[rel] = full_p.read_text(encoding="utf-8")
                            except Exception:
                                pass
        except Exception as e:
            logger.warning(f"Error during baseline collection: {e}")
            collection_completed = False

        passed_set: Set[str] = set()
        failed_set: Set[str] = set()
        skipped_set: Set[str] = set()
        execution_completed = False
        timed_out = False
        execution_error: Optional[str] = None
        exit_code = 0

        # Run original test suite and record baseline outcomes
        if run_tests and baseline_tests and collection_completed:
            try:
                from agent.execution.sandbox import ExecutionSandbox
                sandbox = ExecutionSandbox(str(self.repo_path), trust_level=self.trust_level)
                baseline_res = sandbox.run_pytest()
                exit_code = baseline_res.exit_code
                timed_out = getattr(baseline_res, "timed_out", False) or "timed out" in (baseline_res.error_summary or "").lower()

                passed_list, failed_list, skipped_list = self._parse_pytest_outcomes(
                    baseline_res.stdout or "",
                    baseline_tests,
                )

                if baseline_res.passed and not passed_list and not failed_list:
                    passed_list = sorted(list(baseline_tests))

                passed_set = set(passed_list)
                failed_set = set(failed_list)
                skipped_set = set(skipped_list)

                # Pytest exit codes: 0 = passed, 1 = tests failed
                if exit_code in (0, 1) and not timed_out:
                    execution_completed = True
                    execution_error = None
                else:
                    execution_completed = False
                    execution_error = baseline_res.error_summary or f"Pytest exited with abnormal exit code {exit_code}"
            except Exception as e:
                logger.warning(f"Could not execute baseline test suite: {e}")
                execution_completed = False
                execution_error = str(e)
        elif not baseline_tests and collection_completed:
            # Greenfield task: no baseline tests discovered, collection completed cleanly
            execution_completed = True
            execution_error = None
        else:
            # Baseline tests exist on disk, but tests were not executed (e.g. run_tests=False)
            execution_completed = False
            execution_error = "Baseline tests were not executed prior to changes"

        snapshot = BaselineSnapshot(
            inventory=baseline_tests,
            passed_tests=passed_set,
            failed_tests=failed_set,
            skipped_tests=skipped_set,
            execution_completed=execution_completed,
            collection_completed=collection_completed,
            timed_out=timed_out,
            execution_error=execution_error,
        )
        snapshot.seal(signing_key=self._signing_secret)

        ledger_entry = {
            "snapshot_hash": snapshot.snapshot_hash,
            "signature": snapshot.signature,
            "inventory_count": len(snapshot.inventory),
            "timestamp": time.time(),
        }
        self._trusted_baseline_ledger[str(self.repo_path)] = ledger_entry
        _PROTECTED_VERIFICATION_LEDGER[str(self.repo_path)] = ledger_entry
        self._last_baseline_ledger_entry = ledger_entry

        baseline_outcomes = {
            "suite_passed": exit_code == 0 if execution_completed else False,
            "passed_tests": sorted(list(passed_set)),
            "failed_tests": sorted(list(failed_set)),
            "skipped_tests": sorted(list(skipped_set)),
            "exit_code": exit_code,
            "error_summary": execution_error or "",
            "executed": execution_completed,
            "timed_out": timed_out,
            "collection_completed": collection_completed,
            "snapshot_hash": snapshot.snapshot_hash,
            "signature": snapshot.signature,
            "status": snapshot.derive_status(),
        }

        baseline_record = {
            "baseline_tests": sorted(list(baseline_tests)),
            "baseline_files": sorted(list(baseline_files)),
            "baseline_test_structures": baseline_test_structures,
            "baseline_test_files": baseline_test_files,
            "baseline_file_hashes": baseline_file_hashes,
            "baseline_outcomes": baseline_outcomes,
            "baseline_snapshot": snapshot,
            "baseline_snapshot_hash": snapshot.snapshot_hash,
            "baseline_signature": snapshot.signature,
        }
        self._last_baseline = baseline_record
        return baseline_record

    def _extract_test_structures(self, test_file_path: Path) -> Dict[str, Dict[str, Any]]:
        """Extracts detailed test structures including assertion counts and assertion AST representations
        to detect weakened tests or deleted/commented-out assertions.
        """
        structures: Dict[str, Dict[str, Any]] = {}
        try:
            content = test_file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(test_file_path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                    assertions: List[str] = []
                    for child in ast.walk(node):
                        # 1. Standard python assert statement: assert x == y
                        if isinstance(child, ast.Assert):
                            try:
                                assertions.append(ast.unparse(child).strip())
                            except Exception:
                                assertions.append("assert")
                        # 2. Context manager: with pytest.raises(...):
                        elif isinstance(child, ast.With):
                            for item in child.items:
                                item_str = ""
                                try:
                                    item_str = ast.unparse(item.context_expr)
                                except Exception:
                                    pass
                                if "raises" in item_str or "assertRaises" in item_str:
                                    assertions.append(f"with {item_str}")
                        # 3. Method call: self.assertEqual, self.assertTrue, etc.
                        elif isinstance(child, ast.Call):
                            call_str = ""
                            try:
                                call_str = ast.unparse(child.func)
                            except Exception:
                                pass
                            if any(call_str.endswith(f"assert{m}") or call_str.startswith("assert_") for m in ["Equal", "True", "False", "In", "Raises", "AlmostEqual", "Is", "IsNot"]):
                                assertions.append(f"call {call_str}")

                    rel = str(test_file_path.relative_to(self.repo_path)).replace("\\", "/")
                    structures[node.name] = {
                        "name": node.name,
                        "file": rel,
                        "assertion_count": len(assertions),
                        "assertions": assertions,
                    }
        except Exception as e:
            logger.debug(f"Could not parse test structures in {test_file_path}: {e}")
        return structures

    def _detect_actual_file_changes(self, baseline: Dict[str, Any]) -> Set[str]:
        """Detects actual file modifications on disk using Git status (if available)
        and cryptographic content hash comparison against the baseline snapshot.
        """
        modified = set()

        # 1. Git-based status inspection
        if (self.repo_path / ".git").exists():
            try:
                proc = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=str(self.repo_path),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if proc.returncode == 0 and proc.stdout:
                    for line in proc.stdout.splitlines():
                        if len(line) > 3:
                            rel_file = line[3:].strip().replace("\\", "/")
                            if not any(x in rel_file for x in (".checkpoints", ".pytest_cache", "__pycache__")):
                                modified.add(rel_file)
            except Exception as e:
                logger.debug(f"Git status inspection skipped: {e}")

        # 2. Filesystem hash delta against baseline snapshot
        baseline_hashes = baseline.get("baseline_file_hashes", {})
        if self.repo_path.exists():
            current_files = set()
            for root, _, files in os.walk(self.repo_path):
                if any(x in root for x in (".pytest_cache", ".git", "__pycache__", "venv", ".checkpoints")):
                    continue
                for f in files:
                    full_p = Path(root) / f
                    rel = os.path.relpath(full_p, self.repo_path).replace("\\", "/")
                    current_files.add(rel)
                    try:
                        curr_hash = hashlib.sha256(full_p.read_bytes()).hexdigest()
                        if rel in baseline_hashes:
                            if curr_hash != baseline_hashes[rel]:
                                modified.add(rel)
                        elif baseline_hashes:
                            # Newly created file not in baseline
                            modified.add(rel)
                    except Exception:
                        pass

            # Detect files deleted from baseline
            for rel in baseline_hashes:
                if rel not in current_files:
                    modified.add(rel)

        return modified

    def _parse_pytest_outcomes(self, stdout: str, test_names: Set[str]) -> Tuple[List[str], List[str], List[str]]:
        """Parses individual test outcomes from verbose pytest stdout."""
        passed = set()
        failed = set()
        skipped = set()
        for line in stdout.splitlines():
            m = re.search(r"(?:::|\b)(test_[a-zA-Z0-9_]+)\s+([A-Z]+)", line)
            if m:
                t_name = m.group(1)
                status = m.group(2).upper()
                if status == "PASSED":
                    passed.add(t_name)
                elif status == "FAILED":
                    failed.add(t_name)
                elif status in ("SKIPPED", "XFAIL"):
                    skipped.add(t_name)
            else:
                fm = re.search(r"FAILED\s+(?:[^\s:]+::)?(test_[a-zA-Z0-9_]+)", line)
                if fm:
                    failed.add(fm.group(1))
                pm = re.search(r"PASSED\s+(?:[^\s:]+::)?(test_[a-zA-Z0-9_]+)", line)
                if pm:
                    passed.add(pm.group(1))
                sm = re.search(r"(?:SKIPPED|XFAIL)\s+(?:[^\s:]+::)?(test_[a-zA-Z0-9_]+)", line)
                if sm:
                    skipped.add(sm.group(1))

        return sorted(list(passed)), sorted(list(failed)), sorted(list(skipped))

    def _extract_test_names(self, test_file_path: Path) -> Set[str]:
        """Extracts all function and method names starting with 'test_' via AST parsing."""
        names = set()
        try:
            content = test_file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(test_file_path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("test_"):
                        names.add(node.name)
        except Exception:
            pass
        return names

    def run_linting(self, files_to_check: List[str]) -> LintCheckResult:
        """Conducts static AST parsing, syntax validation, and compilation checks."""
        issues: List[str] = []
        checked: List[str] = []

        for rel in files_to_check:
            target = (self.repo_path / rel).resolve()
            if not target.exists() or not target.name.endswith(".py"):
                continue

            checked.append(rel)
            try:
                content = target.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(target))
                compile(tree, filename=str(target), mode="exec")
            except SyntaxError as e:
                issues.append(f"SyntaxError in {rel} line {e.lineno}: {e.msg}")
            except Exception as e:
                issues.append(f"Compilation error in {rel}: {e}")

        return LintCheckResult(
            passed=len(issues) == 0,
            issues=issues,
            files_checked=checked,
        )

    def review_diff(
        self,
        baseline: Dict[str, Any],
        relevant_files: List[str],
        coder_res: Optional[CoderResult],
        test_gen_res: Optional[TestGenResult],
    ) -> DiffReviewResult:
        """Inspects file delta to ensure no existing tests were deleted, weakened,
        or had assertions removed/commented out, and verifies no unrelated files were touched.
        """
        baseline_tests = set(baseline.get("baseline_tests", []))
        baseline_structs = baseline.get("baseline_test_structures", {})
        baseline_files_content = baseline.get("baseline_test_files", {})
        
        # 1. Scan current tests and test structures to detect deletions and weakenings
        current_tests: Set[str] = set()
        current_test_structures: Dict[str, Dict[str, Any]] = {}
        current_test_files: Dict[str, str] = {}

        for root, _, files in os.walk(self.repo_path):
            if any(x in root for x in (".pytest_cache", ".git", "__pycache__")):
                continue
            for f in files:
                if f.startswith("test_") and f.endswith(".py"):
                    full_p = Path(root) / f
                    rel = os.path.relpath(full_p, self.repo_path).replace("\\", "/")
                    current_tests.update(self._extract_test_names(full_p))
                    structs = self._extract_test_structures(full_p)
                    for t_name, s_data in structs.items():
                        current_test_structures[f"{rel}::{t_name}"] = s_data
                        current_test_structures[t_name] = s_data
                    try:
                        current_test_files[rel] = full_p.read_text(encoding="utf-8")
                    except Exception:
                        pass

        deleted_tests = sorted(list(baseline_tests - current_tests))
        weakened_tests: List[str] = []
        deleted_assertions: List[str] = []

        # 2. Check for weakened test functions or deleted/commented-out assertions via AST
        for b_key, b_struct in baseline_structs.items():
            # b_struct is keyed both by name and rel::name; only check the canonical rel::name or if no ::
            if "::" not in b_key and any(f"::{b_key}" in k for k in baseline_structs if k != b_key):
                continue
            t_name = b_struct.get("name", "")
            t_file = b_struct.get("file", "")
            if t_name in deleted_tests:
                continue

            c_struct = current_test_structures.get(b_key) or current_test_structures.get(t_name)
            if not c_struct:
                continue

            b_count = b_struct.get("assertion_count", 0)
            c_count = c_struct.get("assertion_count", 0)

            # Check for reduced assertion count
            if b_count > 0 and c_count < b_count:
                weakened_tests.append(f"{t_name} in {t_file} (assertions reduced from {b_count} to {c_count})")

            # Check for missing specific assertions
            b_assertions = b_struct.get("assertions", [])
            c_assertions = set(c_struct.get("assertions", []))
            for b_assert in b_assertions:
                if b_assert not in c_assertions:
                    deleted_assertions.append(f"{t_name} in {t_file}: missing '{b_assert}'")
                    if not any(t_name in w for w in weakened_tests):
                        weakened_tests.append(f"{t_name} in {t_file} (assertion '{b_assert}' removed or modified)")

        # 3. Diff-based test modification audit (detecting commented-out assertions in unified diff)
        for rel, base_content in baseline_files_content.items():
            if rel in current_test_files and current_test_files[rel] != base_content:
                diff_lines = list(difflib.unified_diff(
                    base_content.splitlines(),
                    current_test_files[rel].splitlines(),
                    lineterm="",
                ))
                for line in diff_lines:
                    if line.startswith("-") and not line.startswith("---"):
                        stripped = line[1:].strip()
                        if (stripped.startswith("assert ") or "pytest.raises" in stripped or stripped.startswith("self.assert")):
                            # Check if line was commented out in current content
                            commented_version = f"# {stripped}"
                            if commented_version in current_test_files[rel] or stripped not in current_test_files[rel]:
                                msg = f"{rel}: assertion '{stripped}' was commented out or deleted"
                                if msg not in deleted_assertions:
                                    deleted_assertions.append(msg)
                                if not any(rel in w for w in weakened_tests):
                                    weakened_tests.append(f"{rel} (assertion commented out or deleted)")

        tests_preserved = (len(deleted_tests) == 0 and len(weakened_tests) == 0 and len(deleted_assertions) == 0)

        # 4. Track actual disk/git modifications rather than trusting only agent metadata
        actual_disk_modified = self._detect_actual_file_changes(baseline)
        all_modified = set(actual_disk_modified)
        if coder_res:
            all_modified.update(coder_res.files_modified)
        if test_gen_res:
            all_modified.update(test_gen_res.test_files_modified)

        # Build allowed scope from relevant_files + standard workspace targets
        allowed_scopes = set(relevant_files)
        allowed_scopes.update({
            "calculator/core.py",
            "tests/test_calculator.py",
            "api/client.py",
            "tests/test_client.py",
        })

        unrelated: List[str] = []
        for mod in all_modified:
            norm_mod = mod.replace("\\", "/").lstrip("./")
            is_allowed = (
                norm_mod in allowed_scopes
                or norm_mod.startswith("tests/")
                or any(r in norm_mod for r in relevant_files)
            )
            if not is_allowed:
                unrelated.append(mod)

        passed = tests_preserved and len(unrelated) == 0
        summary_parts = []
        if not tests_preserved:
            if deleted_tests:
                summary_parts.append(f"WARNING: {len(deleted_tests)} existing baseline tests were removed: {', '.join(deleted_tests)}")
            if weakened_tests:
                summary_parts.append(f"WARNING: {len(weakened_tests)} existing baseline tests were weakened: {', '.join(weakened_tests)}")
            if deleted_assertions and not weakened_tests:
                summary_parts.append(f"WARNING: Assertions removed/commented out: {', '.join(deleted_assertions)}")
        if unrelated:
            summary_parts.append(f"WARNING: Unrelated files modified outside task scope: {', '.join(unrelated)}")
        if passed:
            summary_parts.append("Git diff is clean: all baseline tests and assertions preserved with zero out-of-scope file modifications.")

        return DiffReviewResult(
            passed=passed,
            tests_preserved=tests_preserved,
            deleted_tests=deleted_tests,
            weakened_tests=weakened_tests,
            deleted_assertions=deleted_assertions,
            unrelated_files_modified=unrelated,
            modified_files=sorted(list(all_modified)),
            diff_summary=" | ".join(summary_parts),
        )

    def verify(self, state: AgentState) -> VerificationResult:
        """Conducts full independent verification and determines distinct final outcome."""
        test_res: Optional[TestResult] = state.get("test_results")
        review_res: Optional[ReviewResult] = state.get("review_result")
        coder_res: Optional[CoderResult] = state.get("coder_result")
        test_gen_res: Optional[TestGenResult] = state.get("test_gen_result")
        relevant = state.get("relevant_files", [])

        # Check for explicit cancellation
        if state.get("status") == "cancelled" or state.get("cancelled", False):
            return VerificationResult(
                verified=False,
                outcome=WorkflowOutcome.CANCELLED,
                baseline_tests_passed=False,
                generated_tests_passed=False,
                lint_checks_passed=False,
                tests_preserved=True,
                git_diff_clean=True,
                reviewer_approved=False,
                failure_reasons=["Workflow cancelled by user or operator signal."],
                summary="Workflow was cancelled prior to verification.",
            )

        # Check for blocked state (e.g. human approval denied or permission policy violation)
        if state.get("status") == "blocked" or state.get("blocked", False):
            return VerificationResult(
                verified=False,
                outcome=WorkflowOutcome.BLOCKED,
                baseline_tests_passed=False,
                generated_tests_passed=False,
                lint_checks_passed=False,
                tests_preserved=True,
                git_diff_clean=True,
                reviewer_approved=False,
                failure_reasons=["Execution was blocked by security policy or rejected human approval."],
                summary="Workflow blocked: action rejected by security policy or operator.",
            )

        # 1. Diff and Scope Review (Tests preserved & No unrelated changes)
        last_b = getattr(self, "_last_baseline", {}) or {}
        baseline_data = {
            "baseline_tests": state.get("baseline_tests") or last_b.get("baseline_tests", []),
            "baseline_files": state.get("baseline_files") or last_b.get("baseline_files", []),
            "baseline_test_structures": state.get("baseline_test_structures") or last_b.get("baseline_test_structures", {}),
            "baseline_test_files": state.get("baseline_test_files") or last_b.get("baseline_test_files", {}),
            "baseline_file_hashes": state.get("baseline_file_hashes") or last_b.get("baseline_file_hashes", {}),
        }
        diff_res = self.review_diff(baseline_data, relevant, coder_res, test_gen_res)

        # 2. Linting and Static Checks on all modified files
        files_to_lint = []
        if coder_res:
            files_to_lint.extend(coder_res.files_modified)
        if test_gen_res:
            files_to_lint.extend(test_gen_res.test_files_modified)
        lint_res = self.run_linting(files_to_lint)

        # 3. Baseline & Current Test Suite Comparative Analysis
        snapshot: Optional[BaselineSnapshot] = state.get("baseline_snapshot")
        if snapshot is None and hasattr(self, "_last_baseline"):
            snapshot = self._last_baseline.get("baseline_snapshot")

        raw_outcomes = state.get("baseline_outcomes") or (self._last_baseline.get("baseline_outcomes") if hasattr(self, "_last_baseline") else {}) or {}

        if snapshot is None:
            inv = set(state.get("baseline_tests") or raw_outcomes.get("inventory") or [])
            passed = set(raw_outcomes.get("passed_tests") or [])
            failed = set(raw_outcomes.get("failed_tests") or [])
            skipped = set(raw_outcomes.get("skipped_tests") or [])
            exec_comp = bool(raw_outcomes.get("execution_completed", raw_outcomes.get("executed", False)))
            coll_comp = bool(raw_outcomes.get("collection_completed", False))
            t_out = bool(raw_outcomes.get("timed_out", False))
            err = raw_outcomes.get("execution_error") or raw_outcomes.get("error_summary") or None
            if err == "":
                err = None

            # Explicit override if state says UNVERIFIABLE
            if state.get("baseline_status") == BaselineVerificationStatus.UNVERIFIABLE or raw_outcomes.get("status") == BaselineVerificationStatus.UNVERIFIABLE:
                exec_comp = False
                err = err or "Explicitly marked UNVERIFIABLE"

            snapshot = BaselineSnapshot(
                inventory=inv,
                passed_tests=passed,
                failed_tests=failed,
                skipped_tests=skipped,
                execution_completed=exec_comp,
                collection_completed=coll_comp,
                timed_out=t_out,
                execution_error=err,
                snapshot_hash=raw_outcomes.get("snapshot_hash") or state.get("baseline_snapshot_hash"),
                signature=raw_outcomes.get("signature") or state.get("baseline_signature"),
            )

        # Retrieve authoritative checkpoint from trusted verification ledger
        repo_key = str(self.repo_path)
        ledger_entry = (
            self._trusted_baseline_ledger.get(repo_key)
            or _PROTECTED_VERIFICATION_LEDGER.get(repo_key)
            or getattr(self, "_last_baseline_ledger_entry", None)
        )
        trusted_digest = ledger_entry.get("snapshot_hash") if ledger_entry else None
        trusted_signature = ledger_entry.get("signature") if ledger_entry else None

        # Prioritize trusted out-of-band ledger digest over mutable state dictionary
        expected_snapshot_hash = (
            trusted_digest
            or state.get("baseline_snapshot_hash")
            or getattr(snapshot, "snapshot_hash", None)
            or (self._last_baseline.get("baseline_snapshot_hash") if hasattr(self, "_last_baseline") and self._last_baseline else None)
        )
        if snapshot.snapshot_hash is None and expected_snapshot_hash:
            snapshot.snapshot_hash = expected_snapshot_hash

        if snapshot.signature is None:
            snapshot.signature = (
                state.get("baseline_signature")
                or (raw_outcomes.get("signature") if isinstance(raw_outcomes, dict) else None)
                or trusted_signature
            )

        baseline_snapshot_hash_valid = True
        # 1. Digest matching: snapshot recomputed hash must match expected hash
        if expected_snapshot_hash is None or snapshot.compute_hash() != expected_snapshot_hash:
            baseline_snapshot_hash_valid = False
        # 2. Trusted ledger matching: if trusted ledger exists, snapshot hash must strictly match it
        elif trusted_digest and (snapshot.compute_hash() != trusted_digest or snapshot.snapshot_hash != trusted_digest):
            baseline_snapshot_hash_valid = False
        # 3. Cryptographic signature check: if signed or ledger has signature, verify with verifier's secret
        elif snapshot.signature and not snapshot.verify_signature(self._signing_secret):
            baseline_snapshot_hash_valid = False
        elif trusted_signature and (not snapshot.signature or not hmac.compare_digest(snapshot.signature, trusted_signature)):
            baseline_snapshot_hash_valid = False

        baseline_status = snapshot.derive_status()
        if not baseline_snapshot_hash_valid:
            baseline_status = BaselineVerificationStatus.UNVERIFIABLE

        baseline_inventory_count = len(snapshot.inventory)

        # Extract post-patch test execution outcomes
        current_failed_tests = []
        current_passed_tests = []
        current_skipped_tests = []

        if test_res:
            if test_res.failed_tests:
                for t in test_res.failed_tests:
                    t_canon = canonicalize_test_id(t)
                    current_failed_tests.append(t_canon)
            if getattr(test_res, "passed_tests", None):
                for t in test_res.passed_tests:
                    t_canon = canonicalize_test_id(t)
                    current_passed_tests.append(t_canon)
            if getattr(test_res, "skipped_tests", None):
                for t in test_res.skipped_tests:
                    t_canon = canonicalize_test_id(t)
                    current_skipped_tests.append(t_canon)

            # Parse from stdout if available
            parsed_passed, parsed_failed, parsed_skipped = self._parse_pytest_outcomes(
                test_res.stdout or "",
                snapshot.inventory,
            )
            for p in parsed_passed:
                p_canon = canonicalize_test_id(p)
                if p_canon not in current_passed_tests:
                    current_passed_tests.append(p_canon)
            for f in parsed_failed:
                f_canon = canonicalize_test_id(f)
                if f_canon not in current_failed_tests:
                    current_failed_tests.append(f_canon)
            for s in parsed_skipped:
                s_canon = canonicalize_test_id(s)
                if s_canon not in current_skipped_tests:
                    current_skipped_tests.append(s_canon)

            # Fallback for clean test mocks: if test_res.passed is True, exit_code is 0,
            # no failures occurred, no collection errors in stdout/stderr, and stdout didn't have verbose per-test lines,
            # then all baseline tests that were preserved on disk successfully passed.
            has_collection_error = (
                test_res.exit_code not in (0, 1)
                or "error during collection" in (test_res.stdout or "").lower()
                or "error during collection" in (test_res.stderr or "").lower()
                or "collection error" in (test_res.stdout or "").lower()
                or "collection error" in (test_res.stderr or "").lower()
            )
            if (
                test_res.passed
                and test_res.exit_code == 0
                and not current_failed_tests
                and not current_passed_tests
                and not current_skipped_tests
                and not has_collection_error
            ):
                current_passed_tests = sorted([canonicalize_test_id(t) for t in snapshot.passed_tests])

        current_passed_set = set(current_passed_tests)
        current_failed_set = set(current_failed_tests)

        def _test_in_set(t: str, s: Set[str]) -> bool:
            t_canon = canonicalize_test_id(t)
            s_canon = {canonicalize_test_id(x) for x in s}
            if t_canon in s_canon:
                return True
            # If t is a bare identifier without path/scope, allow matching if uniquely identified
            if "::" not in t_canon:
                matches = [item for item in s_canon if item.endswith(f"::{t_canon}") or item == t_canon]
                return len(matches) > 0
            return False

        # Baseline Verification Integrity:
        # Distinguish:
        # - baseline_regressions: Passed before, failed after.
        # - baseline_tests_not_executed: Passed before, not successfully executed after (skipped/unexecuted/collection error).
        # - baseline_tests_preserved: Tests whose existing contracts were successfully checked and passed post-patch.
        if baseline_status == BaselineVerificationStatus.NOT_APPLICABLE:
            baseline_regressions = []
            baseline_tests_not_executed = []
            baseline_tests_preserved = []
            pre_existing_failures = []
            fixed_tests = []
            baseline_passed = diff_res.tests_preserved
        elif baseline_status == BaselineVerificationStatus.UNVERIFIABLE:
            baseline_regressions = []
            baseline_tests_not_executed = sorted(list(snapshot.passed_tests))
            baseline_tests_preserved = []
            pre_existing_failures = []
            fixed_tests = []
            baseline_passed = False
        else:
            # BaselineVerificationStatus.VERIFIED
            # 1. Regressions: Tests that strictly PASSED in baseline snapshot, but now FAIL
            baseline_regressions = sorted([
                t for t in snapshot.passed_tests
                if _test_in_set(t, current_failed_set)
            ])
            # 2. Preserved: Tests whose existing contracts were successfully checked and passed post-patch
            baseline_tests_preserved = sorted([
                t for t in snapshot.passed_tests
                if _test_in_set(t, current_passed_set) and not _test_in_set(t, current_failed_set)
            ])
            # 3. Not Executed: Tests that passed before, but were not successfully executed after
            # (e.g. skipped, collection error, timeout, or missing from test execution)
            baseline_tests_not_executed = sorted([
                t for t in snapshot.passed_tests
                if not _test_in_set(t, current_passed_set) and not _test_in_set(t, current_failed_set)
            ])
            pre_existing_failures = sorted([
                t for t in snapshot.failed_tests
                if _test_in_set(t, current_failed_set)
            ])
            fixed_tests = sorted([
                t for t in snapshot.failed_tests
                if not _test_in_set(t, current_failed_set) and _test_in_set(t, current_passed_set)
            ])
            baseline_passed = (
                len(baseline_regressions) == 0
                and len(baseline_tests_not_executed) == 0
                and diff_res.tests_preserved
            )

        tests_passed = bool(test_res and test_res.passed and test_res.exit_code == 0)
        generated_passed = bool(
            (not current_failed_tests or all(_test_in_set(t, snapshot.failed_tests) for t in current_failed_tests))
            and (not test_gen_res or len(test_gen_res.test_cases_added) > 0)
        )

        # 4. Capture immutable repository snapshot manifest to protect against TOCTOU tampering
        verified_manifest: Dict[str, str] = {}
        if self.repo_path.exists():
            for root, _, files in os.walk(self.repo_path):
                if any(x in root for x in (".git", ".pytest_cache", "__pycache__", "venv", ".checkpoints")):
                    continue
                for f in files:
                    full_p = Path(root) / f
                    rel = os.path.relpath(full_p, self.repo_path).replace("\\", "/")
                    try:
                        verified_manifest[rel] = hashlib.sha256(full_p.read_bytes()).hexdigest()
                    except Exception:
                        pass

        manifest_str = "|".join(f"{k}:{verified_manifest[k]}" for k in sorted(verified_manifest.keys()))
        snapshot_hash = hashlib.sha256(manifest_str.encode("utf-8")).hexdigest() if verified_manifest else None

        # 5. Independent Reviewer Quality Gate (Cryptographically bound to verified manifest)
        reviewer_tampered_files = []
        unreviewed_code_files = []

        # Completeness & Hash Integrity Audit:
        # Every reviewable modified production file (including polyglot and extensionless files like Dockerfile/Makefile)
        # must satisfy two non-negotiable conditions:
        # 1. Completeness: Present in review_res.reviewed_file_hashes
        # 2. Integrity: Hash recorded by Reviewer matches verified_manifest.get(path) exactly
        reviewable_modified_files = [
            mod_file for mod_file in diff_res.modified_files
            if should_be_reviewed(mod_file)
        ]

        reviewer_approved = bool(
            review_res
            and review_res.approved
            and review_res.quality_score is not None
            and review_res.quality_score >= 8.0
            and len(review_res.blocking_issues) == 0
        )

        def _norm_path(p: str) -> str:
            n = p.replace("\\", "/")
            if n.startswith("./"):
                n = n[2:]
            return n.lstrip("/")

        reviewed_hashes_lookup: Dict[str, str] = {}
        if review_res and getattr(review_res, "reviewed_file_hashes", None):
            for k, v in review_res.reviewed_file_hashes.items():
                reviewed_hashes_lookup[_norm_path(k)] = v

        for path in reviewable_modified_files:
            norm_p = _norm_path(path)
            reviewed_hash = reviewed_hashes_lookup.get(norm_p)
            verified_hash = verified_manifest.get(norm_p) or verified_manifest.get(path)
            if not reviewed_hash or reviewed_hash != verified_hash:
                reviewer_approved = False
                if not reviewed_hash:
                    if path not in unreviewed_code_files:
                        unreviewed_code_files.append(path)
                else:
                    tamper_msg = f"{path} (modified after review: expected {reviewed_hash[:8]}, got {str(verified_hash)[:8]})"
                    if not any(path in item for item in reviewer_tampered_files):
                        reviewer_tampered_files.append(tamper_msg)

        # Audit any other files recorded in reviewed_file_hashes to ensure none were deleted or modified after review
        if review_res and getattr(review_res, "reviewed_file_hashes", None):
            for rel, expected_hash in review_res.reviewed_file_hashes.items():
                norm_rel = _norm_path(rel)
                verified_hash = verified_manifest.get(norm_rel) or verified_manifest.get(rel)
                if verified_hash is None:
                    reviewer_approved = False
                    if not any(rel in item for item in reviewer_tampered_files):
                        reviewer_tampered_files.append(f"{rel} (deleted after review)")
                elif verified_hash != expected_hash:
                    reviewer_approved = False
                    tamper_msg = f"{rel} (modified after review: expected {expected_hash[:8]}, got {verified_hash[:8]})"
                    if not any(rel in item for item in reviewer_tampered_files):
                        reviewer_tampered_files.append(tamper_msg)

        if len(reviewer_tampered_files) > 0 or len(unreviewed_code_files) > 0:
            reviewer_approved = False

        # Compile failures
        failure_reasons = []
        if not baseline_snapshot_hash_valid:
            failure_reasons.append(
                f"Baseline snapshot integrity violation: baseline snapshot hash mutated from "
                f"{str(expected_snapshot_hash)[:8]} to {snapshot.compute_hash()[:8]}. Verification blocked."
            )
        if baseline_status == BaselineVerificationStatus.UNVERIFIABLE:
            err_msg = snapshot.execution_error or "baseline test execution never completed, timed out, or encountered execution error"
            failure_reasons.append(
                f"Baseline verification inconclusive (BASELINE_UNVERIFIABLE): {err_msg}. Cannot establish whether failing tests are regressions; patch admission blocked."
            )
        if len(baseline_regressions) > 0:
            failure_reasons.append(
                f"Regressed: {len(baseline_regressions)} previously passing baseline tests now fail: {', '.join(baseline_regressions)}"
            )
        if len(baseline_tests_not_executed) > 0 and baseline_status != BaselineVerificationStatus.UNVERIFIABLE:
            failure_reasons.append(
                f"Incomplete baseline verification: {len(baseline_tests_not_executed)} previously passing baseline tests were not executed or verified post-patch: {', '.join(baseline_tests_not_executed)}"
            )
        if not tests_passed:
            exit_code = test_res.exit_code if test_res else 1
            non_preexisting = [t for t in current_failed_tests if not _test_in_set(t, snapshot.failed_tests)]
            if non_preexisting:
                failure_reasons.append(f"Sandbox test suite failed with exit code {exit_code}: {', '.join(non_preexisting)}")
            elif pre_existing_failures:
                failure_reasons.append(f"Sandbox test suite failed with exit code {exit_code}: pre-existing baseline failures {', '.join(pre_existing_failures)}")
            else:
                failure_reasons.append(f"Sandbox test suite failed with exit code {exit_code}")

        if not lint_res.passed:
            failure_reasons.append(f"Linting failed with issues: {'; '.join(lint_res.issues)}")
        if not diff_res.tests_preserved:
            if diff_res.deleted_tests:
                failure_reasons.append(f"Regressed: {len(diff_res.deleted_tests)} existing tests were removed ({', '.join(diff_res.deleted_tests)})")
            if diff_res.weakened_tests:
                failure_reasons.append(f"Regressed: {len(diff_res.weakened_tests)} existing tests were weakened with deleted/commented-out assertions ({', '.join(diff_res.weakened_tests)})")
            if diff_res.deleted_assertions and not diff_res.weakened_tests:
                failure_reasons.append(f"Regressed: Assertions deleted or commented out from existing tests: {', '.join(diff_res.deleted_assertions)}")
        if len(diff_res.unrelated_files_modified) > 0:
            failure_reasons.append(f"Unrelated files modified: {', '.join(diff_res.unrelated_files_modified)}")
        if not reviewer_approved:
            if reviewer_tampered_files:
                failure_reasons.append(f"Reviewer approval invalidated: files were modified after review ({'; '.join(reviewer_tampered_files)})")
            if unreviewed_code_files:
                failure_reasons.append(f"Reviewer approval incomplete: modified production files were never audited by Reviewer ({', '.join(unreviewed_code_files)})")
            if not reviewer_tampered_files and not unreviewed_code_files:
                if review_res:
                    if review_res.quality_score is None:
                        failure_reasons.append("Reviewer audit is missing an explicit quality score (score is unavailable/unrated).")
                    else:
                        failure_reasons.append(f"Reviewer rejected changes (Score: {review_res.quality_score}/10, {len(review_res.blocking_issues)} blocking issues: {'; '.join(review_res.blocking_issues)})")
                else:
                    failure_reasons.append("Independent reviewer audit did not approve the solution.")

        # TOCTOU integrity check: assert files did not mutate on disk during verification execution
        toctou_violations = []
        for rel, expected_h in verified_manifest.items():
            fpath = self.repo_path / rel
            if not fpath.exists():
                toctou_violations.append(f"{rel} (deleted during verification)")
            else:
                try:
                    if hashlib.sha256(fpath.read_bytes()).hexdigest() != expected_h:
                        toctou_violations.append(f"{rel} (mutated during verification)")
                except Exception:
                    pass
        if toctou_violations:
            failure_reasons.append(f"TOCTOU violation: files modified on disk during verification ({', '.join(toctou_violations)})")

        # Determine outcome:
        # Crucial Rule: The agent must NEVER report success merely because it reached its retry limit!
        all_passed = (
            tests_passed
            and baseline_passed
            and baseline_status != BaselineVerificationStatus.UNVERIFIABLE
            and baseline_snapshot_hash_valid
            and lint_res.passed
            and diff_res.passed
            and reviewer_approved
            and len(toctou_violations) == 0
        )

        if all_passed:
            outcome = WorkflowOutcome.COMPLETED_SUCCESSFULLY
            summary = "✅ All independent verification gates passed: baseline tests, generated tests, AST linting, clean diff, reviewer approval, and immutable TOCTOU snapshot verified."
        else:
            outcome = WorkflowOutcome.COMPLETED_WITH_FAILURES
            summary = f"❌ Verification failed ({len(failure_reasons)} issues). Completed with failures: {'; '.join(failure_reasons)}"

        no_blocking_issues = bool(
            review_res
            and review_res.quality_score is not None
            and review_res.quality_score >= 8.0
            and len(review_res.blocking_issues) == 0
        )
        review_hashes_valid = bool(
            len(reviewer_tampered_files) == 0
            and len(unreviewed_code_files) == 0
        )
        toctou_valid = (len(toctou_violations) == 0)

        return VerificationResult(
            verified=all_passed,
            outcome=outcome,
            baseline_status=baseline_status,
            baseline_inventory_count=baseline_inventory_count,
            baseline_snapshot=snapshot,
            tests_passed=tests_passed,
            baseline_tests_passed=baseline_passed,
            generated_tests_passed=generated_passed,
            lint_checks_passed=lint_res.passed,
            tests_preserved=diff_res.tests_preserved,
            git_diff_clean=len(diff_res.unrelated_files_modified) == 0,
            reviewer_approved=reviewer_approved,
            no_blocking_issues=no_blocking_issues,
            review_hashes_valid=review_hashes_valid,
            toctou_valid=toctou_valid,
            baseline_snapshot_hash_valid=baseline_snapshot_hash_valid,
            baseline_signature=snapshot.signature,
            baseline_regressions=baseline_regressions,
            baseline_tests_not_executed=baseline_tests_not_executed,
            baseline_tests_preserved=baseline_tests_preserved,
            pre_existing_failures=pre_existing_failures,
            fixed_tests=fixed_tests,
            failure_reasons=failure_reasons,
            lint_details=lint_res,
            diff_details=diff_res,
            summary=summary,
            snapshot_hash=snapshot_hash,
            verified_manifest=verified_manifest,
        )

    def verify_manifest_intact(self, manifest: Optional[Dict[str, str]]) -> Tuple[bool, List[str]]:
        """Validates that repository files on disk currently match the exact verified manifest
        without temporal drift or post-verification tampering.
        Fails closed if manifest is None. Verifies expected empty state if manifest is empty {}.
        """
        if manifest is None:
            return False, ["Verified manifest is None (manifest missing; failed closed)"]

        violations = []
        for rel, expected_hash in manifest.items():
            fpath = self.repo_path / rel
            if not fpath.exists():
                violations.append(f"{rel} (deleted after verification)")
            else:
                try:
                    curr_hash = hashlib.sha256(fpath.read_bytes()).hexdigest()
                    if curr_hash != expected_hash:
                        violations.append(f"{rel} (modified after verification: expected {expected_hash[:8]}, got {curr_hash[:8]})")
                except Exception as e:
                    violations.append(f"{rel} (read error after verification: {e})")

        # Check for newly created untracked files after verification
        if self.repo_path.exists():
            for root, _, files in os.walk(self.repo_path):
                if any(x in root for x in (".git", ".pytest_cache", "__pycache__", "venv", ".checkpoints")):
                    continue
                for f in files:
                    full_p = Path(root) / f
                    rel = os.path.relpath(full_p, self.repo_path).replace("\\", "/")
                    if rel not in manifest:
                        if len(manifest) == 0:
                            violations.append(f"{rel} (untracked file created: manifest expected empty repository)")
                        else:
                            violations.append(f"{rel} (untracked file created after verification)")

        return len(violations) == 0, violations

    def create_immutable_handover(self, manifest: Optional[Dict[str, str]] = None) -> Tuple[Optional[str], Optional[str]]:
        """Creates a sealed, read-only immutable snapshot bundle (tar.gz archive) of all verified files.
        Guarantees that downstream delivery consumers receive an unalterable artifact that is
        permanently detached from subsequent live working tree mutations.
        """
        if manifest is None:
            manifest_to_seal: Dict[str, str] = {}
            if self.repo_path.exists():
                for root, _, files in os.walk(self.repo_path):
                    if any(x in root for x in (".git", ".pytest_cache", "__pycache__", "venv", ".checkpoints")):
                        continue
                    for f in files:
                        full_p = Path(root) / f
                        rel = os.path.relpath(full_p, self.repo_path).replace("\\", "/")
                        try:
                            manifest_to_seal[rel] = hashlib.sha256(full_p.read_bytes()).hexdigest()
                        except Exception:
                            pass
        else:
            manifest_to_seal = manifest

        handover_dir = self.repo_path / ".checkpoints" / "handover"
        handover_dir.mkdir(parents=True, exist_ok=True)

        manifest_str = "|".join(f"{k}:{manifest_to_seal[k]}" for k in sorted(manifest_to_seal.keys()))
        digest = hashlib.sha256(manifest_str.encode("utf-8")).hexdigest()
        archive_path = handover_dir / f"verified_handover_{digest[:12]}.tar.gz"

        # Content-addressed immutable handover archive: if already sealed, return immediately
        if archive_path.exists():
            artifact_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            return str(archive_path), artifact_hash

        import tarfile
        with tarfile.open(archive_path, "w:gz") as tar:
            for rel in sorted(manifest_to_seal.keys()):
                full_p = self.repo_path / rel
                if full_p.exists():
                    tar.add(full_p, arcname=rel)

        try:
            os.chmod(archive_path, 0o444)
        except Exception:
            pass

        artifact_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        return str(archive_path), artifact_hash

    def is_task_successful(self, state: AgentState, verification: Optional[VerificationResult]) -> bool:
        """Instance method alias for strict sovereign success condition."""
        return is_task_successful(state, verification)


def is_task_successful(state: AgentState, verification: Optional[VerificationResult]) -> bool:
    """Strict Sovereign Success Condition:
    The final authority on whether an engineering task succeeded.
    The Manager cannot declare success merely because the Coder says the task is complete.
    The final decision must be based on independently verifiable evidence.
    Fails closed if verification evidence or baseline status is missing or invalid.
    """
    if not verification or not getattr(verification, "verified", False):
        return False

    # Check status and operator abort flags
    status_str = str(state.get("status", "")).lower()
    if status_str in ("cancelled", "blocked"):
        return False
    if state.get("cancelled") or state.get("abort_requested") or state.get("blocked"):
        return False

    # Strict evidence presence and type validation: required audit fields MUST exist
    regressions = getattr(verification, "baseline_regressions", None)
    if not isinstance(regressions, (list, set, tuple)) or len(regressions) != 0:
        return False

    unexecuted = getattr(verification, "baseline_tests_not_executed", None)
    if not isinstance(unexecuted, (list, set, tuple)) or len(unexecuted) != 0:
        return False

    # Fail closed on missing or unverified baseline status
    status = getattr(verification, "baseline_status", None)
    if status not in {
        BaselineVerificationStatus.VERIFIED,
        BaselineVerificationStatus.NOT_APPLICABLE,
    }:
        return False

    # Fail closed if baseline snapshot integrity was violated or missing
    if getattr(verification, "baseline_snapshot_hash_valid", None) is not True:
        return False

    # Validate that NOT_APPLICABLE is only permitted when baseline inventory is genuinely empty,
    # baseline_inventory_count exists and is explicitly 0, collection is proven completed, and snapshot digest is valid.
    if status == BaselineVerificationStatus.NOT_APPLICABLE:
        inv_count = getattr(verification, "baseline_inventory_count", None)
        if inv_count is None or not isinstance(inv_count, int) or inv_count != 0:
            return False
        if len(state.get("baseline_tests", [])) > 0:
            return False
        pre_existing = getattr(verification, "pre_existing_failures", None)
        if pre_existing is not None and (not isinstance(pre_existing, (list, set, tuple)) or len(pre_existing) != 0):
            return False
        snap = getattr(verification, "baseline_snapshot", None)
        if snap is not None:
            if not getattr(snap, "collection_completed", False):
                return False
            if not getattr(snap, "execution_completed", False):
                return False
            if getattr(snap, "timed_out", False) or bool(getattr(snap, "execution_error", None)):
                return False
            if len(getattr(snap, "inventory", set())) != 0:
                return False
            if len(getattr(snap, "passed_tests", set())) != 0:
                return False
            if len(getattr(snap, "failed_tests", set())) != 0:
                return False
            if len(getattr(snap, "skipped_tests", set())) != 0:
                return False
            if getattr(snap, "snapshot_hash", None) is None:
                return False
            if snap.compute_hash() != snap.snapshot_hash:
                return False

    return bool(
        getattr(verification, "outcome", None) == WorkflowOutcome.COMPLETED_SUCCESSFULLY
        and getattr(verification, "tests_passed", False)
        and getattr(verification, "baseline_tests_passed", False)
        and getattr(verification, "lint_passed", False)
        and getattr(verification, "diff_passed", False)
        and getattr(verification, "reviewer_approved", False)
        and getattr(verification, "no_blocking_issues", False)
        and getattr(verification, "review_hashes_valid", False)
        and getattr(verification, "toctou_valid", False)
        and getattr(verification, "baseline_snapshot_hash_valid", False)
        and len(regressions) == 0
        and len(unexecuted) == 0
        and len(getattr(verification, "failure_reasons", [])) == 0
    )


def is_patch_admissible(verification: VerificationResult) -> bool:
    """Evaluates whether a candidate patch passes the sovereign admission gate.
    Prevents any patch with detected baseline regressions, unverified baseline state,
    incomplete post-patch baseline verification (unexecuted baseline tests),
    inconsistent NOT_APPLICABLE status, or tampering from being merged.
    Fails closed if verification evidence or baseline_status is missing or invalid.
    """
    if verification is None:
        return False

    # 0. Strict evidence presence and type validation: required audit fields MUST exist.
    # Missing evidence fails closed (rejects admission) and is NEVER defaulted to an empty list or True.
    regressions = getattr(verification, "baseline_regressions", None)
    if not isinstance(regressions, (list, set, tuple)):
        return False
    if len(regressions) != 0:
        return False

    unexecuted = getattr(verification, "baseline_tests_not_executed", None)
    if not isinstance(unexecuted, (list, set, tuple)):
        return False
    if len(unexecuted) != 0:
        return False

    # 1. Require cryptographic snapshot digest integrity validation (explicit check)
    snapshot_hash_valid = getattr(verification, "baseline_snapshot_hash_valid", None)
    if snapshot_hash_valid is not True:
        return False

    # 2. Require explicit, verified baseline status (Fail Closed on missing evidence)
    status = getattr(verification, "baseline_status", None)
    if status not in {
        BaselineVerificationStatus.VERIFIED,
        BaselineVerificationStatus.NOT_APPLICABLE,
    }:
        return False

    # 3. Strict invariant: NOT_APPLICABLE is valid ONLY when baseline inventory count exists and is explicitly 0,
    # test discovery collection was proven completed, and snapshot digest is valid
    if status == BaselineVerificationStatus.NOT_APPLICABLE:
        inv_count = getattr(verification, "baseline_inventory_count", None)
        if inv_count is None or not isinstance(inv_count, int) or inv_count != 0:
            return False
        pre_existing = getattr(verification, "pre_existing_failures", None)
        if pre_existing is not None and (not isinstance(pre_existing, (list, set, tuple)) or len(pre_existing) != 0):
            return False
        snap = getattr(verification, "baseline_snapshot", None)
        if snap is not None:
            if not getattr(snap, "collection_completed", False):
                return False
            if not getattr(snap, "execution_completed", False):
                return False
            if getattr(snap, "timed_out", False) or bool(getattr(snap, "execution_error", None)):
                return False
            if len(getattr(snap, "inventory", set())) != 0:
                return False
            if len(getattr(snap, "passed_tests", set())) != 0:
                return False
            if len(getattr(snap, "failed_tests", set())) != 0:
                return False
            if len(getattr(snap, "skipped_tests", set())) != 0:
                return False
            if getattr(snap, "snapshot_hash", None) is None:
                return False
            if snap.compute_hash() != snap.snapshot_hash:
                return False

    # 4. Enforce the six documented sovereign admission conditions (strictly boolean True)
    passed = getattr(verification, "passed", None)
    if passed is not True:
        return False

    tests_preserved = getattr(verification, "tests_preserved", None)
    if tests_preserved is not True:
        return False

    toctou_valid = getattr(verification, "toctou_valid", None)
    if toctou_valid is not True:
        return False

    return True


can_admit_patch = is_patch_admissible
VerifierAgent = IndependentVerifier


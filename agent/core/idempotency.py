"""Atomic File Operations and Persistent Action Idempotency Journal.

Solves the crash window between physical file modification and LangGraph checkpointing:
1. Writes patches to temporary files in the same directory (same filesystem).
2. Validates patch syntax and AST compilation before modifying the target file.
3. Atomically swaps the target file using POSIX os.replace().
4. Durably records the action ID and SHA-256 patch hash in a persistent SQLite journal.
5. On crash recovery, inspects the actual file on disk:
   If disk SHA-256 matches the journal's recorded hash, the operation already
   succeeded before the crash, preventing duplicate side-effects.
6. Scopes keys with iteration counts (e.g. test_gen:{file}:iter{N}) to permit legitimate
   regeneration across subsequent iterations while maintaining intra-iteration idempotency.
"""

import ast
import os
import json
import time
import sqlite3
import hashlib
import logging
import tempfile
import threading
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("agent.idempotency")

DEFAULT_JOURNAL_PATH = Path(".checkpoints") / "idempotency_journal.sqlite"


class IdempotencyPhase(str, Enum):
    """The 4-phase distributed transaction state machine phases."""
    PREPARED = "PREPARED"      # Intent logged with expected & initial hashes before touching disk
    APPLYING = "APPLYING"      # Physical filesystem replacement in progress (Uncertain Commit Window)
    VERIFY = "VERIFY"          # Physical disk inspected and compared against expected outcome
    COMPLETED = "COMPLETED"    # Verified execution result durably committed to ledger
    FAILED = "FAILED"          # Execution halted due to syntax, I/O, or permission error
    IN_PROGRESS = "IN_PROGRESS" # Legacy backward-compatibility alias


def _sync_parent_dir(path: Path) -> None:
    """Flushes parent directory entry to disk to ensure directory rename durability."""
    try:
        parent_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except Exception as e:
        logger.debug(f"Directory fsync not supported or permitted on {path.parent}: {e}")


def generate_idempotency_key(
    action_type: str,
    target: str,
    payload: Any = "",
    thread_id: Optional[str] = None,
    iteration: int = 0,
) -> str:
    """Generates a deterministic, collision-resistant idempotency key for an action."""
    if isinstance(payload, (dict, list)):
        payload_str = json.dumps(payload, sort_keys=True)
    else:
        payload_str = str(payload)
    payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()[:16]
    thread = thread_id or "unscoped"
    clean_target = str(target).replace("\\", "/").strip("/")
    return f"{thread}:{action_type}:{clean_target}:iter{iteration}:{payload_hash}"

class IdempotencyJournal:
    """Persistent SQLite-backed registry tracking completed external actions and content hashes."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        synchronous_mode: str = "NORMAL",
        busy_timeout_ms: int = 30000,
    ):
        self.db_path = Path(db_path or DEFAULT_JOURNAL_PATH).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.synchronous_mode = synchronous_mode.upper()
        self.busy_timeout_ms = busy_timeout_ms
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=float(self.busy_timeout_ms) / 1000.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(f"PRAGMA synchronous={self.synchronous_mode};")
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms};")
        return conn

    def wal_checkpoint(self, mode: str = "PASSIVE") -> Tuple[int, int, int]:
        """Flushes WAL pages to main database file."""
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute(f"PRAGMA wal_checkpoint({mode.upper()});")
                row = cur.fetchone()
                return (row[0], row[1], row[2]) if row else (0, 0, 0)

    def _init_db(self):
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS idempotency_journal (
                        action_id TEXT PRIMARY KEY,
                        file_path TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        iteration INTEGER NOT NULL,
                        applied_at REAL NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS execution_ledger (
                        idempotency_key TEXT PRIMARY KEY,
                        action_type TEXT NOT NULL,
                        target TEXT NOT NULL,
                        payload_hash TEXT NOT NULL,
                        status TEXT NOT NULL,
                        output_json TEXT,
                        started_at REAL NOT NULL,
                        completed_at REAL,
                        expected_hash TEXT,
                        initial_hash TEXT,
                        verified_hash TEXT,
                        phase TEXT DEFAULT 'PREPARED',
                        reconciled_from_crash INTEGER DEFAULT 0
                    );
                """)
                # Migration check for existing databases
                existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(execution_ledger);").fetchall()}
                for col_name, col_def in [
                    ("expected_hash", "TEXT"),
                    ("initial_hash", "TEXT"),
                    ("verified_hash", "TEXT"),
                    ("phase", "TEXT DEFAULT 'PREPARED'"),
                    ("reconciled_from_crash", "INTEGER DEFAULT 0"),
                ]:
                    if col_name not in existing_cols:
                        conn.execute(f"ALTER TABLE execution_ledger ADD COLUMN {col_name} {col_def};")
                conn.commit()

    def record_action(self, action_id: str, file_path: str, content_hash: str, iteration: int = 0) -> None:
        """Atomically logs an applied action and its SHA-256 content hash."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO idempotency_journal (action_id, file_path, content_hash, iteration, applied_at)
                    VALUES (?, ?, ?, ?, strftime('%s', 'now'))
                """, (action_id, file_path, content_hash, iteration))
                conn.commit()

    def get_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves action details if previously recorded."""
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute("""
                    SELECT action_id, file_path, content_hash, iteration, applied_at
                    FROM idempotency_journal WHERE action_id = ?
                """, (action_id,))
                row = cur.fetchone()
                if row:
                    return {
                        "action_id": row[0],
                        "file_path": row[1],
                        "content_hash": row[2],
                        "iteration": row[3],
                        "applied_at": row[4],
                    }
                return None

    def record_prepared(
        self,
        idempotency_key: str,
        action_type: str,
        target: str,
        payload_hash: str,
        expected_hash: Optional[str] = None,
        initial_hash: Optional[str] = None,
    ) -> None:
        """Phase 1: Persist action intent, target, and expected/initial content hashes."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO execution_ledger (
                        idempotency_key, action_type, target, payload_hash, status,
                        output_json, started_at, completed_at, expected_hash, initial_hash,
                        verified_hash, phase, reconciled_from_crash
                    )
                    VALUES (?, ?, ?, ?, 'PREPARED', NULL, strftime('%s', 'now'), NULL, ?, ?, NULL, 'PREPARED', 0)
                    ON CONFLICT(idempotency_key) DO UPDATE SET
                        status = 'PREPARED',
                        phase = 'PREPARED',
                        expected_hash = excluded.expected_hash,
                        initial_hash = excluded.initial_hash,
                        started_at = strftime('%s', 'now')
                """, (idempotency_key, action_type, target, payload_hash, expected_hash, initial_hash))
                conn.commit()

    def record_applying(self, idempotency_key: str) -> None:
        """Phase 2: Transition to APPLYING before physical filesystem mutation begins."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE execution_ledger
                    SET status = 'APPLYING', phase = 'APPLYING'
                    WHERE idempotency_key = ?
                """, (idempotency_key,))
                conn.commit()

    def record_verify(self, idempotency_key: str, verified_hash: str) -> None:
        """Phase 3: Inspect physical disk hash and record verified outcome."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE execution_ledger
                    SET status = 'VERIFY', phase = 'VERIFY', verified_hash = ?
                    WHERE idempotency_key = ?
                """, (verified_hash, idempotency_key))
                conn.commit()

    def record_execution_completion(
        self, idempotency_key: str, output: Any = None, reconciled_from_crash: bool = False
    ) -> None:
        """Phase 4: Atomically marks an execution attempt as COMPLETED with output payload."""
        output_json = json.dumps(output) if output is not None else None
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE execution_ledger
                    SET status = 'COMPLETED', phase = 'COMPLETED', output_json = ?,
                        completed_at = strftime('%s', 'now'),
                        reconciled_from_crash = CASE WHEN ? THEN 1 ELSE reconciled_from_crash END
                    WHERE idempotency_key = ?
                """, (output_json, 1 if reconciled_from_crash else 0, idempotency_key))
                conn.commit()

    def record_execution_start(
        self,
        idempotency_key: str,
        action_type: str,
        target: str,
        payload_hash: str,
        expected_hash: Optional[str] = None,
        initial_hash: Optional[str] = None,
    ) -> None:
        """Records an execution attempt in the persistent ledger (backward-compatible)."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO execution_ledger (
                        idempotency_key, action_type, target, payload_hash, status,
                        output_json, started_at, completed_at, expected_hash, initial_hash,
                        verified_hash, phase, reconciled_from_crash
                    )
                    VALUES (?, ?, ?, ?, 'IN_PROGRESS', NULL, strftime('%s', 'now'), NULL, ?, ?, NULL, 'PREPARED', 0)
                    ON CONFLICT(idempotency_key) DO UPDATE SET
                        status = 'IN_PROGRESS',
                        phase = 'PREPARED',
                        expected_hash = coalesce(?, execution_ledger.expected_hash),
                        initial_hash = coalesce(?, execution_ledger.initial_hash),
                        started_at = strftime('%s', 'now')
                """, (idempotency_key, action_type, target, payload_hash, expected_hash, initial_hash, expected_hash, initial_hash))
                conn.commit()

    def record_execution_failure(
        self, idempotency_key: str, error_message: str
    ) -> None:
        """Marks an execution attempt as FAILED with diagnostic error message."""
        output_json = json.dumps({"error": error_message})
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE execution_ledger
                    SET status = 'FAILED', phase = 'FAILED', output_json = ?, completed_at = strftime('%s', 'now')
                    WHERE idempotency_key = ?
                """, (output_json, idempotency_key))
                conn.commit()

    def get_execution(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Retrieves an execution record from the ledger."""
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute("""
                    SELECT idempotency_key, action_type, target, payload_hash, status,
                           output_json, started_at, completed_at, expected_hash, initial_hash,
                           verified_hash, phase, reconciled_from_crash
                    FROM execution_ledger WHERE idempotency_key = ?
                """, (idempotency_key,))
                row = cur.fetchone()
                if row:
                    output = None
                    if row[5]:
                        try:
                            output = json.loads(row[5])
                        except Exception:
                            output = row[5]
                    return {
                        "idempotency_key": row[0],
                        "action_type": row[1],
                        "target": row[2],
                        "payload_hash": row[3],
                        "status": row[4],
                        "output": output,
                        "started_at": row[6],
                        "completed_at": row[7],
                        "expected_hash": row[8] if len(row) > 8 else None,
                        "initial_hash": row[9] if len(row) > 9 else None,
                        "verified_hash": row[10] if len(row) > 10 else None,
                        "phase": row[11] if len(row) > 11 else row[4],
                        "reconciled_from_crash": bool(row[12]) if len(row) > 12 else False,
                    }
                return None

    def reconcile_with_physical_disk(
        self, idempotency_key: str, repo_path: Path
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Reconciles uncertain commit window (APPLYING/VERIFY/IN_PROGRESS) against physical disk reality.

        Returns:
            (reconciled: bool, reason: str, output: Optional[dict])
            - (True, "ALREADY_COMPLETED", output): Ledger was already COMPLETED.
            - (True, "RECONCILED_FROM_PHYSICAL_DISK", output): Physical write succeeded before crash;
              ledger updated from APPLYING/IN_PROGRESS -> COMPLETED with verified disk hash.
            - (False, "PHYSICAL_DISK_UNMODIFIED", None): Physical write never occurred before crash; safe to retry.
            - (False, "UNRECONCILED_DRIFT", None): File on disk matches neither initial nor expected hash.
            - (False, "NO_RECORD", None): No ledger entry for this key.
        """
        with self._lock:
            rec = self.get_execution(idempotency_key)
            if not rec:
                return False, "NO_RECORD", None

            if rec.get("status") == "COMPLETED":
                return True, "ALREADY_COMPLETED", rec.get("output")

            target_str = rec.get("target", "")
            target_path = (repo_path / target_str).resolve()
            expected_hash = rec.get("expected_hash")
            initial_hash = rec.get("initial_hash")
            action_type = rec.get("action_type")

            # Check physical file on disk
            if target_path.exists() and target_path.is_file():
                try:
                    current_content = target_path.read_text(encoding="utf-8")
                    current_hash = hashlib.sha256(current_content.encode("utf-8")).hexdigest()
                except Exception as e:
                    logger.warning(f"Error reading {target_path} during reconciliation: {e}")
                    return False, f"READ_ERROR: {e}", None

                # Physical write succeeded before the crash! (Reconcile uncertain commit window)
                if expected_hash and current_hash == expected_hash:
                    output = {
                        "action_id": idempotency_key,
                        "file_path": target_str,
                        "content_hash": current_hash,
                        "bytes_written": len(current_content.encode("utf-8")),
                        "status": "already_applied_reconciled",
                        "verified_on_disk": True,
                    }
                    self.record_verify(idempotency_key, current_hash)
                    self.record_execution_completion(idempotency_key, output, reconciled_from_crash=True)
                    self.record_action(idempotency_key, target_str, current_hash, iteration=0)
                    return True, "RECONCILED_FROM_PHYSICAL_DISK", output

                # Physical write never took effect before crash
                if initial_hash and current_hash == initial_hash:
                    return False, "PHYSICAL_DISK_UNMODIFIED", None

                # Content on disk matches neither initial nor expected hash
                return False, "UNRECONCILED_DRIFT", None

            else:
                if action_type == "delete_file" or expected_hash == "DELETED":
                    output = {
                        "action_id": idempotency_key,
                        "file_path": target_str,
                        "status": "deleted_pre_crash_reconciled",
                        "verified_on_disk": True,
                    }
                    self.record_execution_completion(idempotency_key, output, reconciled_from_crash=True)
                    return True, "DELETION_RECONCILED_FROM_PHYSICAL_DISK", output

                if initial_hash is None:
                    return False, "FILE_NOT_YET_CREATED", None

                return False, "TARGET_FILE_MISSING", None

    def is_execution_completed(self, idempotency_key: str) -> bool:
        """Returns True if the idempotency key was previously executed to completion."""
        rec = self.get_execution(idempotency_key)
        return rec is not None and rec.get("status") == "COMPLETED"

    def clear(self) -> None:
        """Clears all journal and ledger entries (used in test fixtures)."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM idempotency_journal")
                conn.execute("DELETE FROM execution_ledger")
                conn.commit()


class AtomicFilePatcher:
    """Coordinates atomic file replacement, validation, and idempotency recovery inspection."""

    def __init__(self, repo_path: str, journal: Optional[IdempotencyJournal] = None):
        self.repo_path = Path(repo_path).resolve()
        if journal:
            self.journal = journal
        else:
            db_path = self.repo_path / ".checkpoints" / "idempotency_journal.sqlite"
            self.journal = IdempotencyJournal(db_path=str(db_path))

    def compute_hash(self, content: str) -> str:
        """Computes SHA-256 hex digest of string content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def is_action_applied(self, action_id: str, target_file: Path) -> bool:
        """Inspects disk file and journal to verify if action was already satisfied before crash."""
        if not target_file.exists():
            return False

        record = self.journal.get_action(action_id)
        if not record:
            return False

        try:
            current_content = target_file.read_text(encoding="utf-8")
            current_hash = self.compute_hash(current_content)
            # If current file on disk matches the journal's recorded hash, the write succeeded!
            return current_hash == record["content_hash"]
        except Exception as e:
            logger.warning(f"Failed to inspect target file {target_file} for idempotency: {e}")
            return False

    def atomic_write(
        self,
        target_file: Path,
        content: str,
        action_id: str,
        iteration: int = 0,
        validate_syntax: bool = True,
    ) -> Dict[str, Any]:
        """Atomically validates, writes to temp file, swaps into place, and journals action
        using the 4-phase distributed idempotency state machine:
        PREPARED -> APPLYING -> VERIFY -> COMPLETED.
        """
        target_file = target_file.resolve()
        target_file.parent.mkdir(parents=True, exist_ok=True)
        rel_path = str(target_file.relative_to(self.repo_path)) if target_file.is_relative_to(self.repo_path) else str(target_file)
        content_hash = self.compute_hash(content)
        initial_hash = self.compute_hash(target_file.read_text("utf-8")) if target_file.exists() else None

        # 0. Check physical disk reconciliation for uncertain commit window recovery
        # If ledger was in PREPARED, APPLYING, VERIFY, or IN_PROGRESS when a crash occurred,
        # inspect physical disk reality rather than blindly retrying or failing!
        rec = self.journal.get_execution(action_id)
        if rec:
            if rec.get("status") == "COMPLETED":
                logger.info(f"Execution idempotency hit: {action_id} already COMPLETED in ledger.")
                return rec.get("output") or {
                    "action_id": action_id,
                    "file_path": rel_path,
                    "content_hash": content_hash,
                    "status": "already_applied",
                }
            reconciled, reason, output = self.journal.reconcile_with_physical_disk(action_id, self.repo_path)
            if reconciled:
                logger.info(f"Uncertain commit window reconciled: {action_id} verified on disk ({reason}).")
                return output or {
                    "action_id": action_id,
                    "file_path": rel_path,
                    "content_hash": content_hash,
                    "status": "reconciled_post_crash",
                }

        # Check direct content match on disk
        if self.is_action_applied(action_id, target_file) or (
            target_file.exists() and self.compute_hash(target_file.read_text("utf-8")) == content_hash
        ):
            logger.info(f"Execution idempotency hit: {action_id} already applied to {rel_path}. Skipping rewrite.")
            res = {
                "action_id": action_id,
                "file_path": rel_path,
                "content_hash": content_hash,
                "bytes_written": len(content.encode("utf-8")),
                "status": "already_applied",
            }
            self.journal.record_action(action_id, rel_path, content_hash, iteration)
            self.journal.record_execution_completion(action_id, res)
            return res

        # ------------------------------------------------------------------
        # Phase 1: PREPARED - Persist action ID, target, and expected/initial hashes
        # ------------------------------------------------------------------
        self.journal.record_prepared(
            action_id,
            action_type="file_write",
            target=rel_path,
            payload_hash=content_hash,
            expected_hash=content_hash,
            initial_hash=initial_hash,
        )

        # Validate patch syntax before touching the target file
        if validate_syntax and target_file.suffix == ".py":
            try:
                tree = ast.parse(content, filename=str(target_file))
                compile(tree, filename=str(target_file), mode="exec")
            except SyntaxError as e:
                err_msg = f"Syntax validation failed for {rel_path} line {e.lineno}: {e.msg}"
                self.journal.record_execution_failure(action_id, err_msg)
                raise ValueError(err_msg) from e

        # ------------------------------------------------------------------
        # Phase 2: APPLYING - Atomic filesystem replacement
        # ------------------------------------------------------------------
        self.journal.record_applying(action_id)
        tmp_fd, tmp_path_str = tempfile.mkstemp(dir=target_file.parent, prefix=".tmp_patch_")
        tmp_path = Path(tmp_path_str)

        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            # Atomic swap via POSIX rename
            os.replace(tmp_path, target_file)
            _sync_parent_dir(target_file)

            # --------------------------------------------------------------
            # Phase 3: VERIFY - Inspect physical disk hash and expected outcome
            # --------------------------------------------------------------
            disk_content = target_file.read_text(encoding="utf-8")
            disk_hash = self.compute_hash(disk_content)
            self.journal.record_verify(action_id, verified_hash=disk_hash)

            if disk_hash != content_hash:
                raise IOError(
                    f"Physical disk verification failed for {rel_path}: "
                    f"expected {content_hash}, found {disk_hash}"
                )

            # --------------------------------------------------------------
            # Phase 4: COMPLETED - Persist verified execution result
            # --------------------------------------------------------------
            self.journal.record_action(action_id, rel_path, content_hash, iteration)
            output = {
                "action_id": action_id,
                "file_path": rel_path,
                "content_hash": content_hash,
                "bytes_written": len(content.encode("utf-8")),
                "status": "atomically_applied",
                "verified": True,
            }
            self.journal.record_execution_completion(action_id, output)
            return output
        except Exception as e:
            self.journal.record_execution_failure(action_id, str(e))
            raise
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

_global_patcher: Optional[AtomicFilePatcher] = None

def get_atomic_patcher(repo_path: str) -> AtomicFilePatcher:
    """Returns singleton or dedicated AtomicFilePatcher for a given repository."""
    global _global_patcher
    if _global_patcher is None or _global_patcher.repo_path != Path(repo_path).resolve():
        _global_patcher = AtomicFilePatcher(repo_path)
    return _global_patcher

"""Dedicated, unbounded append-only diagnostic event ledger.

Decouples durable error recurrence tracking and permanent audit history from
the transient, bounded in-memory LangGraph state window (e.g. error_history capped at 25 items).
"""

import sqlite3
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List


class DiagnosticEventLedger:
    """Thread-safe, durable append-only SQLite ledger for diagnostic events."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = Path(db_path).resolve()
        else:
            self.db_path = Path(".checkpoints/diagnostic_ledger.sqlite").resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=10.0,
        )
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS diagnostic_events (
                        event_id TEXT PRIMARY KEY,
                        thread_id TEXT NOT NULL,
                        iteration INTEGER NOT NULL,
                        step_idx INTEGER NOT NULL,
                        signature TEXT NOT NULL,
                        root_cause TEXT NOT NULL,
                        remediation_plan TEXT,
                        created_at REAL NOT NULL,
                        timestamp TEXT NOT NULL,
                        context TEXT
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_diag_sig ON diagnostic_events(signature);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_diag_thread ON diagnostic_events(thread_id);")

    def record_event(self, event: Dict[str, Any]) -> bool:
        """Atomically appends a diagnostic event to the ledger.
        
        Returns:
            True if newly recorded, False if already present (idempotent duplicate).
        """
        event_id = event.get("event_id")
        if not event_id:
            return False

        with self._lock:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT OR IGNORE INTO diagnostic_events (
                        event_id, thread_id, iteration, step_idx, signature,
                        root_cause, remediation_plan, created_at, timestamp, context
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        event_id,
                        str(event.get("thread_id", "default")),
                        int(event.get("iteration", 1)),
                        int(event.get("step_idx", 0)),
                        str(event.get("signature", "")),
                        str(event.get("root_cause", event.get("signature", ""))),
                        event.get("remediation_plan") or event.get("context"),
                        float(event.get("created_at", 0.0)),
                        str(event.get("timestamp", "")),
                        str(event.get("context", "")),
                    ),
                )
                conn.commit()
                return cur.rowcount > 0

    def get_recurrence_stats(self, signature: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """Queries unbounded historical recurrence facts for a given error signature.
        
        Guarantees accurate recurrence detection even if in-memory state truncated older events.
        """
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.cursor()
                if thread_id:
                    cur.execute(
                        """
                        SELECT COUNT(*), MIN(iteration), MAX(iteration), MIN(created_at), MAX(created_at)
                        FROM diagnostic_events
                        WHERE signature = ? AND thread_id = ?;
                        """,
                        (signature, thread_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT COUNT(*), MIN(iteration), MAX(iteration), MIN(created_at), MAX(created_at)
                        FROM diagnostic_events
                        WHERE signature = ?;
                        """,
                        (signature,),
                    )
                row = cur.fetchone()
                if not row or row[0] == 0:
                    return {
                        "total_occurrences": 0,
                        "first_seen_iteration": None,
                        "latest_iteration": None,
                        "resurfaced": False,
                        "first_seen_at": None,
                        "latest_seen_at": None,
                    }
                count, min_iter, max_iter, min_time, max_time = row
                resurfaced = (count > 1) or (min_iter is not None and max_iter is not None and min_iter < max_iter)
                return {
                    "total_occurrences": count,
                    "first_seen_iteration": min_iter,
                    "latest_iteration": max_iter,
                    "resurfaced": resurfaced,
                    "first_seen_at": min_time,
                    "latest_seen_at": max_time,
                }

    def get_all_events(self, thread_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns the full unbounded audit log of diagnostic events in chronological order."""
        with self._lock:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                if thread_id:
                    cur.execute(
                        "SELECT * FROM diagnostic_events WHERE thread_id = ? ORDER BY created_at ASC, iteration ASC;",
                        (thread_id,),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM diagnostic_events ORDER BY created_at ASC, iteration ASC;"
                    )
                return [dict(row) for row in cur.fetchall()]


_GLOBAL_LEDGER: Optional[DiagnosticEventLedger] = None
_LEDGER_LOCK = threading.Lock()

def get_diagnostic_ledger(db_path: Optional[str] = None) -> DiagnosticEventLedger:
    """Returns singleton instance of the DiagnosticEventLedger."""
    global _GLOBAL_LEDGER
    with _LEDGER_LOCK:
        if _GLOBAL_LEDGER is None or (db_path and str(_GLOBAL_LEDGER.db_path) != str(Path(db_path).resolve())):
            _GLOBAL_LEDGER = DiagnosticEventLedger(db_path=db_path)
        return _GLOBAL_LEDGER


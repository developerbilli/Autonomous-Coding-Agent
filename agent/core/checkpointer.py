"""Persistent SQLite Checkpointer and Crash Recovery Engine for LangGraph."""

import os
import time
import uuid
import sqlite3
import hashlib
import logging
import threading
from pathlib import Path
from typing import (
    Dict,
    Any,
    List,
    Optional,
    Sequence,
    Tuple,
    Iterator,
    AsyncIterator,
)
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
    get_checkpoint_metadata,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

logger = logging.getLogger("agent.checkpointer")

DEFAULT_DB_PATH = Path(".checkpoints") / "coding_agent.sqlite"

class SqliteCheckpointSaver(BaseCheckpointSaver):
    """Production-grade SQLite-backed checkpointer ensuring full crash recovery,
    stable thread identification, and resumable execution across process restarts.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        serde=None,
        synchronous_mode: str = "NORMAL",
        busy_timeout_ms: int = 30000,
    ):
        super().__init__(serde=serde or JsonPlusSerializer())
        self.db_path = Path(db_path or DEFAULT_DB_PATH).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.synchronous_mode = synchronous_mode.upper()
        self.busy_timeout_ms = busy_timeout_ms
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a thread-safe connection to the SQLite database with configured durability."""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=float(self.busy_timeout_ms) / 1000.0)
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms};")
        for attempt in range(5):
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                break
            except sqlite3.OperationalError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (2 ** attempt))
        conn.execute(f"PRAGMA synchronous={self.synchronous_mode};")
        return conn

    def wal_checkpoint(self, mode: str = "PASSIVE") -> Tuple[int, int, int]:
        """Flushes WAL frames into the main database file.
        
        Modes:
        - PASSIVE: Checkpoints as many frames as possible without waiting for readers.
        - FULL: Checkpoints all frames, blocking new readers until completed.
        - RESTART: Checkpoints all frames and restarts the WAL log.
        - TRUNCATE: Checkpoints all frames and truncates the WAL file to zero bytes.
        
        Returns:
            Tuple of (busy_status, log_pages, checkpointed_pages)
        """
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute(f"PRAGMA wal_checkpoint({mode.upper()});")
                row = cur.fetchone()
                return (row[0], row[1], row[2]) if row else (0, 0, 0)

    def _init_db(self):
        """Initializes tables for checkpoints, channel blobs, and pending writes."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS checkpoints (
                        thread_id TEXT NOT NULL,
                        checkpoint_ns TEXT NOT NULL,
                        checkpoint_id TEXT NOT NULL,
                        parent_checkpoint_id TEXT,
                        checkpoint_type TEXT NOT NULL DEFAULT 'msgpack',
                        checkpoint_data BLOB NOT NULL,
                        metadata_type TEXT NOT NULL DEFAULT 'msgpack',
                        metadata_data BLOB NOT NULL,
                        created_at REAL NOT NULL,
                        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                    );
                """)
                # Handle migration if existing table lacks type columns
                cursor = conn.execute("PRAGMA table_info(checkpoints)")
                columns = [r[1] for r in cursor.fetchall()]
                if "checkpoint_type" not in columns:
                    conn.execute("ALTER TABLE checkpoints ADD COLUMN checkpoint_type TEXT NOT NULL DEFAULT 'msgpack'")
                if "metadata_type" not in columns:
                    conn.execute("ALTER TABLE checkpoints ADD COLUMN metadata_type TEXT NOT NULL DEFAULT 'msgpack'")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS checkpoint_blobs (
                        thread_id TEXT NOT NULL,
                        checkpoint_ns TEXT NOT NULL,
                        channel TEXT NOT NULL,
                        version TEXT NOT NULL,
                        type TEXT NOT NULL,
                        blob_data BLOB NOT NULL,
                        PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS checkpoint_writes (
                        thread_id TEXT NOT NULL,
                        checkpoint_ns TEXT NOT NULL,
                        checkpoint_id TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        idx INTEGER NOT NULL,
                        channel TEXT NOT NULL,
                        type TEXT NOT NULL,
                        blob_data BLOB NOT NULL,
                        task_path TEXT,
                        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
                    );
                """)
                conn.commit()

    def put(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> Dict[str, Any]:
        """Atomically persists a graph checkpoint and its channel blobs to SQLite."""
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        parent_id = config["configurable"].get("checkpoint_id")
        checkpoint_id = checkpoint["id"]

        c = checkpoint.copy()
        values: Dict[str, Any] = c.pop("channel_values", {})

        serialized_checkpoint = self.serde.dumps_typed(c)
        meta_dict = get_checkpoint_metadata(config, metadata)
        serialized_metadata = self.serde.dumps_typed(meta_dict)

        with self._lock:
            with self._get_connection() as conn:
                # 1. Insert channel blobs for updated versions
                for channel, version in new_versions.items():
                    val = values.get(channel)
                    dump_type, dump_blob = self.serde.dumps_typed(val)
                    conn.execute("""
                        INSERT OR REPLACE INTO checkpoint_blobs
                        (thread_id, checkpoint_ns, channel, version, type, blob_data)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (thread_id, checkpoint_ns, channel, str(version), dump_type, dump_blob))

                # 2. Insert main checkpoint record
                type_c, blob_c = serialized_checkpoint
                type_m, blob_m = serialized_metadata
                conn.execute("""
                    INSERT OR REPLACE INTO checkpoints
                    (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, checkpoint_type, checkpoint_data, metadata_type, metadata_data, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
                """, (thread_id, checkpoint_ns, checkpoint_id, parent_id, type_c, blob_c, type_m, blob_m))
                conn.commit()

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: Dict[str, Any],
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Atomically persists pending task writes to SQLite."""
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(config["configurable"]["checkpoint_id"])

        with self._lock:
            with self._get_connection() as conn:
                for idx, (channel, val) in enumerate(writes):
                    dump_type, dump_blob = self.serde.dumps_typed(val)
                    conn.execute("""
                        INSERT OR REPLACE INTO checkpoint_writes
                        (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, blob_data, task_path)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, dump_type, dump_blob, task_path))
                conn.commit()

    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        """Retrieves a checkpoint tuple by thread_id and optional checkpoint_id."""
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = config["configurable"].get("checkpoint_id")

        with self._lock:
            with self._get_connection() as conn:
                if checkpoint_id:
                    cursor = conn.execute("""
                        SELECT checkpoint_id, parent_checkpoint_id, checkpoint_type, checkpoint_data, metadata_type, metadata_data
                        FROM checkpoints
                        WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
                    """, (thread_id, checkpoint_ns, checkpoint_id))
                else:
                    cursor = conn.execute("""
                        SELECT checkpoint_id, parent_checkpoint_id, checkpoint_type, checkpoint_data, metadata_type, metadata_data
                        FROM checkpoints
                        WHERE thread_id = ? AND checkpoint_ns = ?
                        ORDER BY rowid DESC LIMIT 1
                    """, (thread_id, checkpoint_ns))

                row = cursor.fetchone()
                if not row:
                    return None

                c_id, parent_id, c_type, c_blob, m_type, m_blob = row

                # Deserialize checkpoint & metadata
                checkpoint_dict = self.serde.loads_typed((c_type, c_blob))
                metadata_dict = self.serde.loads_typed((m_type, m_blob))

                # Reconstruct channel values from blobs table
                channel_values = {}
                for channel, version in checkpoint_dict.get("channel_versions", {}).items():
                    blob_cur = conn.execute("""
                        SELECT type, blob_data FROM checkpoint_blobs
                        WHERE thread_id = ? AND checkpoint_ns = ? AND channel = ? AND version = ?
                    """, (thread_id, checkpoint_ns, channel, str(version)))
                    blob_row = blob_cur.fetchone()
                    if blob_row:
                        b_type, b_data = blob_row
                        if b_type == "empty":
                            channel_values[channel] = None
                        else:
                            channel_values[channel] = self.serde.loads_typed((b_type, b_data))

                checkpoint_dict["channel_values"] = channel_values

                # Retrieve pending writes
                writes_cur = conn.execute("""
                    SELECT task_id, channel, type, blob_data, task_path FROM checkpoint_writes
                    WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
                    ORDER BY idx ASC
                """, (thread_id, checkpoint_ns, c_id))
                pending_writes = [
                    (w_task_id, w_channel, self.serde.loads_typed((w_type, w_blob)))
                    for w_task_id, w_channel, w_type, w_blob, _ in writes_cur.fetchall()
                ]

                parent_config = (
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": parent_id,
                        }
                    }
                    if parent_id
                    else None
                )

                return CheckpointTuple(
                    config={
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": c_id,
                        }
                    },
                    checkpoint=checkpoint_dict,
                    metadata=metadata_dict,
                    parent_config=parent_config,
                    pending_writes=pending_writes,
                )

    def list(
        self,
        config: Optional[Dict[str, Any]],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        """Lists historical checkpoint tuples for a thread."""
        if not config:
            return

        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))

        query = """
            SELECT checkpoint_id FROM checkpoints
            WHERE thread_id = ? AND checkpoint_ns = ?
            ORDER BY rowid DESC
        """
        params: List[Any] = [thread_id, checkpoint_ns]
        if limit:
            query += f" LIMIT {int(limit)}"

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(query, params)
                c_ids = [r[0] for r in cursor.fetchall()]

        for c_id in c_ids:
            tup = self.get_tuple({
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": c_id,
                }
            })
            if tup:
                yield tup

    def delete_thread(self, thread_id: str) -> None:
        """Deletes all checkpoints, blobs, and writes associated with a thread ID."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
                conn.execute("DELETE FROM checkpoint_blobs WHERE thread_id = ?", (thread_id,))
                conn.execute("DELETE FROM checkpoint_writes WHERE thread_id = ?", (thread_id,))
                conn.commit()

    async def aget_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        return self.get_tuple(config)

    async def alist(
        self,
        config: Optional[Dict[str, Any]],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> Dict[str, Any]:
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: Dict[str, Any],
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        return self.put_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        return self.delete_thread(thread_id)

def generate_stable_thread_id(
    repo_path: str,
    task: str,
    fresh: bool = False,
    run_id: Optional[str] = None,
) -> str:
    """Generates a stable, deterministic thread identifier for a given repo and task.

    Incorporates the full canonical repository path and a normalized task hash to prevent
    collisions across distinct repositories with identical directory basenames.

    When fresh=True or run_id is supplied, appends a run suffix to allow intentional
    clean-slate runs without colliding with previous checkpoint histories.
    """
    canonical_path = str(Path(repo_path).resolve())
    repo_name = Path(canonical_path).name
    # Combine the complete canonical filesystem path and task description
    combined_key = f"{canonical_path}::{task.strip().lower()}"
    digest = hashlib.sha256(combined_key.encode("utf-8")).hexdigest()[:12]
    base_id = f"thread_{repo_name}_{digest}"

    if fresh or run_id:
        suffix = run_id or hashlib.sha256(os.urandom(16)).hexdigest()[:8]
        return f"{base_id}_run_{suffix}"
    return base_id


def resolve_thread_id(
    state: Optional[Dict[str, Any]] = None,
    config: Optional[Any] = None,
    fallback_prefix: str = "thread_anon",
) -> str:
    """Resolves the canonical thread_id with strict precedence:
    1. Invocation configuration: config['configurable']['thread_id']
       (Standard LangGraph checkpoint thread identifier).
    2. Workflow state: state['thread_id']
    3. Task-level identifier: state['task_id'] or config['configurable']['task_id']
    4. Deterministic stable thread derived from repository and task:
       generate_stable_thread_id(repo_path, task) if repo_path and task are available.
    5. Isolated thread UUID fallback:
       Never fall back to a static shared 'default' that could cause unrelated
       workflows to collide in the event-ID, journal, or ledger namespaces.
    """
    state_dict = state or {}

    # 1. Check LangGraph RunnableConfig / invocation config
    if config is not None:
        cfg = config.get("configurable", {}) if isinstance(config, dict) else getattr(config, "configurable", {})
        if isinstance(cfg, dict):
            cfg_thread = cfg.get("thread_id")
            if cfg_thread and str(cfg_thread).strip() and str(cfg_thread).strip().lower() != "default":
                return str(cfg_thread).strip()
            cfg_task = cfg.get("task_id")
            if cfg_task and str(cfg_task).strip() and str(cfg_task).strip().lower() != "default":
                return f"thread_{str(cfg_task).strip()}"

    # 2. Check workflow state thread_id
    state_thread = state_dict.get("thread_id")
    if state_thread and str(state_thread).strip() and str(state_thread).strip().lower() != "default":
        return str(state_thread).strip()

    # 3. Check task_id in state
    task_id = state_dict.get("task_id")
    if task_id and str(task_id).strip() and str(task_id).strip().lower() != "default":
        return f"thread_{str(task_id).strip()}"

    # 4. Derive deterministic stable thread ID from repo_path + task
    repo_path = state_dict.get("repo_path")
    task = state_dict.get("task")
    if repo_path and task:
        try:
            return generate_stable_thread_id(str(repo_path), str(task))
        except Exception:
            pass

    # 5. Fallback: Isolated unique UUID (never static 'default')
    return f"{fallback_prefix}_{uuid.uuid4().hex[:12]}"


def resolve_thread_execution_mode(
    checkpointer: SqliteCheckpointSaver,
    thread_id: str,
    explicit_resume: bool = False,
    force_fresh: bool = False,
) -> Tuple[str, str]:
    """Determines whether to resume an existing checkpoint thread or start a fresh run.

    Lifecycle policy:
    1. If force_fresh is True:
       - Appends a new fresh run ID to fork a new thread.
       - Returns: (fresh_thread_id, "fresh")
    2. If explicit_resume is True:
       - Validates that checkpoints exist for thread_id.
       - Returns: (thread_id, "resume")
    3. Default (unspecified / auto-detect):
       - If checkpoints exist for thread_id:
         - Inspects the latest checkpoint's terminal outcome status.
         - If the previous run reached a terminal outcome ('completed_successfully',
           'completed_with_failures', 'aborted', 'blocked'):
           Starts a fresh run with an auto-generated run suffix so a completed task
           does not accidentally resume in a finalized state.
         - If the run was interrupted mid-flight (e.g., status in 'coding', 'testing',
           'debugging', 'reviewing', 'pending'):
           Automatically resumes the thread.
       - If no checkpoints exist for thread_id:
         - Starts a fresh run on thread_id.

    Returns:
        Tuple of (resolved_thread_id, execution_mode) where mode is 'fresh' or 'resume'.
    """
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    latest = checkpointer.get_tuple(config)

    if force_fresh:
        fresh_id = f"{thread_id}_run_{hashlib.sha256(os.urandom(8)).hexdigest()[:8]}"
        return fresh_id, "fresh"

    if explicit_resume:
        return thread_id, "resume"

    if latest is None:
        return thread_id, "fresh"

    # Thread exists: check if terminal outcome was reached
    channel_values = latest.checkpoint.get("channel_values", {})
    status = channel_values.get("status", "")
    terminal_statuses = {"completed_successfully", "completed_with_failures", "aborted", "blocked"}

    if status in terminal_statuses:
        # Previous run already finished; start fresh run for new invocation
        fresh_id = f"{thread_id}_run_{hashlib.sha256(os.urandom(8)).hexdigest()[:8]}"
        return fresh_id, "fresh"

    # Interrupted mid-flight; auto-resume
    return thread_id, "resume"

_default_checkpointer: Optional[SqliteCheckpointSaver] = None

def get_sqlite_checkpointer(db_path: Optional[str] = None) -> SqliteCheckpointSaver:
    """Returns a shared or dedicated SqliteCheckpointSaver instance."""
    global _default_checkpointer
    if db_path:
        return SqliteCheckpointSaver(db_path)
    if _default_checkpointer is None:
        _default_checkpointer = SqliteCheckpointSaver()
    return _default_checkpointer

"""Central state schema and structured agent contracts for the Multi-Agent Coding System."""

import time
from typing import TypedDict, Optional, List, Dict, Any, Literal, Annotated, Callable, Union, Set, Tuple
from pydantic import BaseModel, Field


class ErrorEvent(BaseModel):
    """Structured diagnostic representation distinguishing an error's signature from its occurrences."""
    signature: str                     # Normalized error identity
    agent: str = "system"              # Specialist/node reporting the error
    iteration: int = 1                 # Iteration when observed
    superstep: int = 0                 # Graph superstep or execution round
    sequence_num: int = 0              # Monotonically increasing sequence number within workflow
    created_at: float = Field(default_factory=time.time) # High-precision epoch timestamp
    timestamp: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    occurrence_count: int = 1          # Number of occurrences
    resurfaced: bool = False           # True if reappeared after intervening errors
    first_seen_iteration: int = 1      # First iteration observed
    context: Optional[str] = None      # Stack trace excerpt or failed test name
    event_id: Optional[str] = None     # Unique event ID for idempotency/retry deduplication
    seen_event_ids: List[str] = Field(default_factory=list) # Recorded occurrence identifiers


# Global workflow sequence generator for deterministic logical clocks
_GLOBAL_SEQUENCE_COUNTER: int = 0

def get_next_sequence_num() -> int:
    """Returns a monotonically increasing sequence counter for deterministic total ordering."""
    global _GLOBAL_SEQUENCE_COUNTER
    _GLOBAL_SEQUENCE_COUNTER += 1
    return _GLOBAL_SEQUENCE_COUNTER

def reset_sequence_counter() -> None:
    """Resets the global sequence counter (used in test fixtures)."""
    global _GLOBAL_SEQUENCE_COUNTER
    _GLOBAL_SEQUENCE_COUNTER = 0


# ============================================================
# Explicit LangGraph Channel Reducers & Registry
# ============================================================

def reduce_error_history(
    current: Optional[List[Dict[str, Any]]],
    update: Union[List[Any], Any, None],
) -> List[Dict[str, Any]]:
    """Semantic channel reducer distinguishing error signatures from error occurrences.
    
    Mathematical & Architectural Properties:
    1. Associativity: (A ⊕ B) ⊕ C == A ⊕ (B ⊕ C). Occurrence counts aggregate additively.
    2. Commutativity of Parallel Updates: Parallel node updates (e.g. Node A emitting E2 and Node B emitting E3)
       are ordered deterministically by (first_seen_iteration, superstep, sequence_num, created_at, agent, signature),
       guaranteeing bit-for-bit identical state regardless of parallel branch arrival order.
    3. Idempotence: Replaying identical event_ids (e.g. node retries) preserves occurrence counts.
    4. Identity: Merging None or [] leaves state unchanged.
    5. Bounded Window: Retains up to 25 distinct canonical error events.
    """
    if current is None:
        result_map: Dict[str, Dict[str, Any]] = {}
    else:
        result_map = {}
        for idx, e in enumerate(current):
            if isinstance(e, dict):
                item_dict = dict(e)
                if "first_seen_iteration" not in item_dict:
                    item_dict["first_seen_iteration"] = int(item_dict.get("iteration", 1))
            else:
                item_dict = {
                    "signature": str(e),
                    "agent": "system",
                    "iteration": 1,
                    "superstep": 0,
                    "sequence_num": idx,
                    "created_at": float(idx),
                    "occurrence_count": 1,
                    "resurfaced": False,
                    "timestamp": "",
                    "first_seen_iteration": 1,
                    "context": None,
                    "seen_event_ids": [],
                }
            sig_key = item_dict.get("signature", "")
            if not sig_key:
                continue
            seq = int(item_dict.get("sequence_num", idx))
            t = float(item_dict.get("created_at", float(idx)))
            item_dict.setdefault("min_seq", seq)
            item_dict.setdefault("max_seq", seq)
            item_dict.setdefault("min_time", t)
            item_dict.setdefault("max_time", t)
            result_map[sig_key] = item_dict

    if update is None:
        sorted_res = sorted(result_map.values(), key=_error_sort_key)
        return sorted_res[-25:]

    updates = update if isinstance(update, (list, tuple)) else [update]

    for idx, item in enumerate(updates):
        if item is None:
            continue

        # Normalize incoming delta
        if isinstance(item, str):
            sig = item.strip()
            if not sig:
                continue
            agent = "system"
            iteration = 1
            incoming_first_seen = 1
            superstep = 0
            sequence_num = idx
            created_at = time.time() + (idx * 0.0001)
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            incoming_count = 1
            incoming_resurfaced = False
            context = None
            event_id = None
            incoming_seen_ids = []
        elif isinstance(item, dict):
            sig = str(item.get("signature", item.get("error", ""))).strip()
            if not sig:
                continue
            agent = str(item.get("agent", "system"))
            iteration = int(item.get("iteration", 1))
            incoming_first_seen = int(item.get("first_seen_iteration", iteration))
            superstep = int(item.get("superstep", 0))
            sequence_num = int(item.get("sequence_num", idx))
            created_at = float(item.get("created_at", time.time() + (idx * 0.0001)))
            timestamp = str(item.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
            incoming_count = int(item.get("occurrence_count", 1))
            incoming_resurfaced = bool(item.get("resurfaced", False))
            context = item.get("context")
            event_id = item.get("event_id")
            incoming_seen_ids = list(item.get("seen_event_ids", []))
            if event_id and event_id not in incoming_seen_ids:
                incoming_seen_ids.append(event_id)
        elif hasattr(item, "signature"):
            sig = getattr(item, "signature", "").strip()
            if not sig:
                continue
            agent = str(getattr(item, "agent", "system"))
            iteration = int(getattr(item, "iteration", 1))
            incoming_first_seen = int(getattr(item, "first_seen_iteration", iteration))
            superstep = int(getattr(item, "superstep", 0))
            sequence_num = int(getattr(item, "sequence_num", idx))
            created_at = float(getattr(item, "created_at", time.time() + (idx * 0.0001)))
            timestamp = str(getattr(item, "timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
            incoming_count = int(getattr(item, "occurrence_count", 1))
            incoming_resurfaced = bool(getattr(item, "resurfaced", False))
            context = getattr(item, "context", None)
            event_id = getattr(item, "event_id", None)
            incoming_seen_ids = list(getattr(item, "seen_event_ids", []))
            if event_id and event_id not in incoming_seen_ids:
                incoming_seen_ids.append(event_id)
        else:
            sig = str(item).strip()
            if not sig:
                continue
            agent = "system"
            iteration = 1
            incoming_first_seen = 1
            superstep = 0
            sequence_num = idx
            created_at = time.time() + (idx * 0.0001)
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            incoming_count = 1
            incoming_resurfaced = False
            context = None
            event_id = None
            incoming_seen_ids = []

        if sig in result_map:
            entry = result_map[sig]
            seen_ids = set(entry.get("seen_event_ids", []))
            # Idempotence: replaying identical event_id does not increment occurrence_count
            is_replay = bool(event_id and event_id in seen_ids)

            # Commutative event_id replay metadata reconciliation:
            # Earliest observation time wins so arrival order does NOT make duplicate-event metadata first-arrival-wins
            if is_replay:
                if created_at < float(entry.get("created_at", float("inf"))):
                    entry["created_at"] = created_at
                    entry["timestamp"] = timestamp
                entry["min_time"] = min(float(entry.get("min_time", created_at)), created_at)
                entry["max_time"] = max(float(entry.get("max_time", created_at)), created_at)
                entry["min_seq"] = min(int(entry.get("min_seq", sequence_num)), sequence_num)
                entry["max_seq"] = max(int(entry.get("max_seq", sequence_num)), sequence_num)
                continue

            if event_id:
                seen_ids.add(event_id)
            for s_id in incoming_seen_ids:
                seen_ids.add(s_id)
            entry["seen_event_ids"] = sorted(seen_ids)

            # Associative addition of occurrence counts
            entry["occurrence_count"] = entry.get("occurrence_count", 1) + incoming_count

            # Commutative iteration semi-lattices (independent of merge arrival order)
            entry["first_seen_iteration"] = min(
                int(entry.get("first_seen_iteration", entry.get("iteration", 1))),
                incoming_first_seen,
            )
            entry["iteration"] = max(int(entry.get("iteration", 1)), iteration)

            if incoming_resurfaced:
                entry["resurfaced"] = True

            entry["superstep"] = max(entry.get("superstep", 0), superstep)
            entry["sequence_num"] = max(entry.get("sequence_num", 0), sequence_num)
            entry["min_seq"] = min(int(entry.get("min_seq", sequence_num)), sequence_num)
            entry["max_seq"] = max(int(entry.get("max_seq", sequence_num)), sequence_num)
            entry["min_time"] = min(float(entry.get("min_time", created_at)), created_at)
            entry["max_time"] = max(float(entry.get("max_time", created_at)), created_at)

            # Commutative metadata election: deterministic total ordering decides winning metadata
            curr_tuple = (
                entry.get("created_at", 0.0),
                entry.get("superstep", 0),
                entry.get("sequence_num", 0),
                str(entry.get("agent", "")),
            )
            new_tuple = (created_at, superstep, sequence_num, agent)
            if new_tuple >= curr_tuple:
                entry["created_at"] = created_at
                entry["timestamp"] = timestamp
                if agent != "system":
                    entry["agent"] = agent
                if context:
                    entry["context"] = context
        else:
            seen_ids = set(incoming_seen_ids)
            if event_id:
                seen_ids.add(event_id)
            new_entry = {
                "signature": sig,
                "agent": agent,
                "iteration": iteration,
                "superstep": superstep,
                "sequence_num": sequence_num,
                "created_at": created_at,
                "timestamp": timestamp,
                "occurrence_count": incoming_count,
                "resurfaced": incoming_resurfaced or (incoming_first_seen < iteration),
                "first_seen_iteration": incoming_first_seen,
                "context": context,
                "seen_event_ids": sorted(seen_ids),
                "min_seq": sequence_num,
                "max_seq": sequence_num,
                "min_time": created_at,
                "max_time": created_at,
            }
            result_map[sig] = new_entry

    # Permutation-invariant intervening error & resurfacing reconciliation
    for sig, entry in result_map.items():
        if entry.get("resurfaced"):
            continue
        if int(entry.get("first_seen_iteration", 1)) < int(entry.get("iteration", 1)):
            entry["resurfaced"] = True
            continue
        min_s = int(entry.get("min_seq", entry.get("sequence_num", 0)))
        max_s = int(entry.get("max_seq", entry.get("sequence_num", 0)))
        min_t = float(entry.get("min_time", entry.get("created_at", 0.0)))
        max_t = float(entry.get("max_time", entry.get("created_at", 0.0)))
        if min_s < max_s or min_t < max_t:
            for other_sig, other in result_map.items():
                if other_sig == sig:
                    continue
                o_min_s = int(other.get("min_seq", other.get("sequence_num", 0)))
                o_max_s = int(other.get("max_seq", other.get("sequence_num", 0)))
                o_min_t = float(other.get("min_time", other.get("created_at", 0.0)))
                o_max_t = float(other.get("max_time", other.get("created_at", 0.0)))
                if (min_s < o_min_s < max_s) or (min_s < o_max_s < max_s) or \
                   (min_t < o_min_t < max_t) or (min_t < o_max_t < max_t):
                    entry["resurfaced"] = True
                    break

    sorted_res = sorted(result_map.values(), key=_error_sort_key)
    return sorted_res[-25:]


def _error_sort_key(e: Dict[str, Any]) -> Tuple[int, int, int, float, str, str]:
    """Total ordering sort key ensuring commutative deterministic merging."""
    return (
        int(e.get("first_seen_iteration", 1)),
        int(e.get("superstep", 0)),
        int(e.get("sequence_num", 0)),
        float(e.get("created_at", 0.0)),
        str(e.get("agent", "system")),
        str(e.get("signature", "")),
    )


def reduce_completed_actions(
    current: Optional[List[str]],
    update: Union[List[str], str, None],
) -> List[str]:
    """Semantic channel reducer for idempotency action keys.
    
    Mathematical & Architectural Properties:
    1. Associativity: (A ⊕ B) ⊕ C == A ⊕ (B ⊕ C).
    2. Commutativity: A ⊕ B == B ⊕ A.
    3. Idempotence: A ⊕ A == A.
    4. Identity: A ⊕ None == A.
    Canonical state is a strictly unique, canonically ordered set.
    """
    if current is None:
        result_set = set()
    else:
        result_set = set(current)

    if update is not None:
        updates = [update] if isinstance(update, str) else list(update)
        for act in updates:
            if act:
                result_set.add(str(act))

    return sorted(result_set)


def _events_match(e1: Any, e2: Any) -> bool:
    """Semantic comparison of two history events, robust against ephemeral timestamp fluctuations in legacy events."""
    if e1 == e2:
        return True
    if not isinstance(e1, dict) or not isinstance(e2, dict):
        return False
    # If both have event_id, match strictly on event_id
    id1, id2 = e1.get("event_id"), e2.get("event_id")
    if id1 and id2:
        return id1 == id2
    if (id1 and not id2) or (id2 and not id1):
        return False
    # For legacy/unkeyed events, compare all semantic content excluding ephemeral timestamps
    VOLATILE_KEYS = {"created_at", "timestamp"}
    d1 = {k: v for k, v in e1.items() if k not in VOLATILE_KEYS}
    d2 = {k: v for k, v in e2.items() if k not in VOLATILE_KEYS}
    return bool(d1) and d1 == d2


def reduce_agent_history(
    current: Optional[List[Dict[str, Any]]],
    update: Union[List[Dict[str, Any]], Dict[str, Any], None],
) -> List[Dict[str, Any]]:
    """Semantic channel reducer for agent execution telemetry events.
    
    Mathematical & Architectural Properties:
    1. Deterministic Total Ordering: Sorts sequenced events by (superstep, sequence_num, created_at, agent, action).
    2. Commutativity for Parallel Nodes: If parallel branches emit events concurrently,
       their explicit sequence numbers and superstep coordinates ensure the audit trail
       has a single, deterministic chronological sequence regardless of thread interleaving.
    3. Associativity: (A ⊕ B) ⊕ C == A ⊕ (B ⊕ C).
    4. Idempotence: Identical consecutive events without sequence increments are suppressed.
    """
    if current is None:
        result: List[Dict[str, Any]] = []
    else:
        result = [dict(e) for e in current]

    if update is None:
        return result

    updates = [update] if isinstance(update, dict) else list(update)

    # Prefix check: if caller passed full accumulated history instead of an incremental delta,
    # strip the already-committed prefix (using semantic event matching for legacy/unkeyed events).
    if len(updates) >= len(result) and result and all(_events_match(u, r) for u, r in zip(updates[:len(result)], result)):
        updates = updates[len(result):]

    # Fast set lookup for recorded event identifiers across entire history
    existing_ids = {e.get("event_id") for e in result if isinstance(e, dict) and e.get("event_id")}

    has_sequenced_items = False
    for ev in updates:
        if not isinstance(ev, dict):
            continue
        ev_dict = dict(ev)
        if "sequence_num" in ev_dict or "superstep" in ev_dict or "created_at" in ev_dict:
            has_sequenced_items = True

        # Event-level idempotency: deduplicate against all past events in the ledger
        ev_id = ev_dict.get("event_id")
        if ev_id and ev_id in existing_ids:
            continue

        # Suppress identical consecutive events if unsequenced
        if not result or result[-1] != ev_dict:
            if ev_id:
                existing_ids.add(ev_id)
            result.append(ev_dict)

    # If events contain explicit sequence coordinates, sort deterministically (stable sort)
    if has_sequenced_items or any("sequence_num" in e or "superstep" in e for e in result):
        result.sort(key=lambda e: (
            int(e.get("superstep", e.get("iteration", 0))),
            int(e.get("sequence_num", 0)),
            float(e.get("created_at", e.get("timestamp_epoch", 0.0) or 0.0)),
            str(e.get("agent", "")),
            str(e.get("action", "")),
        ))

    return result


# Explicit Reducer Registry: zero reflection fragility, 100% deterministic
STATE_REDUCERS: Dict[str, Callable[[Any, Any], Any]] = {
    "error_history": reduce_error_history,
    "completed_actions": reduce_completed_actions,
    "agent_history": reduce_agent_history,
}


def apply_state_update(state: Dict[str, Any], update: Dict[str, Any]) -> None:
    """Applies node outputs to state dictionary honoring explicit channel reducers."""
    for key, val in update.items():
        if key in STATE_REDUCERS:
            state[key] = STATE_REDUCERS[key](state.get(key), val)
        else:
            state[key] = val

class SymbolInfo(BaseModel):
    name: str
    kind: str  # "function", "class", "method", "variable", "interface", "config"
    file_path: str
    start_line: int
    end_line: int
    docstring: Optional[str] = None
    arguments: List[str] = Field(default_factory=list)
    calls: List[str] = Field(default_factory=list)
    callers: List[str] = Field(default_factory=list)
    imports: List[str] = Field(default_factory=list)
    language: str = "python"

class ImportInfo(BaseModel):
    module: str
    names: List[str] = Field(default_factory=list)
    alias: Optional[str] = None
    file_path: str
    lineno: int

class TestResult(BaseModel):
    __test__ = False
    passed: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    failed_tests: List[str] = Field(default_factory=list)
    passed_tests: List[str] = Field(default_factory=list)
    skipped_tests: List[str] = Field(default_factory=list)
    error_summary: Optional[str] = None
    isolation_level: Optional[str] = None
    security_metadata: Dict[str, Any] = Field(default_factory=dict)
    output_truncated: bool = False

# ============================================================
# Structured Agent Outputs Returned to the Manager
# ============================================================

class ManagerSubTask(BaseModel):
    id: str
    description: str
    assigned_agent: Literal["coder", "test_generator", "reviewer", "debugger"]
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    result_summary: Optional[str] = None

class ManagerPlan(BaseModel):
    """Structured plan synthesized by ManagerPlannerAgent."""
    goal: str
    strategy: str
    subtasks: List[ManagerSubTask] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)

class ManagerDecision(BaseModel):
    """Dynamic routing decision made by ManagerPlannerAgent based on agent outputs."""
    next_action: Literal[
        "delegate_coder",
        "delegate_test_gen",
        "run_sandbox",
        "delegate_debug",
        "delegate_review",
        "finalize",
        "abort"
    ]
    target_agent: str
    reasoning: str
    directives: Dict[str, Any] = Field(default_factory=dict)

class CoderResult(BaseModel):
    """Structured result returned by CoderAgent to Manager."""
    agent_name: str = "CoderAgent"
    files_modified: List[str] = Field(default_factory=list)
    patches: Dict[str, str] = Field(default_factory=dict)
    methods_implemented: List[str] = Field(default_factory=list)
    rationale: str
    contracts: List[str] = Field(default_factory=list)

class TestGenResult(BaseModel):
    """Structured result returned by TestGeneratorAgent to Manager."""
    __test__ = False
    agent_name: str = "TestGeneratorAgent"
    test_files_modified: List[str] = Field(default_factory=list)
    test_cases_added: List[str] = Field(default_factory=list)
    edge_cases_tested: List[str] = Field(default_factory=list)
    test_code_summary: str

class ReviewResult(BaseModel):
    """Structured quality audit returned by ReviewerAgent to Manager."""
    agent_name: str = "ReviewerAgent"
    approved: bool
    quality_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=10.0,
        description="Explicit numerical quality score from 0.0 to 10.0. None indicates unrated or unavailable.",
    )
    blocking_issues: List[str] = Field(default_factory=list)
    non_blocking_feedback: List[str] = Field(default_factory=list)
    security_checks: List[str] = Field(default_factory=list)
    review_summary: str = ""
    reviewed_files: List[str] = Field(default_factory=list)
    reviewed_file_hashes: Dict[str, str] = Field(
        default_factory=dict,
        description="Cryptographic SHA-256 hashes of the files at the exact time of Reviewer audit.",
    )

class DebugResult(BaseModel):
    """Structured root-cause diagnosis returned by DebuggerAgent to Manager."""
    agent_name: str = "DebuggerAgent"
    root_cause: str
    failing_tests: List[str] = Field(default_factory=list)
    suspect_symbols: List[str] = Field(default_factory=list)
    remediation_plan: str
    target_fix_agent: Literal["coder", "test_generator"] = "coder"

# ============================================================
# Central LangGraph AgentState
# ============================================================

class AgentState(TypedDict, total=False):
    """Shared state dictionary tracked and updated across all LangGraph nodes."""
    task: str
    repo_path: str
    symbol_index: Dict[str, SymbolInfo]
    relevant_files: List[str]
    retrieved_code: Dict[str, str]
    plan: List[str]
    active_step: int
    
    # Structured Agent Artifacts
    manager_plan: Optional[ManagerPlan]
    manager_decision: Optional[ManagerDecision]
    coder_result: Optional[CoderResult]
    test_gen_result: Optional[TestGenResult]
    review_result: Optional[ReviewResult]
    debug_result: Optional[DebugResult]
    
    # Execution & Lifecycle
    proposed_patches: Dict[str, str]
    test_results: Optional[TestResult]
    iteration_count: int
    max_iterations: int
    error_history: Annotated[List[Dict[str, Any]], reduce_error_history]
    agent_history: Annotated[List[Dict[str, Any]], reduce_agent_history]
    final_report: Optional[str]
    status: str
    demo_mode: Optional[bool]
    architecture_mode: Optional[str]  # "multi_agent" vs "single_agent_baseline"
    thread_id: Optional[str]
    completed_actions: Annotated[List[str], reduce_completed_actions]  # Prevents repeating completed external side-effects on resume
    resumed_from_checkpoint: Optional[bool]
    permission_policy: Optional[Any]
    approval_gate: Optional[Any]
    security_audit_log: Optional[List[Dict[str, Any]]]
    baseline_tests: Optional[List[str]]
    baseline_files: Optional[List[str]]
    baseline_test_structures: Optional[Dict[str, Any]]
    baseline_test_files: Optional[Dict[str, str]]
    baseline_file_hashes: Optional[Dict[str, str]]
    baseline_outcomes: Optional[Dict[str, Any]]
    verification_result: Optional[Any]
    workflow_outcome: Optional[str]
    task_succeeded: Optional[bool]
    blocked: Optional[bool]
    cancelled: Optional[bool]
    snapshot_hash: Optional[str]
    verified_manifest: Optional[Dict[str, str]]
    handover_artifact: Optional[str]
    handover_hash: Optional[str]
    
    # Repository Intelligence & Long-Term Memory Context
    dependency_graph: Optional[Dict[str, Any]]
    git_context: Optional[Dict[str, Any]]
    test_mappings: Optional[Dict[str, Any]]
    config_files: Optional[Dict[str, Any]]
    recalled_memories: Optional[Dict[str, Any]]
    applied_pattern_ids: Optional[List[str]]


def validate_reducer_registry_synchronization() -> None:
    """Verifies that LangGraph Annotated channel reducers and STATE_REDUCERS are 1:1 synchronized.
    
    Guarantees that:
    1. Every channel on AgentState with an Annotated[T, reducer] has a corresponding entry in STATE_REDUCERS.
    2. Every channel in STATE_REDUCERS is declared with Annotated[T, reducer] on AgentState.
    3. The reducer callable in both registries is identical.
    
    Raises:
        AssertionError: If any discrepancy exists between the two execution paths.
    """
    import typing
    hints = typing.get_type_hints(AgentState, include_extras=True)
    annotated_channels = {}
    for key, hint in hints.items():
        if typing.get_origin(hint) is typing.Annotated:
            args = typing.get_args(hint)
            if len(args) > 1 and callable(args[1]):
                annotated_channels[key] = args[1]

    # Check 1: All Annotated reducers present in STATE_REDUCERS
    missing_in_registry = set(annotated_channels.keys()) - set(STATE_REDUCERS.keys())
    if missing_in_registry:
        raise AssertionError(
            f"Reducer synchronization error: channels {missing_in_registry} are declared with Annotated "
            f"reducers in AgentState, but missing from STATE_REDUCERS registry!"
        )

    # Check 2: All STATE_REDUCERS declared in Annotated
    missing_in_annotated = set(STATE_REDUCERS.keys()) - set(annotated_channels.keys())
    if missing_in_annotated:
        raise AssertionError(
            f"Reducer synchronization error: channels {missing_in_annotated} exist in STATE_REDUCERS, "
            f"but are not annotated with reducers on AgentState!"
        )

    # Check 3: Identity check
    for key, fn in annotated_channels.items():
        reg_fn = STATE_REDUCERS[key]
        if fn != reg_fn:
            raise AssertionError(
                f"Reducer mismatch for channel '{key}': Annotated has {fn}, but STATE_REDUCERS has {reg_fn}"
            )

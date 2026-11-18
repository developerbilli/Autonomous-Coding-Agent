"""LangGraph Multi-Agent Orchestration Workflow.

Features 5 distinct, specialized agents:
1. Manager / Planner Agent (ManagerPlannerAgent)
2. Coder Agent (CoderAgent)
3. Test Generation Agent (TestGeneratorAgent)
4. Reviewer Agent (ReviewerAgent)
5. Debugger Agent (DebuggerAgent)

All agents share a unified typed AgentState and return structured Pydantic results to the Manager.
"""

import time
import hashlib
import logging
from typing import Dict, Any, Literal, Optional, List
try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore
from agent.core.state import (
    AgentState,
    TestResult,
    ManagerPlan,
    ManagerDecision,
    CoderResult,
    TestGenResult,
    ReviewResult,
    DebugResult,
)
from agent.explorer.ast_indexer import ASTIndexer
from agent.execution.sandbox import ExecutionSandbox
from agent.core.checkpointer import get_sqlite_checkpointer, resolve_thread_id
from agent.agents.manager import ManagerPlannerAgent
from agent.agents.coder import CoderAgent
from agent.agents.test_generator import TestGeneratorAgent
from agent.agents.reviewer import ReviewerAgent
from agent.agents.debugger import DebuggerAgent
from agent.memory.engine import get_memory_engine
from agent.core.diagnostic_ledger import get_diagnostic_ledger
from agent.verification.verifier import (
    IndependentVerifier,
    WorkflowOutcome,
    VerificationResult,
    is_task_successful,
)

# ============================================================
# Specialized Multi-Agent LangGraph Nodes
# ============================================================

def explore_repo_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Phase 1: Explores repository with rich AST, dependency, git, and test understanding."""
    if state.get("cancelled") or state.get("abort_requested"):
        return {"cancelled": True, "status": "cancelled"}

    repo_path = state["repo_path"]
    task = state["task"]
    thread_id = resolve_thread_id(state, config)
    
    indexer = ASTIndexer(repo_path)
    symbols = indexer.index_repository()
    rich_context = indexer.retrieve_rich_context(task)

    # Snapshot baseline tests, inventory, and pre-implementation test outcomes
    verifier = IndependentVerifier(repo_path, trust_level=state.get("repo_trust_level"))
    baseline_data = verifier.capture_baseline(run_tests=True)

    return {
        "thread_id": thread_id,
        "symbol_index": symbols,
        "relevant_files": rich_context.get("relevant_files", []),
        "retrieved_code": rich_context.get("retrieved_code", {}),
        "dependency_graph": indexer.dependency_graph.to_dict(),
        "git_context": rich_context.get("git_context", {}),
        "test_mappings": indexer.test_mapper.to_dict(),
        "config_files": rich_context.get("config_files", {}),
        "baseline_tests": baseline_data.get("baseline_tests", []),
        "baseline_files": baseline_data.get("baseline_files", []),
        "baseline_test_structures": baseline_data.get("baseline_test_structures", {}),
        "baseline_test_files": baseline_data.get("baseline_test_files", {}),
        "baseline_file_hashes": baseline_data.get("baseline_file_hashes", {}),
        "baseline_outcomes": baseline_data.get("baseline_outcomes", {}),
        "baseline_snapshot": baseline_data.get("baseline_snapshot"),
        "status": "planning",
    }


def manager_planner_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Agent 1: Manager & Planner Agent decomposes task and delegates to specialists."""
    if state.get("cancelled") or state.get("abort_requested"):
        return {"cancelled": True, "status": "cancelled"}

    task = state["task"]
    relevant_files = state.get("relevant_files", [])
    raw_symbols = state.get("symbol_index", {})
    if isinstance(raw_symbols, dict):
        symbol_names = list(raw_symbols.keys())
    else:
        symbol_names = [getattr(s, "name", str(s)) for s in raw_symbols]

    manager = ManagerPlannerAgent()
    recalled = get_memory_engine().recall_context_for_task(task, state.get("repo_path", ""))
    plan: ManagerPlan = manager.create_plan(
        task,
        relevant_files,
        symbol_names,
        guidance=recalled.get("guidance_summary"),
    )

    current_iter = state.get("iteration_count", 0)
    thread_id = resolve_thread_id(state, config)
    step_idx = len(state.get("agent_history", []))
    now_epoch = time.time()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch))
    event_id = f"hist:manager:plan:{thread_id}:iter{current_iter}:step{step_idx}"

    history_entry = {
        "event_id": event_id,
        "agent": "ManagerPlannerAgent",
        "action": "create_plan",
        "summary": plan.strategy,
        "subtasks_count": len(plan.subtasks),
        "recalled_memories_count": recalled.get("total_recalled", 0),
        "iteration": current_iter,
        "created_at": now_epoch,
        "timestamp": now_iso,
    }

    applied_pattern_ids = [
        p["pattern_id"] for p in recalled.get("recalled_patterns", [])
        if isinstance(p, dict) and p.get("pattern_id")
    ]

    return {
        "manager_plan": plan,
        "plan": [st.description for st in plan.subtasks],
        "active_step": 0,
        "thread_id": thread_id,
        "recalled_memories": recalled,
        "applied_pattern_ids": applied_pattern_ids,
        "agent_history": [history_entry],
        "status": "coding",
    }

def coder_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Agent 2: Coder Agent implements requirements and applies fixes."""
    if state.get("cancelled") or state.get("abort_requested"):
        return {"cancelled": True, "status": "cancelled"}

    repo_path = state["repo_path"]
    policy = state.get("permission_policy")
    gate = state.get("approval_gate")
    coder = CoderAgent(repo_path, policy=policy, approval_gate=gate)
    result: CoderResult = coder.implement(state)

    proposed = dict(state.get("proposed_patches", {}))
    proposed.update(result.patches)

    current_iter = state.get("iteration_count", 0)
    thread_id = resolve_thread_id(state, config)
    step_idx = len(state.get("agent_history", []))
    now_epoch = time.time()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch))
    files_str = ":".join(sorted(result.files_modified))
    mod_hash = hashlib.sha256(files_str.encode()).hexdigest()[:8]
    event_id = f"hist:coder:implement:{thread_id}:iter{current_iter}:step{step_idx}:{mod_hash}"

    history_entry = {
        "event_id": event_id,
        "agent": "CoderAgent",
        "action": "implement",
        "files_modified": result.files_modified,
        "methods": result.methods_implemented,
        "rationale": result.rationale,
        "iteration": current_iter,
        "created_at": now_epoch,
        "timestamp": now_iso,
    }

    # Track completed actions to prevent repeating side-effects on resume
    completed = list(state.get("completed_actions", []))
    for f in result.files_modified:
        action_key = f"coder:patch:{thread_id}:{f}:iter{current_iter}"
        if action_key not in completed:
            completed.append(action_key)

    return {
        "coder_result": result,
        "proposed_patches": proposed,
        "completed_actions": completed,
        "thread_id": thread_id,
        "agent_history": [history_entry],
        "status": "test_generation",
        "review_result": None,
    }

def test_generator_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Agent 3: Test Generation Agent autonomously writes unit and edge-case tests."""
    if state.get("cancelled") or state.get("abort_requested"):
        return {"cancelled": True, "status": "cancelled"}

    repo_path = state["repo_path"]
    policy = state.get("permission_policy")
    gate = state.get("approval_gate")
    test_gen = TestGeneratorAgent(repo_path, policy=policy, approval_gate=gate)
    result: TestGenResult = test_gen.generate_tests(state)

    current_iter = state.get("iteration_count", 0)
    thread_id = resolve_thread_id(state, config)
    step_idx = len(state.get("agent_history", []))
    now_epoch = time.time()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch))
    files_str = ":".join(sorted(result.test_files_modified))
    files_hash = hashlib.sha256(files_str.encode()).hexdigest()[:8]
    event_id = f"hist:test_gen:generate:{thread_id}:iter{current_iter}:step{step_idx}:{files_hash}"

    history_entry = {
        "event_id": event_id,
        "agent": "TestGeneratorAgent",
        "action": "generate_tests",
        "test_cases": result.test_cases_added,
        "edge_cases": result.edge_cases_tested,
        "iteration": current_iter,
        "created_at": now_epoch,
        "timestamp": now_iso,
    }

    # Track completed test generation to prevent duplication on resume within same iteration
    completed = list(state.get("completed_actions", []))
    for f in result.test_files_modified:
        action_key = f"test_gen:{thread_id}:{f}:iter{current_iter}"
        if action_key not in completed:
            completed.append(action_key)

    return {
        "test_gen_result": result,
        "completed_actions": completed,
        "thread_id": thread_id,
        "agent_history": [history_entry],
        "status": "testing",
    }

def sandbox_runner_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Phase: Executes tests in isolated subprocess sandbox."""
    if state.get("cancelled") or state.get("abort_requested"):
        return {"cancelled": True, "status": "cancelled"}

    repo_path = state["repo_path"]
    thread_id = resolve_thread_id(state, config)
    trust_level = state.get("repo_trust_level")
    sandbox = ExecutionSandbox(repo_path, trust_level=trust_level)
    results = sandbox.run_pytest()

    return {
        "test_results": results,
        "thread_id": thread_id,
        "status": "evaluating",
    }

def manager_evaluate_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Agent 1 (Loop): Manager evaluates specialist outputs and chooses the next step."""
    if state.get("cancelled") or state.get("abort_requested"):
        return {
            "cancelled": True,
            "status": "cancelled",
            "manager_decision": ManagerDecision(
                next_action="abort",
                target_agent="manager",
                reasoning="Workflow cancelled by operator signal.",
            )
        }

    manager = ManagerPlannerAgent()
    decision: ManagerDecision = manager.evaluate_and_route(state)

    current_iter = state.get("iteration_count", 0)
    thread_id = resolve_thread_id(state, config)
    step_idx = len(state.get("agent_history", []))
    now_epoch = time.time()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch))
    event_id = f"hist:manager:evaluate:{thread_id}:iter{current_iter}:step{step_idx}:{decision.next_action}"

    history_entry = {
        "event_id": event_id,
        "agent": "ManagerPlannerAgent",
        "action": "evaluate_and_route",
        "decision": decision.next_action,
        "reasoning": decision.reasoning,
        "iteration": current_iter,
        "created_at": now_epoch,
        "timestamp": now_iso,
    }

    updates: Dict[str, Any] = {
        "manager_decision": decision,
        "thread_id": thread_id,
        "agent_history": [history_entry],
        "status": decision.next_action,
    }
    if decision.next_action == "abort":
        updates["cancelled"] = True
        updates["status"] = "cancelled"

    # Centralized retry-budget metering across ALL remediation routes
    REMEDIATION_ACTIONS = {"delegate_coder", "delegate_debug", "delegate_test_gen", "run_sandbox"}
    if decision.next_action in REMEDIATION_ACTIONS:
        updates["iteration_count"] = state.get("iteration_count", 0) + 1
        updates["review_result"] = None

    return updates

def debugger_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Agent 4: Debugger Agent performs root-cause diagnosis on failures."""
    if state.get("cancelled") or state.get("abort_requested"):
        return {"cancelled": True, "status": "cancelled"}

    repo_path = state["repo_path"]
    debugger = DebuggerAgent(repo_path)
    result: DebugResult = debugger.diagnose_failure(state)

    current_iter = int(state.get("iteration_count", 0))
    thread_id = resolve_thread_id(state, config)
    step_idx = len(state.get("agent_history", []))

    # Derive stable task and diagnostic invocation identifier (independent of LLM output)
    cfg_dict = config.get("configurable", {}) if isinstance(config, dict) else (getattr(config, "configurable", {}) if config else {})
    task_id = (
        state.get("task_id")
        or (cfg_dict.get("task_id") if isinstance(cfg_dict, dict) else None)
        or (hashlib.sha256(str(state.get("task", "")).encode("utf-8")).hexdigest()[:8] if state.get("task") else "task")
    )
    diag_inv_id = str(state.get("diagnostic_invocation_id") or f"diag_{task_id}").strip()

    # Explicit attempt identifier for multiple legitimate diagnostic events within one iteration
    prior_diag_attempts = sum(
        1 for h in state.get("agent_history", [])
        if isinstance(h, dict)
        and h.get("agent") == "DebuggerAgent"
        and int(h.get("iteration", 0)) == current_iter
    )
    attempt_idx = int(state.get("diagnostic_attempt") or state.get("attempt_id") or (prior_diag_attempts + 1))
    attempt_id = f"attempt{attempt_idx}"

    event_id = f"diag:{thread_id}:iter{current_iter}:step{step_idx}:{diag_inv_id}:{attempt_id}"
    hist_event_id = f"hist:debugger:{thread_id}:iter{current_iter}:step{step_idx}:{diag_inv_id}:{attempt_id}"

    now_epoch = time.time()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch))

    error_entry = {
        "event_id": event_id,
        "signature": result.root_cause,
        "agent": "DebuggerAgent",
        "iteration": current_iter,
        "created_at": now_epoch,
        "timestamp": now_iso,
        "context": result.remediation_plan,
    }

    # Record to durable append-only diagnostic ledger (unbounded persistence decoupled from in-memory state)
    try:
        ledger = get_diagnostic_ledger()
        ledger.record_event({
            "event_id": event_id,
            "thread_id": thread_id,
            "iteration": current_iter,
            "step_idx": step_idx,
            "signature": result.root_cause,
            "root_cause": result.root_cause,
            "remediation_plan": result.remediation_plan,
            "created_at": now_epoch,
            "timestamp": now_iso,
            "context": result.remediation_plan,
        })
    except Exception as e:
        logging.getLogger(__name__).warning("Diagnostic ledger record failed: %s", e)

    history_entry = {
        "event_id": hist_event_id,
        "agent": "DebuggerAgent",
        "action": "diagnose_failure",
        "root_cause": result.root_cause,
        "remediation_plan": result.remediation_plan,
        "iteration": current_iter,
        "created_at": now_epoch,
        "timestamp": now_iso,
    }

    return {
        "debug_result": result,
        "iteration_count": current_iter,
        "thread_id": thread_id,
        "error_history": [error_entry],
        "agent_history": [history_entry],
        "status": "coding",
        "review_result": None,
    }

def reviewer_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Agent 5: Reviewer Agent conducts independent quality and security audit."""
    if state.get("cancelled") or state.get("abort_requested"):
        return {"cancelled": True, "status": "cancelled"}

    repo_path = state["repo_path"]
    reviewer = ReviewerAgent(repo_path)
    result: ReviewResult = reviewer.review_code(state)

    current_iter = state.get("iteration_count", 0)
    thread_id = resolve_thread_id(state, config)
    step_idx = len(state.get("agent_history", []))
    now_epoch = time.time()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch))
    status_str = "approved" if result.approved else "rejected"
    event_id = f"hist:reviewer:review:{thread_id}:iter{current_iter}:step{step_idx}:{status_str}"

    history_entry = {
        "event_id": event_id,
        "agent": "ReviewerAgent",
        "action": "review_code",
        "approved": result.approved,
        "score": result.quality_score,
        "blocking_issues": result.blocking_issues,
        "iteration": current_iter,
        "created_at": now_epoch,
        "timestamp": now_iso,
    }

    return {
        "review_result": result,
        "thread_id": thread_id,
        "agent_history": [history_entry],
        "status": "evaluating",
    }

def branch_join_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Parallel Fork/Join Barrier: Synchronizes parallel test generation and code review branches."""
    if state.get("cancelled") or state.get("abort_requested"):
        return {"cancelled": True, "status": "cancelled"}

    thread_id = resolve_thread_id(state, config)
    current_iter = state.get("iteration_count", 0)
    step_idx = len(state.get("agent_history", []))
    now_epoch = time.time()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch))
    event_id = f"hist:branch_join:{thread_id}:iter{current_iter}:step{step_idx}"

    history_entry = {
        "event_id": event_id,
        "agent": "SystemOrchestrator",
        "action": "parallel_branch_join",
        "test_gen_completed": state.get("test_gen_result") is not None,
        "review_completed": state.get("review_result") is not None,
        "iteration": current_iter,
        "created_at": now_epoch,
        "timestamp": now_iso,
    }

    return {
        "thread_id": thread_id,
        "agent_history": [history_entry],
        "status": "branch_joined",
    }

def manager_finalize_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Agent 1 (Final): Manager executes independent verification and compiles final outcome report."""
    repo_path = state["repo_path"]
    thread_id = resolve_thread_id(state, config)
    verifier = IndependentVerifier(repo_path, trust_level=state.get("repo_trust_level"))
    verification_res: VerificationResult = state.get("verification_result") or verifier.verify(state)

    # Sovereign authority evaluation: Manager cannot declare success on its own
    task_succeeded = is_task_successful(state, verification_res)

    # Issue B: Never skip integrity check on empty manifest; fail closed on None, verify empty on {}
    # (TOCTOU integrity check applies to completion workflows; cancelled/blocked states are preserved)
    if verification_res.outcome not in (WorkflowOutcome.CANCELLED, WorkflowOutcome.BLOCKED):
        if verification_res.verified_manifest is None:
            logger.critical("TOCTOU failure: verified_manifest is None; failing closed.")
            object.__setattr__(verification_res, "toctou_valid", False)
            object.__setattr__(verification_res, "verified", False)
            object.__setattr__(verification_res, "outcome", WorkflowOutcome.COMPLETED_WITH_FAILURES)
            verification_res.failure_reasons.append("TOCTOU failure: verified_manifest is None (manifest missing; failed closed)")
            task_succeeded = False
        else:
            intact, toctou_drift = verifier.verify_manifest_intact(verification_res.verified_manifest)
            if not intact:
                logger.critical(f"TOCTOU violation detected prior to report compilation: {toctou_drift}")
                object.__setattr__(verification_res, "toctou_valid", False)
                object.__setattr__(verification_res, "verified", False)
                object.__setattr__(verification_res, "outcome", WorkflowOutcome.COMPLETED_WITH_FAILURES)
                verification_res.failure_reasons.append(
                    f"TOCTOU race detected: files mutated during finalization ({', '.join(toctou_drift)})"
                )
                task_succeeded = False

    # Issue C (Fundamental boundary): Create atomic immutable handover artifact if verified
    handover_artifact_path = None
    handover_artifact_hash = None
    if task_succeeded and verification_res.verified and verification_res.toctou_valid:
        handover_artifact_path, handover_artifact_hash = verifier.create_immutable_handover(
            verification_res.verified_manifest
        )
        if handover_artifact_path:
            object.__setattr__(verification_res, "handover_artifact", handover_artifact_path)
            object.__setattr__(verification_res, "handover_hash", handover_artifact_hash)

    # Prepare state with verified outcome for final report compilation
    state_with_verification = dict(state)
    state_with_verification["verification_result"] = verification_res
    state_with_verification["workflow_outcome"] = verification_res.outcome.value
    state_with_verification["task_succeeded"] = task_succeeded
    if handover_artifact_path:
        state_with_verification["handover_artifact"] = handover_artifact_path
        state_with_verification["handover_hash"] = handover_artifact_hash

    # Issue A: Compile final report AFTER all integrity checks and handover creation
    manager = ManagerPlannerAgent()
    report = manager.compile_final_report(state_with_verification)

    # Defense-in-depth: Re-check manifest after report generation; if drift occurred, regenerate report
    if verification_res.verified_manifest is not None and task_succeeded:
        intact_post, toctou_drift_post = verifier.verify_manifest_intact(verification_res.verified_manifest)
        if not intact_post:
            logger.critical(f"TOCTOU race detected during report generation: {toctou_drift_post}")
            object.__setattr__(verification_res, "toctou_valid", False)
            object.__setattr__(verification_res, "verified", False)
            object.__setattr__(verification_res, "outcome", WorkflowOutcome.COMPLETED_WITH_FAILURES)
            verification_res.failure_reasons.append(
                f"TOCTOU race detected during report generation ({', '.join(toctou_drift_post)})"
            )
            task_succeeded = False
            state_with_verification["verification_result"] = verification_res
            state_with_verification["workflow_outcome"] = verification_res.outcome.value
            state_with_verification["task_succeeded"] = False
            report = manager.compile_final_report(state_with_verification)

    updates = {
        "verification_result": verification_res,
        "workflow_outcome": verification_res.outcome.value,
        "task_succeeded": task_succeeded,
        "final_report": report,
        "thread_id": thread_id,
        "status": verification_res.outcome.value,
    }
    if verification_res.snapshot_hash:
        updates["snapshot_hash"] = verification_res.snapshot_hash
    if verification_res.verified_manifest:
        updates["verified_manifest"] = verification_res.verified_manifest
    if getattr(verification_res, "handover_artifact", None):
        updates["handover_artifact"] = verification_res.handover_artifact
        updates["handover_hash"] = verification_res.handover_hash

    # Persist episode into long-term episodic memory for future recall
    try:
        get_memory_engine().record_episode_from_state({**state, **updates})
    except Exception as e:
        logger.warning(f"Could not persist episode to long-term memory: {e}")

    # Empirical Evidence Loop: Update downstream reuse metrics for recalled semantic patterns
    applied_pats = state.get("applied_pattern_ids") or []
    if applied_pats:
        try:
            mem_engine = get_memory_engine()
            evidence_tag = "unit_tests_passed" if task_succeeded else "verification_failed"
            for pat_id in applied_pats:
                mem_engine.semantic_store.record_reuse(
                    pattern_id=pat_id,
                    success=task_succeeded,
                    evidence=evidence_tag,
                )
        except Exception as e:
            logger.warning(f"Could not record semantic pattern reuse: {e}")

    return updates

# ============================================================
# Dynamic Routing Condition
# ============================================================

logger = logging.getLogger("agent.graph")

DECISION_TO_NODE_MAP: Dict[str, str] = {
    "delegate_coder": "coder",
    "delegate_test_gen": "test_generator",
    "run_sandbox": "sandbox_runner",
    "delegate_debug": "debugger",
    "delegate_review": "reviewer",
    "finalize": "manager_finalize",
    "abort": "manager_finalize",
}

def route_manager_decision(
    state: AgentState,
) -> Literal["coder", "test_generator", "sandbox_runner", "debugger", "reviewer", "manager_finalize"]:
    """Conditional Edge routing based on Manager's structured decision.

    Translates ManagerDecision.next_action to the corresponding graph node:
    - 'delegate_coder'    -> 'coder'
    - 'delegate_test_gen' -> 'test_generator'
    - 'run_sandbox'       -> 'sandbox_runner'
    - 'delegate_debug'    -> 'debugger'
    - 'delegate_review'   -> 'reviewer'
    - 'finalize'          -> 'manager_finalize'
    - 'abort'             -> 'manager_finalize' (marks state as cancelled)

    Includes safe fallback to 'manager_finalize' for missing or invalid decisions.
    """
    decision: Optional[ManagerDecision] = state.get("manager_decision")
    if not decision:
        logger.warning("No ManagerDecision found in state; falling back safely to 'manager_finalize'.")
        return "manager_finalize"

    action = getattr(decision, "next_action", None)
    if not action:
        logger.warning("ManagerDecision missing next_action; falling back safely to 'manager_finalize'.")
        return "manager_finalize"

    if action == "abort":
        state["cancelled"] = True
        state["status"] = "cancelled"
        return "manager_finalize"

    target_node = DECISION_TO_NODE_MAP.get(action)
    if not target_node:
        logger.warning(
            f"Unrecognized ManagerDecision.next_action: '{action}'. "
            f"Allowed actions: {list(DECISION_TO_NODE_MAP.keys())}. "
            "Falling back safely to 'manager_finalize'."
        )
        return "manager_finalize"

    return target_node

# ============================================================
# Backward-compatibility alias functions
# ============================================================
plan_node = manager_planner_node
implement_node = coder_node
test_runner_node = sandbox_runner_node
debug_node = debugger_node
review_and_report_node = manager_finalize_node

def should_continue(state: AgentState) -> Literal["debug_and_revise", "review_and_report"]:
    test_res = state.get("test_results")
    iteration = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", 3)
    if test_res and test_res.passed:
        return "review_and_report"
    if iteration < max_iter:
        return "debug_and_revise"
    return "review_and_report"

# ============================================================
# Graph Builder
# ============================================================

def build_coding_agent_graph(
    checkpointer: Any = None,
    interrupt_before: Optional[List[str]] = None,
    interrupt_after: Optional[List[str]] = None,
):
    """Builds and compiles the real multi-agent orchestration LangGraph workflow with durable checkpointer."""
    # pyrefly: ignore[missing-import]
    from langgraph.graph import StateGraph, START, END

    saver = checkpointer if checkpointer is not None else get_sqlite_checkpointer()

    workflow = StateGraph(AgentState)

    # Register 5 Specialized Agents + Infrastructure Nodes + Parallel Join Barrier
    workflow.add_node("explore_repo", explore_repo_node)
    workflow.add_node("manager_planner", manager_planner_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("test_generator", test_generator_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("branch_join", branch_join_node)
    workflow.add_node("sandbox_runner", sandbox_runner_node)
    workflow.add_node("manager_evaluate", manager_evaluate_node)
    workflow.add_node("debugger", debugger_node)
    workflow.add_node("manager_finalize", manager_finalize_node)

    # Initial Orchestration Pipeline
    workflow.add_edge(START, "explore_repo")
    workflow.add_edge("explore_repo", "manager_planner")
    workflow.add_edge("manager_planner", "coder")

    # PARALLEL FORK: Coder concurrently branches into Test Generator and Reviewer
    workflow.add_edge("coder", "test_generator")
    workflow.add_edge("coder", "reviewer")

    # PARALLEL JOIN: Both parallel branches converge at branch_join barrier
    # Explicit list-based join registers NamedBarrierValue in LangGraph Pregel,
    # guaranteeing branch_join cannot execute until BOTH branches complete.
    workflow.add_edge(["test_generator", "reviewer"], "branch_join")

    # Post-Join Pipeline: Sandboxed execution followed by Manager Evaluation
    workflow.add_edge("branch_join", "sandbox_runner")
    workflow.add_edge("sandbox_runner", "manager_evaluate")

    # Manager's Dynamic Routing Gate with comprehensive node coverage
    workflow.add_conditional_edges(
        "manager_evaluate",
        route_manager_decision,
        
        {
            "coder": "coder",
            "test_generator": "test_generator",
            "sandbox_runner": "sandbox_runner",
            "debugger": "debugger",
            "reviewer": "reviewer",
            "manager_finalize": "manager_finalize",
        },
    )

    # Debugger loops back to Coder with structured remediation (re-triggering parallel fork)
    workflow.add_edge("debugger", "coder")
    
    # Finalize routes to END
    workflow.add_edge("manager_finalize", END)

    compile_kwargs: Dict[str, Any] = {"checkpointer": saver}
    if interrupt_before:
        compile_kwargs["interrupt_before"] = interrupt_before
    if interrupt_after:
        compile_kwargs["interrupt_after"] = interrupt_after

    return workflow.compile(**compile_kwargs)

# Export compiled graph with default SQLite checkpointer
graph = build_coding_agent_graph()

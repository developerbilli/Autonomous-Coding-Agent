"""Autonomous AI Coding Agent CLI Entrypoint with LangSmith Tracing & Observability."""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Step 4: Load environment variables before importing or invoking graph
load_dotenv()

from agent.core.state import AgentState
from agent.core.graph import build_coding_agent_graph
from agent.core.baseline import SingleAgentBaseline
from agent.core.checkpointer import (
    generate_stable_thread_id,
    resolve_thread_execution_mode,
    get_sqlite_checkpointer,
)

def check_observability_status():
    """Checks and logs whether LangSmith tracing is active."""
    tracing_enabled = os.getenv("LANGSMITH_TRACING", "false").lower() in ("true", "1")
    api_key = os.getenv("LANGSMITH_API_KEY")
    project = os.getenv("LANGSMITH_PROJECT", "autonomous-coding-agent")

    if tracing_enabled and api_key and not api_key.startswith("your_"):
        print(f"📡 LangSmith Tracing: ACTIVE")
        print(f"   Project: {project}")
        print(f"   Endpoint: {os.getenv('LANGSMITH_ENDPOINT', 'https://api.smith.langchain.com')}\n")
    else:
        print("ℹ️  LangSmith Tracing: INACTIVE (Local offline execution)")
        print("   To enable, set LANGSMITH_TRACING=true and LANGSMITH_API_KEY in .env\n")

def run_agent_workflow(
    repo_path: str,
    task: str,
    max_iterations: int = 3,
    task_type: str = "feature_addition",
    mode: str = "multi-agent",
    demo_mode: bool = False,
    thread_id: Optional[str] = None,
    resume: bool = False,
    trust_level: Optional[str] = None,
):
    checkpointer = get_sqlite_checkpointer()
    base_thread = thread_id or generate_stable_thread_id(repo_path, task)
    stable_thread, exec_mode = resolve_thread_execution_mode(
        checkpointer=checkpointer,
        thread_id=base_thread,
        explicit_resume=resume,
    )
    is_resuming = (exec_mode == "resume")

    print("=======================================================")
    print(" 🤖 Autonomous AI Coding Agent (LangGraph + LangSmith)")
    print(f" Architecture Mode: {mode.upper()}")
    print(f" Target Repository: {repo_path}")
    print(f" Trust Level: {trust_level.upper() if trust_level else 'UNTRUSTED (Zero-Trust Default)'}")
    print(f" Task: {task}")
    print(f" Thread ID: {stable_thread} {'(Resuming from Checkpoint)' if is_resuming else '(Fresh Run)'}")
    print("=======================================================\n")

    check_observability_status()

    if mode == "baseline":
        print("⚡ Invoking Single-Agent Baseline Engine...")
        baseline = SingleAgentBaseline(repo_path)
        result = baseline.run(task, max_iterations=max_iterations, demo_mode=demo_mode)
        print("\n✅ Baseline Execution Completed!\n")
        if result["final_state"].get("final_report"):
            print(result["final_state"]["final_report"])
        return result["final_state"]

    # Build compiled 5-Agent LangGraph workflow with durable checkpointer
    print("🚀 Invoking 5-Agent LangGraph Multi-Agent Orchestration...")
    print("   Specialists: Manager/Planner • Coder • Test-Gen • Reviewer • Debugger\n")
    checkpointer = get_sqlite_checkpointer()
    app = build_coding_agent_graph(checkpointer=checkpointer)

    config = {
        "run_name": f"coding-agent:{Path(repo_path).name}",
        "tags": ["autonomous-coding-agent", "multi-agent", task_type],
        "metadata": {
            "task_type": task_type,
            "architecture_mode": "multi_agent",
            "repository": str(Path(repo_path).name),
            "max_iterations": max_iterations,
        },
        "configurable": {
            "thread_id": stable_thread,
        },
    }

    # Check for existing checkpoint if resuming
    existing_state = None
    try:
        existing_tuple = checkpointer.get_tuple(config)
        if existing_tuple:
            existing_state = existing_tuple.checkpoint.get("channel_values")
    except Exception:
        pass

    if is_resuming and existing_state:
        print(f"🔄 Resuming workflow from checkpoint '{existing_tuple.checkpoint['id']}'...")
        final_state = app.invoke(None, config=config)
    else:
        initial_state: AgentState = {
            "task": task,
            "repo_path": repo_path,
            "symbol_index": {},
            "relevant_files": [],
            "retrieved_code": {},
            "plan": [],
            "active_step": 0,
            "proposed_patches": {},
            "test_results": None,
            "iteration_count": 0,
            "max_iterations": max_iterations,
            "error_history": [],
            "agent_history": [],
            "completed_actions": [],
            "final_report": None,
            "status": "exploring",
            "demo_mode": demo_mode,
            "architecture_mode": "multi_agent",
            "repo_trust_level": trust_level,
            "thread_id": stable_thread,
        }
        final_state = app.invoke(initial_state, config=config)

    outcome = final_state.get("workflow_outcome") or final_state.get("status", "unknown")
    if outcome == "completed_successfully":
        print("\n✅ Multi-Agent Workflow Completed Successfully! (All Verification Gates Passed)\n")
    elif outcome == "completed_with_failures":
        print("\n❌ Multi-Agent Workflow Completed With Failures! (Retry Limit Reached or Verification Failed)\n")
    elif outcome == "blocked":
        print("\n⚠️ Multi-Agent Workflow Blocked! (Security Policy or Operator Denial)\n")
    elif outcome == "cancelled":
        print("\n⚪ Multi-Agent Workflow Cancelled!\n")
    else:
        print(f"\nℹ️ Multi-Agent Workflow Finished with status: {outcome}\n")

    if final_state.get("final_report"):
        print(final_state["final_report"])

    return final_state

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Autonomous AI Coding Agent with Multi-Agent Orchestration.")
    # Repository Ingestion Options
    parser.add_argument("--source", type=str, choices=["local", "github", "zip", "greenfield"], default="local", help="Repository ingestion source type (local, github, zip, greenfield)")
    parser.add_argument("--repo", type=str, default="calculator_repo", help="Path to target local codebase")
    parser.add_argument("--git-url", type=str, default=None, help="GitHub repository URL for automated cloning")
    parser.add_argument("--branch", type=str, default="main", help="Target Git branch for cloning")
    parser.add_argument("--token", type=str, default=None, help="GitHub token for private repository access")
    parser.add_argument("--isolate", action="store_true", help="Run in an isolated copy-on-write workspace snapshot")
    parser.add_argument("--project-name", type=str, default=None, help="Project name for greenfield creation")
    parser.add_argument("--trusted", "--operator-attestation", dest="operator_attestation", action="store_true", help="Explicit operator sign-off attesting that repository code is vetted and trusted (defaults to False / Zero-Trust)")

    # Workflow Options
    parser.add_argument("--task", type=str, default="Complete Calculator implementation: add division with zero check, power, square root, and factorial", help="Task description")
    parser.add_argument("--max-iter", type=int, default=3, help="Max self-healing iterations")
    parser.add_argument("--type", type=str, default="feature_addition", help="Task type (e.g. bug_fix, feature_addition, refactor)")
    parser.add_argument("--mode", type=str, choices=["multi-agent", "baseline"], default="multi-agent", help="Execution mode: multi-agent (5 specialized agents) or baseline (single agent)")
    parser.add_argument("--demo", action="store_true", help="Demonstrate self-healing and reviewer catch loop on first iteration")
    parser.add_argument("--benchmark", action="store_true", help="Run the empirical comparison benchmark between Baseline and Multi-Agent")
    parser.add_argument("--thread-id", type=str, default=None, help="Stable thread identifier for checkpoint persistence and recovery")
    parser.add_argument("--resume", action="store_true", help="Resume interrupted workflow from the latest stored checkpoint")

    args = parser.parse_args()

    if args.benchmark:
        from benchmark_baseline_vs_multiagent import run_benchmark
        run_benchmark()
        sys.exit(0)

    # Ingestion Layer: prepare task workspace
    from agent.repository.manager import RepositoryManager, WorkspaceSpec, WorkspaceSourceType
    repo_mgr = RepositoryManager()
    source_identifier = args.git_url or args.repo or args.project_name or "repo"
    task_id = args.thread_id or generate_stable_thread_id(source_identifier, args.task)

    spec = WorkspaceSpec(
        source_type=WorkspaceSourceType(args.source),
        github_url=args.git_url,
        branch=args.branch,
        auth_token=args.token,
        local_path=args.repo,
        project_name=args.project_name,
        isolate_local_copy=args.isolate,
        operator_attestation=args.operator_attestation,
    )
    print(f"📦 Preparing workspace (Source: {args.source.upper()})...")
    workspace_path = repo_mgr.prepare_workspace(task_id, spec)
    resolved_repo = str(workspace_path.resolve())
    print(f"📁 Workspace ready at: {resolved_repo}")
    print(f"🔒 Security Posture: Trust Level = '{spec.trust_level.upper()}' (Operator Attestation: {spec.operator_attestation})\n")

    run_agent_workflow(
        repo_path=resolved_repo,
        task=args.task,
        max_iterations=args.max_iter,
        task_type=args.type,
        mode=args.mode,
        demo_mode=args.demo,
        thread_id=task_id,
        resume=args.resume,
        trust_level=spec.trust_level,
    )

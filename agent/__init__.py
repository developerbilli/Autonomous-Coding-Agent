"""Autonomous AI Multi-Agent Coding System.

A resilient, stateful multi-agent software engineering system featuring:
- 5 specialized agents coordinated via LangGraph
- Strict separation of concerns under Pydantic state contracts
- Durable SQLite WAL checkpointer with crash recovery
- Hardened subprocess/container sandbox execution
- Sovereign 4-Pillar Independent Verification Authority
"""

from agent.core.state import (
    AgentState,
    ManagerPlan,
    ManagerDecision,
    CoderResult,
    TestGenResult,
    ReviewResult,
    DebugResult,
    TestResult,
)
from agent.core.graph import (
    build_coding_agent_graph,
    explore_repo_node,
    manager_planner_node,
    coder_node,
    test_generator_node,
    sandbox_runner_node,
    manager_evaluate_node,
    debugger_node,
    reviewer_node,
    manager_finalize_node,
)
from agent.agents.manager import ManagerPlannerAgent
from agent.agents.coder import CoderAgent
from agent.agents.test_generator import TestGeneratorAgent
from agent.agents.debugger import DebuggerAgent
from agent.agents.reviewer import ReviewerAgent
from agent.verification.verifier import (
    IndependentVerifier,
    WorkflowOutcome,
    VerificationResult,
)
from agent.execution.sandbox import ExecutionSandbox
from agent.core.checkpointer import (
    SqliteCheckpointSaver,
    get_sqlite_checkpointer,
    generate_stable_thread_id,
    resolve_thread_execution_mode,
)

__version__ = "1.0.0"

__all__ = [
    "AgentState",
    "ManagerPlan",
    "ManagerDecision",
    "CoderResult",
    "TestGenResult",
    "ReviewResult",
    "DebugResult",
    "TestResult",
    "VerificationResult",
    "build_coding_agent_graph",
    "ManagerPlannerAgent",
    "CoderAgent",
    "TestGeneratorAgent",
    "DebuggerAgent",
    "ReviewerAgent",
    "IndependentVerifier",
    "WorkflowOutcome",
    "ExecutionSandbox",
    "SqliteCheckpointSaver",
    "get_sqlite_checkpointer",
    "generate_stable_thread_id",
    "resolve_thread_execution_mode",
]

"""Single-Agent Baseline: Monolithic architecture used as an empirical benchmark."""

import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from agent.core.state import AgentState, TestResult, reduce_error_history
from agent.explorer.ast_indexer import ASTIndexer
from agent.execution.sandbox import ExecutionSandbox
from agent.llm.provider import get_llm_provider, extract_code_block
from agent.core.coder import CodeSynthesizer

try:
    from langsmith import traceable
except ImportError:
    def traceable(name=None, run_type=None, **kwargs):
        def decorator(func):
            return func
        return decorator

logger = logging.getLogger("agent.baseline")

class SingleAgentBaseline:
    """Represents the single-agent monolithic approach:
    A single model/node performs code edits without independent test generation,
    without independent adversarial review, and without structured debugging diagnosis.
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.sandbox = ExecutionSandbox(str(self.repo_path))
        self.indexer = ASTIndexer(str(self.repo_path))
        self.llm = get_llm_provider()
        self.synthesizer = CodeSynthesizer(str(self.repo_path))

    @traceable(name="SingleAgentBaseline.run", run_type="chain")
    def run(self, task: str, max_iterations: int = 3, demo_mode: bool = False) -> Dict[str, Any]:
        """Runs the single-agent baseline workflow and measures success, test generation, and defect catches."""
        start_time = time.time()
        
        # Phase 1: Simple AST scan
        symbols = self.indexer.index_repository()
        keywords = [w.strip(".,;:\"'") for w in task.split() if len(w) > 3]
        relevant_files = []
        for kw in keywords:
            matches = self.indexer.find_symbols_by_name(kw)
            for m in matches:
                if m.file_path not in relevant_files:
                    relevant_files.append(m.file_path)

        state: AgentState = {
            "task": task,
            "repo_path": str(self.repo_path),
            "symbol_index": symbols,
            "relevant_files": relevant_files,
            "retrieved_code": {},
            "plan": [f"Implement changes for {task}", "Run existing tests"],
            "active_step": 0,
            "proposed_patches": {},
            "test_results": None,
            "iteration_count": 0,
            "max_iterations": max_iterations,
            "error_history": [],
            "final_report": None,
            "status": "coding",
            "demo_mode": demo_mode,
            "architecture_mode": "single_agent_baseline",
        }

        # Iteration loop (single agent trying to fix code upon test failure)
        iteration = 0
        tests_passed = False
        defects_caught_before_release = 0
        new_tests_generated = 0  # Baseline NEVER generates tests

        while iteration < max_iterations:
            # Monolithic code synthesis
            patches = self.synthesizer.synthesize_and_apply(state)
            state["proposed_patches"].update(patches)

            # Test execution (relies ONLY on pre-existing tests; cannot create new tests)
            test_res = self.sandbox.run_pytest()
            state["test_results"] = test_res

            if test_res.passed:
                tests_passed = True
                break

            # Without a debugger agent, single agent just accumulates raw error string
            iteration += 1
            state["iteration_count"] = iteration
            if test_res.error_summary:
                state["error_history"] = reduce_error_history(
                    state.get("error_history"),
                    {"signature": test_res.error_summary, "agent": "SingleAgentBaseline", "iteration": iteration},
                )

        latency = time.time() - start_time

        report = (
            f"### Single-Agent Baseline Summary\n"
            f"- **Success**: {'PASSED' if tests_passed else 'FAILED'}\n"
            f"- **Iterations**: {iteration}\n"
            f"- **New Tests Created**: {new_tests_generated} (Baseline has no Test-Gen Agent)\n"
            f"- **Review Rejections**: 0 (Baseline has no Reviewer Agent, 100% self-confirmation bias)\n"
            f"- **Root Cause Diagnoses**: 0 (Baseline has no Debugger Agent, relies on raw tracebacks)\n"
            f"- **Total Latency**: {latency:.2f}s\n"
        )
        state["final_report"] = report
        state["status"] = "completed" if tests_passed else "failed"

        return {
            "passed": tests_passed,
            "iterations": iteration,
            "new_tests_generated": new_tests_generated,
            "defects_caught_by_review": defects_caught_before_release,
            "structured_diagnoses": 0,
            "latency": latency,
            "final_state": state,
        }

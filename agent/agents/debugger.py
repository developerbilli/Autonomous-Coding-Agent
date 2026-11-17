"""Debugger Agent: Specialized in stack-trace analysis, defect isolation, and root-cause diagnosis."""

import re
import json
import logging
from typing import Dict, Any, List, Optional
from agent.core.state import AgentState, DebugResult, TestResult, ReviewResult
from agent.llm.provider import get_llm_provider, extract_code_block

try:
    from langsmith import traceable
except ImportError:
    def traceable(name=None, run_type=None, **kwargs):
        def decorator(func):
            return func
        return decorator

logger = logging.getLogger("agent.debugger")

class DebuggerAgent:
    """Specialized Debugging & Failure Diagnosis Agent:
    Analyzes failed sandbox test tracebacks, isolates the root-cause defect,
    identifies affected AST symbols, and generates actionable repair directives.
    """

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.llm = get_llm_provider()

    @traceable(name="DebuggerAgent.diagnose_failure", run_type="chain")
    def diagnose_failure(self, state: AgentState) -> DebugResult:
        """Parses test failure logs or reviewer objections to produce a structured diagnosis."""
        test_res: Optional[TestResult] = state.get("test_results")
        review_res: Optional[ReviewResult] = state.get("review_result")
        failing_tests = test_res.failed_tests if test_res else []
        error_summary = test_res.error_summary if test_res else (test_res.stdout if test_res else "")

        # Also incorporate reviewer objections if relevant
        reviewer_issues = review_res.blocking_issues if review_res else []

        # LLM Root-Cause Analysis
        if self.llm.is_available() and (error_summary or reviewer_issues):
            prompt = f"""You are DebuggerAgent, a Lead Diagnostic Engineer specializing in Python runtime failures, AST stack traces, and defect isolation.

FAILED TESTS IDENTIFIED:
{', '.join(failing_tests) if failing_tests else 'None'}

TEST ERROR SUMMARY & TRACEBACK:
{error_summary}

REVIEWER BLOCKING FINDINGS:
{chr(10).join(['- ' + issue for issue in reviewer_issues]) if reviewer_issues else 'None'}

Diagnose why the code failed and formulate an unambiguous remediation strategy for CoderAgent.
Return a strictly valid JSON object matching this schema:
{{
  "root_cause": "Detailed technical explanation of the failure (e.g., divide method did not raise ValueError on zero division)",
  "failing_tests": {json.dumps(failing_tests)},
  "suspect_symbols": ["Calculator.divide", "Calculator.square_root"],
  "remediation_plan": "Add an explicit `if b == 0: raise ValueError(...)` guard clause in divide method",
  "target_fix_agent": "coder"
}}
Output ONLY the JSON object.
"""
            raw = self.llm.gemini.generate(prompt, temperature=0.1, max_tokens=1024)
            if raw:
                try:
                    cleaned = extract_code_block(raw)
                    data = json.loads(cleaned)
                    return DebugResult(
                        agent_name="DebuggerAgent",
                        root_cause=data.get("root_cause", "Unspecified runtime assertion failure."),
                        failing_tests=data.get("failing_tests", failing_tests),
                        suspect_symbols=data.get("suspect_symbols", []),
                        remediation_plan=data.get("remediation_plan", "Resolve assertion failure by applying edge guards."),
                        target_fix_agent=data.get("target_fix_agent", "coder"),
                    )
                except Exception as e:
                    logger.warning(f"Failed to parse Debugger JSON: {e}")

        # Deterministic diagnostic parsing fallback
        suspects = []
        root_causes = []
        plan_steps = []

        if any("divide" in t for t in failing_tests) or "ZeroDivision" in error_summary or "divide" in str(reviewer_issues):
            suspects.append("Calculator.divide")
            root_causes.append("Division method failed to catch divisor=0 and raise ValueError as required.")
            plan_steps.append("Insert `if b == 0: raise ValueError('Cannot divide by zero.')` inside `divide`.")

        if any("square_root" in t for t in failing_tests) or "ValueError" in error_summary and "negative" in error_summary:
            suspects.append("Calculator.square_root")
            root_causes.append("Square root method failed to check for negative input before math.sqrt.")
            plan_steps.append("Insert `if n < 0: raise ValueError('Cannot compute square root of negative')` inside `square_root`.")

        if any("factorial" in t for t in failing_tests):
            suspects.append("Calculator.factorial")
            root_causes.append("Factorial method failed to check for negative input or non-integer.")
            plan_steps.append("Insert `if not isinstance(n, int) or n < 0: raise ValueError(...)` inside `factorial`.")

        if not root_causes:
            root_causes.append(error_summary[:200] if error_summary else "Assertion mismatch during test execution.")
            plan_steps.append("Inspect method implementation and align with expected assertions.")

        return DebugResult(
            agent_name="DebuggerAgent",
            root_cause="; ".join(root_causes),
            failing_tests=failing_tests,
            suspect_symbols=suspects or ["Calculator"],
            remediation_plan="; ".join(plan_steps),
            target_fix_agent="coder",
        )

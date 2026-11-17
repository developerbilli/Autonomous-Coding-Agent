import json
import pytest
from agent.mcp.server import MCPServer

@pytest.fixture
def mcp():
    return MCPServer()

def test_mcp_tool_definitions(mcp):
    tools = mcp.get_tool_definitions()
    tool_names = [t["name"] for t in tools]
    assert "analyze_repository" in tool_names
    assert "run_autonomous_coding_agent" in tool_names
    assert "execute_sandbox_tests" in tool_names
    assert "diagnose_stack_trace" in tool_names
    assert "review_code_patch" in tool_names
    assert "verify_patch_admission" in tool_names

def test_mcp_analyze_repository(mcp):
    res = mcp.handle_tool_call("analyze_repository", {
        "repo_path": "calculator_repo",
        "task_query": "calculator"
    })
    assert "content" in res
    assert len(res["content"]) > 0
    parsed = json.loads(res["content"][0]["text"])
    assert parsed["total_symbols_indexed"] > 0
    assert "symbols" in parsed

def test_mcp_diagnose_stack_trace(mcp):
    res = mcp.handle_tool_call("diagnose_stack_trace", {
        "error_summary": "ZeroDivisionError: division by zero in calculator/core.py line 23",
        "failed_tests": ["test_divide_by_zero"]
    })
    parsed = json.loads(res["content"][0]["text"])
    assert "root_cause" in parsed
    assert "remediation_plan" in parsed

def test_mcp_execute_sandbox_tests(mcp):
    res = mcp.handle_tool_call("execute_sandbox_tests", {
        "repo_path": "calculator_repo"
    })
    parsed = json.loads(res["content"][0]["text"])
    assert "passed" in parsed
    assert "exit_code" in parsed


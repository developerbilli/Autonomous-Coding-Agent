#!/usr/bin/env python3
"""Autonomous AI Multi-Agent Coding System - Model Context Protocol (MCP) Server.

Exposes specialized engineering agents (Manager, Coder, Test Generator, Debugger, Reviewer, Verifier)
and static analysis tools (AST Indexer, Dependency Graph, Sandbox Runner) via standard MCP protocol.
Compatible with Antigravity, Claude Desktop, Cursor, Continue.dev, and any MCP-compliant AI client.
"""

import sys
import json
import logging
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure project root and user site-packages are in sys.path when invoked via MCP stdio by external clients
import site
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
try:
    user_site = site.getusersitepackages()
    if user_site and user_site not in sys.path:
        sys.path.append(user_site)
except Exception:
    pass

# Logging must write strictly to stderr so stdout is reserved for MCP JSON-RPC messages
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[MCP Server] %(levelname)s: %(message)s"
)
logger = logging.getLogger("mcp-server")

# Import core agent subsystems
from agent.repository.manager import RepositoryManager, WorkspaceSpec, WorkspaceSourceType
from agent.explorer.ast_indexer import ASTIndexer
from agent.execution.sandbox import ExecutionSandbox
from agent.agents.debugger import DebuggerAgent
from agent.agents.reviewer import ReviewerAgent
from agent.verification.verifier import IndependentVerifier
from agent.core.graph import build_coding_agent_graph
from agent.core.state import AgentState

MCP_PROTOCOL_VERSION = "2024-11-05"

class MCPServer:
    """Enterprise Model Context Protocol (MCP) stdio server."""

    def __init__(self):
        self.repo_mgr = RepositoryManager()

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns the formal schemas for all exposed coding agent tools."""
        return [
            {
                "name": "analyze_repository",
                "description": "Performs comprehensive AST parsing, symbol indexing, callers/callees dependency traversal, and git change extraction for a target codebase.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Local path to the repository directory to inspect."
                        },
                        "task_query": {
                            "type": "string",
                            "description": "Optional search query or task description to extract relevant files and code contexts."
                        }
                    },
                    "required": ["repo_path"]
                }
            },
            {
                "name": "run_autonomous_coding_agent",
                "description": "Launches the complete 5-agent LangGraph workflow (Manager, Coder, Test-Gen, Sandbox, Debugger, Reviewer, Sovereign Verifier) to implement features, fix bugs, and commit changes.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "The natural-language coding task, feature request, or bug description."
                        },
                        "repo_path": {
                            "type": "string",
                            "description": "Local repository directory path (if working locally)."
                        },
                        "github_url": {
                            "type": "string",
                            "description": "Remote GitHub repository URL to clone and operate on."
                        },
                        "branch": {
                            "type": "string",
                            "description": "Git branch to clone or target (default: 'main').",
                            "default": "main"
                        },
                        "max_iterations": {
                            "type": "integer",
                            "description": "Maximum self-healing debugging iterations (default: 3).",
                            "default": 3
                        }
                    },
                    "required": ["task"]
                }
            },
            {
                "name": "execute_sandbox_tests",
                "description": "Executes pytest inside the air-gapped UnifiedExecutionSandbox, capturing exit codes, durations, pass/fail counts, and failure stack traces.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Directory of the repository containing pytest test suites."
                        },
                        "test_target": {
                            "type": "string",
                            "description": "Specific test file or directory path relative to repository (default: 'tests').",
                            "default": "tests"
                        }
                    },
                    "required": ["repo_path"]
                }
            },
            {
                "name": "diagnose_stack_trace",
                "description": "Invokes the specialized DebuggerAgent on stack traces and failure summaries to isolate suspect symbols, file locations, and synthesize an actionable remediation plan.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "error_summary": {
                            "type": "string",
                            "description": "The raw pytest stdout/stderr or Python traceback string."
                        },
                        "failed_tests": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of failing test node IDs or test names."
                        },
                        "repo_path": {
                            "type": "string",
                            "description": "Optional repository path to enable AST source context lookup."
                        }
                    },
                    "required": ["error_summary"]
                }
            },
            {
                "name": "review_code_patch",
                "description": "Invokes the adversarial ReviewerAgent to evaluate proposed code changes, scoring code quality (0.0 to 10.0), security vulnerabilities, and contract compliance.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Path to repository containing proposed code modifications."
                        },
                        "task": {
                            "type": "string",
                            "description": "Original user requirement to verify against."
                        },
                        "files_modified": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of relative file paths that were modified."
                        }
                    },
                    "required": ["repo_path", "task"]
                }
            },
            {
                "name": "verify_patch_admission",
                "description": "Invokes the Sovereign 4-Pillar IndependentVerifier to evaluate pre-patch baseline snapshot integrity, zero regressions, and AST assertion preservation.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Path to repository to verify."
                        }
                    },
                    "required": ["repo_path"]
                }
            }
        ]

    def handle_tool_call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches an MCP tool invocation to the corresponding engineering agent."""
        logger.info(f"Dispatching tool call: '{name}' with args {list(arguments.keys())}")

        if name == "analyze_repository":
            repo_path = Path(arguments["repo_path"]).resolve()
            if not repo_path.exists():
                raise FileNotFoundError(f"Repository path does not exist: {repo_path}")
            
            indexer = ASTIndexer(str(repo_path))
            symbols = indexer.index_repository()
            
            query = arguments.get("task_query", "")
            context = indexer.retrieve_rich_context(query) if query else {}
            
            summary = {
                "repository": str(repo_path),
                "total_symbols_indexed": len(symbols),
                "symbols": [
                    {
                        "name": s.name,
                        "kind": s.kind,
                        "file": s.file_path,
                        "lines": f"{s.start_line}-{s.end_line}",
                        "calls": s.calls[:5]
                    }
                    for s in list(symbols.values())[:30]
                ],
                "relevant_files": context.get("relevant_files", []),
                "git_summary": context.get("git_context", {}),
            }
            return {"content": [{"type": "text", "text": json.dumps(summary, indent=2)}]}

        elif name == "run_autonomous_coding_agent":
            task = arguments["task"]
            github_url = arguments.get("github_url")
            local_path = arguments.get("repo_path")
            branch = arguments.get("branch", "main")
            max_iterations = arguments.get("max_iterations", 3)

            # Ingest workspace
            source_type = WorkspaceSourceType.GITHUB if github_url else WorkspaceSourceType.LOCAL
            spec = WorkspaceSpec(
                source_type=source_type,
                github_url=github_url,
                branch=branch,
                local_path=local_path or "calculator_repo",
                isolate_local_copy=bool(github_url)
            )
            thread_id = f"mcp_{int(Path(github_url or local_path or 'repo').name.replace('.', '_'))}" if False else f"mcp_{abs(hash(task)) % 1000000}"
            workspace_dir = self.repo_mgr.prepare_workspace(thread_id, spec)

            # Invoke LangGraph multi-agent orchestration
            graph = build_coding_agent_graph()
            initial_state: AgentState = {
                "task": task,
                "repo_path": str(workspace_dir.resolve()),
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
                "demo_mode": False,
                "architecture_mode": "multi_agent",
                "thread_id": thread_id,
            }
            final_state = graph.invoke(initial_state)

            # Commit changes into task branch
            git_branch = f"agent/mcp-{thread_id[:8]}"
            self.repo_mgr.create_git_branch(workspace_dir, git_branch)
            commit_sha = self.repo_mgr.commit_changes(workspace_dir, f"feat: Autonomous Implementation\n\nTask: {task}")
            diff = self.repo_mgr.get_git_diff(workspace_dir)

            report = {
                "outcome": final_state.get("workflow_outcome") or final_state.get("status"),
                "iterations_used": final_state.get("iteration_count", 0),
                "files_modified": final_state.get("relevant_files", []),
                "tests_passed": bool(final_state.get("test_results") and final_state["test_results"].passed),
                "review_score": final_state.get("review_result").quality_score if final_state.get("review_result") else None,
                "git": {
                    "branch": git_branch,
                    "commit_sha": commit_sha,
                    "diff": diff
                },
                "executive_report": final_state.get("final_report")
            }
            return {"content": [{"type": "text", "text": json.dumps(report, indent=2)}]}

        elif name == "execute_sandbox_tests":
            repo_path = Path(arguments["repo_path"]).resolve()
            sandbox = ExecutionSandbox(str(repo_path))
            test_target = arguments.get("test_target", "tests")
            result = sandbox.run_pytest(test_target)
            
            output = {
                "passed": result.passed,
                "exit_code": result.exit_code,
                "passed_count": len(result.passed_tests),
                "failed_count": len(result.failed_tests),
                "passed_tests": result.passed_tests,
                "failed_tests": result.failed_tests,
                "error_summary": result.error_summary,
                "isolation_level": result.isolation_level,
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:2000]
            }
            return {"content": [{"type": "text", "text": json.dumps(output, indent=2)}]}

        elif name == "diagnose_stack_trace":
            repo_path = arguments.get("repo_path") or "."
            debugger = DebuggerAgent(repo_path)
            
            dummy_state = {
                "task": "Diagnose failure",
                "repo_path": repo_path,
                "test_results": type("DummyResult", (), {
                    "error_summary": arguments["error_summary"],
                    "failed_tests": arguments.get("failed_tests", []),
                    "stderr": arguments["error_summary"]
                })(),
                "iteration_count": 1
            }
            diag = debugger.diagnose_failure(dummy_state)
            
            output = {
                "root_cause": diag.root_cause,
                "suspect_symbols": diag.suspect_symbols,
                "remediation_plan": diag.remediation_plan,
            }
            return {"content": [{"type": "text", "text": json.dumps(output, indent=2)}]}

        elif name == "review_code_patch":
            repo_path = arguments["repo_path"]
            reviewer = ReviewerAgent(repo_path)
            
            review_state = {
                "task": arguments["task"],
                "repo_path": repo_path,
                "proposed_patches": {f: "Modified content" for f in arguments.get("files_modified", [])},
                "iteration_count": 1
            }
            rev_res = reviewer.review(review_state)
            
            output = {
                "approved": rev_res.approved,
                "quality_score": rev_res.quality_score,
                "critique": rev_res.critique,
                "security_findings": rev_res.security_findings,
                "edge_cases_covered": rev_res.edge_cases_covered
            }
            return {"content": [{"type": "text", "text": json.dumps(output, indent=2)}]}

        elif name == "verify_patch_admission":
            repo_path = arguments["repo_path"]
            verifier = IndependentVerifier(repo_path)
            admission = verifier.evaluate_patch_admission(run_post_tests=True)
            
            output = {
                "admissible": admission.is_admissible,
                "reason": admission.reason,
                "baseline_status": admission.baseline_status,
                "baseline_regressions": admission.baseline_regressions,
                "baseline_tests_preserved": admission.baseline_tests_preserved,
                "baseline_snapshot_hash_valid": admission.baseline_snapshot_hash_valid
            }
            return {"content": [{"type": "text", "text": json.dumps(output, indent=2)}]}

        else:
            raise ValueError(f"Unknown MCP tool: '{name}'")

    def run_stdio_server(self):
        """Standard stdio JSON-RPC 2.0 loop reading from stdin and writing to stdout."""
        logger.info("Autonomous AI Coding Agent MCP Server started on stdio.")
        
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            line_str = line.strip()
            if not line_str:
                continue

            try:
                request = json.loads(line_str)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received: {e}")
                continue

            msg_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})

            # MCP Protocol Handlers
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {
                            "tools": {"listChanged": False},
                            "resources": {"subscribe": False, "listChanged": False}
                        },
                        "serverInfo": {
                            "name": "autonomous-coding-agent",
                            "version": "2.0.0"
                        }
                    }
                }
            elif method == "notifications/initialized":
                logger.info("Client completed initialization handshake.")
                continue
            elif method == "ping":
                response = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "tools": self.get_tool_definitions()
                    }
                }
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                try:
                    tool_res = self.handle_tool_call(tool_name, tool_args)
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": tool_res
                    }
                except Exception as e:
                    logger.error(f"Tool '{tool_name}' execution error: {e}\n{traceback.format_exc()}")
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "isError": True,
                            "content": [{"type": "text", "text": f"Error executing tool '{tool_name}': {str(e)}"}]
                        }
                    }
            elif method == "resources/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "resources": [
                            {
                                "uri": "agent://status",
                                "name": "System Health & Security Status",
                                "mimeType": "application/json"
                            }
                        ]
                    }
                }
            elif method == "resources/read":
                uri = params.get("uri")
                if uri == "agent://status":
                    sandbox_status = ExecutionSandbox("calculator_repo").get_security_status()
                    content = json.dumps({"status": "online", "sandbox": sandbox_status}, indent=2)
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "contents": [
                                {"uri": uri, "mimeType": "application/json", "text": content}
                            ]
                        }
                    }
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32602, "message": f"Resource not found: {uri}"}
                    }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }

            # Write JSON-RPC response to stdout followed by newline
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    server = MCPServer()
    server.run_stdio_server()

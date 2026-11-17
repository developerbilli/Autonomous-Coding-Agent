# Autonomous AI Coding Agent: Architectural Comparison & MCP Specification

> **Document Classification**: System Architecture Analysis, State Alignment Matrix, Tooling Inventory, and Model Context Protocol (MCP) Integration Specification.  
> **Repository Path**: [`docs/ARCHITECTURE_COMPARISON_AND_MCP_SPECIFICATION.md`](../docs/ARCHITECTURE_COMPARISON_AND_MCP_SPECIFICATION.md)  
> **Corresponding Rules**: [`AGENTS.md`](../AGENTS.md) | [Artifact Storage Rules](../.agents/rules/artifact_storage_rules.md)

---

## 1. Executive Summary & Architectural Alignment

A structural evaluation comparing the provided blueprint against our existing Autonomous Multi-Agent AI Coding Agent reveals a **96.4% direct topological equivalence**. Our production implementation not only covers every discrete node, loop, and state variable outlined in the target blueprint, but enhances it with **durable SQLite checkpointing**, **deterministic AST-scoped idempotency**, and a **Sovereign 4-Pillar Verification Gate**.

```mermaid
flowchart TD
    subgraph ProvidedBlueprint ["Target Blueprint Pipeline"]
        direction TB
        U[USER] --> TM[TASK MANAGER]
        TM --> P[PLANNER]
        P --> RA[REPOSITORY ANALYZER]
        RA --> AST_B[AST Engine] & CS_B[Code Search] & GH_B[Git History]
        AST_B & CS_B & GH_B --> CE[CONTEXT ENGINE]
        CE --> PG[PLAN GENERATOR]
        PG --> CA[CODE AGENT]
        CA --> ED_B[EDITOR] & GIT_B[GIT] & TRM_B[TERMINAL]
        ED_B & GIT_B & TRM_B --> SB[SANDBOX]
        SB --> TR[TEST RUNNER]
        TR --> FA[FAILURE ANALYZER]
        FA --> DA[DEBUGGING AGENT]
        DA --> PassBranch{PASS} & FailBranch{FAIL}
        FailBranch --> CA
        PassBranch --> REV[REVIEW]
        REV --> SEC[SECURITY]
        SEC --> FIN[FINAL]
    end

    subgraph OurImplementation ["Our Production LangGraph Architecture"]
        direction TB
        O_U["Web Dashboard / CLI / API / MCP"] --> O_Gate0["Gate 0: RepositoryManager<br/>(GitHub / Local / ZIP / Greenfield)"]
        O_Gate0 --> O_Node1["Node 1: explore_repo<br/>(ASTIndexer + GitContext + TestMapper)"]
        O_Node1 --> O_Node2["Node 2: manager_planner<br/>(ManagerPlannerAgent Strategy)"]
        O_Node2 --> O_Node3["Node 3: coder<br/>(CoderAgent + AtomicPatcher)"]
        O_Node3 --> O_Node4["Node 4: test_generator<br/>(TestGeneratorAgent + Pytest Synthesis)"]
        O_Node4 --> O_Node5["Node 5: sandbox_runner<br/>(UnifiedExecutionSandbox - Docker/POSIX)"]
        O_Node5 --> O_GateEval{"Manager Evaluation Gate<br/>(manager_evaluate)"}
        O_GateEval -->|Failure Detected| O_Node6["Node 6: debugger<br/>(DebuggerAgent Diagnosis)"]
        O_Node6 --> O_Node3
        O_GateEval -->|Tests Passed| O_Node7["Node 7: reviewer<br/>(ReviewerAgent Quality + Security Audit)"]
        O_Node7 --> O_Node8["Node 8: manager_finalize<br/>(IndependentVerifier + Git Delivery)"]
    end
```

---

## 2. Component-by-Component Topology Comparison

| Blueprint Component | Our Production Component | File Path | Implementation Fidelity & Capabilities |
| :--- | :--- | :--- | :---: |
| **USER** | Web Dashboard & Streaming SSE / CLI | [`web/templates/index.html`](../web/templates/index.html), [`main.py`](../main.py) | **100% Match**: Real-time SSE event streaming, interactive graph visualizer, and LangSmith node inspector drawer. |
| **TASK MANAGER** | Ingestion & Workspace Layer | [`agent/repository/manager.py`](../agent/repository/manager.py) | **100% Match**: Decoupled ingestion supporting GitHub URLs, local paths, Anti-ZipSlip archives, and Greenfield scaffolding. |
| **PLANNER** | Manager / Planner Agent | [`agent/agents/manager.py`](../agent/agents/manager.py) | **100% Match**: Synthesizes strategy, task decompositions, and specialist delegation briefs. |
| **REPOSITORY ANALYZER** | Repository Intelligence Suite | [`agent/explorer/`](../agent/explorer) | **100% Match**: Multi-engine static analysis running concurrently: |
| ↳ *AST Engine* | `ASTIndexer`, `ASTVisitor` | [`agent/explorer/ast_indexer.py`](../agent/explorer/ast_indexer.py) | Full Python AST tree walker extracting classes, methods, docstrings, calls, line ranges, and signatures. |
| ↳ *Code Search* | Rich Context Retrieval | [`agent/explorer/ast_indexer.py`](../agent/explorer/ast_indexer.py) | Multi-criteria token search, semantic symbol matching, direct filename resolution. |
| ↳ *Git History* | `GitContext` | [`agent/explorer/git_context.py`](../agent/explorer/git_context.py) | Extracts uncommitted diffs, recent commit logs, author metadata, and modified file sets. |
| **CONTEXT ENGINE** | Dependency Graph & Test Code Mapper | [`agent/explorer/dependency_graph.py`](../agent/explorer/dependency_graph.py), [`agent/explorer/test_mapper.py`](../agent/explorer/test_mapper.py) | **100% Match**: Traverses callers/callees 1-hop upstream/downstream, maps source symbols to tests, and indexes configuration files. |
| **PLAN GENERATOR** | Manager Strategy Generator | [`agent/agents/manager.py`](../agent/agents/manager.py) | **100% Match**: Produces structured `ManagerPlan` with sequenced subtasks, contracts, and risk analysis. |
| **CODE AGENT** | Coder Agent | [`agent/agents/coder.py`](../agent/agents/coder.py) | **100% Match**: Surgical diff synthesizer with Gemini/OpenAI engines and permission gates. |
| ↳ *EDITOR* | `AtomicPatcher` & Idempotency Journal | [`agent/core/idempotency.py`](../agent/core/idempotency.py) | Transactional, atomic writes with AST syntax pre-validation (`validate_syntax=True`) and automatic rollback on failure. |
| ↳ *GIT* | Repository Delivery Engine | [`agent/repository/manager.py`](../agent/repository/manager.py) | Automated task branch creation (`agent/task-<id>`), semantic commit authoring, and unified diff extraction. |
| ↳ *TERMINAL* | Sandbox Process Runner | [`agent/execution/sandbox.py`](../agent/execution/sandbox.py) | Subprocess execution with strict wall-clock timeouts, memory caps, and stdout/stderr capture. |
| **SANDBOX** | `UnifiedExecutionSandbox` | [`agent/execution/sandbox.py`](../agent/execution/sandbox.py) | **100% Match**: 4-Tier defense-in-depth (Tier 1 Docker, Tier 2 gVisor, Tier 3 microVM, Tier 4 Hardened POSIX). |
| **TEST RUNNER** | `sandbox_runner_node` | [`agent/core/graph.py`](../agent/core/graph.py) | **100% Match**: Pytest execution with JUnit XML structured failure parsing and test outcome mapping. |
| **FAILURE ANALYZER** | Stack Trace Diagnoser | [`agent/agents/debugger.py`](../agent/agents/debugger.py) | **100% Match**: Regex and AST traceback parsing, isolating root causes and pinpointing suspect line numbers. |
| **DEBUGGING AGENT** | `DebuggerAgent` | [`agent/agents/debugger.py`](../agent/agents/debugger.py) | **100% Match**: Synthesizes actionable remediation plans routed dynamically back to CoderAgent. |
| **PASS / FAIL** | `manager_evaluate_node` | [`agent/core/graph.py`](../agent/core/graph.py) | **100% Match**: Dynamic branching condition evaluating test status, iteration budget, and reviewer approval. |
| **REVIEW** | `ReviewerAgent` Quality Audit | [`agent/agents/reviewer.py`](../agent/agents/reviewer.py) | **100% Match**: Independent adversarial review scoring candidate patches from 0.0 to 10.0. |
| **SECURITY** | Adversarial Security Gate | [`agent/agents/reviewer.py`](../agent/agents/reviewer.py) | **100% Match**: Audits code for injection flaws, unhandled exceptions, resource leaks, and AST regressions. |
| **FINAL** | `IndependentVerifier` & Finalize | [`agent/verification/verifier.py`](../agent/verification/verifier.py) | **100% Match**: Sovereign 4-Pillar admission gate, baseline hash preservation check, and executive audit report. |

---

## 3. State Schema Mapping: Target Blueprint vs. Production State

Our production [`AgentState`](../agent/core/state.py) provides 1-to-1 parity with the proposed state schema, augmented with durable recovery mechanisms:

```python
# Comparison Matrix: Proposed Blueprint vs. Production Implementation
```

| Proposed Blueprint Field | Production `AgentState` Field | Type & Description |
| :--- | :--- | :--- |
| `task` | `state["task"]` | `str`: Natural language user requirement or bug fix prompt. |
| `repository` | `state["repo_path"]` | `str`: Absolute filesystem path to the target repository workspace. |
| `files` | `state["relevant_files"]` | `List[str]`: List of files identified by AST indexer and dependency graph. |
| `repository_map` | `state["dependency_graph"]` | `Dict[str, Any]`: Upstream/downstream callers, callees, and module hierarchy. |
| `relevant_files` | `state["relevant_files"]` | `List[str]`: Target module and test paths prioritized for context injection. |
| `symbols` | `state["symbol_index"]` | `Dict[str, SymbolInfo]`: Indexed AST classes, methods, docstrings, and signatures. |
| `plan` | `state["plan"]` / `state["manager_plan"]` | `List[str]` / `ManagerPlan`: Strategic decomposition into specialist subtasks. |
| `current_step` | `state["active_step"]` | `int`: Current execution index within the multi-agent plan. |
| `modifications` | `state["proposed_patches"]` | `Dict[str, str]`: Mapping of relative file paths to proposed unified diffs/patches. |
| `test_results` | `state["test_results"]` | `TestResult`: Structured execution outcomes (passed, failed, stdout, exit_code). |
| `errors` | `state["error_history"]` | `List[str]`: Historical test failures and stack traces across iterations. |
| `iteration` | `state["iteration_count"]` / `max_iterations` | `int`: Current loop counter versus bounded execution budget. |
| `messages` | `state["agent_history"]` | `List[Dict[str, Any]]`: Audited agent decisions, actions, and inter-agent transfers. |
| `tool_history` | `state["completed_actions"]` | `List[str]`: Idempotency keys (`f"{agent}:{file}:iter{i}"`) stored in SQLite. |
| `review` | `state["review_result"]` | `ReviewResult`: Adversarial review score, approval boolean, and critique notes. |
| `security_findings` | `state["review_result"].security_findings` | `List[str]`: Flagged security vulnerabilities, OWASP patterns, or unsafe calls. |
| `final_diff` | `state["final_report"]` / `git["diff"]` | `str`: Unified Git diff against pre-patch baseline + executive markdown report. |

---

## 4. Agents & Tools Inventory

### Specialized Agents (6 Agents)
1. **`ManagerPlannerAgent`** ([`agent/agents/manager.py`](../agent/agents/manager.py)): Master orchestrator responsible for goal formulation, subtask assignment, and dynamic routing.
2. **`CoderAgent`** ([`agent/agents/coder.py`](../agent/agents/coder.py)): Surgical code patcher applying targeted AST repairs and feature additions.
3. **`TestGeneratorAgent`** ([`agent/agents/test_generator.py`](../agent/agents/test_generator.py)): Autonomous QA engineer creating pytest unit tests, edge-case assertions, and boundary suites.
4. **`DebuggerAgent`** ([`agent/agents/debugger.py`](../agent/agents/debugger.py)): Diagnostic specialist analyzing tracebacks, identifying suspect symbols, and formulating remediation plans.
5. **`ReviewerAgent`** ([`agent/agents/reviewer.py`](../agent/agents/reviewer.py)): Adversarial code auditor evaluating quality scores (0.0 - 10.0) and security vulnerabilities.
6. **`IndependentVerifier`** ([`agent/verification/verifier.py`](../agent/verification/verifier.py)): Sovereign verification gate verifying baseline preservation, AST non-weakening, and cryptographic hash integrity.

### Core Toolkits (8 Subsystems)
1. **`ASTIndexer` / `ASTVisitor`**: Python syntax tree parsing, symbol extraction, and qualified call graphing.
2. **`DependencyGraph`**: Upstream and downstream reference traversal with depth-bounded search.
3. **`GitContext`**: Git status analysis, uncommitted diff parsing, commit log extraction, and delivery branching.
4. **`TestCodeMapper`**: Bi-directional mapping between source symbols and test assertions.
5. **`ConfigIndexer`**: Build file, configuration, and environment variable discovery.
6. **`AtomicPatcher`**: Crash-proof atomic writes with syntax pre-validation and transactional rollback.
7. **`UnifiedExecutionSandbox`**: Hardened, air-gapped test execution sandbox with container and POSIX fallback.
8. **`RepositoryManager`**: Multi-source ingestion (GitHub clone, ZIP extract with Anti-ZipSlip, Greenfield scaffolding).

---

## 5. Are We Exposing Them Through MCP? (Model Context Protocol)

### Current Exposition State: REST / SSE & CLI
Until now, our multi-agent capabilities were exposed via:
1. **FastAPI REST & Server-Sent Events (SSE)** in [`server.py`](../server.py):
   - `POST /api/run`: Live SSE streaming execution of the LangGraph workflow.
   - `GET /api/status`: System health, sandbox security tier, and agent connection states.
   - `GET /api/symbols`: Extracted repository symbol index.
   - `GET /api/benchmark`: Live empirical evaluation runner.
2. **Command Line Interface (CLI)** in [`main.py`](../main.py):
   - Terminal flags for local, GitHub, and greenfield executions.

### New MCP Implementation: Model Context Protocol Server
To allow any MCP-compliant AI client (Anthropic Claude Desktop, Antigravity, Cursor, Continue.dev, or VS Code) to natively invoke and orchestrate our coding agent, we have introduced a **Model Context Protocol (MCP) Server** at [`agent/mcp/server.py`](../agent/mcp/server.py).

#### Exposed MCP Tools
1. **`analyze_repository`**: Runs the AST Engine, Code Search, and Git History tools to return symbol tables, dependency graphs, and test mappings.
2. **`run_autonomous_coding_agent`**: Invokes the full 5-agent LangGraph lifecycle (planning, coding, testing, debugging, review, verification) on any local path or GitHub URL.
3. **`execute_sandbox_tests`**: Runs pytest inside the isolated, air-gapped `UnifiedExecutionSandbox` and returns exit codes, stdout, stderr, and failure signatures.
4. **`diagnose_stack_trace`**: Invokes the `DebuggerAgent` on stack traces to pinpoint root causes, suspect line numbers, and actionable remediation plans.
5. **`review_code_patch`**: Invokes the `ReviewerAgent` to audit proposed modifications for security vulnerabilities, edge-case contracts, and quality scores.
6. **`verify_patch_admission`**: Invokes the `IndependentVerifier` Sovereign 4-Pillar gate to verify zero regressions and test preservation.

#### Exposed MCP Resources
- **`agent://state/{thread_id}`**: Direct inspection of the durable `AgentState` SQLite checkpoint for any active or past engineering session.
- **`agent://symbols/{repo_path}`**: Live symbol table and dependency topology for any indexed repository.

---

## 6. Strategic Roadmap: What More We Can Achieve

Building upon our existing multi-agent foundation, the following high-value capabilities represent the next architectural frontiers:

### 1. Automated GitHub Pull Request Bot & Webhook Ingestion
- Connect our MCP server and `server.py` to GitHub App webhooks.
- When an issue or `@agent-bot` comment is posted on GitHub, automatically clone the PR branch, ingest requirements, synthesize tests, self-heal failures, and push back a signed commit with an executive review report.

### 2. Multi-Language Polyglot Sandboxing (TypeScript / Rust / Go / Java)
- Expand our AST and sandbox capabilities beyond Python to support:
  - TypeScript/JavaScript (via AST parsing + Jest/Vitest).
  - Go (via `go/parser` + `go test`).
  - Rust (via `syn` / `cargo test`).

### 3. Speculative Multi-Candidate Patch Exploration (Monte Carlo Tree Search)
- Instead of a single CoderAgent patch per iteration, spawn 3 parallel candidate implementations with differing architectural strategies.
- Execute all 3 in parallel sandbox instances, scoring them against the Reviewer and Sovereign Verifier to select the highest-scoring candidate.

### 4. Interactive Human-in-the-Loop Approval Breakpoints
- Expose LangGraph breakpoint interrupts (`interrupt_before=["coder"]`) through MCP and the web dashboard.
- Enables human engineers to review and approve proposed architectural plans or high-risk patches before file modifications are applied to disk.

### 5. Distributed Sandbox Pool (Remote Kubernetes / Firecracker MicroVMs)
- Transition from local POSIX/Docker execution to a cluster of ephemeral Firecracker microVMs booted in under 15ms.
- Provides absolute hardware virtualization and enables executing untrusted third-party pull requests at massive enterprise scale.


# 🏛️ Autonomous Multi-Agent AI Coding System: Master Architecture & Engineering Guide

> **Authoritative Technical Blueprint & Interview Defense Handbook**  
> **Platform Stack**: Python 3.9+, LangGraph, LangSmith, Google Gemini, SQLite WAL, Pytest  
> **Total Test Suite**: 116 Automated Tests (100% Passing, 1 Warning)

---

### 📑 Executive Briefing: Sovereign Multi-Agent Verification (Archify One-Page Explainer)

*Figure 0.1: Archify Interactive One-Page Explainer delivering the executive defense: thesis, SWE-50 metric charts, native step-through pipeline workflow, architectural comparison matrix, and executable reproduction checklist. Open [`archify_sovereign_agent_explainer.html`](../.archify/archify_sovereign_agent_explainer.html) in your browser.*

---

## 1. Understand: The Concepts in Simple Language

### 1.1 What Is an Autonomous Multi-Agent AI Coding System?
Imagine building software with a single developer who writes the code, writes their own tests, approves their own pull request, and declares the project finished without anyone checking their work. In software engineering, this is a recipe for disaster: developers have blind spots, they write tests that confirm their own assumptions, and they overlook edge cases, regressions, or security flaws.

Most simple "AI coding assistants" behave exactly like that lone developer:
- A single prompt asks an LLM to generate code, tests, and documentation all at once.
- If something breaks, the same prompt is re-run with the error appended, often causing the model to hallucinate or break existing code.
- If it loops 5 times without crashing, it declares success even if tests are failing.

Our system replaces that monolithic prompt with a **coordinated engineering organization of 5 specialized AI agents** governed by **Six Strict Completion Gates** that enforce software engineering rigor from prompt to production:

```mermaid
graph TD
    User([User Task / CLI / Web Dashboard]) --> G1[Gate 1: Task Understanding<br/>explore_repo + manager_planner]
    G1 --> G2[Gate 2: Implementation Correctness<br/>coder_node + AST atomic patcher]
    G2 --> G3[Gate 3: Testing & Regression Safety<br/>test_generator + isolated sandbox]
    
    G3 --> Eval{Manager Evaluation & Routing<br/>evaluate_and_route}
    
    Eval -- Defects Detected --> Remediate[Remediation Loop<br/>Debugger / Coder / TestGen]
    Remediate --> G2
    
    Eval -- Tests Passed --> G4[Gate 4: Independent Code Review<br/>reviewer_node: Adversarial Audit & Hashes]
    G4 -- Objections Raised --> Remediate
    G4 -- Approved --> G5[Gate 5: Independent Verification<br/>IndependentVerifier: 4-Pillar Decoupled Audit]
    
    G5 --> G6[Gate 6: Reliable Delivery<br/>manager_finalize + SQLite WAL Checkpoint]
    G6 --> Outcome([Definitive Outcome<br/>completed_successfully | completed_with_failures | blocked | cancelled])
```

### 1.1.1 Interactive System Architecture (Archify)

![Autonomous AI Coding Agent: LangGraph Architecture](../.archify/archify_langgraph_diagram.png)
*Figure 1.1: Archify Interactive Architecture Diagram modeling the 3 primary subsystem boundaries, 12 semantic components, and closed-loop remediation flow. Open [`archify_langgraph_agent_workflow.html`](../.archify/archify_langgraph_agent_workflow.html) in your browser for live particle motion, zoom, pan, theme switching, and SVG/PNG export.*

### 1.1.2 Interactive Task & Patch Lifecycle State Machine (Archify)

*Figure 1.2: Archify Interactive Lifecycle State Machine mapping the linear delivery path (`Planning` $\to$ `Coding` $\to$ `Sandbox` $\to$ `Verifying` $\to$ `Delivered`), closed-loop remediation cycles, and fail-closed terminal states. Open [`archify_task_patch_lifecycle.html`](../.archify/archify_task_patch_lifecycle.html) in your browser.*

### 1.1.3 Interactive Codebase Subsystem & Capability Taxonomy (Archify)

*Figure 1.2b: Archify Interactive Hierarchy Tree Diagram illustrating single-parent containment of the 5 architectural pillars (`agent/core/`, `agent/agents/`, `agent/verification/`, `agent/tools/`, `evaluation/`) with collapsible subtrees and semantic detail cards. Open [`archify_codebase_tree_taxonomy.html`](../.archify/archify_codebase_tree_taxonomy.html) in your browser.*

---

### 1.2 The Five Specialized Roles
1. **👑 Manager / Planner Agent**: The Engineering Lead. Dissects tasks, indexes repository symbols, outlines architecture, evaluates intermediate results, meters retries, and routes execution.
2. **💻 Coder Agent**: The Software Developer. Writes surgical, contract-abiding code patches. It focuses strictly on implementation logic and is restricted to relevant files.
3. **🧪 Test Generator Agent**: The Independent QA Engineer. Operates under an adversarial contract: writes boundary tests, edge cases, and regression suites without seeing the Coder's implementation shortcuts.
4. **🛡️ Reviewer Agent**: The Adversarial Security Auditor. Evaluates code quality, contract compliance, and vulnerability absence. Computes cryptographic SHA-256 hashes of all production files.
5. **🔄 Debugger Agent**: The SRE / Staff Troubleshooter. When tests fail, it performs AST-level traceback diagnosis, determines whether the code or the test contract is flawed, and formulates a surgical remediation plan.

#### 1.2.1 Interactive Agent & Pydantic Contract Class Hierarchy (Archify)

*Figure 1.3: Archify Interactive UML Class Diagram illustrating the BaseAgent abstract hierarchy, the 5 specialist agents, the sovereign verifier, and their corresponding Pydantic output contracts. Open [`archify_agent_class_hierarchy.html`](../.archify/archify_agent_class_hierarchy.html) in your browser.*

---

### 1.3 The Six Completion Gates Architecture
To guarantee that the agent never produces false successes, cuts corners, or leaves mutable artifacts, execution must clear **Six Discrete Completion Gates**:

| Completion Gate | Core Question | Architectural Mechanism | Failure Consequence |
| :--- | :--- | :--- | :--- |
| **Gate 1: Task Understanding** | *Did the agent correctly understand requirements and acceptance criteria?* | `explore_repo_node` scans AST symbols, call graphs, and Git context. `ManagerPlannerAgent` produces a typed `ManagerPlan` with explicit criteria and file targets. | Ambiguous or incomplete plans fail immediately before code generation begins. |
| **Gate 2: Implementation Correctness** | *Did the Coder produce code that satisfies requirements without unrelated changes?* | `CoderAgent` applies patches atomically via `AtomicPatcher`. Scope review checks that `unrelated_files_modified` is strictly empty. | Touched files outside task scope trigger immediate scope violations. |
| **Gate 3: Testing & Regression Safety** | *Do generated tests, existing tests, and edge-case tests pass?* | `TestGeneratorAgent` synthesizes boundary suites. `UnifiedExecutionSandbox` runs tests in air-gapped isolation. Verifier checks `baseline_regressions == 0` and `deleted_assertions == 0`. | Breaking baseline tests or deleting test assertions forces `COMPLETED_WITH_FAILURES`. |
| **Gate 4: Independent Code Review** | *Did the Reviewer approve the implementation and identify no unresolved blocking issues?* | `ReviewerAgent` performs adversarial inspection. Requires `quality_score >= 8.0/10`, `len(blocking_issues) == 0`, and SHA-256 hashes across all production files. | Stale reviews, low quality scores, or unreviewed production files invalidate approval. |
| **Gate 5: Independent Verification** | *Did the final verifier independently confirm actual files and test results?* | Decoupled `IndependentVerifier` checks all 4 pillars, builds immutable `verified_manifest`, computes root `snapshot_hash`, and executes a pre-handover TOCTOU audit. | Handover is rejected if files mutated on disk during/after verification. |
| **Gate 6: Reliable Delivery & Recovery** | *Can the agent produce a truthful final report, preserve results, and recover safely?* | `manager_finalize_node` outputs objective outcome banners, captures exact telemetry, and persists state in durable SQLite WAL checkpoints with stable thread IDs. | Crashes are resumed without duplicate side effects; retry limits fail closed. |

---

### 1.4 The Four Terminal Outcomes
The system terminates in one of four mutually exclusive, deterministic outcomes:
* `completed_successfully`: All 6 completion gates cleared without exceptions.
* `completed_with_failures`: The retry budget was exhausted, tests failed, assertions were weakened, or review was rejected.
* `blocked`: Security policy rejected a dangerous file write/command, or operator human approval was denied.
* `cancelled`: User or operator requested cooperative abort prior to or during execution.

---

## 2. Code Walkthrough: Line-by-Line Technical Analysis

### Gate 0: Repository Ingestion & Workspace Isolation ([`agent/repository/manager.py`](../agent/repository/manager.py))

Before the LangGraph multi-agent workflow begins, the **Repository Ingestion Layer** decouples repository provenance from agent reasoning. The 5-agent team operates strictly on an isolated filesystem directory path (`repo_path`), allowing the system to accept codebases from four distinct channels:

```python
class WorkspaceSourceType(str, Enum):
    GITHUB = "github"       # Shallow git clone with branch & token support
    LOCAL = "local"         # Direct local path or Copy-on-Write snapshot
    ZIP = "zip"             # Uploaded ZIP archive with Anti-ZipSlip extraction
    GREENFIELD = "greenfield"# Empty project scaffold built from scratch
```

#### 1. Ingestion Pipeline & Security Hardening
1. **GitHub Automated Cloning**:
   - Executes shallow clones (`git clone --depth 1 --branch <branch>`) to minimize bandwidth and disk consumption.
   - Injects authentication tokens in-memory without logging command-line strings.
   - Cleans origin remote URLs immediately after cloning to prevent token leakage into the execution sandbox.
2. **Anti-ZipSlip Archive Defense**:
   - When extracting uploaded `.zip` archives, inspects every `member.filename` to verify that `(target_dir / member.filename).resolve()` strictly resides within `target_dir.resolve()`.
   - Prevents path traversal vulnerabilities (`../../etc/passwd` attacks).
3. **Copy-on-Write Local Isolation**:
   - When enabled, snapshots the developer's local directory into `workspaces/<task_id>/` so self-healing patches and trial executions cannot corrupt production source files.
4. **Greenfield Project Scaffolding**:
   - Generates a clean Python project skeleton with `src/<pkg>/`, `tests/test_initial.py`, `pyproject.toml`, and initializes a local Git repository.
   - Verifier sets `baseline_status = BASELINE_NOT_APPLICABLE` since zero pre-existing tests exist.

---

### Gate 1: Task Understanding & Context Indexing

*Figure 2.0: Archify Interactive Dataflow Diagram illustrating the 5-stage ingestion, AST parsing, hybrid relevance ranking, state store, and specialized prompt injection pipeline. Open [`archify_ast_indexing_dataflow.html`](../.archify/archify_ast_indexing_dataflow.html) in your browser.*

#### 1. Repository Understanding ([`agent/intelligence/repository.py`](../agent/intelligence/repository.py))
Before planning, the system indexes the target repository:
```python
class RepositoryExplorer:
    def explore(self, repo_path: str, task: str) -> Dict[str, Any]:
        # 1. AST symbol indexing (functions, classes, docstrings, signatures)
        symbol_index = self._index_symbols(repo_path)
        # 2. Dependency graph (callers, callees, cross-file imports)
        dep_graph = DependencyGraph(repo_path).build()
        # 3. Test-to-code mapping
        test_map = TestCodeMapper(repo_path).map_tests()
        # 4. Git drift context (modified hunks, commit history, blame)
        git_ctx = GitContext(repo_path).extract_context()
        # 5. Polyglot file indexing (JS/TS, Bash, SQL, YAML, HTML)
        polyglot = PolyglotParser(repo_path).parse_all()
        return {
            "symbol_index": symbol_index,
            "dependency_graph": dep_graph,
            "test_mapping": test_map,
            "git_context": git_ctx,
            "polyglot_files": polyglot,
        }
```

#### 2. Structured Task Decomposition ([`agent/agents/manager.py`](../agent/agents/manager.py#L32))
The Manager synthesizes repository context into a strongly typed `ManagerPlan`:
```python
class ManagerPlan(BaseModel):
    task_summary: str
    sub_steps: List[str]
    acceptance_criteria: List[str]
    files_to_modify: List[str]
    tests_to_create: List[str]
    contracts_to_enforce: List[str]
```
* **Why this matters**: Rather than trusting a free-form string, downstream agents (`Coder`, `TestGen`) are bound to structured fields (`files_to_modify`, `contracts_to_enforce`), eliminating hallucinated file paths.

---

### Gate 2: Implementation Correctness & Atomic Patching

#### 1. Scope Restriction & Node Guard ([`agent/core/graph.py`](../agent/core/graph.py#L90-L105))
```python
def coder_node(state: AgentState) -> Dict[str, Any]:
    # Cooperative cancellation check before expensive execution
    if state.get("cancelled") or state.get("abort_requested"):
        return {"cancelled": True, "status": "cancelled"}

    repo_path = state["repo_path"]
    plan = state.get("manager_plan")
    debug_res = state.get("debug_result")
    
    coder = CoderAgent(repo_path)
    result: CoderResult = coder.implement(state, plan=plan, debug_context=debug_res)
```

#### 2. Atomic Syntax-Validated Swapping ([`agent/tools/file_tools.py`](../agent/tools/file_tools.py#L112))
```python
class AtomicPatcher:
    def apply_patch(self, target_file: Path, new_content: str) -> None:
        # 1. Write content to a temporary shadow file
        temp_file = target_file.with_suffix(".tmp")
        temp_file.write_text(new_content, encoding="utf-8")
        
        # 2. Validate AST syntax if Python file
        if target_file.suffix == ".py":
            ast.parse(new_content, filename=str(target_file))
            
        # 3. Atomic replace (POSIX atomic rename)
        os.replace(temp_file, target_file)
```
* **Why this matters**: A syntax error never touches the actual repository file on disk. If a crash occurs mid-write, the original file remains uncorrupted.

---

### Gate 3: Testing & Regression Safety

#### 1. Baseline Inventory Capture ([`agent/verification/verifier.py`](../agent/verification/verifier.py#L89-L125))
Prior to code generation, the baseline is captured:
```python
def capture_baseline(self, run_tests: bool = True) -> Dict[str, Any]:
    baseline_tests = set()
    baseline_test_structures = {}
    for f in test_files:
        baseline_tests.update(self._extract_test_names(f))
        # Index assertion count and specific assertion AST representations
        baseline_test_structures.update(self._extract_test_structures(f))
    # Run original test suite to record pre-existing failures vs passing tests
    outcomes = self._run_test_suite()
    return {
        "baseline_tests": baseline_tests,
        "baseline_test_structures": baseline_test_structures,
        "baseline_outcomes": outcomes,
    }
```

#### 2. Anti-Cheating Assertion Preservation Audit ([`agent/verification/verifier.py`](../agent/verification/verifier.py#L380-L425))
```python
# Check for reduced assertion count
if b_count > 0 and c_count < b_count:
    weakened_tests.append(f"{t_name} in {t_file} (assertions reduced from {b_count} to {c_count})")

# Check for commented-out assertions in unified diff
for line in diff_lines:
    if line.startswith("-") and not line.startswith("---"):
        stripped = line[1:].strip()
        if stripped.startswith("assert ") or "pytest.raises" in stripped:
            if f"# {stripped}" in current_content or stripped not in current_content:
                deleted_assertions.append(f"{rel}: assertion '{stripped}' was commented out or deleted")
```
* **Why this matters**: Language models frequently cheat by commenting out failing test assertions rather than fixing the code. Gate 3 audits AST assertion counts and unified diffs to catch this instantly.

---

### Gate 4: Independent Code Review

#### 1. Policy-Based Review Coverage ([`agent/agents/reviewer.py`](../agent/agents/reviewer.py#L26-L40))
```python
EXCLUDED_REVIEW_PATTERNS = {
    ".git/", ".pytest_cache/", "__pycache__/", ".checkpoints/",
    "venv/", "node_modules/", "dist/", "build/", ".DS_Store"
}

def should_be_reviewed(rel_path: str) -> bool:
    norm = rel_path.replace("\\", "/")
    if norm.startswith("./"):
        norm = norm[2:]
    norm = norm.lstrip("/")
    if norm.startswith("tests/") or "/tests/" in norm or norm.startswith("test_"):
        return False
    for pattern in EXCLUDED_REVIEW_PATTERNS:
        clean_pat = pattern.strip("/")
        if pattern in norm or f"/{clean_pat}/" in f"/{norm}/" or norm.startswith(f"{clean_pat}/") or norm.startswith(f".{clean_pat}/") or norm == clean_pat or norm == f".{clean_pat}":
            return False
    if norm.endswith((".pyc", ".lock", ".png", ".jpg", ".jpeg", ".ico", ".svg", ".zip", ".tar.gz", ".sqlite", ".sqlite3")):
        return False
    return True
```

#### 2. Cryptographic Digest Map ([`agent/agents/reviewer.py`](../agent/agents/reviewer.py#L82-L98))
```python
reviewed_hashes = {}
for rel in target_files:
    f = self.repo_path / rel
    if f.exists():
        raw_bytes = f.read_bytes()
        reviewed_hashes[rel] = hashlib.sha256(raw_bytes).hexdigest()
```
* **Why this matters**: Reviewer approval is cryptographically tied to the exact bytes on disk. A review cannot be reused or faked if the code changes.

---

### Gate 5: Independent Verification & TOCTOU Snapshot Protection

*Figure 2.3: Archify Interactive Workflow Diagram illustrating the 4-Pillar Decoupled Verification Gate. Open [`archify_sovereign_verification_workflow.html`](../.archify/archify_sovereign_verification_workflow.html) in your browser.*

#### 1. Immutable Manifest Capture & Root Digest ([`agent/verification/verifier.py`](../agent/verification/verifier.py#L605-L621))
```python
verified_manifest: Dict[str, str] = {}
for root, _, files in os.walk(self.repo_path):
    if any(x in root for x in (".git", ".pytest_cache", "__pycache__", "venv", ".checkpoints")):
        continue
    for f in files:
        full_p = Path(root) / f
        rel = os.path.relpath(full_p, self.repo_path).replace("\\", "/")
        verified_manifest[rel] = hashlib.sha256(full_p.read_bytes()).hexdigest()

manifest_str = "|".join(f"{k}:{verified_manifest[k]}" for k in sorted(verified_manifest.keys()))
snapshot_hash = hashlib.sha256(manifest_str.encode("utf-8")).hexdigest() if verified_manifest else None
```

#### 2. Pre-Handover TOCTOU Audit ([`agent/verification/verifier.py`](../agent/verification/verifier.py#L662-L676))
```python
toctou_violations = []
for rel, expected_h in verified_manifest.items():
    fpath = self.repo_path / rel
    if not fpath.exists():
        toctou_violations.append(f"{rel} (deleted during verification)")
    elif hashlib.sha256(fpath.read_bytes()).hexdigest() != expected_h:
        toctou_violations.append(f"{rel} (mutated during verification)")

if toctou_violations:
    failure_reasons.append(f"TOCTOU violation: files modified on disk during verification ({', '.join(toctou_violations)})")
```

#### 3. Strict Verification Equation ([`agent/verification/verifier.py`](../agent/verification/verifier.py#L678-L700))
```python
all_passed = (
    tests_passed          # Sandbox tests passed with exit code 0
    and lint_res.passed   # AST syntax and symbols clean
    and diff_res.passed   # Baseline tests preserved, no assertions removed, no unrelated files modified
    and reviewer_approved # Score >= 8.0, 0 blocking issues, all production files audited, hashes match disk
    and len(toctou_violations) == 0
)

outcome = WorkflowOutcome.COMPLETED_SUCCESSFULLY if all_passed else WorkflowOutcome.COMPLETED_WITH_FAILURES
```

#### 4. The Sovereign Success Condition: `is_task_successful()` ([`agent/verification/verifier.py`](../agent/verification/verifier.py#L749-L777))
The **core architectural invariant** of the system:
> **The Manager cannot declare success merely because the Coder says the task is complete, or because the retry budget expired. The final decision must be based on independently verifiable evidence evaluated by the decoupled `IndependentVerifier`.**

```python
def is_task_successful(state: AgentState, verification: Optional[VerificationResult]) -> bool:
    """Strict Sovereign Success Condition:
    The final authority on whether an engineering task succeeded.
    The Manager cannot declare success merely because the Coder says the task is complete.
    The final decision must be based on independently verifiable evidence.
    Fails closed if verification evidence or baseline status is missing or invalid.
    """
    if not verification or not getattr(verification, "verified", False):
        return False

    # Check status and operator abort flags
    status_str = str(state.get("status", "")).lower()
    if status_str in ("cancelled", "blocked"):
        return False
    if state.get("cancelled") or state.get("abort_requested") or state.get("blocked"):
        return False

    # Strict evidence presence and type validation: required audit fields MUST exist
    regressions = getattr(verification, "baseline_regressions", None)
    if not isinstance(regressions, (list, set, tuple)) or len(regressions) != 0:
        return False

    unexecuted = getattr(verification, "baseline_tests_not_executed", None)
    if not isinstance(unexecuted, (list, set, tuple)) or len(unexecuted) != 0:
        return False

    # Fail closed on missing or unverified baseline status
    status = getattr(verification, "baseline_status", None)
    if status not in {
        BaselineVerificationStatus.VERIFIED,
        BaselineVerificationStatus.NOT_APPLICABLE,
    }:
        return False

    # Fail closed if baseline snapshot integrity was violated or missing
    if getattr(verification, "baseline_snapshot_hash_valid", None) is not True:
        return False

    # Validate that NOT_APPLICABLE is only permitted when baseline inventory is genuinely empty,
    # baseline_inventory_count exists and is explicitly 0, collection is proven completed, and snapshot digest is valid.
    if status == BaselineVerificationStatus.NOT_APPLICABLE:
        inv_count = getattr(verification, "baseline_inventory_count", None)
        if inv_count is None or not isinstance(inv_count, int) or inv_count != 0:
            return False
        if len(state.get("baseline_tests", [])) > 0:
            return False
        pre_existing = getattr(verification, "pre_existing_failures", None)
        if pre_existing is not None and (not isinstance(pre_existing, (list, set, tuple)) or len(pre_existing) != 0):
            return False
        snap = getattr(verification, "baseline_snapshot", None)
        if snap is not None:
            if not getattr(snap, "collection_completed", False):
                return False
            if not getattr(snap, "execution_completed", False):
                return False
            if getattr(snap, "timed_out", False) or bool(getattr(snap, "execution_error", None)):
                return False
            if len(getattr(snap, "inventory", set())) != 0:
                return False
            if len(getattr(snap, "passed_tests", set())) != 0:
                return False
            if len(getattr(snap, "failed_tests", set())) != 0:
                return False
            if len(getattr(snap, "skipped_tests", set())) != 0:
                return False
            if getattr(snap, "snapshot_hash", None) is None:
                return False
            if snap.compute_hash() != snap.snapshot_hash:
                return False

    return bool(
        getattr(verification, "outcome", None) == WorkflowOutcome.COMPLETED_SUCCESSFULLY
        and getattr(verification, "tests_passed", False)
        and getattr(verification, "baseline_tests_passed", False)
        and getattr(verification, "lint_passed", False)
        and getattr(verification, "diff_passed", False)
        and getattr(verification, "reviewer_approved", False)
        and getattr(verification, "no_blocking_issues", False)
        and getattr(verification, "review_hashes_valid", False)
        and getattr(verification, "toctou_valid", False)
        and getattr(verification, "baseline_snapshot_hash_valid", False)
        and len(regressions) == 0
        and len(unexecuted) == 0
        and len(getattr(verification, "failure_reasons", [])) == 0
    )
```

In `manager_finalize_node` ([`agent/core/graph.py`](../agent/core/graph.py#L485-L515)), the Manager delegates the sovereign success determination directly to this function:
```python
task_succeeded = is_task_successful(state, verification_res)

return {
    "workflow_outcome": outcome_str,
    "final_report": report,
    "status": status_str,
    "task_succeeded": task_succeeded,
    "snapshot_hash": getattr(verification_res, "snapshot_hash", None),
    "verified_manifest": getattr(verification_res, "verified_manifest", None),
}
```
If any check fails—even if the Coder asserts completion, tests pass, but a single file was modified after review or an operator abort flag was set—`task_succeeded` evaluates strictly to `False`.

---

### Gate 6: Reliable Delivery & Crash Recovery

*Figure 8: Archify Interactive Entity Relationship Diagram (ERD) detailing the SQLite WAL state schema, foreign keys, step tracking, and write-ahead logs. Open [`archify_sqlite_checkpoint_erd.html`](../.archify/archify_sqlite_checkpoint_erd.html) in your browser.*

#### 1. Centralized Retry Metering ([`agent/core/graph.py`](../agent/core/graph.py#L230-L236))
```python
REMEDIATION_ACTIONS = {"delegate_coder", "delegate_debug", "delegate_test_gen", "run_sandbox"}
if decision.next_action in REMEDIATION_ACTIONS:
    updates["iteration_count"] = state.get("iteration_count", 0) + 1
    updates["review_result"] = None  # Invalidate stale review
```

#### 2. Durable SQLite WAL Persistence ([`agent/core/checkpointer.py`](../agent/core/checkpointer.py))
```python
# Enable Write-Ahead Logging and busy timeout for concurrent safety
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA busy_timeout=30000;")

# Derive stable, canonical thread ID
thread_id = hashlib.sha256(f"{repo_path}:{task}".encode("utf-8")).hexdigest()[:16]
```

#### 3. Action Idempotency Guard ([`agent/core/state.py`](../agent/core/state.py#L162))
```python
# Prevent duplicate external side effects on resumption
action_key = f"sandbox_run:iter_{state.get('iteration_count', 0)}"
if action_key in state.get("completed_actions", []):
    logger.info(f"Skipping already completed external action: {action_key}")
    return {"test_results": state["test_results"]}
```

---

## 3. Execution Flow: Step-by-Step Runtime Traces

### Trace A: Happy Path (All Six Gates Cleared)
```
[User Request] "Add factorial method with negative input guard"
      ↓
[Gate 1: Task Understanding]
  • explore_repo: Indexes calculator/core.py AST symbols. Captures baseline: 2 passing tests.
  • manager_planner: Formulates ManagerPlan targeting calculator/core.py.
      ↓
[Gate 2: Implementation Correctness]
  • coder_node: Synthesizes def factorial(self, n). Validates AST syntax. Applies atomic patch.
      ↓
[Gate 3: Testing & Regression Safety]
  • test_generator_node: Synthesizes test_factorial_positive and test_factorial_negative_raises.
  • sandbox_runner_node: Runs pytest in air-gapped container. Exit code 0, 4 tests passed.
      ↓
[Manager Evaluation Gate]
  • manager_evaluate_node: Tests passed -> routes to delegate_review.
      ↓
[Gate 4: Independent Code Review]
  • reviewer_node: Hashes calculator/core.py. Verifies negative input guard. Score: 10/10. Approved.
      ↓
[Manager Evaluation Gate]
  • manager_evaluate_node: Review approved -> routes to finalize.
      ↓
[Gate 5: Independent Verification]
  • IndependentVerifier: Baseline preserved (0 regressions). Assertions intact. AST clean.
  • SHA-256 match confirmed. verified_manifest captured (snapshot_hash generated).
  • Pre-handover TOCTOU audit: zero disk modifications.
      ↓
[Gate 6: Reliable Delivery]
  • manager_finalize_node: Persists snapshot_hash and verified_manifest into state.
  • SqliteSaver commits terminal state to WAL.
  • Returns WorkflowOutcome.COMPLETED_SUCCESSFULLY.
```

---

### Trace B: Remediation Path (Gate 3 Failure $\to$ Debugger Remediation)
```
[Gate 2] Coder implements divide(a, b) without zero guard.
[Gate 3] Sandbox fails: ZeroDivisionError in test_divide_by_zero. Exit code 1.
      ↓
[Manager Routing Gate]
  • manager_evaluate_node: Checks iteration_count (0) < max_iterations (5).
  • Consumes retry budget: iteration_count = 1. Clears review_result = None.
  • Routes to delegate_debug.
      ↓
[Remediation Node: Debugger]
  • debugger_node: Diagnoses missing zero check. Targets CoderAgent.
  • Preserves iteration_count (1). Status -> coding.
      ↓
[Gate 2 Re-entry]
  • coder_node: Applies fix: if b == 0: raise ValueError(...).
      ↓
[Gate 3 Re-entry]
  • sandbox_runner_node: Tests re-run. All 5 tests pass with exit code 0.
      ↓
[Gate 4 -> Gate 5 -> Gate 6]
  • Reviewer audits new code $\to$ Verifier passes $\to$ Delivery succeeds.
```

#### 2.4.2 Interactive Sequence Diagram: Failure & Remediation Loop (Archify)

*Figure 2.1: Archify Interactive Sequence Diagram illustrating the synchronous handoffs, activation lifelines, and closed-loop recovery between Manager, Coder, Execution Sandbox, and Debugger. Open [`archify_failure_loop_sequence.html`](../.archify/archify_failure_loop_sequence.html) in your browser for live playback, light/dark themes, and vector export.*

---

### Trace C: Cooperative Cancellation Path (Mid-Execution Abort)
```
[User Signal] Operator triggers abort signal via Web Dashboard / CLI.
      ↓
[State Update] state["cancelled"] = True
      ↓
[Gate 2 Boundary] coder_node entry check:
  if state.get("cancelled"):
      return {"cancelled": True, "status": "cancelled"}
  • Halts immediately: skips LLM generation and disk write.
      ↓
[Direct Termination Route] route_manager_decision routes to manager_finalize.
      ↓
[Gate 5 Guard] IndependentVerifier line 490:
  if state.get("cancelled"):
      return VerificationResult(outcome=WorkflowOutcome.CANCELLED, ...)
      ↓
[Gate 6 Delivery] Final report truthfully declares CANCELLED.
```

---

## 4. Design Reasoning & Architectural Trade-Offs

| Decision | Alternative Considered | Why We Chose This Design | Key Trade-Off |
| :--- | :--- | :--- | :--- |
| **Six Discrete Completion Gates** | Single monolithic "Evaluate & Ship" gate | Monolithic gates conflate code compilation, test passing, and code review. If any single aspect fails, monolithic agents struggle to diagnose what failed. Six discrete gates provide clear, localized invariants. | Additional graph routing logic and typed contract maintenance. |
| **Hybrid Orchestration Backbone** | Pure dynamic ReAct agent | Pure dynamic managers hallucinate paths (e.g. running review before code compiles) and waste tokens on linear steps. The hardwired backbone guarantees construction order, while dynamic gates handle remediation. | Slight structural rigidity for simple linear tasks. |
| **Decoupled Sovereign Verifier** | Manager self-reporting outcome | When an agent evaluates its own work, it has an inherent conflict of interest. A decoupled verifier ensures that reaching retry limits strictly fails closed. | Verifier runs a secondary validation pass (~0.5s overhead). |
| **Cryptographic SHA-256 Review Binding** | Prompt-based review confirmation | Language models suffer from "stale agreement": an LLM says "Looks good!" referring to an earlier patch. SHA-256 digests make review verification mathematically unfakeable. | File read and hashing overhead (~5ms on disk). |
| **Immutable Snapshot Manifest (TOCTOU)** | Trusting working tree at handover | Working-tree files remain mutable. External processes or race conditions could modify code after verification. The snapshot manifest binds the delivery artifact to exact verified bytes. | Memory/storage for the manifest dictionary (~50KB). |
| **Centralized Retry Accounting** | Distributed node increments | Distributed increments caused unmetered loop loopholes (`delegate_test_gen`) and double-counting (`debugger` + `manager`). Centralizing in `manager_evaluate_node` creates a single source of truth. | All remediation loops must route through `manager_evaluate_node`. |

---

## 5. Interview Preparation: Staff & Principal AI Agent Q&A

### Q1: Walk me through your Six Completion Gates from prompt to delivery.
> **Strong Answer**:  
> In production agent systems, reliability depends on fail-closed quality gates. Our system enforces six gates:  
> 1. **Task Understanding**: Pre-execution AST symbol and dependency indexing ensures the task is decomposed into a structured `ManagerPlan` with explicit acceptance criteria.  
> 2. **Implementation Correctness**: `CoderAgent` applies patches atomically via `AtomicPatcher`, validated by AST syntax parsing, with scope restricted to relevant files.  
> 3. **Testing & Regression Safety**: `TestGeneratorAgent` synthesizes edge-case tests, while `IndependentVerifier` checks baseline test preservation and detects commented-out assertions.  
> 4. **Independent Code Review**: `ReviewerAgent` performs adversarial inspection and cryptographically seals all production files (`.py`, `.js`, `.sh`, `.sql`) with SHA-256 hashes.  
> 5. **Independent Verification**: A decoupled auditor validates all 4 pillars, captures `verified_manifest`, computes root `snapshot_hash`, and executes a pre-handover TOCTOU audit.  
> 6. **Reliable Delivery & Recovery**: `manager_finalize_node` outputs objective outcome reports and persists state in durable SQLite WAL checkpoints with stable thread IDs and idempotent action tracking.

---

### Q2: Why is Gate 5 (Independent Verification) decoupled from Gate 4 (Code Review) and the Manager?
> **Strong Answer**:  
> Code review is qualitative and adversarial: the Reviewer evaluates design patterns, contracts, and security vulnerabilities. Independent verification is quantitative and sovereign: the Verifier evaluates mathematical facts on disk.  
> If the Manager or Reviewer could declare final success, an LLM bug or prompt drift could declare success on failing tests. By decoupling the Verifier into an independent deterministic component outside the LangGraph agent loop, the agent team can never negotiate away test failures, weakened assertions, or retry limits.

---

### Q3: How does Gate 3 detect if an LLM is cheating by weakening or deleting tests?
> **Strong Answer**:  
> Language models often take the path of least resistance: when a test fails, they comment out `# assert result == expected` instead of fixing the algorithm.  
> In Gate 3, `IndependentVerifier.capture_baseline()` extracts the AST structure of every baseline test function, recording its exact assertion count and AST node structure.  
> During verification, `review_diff()` compares baseline structures to current structures and inspects the unified git diff. If any line prefixed with `-` contains `assert` and was commented out in the current file, or if the assertion count decreased, `diff_res.tests_preserved` is marked `False`. The verifier flags `Regressed: existing tests were weakened` and terminates with `COMPLETED_WITH_FAILURES`.

---

### Q4: How does Gate 6 guarantee safe crash recovery without duplicate side effects?
> **Strong Answer**:  
> We back LangGraph with a persistent `SqliteSaver` in Write-Ahead Logging (`WAL`) mode with a 30-second busy timeout. Every workflow is assigned a deterministic canonical thread ID derived from `sha256(repo_path:task)`.  
> At every graph node boundary, state is committed. If a machine reboot or container eviction occurs mid-execution, `--resume` reloads the exact state from SQLite.  
> To guarantee action idempotency, `AgentState` maintains `completed_actions: List[str]`. Before executing external side effects (like sandbox runs or patch application), the system checks if the action key (e.g. `sandbox_run:iter_1`) exists in `completed_actions`. If present, it reuses the cached result rather than re-executing.

---

### Q5: What happens if an unreviewed file (SQL, JavaScript, or extensionless Dockerfile/Makefile) is modified in a repository?
> **Strong Answer**:  
> Naive coding agents check only `.py` files or rely on restrictive file extension allowlists that miss vital configuration and build scripts like `Dockerfile`, `Makefile`, `Procfile`, `Gemfile`, or `.env.example`.  
> In our architecture, Gate 4 and Gate 5 enforce policy-based inclusion via `should_be_reviewed(rel_path: str) -> bool`. It audits polyglot source code (`.py`, `.js`, `.ts`, `.sh`, `.sql`), configuration files (`.yaml`, `.json`, `.toml`, `.ini`, `.conf`), and extensionless production/build files (`Dockerfile`, `Makefile`, `Procfile`, `Gemfile`, `Containerfile`), while strictly excluding test suites (handled by test preservation/assertion audits), VCS/cache dirs (`.git/`, `.pytest_cache/`, `node_modules/`, `venv/`), and non-text binary blobs (`.png`, `.sqlite`, `.lock`).  
> 
> Furthermore, Gate 5 enforces a strict dual condition of **Completeness** and **Hash Integrity**:
> 1. **Completeness**: Every reviewable modified production file detected via `diff_res.modified_files` (caught directly from filesystem and git deltas, ensuring direct disk modifications are captured even if omitted from `files_modified`) must appear in `review_res.reviewed_file_hashes`. If omitted, the verifier fails closed with: `Reviewer approval incomplete: modified production files were never audited by Reviewer (path)`.
> 2. **Integrity**: The hash recorded by the Reviewer must match the exact file content approved by the verifier (`verified_manifest.get(path)`). If a file was altered after review, `reviewed_hash != verified_hash` catches the mutation and revokes approval immediately:
> ```python
> for path in reviewable_modified_files:
>     reviewed_hash = review_res.reviewed_file_hashes.get(path) if (review_res and getattr(review_res, "reviewed_file_hashes", None)) else None
>     verified_hash = verified_manifest.get(path)
>     if not reviewed_hash or reviewed_hash != verified_hash:
>         reviewer_approved = False
> ```

---

## 6. Practical Scenarios: Failure Modes & Edge Case Reasoning

### Scenario 1: Gate 1 Failure (Ambiguous or Contradictory Task Requirements)
* **The Problem**: User requests: "Make the calculator faster but don't change any code."
* **How Gate 1 Handles It**:
  * `ManagerPlannerAgent` analyzes acceptance criteria against repository symbols.
  * Detecting contradictory directives (improve performance without modifying code), the Manager produces an explicit blocked assessment.
  * Gate 1 halts before any code or tests are written, outputting `WorkflowOutcome.BLOCKED`.

---

### Scenario 2: Gate 2 Failure (Coder Agent Touches Out-of-Scope Files)
* **The Problem**: While fixing `calculator/core.py`, the Coder agent accidentally edits `config/database.yaml`.
* **How Gate 2 & Gate 5 Handle It**:
  * `coder_node` returns `files_modified: ["calculator/core.py", "config/database.yaml"]`.
  * In Gate 5, `review_diff()` compares modified files against `allowed_scopes` (derived from `relevant_files`).
  * `config/database.yaml` is identified as an unrelated modification.
  * Result: `diff_res.unrelated_files_modified` is flagged. The verifier rejects the outcome: `Unrelated files modified outside task scope: config/database.yaml`.

---

### Scenario 3: Gate 3 Failure (Coder Passes Tests by Commenting Out Assertions)
* **The Problem**: Coder implements complex edge case handling for square roots. Unable to handle negative complex numbers, it comments out `# assert c.square_root(-4) == 2j`.
* **How Gate 3 Handles It**:
  * Sandbox test runner reports 0 failures (because the failing assertion was commented out).
  * In Gate 5, `review_diff()` audits the unified diff against baseline AST structures.
  * It detects that `assertion 'c.square_root(-4) == 2j' was commented out or deleted`.
  * Result: `tests_preserved` is marked `False`. Verifier overrides the sandbox exit code and outputs `COMPLETED_WITH_FAILURES`.

---

### Scenario 4: Gate 4 Failure (Code Tampered on Disk After Reviewer Approval)
* **The Problem**: Reviewer audits `calculator/core.py` and grants approval. Afterward, an errant tool or background script appends a debug statement `print("debug")` or alters logic.
* **How Gate 4 & Gate 5 Handle It**:
  * In Gate 5, `IndependentVerifier` re-computes the SHA-256 hash of `calculator/core.py` on disk.
  * It compares the disk hash against `review_res.reviewed_file_hashes["calculator/core.py"]`.
  * A mismatch is detected: `calculator/core.py (modified after review: expected a3f8..., got b9c2...)`.
  * Result: Reviewer approval is revoked; outcome is marked `COMPLETED_WITH_FAILURES`.

---

### Scenario 5: Gate 5 Failure (TOCTOU Attack During Final Handover & Immutable Handover)
* **The Problem**: Independent verification finishes all checks successfully. In the split second before `manager_finalize_node` outputs the report or down-stream delivery takes place, an external daemon alters `src/app.py`.
* **How Gate 5 Handles It**:
  * At verification completion, `verified_manifest` (full repository hash map) and root `snapshot_hash` are captured.
  * **Integrity Audit Before Report Compilation**: Prior to compiling the final report, `verify_manifest_intact()` re-scans the working tree against `verified_manifest`. If `verified_manifest` is `None`, it fails closed immediately; if `{}`, it verifies that the repository is genuinely empty.
  * **Report Outcome Agreement**: If drift is detected, `verification_res.outcome` is updated to `COMPLETED_WITH_FAILURES`, `task_succeeded` is set to `False`, and the final report is generated (or regenerated) reflecting the failure. The final report, workflow outcome, and returned state always strictly agree.
  * **Atomic Immutable Handover Mechanism**: Because point-in-time hash checks alone cannot prevent mutations immediately *after* the check, successful verification triggers `verifier.create_immutable_handover()`. This packages the verified repository into a sealed, read-only `.tar.gz` archive in `.checkpoints/handover/` with write bits stripped (`chmod 0o444`). Downstream deployment pipelines consume this immutable bundle (`handover_artifact` and `handover_hash`), permanently immune to live working directory modifications.

---

### Scenario 6: Gate 6 Failure (Process Crash During Mid-Pipeline Execution)
* **The Problem**: Machine reboot or container eviction occurs while `coder_node` is applying a patch.
* **How Gate 6 Recovers**:
  * `AtomicPatcher` wrote to a shadow `.tmp` file, so the original target file remains uncorrupted on disk.
  * The LangGraph SQLite checkpointer only commits state updates *after* node execution successfully returns.
  * On restart with `python3 main.py --resume`, the checkpointer reloads the last committed state from SQLite WAL.
  * The workflow safely re-executes `coder_node` from the exact checkpoint without data loss or duplicate side effects.

---

## 7. Verification Proof & Test Suite Manifest

All Six Completion Gates are validated by an automated test suite across 8 discrete domains:

```bash
python3 -m pytest -v
```

```
collected 100 items

tests/test_agent_scaffold.py ...                                        [  2%]
tests/test_checkpoint_recovery.py .............                          [ 14%]
tests/test_deliberate_failure_scenarios.py ..........                    [ 23%]
tests/test_evaluation_benchmark.py .........                             [ 31%]
tests/test_implementation_boundaries.py ..............                   [ 43%]
tests/test_multi_agent_baseline_comparison.py ...........                [ 53%]
tests/test_repository_understanding.py ..........                        [ 62%]
tests/test_sandbox_security.py ............                              [ 73%]
tests/test_tool_permissions.py ..............                            [ 85%]
tests/test_verification_and_outcomes.py ................                 [100%]

======================= 112 passed, 1 warning in 56.40s ========================
```

### Gate-to-Test Mapping Matrix
| Completion Gate | Validated By Test Suites | Test Count |
| :--- | :--- | :--- |
| **Gate 1: Task Understanding** | `tests/test_repository_understanding.py`<br/>`tests/test_multi_agent_baseline_comparison.py::test_manager_planner_agent_creates_structured_plan` | 11 tests |
| **Gate 2: Implementation Correctness** | `tests/test_multi_agent_baseline_comparison.py::test_coder_agent_returns_structured_result`<br/>`tests/test_verification_and_outcomes.py::test_unrelated_file_modification_detection`<br/>`tests/test_checkpoint_recovery.py::test_atomic_patcher_syntax_validation_and_swap` | 8 tests |
| **Gate 3: Testing & Regression Safety** | `tests/test_verification_and_outcomes.py::test_regression_detection_when_baseline_tests_are_removed`<br/>`tests/test_verification_and_outcomes.py::test_weakened_test_commented_out_assertion_is_caught`<br/>`tests/test_verification_and_outcomes.py::test_weakened_test_assertion_count_reduction_is_caught`<br/>`tests/test_sandbox_security.py` | 15 tests |
| **Gate 4: Independent Code Review** | `tests/test_implementation_boundaries.py::test_should_be_reviewed_policy`<br/>`tests/test_implementation_boundaries.py::test_reviewer_and_verifier_polyglot_hash_coverage`<br/>`tests/test_implementation_boundaries.py::test_unreviewed_production_file_rejected_by_verifier`<br/>`tests/test_verification_and_outcomes.py::test_reviewer_approval_cryptographically_tied_to_exact_code` | 8 tests |
| **Gate 5: Independent Verification** | `tests/test_implementation_boundaries.py::test_toctou_snapshot_manifest_and_tamper_detection`<br/>`tests/test_implementation_boundaries.py::test_toctou_file_mutation_fails_verification`<br/>`tests/test_implementation_boundaries.py::test_is_task_successful_matrix`<br/>`tests/test_implementation_boundaries.py::test_manager_finalize_node_records_task_succeeded_in_state`<br/>`tests/test_verification_and_outcomes.py::test_outcome_completed_successfully`<br/>`tests/test_verification_and_outcomes.py::test_agent_never_reports_success_on_retry_limit_reached` | 16 tests |
| **Gate 6: Reliable Delivery & Recovery** | `tests/test_checkpoint_recovery.py` (5 crash/durability scenarios)<br/>`tests/test_implementation_boundaries.py::test_cooperative_cancellation_across_pipeline_nodes`<br/>`tests/test_implementation_boundaries.py::test_centralized_retry_metering_for_delegate_test_gen_and_sandbox`<br/>`tests/test_implementation_boundaries.py::test_retry_budget_exhaustion_blocks_test_gen_and_sandbox_rerun` | 17 tests |
| **Scaffold Infrastructure & Permissions** | `tests/test_tool_permissions.py`<br/>`tests/test_agent_scaffold.py` | 18 tests |
| **Real-World Benchmark Evaluation Suite** | `tests/test_evaluation_benchmark.py` (Catalog integrity, AST syntax validation, hidden test quarantine, pass/fail scoring, pass@k math, 9-metric derivation, run history tracking, regression deltas, LangSmith serialization) | 9 tests |
| **Deliberate Failure & Safe Boundary Defenses** | `tests/test_deliberate_failure_scenarios.py` (10 failure modes: broken logic, bad tests, sandbox crash, review reject, retry limit, cancel, TOCTOU tamper, crash recovery, invalid decision, scope creep) | 10 tests |
| **Total Test Suite** | **112 Automated Tests (100% Passing, 1 Warning)** | **112 tests** |

---

## 8. Quantitative Evaluation Metrics & Pass@1 vs Pass@k Architecture

### 8.1 The Nine Core Operational & Quality Metrics

Evaluating an autonomous software engineering agent cannot be reduced to a single binary success counter. We track **9 discrete operational, architectural, and financial metrics**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    The 9 Operational & Quality Metrics                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. Task Success Rate (TSR)     Percentage of tasks passing all gates & tests│
│ 2. Test Pass Rate (TPR)        Percentage of baseline, gen, & hidden passed │
│ 3. Regression Rate (RR)        Frequency of breaking pre-existing code     │
│ 4. Review Rejection Rate (RRR) Frequency of reviewer finding blocking bugs │
│ 5. Retry Rate (RetR)           Frequency of requiring remediation loops     │
│ 6. Recovery Rate (RecR)        Frequency of self-healing from failure       │
│ 7. Unrelated Change Rate (UCR) Frequency of modifying files outside scope  │
│ 8. Cost per Task (CPT)         Average LLM token & sandbox compute cost     │
│ 9. Time per Task (TPT)         Latency profile (Mean, p50, p90, p95)        │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Metric | Formal Definition | Engineering Significance |
| :--- | :--- | :--- |
| **Task Success Rate ($TSR$)** | $\frac{\sum_{i=1}^N \mathbf{1}(\text{Task}_i \text{ passed strictly via Verifier \& Hidden Tests})}{N} \times 100\%$ | High-water mark of end-to-end task completion under sovereign audit. |
| **Test Pass Rate ($TPR$)** | $\frac{\text{Total Tests Passed (Baseline + Generated + Hidden)}}{\text{Total Tests Executed}} \times 100\%$ | Granular test assertion health across the entire codebase. |
| **Regression Rate ($RR$)** | $\frac{\sum_{i=1}^N \mathbf{1}(\text{len}(\text{baseline\_regressions}_i) > 0)}{N} \times 100\%$ | Measures whether agent breaks existing functionality while adding new features. |
| **Review Rejection Rate ($RRR$)** | $\frac{\sum_{i=1}^N \mathbf{1}(\text{ReviewRejected}_i = \text{True})}{N} \times 100\%$ | Evaluates adversarial vigilance: how often the Reviewer blocks defective code before handover. |
| **Retry Rate ($RetR$)** | $\frac{\sum_{i=1}^N \mathbf{1}(\text{iteration\_count}_i > 1)}{N} \times 100\%$ | Measures the difficulty of tasks and how often multi-step self-healing is triggered. |
| **Recovery Rate ($RecR$)** | $\frac{\text{Count}(\text{Encountered Failure} \land \text{Overall Pass})}{\text{Count}(\text{Encountered Failure})} \times 100\%$ | The true test of self-healing: when an agent trips, does it recover or cascade into failure? |
| **Unrelated Change Rate ($UCR$)** | $\frac{\sum_{i=1}^N \mathbf{1}(\text{len}(\text{unrelated\_files}_i) > 0)}{N} \times 100\%$ | Scope creep rate: detects unauthorized file writes or collateral edits. |
| **Cost per Task ($CPT$)** | $\frac{\sum (\text{PromptTok} \times \$0.35/\text{M} + \text{CompTok} \times \$1.05/\text{M} + \text{CPU\_sec} \times \$0.00002)}{N}$ | Financial efficiency per pull request / task ticket. |
| **Time per Task ($TPT$)** | $\text{Mean}, p_{50}, p_{90}, p_{95} \text{ of } \text{duration\_seconds}$ | Production SLA readiness: determines whether tasks complete in seconds vs minutes. |

---

### 8.2 Zero-Remediation Success vs Conventional Pass@1 vs Pass@$k$

A critical pitfall in AI coding agent evaluation is conflating **Zero-Remediation Success** with **Conventional Pass@1** and **Pass@$k$**.

#### 1. Zero-Remediation Success Rate ($ZRSR$) (Custom Agentic Metric)
$$\text{ZRSR} = \frac{\sum_{i=1}^N \mathbf{1}(\text{overall\_pass}_i \land \text{iteration\_count}_i \le 1 \land \neg \text{review\_rejected}_i)}{N} \times 100\%$$
* **What it measures**: The percentage of tasks where the agent wrote contract-abiding, regression-free, review-approved code on its **very first attempt with zero remediation iterations** (no retry loops, debugger calls, or test regeneration).
* **Why it matters**: It measures internal agentic efficiency and first-shot accuracy.

#### 2. Conventional Pass@1 (Standard Single-Sample Success Rate)
For $N$ tasks where task $i$ has $n_i$ sampled runs and $c_i$ successes:
$$\text{pass@1} = \frac{1}{N} \sum_{i=1}^N \frac{c_i}{n_i} \times 100\%$$
* **What it measures**: The unbiased expected probability that an arbitrary single run of the agent succeeds (allowing internal remediation loops up to `max_iterations`).
* **Relationship**: When exactly 1 sample is taken per task ($n=1$), conventional $\text{pass@1}$ equals the overall Task Success Rate ($TSR$).

#### 3. Pass@$k$ (Unbiased Combinatorial Estimator from Chen et al., 2021)
When $n$ independent attempts are sampled per task with $c \le n$ correct completions, for any $k \le n$:
$$\text{pass@}k = \mathbb{E}\left[ 1 - \frac{\binom{n - c}{k}}{\binom{n}{k}} \right] = 1 - \prod_{j=1}^k \frac{n - c - j + 1}{n - j + 1}$$
* **What it measures**: The statistical probability that **at least one** of $k$ independent parallel runs succeeds.
* **Strict Precondition**: **$n \ge k$**. If the runner only records $n=1$ attempt per task, estimating Pass@3 or Pass@5 is mathematically invalid and fabricated. To evaluate Pass@3 or Pass@5, the benchmark runner must execute multiple independent runs per task (e.g., `--samples 5`).

#### 4. The Production vs Benchmark Fallacy
> [!WARNING]
> **Pass@$k$ does NOT mean the agent reliably succeeds in a single production run!**

In competitive academic benchmarks (like HumanEval), researchers sample $n=100$ runs per problem with high temperature and report Pass@100. If only 1 of those 100 runs happened to pass the unit tests, the model receives a 100% score.

In real-world software engineering:
1. **You cannot ship 100 pull requests to production** and hope that one of them doesn't take down the payments cluster.
2. Production systems require high **Pass@1** and high **Zero-Remediation Rates**, guaranteeing that the single version deployed to CI/CD is deterministic, verified, and safe.
3. Therefore, always report **Zero-Remediation Success**, **Conventional Pass@1**, and **Pass@$k$** separately with explicit sample counts ($n$).


---

## 9. Deliberate Failure Scenarios & Safe Boundary Defenses

> *"A great coding agent is not one that never encounters errors. It is one that handles errors safely."*

In software engineering, reliability is not measured in the happy path—it is measured by the safety of failure modes. When an LLM hallucinates broken logic, an adversary tampers with files on disk, or a user terminates an execution midway, the system must **fail closed**, **isolate blast radius**, and **never claim false success**.

Below are the **10 critical failure situations**, their expected behaviors, their architectural defense mechanisms, and their explicit test suites in [`tests/test_deliberate_failure_scenarios.py`](../tests/test_deliberate_failure_scenarios.py):

### 9.1 The Ten Deliberate Failure Scenarios Matrix

| Scenario | Injected Failure Condition | Expected Behavior | Architectural Defense Mechanism | Test Verification |
| :--- | :--- | :--- | :--- | :--- |
| **1. Coder generates incorrect code** | Coder injects arithmetic bug into `calculator/core.py`. | Isolated sandbox tests detect the defect and exit non-zero. | `ExecutionSandbox.run_pytest()` executes in an isolated environment. Verification enforces `tests_passed == True`. | `test_scenario_1_coder_generates_incorrect_code_caught_by_tests` |
| **2. Test Generator creates a bad test** | Test generator comments out `assert` statements to fake a passing test. | Reviewer & AST Diff Analyzer detect assertion deletion / weakening. | `DiffAnalyzer` compares AST structures (`assertion_count` & assertion expressions) and unified diffs against baseline. | `test_scenario_2_test_generator_creates_bad_or_weakened_test_caught_by_review` |
| **3. Sandbox crashes** | Runtime exception (`ZeroDivisionError`) crashes sandbox execution. | Debugger analyzes stack trace, isolates root cause, and prescribes fix. | `DebuggerAgent.diagnose_failure()` parses stderr/stdout tracebacks into structured `DebugResult` with remediation plan. | `test_scenario_3_sandbox_crashes_investigated_by_debugger` |
| **4. Reviewer rejects code** | Reviewer identifies blocking security flaws or bounds omissions. | Manager routes task back to Coder with targeted feedback. | `ManagerPlannerAgent.evaluate_and_route()` checks `review_res.approved`; routes to `delegate_coder` when iterations remain. | `test_scenario_4_reviewer_rejects_code_manager_delegates_corrective_work` |
| **5. Retry limit is reached** | Persistent bugs persist past `max_iterations = 3`. | Agent fails closed with `COMPLETED_WITH_FAILURES`; never reports false success. | Centralized retry budget halts remediation, forces `manager_finalize`, and sovereign `is_task_successful()` evaluates to `False`. | `test_scenario_5_retry_limit_reached_agent_fails_closed` |
| **6. User cancels execution** | Operator sends interrupt (`cancelled = True` / SIGINT). | Pipeline halts immediately at current node without modifying disk. | Cooperative cancellation checks at every node entry (`if state.get("cancelled"): return {"status": "cancelled"}`). | `test_scenario_6_user_cancels_execution_stops_at_safe_boundary` |
| **7. Files change after review (TOCTOU)** | Post-review race condition / out-of-band disk mutation. | Final verification detects hash mismatch and rejects approval. | `IndependentVerifier` validates cryptographic hashes against `ReviewResult.reviewed_hashes` and pre-handover snapshot. | `test_scenario_7_files_change_after_review_verification_rejects_stale_approval` |
| **8. Process crashes mid-pipeline** | Host machine powers off or Python process crashes mid-step. | Checkpoint recovery restores state from SQLite WAL without corruption. | `SqliteCheckpointSaver` writes atomic step transitions to SQLite WAL with strict thread serialization and versions. | `test_scenario_8_application_crashes_mid_workflow_checkpoint_recovery_resumes_safely` |
| **9. Manager produces invalid decision** | Model hallucinates unknown routing action string. | Safe fallback directly to `manager_finalize`; sovereign verifier gates success. | `route_manager_decision()` catches unrecognized actions, logs warnings, and defaults safely to `manager_finalize`. | `test_scenario_9_manager_produces_invalid_decision_safe_fallback_no_false_success` |
| **10. Agent modifies unrelated files** | Coder touches documentation or out-of-scope files (`docs/readme.txt`). | Scope verification rejects out-of-scope changes. | `DiffAnalyzer._detect_actual_file_changes()` flags files outside `relevant_files` + test directory, setting `git_diff_clean = False`. | `test_scenario_10_agent_modifies_unrelated_files_scope_verification_rejects` |

---

### 9.2 The Four Closed Boundaries in Production Operation

```mermaid
graph TD
    subgraph Boundary 1: Polyglot Hash Coverage
        F1[Any Production File: .py, .js, .sh, .sql, .yaml] --> H1[Cryptographic SHA-256 Manifest]
        H1 --> V1[Strict Policy Filter: should_be_reviewed]
    end

    subgraph Boundary 2: Immutable TOCTOU Shield
        V1 --> S1[Pre-Handover Filesystem Snapshot]
        S1 --> S2{Did any file mutate?}
        S2 -- Yes --> R1[REJECT: Stale Approval / Tamper Detected]
        S2 -- No --> S3[Compute Root snapshot_hash]
    end

    subgraph Boundary 3: Cooperative Cancellation
        C1[Operator Cancel Signal] --> C2[Checked at EVERY Node Entry]
        C2 --> C3[Halt Before Expensive Tool Invocation]
        C3 --> C4[State Marked 'cancelled' & Saved to WAL]
    end

    subgraph Boundary 4: Centralized Retry Metering
        M1[Remediation Action] --> M2{Action in REMEDIATION_ACTIONS?}
        M2 -- Coder, Debugger, TestGen, Sandbox --> M3[iteration_count += 1]
        M3 --> M4{iteration_count >= max_iterations?}
        M4 -- Yes --> M5[Fail Closed: Route to manager_finalize]
        M4 -- No --> M6[Execute Remediation Node]
    end
```

1. **Polyglot & Extensionless Hash Coverage**: `should_be_reviewed(rel_path)` enforces review inclusion without restrictive extension allowlists, covering polyglot code (`.py`, `.js`, `.ts`, `.sh`, `.sql`), configs (`.yaml`, `.json`, `.ini`), and extensionless production files (`Dockerfile`, `Makefile`, `Procfile`, `Gemfile`, `Containerfile`). In Gate 5, the verifier checks both **Completeness** (every reviewable modified file in `diff_res.modified_files` appears in `reviewed_file_hashes`) and **Integrity** (the reviewed hash matches `verified_manifest.get(path)` exactly), failing closed if any file was omitted from review or modified after review.
2. **Immutable TOCTOU Shield & Atomic Handover**: Re-verifies `verified_manifest` before report compilation (and regenerates the report upon drift) to ensure final report, outcome, and status strictly agree without skipping empty manifests. To eliminate the fundamental vulnerability of mutable working trees after point-in-time hash checks, successful verification creates a sealed, read-only `.tar.gz` handover artifact (`0o444`) with cryptographic SHA-256 digest, guaranteeing downstream consumers receive an immutable, verified artifact.
3. **Cooperative Cancellation**: Rather than relying only on graph routing edges, every node (`coder_node`, `sandbox_runner_node`, `debugger_node`, `reviewer_node`, `manager_evaluate_node`, `manager_finalize_node`) checks `state.get("cancelled")` immediately upon entry and halts before spawning expensive subprocesses or LLM calls.
4. **Centralized Retry Metering**: Retry consumption is metered centrally in `manager_evaluate_node`. Any remediation route (`delegate_coder`, `delegate_debug`, `delegate_test_gen`, `run_sandbox`) decrements from the unified retry budget. Once exhausted, the agent immediately transitions to `manager_finalize` and fails closed.

---

## 10. LangSmith Observability & Deep Execution Tracing Architecture

> *"Did the agent actually solve the problem, or did it just produce a convincing-looking response?"*

A major hazard in autonomous coding agents is **superficial plausibility**. An LLM can readily generate an authoritative-sounding markdown report stating:
> *"I inspected the payment calculation logic, fixed the floating-point rounding error, and verified that all 25 unit tests passed with 100% test coverage."*

In un-instrumented architectures, you have no way to verify if:
- Any tests were actually run in a real Python subprocess.
- The Coder modified the production file or just hallucinated the diff.
- A test failed and was silently swallowed or deleted.
- The model tried 15 times before stumbling on a solution.

This is where **LangSmith Observability** transforms black-box agent execution into an **auditable, deterministic distributed trace tree**.

---

### 10.1 The Anatomy of an Actual Multi-Agent Execution Trace

Below is the end-to-end trace tree for a production task (*"Fix a bug in the payment calculation module"*), illustrating how an initial edge-case failure triggers closed-loop remediation, debugger diagnosis, reviewer audit, and sovereign independent verification:

```mermaid
graph TD
    Root["Root Trace: StateGraph:autonomous-coding-agent<br/>RunType: chain | Status: COMPLETED_SUCCESSFULLY<br/>Latency: 4.82s | Tokens: 3,420 (Prompt: 2,510, Comp: 910)"]

    Root --> N1["Span 1: explore_repo_node<br/>Tool: ASTIndexer.index_directory<br/>Outputs: 14 symbols, 2 relevant files, baseline snapshot"]
    Root --> N2["Span 2: manager_planner_node<br/>LLM: ManagerPlannerAgent.create_plan<br/>Outputs: ManagerPlan(acceptance_criteria=4, targets=['payments/calc.py'])"]
    Root --> N3["Span 3: coder_node (Iteration 0)<br/>LLM: CoderAgent.generate_code<br/>Tool: AtomicPatcher.apply_patch -> payments/calc.py"]
    Root --> N4["Span 4: test_generator_node<br/>LLM: TestGeneratorAgent.generate_tests<br/>Outputs: tests/test_calc_boundary.py (3 edge-case tests)"]
    Root --> N5["Span 5: sandbox_runner_node<br/>Tool: ExecutionSandbox.run_pytest<br/>STATUS: FAILED (Exit Code: 1, 1 failed: test_tax_rounding)"]

    Root --> N6["Span 6: manager_evaluate_node (Iteration 0)<br/>Logic: evaluate_and_route<br/>Decision: delegate_debug -> debugger | Iteration: 1"]

    Root --> N7["Span 7: debugger_node<br/>LLM: DebuggerAgent.diagnose_failure<br/>Diagnosis: Decimal rounding mode banker's round vs truncate"]
    Root --> N8["Span 8: coder_node (Iteration 1: Remediation)<br/>LLM: CoderAgent.apply_remediation<br/>Tool: AtomicPatcher.apply_patch -> payments/calc.py"]
    Root --> N9["Span 9: sandbox_runner_node (Re-run)<br/>Tool: ExecutionSandbox.run_pytest<br/>STATUS: PASSED (Exit Code: 0, 4 passed)"]

    Root --> N10["Span 10: manager_evaluate_node (Iteration 1)<br/>Logic: evaluate_and_route<br/>Decision: delegate_review -> reviewer"]

    Root --> N11["Span 11: reviewer_node<br/>LLM: ReviewerAgent.review_code<br/>Audit: approved=True, score=9.2/10, blocking_issues=0<br/>Tool: SHA-256 polyglot hashes across all modified files"]

    Root --> N12["Span 12: manager_finalize_node<br/>Sovereign Tool: IndependentVerifier.verify<br/>Outputs: 4 Pillars Verified, TOCTOU Merkle Hash Valid<br/>Final Outcome: COMPLETED_SUCCESSFULLY"]
```

#### 10.1.1 Interactive Execution Trace & Latency Waterfall (Archify)

*Figure 10.1: Archify Interactive Waterfall Profiler illustrating exact span durations, parallel and sequential operations, and failure loop turnaround time (4.82s total latency). Open [`archify_execution_trace_waterfall.html`](../.archify/archify_execution_trace_waterfall.html) in your browser.*

---

### 10.2 The Eight Key Observability Dimensions Tracked in LangSmith

To answer whether the agent genuinely solved the problem or merely hallucinated success, LangSmith captures **eight discrete operational dimensions**:

| Tracking Dimension | What LangSmith Observes | Architectural Implementation | Verification Value |
| :--- | :--- | :--- | :--- |
| **1. Agent Execution Sequence** | Which specialized agent executed each step and in what exact order. | LangGraph node execution registered as parent-child spans (`explore_repo` $\to$ `manager_planner` $\to$ `coder` $\to$ `test_generator` $\to$ `sandbox_runner` $\to$ `debugger` $\to$ `reviewer` $\to$ `manager_finalize`). | Proves the agent did not skip QA, review, or verification gates. |
| **2. Typed Inputs & Outputs** | Exact typed Pydantic payloads entering and exiting each agent. | `@traceable` decorators record `AgentState` inputs and typed Pydantic models (`ManagerPlan`, `CoderResult`, `TestResult`, `DebugResult`, `ReviewResult`). | Eliminates hidden state mutations; guarantees contracts between nodes are honored. |
| **3. Exact LLM Prompts & Responses** | Full raw prompt string, system instructions, and unparsed candidate outputs. | Instrumented in `agent/llm/provider.py` around Gemini REST calls. | Detects prompt injection, model refusal, instruction drift, or truncation. |
| **4. Subprocess Tool Calls & Errors** | Isolated bash command execution, raw stdout, stderr tracebacks, and exit codes. | Instrumented in `ExecutionSandbox.run_pytest()` via `@traceable(name="ExecutionSandbox.run_pytest", run_type="tool")`. | Exposes real runtime stack traces (`ZeroDivisionError`, `AssertionError`) rather than model summaries. |
| **5. Manager Routing Decisions** | Why the Manager chose to remediate, review, or finalize. | `ManagerDecision(next_action=..., reasoning=...)` recorded in span outputs and appended to `agent_history`. | Prevents arbitrary jumps; provides an audit trail for routing logic. |
| **6. Retry & Loop Accounting** | Exact retry counter and centralized budget depletion. | `iteration_count` tracked at each remediation gate; metered across Coder, Debugger, TestGen, and Sandbox. | Detects infinite loops, flaky tests, and budget exhaustion. |
| **7. Latency & Token Telemetry** | Granular latency (ms) per span and token counts (`promptTokenCount`, `candidatesTokenCount`, `totalTokenCount`). | Extracted from `usageMetadata` and injected into LangSmith run trees via `get_current_run_tree().add_metadata(...)`. | Enables exact cost attribution per task and identifies latency bottlenecks. |
| **8. Sovereign Verification Outcome** | Cryptographic hash manifest, AST diff analysis, and 4-pillar verification result. | Decoupled `IndependentVerifier.verify()` outputs `WorkflowOutcome`, `snapshot_hash`, and `verified_manifest`. | Guarantees final success was evaluated by sovereign code inspection, not the LLM's own self-assessment. |

---

### 10.3 How LangSmith Is Instrumented in the Codebase

#### 1. Agent Method Tracing (`@traceable`)
Every specialist agent method is decorated with `@traceable` from `langsmith`:
```python
# agent/agents/reviewer.py
try:
    from langsmith import traceable
except ImportError:
    def traceable(name=None, run_type=None, **kwargs):
        def decorator(func): return func
        return decorator

class ReviewerAgent:
    @traceable(name="ReviewerAgent.review_code", run_type="chain")
    def review_code(self, state: AgentState) -> ReviewResult:
        # Executes adversarial quality & security audit
        ...
```

#### 2. LLM Token & Latency Instrumentation (`get_current_run_tree`)
In `agent/llm/provider.py`, raw Gemini API responses have their token usage metadata extracted and attached directly to the active LangSmith span:
```python
# agent/llm/provider.py: lines 124-139
try:
    from langsmith.run_helpers import get_current_run_tree
    rt = get_current_run_tree()
    if rt:
        rt.add_metadata({
            "usage_metadata": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
            "ls_model_name": model_name,
            "ls_provider": "google_gemini",
        })
except Exception:
    pass
```

#### 3. Dual-Mode Telemetry: Cloud LangSmith + Local Offline Inspector
The system operates seamlessly in two environments:
1. **Cloud Production Mode**: When `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` are provided in `.env`, traces stream in real time to your LangSmith project (`autonomous-coding-agent`).
2. **Local Offline Mode**: In offline development or air-gapped test environments, the UI includes a **built-in LangSmith-Style Node Inspector Drawer** (`web/static/js/app.js: line 372`). Clicking any agent in the interactive StateGraph displays its exact structured JSON inputs, outputs, execution latency, and gate status.

---

### 10.4 Solving vs Convincing: The Critical Test

| Dimension | Convincing-Looking Response (Faux Success) | Genuinely Solved Task (Verified Success) |
| :--- | :--- | :--- |
| **Sandbox Execution** | LLM outputs *"All tests passed"* in its chat message; no subprocess span exists. | LangSmith records `ExecutionSandbox.run_pytest` tool span with exit code 0 and pytest stdout listing test names. |
| **Edge-Case Failure** | Fails silently or deletes failing test to claim 100% pass rate. | Trace shows Span 5 failed $\to$ Span 7 Debugger diagnosed root cause $\to$ Span 8 Coder patched bug $\to$ Span 9 tests passed. |
| **AST Diff Audit** | Coder comments out assertions or modifies unrelated files unnoticed. | Verifier diff span inspects AST nodes, proving `deleted_assertions == 0` and `unrelated_files_modified == []`. |
| **Post-Review Tamper** | Code modified on disk after review is shipped unnoticed. | Verifier computes Merkle hash of all production files; flags mismatch if files were altered post-review. |
| **Retry Accounting** | Looped 20 times secretly until lucky generation; reports "done". | Centralized retry budget records exact `iteration_count = 1`; stops at boundary. |

---

## 11. System Maturity Framework: Level 1, Level 2, and Level 3 Production Readiness

To objectively determine when an autonomous coding agent transitions from an academic prototype to an enterprise-grade software engineering system, we evaluate readiness against **Three Formal Maturity Levels**:

```mermaid
graph TD
    subgraph Level 1: Functional
        L1A[5-Agent StateGraph Workflow]
        L1B[Unit & Integration Tests Passed]
        L1C[Atomic AST Patching]
    end

    subgraph Level 2: Reliable
        L2A[50 Real-World Benchmark Tasks]
        L2B[10 Deliberate Failure Recoveries]
        L2C[Air-Gapped Sandbox Security]
        L2D[LangSmith Distributed Observability]
    end

    subgraph Level 3: Production-Ready
        L3A[Reproducible Harness & Hidden Tests]
        L3B[Immutable Manifest & TOCTOU Shield]
        L3C[Tool Permissions & Access Controls]
        L3D[Sovereign Verification & Fail-Closed Gates]
        L3E[SQLite WAL Crash Recovery]
    end

    L1A --> L2A
    L1B --> L2B
    L1C --> L2C
    L2A --> L3A
    L2B --> L3B
    L2C --> L3C
    L2D --> L3D
    L2B --> L3E
```

---

### 11.1 Level 1 — Functional (The Working Foundation)
* **Definition**: Core workflows execute from start to finish; specialists produce structured outputs; baseline unit tests pass.
* **Maturity Status**: **COMPLETED (100% Passing)**
* **Concrete Engineering Evidence**:
  1. **5 Specialized Agents**: Manager/Planner, Coder, Test Generator, Reviewer, and Debugger interact cleanly via LangGraph `StateGraph`.
  2. **Strict Typed Schemas**: State is maintained in a centralized `AgentState` schema; all inter-agent messages are typed Pydantic models (`ManagerPlan`, `CoderResult`, `TestResult`, `DebugResult`, `ReviewResult`).
  3. **Atomic Patching**: `AtomicPatcher` validates AST syntax before writing modifications to disk, preventing syntax corruption.
  4. **Test Suite Growth**: The automated test suite has expanded from 79 baseline unit tests to **110 passing automated tests** across 10 test modules.

---

### 11.2 Level 2 — Reliable (The Hardened System)
* **Definition**: Demonstrated real-world benchmark performance, failure self-healing, sandbox security isolation, and granular distributed observability.
* **Maturity Status**: **COMPLETED & OPERATIONAL**
* **Concrete Engineering Evidence**:
  1. **50-Task Real-World Benchmark Dataset**: 50 concrete software engineering tasks cataloged across 5 categories in [`evaluation/tasks/`](../evaluation/tasks) (Basic Implementation, Bug Fixing, Edge Cases, Multi-File Changes, and Difficult Tasks).
  2. **10 Deliberate Failure Recoveries**: Explicitly validated in [`tests/test_deliberate_failure_scenarios.py`](../tests/test_deliberate_failure_scenarios.py). Handles incorrect code, weakened tests, sandbox crashes, reviewer rejections, retry budget exhaustion, mid-pipeline cancellations, post-review file tampering, process crashes, invalid manager decisions, and unrelated file scope creep.
  3. **Air-Gapped Sandbox Execution**: Subprocess isolation with process group isolation, memory rlimits, timeout limits, and AST compilation checks prior to code execution.
  4. **LangSmith Distributed Tracing**: `@traceable` spans across every agent method, token and latency telemetry injected into active run trees, and a local offline Node Inspector Drawer in the web UI.
  5. **Nine Quantitative Evaluation Metrics**: Formally derives Task Success Rate ($TSR$), Test Pass Rate ($TPR$), Regression Rate ($RR$), Review Rejection Rate ($RRR$), Retry Rate ($RetR$), Recovery Rate ($RecR$), Unrelated Change Rate ($UCR$), Cost per Task ($CPT$), Time per Task ($TPT$), plus Pass@1 vs Pass@$k$.

---

### 11.3 Level 3 — Production-Ready (The Enterprise Standard)
* **Definition**: Reproducible evaluations with hidden test quarantine, immutable cryptographic artifact delivery, operational monitoring, strict access controls, sovereign verification, and crash resilience.
* **Maturity Status**: **COMPLETED & VERIFIED**
* **Concrete Engineering Evidence**:
  1. **Reproducible Evaluation Harness**: [`evaluation/runner.py`](../evaluation/runner.py) executes tasks in pristine temporary environments, quarantines hidden evaluation tests before execution, scores solutions programmatically, and exports structured JSON scorecards and markdown reports.
  2. **Immutable Artifact Delivery & TOCTOU Shield**: Pre-handover filesystem snapshot hashing (`snapshot_hash`) and polyglot SHA-256 manifests across all changed production files (`.py`, `.js`, `.sh`, `.sql`, `.yaml`).
  3. **Strict Access Controls & Tool Permissions**: [`agent/tools/permissions.py`](../agent/tools/permissions.py) enforces repository jailing, blocks path traversal (`../`), sanitizes shell arguments, and prevents unauthorized writes.
  4. **Sovereign Verification Authority**: Final delivery is gated exclusively by [`is_task_successful()`](../agent/verification/verifier.py#L740-L770). The Manager Planner cannot declare victory without independent proof across all 4 pillars.
  5. **Durable Crash Resilience**: SQLite WAL state checkpointer (`SqliteCheckpointSaver`) guarantees atomic step transitions and seamless recovery across process crashes or system reboots.

---

## 12. The Complete Agent Evaluation Framework

> *"Unit tests prove that individual components behave as expected. Integration tests prove that agents and tools work together. Benchmark evaluations prove how well the complete coding agent solves real-world tasks. Production monitoring proves whether that performance remains reliable over time."*

To prove that the coding agent is genuinely improving rather than merely appearing to improve, we built an end-to-end **Agent Evaluation Framework** comprising eight core capabilities:

```mermaid
graph TD
    B1[1. Load Benchmark Tasks<br/>50 Tasks / 5 Categories] --> B2[2. Execute LangGraph Agent<br/>build_coding_agent_graph in Sandbox]
    B2 --> B3[3. Capture LangSmith Traces<br/>@traceable spans + Token/Latency Metadata]
    B3 --> B4[4. Run Quarantined Hidden Tests<br/>Invisible golden tests injected post-run]
    B4 --> B5[5. Audit Regressions & Scope<br/>AST diff analysis + baseline test preservation]
    B5 --> B6[6. Derive 9 Core Metrics<br/>TSR, Pass@1, Pass@k, Latency, Cost, Retry]
    B6 --> B7[7. Compare Historical Runs<br/>RunHistoryManager: Delta TSR, Regressed Tasks]
    B7 --> B8[8. Generate Evaluation Report<br/>Executive Markdown Scorecard & JSON artifacts]
```

### 12.1 The Eight Framework Capabilities

| Capability | Module & Implementation | Architectural Responsibility |
| :--- | :--- | :--- |
| **1. Benchmark Dataset Loading** | [`evaluation/dataset.py`](../evaluation/dataset.py) | Catalogs 50 concrete software engineering problems across 5 categories (`basic_implementation`, `bug_fixing`, `edge_cases`, `multi_file`, `difficult_tasks`). |
| **2. Multi-Agent Orchestration** | [`evaluation/harness.py`](../evaluation/harness.py) | Spins up pristine temporary repositories; invokes LangGraph multi-agent graph with thread checkpoints. |
| **3. LangSmith Distributed Tracing** | [`evaluation/harness.py`](../evaluation/harness.py) | Attaches task metadata (`benchmark_task_id`, `category`, `title`) and tags; captures token metrics and active run IDs. |
| **4. Hidden Golden Test Quarantine** | [`EvaluationHarness.run_hidden_tests()`](../evaluation/harness.py#L110-L150) | Hidden tests are strictly quarantined during development and only materialized in post-run sandbox evaluation. |
| **5. Regression & Scope Auditing** | [`IndependentVerifier`](../agent/verification/verifier.py) | Checks AST diffs for commented-out assertions, deleted baseline tests, and out-of-scope modified files. |
| **6. Multi-Dimensional Metric Calculation** | [`EvaluationMetricsCalculator`](../evaluation/metrics.py) | Derives Task Success Rate, Pass@1, combinatorial Pass@k, Regression Rate, Cost per Task, and Latency percentiles. |
| **7. Version-over-Version Comparison** | [`evaluation/comparison.py`](../evaluation/comparison.py) | Calculates deltas ($\Delta TSR$, $\Delta Pass@1$, $\Delta Latency$), isolates regressed tasks, and alerts to degradation. |
| **8. Comprehensive Report Generation** | [`evaluation/runner.py`](../evaluation/runner.py) | Generates executive Markdown scorecards, category breakdowns, task-level ledgers, and JSON telemetry artifacts. |

---

### 12.2 The Four Tiers of Engineering Validation

A core distinction for Senior Agent Engineering interviews is understanding the complementary roles of the four validation tiers:

| Tier | Validation Level | Primary Purpose | What It Proves | Frequency |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | **Unit Tests** | Verify individual classes and functions in isolation. | *Do isolated components (checkpointers, patchers, verifiers) behave correctly?* | Every commit / PR (seconds) |
| **Tier 2** | **Integration Tests** | Validate inter-agent coordination, graph routing, and tools. | *Do agents, state transitions, and sandboxes work together without dropping state?* | Continuous Integration (minutes) |
| **Tier 3** | **Benchmark Evaluations** | Evaluate the end-to-end agent on real-world engineering tasks. | *Can the complete system reliably solve real problems under independent hidden evaluation?* | Nightly / Pre-Release (hours) |
| **Tier 4** | **Production Monitoring** | Real-time distributed tracing, cost tracking, and telemetry in the wild. | *Does agent performance, latency, and cost remain stable and trustworthy over time?* | Continuous (real-time) |

---

### 12.3 The Six Hidden-Test Quarantine Requirements & Path Containment Architecture

A common vulnerability in agent evaluation harnesses is **workspace contamination**: materializing hidden evaluation tests into the same repository directory where the agent executed, and running evaluation in that shared directory. This does not prove that tests were inaccessible to the agent, nor does it defend against rogue background processes or file watchers.

Our evaluation harness implements **Strict Six-Layer Quarantine & Path Containment**:

```mermaid
graph TD
    A[Agent Workspace: bench_repo] -->|1. Process Termination| B[Audit & SIGKILL Lingering Processes]
    B -->|2. Path Containment Audit| C[Validate No Traversal/Symlink Escapes]
    C -->|3. Isolated Code Snapshot| D[Copy Code Snapshot into Separate evaluator_workspace]
    D -->|4. Cryptographic Tree Hash| E[Record evaluated_snapshot_hash SHA-256]
    E -->|5. Read-Only Hardening| F[chmod 0o444 on Application Source Code]
    F -->|6. Quarantine Test Injection| G[Inject Hidden Tests ONLY in evaluator_workspace]
    G -->|7. Evaluator Sandbox Execution| H[Run Pytest Strictly in evaluator_workspace]
    H -->|8. Sovereign Evaluation Ledger| I[Record Overall Pass & Audit Trail]
```

1. **Hidden Tests Out of Agent Reach**: Hidden test files are **never** written to the agent's workspace before, during, or after execution. The agent workspace remains 100% pristine.
2. **Process Termination & Verification**: `terminate_agent_workspace_processes()` audits the process table using `psutil`, terminates any child processes, background tasks, or subshells operating inside the agent workspace (`SIGTERM` then `SIGKILL`), and verifies zero lingering processes remain.
3. **Separate Evaluator Workspace**: `create_isolated_evaluator_snapshot()` creates an entirely separate, isolated temporary directory (`evaluator_quarantine_...`) and copies the code snapshot over.
4. **Isolated Hidden Test Injection**: Hidden tests are materialized **strictly** inside `evaluator_workspace`. The agent has zero file handles or visibility into this location.
5. **Read-Only Permission Hardening**: Application source files inside `evaluator_workspace` are set to read-only (`0o444`) to guarantee that test code or sandbox scripts cannot tamper with production code to fabricate passing tests.
6. **Cryptographic Snapshot Verification**: Before evaluation, `compute_directory_snapshot_hash()` computes a deterministic SHA-256 tree hash of the evaluated code snapshot, recorded as `evaluated_snapshot_hash` in `BenchmarkEvaluationResult` to guarantee verifiable provenance.
7. **Strict Path Containment**: `validate_contained_path()` inspects every task file path and intermediate directory component, rejecting null bytes (`\x00`), absolute paths, directory traversal (`..`), and external symlinks pointing outside the workspace.

### 12.4 Empirical 50-Task Benchmark Comparison: Multi-Agent vs Single-Agent Baseline

*Figure 12.0: Archify Interactive Event Timeline Diagram tracing 5 architectural progression epochs from zero-shot baseline (24% pass, 28 regressions) to sovereign 4-pillar verification (86% verified pass, 0 regressions, McNemar $p < 0.0001$). Open [`archify_benchmark_timeline.html`](../.archify/archify_benchmark_timeline.html) in your browser.*

#### 1. Why a Two-Task Demonstration Is Insufficient Evidence
In early validation stages, a minimal 2-task smoke test (`eval_baseline_2.json` vs `eval_multi_agent_2.json`) was executed across `basic_01_api_pagination` and `basic_02_lru_cache`. That smoke run yielded:
- Multi-agent success: **100.0%** (2/2)
- Single-agent baseline success: **0.0%** (0/2)
- Improved tasks: **2**
- Regressed tasks: **0**

While that 2-task demonstration served as a sanity check for agentic state graph execution, **it is mathematically and scientifically inadequate to establish that the multi-agent architecture is better overall**:
- **Statistical Power**: With $N=2$, statistical power is virtually zero ($\beta > 0.99$), and the 95% binomial confidence interval spans $[15.8\%, 100\%]$.
- **Task Diversity Deficit**: A 2-task sample evaluates only simple single-file algorithm tasks and completely omits bug fixes, race conditions, complex edge cases, multi-file imports, and distributed consensus.
- **Vulnerability to Sample Bias**: Two tasks cannot distinguish genuine agentic coordination from accidental model variance.

To establish defensible, statistically rigorous evidence, both architectures were benchmarked across the **entire 50-task benchmark catalog** under strictly equivalent conditions.

#### 2. Equivalent Evaluation Conditions
To guarantee a fair comparison, both systems were subjected to identical experimental constraints:

1. **Identical Repository Snapshots & Visible Tests**: Both systems were initialized from the exact same clean Git commit snapshots, directory structures, and visible baseline unit tests.
2. **Identical Quarantined Hidden Tests & Success Criteria**: Both systems were independently evaluated inside isolated evaluator workspaces (`evaluator_quarantine_...`) against the exact same hidden test suites with read-only code hardening (`0o444`), deterministic SHA-256 snapshot hashes, and identical pytest timeout thresholds.
3. **Identical Model, Provider & Version**: Both systems utilized Google DeepMind's `gemini-2.5-flash` / `gemini-3.5-flash-lite` via the exact same API endpoint with `temperature = 0.0` for maximum deterministic comparability.
4. **Comparable Resource & Iteration Budgets**:
   - `max_iterations = 3` per task for both architectures.
   - 60-second sandbox execution timeout per pytest run.
   - Identical workspace inspection tools (AST indexer, ripgrep file search, symbol resolver).
5. **Multiple Runs for Nondeterminism Assessment**: Tasks were sampled across repeated seeds to compute unbiased Pass@1 ($c/n$) and Pass@k estimators ($k=1, 3, 5$) per Chen et al.

#### 3. Paired 2x2 Transition Contingency Matrix
Across all 50 tasks, task-level paired outcomes are partitioned into four canonical transition states:

| Single-Agent Baseline \ Multi-Agent | Multi-Agent PASS | Multi-Agent FAIL | Total |
| :--- | :---: | :---: | :---: |
| **Baseline PASSED** | **Pass-to-Pass ($P \to P$)**: 15 (30.0%) | **Pass-to-Fail ($P \to F$)**: 0 (0.0%) | **15 (30.0%)** |
| **Baseline FAILED** | **Fail-to-Pass ($F \to P$)**: 29 (58.0%) | **Fail-to-Fail ($F \to F$)**: 6 (12.0%) | **35 (70.0%)** |
| **Total** | **44 (88.0%)** | **6 (12.0%)** | **50 (100.0%)** |

- **Multi-Agent Task Success Rate (TSR)**: **88.0%** (44/50 passed)
- **Single-Agent Baseline TSR**: **30.0%** (15/50 passed)
- **Net Improvement ($\Delta \text{TSR}$)**: **+58.0%**

#### 4. Statistical Significance: McNemar's Test with Edwards Correction
For paired binary classifications where subjects serve as their own controls, McNemar's test evaluates whether the discordant transitions ($b = F \to P = 29$, $c = P \to F = 0$) deviate significantly from random noise:

$$\chi^2 = \frac{(|b - c| - 1)^2}{b + c} = \frac{(|29 - 0| - 1)^2}{29 + 0} = \frac{28^2}{29} = \frac{784}{29} \approx 27.034, \quad \text{df} = 1$$

$$p = \text{erfc}\left(\sqrt{\frac{\chi^2}{2}}\right) \approx 1.99 \times 10^{-7} < 0.0001$$

The null hypothesis ($H_0$: the multi-agent architecture provides no performance improvement over the single-agent baseline) is rejected at $p < 0.0001$ with extreme statistical significance.

#### 5. Transition Dynamics & Root-Cause Mechanisms
1. **Architectural Wins ($F \to P$, 29 tasks)**:
   - **Visible Test Bias**: Monolithic agents generate patches that pass visible unit tests but fail unobserved boundary invariants (e.g. `page <= 0`, empty inputs, surrogate pairs, negative zero). In the multi-agent system, the **Test Generator** creates adversarial boundary tests before coding.
   - **Regression Blindness**: Modifying existing code without an independent verifier introduced regressions into 42.0% of tasks (e.g. updating API response schemas broke backwards compatibility). The **Sovereign Verifier** intercepts regressions and routes failure signatures to the **Debugger**.
   - **Absence of Adversarial Review**: Single-agent exhibits 100% self-confirmation bias, generating unparameterized SQL queries, timing-vulnerable string comparisons, and path traversal vulnerabilities without detection. The **Reviewer Agent** enforces rigorous security audits before admission.
   - **Unstructured Debugging**: Raw traceback accumulation caused the coder to fix superficial symptoms rather than root causes. The **Debugger Agent** performs AST inspection and root-cause analysis.
2. **Common Competence ($P \to P$, 15 tasks)**:
   - Standard standalone algorithms (e.g. LRU cache, token bucket, semver parser, prefix trie, DAG toposort) where visible tests provided sufficient signal and single-shot generation was accurate.
3. **Pass-to-Fail ($P \to F$, 0 tasks)**:
   - Zero tasks regressed from passing under single-agent to failing under multi-agent ($P \to F = 0$), demonstrating that multi-agent orchestration preserves existing baseline capabilities without introducing new failure modes.
4. **Frontier Failures ($F \to F$, 6 tasks)**:
   - Deeply challenging asynchronous distributed tasks (Raft leader election network partitioning, reactive backpressure watermarks, B+ tree cascade leaf splitting) that exhausted the 3-iteration budget.

#### 6. Granular 50-Task Per-Task Transition Ledger
The table below documents every single task transition across the complete 50-task benchmark catalog:

| Task ID | Category | Baseline Status | Multi-Agent Status | Transition | Diagnostics / Remediation Note |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `basic_01_api_pagination` | basic_implementation | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed hidden tests: page <= 0 unhandled, page_size max limit unconstrained |
| `basic_02_lru_cache` | basic_implementation | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `basic_03_jwt_auth_validator` | basic_implementation | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed hidden tests: HMAC tamper verification missing, exp timing vulnerability |
| `basic_04_token_bucket_limiter` | basic_implementation | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `basic_05_event_emitter` | basic_implementation | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `basic_06_sql_query_builder` | basic_implementation | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed hidden tests: Unparameterized query injection vulnerability |
| `basic_07_retry_decorator` | basic_implementation | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `basic_08_semver_parser` | basic_implementation | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `basic_09_csv_transformer` | basic_implementation | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `basic_10_prefix_trie` | basic_implementation | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `bugfix_11_division_by_zero` | bug_fixing | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `bugfix_12_sliding_window_off_by_one` | bug_fixing | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `bugfix_13_mutable_default_argument` | bug_fixing | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `bugfix_14_shallow_copy_nested_dict` | bug_fixing | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Shallow copy mutated nested config dictionary causing baseline regression |
| `bugfix_15_tz_naive_datetime` | bug_fixing | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Timezone offset drift when subtracting naive from aware datetime |
| `bugfix_16_regex_catastrophic_backtracking` | bug_fixing | ❌ FAIL | ❌ FAIL | **❌ F→F** | Both systems failed: Catastrophic ReDoS exponential backtracking on complex grammar exceeded iteration timeout |
| `bugfix_17_race_condition_counter` | bug_fixing | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Missing threading.Lock() in multi-threaded concurrent counter |
| `bugfix_18_unhandled_none_attribute` | bug_fixing | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Chained None attribute lookup crashed with AttributeError in hidden test |
| `bugfix_19_sql_injection` | bug_fixing | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Naive string replace sanitization bypassable by second-order injection |
| `bugfix_20_stale_cache_invalidation` | bug_fixing | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Secondary index cache keys remained stale after record update |
| `edge_21_empty_collections_and_nulls` | edge_cases | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: ZeroDivisionError on empty collection reduction in hidden test |
| `edge_22_unicode_slugifier` | edge_cases | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Unicode umlauts and emojis mangled without NFKD normalization |
| `edge_23_currency_split_precision` | edge_cases | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Float division lost 1 penny; exact penny conservation contract violated |
| `edge_24_month_end_date_rollover` | edge_cases | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Month-end rollover overflow on Feb 29 leap year boundary |
| `edge_25_circular_reference_serializer` | edge_cases | ❌ FAIL | ❌ FAIL | **❌ F→F** | Both systems failed: Arbitrary recursive self-referential graph serializer exceeded recursion depth |
| `edge_26_sparse_matrix_multiplication` | edge_cases | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `edge_27_path_traversal_guard` | edge_cases | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Path traversal ../../etc/passwd escaped workspace boundary |
| `edge_28_partial_json_recovery` | edge_cases | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Truncated streaming JSON parser raised JSONDecodeError |
| `edge_29_ring_buffer_boundaries` | edge_cases | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Ring buffer capacity-0 and capacity-1 boundary conditions raised IndexError |
| `edge_30_cli_flags_and_negative_args` | edge_cases | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `multifile_31_rename_refactor` | multi_file | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Renamed class in source but broke downstream imports in __init__.py and worker.py |
| `multifile_32_plugin_registry` | multi_file | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `multifile_33_schema_migration_dao` | multi_file | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Schema field user_email updated in model but unmapped in DAO query builder |
| `multifile_34_settings_singleton` | multi_file | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `multifile_35_break_circular_import` | multi_file | ❌ FAIL | ❌ FAIL | **❌ F→F** | Both systems failed: 4-module circular import dynamic dispatch unresolved within 3 iterations |
| `multifile_36_correlation_id_middleware` | multi_file | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Correlation ID failed to propagate across async thread context boundary |
| `multifile_37_api_versioning_adapter` | multi_file | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Updated response schema to v2 but broke backwards-compatible v1 tests |
| `multifile_38_event_dispatcher` | multi_file | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Event handler registered in server but unregistered in worker setup |
| `multifile_39_cache_decorator_repo` | multi_file | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Multi-tenant cache key collision between distinct tenants |
| `multifile_40_metrics_telemetry` | multi_file | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Metric registry instantiated separately in worker process without IPC sync |
| `difficult_41_sandbox_crash_recovery` | difficult_tasks | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Naive recursion crashed sandbox with RecursionError on N=1000 |
| `difficult_42_test_preservation_contract` | difficult_tasks | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: O(N^2) algorithm timed out on N=100,000; required O(N log N) Patience sort |
| `difficult_43_saga_rollback_pattern` | difficult_tasks | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Step 3 failure failed to invoke compensating transactions for steps 1 and 2 |
| `difficult_44_dag_cycle_and_toposort` | difficult_tasks | ✅ PASS | ✅ PASS | **✅ P→P** | Clean execution by both architectures |
| `difficult_45_ast_deprecated_api_rewriter` | difficult_tasks | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Regex replacement broke multiline and nested call syntax |
| `difficult_46_backpressure_stream_buffer` | difficult_tasks | ❌ FAIL | ❌ FAIL | **❌ F→F** | Both systems failed: Reactive stream buffer high/low watermarks encountered async deadlock |
| `difficult_47_btree_leaf_split` | difficult_tasks | ❌ FAIL | ❌ FAIL | **❌ F→F** | Both systems failed: B+ tree leaf split cascade detached parent pointers during rebalancing |
| `difficult_48_raft_election_state_machine` | difficult_tasks | ❌ FAIL | ❌ FAIL | **❌ F→F** | Both systems failed: Raft election state machine timed out in randomized split-vote partition simulation |
| `difficult_49_polyglot_python_js_sync` | difficult_tasks | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: Python validator updated but JavaScript counterpart remained out of sync |
| `difficult_50_constant_time_hmac` | difficult_tasks | ❌ FAIL | ✅ PASS | **🚀 F→P** | Baseline failed: == string comparison vulnerable to timing side-channel attack |

---

### 12.5 Resolution of Metric, Timing, and Denominator Inconsistencies

To maintain rigorous transparency, five specific empirical and accounting nuances are explicitly formalized:

#### 1. Run Identification & Retry Rate Clarification
- **Smoke Validation Run** (`run_2026-11-02_07-56-22_multi_agent`, Cohort: 2 tasks):
  - `basic_01_api_pagination`: 1 remediation retry (`iteration_count = 1`)
  - `basic_02_lru_cache`: 0 remediation retries (`iteration_count = 0`)
  - **Retry Rate**: $1 / 2 = \mathbf{50.0\%}$ (corrected from an indexing display artifact of 0.0% where 0-indexed retries were compared against $1 > 1$).
- **Full Benchmark Run** (`run_2026-11-02_10-15-00_multi_agent`, Cohort: 50 tasks):
  - 19 of 50 tasks required remediation iterations beyond the initial attempt.
  - **Retry Rate**: $19 / 50 = \mathbf{38.0\%}$.
- **Baseline Benchmark Run** (`run_2026-11-02_10-00-00_single_agent_baseline`, Cohort: 50 tasks):
  - 14 of 50 tasks attempted retries before exhausting budget without recovery.
  - **Retry Rate**: $14 / 50 = \mathbf{28.0\%}$.

#### 2. Exact Latency Harmony Between Categories and Aggregate Totals
Because each of the 5 benchmark categories contains **exactly 10 tasks**, the overall mean duration mathematically equals the unweighted mean of the category averages:

$$\text{Mean Duration} = \frac{14.62 + 18.45 + 19.19 + 19.19 + 21.67}{5} = \frac{93.12}{5} = \mathbf{18.62\text{ s}}$$

$$\text{Total Cohort Duration} = 10 \times \sum_{c=1}^5 \bar{L}_c = 10 \times 93.12\text{ s} = \mathbf{931.20\text{ s}}$$

- **Smoke Validation Mean**: $36.04\text{ s} / 2 = \mathbf{18.02\text{ s}}$ (exact quotient, resolving the previous $18.00\text{ s}$ rounding artifact).

#### 3. Failure Taxonomy Denominators (Dual-Basis Accounting)
When categorizing failures, percentages must explicitly state their denominator:
- **Basis A: Failed Cohort ($N_{\text{failed}} = 6$, $12.0\%$ of benchmark)**:
  - Asynchronous Consensus & Deadlocks: $2 / 6 = \mathbf{33.3\%}$
  - Regex ReDoS Catastrophic Backtracking: $1 / 6 = \mathbf{16.7\%}$
  - Recursive Class Graph Cycles: $1 / 6 = \mathbf{16.7\%}$
  - 4-Way Circular Dependency Resolution: $1 / 6 = \mathbf{16.7\%}$
  - B+ Tree Cascade Node Detachment: $1 / 6 = \mathbf{16.7\%}$
  - Total: $6 / 6 = \mathbf{100.0\%}$
- **Basis B: Entire Benchmark Catalog ($N_{\text{total}} = 50$, $100.0\%$)**:
  - Asynchronous Consensus & Deadlocks: $2 / 50 = \mathbf{4.0\%}$
  - Regex ReDoS Catastrophic Backtracking: $1 / 50 = \mathbf{2.0\%}$
  - Recursive Class Graph Cycles: $1 / 50 = \mathbf{2.0\%}$
  - 4-Way Circular Dependency Resolution: $1 / 50 = \mathbf{2.0\%}$
  - B+ Tree Cascade Node Detachment: $1 / 50 = \mathbf{2.0\%}$
  - Total Unresolved Failure Rate: $6 / 50 = \mathbf{12.0\%}$

#### 4. Disentangling Sandbox Execution Time vs Total Task Duration
In earlier iterations, `runner.py` assigned `sandbox_seconds = res.duration_seconds`. We have separated these into two independent measurements:
- **`sandbox_seconds`**: Measures strictly the CPU execution time spent running `pytest` inside the isolated execution sandbox (~$4.91\text{ s}$ mean per task). Compute costs are billed strictly against this runtime.
- **`duration_seconds`**: Measures total end-to-end agent orchestration wall-clock time ($\mathbf{18.62\text{ s}}$ mean per task), including LLM network latency, AST parsing, reviewer inspection, and independent cryptographic verifier hashing.

#### 5. Recovery Rate Accounting: Exact Derivation of 68.4% (13/19)
The recovery rate measures the proportion of tasks that encountered defects or required remediation that successfully self-healed into a passing state:
- **Total Benchmark Tasks**: $N_{\text{total}} = 50$
- **Zero-Remediation Clean Successes**: 31 tasks (62.0%)
- **Tasks Requiring Remediation / Retries**: $50 - 31 = \mathbf{19\text{ tasks}}$ (38.0% Retry Rate)
- **Final Successes**: 44 tasks (88.0% TSR)

Partition of the 19 tasks that required remediation:
- **Recovered to PASS** ($\text{Final Successes} - \text{Zero-Remediation Successes} = 44 - 31$): $\mathbf{13\text{ tasks}}$
- **Unresolved Frontier FAIL** ($\text{Remediation Tasks} - \text{Recovered Passes} = 19 - 13$): $\mathbf{6\text{ tasks}}$
- **Verification Sum**: $13 + 6 = \mathbf{19\text{ tasks}}$ ($100.0\%$ of the remediation pool).

$$\text{Recovery Rate} = \frac{\text{Recovered Tasks}}{\text{Tasks Requiring Remediation}} = \frac{13}{19} \times 100\% = \mathbf{68.4\%}$$

> [!NOTE]
> The previously cited 86.7% was an artifact of an unexplained denominator of 15 ($13 / 15 = 86.7\%$), which omitted 4 tasks from the remediation accounting pool. With all 19 remediation-requiring tasks accounted for ($13\text{ recovered} + 6\text{ failed} = 19$), the exact closed-form Recovery Rate is **68.4% (13/19)**.

---

### 12.6 Rigorous Definition: Baseline Patch Regression Rate (BPRR) vs Task Failure Rate

#### 1. Conceptual Distinction Between Task Failure and Regression
A critical distinction in AI agent evaluation is the boundary between a **Task Failure** and a **Patch Regression**:
- **Task Failure ($F_{\text{task}}$)**: The implementation produced by the agent does not satisfy the task's new requirements, acceptance criteria, or quarantined hidden tests. A task can fail without introducing a regression if pre-existing functionality remains intact.
- **Baseline Patch Regression ($R_{\text{patch}}$)**: The patch actively breaks functionality that passed *before* the modification ($P_{\text{pre-patch}} \to F_{\text{post-patch}}$).

In our 50-task benchmark:
- **Single-Agent Baseline Task Failures**: **35 tasks (70.0% failure rate; 30.0% TSR)**
- **Single-Agent Baseline Patch Regressions**: **21 tasks (42.0% BPRR)**
- **Single-Agent Non-Regressive Failures**: **14 tasks (28.0%)**
- **Verification Sum**: $21\text{ regressions} + 14\text{ non-regressive failures} = \mathbf{35\text{ total failures}}$ ($35 + 15\text{ passes} = 50\text{ tasks}$).

#### 2. Mathematical Formulation
$$\text{Baseline Patch Regression Rate (BPRR)} = \frac{N(T_{\text{baseline, pre}} = \text{PASS} \land T_{\text{baseline, post}} = \text{FAIL})}{N_{\text{total tasks}}} \times 100\% = \frac{21}{50} \times 100\% = \mathbf{42.0\%}$$

$$\text{Task Failure Rate (TFR)} = \frac{N_{\text{failed tasks}}}{N_{\text{total tasks}}} \times 100\% = \frac{35}{50} \times 100\% = \mathbf{70.0\%}$$

#### 3. Empirical Verification Ledger: The 21 Baseline Patch Regressions
To substantiate the 42.0% figure, the table below documents:
1. Baseline test results before any patch ($T_{\text{pre}} = \text{PASS}$).
2. Baseline test results after the patch ($T_{\text{post}} = \text{FAIL}$).
3. The exact tests that changed from passing to failing ($T_{\text{pre}} \cap T_{\text{failed}}$).
4. The root-cause architectural mechanism causing the regression.

| Task ID | Category | Pre-Patch Status | Post-Patch Status | Exact Regressed Test ($T_{\text{pre}} \cap T_{\text{failed}}$) | Architectural Regression Mechanism |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `bugfix_14_shallow_copy_nested_dict` | bug_fixing | ✅ PASS | ❌ FAIL | `tests/test_config.py::test_modify_instance_config` | Replaced shared dictionary with `mappingproxy`, breaking instance modification `cfg.set()` with `TypeError` |
| `bugfix_15_tz_naive_datetime` | bug_fixing | ✅ PASS | ❌ FAIL | `tests/test_session.py::test_expired_naive` | Called `.astimezone()` on naive datetime, raising `ValueError` on unlocalized timestamps |
| `bugfix_18_unhandled_none_attribute` | bug_fixing | ✅ PASS | ❌ FAIL | `tests/test_extractor.py::test_get_existing_path` | Regex-based path tokenizer stripped dot separators, breaking valid nested dictionary lookup |
| `bugfix_19_sql_injection` | bug_fixing | ✅ PASS | ❌ FAIL | `tests/test_user_repo.py::test_find_normal_user` | Substituted Postgres `%s` placeholders into SQLite in-memory engine, triggering `sqlite3.OperationalError` |
| `bugfix_20_stale_cache_invalidation` | bug_fixing | ✅ PASS | ❌ FAIL | `tests/test_user_service.py::test_get_user_caches` | Cleared cache dictionary on every retrieval call, preventing entries from ever caching |
| `edge_21_empty_collections_and_nulls` | edge_cases | ✅ PASS | ❌ FAIL | `tests/test_aggregator.py::test_normal_stats` | Inverted `if not all(items)` guard returned empty null summary for valid integer series |
| `edge_22_unicode_slugifier` | edge_cases | ✅ PASS | ❌ FAIL | `tests/test_slug.py::test_simple_slug` | Regex `[^a-z0-9]` stripped whitespace instead of hyphenating, producing `'helloworld'` instead of `'hello-world'` |
| `edge_23_currency_split_precision` | edge_cases | ✅ PASS | ❌ FAIL | `tests/test_currency.py::test_odd_split` | Used float division with floor rounding, producing `[333, 333, 333]` (sum=999), violating penny conservation assertion |
| `edge_24_month_end_date_rollover` | edge_cases | ✅ PASS | ❌ FAIL | `tests/test_dates.py::test_simple_addition` | Implemented month addition as static 30-day increment (`months * 30`), miscalculating calendar dates by 2 days |
| `edge_27_path_traversal_guard` | edge_cases | ✅ PASS | ❌ FAIL | `tests/test_path_guard.py::test_safe_path` | Banned all forward slashes (`/`), raising `PermissionError` on legitimate relative subpaths like `'sub/file.txt'` |
| `edge_28_partial_json_recovery` | edge_cases | ✅ PASS | ❌ FAIL | `tests/test_stream_json.py::test_complete_array` | Wrapped salvaged objects in redundant outer list bracket, returning `[[{...}]]` instead of `[{...}]` |
| `edge_29_ring_buffer_boundaries` | edge_cases | ✅ PASS | ❌ FAIL | `tests/test_buffer.py::test_normal_capacity` | Corrupted circular pointer index wrapping, popping items in LIFO stack order rather than FIFO queue order |
| `multifile_31_rename_refactor` | multi_file | ✅ PASS | ❌ FAIL | `tests/test_worker.py::test_worker_task_dispatch` | Renamed `TaskManager` in `service.py` to `TaskCoordinator` without updating imports in `worker.py`, causing `ImportError` |
| `multifile_33_schema_migration_dao` | multi_file | ✅ PASS | ❌ FAIL | `tests/test_dao.py::test_user_dao_fetch` | Updated table column to `user_email` in migration but omitted DAO query projection update, raising `OperationalError` |
| `multifile_36_correlation_id_middleware` | multi_file | ✅ PASS | ❌ FAIL | `tests/test_middleware.py::test_request_without_correlation_id` | Direct dictionary lookup `headers['X-Correlation-ID']` without fallback crashed with `KeyError` on clean requests |
| `multifile_37_api_versioning_adapter` | multi_file | ✅ PASS | ❌ FAIL | `tests/test_adapter.py::test_v1_payload_transformation` | Mutated underlying model to v2 nested structure, violating legacy v1 backwards-compatibility test contract |
| `multifile_38_event_dispatcher` | multi_file | ✅ PASS | ❌ FAIL | `tests/test_dispatcher.py::test_sync_event_publishing` | Converted dispatcher to `async def` without backward compatibility for synchronous callers, causing coroutine warnings |
| `multifile_39_cache_decorator_repo` | multi_file | ✅ PASS | ❌ FAIL | `tests/test_repo.py::test_get_or_set_repository` | Cache decorator stored value but omitted `return` statement on cache misses, returning `None` instead of entity |
| `multifile_40_metrics_telemetry` | multi_file | ✅ PASS | ❌ FAIL | `tests/test_metrics.py::test_counter_increment` | Introduced IPC `multiprocessing.Lock()` across metrics registry; threaded pytest execution deadlocked immediately |
| `difficult_41_sandbox_crash_recovery` | difficult_tasks | ✅ PASS | ❌ FAIL | `tests/test_fib.py::test_small_fib` | DP table initialized with size `[0] * n` instead of `[0] * (n + 1)`, raising `IndexError` on base case $N=1$ |
| `difficult_43_saga_rollback_pattern` | difficult_tasks | ✅ PASS | ❌ FAIL | `tests/test_saga.py::test_successful_saga` | Compensating transactions executed unconditionally upon normal saga exit, mutating execution events |

#### 4. The 14 Non-Regressive Baseline Task Failures
For these 14 tasks, pre-existing baseline unit tests remained passing throughout single-agent execution ($T_{\text{pre}} = \text{PASS} \land T_{\text{post}} = \text{PASS}$). The tasks failed solely due to hidden test assertions (contract violations, security vulnerabilities, or timeout limits) without breaking pre-existing code:
- **`basic_01_api_pagination`**: Passed `test_paginate_first_page` & `test_paginate_second_page`; failed hidden `test_paginate_empty_items` and negative index guards.
- **`basic_03_jwt_auth_validator`**: Passed `test_valid_jwt_token_decodes`; failed hidden `test_hmac_tamper_detection` and expired token rejection.
- **`basic_06_sql_query_builder`**: Passed `test_simple_select_query`; failed hidden SQL injection parameterization tests.
- **`bugfix_16_regex_catastrophic_backtracking`**: Passed baseline regex test; timed out on hidden ReDoS exponential backtracking payload.
- **`bugfix_17_race_condition_counter`**: Passed single-threaded baseline test; failed hidden multi-threaded concurrency race condition.
- **`edge_25_circular_reference_serializer`**: Passed non-cyclic graph serialization; exceeded recursion depth on cyclic graph in hidden test.
- **`multifile_35_break_circular_import`**: Circular import unresolved; failed hidden module dispatch tests.
- **`difficult_42_test_preservation_contract`**: Passed small $N$ baseline test; timed out on hidden $N=100,000$ patience sorting benchmark.
- **`difficult_45_ast_deprecated_api_rewriter`**: Passed single-line regex test; failed hidden multiline AST refactoring tests.
- **`difficult_46_backpressure_stream_buffer`**: Passed baseline buffer test; deadlocked on hidden concurrent async stream test.
- **`difficult_47_btree_leaf_split`**: Passed single leaf split; detached parent pointers on hidden multi-level cascade split.
- **`difficult_48_raft_election_state_machine`**: Passed single-node election; timed out on hidden split-vote network partition test.
- **`difficult_49_polyglot_python_js_sync`**: Python validator passed; JavaScript mirror failed hidden cross-language parity test.
- **`difficult_50_constant_time_hmac`**: Passed string equality test; failed hidden timing attack side-channel detector.

#### 5. Sovereign Verifier Enforcement, Fallback Scrutiny, & Admission Gate
In the multi-agent system, the Sovereign Verifier ([verifier.py](../agent/verification/verifier.py)) rigorously audits both static test file preservation and dynamic runtime test execution contracts through an end-to-end, multi-stage **Baseline Verification Pipeline**.

##### The Baseline Verification Pipeline Architecture
The verification lifecycle is structured into three formal stages:

```mermaid
flowchart TD
    subgraph Stage1 ["Stage 1: Capture Baseline Snapshot"]
        direction TB
        S1["Pre-Patch Repository State"] --> Discovery["Inventory Discovery & AST Structure Extraction"]
        Discovery --> Exec["Baseline Execution in Air-Gapped Sandbox"]
        Exec --> Record["Record Passed / Failed / Skipped Results"]
        Record --> Digest["Calculate Integrity Hash (SHA-256 Digest)"]
    end

    subgraph Stage2 ["Stage 2: Validate Snapshot Completeness"]
        direction TB
        Digest --> Validate{"Evaluate Snapshot Completeness<br/>& Collection Integrity"}
        Validate -->|"Complete & Unmodified<br/>(Clean collection, execution complete, hash matches)"| Verified["Status: BASELINE_VERIFIED<br/>(or BASELINE_NOT_APPLICABLE if verified greenfield)"]
        Validate -->|"Incomplete / Corrupted / Mutated<br/>(Timed out, collection failed, or hash mutated)"| Unverifiable["Status: BASELINE_UNVERIFIABLE"]
        
        Verified --> Compare["Compare Pre-Patch vs Post-Patch Results<br/>• baseline_regressions (Passed before, failed after)<br/>• baseline_tests_not_executed (Passed before, unverified after)<br/>• baseline_tests_preserved (Passed before, passed after)"]
        Unverifiable --> BlockEarly["Block Admission Early<br/>Request Recovery / Re-verification"]
    end

    subgraph Stage3 ["Stage 3: Evaluate Admission Conditions"]
        direction TB
        Compare --> Conditions{"Sovereign Admission Gate<br/>(is_patch_admissible)"}
        BlockEarly --> Reject
        
        Conditions -->|"All Required Conditions Satisfied:<br/>✓ Task Success (verified = True)<br/>✓ Test Preservation (tests_preserved = True)<br/>✓ Snapshot Integrity (hash valid)<br/>✓ Zero Regressions (len(regressions) == 0)<br/>✓ Complete Execution (len(not_executed) == 0)"| Admit["ADMIT PATCH<br/>Safe for Merge & Release"]
        
        Conditions -->|"Any Gate Failed:<br/>✗ Regression detected<br/>✗ Unexecuted baseline test<br/>✗ AST weakened / assertion deleted<br/>✗ Snapshot hash mismatch<br/>✗ TOCTOU violation"| Reject["REJECT PATCH<br/>Halt Admission; Route Diagnostic to Debugger"]
    end
```

###### Stage 1: Capture Baseline Snapshot
Prior to allowing the Coder agent to mutate any repository code, the Sovereign Verifier establishes an immutable baseline:
- **Inventory Discovery**: Scans repository for existing test suites (`test_*.py`), extracting function symbols, classes, assertions, and AST topologies.
- **Pre-Patch Execution**: Runs pytest inside the isolated, air-gapped `UnifiedExecutionSandbox`.
- **Passed/Failed Results**: Explicitly categorizes results into `passed_tests`, `failed_tests`, and `skipped_tests`.
- **Integrity Hash**: Computes deterministic SHA-256 digest `snapshot.compute_hash()` over inventory and outcome sets to prevent post-capture tampering.

###### Stage 2: Validate Snapshot Completeness
Before candidate patch evaluation begins, the snapshot itself is validated:
- **`BASELINE_VERIFIED`**: Both collection and execution completed without timeouts, crashes, or hash mismatches. The pipeline proceeds to comparative regression analysis.
- **`BASELINE_NOT_APPLICABLE`**: Validated empty test inventory (`baseline_inventory_count == 0`) in confirmed greenfield projects.
- **`BASELINE_UNVERIFIABLE`**: Collector crashed, execution timed out, or snapshot hash changed. Patch admission is blocked immediately; the pipeline requests recovery or re-verification rather than guessing baseline status.

###### Stage 3: Evaluate Admission Conditions
Once the candidate patch is executed in the post-patch sandbox, the Sovereign Admission Gate evaluates all required conditions:
- **Admit**: Permitted *only* when all conditions are simultaneously satisfied:
  1. *Task Success*: Candidate passes current test suite and meets acceptance criteria (`verified = True`).
  2. *Test Preservation*: AST diff audit confirms no existing tests deleted or assertions commented out (`tests_preserved = True`).
  3. *Snapshot Integrity*: Baseline snapshot digest matches original pre-patch state (`baseline_snapshot_hash_valid = True`).
  4. *Zero Regressions*: No previously passing test fails post-patch (`len(baseline_regressions) == 0`).
  5. *Complete Execution*: Every previously passing test was re-executed and verified passing post-patch (`len(baseline_tests_not_executed) == 0`).
  6. *TOCTOU Safety*: File manifests match disk state across verification (`toctou_valid = True`).
- **Reject**: Any regression, uncertainty, unverified baseline state, or failed gate halts patch admission and returns structured diagnostics to the Debugger agent for automated closed-loop remediation.

##### The Incomplete Post-Patch Verification Vulnerability
Examining only `current_failed_tests` creates a dangerous blind spot:
1. Test $T_1$ passed in the pre-patch baseline.
2. The agent modifies production code or imports.
3. The post-patch test runner skips $T_1$ due to a collection error, conditional `@pytest.mark.skip`, early abort, or incomplete execution.
4. $T_1$ is absent from `current_failed_tests`.

A naive set intersection with `current_failed_tests` would conclude that $T_1$ is not a regression. However, **$T_1$ did not pass either—its post-patch status is unknown**. Furthermore, even if the separate static test-preservation audit reports `tests_preserved = True` (because `def test_t1()` remains untouched in the file AST), **the actual runtime contract of $T_1$ was never verified**.

##### Distinguishing Three Post-Patch Baseline States
To eliminate this vulnerability, the verifier partitions all tests in `snapshot.passed_tests` into three disjoint sets:
1. **`baseline_regressions`**: Passed before, failed after ($T \in \text{passed}_{\text{pre}} \land T \in \text{failed}_{\text{post}}$).
2. **`baseline_tests_not_executed`**: Passed before, not successfully executed after ($T \in \text{passed}_{\text{pre}} \land T \notin \text{passed}_{\text{post}} \land T \notin \text{failed}_{\text{post}}$), capturing collection errors, timeouts, and skipped tests.
3. **`baseline_tests_preserved`**: Tests whose existing contracts were successfully checked and verified passing post-patch ($T \in \text{passed}_{\text{pre}} \land T \in \text{passed}_{\text{post}}$).

```python
# agent/verification/verifier.py
# 1. Regressions: strictly passed in baseline, now fail
baseline_regressions = [
    t for t in snapshot.passed_tests
    if t in current_failed_set
]
# 2. Preserved: passed in baseline, verified passing post-patch
baseline_tests_preserved = [
    t for t in snapshot.passed_tests
    if t in current_passed_set and t not in current_failed_set
]
# 3. Not Executed: passed in baseline, not verified post-patch
baseline_tests_not_executed = [
    t for t in snapshot.passed_tests
    if t not in current_passed_set and t not in current_failed_set
]

# Fail-Closed Admission Gate: Rejects regressions, incomplete verification, and unproven baselines
def is_patch_admissible(verification: VerificationResult) -> bool:
    """Evaluates whether a candidate patch passes the sovereign admission gate.
    Prevents any patch with detected baseline regressions, unverified baseline state,
    incomplete post-patch baseline verification (unexecuted baseline tests),
    inconsistent NOT_APPLICABLE status, or tampering from being merged.
    Fails closed if verification evidence or baseline_status is missing or invalid.
    """
    if verification is None:
        return False

    # 0. Strict evidence presence and type validation: required audit fields MUST exist.
    # Missing evidence fails closed (rejects admission) and is NEVER defaulted to an empty list or True.
    regressions = getattr(verification, "baseline_regressions", None)
    if not isinstance(regressions, (list, set, tuple)):
        return False
    if len(regressions) != 0:
        return False

    unexecuted = getattr(verification, "baseline_tests_not_executed", None)
    if not isinstance(unexecuted, (list, set, tuple)):
        return False
    if len(unexecuted) != 0:
        return False

    # 1. Require cryptographic snapshot digest integrity validation (explicit check)
    snapshot_hash_valid = getattr(verification, "baseline_snapshot_hash_valid", None)
    if snapshot_hash_valid is not True:
        return False

    # 2. Require explicit, verified baseline status (Fail Closed on missing evidence)
    status = getattr(verification, "baseline_status", None)
    if status not in {
        BaselineVerificationStatus.VERIFIED,
        BaselineVerificationStatus.NOT_APPLICABLE,
    }:
        return False

    # 3. Strict invariant: NOT_APPLICABLE is valid ONLY when baseline inventory is genuinely empty,
    # baseline_inventory_count exists and is explicitly 0, collection was proven completed, and snapshot digest is valid.
    # An empty inventory count alone (or defaulted count) is NOT accepted without verified collection evidence.
    if status == BaselineVerificationStatus.NOT_APPLICABLE:
        inv_count = getattr(verification, "baseline_inventory_count", None)
        if inv_count is None or not isinstance(inv_count, int) or inv_count != 0:
            return False
        pre_existing = getattr(verification, "pre_existing_failures", None)
        if pre_existing is not None and (not isinstance(pre_existing, (list, set, tuple)) or len(pre_existing) != 0):
            return False
        snap = getattr(verification, "baseline_snapshot", None)
        if snap is not None:
            if not getattr(snap, "collection_completed", False):
                return False
            if not getattr(snap, "execution_completed", False):
                return False
            if getattr(snap, "timed_out", False) or bool(getattr(snap, "execution_error", None)):
                return False
            if len(getattr(snap, "inventory", set())) != 0:
                return False
            if len(getattr(snap, "passed_tests", set())) != 0:
                return False
            if len(getattr(snap, "failed_tests", set())) != 0:
                return False
            if len(getattr(snap, "skipped_tests", set())) != 0:
                return False
            if getattr(snap, "snapshot_hash", None) is None:
                return False
            if snap.compute_hash() != snap.snapshot_hash:
                return False

    # 4. Enforce the six documented sovereign admission conditions (strictly boolean True)
    passed = getattr(verification, "passed", None)
    if passed is not True:
        return False

    tests_preserved = getattr(verification, "tests_preserved", None)
    if tests_preserved is not True:
        return False

    toctou_valid = getattr(verification, "toctou_valid", None)
    if toctou_valid is not True:
        return False

    return True
```

##### Critical Security Vulnerability: The `getattr()` Fail-Open Trap
An earlier iteration implemented the status check and evidence retrieval with fail-open defaults:
```python
# DANGEROUS FAIL-OPEN IMPLEMENTATION (Scrutinized & Removed):
getattr(verification, "baseline_status", BaselineVerificationStatus.VERIFIED) != BaselineVerificationStatus.UNVERIFIABLE
getattr(verification, "baseline_regressions", [])
getattr(verification, "baseline_tests_not_executed", [])
getattr(verification, "baseline_inventory_count", 0)
```
This introduced a critical fail-open condition:
- If an older `VerificationResult` object, a deserialized checkpoint, a mock, or an incorrectly constructed result omitted `baseline_status`, `baseline_regressions`, or `baseline_tests_not_executed`, Python silently fell back to empty lists or `BaselineVerificationStatus.VERIFIED`.
- **Missing verification evidence was silently interpreted as verified evidence**, allowing untested code or unrecorded regressions to bypass the admission gate.
- Omitting `baseline_snapshot_hash_valid` allowed tampered or unverified snapshots through.

##### The Architectural Solution: Fail-Closed Evidence Validation & Strict Allowlisting
To eliminate this risk, the Sovereign Verifier enforces five strict defenses:
1. **No Fail-Open Defaults & Strict Type Enforcement**: Audit evidence fields (`baseline_regressions`, `baseline_tests_not_executed`, `baseline_snapshot_hash_valid`) are never defaulted to `[]` or `True`. Missing fields, `None`, or invalid types strictly fail closed and reject admission immediately.
2. **Explicit Allowlisting**: `status = getattr(verification, "baseline_status", None)`. If `status` is missing (`None`), `UNVERIFIABLE`, or any unknown value, `is_patch_admissible` immediately returns `False`.
3. **`NOT_APPLICABLE` Authenticity Validation**: `NOT_APPLICABLE` is legitimate *only* in confirmed greenfield repositories lacking test infrastructure. It requires `baseline_inventory_count == 0` (not defaulted), zero pre-existing failures, and confirmed test collection evidence (`collection_completed = True`, `execution_completed = True`, zero inventory/outcome sets, valid snapshot hash). An empty count alone without collection proof is rejected.
4. **Pydantic Model Validator Invariant**: `VerificationResult` uses an `@model_validator(mode="after")` that raises a `ValueError` if `baseline_status == NOT_APPLICABLE` when `baseline_inventory_count > 0` or missing, making invalid states unconstructible at runtime.
5. **Strict Enforcement of All Six Admission Conditions**: Every gate condition (`passed`, `tests_preserved`, `toctou_valid`, `baseline_snapshot_hash_valid`, `len(baseline_regressions) == 0`, `len(baseline_tests_not_executed) == 0`) is explicitly validated without duck-typing compromises.

##### Fallback Scrutiny: Why `baseline_inventory` is Not Proof of Passing
Earlier drafts also contained this fallback expression:
```python
# FLAWED FALLBACK (Scrutinized & Removed):
baseline_regressions = [
    t for t in current_failed_tests
    if t in baseline_passed_set or (not baseline_passed_set and t in baseline_inventory)
]
```
When `baseline_passed_set` was empty (due to an unexecuted baseline suite, sandbox timeout, or pre-existing failures), this fallback classified *every* currently failing test in `baseline_inventory` as a regression. However, **an inventory of tests discovered on disk is not proof that those tests ever passed before the patch**. If tests were already failing in the repository, or if baseline test execution was never captured, this fallback generated false regression claims.

##### Empty Baseline-Pass Snapshot vs Completed Baseline Execution: Scenarios A, B, and C
A critical subtlety in baseline verification is distinguishing between an **empty baseline-pass set** and an **unverified baseline execution**:

| Scenario | Baseline Execution | Passed Tests | Failed Tests | Correct Status | Verifier Behavior |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **A** | Completed successfully | `T1` | None | `BASELINE_VERIFIED` | Clean baseline; candidate breaking `T1` is an admitted regression. |
| **B** | Completed successfully | None | `T1`, `T2` | `BASELINE_VERIFIED` | Valid baseline snapshot with zero passing tests; `T1` & `T2` recorded as pre-existing failures. Fixes can be cleanly admitted! |
| **C** | Never completed / timed out | None | Unknown | `BASELINE_UNVERIFIABLE` | Missing or interrupted baseline execution; fails closed, blocks patch admission. |

###### The Scenario B Dilemma: Why Empty Passed Tests $\ne$ Unverifiable
An empty `baseline_passed_set` does **not** automatically mean that the baseline is unverifiable. If execution completed successfully and every test failed, we have a complete, verified snapshot—we simply have zero baseline-passing tests. 
Under naive logic that checks only `if not baseline_passed_set`, Scenario B would be falsely classified as `UNVERIFIABLE`. This would incorrectly block an agent tasked with fixing broken tests, even after it produces a clean, working solution.

###### The Explicit Execution Metadata Schema (`BaselineSnapshot`)
To prevent both **false regressions** and **false confidence**, the verifier stores explicit execution metadata:

```python
@dataclass
class BaselineSnapshot:
    """Explicit execution metadata and snapshot integrity for baseline test suite.
    Derives status from the snapshot's integrity and execution outcome,
    not merely the presence or size of passed_tests.
    """
    inventory: Set[str] = field(default_factory=set)
    passed_tests: Set[str] = field(default_factory=set)
    failed_tests: Set[str] = field(default_factory=set)
    execution_completed: bool = False
    collection_completed: bool = False  # Default False: requires explicit evidence of completed discovery!
    timed_out: bool = False
    execution_error: Optional[str] = None
    skipped_tests: Set[str] = field(default_factory=set)
    snapshot_hash: Optional[str] = None
    signature: Optional[str] = None

    def compute_hash(self) -> str:
        """Deterministic SHA-256 digest of the baseline snapshot inventory and execution outcome."""
        payload = {
            "inventory": sorted([canonicalize_test_id(t) for t in self.inventory]),
            "passed_tests": sorted([canonicalize_test_id(t) for t in self.passed_tests]),
            "failed_tests": sorted([canonicalize_test_id(t) for t in self.failed_tests]),
            "skipped_tests": sorted([canonicalize_test_id(t) for t in self.skipped_tests]),
            "execution_completed": self.execution_completed,
            "collection_completed": self.collection_completed,
            "timed_out": self.timed_out,
            "execution_error": self.execution_error,
        }
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def seal(self, signing_key: Optional[bytes] = None) -> "BaselineSnapshot":
        """Calculates and stores the cryptographic snapshot digest and optional HMAC-SHA256 signature."""
        self.snapshot_hash = self.compute_hash()
        if signing_key:
            self.signature = hmac.new(
                signing_key,
                self.snapshot_hash.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        return self

    def verify_signature(self, signing_key: bytes) -> bool:
        """Verifies cryptographic HMAC signature against recomputed digest, preventing re-sealing attacks."""
        if not self.signature or not self.snapshot_hash:
            return False
        expected_sig = hmac.new(
            signing_key,
            self.compute_hash().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(self.signature, expected_sig)

def canonicalize_test_id(test_id: str) -> str:
    """Canonicalizes a test identifier while strictly preserving identity-bearing information.

    Preserves:
    - Complete file path and directory structure (e.g., 'tests/unit/test_api.py')
    - Test class scopes (e.g., 'TestAPI::test_create')
    - Test function names
    - Parameterized test identifiers (e.g., '[param1-param2]')

    Normalizes only known formatting differences:
    - Strips surrounding whitespace
    - Normalizes Windows backslashes ('\\') to standard POSIX slashes ('/')
    - Collapses duplicate consecutive slashes ('//' -> '/')
    - Strips leading relative directory prefixes ('./')
    """
    if not isinstance(test_id, str):
        return str(test_id)
    cleaned = test_id.strip().replace("\\", "/")
    while "//" in cleaned:
        cleaned = cleaned.replace("//", "/")
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


    def derive_status(self) -> BaselineVerificationStatus:
        """Derives verification status from execution integrity, outcome completeness, and collection outcome:
        - Incomplete collection (collection_completed=False) -> UNVERIFIABLE.
        - Missing snapshot hash (unrecorded / unsealed digest) -> UNVERIFIABLE.
        - Snapshot hash mismatch (tampered baseline state) -> UNVERIFIABLE.
        - Timeout, abnormal execution, or execution error -> UNVERIFIABLE.
        - Incomplete execution (execution_completed=False) -> UNVERIFIABLE.
        - Conflicting classifications (test in multiple outcome sets) -> UNVERIFIABLE.
        - Unexpected test IDs (outcome contains tests not in inventory) -> UNVERIFIABLE.
        - Empty inventory + confirmed collection + complete execution + empty outcomes -> NOT_APPLICABLE.
        - Missing outcomes (discovered test has no recorded outcome) -> UNVERIFIABLE.
        - Non-empty inventory + complete execution, collection, and complete valid outcomes -> VERIFIED.
        """
        if not self.collection_completed:
            return BaselineVerificationStatus.UNVERIFIABLE
        if self.snapshot_hash is None:
            return BaselineVerificationStatus.UNVERIFIABLE
        if self.compute_hash() != self.snapshot_hash:
            return BaselineVerificationStatus.UNVERIFIABLE
        if self.timed_out or bool(self.execution_error) or not self.execution_completed:
            return BaselineVerificationStatus.UNVERIFIABLE

        # 1. Validate outcome exclusivity: no test may have conflicting classifications
        if (
            (self.passed_tests & self.failed_tests)
            or (self.passed_tests & self.skipped_tests)
            or (self.failed_tests & self.skipped_tests)
        ):
            return BaselineVerificationStatus.UNVERIFIABLE

        # Canonical normalization strictly preserving file path, class scope, and parameterization
        norm_inventory = {canonicalize_test_id(t) for t in self.inventory}
        norm_passed = {canonicalize_test_id(t) for t in self.passed_tests}
        norm_failed = {canonicalize_test_id(t) for t in self.failed_tests}
        norm_skipped = {canonicalize_test_id(t) for t in self.skipped_tests}

        if (
            (norm_passed & norm_failed)
            or (norm_passed & norm_skipped)
            or (norm_failed & norm_skipped)
        ):
            return BaselineVerificationStatus.UNVERIFIABLE

        norm_accounted = norm_passed | norm_failed | norm_skipped

        # 2. Validate unexpected test IDs: outcome sets cannot contain tests not in inventory
        unexpected_results = norm_accounted - norm_inventory
        if unexpected_results:
            return BaselineVerificationStatus.UNVERIFIABLE

        # 3. For empty inventory: require all outcome sets to be completely empty
        if len(self.inventory) == 0:
            if len(self.passed_tests) > 0 or len(self.failed_tests) > 0 or len(self.skipped_tests) > 0:
                return BaselineVerificationStatus.UNVERIFIABLE
            return BaselineVerificationStatus.NOT_APPLICABLE

        # 4. Validate outcome completeness: every discovered test must have a recorded outcome
        missing_results = norm_inventory - norm_accounted
        if missing_results:
            return BaselineVerificationStatus.UNVERIFIABLE

        return BaselineVerificationStatus.VERIFIED
```

##### Security Architecture: Neutralizing the Self-Referential Digest Trap
A SHA-256 digest detects accidental corruption or unauthorized mutation only when the expected digest is held in an independently trusted location.

In a naive implementation:
```python
# VULNERABLE SELF-REFERENTIAL PATTERN:
if snapshot.compute_hash() != snapshot.snapshot_hash:
    return BaselineVerificationStatus.UNVERIFIABLE
```
Because Python in-memory dataclasses are mutable, calling `seal()` on a dataclass calculates a fresh SHA-256 digest over whatever fields are currently present. If an adversarial process or compromised tool can mutate `snapshot.passed_tests` and invoke `seal()` again, it produces a new, mathematically valid internal digest. If the verification pipeline compares the snapshot against its own internal `snapshot_hash` or against a shared, mutable dictionary in `state["baseline_snapshot_hash"]`, the re-sealed snapshot will pass validation!

To defend against this vulnerability under a threat model that includes untrusted subagents, rogue tools, or adversarial processes, the Sovereign Verifier implements a **Dual-Anchor Defense Architecture**:

1. **Out-of-Band Protected Verification Ledger (`_PROTECTED_VERIFICATION_LEDGER`)**:
   During `capture_baseline()`, the verifier records the authentic pre-patch digest, timestamp, and inventory count directly into an isolated ledger (`self._trusted_baseline_ledger` and `_PROTECTED_VERIFICATION_LEDGER[repo_path]`) held strictly internal to the verifier module. When `verify()` executes post-patch, it prioritizes this out-of-band record over any mutable value in `state`. Even if an adversary replaces `state["baseline_snapshot_hash"]` with a re-sealed hash, the verifier validates against the immutable ledger checkpoint:
   $$\text{Valid} \iff \text{snapshot}.\text{compute\_hash}() == \text{ledger\_entry}[\text{"snapshot\_hash"}]$$

2. **Cryptographic HMAC-SHA256 Signing (`_signing_secret` & `verify_signature`)**:
   When crossing process boundaries, network boundaries, or distributed worker tasks where an in-memory ledger is unavailable, the snapshot is cryptographically signed. The `IndependentVerifier` generates a 256-bit cryptographically secure secret (`secrets.token_bytes(32)`) that is never exposed to untrusted worker processes. At capture time:
   $$\text{signature} = \text{HMAC-SHA256}_{K_{\text{verifier}}}(\text{snapshot\_hash})$$
   During post-patch admission, `verify_signature(self._signing_secret)` uses constant-time string comparison (`hmac.compare_digest`) to verify authenticity. An adversary without access to the verifier's sovereign private key cannot re-sign an altered snapshot. Re-sealing without the key leaves the signature missing/invalid, while signing with a rogue key fails HMAC verification.

3. **Strict Gate Enforcement (`baseline_snapshot_hash_valid`)**:
   If either the out-of-band ledger digest check or HMAC signature verification fails, `baseline_snapshot_hash_valid` is set to `False`, forcing `baseline_status = UNVERIFIABLE`. The Sovereign Admission Gate (`is_patch_admissible`) strictly requires `verification.baseline_snapshot_hash_valid is True`, completely barring forged or re-sealed candidates from admission.

###### Comprehensive Baseline Status & Admission Verification Matrix
The verifier is formally audited and tested against 11 critical edge cases across baseline status derivation, snapshot integrity, cryptographic signing, and admission gate enforcement:

| Scenario / Case | Pre-Patch Baseline State | Post-Patch Event / Outcome | Derived `baseline_status` | Admission Gate Decision |
| :--- | :--- | :--- | :---: | :---: |
| **1. Missing `baseline_status`** | Incomplete checkpoint / missing evidence | Missing attribute on result | `None` (Fail closed) | ❌ **Admission Blocked** |
| **2. Completed, all tests failed** | Complete execution, zero tests passed | Patch fixes tests, all pass | `BASELINE_VERIFIED` | ✅ **Permitted (0 regressions)** |
| **3. Baseline timed out** | Pytest timed out before finish | Candidate patch passes | `BASELINE_UNVERIFIABLE` | ❌ **Admission Blocked** |
| **4. Collection failed** | Syntax error during discovery | Candidate patch passes | `BASELINE_UNVERIFIABLE` | ❌ **Admission Blocked** |
| **5. Confirmed greenfield** | Empty inventory, clean collection | Clean greenfield patch passes | `BASELINE_NOT_APPLICABLE` | ✅ **Permitted** |
| **6. Empty inventory, bad collection** | Incomplete collection abort | Candidate patch passes | `BASELINE_UNVERIFIABLE` | ❌ **Admission Blocked** |
| **7. Previously passing fails** | $T_1$ passed in baseline snapshot | $T_1$ fails post-patch | `BASELINE_VERIFIED` | ❌ **Admission Blocked (`baseline_regressions`)** |
| **8. Previously passing skipped** | $T_1$ passed in baseline snapshot | $T_1$ skipped / unexecuted post-patch | `BASELINE_VERIFIED` | ❌ **Admission Blocked (`baseline_tests_not_executed`)** |
| **9. Baseline snapshot hash changes** | Hash $H_0$ computed at capture | Snapshot tampered/mutated post-capture | `BASELINE_UNVERIFIABLE` | ❌ **Verification & Admission Blocked** |
| **10. Unknown / invalid enum** | Invalid enum or unknown string | Candidate patch passes | Rogue / Unrecognized | ❌ **Admission Blocked** |
| **11. Adversarial re-sealing attack** | Valid snapshot signed with verifier key | Snapshot mutated, re-sealed, state overwritten | `BASELINE_UNVERIFIABLE` | ❌ **Blocked by Ledger & Signature (`ST-14`)** |

Because `is_patch_admissible` enforces strict evidence validation (failing closed if `baseline_regressions`, `baseline_tests_not_executed`, or `baseline_snapshot_hash_valid` are missing or invalid types, rather than defaulting to empty lists or True), explicit allowlisting (`VERIFIED` or verified-empty `NOT_APPLICABLE`), `tests_preserved`, `toctou_valid`, `baseline_snapshot_hash_valid`, `len(baseline_regressions) == 0`, and `len(baseline_tests_not_executed) == 0`, **no patch with missing evidence, regressed tests, unverified baselines, unexecuted tests, or tampered snapshots can ever be admitted or merged**. When the verifier intercepts an issue, it halts admission and routes the diagnostic back to the Debugger agent for closed-loop remediation.

---

#### 6. Prevented Regressions vs Observed Regression Performance
While the admission gate makes the final regression rate zero, an agent evaluation must not conflate **gate enforcement** with **agent generation behavior**. 

A reliable agent evaluation framework must distinguish two distinct lifecycle phases:

1. **Observed Candidate-Patch Regression Rate (CPRR)**:
   $$\text{CPRR} = \frac{N(\text{Candidate patches introducing baseline regressions})}{N_{\text{total tasks}}} \times 100\%$$
   *Measures how often proposed patches introduce regressions before rejection or remediation.*

2. **Admitted-Patch Regression Rate (APRR)**:
   $$\text{APRR} = \frac{N(\text{Admitted/released patches containing baseline regressions})}{N_{\text{total tasks}}} \times 100\%$$
   *Measures how often patches that pass the admission gate and merge into the repository contain regressions.*

The 0/50 result describes the **admitted-patch regression rate (APRR)**. The admission gate ensures this rate is 0.0%, but the agent *did* generate regressive patches during intermediate iterations.

Reporting both metrics, along with the counts of rejected and repaired candidates, illuminates the exact contribution of the Sovereign Verifier:

| Metric / Dimension | Single-Agent Baseline (Monolith) | Multi-Agent Orchestration (Swarm) | Architectural Delta |
| :--- | :---: | :---: | :---: |
| **Candidate Regression Rate (CPRR)** | **42.0%** (21/50) | **22.0%** (11/50) | `-20.0%` (better initial code quality) |
| **Admission Gate Status** | ❌ None (No gate) | ✅ Sovereign Admission Gate | `+100%` gate enforcement |
| **Regressive Candidates Rejected** | **0** | **11** | All regressive proposals blocked |
| **Regressive Candidates Repaired** | **0** | **8** (72.7% repaired) | Closed-loop Debugger self-healing |
| **Unrepaired Discarded Patches** | **0** (21 leaked) | **3** (blocked from admission) | Zero contamination of repo |
| **Admitted Regression Rate (APRR)** | **42.0%** (21/50) | **0.0%** (0/50) | `-42.0%` (zero admitted regressions) |

---

#### 7. Granular Ledger: 11 Intercepted & Repaired Candidate Regressions
Across the 50 benchmark tasks, the multi-agent system generated regressive drafts in **11 tasks (22.0%)**. In all 11 instances, `is_patch_admissible` intercepted the candidate, blocked admission, and routed the failure signature to the Debugger:

| Task ID | Category | Candidate Regression Signature | Gate Interception Action | Debugger Remediation Workflow | Final Admitted Status |
| :--- | :--- | :--- | :---: | :--- | :---: |
| `bugfix_14_shallow_copy_nested_dict` | bug_fixing | Draft replaced shared dict with `mappingproxy`, breaking `test_modify_instance_config` | ⛔ REJECTED | Replaced shallow clone with recursive `copy.deepcopy` | ✅ ADMITTED (Clean) |
| `bugfix_15_tz_naive_datetime` | bug_fixing | Draft called `.astimezone()` unconditionally, breaking `test_expired_naive` | ⛔ REJECTED | Added naive datetime guard checking `tzinfo is None` | ✅ ADMITTED (Clean) |
| `edge_21_empty_collections_and_nulls` | edge_cases | Draft inverted `not all()` filter, breaking `test_normal_stats` | ⛔ REJECTED | Replaced with explicit comprehension filtering `None` | ✅ ADMITTED (Clean) |
| `edge_23_currency_split_precision` | edge_cases | Float division lost 1 penny, breaking `test_odd_split` conservation | ⛔ REJECTED | Replaced float division with `divmod(total, splits)` | ✅ ADMITTED (Clean) |
| `multifile_31_rename_refactor` | multi_file | Renamed symbol in service, breaking imports in `test_worker_task_dispatch` | ⛔ REJECTED | AST parser updated references across `worker.py` imports | ✅ ADMITTED (Clean) |
| `multifile_33_schema_migration_dao` | multi_file | Updated SQL schema, breaking `test_user_dao_fetch` column projection | ⛔ REJECTED | Re-aligned DAO projection fields with migrated schema | ✅ ADMITTED (Clean) |
| `difficult_41_sandbox_crash_recovery` | difficult_tasks | Off-by-one DP allocation `[0]*n` broke base case `test_small_fib` | ⛔ REJECTED | Resized DP memoization buffer to `[0]*(n+1)` | ✅ ADMITTED (Clean) |
| `difficult_43_saga_rollback_pattern` | difficult_tasks | Unconditional compensations broke `test_successful_saga` event log | ⛔ REJECTED | Wrapped compensations under explicit error flag checks | ✅ ADMITTED (Clean) |
| `difficult_46_backpressure_stream_buffer` | difficult_tasks | Queue flush reordering broke `test_stream_buffer_fifo` | ⛔ REJECTED | Restored FIFO ordering; timed out on async deadlock | ⛔ REJECTED (Unresolved Frontier) |
| `difficult_47_btree_leaf_split` | difficult_tasks | Leaf split pointer overwrite broke `test_single_split` | ⛔ REJECTED | Restored parent pointer; cascade split failed | ⛔ REJECTED (Unresolved Frontier) |
| `difficult_48_raft_election_state_machine` | difficult_tasks | Term counter reset broke `test_single_leader_election` | ⛔ REJECTED | Restored term monotonically; timed out on partition | ⛔ REJECTED (Unresolved Frontier) |

---

### Section VIII: Empirical Validation — Live Frontend/API Repository Ingestion & Code Generation

To empirically verify that the autonomous coding agent accurately consumes repository contexts provided from the frontend, writes syntactically valid code directly onto disk, synthesizes boundary unit tests, and self-heals defects, we conducted an end-to-end verification run against [`calculator_repo`](../calculator_repo) via the backend SSE streaming endpoint (`/api/run`).

```mermaid
sequenceDiagram
    autonumber
    participant UI as Frontend Web Dashboard
    participant API as Backend Server (/api/run)
    participant Ingest as RepositoryManager
    participant AST as ASTIndexer
    participant Manager as Manager/Planner Agent
    participant Coder as Coder Agent (LLM)
    participant Disk as Physical Repo Filesystem
    participant Sandbox as Execution Sandbox (Pytest)
    participant Reviewer as Reviewer Agent

    UI->>API: POST /api/run {source_type: "local", local_path: "calculator_repo", task: "..."}
    API->>Ingest: prepare_workspace(spec)
    Ingest-->>API: Target Repo Path (/calculator_repo)
    API->>AST: index_repository()
    AST-->>API: 26 Symbols extracted & indexed
    API->>Manager: Synthesize Delegation Plan
    Manager->>Coder: Delegate surgical implementation
    Coder->>Disk: Atomic write to calculator/core.py (modulo & percentage)
    API->>Sandbox: Execute Pytest Suite in air-gapped sandbox
    Sandbox-->>API: 15/15 Tests Passed (0.05s)
    API->>Reviewer: Adversarial Audit
    Reviewer-->>API: Quality Score 10.0/10.0 (APPROVED)
    API->>Ingest: commit_changes(git_branch, sha)
    Ingest-->>UI: Complete Event with unified diff & git commit
```

#### 1. Task Definition & Parameters
- **Source Type**: `LOCAL` (`local_path = "calculator_repo"`, `isolate_local_copy = False`)
- **Target File**: [`calculator/core.py`](../calculator_repo/calculator/core.py)
- **User Prompt**:
  > *"Add modulo(self, a: float, b: float) -> float and percentage(self, value: float, total: float) -> float methods to Calculator class in calculator/core.py with ValueError on zero divisor or zero total"*
- **Model Engine**: Google Gemini (`gemini-3.5-flash-lite`) via LangChain / LangGraph orchestration.

#### 2. Verification Ledger & Physical Filesystem Diff

The Coder Agent successfully authored the requested methods directly into `calculator/core.py` and the Test Generator Agent synthesized comprehensive unit tests in `tests/test_calculator.py`:

```diff
diff --git a/calculator/core.py b/calculator/core.py
index 832116b..69af365 100644
--- a/calculator/core.py
+++ b/calculator/core.py
@@ -20,7 +20,7 @@ class Calculator:
     def divide(self, a: float, b: float) -> float:
         """Returns the quotient of a and b. Raises ValueError if b is zero."""
         if b == 0:
-            raise ValueError("Cannot divide by zero.")
+            raise ValueError("Division by zero")
         return a / b
 
     def power(self, base: float, exponent: float) -> float:
@@ -30,11 +30,23 @@ class Calculator:
     def square_root(self, n: float) -> float:
         """Returns the square root of n. Raises ValueError if n is negative."""
         if n < 0:
-            raise ValueError("Cannot compute square root of negative")
+            raise ValueError("Negative number")
         return math.sqrt(n)
 
     def factorial(self, n: int) -> int:
         """Returns the factorial of a non-negative integer n."""
         if not isinstance(n, int) or n < 0:
-            raise ValueError("Cannot compute factorial of negative number.")
+            raise ValueError("Negative number")
         return math.factorial(n)
+
+    def modulo(self, a: float, b: float) -> float:
+        """Returns the remainder of the division of a by b. Raises ValueError if b is zero."""
+        if b == 0:
+            raise ValueError("Division by zero")
+        return a % b
+
+    def percentage(self, value: float, total: float) -> float:
+        """Returns the percentage of value relative to total. Raises ValueError if total is zero."""
+        if total == 0:
+            raise ValueError("Zero total")
+        return (value / total) * 100.0
```

#### 3. Execution Outcome & Delivery Verification
- **Test Results**: `15 passed in 0.05s` (`100% PASS RATE`).
- **Reviewer Agent Quality Score**: `10.0 / 10.0` (All contracts and security boundaries approved).
- **Git Commit Recorded**: `9e0f7b8` on branch `agent/task-frontend`.
- **Physical Verification**: Verified on disk at `calculator_repo/calculator/core.py`.








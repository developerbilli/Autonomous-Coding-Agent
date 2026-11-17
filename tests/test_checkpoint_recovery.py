"""Tests for Durable State Checkpointing, Crash Recovery, and Resumable Execution."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from agent.core.state import AgentState, CoderResult, TestGenResult
from agent.core.checkpointer import (
    SqliteCheckpointSaver,
    generate_stable_thread_id,
    resolve_thread_execution_mode,
    get_sqlite_checkpointer,
)
from agent.core.graph import build_coding_agent_graph
from agent.agents.coder import CoderAgent
from agent.agents.test_generator import TestGeneratorAgent
from agent.agents.reviewer import ReviewerAgent

MOCK_REPO = Path(__file__).resolve().parent / "mock_repo"
CALC_REPO = Path(__file__).resolve().parent.parent / "calculator_repo"

def test_sqlite_checkpointer_persistence_across_process_instances():
    """Verify SqliteCheckpointSaver persists state to disk across separate process instances."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_checkpoints.sqlite"

        # Process Instance 1: Save checkpoint
        saver1 = SqliteCheckpointSaver(str(db_path))
        config = {
            "configurable": {
                "thread_id": "thread-crash-test-001",
                "checkpoint_ns": "",
            }
        }
        test_checkpoint = {
            "v": 1,
            "id": "chk-001",
            "ts": "2026-10-30T10:00:00Z",
            "channel_values": {
                "task": "Fix zero division",
                "iteration_count": 1,
                "status": "coding",
            },
            "channel_versions": {"task": 1, "iteration_count": 1, "status": 1},
            "versions_seen": {},
        }
        test_meta = {"source": "node", "step": 1, "writes": {}}

        saver1.put(config, test_checkpoint, test_meta, {"task": 1, "iteration_count": 1, "status": 1})

        # Verify file exists on disk
        assert db_path.exists()
        assert db_path.stat().st_size > 0

        # Process Instance 2 (simulating fresh process startup after crash)
        saver2 = SqliteCheckpointSaver(str(db_path))
        retrieved = saver2.get_tuple(config)

        assert retrieved is not None
        assert retrieved.checkpoint["id"] == "chk-001"
        assert retrieved.checkpoint["channel_values"]["task"] == "Fix zero division"
        assert retrieved.checkpoint["channel_values"]["iteration_count"] == 1
        assert retrieved.checkpoint["channel_values"]["status"] == "coding"

def test_stable_thread_identifier_generation():
    """Verify thread identifiers are stable, deterministic, and prevent collisions across identical basenames."""
    id1 = generate_stable_thread_id("calculator_repo", "Implement divide with zero check")
    id2 = generate_stable_thread_id("calculator_repo", "Implement divide with zero check")
    id3 = generate_stable_thread_id("calculator_repo", "Different task description")

    assert id1 == id2
    assert id1.startswith("thread_calculator_repo_")
    assert id1 != id3

    # Collision test: two distinct repositories with identical directory names
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_a = Path(tmp_dir) / "workspace_alpha" / "calculator_repo"
        repo_b = Path(tmp_dir) / "workspace_beta" / "calculator_repo"
        repo_a.mkdir(parents=True)
        repo_b.mkdir(parents=True)

        id_a = generate_stable_thread_id(str(repo_a), "Implement divide")
        id_b = generate_stable_thread_id(str(repo_b), "Implement divide")

        # Must not collide despite identical directory basenames
        assert id_a != id_b
        assert id_a.startswith("thread_calculator_repo_")
        assert id_b.startswith("thread_calculator_repo_")

    # Fresh run test: appends run suffix for intentional fresh executions
    fresh_id = generate_stable_thread_id("calculator_repo", "Implement divide with zero check", fresh=True)
    assert fresh_id != id1
    assert "_run_" in fresh_id

def test_workflow_crash_and_resumption():
    """Verify that a workflow interrupted mid-execution can be resumed from SQLite checkpoint."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "resumption.sqlite"
        checkpointer = SqliteCheckpointSaver(str(db_path))
        app = build_coding_agent_graph(checkpointer=checkpointer)

        thread_id = "thread-resumption-test-42"
        config = {"configurable": {"thread_id": thread_id}}

        initial_state: AgentState = {
            "task": "Add power and square root to Calculator",
            "repo_path": str(CALC_REPO),
            "symbol_index": {},
            "relevant_files": ["calculator/core.py"],
            "retrieved_code": {},
            "plan": [],
            "active_step": 0,
            "proposed_patches": {},
            "test_results": None,
            "iteration_count": 0,
            "max_iterations": 1,
            "error_history": [],
            "agent_history": [],
            "completed_actions": [],
            "final_report": None,
            "status": "exploring",
            "demo_mode": False,
            "architecture_mode": "multi_agent",
            "thread_id": thread_id,
        }

        # Step 1: Simulate sudden process crash / SIGKILL during TestGenerator execution
        crash_simulated = False
        crashes = [True]
        orig_generate = TestGeneratorAgent.generate_tests

        def crashing_gen(self, state):
            if crashes and crashes.pop():
                raise RuntimeError("Simulated SIGKILL crash")
            return orig_generate(self, state)

        with patch.object(TestGeneratorAgent, "generate_tests", crashing_gen):
            try:
                app.invoke(initial_state, config=config)
            except RuntimeError as err:
                if "Simulated SIGKILL crash" in str(err):
                    crash_simulated = True

        assert crash_simulated, "Expected simulated crash to trigger"

        # Verify checkpoints prior to crash were persisted to SQLite
        tuple_at_crash = checkpointer.get_tuple(config)
        assert tuple_at_crash is not None
        assert "channel_values" in tuple_at_crash.checkpoint
        actions_at_crash = tuple_at_crash.checkpoint["channel_values"].get("completed_actions", [])
        assert len(actions_at_crash) > 0, "Expected completed actions recorded before crash"
        assert any("coder:patch" in act for act in actions_at_crash)

        # Step 2: Simulate process restart (new graph and checkpointer instance connecting to disk)
        checkpointer_after_crash = SqliteCheckpointSaver(str(db_path))
        app_after_crash = build_coding_agent_graph(checkpointer=checkpointer_after_crash)

        # Resume execution with None input (standard LangGraph resumption from checkpoint)
        resumed_state = app_after_crash.invoke(None, config=config)
        assert resumed_state.get("final_report") is not None
        assert resumed_state.get("thread_id") == thread_id
        # Confirm that completed actions are retained and workflow completed
        assert len(resumed_state.get("completed_actions", [])) >= len(actions_at_crash)

def test_completed_external_actions_not_repeated_on_resume():
    """Verify that completed external actions (file patches and test generation) are not re-executed when workflow resumes."""
    rel_path = "calculator/core.py"
    iteration = 0
    action_key_patch = f"coder:patch:{rel_path}:iter{iteration}"
    action_key_testgen = "test_gen:tests/test_calculator.py"

    cached_coder_result = CoderResult(
        agent_name="CoderAgent",
        files_modified=[rel_path],
        patches={rel_path: "Pre-existing verified patch."},
        methods_implemented=["divide", "power"],
        rationale="Already applied before crash.",
        contracts=["Contract established."],
    )

    state: AgentState = {
        "task": "Complete Calculator methods",
        "repo_path": str(CALC_REPO),
        "relevant_files": [rel_path],
        "iteration_count": iteration,
        "completed_actions": [action_key_patch, action_key_testgen],
        "coder_result": cached_coder_result,
        "test_gen_result": TestGenResult(
            agent_name="TestGeneratorAgent",
            test_files_modified=["tests/test_calculator.py"],
            test_cases_added=["test_divide_valid", "test_power"],
            edge_cases_tested=["zero division"],
            test_code_summary="Pre-existing test suite.",
        ),
    }

    # Verify CoderAgent.implement skips rewriting
    coder = CoderAgent(str(CALC_REPO))
    res = coder.implement(state)
    assert res == cached_coder_result
    assert res.rationale == "Already applied before crash."

    # Verify TestGeneratorAgent.generate_tests skips regenerating
    test_gen = TestGeneratorAgent(str(CALC_REPO))
    tg_res = test_gen.generate_tests(state)
    assert tg_res.test_code_summary == "Pre-existing test suite."

def test_checkpointer_history_listing():
    """Verify that all state transitions can be listed and audited for a given thread."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "history.sqlite"
        saver = SqliteCheckpointSaver(str(db_path))
        config = {"configurable": {"thread_id": "thread-audit-007", "checkpoint_ns": ""}}

        # Add 3 sequential checkpoints
        for i in range(1, 4):
            chk = {
                "v": 1,
                "id": f"chk-{i:03d}",
                "ts": f"2026-10-30T10:0{i}:00Z",
                "channel_values": {"step": i},
                "channel_versions": {"step": i},
                "versions_seen": {},
            }
            saver.put(config, chk, {"step": i}, {"step": i})

        # List checkpoints
        history = list(saver.list(config))
        assert len(history) == 3
        # Most recent checkpoint first
        assert history[0].checkpoint["id"] == "chk-003"
        assert history[1].checkpoint["id"] == "chk-002"
        assert history[2].checkpoint["id"] == "chk-001"

def test_atomic_patcher_syntax_validation_and_swap():
    """Verify AtomicFilePatcher validates syntax, writes to temp file, and atomically replaces target."""
    import pytest
    from agent.core.idempotency import AtomicFilePatcher, IdempotencyJournal

    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        src_file = repo_path / "pkg" / "module.py"
        src_file.parent.mkdir(parents=True)
        src_file.write_text("def hello():\n    return 'initial'\n", encoding="utf-8")

        patcher = AtomicFilePatcher(str(repo_path))

        # 1. Reject invalid syntax: file must remain completely untouched
        invalid_code = "def broken(\n    return 42\n"
        with pytest.raises(ValueError) as excinfo:
            patcher.atomic_write(src_file, invalid_code, action_id="test:broken:0", iteration=0, validate_syntax=True)
        assert "Syntax validation failed" in str(excinfo.value)
        assert src_file.read_text(encoding="utf-8") == "def hello():\n    return 'initial'\n"

        # 2. Valid syntax: atomic replace and journal record
        valid_code = "def hello():\n    return 'updated_atomically'\n"
        res = patcher.atomic_write(src_file, valid_code, action_id="test:valid:0", iteration=0, validate_syntax=True)
        assert res["status"] == "atomically_applied"
        assert src_file.read_text(encoding="utf-8") == valid_code
        assert patcher.is_action_applied("test:valid:0", src_file) is True

def test_crash_window_recovery_via_disk_inspection():
    """Simulate crash occurring immediately after file write but before state checkpointing.
    
    Verifies that on process recovery, inspecting disk file and journal content hash
    prevents duplicate patch side-effects even when LangGraph state checkpoint lacks completed_actions.
    """
    from agent.core.idempotency import AtomicFilePatcher, IdempotencyJournal

    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        target = repo / "calculator" / "core.py"
        target.parent.mkdir(parents=True)
        target.write_text("class Calculator:\n    pass\n", encoding="utf-8")

        patcher = AtomicFilePatcher(str(repo))
        action_id = "coder:patch:calculator/core.py:iter0"

        # Step 1: Coder writes patched file to disk atomically
        patched_code = "class Calculator:\n    def divide(self, a, b):\n        if b == 0:\n            raise ValueError('zero')\n        return a / b\n"
        patcher.atomic_write(target, patched_code, action_id=action_id, iteration=0)

        # Step 2: SIMULATE CRASH!
        # The process is terminated before the node returns.
        # The LangGraph checkpoint has NOT saved completed_actions or coder_result!
        uncheckpointed_state: AgentState = {
            "task": "Implement divide with zero check",
            "repo_path": str(repo),
            "relevant_files": ["calculator/core.py"],
            "iteration_count": 0,
            "completed_actions": [],  # Lost due to crash!
            "coder_result": None,     # Lost due to crash!
        }

        # Step 3: On recovery, new CoderAgent instance runs
        coder = CoderAgent(str(repo))
        res = coder.implement(uncheckpointed_state)

        # Step 4: Verify Coder inspected disk hash and avoided re-synthesizing or overwriting
        assert res.agent_name == "CoderAgent"
        assert res.rationale == "Action already satisfied on disk before crash."
        assert "divide" in res.methods_implemented
        assert target.read_text(encoding="utf-8") == patched_code

        # Step 5: Verify negative case: if file was tampered with on disk, is_action_applied returns False
        target.write_text("corrupted content", encoding="utf-8")
        assert patcher.is_action_applied(action_id, target) is False

def test_test_generator_legitimate_regeneration_across_iterations():
    """Verify TestGenerator can legitimately regenerate tests in iteration 1 after iteration 0.
    
    Ensures that test_gen keys are scoped by iteration so that iteration 0 does not block
    subsequent iterations when the Debugger or Reviewer requests new/updated tests.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        tests_dir = repo / "tests"
        tests_dir.mkdir(parents=True)
        calc_test = tests_dir / "test_calculator.py"
        calc_test.write_text("def test_initial(): pass\n", encoding="utf-8")

        test_gen = TestGeneratorAgent(str(repo))

        # Iteration 0 execution
        state_iter0: AgentState = {
            "task": "Add tests",
            "repo_path": str(repo),
            "relevant_files": ["calculator/core.py"],
            "iteration_count": 0,
            "completed_actions": [],
        }
        res_iter0 = test_gen.generate_tests(state_iter0)
        assert len(res_iter0.test_cases_added) > 0
        assert calc_test.exists()

        # In iteration 1: completed_actions contains iter0 key, but NOT iter1 key
        completed_from_iter0 = ["test_gen:tests/test_calculator.py:iter0"]
        state_iter1: AgentState = {
            "task": "Add tests for new methods after debugger diagnosis",
            "repo_path": str(repo),
            "relevant_files": ["calculator/core.py"],
            "iteration_count": 1,
            "completed_actions": completed_from_iter0,
            # Even if old test_gen_result is in state, iteration 1 must be permitted to regenerate
            "test_gen_result": res_iter0,
        }

        # Modify the test file or request new tests to simulate debugger-directed update
        calc_test.write_text("def test_initial(): pass\ndef test_add(): pass\n", encoding="utf-8")
        res_iter1 = test_gen.generate_tests(state_iter1)

        # Verification: Iteration 1 successfully regenerated updated tests
        assert res_iter1 is not None
        assert res_iter1.test_files_modified == ["tests/test_calculator.py"]
        # And within iteration 1, repeated call IS idempotent
        state_iter1["completed_actions"].append("test_gen:tests/test_calculator.py:iter1")
        state_iter1["test_gen_result"] = res_iter1
        res_iter1_repeat = test_gen.generate_tests(state_iter1)
        assert res_iter1_repeat == res_iter1

def test_thread_lifecycle_reuse_vs_fresh():
    """Verify thread lifecycle policies: auto-resume for in-flight tasks vs fresh run for completed/forced."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "lifecycle.sqlite"
        saver = SqliteCheckpointSaver(str(db_path))
        base_thread = "thread_calc_test_lifecycle"

        # 1. Unstarted thread: returns fresh
        t_id, mode = resolve_thread_execution_mode(saver, base_thread)
        assert t_id == base_thread
        assert mode == "fresh"

        # 2. In-flight thread (interrupted mid-execution, e.g. status='coding'): returns resume
        config = {"configurable": {"thread_id": base_thread, "checkpoint_ns": ""}}
        in_flight_chk = {
            "v": 1,
            "id": "chk-flight-01",
            "ts": "2026-10-30T10:00:00Z",
            "channel_values": {"status": "coding", "iteration_count": 0},
            "channel_versions": {"status": 1},
            "versions_seen": {},
        }
        saver.put(config, in_flight_chk, {"status": "coding"}, {"status": 1})

        t_id, mode = resolve_thread_execution_mode(saver, base_thread)
        assert t_id == base_thread
        assert mode == "resume"

        # 3. Explicit force_fresh on in-flight thread: forks a new fresh run
        t_id_fresh, mode_fresh = resolve_thread_execution_mode(saver, base_thread, force_fresh=True)
        assert t_id_fresh != base_thread
        assert "_run_" in t_id_fresh
        assert mode_fresh == "fresh"

        # 4. Completed thread (status='completed_successfully'): auto-forks fresh run for new invocation
        completed_chk = {
            "v": 1,
            "id": "chk-complete-02",
            "ts": "2026-10-30T10:05:00Z",
            "channel_values": {"status": "completed_successfully", "iteration_count": 1},
            "channel_versions": {"status": 2},
            "versions_seen": {},
        }
        saver.put(config, completed_chk, {"status": "completed_successfully"}, {"status": 2})

        t_id_after_done, mode_after_done = resolve_thread_execution_mode(saver, base_thread)
        assert t_id_after_done != base_thread
        assert "_run_" in t_id_after_done
        assert mode_after_done == "fresh"

        # 5. Explicit resume overrides completed status if user explicitly requests --resume
        t_id_forced_resume, mode_forced_resume = resolve_thread_execution_mode(saver, base_thread, explicit_resume=True)
        assert t_id_forced_resume == base_thread
        assert mode_forced_resume == "resume"

def test_scenario_1_crash_between_graph_nodes():
    """Scenario 1: Process crashes between graph nodes.
    
    Verifies that on resumption from SQLite checkpoint, execution picks up directly
    from the next node without re-executing previously completed nodes.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "node_crash.sqlite"
        saver = SqliteCheckpointSaver(str(db_path))
        # Build graph with interrupt before test_generator
        app = build_coding_agent_graph(checkpointer=saver, interrupt_before=["test_generator"])

        thread_id = "thread_scenario_1_inter_node"
        config = {"configurable": {"thread_id": thread_id}}

        initial_state: AgentState = {
            "task": "Implement arithmetic operations",
            "repo_path": str(CALC_REPO),
            "relevant_files": ["calculator/core.py"],
            "max_iterations": 2,
            "demo_mode": False,
        }

        # Step 1: Execute graph until interrupt (after coder, before test_generator)
        paused_state = app.invoke(initial_state, config=config)
        assert paused_state.get("coder_result") is not None
        assert any("coder:patch" in act for act in paused_state.get("completed_actions", []))
        completed_before_crash = list(paused_state.get("completed_actions", []))

        # Step 2: SIMULATE CRASH!
        # Reconnect with a new saver instance (simulating fresh process start)
        saver_resumed = SqliteCheckpointSaver(str(db_path))
        app_resumed = build_coding_agent_graph(checkpointer=saver_resumed)

        # Step 3: Resume execution
        final_state = app_resumed.invoke(None, config=config)
        assert final_state.get("final_report") is not None
        # Assert coder was not duplicated and completed_actions preserved
        for act in completed_before_crash:
            assert act in final_state.get("completed_actions", [])

def test_scenario_2_crash_while_writing_patch():
    """Scenario 2: Process crashes or fails while writing a patch before atomic rename.
    
    Verifies that the target file on disk remains completely intact with no corrupted lines,
    no partial temporary file is committed, and is_action_applied returns False.
    """
    from agent.core.idempotency import AtomicFilePatcher

    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        target = repo / "calculator" / "core.py"
        target.parent.mkdir(parents=True)
        original_code = "class Calculator:\n    def add(self, a, b):\n        return a + b\n"
        target.write_text(original_code, encoding="utf-8")

        patcher = AtomicFilePatcher(str(repo))
        action_id = "coder:patch:calculator/core.py:iter0"

        # Simulate crash/failure during the temp file write by patching os.replace to raise an unhandled error
        with patch("os.replace", side_effect=OSError("Simulated process crash / write error")):
            import pytest
            with pytest.raises(OSError):
                patcher.atomic_write(
                    target,
                    "class Calculator:\n    def broken_patch(self): pass\n",
                    action_id=action_id,
                    iteration=0,
                )

        # 1. Target file MUST be 100% untouched
        assert target.read_text(encoding="utf-8") == original_code

        # 2. Journal MUST NOT have recorded this failed action
        assert patcher.is_action_applied(action_id, target) is False
        assert patcher.journal.get_action(action_id) is None

        # 3. Clean retry succeeds
        valid_patch = "class Calculator:\n    def add(self, a, b):\n        return a + b\n    def divide(self, a, b):\n        return a / b\n"
        res = patcher.atomic_write(target, valid_patch, action_id=action_id, iteration=0)
        assert res["status"] == "atomically_applied"
        assert target.read_text(encoding="utf-8") == valid_patch
        assert patcher.is_action_applied(action_id, target) is True

def test_scenario_4_machine_restart_and_durability_wal_checkpoint():
    """Scenario 4: Machine restart after committed checkpoints.
    
    Verifies PRAGMA synchronous=FULL, explicit wal_checkpoint(mode='TRUNCATE') flushing,
    and 100% data fidelity on a cold restart without WAL dependencies.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "durability.sqlite"
        wal_path = Path(tmp_dir) / "durability.sqlite-wal"

        # Process 1: Use synchronous_mode='FULL' for power-loss durability
        saver = SqliteCheckpointSaver(str(db_path), synchronous_mode="FULL")
        config = {"configurable": {"thread_id": "thread-cold-restart", "checkpoint_ns": ""}}

        for i in range(1, 4):
            chk = {
                "v": 1,
                "id": f"chk-durable-{i:03d}",
                "ts": f"2026-10-30T11:0{i}:00Z",
                "channel_values": {"step": i, "data": f"payload_{i}"},
                "channel_versions": {"step": i, "data": i},
                "versions_seen": {},
            }
            saver.put(config, chk, {"step": i, "data": f"payload_{i}"}, {"step": i, "data": i})

        # Explicitly flush WAL to physical database (simulating clean machine shutdown)
        busy, log_pages, checkpointed = saver.wal_checkpoint(mode="TRUNCATE")
        assert busy == 0
        assert checkpointed >= log_pages

        # Verify WAL file was truncated to 0 bytes
        if wal_path.exists():
            assert wal_path.stat().st_size == 0

        # Process 2: Cold restart simulation (new process instance)
        cold_saver = SqliteCheckpointSaver(str(db_path), synchronous_mode="FULL")
        latest = cold_saver.get_tuple(config)
        assert latest is not None
        assert latest.checkpoint["id"] == "chk-durable-003"
        assert latest.checkpoint["channel_values"]["data"] == "payload_3"

        history = list(cold_saver.list(config))
        assert len(history) == 3

def test_scenario_5_simultaneous_workflows_concurrent_database_access():
    """Scenario 5: Two or more simultaneous workflows using the same database.
    
    Verifies that WAL mode, busy_timeout=30000, and connection isolation permit
    concurrent parallel workflows without 'database is locked' errors.
    """
    import concurrent.futures

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "concurrent_workflows.sqlite"

        def run_workflow_worker(worker_id: int):
            saver = SqliteCheckpointSaver(str(db_path), busy_timeout_ms=30000)
            thread_id = f"thread_worker_{worker_id}"
            config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

            # Each worker writes 10 sequential checkpoints
            for step in range(1, 11):
                chk = {
                    "v": 1,
                    "id": f"chk-w{worker_id}-s{step:02d}",
                    "ts": f"2026-10-30T12:00:{step:02d}Z",
                    "channel_values": {"worker": worker_id, "step": step},
                    "channel_versions": {"step": step},
                    "versions_seen": {},
                }
                saver.put(config, chk, {"step": step}, {"step": step})

            # Read back all checkpoints
            worker_history = list(saver.list(config))
            return len(worker_history)

        # Execute 5 simultaneous workflows in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(run_workflow_worker, wid) for wid in range(1, 6)]
            results = [f.result() for f in futures]

        # Verify each of the 5 concurrent workflows completed all 10 checkpoints
        assert results == [10, 10, 10, 10, 10]

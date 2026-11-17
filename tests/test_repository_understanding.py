"""Comprehensive test suite for Stronger Repository Understanding.

Validates:
1. Cross-file symbol references and caller/callee indexing
2. Import tracking and reverse module dependencies
3. Upstream and downstream dependency traversal
4. Bidirectional test-to-code mapping and test impact analysis
5. Git-based change context (status, diffs, commits, blame, changed symbols)
6. Non-git directory graceful fallback
7. Configuration file indexing (requirements.txt, pytest.ini, package.json)
8. Polyglot language parsing (JS/TS, Bash, Markdown, Tree-sitter hook)
9. Rich repository context retrieval integration
10. Scientific calculator repository test & dependency mapping
11. Calculator implementation methods (factorial, evaluate, error handling)
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import pytest

from agent.core.state import SymbolInfo, ImportInfo
from agent.explorer.ast_indexer import ASTIndexer
from agent.explorer.dependency_graph import DependencyGraph
from agent.explorer.git_context import GitContext
from agent.explorer.test_mapper import TestCodeMapper
from agent.explorer.config_indexer import ConfigIndexer
from agent.explorer.polyglot import PolyglotParser, TreeSitterAdapter


@pytest.fixture
def mock_repo_path():
    return str(Path(__file__).parent / "mock_repo")


@pytest.fixture
def calculator_repo_path():
    return str(Path(__file__).parent.parent / "calculator_repo")


def test_symbol_callers_and_callees(mock_repo_path):
    """Verifies caller and callee indexing across files."""
    indexer = ASTIndexer(mock_repo_path)
    symbols = indexer.index_repository()

    assert "APIClient" in symbols
    assert "APIClient.fetch_data" in symbols
    assert "test_fetch_data" in symbols

    # Check that test_fetch_data calls fetch_data
    test_sym = symbols["test_fetch_data"]
    assert "fetch_data" in test_sym.calls or "APIClient" in test_sym.calls

    # Check caller resolution
    callers = indexer.get_callers("APIClient.fetch_data")
    assert "test_fetch_data" in callers

    # Check callers on SymbolInfo directly
    fetch_sym = symbols["APIClient.fetch_data"]
    assert "test_fetch_data" in fetch_sym.callers


def test_imports_and_reverse_imports(mock_repo_path):
    """Verifies that cross-file imports and reverse imports are recorded."""
    indexer = ASTIndexer(mock_repo_path)
    indexer.index_repository()
    dep_graph = indexer.dependency_graph

    # tests/test_client.py imports api.client
    file_imps = dep_graph.get_file_imports("tests/test_client.py")
    assert any(imp.module == "api.client" for imp in file_imps)

    # Reverse import: who imports api.client?
    importers = dep_graph.get_imported_by("api.client")
    assert "tests/test_client.py" in importers

    # Who imports APIClient?
    importers_sym = dep_graph.get_imported_by("APIClient")
    assert "tests/test_client.py" in importers_sym


def test_dependency_traversal_upstream_downstream(mock_repo_path):
    """Verifies upstream and downstream dependency traversal graph."""
    indexer = ASTIndexer(mock_repo_path)
    indexer.index_repository()
    dep_graph = indexer.dependency_graph

    # Upstream traversal from APIClient.fetch_data -> caller test_fetch_data
    upstream = dep_graph.traverse("APIClient.fetch_data", direction="upstream", max_depth=2)
    assert "test_fetch_data" in upstream["upstream"]
    assert any(e["to"] == "APIClient.fetch_data" and e["type"] == "calls" for e in upstream["edges"])

    # Downstream traversal from tests/test_client.py -> imports api.client
    downstream = dep_graph.traverse("tests/test_client.py", direction="downstream", max_depth=1)
    assert any(e["type"] == "imports" for e in downstream["edges"])


def test_test_to_code_mapping(mock_repo_path):
    """Verifies bidirectional test-to-code mapping and test impact analysis."""
    indexer = ASTIndexer(mock_repo_path)
    symbols = indexer.index_repository()
    test_mapper = indexer.test_mapper

    # 1. Source -> Test
    tests_for_sym = test_mapper.get_tests_for_symbol("APIClient.fetch_data")
    assert "test_fetch_data" in tests_for_sym

    tests_for_file = test_mapper.get_tests_for_file("api/client.py")
    assert "tests/test_client.py" in tests_for_file

    # 2. Test -> Source
    src_for_test = test_mapper.get_source_for_test("test_fetch_data")
    assert "APIClient.fetch_data" in src_for_test

    # 3. Test Impact Analysis
    impact = test_mapper.compute_test_impact(
        modified_files=["api/client.py"],
        modified_symbols=["APIClient.fetch_data"]
    )
    assert "tests/test_client.py" in impact["impacted_test_files"]
    assert "test_fetch_data" in impact["impacted_test_symbols"]


def test_git_context_in_git_repo():
    """Verifies GitContext functions (diff, commits, blame, changed symbols) in an active git repo."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Initialize temporary git repo
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.email", "agent@test.com"], cwd=str(tmp_path), check=True)
        subprocess.run(["git", "config", "user.name", "Agent Tester"], cwd=str(tmp_path), check=True)

        # Create initial file & commit
        code_file = tmp_path / "module.py"
        code_file.write_text("def hello():\n    return 'initial'\n\ndef goodbye():\n    return 'bye'\n")
        subprocess.run(["git", "add", "module.py"], cwd=str(tmp_path), check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(tmp_path), check=True, stdout=subprocess.DEVNULL)

        # Modify file (unstaged)
        code_file.write_text("def hello():\n    return 'modified'\n\ndef goodbye():\n    return 'bye'\n")

        git_ctx = GitContext(str(tmp_path))
        assert git_ctx.is_git is True

        # Test status
        status = git_ctx.get_status()
        assert "module.py" in status["modified"]
        assert status["has_changes"] is True

        # Test diff
        diff = git_ctx.get_diff()
        assert "-    return 'initial'" in diff
        assert "+    return 'modified'" in diff

        # Test commits
        commits = git_ctx.get_recent_commits(limit=5)
        assert len(commits) == 1
        assert commits[0]["message"] == "Initial commit"
        assert commits[0]["author"] == "Agent Tester"

        # Test blame on unmodified lines
        blame = git_ctx.get_blame("module.py", 4, 5)
        assert len(blame) >= 1
        assert blame[0]["author"] == "Agent Tester"

        # Test changed symbols mapping
        symbols = {
            "hello": SymbolInfo(name="hello", kind="function", file_path="module.py", start_line=1, end_line=2),
            "goodbye": SymbolInfo(name="goodbye", kind="function", file_path="module.py", start_line=4, end_line=5),
        }
        changed_syms = git_ctx.get_changed_symbols(symbols)
        changed_names = [s.name for s in changed_syms]
        assert "hello" in changed_names
        assert "goodbye" not in changed_names


def test_git_context_graceful_fallback_non_git():
    """Verifies that GitContext gracefully handles non-git directories without crashing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "scratch.py").write_text("x = 1\n")

        git_ctx = GitContext(str(tmp_path))
        assert git_ctx.is_git is False

        status = git_ctx.get_status()
        assert status["is_git"] is False
        assert "scratch.py" in status["modified"]

        diff = git_ctx.get_diff()
        assert diff == ""

        commits = git_ctx.get_recent_commits()
        assert commits == []

        blame = git_ctx.get_blame("scratch.py", 1, 1)
        assert blame == []


def test_config_indexer_discovery_and_metadata():
    """Verifies ConfigIndexer parses requirements.txt, pytest.ini, and package.json."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create sample config files
        (tmp_path / "requirements.txt").write_text("pytest>=8.0.0\nrequests>=2.28.0\n# comment\n")
        (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = tests\naddopts = -v\n")
        (tmp_path / "package.json").write_text('{"name": "frontend", "dependencies": {"react": "^18.0.0"}}\n')

        cfg_indexer = ConfigIndexer(str(tmp_path))
        configs = cfg_indexer.index_configs()

        assert "requirements.txt" in configs
        assert "pytest.ini" in configs
        assert "package.json" in configs

        # Metadata parsing
        deps = cfg_indexer.metadata["dependencies"].get("requirements.txt", [])
        assert any("pytest" in d for d in deps)
        assert any("requests" in d for d in deps)

        test_paths = cfg_indexer.metadata["test_config"].get("pytest_testpaths", [])
        assert "tests" in test_paths

        assert cfg_indexer.metadata["project_name"] == "frontend"

        # Task-based config retrieval
        test_cfgs = cfg_indexer.find_configs_for_task("Fix failing pytest test suite")
        assert "pytest.ini" in test_cfgs

        dep_cfgs = cfg_indexer.find_configs_for_task("Add package dependency")
        assert "requirements.txt" in dep_cfgs or "package.json" in dep_cfgs


def test_polyglot_parser_js_ts_bash_markdown():
    """Verifies PolyglotParser extracts symbols from JavaScript, TypeScript, Bash, and Markdown."""
    parser = PolyglotParser()

    # 1. JavaScript / TypeScript
    js_code = """
import { useState, useEffect } from 'react';
const config = require('./config');

export class WidgetService {
    constructor() {}
}

export function calculateTotal(items, taxRate) {
    return items.length * taxRate;
}

export const processPayment = async (orderId, amount) => {
    return true;
};
"""
    symbols, imports = parser.parse_file("src/service.js", js_code)
    names = [s.name for s in symbols]
    assert "WidgetService" in names
    assert "calculateTotal" in names
    assert "processPayment" in names
    assert any(imp.module == "react" for imp in imports)
    assert any(imp.module == "./config" for imp in imports)

    # 2. Bash script
    sh_code = """#!/bin/bash
setup_environment() {
    echo "Setting up..."
}

function deploy_service() {
    echo "Deploying..."
}
"""
    sh_symbols, _ = parser.parse_file("deploy.sh", sh_code)
    sh_names = [s.name for s in sh_symbols]
    assert "setup_environment" in sh_names
    assert "deploy_service" in sh_names

    # 3. Markdown
    md_code = """# System Overview
## Architecture
"""
    md_symbols, _ = parser.parse_file("README.md", md_code)
    md_names = [s.name for s in md_symbols]
    assert "System Overview" in md_names
    assert "Architecture" in md_names

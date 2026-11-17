import pytest
from pathlib import Path
from agent.explorer.ast_indexer import ASTIndexer
from agent.execution.sandbox import ExecutionSandbox
from agent.tools.file_tools import FileToolHandler

def test_ast_indexer():
    mock_dir = Path(__file__).parent / "mock_repo"
    indexer = ASTIndexer(str(mock_dir))
    symbols = indexer.index_repository()

    assert "APIClient" in symbols
    assert "APIClient.fetch_data" in symbols
    
    sym = symbols["APIClient.fetch_data"]
    assert sym.kind == "method"
    assert "endpoint" in sym.arguments
    
    source = indexer.get_symbol_source(sym)
    assert "def fetch_data" in source

def test_execution_sandbox():
    mock_dir = Path(__file__).parent / "mock_repo"
    sandbox = ExecutionSandbox(str(mock_dir), allow_process_fallback=True)
    
    result = sandbox.run_pytest()
    assert result.passed is True
    assert result.exit_code == 0

def test_file_tools_security():
    mock_dir = Path(__file__).parent / "mock_repo"
    handler = FileToolHandler(str(mock_dir))

    # Safe read
    content = handler.read_file("api/client.py")
    assert "class APIClient" in content

    # Traversal attempt should raise PermissionError
    with pytest.raises(PermissionError):
        handler.read_file("../../outside.txt")

"""Tests for Polyglot Tree-sitter CST parsing and heuristic fallbacks."""

import pytest
from agent.explorer.polyglot import TreeSitterAdapter, PolyglotParser
from agent.core.state import SymbolInfo


class MockCSTNode:
    """Simulates a Tree-sitter CST Node hierarchy."""
    def __init__(self, node_type: str, text: str = "", start_point=(0, 0), end_point=(0, 0), children=None, fields=None):
        self.type = node_type
        self.text = text.encode("utf-8") if isinstance(text, str) else text
        self.start_point = start_point
        self.end_point = end_point
        self.children = children or []
        self._fields = fields or {}

    def child_by_field_name(self, name: str):
        return self._fields.get(name)


class MockTree:
    """Simulates a Tree-sitter syntax tree."""
    def __init__(self, root_node):
        self.root_node = root_node


class MockTreeSitterParser:
    """Simulates a Tree-sitter Parser object."""
    def __init__(self, tree):
        self._tree = tree

    def parse(self, source_bytes: bytes):
        return self._tree


def test_treesitter_heuristic_fallback_when_bindings_absent():
    """Verify polyglot falls back to built-in lexers when tree-sitter grammar is absent."""
    parser = PolyglotParser()
    js_code = """
    class AuthService {
        async login(user, pass) {
            return true;
        }
    }
    function validateToken(token) {
        return token.isValid();
    }
    """
    symbols, imports = parser.parse_file("src/auth.js", js_code)
    assert len(symbols) >= 2
    names = [s.name for s in symbols]
    assert "AuthService" in names
    assert any("validateToken" in n or "login" in n for n in names)


def test_treesitter_cst_symbol_extraction():
    """Verify TreeSitterAdapter traverses CST nodes and extracts classes, functions, params, and calls."""
    adapter = TreeSitterAdapter()

    # Construct a mock CST tree for:
    # class Calculator {
    #     add(a, b) {
    #         logger.log("adding");
    #         return a + b;
    #     }
    # }
    call_func_node = MockCSTNode("identifier", text="logger.log")
    call_node = MockCSTNode(
        "call_expression",
        children=[],
        fields={"function": call_func_node}
    )

    param_a = MockCSTNode("identifier", text="a")
    param_b = MockCSTNode("identifier", text="b")
    params_node = MockCSTNode("parameters", children=[param_a, param_b])

    method_name = MockCSTNode("identifier", text="add")
    method_node = MockCSTNode(
        "method_definition",
        start_point=(2, 4),
        end_point=(6, 5),
        children=[params_node, call_node],
        fields={"name": method_name, "parameters": params_node}
    )

    class_name = MockCSTNode("identifier", text="Calculator")
    class_node = MockCSTNode(
        "class_declaration",
        start_point=(1, 0),
        end_point=(7, 1),
        children=[method_node],
        fields={"name": class_name}
    )

    root_node = MockCSTNode("program", children=[class_node])
    mock_tree = MockTree(root_node)
    mock_parser = MockTreeSitterParser(mock_tree)

    # Register mock parser
    adapter.register_parser("javascript", mock_parser)

    symbols = adapter.parse_with_tree_sitter("javascript", "dummy source", "src/calc.js")
    assert symbols is not None
    assert len(symbols) == 2

    # Verify Class symbol
    class_sym = symbols[0]
    assert class_sym.name == "Calculator"
    assert class_sym.kind == "class"
    assert class_sym.start_line == 2
    assert class_sym.end_line == 8

    # Verify Method symbol
    method_sym = symbols[1]
    assert method_sym.name == "Calculator.add"
    assert method_sym.kind == "method"
    assert method_sym.start_line == 3
    assert method_sym.end_line == 7
    assert method_sym.arguments == ["a", "b"]
    assert "logger.log" in method_sym.calls


def test_treesitter_safe_recovery_on_corrupt_cst():
    """Verify parse_with_tree_sitter returns None on exceptions during CST traversal."""
    adapter = TreeSitterAdapter()

    class ExplodingParser:
        def parse(self, source_bytes):
            raise RuntimeError("Parser internal segment fault")

    adapter.register_parser("python", ExplodingParser())
    result = adapter.parse_with_tree_sitter("python", "def broken():", "test.py")
    assert result is None  # Must gracefully return None to trigger fallback


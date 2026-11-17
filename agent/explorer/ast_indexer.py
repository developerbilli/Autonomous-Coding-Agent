"""Unified Repository Intelligence and AST Indexer.

Combines Python AST parsing, cross-file symbol references, dependency traversal,
Git-based change context, test-to-code mapping, polyglot language parsing,
and configuration indexing into a single queryable engine.
"""

import ast
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from agent.core.state import SymbolInfo, ImportInfo
from agent.explorer.dependency_graph import DependencyGraph
from agent.explorer.git_context import GitContext
from agent.explorer.test_mapper import TestCodeMapper
from agent.explorer.config_indexer import ConfigIndexer
from agent.explorer.polyglot import PolyglotParser

try:
    from langsmith import traceable
except ImportError:
    def traceable(name=None, run_type=None, **kwargs):
        def decorator(func):
            return func
        return decorator


class ASTVisitor(ast.NodeVisitor):
    """Parses Python AST nodes to extract classes, functions, calls, and imports."""

    def __init__(self, file_path: str, source_code: str):
        self.file_path = file_path
        self.source_code = source_code
        self.symbols: Dict[str, SymbolInfo] = {}
        self.imports: List[ImportInfo] = []
        self.current_class: Optional[str] = None

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(ImportInfo(
                module=alias.name,
                names=[],
                alias=alias.asname,
                file_path=self.file_path,
                lineno=node.lineno,
            ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        mod = node.module or ""
        names = [alias.name for alias in node.names]
        self.imports.append(ImportInfo(
            module=mod,
            names=names,
            file_path=self.file_path,
            lineno=node.lineno,
        ))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        class_name = node.name
        docstring = ast.get_docstring(node)
        
        info = SymbolInfo(
            name=class_name,
            kind="class",
            file_path=self.file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            docstring=docstring,
            language="python",
        )
        self.symbols[class_name] = info
        
        previous_class = self.current_class
        self.current_class = class_name
        self.generic_visit(node)
        self.current_class = previous_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._record_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._record_function(node, is_async=True)

    def _record_function(self, node, is_async: bool):
        args = [arg.arg for arg in node.args.args]
        docstring = ast.get_docstring(node)
        
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    # Capture attribute call (e.g. self.add, client.fetch_data, math.sqrt)
                    calls.append(child.func.attr)

        qualified_name = f"{self.current_class}.{node.name}" if self.current_class else node.name
        kind = "method" if self.current_class else "function"

        info = SymbolInfo(
            name=qualified_name,
            kind=kind,
            file_path=self.file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            docstring=docstring,
            arguments=args,
            calls=calls,
            language="python",
        )
        self.symbols[qualified_name] = info
        self.generic_visit(node)


class ASTIndexer:
    """Enterprise repository intelligence engine.
    
    Indexes Python codebases, polyglot languages, dependencies,
    callers/callees, git change context, test mappings, and configuration files.
    """
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.symbols: Dict[str, SymbolInfo] = {}
        
        # Subsystem engines
        self.dependency_graph = DependencyGraph()
        self.git_context = GitContext(str(self.repo_path))
        self.test_mapper = TestCodeMapper(str(self.repo_path), self.dependency_graph)
        self.config_indexer = ConfigIndexer(str(self.repo_path))
        self.polyglot_parser = PolyglotParser()

    @traceable(name="Repository Intelligence Indexing")
    def index_repository(self) -> Dict[str, SymbolInfo]:
        """Walks the repository and parses symbols, dependencies, configs, tests, and git context."""
        self.symbols.clear()
        self.dependency_graph = DependencyGraph()
        self.test_mapper = TestCodeMapper(str(self.repo_path), self.dependency_graph)
        
        # 1. Parse all source files
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if not d.startswith((".", "__pycache__", "venv", ".venv", "env", "node_modules"))]
            
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.repo_path)
                
                # Python files
                if file.endswith(".py"):
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            source = f.read()
                        tree = ast.parse(source, filename=full_path)
                        visitor = ASTVisitor(file_path=rel_path, source_code=source)
                        visitor.visit(tree)
                        
                        # Register symbols and imports
                        for sym in visitor.symbols.values():
                            self.symbols[sym.name] = sym
                            self.dependency_graph.register_symbol(sym)
                        
                        for imp in visitor.imports:
                            self.dependency_graph.register_import(rel_path, imp)
                    except (SyntaxError, UnicodeDecodeError):
                        continue
                
                # Polyglot files (JS, TS, Bash, Markdown, etc.)
                elif self.polyglot_parser.supports_file(rel_path):
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            source = f.read()
                        poly_syms, poly_imps = self.polyglot_parser.parse_file(rel_path, source)
                        for sym in poly_syms:
                            self.symbols[sym.name] = sym
                            self.dependency_graph.register_symbol(sym)
                        for imp in poly_imps:
                            self.dependency_graph.register_import(rel_path, imp)
                    except Exception:
                        continue

        # 2. Resolve cross-file callers and callers index
        self.dependency_graph.resolve_callers()

        # 3. Build test-to-code bidirectional mappings
        self.test_mapper.build_mappings(self.symbols)

        # 4. Index configuration files
        self.config_indexer.index_configs()

        return self.symbols

    @traceable(name="AST Code Retrieval")
    def retrieve_context(self, task: str) -> Dict[str, Any]:
        """Backward-compatible retrieval: extracts relevant symbols and snippets."""
        if not self.symbols:
            self.index_repository()

        keywords = [w.strip(".,;:\"'") for w in task.split() if len(w) > 3]
        relevant_files = set()
        retrieved_code = {}

        for kw in keywords:
            matches = self.find_symbols_by_name(kw)
            for sym in matches[:5]:
                relevant_files.add(sym.file_path)
                source_snippet = self.get_symbol_source(sym)
                retrieved_code[f"{sym.file_path}::{sym.name}"] = source_snippet

        return {
            "relevant_files": list(relevant_files),
            "retrieved_code": retrieved_code,
        }

    @traceable(name="Rich Repository Context Retrieval")
    def retrieve_rich_context(self, task: str) -> Dict[str, Any]:
        """Comprehensive repository understanding retrieval.
        
        Expands keyword matches with:
        1. Primary symbol matches
        2. Dependency traversal (callers, callees, imported modules)
        3. Test-to-code mapping (associated unit and edge tests)
        4. Configuration and environment files
        5. Git change context and diffs
        """
        if not self.symbols:
            self.index_repository()

        keywords = [w.strip(".,;:\"'") for w in task.split() if len(w) > 3]
        relevant_files: Set[str] = set()
        retrieved_code: Dict[str, str] = {}
        matched_symbols: List[SymbolInfo] = []

        # 1. Primary symbol matches
        for kw in keywords:
            matches = self.find_symbols_by_name(kw)
            for sym in matches[:5]:
                matched_symbols.append(sym)
                relevant_files.add(sym.file_path)
                source_snippet = self.get_symbol_source(sym)
                retrieved_code[f"{sym.file_path}::{sym.name}"] = source_snippet

        # 1b. Direct filename matching: match task keywords against repository file names
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if not d.startswith((".", "__pycache__", "venv", ".venv", "env", "node_modules"))]
            for file in files:
                if file.endswith((".py", ".js", ".ts", ".go", ".rs", ".java", ".json", ".md")):
                    rel_file = os.path.relpath(os.path.join(root, file), self.repo_path)
                    for kw in keywords:
                        kw_lower = kw.lower()
                        file_lower = file.lower()
                        if (kw_lower in file_lower or file_lower.replace(".py", "") in kw_lower) and len(kw_lower) >= 3:
                            relevant_files.add(rel_file)
                            try:
                                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                                    snippet = f.read()
                                retrieved_code[rel_file] = snippet[:3000]
                            except Exception:
                                pass

        # 2. Dependency traversal & callers expansion
        traversed_deps: Dict[str, Any] = {}
        caller_map: Dict[str, List[str]] = {}
        for sym in matched_symbols:
            callers = self.dependency_graph.get_callers(sym.name)
            if callers:
                caller_map[sym.name] = callers
                for c_name in callers:
                    c_sym = self.symbols.get(c_name)
                    if c_sym:
                        relevant_files.add(c_sym.file_path)
                        retrieved_code[f"{c_sym.file_path}::{c_sym.name}"] = self.get_symbol_source(c_sym)

            # Traverse 1-hop upstream/downstream
            dep_info = self.dependency_graph.traverse(sym.name, direction="both", max_depth=1)
            traversed_deps[sym.name] = dep_info
            for node in dep_info.get("upstream", []):
                if node in self.symbols:
                    relevant_files.add(self.symbols[node].file_path)

        # 3. Test-to-code mapping expansion
        matched_tests: Dict[str, List[str]] = {}
        for sym in matched_symbols:
            tests = self.test_mapper.get_tests_for_symbol(sym.name)
            if tests:
                matched_tests[sym.name] = tests
                for t_name in tests:
                    t_sym = self.symbols.get(t_name)
                    if t_sym:
                        relevant_files.add(t_sym.file_path)
                        retrieved_code[f"{t_sym.file_path}::{t_sym.name}"] = self.get_symbol_source(t_sym)

        for f_path in list(relevant_files):
            test_files = self.test_mapper.get_tests_for_file(f_path)
            for tf in test_files:
                relevant_files.add(tf)

        # 4. Relevant configuration files
        configs = self.config_indexer.find_configs_for_task(task)

        # 5. Git change context
        git_summary = self.git_context.get_context_summary(self.symbols)
        # If there are modified files in git, prioritize them
        for mod_f in git_summary.get("modified_files", []):
            if (self.repo_path / mod_f).exists():
                relevant_files.add(mod_f)

        return {
            "relevant_files": sorted(list(relevant_files)),
            "retrieved_code": retrieved_code,
            "primary_symbols": [s.name for s in matched_symbols],
            "callers": caller_map,
            "dependency_traversal": traversed_deps,
            "mapped_tests": matched_tests,
            "config_files": configs,
            "git_context": git_summary,
            "test_impact": self.test_mapper.compute_test_impact(
                list(relevant_files), [s.name for s in matched_symbols]
            ),
        }

    def find_symbols_by_name(self, query: str) -> List[SymbolInfo]:
        """Finds symbols whose names match or contain the query string."""
        q = query.lower()
        return [sym for name, sym in self.symbols.items() if q in name.lower()]

    def get_symbol_source(self, symbol: SymbolInfo) -> str:
        """Extracts the exact source lines corresponding to the symbol."""
        full_path = self.repo_path / symbol.file_path
        if not full_path.exists():
            return ""
        
        try:
            lines = full_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            start = max(0, symbol.start_line - 1)
            end = symbol.end_line
            return "\n".join(lines[start:end])
        except Exception:
            return ""

    # Convenience helper facades
    def get_callers(self, symbol_name: str) -> List[str]:
        return self.dependency_graph.get_callers(symbol_name)

    def get_callees(self, symbol_name: str) -> List[str]:
        return self.dependency_graph.get_callees(symbol_name)

    def traverse_dependencies(self, target: str, direction: str = "both", max_depth: int = 2) -> Dict[str, Any]:
        return self.dependency_graph.traverse(target, direction=direction, max_depth=max_depth)

    def get_tests_for_symbol(self, symbol_name: str) -> List[str]:
        return self.test_mapper.get_tests_for_symbol(symbol_name)

    def get_tests_for_file(self, file_path: str) -> List[str]:
        return self.test_mapper.get_tests_for_file(file_path)

    def get_git_status(self) -> Dict[str, Any]:
        return self.git_context.get_status()

    def get_git_diff(self, cached: bool = False, file_path: Optional[str] = None) -> str:
        return self.git_context.get_diff(cached=cached, file_path=file_path)

    def get_configs(self) -> Dict[str, str]:
        return self.config_indexer.configs

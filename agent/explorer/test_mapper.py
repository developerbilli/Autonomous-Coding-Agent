"""Bidirectional Test-to-Code mapping and test impact analyzer.

Maps implementation symbols/files to their corresponding test cases,
maps test cases back to the source code under test,
and computes targeted test subsets for modified code.
"""

from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from agent.core.state import SymbolInfo
from agent.explorer.dependency_graph import DependencyGraph


class TestCodeMapper:
    """Discovers and maps tests to source code and vice versa."""
    __test__ = False

    def __init__(self, repo_path: str, dependency_graph: DependencyGraph):
        self.repo_path = Path(repo_path).resolve()
        self.dep_graph = dependency_graph
        
        # test_file -> List[test_symbol_names]
        self.test_files: Dict[str, List[str]] = {}
        # source_file -> Set[test_file]
        self.source_to_test_files: Dict[str, Set[str]] = {}
        # source_symbol -> Set[test_symbol]
        self.source_to_test_symbols: Dict[str, Set[str]] = {}
        # test_symbol -> Set[source_symbol]
        self.test_to_source_symbols: Dict[str, Set[str]] = {}

    def is_test_file(self, file_path: str) -> bool:
        """Determines if a file path belongs to a test suite."""
        path_str = file_path.lower().replace("\\", "/")
        p = Path(path_str)
        return (
            "test" in p.parts
            or p.name.startswith("test_")
            or p.name.endswith("_test.py")
        )

    def is_test_symbol(self, symbol: SymbolInfo) -> bool:
        """Determines if a symbol is a test function, method, or class."""
        if not self.is_test_file(symbol.file_path):
            return False
        short = symbol.name.split(".")[-1]
        return short.startswith("test_") or short.startswith("Test") or short.endswith("_test")

    def build_mappings(self, symbols: Dict[str, SymbolInfo]):
        """Builds bidirectional test-to-code and code-to-test mappings."""
        self.test_files.clear()
        self.source_to_test_files.clear()
        self.source_to_test_symbols.clear()
        self.test_to_source_symbols.clear()

        # 1. Identify all test files and test symbols
        for name, sym in symbols.items():
            if self.is_test_file(sym.file_path):
                if sym.file_path not in self.test_files:
                    self.test_files[sym.file_path] = []
                if self.is_test_symbol(sym):
                    self.test_files[sym.file_path].append(name)

        # 2. File-level mapping via imports and naming conventions
        for name, sym in symbols.items():
            if self.is_test_file(sym.file_path):
                continue
            
            src_file = sym.file_path
            stem = Path(src_file).stem  # e.g. "core" or "client" or "calculator"
            
            # Check reverse imports: which test files import this source file?
            importers = self.dep_graph.get_imported_by(src_file)
            for imp_file in importers:
                if self.is_test_file(imp_file):
                    self._link_source_and_test_file(src_file, imp_file)

            # Check naming conventions: test_{stem}.py or {stem}_test.py
            for test_file in self.test_files:
                test_stem = Path(test_file).stem
                if (
                    f"test_{stem}" in test_stem
                    or f"{stem}_test" in test_stem
                    or stem in test_stem
                ):
                    self._link_source_and_test_file(src_file, test_file)

        # 3. Symbol-level mapping via AST calls, callers, and naming conventions
        for src_name, src_sym in symbols.items():
            if self.is_test_file(src_sym.file_path):
                continue

            short_src = src_name.split(".")[-1]

            # A. Check callers in test files
            callers = self.dep_graph.get_callers(src_name)
            for caller in callers:
                caller_sym = symbols.get(caller)
                if caller_sym and self.is_test_symbol(caller_sym):
                    self._link_source_and_test_symbol(src_name, caller)

            # B. Check test symbols whose names contain the source symbol name
            for test_file, test_syms in self.test_files.items():
                for t_sym_name in test_syms:
                    t_short = t_sym_name.split(".")[-1].lower()
                    # e.g. test_divide matches divide
                    if f"test_{short_src.lower()}" in t_short or short_src.lower() in t_short:
                        self._link_source_and_test_symbol(src_name, t_sym_name)

            # C. Check test calls: does the test call short_src?
            for test_file, test_syms in self.test_files.items():
                for t_sym_name in test_syms:
                    t_sym = symbols.get(t_sym_name)
                    if t_sym and (short_src in t_sym.calls or src_name in t_sym.calls):
                        self._link_source_and_test_symbol(src_name, t_sym_name)

    def _link_source_and_test_file(self, src_file: str, test_file: str):
        if src_file not in self.source_to_test_files:
            self.source_to_test_files[src_file] = set()
        self.source_to_test_files[src_file].add(test_file)

    def _link_source_and_test_symbol(self, src_sym: str, test_sym: str):
        if src_sym not in self.source_to_test_symbols:
            self.source_to_test_symbols[src_sym] = set()
        self.source_to_test_symbols[src_sym].add(test_sym)

        if test_sym not in self.test_to_source_symbols:
            self.test_to_source_symbols[test_sym] = set()
        self.test_to_source_symbols[test_sym].add(src_sym)

    def get_tests_for_symbol(self, symbol_name: str) -> List[str]:
        """Returns test symbols that test the given source symbol."""
        tests = set(self.source_to_test_symbols.get(symbol_name, set()))
        if not tests and "." in symbol_name:
            short = symbol_name.split(".")[-1]
            tests = set(self.source_to_test_symbols.get(short, set()))
        return sorted(list(tests))

    def get_tests_for_file(self, file_path: str) -> List[str]:
        """Returns test files that test the given source file."""
        return sorted(list(self.source_to_test_files.get(file_path, set())))

    def get_source_for_test(self, test_name_or_file: str) -> List[str]:
        """Returns source symbols or files tested by the given test."""
        if test_name_or_file in self.test_to_source_symbols:
            return sorted(list(self.test_to_source_symbols[test_name_or_file]))
        
        # Check if it's a test file
        src_files = []
        for src_file, test_files in self.source_to_test_files.items():
            if test_name_or_file in test_files:
                src_files.append(src_file)
        return sorted(src_files)

    def compute_test_impact(self, modified_files: List[str], modified_symbols: List[str]) -> Dict[str, Any]:
        """Computes the prioritized set of tests to run based on modified files and symbols."""
        impacted_test_files: Set[str] = set()
        impacted_test_symbols: Set[str] = set()

        for sym in modified_symbols:
            tests = self.get_tests_for_symbol(sym)
            impacted_test_symbols.update(tests)
            for t in tests:
                t_sym = self.dep_graph.symbol_table.get(t)
                if t_sym:
                    impacted_test_files.add(t_sym.file_path)

        for file_path in modified_files:
            test_files = self.get_tests_for_file(file_path)
            impacted_test_files.update(test_files)

        return {
            "impacted_test_files": sorted(list(impacted_test_files)),
            "impacted_test_symbols": sorted(list(impacted_test_symbols)),
            "total_impacted_tests": len(impacted_test_symbols),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serializes test mapping summary for state inspection."""
        return {
            "test_files_count": len(self.test_files),
            "test_files": list(self.test_files.keys()),
            "source_to_test_files": {k: sorted(list(v)) for k, v in self.source_to_test_files.items()},
            "source_to_test_symbols": {k: sorted(list(v)) for k, v in self.source_to_test_symbols.items() if v},
        }

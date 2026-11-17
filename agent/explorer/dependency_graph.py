"""Symbol reference and dependency traversal graph.

Tracks cross-file imports, call graphs (callers and callees),
and traverses upstream/downstream symbol and file dependencies.
"""

from typing import Dict, List, Set, Optional, Any, Literal
from pathlib import Path
from agent.core.state import SymbolInfo, ImportInfo


class DependencyGraph:
    """Graph model tracking imports, callers, callees, and symbol dependencies."""

    def __init__(self):
        # file_path -> List[ImportInfo]
        self.file_imports: Dict[str, List[ImportInfo]] = {}
        # imported_name_or_module -> Set[file_path]
        self.reverse_imports: Dict[str, Set[str]] = {}
        
        # qualified_symbol -> Set[called_identifier]
        self.callees: Dict[str, Set[str]] = {}
        # symbol_name_or_qualified -> Set[calling_qualified_symbol]
        self.callers: Dict[str, Set[str]] = {}
        
        # file_path -> List[qualified_symbol]
        self.file_symbols: Dict[str, List[str]] = {}
        # symbol_name -> SymbolInfo
        self.symbol_table: Dict[str, SymbolInfo] = {}

    def register_import(self, file_path: str, import_info: ImportInfo):
        """Records an import statement in a file."""
        if file_path not in self.file_imports:
            self.file_imports[file_path] = []
        self.file_imports[file_path].append(import_info)

        # Index reverse imports for both module and specific imported symbols
        mod_key = import_info.module
        if mod_key not in self.reverse_imports:
            self.reverse_imports[mod_key] = set()
        self.reverse_imports[mod_key].add(file_path)

        for name in import_info.names:
            full_name = f"{import_info.module}.{name}" if import_info.module else name
            if full_name not in self.reverse_imports:
                self.reverse_imports[full_name] = set()
            self.reverse_imports[full_name].add(file_path)
            if name not in self.reverse_imports:
                self.reverse_imports[name] = set()
            self.reverse_imports[name].add(file_path)

    def register_symbol(self, symbol: SymbolInfo):
        """Registers a symbol in the graph."""
        self.symbol_table[symbol.name] = symbol
        if symbol.file_path not in self.file_symbols:
            self.file_symbols[symbol.file_path] = []
        if symbol.name not in self.file_symbols[symbol.file_path]:
            self.file_symbols[symbol.file_path].append(symbol.name)

        if symbol.name not in self.callees:
            self.callees[symbol.name] = set()
        for call in symbol.calls:
            self.callees[symbol.name].add(call)

    def resolve_callers(self):
        """Resolves raw called identifiers across all symbols into a caller index.
        
        Also populates symbol.callers and symbol.imports on SymbolInfo instances.
        """
        # Clear caller index before resolving
        self.callers.clear()

        # Build name-to-qualified-symbols map for fast lookup
        short_to_qualified: Dict[str, List[str]] = {}
        for qual_name in self.symbol_table:
            short_name = qual_name.split(".")[-1]
            if short_name not in short_to_qualified:
                short_to_qualified[short_name] = []
            short_to_qualified[short_name].append(qual_name)

        for caller_sym, called_names in self.callees.items():
            for called in called_names:
                # Direct match
                if called in self.symbol_table:
                    self._add_caller(called, caller_sym)
                
                # Method or short name match (e.g. "fetch_data" -> "APIClient.fetch_data")
                if called in short_to_qualified:
                    for qual in short_to_qualified[called]:
                        self._add_caller(qual, caller_sym)
                
                # Also index under short name
                self._add_caller(called, caller_sym)

        # Sync resolved callers and file imports back to SymbolInfo objects
        for sym_name, sym in self.symbol_table.items():
            direct_callers = sorted(list(self.callers.get(sym_name, set())))
            sym.callers = direct_callers
            
            # File imports
            file_imps = self.file_imports.get(sym.file_path, [])
            sym.imports = [
                f"{imp.module}:{','.join(imp.names)}" if imp.names else imp.module
                for imp in file_imps
            ]

    def _add_caller(self, target: str, caller: str):
        if target not in self.callers:
            self.callers[target] = set()
        self.callers[target].add(caller)

    def get_callers(self, symbol_name: str) -> List[str]:
        """Returns qualified symbols that call the given symbol."""
        callers = self.callers.get(symbol_name, set())
        if not callers and "." in symbol_name:
            # Fall back to checking short name
            short = symbol_name.split(".")[-1]
            callers = self.callers.get(short, set())
        # Filter out self-calls for cleaner reporting
        return sorted([c for c in callers if c != symbol_name])

    def get_callees(self, symbol_name: str) -> List[str]:
        """Returns identifiers called by the given symbol."""
        return sorted(list(self.callees.get(symbol_name, set())))

    def get_imported_by(self, file_or_module: str) -> List[str]:
        """Returns file paths that import the given file, module, or symbol."""
        # Normalize file path to module name if necessary
        clean = file_or_module.replace("/", ".").rstrip(".py")
        results = set(self.reverse_imports.get(file_or_module, set()))
        results.update(self.reverse_imports.get(clean, set()))
        # Check module prefix matches
        for key, files in self.reverse_imports.items():
            if key.startswith(clean) or clean.startswith(key):
                results.update(files)
        return sorted(list(results))

    def get_file_imports(self, file_path: str) -> List[ImportInfo]:
        """Returns all import records for a specific file."""
        return self.file_imports.get(file_path, [])

    def get_related_symbols(self, symbol_name: str) -> List[str]:
        """Finds closely related symbols:
        - Siblings in the same class
        - Direct callers
        - Direct callees that exist in symbol_table
        - Symbols defined in the same file
        """
        related: Set[str] = set()
        sym = self.symbol_table.get(symbol_name)
        if not sym:
            return []

        # 1. Siblings in same class or file
        if "." in symbol_name:
            class_prefix = symbol_name.rsplit(".", 1)[0]
            for other_name in self.symbol_table:
                if other_name != symbol_name and other_name.startswith(class_prefix + "."):
                    related.add(other_name)
        
        # 2. File symbols
        for file_sym in self.file_symbols.get(sym.file_path, []):
            if file_sym != symbol_name:
                related.add(file_sym)

        # 3. Direct callers
        for caller in self.get_callers(symbol_name):
            if caller in self.symbol_table:
                related.add(caller)

        # 4. Direct callees that are resolved symbols
        for callee in self.get_callees(symbol_name):
            if callee in self.symbol_table:
                related.add(callee)
            elif "." in callee:
                # check short names
                short = callee.split(".")[-1]
                for qual in self.symbol_table:
                    if qual.endswith("." + short):
                        related.add(qual)

        return sorted(list(related))

    def traverse(
        self,
        target: str,
        direction: Literal["upstream", "downstream", "both"] = "both",
        max_depth: int = 2
    ) -> Dict[str, Any]:
        """Traverses dependencies around a symbol or file.
        
        Returns:
            Dict containing:
                - target: original target
                - upstream: list of callers and importing files
                - downstream: list of callees and imported modules
                - nodes: list of all visited nodes
                - edges: list of {from, to, type: 'calls'|'imports'|'defines'}
        """
        nodes: Set[str] = {target}
        edges: List[Dict[str, str]] = []
        upstream_visited: Set[str] = set()
        downstream_visited: Set[str] = set()

        # Helper: traverse upstream (who calls / imports target)
        def _traverse_upstream(current: str, depth: int):
            if depth > max_depth or current in upstream_visited:
                return
            upstream_visited.add(current)
            nodes.add(current)

            # If current is a symbol, find callers
            if current in self.symbol_table:
                callers = self.get_callers(current)
                for caller in callers:
                    edges.append({"from": caller, "to": current, "type": "calls"})
                    _traverse_upstream(caller, depth + 1)
                
                # File that defines it
                file_path = self.symbol_table[current].file_path
                edges.append({"from": file_path, "to": current, "type": "defines"})
                _traverse_upstream(file_path, depth + 1)
            else:
                # Current might be a file path, find who imports it
                importers = self.get_imported_by(current)
                for imp_file in importers:
                    edges.append({"from": imp_file, "to": current, "type": "imports"})
                    _traverse_upstream(imp_file, depth + 1)

        # Helper: traverse downstream (what does target call / import)
        def _traverse_downstream(current: str, depth: int):
            if depth > max_depth or current in downstream_visited:
                return
            downstream_visited.add(current)
            nodes.add(current)

            # If current is a symbol, find callees
            if current in self.symbol_table:
                for callee in self.get_callees(current):
                    # Check if callee is a known qualified symbol
                    target_sym = callee if callee in self.symbol_table else None
                    if not target_sym and "." in callee:
                        short = callee.split(".")[-1]
                        for qual in self.symbol_table:
                            if qual.endswith("." + short):
                                target_sym = qual
                                break
                    edge_to = target_sym or callee
                    edges.append({"from": current, "to": edge_to, "type": "calls"})
                    if target_sym:
                        _traverse_downstream(target_sym, depth + 1)
            else:
                # Current is a file, find its imports and defined symbols
                for imp in self.get_file_imports(current):
                    edges.append({"from": current, "to": imp.module, "type": "imports"})
                for sym_name in self.file_symbols.get(current, []):
                    edges.append({"from": current, "to": sym_name, "type": "defines"})
                    _traverse_downstream(sym_name, depth + 1)

        if direction in ("upstream", "both"):
            _traverse_upstream(target, 1)
        if direction in ("downstream", "both"):
            _traverse_downstream(target, 1)

        # Remove target from upstream/downstream lists
        upstream_list = sorted(list(upstream_visited - {target}))
        downstream_list = sorted(list(downstream_visited - {target}))

        # Deduplicate edges
        unique_edges = []
        seen_edges = set()
        for e in edges:
            edge_tuple = (e["from"], e["to"], e["type"])
            if edge_tuple not in seen_edges:
                seen_edges.add(edge_tuple)
                unique_edges.append(e)

        return {
            "target": target,
            "direction": direction,
            "max_depth": max_depth,
            "nodes": sorted(list(nodes)),
            "edges": unique_edges,
            "upstream": upstream_list,
            "downstream": downstream_list,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serializes dependency graph summary for state inspection."""
        return {
            "total_symbols": len(self.symbol_table),
            "total_files": len(self.file_symbols),
            "total_imports": sum(len(imps) for imps in self.file_imports.values()),
            "callers_index": {k: sorted(list(v)) for k, v in self.callers.items() if v},
            "reverse_imports": {k: sorted(list(v)) for k, v in self.reverse_imports.items() if v},
        }

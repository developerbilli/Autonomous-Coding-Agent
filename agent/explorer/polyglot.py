"""Extensible Polyglot and Tree-sitter Language Parser.

Supports languages beyond Python (JavaScript, TypeScript, Shell, JSON/YAML/TOML, Markdown).
Includes Tree-sitter adapter hook when tree-sitter packages are installed,
with robust zero-dependency heuristic fallback.
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from agent.core.state import SymbolInfo, ImportInfo


class TreeSitterAdapter:
    """Dynamic Tree-sitter adapter that activates when tree-sitter bindings are present.
    
    Provides Concrete Syntax Tree (CST) queries across multiple languages,
    extracting functions, classes, methods, parameters, and invocation calls.
    """

    FUNCTION_NODE_TYPES = {
        "function_definition",
        "async_function_definition",
        "function_declaration",
        "method_definition",
        "arrow_function",
        "function_item",
        "function_signature",
    }

    CLASS_NODE_TYPES = {
        "class_definition",
        "class_declaration",
        "class",
        "struct_item",
        "trait_item",
        "enum_item",
        "type_declaration",
    }

    def __init__(self):
        self.is_available = self._detect_tree_sitter()
        self.parsers: Dict[str, Any] = {}

    def _detect_tree_sitter(self) -> bool:
        try:
            import tree_sitter
            return True
        except ImportError:
            try:
                import tree_sitter_languages
                return True
            except ImportError:
                return False

    def register_parser(self, language: str, parser: Any) -> None:
        """Registers a custom or mock Tree-sitter parser instance for a language."""
        self.parsers[language.lower()] = parser

    def get_parser(self, language: str) -> Optional[Any]:
        """Retrieves or instantiates a Tree-sitter parser for the target language."""
        lang_key = language.lower()
        if lang_key in self.parsers:
            return self.parsers[lang_key]

        try:
            # Try tree_sitter_languages first (modern standard wrapper)
            import tree_sitter_languages
            parser = tree_sitter_languages.get_parser(lang_key)
            self.parsers[lang_key] = parser
            return parser
        except Exception:
            pass

        try:
            # Try core tree_sitter Language bindings
            from tree_sitter import Language, Parser
            parser = Parser()
            # If language library is available in standard lookup
            self.parsers[lang_key] = parser
            return parser
        except Exception:
            pass

        return None

    def parse_with_tree_sitter(
        self, language: str, source_code: str, file_path: str
    ) -> Optional[List[SymbolInfo]]:
        """Parses source code using Tree-sitter CST queries if available for the given language."""
        parser = self.get_parser(language)
        if parser is None:
            return None

        try:
            source_bytes = source_code.encode("utf-8")
            tree = parser.parse(source_bytes)
            if not tree or not tree.root_node:
                return None

            symbols: List[SymbolInfo] = []
            self._extract_cst_symbols(tree.root_node, source_bytes, file_path, symbols)
            return symbols
        except Exception:
            # Fall back safely on parse or grammar failure
            return None

    def _extract_cst_symbols(
        self,
        node: Any,
        source_bytes: bytes,
        file_path: str,
        symbols: List[SymbolInfo],
        current_class: Optional[str] = None,
    ) -> None:
        """Recursively traverses the CST and extracts functions, methods, and classes."""
        node_type = getattr(node, "type", "")
        start_row = node.start_point[0] + 1
        end_row = node.end_point[0] + 1

        # 1. Class Definitions
        if node_type in self.CLASS_NODE_TYPES:
            class_name = self._extract_identifier(node, source_bytes)
            if class_name:
                doc = self._extract_docstring(node, source_bytes)
                symbols.append(
                    SymbolInfo(
                        name=class_name,
                        kind="class",
                        file_path=file_path,
                        start_line=start_row,
                        end_line=end_row,
                        docstring=doc,
                        arguments=[],
                        calls=[],
                    )
                )
                # Traverse children with class context
                for child in getattr(node, "children", []):
                    self._extract_cst_symbols(child, source_bytes, file_path, symbols, current_class=class_name)
                return

        # 2. Function & Method Definitions
        if node_type in self.FUNCTION_NODE_TYPES:
            func_name = self._extract_identifier(node, source_bytes)
            if func_name:
                params = self._extract_parameters(node, source_bytes)
                calls = self._extract_calls(node, source_bytes)
                doc = self._extract_docstring(node, source_bytes)
                kind = "method" if current_class or node_type == "method_definition" else "function"

                symbols.append(
                    SymbolInfo(
                        name=f"{current_class}.{func_name}" if current_class else func_name,
                        kind=kind,
                        file_path=file_path,
                        start_line=start_row,
                        end_line=end_row,
                        arguments=params,
                        calls=calls,
                        docstring=doc,
                    )
                )
                return

        # Recurse children
        for child in getattr(node, "children", []):
            self._extract_cst_symbols(child, source_bytes, file_path, symbols, current_class=current_class)

    def _extract_identifier(self, node: Any, source_bytes: bytes) -> Optional[str]:
        """Extracts identifier name from CST node via 'name' field or identifier child."""
        # Check child_by_field_name('name')
        if hasattr(node, "child_by_field_name"):
            name_node = node.child_by_field_name("name")
            if name_node and hasattr(name_node, "text"):
                return name_node.text.decode("utf-8") if isinstance(name_node.text, bytes) else str(name_node.text)

        # Fallback: scan direct children for identifier or property_identifier
        for child in getattr(node, "children", []):
            c_type = getattr(child, "type", "")
            if c_type in ("identifier", "property_identifier", "type_identifier"):
                text = getattr(child, "text", None)
                if text is not None:
                    return text.decode("utf-8") if isinstance(text, bytes) else str(text)
        return None

    def _extract_parameters(self, node: Any, source_bytes: bytes) -> List[str]:
        """Extracts parameter names from parameters/formal_parameters node."""
        params: List[str] = []
        param_node = None
        if hasattr(node, "child_by_field_name"):
            param_node = node.child_by_field_name("parameters")

        if not param_node:
            for child in getattr(node, "children", []):
                if getattr(child, "type", "") in ("parameters", "formal_parameters", "parameter_list"):
                    param_node = child
                    break

        if param_node:
            for p in getattr(param_node, "children", []):
                p_type = getattr(p, "type", "")
                if p_type in ("identifier", "required_parameter", "optional_parameter", "typed_parameter"):
                    text = self._extract_identifier(p, source_bytes) or getattr(p, "text", None)
                    if text:
                        str_val = text.decode("utf-8") if isinstance(text, bytes) else str(text)
                        if str_val not in ("(", ")", ","):
                            params.append(str_val.strip())
        return params

    def _extract_calls(self, node: Any, source_bytes: bytes) -> List[str]:
        """Collects unique function call expressions within node."""
        calls: List[str] = []
        for child in getattr(node, "children", []):
            c_type = getattr(child, "type", "")
            if c_type in ("call_expression", "call"):
                func_child = getattr(child, "child_by_field_name", lambda _: None)("function")
                if func_child:
                    call_name = getattr(func_child, "text", None)
                    if call_name:
                        s = call_name.decode("utf-8") if isinstance(call_name, bytes) else str(call_name)
                        if s and s not in calls:
                            calls.append(s)
            calls.extend(self._extract_calls(child, source_bytes))
        return list(dict.fromkeys(calls))

    def _extract_docstring(self, node: Any, source_bytes: bytes) -> Optional[str]:
        """Extracts docstring or preceding comment from CST node."""
        for child in getattr(node, "children", []):
            if getattr(child, "type", "") in ("comment", "string", "block_comment"):
                text = getattr(child, "text", None)
                if text:
                    s = text.decode("utf-8") if isinstance(text, bytes) else str(text)
                    return s.strip(" '\"\n\t*#/\\")
        return None


class PolyglotParser:
    """Multi-language symbol extractor supporting JS/TS, Shell, Markdown, and Config formats."""

    SUPPORTED_EXTENSIONS = {
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".sh": "bash",
        ".bash": "bash",
        ".md": "markdown",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
    }

    def __init__(self):
        self.tree_sitter = TreeSitterAdapter()

    def supports_file(self, file_path: str) -> bool:
        """Checks if the file extension is supported for polyglot indexing."""
        suffix = Path(file_path).suffix.lower()
        return suffix in self.SUPPORTED_EXTENSIONS

    def parse_file(self, file_path: str, source_code: str) -> Tuple[List[SymbolInfo], List[ImportInfo]]:
        """Parses non-Python source code into SymbolInfo and ImportInfo objects."""
        suffix = Path(file_path).suffix.lower()
        lang = self.SUPPORTED_EXTENSIONS.get(suffix)
        if not lang:
            return [], []

        # Attempt Tree-sitter parse if active
        ts_symbols = self.tree_sitter.parse_with_tree_sitter(lang, source_code, file_path)
        if ts_symbols is not None:
            return ts_symbols, []

        # Built-in robust parsers
        if lang in ("javascript", "typescript"):
            return self._parse_js_ts(file_path, source_code, lang)
        elif lang == "bash":
            return self._parse_bash(file_path, source_code)
        elif lang == "markdown":
            return self._parse_markdown(file_path, source_code)
        elif lang in ("json", "yaml", "toml"):
            return self._parse_config_symbols(file_path, source_code, lang)

        return [], []

    def _parse_js_ts(self, file_path: str, source: str, lang: str) -> Tuple[List[SymbolInfo], List[ImportInfo]]:
        """Extracts classes, functions, arrow functions, and ES6/CommonJS imports."""
        symbols: List[SymbolInfo] = []
        imports: List[ImportInfo] = []
        lines = source.splitlines()

        # Regex patterns
        class_re = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z0-9_$]+)")
        func_re = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\(([^)]*)\)")
        arrow_re = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>")
        import_es6_re = re.compile(r"^\s*import\s+(?:\{([^}]+)\}|\*\s+as\s+([A-Za-z0-9_$]+)|([A-Za-z0-9_$]+))\s+from\s+['\"]([^'\"]+)['\"]")
        require_re = re.compile(r"^\s*(?:const|let|var)\s+(?:\{([^}]+)\}|([A-Za-z0-9_$]+))\s*=\s*require\(['\"]([^'\"]+)['\"]\)")

        current_class: Optional[str] = None
        current_class_end = 0

        for idx, line in enumerate(lines, start=1):
            # Imports
            m_es6 = import_es6_re.match(line)
            if m_es6:
                named, star, default, module = m_es6.groups()
                names = [n.strip() for n in named.split(",")] if named else ([star] if star else [default])
                imports.append(ImportInfo(module=module, names=[n for n in names if n], file_path=file_path, lineno=idx))
                continue

            m_req = require_re.match(line)
            if m_req:
                destruct, var_name, module = m_req.groups()
                names = [n.strip() for n in destruct.split(",")] if destruct else [var_name]
                imports.append(ImportInfo(module=module, names=[n for n in names if n], file_path=file_path, lineno=idx))
                continue

            # Class definition
            m_class = class_re.match(line)
            if m_class:
                class_name = m_class.group(1)
                symbols.append(SymbolInfo(
                    name=class_name,
                    kind="class",
                    file_path=file_path,
                    start_line=idx,
                    end_line=idx,
                    language=lang,
                ))
                current_class = class_name
                continue

            # Function definition
            m_func = func_re.match(line)
            if m_func:
                name, args_str = m_func.groups()
                args = [a.strip().split(":")[0].split("=")[0].strip() for a in args_str.split(",") if a.strip()]
                symbols.append(SymbolInfo(
                    name=name,
                    kind="function",
                    file_path=file_path,
                    start_line=idx,
                    end_line=idx,
                    arguments=args,
                    language=lang,
                ))
                continue

            # Arrow function
            m_arrow = arrow_re.match(line)
            if m_arrow:
                name, args_str = m_arrow.groups()
                args = [a.strip().split(":")[0].split("=")[0].strip() for a in args_str.split(",") if a.strip()]
                symbols.append(SymbolInfo(
                    name=name,
                    kind="function",
                    file_path=file_path,
                    start_line=idx,
                    end_line=idx,
                    arguments=args,
                    language=lang,
                ))

        return symbols, imports

    def _parse_bash(self, file_path: str, source: str) -> Tuple[List[SymbolInfo], List[ImportInfo]]:
        """Extracts bash functions from shell scripts."""
        symbols: List[SymbolInfo] = []
        func_re = re.compile(r"^\s*(?:function\s+)?([A-Za-z0-9_-]+)\s*\(\s*\)\s*\{")

        for idx, line in enumerate(source.splitlines(), start=1):
            m = func_re.match(line)
            if m:
                func_name = m.group(1)
                symbols.append(SymbolInfo(
                    name=func_name,
                    kind="function",
                    file_path=file_path,
                    start_line=idx,
                    end_line=idx,
                    language="bash",
                ))

        return symbols, []

    def _parse_markdown(self, file_path: str, source: str) -> Tuple[List[SymbolInfo], List[ImportInfo]]:
        """Extracts markdown headings as navigable structure symbols."""
        symbols: List[SymbolInfo] = []
        heading_re = re.compile(r"^(#{1,6})\s+(.*)$")

        for idx, line in enumerate(source.splitlines(), start=1):
            m = heading_re.match(line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                symbols.append(SymbolInfo(
                    name=title,
                    kind="section",
                    file_path=file_path,
                    start_line=idx,
                    end_line=idx,
                    language="markdown",
                    docstring=f"Markdown H{level} Heading",
                ))

        return symbols, []

    def _parse_config_symbols(self, file_path: str, source: str, lang: str) -> Tuple[List[SymbolInfo], List[ImportInfo]]:
        """Extracts top-level keys from configuration files."""
        symbols: List[SymbolInfo] = []

        if lang == "json":
            try:
                data = json.loads(source)
                if isinstance(data, dict):
                    for k in data.keys():
                        symbols.append(SymbolInfo(
                            name=str(k),
                            kind="config",
                            file_path=file_path,
                            start_line=1,
                            end_line=1,
                            language="json",
                        ))
            except Exception:
                pass
        else:
            # YAML / TOML key regex
            key_re = re.compile(r"^([A-Za-z0-9_-]+)\s*:")
            for idx, line in enumerate(source.splitlines(), start=1):
                m = key_re.match(line)
                if m:
                    key = m.group(1)
                    symbols.append(SymbolInfo(
                        name=key,
                        kind="config",
                        file_path=file_path,
                        start_line=idx,
                        end_line=idx,
                        language=lang,
                    ))

        return symbols, []

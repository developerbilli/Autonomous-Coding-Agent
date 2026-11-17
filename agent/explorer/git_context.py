"""Git-based change context and history analyzer.

Extracts working tree status, staged/unstaged diffs, recent commit logs,
line-level blame annotations, and changed AST symbol mapping.
Gracefully falls back to filesystem mtime tracking when not in a git repository.
"""

import subprocess
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from agent.core.state import SymbolInfo


class GitContext:
    """Extracts git change context, diffs, blame, and changed symbols."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.is_git = self._check_is_git()

    def _check_is_git(self) -> bool:
        """Determines whether repo_path is inside a git working tree."""
        if not (self.repo_path / ".git").exists():
            # Check if parent is git worktree
            try:
                res = subprocess.run(
                    ["git", "rev-parse", "--is-inside-work-tree"],
                    cwd=str(self.repo_path),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                    timeout=5,
                )
                return res.returncode == 0 and res.stdout.strip() == "true"
            except Exception:
                return False
        return True

    def _run_git(self, args: List[str]) -> Tuple[int, str, str]:
        """Executes a git command safely within repo_path."""
        if not self.is_git:
            return 1, "", "Not a git repository"
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=str(self.repo_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=10,
            )
            return res.returncode, res.stdout, res.stderr
        except Exception as e:
            return 1, "", str(e)

    def get_status(self) -> Dict[str, Any]:
        """Returns structured working tree status: modified, staged, untracked, deleted."""
        if not self.is_git:
            return self._fallback_filesystem_status()

        code, out, _ = self._run_git(["status", "--porcelain", "-b"])
        if code != 0:
            return self._fallback_filesystem_status()

        lines = out.splitlines()
        branch = "unknown"
        untracked = []
        modified = []
        staged = []
        deleted = []

        for line in lines:
            if line.startswith("##"):
                branch = line[3:].strip().split("...")[0]
                continue
            if len(line) < 3:
                continue
            
            x, y = line[0], line[1]
            filepath = line[3:].strip()
            
            if x == "?" and y == "?":
                untracked.append(filepath)
            elif x in ("M", "A", "D", "R"):
                staged.append(filepath)
                if y == "M":
                    modified.append(filepath)
            elif y == "M":
                modified.append(filepath)
            elif y == "D" or x == "D":
                deleted.append(filepath)

        return {
            "is_git": True,
            "branch": branch,
            "modified": sorted(list(set(modified))),
            "staged": sorted(list(set(staged))),
            "untracked": sorted(list(set(untracked))),
            "deleted": sorted(list(set(deleted))),
            "has_changes": bool(modified or staged or untracked or deleted),
        }

    def get_diff(self, cached: bool = False, file_path: Optional[str] = None) -> str:
        """Returns the current git diff (unstaged by default, or staged if cached=True)."""
        if not self.is_git:
            return ""

        args = ["diff"]
        if cached:
            args.append("--cached")
        if file_path:
            args.extend(["--", file_path])

        code, out, _ = self._run_git(args)
        return out if code == 0 else ""

    def get_recent_commits(self, limit: int = 5, file_path: Optional[str] = None) -> List[Dict[str, str]]:
        """Returns recent commits with hash, author, date, and commit message."""
        if not self.is_git:
            return []

        args = ["log", f"-n{limit}", '--pretty=format:%H|%an|%ad|%s', "--date=short"]
        if file_path:
            args.extend(["--", file_path])

        code, out, _ = self._run_git(args)
        if code != 0 or not out.strip():
            return []

        commits = []
        for line in out.strip().splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "commit_hash": parts[0][:8],
                    "full_hash": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3],
                })
        return commits

    def get_blame(self, file_path: str, start_line: int, end_line: int) -> List[Dict[str, Any]]:
        """Returns line-level git blame information for the given line range."""
        if not self.is_git:
            return []

        args = ["blame", f"-L{start_line},{end_line}", "--line-porcelain", "--", file_path]
        code, out, _ = self._run_git(args)
        if code != 0 or not out.strip():
            return []

        hunks = []
        current_commit = {}
        for line in out.splitlines():
            if re.match(r"^[0-9a-f]{40}\s", line):
                parts = line.split()
                current_commit = {"commit_hash": parts[0][:8], "orig_line": parts[1], "final_line": parts[2]}
            elif line.startswith("author "):
                current_commit["author"] = line[7:].strip()
            elif line.startswith("author-time "):
                current_commit["time"] = line[12:].strip()
            elif line.startswith("summary "):
                current_commit["summary"] = line[8:].strip()
            elif line.startswith("\t"):
                current_commit["line_content"] = line[1:]
                hunks.append(dict(current_commit))
                current_commit = {}

        return hunks

    def get_changed_line_ranges(self) -> Dict[str, List[Tuple[int, int]]]:
        """Parses the working tree diff and returns modified line ranges per file."""
        diff_text = self.get_diff() + "\n" + self.get_diff(cached=True)
        if not diff_text.strip():
            return {}

        file_changed_lines: Dict[str, Set[int]] = {}
        current_file: Optional[str] = None
        current_new_line: int = 0
        in_hunk: bool = False
        
        file_header_re = re.compile(r"^diff --git a/(.*?) b/(.*?)$")
        hunk_header_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

        for line in diff_text.splitlines():
            m_file = file_header_re.match(line)
            if m_file:
                current_file = m_file.group(2)
                if current_file not in file_changed_lines:
                    file_changed_lines[current_file] = set()
                in_hunk = False
                continue

            if current_file:
                m_hunk = hunk_header_re.match(line)
                if m_hunk:
                    current_new_line = int(m_hunk.group(1))
                    in_hunk = True
                    continue

                if in_hunk:
                    if line.startswith("+") and not line.startswith("+++"):
                        file_changed_lines[current_file].add(current_new_line)
                        current_new_line += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        # Deleted line in old version, record affected location
                        file_changed_lines[current_file].add(max(1, current_new_line))
                    elif line.startswith(" "):
                        current_new_line += 1

        # Convert set of lines into contiguous (start, end) ranges
        file_ranges: Dict[str, List[Tuple[int, int]]] = {}
        for f_path, lines_set in file_changed_lines.items():
            if not lines_set:
                continue
            sorted_lines = sorted(list(lines_set))
            ranges = []
            range_start = sorted_lines[0]
            prev = sorted_lines[0]
            for l in sorted_lines[1:]:
                if l == prev + 1:
                    prev = l
                else:
                    ranges.append((range_start, prev))
                    range_start = l
                    prev = l
            ranges.append((range_start, prev))
            file_ranges[f_path] = ranges

        return file_ranges

    def get_changed_symbols(self, symbols: Dict[str, SymbolInfo]) -> List[SymbolInfo]:
        """Maps changed diff line ranges to AST symbols that intersect with the changes."""
        changed_ranges = self.get_changed_line_ranges()
        if not changed_ranges:
            return []

        changed_symbols = []
        for name, sym in symbols.items():
            ranges = changed_ranges.get(sym.file_path, [])
            for start, end in ranges:
                # Check if change overlaps with symbol definition range
                if not (end < sym.start_line or start > sym.end_line):
                    changed_symbols.append(sym)
                    break

        return changed_symbols

    def get_context_summary(self, symbols: Optional[Dict[str, SymbolInfo]] = None) -> Dict[str, Any]:
        """Provides a comprehensive, structured git context summary for agent reasoning."""
        status = self.get_status()
        recent_commits = self.get_recent_commits(limit=5)
        diff_snippet = self.get_diff()[:2000] if self.is_git else ""
        changed_syms = self.get_changed_symbols(symbols) if symbols else []

        return {
            "is_git": self.is_git,
            "branch": status.get("branch", "unknown"),
            "modified_files": status.get("modified", []),
            "staged_files": status.get("staged", []),
            "untracked_files": status.get("untracked", []),
            "has_uncommitted_changes": status.get("has_changes", False),
            "recent_commits": recent_commits,
            "diff_preview": diff_snippet,
            "changed_symbol_names": [s.name for s in changed_syms],
        }

    def _fallback_filesystem_status(self) -> Dict[str, Any]:
        """Fallback for non-git directories: scans files sorted by modification time."""
        files_by_mtime = []
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if not d.startswith((".", "__pycache__", "venv"))]
            for f in files:
                full_path = Path(root) / f
                rel_path = str(full_path.relative_to(self.repo_path))
                try:
                    mtime = full_path.stat().st_mtime
                    files_by_mtime.append((rel_path, mtime))
                except OSError:
                    continue

        files_by_mtime.sort(key=lambda x: x[1], reverse=True)
        recent_files = [f[0] for f in files_by_mtime[:10]]

        return {
            "is_git": False,
            "branch": "none",
            "modified": recent_files,
            "staged": [],
            "untracked": [],
            "deleted": [],
            "has_changes": False,
        }

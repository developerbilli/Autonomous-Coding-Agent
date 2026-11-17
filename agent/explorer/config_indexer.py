"""Configuration, build, and environment file indexer.

Discovers and parses configuration files across formats:
pyproject.toml, requirements.txt, setup.cfg, pytest.ini, package.json,
Dockerfile, docker-compose.yml, CI workflows, and environment templates.
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any


class ConfigIndexer:
    """Discovers, parses, and retrieves configuration and metadata files."""

    CONFIG_PATTERNS = {
        "python": [
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "requirements-dev.txt",
            "requirements_dev.txt",
            "pytest.ini",
            "tox.ini",
            ".flake8",
            "ruff.toml",
        ],
        "javascript": [
            "package.json",
            "tsconfig.json",
            "vite.config.js",
            "vite.config.ts",
            "webpack.config.js",
        ],
        "container_ci": [
            "Dockerfile",
            "Containerfile",
            "Makefile",
            "Procfile",
            "Gemfile",
            "docker-compose.yml",
            "docker-compose.yaml",
        ],
        "environment": [
            ".env.example",
            ".env.template",
            ".env.sample",
        ],
    }

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.configs: Dict[str, str] = {}
        self.metadata: Dict[str, Any] = {
            "dependencies": {},
            "test_config": {},
            "python_requires": None,
            "project_name": None,
        }

    def index_configs(self) -> Dict[str, str]:
        """Walks the repository and discovers all configuration and metadata files."""
        self.configs.clear()
        
        flat_patterns = set()
        for cat_list in self.CONFIG_PATTERNS.values():
            flat_patterns.update(cat_list)

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if not d.startswith((".", "__pycache__", "venv", "node_modules"))]
            
            for file in files:
                # Direct match or workflow match
                rel_dir = os.path.relpath(root, self.repo_path)
                full_path = Path(root) / file
                rel_path = str(full_path.relative_to(self.repo_path))

                is_config = (
                    file in flat_patterns
                    or file.endswith(".ini")
                    or file.endswith(".toml")
                    or (rel_dir.startswith(".github/workflows") and file.endswith((".yml", ".yaml")))
                )

                if is_config:
                    try:
                        content = full_path.read_text(encoding="utf-8", errors="ignore")
                        # Cap content snippet at 4KB to avoid context bloat
                        self.configs[rel_path] = content[:4096]
                        self._parse_config_metadata(rel_path, content)
                    except Exception:
                        continue

        return self.configs

    def _parse_config_metadata(self, file_path: str, content: str):
        """Extracts structured dependencies, test options, and environment rules."""
        file_name = Path(file_path).name

        # 1. requirements.txt
        if file_name.startswith("requirements") and file_name.endswith(".txt"):
            deps = []
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "-")):
                    deps.append(line.split(";")[0].strip())
            self.metadata["dependencies"][file_path] = deps

        # 2. package.json
        elif file_name == "package.json":
            try:
                data = json.loads(content)
                self.metadata["project_name"] = data.get("name")
                pkg_deps = list(data.get("dependencies", {}).keys()) + list(data.get("devDependencies", {}).keys())
                self.metadata["dependencies"]["package.json"] = pkg_deps
            except Exception:
                pass

        # 3. pytest.ini
        elif file_name == "pytest.ini":
            test_dirs = []
            for line in content.splitlines():
                if line.strip().startswith("testpaths"):
                    parts = line.split("=", 1)
                    if len(parts) > 1:
                        test_dirs = [p.strip() for p in parts[1].split()]
            self.metadata["test_config"]["pytest_testpaths"] = test_dirs

        # 4. pyproject.toml
        elif file_name == "pyproject.toml":
            # Simple regex search without requiring external toml library
            m_name = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
            if m_name:
                self.metadata["project_name"] = m_name.group(1)
            
            m_py = re.search(r'requires-python\s*=\s*["\']([^"\']+)["\']', content)
            if m_py:
                self.metadata["python_requires"] = m_py.group(1)

    def find_configs_for_task(self, task: str) -> Dict[str, str]:
        """Returns relevant configurations matching keywords in the task description."""
        if not self.configs:
            self.index_configs()

        task_lower = task.lower()
        matched: Dict[str, str] = {}

        # Keywords mapped to config types
        triggers = {
            "test": ["pytest.ini", "tox.ini"],
            "pytest": ["pytest.ini"],
            "depend": ["requirements.txt", "pyproject.toml", "package.json"],
            "package": ["pyproject.toml", "setup.py", "package.json"],
            "docker": ["Dockerfile", "docker-compose.yml"],
            "container": ["Dockerfile", "docker-compose.yml"],
            "env": [".env.example", ".env.template"],
            "workflow": [".github/workflows"],
            "ci": [".github/workflows"],
        }

        for kw, target_configs in triggers.items():
            if kw in task_lower:
                for cfg_path, content in self.configs.items():
                    for target in target_configs:
                        if target in cfg_path:
                            matched[cfg_path] = content

        # If no specific keyword triggered, return common root configs (e.g. pytest.ini, requirements.txt)
        if not matched:
            for common in ("pytest.ini", "requirements.txt", "pyproject.toml", "package.json"):
                if common in self.configs:
                    matched[common] = self.configs[common]

        return matched

    def to_dict(self) -> Dict[str, Any]:
        """Serializes configuration summary for state inspection."""
        return {
            "config_files": list(self.configs.keys()),
            "metadata": self.metadata,
        }

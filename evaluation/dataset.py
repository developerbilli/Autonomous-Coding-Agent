"""Benchmark Task Dataset Schema and Catalog Loader.

Defines the BenchmarkTask dataclass and aggregations across the 5 categories:
1. Basic Implementation (10 tasks)
2. Bug Fixing (10 tasks)
3. Edge Cases (10 tasks)
4. Multi-File Changes (10 tasks)
5. Difficult Tasks (10 tasks)
Total: Exactly 50 real-world benchmark engineering tasks.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class BenchmarkCategory(str, Enum):
    BASIC_IMPLEMENTATION = "basic_implementation"
    BUG_FIXING = "bug_fixing"
    EDGE_CASES = "edge_cases"
    MULTI_FILE = "multi_file"
    DIFFICULT_TASKS = "difficult_tasks"


@dataclass
class BenchmarkTask:
    task_id: str
    category: BenchmarkCategory
    title: str
    description: str
    initial_files: Dict[str, str]
    baseline_tests: Dict[str, str]
    hidden_tests: Dict[str, str]
    expected_behavior: str
    acceptance_criteria: List[str]
    timeout_seconds: int = 60
    metadata: Dict[str, str] = field(default_factory=dict)


def _load_all_tasks() -> List[BenchmarkTask]:
    """Lazy-loads and aggregates all 50 tasks across the 5 catalog modules."""
    from evaluation.tasks.basic_implementation import get_basic_implementation_tasks
    from evaluation.tasks.bug_fixing import get_bug_fixing_tasks
    from evaluation.tasks.edge_cases import get_edge_cases_tasks
    from evaluation.tasks.multi_file import get_multi_file_tasks
    from evaluation.tasks.difficult_tasks import get_difficult_tasks

    tasks: List[BenchmarkTask] = []
    tasks.extend(get_basic_implementation_tasks())
    tasks.extend(get_bug_fixing_tasks())
    tasks.extend(get_edge_cases_tasks())
    tasks.extend(get_multi_file_tasks())
    tasks.extend(get_difficult_tasks())
    return tasks


_TASK_CACHE: Optional[List[BenchmarkTask]] = None


def get_all_tasks() -> List[BenchmarkTask]:
    """Returns all 50 benchmark tasks in the evaluation dataset."""
    global _TASK_CACHE
    if _TASK_CACHE is None:
        _TASK_CACHE = _load_all_tasks()
    return list(_TASK_CACHE)


def get_tasks_by_category(category: BenchmarkCategory) -> List[BenchmarkTask]:
    """Filters benchmark tasks by category."""
    all_tasks = get_all_tasks()
    return [t for t in all_tasks if t.category == category]


def get_task_by_id(task_id: str) -> Optional[BenchmarkTask]:
    """Looks up a specific task by task_id."""
    for t in get_all_tasks():
        if t.task_id == task_id:
            return t
    return None

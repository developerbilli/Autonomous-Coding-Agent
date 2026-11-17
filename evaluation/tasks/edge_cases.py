"""Category 3: Edge Cases Benchmark Tasks (10 Tasks).

Tests the agent's defensive engineering and boundary awareness:
Can it handle unusual inputs, Unicode, leap days, cyclic graphs, path traversals, and numeric precision?
"""

from typing import List
from evaluation.dataset import BenchmarkTask, BenchmarkCategory


def get_edge_cases_tasks() -> List[BenchmarkTask]:
    tasks: List[BenchmarkTask] = []

    # 21. Empty Collections and Nulls
    tasks.append(
        BenchmarkTask(
            task_id="edge_21_empty_collections_and_nulls",
            category=BenchmarkCategory.EDGE_CASES,
            title="Statistical Summary with Nulls and Empty Inputs",
            description=(
                "Implement `calculate_summary_stats(numbers: List[Optional[float]]) -> dict` in `stats/aggregator.py`. "
                "Filters out `None` values. If the filtered list is empty, returns "
                "`{'count': 0, 'mean': 0.0, 'variance': 0.0, 'min': None, 'max': None}`. "
                "For a single value, variance must be `0.0`. Never raise `ZeroDivisionError`."
            ),
            initial_files={
                "stats/aggregator.py": (
                    "from typing import List, Optional, Dict, Any\n\n"
                    "def calculate_summary_stats(numbers: List[Optional[float]]) -> Dict[str, Any]:\n"
                    "    # TODO: Implement robust statistics handling nulls and empty sets\n"
                    "    pass\n"
                )
            },
            baseline_tests={
                "tests/test_aggregator.py": (
                    "from stats.aggregator import calculate_summary_stats\n\n"
                    "def test_normal_stats():\n"
                    "    res = calculate_summary_stats([10.0, 20.0, 30.0])\n"
                    "    assert res['count'] == 3\n"
                    "    assert res['mean'] == 20.0\n"
                    "    assert res['min'] == 10.0\n"
                    "    assert res['max'] == 30.0\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_aggregator.py": (
                    "from stats.aggregator import calculate_summary_stats\n\n"
                    "def test_all_none_and_empty():\n"
                    "    assert calculate_summary_stats([]) == {'count': 0, 'mean': 0.0, 'variance': 0.0, 'min': None, 'max': None}\n"
                    "    assert calculate_summary_stats([None, None]) == {'count': 0, 'mean': 0.0, 'variance': 0.0, 'min': None, 'max': None}\n\n"
                    "def test_single_value_variance():\n"
                    "    res = calculate_summary_stats([None, 42.0])\n"
                    "    assert res['count'] == 1\n"
                    "    assert res['mean'] == 42.0\n"
                    "    assert res['variance'] == 0.0\n"
                )
            },
            expected_behavior="Filters out None values safely, handles 0-count and 1-count boundaries without division by zero.",
            acceptance_criteria=[
                "Calculates mean, variance, min, max",
                "Handles empty input and all-None inputs without exceptions",
                "Single item yields variance 0.0",
            ],
        )
    )

    # 22. Unicode Normalization & Emojis
    tasks.append(
        BenchmarkTask(
            task_id="edge_22_unicode_slugifier",
            category=BenchmarkCategory.EDGE_CASES,
            title="Unicode Normalization and Emoji-Safe Slugifier",
            description=(
                "Implement `slugify(text: str) -> str` in `text/slugifier.py`. "
                "Converts text into an ASCII-only URL-safe slug: "
                "normalizes NFKD unicode characters (e.g. `é` -> `e`, `ü` -> `u`, `ñ` -> `n`), "
                "strips emojis and unencodable characters, converts to lowercase, "
                "replaces whitespace and punctuation with single hyphens, "
                "and strips leading/trailing hyphens. If result is empty, return `'untitled'`."
            ),
            initial_files={
                "text/slugifier.py": (
                    "def slugify(text: str) -> str:\n"
                    "    # TODO: Implement Unicode NFKD slugification\n"
                    "    pass\n"
                )
            },
            baseline_tests={
                "tests/test_slug.py": (
                    "from text.slugifier import slugify\n\n"
                    "def test_simple_slug():\n"
                    "    assert slugify('Hello World!') == 'hello-world'\n"
                    "    assert slugify('Café au Lait') == 'cafe-au-lait'\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_slug.py": (
                    "from text.slugifier import slugify\n\n"
                    "def test_emojis_and_special_chars():\n"
                    "    assert slugify('🚀 Launch in 3.. 2.. 1!') == 'launch-in-3-2-1'\n"
                    "    assert slugify('   --Multiple   Spaces--  ') == 'multiple-spaces'\n\n"
                    "def test_empty_or_pure_emoji():\n"
                    "    assert slugify('🔥🎉') == 'untitled'\n"
                    "    assert slugify('   ') == 'untitled'\n"
                )
            },
            expected_behavior="Normalizes Unicode decomposition, strips non-ASCII, collapses hyphens, and defaults gracefully on empty output.",
            acceptance_criteria=[
                "Transliterates accents to ASCII equivalents",
                "Removes emojis and symbols cleanly",
                "Collapses consecutive hyphens and trims edges",
                "Returns 'untitled' for empty results",
            ],
        )
    )

    # 23. Currency Rounding and Split Conservation
    tasks.append(
        BenchmarkTask(
            task_id="edge_23_currency_split_precision",
            category=BenchmarkCategory.EDGE_CASES,
            title="Exact Penny-Conserving Currency Split",
            description=(
                "Implement `split_bill(amount_cents: int, num_splits: int) -> List[int]` in `billing/currency.py`. "
                "Splits an exact integer cent amount into `num_splits` portions such that the sum of portions "
                "EXACTLY equals `amount_cents`. The remainder cents must be distributed 1-by-1 starting from the first split. "
                "Raise `ValueError` if `amount_cents < 0` or `num_splits <= 0`."
            ),
            initial_files={
                "billing/currency.py": (
                    "from typing import List\n\n"
                    "def split_bill(amount_cents: int, num_splits: int) -> List[int]:\n"
                    "    # TODO: Implement penny-conserving bill splitting\n"
                    "    pass\n"
                )
            },
            baseline_tests={
                "tests/test_currency.py": (
                    "from billing.currency import split_bill\n\n"
                    "def test_even_split():\n"
                    "    assert split_bill(1000, 2) == [500, 500]\n\n"
                    "def test_odd_split():\n"
                    "    # 1000 cents split 3 ways: 334, 333, 333\n"
                    "    res = split_bill(1000, 3)\n"
                    "    assert res == [334, 333, 333]\n"
                    "    assert sum(res) == 1000\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_currency.py": (
                    "import pytest\n"
                    "from billing.currency import split_bill\n\n"
                    "def test_zero_amount():\n"
                    "    assert split_bill(0, 4) == [0, 0, 0, 0]\n\n"
                    "def test_cents_smaller_than_splits():\n"
                    "    # 2 cents split 5 ways: [1, 1, 0, 0, 0]\n"
                    "    assert split_bill(2, 5) == [1, 1, 0, 0, 0]\n\n"
                    "def test_invalid_arguments():\n"
                    "    with pytest.raises(ValueError):\n"
                    "        split_bill(-100, 2)\n"
                    "    with pytest.raises(ValueError):\n"
                    "        split_bill(100, 0)\n"
                )
            },
            expected_behavior="Computes quotient and remainder with divmod, distributing remainder cents evenly without loss.",
            acceptance_criteria=[
                "Sum of splits exactly equals initial amount",
                "Distributes remainder cents starting from index 0",
                "Rejects non-positive split counts",
            ],
        )
    )

    # 24. Leap Year and Month End Rollover
    tasks.append(
        BenchmarkTask(
            task_id="edge_24_month_end_date_rollover",
            category=BenchmarkCategory.EDGE_CASES,
            title="Leap Year and End-of-Month Date Rollover",
            description=(
                "Implement `add_months(d: date, months: int) -> date` in `scheduler/dates.py`. "
                "Adds `months` to `d`. If the resulting day of month does not exist in the target month "
                "(e.g. Jan 31 + 1 month -> Feb 28, or Feb 29 on leap years like 2024), "
                "it must clamp to the last valid day of that month. Supports both positive and negative month offsets."
            ),
            initial_files={
                "scheduler/dates.py": (
                    "from datetime import date\n\n"
                    "def add_months(d: date, months: int) -> date:\n"
                    "    # TODO: Implement month addition with day clamping\n"
                    "    pass\n"
                )
            },
            baseline_tests={
                "tests/test_dates.py": (
                    "from datetime import date\n"
                    "from scheduler.dates import add_months\n\n"
                    "def test_simple_addition():\n"
                    "    assert add_months(date(2023, 1, 15), 1) == date(2023, 2, 15)\n"
                    "    assert add_months(date(2023, 11, 10), 3) == date(2024, 2, 10)\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_dates.py": (
                    "from datetime import date\n"
                    "from scheduler.dates import add_months\n\n"
                    "def test_leap_year_feb_clamping():\n"
                    "    # 2024 is leap year -> Feb 29\n"
                    "    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)\n"
                    "    # 2023 is non-leap year -> Feb 28\n"
                    "    assert add_months(date(2023, 1, 31), 1) == date(2023, 2, 28)\n\n"
                    "def test_negative_months_rollover():\n"
                    "    assert add_months(date(2023, 3, 31), -1) == date(2023, 2, 28)\n"
                )
            },
            expected_behavior="Computes target year/month arithmetic, calculates calendar month range, and clamps day to month max.",
            acceptance_criteria=[
                "Handles year boundaries correctly",
                "Clamps to Feb 29 on leap years and Feb 28 on regular years",
                "Supports negative month offsets",
            ],
        )
    )

    # 25. Cyclic Reference Graph Serializer
    tasks.append(
        BenchmarkTask(
            task_id="edge_25_circular_reference_serializer",
            category=BenchmarkCategory.EDGE_CASES,
            title="Cyclic Reference Graph Serializer",
            description=(
                "Implement `serialize_graph(node: dict) -> dict` in `serializers/graph.py`. "
                "Performs a deep copy/serialization of nested dictionaries and lists. "
                "If an identical dictionary reference has already been encountered in the traversal path, "
                "replace it with `{'__circular_ref__': id(node)}` to prevent `RecursionError`."
            ),
            initial_files={
                "serializers/graph.py": (
                    "from typing import Any, Dict\n\n"
                    "def serialize_graph(node: Any) -> Any:\n"
                    "    # TODO: Serialize structure while detecting cycles\n"
                    "    pass\n"
                )
            },
            baseline_tests={
                "tests/test_graph.py": (
                    "from serializers.graph import serialize_graph\n\n"
                    "def test_acyclic_graph():\n"
                    "    data = {'a': 1, 'b': [2, 3], 'c': {'d': 4}}\n"
                    "    assert serialize_graph(data) == data\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_graph.py": (
                    "from serializers.graph import serialize_graph\n\n"
                    "def test_cyclic_graph_does_not_infinite_recurse():\n"
                    "    parent = {'id': 1}\n"
                    "    child = {'id': 2, 'parent': parent}\n"
                    "    parent['child'] = child\n"
                    "    res = serialize_graph(parent)\n"
                    "    assert res['id'] == 1\n"
                    "    assert res['child']['id'] == 2\n"
                    "    assert '__circular_ref__' in res['child']['parent']\n"
                )
            },
            expected_behavior="Tracks visited object IDs in recursion stack and outputs surrogate circular ref token on cycle detection.",
            acceptance_criteria=[
                "Serializes deep acyclic trees accurately",
                "Detects self-references and mutual references without RecursionError",
            ],
        )
    )

    # 26. Sparse Matrix Multiplication & Dimensions
    tasks.append(
        BenchmarkTask(
            task_id="edge_26_sparse_matrix_multiplication",
            category=BenchmarkCategory.EDGE_CASES,
            title="Matrix Multiplication with Dimension Validation",
            description=(
                "Implement `matrix_multiply(A: List[List[float]], B: List[List[float]]) -> List[List[float]]` "
                "in `math/matrix.py`. "
                "Computes matrix product $C = A \\times B$. "
                "Raise `ValueError('Incompatible dimensions')` if cols(A) != rows(B). "
                "Raise `ValueError('Empty matrix')` if either A or B has 0 rows or columns."
            ),
            initial_files={
                "math/matrix.py": (
                    "from typing import List\n\n"
                    "def matrix_multiply(A: List[List[float]], B: List[List[float]]) -> List[List[float]]:\n"
                    "    # TODO: Implement matrix multiplication with validation\n"
                    "    pass\n"
                )
            },
            baseline_tests={
                "tests/test_matrix.py": (
                    "from math.matrix import matrix_multiply\n\n"
                    "def test_square_multiplication():\n"
                    "    A = [[1, 2], [3, 4]]\n"
                    "    B = [[2, 0], [1, 2]]\n"
                    "    # [1*2 + 2*1, 1*0 + 2*2] -> [4, 4]\n"
                    "    # [3*2 + 4*1, 3*0 + 4*2] -> [10, 8]\n"
                    "    assert matrix_multiply(A, B) == [[4, 4], [10, 8]]\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_matrix.py": (
                    "import pytest\n"
                    "from math.matrix import matrix_multiply\n\n"
                    "def test_incompatible_dimensions():\n"
                    "    A = [[1, 2, 3]]  # 1x3\n"
                    "    B = [[1, 2], [3, 4]]  # 2x2\n"
                    "    with pytest.raises(ValueError, match='Incompatible dimensions'):\n"
                    "        matrix_multiply(A, B)\n\n"
                    "def test_empty_matrix_raises():\n"
                    "    with pytest.raises(ValueError, match='Empty matrix'):\n"
                    "        matrix_multiply([], [[1]])\n"
                )
            },
            expected_behavior="Validates dimension compatibility before computing dot products across rows and columns.",
            acceptance_criteria=[
                "Multiplies rectangular and square matrices",
                "Raises ValueError on dimension mismatch",
                "Raises ValueError on empty matrices",
            ],
        )
    )

    # 27. Path Traversal & URL Encoding Guard
    tasks.append(
        BenchmarkTask(
            task_id="edge_27_path_traversal_guard",
            category=BenchmarkCategory.EDGE_CASES,
            title="Safe Path Resolver & Directory Traversal Shield",
            description=(
                "Implement `safe_resolve_path(base_dir: str, requested_path: str) -> str` in `security/path_guard.py`. "
                "Resolves `requested_path` relative to `base_dir`. "
                "Decodes URL encodings (including single `%2e%2e` and double `%252e%252e` traversal tricks). "
                "If the resolved path falls outside `base_dir`, or contains null bytes (`\\0`), "
                "raise `PermissionError('Path traversal detected')`. Return absolute resolved path."
            ),
            initial_files={
                "security/path_guard.py": (
                    "from typing import Optional\n\n"
                    "def safe_resolve_path(base_dir: str, requested_path: str) -> str:\n"
                    "    # TODO: Implement path traversal guard with URL decoding\n"
                    "    pass\n"
                )
            },
            baseline_tests={
                "tests/test_path_guard.py": (
                    "import os, tempfile\n"
                    "from security.path_guard import safe_resolve_path\n\n"
                    "def test_safe_path():\n"
                    "    with tempfile.TemporaryDirectory() as tmp:\n"
                    "        p = safe_resolve_path(tmp, 'sub/file.txt')\n"
                    "        assert p.startswith(os.path.realpath(tmp))\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_path_guard.py": (
                    "import pytest, tempfile\n"
                    "from security.path_guard import safe_resolve_path\n\n"
                    "def test_traversal_attempts_blocked():\n"
                    "    with tempfile.TemporaryDirectory() as tmp:\n"
                    "        with pytest.raises(PermissionError):\n"
                    "            safe_resolve_path(tmp, '../../etc/passwd')\n"
                    "        with pytest.raises(PermissionError):\n"
                    "            safe_resolve_path(tmp, '%2e%2e/%2e%2e/secret')\n"
                    "        with pytest.raises(PermissionError):\n"
                    "            safe_resolve_path(tmp, '%252e%252e/double_encoded')\n"
                )
            },
            expected_behavior="Recursively decodes URL components, checks canonical realpath, and raises PermissionError on path escape.",
            acceptance_criteria=[
                "Resolves valid subpaths inside base directory",
                "Blocks .. escapes and encoded traversals",
                "Raises PermissionError on unauthorized directory escape",
            ],
        )
    )

    # 28. Malformed Truncated Streaming JSON Parser
    tasks.append(
        BenchmarkTask(
            task_id="edge_28_partial_json_recovery",
            category=BenchmarkCategory.EDGE_CASES,
            title="Truncated Streaming JSON Object Recovery",
            description=(
                "Implement `extract_complete_json_objects(raw_stream: str) -> List[dict]` in `parsers/stream_json.py`. "
                "Given a raw string representing a streaming JSON array of objects that may have been abruptly severed/interrupted "
                "(e.g. `[{\"id\": 1}, {\"id\": 2}, {\"id\": 3, \"name\": \"unfin`), "
                "parse and return all complete JSON objects that were fully formed before truncation."
            ),
            initial_files={
                "parsers/stream_json.py": (
                    "from typing import List, Dict, Any\n\n"
                    "def extract_complete_json_objects(raw_stream: str) -> List[Dict[str, Any]]:\n"
                    "    # TODO: Parse valid complete objects from truncated stream\n"
                    "    pass\n"
                )
            },
            baseline_tests={
                "tests/test_stream_json.py": (
                    "from parsers.stream_json import extract_complete_json_objects\n\n"
                    "def test_complete_array():\n"
                    "    raw = '[{\"id\": 1}, {\"id\": 2}]'\n"
                    "    assert extract_complete_json_objects(raw) == [{'id': 1}, {'id': 2}]\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_stream_json.py": (
                    "from parsers.stream_json import extract_complete_json_objects\n\n"
                    "def test_truncated_stream():\n"
                    "    raw = '[{\"id\": 1}, {\"id\": 2}, {\"id\": 3, \"status\": \"pend'\n"
                    "    assert extract_complete_json_objects(raw) == [{'id': 1}, {'id': 2}]\n\n"
                    "def test_empty_or_broken_stream():\n"
                    "    assert extract_complete_json_objects('[') == []\n"
                    "    assert extract_complete_json_objects('') == []\n"
                )
            },
            expected_behavior="Scans brace boundaries or uses JSONDecoder.raw_decode iteratively to salvage intact objects.",
            acceptance_criteria=[
                "Parses intact arrays without error",
                "Recovers prior valid objects when stream is cut off mid-record",
                "Returns empty list for empty or completely corrupted streams",
            ],
        )
    )

    # 29. Ring Buffer Zero and One Capacity
    tasks.append(
        BenchmarkTask(
            task_id="edge_29_ring_buffer_boundaries",
            category=BenchmarkCategory.EDGE_CASES,
            title="Ring Buffer Capacity-0 and Capacity-1 Boundary Guards",
            description=(
                "Implement `RingBuffer(capacity: int)` in `collections/ring_buffer.py`. "
                "Methods: `append(item)`, `pop() -> item`, `is_empty() -> bool`, `is_full() -> bool`. "
                "When `capacity == 0`, buffer is always full and always empty; `append()` is a no-op, `pop()` raises `IndexError`. "
                "When `capacity == 1`, each `append()` overwrites the single item. "
                "Negative capacity raises `ValueError`."
            ),
            initial_files={
                "collections/ring_buffer.py": (
                    "from typing import Any, Optional\n\n"
                    "class RingBuffer:\n"
                    "    def __init__(self, capacity: int):\n"
                    "        # TODO: Implement ring buffer\n"
                    "        pass\n\n"
                    "    def append(self, item: Any) -> None:\n"
                    "        pass\n\n"
                    "    def pop(self) -> Any:\n"
                    "        pass\n\n"
                    "    def is_empty(self) -> bool:\n"
                    "        pass\n\n"
                    "    def is_full(self) -> bool:\n"
                    "        pass\n"
                )
            },
            baseline_tests={
                "tests/test_buffer.py": (
                    "from collections.ring_buffer import RingBuffer\n\n"
                    "def test_normal_capacity():\n"
                    "    b = RingBuffer(2)\n"
                    "    b.append(1)\n"
                    "    b.append(2)\n"
                    "    assert b.is_full() is True\n"
                    "    assert b.pop() == 1\n"
                    "    assert b.pop() == 2\n"
                    "    assert b.is_empty() is True\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_buffer.py": (
                    "import pytest\n"
                    "from collections.ring_buffer import RingBuffer\n\n"
                    "def test_capacity_zero():\n"
                    "    b = RingBuffer(0)\n"
                    "    b.append('lost')\n"
                    "    assert b.is_empty() is True\n"
                    "    with pytest.raises(IndexError):\n"
                    "        b.pop()\n\n"
                    "def test_capacity_one():\n"
                    "    b = RingBuffer(1)\n"
                    "    b.append('a')\n"
                    "    b.append('b')  # Overwrites 'a'\n"
                    "    assert b.pop() == 'b'\n"
                )
            },
            expected_behavior="Handles capacity 0 and 1 without modulo zero or index out of range errors.",
            acceptance_criteria=[
                "Capacity 0 drops writes and raises IndexError on pop",
                "Capacity 1 continuously overwrites oldest single value",
                "Negative capacity raises ValueError",
            ],
        )
    )

    # 30. Conflicting CLI Flags and Negative Numbers
    tasks.append(
        BenchmarkTask(
            task_id="edge_30_cli_flags_and_negative_args",
            category=BenchmarkCategory.EDGE_CASES,
            title="CLI Parser with Mutually Exclusive Flags and Negative Numbers",
            description=(
                "Implement `parse_args(argv: List[str]) -> dict` in `cli/parser.py`. "
                "Supports options `--output <file>`, `--limit <int>`, `--offset <int>` (supports negative integers like `--offset -10`), "
                "and flags `--verbose`, `--quiet`. "
                "If both `--verbose` and `--quiet` are supplied, raise `ValueError('Conflicting flags: verbose and quiet')`. "
                "Returns dictionary with normalized keys."
            ),
            initial_files={
                "cli/parser.py": (
                    "from typing import List, Dict, Any\n\n"
                    "def parse_args(argv: List[str]) -> Dict[str, Any]:\n"
                    "    # TODO: Implement robust CLI argument parser\n"
                    "    pass\n"
                )
            },
            baseline_tests={
                "tests/test_cli.py": (
                    "from cli.parser import parse_args\n\n"
                    "def test_basic_options():\n"
                    "    res = parse_args(['--output', 'report.pdf', '--limit', '25', '--verbose'])\n"
                    "    assert res['output'] == 'report.pdf'\n"
                    "    assert res['limit'] == 25\n"
                    "    assert res['verbose'] is True\n"
                    "    assert res.get('quiet') is False\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_cli.py": (
                    "import pytest\n"
                    "from cli.parser import parse_args\n\n"
                    "def test_negative_integer_arg():\n"
                    "    res = parse_args(['--offset', '-5'])\n"
                    "    assert res['offset'] == -5\n\n"
                    "def test_conflicting_flags():\n"
                    "    with pytest.raises(ValueError, match='Conflicting flags'):\n"
                    "        parse_args(['--verbose', '--quiet'])\n"
                )
            },
            expected_behavior="Differentiates negative integer values from option flags, checks mutual exclusion between conflicting flags.",
            acceptance_criteria=[
                "Parses options with string and integer types",
                "Correctly distinguishes negative values from option flags",
                "Enforces mutual exclusion between --verbose and --quiet",
            ],
        )
    )

    return tasks

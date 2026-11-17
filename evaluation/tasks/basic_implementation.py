"""Category 1: Basic Implementation Benchmark Tasks (10 Tasks).

Tests the agent's fundamental engineering capability:
Can it translate technical requirements into correct, clean, contract-abiding code?
"""

from typing import List
from evaluation.dataset import BenchmarkTask, BenchmarkCategory


def get_basic_implementation_tasks() -> List[BenchmarkTask]:
    tasks: List[BenchmarkTask] = []

    # 1. API Pagination
    tasks.append(
        BenchmarkTask(
            task_id="basic_01_api_pagination",
            category=BenchmarkCategory.BASIC_IMPLEMENTATION,
            title="Collection API Pagination",
            description=(
                "Implement `paginate(items, page=1, per_page=10)` in `api/paginator.py`. "
                "Must return a dictionary with keys: `items`, `page`, `per_page`, `total_items`, `total_pages`. "
                "Page numbers are 1-indexed. If `page` exceeds `total_pages`, return an empty `items` list. "
                "Raise `ValueError` if `page < 1` or `per_page < 1`."
            ),
            initial_files={
                "api/paginator.py": (
                    "from typing import List, Any, Dict\n\n"
                    "def paginate(items: List[Any], page: int = 1, per_page: int = 10) -> Dict[str, Any]:\n"
                    "    # TODO: Implement pagination logic\n"
                    "    pass\n"
                )
            },
            baseline_tests={
                "tests/test_paginator.py": (
                    "from api.paginator import paginate\n\n"
                    "def test_paginate_first_page():\n"
                    "    data = list(range(25))\n"
                    "    res = paginate(data, page=1, per_page=10)\n"
                    "    assert res['page'] == 1\n"
                    "    assert res['per_page'] == 10\n"
                    "    assert res['total_items'] == 25\n"
                    "    assert res['total_pages'] == 3\n"
                    "    assert res['items'] == list(range(10))\n\n"
                    "def test_paginate_second_page():\n"
                    "    data = list(range(25))\n"
                    "    res = paginate(data, page=2, per_page=10)\n"
                    "    assert res['items'] == list(range(10, 20))\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_paginator.py": (
                    "import pytest\n"
                    "from api.paginator import paginate\n\n"
                    "def test_paginate_empty_items():\n"
                    "    res = paginate([], page=1, per_page=10)\n"
                    "    assert res['items'] == []\n"
                    "    assert res['total_items'] == 0\n"
                    "    assert res['total_pages'] == 0\n\n"
                    "def test_paginate_page_out_of_bounds():\n"
                    "    res = paginate([1, 2, 3], page=99, per_page=10)\n"
                    "    assert res['items'] == []\n"
                    "    assert res['total_pages'] == 1\n\n"
                    "def test_paginate_invalid_arguments():\n"
                    "    with pytest.raises(ValueError):\n"
                    "        paginate([1, 2], page=0, per_page=10)\n"
                    "    with pytest.raises(ValueError):\n"
                    "        paginate([1, 2], page=1, per_page=0)\n"
                )
            },
            expected_behavior="Computes correct slice bounds, total pages with ceiling division, and validates positive pagination parameters.",
            acceptance_criteria=[
                "Returns dict with keys items, page, per_page, total_items, total_pages",
                "Handles empty collection with total_pages=0",
                "Raises ValueError on non-positive page or per_page",
            ],
        )
    )

    # 2. LRU Cache
    tasks.append(
        BenchmarkTask(
            task_id="basic_02_lru_cache",
            category=BenchmarkCategory.BASIC_IMPLEMENTATION,
            title="LRU Cache with O(1) Operations",
            description=(
                "Implement `LRUCache` in `cache/lru.py`. Must support `get(key)` and `put(key, value)`. "
                "`get` returns value or `-1` if key is not found. "
                "When cache reaches `capacity`, the least recently used key must be evicted. "
                "`capacity <= 0` must raise `ValueError`."
            ),
            initial_files={
                "cache/lru.py": (
                    "class LRUCache:\n"
                    "    def __init__(self, capacity: int):\n"
                    "        # TODO: Implement LRUCache\n"
                    "        pass\n\n"
                    "    def get(self, key: int) -> int:\n"
                    "        pass\n\n"
                    "    def put(self, key: int, value: int) -> None:\n"
                    "        pass\n"
                )
            },
            baseline_tests={
                "tests/test_lru.py": (
                    "from cache.lru import LRUCache\n\n"
                    "def test_lru_basic_eviction():\n"
                    "    c = LRUCache(2)\n"
                    "    c.put(1, 10)\n"
                    "    c.put(2, 20)\n"
                    "    assert c.get(1) == 10\n"
                    "    c.put(3, 30)  # Evicts key 2\n"
                    "    assert c.get(2) == -1\n"
                    "    assert c.get(3) == 30\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_lru.py": (
                    "import pytest\n"
                    "from cache.lru import LRUCache\n\n"
                    "def test_lru_update_existing_key():\n"
                    "    c = LRUCache(2)\n"
                    "    c.put(1, 10)\n"
                    "    c.put(2, 20)\n"
                    "    c.put(1, 15)  # Update key 1\n"
                    "    c.put(3, 30)  # Should evict key 2, not key 1\n"
                    "    assert c.get(1) == 15\n"
                    "    assert c.get(2) == -1\n"
                    "    assert c.get(3) == 30\n\n"
                    "def test_lru_invalid_capacity():\n"
                    "    with pytest.raises(ValueError):\n"
                    "        LRUCache(0)\n"
                    "    with pytest.raises(ValueError):\n"
                    "        LRUCache(-5)\n"
                )
            },
            expected_behavior="Maintains recency order on both get and put, updates existing keys without eviction, raises ValueError on invalid capacity.",
            acceptance_criteria=[
                "get returns -1 for missing keys",
                "Evicts least-recently-used item on overflow",
                "Updating existing key updates value and marks it most recently used",
                "Raises ValueError for capacity <= 0",
            ],
        )
    )

    # 3. JWT Auth Validator
    tasks.append(
        BenchmarkTask(
            task_id="basic_03_jwt_auth_validator",
            category=BenchmarkCategory.BASIC_IMPLEMENTATION,
            title="JWT Token Validator & HMAC Verifier",
            description=(
                "Implement `validate_jwt(token: str, secret: str, current_time: int) -> dict` in `auth/jwt_validator.py`. "
                "Tokens use header `{'alg': 'HS256', 'typ': 'JWT'}` with HMAC-SHA256 signature and base64url encoding. "
                "Verify signature, check `exp` claim against `current_time` (raise `ValueError('Token expired')` if expired), "
                "and check `nbf` claim (raise `ValueError('Token not active yet')` if current_time < nbf). "
                "Raise `ValueError('Invalid signature')` if signature fails."
            ),
            initial_files={
                "auth/jwt_validator.py": (
                    "from typing import Dict, Any\n\n"
                    "def validate_jwt(token: str, secret: str, current_time: int) -> Dict[str, Any]:\n"
                    "    # TODO: Implement JWT validation\n"
                    "    pass\n"
                )
            },
            baseline_tests={
                "tests/test_jwt.py": (
                    "import hmac, hashlib, base64, json\n"
                    "from auth.jwt_validator import validate_jwt\n\n"
                    "def _b64(d):\n"
                    "    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip('=')\n\n"
                    "def test_valid_token():\n"
                    "    h = _b64({'alg': 'HS256', 'typ': 'JWT'})\n"
                    "    p = _b64({'sub': 'user123', 'exp': 2000, 'nbf': 1000})\n"
                    "    msg = f'{h}.{p}'.encode()\n"
                    "    sig = base64.urlsafe_b64encode(hmac.new(b'secret', msg, hashlib.sha256).digest()).decode().rstrip('=')\n"
                    "    token = f'{h}.{p}.{sig}'\n"
                    "    payload = validate_jwt(token, 'secret', current_time=1500)\n"
                    "    assert payload['sub'] == 'user123'\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_jwt.py": (
                    "import pytest, hmac, hashlib, base64, json\n"
                    "from auth.jwt_validator import validate_jwt\n\n"
                    "def _b64(d):\n"
                    "    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip('=')\n\n"
                    "def test_expired_token():\n"
                    "    h = _b64({'alg': 'HS256', 'typ': 'JWT'})\n"
                    "    p = _b64({'sub': 'user123', 'exp': 1000})\n"
                    "    msg = f'{h}.{p}'.encode()\n"
                    "    sig = base64.urlsafe_b64encode(hmac.new(b'key', msg, hashlib.sha256).digest()).decode().rstrip('=')\n"
                    "    with pytest.raises(ValueError, match='Token expired'):\n"
                    "        validate_jwt(f'{h}.{p}.{sig}', 'key', current_time=1001)\n\n"
                    "def test_invalid_signature():\n"
                    "    h = _b64({'alg': 'HS256', 'typ': 'JWT'})\n"
                    "    p = _b64({'sub': 'user123', 'exp': 2000})\n"
                    "    token = f'{h}.{p}.invalidsig'\n"
                    "    with pytest.raises(ValueError, match='Invalid signature'):\n"
                    "        validate_jwt(token, 'key', current_time=1500)\n"
                )
            },
            expected_behavior="Validates 3-part JWT base64url encoding, verifies HMAC-SHA256 signature, and enforces expiration/nbf timestamps.",
            acceptance_criteria=[
                "Decodes valid JWT payload",
                "Rejects expired tokens with explicit message",
                "Rejects signature mismatches",
                "Supports base64url unpadded decoding",
            ],
        )
    )

    # 4. Rate Limiter (Token Bucket)
    tasks.append(
        BenchmarkTask(
            task_id="basic_04_token_bucket_limiter",
            category=BenchmarkCategory.BASIC_IMPLEMENTATION,
            title="Token Bucket Rate Limiter",
            description=(
                "Implement `TokenBucket(capacity: int, refill_rate: float)` in `limiter/token_bucket.py`. "
                "`capacity` is the maximum token count. `refill_rate` is tokens per second. "
                "`consume(tokens: int = 1, current_time: float = 0.0) -> bool`: "
                "Refills tokens proportionally to elapsed time since last check (capped at capacity). "
                "If sufficient tokens exist, deducts them and returns `True`; otherwise returns `False` without deducting. "
                "Raise `ValueError` if `capacity <= 0` or `refill_rate <= 0`."
            ),
            initial_files={
                "limiter/token_bucket.py": (
                    "class TokenBucket:\n"
                    "    def __init__(self, capacity: int, refill_rate: float):\n"
                    "        # TODO: Implement TokenBucket\n"
                    "        pass\n\n"
                    "    def consume(self, tokens: int = 1, current_time: float = 0.0) -> bool:\n"
                    "        pass\n"
                )
            },
            baseline_tests={
                "tests/test_limiter.py": (
                    "from limiter.token_bucket import TokenBucket\n\n"
                    "def test_burst_and_reject():\n"
                    "    tb = TokenBucket(capacity=5, refill_rate=1.0)\n"
                    "    assert tb.consume(3, current_time=0.0) is True\n"
                    "    assert tb.consume(2, current_time=0.0) is True\n"
                    "    assert tb.consume(1, current_time=0.0) is False\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_limiter.py": (
                    "import pytest\n"
                    "from limiter.token_bucket import TokenBucket\n\n"
                    "def test_token_refill_over_time():\n"
                    "    tb = TokenBucket(capacity=10, refill_rate=2.0)\n"
                    "    assert tb.consume(10, current_time=0.0) is True\n"
                    "    assert tb.consume(1, current_time=0.0) is False\n"
                    "    # 2 seconds later -> 4 tokens refilled\n"
                    "    assert tb.consume(4, current_time=2.0) is True\n"
                    "    assert tb.consume(1, current_time=2.0) is False\n\n"
                    "def test_invalid_parameters():\n"
                    "    with pytest.raises(ValueError):\n"
                    "        TokenBucket(0, 1.0)\n"
                    "    with pytest.raises(ValueError):\n"
                    "        TokenBucket(5, -1.0)\n"
                )
            },
            expected_behavior="Accurately accumulates tokens based on elapsed delta time, prevents exceeding capacity, and rejects over-consumption.",
            acceptance_criteria=[
                "Consumes tokens up to capacity",
                "Refills at specified rate per second",
                "Caps tokens at capacity",
                "Rejects non-positive configuration parameters",
            ],
        )
    )

    # 5. Event Emitter
    tasks.append(
        BenchmarkTask(
            task_id="basic_05_event_emitter",
            category=BenchmarkCategory.BASIC_IMPLEMENTATION,
            title="Publish/Subscribe Event Emitter",
            description=(
                "Implement `EventEmitter` in `events/emitter.py`. "
                "Methods: `on(event, listener)`, `once(event, listener)`, `off(event, listener)`, "
                "`emit(event, *args, **kwargs) -> int` (returns count of listeners executed), "
                "and `listener_count(event) -> int`. "
                "`once` listeners must automatically unregister after their first execution."
            ),
            initial_files={
                "events/emitter.py": (
                    "from typing import Callable, Any\n\n"
                    "class EventEmitter:\n"
                    "    def __init__(self):\n"
                    "        pass\n\n"
                    "    def on(self, event: str, listener: Callable) -> None:\n"
                    "        pass\n\n"
                    "    def once(self, event: str, listener: Callable) -> None:\n"
                    "        pass\n\n"
                    "    def off(self, event: str, listener: Callable) -> None:\n"
                    "        pass\n\n"
                    "    def emit(self, event: str, *args: Any, **kwargs: Any) -> int:\n"
                    "        pass\n\n"
                    "    def listener_count(self, event: str) -> int:\n"
                    "        pass\n"
                )
            },
            baseline_tests={
                "tests/test_emitter.py": (
                    "from events.emitter import EventEmitter\n\n"
                    "def test_on_and_emit():\n"
                    "    ee = EventEmitter()\n"
                    "    calls = []\n"
                    "    ee.on('greet', lambda name: calls.append(f'Hello {name}'))\n"
                    "    count = ee.emit('greet', 'Alice')\n"
                    "    assert count == 1\n"
                    "    assert calls == ['Hello Alice']\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_emitter.py": (
                    "from events.emitter import EventEmitter\n\n"
                    "def test_once_listener_auto_removes():\n"
                    "    ee = EventEmitter()\n"
                    "    calls = []\n"
                    "    ee.once('ping', lambda: calls.append(1))\n"
                    "    assert ee.listener_count('ping') == 1\n"
                    "    assert ee.emit('ping') == 1\n"
                    "    assert calls == [1]\n"
                    "    assert ee.listener_count('ping') == 0\n"
                    "    assert ee.emit('ping') == 0\n"
                    "    assert calls == [1]\n\n"
                    "def test_off_unregisters_listener():\n"
                    "    ee = EventEmitter()\n"
                    "    fn = lambda: None\n"
                    "    ee.on('evt', fn)\n"
                    "    assert ee.listener_count('evt') == 1\n"
                    "    ee.off('evt', fn)\n"
                    "    assert ee.listener_count('evt') == 0\n"
                )
            },
            expected_behavior="Manages subscriber lists per event key, handles once listeners with self-cleanup, and supports arguments dispatch.",
            acceptance_criteria=[
                "Registers regular listeners via on",
                "Executes and unregisters once listeners",
                "Removes listeners via off",
                "Returns number of invoked listeners",
            ],
        )
    )

    # 6. SQL Query Builder
    tasks.append(
        BenchmarkTask(
            task_id="basic_06_sql_query_builder",
            category=BenchmarkCategory.BASIC_IMPLEMENTATION,
            title="Fluent SQL Query Builder with Parameterization",
            description=(
                "Implement `QueryBuilder` in `db/query_builder.py`. "
                "Methods: `table(name)`, `select(*cols)`, `where(col, op, val)`, `order_by(col, direction='ASC')`, "
                "`limit(n)`, and `build() -> Tuple[str, List[Any]]`. "
                "Must generate parameterized SQL (e.g. `SELECT id, name FROM users WHERE age > ? AND status = ? ORDER BY name ASC LIMIT ?`) "
                "and return the tuple of (query_string, parameter_values)."
            ),
            initial_files={
                "db/query_builder.py": (
                    "from typing import Tuple, List, Any\n\n"
                    "class QueryBuilder:\n"
                    "    def __init__(self):\n"
                    "        pass\n\n"
                    "    def table(self, name: str) -> 'QueryBuilder':\n"
                    "        pass\n\n"
                    "    def select(self, *columns: str) -> 'QueryBuilder':\n"
                    "        pass\n\n"
                    "    def where(self, column: str, op: str, value: Any) -> 'QueryBuilder':\n"
                    "        pass\n\n"
                    "    def order_by(self, column: str, direction: str = 'ASC') -> 'QueryBuilder':\n"
                    "        pass\n\n"
                    "    def limit(self, count: int) -> 'QueryBuilder':\n"
                    "        pass\n\n"
                    "    def build(self) -> Tuple[str, List[Any]]:\n"
                    "        pass\n"
                )
            },
            baseline_tests={
                "tests/test_builder.py": (
                    "from db.query_builder import QueryBuilder\n\n"
                    "def test_simple_select():\n"
                    "    qb = QueryBuilder()\n"
                    "    sql, params = qb.table('users').select('id', 'name').where('age', '>=', 18).build()\n"
                    "    assert sql == 'SELECT id, name FROM users WHERE age >= ?'\n"
                    "    assert params == [18]\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_builder.py": (
                    "from db.query_builder import QueryBuilder\n\n"
                    "def test_complex_query_multiple_wheres():\n"
                    "    qb = QueryBuilder()\n"
                    "    sql, params = (\n"
                    "        qb.table('orders')\n"
                    "        .select('*')\n"
                    "        .where('user_id', '=', 42)\n"
                    "        .where('status', '=', 'completed')\n"
                    "        .order_by('created_at', 'DESC')\n"
                    "        .limit(10)\n"
                    "        .build()\n"
                    "    )\n"
                    "    assert sql == 'SELECT * FROM orders WHERE user_id = ? AND status = ? ORDER BY created_at DESC LIMIT ?'\n"
                    "    assert params == [42, 'completed', 10]\n"
                )
            },
            expected_behavior="Chains fluent query calls into a clean parameterized SQL statement and ordered list of parameter values.",
            acceptance_criteria=[
                "Chains table, select, where, order_by, limit",
                "Joins multiple where clauses with AND",
                "Substitutes placeholders with ? and extracts parameters",
            ],
        )
    )

    # 7. Retry Backoff Decorator
    tasks.append(
        BenchmarkTask(
            task_id="basic_07_retry_decorator",
            category=BenchmarkCategory.BASIC_IMPLEMENTATION,
            title="Exponential Backoff Retry Decorator",
            description=(
                "Implement `@retry(max_attempts=3, backoff_factor=2.0, exceptions=(Exception,))` in `utils/retry.py`. "
                "Wraps a function and retries on specified exceptions up to `max_attempts`. "
                "Delays execution by `backoff_factor ** (attempt - 1)` seconds using `time.sleep`. "
                "If all attempts fail, re-raises the final exception. Non-matching exceptions must raise immediately without retry."
            ),
            initial_files={
                "utils/retry.py": (
                    "from typing import Tuple, Type, Callable, Any\n"
                    "import time\n\n"
                    "def retry(max_attempts: int = 3, backoff_factor: float = 2.0, exceptions: Tuple[Type[Exception], ...] = (Exception,)):\n"
                    "    # TODO: Implement retry decorator\n"
                    "    pass\n"
                )
            },
            baseline_tests={
                "tests/test_retry.py": (
                    "from utils.retry import retry\n\n"
                    "def test_retry_eventual_success():\n"
                    "    attempts = 0\n"
                    "    @retry(max_attempts=3, backoff_factor=0.01)\n"
                    "    def flaky():\n"
                    "        nonlocal attempts\n"
                    "        attempts += 1\n"
                    "        if attempts < 2:\n"
                    "            raise ValueError('Temporary error')\n"
                    "        return 'success'\n"
                    "    assert flaky() == 'success'\n"
                    "    assert attempts == 2\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_retry.py": (
                    "import pytest\n"
                    "from utils.retry import retry\n\n"
                    "def test_retry_exhaustion_raises():\n"
                    "    attempts = 0\n"
                    "    @retry(max_attempts=3, backoff_factor=0.001)\n"
                    "    def always_fail():\n"
                    "        nonlocal attempts\n"
                    "        attempts += 1\n"
                    "        raise RuntimeError('Permanent failure')\n"
                    "    with pytest.raises(RuntimeError, match='Permanent failure'):\n"
                    "        always_fail()\n"
                    "    assert attempts == 3\n\n"
                    "def test_retry_selective_exception():\n"
                    "    attempts = 0\n"
                    "    @retry(max_attempts=3, backoff_factor=0.001, exceptions=(ValueError,))\n"
                    "    def unexpected():\n"
                    "        nonlocal attempts\n"
                    "        attempts += 1\n"
                    "        raise KeyError('Not retried')\n"
                    "    with pytest.raises(KeyError):\n"
                    "        unexpected()\n"
                    "    assert attempts == 1  # Should NOT retry KeyError\n"
                )
            },
            expected_behavior="Retries failed calls up to max_attempts with exponential delay, filtering strictly by target exception types.",
            acceptance_criteria=[
                "Returns value on successful first call or retry",
                "Re-raises final exception after max_attempts",
                "Raises unhandled exception types without retry",
            ],
        )
    )

    # 8. SemVer Parser
    tasks.append(
        BenchmarkTask(
            task_id="basic_08_semver_parser",
            category=BenchmarkCategory.BASIC_IMPLEMENTATION,
            title="Semantic Versioning Parser and Comparator",
            description=(
                "Implement `SemVer(v_str: str)` in `versioning/semver.py`. "
                "Parses versions matching `MAJOR.MINOR.PATCH[-PRERELEASE]`. "
                "Properties: `major`, `minor`, `patch`, `prerelease` (None or str). "
                "Implements rich comparison (`<`, `<=`, `>`, `>=`, `==`). "
                "A version without prerelease has higher precedence than a version with prerelease (e.g. `1.0.0 > 1.0.0-alpha`). "
                "Invalid version strings must raise `ValueError`."
            ),
            initial_files={
                "versioning/semver.py": (
                    "class SemVer:\n"
                    "    def __init__(self, v_str: str):\n"
                    "        # TODO: Implement SemVer parser\n"
                    "        pass\n"
                )
            },
            baseline_tests={
                "tests/test_semver.py": (
                    "from versioning.semver import SemVer\n\n"
                    "def test_semver_basic_comparison():\n"
                    "    v1 = SemVer('1.2.3')\n"
                    "    v2 = SemVer('1.2.4')\n"
                    "    assert v1 < v2\n"
                    "    assert v2 > v1\n"
                    "    assert SemVer('2.0.0') > SemVer('1.9.9')\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_semver.py": (
                    "import pytest\n"
                    "from versioning.semver import SemVer\n\n"
                    "def test_prerelease_precedence():\n"
                    "    release = SemVer('1.0.0')\n"
                    "    alpha = SemVer('1.0.0-alpha')\n"
                    "    beta = SemVer('1.0.0-beta')\n"
                    "    assert alpha < release\n"
                    "    assert alpha < beta\n"
                    "    assert release > alpha\n\n"
                    "def test_invalid_semver():\n"
                    "    with pytest.raises(ValueError):\n"
                    "        SemVer('1.0')\n"
                    "    with pytest.raises(ValueError):\n"
                    "        SemVer('v1.0.0')\n"
                    "    with pytest.raises(ValueError):\n"
                    "        SemVer('1.0.0.0')\n"
                )
            },
            expected_behavior="Parses semver strings, correctly compares numeric segments and prerelease tags, raises ValueError on malformed formats.",
            acceptance_criteria=[
                "Parses major, minor, patch, prerelease",
                "Handles comparison operators accurately",
                "Prioritizes release versions over pre-release versions",
                "Rejects non-semver strings with ValueError",
            ],
        )
    )

    # 9. CSV Stream Transformer
    tasks.append(
        BenchmarkTask(
            task_id="basic_09_csv_transformer",
            category=BenchmarkCategory.BASIC_IMPLEMENTATION,
            title="Streaming CSV Aggregation Engine",
            description=(
                "Implement `transform_csv_stream(csv_lines, filter_col, min_val, agg_col)` in `etl/transformer.py`. "
                "`csv_lines` is an iterable of raw CSV strings (first line is header). "
                "Filters rows where `float(row[filter_col]) >= min_val`. "
                "Aggregates `agg_col`: returns `{'count': int, 'sum': float, 'avg': float, 'min': float, 'max': float}`. "
                "If no matching rows remain, return `{'count': 0, 'sum': 0.0, 'avg': 0.0, 'min': 0.0, 'max': 0.0}`. "
                "Raise `KeyError` if `filter_col` or `agg_col` is not in header."
            ),
            initial_files={
                "etl/transformer.py": (
                    "from typing import Iterable, Dict, Any\n\n"
                    "def transform_csv_stream(csv_lines: Iterable[str], filter_col: str, min_val: float, agg_col: str) -> Dict[str, Any]:\n"
                    "    # TODO: Implement streaming CSV transformation\n"
                    "    pass\n"
                )
            },
            baseline_tests={
                "tests/test_etl.py": (
                    "from etl.transformer import transform_csv_stream\n\n"
                    "def test_basic_csv_aggregation():\n"
                    "    lines = [\n"
                    "        'id,score,price\\n',\n"
                    "        '1,80,10.5\\n',\n"
                    "        '2,95,20.0\\n',\n"
                    "        '3,50,5.0\\n',\n"
                    "    ]\n"
                    "    stats = transform_csv_stream(lines, filter_col='score', min_val=75.0, agg_col='price')\n"
                    "    assert stats['count'] == 2\n"
                    "    assert stats['sum'] == 30.5\n"
                    "    assert stats['avg'] == 15.25\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_etl.py": (
                    "import pytest\n"
                    "from etl.transformer import transform_csv_stream\n\n"
                    "def test_no_matching_rows():\n"
                    "    lines = ['id,score,price\\n', '1,40,10.0\\n']\n"
                    "    stats = transform_csv_stream(lines, 'score', 90.0, 'price')\n"
                    "    assert stats == {'count': 0, 'sum': 0.0, 'avg': 0.0, 'min': 0.0, 'max': 0.0}\n\n"
                    "def test_missing_column_raises():\n"
                    "    lines = ['id,score\\n', '1,50\\n']\n"
                    "    with pytest.raises(KeyError):\n"
                    "        transform_csv_stream(lines, 'nonexistent', 10.0, 'score')\n"
                )
            },
            expected_behavior="Processes CSV lines without loading entire file in memory, filters by threshold, and computes statistical aggregates.",
            acceptance_criteria=[
                "Calculates count, sum, avg, min, max",
                "Handles zero-match scenario with default zeros",
                "Raises KeyError for absent columns",
            ],
        )
    )

    # 10. Prefix Trie Autocomplete
    tasks.append(
        BenchmarkTask(
            task_id="basic_10_prefix_trie",
            category=BenchmarkCategory.BASIC_IMPLEMENTATION,
            title="Prefix Trie with Ranked Autocomplete",
            description=(
                "Implement `PrefixTrie` in `trie/prefix_trie.py`. "
                "Methods: `insert(word: str) -> None`, `contains(word: str) -> bool`, and `autocomplete(prefix: str, limit: int = 5) -> List[str]`. "
                "`autocomplete` returns matching words starting with `prefix` sorted lexicographically, capped at `limit`. "
                "Empty prefix matches all words in trie up to `limit`."
            ),
            initial_files={
                "trie/prefix_trie.py": (
                    "from typing import List\n\n"
                    "class PrefixTrie:\n"
                    "    def __init__(self):\n"
                    "        # TODO: Implement Trie node structure\n"
                    "        pass\n\n"
                    "    def insert(self, word: str) -> None:\n"
                    "        pass\n\n"
                    "    def contains(self, word: str) -> bool:\n"
                    "        pass\n\n"
                    "    def autocomplete(self, prefix: str, limit: int = 5) -> List[str]:\n"
                    "        pass\n"
                )
            },
            baseline_tests={
                "tests/test_trie.py": (
                    "from trie.prefix_trie import PrefixTrie\n\n"
                    "def test_trie_insert_and_autocomplete():\n"
                    "    t = PrefixTrie()\n"
                    "    for w in ['apple', 'application', 'apply', 'banana', 'app']:\n"
                    "        t.insert(w)\n"
                    "    assert t.contains('apple') is True\n"
                    "    assert t.contains('orange') is False\n"
                    "    suggestions = t.autocomplete('app', limit=3)\n"
                    "    assert suggestions == ['app', 'apple', 'application']\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_trie.py": (
                    "from trie.prefix_trie import PrefixTrie\n\n"
                    "def test_empty_prefix_and_missing_prefix():\n"
                    "    t = PrefixTrie()\n"
                    "    for w in ['cat', 'car', 'dog']:\n"
                    "        t.insert(w)\n"
                    "    assert t.autocomplete('zebra') == []\n"
                    "    assert t.autocomplete('', limit=2) == ['car', 'cat']\n"
                )
            },
            expected_behavior="Constructs tree of characters, traverses prefix nodes, and collects completions in alphabetical order with bounds checking.",
            acceptance_criteria=[
                "Correctly verifies word presence with contains",
                "Prefix search returns words in alphabetical order",
                "Respects limit parameter",
                "Handles empty prefix and absent prefixes",
            ],
        )
    )

    return tasks

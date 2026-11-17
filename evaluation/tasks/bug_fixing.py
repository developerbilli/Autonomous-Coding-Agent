"""Category 2: Bug Fixing Benchmark Tasks (10 Tasks).

Tests the agent's diagnostic and remediation capabilities:
Can it diagnose runtime exceptions, logical bugs, race conditions, and subtle language quirks?
"""

from typing import List
from evaluation.dataset import BenchmarkTask, BenchmarkCategory


def get_bug_fixing_tasks() -> List[BenchmarkTask]:
    tasks: List[BenchmarkTask] = []

    # 11. Division by Zero in Financial Calculator
    tasks.append(
        BenchmarkTask(
            task_id="bugfix_11_division_by_zero",
            category=BenchmarkCategory.BUG_FIXING,
            title="Division by Zero in Portfolio Rebalancer",
            description=(
                "Fix unhandled ZeroDivisionError in `finance/rebalance.py`. "
                "When `total_val == 0` (e.g. all asset values are zero), `calculate_weights` throws `ZeroDivisionError`. "
                "Must return `{asset: 0.0 for asset in holdings}` when total value is zero."
            ),
            initial_files={
                "finance/rebalance.py": (
                    "from typing import Dict\n\n"
                    "def calculate_weights(holdings: Dict[str, float]) -> Dict[str, float]:\n"
                    "    total_val = sum(holdings.values())\n"
                    "    # BUG: Fails when total_val is 0.0\n"
                    "    return {k: v / total_val for k, v in holdings.items()}\n"
                )
            },
            baseline_tests={
                "tests/test_rebalance.py": (
                    "from finance.rebalance import calculate_weights\n\n"
                    "def test_normal_weights():\n"
                    "    res = calculate_weights({'AAPL': 100.0, 'GOOG': 300.0})\n"
                    "    assert res['AAPL'] == 0.25\n"
                    "    assert res['GOOG'] == 0.75\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_rebalance.py": (
                    "from finance.rebalance import calculate_weights\n\n"
                    "def test_zero_total_holdings():\n"
                    "    res = calculate_weights({'AAPL': 0.0, 'GOOG': 0.0})\n"
                    "    assert res == {'AAPL': 0.0, 'GOOG': 0.0}\n\n"
                    "def test_empty_holdings():\n"
                    "    res = calculate_weights({})\n"
                    "    assert res == {}\n"
                )
            },
            expected_behavior="Checks if sum is 0.0 before dividing, returning 0.0 weights without throwing ZeroDivisionError.",
            acceptance_criteria=[
                "Calculates proportional weights for normal portfolios",
                "Returns 0.0 weights when all holdings are 0",
                "Handles empty dictionary gracefully",
            ],
        )
    )

    # 12. Sliding Window Off-by-One
    tasks.append(
        BenchmarkTask(
            task_id="bugfix_12_sliding_window_off_by_one",
            category=BenchmarkCategory.BUG_FIXING,
            title="Off-by-One in Moving Average Window",
            description=(
                "Fix off-by-one bug in `analytics/window.py`. "
                "`moving_average(data, window_size)` currently omits the final slice of data. "
                "Also, if `len(data) < window_size` or `window_size <= 0`, return an empty list."
            ),
            initial_files={
                "analytics/window.py": (
                    "from typing import List\n\n"
                    "def moving_average(data: List[float], window_size: int) -> List[float]:\n"
                    "    if window_size <= 0 or len(data) < window_size:\n"
                    "        return []\n"
                    "    result = []\n"
                    "    # BUG: range(len(data) - window_size) drops the final window!\n"
                    "    for i in range(len(data) - window_size):\n"
                    "        result.append(sum(data[i:i + window_size]) / window_size)\n"
                    "    return result\n"
                )
            },
            baseline_tests={
                "tests/test_window.py": (
                    "from analytics.window import moving_average\n\n"
                    "def test_window_basic():\n"
                    "    data = [10.0, 20.0, 30.0, 40.0]\n"
                    "    res = moving_average(data, 2)\n"
                    "    # Expected 3 averages: (10+20)/2=15, (20+30)/2=25, (30+40)/2=35\n"
                    "    assert len(res) == 3\n"
                    "    assert res == [15.0, 25.0, 35.0]\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_window.py": (
                    "from analytics.window import moving_average\n\n"
                    "def test_window_equal_to_data_length():\n"
                    "    res = moving_average([1.0, 2.0, 3.0], 3)\n"
                    "    assert res == [2.0]\n\n"
                    "def test_window_larger_than_data():\n"
                    "    assert moving_average([1.0, 2.0], 5) == []\n\n"
                    "def test_window_size_one():\n"
                    "    assert moving_average([1.0, 2.0, 3.0], 1) == [1.0, 2.0, 3.0]\n"
                )
            },
            expected_behavior="Uses `range(len(data) - window_size + 1)` so all valid window frames are calculated.",
            acceptance_criteria=[
                "Calculates all N - W + 1 averages",
                "Handles window_size == len(data)",
                "Returns empty list when data is smaller than window",
            ],
        )
    )

    # 13. Mutable Default Argument Pollution
    tasks.append(
        BenchmarkTask(
            task_id="bugfix_13_mutable_default_argument",
            category=BenchmarkCategory.BUG_FIXING,
            title="Mutable Default Argument Pollution Bug",
            description=(
                "Fix mutable default argument bug in `cart/basket.py`. "
                "`add_item(item, basket=[])` uses a default list that persists across separate invocations, "
                "leaking state between independent users."
            ),
            initial_files={
                "cart/basket.py": (
                    "from typing import List, Optional\n\n"
                    "# BUG: Mutable default argument basket=[]\n"
                    "def add_item(item: str, basket: List[str] = []) -> List[str]:\n"
                    "    basket.append(item)\n"
                    "    return basket\n"
                )
            },
            baseline_tests={
                "tests/test_basket.py": (
                    "from cart.basket import add_item\n\n"
                    "def test_add_single_item():\n"
                    "    b = add_item('apple')\n"
                    "    assert b == ['apple']\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_basket.py": (
                    "from cart.basket import add_item\n\n"
                    "def test_independent_baskets():\n"
                    "    b1 = add_item('item1')\n"
                    "    b2 = add_item('item2')\n"
                    "    # If bug exists, b2 would contain ['item1', 'item2']\n"
                    "    assert b1 == ['item1']\n"
                    "    assert b2 == ['item2']\n"
                )
            },
            expected_behavior="Replaces mutable default argument with `basket: Optional[List[str]] = None` and initializes new list.",
            acceptance_criteria=[
                "Does not leak state between calls when basket is omitted",
                "Appends to caller-provided basket if passed explicitly",
            ],
        )
    )

    # 14. Shallow Copy Nested Dict Mutation
    tasks.append(
        BenchmarkTask(
            task_id="bugfix_14_shallow_copy_nested_dict",
            category=BenchmarkCategory.BUG_FIXING,
            title="Shallow Copy Nested Config Mutation",
            description=(
                "Fix config corruption bug in `config/manager.py`. "
                "`ConfigManager` copies default settings with `copy()`, creating a shallow copy. "
                "When nested keys (like `database.port`) are modified in one instance, "
                "the shared default template is permanently altered for future instances."
            ),
            initial_files={
                "config/manager.py": (
                    "import copy\n"
                    "from typing import Dict, Any\n\n"
                    "DEFAULT_CONFIG = {\n"
                    "    'app': {'name': 'MyApp', 'debug': False},\n"
                    "    'database': {'host': 'localhost', 'port': 5432}\n"
                    "}\n\n"
                    "class ConfigManager:\n"
                    "    def __init__(self):\n"
                    "        # BUG: shallow copy shares nested dictionary references\n"
                    "        self.settings: Dict[str, Any] = DEFAULT_CONFIG.copy()\n\n"
                    "    def set(self, section: str, key: str, value: Any) -> None:\n"
                    "        self.settings[section][key] = value\n\n"
                    "    def get(self, section: str, key: str) -> Any:\n"
                    "        return self.settings[section][key]\n"
                )
            },
            baseline_tests={
                "tests/test_config.py": (
                    "from config.manager import ConfigManager\n\n"
                    "def test_modify_instance_config():\n"
                    "    cfg = ConfigManager()\n"
                    "    cfg.set('database', 'port', 9999)\n"
                    "    assert cfg.get('database', 'port') == 9999\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_config.py": (
                    "from config.manager import ConfigManager, DEFAULT_CONFIG\n\n"
                    "def test_default_config_remains_unpolluted():\n"
                    "    cfg1 = ConfigManager()\n"
                    "    cfg1.set('database', 'port', 7777)\n"
                    "    cfg2 = ConfigManager()\n"
                    "    assert cfg2.get('database', 'port') == 5432\n"
                    "    assert DEFAULT_CONFIG['database']['port'] == 5432\n"
                )
            },
            expected_behavior="Uses deep copy (`copy.deepcopy`) to ensure nested dictionaries are fully isolated.",
            acceptance_criteria=[
                "Modifying one ConfigManager does not affect another",
                "DEFAULT_CONFIG remains untouched",
            ],
        )
    )

    # 15. Timezone-Aware vs Naive Datetime Comparison
    tasks.append(
        BenchmarkTask(
            task_id="bugfix_15_tz_naive_datetime",
            category=BenchmarkCategory.BUG_FIXING,
            title="Timezone-Aware Datetime Subtraction Bug",
            description=(
                "Fix `TypeError: can't subtract offset-naive and offset-aware datetimes` in `auth/session.py`. "
                "`is_expired(created_at, ttl_seconds)` compares `datetime.now()` (naive) "
                "with `created_at` which may be timezone-aware (UTC). "
                "Standardize comparison in UTC."
            ),
            initial_files={
                "auth/session.py": (
                    "from datetime import datetime, timezone\n\n"
                    "def is_expired(created_at: datetime, ttl_seconds: int = 3600) -> bool:\n"
                    "    # BUG: datetime.now() is naive, fails if created_at has timezone\n"
                    "    now = datetime.now()\n"
                    "    elapsed = (now - created_at).total_seconds()\n"
                    "    return elapsed >= ttl_seconds\n"
                )
            },
            baseline_tests={
                "tests/test_session.py": (
                    "from datetime import datetime, timezone, timedelta\n"
                    "from auth.session import is_expired\n\n"
                    "def test_expired_naive():\n"
                    "    created = datetime.now() - timedelta(seconds=4000)\n"
                    "    assert is_expired(created, ttl_seconds=3600) is True\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_session.py": (
                    "from datetime import datetime, timezone, timedelta\n"
                    "from auth.session import is_expired\n\n"
                    "def test_aware_utc_comparison():\n"
                    "    created = datetime.now(timezone.utc) - timedelta(seconds=100)\n"
                    "    assert is_expired(created, ttl_seconds=3600) is False\n\n"
                    "def test_aware_utc_expired():\n"
                    "    created = datetime.now(timezone.utc) - timedelta(seconds=5000)\n"
                    "    assert is_expired(created, ttl_seconds=3600) is True\n"
                )
            },
            expected_behavior="Normalizes both datetimes to UTC or consistent timezone before calculating elapsed delta.",
            acceptance_criteria=[
                "Works seamlessly with timezone-aware datetime objects",
                "Works with naive datetimes without raising TypeError",
            ],
        )
    )

    # 16. Regex Catastrophic Backtracking (ReDoS)
    tasks.append(
        BenchmarkTask(
            task_id="bugfix_16_regex_catastrophic_backtracking",
            category=BenchmarkCategory.BUG_FIXING,
            title="Catastrophic Backtracking in Pattern Validator",
            description=(
                "Fix catastrophic backtracking (ReDoS) in `validators/phone.py`. "
                "The current regex `^(\\d+)+$` causes exponential backtracking on inputs like `'1' * 35 + 'x'`. "
                "Replace with an efficient, linear pattern that validates non-empty digits with optional single dashes between digits."
            ),
            initial_files={
                "validators/phone.py": (
                    "import re\n\n"
                    "# BUG: Catastrophic backtracking nested quantifier (\\d+)+\n"
                    "PHONE_PATTERN = re.compile(r'^(\\d+)+$')\n\n"
                    "def is_valid_phone(s: str) -> bool:\n"
                    "    return bool(PHONE_PATTERN.match(s))\n"
                )
            },
            baseline_tests={
                "tests/test_phone.py": (
                    "from validators.phone import is_valid_phone\n\n"
                    "def test_phone_valid():\n"
                    "    assert is_valid_phone('1234567890') is True\n"
                    "    assert is_valid_phone('abc') is False\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_phone.py": (
                    "import time\n"
                    "from validators.phone import is_valid_phone\n\n"
                    "def test_redos_attack_string_completes_instantly():\n"
                    "    attack_str = '9' * 40 + '!'\n"
                    "    t0 = time.time()\n"
                    "    assert is_valid_phone(attack_str) is False\n"
                    "    duration = time.time() - t0\n"
                    "    assert duration < 0.1, f'Took too long ({duration}s), vulnerable to ReDoS!'\n"
                )
            },
            expected_behavior="Uses simple atomic pattern (e.g. `^\\d+$` or linear scanning) completing in sub-millisecond time.",
            acceptance_criteria=[
                "Validates digits correctly",
                "Rejects invalid input instantly without CPU spike",
            ],
        )
    )

    # 17. Race Condition in Counter
    tasks.append(
        BenchmarkTask(
            task_id="bugfix_17_race_condition_counter",
            category=BenchmarkCategory.BUG_FIXING,
            title="Race Condition in Thread-Safe Metric Counter",
            description=(
                "Fix race condition in `concurrency/counter.py`. "
                "`ThreadSafeCounter` claims to be thread-safe but updates `self.count += 1` "
                "without synchronization locks, losing updates under concurrent threads."
            ),
            initial_files={
                "concurrency/counter.py": (
                    "class ThreadSafeCounter:\n"
                    "    def __init__(self):\n"
                    "        self.count = 0\n"
                    "        # BUG: Missing threading.Lock synchronization\n\n"
                    "    def increment(self) -> int:\n"
                    "        self.count += 1\n"
                    "        return self.count\n\n"
                    "    def get(self) -> int:\n"
                    "        return self.count\n"
                )
            },
            baseline_tests={
                "tests/test_counter.py": (
                    "from concurrency.counter import ThreadSafeCounter\n\n"
                    "def test_single_thread():\n"
                    "    c = ThreadSafeCounter()\n"
                    "    c.increment()\n"
                    "    c.increment()\n"
                    "    assert c.get() == 2\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_counter.py": (
                    "import threading\n"
                    "from concurrency.counter import ThreadSafeCounter\n\n"
                    "def test_concurrent_increments():\n"
                    "    c = ThreadSafeCounter()\n"
                    "    threads = []\n"
                    "    for _ in range(10):\n"
                    "        t = threading.Thread(target=lambda: [c.increment() for _ in range(500)])\n"
                    "        threads.append(t)\n"
                    "        t.start()\n"
                    "    for t in threads:\n"
                    "        t.join()\n"
                    "    assert c.get() == 5000\n"
                )
            },
            expected_behavior="Protects increment and read operations with `threading.Lock()`.",
            acceptance_criteria=[
                "Increments exactly to N under heavy multithreaded contention",
                "Acquires and releases lock cleanly",
            ],
        )
    )

    # 18. Unhandled None Attribute in Deep Extractor
    tasks.append(
        BenchmarkTask(
            task_id="bugfix_18_unhandled_none_attribute",
            category=BenchmarkCategory.BUG_FIXING,
            title="AttributeError on None in Nested Dictionary Extractor",
            description=(
                "Fix unhandled `None` attribute in `parsers/extractor.py`. "
                "`get_path(data, 'user.profile.age', default=None)` crashes with `AttributeError` or `TypeError` "
                "when an intermediate key exists but has value `None`."
            ),
            initial_files={
                "parsers/extractor.py": (
                    "from typing import Any\n\n"
                    "def get_path(data: Any, path: str, default: Any = None) -> Any:\n"
                    "    keys = path.split('.')\n"
                    "    curr = data\n"
                    "    for k in keys:\n"
                    "        # BUG: Fails when curr is None\n"
                    "        curr = curr[k]\n"
                    "    return curr\n"
                )
            },
            baseline_tests={
                "tests/test_extractor.py": (
                    "from parsers.extractor import get_path\n\n"
                    "def test_get_existing_path():\n"
                    "    d = {'user': {'profile': {'age': 30}}}\n"
                    "    assert get_path(d, 'user.profile.age') == 30\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_extractor.py": (
                    "from parsers.extractor import get_path\n\n"
                    "def test_intermediate_none_returns_default():\n"
                    "    d = {'user': {'profile': None}}\n"
                    "    assert get_path(d, 'user.profile.age', default='N/A') == 'N/A'\n\n"
                    "def test_missing_key_returns_default():\n"
                    "    d = {'user': {}}\n"
                    "    assert get_path(d, 'user.profile.age', default=-1) == -1\n"
                )
            },
            expected_behavior="Verifies that each intermediate node is a mapping before key lookup, safely returning default.",
            acceptance_criteria=[
                "Returns value for valid path",
                "Returns default when intermediate node is None or missing",
                "Does not raise AttributeError or TypeError",
            ],
        )
    )

    # 19. SQL Injection Concatenation
    tasks.append(
        BenchmarkTask(
            task_id="bugfix_19_sql_injection",
            category=BenchmarkCategory.BUG_FIXING,
            title="SQL Injection Fix in User Repository",
            description=(
                "Fix SQL injection vulnerability in `db/user_repo.py`. "
                "`find_by_username(cursor, username)` uses formatted string interpolation `f\"SELECT * ... '{username}'\"`. "
                "Refactor to safe parameterization using `?` placeholders."
            ),
            initial_files={
                "db/user_repo.py": (
                    "from typing import Any, Optional, Tuple\n\n"
                    "def find_by_username(cursor: Any, username: str) -> Optional[Tuple]:\n"
                    "    # BUG: SQL Injection via f-string interpolation\n"
                    "    query = f\"SELECT id, username, email FROM users WHERE username = '{username}'\"\n"
                    "    cursor.execute(query)\n"
                    "    return cursor.fetchone()\n"
                )
            },
            baseline_tests={
                "tests/test_user_repo.py": (
                    "import sqlite3\n"
                    "from db.user_repo import find_by_username\n\n"
                    "def test_find_normal_user():\n"
                    "    conn = sqlite3.connect(':memory:')\n"
                    "    cur = conn.cursor()\n"
                    "    cur.execute('CREATE TABLE users (id INT, username TEXT, email TEXT)')\n"
                    "    cur.execute(\"INSERT INTO users VALUES (1, 'alice', 'alice@test.com')\")\n"
                    "    user = find_by_username(cur, 'alice')\n"
                    "    assert user == (1, 'alice', 'alice@test.com')\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_user_repo.py": (
                    "import sqlite3\n"
                    "from db.user_repo import find_by_username\n\n"
                    "def test_malicious_input_does_not_break_or_inject():\n"
                    "    conn = sqlite3.connect(':memory:')\n"
                    "    cur = conn.cursor()\n"
                    "    cur.execute('CREATE TABLE users (id INT, username TEXT, email TEXT)')\n"
                    "    cur.execute(\"INSERT INTO users VALUES (1, 'admin', 'admin@corp.com')\")\n"
                    "    # Injection attempt\n"
                    "    res = find_by_username(cur, \"' OR '1'='1\")\n"
                    "    assert res is None, 'SQL injection vulnerability detected!'\n"
                )
            },
            expected_behavior="Uses parameterized query `cursor.execute(..., (username,))` preventing SQL injection.",
            acceptance_criteria=[
                "Safely handles quotes and injection payloads",
                "Executes query with parameter tuple",
            ],
        )
    )

    # 20. Stale Cache Invalidation
    tasks.append(
        BenchmarkTask(
            task_id="bugfix_20_stale_cache_invalidation",
            category=BenchmarkCategory.BUG_FIXING,
            title="Stale Cache Invalidation in UserService",
            description=(
                "Fix stale cache bug in `services/user_service.py`. "
                "`update_user_email(user_id, email)` updates the persistent store but forgets "
                "to invalidate `self.cache.delete(f'user:{user_id}')`, resulting in stale cache reads."
            ),
            initial_files={
                "services/user_service.py": (
                    "from typing import Dict, Any, Optional\n\n"
                    "class UserService:\n"
                    "    def __init__(self, db: Dict[int, Dict[str, Any]], cache: Dict[str, Any]):\n"
                    "        self.db = db\n"
                    "        self.cache = cache\n\n"
                    "    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:\n"
                    "        cache_key = f'user:{user_id}'\n"
                    "        if cache_key in self.cache:\n"
                    "            return self.cache[cache_key]\n"
                    "        user = self.db.get(user_id)\n"
                    "        if user:\n"
                    "            self.cache[cache_key] = user.copy()\n"
                    "        return user\n\n"
                    "    def update_user_email(self, user_id: int, new_email: str) -> None:\n"
                    "        if user_id in self.db:\n"
                    "            self.db[user_id]['email'] = new_email\n"
                    "            # BUG: Missing cache invalidation!\n"
                )
            },
            baseline_tests={
                "tests/test_user_service.py": (
                    "from services.user_service import UserService\n\n"
                    "def test_get_user_caches():\n"
                    "    db = {1: {'id': 1, 'email': 'old@test.com'}}\n"
                    "    cache = {}\n"
                    "    svc = UserService(db, cache)\n"
                    "    assert svc.get_user(1)['email'] == 'old@test.com'\n"
                    "    assert 'user:1' in cache\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_user_service.py": (
                    "from services.user_service import UserService\n\n"
                    "def test_update_invalidates_cache():\n"
                    "    db = {1: {'id': 1, 'email': 'v1@test.com'}}\n"
                    "    cache = {}\n"
                    "    svc = UserService(db, cache)\n"
                    "    # Populate cache\n"
                    "    svc.get_user(1)\n"
                    "    # Update email\n"
                    "    svc.update_user_email(1, 'v2@test.com')\n"
                    "    # Next read MUST reflect new email, not stale cached email\n"
                    "    assert svc.get_user(1)['email'] == 'v2@test.com'\n"
                )
            },
            expected_behavior="Evicts or updates cache key on record mutation so subsequent reads reflect fresh database state.",
            acceptance_criteria=[
                "Invalidates cache key upon email update",
                "Subsequent get_user returns updated email",
            ],
        )
    )

    return tasks

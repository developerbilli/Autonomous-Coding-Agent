"""Category 4: Multi-File Changes Benchmark Tasks (10 Tasks).

Tests the agent's architectural and cross-file refactoring capabilities:
Can it understand repository-wide dependencies, coordinate edits across multiple modules,
and avoid breaking cross-file contracts?
"""

from typing import List
from evaluation.dataset import BenchmarkTask, BenchmarkCategory


def get_multi_file_tasks() -> List[BenchmarkTask]:
    tasks: List[BenchmarkTask] = []

    # 31. Repo-wide Rename Refactor
    tasks.append(
        BenchmarkTask(
            task_id="multifile_31_rename_refactor",
            category=BenchmarkCategory.MULTI_FILE,
            title="Repository-Wide Class Rename & Downstream Import Alignment",
            description=(
                "Refactor `UserAccount` to `UserProfile` across the repository. "
                "1. Rename class in `models/account.py`. "
                "2. Update references and import in `services/account_service.py`. "
                "3. Update references and import in `controllers/account_controller.py`. "
                "Ensure all downstream methods `get_profile_by_id` and `create_profile` work seamlessly."
            ),
            initial_files={
                "models/account.py": (
                    "class UserAccount:\n"
                    "    def __init__(self, user_id: int, username: str):\n"
                    "        self.user_id = user_id\n"
                    "        self.username = username\n"
                ),
                "services/account_service.py": (
                    "from models.account import UserAccount\n\n"
                    "class AccountService:\n"
                    "    def __init__(self):\n"
                    "        self.accounts = {}\n\n"
                    "    def create_account(self, user_id: int, username: str) -> UserAccount:\n"
                    "        acc = UserAccount(user_id, username)\n"
                    "        self.accounts[user_id] = acc\n"
                    "        return acc\n"
                ),
                "controllers/account_controller.py": (
                    "from services.account_service import AccountService\n\n"
                    "class AccountController:\n"
                    "    def __init__(self, service: AccountService):\n"
                    "        self.service = service\n\n"
                    "    def handle_signup(self, user_id: int, username: str) -> dict:\n"
                    "        acc = self.service.create_account(user_id, username)\n"
                    "        return {'id': acc.user_id, 'username': acc.username}\n"
                ),
            },
            baseline_tests={
                "tests/test_controller.py": (
                    "from services.account_service import AccountService\n"
                    "from controllers.account_controller import AccountController\n\n"
                    "def test_signup_flow():\n"
                    "    svc = AccountService()\n"
                    "    ctrl = AccountController(svc)\n"
                    "    res = ctrl.handle_signup(101, 'bob')\n"
                    "    assert res == {'id': 101, 'username': 'bob'}\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_refactor.py": (
                    "from models.account import UserProfile\n"
                    "from services.account_service import AccountService\n\n"
                    "def test_renamed_model_type():\n"
                    "    p = UserProfile(1, 'alice')\n"
                    "    assert p.user_id == 1\n"
                    "    svc = AccountService()\n"
                    "    acc = svc.create_account(2, 'charlie')\n"
                    "    assert isinstance(acc, UserProfile)\n"
                )
            },
            expected_behavior="Renames class to UserProfile, updates imports and type annotations across models, services, and controllers.",
            acceptance_criteria=[
                "Exports UserProfile from models/account.py",
                "Updates imports in services/account_service.py",
                "Controller and service tests pass cleanly",
            ],
        )
    )

    # 32. Plugin Registry Architecture
    tasks.append(
        BenchmarkTask(
            task_id="multifile_32_plugin_registry",
            category=BenchmarkCategory.MULTI_FILE,
            title="Extensible Dynamic Plugin Registry",
            description=(
                "Implement a dynamic plugin system: "
                "1. `plugins/base.py`: Define `BasePlugin(name: str)` with abstract method `process(data: str) -> str`. "
                "2. `plugins/markdown_plugin.py`: Inherit `BasePlugin`, uppercase data surrounded with `**`. "
                "3. `plugins/reverse_plugin.py`: Inherit `BasePlugin`, reverse the string. "
                "4. `registry.py`: Implement `PluginRegistry` with `register(plugin)`, `get(name)`, `run_pipeline(names, data)`."
            ),
            initial_files={
                "plugins/base.py": (
                    "from abc import ABC, abstractmethod\n\n"
                    "class BasePlugin(ABC):\n"
                    "    def __init__(self, name: str):\n"
                    "        self.name = name\n\n"
                    "    @abstractmethod\n"
                    "    def process(self, data: str) -> str:\n"
                    "        pass\n"
                ),
                "plugins/markdown_plugin.py": (
                    "from plugins.base import BasePlugin\n\n"
                    "class MarkdownPlugin(BasePlugin):\n"
                    "    # TODO: Implement markdown bold plugin\n"
                    "    pass\n"
                ),
                "plugins/reverse_plugin.py": (
                    "from plugins.base import BasePlugin\n\n"
                    "class ReversePlugin(BasePlugin):\n"
                    "    # TODO: Implement reverse text plugin\n"
                    "    pass\n"
                ),
                "registry.py": (
                    "from typing import Dict, List\n"
                    "from plugins.base import BasePlugin\n\n"
                    "class PluginRegistry:\n"
                    "    def __init__(self):\n"
                    "        self._plugins: Dict[str, BasePlugin] = {}\n\n"
                    "    def register(self, plugin: BasePlugin) -> None:\n"
                    "        pass\n\n"
                    "    def get(self, name: str) -> BasePlugin:\n"
                    "        pass\n\n"
                    "    def run_pipeline(self, plugin_names: List[str], data: str) -> str:\n"
                    "        pass\n"
                ),
            },
            baseline_tests={
                "tests/test_registry.py": (
                    "from registry import PluginRegistry\n"
                    "from plugins.markdown_plugin import MarkdownPlugin\n\n"
                    "def test_register_and_run_markdown():\n"
                    "    reg = PluginRegistry()\n"
                    "    md = MarkdownPlugin('md')\n"
                    "    reg.register(md)\n"
                    "    assert reg.get('md').process('hello') == '**HELLO**'\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_registry.py": (
                    "from registry import PluginRegistry\n"
                    "from plugins.markdown_plugin import MarkdownPlugin\n"
                    "from plugins.reverse_plugin import ReversePlugin\n\n"
                    "def test_multi_plugin_pipeline():\n"
                    "    reg = PluginRegistry()\n"
                    "    reg.register(MarkdownPlugin('md'))\n"
                    "    reg.register(ReversePlugin('rev'))\n"
                    "    # 'abc' -> md -> '**ABC**' -> rev -> '**CBA**'\n"
                    "    out = reg.run_pipeline(['md', 'rev'], 'abc')\n"
                    "    assert out == '**CBA**'\n"
                )
            },
            expected_behavior="Implements plugins conforming to BasePlugin, registers them in registry, and threads data sequentially through pipeline.",
            acceptance_criteria=[
                "MarkdownPlugin formats string with bold uppercase",
                "ReversePlugin reverses string",
                "PluginRegistry executes multiple plugins in specified order",
            ],
        )
    )

    # 33. Schema Migration & Model DAO Sync
    tasks.append(
        BenchmarkTask(
            task_id="multifile_33_schema_migration_dao",
            category=BenchmarkCategory.MULTI_FILE,
            title="Database Schema Field Migration Across DAO & Model",
            description=(
                "Add an `is_active: bool = True` field to the User domain: "
                "1. `db/schema.sql`: Add `is_active INTEGER DEFAULT 1` to CREATE TABLE users. "
                "2. `models/user.py`: Add `is_active: bool = True` to `User` dataclass. "
                "3. `dao/user_dao.py`: Update `create_user` to persist `is_active` and `get_user` to construct User with `is_active`."
            ),
            initial_files={
                "db/schema.sql": (
                    "CREATE TABLE IF NOT EXISTS users (\n"
                    "    id INTEGER PRIMARY KEY,\n"
                    "    email TEXT NOT NULL\n"
                    ");\n"
                ),
                "models/user.py": (
                    "from dataclasses import dataclass\n\n"
                    "@dataclass\n"
                    "class User:\n"
                    "    id: int\n"
                    "    email: str\n"
                ),
                "dao/user_dao.py": (
                    "import sqlite3\n"
                    "from models.user import User\n\n"
                    "class UserDAO:\n"
                    "    def __init__(self, conn: sqlite3.Connection):\n"
                    "        self.conn = conn\n\n"
                    "    def create_user(self, user_id: int, email: str) -> User:\n"
                    "        self.conn.execute('INSERT INTO users (id, email) VALUES (?, ?)', (user_id, email))\n"
                    "        self.conn.commit()\n"
                    "        return User(user_id, email)\n\n"
                    "    def get_user(self, user_id: int) -> User:\n"
                    "        cur = self.conn.execute('SELECT id, email FROM users WHERE id = ?', (user_id,))\n"
                    "        row = cur.fetchone()\n"
                    "        return User(row[0], row[1]) if row else None\n"
                ),
            },
            baseline_tests={
                "tests/test_dao.py": (
                    "import sqlite3\n"
                    "from dao.user_dao import UserDAO\n\n"
                    "def test_create_and_get():\n"
                    "    conn = sqlite3.connect(':memory:')\n"
                    "    with open('db/schema.sql') as f:\n"
                    "        conn.executescript(f.read())\n"
                    "    dao = UserDAO(conn)\n"
                    "    u = dao.create_user(1, 'alice@test.com')\n"
                    "    assert u.id == 1\n"
                    "    assert u.email == 'alice@test.com'\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_dao.py": (
                    "import sqlite3\n"
                    "from dao.user_dao import UserDAO\n\n"
                    "def test_is_active_persistence():\n"
                    "    conn = sqlite3.connect(':memory:')\n"
                    "    with open('db/schema.sql') as f:\n"
                    "        conn.executescript(f.read())\n"
                    "    dao = UserDAO(conn)\n"
                    "    u1 = dao.create_user(2, 'active@test.com', is_active=False)\n"
                    "    assert u1.is_active is False\n"
                    "    fetched = dao.get_user(2)\n"
                    "    assert fetched.is_active is False\n"
                )
            },
            expected_behavior="Updates schema SQL, dataclass, and DAO queries in lockstep to support boolean is_active.",
            acceptance_criteria=[
                "Schema defines is_active with default 1",
                "User model includes is_active field",
                "DAO stores and retrieves is_active correctly",
            ],
        )
    )

    # 34. Centralized Settings Singleton
    tasks.append(
        BenchmarkTask(
            task_id="multifile_34_settings_singleton",
            category=BenchmarkCategory.MULTI_FILE,
            title="Consolidate Scattered os.getenv into Typed Settings",
            description=(
                "Refactor ad-hoc `os.getenv` calls into a typed `AppSettings` singleton in `config/settings.py`. "
                "1. `config/settings.py`: Define `AppSettings` with `api_key: str`, `timeout: int = 30`, `debug: bool = False`, "
                "and helper `get_settings()`. "
                "2. `services/auth_service.py`: Import `get_settings()` instead of reading `os.getenv('API_KEY')`. "
                "3. `services/http_service.py`: Import `get_settings()` for `timeout` and `debug`."
            ),
            initial_files={
                "config/settings.py": (
                    "import os\n\n"
                    "class AppSettings:\n"
                    "    # TODO: Implement typed settings\n"
                    "    pass\n\n"
                    "def get_settings() -> AppSettings:\n"
                    "    pass\n"
                ),
                "services/auth_service.py": (
                    "import os\n\n"
                    "class AuthService:\n"
                    "    def authenticate(self, key: str) -> bool:\n"
                    "        expected = os.getenv('API_KEY', 'default_secret')\n"
                    "        return key == expected\n"
                ),
                "services/http_service.py": (
                    "import os\n\n"
                    "class HttpService:\n"
                    "    def get_timeout(self) -> int:\n"
                    "        return int(os.getenv('TIMEOUT', '30'))\n"
                ),
            },
            baseline_tests={
                "tests/test_settings.py": (
                    "from config.settings import get_settings\n\n"
                    "def test_default_settings():\n"
                    "    s = get_settings()\n"
                    "    assert s.timeout == 30\n"
                    "    assert s.debug is False\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_services.py": (
                    "from config.settings import get_settings\n"
                    "from services.auth_service import AuthService\n"
                    "from services.http_service import HttpService\n\n"
                    "def test_services_use_singleton():\n"
                    "    s = get_settings()\n"
                    "    s.api_key = 'custom_secret_key'\n"
                    "    s.timeout = 45\n"
                    "    auth = AuthService()\n"
                    "    assert auth.authenticate('custom_secret_key') is True\n"
                    "    http = HttpService()\n"
                    "    assert http.get_timeout() == 45\n"
                )
            },
            expected_behavior="Extracts environment variables into validated settings singleton and binds downstream services to it.",
            acceptance_criteria=[
                "AppSettings caches single instance",
                "AuthService uses settings.api_key",
                "HttpService uses settings.timeout",
            ],
        )
    )

    # 35. Break Circular Import via Protocol Interfaces
    tasks.append(
        BenchmarkTask(
            task_id="multifile_35_break_circular_import",
            category=BenchmarkCategory.MULTI_FILE,
            title="Break Circular Import with Shared Interface Protocol",
            description=(
                "Resolve circular dependency between `order/order.py` and `invoice/invoice.py`. "
                "`Order` currently imports `Invoice`, and `Invoice` imports `Order`. "
                "Extract common interface/protocol into `interfaces.py` and decouple the mutual module import."
            ),
            initial_files={
                "interfaces.py": (
                    "from typing import Protocol\n\n"
                    "# TODO: Define interfaces to break circular dependency\n"
                ),
                "order/order.py": (
                    "# Circular import issue:\n"
                    "from invoice.invoice import Invoice\n\n"
                    "class Order:\n"
                    "    def __init__(self, order_id: int, total: float):\n"
                    "        self.order_id = order_id\n"
                    "        self.total = total\n"
                    "        self.invoice = None\n\n"
                    "    def generate_invoice(self) -> 'Invoice':\n"
                    "        self.invoice = Invoice(self)\n"
                    "        return self.invoice\n"
                ),
                "invoice/invoice.py": (
                    "# Circular import issue:\n"
                    "from order.order import Order\n\n"
                    "class Invoice:\n"
                    "    def __init__(self, order: 'Order'):\n"
                    "        self.order_id = order.order_id\n"
                    "        self.amount = order.total\n"
                ),
            },
            baseline_tests={
                "tests/test_order_invoice.py": (
                    "def test_import_both_without_circular_error():\n"
                    "    import interfaces\n"
                    "    from order.order import Order\n"
                    "    from invoice.invoice import Invoice\n"
                    "    o = Order(1, 150.0)\n"
                    "    inv = o.generate_invoice()\n"
                    "    assert inv.amount == 150.0\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_clean_import.py": (
                    "import sys\n\n"
                    "def test_clean_independent_invoice_import():\n"
                    "    # Verify Invoice can be imported first without Order cycle crash\n"
                    "    for mod in list(sys.modules.keys()):\n"
                    "        if 'order' in mod or 'invoice' in mod:\n"
                    "            del sys.modules[mod]\n"
                    "    from invoice.invoice import Invoice\n"
                    "    assert Invoice is not None\n"
                )
            },
            expected_behavior="Decouples modules using type protocols or lazy resolution, eliminating mutual import errors.",
            acceptance_criteria=[
                "Both modules import cleanly in any order",
                "Order generates Invoice with accurate attributes",
            ],
        )
    )

    # 36. Correlation ID Middleware Pipeline
    tasks.append(
        BenchmarkTask(
            task_id="multifile_36_correlation_id_middleware",
            category=BenchmarkCategory.MULTI_FILE,
            title="Correlation ID ContextVar Propagation Across Middleware & Logger",
            description=(
                "Implement end-to-end request correlation ID tracking: "
                "1. `context/trace.py`: Define `correlation_id_ctx = ContextVar('correlation_id', default=None)`. "
                "2. `middleware/tracer.py`: Implement `TraceMiddleware(app)`. If request headers contain `X-Correlation-ID`, "
                "store it in context; otherwise generate a uuid4 string. Set response header `X-Correlation-ID`. "
                "3. `logger/app_logger.py`: Format log messages with prefix `[{correlation_id}] {message}`."
            ),
            initial_files={
                "context/trace.py": (
                    "from contextvars import ContextVar\n"
                    "# TODO: Implement correlation contextvar\n"
                ),
                "middleware/tracer.py": (
                    "import uuid\n"
                    "from context.trace import correlation_id_ctx\n\n"
                    "class TraceMiddleware:\n"
                    "    def __init__(self, handler):\n"
                    "        self.handler = handler\n\n"
                    "    def handle_request(self, headers: dict) -> dict:\n"
                    "        # TODO: Handle correlation header\n"
                    "        pass\n"
                ),
                "logger/app_logger.py": (
                    "from context.trace import correlation_id_ctx\n\n"
                    "def format_log(msg: str) -> str:\n"
                    "    # TODO: Prepend current correlation ID\n"
                    "    pass\n"
                ),
            },
            baseline_tests={
                "tests/test_trace.py": (
                    "from middleware.tracer import TraceMiddleware\n"
                    "from logger.app_logger import format_log\n\n"
                    "def test_supplied_correlation_id():\n"
                    "    mw = TraceMiddleware(lambda: format_log('User logged in'))\n"
                    "    res = mw.handle_request({'X-Correlation-ID': 'custom-123'})\n"
                    "    assert res['headers']['X-Correlation-ID'] == 'custom-123'\n"
                    "    assert res['log'] == '[custom-123] User logged in'\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_trace.py": (
                    "from middleware.tracer import TraceMiddleware\n"
                    "from logger.app_logger import format_log\n\n"
                    "def test_auto_generated_uuid():\n"
                    "    mw = TraceMiddleware(lambda: format_log('Auto generated'))\n"
                    "    res = mw.handle_request({})\n"
                    "    cid = res['headers']['X-Correlation-ID']\n"
                    "    assert len(cid) == 36\n"
                    "    assert res['log'] == f'[{cid}] Auto generated'\n"
                )
            },
            expected_behavior="Propagates correlation ID through ContextVar across middleware and logger without thread pollution.",
            acceptance_criteria=[
                "Uses incoming X-Correlation-ID if present",
                "Generates UUID4 if header is absent",
                "Injects ID into logger output",
            ],
        )
    )

    # 37. API Versioning Backward Compatibility
    tasks.append(
        BenchmarkTask(
            task_id="multifile_37_api_versioning_adapter",
            category=BenchmarkCategory.MULTI_FILE,
            title="API v1 to v2 Envelope Migration with Backwards Adapter",
            description=(
                "Evolve API responses: "
                "1. `services/user_service.py`: `get_user_data(user_id)` returns `{'id': user_id, 'name': 'Alice'}`. "
                "2. `routes/v2.py`: Wraps user data in envelope: `{'data': user_data, 'version': '2.0'}`. "
                "3. `routes/v1.py`: Backwards-compatible adapter returning unwrapped `{'id': ..., 'name': ...}`. "
                "Both routes must query `user_service.py`."
            ),
            initial_files={
                "services/user_service.py": (
                    "def get_user_data(user_id: int) -> dict:\n"
                    "    return {'id': user_id, 'name': 'Alice'}\n"
                ),
                "routes/v1.py": (
                    "from services.user_service import get_user_data\n\n"
                    "def get_user_v1(user_id: int) -> dict:\n"
                    "    # TODO: Return raw data\n"
                    "    pass\n"
                ),
                "routes/v2.py": (
                    "from services.user_service import get_user_data\n\n"
                    "def get_user_v2(user_id: int) -> dict:\n"
                    "    # TODO: Return enveloped data\n"
                    "    pass\n"
                ),
            },
            baseline_tests={
                "tests/test_versioning.py": (
                    "from routes.v1 import get_user_v1\n"
                    "from routes.v2 import get_user_v2\n\n"
                    "def test_v1_and_v2():\n"
                    "    assert get_user_v1(1) == {'id': 1, 'name': 'Alice'}\n"
                    "    assert get_user_v2(1) == {'data': {'id': 1, 'name': 'Alice'}, 'version': '2.0'}\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_versioning.py": (
                    "from routes.v1 import get_user_v1\n"
                    "from routes.v2 import get_user_v2\n\n"
                    "def test_different_user_ids():\n"
                    "    assert get_user_v1(99)['id'] == 99\n"
                    "    v2 = get_user_v2(99)\n"
                    "    assert v2['data']['id'] == 99\n"
                    "    assert v2['version'] == '2.0'\n"
                )
            },
            expected_behavior="Serves both v1 legacy format and v2 enveloped format from single underlying service.",
            acceptance_criteria=[
                "v1 returns direct dictionary",
                "v2 returns data and version envelope",
                "Both rely on user_service",
            ],
        )
    )

    # 38. Event Dispatcher & Multiple Listeners
    tasks.append(
        BenchmarkTask(
            task_id="multifile_38_event_dispatcher",
            category=BenchmarkCategory.MULTI_FILE,
            title="Event-Driven Signup with Audit & Welcome Handlers",
            description=(
                "Implement decoupled event architecture: "
                "1. `events/dispatcher.py`: `EventDispatcher` with `subscribe(event_name, handler)` and `dispatch(event_name, payload)`. "
                "2. `audit/audit_log.py`: `AuditLogger` subscribes to `'user.created'` and appends `f'AUDIT: user {user_id}'`. "
                "3. `notifications/notifier.py`: `Notifier` subscribes to `'user.created'` and appends `f'WELCOME: {email}'`. "
                "4. `auth/signup.py`: Dispatches `'user.created'` event when user registers."
            ),
            initial_files={
                "events/dispatcher.py": (
                    "from typing import Callable, List, Dict, Any\n\n"
                    "class EventDispatcher:\n"
                    "    def __init__(self):\n"
                    "        self._handlers: Dict[str, List[Callable]] = {}\n\n"
                    "    def subscribe(self, event: str, handler: Callable) -> None:\n"
                    "        pass\n\n"
                    "    def dispatch(self, event: str, payload: Any) -> None:\n"
                    "        pass\n"
                ),
                "audit/audit_log.py": (
                    "class AuditLogger:\n"
                    "    def __init__(self):\n"
                    "        self.logs = []\n"
                    "    def on_user_created(self, payload: dict) -> None:\n"
                    "        pass\n"
                ),
                "notifications/notifier.py": (
                    "class Notifier:\n"
                    "    def __init__(self):\n"
                    "        self.sent = []\n"
                    "    def on_user_created(self, payload: dict) -> None:\n"
                    "        pass\n"
                ),
                "auth/signup.py": (
                    "from events.dispatcher import EventDispatcher\n\n"
                    "class SignupService:\n"
                    "    def __init__(self, dispatcher: EventDispatcher):\n"
                    "        self.dispatcher = dispatcher\n\n"
                    "    def register(self, user_id: int, email: str) -> None:\n"
                    "        pass\n"
                ),
            },
            baseline_tests={
                "tests/test_events.py": (
                    "from events.dispatcher import EventDispatcher\n"
                    "from audit.audit_log import AuditLogger\n"
                    "from notifications.notifier import Notifier\n"
                    "from auth.signup import SignupService\n\n"
                    "def test_signup_dispatches():\n"
                    "    disp = EventDispatcher()\n"
                    "    audit = AuditLogger()\n"
                    "    notif = Notifier()\n"
                    "    disp.subscribe('user.created', audit.on_user_created)\n"
                    "    disp.subscribe('user.created', notif.on_user_created)\n"
                    "    signup = SignupService(disp)\n"
                    "    signup.register(42, 'test@example.com')\n"
                    "    assert 'AUDIT: user 42' in audit.logs\n"
                    "    assert 'WELCOME: test@example.com' in notif.sent\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_events.py": (
                    "from events.dispatcher import EventDispatcher\n"
                    "from auth.signup import SignupService\n\n"
                    "def test_multiple_registrations():\n"
                    "    disp = EventDispatcher()\n"
                    "    captured = []\n"
                    "    disp.subscribe('user.created', lambda p: captured.append(p['user_id']))\n"
                    "    signup = SignupService(disp)\n"
                    "    signup.register(1, 'a@a.com')\n"
                    "    signup.register(2, 'b@b.com')\n"
                    "    assert captured == [1, 2]\n"
                )
            },
            expected_behavior="Notifies all registered subscribers on event trigger with complete payload.",
            acceptance_criteria=[
                "Dispatcher executes all subscribers",
                "AuditLogger records audit string",
                "Notifier records welcome string",
            ],
        )
    )

    # 39. Cache Decorator Across Repository Layer
    tasks.append(
        BenchmarkTask(
            task_id="multifile_39_cache_decorator_repo",
            category=BenchmarkCategory.MULTI_FILE,
            title="In-Memory Cache Decorator Layer on Product Repository",
            description=(
                "Implement caching across repository calls: "
                "1. `cache/caching.py`: Implement `@memoize_repo(ttl_seconds: int = 60)` decorator that caches return values "
                "based on function name and arguments. Expose `clear_cache()` helper. "
                "2. `repositories/product_repo.py`: Decorate `get_product_by_id(product_id)` and `list_categories()`. "
                "Simulated DB query counts must not increment on cache hits."
            ),
            initial_files={
                "cache/caching.py": (
                    "import time\n"
                    "from functools import wraps\n"
                    "from typing import Callable, Any\n\n"
                    "def memoize_repo(ttl_seconds: int = 60):\n"
                    "    # TODO: Implement memoization decorator\n"
                    "    pass\n\n"
                    "def clear_cache():\n"
                    "    pass\n"
                ),
                "repositories/product_repo.py": (
                    "from cache.caching import memoize_repo\n\n"
                    "class ProductRepository:\n"
                    "    def __init__(self):\n"
                    "        self.query_count = 0\n\n"
                    "    @memoize_repo(ttl_seconds=60)\n"
                    "    def get_product(self, product_id: int) -> dict:\n"
                    "        self.query_count += 1\n"
                    "        return {'id': product_id, 'name': f'Product {product_id}'}\n"
                ),
            },
            baseline_tests={
                "tests/test_cached_repo.py": (
                    "from repositories.product_repo import ProductRepository\n"
                    "from cache.caching import clear_cache\n\n"
                    "def test_cache_hits_do_not_retrigger_db():\n"
                    "    clear_cache()\n"
                    "    repo = ProductRepository()\n"
                    "    p1 = repo.get_product(1)\n"
                    "    assert repo.query_count == 1\n"
                    "    p2 = repo.get_product(1)\n"
                    "    assert repo.query_count == 1  # Cache hit!\n"
                    "    assert p1 == p2\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_cached_repo.py": (
                    "from repositories.product_repo import ProductRepository\n"
                    "from cache.caching import clear_cache\n\n"
                    "def test_different_arguments_separate_keys():\n"
                    "    clear_cache()\n"
                    "    repo = ProductRepository()\n"
                    "    repo.get_product(1)\n"
                    "    repo.get_product(2)\n"
                    "    assert repo.query_count == 2\n"
                    "    clear_cache()\n"
                    "    repo.get_product(1)\n"
                    "    assert repo.query_count == 3  # Cache cleared\n"
                )
            },
            expected_behavior="Caches function outputs keyed by name and arguments, bypassing invocation on subsequent calls.",
            acceptance_criteria=[
                "Caches repeated calls with identical arguments",
                "Executes query for different arguments",
                "clear_cache flushes stored results",
            ],
        )
    )

    # 40. Metrics & Telemetry Across Controller & Worker
    tasks.append(
        BenchmarkTask(
            task_id="multifile_40_metrics_telemetry",
            category=BenchmarkCategory.MULTI_FILE,
            title="Shared Metric Registry Across HTTP Server & Background Worker",
            description=(
                "Implement application-wide metrics: "
                "1. `metrics/collector.py`: Define `MetricsCollector` with `increment_counter(name, val=1)` and `get_counter(name) -> int`. "
                "2. `http/server.py`: Use shared collector to increment `http.requests.total` on each `handle()`. "
                "3. `workers/worker.py`: Use shared collector to increment `worker.jobs.processed` on each `process_job()`."
            ),
            initial_files={
                "metrics/collector.py": (
                    "class MetricsCollector:\n"
                    "    def __init__(self):\n"
                    "        self.counters = {}\n\n"
                    "    def increment_counter(self, name: str, val: int = 1) -> None:\n"
                    "        pass\n\n"
                    "    def get_counter(self, name: str) -> int:\n"
                    "        pass\n"
                ),
                "http/server.py": (
                    "from metrics.collector import MetricsCollector\n\n"
                    "class HttpServer:\n"
                    "    def __init__(self, metrics: MetricsCollector):\n"
                    "        self.metrics = metrics\n\n"
                    "    def handle(self, route: str) -> str:\n"
                    "        # TODO: Increment http.requests.total\n"
                    "        return f'OK {route}'\n"
                ),
                "workers/worker.py": (
                    "from metrics.collector import MetricsCollector\n\n"
                    "class BackgroundWorker:\n"
                    "    def __init__(self, metrics: MetricsCollector):\n"
                    "        self.metrics = metrics\n\n"
                    "    def process_job(self, job_id: str) -> None:\n"
                    "        # TODO: Increment worker.jobs.processed\n"
                    "        pass\n"
                ),
            },
            baseline_tests={
                "tests/test_metrics.py": (
                    "from metrics.collector import MetricsCollector\n"
                    "from http.server import HttpServer\n"
                    "from workers.worker import BackgroundWorker\n\n"
                    "def test_server_and_worker_metrics():\n"
                    "    m = MetricsCollector()\n"
                    "    srv = HttpServer(m)\n"
                    "    wrk = BackgroundWorker(m)\n"
                    "    srv.handle('/home')\n"
                    "    srv.handle('/about')\n"
                    "    wrk.process_job('job-1')\n"
                    "    assert m.get_counter('http.requests.total') == 2\n"
                    "    assert m.get_counter('worker.jobs.processed') == 1\n"
                )
            },
            hidden_tests={
                "tests/test_hidden_metrics.py": (
                    "from metrics.collector import MetricsCollector\n\n"
                    "def test_uninitialized_counter():\n"
                    "    m = MetricsCollector()\n"
                    "    assert m.get_counter('absent') == 0\n"
                    "    m.increment_counter('custom', 5)\n"
                    "    assert m.get_counter('custom') == 5\n"
                )
            },
            expected_behavior="Aggregates application counters from multiple component callers into central registry.",
            acceptance_criteria=[
                "Tracks HTTP requests correctly",
                "Tracks worker jobs correctly",
                "Returns 0 for unrecorded counters",
            ],
        )
    )

    return tasks

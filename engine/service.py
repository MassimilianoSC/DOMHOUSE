"""The engine as a service of its own (P-60 step 2): one process per apartment, the contract at /api/v1, the
connector chosen by CONNECTOR. Started by python -m engine (engine/__main__.py)."""
import asyncio
import importlib
from contextlib import asynccontextmanager

from . import log
from .api import create_contract_app
from .config import EngineConfig
from .connector.interface import CONNECTOR_API_VERSION
from .core import ALL_FEATURES, ApartmentEngine
from .log import SECRET_NAME
from .store import SqliteStore

ENGINE_VERSION = "0.3.0"
IMPLEMENTATION = {"name": "domhouse-engine", "version": ENGINE_VERSION}
DB_NAME = "engine.db"           # in DATA_DIR, with its WAL files next to it


class StartupError(Exception):
    def __init__(self, msg: str, **fields):
        super().__init__(msg)
        self.msg, self.fields = msg, fields


def without_secrets(text: str, env) -> str:
    """An error's text for the log: the values of the secret variables (API_KEY and any *KEY*, *TOKEN*, *PASSWORD*,
    *SECRET* of the environment) blanked out, and at most 300 characters."""
    for name, value in env.items():
        if (name == "API_KEY" or SECRET_NAME.search(name)) and value and len(value) >= 4:
            text = text.replace(value, "[redacted]")
    return text[:300]


def load_connector(config: EngineConfig):
    """engine/connector/<CONNECTOR> must offer make_connector(ConnectorConfig) -> Connector, with api_version equal to
    the engine's CONNECTOR_API_VERSION: otherwise the engine does not start (connector.md §2.1). make_connector may read
    and check the catalog, never open connections (that is start()'s job): whatever it raises, like a library the
    connector's package cannot import, stops the engine with "connector setup failed" (§2.7)."""
    name = f"engine.connector.{config.connector}"
    try:
        module = importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name in (name, "engine.connector"):
            raise StartupError("unknown connector", connector=config.connector) from None
        raise StartupError("connector setup failed", connector=config.connector, error_type=type(exc).__name__,
                           error=without_secrets(str(exc), config.env)) from None
    except Exception as exc:
        raise StartupError("connector setup failed", connector=config.connector, error_type=type(exc).__name__,
                           error=without_secrets(str(exc), config.env)) from None
    make = getattr(module, "make_connector", None)
    if not callable(make):
        raise StartupError("connector without make_connector", connector=config.connector)
    try:
        connector = make(config.for_connector())       # never the key nor the engine's settings (§2.7)
    except Exception as exc:
        raise StartupError("connector setup failed", connector=config.connector, error_type=type(exc).__name__,
                           error=without_secrets(str(exc), config.env)) from None
    version = getattr(connector, "api_version", None)
    if version != CONNECTOR_API_VERSION:
        raise StartupError("connector API version mismatch", engine_version=CONNECTOR_API_VERSION,
                           connector_version=version, connector=config.connector)
    return connector


def create_engine_app(config: EngineConfig, connector=None):
    """The ASGI app of one apartment. The connector is started with the app and stopped with it."""
    connector = connector if connector is not None else load_connector(config)
    running: dict[str, ApartmentEngine] = {}

    @asynccontextmanager
    async def lifespan(app):
        store = SqliteStore(config.data_dir / DB_NAME)
        await connector.start()
        engine = ApartmentEngine(config.apartment_id, connector, simulated=config.simulated, seed=config.simulated,
                                 implementation=IMPLEMENTATION, store=store)
        engine.ensure_started()
        running["engine"] = engine
        log.info("engine started", connector=config.connector, devices=len(engine.devices), port=config.port,
                 restored=engine.restored)
        try:
            yield
        finally:
            for task in [engine.loop_task, engine.consumer_task, *engine.tasks]:
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(*(t for t in [engine.loop_task, engine.consumer_task] if t), return_exceptions=True)
            await connector.stop()
            store.close()
            log.info("engine stopped")

    def engine_of(_apartment_id: str) -> ApartmentEngine:
        engine = running["engine"]
        engine.ensure_started()
        return engine

    # /ask answers from keywords only in simulated mode; with a real connector it is 501 until step 9 (D-104)
    features = [f for f in ALL_FEATURES if config.simulated or f != "ask"]
    return create_contract_app(engine_of, config.api_key, features=features, simulated=config.simulated,
                               implementation=IMPLEMENTATION, ping_seconds=float(config.env.get("MOCK_PING_S", "25")),
                               apartment_id=config.apartment_id, lifespan=lifespan)

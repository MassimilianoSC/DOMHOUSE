"""The engine's configuration: environment variables only, read once at start (P-60 step 2).

    APARTMENT_ID   required   the apartment this process serves (e.g. apt-rimini-01)
    API_KEY        required   the X-API-Key the app must send, at least 16 characters; on the VM it comes from Secret
                              Manager (langbrain-api-key-<apartment_id>), never from the repository
    CONNECTOR      required   simulated | the name of a package in engine/connector/ (e.g. shelly)
    HOST, PORT     optional   where to listen; 127.0.0.1 and 8100 by default (in the container 0.0.0.0)
    DATA_DIR       optional   the apartment's data, /data/<apartment_id> by default (SQLite from step 3)
    CATALOG_PATH   optional   the devices' catalog, <DATA_DIR>/catalog.yaml by default (read by the connector)
    CONFIRM_ON_WATTS   optional   D-131: an infrared split's switch-on is confirmed when its linked meter's watts rise
                                  by at least this much over what they were before the command; 20 by default
    CONFIRM_OFF_WATTS  optional   D-131: its switch-off is confirmed when they drop under this; 15 by default
                                  (both within 10 s of the command, engine/confirmation.py; numbers from 1 to 5000)

With CONNECTOR=simulated also: MOCK_TIME_SCALE (real seconds per simulated minute: 60 = real time, the default here)
and DOMOTICA_TEST_CONNECTOR_DOWN=1 (the connector reported down: conformance scenario C14). A connector receives a
ConnectorConfig (for_connector()): no key, and of the environment only its own variables, <NAME>_* (connector.md §2.7).
"""
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .connector.interface import ConnectorConfig

# the engine's own variables: never passed to a connector, whatever its name
ENGINE_VARIABLES = {"APARTMENT_ID", "API_KEY", "CONNECTOR", "HOST", "PORT", "DATA_DIR", "CATALOG_PATH",
                    "MOCK_TIME_SCALE", "MOCK_PING_S", "CONFIRM_ON_WATTS", "CONFIRM_OFF_WATTS"}
CONFIRM_DEFAULTS = {"CONFIRM_ON_WATTS": 20.0, "CONFIRM_OFF_WATTS": 15.0}   # engine/confirmation.py's
APARTMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
CONNECTOR_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
MIN_KEY_LENGTH = 16
DEFAULT_DATA_ROOT = "/data"      # DATA_DIR is <this>/<apartment_id> when not set; the tests point it elsewhere


class ConfigError(Exception):
    """Every problem found, one per line: the engine does not start (connector.md §2.1, a key is required)."""


@dataclass(frozen=True)
class EngineConfig:
    apartment_id: str
    api_key: str = field(repr=False)
    connector: str
    host: str
    port: int
    data_dir: Path
    catalog_path: Path
    env: Mapping[str, str] = field(repr=False, default_factory=dict)
    confirm_on_watts: float = CONFIRM_DEFAULTS["CONFIRM_ON_WATTS"]
    confirm_off_watts: float = CONFIRM_DEFAULTS["CONFIRM_OFF_WATTS"]

    @property
    def simulated(self) -> bool:
        return self.connector == "simulated"

    def for_connector(self) -> ConnectorConfig:
        """What make_connector receives (connector.md §2.7): no key, no engine setting; of the environment only the
        connector's variables, <NAME>_* (SHELLY_* for CONNECTOR=shelly), never one of the engine's."""
        prefix = self.connector.upper() + "_"
        env = {k: v for k, v in self.env.items()
               if k.startswith(prefix) and k not in ENGINE_VARIABLES and not k.startswith(("DOMOTICA_", "MOCK_"))}
        return ConnectorConfig(apartment_id=self.apartment_id, data_dir=self.data_dir, catalog_path=self.catalog_path,
                               env=env)


def prepare_data_dir(config: EngineConfig) -> None:
    """DATA_DIR exists (created if missing) and the engine can write there (engine.db): otherwise a ConfigError, so the
    engine stops at once with a log line and exit code 2 instead of failing later inside the web server."""
    probe = config.data_dir / ".engine-write-check"
    try:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as exc:
        raise ConfigError(f"DATA_DIR {config.data_dir} is not a writable folder ({type(exc).__name__})") from None


def load_config(env: Mapping[str, str] | None = None) -> EngineConfig:
    env = dict(os.environ if env is None else env)
    problems = []
    apartment_id = env.get("APARTMENT_ID", "").strip()
    if not APARTMENT_RE.match(apartment_id):
        problems.append("APARTMENT_ID is required: letters, digits, - and _ (e.g. apt-rimini-01)")
    api_key = env.get("API_KEY", "").strip()       # as the BFF reads the same secret (bff/instances.py)
    if len(api_key.strip()) < MIN_KEY_LENGTH:
        problems.append(f"API_KEY is required, at least {MIN_KEY_LENGTH} characters")
    connector = env.get("CONNECTOR", "").strip()
    if not CONNECTOR_RE.match(connector):
        problems.append("CONNECTOR is required: simulated or the name of a package in engine/connector/ (e.g. shelly)")
    try:
        port = int(env.get("PORT", "8100"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        problems.append("PORT must be a number between 1 and 65535")
        port = 0
    watts = {}
    for name, default in CONFIRM_DEFAULTS.items():
        raw = env.get(name, "").strip()
        try:
            watts[name] = float(raw) if raw else default
            if not 1 <= watts[name] <= 5000:
                raise ValueError
        except ValueError:
            problems.append(f"{name} must be a number of watts between 1 and 5000")
    if problems:
        raise ConfigError("\n".join(problems))
    data_dir = Path(env.get("DATA_DIR") or f"{DEFAULT_DATA_ROOT}/{apartment_id}")
    return EngineConfig(apartment_id=apartment_id, api_key=api_key, connector=connector,
                        host=env.get("HOST", "127.0.0.1"), port=port, data_dir=data_dir,
                        catalog_path=Path(env.get("CATALOG_PATH") or data_dir / "catalog.yaml"), env=env,
                        confirm_on_watts=watts["CONFIRM_ON_WATTS"], confirm_off_watts=watts["CONFIRM_OFF_WATTS"])

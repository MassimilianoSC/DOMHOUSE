"""The engine's configuration: environment variables only, read once at start (P-60 step 2).

    APARTMENT_ID   required   the apartment this process serves (e.g. apt-rimini-01)
    API_KEY        required   the X-API-Key the app must send, at least 16 characters; on the VM it comes from Secret
                              Manager (langbrain-api-key-<apartment_id>), never from the repository
    CONNECTOR      required   simulated | the name of a package in engine/connector/ (e.g. shelly)
    HOST, PORT     optional   where to listen; 127.0.0.1 and 8100 by default (in the container 0.0.0.0)
    DATA_DIR       optional   the apartment's data, /data/<apartment_id> by default (SQLite from step 3)
    CATALOG_PATH   optional   the devices' catalog, <DATA_DIR>/catalog.yaml by default (read by the connector)
    MODEL_BASE_URL optional   P-60 step 9: the BFF's address (https://..., its POST /internal/ai/chat): the assistant
                              answers with the real model; without it /ask is the keyword one (simulated) or 501

The settings of the rules (D-131, D-133), optional, per apartment (on the VM in <apartment_id>.settings.env, written by
engine-vm.sh set/unset): SETTINGS below, name -> (default, lowest, highest). A value that is not a number or is out of
its range stops the engine at start, as a missing key does. The thresholds the app can change stay in /rules.

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
SETTINGS: dict[str, tuple[float, float, float]] = {
    # D-131: an infrared split's switch-on is confirmed when its linked meter's watts rise by at least this much over
    # what they were before the command, its switch-off when they drop under the second; within 10 s
    "CONFIRM_ON_WATTS": (20.0, 1.0, 5000.0),
    "CONFIRM_OFF_WATTS": (15.0, 1.0, 5000.0),
    # D-133: the boiler's thermostat and the frost protection: on below the setpoint, off above setpoint + this (°C)
    "THERMOSTAT_HYSTERESIS_C": (0.5, 0.1, 3.0),
    # at least these minutes between two switches of the relay made by the thermostat
    "THERMOSTAT_MIN_SWITCH_MINUTES": (5.0, 1.0, 60.0),
    # the split's compressor pause (rule compressor_min_off, not editable from the app: value and limits from here)
    "COMPRESSOR_MIN_OFF_MINUTES": (3.0, 1.0, 15.0),
    # a manual start this many seconds before the pause ends waits for it instead of being refused
    "COMPRESSOR_WAIT_SECONDS": (7.0, 0.0, 60.0),
    # at a restart, a scheduled action due more than these minutes ago is not run any more (failed, "missed")
    "MISSED_AFTER_MINUTES": (30.0, 5.0, 720.0),
    # an approval nobody answers is closed after these minutes (D-119: 30)
    "APPROVAL_EXPIRES_MINUTES": (30.0, 5.0, 720.0),
    # D-137, F1: at the check-out's switch to "empty", motion seen within these minutes and after the departure time
    # asks the manager first
    "CHECKOUT_PRESENCE_MINUTES": (30.0, 5.0, 180.0),
    # P-60 step 9 (D-132): questions to the assistant a day per apartment, counted before calling the model
    "ASK_DAILY_LIMIT": (50.0, 1.0, 1000.0),
    # D-137, F2: in an empty apartment, a meter above these watts for these minutes asks to switch the device off
    "EMPTY_POWER_WATTS": (300.0, 20.0, 5000.0),
    "EMPTY_POWER_MINUTES": (15.0, 5.0, 240.0),
}
# settings that are a choice, name -> (default, allowed values)
CHOICES: dict[str, tuple[str, tuple[str, ...]]] = {
    # D-137, F2: what an unanswered "switch off in an empty apartment" does when it expires: rejected by default (it
    # could be the cleaners' washing machine or a water heater)
    "EMPTY_POWER_EXPIRED_ACTION": ("reject", ("reject", "approve")),
}
DEFAULT_SETTINGS: dict[str, float | str] = {name: spec[0] for name, spec in (SETTINGS | CHOICES).items()}
ENGINE_VARIABLES = {"APARTMENT_ID", "API_KEY", "CONNECTOR", "HOST", "PORT", "DATA_DIR", "CATALOG_PATH",
                    "MOCK_TIME_SCALE", "MOCK_PING_S", "MODEL_BASE_URL", *SETTINGS, *CHOICES}
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
    settings: Mapping[str, float | str] = field(default_factory=lambda: dict(DEFAULT_SETTINGS))
    model_base_url: str | None = None

    @property
    def confirm_on_watts(self) -> float:
        return self.settings["CONFIRM_ON_WATTS"]

    @property
    def confirm_off_watts(self) -> float:
        return self.settings["CONFIRM_OFF_WATTS"]

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
    settings = {}
    for name, (default, low, high) in SETTINGS.items():
        raw = env.get(name, "").strip()
        try:
            settings[name] = float(raw) if raw else default
            if not low <= settings[name] <= high:
                raise ValueError
        except ValueError:
            problems.append(f"{name} must be a number between {low:g} and {high:g}")
    for name, (default, allowed) in CHOICES.items():
        value = env.get(name, "").strip().lower() or default
        if value not in allowed:
            problems.append(f"{name} must be one of: {', '.join(allowed)}")
        settings[name] = value
    model_base_url = env.get("MODEL_BASE_URL", "").strip() or None
    if model_base_url and not model_base_url.startswith(("https://", "http://")):
        problems.append("MODEL_BASE_URL must be the BFF's address, https://...")
    if problems:
        raise ConfigError("\n".join(problems))
    data_dir = Path(env.get("DATA_DIR") or f"{DEFAULT_DATA_ROOT}/{apartment_id}")
    return EngineConfig(apartment_id=apartment_id, api_key=api_key, connector=connector,
                        host=env.get("HOST", "127.0.0.1"), port=port, data_dir=data_dir,
                        catalog_path=Path(env.get("CATALOG_PATH") or data_dir / "catalog.yaml"), env=env,
                        settings=settings, model_base_url=model_base_url)

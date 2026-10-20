"""The engine as a service of its own (P-60 step 2): configuration and key, connector loading, the contract at
/api/v1 in simulated and in real mode, what reaches the app (no energy_total_wh, starting values), one command per
device, the deadline, the log. In-process, plus one start of python -m engine without a key.

Run: python -m pytest engine/tests -q
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from engine import core, log
from engine.config import ConfigError, load_config
from engine.connector.interface import CommandResult, DeviceInfo, Room, StateChange
from engine.connector.simulated import SimulatedConnector
from engine.service import IMPLEMENTATION, StartupError, create_engine_app, load_connector

ROOT = Path(__file__).resolve().parents[2]
KEY = "prova-chiave-0123456789"
CORR = "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
HEADERS = {"X-API-Key": KEY, "X-Actor": "prova@hqe.it", "X-Correlation-Id": CORR}
ENV = {"APARTMENT_ID": "apt-prova-01", "API_KEY": KEY, "CONNECTOR": "simulated"}


def config(**over):
    return load_config({**ENV, **over})


# ---- configuration -------------------------------------------------------------------------------------------------
def test_configuration_lists_every_problem():
    with pytest.raises(ConfigError) as exc:
        load_config({"PORT": "zero"})
    problems = str(exc.value).splitlines()
    assert len(problems) == 4 and all(p.split()[0] in ("APARTMENT_ID", "API_KEY", "CONNECTOR", "PORT") for p in problems)


def test_key_is_required_and_not_short():
    with pytest.raises(ConfigError, match="API_KEY"):
        load_config({**ENV, "API_KEY": "corta"})
    assert "prova-chiave" not in repr(config())          # the key never shows up in a log or a traceback


def test_defaults(monkeypatch):
    from engine import config as config_module
    monkeypatch.setattr(config_module, "DEFAULT_DATA_ROOT", "/data")      # the production default (conftest.py)
    c = config()
    assert (c.host, c.port, c.simulated) == ("127.0.0.1", 8100, True)
    assert c.data_dir.as_posix() == "/data/apt-prova-01" and c.catalog_path.as_posix() == "/data/apt-prova-01/catalog.yaml"


def test_engine_does_not_start_without_a_key():
    env = {k: v for k, v in os.environ.items() if k not in ("API_KEY", "APARTMENT_ID", "CONNECTOR")}
    env.update(APARTMENT_ID="apt-prova-01", CONNECTOR="simulated")
    out = subprocess.run([sys.executable, "-m", "engine"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 2
    line = json.loads(out.stdout.strip().splitlines()[-1])
    assert line["msg"] == "invalid configuration" and line["apartment_id"] == "apt-prova-01"


def test_engine_does_not_start_without_a_writable_data_dir(tmp_path):
    """DATA_DIR that cannot be created or written (the CI runner has no /data): exit 2 and a log line, no traceback."""
    blocker = tmp_path / "un-file"
    blocker.write_text("x")
    env = {k: v for k, v in os.environ.items() if k not in ("API_KEY", "APARTMENT_ID", "CONNECTOR", "DATA_DIR")}
    env.update(APARTMENT_ID="apt-prova-01", CONNECTOR="simulated", API_KEY=KEY, DATA_DIR=str(blocker / "dati"))
    out = subprocess.run([sys.executable, "-m", "engine"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 2 and "Traceback" not in out.stdout + out.stderr
    line = json.loads(out.stdout.strip().splitlines()[-1])
    assert line["msg"] == "invalid configuration" and "DATA_DIR" in line["problems"][0]


# ---- connector loading ---------------------------------------------------------------------------------------------
def test_unknown_connector():
    with pytest.raises(StartupError) as exc:
        load_connector(config(CONNECTOR="nessuno"))
    assert exc.value.msg == "unknown connector"


def test_connector_api_version_mismatch(monkeypatch):
    class Old(SimulatedConnector):
        api_version = "0"
    module = types.ModuleType("engine.connector.vecchio")
    module.make_connector = lambda cfg: Old()
    monkeypatch.setitem(sys.modules, "engine.connector.vecchio", module)
    with pytest.raises(StartupError) as exc:
        load_connector(config(CONNECTOR="vecchio"))
    assert exc.value.msg == "connector API version mismatch"
    assert (exc.value.fields["engine_version"], exc.value.fields["connector_version"]) == ("1", "0")


def broken_connector(monkeypatch, message):
    def make_connector(cfg):
        raise ValueError(message)
    module = types.ModuleType("engine.connector.rotto")
    module.make_connector = make_connector
    monkeypatch.setitem(sys.modules, "engine.connector.rotto", module)


def test_connector_setup_failure_stops_the_engine_without_secrets(monkeypatch):
    """A broken catalog (make_connector raises) is a StartupError: one stable msg, the error in a field, and no
    secret value of the environment in it even if the connector's message carries one."""
    broken_connector(monkeypatch, f"catalog.yaml line 3: unknown device; token={'SEGRETO-0123456789'} key={KEY}")
    with pytest.raises(StartupError) as exc:
        load_connector(config(CONNECTOR="rotto", SHELLY_TOKEN="SEGRETO-0123456789"))
    assert exc.value.msg == "connector setup failed"
    assert exc.value.fields["error_type"] == "ValueError" and "catalog.yaml line 3" in exc.value.fields["error"]
    assert "SEGRETO" not in exc.value.fields["error"] and KEY not in exc.value.fields["error"]


def test_main_exits_3_with_a_log_line(monkeypatch, capsys, tmp_path):
    from engine.__main__ import main
    broken_connector(monkeypatch, "catalog.yaml: missing")
    for name, value in {**ENV, "CONNECTOR": "rotto", "MOCK_TIME_SCALE": "1", "DATA_DIR": str(tmp_path)}.items():
        monkeypatch.setenv(name, value)                             # main() sets MOCK_TIME_SCALE: restored after
    monkeypatch.setattr(log, "_apartment_id", None)
    monkeypatch.setattr(log.logger, "handlers", [])                 # a fresh handler on the captured stdout
    assert main() == 3
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (line["msg"], line["connector"], line["apartment_id"]) == ("connector setup failed", "rotto", "apt-prova-01")


# ---- the contract at /api/v1 ---------------------------------------------------------------------------------------
def test_simulated_service(tmp_path):
    with TestClient(create_engine_app(config(DATA_DIR=str(tmp_path)))) as client:
        version = client.get("/api/v1/version").json()
        assert version["implementation"] == IMPLEMENTATION and "ask" in version["features"]
        assert client.get("/api/v1/devices").status_code == 401
        assert client.get("/api/v1/devices", headers={"X-API-Key": KEY}).status_code == 400
        assert client.get("/apt-prova-01/api/v1/devices", headers=HEADERS).status_code == 404   # no prefix any more
        devices = client.get("/api/v1/devices", headers=HEADERS).json()
        assert devices["apartment_id"] == "apt-prova-01" and len(devices["devices"]) == 5
        assert client.post("/api/v1/_test/state", headers=HEADERS,
                           json={"device_id": "dev-finestra-camera", "capability": "contact",
                                 "state": {"open": True}}).status_code == 204
        health = client.get("/api/v1/health").json()
        assert health["implementation"]["name"] == "domhouse-engine" and health["model_provider"]["provider"] == "mock-keywords"


def test_real_mode_has_no_test_hooks_and_no_ask(tmp_path):
    cfg = config(CONNECTOR="prova", DATA_DIR=str(tmp_path))          # any connector but the simulated one
    with TestClient(create_engine_app(cfg, connector=SimulatedConnector())) as client:
        assert "ask" not in client.get("/api/v1/version").json()["features"]
        assert client.post("/api/v1/_test/state", headers=HEADERS, json={"trigger": "approval"}).status_code == 404
        assert client.post("/api/v1/ask", headers=HEADERS, json={"text": "spegni"}).status_code == 501
        assert client.get("/api/v1/health").json()["model_provider"] == {"status": "unknown", "provider": "none"}
        assert client.get("/api/v1/approvals", headers=HEADERS).json() == {"items": []}
        assert client.get("/api/v1/apartment", headers=HEADERS).json()["current_booking_id"] is None   # no demo history


# ---- what reaches the app ------------------------------------------------------------------------------------------
class CatalogConnector:
    """A connector as a real one starts: a catalog with few fields, then changes. Commands follow `behaviour`."""
    api_version = "1"

    def __init__(self, behaviour="confirm", delay=0.0):
        self.behaviour, self.delay = behaviour, delay
        self.running = self.most_running = 0
        self.asked = []
        now = datetime.now(UTC)
        self._devices = [
            DeviceInfo("dev-presa", "Presa", "camera", True, now,
                       {"switch": {}, "power_meter": {"watts": 0, "energy_total_wh": 1000}, "lampeggio": {"x": 1}}),
            DeviceInfo("dev-caldaia", "Caldaia", "camera", True, now, {"heating": {"setpoint_min": 7, "setpoint_max": 23}},
                       {"sensor_device_id": "dev-presa"}),
        ]

    async def start(self):
        pass

    async def stop(self):
        pass

    def rooms(self):
        return [Room("camera", "Camera")]

    def devices(self):
        return list(self._devices)

    def status(self):
        from engine.connector.interface import ConnectorStatus
        return ConnectorStatus(True, 2, None)

    async def changes(self):
        await asyncio.Event().wait()
        yield  # pragma: no cover

    async def execute(self, cmd, on_progress):
        self.asked.append(cmd)
        self.running += 1
        self.most_running = max(self.most_running, self.running)
        try:
            on_progress("sent")
            if self.behaviour == "hang":
                await asyncio.sleep(3600)
            await asyncio.sleep(self.delay)
            if self.behaviour == "deliver":
                return CommandResult("delivered")
            return CommandResult("confirmed", state=dict(cmd.target))
        finally:
            self.running -= 1


def test_catalog_and_energy_as_the_contract_wants():
    engine = core.ApartmentEngine("apt-prova-01", CatalogConnector(), seed=False)
    presa = engine.devices["dev-presa"]["capabilities"]
    assert set(presa) == {"switch", "power_meter"}                    # unknown capability left out
    assert presa["switch"] == {"on": False} and presa["power_meter"] == {"watts": 0, "kwh_today": 0}
    assert engine.devices["dev-caldaia"]["capabilities"]["heating"] == {"setpoint_min": 7, "setpoint_max": 23,
                                                                        "on": False, "setpoint": 8}
    assert "links" not in engine.devices["dev-caldaia"]
    t0 = datetime.now(UTC)
    for wh, kwh in ((1500, 0.5), (1600, 0.6), (200, 0.8)):              # 200: the device restarted its counter
        engine._apply_change(StateChange("dev-presa", "state", t0, capability="power_meter",
                                         state={"watts": 50, "energy_total_wh": wh}))
        assert engine.devices["dev-presa"]["capabilities"]["power_meter"] == {"watts": 50, "kwh_today": kwh}
    tomorrow = t0 + timedelta(days=1)
    engine._apply_change(StateChange("dev-presa", "state", tomorrow, capability="power_meter",
                                     state={"watts": 50, "energy_total_wh": 300}))
    # a new day: only what was used since the last reading (300 - 200 Wh)
    assert engine.devices["dev-presa"]["capabilities"]["power_meter"]["kwh_today"] == 0.1


def run_commands(connector, *bodies, timeout=12.0):
    async def main():
        engine = core.ApartmentEngine("apt-prova-01", connector, seed=False)
        engine.ensure_started()
        try:
            for device_id, body in bodies:
                engine.create_command(device_id, body, "prova@hqe.it", CORR)
            end = asyncio.get_running_loop().time() + timeout
            while any(c["status"] not in core.FINAL for c in engine.commands.values()):
                assert asyncio.get_running_loop().time() < end, engine.commands
                await asyncio.sleep(0.02)
            return engine
        finally:
            for task in [engine.loop_task, engine.consumer_task, *engine.tasks]:
                if task is not None:
                    task.cancel()
    return asyncio.run(main())


def test_one_command_at_a_time_per_device():
    conn = CatalogConnector(delay=0.2)
    on, off = {"capability": "switch", "action": "turn_on"}, {"capability": "switch", "action": "turn_off"}
    engine = run_commands(conn, ("dev-presa", on), ("dev-presa", off))
    assert conn.most_running == 1 and [c.target for c in conn.asked] == [{"on": True}, {"on": False}]
    assert [c["status"] for c in engine.commands.values()] == ["acked", "acked"]
    assert engine.devices["dev-presa"]["capabilities"]["switch"] == {"on": False}


def test_deadline_gives_timeout(monkeypatch):
    monkeypatch.setattr(core, "COMMAND_DEADLINE_S", 0.3)
    engine = run_commands(CatalogConnector("hang"), ("dev-presa", {"capability": "switch", "action": "turn_on"}))
    cmd = next(iter(engine.commands.values()))
    assert (cmd["status"], cmd["reason"]) == ("timeout", "no_confirmation")
    assert engine.decisions[-1]["outcome"] == "failed"


def test_delivered_shows_the_state_requested():
    body = {"capability": "heating", "action": "set_heating", "params": {"on": True, "setpoint": 19}}
    conn = CatalogConnector("deliver")
    engine = run_commands(conn, ("dev-caldaia", body))
    assert conn.asked[0].target == {"on": True}
    assert next(iter(engine.commands.values()))["status"] == "acked"
    assert engine.devices["dev-caldaia"]["capabilities"]["heating"]["setpoint"] == 19


# ---- the log -------------------------------------------------------------------------------------------------------
def test_log_line_and_no_secrets():
    log.setup_logging("apt-prova-01")
    record = logging.LogRecord("engine", logging.INFO, __file__, 1, "command sent", None, None)
    record.fields = {"correlation_id": CORR, "command_id": "cmd-1", "device_id": "dev-presa", "api_key": KEY,
                     "shelly_token": "t", "password": "p"}
    line = json.loads(log.JsonFormatter().format(record))
    assert (line["level"], line["msg"], line["apartment_id"], line["device_id"]) == \
        ("info", "command sent", "apt-prova-01", "dev-presa")
    assert line["ts"].endswith("Z") and KEY not in json.dumps(line)
    assert line["api_key"] == line["shelly_token"] == line["password"] == "[redacted]"

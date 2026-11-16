"""E-35 (16 November 2026, prova 4 dal vivo, risposta 1135): a Plug unplugged a few seconds before «Accendi», before the
broker noticed, so the command left; Switch.Set got no answer and the connector closed it with failed/internal_error,
detail «transport timeout». The app said «errore interno» and the decision «Errore interno del collegamento». A device
that does not answer is now device_offline for the app, with its own decision, distinct from «andato offline durante
la verifica»; the connector's own reason and detail stay in the log. Provisional: the engine reads the connector's
detail until the connector says device_offline itself (connector-v2 §7.2, question to Youssouf).

Run: python -m pytest engine/tests/test_command_no_answer.py -q
"""
import asyncio
from datetime import UTC, datetime

from engine import core
from engine import log as logs
from engine.connector.interface import CommandResult, ConnectorStatus, DeviceInfo, Room

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"


class OneSocket:
    """One socket online; every command ends with the result given."""
    api_version = "1"

    def __init__(self, result: CommandResult):
        self.result = result

    async def start(self):
        pass

    async def stop(self):
        pass

    def rooms(self):
        return [Room("camera", "Camera")]

    def devices(self):
        return [DeviceInfo("dev-presa", "Presa", "camera", True, datetime.now(UTC), {"switch": {"on": False}})]

    def status(self):
        return ConnectorStatus(True, 1, None)

    async def changes(self):
        await asyncio.Event().wait()
        yield  # pragma: no cover

    async def execute(self, cmd, on_progress):
        on_progress("sent")
        return self.result


def run(result: CommandResult, monkeypatch) -> tuple[dict, dict, list[dict]]:
    warned = []
    monkeypatch.setattr(logs, "warn", lambda message, **fields: warned.append({"message": message, **fields}))

    async def main():
        engine = core.ApartmentEngine("apt-prova-01", OneSocket(result), seed=False)
        engine.ensure_started()
        cmd = engine.create_command("dev-presa", {"capability": "switch", "action": "turn_on"}, ACTOR, CORR)
        for _ in range(250):
            if engine.commands[cmd["command_id"]]["status"] in ("acked", "failed", "timeout"):
                break
            await asyncio.sleep(0.02)
        for task in [engine.loop_task, engine.consumer_task, *engine.tasks]:
            if task is not None:
                task.cancel()
        final = engine.commands[cmd["command_id"]]
        decision = next(d for d in reversed(engine.decisions) if d.get("command_id") == cmd["command_id"])
        return final, decision
    final, decision = asyncio.run(main())
    return final, decision, [w for w in warned if w["message"] == "command failed"]


def test_a_device_that_does_not_answer_is_offline_for_the_app_and_says_what_to_check(monkeypatch):
    final, decision, warned = run(CommandResult("failed", "internal_error", detail="transport timeout"), monkeypatch)
    assert (final["status"], final["reason"]) == ("failed", "device_offline")
    assert (decision["outcome"], decision["reasoning"]) == (
        "failed", "Il dispositivo non ha risposto: riprova, e se succede ancora controlla che sia acceso e "
        "collegato")
    # what the connector said stays in the log: a broker that is down is still told apart from an unplugged socket
    assert [(w["reason"], w["detail"]) for w in warned] == [("internal_error", "transport timeout")]


def test_a_real_internal_error_stays_internal(monkeypatch):
    final, decision, _ = run(CommandResult("failed", "internal_error", detail="RuntimeError"), monkeypatch)
    assert (final["status"], final["reason"]) == ("failed", "internal_error")
    assert decision["reasoning"] == "Errore interno del collegamento"


def test_offline_during_the_check_keeps_its_own_words(monkeypatch):
    final, decision, _ = run(CommandResult("failed", "device_offline", detail="device offline"), monkeypatch)
    assert (final["status"], final["reason"]) == ("failed", "device_offline")
    assert decision["reasoning"] == "Il dispositivo è andato offline durante la verifica"

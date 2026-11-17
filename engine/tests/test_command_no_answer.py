"""E-35 (16 November 2026, prova 4 dal vivo, risposta 1135): a Plug unplugged a few seconds before «Accendi», before the
broker noticed, so the command left; Switch.Set got no answer. The app said «errore interno». A device that does not
answer is device_offline for the app, with its own decision, distinct from «andato offline durante la verifica»; the
connector's own reason and detail stay in the log.

Since PR #15 (17 November) the Shelly connector says it itself: failed/device_offline with a detail ending in
DETAIL_TRANSPORT_TIMEOUT. The engine does not import the connector's constants (it knows no connector): it reads the
text. These are junction tests: the outcome comes from the real translate.error_result, so if the connector's words
change, the engine's words go red here.

Run: python -m pytest engine/tests/test_command_no_answer.py -q
"""
import asyncio
from datetime import UTC, datetime

import pytest

from engine import core
from engine import log as logs
from engine.connector.interface import CommandResult, ConnectorStatus, DeviceInfo, Room
from engine.connector.shelly.command import READ_BACK_PREFIX
from engine.connector.shelly.transport.base import TransportOffline, TransportTimeout
from engine.connector.shelly.translate import error_result

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


NO_ANSWER = "Il dispositivo non ha risposto: riprova, e se succede ancora controlla che sia acceso e collegato"


@pytest.mark.parametrize("prefix", ["", READ_BACK_PREFIX])        # the set without answer, the read back twice
def test_a_device_that_does_not_answer_is_offline_for_the_app_and_says_what_to_check(prefix, monkeypatch):
    result = error_result(TransportTimeout(), prefix=prefix)        # the Shelly connector's real outcome
    final, decision, warned = run(result, monkeypatch)
    assert (final["status"], final["reason"]) == ("failed", "device_offline")
    assert (decision["outcome"], decision["reasoning"]) == ("failed", NO_ANSWER)
    # what the connector said stays in the log: a broker that is down is still told apart from an unplugged socket
    assert [(w["reason"], w["detail"]) for w in warned] == [(result.reason, result.detail)]


@pytest.mark.parametrize("prefix", ["", READ_BACK_PREFIX])
def test_offline_during_the_check_keeps_its_own_words(prefix, monkeypatch):
    final, decision, _ = run(error_result(TransportOffline(), prefix=prefix), monkeypatch)
    assert (final["status"], final["reason"]) == ("failed", "device_offline")
    assert decision["reasoning"] == "Il dispositivo è andato offline durante la verifica"


@pytest.mark.parametrize("detail", ["RuntimeError", "transport timeout", "read back failed: transport timeout"])
def test_an_internal_error_stays_internal_whatever_its_detail(detail, monkeypatch):
    """17 November: the provisional half of E-35 is gone. Before PR #15 the Shelly connector closed a request without
    answer as internal_error «transport timeout» and the engine translated it; now no connector does, and an internal
    error is the connector's own fault, whatever its words."""
    final, decision, _ = run(CommandResult("failed", "internal_error", detail=detail), monkeypatch)
    assert (final["status"], final["reason"]) == ("failed", "internal_error")
    assert decision["reasoning"] == "Errore interno del collegamento"

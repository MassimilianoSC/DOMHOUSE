"""One command to one Shelly device over the Transport (connector.md §2.4, §2.5): set, then read back, before the
deadline.

Transport-independent: it only uses the Protocol in transport/base.py, so ShellyConnector.execute (connector.py, not
written yet) will call it whatever transport is in use, and the tests run it on tests/fake_transport.py.

The sequence:
  1. a device the transport does not have in connected() fails at once with failed/device_offline: no RPC, no "sent"
     (§2.5: no queue for offline devices);
  2. on_progress("sent") as the command is handed to the transport, BEFORE awaiting it (§2.5: «appena il comando è
     consegnato al trasporto»), then the set RPC (Switch.Set). An error here is the command's outcome (error_result,
     no prefix), also after "sent" was reported;
  3. on_progress("verifying"), then the read back (Switch.GetStatus). If it times out or the device is offline, it
     is tried ONE more time, within the deadline: commands are states to reach, so a repeated read is harmless
     (§2.5). If the retry fails too, or the read back gets an RPC error, the outcome is error_result with detail
     "read back failed: ...", so the logs tell a failed read back from a failed command;
  4. confirmed_result on what was read back: reached -> confirmed, not reached -> failed/device_rejected.
Every RPC gets the smaller of rpc_timeout_s and the time left before the deadline; nothing is tried after it.
asyncio.CancelledError is never caught: the engine cancels a command past its deadline and nothing is left half done,
because no state is kept here.
"""
from collections.abc import Callable
from datetime import UTC, datetime

from engine.connector.interface import CommandResult

from .translate import ModelProfile, command_call, confirmed_result, error_result, read_back_call
from .transport.base import Transport, TransportOffline, TransportTimeout

RPC_TIMEOUT_S = 3.0          # one RPC; a command has about 9 s in all (ConnectorCommand.deadline)
READ_BACK_ATTEMPTS = 2       # the read back and one retry
READ_BACK_PREFIX = "read back failed: "


def utcnow() -> datetime:
    return datetime.now(UTC)


def _left_s(deadline: datetime, now: Callable[[], datetime]) -> float:
    return (deadline - now()).total_seconds()


async def run_command(transport: Transport, shelly_id: str, profile: ModelProfile, capability: str, target: dict, *,
                      deadline: datetime, on_progress: Callable[[str], None], channel: int = 0,
                      rpc_timeout_s: float = RPC_TIMEOUT_S, now: Callable[[], datetime] = utcnow) -> CommandResult:
    try:
        method, params = command_call(profile, capability, target, channel)
    except ValueError:
        return CommandResult(outcome="failed", reason="internal_error", detail="target not valid for this device")

    left = _left_s(deadline, now)
    if left <= 0:
        return CommandResult(outcome="failed", reason="internal_error", detail="deadline already passed")
    if shelly_id not in transport.connected():
        return error_result(TransportOffline())
    on_progress("sent")
    try:
        await transport.call(shelly_id, method, params, min(rpc_timeout_s, left))
    except Exception as exc:          # never BaseException: CancelledError goes to the engine
        return error_result(exc)
    on_progress("verifying")

    method, params = read_back_call(profile, capability, channel)
    last_error: Exception = TransportTimeout()     # what remains if the deadline leaves no time to read back
    for _ in range(READ_BACK_ATTEMPTS):
        left = _left_s(deadline, now)
        if left <= 0:
            break
        try:
            read_back = await transport.call(shelly_id, method, params, min(rpc_timeout_s, left))
        except (TransportTimeout, TransportOffline) as exc:
            last_error = exc
            continue
        except Exception as exc:
            return error_result(exc, prefix=READ_BACK_PREFIX)
        return confirmed_result(profile, capability, target, read_back)
    return error_result(last_error, prefix=READ_BACK_PREFIX)

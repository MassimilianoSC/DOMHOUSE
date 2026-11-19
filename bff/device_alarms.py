"""Tool A, package A3 (docs/proposta-a3-server.md §8.4; answer 1175; review point 3, N2): a revocation or a new
password not applied must be seen without anyone opening the page.

- not_applied(): ONCE per order (a mark on the device, atomic): an «agent alarm» log line, which the alarm on the
  server's logs turns into an email (scripts/agent/allarmi/server-allarme.json); for a revocation also the system's
  row in the activity log (answer 1175: the row only for a revocation).
- after_result(): called by the receiver when an aggiorna_broker closes without success (the push of Pub/Sub wakes
  the instance also with minScale 0, the staging).
- round_once(): the reserve, in the existing hourly loop (production has minScale 1): every device whose order is
  not applied, also the ones with no answer at all after 20 minutes. A VM that answers nothing is also told by the
  alarm on the age of the unread orders (scripts/agent/allarmi/ordini-non-letti.json).
"""
from __future__ import annotations

from datetime import UTC, datetime

from . import audit
from . import device_credentials as dc
from .logs import warn
from .repository import get_repository

CODES = {"revoca": "revoca_non_applicata", "rigenera": "rigenera_non_applicata"}


async def not_applied(apt, device_id: str, azione: str | None, seq: int | None, op_id: str | None) -> bool:
    """True when this call wrote the alarm (and, for a revocation, the row); False when already done or not needed."""
    if azione not in CODES or not isinstance(seq, int):
        return False
    if not await get_repository().mark_device_alerted(apt.apartment_id, device_id, seq):
        return False
    warn(f"agent alarm codice={CODES[azione]}", apartment_id=apt.apartment_id, device_id=device_id, seq=seq,
         op_id=op_id)
    if azione == "revoca":
        await audit.record("device_credential_revoke_not_applied", audit.SYSTEM, apt.tenant_id,
                           audit.apartment_target(apt.apartment_id, apt.name), device_id=device_id, seq=seq,
                           op_id=op_id)
    return True


async def _check(apt, now: datetime, only_seq: int | None = None) -> int:
    docs, ultima, ops = await get_repository().device_credentials_view(apt.apartment_id)
    written = 0
    for doc in docs:
        if only_seq is not None and doc.get("pending_seq") != only_seq:
            continue
        if dc.state_of(doc, ops.get(doc.get("op_id")), ultima, now) != "non_applicato":
            continue
        written += await not_applied(apt, doc["device_id"], doc.get("azione"), doc.get("pending_seq"), doc.get("op_id"))
    return written


async def after_result(op_id: str) -> int:
    op = await get_repository().get_agent_op(op_id)
    if op is None or op.operazione != "aggiorna_broker" or op.stato == "riuscito" or op.apartment_id is None:
        return 0
    apt = await get_repository().get_apartment(op.apartment_id)
    return 0 if apt is None else await _check(apt, datetime.now(UTC), only_seq=op.seq)


async def round_once(now: datetime | None = None) -> int:
    written = 0
    for apt in await get_repository().list_apartments():
        try:
            written += await _check(apt, now or datetime.now(UTC))
        except Exception as exc:                     # noqa: BLE001 - one apartment's failure, the others go on
            warn("device credentials round failed", apartment_id=apt.apartment_id, error=type(exc).__name__)
    return written

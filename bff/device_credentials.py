"""Tool A, package A3 (docs/proposta-a3-server.md): the devices' credentials, the logic without input or output.

- The password is born here (secrets.token_urlsafe(24), 192 bits), is shown once in the answer of «Registra» or
  «Rigenera» and is never kept: Firestore gets only its fingerprint, Mosquitto's «$7$» (PBKDF2-SHA512, the format of
  scripts/broker_accounts.py: a test keeps the two equal).
- A device's stored document has `stato_salvato` (attivo, revocato), the action waiting for confirmation (`azione`),
  the order that carries it (`pending_seq`, `op_id`) and `version`. The state shown is COMPUTED when it is read
  (§4.1): from the apartment's last successful `aggiorna_broker` (`ultima_seq_riuscita`, §4.2, N1) and from the
  operation of the device's own order. So the 20 minutes need no timer and a result never writes on the devices.
- The actions allowed per state (§4.3) are a table: a «no» always has its code.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import UTC, datetime, timedelta

MAX_WAIT = timedelta(minutes=20)
MAX_DEVICES = 200
DEVICE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
RESERVED_DEVICE = "connector"            # <apt>.connector is the connector's user (scripts/broker_accounts.py)
ITERATIONS = 1000                        # the same as scripts/broker_accounts.py (Mosquitto's own default)
ACTIONS = ("registra", "rigenera", "revoca", "riprova")
STATES = ("in_attesa", "pronto", "cambio_in_corso", "revoca_in_corso", "revocato", "non_applicato")
IN_FLIGHT = {"registra": "in_attesa", "rigenera": "cambio_in_corso", "revoca": "revoca_in_corso"}
CONFIRMED = {"registra": "pronto", "rigenera": "pronto", "revoca": "revocato"}

MESSAGES = {
    "invalid_device_id": "Il codice non è valido: solo lettere minuscole, cifre e trattini, fino a 64 caratteri.",
    "invalid_version": "Richiesta non valida: ricarica la pagina.",
    "not_found": "Dispositivo non registrato.",
    "already_registered": "Questo dispositivo ha già una password. Se è persa, usa «Rigenera».",
    "version_changed": "Qualcuno ha appena cambiato questo dispositivo: ricarica l'elenco.",
    "operation_in_progress": "C'è già un'operazione in corso su questo dispositivo: aspetta che finisca.",
    "invalid_state": "Con lo stato di adesso questa azione non si può fare: ricarica l'elenco.",
    "too_many_devices": "Questo appartamento ha già 200 dispositivi registrati: è il massimo.",
}
STATUS = {"invalid_device_id": 422, "invalid_version": 422, "not_found": 404, "already_registered": 409,
          "version_changed": 409, "operation_in_progress": 409, "invalid_state": 409, "too_many_devices": 409}

_OK, _BUSY, _BAD, _TAKEN = None, "operation_in_progress", "invalid_state", "already_registered"
# §4.3, on the COMPUTED state (N10): action -> what each state answers (None = allowed)
TABLE = {
    "in_attesa":       {"rigenera": _OK, "revoca": _OK, "riprova": _BAD, "registra": _TAKEN},
    "pronto":          {"rigenera": _OK, "revoca": _OK, "riprova": _BAD, "registra": _TAKEN},
    "cambio_in_corso": {"rigenera": _BUSY, "revoca": _OK, "riprova": _BUSY, "registra": _TAKEN},
    "revoca_in_corso": {"rigenera": _BUSY, "revoca": _BUSY, "riprova": _BUSY, "registra": _BUSY},
    "revocato":        {"rigenera": _BAD, "revoca": _BAD, "riprova": _BAD, "registra": _OK},
    "non_applicato":   {"rigenera": _OK, "revoca": _OK, "riprova": _OK, "registra": _TAKEN},
    # a revocation not applied closes only with «Riprova»: «Rigenera» would bring the device back (review, point 10)
    "non_applicato_revoca": {"rigenera": _BAD, "revoca": _BAD, "riprova": _OK, "registra": _TAKEN},
}


class DeviceError(Exception):
    def __init__(self, error: str):
        super().__init__(MESSAGES[error])
        self.error, self.status, self.message = error, STATUS[error], MESSAGES[error]


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ---- the password and its fingerprint ------------------------------------------------------------------------------
def new_password() -> str:
    return secrets.token_urlsafe(24)                     # 32 characters, no space and no «:» (broker_accounts rule)


def _pbkdf2(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, iterations, 64)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(12)
    return f"$7${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(_pbkdf2(password, salt, ITERATIONS)).decode()}"


def hash_matches(stored: str, password: str) -> bool:
    match = re.fullmatch(r"\$7\$(\d+)\$([^$]+)\$([^$]+)", stored or "")
    if not match:
        return False
    try:
        salt, expected = base64.b64decode(match[2], validate=True), base64.b64decode(match[3], validate=True)
    except ValueError:
        return False
    return hmac.compare_digest(_pbkdf2(password, salt, int(match[1])), expected)


def check_device_id(device_id) -> str:
    """§5.1: the rule, never converted (an uppercase id is refused, not lowered); «connector» is the connector's."""
    if not isinstance(device_id, str) or not DEVICE_ID_RE.fullmatch(device_id) or device_id == RESERVED_DEVICE:
        raise DeviceError("invalid_device_id")
    return device_id


def check_version(version) -> int:
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise DeviceError("invalid_version")
    return version


# ---- the state, computed when read ---------------------------------------------------------------------------------
def _age(op, now: datetime) -> timedelta:
    created = getattr(op, "creato_at", None) or ""
    try:
        return now - datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        return MAX_WAIT * 2


def state_of(doc: dict | None, op, ultima: int, now: datetime | None = None) -> str | None:
    """§4.1 and §4.2: None for a device never registered. `op` is the operation of the device's order (op_id),
    `ultima` the apartment's last successful aggiorna_broker."""
    if doc is None:
        return None
    azione = doc.get("azione")
    if not azione:
        return "revocato" if doc.get("stato_salvato") == "revocato" else "pronto"
    pending = doc.get("pending_seq")
    if isinstance(pending, int) and pending <= (ultima or 0):
        return CONFIRMED[azione]
    if op is not None and op.stato == "inviato" and _age(op, now or datetime.now(UTC)) <= MAX_WAIT:
        return IN_FLIGHT[azione]
    if op is not None and op.stato == "riuscito" and op.operazione == "aggiorna_broker":
        return CONFIRMED[azione]                            # ultima is updated in the same transaction (§4.2)
    return "non_applicato"


def shown_action(doc: dict | None, state: str | None) -> str | None:
    """`azione` in the answer: the action waiting for confirmation, null when nothing waits."""
    if doc is None or state in (None, "pronto", "revocato"):
        return None
    return doc.get("azione")


def check_action(action: str, state: str | None, doc: dict | None) -> None:
    if state is None:
        if action == "registra":
            return
        raise DeviceError("not_found")
    row = "non_applicato_revoca" if state == "non_applicato" and (doc or {}).get("azione") == "revoca" else state
    answer = TABLE[row][action]
    if answer is not None:
        raise DeviceError(answer)


def decide(action: str, device_id: str, version: int | None, impronta: str | None, uid: str,
           now: datetime | None = None):
    """The change of one device, for the repository's transaction: (current document, its operation, ultima) -> the
    new document (pending_seq and op_id are the repository's). Raises DeviceError. Pure: Firestore may call it again."""
    if action not in ACTIONS:
        raise ValueError(action)

    def change(doc: dict | None, op, ultima: int) -> dict:
        moment = now or datetime.now(UTC)
        if doc is not None and action != "registra" and doc.get("version") != version:
            raise DeviceError("version_changed")
        state = state_of(doc, op, ultima, moment)
        check_action(action, state, doc)
        new = dict(doc or {"device_id": device_id, "version": 0})
        new.pop("migrato", None)                 # code review, point 5: changed by the app, no longer lab-01's copy
        new["version"] = int(new.get("version") or 0) + 1
        new["updated_at"] = moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        new["updated_by"] = uid
        if action in ("registra", "rigenera"):
            new.update(impronta=impronta, stato_salvato="attivo", azione=action, revoked_at=None)
        elif action == "revoca":
            new.update(impronta=None, stato_salvato="revocato", azione="revoca", revoked_at=new["updated_at"])
        # riprova: the action waiting stays (§11, point 1); only version, the order and the times change
        return new
    return change


def broker_list(docs: list[dict]) -> list[dict]:
    """The complete list of an apartment for aggiorna_broker: every living device, by id. Raises too_many_devices."""
    living = sorted((d for d in docs if d.get("stato_salvato") == "attivo" and d.get("impronta")),
                    key=lambda d: d["device_id"])
    if len(living) > MAX_DEVICES:
        raise DeviceError("too_many_devices")
    return [{"id": d["device_id"], "impronta": d["impronta"]} for d in living]


def canonical(order: dict) -> bytes:
    """The order's canonical form (keys sorted, no spaces, UTF-8): what is signed and fingerprinted (§6.3)."""
    return json.dumps(order, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

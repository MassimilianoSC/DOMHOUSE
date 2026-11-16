"""Tool A, package A1 (docs/progetto-strumento-a-base.md §3, §4.2, §6): the server's side of the order receiver.

- send(): an order to the VM. The repository gives the apartment's sequence number and saves the operation as
  «inviato» in one transaction; then the order is published on this environment's orders topic (Pub/Sub, with the
  server's own identity: the staging server is the only publisher of that topic, §10.3), with the apartment as
  ordering key. The order carries the uid of who asked, never an email. A publish that fails leaves the operation
  «fallito: non_inviato».
- receive(): a result pushed by Pub/Sub. Accepted only with Google's signature for the exact address of this
  environment's route and its push account, with a verified email (§4.2); then only for an operation still «inviato»,
  of the same environment, apartment and operation, not older than 20 minutes (§6.8). Anything else is acknowledged
  and ignored, with a log line: Pub/Sub never retries it.
- view(): what the platform page shows; an operation «inviato» for more than 20 minutes becomes «fallito:
  tempo_scaduto», and a result that comes later is ignored.
The reason is always a code of a closed list, put into words here (MESSAGES).

A1 sends only «stato», from the platform managers' button «Prova l'agente». Disabled (503) while AGENT_AMBIENTE is
empty: production until the second VM (§5.4).
"""
from __future__ import annotations

import base64
import json
import re
import uuid
from datetime import UTC, datetime, timedelta

from .config import get_settings
from .logs import warn
from .repository import AgentOp, get_repository

MAX_WAIT = timedelta(minutes=20)
OUTCOMES = ("riuscito", "rifiutato", "scartato", "fallito")
# the agent's codes (scripts/agent/comune.py CODES; a test keeps them equal) and the server's own
CODES = (
    "ok", "troppo_grande", "json_non_valido", "campo_mancante", "campo_non_valido", "operazione_sconosciuta",
    "ambiente_diverso", "id_non_valido", "prefisso_sbagliato", "dev_escluso", "parametri_non_validi",
    "porta_fuori_fascia", "impronta_non_valida", "troppi_dispositivi", "catalogo_troppo_grande",
    "prod_non_ammesso", "seq_vecchia", "non_disponibile", "motore_assente", "chiamante_non_ammesso",
    "scaduto", "interrotto", "errore_interno",
    "non_inviato", "tempo_scaduto",
)
MESSAGES = {
    "ok": "Fatto",
    "troppo_grande": "L'ordine è troppo grande",
    "json_non_valido": "L'ordine non è leggibile",
    "campo_mancante": "All'ordine manca un campo",
    "campo_non_valido": "Un campo dell'ordine non è valido",
    "operazione_sconosciuta": "L'agente non conosce questa operazione",
    "ambiente_diverso": "L'ordine è di un altro ambiente",
    "id_non_valido": "Il nome dell'appartamento o del dispositivo non è valido",
    "prefisso_sbagliato": "Il nome dell'appartamento non è di questo ambiente",
    "dev_escluso": "L'appartamento dev non accetta questa operazione",
    "parametri_non_validi": "I dati dell'ordine non sono validi",
    "porta_fuori_fascia": "La porta non è nella fascia di questo ambiente",
    "impronta_non_valida": "Un'impronta di password non è valida",
    "troppi_dispositivi": "Troppi dispositivi in un ordine",
    "catalogo_troppo_grande": "L'elenco dei dispositivi è troppo grande",
    "prod_non_ammesso": "La VM condivisa non accetta ordini della produzione",
    "seq_vecchia": "Ordine più vecchio di uno già eseguito per questo appartamento",
    "non_disponibile": "Operazione non ancora disponibile",
    "motore_assente": "Il motore di questo appartamento non c'è sulla VM",
    "chiamante_non_ammesso": "Errore interno dell'agente (chiamante non ammesso)",
    "scaduto": "L'ordine è arrivato dopo più di 15 minuti e non è stato eseguito",
    "interrotto": "La VM si è riavviata durante l'operazione: riprova",
    "errore_interno": "Errore interno dell'agente: riprova",
    "non_inviato": "Non è stato possibile mandare l'ordine: riprova",
    "tempo_scaduto": "Nessuna risposta dall'agente entro 20 minuti: riprova",
}
STATE_MESSAGES = {"inviato": "Ordine inviato all'agente sulla VM, in attesa della risposta"}
# the ids (docs/progetto-strumento-a-base.md §2.1; scripts/agent/comune.py, a test keeps them equal)
STAGING_ID_RE = re.compile(r"^(lab|test)-[a-z0-9]([a-z0-9-]*[a-z0-9])?$")     # R15, the same as the VM's
PROD_ID_RE = re.compile(r"^a-[a-z0-9]{8}$")
DATA_KEYS_MAX = 20


def utcnow() -> datetime:
    return datetime.now(UTC)


class AgentError(Exception):
    def __init__(self, status: int, error: str, message: str, op: AgentOp | None = None):
        super().__init__(message)
        self.status, self.error, self.message, self.op = status, error, message, op


def configured() -> bool:
    s = get_settings()
    return bool(s.agent_ambiente and s.agent_orders_topic)


def apartment_allowed(apartment_id: str, ambiente: str) -> bool:
    """§2.1 and §5: the same rule the agent applies; «dev» for «stato» only (the only operation sent in A1)."""
    if not isinstance(apartment_id, str):
        return False
    if apartment_id == "dev":
        return True
    if ambiente == "prod":
        return bool(PROD_ID_RE.fullmatch(apartment_id))
    return len(apartment_id) <= 64 and bool(STAGING_ID_RE.fullmatch(apartment_id)) \
        and not apartment_id.endswith("-devices")


# ---- Google Cloud: replaced in the tests ----------------------------------------------------------------------------
def publish(topic: str, body: bytes, ordering_key: str | None) -> None:
    """Pub/Sub's REST publish with the server's own identity (Cloud Run's service account)."""
    import requests
    from .ai_gateway import _token
    message = {"data": base64.b64encode(body).decode("ascii")}
    if ordering_key:
        message["orderingKey"] = ordering_key
    r = requests.post(f"https://pubsub.googleapis.com/v1/{topic}:publish", json={"messages": [message]},
                      headers={"Authorization": f"Bearer {_token()}"}, timeout=10)
    if r.status_code != 200:
        raise OSError(f"pubsub publish {r.status_code}")


def verify_push_token(token: str, audience: str) -> dict:
    """Google's signature and the audience; raises ValueError when they do not hold."""
    import google.auth.transport.requests
    from google.oauth2 import id_token
    return id_token.verify_oauth2_token(token, google.auth.transport.requests.Request(), audience=audience)


# ---- the operations ---------------------------------------------------------------------------------------------
async def send(operazione: str, apartment_id: str | None, uid: str) -> AgentOp:
    s = get_settings()
    if not configured():
        raise AgentError(503, "agent_not_configured", "L'agente sulla VM non è configurato in questo ambiente")
    if operazione != "stato":
        raise AgentError(422, "operation_not_available", "Operazione non disponibile")
    if not apartment_allowed(apartment_id, s.agent_ambiente):
        raise AgentError(422, "invalid_apartment", "Nome dell'appartamento non valido per questo ambiente")
    op = await get_repository().create_agent_op(AgentOp(
        op_id=str(uuid.uuid4()), operazione=operazione, apartment_id=apartment_id, ambiente=s.agent_ambiente,
        richiesto_da=uid, creato_at=utcnow().isoformat(timespec="milliseconds").replace("+00:00", "Z")))
    order = {"op_id": op.op_id, "operazione": op.operazione, "apartment_id": op.apartment_id, "seq": op.seq,
             "parametri": {}, "ambiente": op.ambiente, "richiesto_da": op.richiesto_da}
    try:
        publish(s.agent_orders_topic, json.dumps(order).encode("utf-8"), op.apartment_id)
    except Exception as exc:                                     # noqa: BLE001 - any failure of the publish
        warn("agent order not published", op_id=op.op_id, error=type(exc).__name__)
        await get_repository().finish_agent_op(op.op_id, op.ambiente, op.apartment_id, op.operazione,
                                               {"stato": "fallito", "codice": "non_inviato"}, 10**9)
        raise AgentError(502, "agent_publish_failed", MESSAGES["non_inviato"],
                         await get_repository().get_agent_op(op.op_id)) from None
    warn("agent order sent", op_id=op.op_id, operazione=op.operazione, apartment_id=op.apartment_id, seq=op.seq)
    return op


def _too_old(op: AgentOp) -> bool:
    created = datetime.fromisoformat(op.creato_at.replace("Z", "+00:00"))
    return op.stato == "inviato" and utcnow() - created > MAX_WAIT


async def _expire(op: AgentOp) -> AgentOp:
    if _too_old(op):
        await get_repository().finish_agent_op(op.op_id, op.ambiente, op.apartment_id, op.operazione,
                                               {"stato": "fallito", "codice": "tempo_scaduto"}, 10**9)
        op = await get_repository().get_agent_op(op.op_id) or op
    return op


async def view(op_id: str) -> dict | None:
    op = await get_repository().get_agent_op(op_id)
    if op is None:
        return None
    return describe(await _expire(op))


def describe(op: AgentOp) -> dict:
    return {"op_id": op.op_id, "operazione": op.operazione, "apartment_id": op.apartment_id, "seq": op.seq,
            "stato": op.stato, "codice": op.codice,
            "messaggio": MESSAGES.get(op.codice or "") or STATE_MESSAGES.get(op.stato, ""),
            "dati": op.dati, "creato_at": op.creato_at, "finito_at": op.finito_at}


def authorised(authorization: str | None) -> bool:
    """§4.2: Google's signature, aud = the exact address of this environment's route, email = its push account,
    email_verified."""
    s = get_settings()
    if not (s.agent_push_audience and s.agent_push_email) or not authorization or \
            not authorization.startswith("Bearer "):
        return False
    try:
        claims = verify_push_token(authorization[len("Bearer "):], s.agent_push_audience)
    except Exception:                                            # noqa: BLE001 - any failure of the check
        return False
    return claims.get("aud") == s.agent_push_audience and claims.get("email") == s.agent_push_email \
        and claims.get("email_verified") is True


async def receive(body) -> str:
    """A pushed result: what happened to it, for the log («chiuso» or why it was ignored)."""
    s = get_settings()
    try:
        data = base64.b64decode(body["message"]["data"], validate=True)
        result = json.loads(data.decode("utf-8"))
    except (KeyError, TypeError, ValueError, UnicodeDecodeError):
        return "illeggibile"
    if not isinstance(result, dict) or result.get("esito") not in OUTCOMES or result.get("codice") not in CODES \
            or result.get("ambiente") != s.agent_ambiente or not isinstance(result.get("op_id"), str):
        return "non_valido"
    dati = result.get("dati") if isinstance(result.get("dati"), dict) else {}
    dati = {k: v for k, v in list(dati.items())[:DATA_KEYS_MAX] if isinstance(k, str) and len(k) <= 40 and (
        isinstance(v, (int, float)) or v is None or (isinstance(v, str) and len(v) <= 200))}
    op = await get_repository().get_agent_op(result["op_id"])
    if op is not None and _too_old(op):
        await _expire(op)
        return "tardi"
    return await get_repository().finish_agent_op(
        result["op_id"], result["ambiente"], result.get("apartment_id"), result.get("operazione"),
        {"stato": result["esito"], "codice": result["codice"], "dati": dati}, MAX_WAIT.total_seconds())

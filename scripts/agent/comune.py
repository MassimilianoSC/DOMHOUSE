"""Tool A, package A1: the rules the two services of the order receiver share (docs/progetto-strumento-a-base.md §2.1,
§3, §5). Installed by root, read-only for everybody else. The reader (lettore.py, unprivileged) applies them to what
Pub/Sub gives it; the executor (esecutore.py, root) applies them AGAIN to what the reader passes, without trusting it.

Only the standard library: it runs on the VM's python3, outside any container.

An order is a JSON object of exactly these fields, at most MAX_ORDER_BYTES:
  op_id         a UUID, chosen by the server
  operazione    one of OPERATIONS
  apartment_id  the apartment (§2.1), null only for «capienza»
  seq           its sequence number for that apartment (>= 1), null only for «capienza»
  parametri     an object, exactly the parameters of the operation (none for most)
  ambiente      "staging" or "prod": must be the environment of the subscription it came from
  richiesto_da  the Firebase uid of who asked, never an email
Everything refused raises Refused with a code of CODES: the result says the code, never a text of ours or a script's.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass

OPERATIONS = ("capienza", "crea_motore", "aggiorna_motore", "aggiorna_broker", "applica_catalogo", "stato",
              "togli_motore")
# A1, A3, then A2 (crea_motore, togli_motore); the other two are refused «non_disponibile»
EXECUTED = {"stato", "capienza", "aggiorna_broker", "crea_motore", "togli_motore"}
ENVIRONMENTS = ("staging", "prod")
MAX_ORDER_BYTES = 128 * 1024
MAX_CATALOG_BYTES = 64 * 1024
MAX_DEVICES = 200
MAX_AGE_S = 15 * 60                       # §6.5: an order older than this (Pub/Sub's publish_time) is discarded
PORTS = {"staging": (8150, 8159), "prod": (8101, 8149)}       # §5.3
DEV = "dev"
DEV_ALLOWED = {"stato", "capienza"}

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
UID_RE = re.compile(r"^[A-Za-z0-9]{1,128}$")
# R15 (security review of A1): a whole word after the prefix, no trailing or doubled hyphen at its start; at most 64
STAGING_ID_RE = re.compile(r"^(lab|test)-[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
MAX_ID_LEN = 64
MAX_SEQ = 2**31 - 1        # R6
PROD_ID_RE = re.compile(r"^a-[a-z0-9]{8}$")
DEVICE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
HASH_RE = re.compile(r"^\$7\$[0-9]{3,6}\$[A-Za-z0-9+/]{16}\$[A-Za-z0-9+/]{86}==$")
IMAGE_RE = re.compile(r"^europe-west8-docker\.pkg\.dev/domotica-poc-511707/domotica/engine"
                      r"(:[0-9a-f]{7,40}|@sha256:[0-9a-f]{64})$")

OUTCOMES = ("riuscito", "rifiutato", "scartato", "fallito")
CODES = (
    "ok",
    # the order itself
    "troppo_grande", "json_non_valido", "campo_mancante", "campo_non_valido", "operazione_sconosciuta",
    "ambiente_diverso", "id_non_valido", "prefisso_sbagliato", "dev_escluso", "parametri_non_validi",
    "porta_fuori_fascia", "impronta_non_valida", "troppi_dispositivi", "catalogo_troppo_grande",
    # the executor's own rules
    "prod_non_ammesso", "seq_vecchia", "non_disponibile", "motore_assente", "chiamante_non_ammesso",
    # time and faults
    "scaduto", "interrotto", "errore_interno",
    # A3 §6.3: an order without the server's signature
    "firma_non_valida",
    # A2 (docs/proposta-a2.md §6.3): crea_motore and togli_motore
    "capienza_insufficiente", "staging_pieno", "porta_occupata", "immagine_non_approvata", "gia_esiste_diverso",
    "dati_presenti", "non_creato_da_agente", "segreto_illeggibile", "motore_non_sano", "broker_fallito",
    # A3 §6.1, §6.4: aggiorna_broker
    "appartamento_sconosciuto", "sync_fallito", "migrazione_non_fatta",
)
DATA_MAX_LEN = 200                        # a value of «dati»: a number or a short string

PRINTABLE_RE = re.compile(r"[ -~]*")
FIELDS = ("op_id", "operazione", "apartment_id", "seq", "parametri", "ambiente", "richiesto_da", "firmato_at", "firma")
# A3 §6.3 (review point 1, N5): the server signs every order with HMAC-SHA256 on its canonical form without «firma»;
# «firmato_at» (UTC) lets the executor check the 15 minutes by itself. The reader only checks the two fields' form: it
# has no key. The same canonical form, signature and fingerprint for the results (the «risultati» key).
FIRMA_RE = re.compile(r"^[0-9a-f]{64}$")
TIME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z$")
AHEAD_S = 2 * 60                          # an order signed in the future: at most the clocks' difference
KEY_RE = re.compile(r"^[0-9a-f]{64}$")    # a key: 32 bytes in hex, one per line


def canonical(obj: dict) -> bytes:
    """Keys sorted, no spaces, UTF-8 (bff/device_credentials.canonical is the same: a test keeps them equal)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _unsigned(obj: dict) -> dict:
    return {k: v for k, v in obj.items() if k != "firma"}


def signature(key: bytes, obj: dict) -> str:
    return hmac.new(key, canonical(_unsigned(obj)), hashlib.sha256).hexdigest()


def signed_by(keys, obj) -> bool:
    """True when obj's «firma» is the signature of one of the keys (compare_digest, review point 9)."""
    firma = obj.get("firma") if isinstance(obj, dict) else None
    if not isinstance(firma, str) or not FIRMA_RE.fullmatch(firma):
        return False
    found = False
    for key in keys:
        found |= hmac.compare_digest(signature(key, obj), firma)
    return found


def order_sha256(obj: dict) -> str:
    """The fingerprint of an order: SHA-256 of its canonical form without «firma»."""
    return hashlib.sha256(canonical(_unsigned(obj))).hexdigest()


class Refused(Exception):
    def __init__(self, code: str):
        assert code in CODES, code
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Order:
    op_id: str
    operazione: str
    apartment_id: str | None
    seq: int | None
    parametri: dict
    ambiente: str
    richiesto_da: str


def valid_image(image: str) -> bool:
    return isinstance(image, str) and IMAGE_RE.fullmatch(image) is not None


def _int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_apartment(apartment_id, ambiente: str, operazione: str) -> None:
    """§2.1 and §5.2: the id's rule, then the prefix of the environment; «dev» only for stato and capienza."""
    if not isinstance(apartment_id, str):
        raise Refused("id_non_valido")
    if apartment_id == DEV:
        if operazione not in DEV_ALLOWED:
            raise Refused("dev_escluso")
        return
    if apartment_id.endswith("-devices"):
        raise Refused("id_non_valido")              # §2.1: the old secret's form, until lab-01 is migrated
    if apartment_id.startswith("a-"):
        if not PROD_ID_RE.fullmatch(apartment_id):
            raise Refused("id_non_valido")
        if ambiente != "prod":
            raise Refused("prefisso_sbagliato")
        return
    if len(apartment_id) > MAX_ID_LEN or not STAGING_ID_RE.fullmatch(apartment_id):
        raise Refused("id_non_valido")
    if ambiente != "staging":
        raise Refused("prefisso_sbagliato")


def check_parameters(operazione: str, parametri: dict, ambiente: str) -> dict:
    """§3: exactly the parameters of the operation, each with its rule."""
    if operazione in ("capienza", "stato", "aggiorna_motore", "togli_motore"):
        if parametri:
            raise Refused("parametri_non_validi")
        return {}
    if operazione == "crea_motore":
        if set(parametri) != {"porta"} or not _int(parametri["porta"]):
            raise Refused("parametri_non_validi")
        low, high = PORTS[ambiente]
        if not low <= parametri["porta"] <= high:
            raise Refused("porta_fuori_fascia")
        return {"porta": parametri["porta"]}
    if operazione == "aggiorna_broker":
        devices = parametri.get("dispositivi")
        if set(parametri) != {"dispositivi"} or not isinstance(devices, list):
            raise Refused("parametri_non_validi")
        if len(devices) > MAX_DEVICES:
            raise Refused("troppi_dispositivi")
        seen = set()
        for d in devices:
            if not isinstance(d, dict) or set(d) != {"id", "impronta"}:
                raise Refused("parametri_non_validi")
            if not isinstance(d["id"], str) or not DEVICE_ID_RE.fullmatch(d["id"]) or d["id"] == "connector":
                raise Refused("id_non_valido")              # «connector» is the connector's user (A3 review, point 3)
            if not isinstance(d["impronta"], str) or not HASH_RE.fullmatch(d["impronta"]):
                raise Refused("impronta_non_valida")       # never a password in clear: the whole order is refused
            if d["id"] in seen:
                raise Refused("parametri_non_validi")
            seen.add(d["id"])
        return {"dispositivi": [{"id": d["id"], "impronta": d["impronta"]} for d in devices]}
    if operazione == "applica_catalogo":
        catalogo, versione = parametri.get("catalogo"), parametri.get("versione")
        if set(parametri) != {"catalogo", "versione"} or not isinstance(catalogo, str) or not _int(versione) \
                or versione < 1 or not catalogo:
            raise Refused("parametri_non_validi")
        if len(catalogo.encode("utf-8")) > MAX_CATALOG_BYTES:
            raise Refused("catalogo_troppo_grande")
        return {"catalogo": catalogo, "versione": versione}
    raise Refused("operazione_sconosciuta")


def check_order(data: bytes, ambiente: str) -> Order:
    """The whole order, as bytes, against the environment of the subscription (or of the executor's configuration).
    R2: it never raises anything but Refused: a poisoned order (JSON nested beyond the recursion limit, a lone
    surrogate) is refused like any other."""
    try:
        return _check_order(data, ambiente)
    except Refused:
        raise
    except Exception:                                    # noqa: BLE001 - R2: whatever it is, the order is refused
        raise Refused("parametri_non_validi") from None


def _check_order(data: bytes, ambiente: str) -> Order:
    if not isinstance(data, (bytes, bytearray)) or len(data) > MAX_ORDER_BYTES:
        raise Refused("troppo_grande")
    try:
        o = json.loads(bytes(data).decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise Refused("json_non_valido") from None
    if not isinstance(o, dict):
        raise Refused("json_non_valido")
    for field in FIELDS:
        if field not in o:
            raise Refused("campo_mancante")
    if set(o) != set(FIELDS):
        raise Refused("campo_non_valido")
    if not isinstance(o["op_id"], str) or not UUID_RE.fullmatch(o["op_id"]):
        raise Refused("campo_non_valido")
    if not isinstance(o["richiesto_da"], str) or not UID_RE.fullmatch(o["richiesto_da"]):
        raise Refused("campo_non_valido")
    if not isinstance(o["parametri"], dict):
        raise Refused("campo_non_valido")
    if not isinstance(o["firmato_at"], str) or not TIME_RE.fullmatch(o["firmato_at"]):
        raise Refused("campo_non_valido")
    if not isinstance(o["firma"], str) or not FIRMA_RE.fullmatch(o["firma"]):
        raise Refused("campo_non_valido")
    if o["operazione"] not in OPERATIONS:
        raise Refused("operazione_sconosciuta")
    if ambiente not in ENVIRONMENTS or o["ambiente"] != ambiente:
        raise Refused("ambiente_diverso")
    operazione = o["operazione"]
    if operazione == "capienza":
        if o["apartment_id"] is not None or o["seq"] is not None:
            raise Refused("campo_non_valido")
    else:
        if o["apartment_id"] is None or o["seq"] is None:
            raise Refused("campo_non_valido")
        if not _int(o["seq"]) or not 1 <= o["seq"] <= MAX_SEQ:
            raise Refused("campo_non_valido")
        check_apartment(o["apartment_id"], ambiente, operazione)
    parametri = check_parameters(operazione, o["parametri"], ambiente)
    return Order(o["op_id"], operazione, o["apartment_id"], o["seq"], parametri, o["ambiente"], o["richiesto_da"])


def result_for_raw(data, esito: str, codice: str) -> dict:
    """The result of an order refused before it could be read whole: the fields that are there with the right type,
    so that the server can still match it to its op_id; None for the others."""
    try:
        o = json.loads(bytes(data).decode("utf-8")) if len(data) <= MAX_ORDER_BYTES else {}
    except Exception:                                    # noqa: BLE001 - R2: a poisoned order gives an empty result
        o = {}
    if not isinstance(o, dict):
        o = {}

    def short(key):
        """R2: printable ASCII only, so that the result and the log lines can always be written."""
        value = o.get(key)
        return value if isinstance(value, str) and len(value) <= 80 and PRINTABLE_RE.fullmatch(value) else None
    seq = o.get("seq") if _int(o.get("seq")) else None
    if esito not in OUTCOMES or codice not in CODES:
        raise ValueError("esito o codice fuori dall'elenco")
    return {"op_id": short("op_id"), "operazione": short("operazione"), "apartment_id": short("apartment_id"),
            "ambiente": short("ambiente"), "seq": seq, "esito": esito, "codice": codice}


def result(order: Order, esito: str, codice: str, dati: dict | None = None) -> dict:
    """What goes back on the results queue: codes and, for stato and capienza, a few short values. Never the output
    of a script, never a catalog, never an email (§6.11)."""
    if esito not in OUTCOMES or codice not in CODES:
        raise ValueError("esito o codice fuori dall'elenco")
    clean = {}
    for key, value in (dati or {}).items():
        if not isinstance(key, str) or len(key) > 40:
            raise ValueError("chiave di dati non valida")
        if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            clean[key] = value
        elif isinstance(value, str) and len(value) <= DATA_MAX_LEN:
            clean[key] = value
        else:
            raise ValueError("valore di dati non ammesso")
    out = {"op_id": order.op_id, "operazione": order.operazione, "apartment_id": order.apartment_id,
           "ambiente": order.ambiente, "seq": order.seq, "esito": esito, "codice": codice}
    if clean:
        out["dati"] = clean
    return out

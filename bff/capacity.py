"""Tool A, package A7 (docs/proposta-a7.md; answers 1196-1202): the VM's capacity, as the server knows it.

- room_problem(): the rule of the VM (scripts/agent/comune.py room_problem; a test keeps them equal): at most
  massimo_staging engines in the staging; after the new engine (its real cap) at least 400 MB available; the caps of
  the environment plus the new one within its budget; no budget = no room. An agent from before A7 gives none of the
  new fields: then the rule of before (150 MB estimated, the count of the staging).
- The last successful «capienza» of the environment is kept in Firestore (capacity/<ambiente>), from any order: a
  creation's, or «Aggiorna» (refresh: at most one every 30 s per environment, answer 1200).
- view(): what the creation form shows: the free places with the time of the reading («vecchia» after 10 minutes),
  never a number without a reading.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from . import agent
from .logs import warn
from .repository import get_repository
from .repository.base import iso_seconds

MIN_FREE_MB = 400
OLD_NEW_ENGINE_MB = 150          # the estimate of before A7, for an agent that does not give the real cap
REFRESH_S = 30
STALE_S = 600


class RefreshTooSoon(Exception):
    def __init__(self, free_from: str):
        super().__init__(free_from)
        self.free_from = free_from


def _number(d: dict, key: str):
    value = d.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _old(d: dict) -> bool:
    return "tetto_nuovo_mb" not in d


def room_problem(d: dict, ambiente: str) -> str | None:
    if _old(d):
        mem, n, most = _number(d, "mem_available_mb"), _number(d, "motori_staging"), _number(d, "massimo_staging")
        if mem is None or n is None:
            return "errore_interno"
        if n >= (most if most is not None else 4):
            return "staging_pieno"
        return "capienza_insufficiente" if mem - OLD_NEW_ENGINE_MB < MIN_FREE_MB else None
    mem, tetto, somma = _number(d, "mem_available_mb"), _number(d, "tetto_nuovo_mb"), _number(d, "somma_tetti_mb")
    n, most, budget = _number(d, "motori_ambiente"), _number(d, "massimo_staging"), _number(d, "budget_mb")
    if mem is None or tetto is None or somma is None or n is None:
        return "errore_interno"
    if ambiente == "staging" and most is not None and n >= most:
        return "staging_pieno"
    if mem - tetto < MIN_FREE_MB:
        return "capienza_insufficiente"
    if budget is None or somma + tetto > budget:
        return "capienza_insufficiente"
    return None


def free_places(d: dict, ambiente: str) -> int:
    """How many engines more fit, by the same rule (0 when room_problem says no)."""
    if room_problem(d, ambiente) is not None:
        return 0
    if _old(d):
        most = _number(d, "massimo_staging") or 4
        return max(0, min(most - d["motori_staging"], (d["mem_available_mb"] - MIN_FREE_MB) // OLD_NEW_ENGINE_MB))
    tetto = d["tetto_nuovo_mb"]
    limits = [(d["mem_available_mb"] - MIN_FREE_MB) // tetto, (d["budget_mb"] - d["somma_tetti_mb"]) // tetto]
    if ambiente == "staging" and _number(d, "massimo_staging") is not None:
        limits.append(d["massimo_staging"] - d["motori_ambiente"])
    return max(0, min(limits))


def _now() -> datetime:
    return agent.utcnow()


def _stamp(when: datetime) -> str:
    return when.isoformat(timespec="milliseconds").replace("+00:00", "Z")


UNREADABLE = "La capienza letta non è valida: riprova"


async def save(ambiente: str, op_id: str, dati: dict) -> None:
    """A successful capienza of this environment: the new last reading. One whose numbers cannot be read is NOT a
    reading (o2, 406e150: «Nessun posto libero» would be false): the last good one stays, and the refresh that asked
    for it reads «fallito»."""
    if room_problem(dati, ambiente) == "errore_interno":
        warn("capacity reading refused", op_id=op_id, motivo="dati_illeggibili")
        await get_repository().change_capacity(ambiente, lambda doc: {**doc, "scartata_op": op_id})
        return
    reading = {"letta_at": _stamp(_now()), "op_id": op_id, "dati": dict(dati)}

    def change(doc: dict) -> dict:
        return {**doc, "lettura": reading}
    await get_repository().change_capacity(ambiente, change)


async def view() -> dict:
    ambiente = agent.get_settings().agent_ambiente
    doc = await get_repository().get_capacity(ambiente) or {}
    now = _now()
    out: dict = {"capienza": None, "aggiornamento": None, "aggiornabile_dal": None}
    reading = doc.get("lettura")
    if reading:
        d = reading["dati"]
        out["capienza"] = {
            "ambiente": ambiente, "letta_at": reading["letta_at"],
            "vecchia": now.timestamp() - iso_seconds(reading["letta_at"]) > STALE_S,
            "posti_liberi": free_places(d, ambiente), "motivo": room_problem(d, ambiente),
            "motori_ambiente": d.get("motori_ambiente", d.get("motori_staging")),
            "massimo_motori": d.get("massimo_staging"), "mem_available_mb": d.get("mem_available_mb"),
            "tetto_nuovo_mb": d.get("tetto_nuovo_mb"), "somma_tetti_mb": d.get("somma_tetti_mb"),
            "budget_mb": d.get("budget_mb")}
    if doc.get("op_id"):
        op = await agent.view(doc["op_id"])
        if op is not None:
            out["aggiornamento"] = {k: op[k] for k in ("op_id", "stato", "codice", "messaggio", "creato_at")}
            if doc.get("scartata_op") == doc["op_id"]:          # its result came, but could not be read
                out["aggiornamento"].update(stato="fallito", codice="errore_interno", messaggio=UNREADABLE)
    if doc.get("aggiornato_at"):
        free = datetime.fromtimestamp(iso_seconds(doc["aggiornato_at"]), UTC) + timedelta(seconds=REFRESH_S)
        if free > now:
            out["aggiornabile_dal"] = _stamp(free)
    return out


async def refresh(uid: str) -> dict:
    """«Aggiorna»: a new capienza, at most one every 30 s per environment (raises RefreshTooSoon, or the agent's
    AgentError when the publish fails)."""
    repo = get_repository()
    ambiente = agent.get_settings().agent_ambiente
    now = _now()

    def claim(doc: dict) -> dict:
        last = doc.get("aggiornato_at")
        if last and now.timestamp() - iso_seconds(last) < REFRESH_S:
            raise RefreshTooSoon(_stamp(datetime.fromtimestamp(iso_seconds(last), UTC) + timedelta(seconds=REFRESH_S)))
        return {**doc, "aggiornato_at": _stamp(now)}
    await repo.change_capacity(ambiente, claim)
    op, body = await agent.new_order("capienza", None, uid, {})
    await repo.change_capacity(ambiente, lambda doc: {**doc, "op_id": op.op_id})
    await agent.publish_op(op, body)
    warn("capacity refresh sent", op_id=op.op_id)
    return await view()

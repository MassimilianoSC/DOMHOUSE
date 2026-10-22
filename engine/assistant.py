"""The assistant with a real model (P-60 step 9, D-132, D-143, D-144): POST /ask answered by a model that proposes and
the engine's tools that validate and act, through the same rules and limits as the app.

The model (OpenAI-compatible chat with tools) is reached through the BFF's POST /internal/ai/chat (bff/ai_gateway.py:
monthly cap of the project, 80 % alert, prices), never directly: ModelClient below, configured by MODEL_BASE_URL. Without
it the engine keeps the simulated keyword assistant (core.ApartmentEngine._resolve_ask), as the conformance suite and the
CI run it.

How one question goes:
1. ASK_DAILY_LIMIT (50) questions a day per apartment (the apartment's local day), counted before calling the model.
2. The request already carries the apartment's state (mode, occupancy, devices and their state: lot 28 a), so a
   command needs no reading turn; the model can still read with tools (consumption, decisions, schedule, the state
   again) and PROPOSES actions with tools (mode, a device command, a scheduled action): each proposal is validated at
   once and answered to the model, but nothing is executed while the model talks. A turn made only of valid
   proposals ends the conversation (lot 28 b): the engine writes the outcome itself, no final call to the model.
3. When the model has finished, the engine decides (D-132 point 2, D-144): with guests in, switching off a climate or
   a boiler or changing the mode needs the manager's approval; two or more actions together need it too, one approval
   per action, queued. Otherwise the commands run as automatic ones (actor "assistant", within the limits, R6).
4. The engine writes the outcome itself after the model's text (fixed rule 2: "done" only with acked): "Fatto: …" for
   an acked command, "Comando inviato: …, l'esito arriva nell'app" when it is not final within ACK_WAIT_S, "Serve la tua
   approvazione: …" for each approval, "Programmato: …" for a scheduled action.
5. The whole answer within ASK_TIMEOUT_S (inside the contract's 30 s). Lot 28 c: the model's calls must end by
   ASK_TIMEOUT_S - APPLY_RESERVE_S (the reserve is for running the proposals and waiting for their outcome); a call
   that would go beyond is cut there, no new call starts with less than MIN_CALL_S left, and what was proposed so far
   is applied and answered; with nothing proposed, status failed, reason timeout, at once rather than at 28 s.
Fixed rule 1: no guest data reaches the model: the tools give states, consumption, schedule and decisions, never the
bookings' people (the engine has none of them anyway: names, emails and phones stay with the BFF).
"""
import asyncio
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

MAX_TURNS = 6                 # model calls for one question (reads, then the answer)
ASK_TIMEOUT_S = 28.0          # the contract's 30 s, with a margin for saving and the app's polling
ACK_WAIT_S = 10.0             # a command's outcome is final within 10 s (contract)
APPLY_RESERVE_S = ACK_WAIT_S + 1.0    # lot 28 c: kept for running the proposals and waiting for their outcome
MIN_CALL_S = 4.0              # lot 28 c: no new model call with less than this left in the model's budget
PROPOSALS = {"cambia_modalita", "comanda_dispositivo", "programma"}
TIMEOUT_ANSWER = "Non sono riuscito a rispondere in tempo: riprova, oppure fai dall'app."
TEMPERATURE = 0.2
# D-154: the modes in the manager's sentences by their Italian names («vuoto», not the contract's «empty»)
MODE_NAMES = {"comfort": "comfort", "eco": "eco", "empty": "vuoto"}

SYSTEM_PROMPT = """Sei l'assistente di DOMHOUSE: aiuti il gestore di un appartamento in affitto breve a controllare
clima, caldaia, prese e modalità. Rispondi in italiano, in modo breve: al massimo tre frasi.
Regole fisse, sempre:
1. Non conosci e non chiedi dati degli ospiti (nomi, email, telefoni, note delle prenotazioni): lavori solo su stati,
   consumi, programmazioni e decisioni.
2. Non dire mai che un'azione è stata fatta o eseguita: dopo la tua risposta il sistema scrive da solo l'esito di ogni
   azione. Di' solo che cosa hai chiesto di fare.
3. Non inventare stati, valori o motivi: se gli strumenti non te li danno, rispondi «Non lo so» e rimanda all'app.
4. Per le domande «perché …?» leggi le decisioni e spiega con quelle.
5. Puoi cambiare la modalità, comandare un dispositivo e programmare un'azione; non puoi cambiare regole, utenti o
   appartamenti. Per le regole rispondi che si scrive la richiesta nella pagina Regole dell'app, dove l'assistente
   propone la modifica e il gestore la conferma; per utenti e appartamenti, che si fa dall'app.
Ora locale dell'appartamento: {now} (fuso {tz}). Modalità: comfort, eco, vuoto (empty).
Stato attuale dell'appartamento e dei dispositivi (letto adesso, non serve rileggerlo per un comando):
{state}"""


def _fn(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties or {}, "required": required or []}}}


TOOLS = [
    _fn("leggi_appartamento", "Modalità, occupazione (occupato, vuoto, prenotato), forzatura in corso."),
    _fn("leggi_dispositivi", "I dispositivi con stanza, stato online e stato di ogni capacità."),
    _fn("leggi_consumi", "Consumi in kWh fra due istanti (al massimo 31 giorni), totale e per dispositivo.",
        {"dal": {"type": "string", "description": "ISO 8601"}, "al": {"type": "string", "description": "ISO 8601"}},
        ["dal", "al"]),
    _fn("leggi_decisioni", "Le ultime decisioni del motore e delle persone, con il motivo: per i «perché».",
        {"quante": {"type": "integer", "minimum": 1, "maximum": 50},
         "dispositivo": {"type": "string", "description": "device_id, facoltativo"}}),
    _fn("leggi_programmazioni", "Le azioni programmate nei prossimi giorni."),
    _fn("cambia_modalita", "Propone di cambiare la modalità dell'appartamento.",
        {"modalita": {"type": "string", "enum": ["comfort", "eco", "empty"]}}, ["modalita"]),
    _fn("comanda_dispositivo", "Propone un comando a un dispositivo (switch: turn_on/turn_off; climate: set_climate con "
        "on, mode, setpoint, fan, oppure turn_off; heating: set_heating con on, setpoint, oppure turn_off).",
        {"device_id": {"type": "string"}, "capability": {"type": "string", "enum": ["switch", "climate", "heating"]},
         "action": {"type": "string"}, "params": {"type": "object"}}, ["device_id", "capability", "action"]),
    _fn("programma", "Propone un'azione programmata a un orario futuro: una modalità o un comando a un dispositivo.",
        {"quando": {"type": "string", "description": "ISO 8601, ora locale dell'appartamento se senza fuso"},
         "modalita": {"type": "string", "enum": ["comfort", "eco", "empty"]},
         "device_id": {"type": "string"}, "capability": {"type": "string"}, "action": {"type": "string"},
         "params": {"type": "object"}}, ["quando"]),
]


class ModelRefused(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason, self.message = reason, message


class ModelClient:
    """The BFF's POST /internal/ai/chat, with this engine's apartment id and key (stdlib only: no new dependency)."""

    def __init__(self, base_url: str, apartment_id: str, api_key: str):
        self.url = base_url.rstrip("/") + "/internal/ai/chat"
        self.apartment_id, self.api_key = apartment_id, api_key

    def _post(self, body: dict) -> dict:
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="POST", headers={
            "Content-Type": "application/json", "X-Apartment-Id": self.apartment_id, "X-API-Key": self.api_key})
        try:
            with urllib.request.urlopen(req, timeout=ASK_TIMEOUT_S) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            try:
                err = json.loads(exc.read())
            except ValueError:
                err = {}
            if exc.code == 429:
                raise ModelRefused("monthly_cap", err.get("message") or "Limite mensile raggiunto, riprova dal mese prossimo")
            raise ModelRefused("model_unavailable", "L'assistente non è disponibile ora, riprova più tardi") from None
        except (urllib.error.URLError, TimeoutError, ValueError):
            raise ModelRefused("model_unavailable", "L'assistente non è disponibile ora, riprova più tardi") from None

    async def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        return await asyncio.to_thread(self._post, {"messages": messages, "tools": tools, "temperature": TEMPERATURE})


class Assistant:
    """One question, from the model's first call to the saved answer."""

    def __init__(self, engine, client):
        self.e, self.client = engine, client

    # ---- the question ---------------------------------------------------------------------------------------------
    async def resolve(self, ask: dict, actor: str) -> None:
        from .core import iso, utcnow
        try:
            await asyncio.wait_for(self._run(ask, actor), timeout=ASK_TIMEOUT_S)
        except TimeoutError:
            ask.update(status="failed", reason="timeout", answer=TIMEOUT_ANSWER)
        except ModelRefused as exc:
            ask.update(status="failed", reason=exc.reason, answer=exc.message)
        except Exception as exc:                          # never a pending question left behind
            from . import log
            log.error("assistant failed", apartment_id=self.e.apartment_id, error=type(exc).__name__)
            ask.update(status="failed", reason="internal_error", answer="Non sono riuscito a rispondere: riprova.")
        ask["updated_at"] = iso(utcnow())
        self.e._save_ask(ask)

    def asked_today(self, ask: dict) -> int:
        from .core import parse_dt
        tz = ZoneInfo(self.e.timezone)
        today = parse_dt(ask["created_at"]).astimezone(tz).date()
        return sum(1 for a in self.e.asks.values() if parse_dt(a["created_at"]).astimezone(tz).date() == today)

    async def _run(self, ask: dict, actor: str) -> None:
        from .core import utcnow
        limit = int(self.e.setting("ASK_DAILY_LIMIT"))
        if self.asked_today(ask) > limit:
            ask.update(status="failed", reason="daily_limit",
                       answer=f"Limite di {limit} domande al giorno raggiunto per questo appartamento: riprova domani.")
            return
        tz = ZoneInfo(self.e.timezone)
        now = utcnow().astimezone(tz).strftime("%Y-%m-%d %H:%M")
        state = json.dumps({"appartamento": self.tool("leggi_appartamento", {}, []),
                            **self.tool("leggi_dispositivi", {}, [])}, ensure_ascii=False, default=str)
        messages = [{"role": "system", "content": SYSTEM_PROMPT.format(now=now, tz=self.e.timezone, state=state)},
                    {"role": "user", "content": ask["text"]}]
        proposals: list[dict] = []
        text = ""
        loop = asyncio.get_running_loop()
        model_deadline = loop.time() + ASK_TIMEOUT_S - APPLY_RESERVE_S      # lot 28 c
        for _ in range(MAX_TURNS):
            left = model_deadline - loop.time()
            if left < MIN_CALL_S:
                break
            try:
                answer = await asyncio.wait_for(self.client.chat(messages, TOOLS), timeout=left)
            except TimeoutError:
                break
            msg = (answer.get("choices") or [{}])[0].get("message") or {}
            calls = msg.get("tool_calls") or []
            if not calls:
                text = (msg.get("content") or "").strip()
                break
            messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
            valid_proposals_only = True
            for call in calls:
                fn = call.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                result = self.tool(fn.get("name", ""), args if isinstance(args, dict) else {}, proposals)
                if fn.get("name") not in PROPOSALS or "errore" in result:
                    valid_proposals_only = False
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                 "content": json.dumps(result, ensure_ascii=False, default=str)})
            if valid_proposals_only:                 # lot 28 b: the engine writes the outcome, no final call
                text = (msg.get("content") or "").strip()
                break
        if not proposals and not text:               # lot 28 c: out of time with nothing to do or say
            ask.update(status="failed", reason="timeout", answer=TIMEOUT_ANSWER)
            return
        lines = await self.apply(proposals, ask, actor)
        ask["answer"] = "\n".join([t for t in [text, *lines] if t]) or "Non lo so: guarda nell'app."
        if ask["status"] == "pending":
            ask["status"] = "answered"

    # ---- tools ----------------------------------------------------------------------------------------------------
    def tool(self, name: str, args: dict, proposals: list[dict]) -> dict:
        from .core import MockError
        e = self.e
        try:
            if name == "leggi_appartamento":
                apt = e.apartment()
                return {k: apt.get(k) for k in ("name", "mode", "occupancy", "hold", "next_checkin", "next_checkout", "online")}
            if name == "leggi_dispositivi":
                rooms = {r["room_id"]: r["name"] for r in e.rooms}
                return {"dispositivi": [{"device_id": d["device_id"], "nome": d["label"],
                                         "stanza": rooms.get(d["room_id"], d["room_id"]), "online": d["online"],
                                         "stato": d["capabilities"]} for d in e.devices.values()]}
            if name == "leggi_consumi":
                r = e.energy({"from": args.get("dal"), "to": args.get("al"), "bucket": "day"})
                return {"totale_kwh": r["total_kwh"], "per_dispositivo": r["by_device"],
                        "per_giorno": [{"giorno": s["ts"], "kwh": s["kwh"]} for s in r["series"]]}
            if name == "leggi_decisioni":
                q = {"limit": str(min(max(int(args.get("quante") or 20), 1), 50))}
                if args.get("dispositivo"):
                    q["device_id"] = args["dispositivo"]
                return {"decisioni": [{k: d.get(k) for k in ("ts", "actor", "target", "action", "old_value",
                                                             "new_value", "reasoning", "outcome")}
                                      for d in e.list_decisions(q)["items"]]}
            if name == "leggi_programmazioni":
                return {"programmazioni": [{k: s.get(k) for k in ("run_at", "kind", "action", "status")}
                                           for s in e.list_schedule()["items"] if s["status"] == "planned"]}
            if name == "cambia_modalita":
                mode = args.get("modalita")
                if mode not in ("comfort", "eco", "empty"):
                    return {"errore": "modalità non valida: comfort, eco o empty"}
                proposals.append({"type": "mode", "mode": mode})
                return {"registrata": f"modalità {mode}"}
            if name == "comanda_dispositivo":
                device = e.get_device(args.get("device_id", ""))
                body = {"capability": args.get("capability"), "action": args.get("action"),
                        "params": args.get("params") or {}}
                e.validate_command(device, body)
                proposals.append({"type": "command", "device_id": device["device_id"], "body": body})
                return {"registrato": f"comando {body['action']} a {device['label']}"}
            if name == "programma":
                when = self._when(args.get("quando"))
                if args.get("modalita"):
                    action = {"type": "apartment_mode", "mode": args["modalita"]}
                else:
                    device = e.get_device(args.get("device_id", ""))
                    body = {"capability": args.get("capability"), "action": args.get("action"),
                            "params": args.get("params") or {}}
                    e.validate_command(device, body)
                    action = {"type": "device_command", "device_id": device["device_id"], **body}
                proposals.append({"type": "schedule", "run_at": when, "action": action})
                return {"registrata": f"azione programmata per {when}"}
        except MockError as exc:
            return {"errore": exc.message}
        except (KeyError, TypeError, ValueError) as exc:
            return {"errore": f"argomenti non validi ({type(exc).__name__})"}
        return {"errore": f"strumento sconosciuto: {name}"}

    def _when(self, value) -> str:
        from .core import iso, parse_dt, utcnow
        if not isinstance(value, str):
            raise ValueError("quando")
        try:
            dt = parse_dt(value)
        except ValueError:
            dt = datetime.fromisoformat(value).replace(tzinfo=ZoneInfo(self.e.timezone))   # local time without zone
        if dt <= utcnow() + timedelta(seconds=30):
            raise ValueError("quando nel passato")
        return iso(dt)

    # ---- after the model: approvals, commands, outcomes -----------------------------------------------------------
    def describe(self, p: dict) -> str:
        e = self.e
        if p["type"] == "mode":
            return f"modalità {MODE_NAMES.get(p['mode'], p['mode'])}"
        if p["type"] == "schedule":
            local = datetime.fromisoformat(p["run_at"].replace("Z", "+00:00")).astimezone(ZoneInfo(e.timezone))
            a = p["action"]
            what = f"modalità {MODE_NAMES.get(a['mode'], a['mode'])}" if a["type"] == "apartment_mode" else \
                self.describe({"type": "command", "device_id": a["device_id"], "body": a})
            return f"{what} alle {local.strftime('%H:%M')} del {local.strftime('%d/%m')}"
        device = e.devices[p["device_id"]]
        body = p["body"]
        cap, action, params = e.validate_command(device, body)
        target = e.target_state(device, cap, action, params)
        label = device["label"].lower()
        if not target.get("on"):
            return f"spegnere {label}"
        if cap in ("climate", "heating") and target.get("setpoint") is not None:
            return f"{label} a {target['setpoint']:g} °C"
        return f"accendere {label}"

    def question(self, what: str) -> str:
        """D-154 point 2: the approval asked as a question in the chat, answered with «Sì» / «No» under it (the same
        call as the Approvals page, so the same record) or from the Approvals page."""
        tail = " Rispondi Sì o No qui sotto, oppure dalla pagina Approvazioni."
        if self.e.apartment().get("occupancy") == "occupied":
            if what.startswith("spegnere "):
                return f"Spengo {what[len('spegnere '):]} con ospiti presenti?{tail}"
            if what.startswith("modalità "):
                return f"Passo alla {what} con ospiti presenti?{tail}"
            return f"Confermi, con ospiti presenti: {what}?{tail}"
        return f"Confermi: {what}?{tail}"

    def needs_approval(self, p: dict, together: bool) -> bool:
        """D-132 point 2: with guests in, the guest's comfort (switching off a climate or a boiler, the mode); and any
        action together with others (one approval each, D-144)."""
        if p["type"] == "schedule":
            return False
        if together:
            return True
        if self.e.apartment().get("occupancy") != "occupied":
            return False
        if p["type"] == "mode":
            return True
        device = self.e.devices[p["device_id"]]
        cap, action, params = self.e.validate_command(device, p["body"])
        return cap in ("climate", "heating") and not self.e.target_state(device, cap, action, params).get("on")

    async def apply(self, proposals: list[dict], ask: dict, actor: str) -> list[str]:
        from .core import FINAL, MockError
        e = self.e
        corr, why = ask["correlation_id"], f"Richiesta all'assistente: «{ask['text']}»"
        together = len([p for p in proposals if p["type"] != "schedule"]) >= 2
        lines, waiting = [], []
        for p in proposals:
            what = self.describe(p)
            try:
                if self.needs_approval(p, together):
                    proposed = ({"type": "apartment_mode", "mode": p["mode"]} if p["type"] == "mode" else
                                {"type": "device_command", "device_id": p["device_id"], **p["body"]})
                    opened = e._new_approval("assistant", what[0].upper() + what[1:], why, proposed, "reject", corr)
                    approval = opened or e.approval_queue[-1]
                    if ask["approval_id"] is None:
                        ask["approval_id"] = approval["approval_id"]
                        ask["status"] = "needs_approval"
                    lines.append(self.question(what))
                elif p["type"] == "mode":
                    for command_id in e.set_mode(p["mode"], actor, corr, why, "assistant"):
                        ask["actions"].append({"type": "command", "command_id": command_id})
                    lines.append(f"Modalità {MODE_NAMES.get(p['mode'], p['mode'])} impostata: i comandi ai dispositivi partono ora, l'esito arriva "
                                 f"nell'app.")
                elif p["type"] == "schedule":
                    item = e.create_schedule({"run_at": p["run_at"], "action": p["action"]}, actor, corr,
                                             source="assistant")
                    ask["actions"].append({"type": "schedule", "schedule_id": item["schedule_id"]})
                    lines.append(f"Programmato: {what}.")
                else:
                    cmd = e.create_command(p["device_id"], p["body"], actor, corr, decision_actor="assistant",
                                           reasoning=why)
                    if cmd is None:                           # an automatic start waiting for the compressor's pause
                        lines.append(f"Comando inviato: {what}, parte dopo la pausa del compressore; l'esito arriva "
                                     f"nell'app.")
                        continue
                    ask["actions"].append({"type": "command", "command_id": cmd["command_id"]})
                    waiting.append((cmd["command_id"], what))
            except MockError as exc:
                lines.append(f"Non fatto: {what} ({exc.message}).")
        deadline = asyncio.get_running_loop().time() + ACK_WAIT_S
        while waiting and any(e.commands[c]["status"] not in FINAL for c, _ in waiting) \
                and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.1)
        for command_id, what in waiting:
            status = e.commands[command_id]["status"]
            if status == "acked":
                lines.append(f"Fatto: {what}.")
            elif status in FINAL:
                lines.append(f"Non riuscito: {what} ({e.commands[command_id].get('reason') or status}).")
            else:
                lines.append(f"Comando inviato: {what}, l'esito arriva nell'app.")
        return lines

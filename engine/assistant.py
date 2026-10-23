"""The assistant with a real model (P-60 step 9, D-132, D-143, D-144, D-182): POST /ask answered by a model that
proposes, and the engine that validates and acts, through the same rules and limits as the app.

The model is reached through the BFF's POST /internal/ai/chat (bff/ai_gateway.py: gemini-3.8-flash on Vertex's native
endpoint in the EU, reasoning off, monthly cap, prices, the twin request after 6 s), never directly: ModelClient below,
configured by MODEL_BASE_URL, which refuses an answer without a European X-AI-Location (D-181). Without it the engine
keeps the simulated keyword assistant (core.ApartmentEngine._resolve_ask), as the conformance suite and the CI run it.

How one question goes (D-182: no tools, one call):
1. ASK_DAILY_LIMIT (50) questions a day per apartment (the apartment's local day), counted before calling the model.
2. The request carries the apartment's state, the devices with their state, the recent decisions and the planned
   actions, and asks a JSON object in the text: {"risposta": …, "azioni": […]} with three forms of action (a mode, a
   device command, a scheduled action). parse_answer checks its shape; a JSON not valid runs nothing and the answer is
   the apartment's state.
3. Each action goes through the engine's own checks (the former tools: devices, capabilities, limits, time); a wrong one
   is said in the answer («Non fatto: …»). Then the engine decides (D-132 point 2, D-144, D-162 ASSISTANT_CONFIRM,
   D-170): with guests in, switching off a climate or a boiler or changing the mode needs the manager's approval; two
   or more actions together need it too, one approval per action, queued; a scheduled one asks when guests are in at
   its time. Otherwise the commands run as automatic ones (actor "assistant", within the limits, R6).
4. The engine writes the outcome itself after the model's text (fixed rule 2: "done" only with acked): "Fatto: …" for
   an acked command, "Comando inviato: …, l'esito arriva nell'app" when it is not final in time, a question for each
   approval, "Programmato: …" for a scheduled action.
5. The whole answer within ASK_TIMEOUT_S (inside the contract's 30 s): the model has all of it but
   NO_PROPOSAL_RESERVE_S; beyond, status failed, reason timeout, at once.
Fixed rule 1: no guest data reaches the model: the state has devices, consumption, schedule and decisions, never the
bookings' people (the engine has none of them anyway: names, emails and phones stay with the BFF).
"""
import asyncio
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ASK_TIMEOUT_S = 28.0          # the contract's 30 s, with a margin for saving and the app's polling
ACK_WAIT_S = 10.0             # a command's outcome is final within 10 s (contract)
NO_PROPOSAL_RESERVE_S = 2.0   # C-10 layer 2: with nothing proposed yet, only this is kept (the model gets ~25 s)
CONNECT_TIMEOUT_S = 5.0       # lot 30: DNS, TCP and TLS towards the BFF, apart from waiting for the answer


def european_location(location: str | None) -> bool:
    """D-180/D-181: the model's location as the BFF declares it (X-AI-Location): eu or a European region; a missing
    one counts as not European."""
    v = (location or "").strip().lower()
    return v == "eu" or v.startswith("europe-")
TIMEOUT_ANSWER = "Non sono riuscito a rispondere in tempo: riprova, oppure fai dall'app."
TEMPERATURE = 0.2


def fmt_c(value) -> str:
    return f"{value:g} °C".replace(".", ",")
# D-154, decision 55: the modes in the manager's sentences by their Italian names: «casa vuota», not the contract's
# «empty» nor «vuoto», which is the occupancy (vuoto / occupato / prenotato)
MODE_NAMES = {"comfort": "comfort", "eco": "eco", "empty": "casa vuota"}

SYSTEM_PROMPT = """Sei l'assistente di DOMHOUSE: aiuti il gestore di un appartamento in affitto breve a controllare
clima, caldaia, prese e modalità. Rispondi in italiano, in modo breve: al massimo tre frasi.
Regole fisse, sempre:
1. Non conosci e non chiedi dati degli ospiti (nomi, email, telefoni, note delle prenotazioni): lavori solo su stati,
   consumi, programmazioni e decisioni.
2. Non dire mai che un'azione è stata fatta o eseguita: dopo la tua risposta il sistema scrive da solo l'esito di ogni
   azione. Di' solo che cosa hai chiesto di fare.
3. Non inventare stati, valori o motivi: se lo stato qui sotto non li dice, rispondi «Non lo so» e rimanda all'app.
4. Per le domande «perché …?» usa le decisioni recenti qui sotto e spiega con quelle.
   Non citare codici interni delle regole (come window_open_off): usa i loro nomi in italiano, come nello stato.
5. Puoi cambiare la modalità, comandare un dispositivo e programmare un'azione; non puoi cambiare regole, utenti o
   appartamenti. Per le regole rispondi che si scrive la richiesta nella pagina Regole dell'app, dove l'assistente
   propone la modifica e il gestore la conferma; per utenti e appartamenti, che si fa dall'app.
Ora locale dell'appartamento: {now} (fuso {tz}). Modalità: comfort, eco, casa vuota (empty).
Stato attuale dell'appartamento, dei dispositivi, decisioni recenti e programmazioni (letti adesso; tutti gli orari
sono nell'ora locale dell'appartamento, AAAA-MM-GG HH:MM):
{state}
Gli orari qui sopra e quelli che scrivi in «quando» sono già nell'ora locale dell'appartamento: usali così come sono,
non convertirli.
Rispondi SOLO con un oggetto JSON, senza altro testo e senza blocchi di codice:
{{"risposta": "<al massimo tre frasi per il gestore>", "azioni": [<zero o più azioni>]}}
Ogni azione ha una di queste forme:
{{"tipo": "modalita", "modalita": "comfort" | "eco" | "empty"}}
{{"tipo": "comando", "device_id": "<id di una presa>", "capability": "switch", "action": "turn_on" | "turn_off"}}
{{"tipo": "comando", "device_id": "<id di un clima>", "capability": "climate", "action": "set_climate",
 "params": {{solo i campi da cambiare fra "on": true | false, "mode": "cool" | "heat" | "dry" | "fan", "setpoint": <numero>, "fan": "auto" | "low" | "mid" | "high"}}}}
{{"tipo": "comando", "device_id": "<id di una caldaia>", "capability": "heating", "action": "set_heating",
 "params": {{solo i campi da cambiare fra "on": true | false, "setpoint": <numero>}}}}
{{"tipo": "comando", "device_id": "<id di un clima o di una caldaia>", "capability": "climate" | "heating", "action": "turn_off"}}
{{"tipo": "programma", "quando": "<data e ora locale AAAA-MM-GGTHH:MM:SS>", "modalita": "comfort" | "eco" | "empty"}}
{{"tipo": "programma", "quando": "<data e ora locale>", e device_id, capability, action, params come in un comando}}
Nessun campo con valore null.
Per una domanda senza azioni, «azioni» è vuoto."""


_ACTION_KEYS = {"modalita": {"tipo", "modalita"},
                "comando": {"tipo", "device_id", "capability", "action", "params"},
                "programma": {"tipo", "quando", "modalita", "device_id", "capability", "action", "params"}}


def parse_answer(text: str | None) -> dict | None:
    """D-182: the model's JSON object (also inside a ```json block), checked in its shape: «risposta» a text, «azioni»
    a list of the three forms with no other keys. None = not valid: nothing of it is run."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
        raw = raw.rsplit("```", 1)[0].strip()
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("risposta"), str):
        return None
    actions = data.get("azioni", [])
    if not isinstance(actions, list):
        return None
    for a in actions:
        if not isinstance(a, dict) or a.get("tipo") not in _ACTION_KEYS or not set(a) <= _ACTION_KEYS[a["tipo"]]:
            return None
        if "params" in a and not isinstance(a["params"], dict):
            return None
    return {"risposta": data["risposta"], "azioni": actions}


def clean_command(capability, action, params) -> tuple:
    """(action, params) of a model's command in the form the engine checks (staging, 23 Oct: «accendi la stufetta»
    came with "on": true and mode, setpoint, fan null on a socket's turn_on, refused as «Parametri non ammessi»).
    Null fields and fields the action does not take are dropped; turn_on of a climate or a boiler is set_climate /
    set_heating with on true. A contradiction (turn_on with "on": false, turn_off with "on": true) is refused."""
    from .core import PARAMS, MockError
    if not isinstance(params, dict):
        return action, params                        # the engine's check refuses it as before
    params = {k: v for k, v in params.items() if v is not None}
    if action in ("turn_on", "turn_off"):
        if "on" in params and params["on"] is not (action == "turn_on"):
            raise MockError(422, "invalid_params", "Comando contraddittorio: accensione e spegnimento insieme")
        if action == "turn_on" and capability in ("climate", "heating"):
            action, params = ("set_climate" if capability == "climate" else "set_heating"), {**params, "on": True}
        else:
            params = {}
    if action in PARAMS:
        params = {k: v for k, v in params.items() if k in PARAMS[action]}
    return action, params


_UTC_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|\+00:00)$")


def local_times(value, tz: ZoneInfo):
    """The state for the model with every time of the engine (UTC, «2026-10-22T13:00:00.000Z») in the apartment's
    local time («2026-10-22 15:00»): the manager asks «alle 15» and the model must read 15, not 13 (prose test, 23 Oct)."""
    if isinstance(value, dict):
        return {k: local_times(v, tz) for k, v in value.items()}
    if isinstance(value, list):
        return [local_times(v, tz) for v in value]
    if isinstance(value, datetime):
        return value.astimezone(tz).strftime("%Y-%m-%d %H:%M")
    if isinstance(value, str) and _UTC_TIME.match(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(tz).strftime("%Y-%m-%d %H:%M")
    return value


def as_tool(action: dict) -> tuple[str, dict]:
    """An action of the JSON -> the engine's own validator that used to be a tool (the same checks as before)."""
    args = {k: v for k, v in action.items() if k != "tipo"}
    return {"modalita": "cambia_modalita", "comando": "comanda_dispositivo", "programma": "programma"}[action["tipo"]], args


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
    """The model's way refused: reason (monthly_cap, model_unavailable); fallback False when the quick assistant must
    not answer either (D-181: an answer from outside the EU)."""

    def __init__(self, reason: str, message: str, fallback: bool = True):
        super().__init__(message)
        self.reason, self.message, self.fallback = reason, message, fallback


class ModelClient:
    """The BFF's POST /internal/ai/chat, with this engine's apartment id and key (stdlib only: no new dependency)."""

    def __init__(self, base_url: str, apartment_id: str, api_key: str):
        self.url = base_url.rstrip("/") + "/internal/ai/chat"
        self.apartment_id, self.api_key = apartment_id, api_key

    def _post(self, body: dict) -> dict:
        """POST to the BFF with the phases watched (lot 30): DNS, connessione (TCP, CONNECT_TIMEOUT_S), TLS
        (CONNECT_TIMEOUT_S), invio della richiesta, attesa della risposta (ASK_TIMEOUT_S), lettura della risposta. A
        failure is logged with its phase ("assistant model call failed") and becomes model_unavailable."""
        import http.client
        import socket
        import ssl
        import time
        from urllib.parse import urlsplit

        from . import log

        parts = urlsplit(self.url)
        https = parts.scheme == "https"
        host, port = parts.hostname, parts.port or (443 if https else 80)
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        headers = {"Content-Type": "application/json", "X-Apartment-Id": self.apartment_id, "X-API-Key": self.api_key}
        phase, started = "DNS", time.monotonic()
        try:
            socket.getaddrinfo(host, port)
            phase = "connessione"
            sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT_S)
            if https:
                phase = "TLS"
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            sock.settimeout(ASK_TIMEOUT_S)
            conn = (http.client.HTTPSConnection if https else http.client.HTTPConnection)(host, port)
            conn.sock = sock
            phase = "invio della richiesta"
            conn.request("POST", path, body=json.dumps(body).encode(), headers=headers)
            phase = "attesa della risposta"
            resp = conn.getresponse()
            phase = "lettura della risposta"
            status, raw, location = resp.status, resp.read(), resp.getheader("X-AI-Location")
            conn.close()
        except (OSError, http.client.HTTPException) as exc:
            log.warn("assistant model call failed", apartment_id=self.apartment_id,
                     phase="DNS" if isinstance(exc, socket.gaierror) else phase,
                     timeout=isinstance(exc, TimeoutError), error=type(exc).__name__,
                     seconds=round(time.monotonic() - started, 2))
            raise ModelRefused("model_unavailable", "L'assistente non è disponibile ora, riprova più tardi") from None
        if not european_location(location):           # D-181: refused before anything in the answer is used
            log.error("model location refused", apartment_id=self.apartment_id, ai_location=location or "assente")
            raise ModelRefused("model_unavailable", "L'assistente non è disponibile ora, riprova più tardi",
                               fallback=False)
        if status == 429:
            try:
                message = json.loads(raw).get("message")
            except ValueError:
                message = None
            raise ModelRefused("monthly_cap", message or "Limite mensile raggiunto, riprova dal mese prossimo")
        if status != 200:
            raise ModelRefused("model_unavailable", "L'assistente non è disponibile ora, riprova più tardi")
        try:
            return json.loads(raw)
        except ValueError:
            raise ModelRefused("model_unavailable", "L'assistente non è disponibile ora, riprova più tardi") from None

    async def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        body = {"messages": messages, "temperature": TEMPERATURE}
        if tools:
            body["tools"] = tools
        return await asyncio.to_thread(self._post, body)


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
        messages = self.messages(ask["text"])
        loop = asyncio.get_running_loop()
        end = loop.time() + ASK_TIMEOUT_S
        # D-182: one call, no tools; C-10 layer 2: the model gets all but NO_PROPOSAL_RESERVE_S (the BFF's twin after 6 s)
        try:
            answer = await asyncio.wait_for(self.client.chat(messages, []),
                                            timeout=max(end - NO_PROPOSAL_RESERVE_S - loop.time(), 0.01))
        except TimeoutError:                         # D-182 layer 3: the model did not answer in time
            await self.quick(ask, actor, "timeout", end)
            return
        except ModelRefused as exc:
            if not exc.fallback:
                raise
            await self.quick(ask, actor, exc.reason, end)
            return
        msg = (answer.get("choices") or [{}])[0].get("message") or {}
        data = parse_answer(msg.get("content"))
        if data is None:                             # D-182: not the JSON asked: the state, nothing run
            self._recourse(ask, "json_invalid", False)
            ask["answer"] = "Non ho capito la risposta dell'assistente: non ho eseguito niente. " + self.state_text()
            if ask["status"] == "pending":
                ask["status"] = "answered"
            return
        text = data["risposta"].strip()
        proposals: list[dict] = []
        errors: list[str] = []
        for action in data["azioni"]:
            name, args = as_tool(action)
            result = self.tool(name, args, proposals)     # the same checks as before (limits, devices, time)
            if "errore" in result:
                errors.append(f"Non fatto: {result['errore']}.")
        lines = errors + await self.apply(proposals, ask, actor, until=end - 1.0)
        ask["answer"] = "\n".join([t for t in [text, *lines] if t]) or "Non lo so: guarda nell'app."
        if ask["status"] == "pending":
            ask["status"] = "answered"

    def messages(self, text: str) -> list[dict]:
        """The request (D-182): the system prompt with the state, the recent decisions and the planned actions, then the
        question. The same function feeds scripts/measure_model.py."""
        from .core import utcnow
        tz = ZoneInfo(self.e.timezone)
        now = utcnow().astimezone(tz).strftime("%Y-%m-%d %H:%M")
        state = json.dumps(local_times({
            "appartamento": self.tool("leggi_appartamento", {}, []),
            **self.tool("leggi_dispositivi", {}, []),
            "decisioni_recenti": self.rule_names(self.tool("leggi_decisioni", {"quante": 10}, []).get("decisioni", [])),
            "programmazioni": self.tool("leggi_programmazioni", {}, []).get("programmazioni", [])}, tz),
            ensure_ascii=False, default=str)
        return [{"role": "system", "content": SYSTEM_PROMPT.format(now=now, tz=self.e.timezone, state=state)},
                {"role": "user", "content": text}]

    # ---- D-182 layer 3: the quick assistant ------------------------------------------------------------------------
    QUICK_FOOTER = {"timeout": "Risposta rapida: l'assistente completo non ha risposto in tempo.",
                    "model_unavailable": "Risposta rapida: l'assistente completo non è raggiungibile ora.",
                    "monthly_cap": "Risposta rapida: l'assistente completo ha raggiunto il limite mensile."}

    def _recourse(self, ask: dict, cause: str, command: bool) -> None:
        """D-182 point 4: every recourse with its cause, in the engine's log and in the ask's reason (not shown by the
        site for an answered question; the BFF can count it)."""
        from . import log
        log.warn("assistant fallback", apartment_id=self.e.apartment_id, cause=cause, command=command)
        ask["reason"] = f"risposta_rapida:{cause}"

    def quick_proposal(self, text: str, proposals: list[dict]) -> bool:
        """D-167/D-182: a command only for an unequivocal phrase: a verb and one device (by kind, room or name) or a
        mode, no negation, no condition, no time. True when a proposal was made (checked by the usual validators)."""
        import re
        t = " " + re.sub(r"\s+", " ", text.lower().replace("'", " ")) + " "
        if re.search(r"\b(non|no|mai|niente|nessun[oa]?|se|quando|appena|dopo|prima|alle|entro|tra|fra|finché|ogni)\b", t):
            return False
        number = re.search(r"\b(\d{1,2}(?:[.,]\d)?)\s*(?:gradi|°)", t)
        off = re.search(r"\b(spegni|disattiva)\b", t)
        on = re.search(r"\b(accendi|attiva)\b", t)
        set_to = re.search(r"\b(porta|metti|imposta)\b", t)
        mode = re.search(r"\b(comfort|eco|casa vuota)\b", t)
        if mode and set_to and not number and not off and not on:
            m = {"comfort": "comfort", "eco": "eco", "casa vuota": "empty"}[mode.group(1)]
            return "errore" not in self.tool("cambia_modalita", {"modalita": m}, proposals)
        kinds = [cap for cap, words in (("climate", r"\b(clima|climatizzatore|condizionatore|split)\b"),
                                        ("heating", r"\b(caldaia|riscaldamento|termosifoni?)\b"),
                                        ("switch", r"\b(presa|prese|stufetta|luce)\b")) if re.search(words, t)]
        if len(kinds) > 1 or sum(bool(x) for x in (off, on, number)) != 1:
            return False
        rooms = {r["room_id"] for r in self.e.rooms if f" {r['name'].lower()} " in t}
        candidates = []
        for d in self.e.devices.values():
            caps = [c for c in ("climate", "heating", "switch") if c in d["capabilities"]]
            if not caps or not d["online"] or (kinds and kinds[0] not in caps):
                continue
            if rooms and d["room_id"] not in rooms:
                continue
            candidates.append((d, kinds[0] if kinds else caps[0]))
        if not kinds and number:                          # «porta il soggiorno a 21 gradi»: the room's climate
            candidates = [(d, c) for d, c in candidates if c == "climate"]
        if len(candidates) != 1 or (not kinds and not rooms):
            return False
        device, cap = candidates[0]
        if number:
            if cap == "switch" or not set_to:
                return False
            setpoint = float(number.group(1).replace(",", "."))
            action = "set_climate" if cap == "climate" else "set_heating"
            body = {"capability": cap, "action": action, "params": {"on": True, "setpoint": setpoint}}
        elif off:
            body = {"capability": cap, "action": "turn_off", "params": {}}
        else:
            body = ({"capability": "switch", "action": "turn_on", "params": {}} if cap == "switch" else
                    {"capability": cap, "action": "set_climate" if cap == "climate" else "set_heating",
                     "params": {"on": True}})
        return "errore" not in self.tool("comanda_dispositivo", {"device_id": device["device_id"], **body}, proposals)

    async def quick(self, ask: dict, actor: str, cause: str, end: float) -> None:
        """The answer when the model does not give one (D-182 layer 3): the unequivocal command, through the usual
        approvals; otherwise the state and the app's controls. Never «non sono riuscito» alone."""
        proposals: list[dict] = []
        command = self.quick_proposal(ask["text"], proposals)
        self._recourse(ask, cause, command)
        footer = self.QUICK_FOOTER.get(cause, self.QUICK_FOOTER["model_unavailable"])
        if command:
            lines = await self.apply(proposals, ask, actor, until=end - 1.0)
            ask["answer"] = "\n".join([*lines, footer])
        else:
            ask["answer"] = f"{self.state_text()} Per i comandi usa i pulsanti dell'app.\n{footer}"
        if ask["status"] == "pending":
            ask["status"] = "answered"

    def rule_names(self, decisions: list[dict]) -> list[dict]:
        """D-187: a decision of a rule shows its Italian name («regola «Finestra aperta spegne il clima»»), never its
        internal code (rule:window_open_off): the model then has no code to cite."""
        names = {r["rule_id"]: r["label"] for r in self.e.rules}
        out = []
        for d in decisions:
            actor = d.get("actor") or ""
            if actor.startswith("rule:"):
                d = {**d, "actor": f"regola «{names.get(actor[5:], actor[5:])}»"}
            out.append(d)
        return out

    def state_text(self) -> str:
        """The apartment in plain words: mode, occupancy, what is on, the temperatures."""
        apt = self.e.apartment()
        on, temps = [], []
        for d in self.e.devices.values():
            caps = d["capabilities"]
            for cap in ("climate", "heating", "switch"):
                if caps.get(cap, {}).get("on"):
                    sp = caps[cap].get("setpoint")
                    on.append(d["label"] + (f" ({fmt_c(sp)})" if cap != "switch" and sp is not None else ""))
            if isinstance(caps.get("temperature", {}).get("celsius"), (int, float)):
                temps.append(f"{d['label']} {fmt_c(caps['temperature']['celsius'])}")
        occupancy = {"occupied": "occupato", "reserved": "prenotato", "vacant": "vuoto"}.get(apt.get("occupancy"),
                                                                                             apt.get("occupancy"))
        parts = [f"Modalità {MODE_NAMES.get(apt.get('mode'), apt.get('mode'))}, appartamento {occupancy}."]
        parts.append(f"Accesi: {', '.join(on)}." if on else "Nessun dispositivo acceso.")
        if temps:
            parts.append(f"Temperature: {', '.join(temps)}.")
        return " ".join(parts)

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
                action, params = clean_command(args.get("capability"), args.get("action"), args.get("params") or {})
                body = {"capability": args.get("capability"), "action": action, "params": params}
                e.validate_command(device, body)
                proposals.append({"type": "command", "device_id": device["device_id"], "body": body})
                return {"registrato": f"comando {body['action']} a {device['label']}"}
            if name == "programma":
                when = self._when(args.get("quando"))
                if args.get("modalita"):
                    action = {"type": "apartment_mode", "mode": args["modalita"]}
                else:
                    device = e.get_device(args.get("device_id", ""))
                    action, params = clean_command(args.get("capability"), args.get("action"), args.get("params") or {})
                    body = {"capability": args.get("capability"), "action": action, "params": params}
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

    def schedule_question(self, what: str) -> str:
        """D-170: a scheduled action that will find guests in."""
        return (f"Programmo {what}, con ospiti presenti a quell'ora? Rispondi Sì o No qui sotto, oppure dalla pagina "
                f"Approvazioni.")

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

    def _touches_comfort_at(self, p: dict) -> bool:
        """D-170: guests in at the action's time and a mode, or a climate or a boiler switched off."""
        from .core import parse_dt
        if not self.e.occupied_at(parse_dt(p["run_at"])):
            return False
        a = p["action"]
        if a["type"] == "apartment_mode":
            return True
        device = self.e.devices.get(a.get("device_id", ""))
        if not device:
            return False
        cap, action, params = self.e.validate_command(device, a)
        return cap in ("climate", "heating") and not self.e.target_state(device, cap, action, params).get("on")

    def needs_approval(self, p: dict, together: bool) -> bool:
        """D-132 point 2: with guests in, the guest's comfort (switching off a climate or a boiler, the mode); and any
        action together with others (one approval each, D-144). D-162: the setting ASSISTANT_CONFIRM, «ospiti» (this,
        the default), «sempre» (every action), «multiple» (only actions together)."""
        policy = self.e.setting("ASSISTANT_CONFIRM")
        if p["type"] == "schedule":
            # D-170: a scheduled action, by the calendar at its time (the same rule as an immediate one on the guests'
            # comfort); with «multiple» and «sempre» as before: scheduled actions do not ask
            return policy == "ospiti" and self._touches_comfort_at(p)
        if policy == "sempre":
            return True
        if together:
            return True
        if policy == "multiple":
            return False
        if self.e.apartment().get("occupancy") != "occupied":
            return False
        if p["type"] == "mode":
            return True
        device = self.e.devices[p["device_id"]]
        cap, action, params = self.e.validate_command(device, p["body"])
        return cap in ("climate", "heating") and not self.e.target_state(device, cap, action, params).get("on")

    async def apply(self, proposals: list[dict], ask: dict, actor: str, until: float | None = None) -> list[str]:
        """Runs the proposals; waits for the commands' outcome at most ACK_WAIT_S and never beyond `until` (C-10: a
        command not final by then is announced as sent, its outcome arrives in the app)."""
        from .core import FINAL, MockError
        e = self.e
        corr, why = ask["correlation_id"], f"Richiesta all'assistente: «{ask['text']}»"
        together = len([p for p in proposals if p["type"] != "schedule"]) >= 2
        lines, waiting = [], []
        for p in proposals:
            what = self.describe(p)
            try:
                if self.needs_approval(p, together):
                    if p["type"] == "schedule":           # D-170: the action, its time kept aside by the engine
                        proposed = p["action"]
                        description = f"Programmare {what}"
                    else:
                        proposed = ({"type": "apartment_mode", "mode": p["mode"]} if p["type"] == "mode" else
                                    {"type": "device_command", "device_id": p["device_id"], **p["body"]})
                        description = what[0].upper() + what[1:]
                    opened = e._new_approval("assistant", description, why, proposed, "reject", corr)
                    approval = opened or e.approval_queue[-1]
                    if p["type"] == "schedule":
                        e.schedule_approval(approval["approval_id"], p["run_at"])
                    if ask["approval_id"] is None:
                        ask["approval_id"] = approval["approval_id"]
                        ask["status"] = "needs_approval"
                    lines.append(self.schedule_question(what) if p["type"] == "schedule" else self.question(what))
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
        if until is not None:
            deadline = min(deadline, until)
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

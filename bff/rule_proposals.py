"""Rules proposed by the assistant and confirmed by the manager (P-60 step 12, D-133 point 3, D-151).

The manager writes in the Rules page what to change («la finestra aperta spegne dopo 10 minuti»); the BFF reads the
apartment's GET /rules, asks the model for a structured proposal (one tool, «proponi_modifiche»), checks every value
against the rule's limits and editability, and answers the changes with old and new value. Nothing changes until the
manager presses «Applica»: then apply() checks again, refuses with 409 when the rules changed in the meantime (their
updated_at) and sends PUT /rules with the manager's pseudonym, so the engine records the decision under their name;
the BFF writes «regole modificate» in the activity log. The proposal is not stored: the site keeps it until the click.

The model: through bff/ai_gateway.py (monthly cap, prices, 80 % alert). On a demonstration apartment without AI_DEMOS a
simple recognizer of Italian phrases answers instead (D-151 point 21): enough for the tests and the checklist.
Lot 29 (a proposal over the gateway's 25 s in staging): a simple phrase, one rule and one value, is answered by the
recognizer everywhere, with no model call; the model gets only the editable rules, one line each, and one flat tool
(rule, parameter, number: no object with free keys); its call has PROPOSAL_TIMEOUT_S, then a clear answer.
At most DAILY_LIMIT proposals a day per apartment (the apartment's local day), counted before the model is asked.

Every rule and parameter comes from the engine's GET /rules: the contract's Rule.params admits further numeric
parameters (additionalProperties: number), so presence_minutes of checkout_eco (D-151) needs nothing here.
"""
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

DAILY_LIMIT = 20
TEXT_MAX = 500
PROPOSAL_TIMEOUT_S = 15.0     # lot 29: the model's call for a proposal; then «L'assistente non ha risposto in tempo…»
TIMEOUT_MESSAGE = ("L'assistente non ha risposto in tempo: riprova con una frase più breve, oppure cambia la regola a "
                   "mano qui sotto.")
ENABLED_FIELD = "attiva"      # the tool's name for on/off: valore 1 = attiva, 0 = spenta

# the predefined values (the contract's example of GET /rules, the engine's DEFAULT_RULES), for «regole personalizzate»
DEFAULTS = {
    "window_open_off": {"enabled": True, "minutes": 5},
    "setpoint_limits": {"enabled": True, "min": 16, "max": 24, "comfort_celsius": 21, "eco_celsius": 18,
                        "comfort_cool_celsius": 25},
    "frost_protection": {"enabled": True, "celsius": 8},
    "mold_protection": {"enabled": True, "humidity_percent": 65},
    "prearrival": {"enabled": True, "hours_before": 2},
    "checkout_eco": {"enabled": True, "minutes_after": 30, "presence_minutes": 30},
    "offline_alert": {"enabled": True, "minutes": 15},
}

# what each rule and parameter means, for the model (the same words as the site's Rules page)
MEANING = {
    "window_open_off": "spegne clima e caldaia se una finestra resta aperta più di minutes minuti",
    "setpoint_limits": ("limita la temperatura impostabile da ospiti e app: da min a max gradi; in comfort la caldaia "
                        "e il clima scaldano a comfort_celsius, il clima raffresca a comfort_cool_celsius; in eco la "
                        "caldaia sta a eco_celsius"),
    "frost_protection": "con la casa vuota mantiene almeno celsius gradi",
    "mold_protection": "con la casa vuota deumidifica sopra humidity_percent di umidità",
    "prearrival": "porta la casa in comfort hours_before ore prima dell'arrivo degli ospiti",
    "checkout_eco": ("passa a casa vuota minutes_after minuti dopo il check-out; se il sensore di movimento ha visto "
                     "qualcuno negli ultimi presence_minutes minuti dopo l'orario di partenza, chiede prima al gestore"),
    "compressor_min_off": "pausa minima del compressore (non modificabile)",
    "offline_alert": "avvisa quando un dispositivo resta offline più di minutes minuti",
}


class ProposalError(Exception):
    def __init__(self, status: int, error: str, message: str):
        super().__init__(message)
        self.status, self.error, self.message = status, error, message


def _num(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def fmt(v) -> str:
    if isinstance(v, bool):
        return "attiva" if v else "spenta"
    return f"{v:g}".replace(".", ",") if isinstance(v, (int, float)) else str(v)


def changes(ruleset: dict, patches: list) -> tuple[list[dict], list[dict]]:
    """(the RulePatch list without the values already equal, the changes with old and new value). Raises
    ProposalError 422 with an Italian message on an unknown rule or parameter, a rule not editable, a value out of
    its limits, a setpoint minimum over the maximum: the same checks as the engine's PUT /rules."""
    if not isinstance(patches, list):
        raise ProposalError(422, "bad_request", "rules deve essere un elenco")
    by_id = {r["rule_id"]: r for r in ruleset.get("rules") or []}
    clean, out = [], []
    after = {rid: dict(r["params"]) for rid, r in by_id.items()}
    for p in patches:
        if not isinstance(p, dict) or p.get("rule_id") not in by_id:
            raise ProposalError(422, "unknown_rule", f"Regola inesistente: {p.get('rule_id') if isinstance(p, dict) else p}")
        rule = by_id[p["rule_id"]]
        if not rule["editable"]:
            raise ProposalError(422, "rule_not_editable", f"La regola «{rule['label']}» non è modificabile")
        patch: dict = {}
        if "enabled" in p and p["enabled"] is not None:
            if not isinstance(p["enabled"], bool):
                raise ProposalError(422, "bad_request", "enabled deve essere vero o falso")
            if p["enabled"] != rule["enabled"]:
                patch["enabled"] = p["enabled"]
                out.append({"rule_id": rule["rule_id"], "label": rule["label"], "field": "enabled",
                            "old": rule["enabled"], "new": p["enabled"]})
        for key, value in (p.get("params") or {}).items():
            lim = rule["limits"].get(key)
            if lim is None:
                raise ProposalError(422, "unknown_param", f"«{rule['label']}»: parametro inesistente {key}")
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not lim["min"] <= value <= lim["max"]:
                raise ProposalError(422, "param_out_of_range",
                                    f"«{rule['label']}»: il valore deve essere tra {fmt(lim['min'])} e {fmt(lim['max'])}")
            value = _num(value)
            after[rule["rule_id"]][key] = value
            if value != rule["params"].get(key):
                patch.setdefault("params", {})[key] = value
                out.append({"rule_id": rule["rule_id"], "label": rule["label"], "field": key,
                            "old": rule["params"].get(key), "new": value})
        if patch:
            clean.append({"rule_id": rule["rule_id"], **patch})
    sl = after.get("setpoint_limits")
    if sl and sl["min"] > sl["max"]:
        raise ProposalError(422, "invalid_range", "Il minimo del setpoint non può superare il massimo")
    # D-161/D-162, the engine's own checks (lot 30): a proposal never shows a change that «Applica» would refuse
    if sl and "eco_celsius" in sl and "comfort_celsius" in sl and sl["eco_celsius"] > sl["comfort_celsius"]:
        raise ProposalError(422, "invalid_range", "La temperatura eco non può superare quella comfort")
    if sl and "comfort_celsius" in sl and "comfort_cool_celsius" in sl and sl["comfort_celsius"] >= sl["comfort_cool_celsius"]:
        raise ProposalError(422, "invalid_range", "La temperatura di raffrescamento deve essere più alta di quella comfort")
    return clean, out


def customized(ruleset: dict) -> list[dict]:
    """The editable values that differ from the predefined ones (D-151 point 22 d)."""
    out = []
    for r in ruleset.get("rules") or []:
        base = DEFAULTS.get(r["rule_id"])
        if not base or not r["editable"]:
            continue
        for field, default in base.items():
            value = r["enabled"] if field == "enabled" else r["params"].get(field)
            if value is not None and value != default:
                out.append({"rule_id": r["rule_id"], "label": r["label"], "field": field, "value": value,
                            "default": default})
    return out


# ---- the model ------------------------------------------------------------------------------------------------------
SYSTEM_PROMPT = """Sei l'assistente di DOMHOUSE per le regole automatiche di un appartamento in affitto breve.
Il gestore ti scrive in italiano che cosa vuole cambiare. Rispondi SOLO con un oggetto JSON, senza altro testo e senza
blocchi di codice:
{{"modifiche": [{{"rule_id": "<id>", "parametro": "<nome del parametro, oppure attiva>", "valore": <numero>}}],
 "spiegazione": "<frase breve in italiano per il gestore>"}}
Per «attiva» il valore è 1 per accendere la regola e 0 per spegnerla. Regole fisse:
1. Usa solo le regole e i parametri dell'elenco, dentro i loro limiti. Non inventare regole nuove.
2. Se la richiesta non riguarda queste regole, è fuori dai limiti o non è chiara: «modifiche» vuoto e nella
   spiegazione che cosa si può fare (per esempio «Il massimo per questa regola è 30 minuti»).
3. Solo le regole da cambiare.
Regole modificabili dell'appartamento (rule_id «nome»: significato; stato; parametri con valore e limiti):
{rules}"""

def prompt(ruleset: dict) -> str:
    """Only the editable rules, one short line each (lot 29)."""
    lines = []
    for r in ruleset.get("rules") or []:
        if not r["editable"]:
            continue
        params = ", ".join(f"{k}={fmt(v)} (da {fmt(r['limits'][k]['min'])} a {fmt(r['limits'][k]['max'])})"
                           for k, v in r["params"].items() if k in r["limits"])
        lines.append(f"- {r['rule_id']} «{r['label']}»: {MEANING.get(r['rule_id'], '')}; "
                     f"{'attiva' if r['enabled'] else 'spenta'}; {params}")
    return SYSTEM_PROMPT.format(rules="\n".join(lines))


def _json_object(text: str) -> dict | None:
    """The JSON object of an answer, also inside a ```json block; None when there is none."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
        raw = raw.rsplit("```", 1)[0].strip()
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def from_answer(answer: dict) -> tuple[list | None, str]:
    """(the proposed patches or None, the explanation or the model's sentence). D-182: the proposal is the JSON object
    of the text (a tool call, if a model still makes one, is read the same way). The flat rows (rule, parameter, number)
    become RulePatch: «attiva» 1/0 -> enabled true/false, any other parameter -> params."""
    msg = ((answer.get("choices") or [{}])[0]).get("message") or {}
    args = None
    for call in msg.get("tool_calls") or []:
        fn = call.get("function") or {}
        if fn.get("name") == "proponi_modifiche":
            args = _json_object(fn.get("arguments") or "{}") or {}
    if args is None:
        args = _json_object(msg.get("content") or "")
    if args is not None:
        if not isinstance(args.get("modifiche", []), list):
            return None, "Non ho capito la richiesta: prova a scriverla in un altro modo."
        by_rule: dict[str, dict] = {}
        for row in args.get("modifiche") or []:
            if not isinstance(row, dict) or not isinstance(row.get("rule_id"), str):
                continue
            patch = by_rule.setdefault(row["rule_id"], {"rule_id": row["rule_id"]})
            if row.get("parametro") == ENABLED_FIELD:
                patch["enabled"] = bool(row.get("valore"))
            elif isinstance(row.get("parametro"), str):
                patch.setdefault("params", {})[row["parametro"]] = row.get("valore")
        said = str(args.get("spiegazione") or "").strip()
        if not by_rule:                          # nothing proposed: the model's sentence says why
            return None, said or "Non ho capito la richiesta: prova a scriverla in un altro modo."
        return list(by_rule.values()), said
    return None, str(msg.get("content") or "").strip() or "Non ho capito la richiesta: prova a scriverla in un altro modo."


# ---- the recognizer for the demonstrations without the model -------------------------------------------------------
_NUM = r"(\d+(?:[.,]\d+)?)"
AMBIGUOUS_TEMPERATURE = ("È la temperatura comfort, eco, di raffrescamento o un limite (minimo o massimo)? Scrivilo, per "
                         "esempio «comfort 22» o «massimo 24».")
_RULE_WORDS = (("window_open_off", ("finestr",)), ("frost_protection", ("antigelo", "gelo")),
               ("mold_protection", ("muffa", "umidit")), ("prearrival", ("arrivo",)),
               ("checkout_eco", ("check-out", "checkout", "partenza")), ("offline_alert", ("offline",)),
               ("setpoint_limits", ("setpoint", "temperatura", "comfort", " eco", "raffresc")))


def simple(text: str) -> bool:
    """Lot 29: one rule named, at most one number (two for the setpoint's range): the recognizer answers, no model."""
    t = text.lower()
    named = [rule for rule, words in _RULE_WORDS if any(w in t for w in words)]
    if len(named) != 1:
        return False
    numbers = len(re.findall(_NUM, t))
    return numbers <= (2 if named[0] == "setpoint_limits" else 1)


def recognize(text: str, ruleset: dict) -> tuple[list | None, str]:
    """A few Italian phrases, one rule at a time: «finestra 10 minuti», «antigelo 9 gradi», «umidità 70», «pre-arrivo
    3 ore», «check-out 45 minuti», «presenza al check-out 60 minuti», «offline 30 minuti», «setpoint da 17 a 25»,
    «spegni/attiva la regola …»."""
    t = text.lower()
    n = [float(x.replace(",", ".")) for x in re.findall(_NUM, t)]
    rule, key = None, None
    if "finestr" in t:
        rule, key = "window_open_off", "minutes"
    elif "antigelo" in t or "gelo" in t:
        rule, key = "frost_protection", "celsius"
    elif "muffa" in t or "umidit" in t:
        rule, key = "mold_protection", "humidity_percent"
    elif "arrivo" in t:
        rule, key = "prearrival", "hours_before"
    elif "check-out" in t or "checkout" in t or "partenza" in t:
        rule, key = ("checkout_eco", "presence_minutes") if ("presenza" in t or "movimento" in t) else \
            ("checkout_eco", "minutes_after")
    elif "offline" in t:
        rule, key = "offline_alert", "minutes"
    elif "setpoint" in t or "temperatura" in t or "comfort" in t or "raffresc" in t or re.search(r"\beco\b", t):
        rule = "setpoint_limits"
    if rule is None:
        return None, ("Posso cambiare le regole della pagina: finestra aperta, limiti del setpoint, antigelo, "
                      "antimuffa, pre-arrivo, risparmio al check-out, avviso offline.")
    if re.search(r"\b(spegn|disattiv|togli)", t):
        return [{"rule_id": rule, "enabled": False}], "Spengo la regola."
    if re.search(r"\b(attiv|accend|riattiv)", t) and not n:
        return [{"rule_id": rule, "enabled": True}], "Attivo la regola."
    if rule == "setpoint_limits" and n and len(n) == 1:              # D-161: the modes' temperatures
        if "raffresc" in t:
            return [{"rule_id": rule, "params": {"comfort_cool_celsius": _num(n[0])}}], "Cambio il raffrescamento in comfort."
        if "comfort" in t:
            return [{"rule_id": rule, "params": {"comfort_celsius": _num(n[0])}}], "Cambio la temperatura comfort."
        if re.search(r"\beco\b", t):
            return [{"rule_id": rule, "params": {"eco_celsius": _num(n[0])}}], "Cambio la temperatura eco."
    if rule == "setpoint_limits":
        if len(n) >= 2:
            return [{"rule_id": rule, "params": {"min": _num(min(n[:2])), "max": _num(max(n[:2]))}}], \
                "Cambio i limiti del setpoint."
        if n and "min" in t:
            return [{"rule_id": rule, "params": {"min": _num(n[0])}}], "Cambio il minimo del setpoint."
        if n and "mass" in t:
            return [{"rule_id": rule, "params": {"max": _num(n[0])}}], "Cambio il massimo del setpoint."
        if n:                                     # lot 30: «temperatura 22» alone is not a limit, ask which one
            return None, AMBIGUOUS_TEMPERATURE
    elif n:
        return [{"rule_id": rule, "params": {key: _num(n[0])}}], "Cambio il valore della regola."
    return None, "Scrivi anche il valore, per esempio «finestra aperta 10 minuti»."


def local_day(tz: str) -> str:
    return datetime.now(ZoneInfo(tz)).date().isoformat()

"""Rules proposed by the assistant and confirmed by the manager (P-60 step 12, D-133 point 3, D-151).

The manager writes in the Rules page what to change («la finestra aperta spegne dopo 10 minuti»); the BFF reads the
apartment's GET /rules, asks the model for a structured proposal (one tool, «proponi_modifiche»), checks every value
against the rule's limits and editability, and answers the changes with old and new value. Nothing changes until the
manager presses «Applica»: then apply() checks again, refuses with 409 when the rules changed in the meantime (their
updated_at) and sends PUT /rules with the manager's pseudonym, so the engine records the decision under their name;
the BFF writes «regole modificate» in the activity log. The proposal is not stored: the site keeps it until the click.

The model: through bff/ai_gateway.py (monthly cap, prices, 80 % alert). On a demonstration apartment without AI_DEMOS a
simple recognizer of Italian phrases answers instead (D-151 point 21): enough for the tests and the checklist.
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

# the predefined values (the contract's example of GET /rules, the engine's DEFAULT_RULES), for «regole personalizzate»
DEFAULTS = {
    "window_open_off": {"enabled": True, "minutes": 5},
    "setpoint_limits": {"enabled": True, "min": 16, "max": 24},
    "frost_protection": {"enabled": True, "celsius": 8},
    "mold_protection": {"enabled": True, "humidity_percent": 65},
    "prearrival": {"enabled": True, "hours_before": 2},
    "checkout_eco": {"enabled": True, "minutes_after": 30, "presence_minutes": 30},
    "offline_alert": {"enabled": True, "minutes": 15},
}

# what each rule and parameter means, for the model (the same words as the site's Rules page)
MEANING = {
    "window_open_off": "spegne clima e caldaia se una finestra resta aperta più di minutes minuti",
    "setpoint_limits": "limita la temperatura impostabile da ospiti e app: da min a max gradi",
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
Il gestore ti scrive in italiano che cosa vuole cambiare. Tu proponi le modifiche chiamando lo strumento
proponi_modifiche, una volta sola, con solo le regole da cambiare. Regole fisse:
1. Usa solo le regole e i parametri dell'elenco, dentro i loro limiti. Non inventare regole nuove.
2. Se la richiesta non riguarda queste regole, è fuori dai limiti o non è chiara, non chiamare lo strumento:
   rispondi in una frase che cosa si può fare (per esempio «Il massimo per questa regola è 30 minuti»).
3. La spiegazione è una frase breve in italiano per il gestore.
Regole dell'appartamento (rule_id, nome, significato, attiva, parametri, limiti):
{rules}"""

TOOL = {"type": "function", "function": {
    "name": "proponi_modifiche",
    "description": "Propone al gestore le modifiche alle regole; si applicano solo se lui conferma.",
    "parameters": {"type": "object", "required": ["modifiche", "spiegazione"], "properties": {
        "modifiche": {"type": "array", "items": {"type": "object", "required": ["rule_id"], "properties": {
            "rule_id": {"type": "string"},
            "enabled": {"type": "boolean", "description": "true per attivare la regola, false per spegnerla"},
            "params": {"type": "object", "additionalProperties": {"type": "number"}}}}},
        "spiegazione": {"type": "string"}}}}}


def prompt(ruleset: dict) -> str:
    lines = []
    for r in ruleset.get("rules") or []:
        lines.append(json.dumps({"rule_id": r["rule_id"], "nome": r["label"], "significato": MEANING.get(r["rule_id"], ""),
                                 "attiva": r["enabled"], "modificabile": r["editable"], "parametri": r["params"],
                                 "limiti": r["limits"]}, ensure_ascii=False))
    return SYSTEM_PROMPT.format(rules="\n".join(lines))


def from_answer(answer: dict) -> tuple[list | None, str]:
    """(the proposed patches or None, the explanation or the model's sentence)."""
    msg = ((answer.get("choices") or [{}])[0]).get("message") or {}
    for call in msg.get("tool_calls") or []:
        fn = call.get("function") or {}
        if fn.get("name") == "proponi_modifiche":
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                return None, "Non ho capito la richiesta: prova a scriverla in un altro modo."
            return args.get("modifiche") or [], str(args.get("spiegazione") or "").strip()
    return None, str(msg.get("content") or "").strip() or "Non ho capito la richiesta: prova a scriverla in un altro modo."


# ---- the recognizer for the demonstrations without the model -------------------------------------------------------
_NUM = r"(\d+(?:[.,]\d+)?)"


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
    elif "setpoint" in t or "temperatura" in t:
        rule = "setpoint_limits"
    if rule is None:
        return None, ("Posso cambiare le regole della pagina: finestra aperta, limiti del setpoint, antigelo, "
                      "antimuffa, pre-arrivo, risparmio al check-out, avviso offline.")
    if re.search(r"\b(spegn|disattiv|togli)", t):
        return [{"rule_id": rule, "enabled": False}], "Spengo la regola."
    if re.search(r"\b(attiv|accend|riattiv)", t) and not n:
        return [{"rule_id": rule, "enabled": True}], "Attivo la regola."
    if rule == "setpoint_limits":
        if len(n) >= 2:
            return [{"rule_id": rule, "params": {"min": _num(min(n[:2])), "max": _num(max(n[:2]))}}], \
                "Cambio i limiti del setpoint."
        if n and "min" in t:
            return [{"rule_id": rule, "params": {"min": _num(n[0])}}], "Cambio il minimo del setpoint."
        if n:
            return [{"rule_id": rule, "params": {"max": _num(n[0])}}], "Cambio il massimo del setpoint."
    elif n:
        return [{"rule_id": rule, "params": {key: _num(n[0])}}], "Cambio il valore della regola."
    return None, "Scrivi anche il valore, per esempio «finestra aperta 10 minuti»."


def local_day(tz: str) -> str:
    return datetime.now(ZoneInfo(tz)).date().isoformat()

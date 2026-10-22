"""Vertex's own generateContent behind the BFF's model gateway (D-182: gemini-3.8-flash, location eu, native endpoint,
reasoning off): the engine and the rules' proposals keep speaking the OpenAI-compatible chat format to the BFF; this
module translates the request to Vertex's native format and the answer back. The host of a multi-region is Google's
aiplatform.<eu|us>.rep.googleapis.com (docs: vertex-ai/generative-ai/docs/learn/locations).

Request: the system message -> systemInstruction; user messages -> contents (role user); an assistant message with
tool calls -> role model with functionCall parts (the thoughtSignature Gemini returned is sent back, as it requires);
tool messages -> functionResponse parts (consecutive ones in one user turn); tools -> functionDeclarations (an object
without properties gets the command's fields); temperature, max_tokens and reasoning_effort -> generationConfig
(thinkingConfig.thinkingLevel). Answer: text parts -> content, functionCall parts -> tool_calls (with the signature
kept in the tool call, so the engine echoes it back untouched), finishReason -> finish_reason, usageMetadata -> usage
(total includes the reasoning, as the prices expect).
"""
import json

PARAMS_FIELDS = {"type": "object", "properties": {
    "on": {"type": "boolean"}, "mode": {"type": "string", "description": "cool, heat, dry, fan"},
    "setpoint": {"type": "number"}, "fan": {"type": "string", "description": "auto, low, mid, high"}}}
FINISH = {"STOP": "stop", "MAX_TOKENS": "length", "SAFETY": "content_filter", "RECITATION": "content_filter"}
def host(location: str) -> str:
    if location in ("eu", "us"):
        return f"aiplatform.{location}.rep.googleapis.com"
    if location == "global":
        return "aiplatform.googleapis.com"
    return f"{location}-aiplatform.googleapis.com"


def url(project: str, location: str, model: str) -> str:
    host_ = host(location)
    return (f"https://{host_}/v1/projects/{project}/locations/{location}/publishers/google/models/"
            f"{model.split('/')[-1]}:generateContent")


def schema(s: dict) -> dict:
    out = dict(s)
    out.pop("additionalProperties", None)
    if out.get("type") == "object" and not out.get("properties"):
        return dict(PARAMS_FIELDS)
    if "properties" in out:
        out["properties"] = {k: schema(v) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = schema(out["items"])
    return out


def _args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _response(content) -> dict:
    try:
        value = json.loads(content) if isinstance(content, str) else content
    except ValueError:
        value = content
    return value if isinstance(value, dict) else {"content": value}


def request(body: dict, thinking_budget: int | None = None) -> dict:
    """An OpenAI chat body (messages, tools, temperature, max_tokens, reasoning_effort) -> a generateContent body;
    thinking_budget (D-182: 0, reasoning off) wins over reasoning_effort."""
    out: dict = {"contents": [], "generationConfig": {}}
    names: dict[str, str] = {}                  # tool_call id -> function name, for the functionResponse
    pending: list[dict] = []                    # functionResponse parts waiting to be one user turn

    def flush():
        if pending:
            out["contents"].append({"role": "user", "parts": list(pending)})
            pending.clear()
    for m in body.get("messages") or []:
        role = m.get("role")
        if role == "system":
            out["systemInstruction"] = {"parts": [{"text": m.get("content") or ""}]}
        elif role == "tool":
            pending.append({"functionResponse": {"name": names.get(m.get("tool_call_id", ""), "strumento"),
                                                 "response": _response(m.get("content"))}})
        else:
            flush()
            if role == "assistant":
                parts = [{"text": m["content"]}] if m.get("content") else []
                for call in m.get("tool_calls") or []:
                    fn = call.get("function") or {}
                    names[call.get("id", "")] = fn.get("name", "")
                    part = {"functionCall": {"name": fn.get("name", ""), "args": _args(fn.get("arguments"))}}
                    if call.get("thought_signature"):
                        part["thoughtSignature"] = call["thought_signature"]
                    parts.append(part)
                out["contents"].append({"role": "model", "parts": parts or [{"text": ""}]})
            else:
                out["contents"].append({"role": "user", "parts": [{"text": m.get("content") or ""}]})
    flush()
    if body.get("tools"):
        out["tools"] = [{"functionDeclarations": [
            {"name": t["function"]["name"], "description": t["function"].get("description", ""),
             "parameters": schema(t["function"].get("parameters") or {"type": "object", "properties": {}})}
            for t in body["tools"]]}]
    gc = out["generationConfig"]
    if "temperature" in body:
        gc["temperature"] = body["temperature"]
    if body.get("max_tokens"):
        gc["maxOutputTokens"] = body["max_tokens"]
    if thinking_budget is not None and thinking_budget >= 0:
        gc["thinkingConfig"] = {"thinkingBudget": thinking_budget}
    elif body.get("reasoning_effort"):
        gc["thinkingConfig"] = {"thinkingLevel": body["reasoning_effort"]}
    return out


def answer(native: dict) -> dict:
    """A generateContent answer -> an OpenAI chat completion (choices[0].message, finish_reason, usage)."""
    cand = (native.get("candidates") or [{}])[0]
    texts, calls = [], []
    for i, part in enumerate((cand.get("content") or {}).get("parts") or []):
        if part.get("thought"):
            continue                                      # the reasoning's summary, never shown
        if "functionCall" in part:
            fc = part["functionCall"]
            call = {"id": f"call-{i}", "type": "function",
                    "function": {"name": fc.get("name", ""), "arguments": json.dumps(fc.get("args") or {},
                                                                                   ensure_ascii=False)}}
            if part.get("thoughtSignature"):
                call["thought_signature"] = part["thoughtSignature"]
            calls.append(call)
        elif part.get("text"):
            texts.append(part["text"])
    message = {"role": "assistant", "content": "".join(texts) or None}
    if calls:
        message["tool_calls"] = calls
    u = native.get("usageMetadata") or {}
    prompt = int(u.get("promptTokenCount") or 0)
    total = int(u.get("totalTokenCount") or 0) or prompt + int(u.get("candidatesTokenCount") or 0) \
        + int(u.get("thoughtsTokenCount") or 0)
    return {"choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if calls else FINISH.get(cand.get("finishReason"), "stop")}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": total - prompt, "total_tokens": total,
                      "prompt_tokens_details": {"cached_tokens": int(u.get("cachedContentTokenCount") or 0)},
                      "completion_tokens_details": {"reasoning_tokens": int(u.get("thoughtsTokenCount") or 0)}}}

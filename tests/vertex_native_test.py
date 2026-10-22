"""bff/vertex_native.py (D-182): the OpenAI-compatible chat the engine speaks, translated to Vertex's generateContent and
back: system, user, an assistant's function calls with the reasoning signature Gemini wants back, the tools' answers by
name, functionDeclarations with the command's fields, thinkingBudget 0, usage for the prices."""
import json

from bff import vertex_native as vn


def test_the_answer_back_in_the_engines_shape():
    native = {"candidates": [{"content": {"parts": [{"text": "Controllo. "}, {"thought": True, "text": "riflessione"},
                                                    {"functionCall": {"name": "leggi_dispositivi", "args": {}},
                                                     "thoughtSignature": "SIG"}]}, "finishReason": "STOP"}],
              "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 10, "thoughtsTokenCount": 40,
                                "totalTokenCount": 150}}
    a = vn.answer(native)
    msg = a["choices"][0]["message"]
    assert msg["content"] == "Controllo. " and a["choices"][0]["finish_reason"] == "tool_calls"   # never the reasoning
    assert msg["tool_calls"][0]["function"] == {"name": "leggi_dispositivi", "arguments": "{}"}
    assert msg["tool_calls"][0]["thought_signature"] == "SIG"
    assert (a["usage"]["prompt_tokens"], a["usage"]["completion_tokens"]) == (100, 50)          # reasoning paid as output
    assert vn.answer({"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]})["choices"][0][
        "finish_reason"] == "length"


def test_the_request_with_calls_tools_and_reasoning_off():
    body = {"messages": [{"role": "system", "content": "S"}, {"role": "user", "content": "q"},
                         {"role": "assistant", "content": "Controllo.", "tool_calls": [
                             {"id": "call-1", "type": "function", "thought_signature": "SIG",
                              "function": {"name": "leggi_dispositivi", "arguments": "{}"}}]},
                         {"role": "tool", "tool_call_id": "call-1", "content": json.dumps({"dispositivi": []})}],
            "tools": [{"type": "function", "function": {"name": "comanda_dispositivo", "parameters": {
                "type": "object", "properties": {"params": {"type": "object"}}}}}],
            "temperature": 0.2, "max_tokens": 4096, "reasoning_effort": "low"}
    r = vn.request(body, thinking_budget=0)
    assert r["systemInstruction"] == {"parts": [{"text": "S"}]}
    assert r["contents"][1] == {"role": "model", "parts": [{"text": "Controllo."}, {
        "functionCall": {"name": "leggi_dispositivi", "args": {}}, "thoughtSignature": "SIG"}]}
    assert r["contents"][2] == {"role": "user", "parts": [{"functionResponse": {"name": "leggi_dispositivi",
                                                                                "response": {"dispositivi": []}}}]}
    params = r["tools"][0]["functionDeclarations"][0]["parameters"]["properties"]["params"]
    assert set(params["properties"]) == {"on", "mode", "setpoint", "fan"}
    assert r["generationConfig"] == {"temperature": 0.2, "maxOutputTokens": 4096, "thinkingConfig": {"thinkingBudget": 0}}
    assert vn.request(body)["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}       # without a budget


def test_the_hosts():
    assert vn.url("p", "eu", "google/gemini-3.8-flash") == (
        "https://aiplatform.eu.rep.googleapis.com/v1/projects/p/locations/eu/publishers/google/models/gemini-3.8-flash:generateContent")
    assert vn.url("p", "europe-west1", "gemini-3.8-flash").startswith("https://europe-west1-aiplatform.googleapis.com/")

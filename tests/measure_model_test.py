"""scripts/measure_model.py (C-10, D-167) without the network: the engine's real request, every failure with its cause
(timeout, truncated by max_tokens, endpoint error), the summary with median, p95 and the estimated cost."""
import importlib.util
import json
from pathlib import Path

import httpx

from bff import ai_gateway

ROOT = Path(__file__).resolve().parent.parent


def _script():
    spec = importlib.util.spec_from_file_location("measure_model", ROOT / "scripts" / "measure_model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_request_is_the_engines_own():
    mm = _script()
    messages, tools = mm.request_messages("spegni il clima")
    assert messages[1] == {"role": "user", "content": "spegni il clima"}
    assert "Stato attuale dell'appartamento" in messages[0]["content"] and "dev-clima-soggiorno" in messages[0]["content"]
    assert {t["function"]["name"] for t in tools} >= {"comanda_dispositivo", "leggi_decisioni"}


def test_causes_and_summary(monkeypatch, capsys):
    mm = _script()
    usage = {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200}
    replies = [
        httpx.Response(200, json={"choices": [{"message": {"content": "Fatto."}, "finish_reason": "stop"}], "usage": usage}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}, "finish_reason": "length"}],
                                  "usage": {**usage, "completion_tokens_details": {"reasoning_tokens": 4096}}}),
        httpx.Response(429, text="Resource exhausted: quota"),
        "timeout",
    ]
    sent = []

    from bff import net_phase

    async def fake_post(url, json=None, headers=None, connect_s=None, read_s=None, network=None):
        sent.append(json)
        r = replies[(len(sent) - 1) % len(replies)]
        if r == "timeout":
            raise net_phase.PhaseFailure(net_phase.WAIT, True, 25.0, httpx.ReadTimeout("lento"))
        if network is not None:
            network.update(dns=0.01, connessione=0.03, tls=0.05)
        return r
    monkeypatch.setattr(net_phase, "post_traced", fake_post)
    monkeypatch.setattr(ai_gateway, "_token", lambda: "tok")
    monkeypatch.setenv("GCP_PROJECT_ID", "progetto-prova")
    monkeypatch.setattr("sys.argv", ["measure_model.py", "-n", "4", "--reasoning", "default", "--reasoning", "low"])
    assert mm.main() == 0
    out = capsys.readouterr().out
    assert "reasoning_effort" not in sent[0] and sent[4]["reasoning_effort"] == "low"
    assert "troncata: max_tokens esauriti" in out and "(ragionamento 4096 token)" in out
    assert "endpoint HTTP 429: Resource exhausted: quota" in out
    assert "timeout nella fase «attesa della risposta»: 1" in out                # the phase, in the summary too
    assert "rete: DNS 10 ms, TCP 30 ms, TLS 50 ms" in out
    assert "riuscite 1 su 4" in out and "mediana" in out and "p95" in out and "Costo stimato totale:" in out
    assert json.dumps(sent).count("progetto-prova") == 0                  # the project goes in the URL, not the body


def test_the_native_regional_endpoint(monkeypatch, capsys):
    """The committente's test (2): Vertex's generateContent on a regional endpoint, same prompt and tools translated."""
    mm = _script()
    from bff import net_phase
    usage = {"promptTokenCount": 1000, "candidatesTokenCount": 50, "thoughtsTokenCount": 150, "totalTokenCount": 1200}
    replies = [
        httpx.Response(200, json={"candidates": [{"content": {"parts": [{"functionCall": {"name": "comanda_dispositivo",
                                                                                         "args": {}}}]},
                                                  "finishReason": "STOP"}], "usageMetadata": usage}),
        httpx.Response(200, json={"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}],
                                  "usageMetadata": usage}),
    ]
    sent = []

    async def fake_post(url, json=None, headers=None, connect_s=None, read_s=None, network=None):
        sent.append((url, json))
        return replies[(len(sent) - 1) % len(replies)]
    monkeypatch.setattr(net_phase, "post_traced", fake_post)
    monkeypatch.setattr(ai_gateway, "_token", lambda: "tok")
    monkeypatch.setenv("GCP_PROJECT_ID", "progetto-prova")
    monkeypatch.setattr("sys.argv", ["measure_model.py", "-n", "2", "--endpoint", "nativo", "--location", "europe-west4",
                                     "--model", "google/gemini-3.8-flash", "--reasoning", "low"])
    assert mm.main() == 0
    out = capsys.readouterr().out
    url, body = sent[0]
    assert url == ("https://europe-west4-aiplatform.googleapis.com/v1/projects/progetto-prova/locations/europe-west4"
                   "/publishers/google/models/gemini-3.8-flash:generateContent")
    assert "Stato attuale dell'appartamento" in body["systemInstruction"]["parts"][0]["text"]
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    declared = {f["name"]: f for f in body["tools"][0]["functionDeclarations"]}
    assert declared["comanda_dispositivo"]["parameters"]["properties"]["params"]["properties"]["setpoint"] == {"type": "number"}
    assert "riuscite 1 su 2" in out and "troncata: max_tokens esauriti: 1" in out and "(ragionamento 150 token)" in out
    assert "nativo europe-west4" in out
    # Google's hosts: eu and us on aiplatform.<loc>.rep.googleapis.com, global on the plain host
    assert mm.native_url("p", "eu", "google/gemini-3.8-flash") == (
        "https://aiplatform.eu.rep.googleapis.com/v1/projects/p/locations/eu/publishers/google/models/gemini-3.8-flash:generateContent")
    assert mm.native_url("p", "global", "gemini-3.8-flash").startswith("https://aiplatform.googleapis.com/v1/projects/p/locations/global/")
    assert mm.host_for("europe-west1") == "europe-west1-aiplatform.googleapis.com"


def test_rep_host_for_the_openai_endpoint(monkeypatch, capsys):
    mm = _script()
    from bff import net_phase
    urls = []

    async def fake_post(url, json=None, headers=None, connect_s=None, read_s=None, network=None):
        urls.append(url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}})
    monkeypatch.setattr(net_phase, "post_traced", fake_post)
    monkeypatch.setattr(ai_gateway, "_token", lambda: "tok")
    monkeypatch.setenv("GCP_PROJECT_ID", "p")
    monkeypatch.setattr("sys.argv", ["measure_model.py", "-n", "1", "--rep-host"])
    assert mm.main() == 0
    assert urls == ["https://aiplatform.eu.rep.googleapis.com/v1/projects/p/locations/eu/endpoints/openapi/chat/completions"]
    monkeypatch.setattr("sys.argv", ["measure_model.py", "-n", "1"])                     # today's host, as the BFF
    mm.main()
    assert urls[-1].startswith("https://aiplatform.googleapis.com/v1/projects/p/locations/eu/")


def test_the_json_in_the_text_is_checked():
    """D-179 test (1): no tools, the command asked as a JSON object in the text, validated by us."""
    mm = _script()
    good = '{"risposta": "Spengo il clima.", "azioni": [{"tipo": "comando", "device_id": "dev-clima-soggiorno", ' \
           '"capability": "climate", "action": "turn_off", "params": {}}]}'
    assert mm.json_answer_valid(good) and mm.json_answer_valid("```json\n" + good + "\n```")
    assert mm.json_answer_valid('{"risposta": "Ci sono 20 gradi.", "azioni": []}')
    assert not mm.json_answer_valid("Spengo il clima.")                                     # prose
    assert not mm.json_answer_valid('{"risposta": "x", "azioni": [{"tipo": "modalita", "modalita": "notte"}]}')
    assert not mm.json_answer_valid('{"risposta": "x", "azioni": [{"tipo": "comando", "device_id": "d", '
                                    '"capability": "climate", "action": "explode", "params": {}}]}')


def test_claude_on_vertex_and_the_final_table(monkeypatch, capsys):
    mm = _script()
    from bff import net_phase
    sent = []

    async def fake_post(url, json=None, headers=None, connect_s=None, read_s=None, network=None):
        sent.append((url, json))
        if len(sent) == 1:
            return httpx.Response(200, json={"content": [{"type": "tool_use", "id": "toolu_1", "name": "comanda_dispositivo",
                                                          "input": {}}], "stop_reason": "tool_use",
                                             "usage": {"input_tokens": 1000, "output_tokens": 100}})
        raise net_phase.PhaseFailure(net_phase.WAIT, True, 25.0, httpx.ReadTimeout("lento"))
    monkeypatch.setattr(net_phase, "post_traced", fake_post)
    monkeypatch.setattr(ai_gateway, "_token", lambda: "tok")
    monkeypatch.setenv("GCP_PROJECT_ID", "p")
    monkeypatch.setattr("sys.argv", ["measure_model.py", "-n", "2", "--endpoint", "anthropic", "--location", "europe-west1",
                                     "--model", "claude-haiku-5-5", "--price-in", "1", "--price-out", "5"])
    assert mm.main() == 0
    out = capsys.readouterr().out
    url, body = sent[0]
    assert url == "https://europe-west1-aiplatform.googleapis.com/v1/projects/p/locations/europe-west1/publishers/anthropic/models/claude-haiku-5-5:rawPredict"
    assert body["anthropic_version"] == "vertex-2023-10-16" and "Stato attuale dell'appartamento" in body["system"]
    assert {t["name"] for t in body["tools"]} >= {"comanda_dispositivo"} and "input_schema" in body["tools"][0]
    assert "| claude-haiku-5-5 | anthropic europe-west1 | sì | 1 | " in out and "| 0.00150 € | – |" in out
    monkeypatch.setattr("sys.argv", ["measure_model.py", "--endpoint", "anthropic"])            # a model is needed
    assert mm.main() == 2


def test_a_location_outside_europe_is_said_diagnosis_only(monkeypatch, capsys):
    mm = _script()
    from bff import net_phase

    async def fake_post(url, json=None, headers=None, connect_s=None, read_s=None, network=None):
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}})
    monkeypatch.setattr(net_phase, "post_traced", fake_post)
    monkeypatch.setattr(ai_gateway, "_token", lambda: "tok")
    monkeypatch.setenv("GCP_PROJECT_ID", "p")
    monkeypatch.setattr("sys.argv", ["measure_model.py", "-n", "1", "--location", "global"])
    assert mm.main() == 0
    out = capsys.readouterr().out
    assert "global è escluso dagli ambienti (D-180" in out and "(global: escluso dagli ambienti, D-180; solo diagnosi)" in out

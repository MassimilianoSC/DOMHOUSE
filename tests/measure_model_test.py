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

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.append(json)
        r = replies[(len(sent) - 1) % len(replies)]
        if r == "timeout":
            raise httpx.ReadTimeout("lento")
        return r
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(ai_gateway, "_token", lambda: "tok")
    monkeypatch.setenv("GCP_PROJECT_ID", "progetto-prova")
    monkeypatch.setattr("sys.argv", ["measure_model.py", "-n", "4", "--reasoning", "default", "--reasoning", "low"])
    assert mm.main() == 0
    out = capsys.readouterr().out
    assert "reasoning_effort" not in sent[0] and sent[4]["reasoning_effort"] == "low"
    assert "troncata: max_tokens esauriti" in out and "(ragionamento 4096 token)" in out
    assert "endpoint HTTP 429: Resource exhausted: quota" in out and "timeout" in out
    assert "riuscite 1 su 4" in out and "mediana" in out and "p95" in out and "Costo stimato totale:" in out
    assert json.dumps(sent).count("progetto-prova") == 0                  # the project goes in the URL, not the body

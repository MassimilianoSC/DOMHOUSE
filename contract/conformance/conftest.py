"""
Suite di conformità al contratto `contract/openapi.yaml` (versione 1.0.4).

Esecuzione contro un'istanza reale:
    pytest contract/conformance --base-url http://10.0.0.10:8101/api/v1 --api-key "$LB_API_KEY"

Esecuzione contro il mock Prism (verifica che la suite sia coerente con il contratto;
il mock non ha stato, quindi gli scenari che richiedono stato vengono saltati):
    npx @stoplight/prism-cli mock contract/openapi.yaml -p 4010
    pytest contract/conformance --base-url http://127.0.0.1:4010 --mock

Regole della suite:
- ogni scenario C01–C16 è un test; il docstring riporta il testo dello scenario;
- uno scenario che richiede una feature assente da GET /version.features viene SALTATO
  (non fallisce): così la suite si può eseguire dalla settimana 1 con features = [];
- gli stati simulati (dispositivo offline, finestra aperta, approvazione) si creano con
  POST /_test/state: se risponde 404 (istanza non simulata) lo scenario viene saltato;
- nessun test usa endpoint fuori dal contratto.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field

import httpx
import pytest

ACTOR = "conformance@hqe.it"
TIMEOUT_COMANDO_S = 12  # il contratto dice 10 s; 2 s di margine di rete
TIMEOUT_ASK_S = 35      # il contratto dice 30 s


def pytest_addoption(parser):
    parser.addoption("--base-url", action="store", required=True,
                     help="Base URL dell'istanza, incluso /api/v1 (per Prism: senza /api/v1)")
    parser.addoption("--api-key", action="store", default="chiave-di-prova",
                     help="Valore di X-API-Key")
    parser.addoption("--mock", action="store_true", default=False,
                     help="L'obiettivo è il mock Prism: salta gli scenari che richiedono stato")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

@dataclass
class Client:
    base_url: str
    api_key: str
    mock: bool
    http: httpx.Client = field(init=False)
    features: set[str] = field(default_factory=set)

    def __post_init__(self):
        self.http = httpx.Client(base_url=self.base_url, timeout=20.0)

    def headers(self, correlation_id: str | None = None, actor: str = ACTOR, api_key: str | None = None) -> dict:
        h = {
            "X-API-Key": self.api_key if api_key is None else api_key,
            "X-Actor": actor,
            "X-Correlation-Id": correlation_id or str(uuid.uuid4()),
        }
        return {k: v for k, v in h.items() if v is not None}

    def get(self, path: str, **kw):
        kw.setdefault("headers", self.headers())
        return self.http.get(path, **kw)

    def post(self, path: str, body: dict | None = None, **kw):
        kw.setdefault("headers", self.headers())
        return self.http.post(path, json=body, **kw)

    def put(self, path: str, body: dict, **kw):
        kw.setdefault("headers", self.headers())
        return self.http.put(path, json=body, **kw)

    def patch(self, path: str, body: dict, **kw):
        kw.setdefault("headers", self.headers())
        return self.http.patch(path, json=body, **kw)

    def delete(self, path: str, **kw):
        kw.setdefault("headers", self.headers())
        return self.http.delete(path, **kw)

    # ---- helper di scenario ------------------------------------------------

    def richiede(self, *features: str):
        """Salta il test se una feature non è attiva sull'istanza."""
        mancanti = [f for f in features if f not in self.features]
        if mancanti:
            pytest.skip(f"feature non attive su questa istanza: {', '.join(mancanti)}")

    def richiede_stato(self, motivo: str):
        """Salta il test se l'obiettivo è il mock (che non ha stato)."""
        if self.mock:
            pytest.skip(f"richiede stato: {motivo} (mock Prism)")

    def stato_simulato(self, body: dict) -> None:
        """POST /_test/state; salta il test se l'istanza non è in modalità simulata."""
        r = self.post("/_test/state", body)
        if r.status_code == 404:
            pytest.skip("istanza non in modalità simulata: /_test/state non disponibile")
        assert r.status_code == 204, f"/_test/state → {r.status_code}: {r.text}"

    def dispositivo_con(self, capability: str, online: bool | None = True) -> dict:
        r = self.get("/devices")
        assert r.status_code == 200, r.text
        for d in r.json()["devices"]:
            if capability in d["capabilities"] and (online is None or d["online"] == online):
                return d
        pytest.skip(f"nessun dispositivo con capacità '{capability}' (online={online}) sull'istanza")

    def attendi_comando(self, command_id: str, finali=("acked", "failed", "timeout"), timeout_s: float = TIMEOUT_COMANDO_S) -> dict:
        scadenza = time.monotonic() + timeout_s
        ultimo = None
        while time.monotonic() < scadenza:
            r = self.get(f"/commands/{command_id}")
            assert r.status_code == 200, r.text
            ultimo = r.json()
            if ultimo["status"] in finali:
                return ultimo
            time.sleep(0.3)
        pytest.fail(f"comando {command_id} non ha raggiunto uno stato finale entro {timeout_s}s: {ultimo}")

    def decisioni(self, correlation_id: str) -> list[dict]:
        r = self.get("/decisions", params={"correlation_id": correlation_id, "limit": 50})
        assert r.status_code == 200, r.text
        return r.json()["items"]

    def cursore(self) -> str:
        """Ultimo `id` presente sul flusso in questo momento (rigiocando il buffer con Last-Event-ID: 0); "0" se vuoto.
        Senza Last-Event-ID il contratto prevede solo eventi nuovi: i test leggono il cursore PRIMA dell'azione e poi
        si ricollegano con Last-Event-ID = cursore, così vedono esattamente ciò che l'azione ha prodotto."""
        eventi = self.leggi_stream(max_eventi=10000, timeout_s=1.5, last_event_id="0")
        return eventi[-1]["id"] if eventi else "0"

    def leggi_stream(self, max_eventi: int, timeout_s: float = 8.0, last_event_id: str | None = None) -> list[dict]:
        """Legge fino a `max_eventi` eventi SSE (o fino al timeout) e restituisce i dati decodificati."""
        headers = self.headers()
        if last_event_id is not None:
            headers["Last-Event-ID"] = last_event_id
        eventi: list[dict] = []
        try:
            with self.http.stream("GET", "/stream", headers=headers, timeout=timeout_s) as r:
                assert r.status_code == 200, r.text
                corrente: dict = {}
                for riga in r.iter_lines():
                    if riga == "":
                        if "data" in corrente:
                            try:
                                dati = json.loads(corrente["data"])
                            except json.JSONDecodeError:
                                dati = {"raw": corrente["data"]}
                            dati.setdefault("event", corrente.get("event"))
                            dati.setdefault("id", corrente.get("id"))
                            eventi.append(dati)
                            if len(eventi) >= max_eventi:
                                break
                        corrente = {}
                        continue
                    if riga.startswith(":"):
                        continue
                    chiave, _, valore = riga.partition(":")
                    corrente[chiave.strip()] = valore.strip()
        except (httpx.ReadTimeout, httpx.RemoteProtocolError):
            pass
        return eventi


@pytest.fixture(scope="session")
def client(request) -> Client:
    c = Client(
        base_url=request.config.getoption("--base-url"),
        api_key=request.config.getoption("--api-key"),
        mock=request.config.getoption("--mock"),
    )
    r = c.http.get("/version")
    assert r.status_code == 200, f"GET /version → {r.status_code}: {r.text}"
    v = r.json()
    assert v["contract_version"].split(".")[0] == "1", f"versione di contratto incompatibile: {v['contract_version']}"
    c.features = set(v["features"])
    return c

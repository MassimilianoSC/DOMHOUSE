"""D-217, via A: POST /_internal/reachability, outside the contract. The BFF (bff/push.py _note_reachable) says it could
not reach this engine from `from` to `to`; the engine writes one decision, «Sistema domotico di nuovo raggiungibile
dopo …», sent live as decision.logged; the same interval twice gives the same decision; a wrong body is 400; the
route has the same key and headers as every call. Format agreed with o2 on 10 November 2026.

Run: python -m pytest engine/tests -q
"""
from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from engine import core
from engine.config import load_config
from engine.service import create_engine_app

KEY = "prova-chiave-0123456789"
CORR = "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
HEADERS = {"X-API-Key": KEY, "X-Actor": "system:bff", "X-Correlation-Id": CORR}
PATH = "/api/v1/_internal/reachability"


def z(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


@pytest.mark.parametrize("minutes, words", [
    (0.5, "meno di un minuto"), (1, "1 minuto"), (25, "25 minuti"), (59.9, "59 minuti"),
    (60, "1 ora"), (120, "2 ore"), (61, "1 ora e 1 minuto"), (190, "3 ore e 10 minuti"),
    (24 * 60, "1 giorno"), (24 * 60 + 61, "1 giorno e 1 ora"), (2 * 24 * 60 + 4 * 60 + 59, "2 giorni e 4 ore"),
])
def test_the_duration_is_said_as_a_person_says_it(minutes, words):
    assert core.duration_words(timedelta(minutes=minutes)) == words


@pytest.fixture
def client(tmp_path):
    env = {"APARTMENT_ID": "apt-prova-01", "API_KEY": KEY, "CONNECTOR": "simulated", "DATA_DIR": str(tmp_path)}
    with TestClient(create_engine_app(load_config(env))) as c:
        yield c


def test_the_return_is_one_decision_and_the_same_interval_gives_the_same(client):
    to = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=5)
    body = {"from": z(to - timedelta(hours=3, minutes=10)), "to": z(to)}
    first = client.post(PATH, json=body, headers=HEADERS)
    assert first.status_code == 201, first.text
    d = first.json()
    assert (d["actor"], d["target"], d["action"], d["old_value"], d["new_value"], d["outcome"], d["correlation_id"]) == \
        ("system", {"type": "apartment"}, "instance_reachable", "unreachable", "reachable", "informational", CORR)
    assert d["reasoning"] == "Sistema domotico di nuovo raggiungibile dopo 3 ore e 10 minuti"
    again = client.post(PATH, json=body, headers=HEADERS)
    assert again.status_code == 200 and again.json()["decision_id"] == d["decision_id"]
    listed = client.get("/api/v1/decisions", headers=HEADERS).json()["items"]
    assert [x["decision_id"] for x in listed if x["action"] == "instance_reachable"] == [d["decision_id"]]


def test_the_decision_goes_live_to_whoever_follows_the_stream():
    """The engine's own subscribers (what GET /stream reads): decision.logged with the decision, like every decision."""
    import asyncio
    from engine.connector.simulated import SimulatedConnector
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    queue: asyncio.Queue = asyncio.Queue()
    e.subscribers.add(queue)
    now = datetime.now(UTC)
    status, d = e.note_reachable({"from": z(now - timedelta(minutes=25)), "to": z(now)}, CORR)
    assert status == 201 and d["reasoning"].endswith("dopo 25 minuti")
    events = [queue.get_nowait() for _ in range(queue.qsize())]
    assert [(x["event"], x["data"]["decision_id"]) for x in events if x["event"] == "decision.logged"] == \
        [("decision.logged", d["decision_id"])]


@pytest.mark.parametrize("body, words", [
    (None, "obbligatori"),
    ({"from": "2026-11-10T07:00:00.000Z"}, "obbligatori"),
    ({"from": "2026-11-10T07:00:00", "to": "2026-11-10T08:00:00.000Z"}, "con il fuso"),    # no zone
    ({"from": "ieri", "to": "2026-11-10T08:00:00.000Z"}, "con il fuso"),
    ({"from": "2026-11-10T08:00:00.000Z", "to": "2026-11-10T08:00:00.000Z"}, "prima di to"),
    ({"from": "2026-11-10T08:00:00.000Z", "to": "2099-01-01T00:00:00.000Z"}, "nel futuro"),
])
def test_a_body_that_is_not_two_instants_in_order_is_refused(client, body, words):
    r = client.post(PATH, json=body, headers=HEADERS) if body is not None else client.post(PATH, headers=HEADERS)
    assert r.status_code == 400 and words in r.json()["message"], r.text
    assert not [x for x in client.get("/api/v1/decisions", headers=HEADERS).json()["items"]
                if x["action"] == "instance_reachable"]


def test_the_route_wants_the_key_and_the_headers_of_every_call(client):
    body = {"from": z(datetime.now(UTC) - timedelta(hours=1)), "to": z(datetime.now(UTC))}
    assert client.post(PATH, json=body).status_code == 401
    assert client.post(PATH, json=body, headers={"X-API-Key": KEY}).status_code == 400

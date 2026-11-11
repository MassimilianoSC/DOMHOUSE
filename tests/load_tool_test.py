"""scripts/load/carico.py (P-84): the load tool against a real local server in development mode (AUTH_MODE=dev, the
built-in simulated engine), as it will run against staging: the people open the page, keep the stream and refresh like
the site; the commands are confirmed in the stream; it stops above 5% of errors; it refuses a server that is not the
one expected. No Firebase, no network beyond this machine."""
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "load" / "carico.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("carico", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    port = free_port()
    env = {**os.environ, "APP_ENV": "dev", "AUTH_MODE": "dev", "INSTANCE_MODE": "mock", "REPOSITORY": "memory",
           "PORT": str(port), "PYTHONUNBUFFERED": "1", "STREAM_MAX_S": "8"}      # the stream ends and is reopened
    log = open(tmp_path_factory.mktemp("bff") / "bff.log", "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "bff.main:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2) as r:
                if r.status == 200:
                    break
        except OSError:
            time.sleep(0.3)
    else:
        proc.kill()
        pytest.fail("il server locale non è partito")
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()


def run_tool(*args: str, timeout: float = 180) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, cwd=ROOT)


def results(folder: Path, test: str) -> dict:
    files = sorted(folder.glob(f"risultati-{test}-*.json"))
    assert len(files) == 1, files
    return json.loads(files[0].read_text(encoding="utf-8"))


def test_people_open_the_page_keep_the_stream_and_refresh_like_the_site(server, tmp_path):
    out = run_tool("persone", "--dev", "--bff", server, "--gradini", "2,4", "--minuti", "0.25", "--salita-s", "1",
                   "--cartella", str(tmp_path))
    assert out.returncode == 0, out.stdout + out.stderr
    assert "INIZIO della prova" in out.stdout and "FINE della prova" in out.stdout and "RIEPILOGO" in out.stdout
    data = results(tmp_path, "persone")
    assert [s["persone"] for s in data["gradini"]] == [2, 4]
    for step in data["gradini"]:
        assert step["errori"] == 0, step["codici_errore"]
        assert step["tempi_s"]["stream"]["n"] >= 1 and step["tempi_s"]["elenco"]["n"] >= 1
        assert step["fermato"] is None
    first = data["gradini"][0]
    assert first["tempi_s"]["apertura"]["n"] == 2                     # each new person opened the page once
    assert data["gradini"][1]["tempi_s"]["apertura"]["n"] == 2        # the two added at the second step
    # STREAM_MAX_S=8 on a 15 s step: the server closed streams normally and the people opened them again
    assert sum(s["stream_chiusure_normali"] for s in data["gradini"]) >= 2
    assert all(s["stream_cadute"] == 0 for s in data["gradini"])


def test_commands_are_timed_until_their_final_state_in_the_stream(server, tmp_path):
    out = run_tool("comandi", "--dev", "--bff", server, "--persone", "3", "--ritmi", "60", "--minuti", "0.25",
                   "--salita-s", "1", "--cartella", str(tmp_path))
    assert out.returncode == 0, out.stdout + out.stderr
    step = results(tmp_path, "comandi")["gradini"][-1]
    c = step["comandi"]
    assert c["n"] >= 10 and c["stati"].get("acked", 0) >= 1, c
    assert set(c["stati"]) <= {"acked", "failed", "timeout"}, c       # none refused, none without its final state
    assert 0 < c["confermati_mediana_s"] < 30
    assert step["errori"] == 0, step["codici_errore"]


def test_it_stops_by_itself_above_five_percent_of_errors(server, tmp_path):
    out = run_tool("persone", "--dev", "--bff", server, "--appartamento", "apt-che-non-esiste", "--gradini", "3,6",
                   "--minuti", "1", "--salita-s", "1", "--cartella", str(tmp_path))
    assert out.returncode == 3, out.stdout + out.stderr
    steps = results(tmp_path, "persone")["gradini"]
    assert len(steps) == 1 and "oltre il limite del 5 %" in steps[0]["fermato"]   # the second step never started
    assert "FERMATA" in out.stdout


def test_it_works_only_on_the_expected_server(server, tmp_path):
    users = tmp_path / "utenti.json"
    users.write_text(json.dumps({"bff_url": server, "firebase_api_key": "x", "referer": "https://example.invalid/",
                                 "utenti": [{"email": "a@b.invalid", "password": "p", "apartment_id": "x"}]}),
                     encoding="utf-8")
    out = run_tool("persone", "--utenti", str(users), "--cartella", str(tmp_path), timeout=60)
    assert out.returncode != 0 and "lavora solo su staging" in out.stdout + out.stderr
    assert not list(tmp_path.glob("risultati-*"))


def test_percentiles_and_italian_numbers():
    tool = load_tool()
    values = [float(i) for i in range(1, 101)]
    assert tool.pct(values, 50) == 50 and tool.pct(values, 95) == 95 and tool.pct([], 50) is None
    assert tool.num(0.456, 2) == "0,46" and tool.whole(12345) == "12.345" and tool.num(None) == "n.d."
    with pytest.raises(SystemExit):
        tool.parse_args(["persone", "--gradini", "100,50"])
    assert tool.parse_args(["comandi"]).minuti == 3.0 and tool.parse_args(["persone"]).minuti == 5.0

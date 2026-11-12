"""P-84: the load test of the app's server, as the site uses it (method approved on 11 November 2026, answer 1065 = a).

It runs from Cloud Shell, never from the committente's PC and never against production (it stops unless the server
says it is staging). It signs in as the test people made by scripts/load/ambiente.py (their file: carico-utenti.json)
with Firebase's email and password, the site's own way, and behaves like the site on an apartment's page:

  * on opening: /app/me, then together /app/apartments, /app/apartments/<id> and the engine's /devices ("apertura");
  * one stream (/app/apartments/<id>/stream) always open, reopened when the server closes it (every 240 s);
  * /app/apartments every 20 s, /app/apartments/<id> every 30 s, the engine's /decisions every 30 s (as the site);
  * /app/me every 60 s ("sonda": the server alone, no engine, to tell the server's time from the engine's).

    python3 carico.py persone --utenti carico-utenti.json                 # 25 ... 1000 people, 5 minutes per step
    python3 carico.py comandi --utenti carico-utenti.json                 # 50 people, then 6 ... 120 commands a minute

persone: the people grow by steps (--gradini), each reached in --salita-s seconds and held --minuti minutes. comandi:
--persone people as above, plus commands (switch on/off of a simulated device, through the server) at each rate of
--ritmi (commands a minute in all), each timed from the request to its final state in the person's stream.
Both stop by themselves when more than 5% of the requests of a step fail. At the end: Cloud Run's instances and
Firestore's reads of each step (Cloud Monitoring, read only, with gcloud's identity; --senza-metriche skips them), a
summary in plain words and every number in risultati-<test>-<UTC>.json. The first and last lines say the real start
and end in UTC, for the registro (D-210).

Offline (tests/load_tool_test.py) the same code runs against a local server in development mode: --dev with
--utente-dev and --appartamento instead of --utenti (X-Dev-User, no Firebase).
Needs only httpx (pip3 install --user httpx==0.28.1).
"""
import argparse
import asyncio
import collections
import json
import math
import os
import random
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx

ERROR_LIMIT = 0.05            # the approved stop: more than 5% of a step's requests failed
ERROR_MIN_REQUESTS = 50       # ... counted once the step has at least this many
LAG_UNRELIABLE_S = 0.2        # this machine's event loop late by more than this (95%): the step's times are not the server's
COMMAND_WAIT_S = 30.0         # a command without its final state in the stream after this: «senza conferma»
FINAL = {"acked", "failed", "timeout"}
METRICS_DELAY_S = 240         # Cloud Monitoring has the last minutes' numbers after about this
POLLS = (("elenco", 20.0), ("riepilogo", 30.0), ("decisioni", 30.0), ("sonda", 60.0))
SIGN_IN = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
REFRESH = "https://securetoken.googleapis.com/v1/token"
MONITORING = "https://monitoring.googleapis.com/v3/projects/{project}/timeSeries"


def say(*a) -> None:
    print(*a, flush=True)


def utc(ts: float | None = None) -> str:
    return datetime.fromtimestamp(time.time() if ts is None else ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rfc3339(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def pct(values: list[float], p: float) -> float | None:
    """Nearest rank: the value under which p% of them are."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, min(len(s) - 1, math.ceil(p / 100 * len(s)) - 1))]


def num(x: float | None, digits: int = 1) -> str:
    """Italian decimals: 0,4."""
    return "n.d." if x is None else f"{x:.{digits}f}".replace(".", ",")


def whole(n: float | None) -> str:
    return "n.d." if n is None else f"{int(round(n)):,}".replace(",", ".")


class Stats:
    """The numbers of one step."""

    def __init__(self, name: str, people: int):
        self.name, self.people = name, people
        self.started = time.time()
        self.ended: float | None = None
        self.times: dict[str, list[float]] = collections.defaultdict(list)
        self.ok: collections.Counter = collections.Counter()
        self.failed: collections.Counter = collections.Counter()
        self.codes: collections.Counter = collections.Counter()
        self.stream_dropped = 0                 # a stream that broke after it had started (not the normal 240 s end)
        self.stream_ended = 0                   # normal ends
        self.lags: list[float] = []
        self.cpu_start = time.process_time()
        self.cpu_s: float | None = None
        self.commands: list[float] = []
        self.command_states: collections.Counter = collections.Counter()
        self.stopped: str | None = None
        self.metrics: dict = {}

    def record(self, kind: str, seconds: float, ok: bool, code) -> None:
        if ok:
            self.ok[kind] += 1
            self.times[kind].append(seconds)
        else:
            self.failed[kind] += 1
            self.codes[f"{kind} {code}"] += 1

    def requests(self) -> tuple[int, int]:
        return sum(self.ok.values()) + sum(self.failed.values()), sum(self.failed.values())

    def error_rate(self) -> float:
        total, failed = self.requests()
        return failed / total if total else 0.0

    def close(self) -> None:
        self.ended = time.time()
        self.cpu_s = time.process_time() - self.cpu_start

    def as_dict(self) -> dict:
        total, failed = self.requests()
        wall = (self.ended or time.time()) - self.started
        return {
            "gradino": self.name, "persone": self.people, "inizio": utc(self.started), "fine": utc(self.ended),
            "richieste": total, "errori": failed, "errori_pct": round(100 * self.error_rate(), 2),
            "codici_errore": dict(self.codes.most_common(10)),
            "tempi_s": {k: {"mediana": pct(v, 50), "p95": pct(v, 95), "n": len(v)} for k, v in sorted(self.times.items())},
            "stream_cadute": self.stream_dropped, "stream_chiusure_normali": self.stream_ended,
            "ritardo_generatore_p95_s": pct(self.lags, 95),
            "cpu_generatore_pct": round(100 * (self.cpu_s or 0) / wall, 1) if wall > 0 else None,
            "comandi": {"n": sum(self.command_states.values()), "confermati_mediana_s": pct(self.commands, 50),
                        "confermati_p95_s": pct(self.commands, 95),
                        "stati": dict(self.command_states)},
            "fermato": self.stopped, "metriche": self.metrics,
        }


class DevIdentity:
    """Development mode (local server, AUTH_MODE=dev): the person is named in a header."""

    def __init__(self, email: str):
        self.email = email

    async def headers(self) -> dict:
        return {"X-Dev-User": self.email}


class FirebaseIdentity:
    """A test person signed in with Firebase as the site does; the token renewed 5 minutes before it expires."""

    def __init__(self, email: str, password: str, api_key: str, referer: str, client: httpx.AsyncClient):
        self.email, self._password, self._key, self._referer, self._client = email, password, api_key, referer, client
        self._token, self._refresh, self._expires = "", "", 0.0
        self._lock = asyncio.Lock()

    async def sign_in(self) -> None:
        r = await self._client.post(SIGN_IN, params={"key": self._key}, headers={"Referer": self._referer},
                                    json={"email": self.email, "password": self._password, "returnSecureToken": True})
        if r.status_code != 200:
            raise SystemExit(f"accesso di {self.email} rifiutato da Firebase: {r.status_code} "
                             f"{r.json().get('error', {}).get('message', '') if r.content else ''}")
        body = r.json()
        self._token, self._refresh = body["idToken"], body["refreshToken"]
        self._expires = time.monotonic() + int(body.get("expiresIn", 3600))

    async def headers(self) -> dict:
        async with self._lock:
            if time.monotonic() > self._expires - 300:
                r = await self._client.post(REFRESH, params={"key": self._key}, headers={"Referer": self._referer},
                                            data={"grant_type": "refresh_token", "refresh_token": self._refresh})
                if r.status_code == 200:
                    body = r.json()
                    self._token, self._refresh = body["id_token"], body["refresh_token"]
                    self._expires = time.monotonic() + int(body.get("expires_in", 3600))
                else:
                    await self.sign_in()
        return {"Authorization": f"Bearer {self._token}"}


class Run:
    """What every person shares: the HTTP client, the server's address and the step being measured."""

    def __init__(self, base: str, client: httpx.AsyncClient):
        self.base, self.client = base.rstrip("/"), client
        self.stats = Stats("avvio", 0)
        self.stopping = False
        self.starting: set[asyncio.Task] = set()     # people opening their page (kept, or the loop could drop them)

    async def call(self, kind: str, ident, method: str, path: str, body: dict | None = None) -> tuple[int | None, dict | None]:
        t0 = time.monotonic()
        stats = self.stats
        try:
            headers = {**await ident.headers(), "X-Correlation-Id": str(uuid.uuid4())}
            r = await self.client.request(method, self.base + path, headers=headers, json=body, timeout=30.0)
        except httpx.HTTPError as exc:
            stats.record(kind, time.monotonic() - t0, False, type(exc).__name__)
            return None, None
        stats.record(kind, time.monotonic() - t0, r.status_code < 400, r.status_code)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, None

    async def watch_lag(self) -> None:
        """How late this machine's event loop is: when it is, the measured times are this machine's, not the server's."""
        while not self.stopping:
            t0 = time.monotonic()
            await asyncio.sleep(0.5)
            self.stats.lags.append(max(0.0, time.monotonic() - t0 - 0.5))


class Person:
    def __init__(self, run: Run, ident, apartment_id: str):
        self.run, self.ident, self.apt = run, ident, apartment_id
        self.tasks: list[asyncio.Task] = []
        self.waiting: dict[str, asyncio.Future] = {}
        self.finished: dict[str, str] = {}      # command_id -> final state seen before anyone waited for it

    @property
    def apt_path(self) -> str:
        return f"/app/apartments/{self.apt}"

    async def start(self) -> None:
        t0 = time.monotonic()
        codes = [(await self.run.call("me", self.ident, "GET", "/app/me"))[0]]
        codes += [c for c, _ in await asyncio.gather(
            self.run.call("elenco", self.ident, "GET", "/app/apartments"),
            self.run.call("riepilogo", self.ident, "GET", self.apt_path),
            self.run.call("dispositivi", self.ident, "GET", f"{self.apt_path}/instance/devices"))]
        if all(c is not None and c < 400 for c in codes):
            self.run.stats.times["apertura"].append(time.monotonic() - t0)
        self.tasks.append(asyncio.create_task(self.stream()))
        for kind, every in POLLS:
            self.tasks.append(asyncio.create_task(self.poll(kind, every)))

    async def stop(self) -> None:
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def poll(self, kind: str, every: float) -> None:
        path = {"elenco": "/app/apartments", "riepilogo": self.apt_path, "sonda": "/app/me",
                "decisioni": f"{self.apt_path}/instance/decisions?limit=30"}[kind]
        await asyncio.sleep(random.uniform(0, every))       # not all together, as people who opened the page at different times
        while not self.run.stopping:
            await self.run.call(kind, self.ident, "GET", path)
            await asyncio.sleep(every * random.uniform(0.95, 1.05))

    async def stream(self) -> None:
        last_id = None
        while not self.run.stopping:
            t0 = time.monotonic()
            started = False
            stats = self.run.stats
            try:
                headers = {**await self.ident.headers(), "Accept": "text/event-stream"}
                if last_id:
                    headers["Last-Event-ID"] = last_id
                timeout = httpx.Timeout(30.0, read=90.0)    # the server pings every 25 s
                async with self.run.client.stream("GET", f"{self.run.base}{self.apt_path}/stream", headers=headers,
                                                  timeout=timeout) as r:
                    if r.status_code != 200:
                        await r.aread()
                        stats.record("stream", time.monotonic() - t0, False, r.status_code)
                        await asyncio.sleep(3 + random.random())
                        continue
                    event, data, eid = "", [], None
                    async for line in r.aiter_lines():
                        if not started:
                            started = True
                            stats.record("stream", time.monotonic() - t0, True, 200)
                        if line == "":
                            if eid:
                                last_id = eid
                            if event == "command.updated" and data:
                                self.command_event("\n".join(data))
                            event, data, eid = "", [], None
                        elif not line.startswith(":"):
                            field, _, value = line.partition(":")
                            value = value[1:] if value.startswith(" ") else value
                            if field == "event":
                                event = value
                            elif field == "data":
                                data.append(value)
                            elif field == "id":
                                eid = value
                    self.run.stats.stream_ended += 1
            except asyncio.CancelledError:
                raise
            except httpx.HTTPError as exc:
                if started:
                    self.run.stats.stream_dropped += 1
                else:
                    stats.record("stream", time.monotonic() - t0, False, type(exc).__name__)
                    await asyncio.sleep(3 + random.random())
            await asyncio.sleep(random.uniform(0.2, 1.0))

    def command_event(self, raw: str) -> None:
        try:
            body = json.loads(raw)
            data = body.get("data") or {}
            command_id, status = data.get("command_id"), data.get("status")
        except (ValueError, AttributeError):
            return
        if status not in FINAL or not command_id:
            return
        fut = self.waiting.pop(command_id, None)
        if fut is not None and not fut.done():
            fut.set_result(status)
        else:
            self.finished[command_id] = status
            if len(self.finished) > 500:
                self.finished.pop(next(iter(self.finished)))

    async def command(self, device_id: str, on: bool) -> None:
        stats = self.run.stats
        t0 = time.monotonic()
        code, body = await self.run.call("comando", self.ident, "POST", f"{self.apt_path}/instance/devices/{device_id}/commands",
                                         {"capability": "switch", "action": "turn_on" if on else "turn_off"})
        if code != 202 or not body or not body.get("command_id"):
            stats.command_states[f"rifiutato {code}"] += 1
            return
        command_id = body["command_id"]
        if command_id in self.finished:
            status = self.finished.pop(command_id)
        else:
            fut = asyncio.get_running_loop().create_future()
            self.waiting[command_id] = fut
            try:
                status = await asyncio.wait_for(fut, COMMAND_WAIT_S)
            except TimeoutError:
                self.waiting.pop(command_id, None)
                stats.command_states["senza conferma"] += 1
                return
        stats.command_states[status] += 1
        if status == "acked":
            stats.commands.append(time.monotonic() - t0)


def load_people(args, client: httpx.AsyncClient) -> tuple[list, dict]:
    """[(identity, apartment_id)] and the file's settings; in --dev one person repeated."""
    if args.dev:
        return [(DevIdentity(args.utente_dev), args.appartamento)], {"bff_url": args.bff}
    with open(args.utenti, encoding="utf-8") as f:
        conf = json.load(f)
    people = [(FirebaseIdentity(u["email"], u["password"], conf["firebase_api_key"], conf["referer"], client),
               u["apartment_id"]) for u in conf["utenti"]]
    return people, conf


async def check_target(client: httpx.AsyncClient, base: str, dev: bool) -> str:
    r = await client.get(f"{base.rstrip('/')}/health", timeout=30.0)
    env = r.json().get("app_env") if r.status_code == 200 else None
    allowed = ("dev",) if dev else ("staging",)
    if env not in allowed:
        raise SystemExit(f"{base} dice di essere «{env}»: questo strumento lavora solo su {' o '.join(allowed)}")
    return env


def gcloud_token() -> str | None:
    try:
        out = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


async def read_metric(client, token: str, project: str, flt: str, start: float, end: float, aligner: str,
                      reducer: str) -> list[float]:
    """One value a minute in [start, end], all series summed (Cloud Monitoring, read only)."""
    params = {"filter": flt, "interval.startTime": rfc3339(start), "interval.endTime": rfc3339(end),
              "aggregation.alignmentPeriod": "60s", "aggregation.perSeriesAligner": aligner,
              "aggregation.crossSeriesReducer": reducer, "view": "FULL"}
    r = await client.get(MONITORING.format(project=project), params=params,
                         headers={"Authorization": f"Bearer {token}"}, timeout=60.0)
    r.raise_for_status()
    values = []
    for series in r.json().get("timeSeries", []):
        for point in series.get("points", []):
            v = point["value"]
            values.append(float(v.get("int64Value", v.get("doubleValue", 0))))
    return values


async def add_metrics(client, conf: dict, steps: list[Stats]) -> str | None:
    """Cloud Run's instances (most at once) and Firestore's reads of every step; None, or why they are missing."""
    project, service, database = conf.get("project_id"), conf.get("service"), conf.get("database", "staging")
    if not project or not service:
        return "progetto o servizio mancanti nel file degli utenti"
    token = gcloud_token()
    if not token:
        return "gcloud non dà un token (sei in Cloud Shell con l'account del progetto?)"
    wait = max(0.0, METRICS_DELAY_S - (time.time() - (steps[-1].ended or time.time())))
    if wait:
        say(f"\nAttendo {int(wait)} s: Cloud Monitoring registra i numeri degli ultimi minuti con questo ritardo.")
        await asyncio.sleep(wait)
    instances = (f'metric.type="run.googleapis.com/container/instance_count" resource.type="cloud_run_revision" '
                 f'resource.labels.service_name="{service}"')
    reads = (f'metric.type="firestore.googleapis.com/document/read_ops_count" '
             f'resource.type="firestore.googleapis.com/Database" resource.labels.database_id="{database}"')
    problem = None
    for st in steps:
        try:
            counts = await read_metric(client, token, project, instances, st.started, st.ended, "ALIGN_MAX", "REDUCE_SUM")
            st.metrics["istanze_max"] = max(counts) if counts else None
        except httpx.HTTPError as exc:
            problem = f"istanze non lette: {exc}"
        try:
            ops = await read_metric(client, token, project, reads, st.started, st.ended, "ALIGN_DELTA", "REDUCE_SUM")
            st.metrics["letture_firestore"] = sum(ops) if ops else None
        except httpx.HTTPError as exc:
            problem = f"letture di Firestore non lette: {exc}"
    return problem


def step_line(st: Stats) -> list[str]:
    d = st.as_dict()
    t = d["tempi_s"]

    def time_of(kind: str) -> str:
        v = t.get(kind)
        if not v or v["mediana"] is None:
            return "n.d."
        return f"{num(v['mediana'])} s (95 su 100 entro {num(v['p95'])} s)"
    minutes = ((st.ended or time.time()) - st.started) / 60
    lines = [f"- {st.people} persone collegate ({st.name}, {utc(st.started)} - {utc(st.ended)}):",
             f"    pagina aperta in {time_of('apertura')}",
             f"    aggiornamenti dell'elenco in {time_of('elenco')}; della scheda in {time_of('riepilogo')}",
             f"    collegamento in tempo reale aperto in {time_of('stream')}; caduti {st.stream_dropped}",
             f"    solo il server, senza il motore, in {time_of('sonda')}",
             f"    errori {num(d['errori_pct'])} % su {whole(d['richieste'])} richieste"
             + (f" (i più frequenti: {', '.join(f'{k} x{v}' for k, v in st.codes.most_common(3))})" if st.codes else "")]
    if d["comandi"]["n"]:
        c = d["comandi"]
        lines.append(f"    comandi: {c['n']}, confermati in {num(c['confermati_mediana_s'])} s "
                     f"(95 su 100 entro {num(c['confermati_p95_s'])} s); esiti {c['stati']}")
    m = st.metrics
    if m.get("istanze_max") is not None:
        lines.append(f"    istanze del server usate al massimo: {whole(m['istanze_max'])}")
    if m.get("letture_firestore") is not None and st.people and minutes > 0:
        per_hour = m["letture_firestore"] / st.people / minutes * 60
        lines.append(f"    letture del database: {whole(m['letture_firestore'])} (circa {whole(per_hour)} per persona all'ora)")
    lag = d["ritardo_generatore_p95_s"]
    if lag is not None and lag > LAG_UNRELIABLE_S:
        lines.append(f"    ATTENZIONE: il computer che genera il carico era in ritardo ({num(lag, 2)} s): "
                     "questi tempi sono anche suoi, non solo del server")
    if st.stopped:
        lines.append(f"    FERMATA: {st.stopped}")
    return lines


async def hold(run: Run, seconds: float, label: str) -> bool:
    """Measure for this long; False when the errors went over the limit (the step and the test stop)."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        await asyncio.sleep(min(5.0, max(0.0, end - time.monotonic())))
        total, _ = run.stats.requests()
        if total >= ERROR_MIN_REQUESTS and run.stats.error_rate() > ERROR_LIMIT:
            run.stats.stopped = (f"errori al {num(100 * run.stats.error_rate())} % ({label}), oltre il limite del "
                                 f"{int(ERROR_LIMIT * 100)} %: la prova si ferma qui")
            return False
    return True


async def grow(run: Run, people: list[Person], pool: list, target: int, ramp_s: float) -> None:
    """New people up to target, spread over ramp_s seconds; each takes the next test person of the pool in turn."""
    missing = target - len(people)
    for i in range(max(0, missing)):
        ident, apt = pool[len(people) % len(pool)]
        p = Person(run, ident, apt)
        people.append(p)
        t = asyncio.create_task(p.start())
        run.starting.add(t)
        t.add_done_callback(run.starting.discard)
        await asyncio.sleep(ramp_s / missing)


async def main_async(args) -> int:
    limits = httpx.Limits(max_connections=None, max_keepalive_connections=2000)
    async with httpx.AsyncClient(limits=limits, follow_redirects=False) as client:
        pool, conf = load_people(args, client)
        base = conf["bff_url"]
        env = await check_target(client, base, args.dev)
        started = time.time()
        say(f"INIZIO della prova «{args.prova}»: {utc(started)} (UTC), server {base} ({env})")
        if not args.dev:
            say(f"Accesso a Firebase delle {len(pool)} persone di prova...")
            for ident, _ in pool:
                await ident.sign_in()
                await asyncio.sleep(0.2)            # gently: Firebase slows down many sign-ins from one address
        run = Run(base, client)
        lag = asyncio.create_task(run.watch_lag())
        people: list[Person] = []
        steps: list[Stats] = []
        try:
            if args.prova == "persone":
                for target in args.gradini:
                    run.stats = Stats(f"gradino {target}", target)
                    steps.append(run.stats)
                    say(f"\n{utc()} gradino: {target} persone (salita in {int(args.salita_s)} s, poi {num(args.minuti)} minuti)")
                    await grow(run, people, pool, target, args.salita_s)
                    ok = await hold(run, args.minuti * 60, f"{target} persone")
                    run.stats.close()
                    say("\n".join(step_line(run.stats)))
                    if not ok:
                        break
            else:
                run.stats = Stats(f"apertura di {args.persone} persone", args.persone)
                steps.append(run.stats)
                say(f"\n{utc()} {args.persone} persone collegate, poi i comandi")
                await grow(run, people, pool, args.persone, args.salita_s)
                await asyncio.sleep(10)
                run.stats.close()
                devices = await switches(run, people)
                if not devices:
                    raise SystemExit("nessun dispositivo con interruttore in linea negli appartamenti di prova")
                for rate in args.ritmi:
                    run.stats = Stats(f"{rate:g} comandi al minuto", args.persone)
                    steps.append(run.stats)
                    say(f"\n{utc()} {rate:g} comandi al minuto per {num(args.minuti)} minuti")
                    ok = await commands(run, people, devices, rate, args.minuti * 60)
                    run.stats.close()
                    say("\n".join(step_line(run.stats)))
                    if not ok:
                        break
        finally:
            run.stopping = True
            await asyncio.gather(*(p.stop() for p in people), return_exceptions=True)
            lag.cancel()
            for st in steps:
                if st.ended is None:
                    st.close()
        ended = time.time()
        problem = None
        if steps and not args.dev and not args.senza_metriche:
            problem = await add_metrics(client, conf, steps)
        say(f"\nFINE della prova «{args.prova}»: {utc(ended)} (UTC); durata {num((ended - started) / 60)} minuti")
        say("\nRIEPILOGO")
        for st in steps:
            say("\n".join(step_line(st)))
        if problem:
            say(f"(numeri di Cloud Monitoring mancanti: {problem})")
        out = os.path.join(args.cartella, f"risultati-{args.prova}-{utc(started).replace(':', '')}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"prova": args.prova, "inizio": utc(started), "fine": utc(ended), "server": base,
                       "gradini": [st.as_dict() for st in steps], "metriche_mancanti": problem}, f, indent=2,
                      ensure_ascii=False)
        say(f"Tutti i numeri: {out}")
        return 0 if not any(st.stopped for st in steps) else 3


async def switches(run: Run, people: list[Person]) -> dict[str, list[str]]:
    """apartment -> its simulated devices with a switch, online, read once through one of its people."""
    found: dict[str, list[str]] = {}
    for p in people:
        if p.apt in found:
            continue
        code, body = await run.call("dispositivi", p.ident, "GET", f"{p.apt_path}/instance/devices")
        if code == 200 and body:
            found[p.apt] = [d["device_id"] for d in body.get("devices", [])
                            if d.get("online") and "switch" in (d.get("capabilities") or {})]
    return {k: v for k, v in found.items() if v}


async def commands(run: Run, people: list[Person], devices: dict[str, list[str]], rate: float, seconds: float) -> bool:
    """rate commands a minute, each by a person of an apartment with switches, on and off in turn per device."""
    able = [p for p in people if p.apt in devices]
    state: dict[tuple[str, str], bool] = {}
    pending: set[asyncio.Task] = set()
    end = time.monotonic() + seconds
    checker = asyncio.create_task(hold(run, seconds, f"{rate:g} comandi al minuto"))
    while time.monotonic() < end and not checker.done():
        p = random.choice(able)
        device = random.choice(devices[p.apt])
        on = not state.get((p.apt, device), False)
        state[(p.apt, device)] = on
        t = asyncio.create_task(p.command(device, on))
        pending.add(t)
        t.add_done_callback(pending.discard)
        await asyncio.sleep(60.0 / rate)
    ok = await checker if checker.done() else True
    checker.cancel()
    if pending:                                  # the last ones get their time to be confirmed
        await asyncio.wait(pending, timeout=COMMAND_WAIT_S + 5)
    return ok


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("prova", choices=("persone", "comandi"))
    p.add_argument("--utenti", default="carico-utenti.json", help="il file delle persone di prova (ambiente.py prepara)")
    p.add_argument("--gradini", default="25,50,100,200,400,700,1000", help="persone: i gradini")
    p.add_argument("--minuti", type=float, default=None, help="minuti di misura per gradino (persone 5, comandi 3)")
    p.add_argument("--salita-s", type=float, default=60.0, help="secondi per arrivare al gradino")
    p.add_argument("--persone", type=int, default=50, help="comandi: le persone collegate intanto")
    p.add_argument("--ritmi", default="6,30,60,120", help="comandi: comandi al minuto, in tutto")
    p.add_argument("--senza-metriche", action="store_true", help="non leggere istanze e letture da Cloud Monitoring")
    p.add_argument("--cartella", default=".", help="dove scrivere il file dei risultati")
    p.add_argument("--dev", action="store_true", help="server locale in modalità sviluppo (prove offline)")
    p.add_argument("--bff", default="http://127.0.0.1:8080", help="--dev: l'indirizzo del server locale")
    p.add_argument("--utente-dev", default="operatore@demo.it", help="--dev: la persona")
    p.add_argument("--appartamento", default="apt-rimini-01", help="--dev: l'appartamento")
    a = p.parse_args(argv)
    a.gradini = [int(x) for x in a.gradini.split(",") if x.strip()]
    a.ritmi = [float(x) for x in a.ritmi.split(",") if x.strip()]
    if a.minuti is None:
        a.minuti = 5.0 if a.prova == "persone" else 3.0
    if not a.gradini or any(n <= 0 for n in a.gradini) or a.gradini != sorted(a.gradini):
        p.error("--gradini: numeri positivi in ordine crescente")
    if not a.ritmi or any(r <= 0 for r in a.ritmi):
        p.error("--ritmi: numeri positivi")
    return a


def open_files_limit(wanted: int = 8192) -> int | None:
    """Every person keeps a connection open for the stream and opens others to refresh: 1000 people need more than the
    1024 open files a Linux shell often allows. Raised up to what the system permits; None where there is no such
    limit (Windows)."""
    try:
        import resource
    except ImportError:
        return None
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = wanted if hard == resource.RLIM_INFINITY else min(wanted, hard)
    if soft != resource.RLIM_INFINITY and soft < target:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            soft = target
        except (ValueError, OSError):
            pass
    return soft


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):          # « » and accents whatever the terminal says it reads
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(sys.argv[1:] if argv is None else argv)
    limit = open_files_limit()
    if limit is not None and args.prova == "persone" and limit < 2 * max(args.gradini) + 200:
        say(f"ATTENZIONE: questo computer permette {limit} collegamenti aperti; per {max(args.gradini)} persone ne "
            f"servono circa {2 * max(args.gradini)}: gli ultimi gradini misurerebbero questo computer, non il server")
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        say(f"\nInterrotta a mano alle {utc()} (UTC)")
        return 130


if __name__ == "__main__":
    sys.exit(main())

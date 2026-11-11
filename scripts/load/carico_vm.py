"""P-84: temporary simulated engines on the VM, for the load test, and the measure of how many the VM holds. It runs ON
the VM, as root, with the VM's own identity, like engine-vm.sh (python3 of the VM, no other package):

    sudo python3 carico_vm.py prepara 5          # carico-01 ... carico-05, the apartments of the test in the app
    sudo python3 carico_vm.py gradini 5,10,20    # how many engines the VM holds: at rest and with commands
    sudo python3 carico_vm.py osserva 60         # while carico.py runs: the VM watched for 60 minutes, a line a minute
    sudo python3 carico_vm.py stato
    sudo python3 carico_vm.py pulisci            # every test engine, its data and its key file: gone
    DRY_RUN=1 sudo -E python3 carico_vm.py ...   # says what it would do, starts and removes nothing

The test engines are NOT the apartments' engines of engine-vm.sh, and nothing of them is in /opt/domhouse:
  * the 5-minute watch (engine-vm.sh check-all), the daily backup and the start after a boot never see them: no
    «engine silent» email when they start or stop, no restart by the watch, nothing at the next boot (restart: no);
  * their logs stay in Docker's «local» format, which the Ops Agent does not read (it reads *-json.log): no email of
    «Motori: errori» and nothing in Cloud Logging;
  * key files in /etc/domhouse-carico (600, root), data in /var/lib/domhouse-carico/<id>, containers engine-carico-NN
    with the label domhouse.carico=1, ports 8150 and up on the VM's internal address (the subnet only, as dev).
The engines of the apartments in the app (prepara N: carico-01 ... carico-N) use the key in Secret Manager
langbrain-api-key-carico-NN (made by ambiente.py prepara), the server needs the same one; the others (gradini, beyond N)
a random key made here, that never leaves this machine. The image is the one of dev (/opt/domhouse/dev.settings).

Protection of dev and of the broker (approved with the method, answer 1065): every test engine has at most 150 MiB of
memory (it dies alone if it grows, without touching the others) and a low CPU weight (dev and the broker go first when
the CPU is short); the memory of the VM is read every 10 s: no new step above 75%, and above 85% the last step is
removed at once. Each step of «gradini» (default 3 minutes per phase): the new engines started and healthy, 1 minute
to settle, the rest measured, then commands (switch on/off, every engine one every 10 s) measured. The summary says per
step: memory of the VM, memory per engine, CPU of the VM, dev's answer time, the commands' times and failures.
osserva keeps the same watch while the people of carico.py load the server (and through it the test engines): a line
a minute with the same numbers, and above 85% every test engine goes at once (dev first, the test after).
"""
import argparse
import base64
import json
import math
import os
import re
import secrets
import shlex
import shutil
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

PREFIX = "carico-"
LABEL = "domhouse.carico=1"
PORT_BASE = 8150                       # as ambiente.py: carico-01 on 8150, carico-02 on 8151 ...
MAX_ENGINES = 40
MEMORY_LIMIT = "150m"
CPU_SHARES = "128"                     # Docker's default is 1024: under contention dev and the broker get 8 times more
ENGINE_UID = 10001
STEP_MAX_PCT = 75                      # no new step above this memory
STOP_PCT = 85                          # above this the last step goes, at once
SAMPLE_S = 10
OPT = os.environ.get("DOMHOUSE_OPT", "/opt/domhouse")
ETC = os.environ.get("CARICO_ETC", "/etc/domhouse-carico")
DATA = os.environ.get("CARICO_DATA", "/var/lib/domhouse-carico")
MEMINFO = os.environ.get("CARICO_MEMINFO", "/proc/meminfo")
PROCSTAT = os.environ.get("CARICO_PROCSTAT", "/proc/stat")
METADATA = os.environ.get("CARICO_METADATA", "http://metadata.google.internal/computeMetadata/v1")
SECRETS_API = os.environ.get("CARICO_SECRETS_API", "https://secretmanager.googleapis.com/v1")
DOCKER = shlex.split(os.environ.get("CARICO_DOCKER", "docker"))
SECRET_PREFIX = "langbrain-api-key-"
DRY = bool(os.environ.get("DRY_RUN"))


def say(*a) -> None:
    print(*a, flush=True)


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def die(msg: str) -> None:
    say(f"errore: {msg}")
    sys.exit(1)


def num(x, digits: int = 1) -> str:
    return "n.d." if x is None else f"{x:.{digits}f}".replace(".", ",")


def docker(*args: str, check: bool = True) -> str:
    out = subprocess.run([*DOCKER, *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        die(f"docker {' '.join(args[:2])}: {out.stderr.strip()[:300]}")
    return out.stdout


def metadata(path: str) -> str:
    req = urllib.request.Request(f"{METADATA}/{path}", headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode().strip()


def bind_ip() -> str:
    ip = os.environ.get("CARICO_BIND_IP") or metadata("instance/network-interfaces/0/ip")
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", ip):
        die("non leggo l'indirizzo interno della VM dal server dei metadati")
    return ip


def read_secret(name: str) -> str:
    """Its latest value, never printed: the VM's token from the metadata server, as engine-vm.sh read_secret."""
    token = json.loads(metadata("instance/service-accounts/default/token"))["access_token"]
    project = metadata("project/project-id")
    req = urllib.request.Request(f"{SECRETS_API}/projects/{project}/secrets/{name}/versions/latest:access",
                                 headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return base64.b64decode(json.load(r)["payload"]["data"]).decode().strip()
    except urllib.error.HTTPError as exc:
        die(f"segreto {name} non leggibile dalla VM ({exc.code}): ambiente.py prepara è stato lanciato?")
    return ""


def memory_pct() -> int:
    """What the kernel cannot hand out at once, as the watch's line «vm mem_used_pct» (engine-vm.sh vm_line)."""
    values = {}
    with open(MEMINFO, encoding="utf-8") as f:
        for line in f:
            key, _, rest = line.partition(":")
            values[key] = int(rest.split()[0])
    return int((values["MemTotal"] - values["MemAvailable"]) * 100 / values["MemTotal"])


def cpu_times() -> tuple[int, int, int]:
    """(total, idle + iowait, steal) of all the VM's CPUs since boot."""
    with open(PROCSTAT, encoding="utf-8") as f:
        parts = [int(x) for x in f.readline().split()[1:]]
    steal = parts[7] if len(parts) > 7 else 0
    return sum(parts[:8]), parts[3] + parts[4], steal


def engine_id(i: int) -> str:
    return f"{PREFIX}{i:02d}"


def running() -> list[str]:
    """The test engines that exist (any state), by id, in order."""
    out = docker("ps", "-a", "--filter", f"label={LABEL}", "--format", "{{.Names}}")
    return sorted(n[len("engine-"):] for n in out.split() if n.startswith("engine-" + PREFIX))


def dev_settings() -> dict:
    path = os.path.join(OPT, "dev.settings")
    try:
        with open(path, encoding="utf-8") as f:
            return dict(line.strip().split("=", 1) for line in f if "=" in line)
    except OSError:
        die(f"{path} non c'è: il motore dev non è installato su questa VM")
    return {}


def ports_in_use() -> set[int]:
    """The ports of the apartments' engines (engine-vm.sh): a test engine never takes one of them."""
    used = set()
    for name in os.listdir(OPT) if os.path.isdir(OPT) else []:
        if name.endswith(".settings"):
            with open(os.path.join(OPT, name), encoding="utf-8") as f:
                for line in f:
                    if line.startswith("PORT="):
                        used.add(int(line.split("=", 1)[1]))
    return used


def health(ip: str, port: int, timeout: float = 5.0) -> tuple[int | None, float]:
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(f"http://{ip}:{port}/api/v1/health", timeout=timeout) as r:
            return r.status, time.monotonic() - t0
    except urllib.error.HTTPError as exc:
        return exc.code, time.monotonic() - t0
    except (urllib.error.URLError, OSError):
        return None, time.monotonic() - t0


def start_engine(i: int, key: str, image: str, ip: str) -> None:
    apt, port = engine_id(i), PORT_BASE + i - 1
    if DRY:
        say(f"(prova a secco) avvierei engine-{apt} sulla porta {port}, {MEMORY_LIMIT} di memoria al massimo")
        return
    os.makedirs(ETC, mode=0o700, exist_ok=True)
    env_file = os.path.join(ETC, f"{apt}.env")
    old = os.umask(0o077)                     # before the file exists: never readable by others, not even for a moment
    try:
        with open(env_file + ".new", "w", encoding="utf-8") as f:
            f.write(f"API_KEY={key}\n")
    finally:
        os.umask(old)
    os.replace(env_file + ".new", env_file)
    data = os.path.join(DATA, apt)
    os.makedirs(data, mode=0o750, exist_ok=True)
    if hasattr(os, "chown"):                  # the container's user (Windows, in the tests, has no owners)
        os.chown(data, ENGINE_UID, ENGINE_UID)
    docker("rm", "-f", f"engine-{apt}", check=False)
    docker("run", "-d", "--name", f"engine-{apt}", "--label", LABEL, "--restart", "no",
           "--memory", MEMORY_LIMIT, "--memory-swap", MEMORY_LIMIT, "--cpu-shares", CPU_SHARES,
           "--log-driver", "local", "--log-opt", "max-size=5m",
           "-e", f"APARTMENT_ID={apt}", "-e", "CONNECTOR=simulated", "-e", f"PORT={port}", "--env-file", env_file,
           "-p", f"{ip}:{port}:{port}", "-v", f"{data}:/data/{apt}", image)


def wait_healthy(ids: list[int], ip: str, tries: int = 30) -> list[int]:
    """The ones that answer 200 within tries x 2 s."""
    if DRY:
        return ids
    waiting = set(ids)
    for _ in range(tries):
        for i in sorted(waiting):
            if health(ip, PORT_BASE + i - 1, 3)[0] == 200:
                waiting.discard(i)
        if not waiting:
            break
        time.sleep(2)
    return [i for i in ids if i not in waiting]


def remove(ids: list[str]) -> None:
    for apt in ids:
        if DRY:
            say(f"(prova a secco) toglierei engine-{apt}, i suoi dati e il suo file della chiave")
            continue
        docker("rm", "-f", f"engine-{apt}", check=False)
        shutil.rmtree(os.path.join(DATA, apt), ignore_errors=True)
        try:
            os.remove(os.path.join(ETC, f"{apt}.env"))
        except FileNotFoundError:
            pass
        say(f"tolto engine-{apt}")


def guard_before_step(target: int) -> None:
    pct = memory_pct()
    if pct > STEP_MAX_PCT:
        die(f"memoria della VM al {pct} %, oltre il {STEP_MAX_PCT} %: non salgo a {target} motori")


def start_up_to(target: int, app_count: int, image: str, ip: str) -> list[int]:
    """Engines up to target (existing ones kept); returns the new ones."""
    have = {int(a[len(PREFIX):]) for a in running()}
    new = [i for i in range(1, target + 1) if i not in have]
    for i in new:
        key = read_secret(SECRET_PREFIX + engine_id(i)) if i <= app_count and not DRY else secrets.token_urlsafe(32)
        start_engine(i, key, image, ip)
    ok = wait_healthy(new, ip)
    if len(ok) != len(new):
        bad = [engine_id(i) for i in new if i not in ok]
        say(f"ATTENZIONE: non rispondono {', '.join(bad)} (docker logs engine-<id> per vedere perché)")
    return new


def stats_of_engines() -> dict[str, tuple[float, float]]:
    """engine id -> (memory MiB, CPU %) from docker stats."""
    out = docker("stats", "--no-stream", "--format", "{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}", check=False)
    found = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or not parts[0].startswith("engine-"):
            continue
        m = re.match(r"([\d.]+)\s*([KMG]i?B)", parts[1].strip())
        if not m:
            continue
        factor = {"KiB": 1 / 1024, "KB": 1 / 1024, "MiB": 1, "MB": 1, "GiB": 1024, "GB": 1024}[m.group(2)]
        found[parts[0][len("engine-"):]] = (float(m.group(1)) * factor, float(parts[2].strip().rstrip("%") or 0))
    return found


class Commands(threading.Thread):
    """Every test engine gets a switch command every 10 s, straight to the engine (the server is measured by carico.py)."""

    EVERY_S = 10.0

    def __init__(self, ids: list[int], ip: str, seconds: float):
        super().__init__(daemon=True)
        self.ids, self.ip, self.seconds = ids, ip, seconds
        self.times: list[float] = []
        self.failed: dict[str, int] = {}

    def key(self, i: int) -> str:
        with open(os.path.join(ETC, f"{engine_id(i)}.env"), encoding="utf-8") as f:
            return f.read().split("=", 1)[1].strip()

    def request(self, i: int, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(f"http://{self.ip}:{PORT_BASE + i - 1}/api/v1{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-API-Key": self.key(i), "X-Actor": "system:carico",
                                              "X-Correlation-Id": str(uuid.uuid4()), "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"null")

    def run(self) -> None:
        devices = {}
        for i in self.ids:
            try:
                _, body = self.request(i, "GET", "/devices")
                devices[i] = [d["device_id"] for d in body.get("devices", []) if d.get("online")
                              and "switch" in (d.get("capabilities") or {})]
            except (urllib.error.URLError, OSError, ValueError) as exc:
                self.failed[f"elenco {type(exc).__name__}"] = self.failed.get(f"elenco {type(exc).__name__}", 0) + 1
        end = time.monotonic() + self.seconds
        state: dict[tuple[int, str], bool] = {}
        workers: list[threading.Thread] = []
        while time.monotonic() < end:
            for i, devs in devices.items():
                if not devs:
                    continue
                d = devs[int(time.monotonic()) % len(devs)]
                on = not state.get((i, d), False)
                state[(i, d)] = on
                t = threading.Thread(target=self.one, args=(i, d, on), daemon=True)
                t.start()
                workers.append(t)
            time.sleep(min(self.EVERY_S, max(0.0, end - time.monotonic())))
        for t in workers:
            t.join(timeout=20)

    def one(self, i: int, device: str, on: bool) -> None:
        t0 = time.monotonic()
        try:
            status, _ = self.request(i, "POST", f"/devices/{device}/commands",
                                     {"capability": "switch", "action": "turn_on" if on else "turn_off"})
            self.times.append(time.monotonic() - t0)
        except urllib.error.HTTPError as exc:
            self.failed[str(exc.code)] = self.failed.get(str(exc.code), 0) + 1
        except (urllib.error.URLError, OSError) as exc:
            self.failed[type(exc).__name__] = self.failed.get(type(exc).__name__, 0) + 1


def measure(seconds: float, ip: str, dev_port: int, new: list[int], phase: str) -> tuple[dict, bool]:
    """Samples every SAMPLE_S; (numbers, False if above STOP_PCT: the new engines are removed at once)."""
    mem, dev_times, dev_failed, per_engine = [], [], 0, {}
    cpu0 = cpu_times()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pct = memory_pct()
        mem.append(pct)
        if pct > STOP_PCT:
            say(f"{utc()} memoria della VM al {pct} %, oltre l'{STOP_PCT} %: tolgo subito l'ultimo gradino")
            remove([engine_id(i) for i in new])
            return {"fase": phase, "memoria_max_pct": pct, "fermato": f"memoria al {pct} %"}, False
        code, took = health(ip, dev_port)
        if code == 200:
            dev_times.append(took)
        else:
            dev_failed += 1
        for apt, (mib, cpu) in stats_of_engines().items():
            if apt.startswith(PREFIX):
                per_engine.setdefault(apt, []).append(mib)
        time.sleep(min(SAMPLE_S, max(0.0, end - time.monotonic())))
    cpu1 = cpu_times()
    total = max(1, cpu1[0] - cpu0[0])
    mibs = [statistics.mean(v) for v in per_engine.values() if v]
    return {"fase": phase, "memoria_media_pct": round(statistics.mean(mem)) if mem else None,
            "memoria_max_pct": max(mem) if mem else None,
            "mib_per_motore": round(statistics.mean(mibs), 1) if mibs else None,
            "mib_motore_max": round(max(mibs), 1) if mibs else None,
            "cpu_vm_pct": round(100 * (total - (cpu1[1] - cpu0[1])) / total, 1),
            "cpu_rubata_pct": round(100 * (cpu1[2] - cpu0[2]) / total, 1),
            "dev_mediana_s": round(statistics.median(dev_times), 3) if dev_times else None,
            "dev_max_s": round(max(dev_times), 3) if dev_times else None, "dev_senza_risposta": dev_failed}, True


def describe(n: int, m: dict) -> str:
    if m.get("fermato"):
        return f"- {n} motori, {m['fase']}: FERMATO, {m['fermato']}"
    line = (f"- {n} motori, {m['fase']}: memoria della VM {m['memoria_media_pct']} % (massimo {m['memoria_max_pct']} %), "
            f"{num(m['mib_per_motore'])} MiB per motore (il più grande {num(m['mib_motore_max'])}), "
            f"CPU della VM {num(m['cpu_vm_pct'])} %, dev risponde in {num(m['dev_mediana_s'], 3)} s "
            f"(al massimo {num(m['dev_max_s'], 3)} s, senza risposta {m['dev_senza_risposta']} volte)")
    if "comandi" in m:
        c = m["comandi"]
        line += (f"; comandi {c['n']}, accettati in {num(c['mediana_s'], 3)} s (95 su 100 entro "
                 f"{num(c['p95_s'], 3)} s), falliti {c['falliti']}")
    return line


def app_count() -> int:
    try:
        with open(os.path.join(ETC, "app-count"), encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):          # « » and accents whatever the terminal says it reads
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("azione", choices=("prepara", "gradini", "osserva", "stato", "pulisci"))
    p.add_argument("valore", nargs="?", help="prepara: quanti appartamenti nell'app; gradini: per esempio 5,10,20; "
                                             "osserva: minuti")
    p.add_argument("--minuti", type=float, default=3.0, help="gradini: minuti di misura a riposo e con i comandi")
    p.add_argument("--assesto-s", type=float, default=60.0, help="gradini: secondi di attesa dopo l'avvio")
    a = p.parse_args(argv)
    if getattr(os, "geteuid", lambda: 0)() != 0 and os.environ.get("CARICO_ROOT_CHECK") != "0":   # "0" only in the tests
        die("lancialo con sudo")
    say(f"{utc()} (UTC) carico_vm {a.azione} {a.valore or ''}".rstrip())
    if a.azione == "stato":
        ids = running()
        say(f"motori di prova: {len(ids)} ({', '.join(ids) or 'nessuno'}); memoria della VM {memory_pct()} %")
        for apt, (mib, cpu) in sorted(stats_of_engines().items()):
            say(f"  engine-{apt}: {num(mib)} MiB, CPU {num(cpu)} %")
        return 0
    if a.azione == "pulisci":
        ids = running()
        remove(ids)
        if not DRY:
            for d in (ETC, DATA):
                shutil.rmtree(d, ignore_errors=True)
        left = running() if not DRY else []
        say("Nessun motore di prova rimasto." if not left else f"RESTANO: {', '.join(left)}")
        return 0 if not left else 1
    image = dev_settings().get("ENGINE_IMAGE") or die("ENGINE_IMAGE mancante in dev.settings")
    dev_port = int(dev_settings().get("PORT", "8100"))
    ip = bind_ip()
    if a.azione == "prepara":
        if not a.valore or not a.valore.isdigit() or not 1 <= int(a.valore) <= 20:
            die("uso: prepara <quanti appartamenti nell'app, da 1 a 20>")
        n = int(a.valore)
        clash = ports_in_use() & set(range(PORT_BASE, PORT_BASE + MAX_ENGINES))
        if clash:
            die(f"porte già usate da motori veri: {sorted(clash)}")
        guard_before_step(n)
        if not DRY:
            os.makedirs(ETC, mode=0o700, exist_ok=True)
            with open(os.path.join(ETC, "app-count"), "w", encoding="utf-8") as f:
                f.write(str(n))
        say(f"immagine {image}, indirizzo {ip}, porte da {PORT_BASE} a {PORT_BASE + n - 1}")
        new = start_up_to(n, n, image, ip)
        healthy = [i for i in range(1, n + 1) if DRY or health(ip, PORT_BASE + i - 1)[0] == 200]
        say(f"{utc()} pronti {len(healthy)} motori su {n} ({len(new)} avviati ora)")
        return 0 if len(healthy) == n else 1
    if a.azione == "osserva":
        try:
            minutes = float(a.valore or "60")
        except ValueError:
            minutes = 0
        if not 0 < minutes <= 240:
            die("uso: osserva <minuti, al massimo 240>")
        say(f"INIZIO dell'osservazione della VM: {utc()} (UTC), {minutes:g} minuti")
        end = time.monotonic() + minutes * 60
        while time.monotonic() < end:
            ids = [int(x[len(PREFIX):]) for x in running()]
            m, ok = measure(min(60.0, end - time.monotonic()), ip, dev_port, ids, f"osservazione {utc()}")
            say(describe(len(ids), m))
            if not ok:
                break
        say(f"FINE dell'osservazione della VM: {utc()} (UTC)")
        return 0
    steps = sorted({int(x) for x in (a.valore or "").split(",") if x.strip().isdigit()})
    if not steps or steps[-1] > MAX_ENGINES:
        die(f"uso: gradini 5,10,20 (al massimo {MAX_ENGINES})")
    count = app_count()
    started = utc()
    say(f"INIZIO della prova dei motori per VM: {started} (UTC); memoria della VM ora {memory_pct()} %")
    results = []
    for target in steps:
        pct = memory_pct()
        if pct > STEP_MAX_PCT:                   # the steps already measured are still summed up below
            say(f"{utc()} memoria della VM al {pct} %, oltre il {STEP_MAX_PCT} %: non salgo a {target} motori")
            results.append((target, {"fase": "prima di partire", "fermato": f"memoria al {pct} %, non salgo"}))
            break
        say(f"\n{utc()} gradino: {target} motori")
        new = start_up_to(target, count, image, ip)
        if DRY:
            continue
        time.sleep(a.assesto_s)
        rest, ok = measure(a.minuti * 60, ip, dev_port, new, "a riposo")
        say(describe(target, rest))
        results.append((target, rest))
        if not ok:
            break
        cmds = Commands([int(x[len(PREFIX):]) for x in running()], ip, a.minuti * 60)
        cmds.start()
        busy, ok = measure(a.minuti * 60, ip, dev_port, new, "con i comandi")
        cmds.join(timeout=60)
        times = sorted(cmds.times)
        if ok:
            busy["comandi"] = {"n": len(times) + sum(cmds.failed.values()),
                               "mediana_s": statistics.median(times) if times else None,
                               "p95_s": times[max(0, math.ceil(0.95 * len(times)) - 1)] if times else None,
                               "falliti": dict(cmds.failed) or 0}
        say(describe(target, busy))
        results.append((target, busy))
        if not ok:
            break
    say(f"\nFINE della prova dei motori per VM: {utc()} (UTC)")
    say("\nRIEPILOGO")
    for target, m in results:
        say(describe(target, m))
    say("\nI motori di prova restano accesi: «pulisci» li toglie.")
    with open(f"risultati-motori-{started.replace(':', '')}.json", "w", encoding="utf-8") as f:
        json.dump([{"motori": t, **m} for t, m in results], f, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())

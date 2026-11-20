"""Tool A, package A1: the executor of the order receiver (docs/progetto-strumento-a-base.md §1, §3, §5, §6).

Root, minimal, a systemd service (domhouse-agent-esecutore.service). It listens ONLY on a local UNIX socket
(/run/domhouse-agent/esecutore.sock, folder root:domhouse-agent 750, socket 660) and serves only the reader's uid
(SO_PEERCRED). The reader is the exposed piece (it reads JSON from Pub/Sub and holds the VM's token): if it is
compromised, this is the only defence, so everything is checked again here, with this executor's OWN configuration
(/etc/domhouse/agent.conf, root's):
  - the order's schema, ids, prefixes, «dev» and parameters (comune.check_order) against its own environment;
  - on the shared VM (CONDIVISA=1) any order of «prod» is refused, whatever the reader says (§5.4);
  - the sequence per apartment: higher than the last applied, kept in a root file that stays after the engine goes
    (a tombstone: an old order cannot bring back an apartment just removed, §6.4).
Programs run with execve and a list of arguments (subprocess, never a shell), with the environment cleaned to PATH
alone (§1). Their output stays in the executor's journal (/var/lib/domhouse-executor/giornale, root, 14 days): the
result carries codes only, the system log one line of op_id, operation, apartment, environment, outcome, duration.

Package A1 executes «stato» (the engine's /health and the image it runs) and «capienza» (MemAvailable and the
engines); A3 «aggiorna_broker»; A2 «crea_motore» and «togli_motore» (docs/proposta-a2.md §4.2, §5.2). The others are
refused «non_disponibile» until their package. Every order that changes the VM holds the VM's lock
(/opt/domhouse/.engines.lock, the one of engine-vm.sh and broker-vm.sh) and runs the scripts with DOMHOUSE_LOCK_HELD=1.

Only the standard library. No address and no VM name in the code (§7.1 of the registro): the engines' address is
BIND_IP of the configuration or, if absent, the VM's internal address from the metadata server.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import socket
import socketserver
import struct
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comune  # noqa: E402

CONFIG_PATH = Path("/etc/domhouse/agent.conf")
SOCKET_PATH = Path("/run/domhouse-agent/esecutore.sock")
CLEAN_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}
DOCKER = "/usr/bin/docker"
RUN_TIMEOUT_S = 30
HEALTH_TIMEOUT_S = 5
HEALTH_MAX_BYTES = 64 * 1024
JOURNAL_DAYS = 14
REQUEST_MAX_BYTES = 2 * comune.MAX_ORDER_BYTES + 1024
PEER_TIMEOUT_S = 10                 # R14: a peer that sends nothing does not hold the only executor
# R16: every refusal the reader should have made itself means a reader that lets things through (compromised?):
# an alarm; not these three, which are normal outcomes, nor errore_interno, which has its own line
# A3 code review, point 1: lab-01 before its migration and an apartment the broker does not know are normal refusals
NORMAL_REFUSALS = {"seq_vecchia", "non_disponibile", "motore_assente", "errore_interno", "appartamento_sconosciuto",
                   "migrazione_non_fatta",
                   # A2: no room, or a port someone took by hand: normal; the other refusals of A2 are alarms
                   "capienza_insufficiente", "staging_pieno", "porta_occupata"}
# A2 (proposta §4.3, review point 6): the approved image, only by digest, from our repository
DIGEST_RE = re.compile(r"^europe-west8-docker\.pkg\.dev/domotica-poc-511707/domotica/engine@sha256:[0-9a-f]{64}$")
# A7: the caps of engine-vm.sh mem_limit_of (decision 1128): ENGINE_MEM_LIMIT in the settings, else 120 MB for the
# test engines and 256 MB for the others; the load test's engines (scripts/load: ports 8170-8199) stay out (§5.6)
MEM_LIMIT_RE = re.compile(r"^ENGINE_MEM_LIMIT=([0-9]{2,5})m$", re.M)
TEST_CAP_MB, OTHER_CAP_MB = 120, 256
LOAD_PORTS = range(8170, 8200)
EMPTY_CATALOG = "rooms: []\ndevices: []\n"
# A2: the worst case of one crea_motore (lock, install, broker refused, both taken back) stays well under the time
# the reader waits for an answer (lettore.EXECUTOR_TIMEOUT_S; a test keeps it so)
LOCK_WAIT_S = 60
INSTALL_TIMEOUT_S = 300                      # a pull and a start of the engine (health: at most about 3 minutes)
BROKER_TIMEOUT_S = 60
REMOVE_TIMEOUT_S = 90
WORST_CREATE_S = LOCK_WAIT_S + INSTALL_TIMEOUT_S + 2 * BROKER_TIMEOUT_S + REMOVE_TIMEOUT_S
PORT_RE = re.compile(r"^PORT=([0-9]{4,5})$", re.M)
ENV_RE = re.compile(r"^ENV=(staging|prod)$", re.M)
METADATA_IP = "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip"
CONFIG_KEYS = {"AMBIENTE", "CONDIVISA", "LETTORE", "MAX_MOTORI_STAGING", "BIND_IP", "BUDGET_MB_STAGING",
               "BUDGET_MB_PROD"}


class Config(NamedTuple):
    ambiente: str
    condivisa: bool
    reader_uid: int
    opt: Path = Path("/opt/domhouse")
    state: Path = Path("/var/lib/domhouse-executor")
    bind_ip: str | None = None
    max_staging: int = 4
    budget_staging: int | None = 500           # A7 (answer 1197): the sum of the staging engines' caps, at most
    budget_prod: int | None = None             # A7 (answer 1202): set with the second VM (A10); none = no room
    meminfo: Path = Path("/proc/meminfo")
    keys_dir: Path = Path("/etc/domhouse")     # A3 §6.3: agent-ordini.key and agent-risultati.key, root's, 600
    broker_etc: Path = Path("/etc/domhouse/_broker")   # A3 §6.1: the broker's list of apartments and devices/
    etc: Path = Path("/etc/domhouse")          # A2: the catalogs, the keys' files of the engines, agent-immagine-<env>
    data: Path = Path("/data")                 # A2: the engines' data
    proc_net: Path = Path("/proc/net")         # A2: tcp and tcp6, the ports listening (no AF_NETLINK needed)
    # second reading of the code review (N1, N2): on the VM the service checks that its ReadOnlyPaths still hold
    check_protection: bool = False


def read_config(path: Path, uid_of: Callable[[str], int], check_owner: bool = True) -> Config:
    """KEY=value, only the known keys, each with its rule. On the VM the file must be root's and writable by root
    only: otherwise the executor does not start."""
    if check_owner:
        st = path.stat()
        if st.st_uid != 0 or st.st_mode & 0o022:
            raise ValueError(f"{path}: deve essere di root e scrivibile solo da root")
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key not in CONFIG_KEYS or key in values:
            raise ValueError(f"riga non ammessa: {line[:60]}")
        values[key] = value.strip()
    if values.get("AMBIENTE") not in comune.ENVIRONMENTS:
        raise ValueError("AMBIENTE deve essere staging o prod")
    if values.get("CONDIVISA", "1") not in ("0", "1"):
        raise ValueError("CONDIVISA deve essere 0 o 1")
    lettore = values.get("LETTORE", "domhouse-agent")
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", lettore):
        raise ValueError("LETTORE non valido")
    max_staging = values.get("MAX_MOTORI_STAGING", "4")
    if not re.fullmatch(r"[1-9][0-9]?", max_staging):
        raise ValueError("MAX_MOTORI_STAGING non valido")
    budgets = {}
    for key, default in (("BUDGET_MB_STAGING", "500"), ("BUDGET_MB_PROD", None)):
        value = values.get(key, default)
        if value is not None and not re.fullmatch(r"[1-9][0-9]{1,5}", value):
            raise ValueError(f"{key} non valido")
        budgets[key] = int(value) if value is not None else None
    bind_ip = values.get("BIND_IP")
    if bind_ip is not None and not re.fullmatch(r"[0-9]{1,3}(\.[0-9]{1,3}){3}", bind_ip):
        raise ValueError("BIND_IP non valido")
    return Config(ambiente=values["AMBIENTE"], condivisa=values.get("CONDIVISA", "1") == "1",
                  reader_uid=uid_of(lettore), bind_ip=bind_ip, max_staging=int(max_staging),
                  budget_staging=budgets["BUDGET_MB_STAGING"], budget_prod=budgets["BUDGET_MB_PROD"])


def read_keys(path: Path, check_owner: bool = True) -> list[bytes]:
    """A3 §6.3: one key per line, 32 bytes in hex; one, or two during a change of key (the new one first). On the VM
    the file must be root's and readable by root only. Read at every order: a change needs no restart."""
    if check_owner:
        st = path.stat()
        if st.st_uid != 0 or st.st_mode & 0o077:
            raise ValueError(f"{path}: deve essere di root e leggibile solo da root")
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not 1 <= len(lines) <= 2 or not all(comune.KEY_RE.fullmatch(line) for line in lines):
        raise ValueError(f"{path}: una o due chiavi esadecimali da 64 caratteri")
    return [bytes.fromhex(line) for line in lines]


def read_image(path: Path, check_owner: bool = True) -> str:
    """A2 (proposta §4.3): the approved image of this environment, one line «…/engine@sha256:<64>», root's file
    writable by root only, read at every order (publish-all.sh writes it)."""
    if check_owner:
        st = path.stat()
        if st.st_uid != 0 or st.st_mode & 0o022:
            raise ValueError(f"{path}: deve essere di root e scrivibile solo da root")
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) != 1 or not DIGEST_RE.fullmatch(lines[0]):
        raise ValueError(f"{path}: una riga con l'immagine per digest")
    return lines[0]


@contextlib.contextmanager
def vm_lock(path: Path):
    """The VM's lock (flock on the same file as engine-vm.sh), waited for at most LOCK_WAIT_S. Only on Linux: where
    fcntl does not exist (the tests on Windows) there is nothing to lock."""
    try:
        import fcntl
    except ImportError:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        deadline = time.monotonic() + LOCK_WAIT_S
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise TimeoutError("blocco della VM occupato") from None
                time.sleep(1)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def run_program(argv: list[str], env: dict, timeout: float) -> tuple[int, str]:
    """execve with a list of arguments: never a shell, never the caller's environment. Code review A2, point 3: the
    program runs in a session of its own, and past its time the WHOLE group is killed (a «docker compose up» left
    alive could recreate a container after the way back removed it), before the caller takes anything back."""
    try:
        proc = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                shell=False, stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return 127, ""
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            if hasattr(os, "killpg"):
                os.killpg(proc.pid, signal.SIGKILL)
            else:                                   # Windows (the tests): no process groups
                proc.kill()
        except OSError:
            pass
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return 127, ""
    return proc.returncode, (out or "")[-4000:]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """R13: an engine is not trusted: a redirect is never followed (it answers with its 3xx code)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# R13: no redirects, and no proxy from the environment (the environment is clean anyway)
HEALTH_OPENER = urllib.request.OpenerDirector()
for _handler in (urllib.request.ProxyHandler({}), urllib.request.UnknownHandler(), urllib.request.HTTPHandler(),
                 urllib.request.HTTPDefaultErrorHandler(), NoRedirect(), urllib.request.HTTPErrorProcessor()):
    HEALTH_OPENER.add_handler(_handler)


def _sync_dir(path: Path) -> None:
    """R6, R10: fsync of the folder after a rename (Linux); a no-op where folders cannot be opened."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def http_get(url: str, timeout: float) -> tuple[int, dict | None]:
    """The engine's /health: code and JSON, the body read up to HEALTH_MAX_BYTES (the engine is not trusted)."""
    try:
        with HEALTH_OPENER.open(url, timeout=timeout) as answer:
            body = answer.read(HEALTH_MAX_BYTES + 1)
            code = answer.status
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (OSError, ValueError):
        return 0, None
    if len(body) > HEALTH_MAX_BYTES:
        return code, None
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return code, None
    return code, data if isinstance(data, dict) else None


def _short(value) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= 40 else None


class Esecutore:
    def __init__(self, config: Config, run=run_program, http_get=http_get, log: Callable[[str], None] = print,
                 keys: Callable[[str], list[bytes]] | None = None, clock: Callable[[], datetime] | None = None,
                 image: Callable[[], str] | None = None, lock=None):
        self.config, self.run, self.http_get, self.log = config, run, http_get, log
        self.keys = keys or (lambda name: read_keys(config.keys_dir / f"agent-{name}.key"))
        self.clock = clock or (lambda: datetime.now(UTC))
        self.image = image or (lambda: read_image(config.etc / f"agent-immagine-{config.ambiente}"))
        self.lock = lock or (lambda: vm_lock(config.opt / ".engines.lock"))

    # ---- the request -------------------------------------------------------------------------------------------
    def handle(self, data: bytes, peer_uid: int) -> dict:
        started = time.monotonic()
        output: list[str] = []
        if peer_uid != self.config.reader_uid:
            out = comune.result_for_raw(data, "rifiutato", "chiamante_non_ammesso")
        else:
            out = self._checked(data, output)
        out = self._signed(out, data)
        if out["esito"] == "rifiutato" and out["codice"] not in NORMAL_REFUSALS:      # R16
            self.log(f"agent alarm codice={out['codice']} ambiente={self.config.ambiente} op_id={out.get('op_id')}")
        self._record(out, started, output)
        return out

    # ---- A3 §6.3: signatures both ways -------------------------------------------------------------------------
    @staticmethod
    def _parsed(data: bytes) -> dict | None:
        try:
            o = json.loads(bytes(data).decode("utf-8")) if len(data) <= comune.MAX_ORDER_BYTES else None
        except (UnicodeDecodeError, ValueError, RecursionError):
            return None
        return o if isinstance(o, dict) else None

    def _keys(self, name: str) -> list[bytes]:
        try:
            keys = self.keys(name)
        except (OSError, ValueError):
            keys = []
        if not keys:
            self.log(f"agent alarm codice=chiave_illeggibile chiave={name}")
        return keys

    def _signature_problem(self, data: bytes) -> str | None:
        """Before anything else: the server's signature (one of the «ordini» keys), then the time by this clock."""
        o = self._parsed(data)
        if o is None or not comune.signed_by(self._keys("ordini"), o):
            return "firma_non_valida"
        at = o.get("firmato_at")
        if not isinstance(at, str) or not comune.TIME_RE.fullmatch(at):
            return "campo_non_valido"
        signed_at = datetime.fromisoformat(at.replace("Z", "+00:00"))
        now = self.clock()
        if now - signed_at > timedelta(seconds=comune.MAX_AGE_S) or signed_at - now > timedelta(seconds=comune.AHEAD_S):
            return "scaduto"
        return None

    def _signed(self, out: dict, data: bytes) -> dict:
        """Every result: the fingerprint of the order executed, then the «risultati» signature. Without its key the
        result goes unsigned (the server never takes it as a success) and an alarm is written."""
        out = dict(out)
        o = self._parsed(data)
        if o is not None:
            out["ordine_sha256"] = comune.order_sha256(o)
        keys = self._keys("risultati")
        if keys:
            out["firma"] = comune.signature(keys[0], out)
        return out

    def _checked(self, data: bytes, output: list[str]) -> dict:
        problem = self._signature_problem(data)                 # first of all (review point 1)
        if problem is not None:
            return comune.result_for_raw(data, "rifiutato", problem)
        if self.config.condivisa and self._says_prod(data):
            return comune.result_for_raw(data, "rifiutato", "prod_non_ammesso")
        try:
            order = comune.check_order(data, self.config.ambiente)
        except comune.Refused as refused:
            return comune.result_for_raw(data, "rifiutato", refused.code)
        if order.operazione not in comune.EXECUTED:
            return comune.result(order, "rifiutato", "non_disponibile")
        if order.operazione == "capienza":
            return comune.result(order, "riuscito", "ok", self._capacity())
        try:
            fresh = self._next_seq(order.apartment_id, order.seq)    # first: the tombstone holds without the engine
        except ValueError:                                           # R6: unreadable: refused, with an alarm
            self.log(f"agent alarm codice=lapide_illeggibile apartment={order.apartment_id}")
            return comune.result(order, "rifiutato", "errore_interno")
        if not fresh:
            return comune.result(order, "rifiutato", "seq_vecchia")
        if order.operazione in ("aggiorna_broker", "crea_motore", "togli_motore"):
            lost = self._protection_lost() if self.config.check_protection else []
            if lost:
                self.log(f"agent alarm codice=protezione_persa percorsi={','.join(lost)}")
                output.append("file protetto scrivibile: riavviare l'esecutore")
                return comune.result(order, "fallito", "errore_interno")
            try:
                with self.lock():                                    # one change at a time on the VM (§6.1)
                    if order.operazione == "aggiorna_broker":
                        return self._update_broker(order, output)
                    if order.operazione == "crea_motore":
                        return self._create(order, output)
                    return self._remove(order, output)
            except TimeoutError:
                output.append(f"blocco della VM occupato da oltre {LOCK_WAIT_S} s")
                return comune.result(order, "fallito", "errore_interno")
        port = self._port(order.apartment_id)
        if port is None:
            return comune.result(order, "rifiutato", "motore_assente")
        return comune.result(order, "riuscito", "ok", self._state(order.apartment_id, port, output))

    # ---- A3 §6.1: aggiorna_broker -------------------------------------------------------------------------------
    LEGACY = ("lab-01",)            # §6.4: the apartments of the old «-devices» secret, until their migration

    def _update_broker(self, order: comune.Order, output: list[str]) -> dict:
        """The complete list of fingerprints, written atomically to devices/<apt> (root, 600), then the broker's sync
        (only the apartments' files that changed; the reload drops a device removed or changed: bench, 19 November)."""
        apartment = order.apartment_id
        if apartment in self.LEGACY and not (self.config.state / "migrati" / apartment).exists():
            return comune.result(order, "rifiutato", "migrazione_non_fatta")
        try:
            known = (self.config.broker_etc / "apartments").read_text(encoding="utf-8").split()
        except OSError:
            known = []
        if apartment not in known:
            return comune.result(order, "rifiutato", "appartamento_sconosciuto")
        devices = sorted(order.parametri["dispositivi"], key=lambda d: d["id"])
        folder = self.config.broker_etc / "devices"
        folder.mkdir(mode=0o700, exist_ok=True)
        target, temporary = folder / apartment, folder / f".{apartment}.nuovo"
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
                out.write("".join(f"{d['id']} {d['impronta']}\n" for d in devices))
                out.flush()
                os.fsync(out.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
            _sync_dir(folder)
        except OSError as exc:
            output.append(f"scrittura di devices/{apartment}: {type(exc).__name__}")
            return comune.result(order, "fallito", "errore_interno")
        # 20 November (Q2.3c on the VM): ProtectHome hides /root/.docker; without DOCKER_CONFIG «docker compose» is not
        # found and the sync stops («manca docker compose»): the same DOCKER_CONFIG as docker inspect (_state)
        code, text = self.run(["/bin/bash", str(self.config.opt / "broker-vm.sh"), "sync"], self._script_env(),
                              RUN_TIMEOUT_S * 4)
        output.append(text)
        if code != 0 or f"kept {apartment}" in text.split("\n"):
            return comune.result(order, "fallito", "sync_fallito")
        return comune.result(order, "riuscito", "ok", {"dispositivi": len(devices)})

    def _protection_lost(self) -> list[str]:
        """Second reading of the code review, N1 and N2: a ReadOnlyPaths entry on a single file is a bind mount that
        no longer covers a file REPLACED on the host after the start (publish-all, a new key), nor one created after
        it. Such a file is writable again for this service: every order that changes the VM is refused, with an
        alarm, until the service restarts (publish-all restarts it under the lock after each replacement)."""
        c = self.config
        paths = [c.etc / "agent.conf", c.keys_dir / "agent-ordini.key", c.keys_dir / "agent-risultati.key",
                 c.etc / f"agent-immagine-{c.ambiente}", c.opt / "engine-vm.sh", c.opt / "broker-vm.sh",
                 c.opt / "broker_accounts.py", c.opt / "compose.yaml", c.opt / "compose.catalog.yaml", c.opt / "agent"]
        return [str(p) for p in paths if p.exists() and os.access(p, os.W_OK)]

    def _script_env(self) -> dict:
        """The scripts' environment: PATH, docker's folder (ProtectHome hides /root/.docker) and the lock held."""
        return {**CLEAN_ENV, "DOCKER_CONFIG": str(self.config.state / "docker"), "DOMHOUSE_LOCK_HELD": "1"}

    def _script(self, name: str, *args: str, timeout: float = RUN_TIMEOUT_S * 4, output: list[str]) -> int:
        code, text = self.run(["/bin/bash", str(self.config.opt / name), *args], self._script_env(), timeout)
        output.append(f"{name} {args[0]}: {code} {text}")
        return code

    # ---- A2 §4.2: crea_motore -----------------------------------------------------------------------------------
    def _mark(self, apartment: str) -> Path:
        return self.config.state / "creati" / apartment

    def _read_mark(self, apartment: str) -> dict | None:
        try:
            mark = json.loads(self._mark(apartment).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return {}                                     # there but unreadable: never «absent»
        return mark if isinstance(mark, dict) else {}

    def _write_atomic(self, path: Path, text: str, mode: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.parent / f".{path.name}.nuovo"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        _sync_dir(path.parent)

    def _listening(self, port: int) -> bool:
        """The port listening on the VM, from /proc/net/tcp and tcp6 (state 0A), without AF_NETLINK."""
        for name in ("tcp", "tcp6"):
            try:
                lines = (self.config.proc_net / name).read_text(encoding="ascii", errors="replace").splitlines()[1:]
            except OSError:
                continue
            for line in lines:
                parts = line.split()
                if len(parts) > 3 and parts[3] == "0A" and ":" in parts[1]:
                    try:
                        if int(parts[1].rsplit(":", 1)[1], 16) == port:
                            return True
                    except ValueError:
                        continue
        return False

    def _port_taken(self, port: int, apartment: str) -> bool:
        for settings in self.config.opt.glob("*.settings"):
            if settings.stem == apartment:
                continue
            found = PORT_RE.search(settings.read_text(encoding="utf-8", errors="replace"))
            if found and int(found.group(1)) == port:
                return True
        return self._listening(port)

    def _create(self, order: comune.Order, output: list[str]) -> dict:
        apartment, port, env = order.apartment_id, order.parametri["porta"], self.config.ambiente
        try:
            image = self.image()
        except (OSError, ValueError) as exc:
            output.append(f"immagine approvata: {type(exc).__name__}")
            image = ""
        if not DIGEST_RE.fullmatch(image):
            return comune.result(order, "rifiutato", "immagine_non_approvata")
        wanted = {"porta": port, "immagine": image, "env": env}
        mark = self._read_mark(apartment)
        settings = self.config.opt / f"{apartment}.settings"
        if mark is not None and mark != wanted:
            # code review A2, point 7: a «Riprova» after a new approved image, with no engine installed yet: the mark
            # takes the new image; with the engine there, a different image is never changed silently
            same_place = {k: mark.get(k) for k in ("porta", "env")} == {"porta": port, "env": env}
            if not (same_place and not settings.exists()):
                return comune.result(order, "rifiutato", "gia_esiste_diverso")
            try:
                self._write_atomic(self._mark(apartment), json.dumps(wanted, sort_keys=True), 0o600)
            except OSError as exc:
                output.append(f"segno di creazione: {type(exc).__name__}")
                return comune.result(order, "fallito", "errore_interno")
        if mark is None:                                 # step 0 for a new apartment (step 1: ours with the same values)
            # code review A2, point 4: any trace of an apartment the agent did not make (settings, key file, catalog,
            # the broker's list) refuses: the way back would remove what someone made by hand. An empty data folder
            # alone is allowed (N6), a non-empty one is dati_presenti below
            if self._traces(apartment, data=False):
                return comune.result(order, "rifiutato", "gia_esiste_diverso")    # lab-01, made by hand
            if self._port_taken(port, apartment):
                return comune.result(order, "rifiutato", "porta_occupata")
            problem = comune.room_problem(self._capacity(), self.config.ambiente)    # A7: the server's rule
            if problem is not None:
                return comune.result(order, "rifiutato", problem)
            folder = self.config.data / apartment
            if folder.is_symlink() or (folder.exists() and (not folder.is_dir() or any(folder.iterdir()))):
                return comune.result(order, "rifiutato", "dati_presenti")
            try:                                         # 1b: the mark before anything else
                self._write_atomic(self._mark(apartment), json.dumps(wanted, sort_keys=True), 0o600)
            except OSError as exc:
                output.append(f"segno di creazione: {type(exc).__name__}")
                return comune.result(order, "fallito", "errore_interno")
        catalog = self.config.etc / f"{apartment}.catalog.yaml"
        if not catalog.exists():                         # 2: before compose up (a missing file becomes a folder)
            try:
                self._write_atomic(catalog, EMPTY_CATALOG, 0o644)
            except OSError as exc:
                output.append(f"catalogo: {type(exc).__name__}")
                self._take_back(apartment, broker=False, output=output)
                return comune.result(order, "fallito", "errore_interno")
        code = self._script("engine-vm.sh", "install", "--da-agente", apartment, str(port), image, "shelly", env,
                            str(catalog), timeout=INSTALL_TIMEOUT_S, output=output)
        if code != 0:                                    # 3: exit 3 a secret, 4 the engine's health
            self._take_back(apartment, broker=False, output=output)
            return comune.result(order, "fallito", {3: "segreto_illeggibile", 4: "motore_non_sano"}.get(
                code, "errore_interno"))
        if self._script("broker-vm.sh", "add-apartment", apartment, timeout=BROKER_TIMEOUT_S, output=output) != 0:
            self._take_back(apartment, broker=True, output=output)
            return comune.result(order, "fallito", "broker_fallito")
        return comune.result(order, "riuscito", "ok", {"porta": port, "immagine": image})

    def _take_back(self, apartment: str, broker: bool, output: list[str]) -> bool:
        """What this order made, in reverse; the mark goes last and only when everything went."""
        ok = True
        if broker:
            ok &= self._script("broker-vm.sh", "remove-apartment", apartment, timeout=BROKER_TIMEOUT_S,
                               output=output) == 0
        ok &= self._script("engine-vm.sh", "remove", apartment, timeout=REMOVE_TIMEOUT_S, output=output) == 0
        (self.config.etc / f"{apartment}.catalog.yaml").unlink(missing_ok=True)
        if ok:
            self._mark(apartment).unlink(missing_ok=True)
        else:
            self.log(f"agent alarm codice=ritorno_indietro_incompleto apartment={apartment}")
        return ok

    # ---- A2 §5.2: togli_motore (the piece A6 reuses) --------------------------------------------------------------
    def _traces(self, apartment: str, data: bool = True) -> bool:
        try:
            known = (self.config.broker_etc / "apartments").read_text(encoding="utf-8").split()
        except OSError:
            known = []
        paths = [self.config.opt / f"{apartment}.settings", self.config.etc / f"{apartment}.env",
                 self.config.etc / f"{apartment}.catalog.yaml"] + ([self.config.data / apartment] if data else [])
        return apartment in known or any(p.exists() or p.is_symlink() for p in paths)

    def _remove(self, order: comune.Order, output: list[str]) -> dict:
        apartment = order.apartment_id
        if self._read_mark(apartment) is None:
            if self._traces(apartment):
                return comune.result(order, "rifiutato", "non_creato_da_agente")   # lab-01: never until A6
            return comune.result(order, "riuscito", "ok")                          # already removed
        if self._script("engine-vm.sh", "remove", apartment, timeout=REMOVE_TIMEOUT_S, output=output) != 0:
            return comune.result(order, "fallito", "errore_interno")
        if self._script("broker-vm.sh", "remove-apartment", apartment, timeout=BROKER_TIMEOUT_S, output=output) != 0:
            return comune.result(order, "fallito", "broker_fallito")
        self._mark(apartment).unlink(missing_ok=True)                              # last
        return comune.result(order, "riuscito", "ok")

    @staticmethod
    def _says_prod(data: bytes) -> bool:
        try:
            o = json.loads(bytes(data).decode("utf-8")) if len(data) <= comune.MAX_ORDER_BYTES else None
        except (UnicodeDecodeError, ValueError):
            return False
        return isinstance(o, dict) and o.get("ambiente") == "prod"

    # ---- the operations of A1 ------------------------------------------------------------------------------
    def _state(self, apartment_id: str, port: int, output: list[str]) -> dict:
        code, health = self.http_get(f"http://{self._bind_ip()}:{port}/api/v1/health", HEALTH_TIMEOUT_S)
        dati: dict = {"health": code}
        if health:
            if _short(health.get("status")):
                dati["stato"] = health["status"]
            connector = health.get("connector")
            if isinstance(connector, dict) and _short(connector.get("status")):
                dati["connector"] = connector["status"]
        # docker's own folder in the executor's state: /root/.docker is hidden by ProtectHome
        env = {**CLEAN_ENV, "DOCKER_CONFIG": str(self.config.state / "docker")}
        rc, image = self.run([DOCKER, "inspect", "-f", "{{.Config.Image}}", f"engine-{apartment_id}"], env,
                             RUN_TIMEOUT_S)
        output.append(f"docker inspect: {rc} {image.strip()[:200]}")
        image = image.strip()
        if rc == 0 and 0 < len(image) <= comune.DATA_MAX_LEN and "\n" not in image:
            dati["immagine"] = image
        return dati

    def _capacity(self) -> dict:
        available_kb = 0
        for line in self.config.meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                available_kb = int(line.split()[1])
        engines = 0
        by_env = {"staging": [0, 0], "prod": [0, 0]}         # engines, sum of their caps (MB)
        for settings in sorted(self.config.opt.glob("*.settings")):
            text = settings.read_text(encoding="utf-8", errors="replace")
            apartment = settings.stem
            port = PORT_RE.search(text)
            if apartment.startswith(("test-carico-", "carico-")) or (port and int(port.group(1)) in LOAD_PORTS):
                continue                                         # the load test stays out (§5.6)
            engines += 1
            env = ENV_RE.search(text)
            env = env.group(1) if env else "staging"           # dev and lab-01 without ENV: staging
            own = MEM_LIMIT_RE.search(text)
            if own:
                cap = int(own.group(1))
            elif apartment == "dev" or apartment.startswith(("lab-", "test-")):
                cap = TEST_CAP_MB
            else:
                cap = OTHER_CAP_MB
            by_env[env][0] += 1
            by_env[env][1] += cap
        here = self.config.ambiente
        return {"mem_available_mb": round(available_kb / 1024), "motori": engines,
                "motori_staging": by_env["staging"][0], "massimo_staging": self.config.max_staging,
                # A7: the environment of this executor, the cap the new engine would have, the sum and the budget
                "motori_ambiente": by_env[here][0], "tetto_nuovo_mb": TEST_CAP_MB if here == "staging" else OTHER_CAP_MB,
                "somma_tetti_mb": by_env[here][1],
                "budget_mb": self.config.budget_staging if here == "staging" else self.config.budget_prod}

    # ---- state of the VM ---------------------------------------------------------------------------------------
    def _port(self, apartment_id: str) -> int | None:
        settings = self.config.opt / f"{apartment_id}.settings"
        if not settings.is_file():
            return None
        found = PORT_RE.search(settings.read_text(encoding="utf-8", errors="replace"))
        return int(found.group(1)) if found else None

    def _bind_ip(self) -> str:
        if self.config.bind_ip:
            return self.config.bind_ip
        request = urllib.request.Request(METADATA_IP, headers={"Metadata-Flavor": "Google"})
        with urllib.request.urlopen(request, timeout=3) as answer:
            ip = answer.read(64).decode("ascii", "replace").strip()
        if not re.fullmatch(r"[0-9]{1,3}(\.[0-9]{1,3}){3}", ip):
            raise OSError("indirizzo interno non valido dal server dei metadati")
        self.config = self.config._replace(bind_ip=ip)
        return ip

    def _next_seq(self, apartment_id: str, seq: int) -> bool:
        """Higher than the last applied, then written (atomically, synced) before the operation runs. The file stays.
        R6: a tombstone that is there but unreadable, empty or 0 raises ValueError: never read as «none»."""
        folder = self.config.state / "seq"
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = folder / apartment_id
        try:
            text = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            last = 0
        except (OSError, UnicodeDecodeError) as exc:       # R6: a folder, no permission, not text: unreadable
            raise ValueError("lapide illeggibile") from exc
        else:
            if not re.fullmatch(r"[1-9][0-9]{0,9}", text):
                raise ValueError("lapide illeggibile")
            last = int(text)
        if seq <= last:
            return False
        tmp = folder / f".{apartment_id}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(f"{seq}\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _sync_dir(folder)
        return True

    def _record(self, out: dict, started: float, output: list[str]) -> None:
        duration = round((time.monotonic() - started) * 1000)
        self.log(f"agent exec op_id={out.get('op_id')} operazione={out.get('operazione')} "
                 f"apartment={out.get('apartment_id')} ambiente={out.get('ambiente')} esito={out['esito']} "
                 f"codice={out['codice']} durata_ms={duration}")
        folder = self.config.state / "giornale"
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        now = datetime.now(UTC)
        entry = {"ts": now.isoformat(), **out, "durata_ms": duration, "uscita": output}
        with open(folder / f"{now.date().isoformat()}.jsonl", "a", encoding="utf-8") as journal:
            journal.write(json.dumps(entry, ensure_ascii=False) + "\n")
        oldest = (now - timedelta(days=JOURNAL_DAYS)).date().isoformat()
        for old in folder.glob("*.jsonl"):
            if old.stem < oldest:
                old.unlink(missing_ok=True)


# ---- the socket ---------------------------------------------------------------------------------------------------
def peer_uid(sock: socket.socket) -> int:
    """SO_PEERCRED (Linux): the uid of the process on the other side, given by the kernel."""
    creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", creds)[1]


def make_server(path: Path, executor: Esecutore) -> socketserver.UnixStreamServer:
    """One request per connection, one connection at a time (one order at a time for the whole VM, §6.1)."""

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            # R14: the peer first, before reading a byte; then at most PEER_TIMEOUT_S to send its request
            uid = peer_uid(self.connection)
            if uid != executor.config.reader_uid:
                out = executor.handle(b"", uid)
                self.wfile.write(json.dumps(out, ensure_ascii=False).encode("utf-8") + b"\n")
                return
            self.connection.settimeout(PEER_TIMEOUT_S)
            try:
                line = self.rfile.readline(REQUEST_MAX_BYTES + 1)
            except OSError:
                return
            try:
                request = json.loads(line.decode("utf-8")) if len(line) <= REQUEST_MAX_BYTES else None
                data = request["ordine"].encode("utf-8") if isinstance(request, dict) and \
                    isinstance(request.get("ordine"), str) else b""
            except (UnicodeDecodeError, ValueError):
                data = b""
            out = executor.handle(data, uid)
            self.wfile.write(json.dumps(out, ensure_ascii=False).encode("utf-8") + b"\n")

    if path.exists() or path.is_symlink():
        path.unlink()
    server = socketserver.UnixStreamServer(str(path), Handler)
    os.chmod(path, 0o660)
    return server


def main() -> int:
    import pwd
    import syslog
    config = read_config(CONFIG_PATH, uid_of=lambda name: pwd.getpwnam(name).pw_uid)._replace(check_protection=True)
    syslog.openlog("domhouse-agent-esecutore")
    executor = Esecutore(config, log=lambda line: syslog.syslog(syslog.LOG_INFO, line))
    server = make_server(SOCKET_PATH, executor)
    os.chown(SOCKET_PATH, 0, pwd.getpwnam("domhouse-agent").pw_gid)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())

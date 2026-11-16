"""Tool A, package A1: the reader of the order receiver (docs/progetto-strumento-a-base.md §1, §3, §6).

An unprivileged systemd service (domhouse-agent-lettore.service, user domhouse-agent). With the VM's token (metadata
server) it takes orders from ONE Pub/Sub subscription, the one of its environment: the environment comes from its
configuration (/etc/domhouse/agent-lettore.conf), never from the message. For each order:
  1. older than 15 minutes by Pub/Sub's publish_time (which the publisher cannot forge): «scartato: scaduto»;
  2. the checks of comune.py; refused: «rifiutato: <codice>» (an order of another environment also writes an alarm
     line);
  3. its journal entry (/var/lib/domhouse-agent/giornale/<op_id>.json): a copy of a finished order gets the recorded
     result again, a copy of one in progress is ignored;
  4. «in corso» is written (and synced) BEFORE anything runs, then the order is acknowledged at once: Pub/Sub's
     acknowledgement time no longer matters. If the journal cannot be written the order is NOT acknowledged: Pub/Sub
     tries again, and after 5 deliveries it goes to the dead letters (with an alarm);
  5. the executor runs it (local socket); its answer is filtered to codes and short data;
  6. the result goes to the results queue; if that fails it is published again at the next step.
At the start, an entry left open (the VM restarted during an order) becomes «fallito: interrotto» and is never run
again: there is «Riprova» on the server (§6.2).

The journal keeps only what the result needs (op_id, operation, apartment, environment, seq): never the parameters,
never the catalog, never who asked. The system log gets one line per order (op_id, operation, apartment, environment,
outcome, code) and one count per day; never an email, never a script's output.

Only the standard library. No address and no VM name in the code (§7.1 of the registro): project, subscription and
results topic come from the configuration.
"""
from __future__ import annotations

import base64
import json
import os
import re
import socket
import sys
import time
import urllib.request
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comune  # noqa: E402

CONFIG_PATH = Path("/etc/domhouse/agent-lettore.conf")
JOURNAL_PATH = Path("/var/lib/domhouse-agent/giornale")
SOCKET_PATH = Path("/run/domhouse-agent/esecutore.sock")
PUBSUB = "https://pubsub.googleapis.com/v1/"
TOKEN_URL = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
JOURNAL_DAYS = 14
EXECUTOR_TIMEOUT_S = 600            # an operation of a later package (crea_motore) can take minutes
PULL_MAX = 5
RESULT_KEYS = ("op_id", "operazione", "apartment_id", "ambiente", "seq", "esito", "codice", "dati")
SUBSCRIPTION_RE = re.compile(r"^projects/[a-z][a-z0-9-]{4,29}/subscriptions/[A-Za-z][A-Za-z0-9._~%+-]{2,254}$")
TOPIC_RE = re.compile(r"^projects/[a-z][a-z0-9-]{4,29}/topics/[A-Za-z][A-Za-z0-9._~%+-]{2,254}$")


def read_config(path: Path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key not in ("AMBIENTE", "SOTTOSCRIZIONE", "RISULTATI") or key in values:
            raise ValueError(f"riga non ammessa: {line[:60]}")
        values[key] = value.strip()
    if values.get("AMBIENTE") not in comune.ENVIRONMENTS:
        raise ValueError("AMBIENTE deve essere staging o prod")
    if not SUBSCRIPTION_RE.fullmatch(values.get("SOTTOSCRIZIONE", "")):
        raise ValueError("SOTTOSCRIZIONE non valida (projects/<p>/subscriptions/<s>)")
    if not TOPIC_RE.fullmatch(values.get("RISULTATI", "")):
        raise ValueError("RISULTATI non valido (projects/<p>/topics/<t>)")
    return values


class Lettore:
    def __init__(self, ambiente: str, pubsub, execute: Callable[[bytes], dict], journal: Path,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC), log: Callable[[str], None] = print):
        self.ambiente, self.pubsub, self.execute, self.journal = ambiente, pubsub, execute, journal
        self.clock, self.log = clock, log
        self.counts: Counter = Counter()
        self.day = clock().date()

    # ---- the loop ----------------------------------------------------------------------------------------------
    def step(self) -> int:
        """One pull: the results still to publish first, then each order received."""
        self._publish_pending()
        received = self.pubsub.pull(PULL_MAX)
        for item in received:
            self._one(item)
        if self.clock().date() != self.day:
            self.count_line()
        return len(received)

    def recover(self) -> None:
        """At the start: an entry left «in corso» is failed, interrupted, never run again (§6.2)."""
        for path in sorted(self.journal.glob("*.json")) if self.journal.is_dir() else []:
            entry = self._read(path)
            if entry and entry.get("stato") == "in_corso":
                self._close(entry, self._result(entry, "fallito", "interrotto"))
        self._purge()

    def count_line(self) -> None:
        c = self.counts
        self.log(f"agent count ambiente={self.ambiente} giorno={self.day.isoformat()} ricevuti={c['ricevuti']} "
                 f"riusciti={c['riuscito']} rifiutati={c['rifiutato']} scartati={c['scartato']} falliti={c['fallito']}")
        self.counts, self.day = Counter(), self.clock().date()

    # ---- one order ---------------------------------------------------------------------------------------------
    def _one(self, item: dict) -> None:
        self.counts["ricevuti"] += 1
        ack_id, message = item.get("ackId"), item.get("message") or {}
        try:
            data = base64.b64decode(message.get("data", ""), validate=True)
        except (ValueError, TypeError):
            data = b""
        published = self._publish_time(message.get("publishTime"))
        if published is None or self.clock() - published > timedelta(seconds=comune.MAX_AGE_S):
            self._answer_unjournalled(ack_id, comune.result_for_raw(data, "scartato", "scaduto"))
            return
        try:
            order = comune.check_order(data, self.ambiente)
        except comune.Refused as refused:
            if refused.code == "ambiente_diverso":
                self.log(f"agent alarm codice=ambiente_diverso ambiente={self.ambiente} "
                         f"op_id={comune.result_for_raw(data, 'rifiutato', 'ambiente_diverso')['op_id']}")
            self._answer_unjournalled(ack_id, comune.result_for_raw(data, "rifiutato", refused.code))
            return
        entry = self._read(self.journal / f"{order.op_id}.json")
        if entry is not None:
            self.pubsub.ack(ack_id)
            if entry.get("stato") == "chiuso":
                self._publish(entry)                     # the recorded result, again
            return                                       # in progress: a copy, ignored
        entry = {"op_id": order.op_id, "operazione": order.operazione, "apartment_id": order.apartment_id,
                 "ambiente": order.ambiente, "seq": order.seq, "stato": "in_corso",
                 "ricevuto": self.clock().isoformat()}
        try:
            self._write(order.op_id, entry)
        except OSError:
            self.pubsub.nack(ack_id)                     # not in the journal: Pub/Sub tries again
            self.log(f"agent fault journal op_id={order.op_id}")
            return
        try:
            self.pubsub.ack(ack_id)
        except OSError:                                  # in the journal: a copy delivered again is recognised
            self.log(f"agent fault ack op_id={order.op_id}")
        try:
            answer = self.execute(data)
        except (OSError, ValueError):
            answer = None
        self._close(entry, self._filtered(entry, answer))

    def _answer_unjournalled(self, ack_id, result: dict) -> None:
        self._line(result)
        self.pubsub.ack(ack_id)
        try:
            self.pubsub.publish(result)
        except OSError:
            self.log(f"agent fault publish op_id={result.get('op_id')}")

    # ---- results -----------------------------------------------------------------------------------------------
    @staticmethod
    def _result(entry: dict, esito: str, codice: str) -> dict:
        return {"op_id": entry["op_id"], "operazione": entry["operazione"], "apartment_id": entry["apartment_id"],
                "ambiente": entry["ambiente"], "seq": entry["seq"], "esito": esito, "codice": codice}

    def _filtered(self, entry: dict, answer) -> dict:
        """The executor's answer, kept only if it is ours: the same order, an outcome and a code of the lists, short
        data. Anything else is an internal error."""
        if not isinstance(answer, dict) or answer.get("op_id") != entry["op_id"] \
                or answer.get("esito") not in comune.OUTCOMES or answer.get("codice") not in comune.CODES:
            return self._result(entry, "fallito", "errore_interno")
        out = self._result(entry, answer["esito"], answer["codice"])
        dati = answer.get("dati")
        if isinstance(dati, dict):
            clean = {k: v for k, v in dati.items() if isinstance(k, str) and len(k) <= 40 and (
                isinstance(v, (int, float)) or v is None or (isinstance(v, str) and len(v) <= comune.DATA_MAX_LEN))}
            if clean:
                out["dati"] = clean
        return out

    def _close(self, entry: dict, result: dict) -> None:
        self._line(result)
        entry = {**entry, "stato": "chiuso", "risultato": result, "pubblicato": False, "chiuso": self.clock().isoformat()}
        self._write(entry["op_id"], entry)
        self._publish(entry)

    def _publish(self, entry: dict) -> None:
        try:
            self.pubsub.publish(entry["risultato"])
        except OSError:
            self.log(f"agent fault publish op_id={entry['op_id']}")
            return
        if not entry.get("pubblicato"):
            self._write(entry["op_id"], {**entry, "pubblicato": True})

    def _publish_pending(self) -> None:
        for path in sorted(self.journal.glob("*.json")) if self.journal.is_dir() else []:
            entry = self._read(path)
            if entry and entry.get("stato") == "chiuso" and entry.get("pubblicato") is False:
                self._publish(entry)

    def _line(self, result: dict) -> None:
        self.counts[result["esito"]] += 1
        self.log(f"agent order op_id={result.get('op_id')} operazione={result.get('operazione')} "
                 f"apartment={result.get('apartment_id')} ambiente={self.ambiente} esito={result['esito']} "
                 f"codice={result['codice']}")

    # ---- the journal -------------------------------------------------------------------------------------------
    def _write(self, op_id: str, entry: dict) -> None:
        """Atomic and synced: the entry is on disk before the order is acknowledged."""
        self.journal.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.journal / f".{op_id}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.journal / f"{op_id}.json")

    @staticmethod
    def _read(path: Path) -> dict | None:
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return entry if isinstance(entry, dict) else None

    def _purge(self) -> None:
        limit = time.time() - JOURNAL_DAYS * 86400
        for path in self.journal.glob("*.json") if self.journal.is_dir() else []:
            if path.stat().st_mtime < limit:
                path.unlink(missing_ok=True)

    @staticmethod
    def _publish_time(value) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


# ---- Pub/Sub over REST, with the VM's token ------------------------------------------------------------------------
class PubSub:
    def __init__(self, subscription: str, topic: str):
        self.subscription, self.topic = subscription, topic
        self._token, self._expires = "", 0.0

    def _bearer(self) -> str:
        if time.time() > self._expires - 60:
            request = urllib.request.Request(TOKEN_URL, headers={"Metadata-Flavor": "Google"})
            with urllib.request.urlopen(request, timeout=5) as answer:
                body = json.loads(answer.read(16 * 1024).decode("utf-8"))
            self._token, self._expires = body["access_token"], time.time() + int(body.get("expires_in", 300))
        return self._token

    def _call(self, path: str, body: dict, timeout: float = 30) -> dict:
        request = urllib.request.Request(PUBSUB + path, data=json.dumps(body).encode("utf-8"), method="POST",
                                         headers={"Authorization": f"Bearer {self._bearer()}",
                                                  "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return json.loads(answer.read(4 * 1024 * 1024).decode("utf-8") or "{}")

    def pull(self, max_messages: int) -> list:
        return self._call(f"{self.subscription}:pull", {"maxMessages": max_messages}, timeout=60).get(
            "receivedMessages", [])

    def ack(self, ack_id: str) -> None:
        self._call(f"{self.subscription}:acknowledge", {"ackIds": [ack_id]})

    def nack(self, ack_id: str) -> None:
        self._call(f"{self.subscription}:modifyAckDeadline", {"ackIds": [ack_id], "ackDeadlineSeconds": 0})

    def publish(self, result: dict) -> None:
        data = base64.b64encode(json.dumps(result, ensure_ascii=False).encode("utf-8")).decode("ascii")
        self._call(f"{self.topic}:publish", {"messages": [{"data": data}]})


def execute_on_socket(data: bytes) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(EXECUTOR_TIMEOUT_S)
        s.connect(str(SOCKET_PATH))
        s.sendall(json.dumps({"ordine": data.decode("utf-8")}).encode("utf-8") + b"\n")
        line = s.makefile("rb").readline(64 * 1024)
    return json.loads(line.decode("utf-8"))


def main() -> int:
    import syslog
    config = read_config(CONFIG_PATH)
    syslog.openlog("domhouse-agent-lettore")
    reader = Lettore(config["AMBIENTE"], PubSub(config["SOTTOSCRIZIONE"], config["RISULTATI"]), execute_on_socket,
                     JOURNAL_PATH, log=lambda line: syslog.syslog(syslog.LOG_INFO, line))
    reader.recover()
    while True:
        try:
            if reader.step() == 0:
                time.sleep(1)
        except (OSError, ValueError) as exc:
            syslog.syslog(syslog.LOG_WARNING, f"agent fault pull {type(exc).__name__}")
            time.sleep(10)


if __name__ == "__main__":
    sys.exit(main())

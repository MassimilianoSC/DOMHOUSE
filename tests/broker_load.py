"""How the broker behaves with thousands of devices and messages: a measurement, not a test (not in the full run).

    python tests/broker_load.py [devices]         # default 5000; about 10 minutes; prints one line per phase, also kept as JSON in the system temp folder (or BROKER_LOAD_OUT)

The real broker, installed by scripts/broker-vm.sh on the bench of tests/broker_container_test.py and held to 0.5 CPU:
the sustained share of an e2-small (two vCPU at 25 %), which can burst above it for short periods. The memory limit is
the broker's own (512 MB in engine/broker/compose.yaml). The clients are a generator in a container on the internal
network: this file again, in "gen" mode, a minimal MQTT 3.1.1 client on asyncio, standard library only.
Memory is the broker process's VmRSS. CPU comes from its /proc/1/stat, in average CPUs over the phase."""
import asyncio
import json
import os
import ssl
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOST = "172.30.83.2"
USER_PW = "load-password-molto-lunga-000000"


# ── the generator, inside its container ──
def _length(n: int) -> bytes:
    out = bytearray()
    while True:
        n, digit = n >> 7, n & 0x7f
        out.append(digit | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _text(value: str) -> bytes:
    raw = value.encode()
    return struct.pack(">H", len(raw)) + raw


class Client:
    def __init__(self):
        self.reader = self.writer = self.task = None
        self.acked = 0
        self.on_publish = None
        self.next_id = 0

    async def open(self, port, tls, user, password, client_id, clean=True, timeout=60):
        context = None
        if tls:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(HOST, port, ssl=context), timeout)
        body = _text("MQTT") + bytes([4, 0xC0 | (2 if clean else 0)]) + struct.pack(">H", 590) + _text(client_id) + _text(user) + _text(password)
        self.writer.write(b"\x10" + _length(len(body)) + body)
        await self.writer.drain()
        head = await asyncio.wait_for(self.reader.readexactly(4), timeout)
        if head[0] != 0x20 or head[3] != 0:
            raise ConnectionError(f"connack {head.hex()}")
        self.task = asyncio.create_task(self._read())

    async def _read(self):
        try:
            while True:
                first = (await self.reader.readexactly(1))[0]
                size, shift = 0, 0
                while True:
                    byte = (await self.reader.readexactly(1))[0]
                    size |= (byte & 0x7f) << shift
                    shift += 7
                    if not byte & 0x80:
                        break
                body = await self.reader.readexactly(size) if size else b""
                kind = first >> 4
                if kind == 4:
                    self.acked += 1
                elif kind == 3:
                    topic_len = struct.unpack(">H", body[:2])[0]
                    start = 2 + topic_len
                    qos = (first >> 1) & 3
                    if qos:
                        self.writer.write(b"\x40\x02" + body[start:start + 2])
                        start += 2
                    if self.on_publish:
                        self.on_publish(body[start:])
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass

    def publish(self, topic: str, payload: bytes):
        self.next_id = self.next_id % 65535 + 1
        body = _text(topic) + struct.pack(">H", self.next_id) + payload
        self.writer.write(b"\x32" + _length(len(body)) + body)

    async def subscribe(self, topic: str):
        body = struct.pack(">H", 1) + _text(topic) + b"\x01"
        self.writer.write(b"\x82" + _length(len(body)) + body)
        await self.writer.drain()

    async def close(self, say_goodbye=True):
        if self.writer is None:
            return
        try:
            if say_goodbye:
                self.writer.write(b"\xe0\x00")
                await self.writer.drain()
            self.writer.close()
        except (ConnectionError, OSError, RuntimeError):
            pass
        if self.task:
            self.task.cancel()


class Generator:
    def __init__(self):
        self.devices: list[Client] = []
        self.connector: Client | None = None
        self.received, self.latencies = 0, []

    def got(self, payload: bytes):
        self.received += 1
        try:
            self.latencies.append(time.time() - float(payload[:18]))
        except ValueError:
            pass

    async def _open_device(self, index: int, semaphore) -> bool:
        client = Client()
        client.topic = f"load/d{index:05d}/events/rpc"     # the account's own topics: anything else is dropped by the ACL
        async with semaphore:
            try:
                await client.open(8883, True, f"load.d{index:05d}", USER_PW, f"d{index:05d}")
            except Exception:
                return False
        self.devices.append(client)
        return True

    async def connect(self, target: int, parallel: int = 100) -> dict:
        begin, have = time.time(), len(self.devices)
        semaphore = asyncio.Semaphore(parallel)
        results = await asyncio.gather(*(self._open_device(i, semaphore) for i in range(have, target)))
        return {"devices": len(self.devices), "new": len(results), "failed": results.count(False), "seconds": round(time.time() - begin, 1)}

    async def open_connector(self) -> dict:
        self.connector = Client()
        self.connector.on_publish = self.got
        await self.connector.open(1883, False, "load.connector", USER_PW, "connector", clean=False)
        await self.connector.subscribe("load/#")
        await asyncio.sleep(0.5)
        return {"connector": True}

    def _reset(self):
        self.received, self.latencies = 0, []
        for device in self.devices:
            device.acked = 0

    def _acked(self) -> int:
        return sum(d.acked for d in self.devices)

    async def _settle(self, sent, seconds=25):
        end = time.time() + seconds
        last, last_change = -1, time.time()
        while time.time() < end:
            state = (self._acked(), self.received)
            if state[0] >= sent and state[1] >= sent:
                return
            if state != last:
                last, last_change = state, time.time()
            elif time.time() - last_change > 6:
                return
            await asyncio.sleep(0.1)

    def _result(self, sent, seconds) -> dict:
        ordered = sorted(self.latencies)
        at = lambda q: round(ordered[min(len(ordered) - 1, int(len(ordered) * q))] * 1000, 1) if ordered else None
        return {"sent": sent, "acked": self._acked(), "received": self.received, "seconds": round(seconds, 1),
                "per_second": round(sent / seconds) if seconds else None, "p50_ms": at(0.5), "p95_ms": at(0.95), "p99_ms": at(0.99), "max_ms": at(0.999999)}

    def _payload(self, size: int) -> bytes:
        return f"{time.time():18.6f}".encode() + b"x" * max(0, size - 18)

    async def publish(self, rate: int, seconds: float, size: int) -> dict:
        self._reset()
        sent, begin, index = 0, time.time(), 0
        while (elapsed := time.time() - begin) < seconds:
            for _ in range(int(elapsed * rate) - sent):
                device = self.devices[index % len(self.devices)]
                device.publish(device.topic, self._payload(size))
                index += 1
                sent += 1
            await asyncio.gather(*(d.writer.drain() for d in self.devices[:1]))
            await asyncio.sleep(0.01)
        took = time.time() - begin
        await self._settle(sent)
        return self._result(sent, took)

    async def burst(self, count: int, size: int) -> dict:
        self._reset()
        begin = time.time()
        chunk = max(1, len(self.devices))
        for start in range(0, count, chunk):
            for offset in range(min(chunk, count - start)):
                self.devices[offset].publish(self.devices[offset].topic, self._payload(size))
            await asyncio.gather(*(d.writer.drain() for d in self.devices))
        took = time.time() - begin
        await self._settle(count, 90)
        return self._result(count, took)

    async def away_flood(self, count: int, size: int) -> dict:
        """The connector goes away, its session stays: everything published meanwhile queues for it."""
        await self.connector.close()
        await asyncio.sleep(1)
        self._reset()
        before = self.received
        chunk = max(1, min(len(self.devices), 500))
        for start in range(0, count, chunk):
            for offset in range(min(chunk, count - start)):
                self.devices[offset].publish(self.devices[offset].topic, self._payload(size))
            await asyncio.gather(*(d.writer.drain() for d in self.devices[:chunk]))
        end = time.time() + 40
        while self._acked() < count and time.time() < end:
            await asyncio.sleep(0.2)
        return {"sent": count, "acked": self._acked(), "before": before}

    async def connector_back(self) -> dict:
        self.received, self.latencies = 0, []
        self.connector = Client()
        self.connector.on_publish = self.got
        begin = time.time()
        await self.connector.open(1883, False, "load.connector", USER_PW, "connector", clean=False)
        last, last_change = -1, time.time()
        while time.time() - last_change < 5:
            if self.received != last:
                last, last_change = self.received, time.time()
            await asyncio.sleep(0.1)
        return {"delivered_after_return": self.received, "seconds": round(last_change - begin, 1)}

    async def alive(self) -> dict:
        """How many devices still have a working connection: a PINGREQ each, an answer or the reader's end."""
        return {"open": sum(1 for d in self.devices if not d.task.done())}

    async def reconnect_storm(self, parallel: int) -> dict:
        count = len(self.devices)
        await asyncio.gather(*(d.close(say_goodbye=False) for d in self.devices))
        self.devices = []
        return await self.connect(count, parallel)

    async def close_all(self) -> dict:
        await asyncio.gather(*(d.close() for d in self.devices))
        if self.connector:
            await self.connector.close()
        self.devices = []
        return {"closed": True}


async def generator():
    gen, loop = Generator(), asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    while line := await reader.readline():
        request = json.loads(line)
        try:
            answer = await getattr(gen, request["do"])(*request.get("args", []))
        except Exception as exc:
            answer = {"error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(answer), flush=True)
        if request["do"] == "close_all":
            return


# ── the driver, on the PC ──
def broker_numbers():
    import broker_container_test as bench
    text = bench.docker("exec", bench.CONTAINER, "sh", "-c", "grep VmRSS /proc/1/status; cat /proc/1/stat").stdout.split()
    return {"rss_kb": int(text[1]), "cpu_s": (int(text[3 + 13]) + int(text[3 + 14])) / 100}


def main(devices: int):
    import broker_container_test as bench
    rows = []
    bench.docker("rm", "-f", bench.RIG, check=False)
    bench.docker("rm", "-f", bench.CONTAINER, check=False)
    bench.start_bench()
    try:
        bench.put_secret("langbrain-shelly-load", USER_PW)
        bench.put_secret("langbrain-shelly-load-devices", json.dumps({f"d{i:05d}": USER_PW for i in range(devices)}))
        begin = time.time()
        bench.vm("add-apartment", "load")
        print(f"conti di {devices} dispositivi generati e caricati in {time.time() - begin:.1f} s", flush=True)
        bench.docker("update", "--cpus", "0.5", bench.CONTAINER)
        gen = subprocess.Popen(["docker", "run", "--rm", "-i", "--ulimit", "nofile=65536:65536", "--network", bench.INTERNAL_NET,
                                "-v", f"{Path(__file__).resolve().parent.as_posix()}:/t:ro", "python:3.11-slim", "python", "-u", "/t/broker_load.py", "gen"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")

        def phase(name, do, *args):
            before = broker_numbers()
            started = time.time()
            gen.stdin.write(json.dumps({"do": do, "args": list(args)}) + "\n")
            gen.stdin.flush()
            answer = json.loads(gen.stdout.readline())
            took = time.time() - started
            after = broker_numbers()
            row = {"phase": name, "rss_mb": round(after["rss_kb"] / 1024, 1),
                   "cpu": round((after["cpu_s"] - before["cpu_s"]) / took, 2) if took > 0.5 else None, **answer}
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            return row

        rows.append({"phase": "vuoto", **broker_numbers()})
        print(rows[-1], flush=True)
        phase("connector collegato", "open_connector")
        for target in (100, 500, 1000, 2000, devices):
            if target <= devices:
                phase(f"{target} dispositivi collegati", "connect", target)
        phase("200 msg/s, 1 KB, 30 s", "publish", 200, 30, 1024)
        phase("1000 msg/s, 1 KB, 20 s", "publish", 1000, 20, 1024)
        phase("3000 msg/s, 1 KB, 15 s", "publish", 3000, 15, 1024)
        phase("raffica 20000 da 1 KB", "burst", 20000, 1024)
        phase("connector via, 50000 da 1 KB", "away_flood", 50000, 1024)
        phase("connector torna", "connector_back")
        started = time.time()
        bench.vm("reload")
        rows.append({"phase": "ricarica SIGHUP", "seconds": round(time.time() - started, 1)})
        print(rows[-1], flush=True)
        phase("dispositivi ancora collegati dopo SIGHUP", "alive")
        started = time.time()
        bench.docker("restart", bench.CONTAINER, timeout=120)
        rows.append({"phase": "riavvio del broker", "seconds": round(time.time() - started, 1)})
        print(rows[-1], flush=True)
        phase("ritorno di tutti i dispositivi (100 alla volta)", "reconnect_storm", 100)
        phase("tutti chiudono", "close_all")
        gen.stdin.close()
        gen.wait(20)
        rows.append({"phase": "disco della persistenza", "detail": bench.rig(f"du -sh {bench.BENCH}/data/_broker | cut -f1").stdout.strip()})
        print(rows[-1], flush=True)
    finally:
        out = Path(os.environ.get("BROKER_LOAD_OUT", Path(tempfile.gettempdir()) / "broker_load.json"))
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        bench.docker("rm", "-f", "bench-load-gen", check=False)
        bench.stop_bench()


if __name__ == "__main__":
    if sys.argv[1:] == ["gen"]:
        asyncio.run(generator())
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        main(int(sys.argv[1]) if len(sys.argv) > 1 else 5000)

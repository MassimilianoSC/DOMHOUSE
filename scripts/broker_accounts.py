#!/usr/bin/env python3
"""Accounts of the MQTT broker (D-196, D-199). Standard library only: it runs on the VM next to broker-vm.sh and on the
PC under broker-secrets.sh.

    broker_accounts.py sync <apartments file> <auth dir>     on the VM: from Secret Manager to hashes and permissions
    broker_accounts.py add-device <device> < secret          stdin the devices' JSON, stdout the new JSON
    broker_accounts.py remove-device <device> < secret       the same, without the device
    broker_accounts.py rotate-device <device> < secret       the same, with a new password for that device
    broker_accounts.py new-password                          a random password on stdout
    broker_accounts.py probe <host> <port>                   the TLS port answers MQTT? its certificate (PEM) on stdout

Secrets: `langbrain-shelly-<apartment_id>` holds the connector's password; `langbrain-shelly-<apartment_id>-devices`
holds {"<device_id>": "<password>", ...}. Users: `<apartment_id>.connector` and `<apartment_id>.<device_id>`: an
apartment id has no dots, so two apartments cannot produce the same user.

Topics: a device reads and writes `<apartment_id>/<device_id>/#` and may write `<apartment_id>/connector/rpc`, where
the answers to the connector go (the device publishes them on `<src>/rpc`, with src = `<apartment_id>/connector`). The
connector reads and writes `<apartment_id>/#`.

sync reads every secret first and changes nothing if one is missing or malformed: a temporary read error must not
take accounts away. A password is hashed once: a line whose hash still matches is kept, so a sync that changes
nothing leaves the files alone and does not reload the broker. Passwords are never printed, logged or written.
Hash: PBKDF2-SHA512, the broker's own `$7$` format and iteration count. Every password is random, 192 bits, so the
cost of guessing comes from the password, not from the iterations, and a wave of reconnections stays cheap.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import ssl
import sys
import tempfile
import urllib.request
from pathlib import Path

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
ITERATIONS = 1000
MIN_PASSWORD = 24
RESERVED_DEVICE = "connector"       # its topic is where the devices' answers go
BROKER_UID = 1883
FILES = ("devices.passwd", "devices.acl", "connectors.passwd", "connectors.acl")
SECRET_PREFIX = "langbrain-shelly-"
METADATA = os.environ.get("DOMHOUSE_METADATA", "http://metadata.google.internal/computeMetadata/v1")   # moved only by the tests
SECRETS_API = os.environ.get("DOMHOUSE_SECRETS_API", "https://secretmanager.googleapis.com/v1")        # moved only by the tests


class AccountError(Exception):
    """A problem to show as it is: it never contains a password."""


def valid_id(value: str, what: str) -> str:
    if not ID_RE.match(value or ""):
        raise AccountError(f"{what} non valido: {value!r} (lettere, cifre, _ e -, al massimo 64)")
    return value


def valid_device(device: str) -> str:
    valid_id(device, "device_id")
    if device == RESERVED_DEVICE:
        raise AccountError(f"«{RESERVED_DEVICE}» è riservato all'account del connector")
    return device


def connector_user(apartment: str) -> str:
    return f"{apartment}.{RESERVED_DEVICE}"


def device_user(apartment: str, device: str) -> str:
    return f"{apartment}.{device}"


def new_password() -> str:
    return secrets.token_urlsafe(24)


def _pbkdf2(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, iterations, 64)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(12)
    return f"$7${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(_pbkdf2(password, salt, ITERATIONS)).decode()}"


def hash_matches(stored: str, password: str) -> bool:
    match = re.fullmatch(r"\$7\$(\d+)\$([^$]+)\$([^$]+)", stored or "")
    if not match:
        return False
    try:
        salt, expected = base64.b64decode(match[2], validate=True), base64.b64decode(match[3], validate=True)
    except ValueError:
        return False
    return hmac.compare_digest(_pbkdf2(password, salt, int(match[1])), expected)


def check_password(password: str, who: str) -> str:
    if len(password) < MIN_PASSWORD or re.search(r"\s|:", password):
        raise AccountError(f"password di {who} non valida (almeno {MIN_PASSWORD} caratteri, niente spazi né «:»)")
    return password


def parse_devices(text: str, secret: str) -> dict[str, str]:
    """The devices' secret as a dict, checked. The error names the secret and the device, never a value."""
    try:
        devices = json.loads(text)
    except ValueError:
        raise AccountError(f"il segreto {secret} non è un JSON valido") from None
    if not isinstance(devices, dict):
        raise AccountError(f"il segreto {secret} deve essere un oggetto {{dispositivo: password}}")
    for device, password in devices.items():
        valid_device(device)
        if not isinstance(password, str):
            raise AccountError(f"la password di {device} nel segreto {secret} non è un testo")
        check_password(password, device)
    return devices


def _passwd_text(wanted: dict[str, str], previous: dict[str, str]) -> str:
    lines = []
    for user in sorted(wanted):
        old = previous.get(user)
        lines.append(f"{user}:{old if old and hash_matches(old, wanted[user]) else hash_password(wanted[user])}\n")
    return "".join(lines)


def read_passwd(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return dict(line.split(":", 1) for line in path.read_text(encoding="utf-8").splitlines() if ":" in line)


def render(apartments: dict[str, tuple[str, dict[str, str]]], auth_dir: Path) -> dict[str, str]:
    """The four files' text from {apartment: (connector's password, {device: password})}."""
    connectors, devices, connector_acl, device_acl = {}, {}, [], []
    for apartment in sorted(apartments):
        password, its_devices = apartments[apartment]
        connectors[connector_user(apartment)] = password
        connector_acl.append(f"user {connector_user(apartment)}\ntopic readwrite {apartment}/#\n\n")
        for device in sorted(its_devices):
            devices[device_user(apartment, device)] = its_devices[device]
            device_acl.append(f"user {device_user(apartment, device)}\ntopic readwrite {apartment}/{device}/#\n"
                              f"topic write {apartment}/{RESERVED_DEVICE}/rpc\n\n")
    return {"devices.passwd": _passwd_text(devices, read_passwd(auth_dir / "devices.passwd")),
            "devices.acl": "".join(device_acl),
            "connectors.passwd": _passwd_text(connectors, read_passwd(auth_dir / "connectors.passwd")),
            "connectors.acl": "".join(connector_acl)}


def write_files(texts: dict[str, str], auth_dir: Path) -> bool:
    """Replace, atomically, only the files that differ. True if something changed."""
    changed = False
    for name, text in texts.items():
        target = auth_dir / name
        if target.exists() and target.read_text(encoding="utf-8") == text:
            continue
        handle, temporary = tempfile.mkstemp(dir=auth_dir, prefix=f".{name}.")
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
                out.write(text)
            os.chmod(temporary, 0o640)
            if hasattr(os, "chown") and os.geteuid() == 0:
                os.chown(temporary, BROKER_UID, BROKER_UID)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        changed = True
    return changed


def _get(url: str, headers: dict[str, str]) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
        return response.read()


def access_secret(secret: str, token: str, project: str) -> str:
    url = f"{SECRETS_API}/projects/{project}/secrets/{secret}/versions/latest:access"
    try:
        body = json.loads(_get(url, {"Authorization": f"Bearer {token}"}))
        return base64.b64decode(body["payload"]["data"]).decode("utf-8").strip()
    except Exception as exc:     # the reason's class only: an HTTP error may echo the request, never the value
        raise AccountError(f"segreto {secret} non leggibile dalla VM ({type(exc).__name__}): "
                           "esiste? langbrain-vm@ ha Secret Accessor su di lui?") from None


def read_apartments(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [valid_id(line.strip(), "apartment_id") for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sync(apartments_file: Path, auth_dir: Path) -> int:
    ids = read_apartments(apartments_file)
    loaded: dict[str, tuple[str, dict[str, str]]] = {}
    if ids:
        meta = {"Metadata-Flavor": "Google"}
        try:
            token = json.loads(_get(f"{METADATA}/instance/service-accounts/default/token", meta))["access_token"]
            project = _get(f"{METADATA}/project/project-id", meta).decode().strip()
        except Exception as exc:
            raise AccountError(f"token della VM non disponibile ({type(exc).__name__})") from None
        for apartment in ids:
            connector = f"{SECRET_PREFIX}{apartment}"
            devices = f"{connector}-devices"
            password = check_password(access_secret(connector, token, project), f"connector di {apartment}")
            loaded[apartment] = (password, parse_devices(access_secret(devices, token, project), devices))
    changed = write_files(render(loaded, auth_dir), auth_dir)
    for apartment in ids:
        print(f"{apartment}: connector e {len(loaded[apartment][1])} dispositivi")
    print("changed" if changed else "unchanged")
    return 0


def edit_devices(action: str, device: str, text: str) -> str:
    devices = parse_devices(text or "{}", "dei dispositivi")
    valid_device(device)
    if action == "add":
        if device in devices:
            raise AccountError(f"{device} esiste già: per cambiare la password usa rotate-device")
        devices[device] = new_password()
    elif device not in devices:
        raise AccountError(f"{device} non è fra i dispositivi di questo appartamento")
    elif action == "remove":
        del devices[device]
    else:
        devices[device] = new_password()
    return json.dumps(devices, sort_keys=True)


def probe(host: str, port: int, timeout: float = 8) -> str:
    """TLS, then an MQTT CONNECT without credentials: a broker that works answers with a CONNACK refusing it.
    Returns the certificate it serves, as PEM. Any other outcome raises."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False           # the watch reads the certificate; it is the devices that verify it
    context.verify_mode = ssl.CERT_NONE
    variable = b"\x00\x04MQTT\x04\x02\x00\x1e"
    client_id = b"domhouse-check"
    payload = variable + len(client_id).to_bytes(2, "big") + client_id
    with socket.create_connection((host, port), timeout=timeout) as raw, context.wrap_socket(raw) as tls:
        der = tls.getpeercert(binary_form=True)
        tls.sendall(bytes([0x10, len(payload)]) + payload)
        answer = tls.recv(4)
    if len(answer) < 4 or answer[0] != 0x20:
        raise AccountError(f"risposta MQTT inattesa ({len(answer)} byte)")
    return ssl.DER_cert_to_PEM_cert(der)


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):      # on Windows the default is the console's code page, «già» would break
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        command = argv[0] if argv else ""
        if command == "sync" and len(argv) == 3:
            return sync(Path(argv[1]), Path(argv[2]))
        if command in ("add-device", "remove-device", "rotate-device") and len(argv) == 2:
            sys.stdout.write(edit_devices(command.split("-")[0], argv[1], sys.stdin.read()))
            return 0
        if command == "new-password" and len(argv) == 1:
            sys.stdout.write(new_password())     # no line end: on Windows it would be \r\n, and $(...) keeps the \r
            return 0
        if command == "probe" and len(argv) == 3:
            sys.stdout.write(probe(argv[1], int(argv[2])))
            return 0
        raise AccountError("uso: sync | add-device | remove-device | rotate-device | new-password | probe (vedi l'intestazione)")
    except (AccountError, OSError, ssl.SSLError) as exc:
        print(f"errore: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

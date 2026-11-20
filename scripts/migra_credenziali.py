"""A3 §6.4 (answer 1174): lab-01's migration, the PC's half. The fingerprints the broker uses today, printed on the VM
by «sudo bash /opt/domhouse/broker-vm.sh devices-from-auth lab-01» (one «<device> <fingerprint>» per line: no
password ever), become the devices of the app, «pronti», marked «migrato».

    python scripts/migra_credenziali.py --progetto domotica-poc-511707 --database staging --appartamento lab-01 \\
        --file impronte-lab-01.txt                 # says what it would write
    ... --applica                                  # writes (only the devices the app does not have yet)
    python scripts/migra_credenziali.py --progetto domotica-poc-511707 --database staging --appartamento lab-01 \\
        --annulla [--applica]                      # the way back: removes only the documents it made

It writes to Firestore with the identity of who runs it (Application Default Credentials): the committente, in the
procedure. Only the standard library and the server's own repository.

Expired or missing credentials stop it at once with the command to log in again: on 20 November the Q6.2 dry run with an
expired ADC hung, because google-api-core kept retrying «503 Reauthentication is needed» until Ctrl+C. So one check
of the credentials (one try, 30 s) before any database call, and a deadline on the database calls.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bff.repository.base import AgentOp  # noqa: E402,F401 - re-exported for the tests

DEVICE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
HASH_RE = re.compile(r"^\$7\$[0-9]{3,6}\$[A-Za-z0-9+/]{16}\$[A-Za-z0-9+/]{86}==$")
APARTMENT_RE = re.compile(r"^(lab|test)-[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
AUTH_HINT = "lancia «gcloud auth application-default login» con l'account del progetto, poi riprova"
DEADLINE_SECONDS = 60


def check_credentials() -> str | None:
    """None when the PC's Application Default Credentials give a token now; otherwise the message for the committente.
    One try with a 30 s timeout, no retry. Only the error's class is printed (never a token)."""
    import google.auth
    from google.auth import exceptions
    from google.auth.transport.requests import Request
    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
        session = Request()
        credentials.refresh(lambda *a, **k: session(*a, **{**k, "timeout": 30}))
    except (exceptions.DefaultCredentialsError, exceptions.RefreshError) as exc:
        return f"errore: credenziali del PC scadute o assenti ({type(exc).__name__}): {AUTH_HINT}"
    except exceptions.TransportError as exc:
        return f"errore: Google non risponde ({type(exc).__name__}): controlla la rete e riprova"
    return None


def run(coro):
    """The database calls, with a deadline: google-api-core's retry must not hang the procedure."""
    return asyncio.run(asyncio.wait_for(coro, DEADLINE_SECONDS))


def read_fingerprints(text: str) -> dict[str, str]:
    """Every line «<device> <fingerprint>», checked; any bad line refuses the whole file. Never a password."""
    found: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2 or not DEVICE_RE.fullmatch(parts[0]) or parts[0] == "connector" \
                or not HASH_RE.fullmatch(parts[1]) or parts[0] in found:
            raise ValueError(f"riga {number} non valida")
        found[parts[0]] = parts[1]
    if not found:
        raise ValueError("nessuna impronta nel file")
    return found


async def migrate(repo, apartment_id: str, found: dict[str, str], apply: bool) -> list[str]:
    """The devices it writes (only those the app does not have yet), sorted; with apply=False it writes nothing."""
    docs, _, _ = await repo.device_credentials_view(apartment_id)
    todo = sorted(set(found) - {d["device_id"] for d in docs})
    if apply and todo:
        at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        await repo.put_migrated_credentials(apartment_id, {d: found[d] for d in todo}, at)
    return todo


async def undo(repo, apartment_id: str, apply: bool) -> list[str]:
    """The way back: only the documents marked «migrato»; the ones the app made stay."""
    docs, _, _ = await repo.device_credentials_view(apartment_id)
    gone = sorted(d["device_id"] for d in docs if d.get("migrato"))
    if apply and gone:
        await repo.delete_migrated_credentials(apartment_id, gone)
    return gone


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Migrazione delle impronte di un appartamento (A3 §6.4)")
    parser.add_argument("--progetto", required=True)
    parser.add_argument("--database", required=True, choices=("staging", "(default)"))
    parser.add_argument("--appartamento", required=True)
    parser.add_argument("--file")
    parser.add_argument("--annulla", action="store_true")
    parser.add_argument("--applica", action="store_true")
    a = parser.parse_args(argv)
    if not APARTMENT_RE.fullmatch(a.appartamento):
        print("errore: appartamento non valido (lab-… o test-…)", file=sys.stderr)
        return 2
    found: dict[str, str] = {}
    if not a.annulla:
        if not a.file:
            print("errore: serve --file con le impronte stampate dalla VM", file=sys.stderr)
            return 2
        try:
            found = read_fingerprints(Path(a.file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"errore: {exc}", file=sys.stderr)
            return 2
    problem = check_credentials()
    if problem:
        print(problem, file=sys.stderr)
        return 3
    from bff.repository.firestore import FirestoreRepository
    repo = FirestoreRepository(project_id=a.progetto, database=a.database)
    mode = "scritti" if a.applica else "da scrivere (prova: aggiungi --applica)"
    try:
        if a.annulla:
            gone = run(undo(repo, a.appartamento, a.applica))
            print(f"{len(gone)} documenti «migrato» {'tolti' if a.applica else 'da togliere (prova: aggiungi --applica)'}"
                  ": " + (" ".join(gone) or "nessuno"))
            return 0
        todo = run(migrate(repo, a.appartamento, found, a.applica))
    except TimeoutError:
        print(f"errore: nessuna risposta da Firestore entro {DEADLINE_SECONDS} secondi (credenziali scadute o rete): "
              f"{AUTH_HINT}; con --applica, prima rifai la prova a secco per vedere cosa è già scritto", file=sys.stderr)
        return 3
    print(f"{len(found)} impronte nel file; {len(todo)} dispositivi {mode}: " + (" ".join(todo) or "nessuno"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

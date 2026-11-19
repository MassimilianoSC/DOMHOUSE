"""A3 §6.4 (answer 1174): lab-01's migration, the PC's half. scripts/migra_credenziali.py copies the fingerprints the
broker uses today (printed by «broker-vm.sh devices-from-auth lab-01» on the VM) into the server's database as devices
«pronti», marked «migrato»: never a password. Without --applica it only says what it would do; --annulla removes
only the documents it made. Here on the memory repository; on Firestore the committente runs it (procedure)."""
import asyncio
import importlib.util
from pathlib import Path

import pytest

from bff import device_credentials as dc
from bff.repository.memory import InMemoryRepository

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("migra_credenziali", ROOT / "scripts" / "migra_credenziali.py")
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)

H1 = "$7$1000$" + "A" * 16 + "$" + "B" * 86 + "=="
H2 = "$7$1000$" + "C" * 16 + "$" + "D" * 86 + "=="


def test_the_file_is_read_strictly():
    assert mc.read_fingerprints(f"plug {H1}\n\nshelly-1 {H2}\n") == {"plug": H1, "shelly-1": H2}
    for bad in (f"Plug {H1}", "plug una-password", f"connector {H1}", f"plug {H1} x", f"plug {H1}\nplug {H2}", ""):
        with pytest.raises(ValueError):
            mc.read_fingerprints(bad)


def test_dry_run_apply_and_undo():
    repo = InMemoryRepository()
    found = {"plug": H1, "shelly-1": H2}
    plan = asyncio.run(mc.migrate(repo, "lab-01", found, apply=False))
    assert plan == ["plug", "shelly-1"] and repo.device_creds == {}
    assert asyncio.run(mc.migrate(repo, "lab-01", found, apply=True)) == ["plug", "shelly-1"]
    docs, ultima, ops = asyncio.run(repo.device_credentials_view("lab-01"))
    assert [d["device_id"] for d in docs] == ["plug", "shelly-1"] and all(d["migrato"] for d in docs)
    assert [dc.state_of(d, None, ultima) for d in docs] == ["pronto", "pronto"] and docs[0]["impronta"] == H1
    assert asyncio.run(mc.migrate(repo, "lab-01", found, apply=True)) == []           # twice: nothing more
    asyncio.run(repo.device_credential_change(                                       # one made by the app
        "lab-01", "nuovo", dc.decide("registra", "nuovo", None, H2, "uid1"),
        mc.AgentOp(op_id="00000000-0000-4000-8000-000000000501", operazione="aggiorna_broker", apartment_id="lab-01",
                   ambiente="staging", richiesto_da="Uk9TgS2vLmQ1"),
        lambda op, docs: (b"{}", "sha")))
    assert asyncio.run(mc.undo(repo, "lab-01", apply=True)) == ["plug", "shelly-1"]
    docs, _, _ = asyncio.run(repo.device_credentials_view("lab-01"))
    assert [d["device_id"] for d in docs] == ["nuovo"]                                # the app's own stays

"""P-67 (D-136): what the demonstration apartments hold today, READ ONLY, before the export and the deletion from
production (the committente's condition: names, rules, users, and whether the client changed anything).

    REPOSITORY=firestore GCP_PROJECT_ID=<project> python scripts/list_demos.py
    REPOSITORY=firestore GCP_PROJECT_ID=<project> FIRESTORE_DATABASE=staging python scripts/list_demos.py   # staging

For every organisation with demonstration apartments (mock://, simulated): the apartments with their settings, the
people who see them (email and role: the list is for the committente, it is not stored anywhere), and the administrative
actions recorded on those apartments (who changed what and when: the sign that the client modified something). Nothing
is written. The rules and the device states of a demonstration live in the BFF's memory (they start again from the
initial values at every publication): they are seen in the app (Regole), not here.
Every line is printed at once (also through a pipe), and Firestore has FIRESTORE_TIMEOUT_S (30 s) to answer: otherwise
the script stops with exit code 2 and says what to check (21 Oct: from a PC with user credentials and no quota project
it waited without a word until killed).
"""
import asyncio
import functools
import os
import sys

print = functools.partial(print, flush=True)          # every line at once, also through a pipe
QUOTA_HINT = ("Firestore non risponde entro {s:g} secondi: controlla le credenziali (gcloud auth application-default "
              "login, con l'account proprietario del progetto) e il quota project (gcloud auth application-default "
              "set-quota-project domotica-poc-511707).")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def is_demo(apt) -> bool:
    return bool(apt.simulated) or apt.instance_url.strip().lower().startswith("mock://")


async def collect(repo) -> list[str]:
    lines: list[str] = []
    for tenant in await repo.list_tenants():
        demos = [a for a in await repo.list_apartments(tenant.tenant_id) if is_demo(a)]
        if not demos:
            continue
        real = [a for a in await repo.list_apartments(tenant.tenant_id) if not is_demo(a)]
        ids = {a.apartment_id for a in demos}
        lines.append(f"Organizzazione «{tenant.name}» ({tenant.tenant_id}), stato {tenant.status}: "
                     f"{len(demos)} dimostrativi, {len(real)} appartamenti veri")
        for a in demos:
            lines.append(f"  dimostrativo «{a.name}» ({a.apartment_id}): indirizzo «{a.address}», fuso {a.timezone}, "
                         f"attivo {a.enabled}, funzioni {a.enabled_features or 'quelle dell organizzazione'}, "
                         f"prezzo {a.energy_price_eur_kwh if a.energy_price_eur_kwh is not None else 'quello dell organizzazione'} "
                         f"€/kWh, creato il {a.created_at[:10]}")
        for u in await repo.list_users(tenant.tenant_id):
            sees = "tutti" if u.apartment_ids is None else ", ".join(x for x in u.apartment_ids if x in ids) or "nessuno"
            lines.append(f"  utente {u.email} ({u.role}): dimostrativi visti: {sees}")
        entries = [e for e in await repo.list_audit(tenant.tenant_id, 1000)
                   if e.target.type == "apartment" and e.target.id in ids]
        lines.append(f"  azioni amministrative registrate sui dimostrativi: {len(entries)}"
                     + ("" if entries else " (nessuna modifica registrata)"))
        for e in entries:
            who = e.actor.kind + (f" {e.actor.role}" if e.actor.role else "")
            lines.append(f"    {e.at[:16].replace('T', ' ')} {e.action} su «{e.target.label or e.target.id}», da {who}"
                         + (f", {sorted(e.details)}" if e.details else ""))
    if not lines:
        lines.append("Nessun appartamento dimostrativo in questo database.")
    lines.append("Regole e stati dei dimostrativi: nella memoria del server, ripartono dai valori iniziali a ogni "
                 "pubblicazione; si vedono nell'app (Regole), non qui.")
    return lines


def main() -> None:
    from bff.config import get_settings
    from bff.repository import get_repository

    s = get_settings()
    if s.repository != "firestore":
        raise SystemExit("Lancialo con REPOSITORY=firestore GCP_PROJECT_ID=<progetto> (sola lettura).")
    print(f"Database Firestore {s.firestore_database} del progetto {s.gcp_project_id}, sola lettura")
    timeout = float(os.environ.get("FIRESTORE_TIMEOUT_S", "30"))

    async def read():
        return await asyncio.wait_for(collect(get_repository()), timeout=timeout)
    try:
        lines = asyncio.run(read())
    except TimeoutError:
        print(QUOTA_HINT.format(s=timeout))
        sys.exit(2)
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()

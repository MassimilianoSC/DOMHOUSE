"""P-84: what the load test needs in STAGING, and its removal. It WRITES on Google Cloud: the project owner runs it, from
the PC, in Git Bash, with the credentials already used for scripts/set_claims.py (gcloud auth application-default).

    GCP_PROJECT_ID=<project> .venv/Scripts/python scripts/load/ambiente.py prepara --prova   # says what it would do
    GCP_PROJECT_ID=<project> .venv/Scripts/python scripts/load/ambiente.py prepara
    GCP_PROJECT_ID=<project> .venv/Scripts/python scripts/load/ambiente.py pulisci --prova
    GCP_PROJECT_ID=<project> .venv/Scripts/python scripts/load/ambiente.py pulisci
    GCP_PROJECT_ID=<project> .venv/Scripts/python scripts/load/ambiente.py verifica          # read only: what is left

prepara, in this order (it can be run again: what exists is kept or brought back to the same state):
  1. the engines' keys: one secret langbrain-api-key-carico-NN per test apartment, value random and never shown, only
     in europe-west8, label domhouse=carico, readable by the staging server's account (domotica-bff-staging@, D04: the
     account must exist and the staging service must already run as it) and the VM's (langbrain-vm@); production's
     account (domotica-bff@) is never given them;
  2. the organisation «Carico (prova)» (t-carico-prova) in the staging database only (FIRESTORE_DATABASE=staging, forced
     here: production's database is never opened);
  3. the apartments carico-01 ... carico-NN, each linked to its engine on the VM, http://<VM>:8150, 8151, ...
     (scripts/load/carico-vm.sh starts them on the same ports);
  4. the test people carico-01@carico.domhouse.invalid ... (a domain that can never receive mail), operators of the
     organisation in staging only (claims {"staging": {...}}: production refuses them), each on one apartment in turn,
     email verified, a random password; no push token, so no notification can reach anyone;
  5. logs/carico-utenti.json (logs/ is not in git): the server's address, the site's public Firebase key (read from
     frontend/.env.production, never printed), and the people with their passwords, for carico.py in Cloud Shell. It
     goes away with pulisci.
pulisci undoes it, the apartments FIRST (the server stops following their engines within a minute: HUB_ALIGN_S), then
what the server wrote for the test people (their records, pseudonyms, the organisation's activity log, the apartments'
stream positions), the people in Firebase, the organisation, the secrets and the file. It touches only the names above:
the organisation t-carico-prova, apartments carico-* of that organisation, Firebase accounts @carico.domhouse.invalid,
secrets langbrain-api-key-carico-* with the label domhouse=carico. verifica lists what is still there (exit 1 if any).
"""
import argparse
import asyncio
import json
import os
import secrets
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

TENANT_ID = "t-carico-prova"
TENANT_NAME = "Carico (prova)"
DOMAIN = "carico.domhouse.invalid"         # .invalid can never be a real mailbox (RFC 2606)
PREFIX = "carico-"
SECRET_PREFIX = "langbrain-api-key-"        # the name the server derives from the apartment (instances.secret_name)
LABEL = ("domhouse", "carico")
LOCATION = "europe-west8"
PORT_BASE = 8150                            # carico-01 on 8150, carico-02 on 8151 ... (the VM opens 8100-8199 to the subnet)
DEFAULT_VM_IP = "10.198.0.2"
DEFAULT_BFF = "https://domotica-bff-staging-444239063209.europe-west8.run.app"
STAGING_SERVICE = "domotica-bff-staging"
REFERER = "https://domhouse-staging.web.app/"   # one of the site key's allowed addresses (procedura-ambienti-separati M5)
USERS_FILE = ROOT / "logs" / "carico-utenti.json"
ENV_FILE = ROOT / "frontend" / ".env.production"


def say(*a) -> None:
    print(*a, flush=True)


def apartment_ids(n: int) -> list[str]:
    return [f"{PREFIX}{i:02d}" for i in range(1, n + 1)]


def person_email(i: int) -> str:
    return f"{PREFIX}{i:02d}@{DOMAIN}"


def is_test_email(email: str | None) -> bool:
    return bool(email) and email.lower().endswith("@" + DOMAIN)


def site_api_key(path: Path = ENV_FILE) -> str:
    """The site's public Firebase key, from the file the site is built with; never printed."""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("VITE_FIREBASE_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"')
                if value:
                    return value
    except OSError:
        pass
    raise SystemExit(f"manca VITE_FIREBASE_API_KEY in {path}: serve allo strumento per entrare come il sito")


class Secrets:
    """Secret Manager with the credentials of whoever runs the script (the project owner)."""

    def __init__(self, project: str):
        from google.cloud import secretmanager
        self.client = secretmanager.SecretManagerServiceClient()
        self.project = project

    def path(self, name: str) -> str:
        return f"projects/{self.project}/secrets/{name}"

    def exists(self, name: str) -> bool:
        from google.api_core.exceptions import NotFound
        try:
            self.client.get_secret(name=self.path(name))
            return True
        except NotFound:
            return False

    def labelled(self) -> list[str]:
        """The names of the secrets with the load test's label."""
        found = self.client.list_secrets(request={"parent": f"projects/{self.project}",
                                                   "filter": f"labels.{LABEL[0]}={LABEL[1]}"})
        return sorted(s.name.rsplit("/", 1)[1] for s in found)

    def create(self, name: str) -> None:
        self.client.create_secret(request={
            "parent": f"projects/{self.project}", "secret_id": name,
            "secret": {"replication": {"user_managed": {"replicas": [{"location": LOCATION}]}},
                       "labels": {LABEL[0]: LABEL[1]}}})

    def has_version(self, name: str) -> bool:
        found = self.client.list_secret_versions(request={"parent": self.path(name), "filter": "state:ENABLED"})
        return any(True for _ in found)

    def add_version(self, name: str, value: str) -> None:
        self.client.add_secret_version(request={"parent": self.path(name), "payload": {"data": value.encode()}})

    def grant(self, name: str, members: list[str]) -> None:
        policy = self.client.get_iam_policy(request={"resource": self.path(name)})
        role = "roles/secretmanager.secretAccessor"
        binding = next((b for b in policy.bindings if b.role == role), None)
        if binding is None:
            binding = policy.bindings.add()
            binding.role = role
        missing = [m for m in members if m not in binding.members]
        if missing:
            binding.members.extend(missing)
            self.client.set_iam_policy(request={"resource": self.path(name), "policy": policy})

    def delete(self, name: str) -> None:
        self.client.delete_secret(request={"name": self.path(name)})


class Env:
    """Everything the script touches; the tests give fakes."""

    def __init__(self, repo, auth, secrets_store, project: str, vm_ip: str, bff_url: str, users_file: Path,
                 api_key=site_api_key):
        self.repo, self.auth, self.secrets = repo, auth, secrets_store
        self.project, self.vm_ip, self.bff_url, self.users_file = project, vm_ip, bff_url, users_file
        self.api_key = api_key

    @property
    def readers(self) -> list[str]:
        return [f"serviceAccount:domotica-bff-staging@{self.project}.iam.gserviceaccount.com",
                f"serviceAccount:langbrain-vm@{self.project}.iam.gserviceaccount.com"]


async def prepare(env: Env, apartments: int, people: int, dry: bool) -> None:
    from bff.repository import Apartment, Tenant, User
    ids = apartment_ids(apartments)
    key = env.api_key()                                     # before writing anything: without it the test cannot start
    tag = "(prova a secco) " if dry else ""

    say(f"\n== 1. Chiavi dei motori: {len(ids)} segreti in {LOCATION}, leggibili dal server e dalla VM")
    for apt in ids:
        name = SECRET_PREFIX + apt
        if dry:
            say(f"{tag}{name}: {'esiste già' if env.secrets.exists(name) else 'lo creerei'}, con una chiave casuale se "
                "non ne ha una, leggibile da domotica-bff-staging@ e langbrain-vm@")
            continue
        if not env.secrets.exists(name):
            env.secrets.create(name)
            say(f"{name} creato (solo {LOCATION}, etichetta {LABEL[0]}={LABEL[1]})")
        if env.secrets.has_version(name):
            say(f"{name} ha già una chiave: la lascio (il motore sulla VM la legge da lì)")
        else:
            env.secrets.add_version(name, secrets.token_urlsafe(32))
            say(f"{name}: chiave casuale scritta (mai mostrata)")
        env.secrets.grant(name, env.readers)
        say(f"{name} leggibile da domotica-bff-staging@ e langbrain-vm@")

    say(f"\n== 2. Organizzazione «{TENANT_NAME}» ({TENANT_ID}) nel database dello staging")
    existing = await env.repo.get_tenant(TENANT_ID)
    say(f"{tag}{'esiste già' if existing else ('la creerei' if dry else 'la creo')}")
    if not dry and existing is None:
        await env.repo.upsert_tenant(Tenant(tenant_id=TENANT_ID, name=TENANT_NAME, created_by="scripts/load/ambiente.py"))

    say(f"\n== 3. Appartamenti di prova, collegati ai motori sulla VM ({env.vm_ip})")
    for i, apt in enumerate(ids):
        url = f"http://{env.vm_ip}:{PORT_BASE + i}"
        other = await env.repo.get_apartment(apt)
        if other is not None and other.tenant_id != TENANT_ID:
            raise SystemExit(f"{apt} esiste già in un'altra organizzazione ({other.tenant_id}): non lo tocco, mi fermo")
        say(f"{tag}{apt} -> {url}")
        if not dry:
            await env.repo.upsert_apartment(Apartment(apartment_id=apt, tenant_id=TENANT_ID, name=f"Carico {apt[-2:]}",
                                                      instance_url=url, enabled=True))

    say(f"\n== 4. {people} persone di prova (operatori, solo nello staging), una per appartamento a turno")
    listed = []
    for i in range(1, people + 1):
        email, apt = person_email(i), ids[(i - 1) % len(ids)]
        password = secrets.token_urlsafe(18)
        try:
            user = env.auth.get_user_by_email(email)
        except env.auth.UserNotFoundError:
            user = None
        if dry:
            say(f"{tag}{email} su {apt}: {'esiste, gli darei una password nuova' if user else 'la creerei'}")
            continue
        claims = {"staging": {"tenant_id": TENANT_ID, "role": "operator"}}
        if user is None:
            user = env.auth.create_user(email=email, password=password, email_verified=True,
                                        display_name=f"Carico {i:02d}")
        else:
            env.auth.update_user(user.uid, password=password, email_verified=True)
        env.auth.set_custom_user_claims(user.uid, claims)
        await env.repo.upsert_user(User(uid=user.uid, email=email, display_name=f"Carico {i:02d}", tenant_id=TENANT_ID,
                                        role="operator", apartment_ids=[apt]))
        listed.append({"email": email, "password": password, "apartment_id": apt})
    if not dry:
        say(f"{len(listed)} persone pronte (da {person_email(1)} a {person_email(people)})")

    say(f"\n== 5. File per lo strumento di carico: {env.users_file}")
    if dry:
        say(f"{tag}lo scriverei, con le password delle persone di prova (resta fuori da git)")
        return
    env.users_file.parent.mkdir(parents=True, exist_ok=True)
    data = {"bff_url": env.bff_url, "firebase_api_key": key, "referer": REFERER, "project_id": env.project,
            "service": STAGING_SERVICE, "database": "staging", "tenant_id": TENANT_ID, "utenti": listed}
    env.users_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(env.users_file, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    say(f"scritto ({len(listed)} persone); lo toglie «pulisci»")


async def forget_cursor(repo, apartment_id: str) -> None:
    if hasattr(repo, "stream_cursors"):                      # the memory repository of the tests
        repo.stream_cursors.pop(apartment_id, None)
    else:
        await repo._col("stream_cursors").document(apartment_id).delete()


async def forget_activity_log(repo) -> int:
    """The organisation's activity log (written by the server only for admin actions: normally empty here)."""
    if hasattr(repo, "audit"):
        return len(repo.audit.pop(TENANT_ID, {}) or {})
    n = 0
    async for doc in repo._col("tenants").document(TENANT_ID).collection("audit").stream():
        await doc.reference.delete()
        n += 1
    return n


def test_accounts(auth) -> list:
    """Firebase accounts of the test domain only."""
    return [u for u in auth.list_users().iterate_all() if is_test_email(u.email)]


async def clean(env: Env, dry: bool) -> None:
    tag = "(prova a secco) " if dry else ""
    say("\n== 1. Appartamenti di prova (per primi: il server smette di seguirne i motori entro un minuto)")
    apartments = [a for a in await env.repo.list_apartments(TENANT_ID) if a.apartment_id.startswith(PREFIX)]
    for a in apartments:
        say(f"{tag}tolgo {a.apartment_id} ({a.instance_url})")
        if not dry:
            await env.repo.delete_apartment(a.apartment_id)
            await env.repo.delete_bookings(a.apartment_id)
            await forget_cursor(env.repo, a.apartment_id)
    if not apartments:
        say("nessuno")

    say("\n== 2. Persone di prova: record dell'app, pseudonimi, registro dell'organizzazione")
    users = [u for u in await env.repo.list_users(TENANT_ID)]
    for u in users:
        say(f"{tag}tolgo il record di {u.email}")
        if not dry:
            await env.repo.forget_actor(u.uid)
            await env.repo.delete_user(u.uid)
    if not users:
        say("nessuno")
    if not dry:
        n = await forget_activity_log(env.repo)
        say(f"registro dell'organizzazione: {n} voci tolte")

    say(f"\n== 3. Account Firebase @{DOMAIN}")
    accounts = test_accounts(env.auth)
    for u in accounts:
        say(f"{tag}tolgo {u.email}")
        if not dry:
            env.auth.delete_user(u.uid)
    if not accounts:
        say("nessuno")

    say(f"\n== 4. Organizzazione {TENANT_ID}")
    tenant = await env.repo.get_tenant(TENANT_ID)
    say(tag + ("la tolgo" if tenant else "non c'è"))
    if tenant and not dry:
        if hasattr(env.repo, "tenants"):
            env.repo.tenants.pop(TENANT_ID, None)
        else:
            await env.repo._col("tenants").document(TENANT_ID).delete()

    say(f"\n== 5. Segreti con l'etichetta {LABEL[0]}={LABEL[1]}")
    names = [n for n in env.secrets.labelled() if n.startswith(SECRET_PREFIX + PREFIX)]
    for name in names:
        say(f"{tag}tolgo {name}")
        if not dry:
            env.secrets.delete(name)
    if not names:
        say("nessuno")

    say(f"\n== 6. File {env.users_file}")
    if env.users_file.exists():
        say(f"{tag}lo tolgo")
        if not dry:
            env.users_file.unlink()
    else:
        say("non c'è")


async def left(env: Env) -> list[str]:
    """What of the test is still there (read only)."""
    out = []
    if await env.repo.get_tenant(TENANT_ID):
        out.append(f"organizzazione {TENANT_ID}")
    out += [f"appartamento {a.apartment_id}" for a in await env.repo.list_apartments(TENANT_ID)]
    out += [f"record dell'app {u.email}" for u in await env.repo.list_users(TENANT_ID)]
    out += [f"account Firebase {u.email}" for u in test_accounts(env.auth)]
    out += [f"segreto {n}" for n in env.secrets.labelled()]
    if env.users_file.exists():
        out.append(f"file {env.users_file}")
    return out


def real_env(args) -> Env:
    project = os.environ.get("GCP_PROJECT_ID", "").strip()
    if not project:
        raise SystemExit("manca GCP_PROJECT_ID (il progetto)")
    # staging only, whatever the environment of the shell says
    os.environ.update({"REPOSITORY": "firestore", "FIRESTORE_DATABASE": "staging", "FIREBASE_PROJECT_ID": project,
                       "APP_ENV": "staging"})
    import firebase_admin
    from firebase_admin import auth

    from bff.config import get_settings
    get_settings.cache_clear()                               # the settings above, even if something read them before
    from bff.repository import get_repository
    repo = get_repository()
    if getattr(repo, "database", None) != "staging":
        raise SystemExit(f"il database aperto è «{getattr(repo, 'database', '?')}», non «staging»: mi fermo")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": project})
    return Env(repo, auth, Secrets(project), project, args.vm_ip, args.bff, Path(args.file))


async def run(args, env: Env) -> int:
    if args.azione == "prepara":
        await prepare(env, args.appartamenti, args.persone, args.prova)
        if not args.prova:
            say("\nFatto. Poi: i motori sulla VM (carico-vm.sh prepara), lo staging a 1-3 istanze, lo strumento in Cloud Shell.")
    elif args.azione == "pulisci":
        await clean(env, args.prova)
        if not args.prova:
            remaining = await left(env)
            say("\nFatto." if not remaining else "\nRESTA ANCORA: " + "; ".join(remaining))
            return 0 if not remaining else 1
    else:
        remaining = await left(env)
        say("Niente della prova di carico è rimasto." if not remaining else "Resta: \n- " + "\n- ".join(remaining))
        return 0 if not remaining else 1
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):          # « » and accents also in the Windows terminal of Git Bash
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("azione", choices=("prepara", "pulisci", "verifica"))
    p.add_argument("--prova", action="store_true", help="prova a secco: legge e dice cosa farebbe, non scrive niente")
    p.add_argument("--appartamenti", type=int, default=5)
    p.add_argument("--persone", type=int, default=50)
    p.add_argument("--vm-ip", default=DEFAULT_VM_IP)
    p.add_argument("--bff", default=DEFAULT_BFF)
    p.add_argument("--file", default=str(USERS_FILE))
    args = p.parse_args(argv)
    if not 1 <= args.appartamenti <= 20 or not 1 <= args.persone <= 200:
        p.error("da 1 a 20 appartamenti e da 1 a 200 persone")
    env = real_env(args)

    async def go():
        # one event loop for everything: the async Firestore client is bound to the loop of its first call (D-76)
        return await run(args, env)
    return asyncio.run(go())


if __name__ == "__main__":
    sys.exit(main())

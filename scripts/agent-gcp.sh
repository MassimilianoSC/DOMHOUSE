#!/usr/bin/env bash
# Tool A, package A1 (docs/progetto-strumento-a-base.md §1, §4.2, §4.3, §5.4, §6.7): the Google Cloud pieces of the
# order receiver, for STAGING only. It WRITES on Google Cloud: the project owner runs it, from the PC, in Git Bash,
# after step 2 of the plan. Idempotent: what exists is kept, never changed.
#   GCP_PROJECT_ID=<project> scripts/agent-gcp.sh staging
#   DRY_RUN=1 GCP_PROJECT_ID=<project> scripts/agent-gcp.sh staging      # reads only, changes nothing
#
# What it sets up (region-free resources of Pub/Sub, IAM on each resource, never on the project):
#   topics      domhouse-staging-ordini, domhouse-staging-risultati, domhouse-staging-scarti
#   pull        domhouse-staging-ordini-vm: ack 60 s, kept 1 h (an order older than 15 minutes is discarded anyway),
#               dead letters after 5 deliveries, retries between 10 and 60 s, ordered by apartment, never expires
#   pull        domhouse-staging-scarti-lettura: the dead letters, kept 7 days, read only by us
#   push        domhouse-staging-risultati-push: to <staging server>/internal/agent/risultati, signed by the push
#               account domhouse-push-staging@ with that exact address as audience (§4.2)
#   who         the staging server (domotica-bff-staging@) is the ONLY publisher of the orders (§10.3: never widen);
#               the VM (langbrain-vm@) reads only its subscription and publishes only the results; Pub/Sub's own
#               service agent moves the dead letters (publisher on the dead letters, subscriber on the subscription).
#               No «token creator» for it: the project was created on 15 October 2026, after April 2021 (question b
#               of the security review of A1)
#   alarms      «Agente: ordini finiti negli scarti» and «Agente: ordine di un altro ambiente o giornale non
#               scrivibile», files in scripts/agent/allarmi/, on the email channel «Avvisi BFF»
# No Pub/Sub schema on the orders topic: the parameters of an order change with the operation, and Avro's JSON
# encoding would wrap every optional value. The schema is checked twice on the VM (reader and executor, comune.py),
# and the only publisher is the staging server.
# Production: nothing here. Its orders never reach the shared VM (§5.4); they come with the second VM.
set -euo pipefail

say()  { printf '\n== %s\n' "$*"; }
stop() { printf '\nFERMO: %s\n' "$*" >&2; exit 1; }

P="${GCP_PROJECT_ID:-}"; [ -n "${P}" ] || stop "Manca GCP_PROJECT_ID: scrivi GCP_PROJECT_ID=<progetto> prima del comando."
ENVIRONMENT="${1:-}"
case "${ENVIRONMENT}" in
  staging) ;;
  prod) stop "La produzione non manda ordini alla VM condivisa (§5.4): le sue code nascono con la seconda VM." ;;
  *) stop "uso: GCP_PROJECT_ID=<progetto> scripts/agent-gcp.sh staging" ;;
esac
DRY_RUN="${DRY_RUN:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REGION="${GCP_REGION:-europe-west8}"
CHANNEL_NAME="${CHANNEL_NAME:-Avvisi BFF}"
ORDERS="domhouse-${ENVIRONMENT}-ordini"; RESULTS="domhouse-${ENVIRONMENT}-risultati"; DEAD="domhouse-${ENVIRONMENT}-scarti"
SUB="${ORDERS}-vm"; DEAD_SUB="${DEAD}-lettura"; PUSH_SUB="${RESULTS}-push"
VM="serviceAccount:langbrain-vm@${P}.iam.gserviceaccount.com"
SERVER="serviceAccount:domotica-bff-${ENVIRONMENT}@${P}.iam.gserviceaccount.com"
PUSH_NAME="domhouse-push-${ENVIRONMENT}"; PUSH_EMAIL="${PUSH_NAME}@${P}.iam.gserviceaccount.com"

# The PC's Python (I2, 17 November): on Windows «python3» may be the empty alias of the Microsoft Store, which only
# prints «Python non è stato trovato…» and fails. The first of python3 and python that really runs Python 3, checked
# before anything is read (scripts/monitoring/engine-alerts.sh falls back to python the same way)
PYTHON=""
for candidate in python3 python; do
  if "${candidate}" -c 'import sys; sys.exit(sys.version_info < (3, 8))' > /dev/null 2>&1; then PYTHON="${candidate}"; break; fi
done
[ -n "${PYTHON}" ] || stop "Manca Python 3 su questo PC: né python3 né python funzionano (su Windows: python.org, non Microsoft Store)."

echo "Progetto ${P} · ambiente ${ENVIRONMENT}${DRY_RUN:+ · PROVA A SECCO}"
NUMBER="$(gcloud projects describe "${P}" --format='value(projectNumber)')"
[[ "${NUMBER}" =~ ^[0-9]+$ ]] || stop "Non leggo il numero del progetto."
PUBSUB_AGENT="serviceAccount:service-${NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"
# The stable address https://domotica-bff-<env>-<project number>.<region>.run.app, as scripts/deploy.sh prefers: the
# manifest's AGENT_PUSH_AUDIENCE is written with it; status.url (the random-looking one) only if it is not there
URLS="$(gcloud run services describe "domotica-bff-${ENVIRONMENT}" --region="${REGION}" --project="${P}" \
  --format="value(metadata.annotations.'run.googleapis.com/urls')" || true)"
URL="$(printf '%s' "${URLS}" | grep -oE "https://[^\"]+\.${REGION}\.run\.app" | head -1 || true)"
[ -n "${URL}" ] || URL="$(gcloud run services describe "domotica-bff-${ENVIRONMENT}" --region="${REGION}" --project="${P}" --format='value(status.url)')"
[[ "${URL}" =~ ^https://[a-z0-9.-]+$ ]] || stop "Non leggo l'indirizzo del server dello ${ENVIRONMENT}."
ENDPOINT="${URL}/internal/agent/risultati"
echo "server: ${URL}"

# ---- R3 (security review of A1): read-only checks, BEFORE any write (on what exists) and again at the end -----------
# 1. the ONLY publisher of the orders is the staging server (§10.3): on the topic (and no custom role there) and from
#    anywhere in the project (Cloud Asset analysis: the server must be among the results, the analysis fully explored
#    and without errors; persons only from PERSONE_AMMESSE, every other user: stops);
# 2. the VM (langbrain-vm@) cannot impersonate the staging server;
# 3. only the VM publishes the results; only the VM and Pub/Sub's agent read the orders' subscription;
# 4. what already exists is what this script would make: each subscription's topic, ordering, dead letters, retries,
#    retention, push address, account and audience.
# The project has no organisation nor folder above it (gcloud projects get-ancestors, 16 November): the analysis
# with --project sees every binding that counts.
PERSONE_AMMESSE="${PERSONE_AMMESSE:-m.scardovellicrac@gmail.com}"
# Who may impersonate the staging server besides itself and PERSONE_AMMESSE: answer 1151 of 17 November, the committente
# in writing, by exact name (Google's service agents of the project and Firebase's admin account, all from project
# bindings, as the real analysis of I2 showed). A closed list, written here and never read from outside: any other
# identity stops the script; never a pattern
AMMESSI_IMPERSONAZIONE="serviceAccount:service-444239063209@gcp-sa-aiplatform.iam.gserviceaccount.com"
AMMESSI_IMPERSONAZIONE+=",serviceAccount:service-444239063209@gcp-sa-cloudbuild.iam.gserviceaccount.com"
AMMESSI_IMPERSONAZIONE+=",serviceAccount:444239063209@cloudservices.gserviceaccount.com"
AMMESSI_IMPERSONAZIONE+=",serviceAccount:service-444239063209@compute-system.iam.gserviceaccount.com"
AMMESSI_IMPERSONAZIONE+=",serviceAccount:service-444239063209@gcp-sa-pubsub.iam.gserviceaccount.com"
AMMESSI_IMPERSONAZIONE+=",serviceAccount:service-444239063209@serverless-robot-prod.iam.gserviceaccount.com"
AMMESSI_IMPERSONAZIONE+=",serviceAccount:firebase-adminsdk-fbsvc@domotica-poc-511707.iam.gserviceaccount.com"
# Who may publish on the orders topic besides the server, Pub/Sub's agent and PERSONE_AMMESSE: answer 1152 of 17
# November, by exact name (Google's service agents that publish on any topic of the project from project bindings, as
# the read-only analysis of an existing topic showed). NOT admitted: 444239063209@cloudbuild.gserviceaccount.com, the
# old Cloud Build account that runs builds (its builder role is taken away before I3; seen again, the script stops).
# A closed list, written here and never read from outside
AMMESSI_PUBBLICAZIONE="serviceAccount:service-444239063209@gcp-sa-artifactregistry.iam.gserviceaccount.com"
AMMESSI_PUBBLICAZIONE+=",serviceAccount:service-444239063209@gcp-sa-cloudbuild.iam.gserviceaccount.com"
AMMESSI_PUBBLICAZIONE+=",serviceAccount:service-444239063209@container-analysis.iam.gserviceaccount.com"
AMMESSI_PUBBLICAZIONE+=",serviceAccount:service-444239063209@containerregistry.iam.gserviceaccount.com"
AMMESSI_PUBBLICAZIONE+=",serviceAccount:service-444239063209@firebase-rules.iam.gserviceaccount.com"
CHECKER="$(mktemp)"
cat > "${CHECKER}" << 'PY'
import json, sys
from pathlib import Path
(work, phase, server, vm, agent, people, orders, results, dead, sub, dead_sub, push_sub, project, endpoint,
 push_email, impersonators, publishers) = sys.argv[1:]
work = Path(work)
people = {f"user:{p.strip()}" for p in people.split(",") if p.strip()}
impersonators = {m.strip() for m in impersonators.split(",") if m.strip()}         # answer 1151: exact names only
publishers = {m.strip() for m in publishers.split(",") if m.strip()}               # answer 1152: exact names only
problems = []
publish_roles = {"roles/pubsub.publisher", "roles/pubsub.editor", "roles/pubsub.admin", "roles/owner", "roles/editor"}
read_roles = {"roles/pubsub.subscriber", "roles/pubsub.editor", "roles/pubsub.admin", "roles/owner", "roles/editor"}


def load(name):
    f = work / name
    return json.loads(f.read_text() or "{}") if f.exists() else None


def members(policy, roles):
    found = set()
    for b in (policy or {}).get("bindings", []):
        role = b.get("role", "")
        if role.startswith(("projects/", "organizations/")):
            problems.append(f"ruolo personalizzato {role} su una risorsa dell'agente: {', '.join(b.get('members', []))}")
        if role in roles:
            found |= set(b.get("members", []))
    return found


def analysis(name, what):
    """The real output of gcloud asset analyze-iam-policy --format=json (I2, 17 November): a LIST, one element per
    binding, {"ACLs": [{"identities": [{"name": ...}], ...}], "policy": {"binding": {"role", "members"}}}; empty when
    nobody. Whether it is complete gcloud says only on stderr («Your analysis request is fully explored.»), kept by the
    script next to it (<name>.err). Every identity, of the binding and of its ACLs -> its role."""
    f = work / name
    if not f.exists():
        return None
    err = work / name.replace(".json", ".err")
    said = err.read_text(encoding="utf-8", errors="replace").lower() if err.exists() else ""
    if "request is fully explored" not in said or "not fully explored" in said:
        problems.append(f"analisi dei permessi su {what} non completa (gcloud non dice «fully explored»)")
    if "error" in said:
        problems.append(f"analisi dei permessi su {what} con errori: {' '.join(said.split())[:300]}")
    try:
        data = json.loads(f.read_text(encoding="utf-8").strip() or "[]")
    except ValueError:
        data = None
    if not isinstance(data, list):
        problems.append(f"analisi dei permessi su {what}: forma inattesa (non è una lista di binding)")
        return {}
    found = {}
    for entry in data:
        entry = entry if isinstance(entry, dict) else {}
        binding = (entry.get("policy") or {}).get("binding") or {}
        names = list(binding.get("members") or [])
        for acl in entry.get("ACLs") or []:
            names += [i.get("name") for i in (acl.get("identities") or []) if isinstance(i, dict)]
        for m in names:
            if isinstance(m, str):
                found.setdefault(m, binding.get("role"))
    return found


policy = load(f"topic-{orders}.json")
if policy is not None:
    for m in sorted(members(policy, publish_roles) - {server}):
        problems.append(f"sulla coda degli ordini pubblica anche {m}")
policy = load(f"topic-{results}.json")
if policy is not None:
    for m in sorted(members(policy, publish_roles) - {vm}):
        problems.append(f"sulla coda dei risultati pubblica anche {m}")
policy = load(f"subpol-{sub}.json")
if policy is not None:
    for m in sorted(members(policy, read_roles) - {vm, agent}):
        problems.append(f"legge la sottoscrizione degli ordini anche {m}")
found = analysis("asset-topic.json", "coda degli ordini")
if found is not None:
    if server not in found:
        problems.append("l'analisi non vede il server fra chi pubblica sulla coda degli ordini: risultato non affidabile")
    for m, role in sorted(found.items()):
        if m in (server, agent) or m in people:
            continue
        if m in publishers:
            print(f"può pubblicare sulla coda degli ordini, ammesso (risposta 1152): {m} ({role})")
            continue
        problems.append(f"può pubblicare sulla coda degli ordini anche {m} ({role})")
found = analysis("asset-sa.json", "account del server")
if found is not None:
    for m, role in sorted(found.items()):                 # an allow-list: principal://, deleted:, groups… all stop
        if m in impersonators:
            print(f"può impersonare il server, ammesso (risposta 1151): {m} ({role})")
        elif m != server and m not in people:
            problems.append(f"può impersonare il server dello staging anche {m} ({role})")


def get(data, path):
    for key in path.split("."):
        data = data.get(key, {}) if isinstance(data, dict) else {}
    return data


topic = lambda name: f"projects/{project}/topics/{name}"
expected = {
    sub: {"topic": topic(orders), "ackDeadlineSeconds": 60, "messageRetentionDuration": "3600s",
          "enableMessageOrdering": True, "deadLetterPolicy.deadLetterTopic": topic(dead),
          "deadLetterPolicy.maxDeliveryAttempts": 5, "retryPolicy.minimumBackoff": "10s",
          "retryPolicy.maximumBackoff": "60s"},
    dead_sub: {"topic": topic(dead), "messageRetentionDuration": "604800s"},
    push_sub: {"topic": topic(results), "pushConfig.pushEndpoint": endpoint,
               "pushConfig.oidcToken.serviceAccountEmail": push_email, "pushConfig.oidcToken.audience": endpoint},
}
for name, keys in expected.items():
    data = load(f"sub-{name}.json")
    if data is None:
        continue
    for path, want in keys.items():
        have = get(data, path)
        if have != want:
            problems.append(f"{name}: {path} è {have!r}, dovrebbe essere {want!r}")
for m in sorted(people):
    print(f"persona ammessa (PERSONE_AMMESSE): {m[len('user:'):]}")
if problems:
    print("\n".join(problems), file=sys.stderr)
    sys.exit(1)
print(f"controlli superati ({phase})")
PY
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}" "${CHECKER}"' EXIT

checks() {
  # checks <prima|dopo>: collects what exists (read only) and runs the checker; stops the script on a problem
  rm -f "${WORK}"/*
  local t s
  for t in "${ORDERS}" "${RESULTS}" "${DEAD}"; do
    if gcloud pubsub topics describe "${t}" --project="${P}" > /dev/null 2>&1; then
      gcloud pubsub topics get-iam-policy "${t}" --project="${P}" --format=json > "${WORK}/topic-${t}.json"
    fi
  done
  for s in "${SUB}" "${DEAD_SUB}" "${PUSH_SUB}"; do
    gcloud pubsub subscriptions describe "${s}" --project="${P}" --format=json > "${WORK}/sub-${s}.json" 2> /dev/null \
      || rm -f "${WORK}/sub-${s}.json"
  done
  if [ -f "${WORK}/sub-${SUB}.json" ]; then
    gcloud pubsub subscriptions get-iam-policy "${SUB}" --project="${P}" --format=json > "${WORK}/subpol-${SUB}.json"
  fi
  if [ -f "${WORK}/topic-${ORDERS}.json" ]; then
    gcloud asset analyze-iam-policy --project="${P}" \
      --full-resource-name="//pubsub.googleapis.com/projects/${P}/topics/${ORDERS}" \
      --permissions=pubsub.topics.publish --format=json > "${WORK}/asset-topic.json" 2> "${WORK}/asset-topic.err" \
      || stop "Non leggo chi può pubblicare sulla coda degli ordini (analisi dei permessi, API Cloud Asset): abilitala o controlla a mano, poi rilancia."
  fi
  gcloud asset analyze-iam-policy --project="${P}" \
    --full-resource-name="//iam.googleapis.com/projects/${P}/serviceAccounts/${SERVER#serviceAccount:}" \
    --permissions=iam.serviceAccounts.actAs,iam.serviceAccounts.getAccessToken,iam.serviceAccounts.getOpenIdToken,iam.serviceAccounts.signBlob,iam.serviceAccounts.signJwt,iam.serviceAccounts.implicitDelegation \
    --format=json > "${WORK}/asset-sa.json" 2> "${WORK}/asset-sa.err" \
    || stop "Non leggo chi può impersonare il server dello staging (analisi dei permessi, API Cloud Asset): abilitala o controlla a mano, poi rilancia."
  PYTHONIOENCODING=utf-8 "${PYTHON}" "${CHECKER}" "${WORK}" "$1" "${SERVER}" "${VM}" "${PUBSUB_AGENT}" "${PERSONE_AMMESSE}" \
    "${ORDERS}" "${RESULTS}" "${DEAD}" "${SUB}" "${DEAD_SUB}" "${PUSH_SUB}" "${P}" "${ENDPOINT}" "${PUSH_EMAIL}" \
    "${AMMESSI_IMPERSONAZIONE}" "${AMMESSI_PUBBLICAZIONE}" \
    || { if [ "$1" = "prima" ]; then
           stop "Controlli non superati (prima): niente è stato cambiato. Leggi le righe qui sopra."
         else
           stop "Controlli non superati (dopo): le scritture qui sopra sono fatte; leggi le righe qui sopra e decidi con la memoria storica."
         fi; }
}

say "Controlli prima di scrivere (sola lettura)"
checks prima

# make <what> <describe command...> -- <create command...>: creates only if the describe fails
make() {
  local what="$1"; shift
  local describe=() create=()
  while [ "$1" != "--" ]; do describe+=("$1"); shift; done; shift
  create=("$@")
  if "${describe[@]}" > /dev/null 2>&1; then echo "${what}: esiste già"; return 0; fi
  if [ -n "${DRY_RUN}" ]; then echo "(prova a secco) ${what}: lo creerei"; return 0; fi
  "${create[@]}" > /dev/null
  echo "${what}: creato"
}

# grant <kind> <resource> <member> <role>: a binding on that resource only (never on the project)
grant() {
  if [ -n "${DRY_RUN}" ]; then echo "(prova a secco) $4 a $3 su $2"; return 0; fi
  gcloud pubsub "$1" add-iam-policy-binding "$2" --project="${P}" --member="$3" --role="$4" > /dev/null
  echo "$4 a ${3#serviceAccount:} su $2"
}

say "Code"
for t in "${ORDERS}" "${RESULTS}" "${DEAD}"; do
  make "coda ${t}" gcloud pubsub topics describe "${t}" --project="${P}" -- \
    gcloud pubsub topics create "${t}" --project="${P}"
done

say "Account di push dei risultati"
make "account ${PUSH_NAME}" gcloud iam service-accounts describe "${PUSH_EMAIL}" --project="${P}" -- \
  gcloud iam service-accounts create "${PUSH_NAME}" --project="${P}" --display-name="DOMHOUSE push dei risultati (${ENVIRONMENT})"

say "Sottoscrizioni"
make "sottoscrizione ${SUB}" gcloud pubsub subscriptions describe "${SUB}" --project="${P}" -- \
  gcloud pubsub subscriptions create "${SUB}" --project="${P}" --topic="${ORDERS}" --ack-deadline=60 \
    --message-retention-duration=1h --dead-letter-topic="${DEAD}" --max-delivery-attempts=5 \
    --min-retry-delay=10s --max-retry-delay=60s --enable-message-ordering --expiration-period=never
make "sottoscrizione ${DEAD_SUB}" gcloud pubsub subscriptions describe "${DEAD_SUB}" --project="${P}" -- \
  gcloud pubsub subscriptions create "${DEAD_SUB}" --project="${P}" --topic="${DEAD}" \
    --message-retention-duration=7d --expiration-period=never
make "sottoscrizione ${PUSH_SUB}" gcloud pubsub subscriptions describe "${PUSH_SUB}" --project="${P}" -- \
  gcloud pubsub subscriptions create "${PUSH_SUB}" --project="${P}" --topic="${RESULTS}" --ack-deadline=30 \
    --push-endpoint="${ENDPOINT}" --push-auth-service-account="${PUSH_EMAIL}" \
    --push-auth-token-audience="${ENDPOINT}" --expiration-period=never

say "Permessi (su ogni risorsa, mai sul progetto)"
grant topics "${ORDERS}" "${SERVER}" roles/pubsub.publisher
grant subscriptions "${SUB}" "${VM}" roles/pubsub.subscriber
grant topics "${RESULTS}" "${VM}" roles/pubsub.publisher
grant topics "${DEAD}" "${PUBSUB_AGENT}" roles/pubsub.publisher
grant subscriptions "${SUB}" "${PUBSUB_AGENT}" roles/pubsub.subscriber

say "Allarmi"
CHANNEL="$(gcloud beta monitoring channels list --project="${P}" --filter="displayName:\"${CHANNEL_NAME}\"" \
  --format='value(name)' | head -1)"
[ -n "${CHANNEL}" ] || stop "Nessun canale «${CHANNEL_NAME}»: crealo prima con scripts/monitoring/setup.sh."
for file in "${HERE}"/agent/allarmi/*.json; do
  name="$("${PYTHON}" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["displayName"])' "${file}")"
  if [ -n "$(gcloud alpha monitoring policies list --project="${P}" --filter="displayName=\"${name}\"" --format='value(name)' 2>/dev/null)" ]; then
    echo "«${name}»: esiste già"; continue
  fi
  if [ -n "${DRY_RUN}" ]; then echo "(prova a secco) «${name}»: la creerei"; continue; fi
  tmp="$(mktemp)"
  sed "s#__CHANNEL__#${CHANNEL}#" "${file}" > "${tmp}"
  gcloud alpha monitoring policies create --project="${P}" --policy-from-file="${tmp}" > /dev/null
  rm -f "${tmp}"
  echo "«${name}»: creata"
done

say "Controlli alla fine (sola lettura)"
checks dopo
say "Fatto"
echo "Per il server dello ${ENVIRONMENT}: AGENT_AMBIENTE=${ENVIRONMENT}, AGENT_ORDERS_TOPIC=projects/${P}/topics/${ORDERS},"
echo "AGENT_PUSH_AUDIENCE=${ENDPOINT}, AGENT_PUSH_EMAIL=${PUSH_EMAIL},"
echo "AGENT_PUSH_SUBSCRIPTION=projects/${P}/subscriptions/${PUSH_SUB} (nel manifesto, poi una pubblicazione)."
echo "Per la VM: scripts/agent-vm.sh install con"
echo "SOTTOSCRIZIONE=projects/${P}/subscriptions/${SUB} RISULTATI=projects/${P}/topics/${RESULTS}."

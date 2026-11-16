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
#               service agent moves the dead letters (publisher on the dead letters, subscriber on the subscription)
#               and signs the push (token creator on the push account only: needed by projects older than April
#               2021, harmless otherwise; da verificare)
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

echo "Progetto ${P} · ambiente ${ENVIRONMENT}${DRY_RUN:+ · PROVA A SECCO}"
NUMBER="$(gcloud projects describe "${P}" --format='value(projectNumber)')"
[[ "${NUMBER}" =~ ^[0-9]+$ ]] || stop "Non leggo il numero del progetto."
PUBSUB_AGENT="serviceAccount:service-${NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"
URL="$(gcloud run services describe "domotica-bff-${ENVIRONMENT}" --region="${REGION}" --project="${P}" --format='value(status.url)')"
[[ "${URL}" =~ ^https://[a-z0-9.-]+$ ]] || stop "Non leggo l'indirizzo del server dello ${ENVIRONMENT}."
ENDPOINT="${URL}/internal/agent/risultati"
echo "server: ${URL}"

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
if [ -n "${DRY_RUN}" ]; then
  echo "(prova a secco) roles/iam.serviceAccountTokenCreator a ${PUBSUB_AGENT#serviceAccount:} su ${PUSH_EMAIL}"
else
  gcloud iam service-accounts add-iam-policy-binding "${PUSH_EMAIL}" --project="${P}" --member="${PUBSUB_AGENT}" \
    --role=roles/iam.serviceAccountTokenCreator > /dev/null
  echo "roles/iam.serviceAccountTokenCreator a ${PUBSUB_AGENT#serviceAccount:} su ${PUSH_EMAIL}"
fi

say "Allarmi"
CHANNEL="$(gcloud beta monitoring channels list --project="${P}" --filter="displayName:\"${CHANNEL_NAME}\"" \
  --format='value(name)' | head -1)"
[ -n "${CHANNEL}" ] || stop "Nessun canale «${CHANNEL_NAME}»: crealo prima con scripts/monitoring/setup.sh."
for file in "${HERE}"/agent/allarmi/*.json; do
  name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["displayName"])' "${file}")"
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

say "Fatto"
echo "Per il server dello ${ENVIRONMENT}: AGENT_ORDERS_TOPIC=projects/${P}/topics/${ORDERS}, AGENT_PUSH_AUDIENCE=${ENDPOINT},"
echo "AGENT_PUSH_EMAIL=${PUSH_EMAIL} (nel manifesto, poi una pubblicazione). Per la VM: scripts/agent-vm.sh install con"
echo "SOTTOSCRIZIONE=projects/${P}/subscriptions/${SUB} RISULTATI=projects/${P}/topics/${RESULTS}."

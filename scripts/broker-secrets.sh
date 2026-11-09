#!/usr/bin/env bash
# The accounts of the MQTT broker in Secret Manager (D-196, D-199). It WRITES on Google Cloud: the project owner runs it,
# from the PC, in Git Bash. Then, on the VM: sudo bash /opt/domhouse/broker-vm.sh sync (procedure: docs/motore-vm.md).
#
#   GCP_PROJECT_ID=<project> scripts/broker-secrets.sh add-apartment <apartment_id>
#   GCP_PROJECT_ID=<project> scripts/broker-secrets.sh add-device <apartment_id> <device_id>
#   GCP_PROJECT_ID=<project> scripts/broker-secrets.sh remove-device <apartment_id> <device_id>
#   GCP_PROJECT_ID=<project> scripts/broker-secrets.sh rotate-device <apartment_id> <device_id>
#   GCP_PROJECT_ID=<project> scripts/broker-secrets.sh rotate-connector <apartment_id>
#   DRY_RUN=1 GCP_PROJECT_ID=<project> scripts/broker-secrets.sh ...      # says what it would do; reads and writes nothing
#
# Secrets: langbrain-shelly-<apartment_id> (the connector's password) and langbrain-shelly-<apartment_id>-devices
# ({"<device_id>": "<password>"}), kept only in europe-west8, readable by the VM's account and nobody else added here.
# Passwords are random, made here, and go from memory to gcloud through a pipe: never on a command line or on screen.
# The new text is written only if it was built without errors: a failed read can never become an empty new version.
# Removing a device leaves it in the older versions of the secret, which the broker never reads.
set -euo pipefail
set +x

P="${GCP_PROJECT_ID:-}"
[ -n "${P}" ] || { echo "errore: manca GCP_PROJECT_ID" >&2; exit 1; }
DRY_RUN="${DRY_RUN:-}"
LOCATION="${SECRET_LOCATION:-europe-west8}"
VM_ACCOUNT="${VM_ACCOUNT:-langbrain-vm@${P}.iam.gserviceaccount.com}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ACCOUNTS="${HERE}/broker_accounts.py"
if [ -x "${HERE}/../.venv/Scripts/python" ]; then PY="${HERE}/../.venv/Scripts/python"; elif command -v python3 > /dev/null; then PY=python3; else PY=python; fi

die() { echo "errore: $*" >&2; exit 1; }
say() { printf '== %s\n' "$*"; }
valid_id() { [[ "$2" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$ ]] || die "$1 non valido: $2"; }
exists() { gcloud secrets describe "$1" --project="${P}" --format='value(name)' > /dev/null 2>&1; }
has_version() { [ -n "$(gcloud secrets versions list "$1" --project="${P}" --filter='state=ENABLED' --limit=1 --format='value(name)')" ]; }
next_step() { echo "Ora, sulla VM: sudo bash /opt/domhouse/broker-vm.sh ${1:-sync}"; }

add_version() {
  # add_version <secret> <text>: the text reaches gcloud on stdin only; printf is a builtin, so it is no process argument
  [ -n "$2" ] || die "testo vuoto per $1: non scrivo nulla"
  printf '%s' "$2" | gcloud secrets versions add "$1" --project="${P}" --data-file=- > /dev/null
  echo "nuova versione di $1 scritta"
}

create_if_missing() {
  if exists "$1"; then echo "$1 esiste già"; return 0; fi
  gcloud secrets create "$1" --project="${P}" --replication-policy=user-managed --locations="${LOCATION}" > /dev/null
  echo "$1 creato (solo ${LOCATION})"
}

grant_vm() {
  gcloud secrets add-iam-policy-binding "$1" --project="${P}" \
    --member="serviceAccount:${VM_ACCOUNT}" --role=roles/secretmanager.secretAccessor --condition=None > /dev/null
  echo "$1 leggibile da ${VM_ACCOUNT}"
}

edit_devices() {
  # edit_devices <action> <apartment_id> <device_id>
  local secret="langbrain-shelly-$2-devices" current new
  valid_id apartment_id "$2"
  valid_id device_id "$3"
  if [ -n "${DRY_RUN}" ]; then echo "(prova a secco) $1-device $3 in ${secret}: nessuna lettura né scrittura"; return 0; fi
  current="$(gcloud secrets versions access latest --secret="${secret}" --project="${P}")" || die "${secret} non leggibile"
  new="$(printf '%s' "${current}" | "${PY}" "${ACCOUNTS}" "$1-device" "$3")" || die "$1-device non fatto: niente è cambiato"
  add_version "${secret}" "${new}"
  current=""; new=""
  next_step
}

cmd="${1:-}"; [ $# -eq 0 ] || shift
case "${cmd}" in
  add-apartment)
    [ $# -eq 1 ] || die "uso: add-apartment <apartment_id>"
    valid_id apartment_id "$1"
    connector="langbrain-shelly-$1"; devices="${connector}-devices"
    if [ -n "${DRY_RUN}" ]; then echo "(prova a secco) creerei ${connector} e ${devices} in ${LOCATION}, leggibili da ${VM_ACCOUNT}"; exit 0; fi
    say "Segreti di $1"
    create_if_missing "${connector}"
    create_if_missing "${devices}"
    if has_version "${connector}"; then echo "${connector} ha già una versione: la lascio"; else add_version "${connector}" "$("${PY}" "${ACCOUNTS}" new-password)"; fi
    if has_version "${devices}"; then echo "${devices} ha già una versione: la lascio"; else add_version "${devices}" "{}"; fi
    grant_vm "${connector}"
    grant_vm "${devices}"
    next_step "add-apartment $1"
    ;;
  add-device|remove-device|rotate-device)
    [ $# -eq 2 ] || die "uso: ${cmd} <apartment_id> <device_id>"
    edit_devices "${cmd%-device}" "$1" "$2"
    ;;
  rotate-connector)
    [ $# -eq 1 ] || die "uso: rotate-connector <apartment_id>"
    valid_id apartment_id "$1"
    if [ -n "${DRY_RUN}" ]; then echo "(prova a secco) nuova password in langbrain-shelly-$1"; exit 0; fi
    add_version "langbrain-shelly-$1" "$("${PY}" "${ACCOUNTS}" new-password)"
    next_step
    ;;
  *)
    die "uso: add-apartment | add-device | remove-device | rotate-device | rotate-connector (vedi l'intestazione)"
    ;;
esac

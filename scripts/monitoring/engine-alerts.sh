#!/usr/bin/env bash
# The alerts on the engines of the VM (P-60 step 10, D-104, D-148), with one command, idempotent:
#   GCP_PROJECT_ID=<project> scripts/monitoring/engine-alerts.sh
#   DRY_RUN=1 GCP_PROJECT_ID=<project> scripts/monitoring/engine-alerts.sh      # reads only, changes nothing
#
# Optional: CHANNEL_NAME (default "Avvisi BFF": the email channel of the BFF's alerts, D-148; it must exist, created
#           by scripts/monitoring/setup.sh).
# What it sets up (what exists already is kept, never changed): the log-based metric domhouse_check_runs (the summary
# line "domhouse-check: N motori, M muti" of engine-vm.sh check-all, every 5 minutes) and five alert policies, from the
# files in scripts/monitoring/engine-alerts/: «Motori: VM muta» (no summary for 10 minutes: one email for the whole VM),
# «Motori: motore muto o giù» and «Motori: righe di errore» (at most one email every 30 minutes), «Motori: backup
# mancato» (every 12 hours), «Motori: disco della VM oltre l'80 %». They read the lines of engine-vm.sh check-all and
# backup in the VM's syslog and the engines' logs from the Ops Agent (engine-vm.sh logs-agent): before those run on the
# VM the policies wait, nothing breaks. Messages in plain Italian: run by the project owner.
set -euo pipefail

say()  { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
stop() { printf '\n\033[1;31mFERMO: %s\033[0m\n' "$*" >&2; exit 1; }

P="${GCP_PROJECT_ID:-}"; [ -n "${P}" ] || stop "Manca GCP_PROJECT_ID: scrivi GCP_PROJECT_ID=<progetto> prima del comando."
DRY_RUN="${DRY_RUN:-}"
CHANNEL_NAME="${CHANNEL_NAME:-Avvisi BFF}"
HERE="$(cd "$(dirname "$0")" && pwd)"
METRIC="domhouse_check_runs"
METRIC_FILTER='resource.type="gce_instance" AND log_id("syslog") AND jsonPayload.message=~"domhouse-check(\\[[0-9]+\\])?: domhouse-check: [0-9]+ motori"'

echo "Progetto ${P} · canale «${CHANNEL_NAME}»${DRY_RUN:+ · PROVA A SECCO}"

say "Canale degli avvisi"
CHANNEL="$(gcloud beta monitoring channels list --project="${P}" --filter="displayName:\"${CHANNEL_NAME}\"" \
  --format='value(name)' | head -1)"
[ -n "${CHANNEL}" ] || stop "Nessun canale «${CHANNEL_NAME}»: crealo prima con scripts/monitoring/setup.sh."
echo "canale: ${CHANNEL}"

say "Metrica dai log: ${METRIC}"
if gcloud logging metrics describe "${METRIC}" --project="${P}" >/dev/null 2>&1; then
  echo "esiste già"
elif [ -n "${DRY_RUN}" ]; then
  echo "(prova a secco) la creerei con il filtro: ${METRIC_FILTER}"
else
  gcloud logging metrics create "${METRIC}" --project="${P}" \
    --description="DOMHOUSE: le righe di riepilogo del controllo dei motori (engine-vm.sh check-all, ogni 5 minuti)" \
    --log-filter="${METRIC_FILTER}"
  echo "creata"
fi

say "Politiche d'allarme"
created=0
for file in "${HERE}"/engine-alerts/*.json; do
  # UTF-8 on purpose: on Windows Python would print «giù» in the console's code page and the name would not match
  read_name='import json, sys; sys.stdout.reconfigure(encoding="utf-8"); print(json.load(open(sys.argv[1], encoding="utf-8"))["displayName"])'
  name="$(python3 -c "${read_name}" "${file}" 2>/dev/null || python -c "${read_name}" "${file}")"
  existing="$(gcloud alpha monitoring policies list --project="${P}" --filter="displayName=\"${name}\"" --format='value(name)' | head -1)"
  if [ -n "${existing}" ]; then
    echo "«${name}»: esiste già (${existing##*/}), non la tocco"
    continue
  fi
  rendered="$(mktemp)"
  sed "s#__CHANNEL__#${CHANNEL}#g" "${file}" > "${rendered}"
  if [ -n "${DRY_RUN}" ]; then
    echo "«${name}»: (prova a secco) la creerei da $(basename "${file}")"
  else
    gcloud alpha monitoring policies create --project="${P}" --policy-from-file="${rendered}" >/dev/null
    echo "«${name}»: creata"
    created=$((created + 1))
  fi
  rm -f "${rendered}"
done

say "Fatto"
echo "politiche create ora: ${created}. Verifica: gcloud alpha monitoring policies list --project=${P} --format=\"value(displayName,enabled)\""

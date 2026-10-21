#!/usr/bin/env bash
# Sets up (or repairs) the BFF monitoring of P-4 with one command and checks the result:
#   email channel -> uptime check on /health -> alert policy "BFF non raggiungibile" (alert-policy.json)
#   -> log-based alert policy "BFF: scrittura non riuscita" (log-alert-policy.json, P-57): an email when the BFF logs
#      one of the best-effort writes that failed (the messages are in log-alert-messages.txt, one per line).
# Not /healthz: Cloud Run's front end reserves paths ending in "z" and answers 404 from outside without reaching the
# BFF (https://cloud.google.com/run/docs/known-issues#reserved-url-paths, E-12); /healthz serves only internal probes.
#
#   GCP_PROJECT_ID=<project> EMAIL=<recipient> scripts/monitoring/setup.sh
#   DRY_RUN=1 GCP_PROJECT_ID=<project> EMAIL=<recipient> scripts/monitoring/setup.sh   # reads only, changes nothing
#
# Optional: HOST=<BFF host without https://> (default: the deterministic URL of the domotica-bff Cloud Run service),
#           GCP_REGION (default europe-west8),
#           SERVICE (default domotica-bff, production: P-67 keeps the alerts on production only; staging,
#           domotica-bff-staging, has none unless this is run with SERVICE=domotica-bff-staging).
# Idempotent: what exists is kept, what is missing is created, a wrong check path is corrected. At the end it re-reads
# the check path and the policy links and stops with FERMO if they are not what they must be: Git Bash once turned
# --path=/healthz into "/C:/Program Files/Git/healthz" and the alert fired with a healthy server (E-11). Every
# --path= argument therefore goes through MSYS2_ARG_CONV_EXCL (MSYS_NO_PATHCONV=1 would break the gcloud wrapper).
# Messages are in plain Italian: this script is run by the project owner or the project memory session.
set -euo pipefail

say()  { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
stop() { printf '\n\033[1;31mFERMO: %s\033[0m\n' "$*" >&2; exit 1; }
nopath() { MSYS2_ARG_CONV_EXCL='--path=' "$@"; }  # run a command with --path= arguments left untouched by Git Bash

P="${GCP_PROJECT_ID:-}"; [ -n "${P}" ] || stop "Manca GCP_PROJECT_ID: scrivi GCP_PROJECT_ID=<progetto> prima del comando."
EMAIL="${EMAIL:-}"; [ -n "${EMAIL}" ] || stop "Manca EMAIL: scrivi EMAIL=<destinatario degli avvisi> prima del comando."
REGION="${GCP_REGION:-europe-west8}"
DRY_RUN="${DRY_RUN:-}"
SERVICE="${SERVICE:-domotica-bff}"
CHECK_NAME="${SERVICE}-healthz"             # domotica-bff-healthz for production, the existing check
CHECK_PATH="/health"
MATCH='"status":"ok"'
POLICY_NAME="BFF non raggiungibile"
case "${CHECK_PATH}" in
  /_ah/*|*z|*z/) stop "Il percorso ${CHECK_PATH} è riservato da Cloud Run e da fuori risponde sempre 404 (E-12)." ;;
esac
HERE="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="${HERE}/alert-policy.json"
[ -f "${TEMPLATE}" ] || stop "Manca ${TEMPLATE}."
LOG_POLICY_NAME="BFF: scrittura non riuscita"
LOG_TEMPLATE="${HERE}/log-alert-policy.json"
LOG_MESSAGES="${HERE}/log-alert-messages.txt"
[ -f "${LOG_TEMPLATE}" ] || stop "Manca ${LOG_TEMPLATE}."
[ -f "${LOG_MESSAGES}" ] || stop "Manca ${LOG_MESSAGES}."
MESSAGES=()
while IFS= read -r m || [ -n "${m}" ]; do
  m="${m%$'\r'}"; [ -n "${m}" ] && MESSAGES+=("${m}")
done < "${LOG_MESSAGES}"
[ "${#MESSAGES[@]}" -gt 0 ] || stop "${LOG_MESSAGES} è vuoto."
# The filter as it must appear inside the JSON string of the template (quotes escaped once).
OR=""; for m in "${MESSAGES[@]}"; do OR="${OR:+${OR} OR }jsonPayload.msg=\\\"${m}\\\""; done
LOG_FILTER="resource.type=\\\"cloud_run_revision\\\" AND resource.labels.service_name=\\\"${SERVICE}\\\" AND (${OR})"
render_log_policy() {   # the template filled in, in a temporary file whose path is printed
  local out; out="$(mktemp)"
  # in a sed replacement a backslash is consumed: double them so the JSON keeps its \" escapes
  sed -e "s|__CHANNEL__|${CHANNEL}|" -e "s|__FILTER__|${LOG_FILTER//\\/\\\\}|" "${LOG_TEMPLATE}" > "${out}"
  echo "${out}"
}
if [ -n "${RENDER_ONLY:-}" ]; then   # prints the log policy for the channel given, calls nothing (used by the tests)
  CHANNEL="${RENDER_ONLY}"; RENDERED="$(render_log_policy)"; cat "${RENDERED}"; rm -f "${RENDERED}"; exit 0
fi
act() { if [ -n "${DRY_RUN}" ]; then echo "(prova a secco) farei: $1"; return 1; fi; echo "$1"; }

if [ -z "${HOST:-}" ]; then
  URLS="$(gcloud run services describe "${SERVICE}" --project "${P}" --region "${REGION}" --format "value(metadata.annotations.'run.googleapis.com/urls')")"
  HOST="$(printf '%s' "${URLS}" | grep -oE "https://[^\"]+\.${REGION}\.run\.app" | head -1 | sed 's|^https://||' || true)"
  [ -n "${HOST}" ] || stop "Non trovo l'indirizzo del BFF: scrivi HOST=<indirizzo senza https://> prima del comando."
fi
echo "Progetto ${P} · BFF ${HOST} · avvisi a ${EMAIL}${DRY_RUN:+ · PROVA A SECCO}"

# The check must call a page that answers from outside, as the uptime regions will (E-12): tried before every change.
reachable() {
  command -v curl >/dev/null || stop "Manca curl: serve per provare https://${HOST}${CHECK_PATH} da fuori."
  curl -fsS --max-time 10 "https://${HOST}${CHECK_PATH}" 2>/dev/null | grep -qF "${MATCH}" \
    || stop "https://${HOST}${CHECK_PATH} non risponde ${MATCH} da fuori: pubblica prima una versione del BFF che ha ${CHECK_PATH}, poi ripeti."
  echo "https://${HOST}${CHECK_PATH} risponde ${MATCH} da fuori"
}

# --- 1. Email channel ------------------------------------------------------------------------------------------
say "1. Canale email"
CHANNEL="$(gcloud beta monitoring channels list --project="${P}" --filter="labels.email_address=\"${EMAIL}\"" --format='value(name)' | head -1)"
if [ -n "${CHANNEL}" ]; then
  echo "già presente: ${CHANNEL##*/}"
elif act "creo il canale email per ${EMAIL}"; then
  gcloud beta monitoring channels create --project="${P}" --type=email --display-name="Avvisi BFF (${EMAIL})" \
    --channel-labels=email_address="${EMAIL}"
  CHANNEL="$(gcloud beta monitoring channels list --project="${P}" --filter="labels.email_address=\"${EMAIL}\"" --format='value(name)' | head -1)"
  [ -n "${CHANNEL}" ] || stop "Il canale email non risulta creato."
fi

# --- 2. Uptime check -------------------------------------------------------------------------------------------
say "2. Controllo di disponibilità"
CHECK_ID="$(gcloud monitoring uptime list-configs --project="${P}" --filter="displayName=\"${CHECK_NAME}\"" --format='value(name.basename())' 2>/dev/null | head -1)"
if [ -n "${CHECK_ID}" ]; then
  echo "già presente: ${CHECK_ID}"
  PATH_NOW="$(gcloud monitoring uptime list-configs --project="${P}" --filter="displayName=\"${CHECK_NAME}\"" --format='value(httpCheck.path)' | head -1)"
  MATCH_NOW="$(gcloud monitoring uptime list-configs --project="${P}" --filter="displayName=\"${CHECK_NAME}\"" --format='value(contentMatchers[0].content)' | head -1)"
  if [ "${PATH_NOW}" != "${CHECK_PATH}" ] || [ "${MATCH_NOW}" != "${MATCH}" ]; then
    reachable
    if act "correggo percorso «${PATH_NOW}» e contenuto atteso «${MATCH_NOW}» in «${CHECK_PATH}» e «${MATCH}»"; then
      nopath gcloud monitoring uptime update "${CHECK_ID}" --project="${P}" --path="${CHECK_PATH}" \
        --matcher-content="${MATCH}" --matcher-type=contains-string
    fi
  fi
else
  reachable
  if act "creo il controllo ${CHECK_NAME} su https://${HOST}${CHECK_PATH}"; then
  nopath gcloud monitoring uptime create "${CHECK_NAME}" --project="${P}" \
    --resource-type=uptime-url --resource-labels=host="${HOST}",project_id="${P}" \
    --protocol=https --path="${CHECK_PATH}" --period=1 --timeout=10 \
    --regions=europe,usa-oregon,asia-pacific \
    --matcher-content="${MATCH}" --matcher-type=contains-string
  CHECK_ID="$(gcloud monitoring uptime list-configs --project="${P}" --filter="displayName=\"${CHECK_NAME}\"" --format='value(name.basename())' | head -1)"
  [ -n "${CHECK_ID}" ] || stop "Il controllo di disponibilità non risulta creato."
  fi
fi

# --- 3. Alert policy -------------------------------------------------------------------------------------------
say "3. Regola di avviso"
POLICY="$(gcloud alpha monitoring policies list --project="${P}" --filter="displayName=\"${POLICY_NAME}\"" --format='value(name)' | head -1)"
if [ -n "${POLICY}" ]; then
  echo "già presente: ${POLICY##*/}"
elif [ -n "${CHECK_ID}" ] && [ -n "${CHANNEL}" ] && act "creo la regola «${POLICY_NAME}»"; then
  RENDERED="$(mktemp)"
  sed -e "s|__CHECK_ID__|${CHECK_ID}|" -e "s|__CHANNEL__|${CHANNEL}|" "${TEMPLATE}" > "${RENDERED}"
  gcloud alpha monitoring policies create --project="${P}" --policy-from-file="${RENDERED}"
  rm -f "${RENDERED}"
  POLICY="$(gcloud alpha monitoring policies list --project="${P}" --filter="displayName=\"${POLICY_NAME}\"" --format='value(name)' | head -1)"
  [ -n "${POLICY}" ] || stop "La regola di avviso non risulta creata."
elif [ -z "${DRY_RUN}" ]; then
  stop "Non posso creare la regola: manca il canale o il controllo."
fi

# --- 4. Log-based alert policy (P-57) ---------------------------------------------------------------------------
say "4. Regola sulle scritture non riuscite"
log_filter_ok() {   # every message of the list is in the policy's filter
  local f; f="$(gcloud alpha monitoring policies describe "$1" --project="${P}" --format='value(conditions[0].conditionMatchedLog.filter)')"
  for m in "${MESSAGES[@]}"; do case "${f}" in *"\"${m}\""*) ;; *) return 1 ;; esac; done
}
LOG_POLICY="$(gcloud alpha monitoring policies list --project="${P}" --filter="displayName=\"${LOG_POLICY_NAME}\"" --format='value(name)' | head -1)"
if [ -n "${LOG_POLICY}" ]; then
  echo "già presente: ${LOG_POLICY##*/}"
  if ! log_filter_ok "${LOG_POLICY}" && act "aggiorno i messaggi sorvegliati dalla regola «${LOG_POLICY_NAME}»"; then
    RENDERED="$(render_log_policy)"
    gcloud alpha monitoring policies update "${LOG_POLICY}" --project="${P}" --policy-from-file="${RENDERED}"
    rm -f "${RENDERED}"
  fi
elif [ -n "${CHANNEL}" ] && act "creo la regola «${LOG_POLICY_NAME}» (${#MESSAGES[@]} messaggi sorvegliati)"; then
  RENDERED="$(render_log_policy)"
  gcloud alpha monitoring policies create --project="${P}" --policy-from-file="${RENDERED}"
  rm -f "${RENDERED}"
  LOG_POLICY="$(gcloud alpha monitoring policies list --project="${P}" --filter="displayName=\"${LOG_POLICY_NAME}\"" --format='value(name)' | head -1)"
  [ -n "${LOG_POLICY}" ] || stop "La regola «${LOG_POLICY_NAME}» non risulta creata."
elif [ -z "${DRY_RUN}" ]; then
  stop "Non posso creare la regola «${LOG_POLICY_NAME}»: manca il canale email."
fi

# --- 5. Re-read everything: the guard against the Git Bash trap ------------------------------------------------
say "5. Verifica"
if [ -n "${DRY_RUN}" ] && { [ -z "${CHANNEL}" ] || [ -z "${CHECK_ID}" ] || [ -z "${POLICY}" ] || [ -z "${LOG_POLICY}" ]; }; then
  echo "Prova a secco: qualcosa andrebbe creato, quindi la verifica completa si fa dopo la creazione vera."
  exit 0
fi
PATH_NOW="$(gcloud monitoring uptime list-configs --project="${P}" --filter="displayName=\"${CHECK_NAME}\"" --format='value(httpCheck.path)' | head -1)"
[ "${PATH_NOW}" = "${CHECK_PATH}" ] || stop "Il controllo chiama «${PATH_NOW}» invece di «${CHECK_PATH}»: manderebbe falsi allarmi. Avvisa la memoria storica."
echo "percorso del controllo: ${PATH_NOW}"
MATCH_NOW="$(gcloud monitoring uptime list-configs --project="${P}" --filter="displayName=\"${CHECK_NAME}\"" --format='value(contentMatchers[0].content)' | head -1)"
[ "${MATCH_NOW}" = "${MATCH}" ] || stop "Il controllo si aspetta «${MATCH_NOW}» invece di «${MATCH}»."
reachable  # the same page the uptime regions call answers from here too
HOST_NOW="$(gcloud monitoring uptime list-configs --project="${P}" --filter="displayName=\"${CHECK_NAME}\"" --format='value(monitoredResource.labels.host)' | head -1)"
[ "${HOST_NOW}" = "${HOST}" ] || echo "Attenzione: il controllo sorveglia ${HOST_NOW}, non ${HOST} (stesso servizio se sono i due URL di ${SERVICE})."
FILTER="$(gcloud alpha monitoring policies describe "${POLICY}" --project="${P}" --format='value(conditions[0].conditionThreshold.filter)')"
case "${FILTER}" in *"\"${CHECK_ID}\""*) echo "la regola guarda il controllo ${CHECK_ID}" ;;
  *) stop "La regola «${POLICY_NAME}» non guarda il controllo ${CHECK_ID}." ;; esac
CHANNELS="$(gcloud alpha monitoring policies describe "${POLICY}" --project="${P}" --format='value(notificationChannels)')"
case "${CHANNELS}" in *"${CHANNEL}"*) echo "la regola avvisa ${EMAIL}" ;;
  *) stop "La regola «${POLICY_NAME}» non manda gli avvisi a ${EMAIL}." ;; esac
ENABLED="$(gcloud alpha monitoring policies describe "${POLICY}" --project="${P}" --format='value(enabled)')"
[ "${ENABLED}" = "True" ] || stop "La regola «${POLICY_NAME}» è disattivata."
if [ -n "${DRY_RUN}" ] && ! log_filter_ok "${LOG_POLICY}"; then
  echo "Prova a secco: la regola «${LOG_POLICY_NAME}» va aggiornata con i messaggi di ${LOG_MESSAGES##*/}."
  exit 0
fi
log_filter_ok "${LOG_POLICY}" || stop "La regola «${LOG_POLICY_NAME}» non sorveglia tutti i messaggi di ${LOG_MESSAGES##*/}."
echo "la regola «${LOG_POLICY_NAME}» sorveglia ${#MESSAGES[@]} messaggi"
CHANNELS="$(gcloud alpha monitoring policies describe "${LOG_POLICY}" --project="${P}" --format='value(notificationChannels)')"
case "${CHANNELS}" in *"${CHANNEL}"*) echo "e avvisa ${EMAIL}" ;;
  *) stop "La regola «${LOG_POLICY_NAME}» non manda gli avvisi a ${EMAIL}." ;; esac
ENABLED="$(gcloud alpha monitoring policies describe "${LOG_POLICY}" --project="${P}" --format='value(enabled)')"
[ "${ENABLED}" = "True" ] || stop "La regola «${LOG_POLICY_NAME}» è disattivata."

say "Monitoraggio a posto"
echo "Se ${CHECK_PATH} non risponde per 5 minuti da almeno 2 regioni su 3, arriva un'email a ${EMAIL}."
echo "Se il BFF scrive nel log una scrittura non riuscita, arriva un'email a ${EMAIL} (al massimo una all'ora)."

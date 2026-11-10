#!/usr/bin/env bash
# Publishes a lot with one command (D-214): staging, its checks, production, its checks, the VM's engine when its code
# changed, a summary in plain Italian. Run by the project owner (D-116), from Git Bash, in the app folder:
#
#   bash scripts/publish-all.sh <commit>              # one question at the start: «scrivi pubblica»
#   DRY_RUN=1 bash scripts/publish-all.sh <commit>    # reads the real state and shows every step; writes nothing
#
# Settings (no secrets) in scripts/publish-settings.conf: project, region, account, staging site, VPC, SMTP sender,
# VITE_FCM_ENABLED, the VM and the engine's apartment. It uses the scripts that exist: publish.sh (with its own checks:
# contract, .env, D-203 staging before production), deploy-engine.sh, engine-vm.sh through gcloud compute ssh (IAP).
#
# Steps, each skipped when it is already done (the state file says so AND the live state confirms it), so the same
# command after a FERMO starts again from the right place:
#   1 staging      publish.sh TARGET=staging, then: the latest revision ready and serving 100 %, its image the
#                  commit's, /health 200
#   2 production   publish.sh TARGET=prod, then the same checks, plus the active values against the manifest's
#   3 engine       only when a file that goes into the engine's image changed between the commit on the VM and this
#                  one (engine/ without tests/ and *.md, cloudbuild.engine.yaml): the image (built once), then
#                  engine-vm.sh update <apartment> <image>, which waits for /health 200; engine-vm.sh itself is copied
#                  and its timers reinstalled whenever the VM's copy differs from the commit's
#   4 summary      what was done, how long it took, and the commands to go back (never run by this script)
# It stops at the first error with FERMO and what to do; production never starts if staging is not healthy. Every line
# goes also to logs/publish-<date>-<commit>.log (not in Git); the state of a commit is logs/publish-state-<commit>.txt.
# Going back is printed, never done: the owner decides. The broker is not published here: it has its own procedure.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
SETTINGS="${PUBLISH_SETTINGS:-${HERE}/publish-settings.conf}"   # moved only by the tests
PUBLISH_SH="${PUBLISH_SH:-${HERE}/publish.sh}"                  # moved only by the tests
DEPLOY_ENGINE_SH="${DEPLOY_ENGINE_SH:-${HERE}/deploy-engine.sh}"
HEALTH_TRIES="${PUBLISH_HEALTH_TRIES:-12}"                      # every 10 s: two minutes
HEALTH_WAIT_S="${PUBLISH_HEALTH_WAIT_S:-10}"
DRY_RUN="${DRY_RUN:-}"
KNOWN="GCP_PROJECT_ID GCP_REGION ARTIFACT_REPO CLOUDSDK_CORE_ACCOUNT STAGING_SITE VPC_NETWORK VPC_SUBNET SMTP_USER VITE_FCM_ENABLED ENGINE_APARTMENT VM_NAME VM_ZONE"

say()  { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
stop() { printf '\n\033[1;31mFERMO: %s\033[0m\n' "$*" >&2; exit 1; }
note() { printf '  %s\n' "$*"; }

# ---- settings: only the known names, never evaluated as code ------------------------------------------------------
[ -f "${SETTINGS}" ] || stop "Manca ${SETTINGS}: sono le impostazioni della pubblicazione (vedi docs/procedura-ambienti-separati.md)."
while IFS= read -r line || [ -n "${line}" ]; do
  line="${line%$'\r'}"
  case "${line}" in ''|'#'*) continue ;; esac
  name="${line%%=*}"; value="${line#*=}"
  case " ${KNOWN} " in *" ${name} "*) export "${name}=${value}" ;; *) stop "In ${SETTINGS} c'è un nome che non conosco: ${name}" ;; esac
done < "${SETTINGS}"
for name in ${KNOWN}; do [ -n "${!name:-}" ] || stop "In ${SETTINGS} manca ${name}."; done

REF="${1:-}"
[ -n "${REF}" ] || stop "Manca il commit: bash scripts/publish-all.sh <commit> (il commit del lotto te lo dà la memoria storica)."
SHA="$(git -C "${ROOT}" rev-parse --verify --quiet "${REF}^{commit}")" || stop "Il commit «${REF}» non esiste in questa cartella."
SHORT="$(git -C "${ROOT}" rev-parse --short "${SHA}")"
SUBJECT="$(git -C "${ROOT}" log -1 --format=%s "${SHA}")"

# ---- the log, the state, one publication at a time ----------------------------------------------------------------
mkdir -p "${ROOT}/logs"
STARTED="$(date '+%Y-%m-%d %H:%M:%S')"; STARTED_S="$(date +%s)"
LOG="${ROOT}/logs/publish-$(date '+%Y%m%d-%H%M%S')-${SHORT}.log"
STATE="${ROOT}/logs/publish-state-${SHORT}.txt"
exec > >(tee -a "${LOG}") 2>&1
LOCK="${ROOT}/logs/publish.lock"
mkdir "${LOCK}" 2>/dev/null || stop "C'è già una pubblicazione in corso (cartella ${LOCK}).
Se sei sicuro che non ce n'è nessuna (per esempio la finestra si è chiusa a metà), cancella quella cartella e rilancia."
trap 'rmdir "${LOCK}" 2>/dev/null || true' EXIT
[ -n "${DRY_RUN}" ] || touch "${STATE}"
done_step() { [ -n "${DRY_RUN}" ] || echo "$1" >> "${STATE}"; }
has_step() { [ -f "${STATE}" ] && grep -qx "$1" "${STATE}"; }
remember() { [ -n "${DRY_RUN}" ] || grep -q "^$1=" "${STATE}" 2>/dev/null || echo "$1=$2" >> "${STATE}"; }   # the first value stays
recall() { [ -f "${STATE}" ] || return 0; sed -n "s/^$1=//p" "${STATE}" | head -1; }

gc() { gcloud "$@" --project "${GCP_PROJECT_ID}"; }
on_vm() { gc compute ssh "${VM_NAME}" --zone "${VM_ZONE}" --tunnel-through-iap --command "$1" 2>/dev/null | tr -d '\r'; }

say "Pubblicazione del commit ${SHORT} — ${SUBJECT}$([ -n "${DRY_RUN}" ] && echo '  (PROVA A SECCO: non scrivo niente)')"
note "inizio: ${STARTED}; registro: ${LOG}"

# ---- what is live now (read only) ---------------------------------------------------------------------------------
service_state() {   # service -> image|latest created|latest ready|serving revision|its percent|url
  gc run services describe "$1" --region "${GCP_REGION}" \
    --format "value[separator='|'](spec.template.spec.containers[0].image,status.latestCreatedRevisionName,status.latestReadyRevisionName,status.traffic[0].revisionName,status.traffic[0].percent,status.url)" \
    2>/dev/null | tr -d '\r' || true
}
service_problem() {   # service: what is not right, nothing when it serves this commit at 100 %
  local image created ready serving percent url
  IFS='|' read -r image created ready serving percent url <<< "$(service_state "$1")"
  [ -n "${image}" ] || { echo "non riesco a leggere il servizio $1"; return; }
  [ "${image##*:}" = "${SHORT}" ] || { echo "$1 ha l'immagine ${image##*:}, non ${SHORT}"; return; }
  [ "${created}" = "${ready}" ] || { echo "l'ultima revisione di $1 (${created}) non è pronta"; return; }
  [ "${ready}" = "${serving}" ] && [ "${percent:-0}" = "100" ] || echo "la revisione ${ready} di $1 non ha il 100 % del traffico (lo ha ${serving:-nessuna}, ${percent:-0} %)"
}
health_of() {   # service: 200 within HEALTH_TRIES, else the last code
  local url code="000"
  url="$(service_state "$1" | cut -d'|' -f6)"
  [ -n "${url}" ] || { echo "nessun indirizzo"; return; }
  for _ in $(seq 1 "${HEALTH_TRIES}"); do
    code="$(curl -s -o /dev/null -m 10 -w '%{http_code}' "${url}/health" 2>/dev/null || true)"
    [ "${code}" = "200" ] && { echo 200; return; }
    sleep "${HEALTH_WAIT_S}"
  done
  echo "${code:-000}"
}

say "Controlli prima di partire (sola lettura)"
for tool in git gcloud curl; do command -v "${tool}" > /dev/null || stop "Manca ${tool} in questa finestra di Git Bash."; done
git -C "${ROOT}" fetch --quiet origin 2>/dev/null || note "non riesco a leggere GitHub adesso: controllo con l'ultima copia nota di origin/main"
if git -C "${ROOT}" merge-base --is-ancestor "${SHA}" origin/main 2>/dev/null; then
  note "il commit è su GitHub"
elif [ -n "${DRY_RUN}" ]; then
  note "ATTENZIONE: il commit ${SHORT} non è su GitHub; nella pubblicazione vera mi fermerei qui (prima «git push»)."
else
  stop "Il commit ${SHORT} non è su GitHub (origin/main): prima «git push», poi rilancia lo stesso comando."
fi
for service in domotica-bff-staging domotica-bff; do
  IFS='|' read -r image _ _ serving percent _ <<< "$(service_state "${service}")"
  if [ -n "${image}" ]; then note "${service}: ora immagine ${image##*:} (revisione ${serving}, ${percent} %)"
  else note "${service}: stato non letto (il servizio non esiste ancora, oppure gcloud non risponde)"; fi
done
ENGINE_IMAGE="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REPO}/engine:${SHORT}"
VM_IMAGE="$(on_vm "sudo sed -n 's/^ENGINE_IMAGE=//p' /opt/domhouse/${ENGINE_APARTMENT}.settings" | tail -1)"
[ -n "${VM_IMAGE}" ] || stop "Non riesco a leggere l'immagine del motore ${ENGINE_APARTMENT} sulla VM ${VM_NAME} (gcloud compute ssh via IAP).
Controlla che la VM sia accesa e che «gcloud compute ssh» funzioni, poi rilancia."
note "motore ${ENGINE_APARTMENT} sulla VM: ${VM_IMAGE##*:}"
VM_TAG="${VM_IMAGE##*:}"
VM_SHA="$(git -C "${ROOT}" rev-parse --verify --quiet "${VM_TAG}^{commit}" 2>/dev/null || true)"
if [ "${VM_TAG}" = "${SHORT}" ]; then
  ENGINE_CHANGES="già a questo commit"
elif [ -z "${VM_SHA}" ]; then
  ENGINE_CHANGES="commit della VM sconosciuto (${VM_TAG}): aggiorno"
else
  # what goes into the image: engine/ (its Dockerfile drops tests/) and the build file; documents do not count (D-215)
  ENGINE_CHANGES="$(git -C "${ROOT}" diff --name-only "${VM_SHA}" "${SHA}" -- engine cloudbuild.engine.yaml \
    | grep -v '/tests/' | grep -v '\.md$' || true)"
fi
WANTED_SCRIPT="$(git -C "${ROOT}" show "${SHA}:scripts/engine-vm.sh" | tr -d '\r' | sha256sum | cut -d' ' -f1)"
VM_SCRIPT="$(on_vm "sudo tr -d '\\r' < /opt/domhouse/engine-vm.sh | sha256sum" | cut -d' ' -f1)"
case "${ENGINE_CHANGES}" in
  "") note "codice del motore invariato fra ${VM_TAG} e ${SHORT}: il motore non si aggiorna" ;;
  "già a questo commit") note "il motore è già all'immagine ${SHORT}" ;;
  *) note "codice del motore cambiato: il motore passa a ${SHORT}"; printf '%s\n' "${ENGINE_CHANGES}" | head -10 | sed 's/^/    /' ;;
esac
if [ "${WANTED_SCRIPT}" = "${VM_SCRIPT}" ]; then note "engine-vm.sh sulla VM è quello del commit"; else note "engine-vm.sh sulla VM è diverso da quello del commit: lo copio e reinstallo i timer"; fi

# ---- the one question --------------------------------------------------------------------------------------------
say "Cosa farò: staging, controlli, produzione, controlli$([ -n "${ENGINE_CHANGES}" ] && [ "${ENGINE_CHANGES}" != "già a questo commit" ] && echo ', motore sulla VM')$([ "${WANTED_SCRIPT}" != "${VM_SCRIPT}" ] && echo ', engine-vm.sh sulla VM'), riepilogo"
if [ -n "${DRY_RUN}" ]; then
  note "prova a secco: non chiedo conferma"
else
  printf '\n\033[1;33mPer pubblicare il commit %s in staging e in produzione scrivi pubblica:\033[0m ' "${SHORT}"
  read -r answer || answer=""
  answer="${answer%$'\r'}"                  # a Windows console may end the line with \r
  [ "${answer}" = "pubblica" ] || stop "Pubblicazione annullata: non hai scritto «pubblica». Non è cambiato niente."
fi

# ---- 1 and 2: staging, then production -----------------------------------------------------------------------------
publish_target() {   # target service
  local target="$1" service="$2" problem code
  say "${target}: servizio ${service}"
  if has_step "${target}" && [ -z "$(service_problem "${service}")" ]; then
    note "già fatto in un giro precedente, e ${service} serve ${SHORT}: non lo ripubblico"
    return 0
  fi
  remember "prima-${target}" "$(service_state "${service}" | cut -d'|' -f4)"
  if [ -n "${DRY_RUN}" ]; then
    if [ "${target}" = "prod" ] && [ -n "$(service_problem domotica-bff-staging)" ]; then
      note "prova a secco: la produzione si prova a secco solo quando lo staging serve già ${SHORT} (D-203)"
      return 0
    fi
    DRY_RUN=1 TARGET="${target}" bash "${PUBLISH_SH}" "${SHA}" || stop "La prova a secco di publish.sh TARGET=${target} non è riuscita: leggi i messaggi sopra."
    return 0
  fi
  PUBLISH_ALL_CONFIRMED=pubblica TARGET="${target}" bash "${PUBLISH_SH}" "${SHA}" \
    || stop "publish.sh TARGET=${target} si è fermato: leggi i messaggi sopra. Risolto il problema, rilancia lo stesso comando: riparte da qui."
  say "Controlli su ${service}"
  problem="$(service_problem "${service}")"
  [ -z "${problem}" ] || stop "Dopo la pubblicazione ${problem}.
$(back_line "${target}" "${service}")"
  note "revisione nuova pronta e al 100 %, immagine ${SHORT}"
  code="$(health_of "${service}")"
  [ "${code}" = "200" ] || stop "${service} non risponde 200 su /health (ultimo codice: ${code}).
$(back_line "${target}" "${service}")"
  note "/health risponde 200"
  [ "${target}" != "prod" ] || values_match
  done_step "${target}"
}
back_line() {   # target service: the command to go back, printed, never run
  local before; before="$(recall "prima-$1")"
  if [ -n "${before}" ]; then
    echo "Per tornare alla revisione di prima (lo decidi tu, lo script non lo fa):
  gcloud run services update-traffic $2 --to-revisions=${before}=100 --region ${GCP_REGION} --project ${GCP_PROJECT_ID}"
  else
    echo "La revisione di prima non è nota: guarda le revisioni di $2 nella console di Cloud Run."
  fi
}
values_match() {   # production: the active values against the commit's manifest (D-197)
  local manifest live want got
  manifest="$(git -C "${ROOT}" show "${SHA}:bff/cloudrun.yaml")"
  number() { printf '%s\n' "${manifest}" | sed -n "s#^ *$1: *\"\{0,1\}\([0-9][0-9]*\)\"\{0,1\}.*#\1#p" | head -1; }
  want="$(number autoscaling.knative.dev/minScale)|$(number autoscaling.knative.dev/maxScale)|$(number containerConcurrency)|$(number timeoutSeconds)"
  live="$(gc run services describe domotica-bff --region "${GCP_REGION}" \
    --format "value[separator='|'](spec.template.metadata.annotations.'autoscaling.knative.dev/minScale',spec.template.metadata.annotations.'autoscaling.knative.dev/maxScale',spec.template.spec.containerConcurrency,spec.template.spec.timeoutSeconds)" \
    2>/dev/null | tr -d '\r' || true)"
  got="${live}"; [ "${got%%|*}" != "" ] || got="0${got}"     # Cloud Run does not store a minimum of 0
  [ "${got}" = "${want}" ] || stop "Valori attivi della produzione diversi dal manifesto: attivi ${got:-non letti}, manifesto ${want} (istanze minime|massime|richieste contemporanee|tempo massimo).
$(back_line prod domotica-bff)"
  note "valori attivi uguali al manifesto: ${want} (istanze minime|massime|richieste contemporanee|tempo massimo)"
}

publish_target staging domotica-bff-staging
publish_target prod domotica-bff

# ---- 3: the engine on the VM ----------------------------------------------------------------------------------------
say "Motore sulla VM (${VM_NAME}, appartamento ${ENGINE_APARTMENT})"
ENGINE_DONE="invariato"
ENGINE_NEEDED=""
[ -z "${ENGINE_CHANGES}" ] || [ "${ENGINE_CHANGES}" = "già a questo commit" ] || ENGINE_NEEDED=1
# the image first: it is the long step and the one that can fail; then the VM's changes together
if [ -n "${ENGINE_NEEDED}" ]; then
  remember "prima-motore" "${VM_IMAGE}"
  if [ -n "${DRY_RUN}" ]; then
    DRY_RUN=1 bash "${DEPLOY_ENGINE_SH}" "${SHA}" || stop "La prova a secco di deploy-engine.sh non è riuscita."
  else
    bash "${DEPLOY_ENGINE_SH}" "${SHA}" || stop "La costruzione dell'immagine del motore non è riuscita: leggi i messaggi sopra, poi rilancia."
  fi
fi
if [ "${WANTED_SCRIPT}" != "${VM_SCRIPT}" ]; then
  if [ -n "${DRY_RUN}" ]; then
    note "prova a secco: copierei engine-vm.sh del commit e lancerei engine-vm.sh timers"
  else
    COPY="$(mktemp)"
    git -C "${ROOT}" show "${SHA}:scripts/engine-vm.sh" | tr -d '\r' > "${COPY}"
    gc compute scp "${COPY}" "${VM_NAME}:engine-vm.sh" --zone "${VM_ZONE}" --tunnel-through-iap \
      || stop "La copia di engine-vm.sh sulla VM non è riuscita: rilancia lo stesso comando."
    rm -f "${COPY}"
    on_vm "sudo install -m 755 ~/engine-vm.sh /opt/domhouse/engine-vm.sh && sudo bash /opt/domhouse/engine-vm.sh timers > /dev/null && echo timer-ok" \
      | grep -q timer-ok || stop "engine-vm.sh timers sulla VM non è riuscito: rilancia lo stesso comando."
    note "engine-vm.sh copiato e timer reinstallati"
  fi
fi
if [ -n "${ENGINE_NEEDED}" ]; then
  if [ -n "${DRY_RUN}" ]; then
    note "prova a secco: poi engine-vm.sh update ${ENGINE_APARTMENT} ${ENGINE_IMAGE}"
  else
    on_vm "sudo bash /opt/domhouse/engine-vm.sh update ${ENGINE_APARTMENT} ${ENGINE_IMAGE} > /dev/null 2>&1 && echo update-ok" \
      | grep -q update-ok || stop "Il motore ${ENGINE_APARTMENT} non è tornato sano con ${ENGINE_IMAGE}.
Per tornare all'immagine di prima (lo decidi tu):
  gcloud compute ssh ${VM_NAME} --zone ${VM_ZONE} --tunnel-through-iap --project ${GCP_PROJECT_ID} --command='sudo bash /opt/domhouse/engine-vm.sh update ${ENGINE_APARTMENT} $(recall prima-motore)'"
    [ "$(on_vm "sudo sed -n 's/^ENGINE_IMAGE=//p' /opt/domhouse/${ENGINE_APARTMENT}.settings" | tail -1)" = "${ENGINE_IMAGE}" ] \
      || stop "Dopo l'aggiornamento la VM non dice l'immagine ${ENGINE_IMAGE}: guarda engine-vm.sh status ${ENGINE_APARTMENT}."
    note "motore ${ENGINE_APARTMENT} a ${SHORT}, /health 200"
    done_step engine
  fi
  ENGINE_DONE="da ${VM_TAG} a ${SHORT}"
fi

# ---- 4: the summary -------------------------------------------------------------------------------------------------
ELAPSED=$(( $(date +%s) - STARTED_S ))
say "Riepilogo da incollare alla memoria storica$([ -n "${DRY_RUN}" ] && echo ' (prova a secco: niente è stato pubblicato)')"
echo "Pubblicazione del commit ${SHA} (${SUBJECT})"
echo "dalle ${STARTED} alle $(date '+%H:%M:%S'), ${ELAPSED} s"
for service in domotica-bff-staging domotica-bff; do
  IFS='|' read -r image _ _ serving percent url <<< "$(service_state "${service}")"
  echo "${service}: immagine ${image##*:}, revisione ${serving:-non letta} al ${percent:-0} %, ${url:-indirizzo non letto}"
done
echo "motore ${ENGINE_APARTMENT}: ${ENGINE_DONE}$([ "${WANTED_SCRIPT}" != "${VM_SCRIPT}" ] && echo '; engine-vm.sh aggiornato sulla VM')"
for target in staging prod; do
  before="$(recall "prima-${target}")"
  [ -z "${before}" ] || echo "per tornare indietro (${target}): gcloud run services update-traffic $([ "${target}" = prod ] && echo domotica-bff || echo domotica-bff-staging) --to-revisions=${before}=100 --region ${GCP_REGION} --project ${GCP_PROJECT_ID}"
done
[ -z "$(recall prima-motore)" ] || echo "per tornare indietro (motore): engine-vm.sh update ${ENGINE_APARTMENT} $(recall prima-motore) sulla VM"
echo "registro completo: ${LOG}"

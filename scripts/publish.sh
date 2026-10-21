#!/usr/bin/env bash
# Publishes a COMMIT (not the working folder): checks it out into a clean temporary git worktree, copies
# frontend/.env.production (not in Git) into it, runs the safety checks, then runs that commit's scripts/deploy.sh.
#
#   TARGET=staging GCP_PROJECT_ID=<project> SMTP_USER=<sender> scripts/publish.sh            # publishes HEAD
#   TARGET=staging GCP_PROJECT_ID=<project> SMTP_USER=<sender> scripts/publish.sh <commit>   # a given commit
#   TARGET=prod GCP_PROJECT_ID=<project> VPC_NETWORK=<net> VPC_SUBNET=<subnet> SMTP_USER=<sender> scripts/publish.sh
#
# Optional: ENV_FILE=<path> (default frontend/.env.production of this working folder), GCP_REGION, ARTIFACT_REPO,
#           VITE_FCM_ENABLED, SKIP_HOSTING=1 (passed to deploy.sh).
#           BUILD_SA=<email> (default domotica-build@<project>.iam.gserviceaccount.com): Cloud Build's account (P-21).
#           DRY_RUN=1 does everything that stays on this machine (checks, clean copy, PWA build) and nothing that
#           writes outside it: no firebase, no questions, gcloud only to read (and only with GCP_PROJECT_ID set).
# The image tag is the commit's short SHA (computed by deploy.sh in the clean copy); when that image already exists in
# Artifact Registry the build is skipped (read-only check), so republishing a commit never rebuilds a different image.
# Messages are in plain Italian: this script is run by the project owner.
set -euo pipefail

say()  { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
stop() { printf '\n\033[1;31mFERMO: %s\033[0m\n' "$*" >&2; exit 1; }
ask()  { # ask "<question>" "<expected answer>": anything else stops the script
  local answer
  printf '\n\033[1;33m%s\033[0m ' "$1"
  read -r answer || answer=""
  [ "${answer}" = "$2" ] || stop "Pubblicazione annullata: non hai scritto «$2»."
}

TARGET="${TARGET:-}"
[ -n "${TARGET}" ] || stop "Manca TARGET: scrivi TARGET=staging (oppure TARGET=prod) prima del comando."
DRY_RUN="${DRY_RUN:-}"
PROJECT="${GCP_PROJECT_ID:-}"
if [ -z "${PROJECT}" ]; then
  [ -n "${DRY_RUN}" ] || stop "Manca GCP_PROJECT_ID: scrivi GCP_PROJECT_ID=<progetto> prima del comando."
  PROJECT="your-gcp-project-id"
fi
REGION="${GCP_REGION:-europe-west8}"
REPO="${ARTIFACT_REPO:-domotica}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${SRC}/frontend/.env.production}"
# Git blob of contract/openapi.yaml v1.0.5 (line-ending independent). The contract never changes: a different blob
# means the commit is not publishable.
CONTRACT_BLOB="1b5cb31306cff21e2a40ed470f1c91b2cdb30e9e"

case "${TARGET}" in
  staging) ;;
  prod) [ -n "${VPC_NETWORK:-}" ] && [ -n "${VPC_SUBNET:-}" ] || stop "Per prod servono anche VPC_NETWORK e VPC_SUBNET." ;;
  *) stop "TARGET deve essere staging oppure prod (hai scritto «${TARGET}»)." ;;
esac

# --- 0. Cloud Build's own account (P-21): checked first, before anything is spent -----------------------------
export BUILD_SA="${BUILD_SA:-domotica-build@${PROJECT}.iam.gserviceaccount.com}"  # deploy.sh reads the same variable
if [ -z "${GCP_PROJECT_ID:-}" ]; then
  echo "Prova a secco senza GCP_PROJECT_ID: non controllo l'account di Cloud Build (${BUILD_SA})."
elif gcloud iam service-accounts describe "${BUILD_SA}" --project "${PROJECT}" >/dev/null 2>&1; then
  echo "account di Cloud Build presente: ${BUILD_SA}"
else
  stop "Manca l'account ${BUILD_SA}, con cui Cloud Build costruisce il server (oppure gcloud non riesce a leggerlo).
Prima lancia i comandi della sezione «P-21» di docs/comandi-da-lanciare.md, poi ripeti questo comando."
fi

# --- 1. Which commit -------------------------------------------------------------------------------------------
REF="${1:-HEAD}"
SHA="$(git -C "${SRC}" rev-parse --verify --quiet "${REF}^{commit}")" || stop "Il commit «${REF}» non esiste in questa cartella."
SHORT="$(git -C "${SRC}" rev-parse --short "${SHA}")"
SUBJECT="$(git -C "${SRC}" log -1 --format=%s "${SHA}")"
say "Commit da pubblicare: ${SHORT} — ${SUBJECT}"
if [ -n "$(git -C "${SRC}" status --porcelain --untracked-files=no)" ]; then
  echo "Nota: nella cartella di lavoro ci sono modifiche non salvate in un commit. NON verranno pubblicate:"
  echo "si pubblica solo il commit ${SHORT}."
fi

# --- 2. Is it on GitHub? ---------------------------------------------------------------------------------------
if git -C "${SRC}" fetch --quiet origin 2>/dev/null; then :; else
  echo "Nota: non riesco a leggere GitHub adesso; controllo con l'ultima copia nota di origin/main."
fi
if ! git -C "${SRC}" merge-base --is-ancestor "${SHA}" origin/main 2>/dev/null; then
  if [ -n "${DRY_RUN}" ]; then
    echo "Attenzione: il commit ${SHORT} non è su GitHub (origin/main). In una pubblicazione vera chiederei conferma."
  else
    echo "Il commit ${SHORT} non è ancora su GitHub: online andrebbe una versione che GitHub non conserva."
    echo "Di solito prima si fa «git push» e poi si pubblica."
    ask "Il commit ${SHORT} non è su GitHub: pubblicare lo stesso? (scrivi si)" "si"
  fi
fi

# --- 3. Production needs an explicit yes -----------------------------------------------------------------------
if [ "${TARGET}" = "prod" ]; then
  if [ -n "${DRY_RUN}" ]; then
    echo "Attenzione: TARGET=prod. In una pubblicazione vera chiederei di scrivere «prod»."
  else
    echo "Stai per pubblicare in PRODUZIONE: l'app userà il motore domotico vero sulla VM."
    echo "Va fatto solo se il motore risponde (regola 3 di CLAUDE.md)."
    ask "Per continuare scrivi prod:" "prod"
  fi
fi

# --- 4. Checks on the commit itself ----------------------------------------------------------------------------
say "Controlli sul commit"
[ "$(git -C "${SRC}" rev-parse "${SHA}:contract/openapi.yaml" 2>/dev/null)" = "${CONTRACT_BLOB}" ] \
  || stop "contract/openapi.yaml in questo commit è diverso dal contratto v1.0.5. Non si pubblica."
echo "contratto v1.0.5 invariato"
TRACKED_ENV="$(git -C "${SRC}" ls-tree -r --name-only "${SHA}" | grep -E '(^|/)\.env($|\.)' | grep -vE '\.env\.example$' || true)"
[ -z "${TRACKED_ENV}" ] || stop "Il commit contiene file .env che non devono stare in Git: ${TRACKED_ENV}"
echo "nessun file .env nel commit"
[ -f "${ENV_FILE}" ] || stop "Manca ${ENV_FILE}: è la configurazione del sito, va compilata a mano (vedi frontend/.env.example)."
grep -qE '^VITE_FIREBASE_API_KEY=.+' "${ENV_FILE}" || stop "In ${ENV_FILE} manca VITE_FIREBASE_API_KEY."
! grep -qE 'replace-me|your-|<[^>]*>' "${ENV_FILE}" || stop "In ${ENV_FILE} ci sono ancora valori da sostituire (replace-me, your-…, <…>)."
echo "configurazione del sito presente (contenuto non mostrato)"

# --- 5. Clean copy of the commit -------------------------------------------------------------------------------
TMP="$(mktemp -d)"
WT="${TMP}/app"
cleanup() {
  git -C "${SRC}" worktree remove --force "${WT}" >/dev/null 2>&1 || true
  git -C "${SRC}" worktree prune >/dev/null 2>&1 || true
  rm -rf "${TMP}"
}
trap cleanup EXIT
say "Copia pulita del commit ${SHORT}"
# autocrlf off: the copy holds the commit's exact bytes (LF), so bash can run deploy.sh and Cloud Build gets LF files.
git -C "${SRC}" -c core.autocrlf=false worktree add --detach --quiet "${WT}" "${SHA}"
! grep -q $'\r' "${WT}/scripts/deploy.sh" || stop "scripts/deploy.sh nella copia pulita ha fine riga Windows: bash non lo può eseguire."
grep -q -- '--service-account' "${WT}/scripts/deploy.sh" \
  || echo "Attenzione: il commit ${SHORT} è precedente a P-21: Cloud Build userà l'account predefinito di Compute, non ${BUILD_SA}."
cp "${ENV_FILE}" "${WT}/frontend/.env.production"
TAG="$(git -C "${WT}" rev-parse --short HEAD)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/bff:${TAG}"
echo "cartella temporanea: ${WT}"

# --- 6a. Dry run: everything local, nothing online -------------------------------------------------------------
if [ -n "${DRY_RUN}" ]; then
  say "Prova a secco: compilo il sito dalla copia pulita (nessuna pubblicazione)"
  ( cd "${WT}/frontend" && yarn install --frozen-lockfile --silent && \
    VITE_BFF_URL="https://bff.dry-run.invalid" VITE_AUTH_MODE=firebase VITE_FCM_ENABLED="${VITE_FCM_ENABLED:-false}" yarn build ) \
    || stop "La compilazione del sito dal commit ${SHORT} non è riuscita: leggi i messaggi sopra."
  [ -f "${WT}/frontend/dist/index.html" ] || stop "La compilazione del sito non ha prodotto dist/index.html."
  [ -z "$(git -C "${WT}" status --porcelain --untracked-files=no)" ] \
    || stop "La compilazione ha modificato file versionati nella copia pulita: $(git -C "${WT}" status --porcelain --untracked-files=no | tr '\n' ' ')"
  say "Prova a secco riuscita"
  echo "Commit ${SHORT} — ${SUBJECT}"
  echo "Immagine che verrebbe usata: ${IMAGE}"
  echo "Account di Cloud Build: ${BUILD_SA}"
  echo "Nessun comando che scrive online è stato eseguito (gcloud solo in lettura, niente firebase)."
  exit 0
fi

# --- 6b. Real publication: the commit's own deploy.sh, from the clean copy ------------------------------------
if gcloud artifacts docker images describe "${IMAGE}" --project "${PROJECT}" >/dev/null 2>&1; then
  echo "L'immagine ${IMAGE} esiste già: non la ricostruisco."
  export SKIP_BUILD=1
fi
say "Pubblicazione ${TARGET} del commit ${SHORT}"
LOG="${TMP}/deploy.log"
( cd "${WT}" && TARGET="${TARGET}" GCP_PROJECT_ID="${PROJECT}" GCP_REGION="${REGION}" ARTIFACT_REPO="${REPO}" \
    bash scripts/deploy.sh ) 2>&1 | tee "${LOG}" \
  || stop "La pubblicazione si è fermata a metà: leggi i messaggi sopra e passali alla memoria storica."
BFF_URL="$(sed -n 's/^BFF: //p' "${LOG}" | tail -1)"
PWA_URL="$(sed -n 's/^PWA: //p' "${LOG}" | tail -1)"

say "Fatto. Righe da incollare alla memoria storica:"
echo "Pubblicazione ${TARGET} del $(date '+%Y-%m-%d %H:%M')"
echo "commit: ${SHA} (${SUBJECT})"
echo "immagine: ${IMAGE}$([ -n "${SKIP_BUILD:-}" ] && echo ' (già esistente, non ricostruita)')"
echo "BFF: ${BFF_URL:-non letto}"
echo "PWA: ${PWA_URL:-non pubblicata (SKIP_HOSTING)}"

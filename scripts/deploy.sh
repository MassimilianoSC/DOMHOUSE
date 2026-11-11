#!/usr/bin/env bash
# Builds and deploys the BFF to Cloud Run and the PWA to Firebase Hosting.
#
#   TARGET=staging GCP_PROJECT_ID=<project> VPC_NETWORK=<net> VPC_SUBNET=<subnet> VM_INTERNAL_IP=<ip> STAGING_SITE=<site> scripts/deploy.sh
#   TARGET=prod    GCP_PROJECT_ID=<project> VPC_NETWORK=<net> VPC_SUBNET=<subnet> scripts/deploy.sh
# (scripts/publish-all.sh passes them from scripts/publish-settings.conf)
#
# Optional: GCP_REGION (default europe-west8), ARTIFACT_REPO (default domotica), VITE_FCM_ENABLED (default false),
#           SKIP_BUILD=1 to redeploy the last image, SKIP_HOSTING=1 to deploy the BFF only,
#           BUILD_SA (default domotica-build@<project>.iam.gserviceaccount.com): the service account Cloud Build runs
#           as (P-21), instead of the default Compute account with the Editor role,
#           SMTP_USER=<sender address> for invitation emails (its password is the Secret Manager secret smtp-app-password,
#           which must exist before the deploy; without SMTP_USER invites are recorded but no email is sent),
#           DRY_RUN=1 to see the service's active values against the manifest's and stop: gcloud only reads, nothing is
#           built or published.
# Prerequisites: gcloud authenticated on the project, node + yarn, firebase-tools logged in (npx firebase-tools login),
#                frontend/.env.production with VITE_FIREBASE_* (see frontend/.env.example).
set -euo pipefail

TARGET="${TARGET:?set TARGET=staging or TARGET=prod}"
PROJECT="${GCP_PROJECT_ID:?set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-europe-west8}"
REPO="${ARTIFACT_REPO:-domotica}"
BUILD_SA="${BUILD_SA:-domotica-build@${PROJECT}.iam.gserviceaccount.com}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="$(git -C "${ROOT}" rev-parse --short HEAD 2>/dev/null || echo latest)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/bff:${TAG}"

# P-67 (D-136): two environments in the same project, each with its Cloud Run service, Firestore database and Hosting
# site; Firebase Auth is shared (claims per environment). Both reach the VM through Direct VPC egress.
case "${TARGET}" in
  staging) MANIFEST="${ROOT}/bff/cloudrun.staging.yaml"; SERVICE=domotica-bff-staging; DATABASE=staging
           HOSTING_TARGET=staging; SITE="${STAGING_SITE:-}"
           # D53 (P-83): no guessed site: «<project>-staging» is not the staging site, and CORS, APP_PUBLIC_URL and the
           # Cloud Run service were written with it before Hosting failed
           [ -n "${SITE}" ] || { echo "set STAGING_SITE (the staging Hosting site, e.g. the one in scripts/publish-settings.conf)" >&2; exit 1; } ;;
  prod)    MANIFEST="${ROOT}/bff/cloudrun.yaml"; SERVICE=domotica-bff; DATABASE="(default)"
           HOSTING_TARGET=prod; SITE="${PROJECT}" ;;
  *)       echo "TARGET must be staging or prod" >&2; exit 1 ;;
esac
: "${VPC_NETWORK:?set VPC_NETWORK (the VM is reached through Direct VPC egress)}" "${VPC_SUBNET:?set VPC_SUBNET}"
# D04 (P-83): staging reaches only the engines listed in its INSTANCE_ALLOWED, on the VM's internal address
if grep -q "your-vm-internal-ip" "${MANIFEST}"; then
  [[ "${VM_INTERNAL_IP:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || { echo "set VM_INTERNAL_IP (the VM's internal address, for ${MANIFEST}'s INSTANCE_ALLOWED)" >&2; exit 1; }
fi
# the manifest must be the TARGET's: a production published on the staging database (or the reverse) stops here
grep -q "^  name: ${SERVICE}\$" "${MANIFEST}" || { echo "${MANIFEST} is not the service ${SERVICE}" >&2; exit 1; }
grep -A1 "name: FIRESTORE_DATABASE" "${MANIFEST}" | grep -qF "${DATABASE}" \
  || { echo "${MANIFEST} does not use the database ${DATABASE}" >&2; exit 1; }
# D-180: the model's location is eu or a European region, never global nor us (the BFF refuses to start otherwise)
AI_LOC="$(grep -A1 "name: AI_LOCATION" "${MANIFEST}" | sed -n 's/^ *value: *"\{0,1\}\([^" ]*\)"\{0,1\}.*/\1/p' | head -1)"
case "${AI_LOC:-eu}" in
  eu|europe-*) ;;
  *) echo "${MANIFEST}: AI_LOCATION ${AI_LOC} is not European (D-180: eu or europe-…, never global nor us)" >&2; exit 1 ;;
esac
echo "ambiente ${TARGET}: servizio ${SERVICE}, database ${DATABASE}, sito ${SITE}"

step() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31mFERMO: %s\033[0m\n' "$*" >&2; exit 1; }

# D-197 (E-27): the four values that decide how the service runs. A publication replaces them with the manifest's: the
# active ones are shown first, and afterwards the new revision must have the manifest's, or the script stops here.
manifest_number() { sed -n "s#^ *$1: *\"\{0,1\}\([0-9][0-9]*\)\"\{0,1\}.*#\1#p" "${MANIFEST}" | head -1; }
MIN_NEW="$(manifest_number autoscaling.knative.dev/minScale)"
MAX_NEW="$(manifest_number autoscaling.knative.dev/maxScale)"
CONCURRENCY_NEW="$(manifest_number containerConcurrency)"
TIMEOUT_NEW="$(manifest_number timeoutSeconds)"
[ -n "${MIN_NEW}" ] && [ -n "${MAX_NEW}" ] && [ -n "${CONCURRENCY_NEW}" ] && [ -n "${TIMEOUT_NEW}" ] \
  || fail "${MANIFEST} non dichiara istanze minime, istanze massime, concorrenza e tempo massimo: non pubblico."
values_format() {
  printf "value[separator='|'](%s.annotations.'autoscaling.knative.dev/minScale',%s.annotations.'autoscaling.knative.dev/maxScale',%s.containerConcurrency,%s.timeoutSeconds)" "$1" "$1" "$2" "$2"
}
setting_line() {  # setting_line <what> <active> <new>
  local note="non cambia"
  [ "$2" = "$3" ] || note="CAMBIA"
  [ "$2" != "non letto" ] || note=""
  printf '  %-37s attivo: %-10s nuovo: %-10s %s\n' "$1" "$2" "$3" "${note}"
}
LIVE=""
if [ "${PROJECT}" != "your-gcp-project-id" ]; then
  LIVE="$(gcloud run services describe "${SERVICE}" --project "${PROJECT}" --region "${REGION}" \
    --format "$(values_format spec.template.metadata spec.template.spec)" 2>/dev/null | tr -d '\r' || true)"
fi
MIN_LIVE="non letto"; MAX_LIVE="non letto"; CONCURRENCY_LIVE="non letto"; TIMEOUT_LIVE="non letto"
if [ -n "${LIVE}" ]; then
  IFS='|' read -r MIN_LIVE MAX_LIVE CONCURRENCY_LIVE TIMEOUT_LIVE <<< "${LIVE}"
  MIN_LIVE="${MIN_LIVE:-0}"      # Cloud Run does not store a minimum of 0
fi
step "Impostazioni del servizio ${SERVICE}"
[ -n "${LIVE}" ] || echo "  Valori attivi non letti: il servizio non esiste ancora, oppure la lettura non è riuscita."
setting_line "istanze minime" "${MIN_LIVE}" "${MIN_NEW}"
setting_line "istanze massime" "${MAX_LIVE}" "${MAX_NEW}"
setting_line "richieste contemporanee per istanza" "${CONCURRENCY_LIVE}" "${CONCURRENCY_NEW}"
setting_line "tempo massimo di una richiesta (s)" "${TIMEOUT_LIVE}" "${TIMEOUT_NEW}"
if [ -n "${DRY_RUN:-}" ]; then
  echo "Prova a secco: nessuna costruzione e nessuna pubblicazione."
  exit 0
fi

if [ -z "${SKIP_BUILD:-}" ]; then
  step "Build BFF image ${IMAGE} (Cloud Build)"
  gcloud builds submit "${ROOT}" --project "${PROJECT}" --config "${ROOT}/cloudbuild.yaml" --substitutions "_IMAGE=${IMAGE}" --ignore-file "${ROOT}/.gcloudignore" \
    --service-account "projects/${PROJECT}/serviceAccounts/${BUILD_SA}"
fi

step "Deploy Cloud Run service (${TARGET})"
RENDERED="$(mktemp)"
sed -e "s#europe-west8-docker.pkg.dev/your-gcp-project-id/domotica/bff:latest#${IMAGE}#g" \
    -e "s#your-gcp-project-id#${PROJECT}#g" \
    -e "s#europe-west8#${REGION}#g" \
    -e "s#your-vpc-network#${VPC_NETWORK:-}#g" \
    -e "s#your-vpc-subnet#${VPC_SUBNET:-}#g" \
    -e "s#your-vm-internal-ip#${VM_INTERNAL_IP:-}#g" \
    -e "s#your-staging-site#${SITE}#g" \
    -e "s#your-smtp-user@example.com#${SMTP_USER:-}#g" \
    "${MANIFEST}" > "${RENDERED}"
gcloud run services replace "${RENDERED}" --project "${PROJECT}" --region "${REGION}"
gcloud run services add-iam-policy-binding "${SERVICE}" --project "${PROJECT}" --region "${REGION}" \
  --member=allUsers --role=roles/run.invoker --quiet >/dev/null   # auth is done by the BFF (Firebase ID token)
# The service answers on two equivalent URLs; status.url is the old random-looking one. Prefer the deterministic
# https://domotica-bff-<project number>.<region>.run.app (also used by monitoring and the Italianway webhook).
URLS="$(gcloud run services describe "${SERVICE}" --project "${PROJECT}" --region "${REGION}" --format "value(metadata.annotations.'run.googleapis.com/urls')")"
BFF_URL="$(printf '%s' "${URLS}" | grep -oE "https://[^\"]+\.${REGION}\.run\.app" | head -1 || true)"
[ -n "${BFF_URL}" ] || BFF_URL="$(gcloud run services describe "${SERVICE}" --project "${PROJECT}" --region "${REGION}" --format 'value(status.url)')"
rm -f "${RENDERED}"
echo "BFF: ${BFF_URL}"

step "Controllo della revisione nuova"
REVISION="$(gcloud run services describe "${SERVICE}" --project "${PROJECT}" --region "${REGION}" \
  --format 'value(status.latestReadyRevisionName)' | tr -d '\r' || true)"
APPLIED=""
if [ -n "${REVISION}" ]; then
  APPLIED="$(gcloud run revisions describe "${REVISION}" --project "${PROJECT}" --region "${REGION}" \
    --format "$(values_format metadata spec)" | tr -d '\r' || true)"
fi
[ -n "${APPLIED}" ] || fail "Non riesco a rileggere la revisione nuova di ${SERVICE}. Il server è pubblicato, il sito no. Passa questi messaggi alla memoria storica."
IFS='|' read -r MIN_GOT MAX_GOT CONCURRENCY_GOT TIMEOUT_GOT <<< "${APPLIED}"
MIN_GOT="${MIN_GOT:-0}"
WRONG=""
[ "${MIN_GOT}" = "${MIN_NEW}" ] || WRONG="${WRONG} istanze minime: atteso ${MIN_NEW}, trovato ${MIN_GOT};"
[ "${MAX_GOT}" = "${MAX_NEW}" ] || WRONG="${WRONG} istanze massime: atteso ${MAX_NEW}, trovato ${MAX_GOT};"
[ "${CONCURRENCY_GOT}" = "${CONCURRENCY_NEW}" ] || WRONG="${WRONG} richieste contemporanee: atteso ${CONCURRENCY_NEW}, trovato ${CONCURRENCY_GOT};"
[ "${TIMEOUT_GOT}" = "${TIMEOUT_NEW}" ] || WRONG="${WRONG} tempo massimo: atteso ${TIMEOUT_NEW}, trovato ${TIMEOUT_GOT};"
[ -z "${WRONG}" ] || fail "La revisione ${REVISION} non ha i valori del manifesto:${WRONG} il server è pubblicato così, il sito no. Passa questi messaggi alla memoria storica."
echo "La revisione ${REVISION} ha i valori del manifesto."

if [ -z "${SKIP_HOSTING:-}" ]; then
  step "Build PWA (VITE_BFF_URL=${BFF_URL})"
  ( cd "${ROOT}/frontend" && yarn install --frozen-lockfile && \
    VITE_BFF_URL="${BFF_URL}" VITE_AUTH_MODE=firebase VITE_FCM_ENABLED="${VITE_FCM_ENABLED:-false}" yarn build )

  step "Deploy Firebase Hosting (${HOSTING_TARGET} -> ${SITE})"
  # firebase.json declares the targets prod and staging; the site of each is applied here, on a copy of .firebaserc
  # put back afterwards (the committed one holds placeholders only)
  ( cd "${ROOT}/frontend" && cp .firebaserc .firebaserc.deploy-backup && \
    trap 'mv -f .firebaserc.deploy-backup .firebaserc' EXIT && \
    npx firebase-tools target:apply hosting "${HOSTING_TARGET}" "${SITE}" --project "${PROJECT}" && \
    npx firebase-tools deploy --only "hosting:${HOSTING_TARGET}" --project "${PROJECT}" )
  echo "PWA: https://${SITE}.web.app"
fi

step "Done"
echo "First admin: python scripts/set_claims.py --email <admin> --tenant <tenant_id> --role admin --create --send-reset-link"

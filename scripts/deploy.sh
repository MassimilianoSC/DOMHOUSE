#!/usr/bin/env bash
# Builds and deploys the BFF to Cloud Run and the PWA to Firebase Hosting.
#
#   TARGET=staging GCP_PROJECT_ID=<project> scripts/deploy.sh      # mock engine built into the BFF, simulator on
#   TARGET=prod    GCP_PROJECT_ID=<project> VPC_NETWORK=<net> VPC_SUBNET=<subnet> scripts/deploy.sh
#
# Optional: GCP_REGION (default europe-west8), ARTIFACT_REPO (default domotica), VITE_FCM_ENABLED (default false),
#           SKIP_BUILD=1 to redeploy the last image, SKIP_HOSTING=1 to deploy the BFF only,
#           BUILD_SA (default domotica-build@<project>.iam.gserviceaccount.com): the service account Cloud Build runs
#           as (P-21), instead of the default Compute account with the Editor role,
#           SMTP_USER=<sender address> for invitation emails (its password is the Secret Manager secret smtp-app-password,
#           which must exist before the deploy; without SMTP_USER invites are recorded but no email is sent).
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
           HOSTING_TARGET=staging; SITE="${STAGING_SITE:-${PROJECT}-staging}" ;;
  prod)    MANIFEST="${ROOT}/bff/cloudrun.yaml"; SERVICE=domotica-bff; DATABASE="(default)"
           HOSTING_TARGET=prod; SITE="${PROJECT}" ;;
  *)       echo "TARGET must be staging or prod" >&2; exit 1 ;;
esac
: "${VPC_NETWORK:?set VPC_NETWORK (the VM is reached through Direct VPC egress)}" "${VPC_SUBNET:?set VPC_SUBNET}"
# the manifest must be the TARGET's: a production published on the staging database (or the reverse) stops here
grep -q "^  name: ${SERVICE}\$" "${MANIFEST}" || { echo "${MANIFEST} is not the service ${SERVICE}" >&2; exit 1; }
grep -A1 "name: FIRESTORE_DATABASE" "${MANIFEST}" | grep -qF "${DATABASE}" \
  || { echo "${MANIFEST} does not use the database ${DATABASE}" >&2; exit 1; }
echo "ambiente ${TARGET}: servizio ${SERVICE}, database ${DATABASE}, sito ${SITE}"

step() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }

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

#!/usr/bin/env bash
# Builds the engine's image of a COMMIT with Cloud Build and pushes it to Artifact Registry (P-60 step 3c). It does not
# touch the VM: installing or updating an apartment's engine there is scripts/engine-vm.sh (procedure in
# docs/motore-vm.md).
#
#   GCP_PROJECT_ID=<project> scripts/deploy-engine.sh             # HEAD
#   GCP_PROJECT_ID=<project> scripts/deploy-engine.sh <commit>    # a given commit (e.g. the one of a lot)
#   DRY_RUN=1 GCP_PROJECT_ID=<project> scripts/deploy-engine.sh <commit>   # says what it would build, no Cloud Build
#
# The commit is exported (git archive, line endings as in the repository) to a temporary folder and the image is built
# from there, so the working copy may hold other work: it is neither read nor required clean. The image is
# <region>-docker.pkg.dev/<project>/<repo>/engine:<the commit's short sha>; the script prints it at the end.
# Optional: GCP_REGION (default europe-west8), ARTIFACT_REPO (default domotica),
#           BUILD_SA (default domotica-build@<project>.iam.gserviceaccount.com): the account Cloud Build runs as (P-21).
# Prerequisites: gcloud authenticated on the project (CLOUDSDK_CORE_ACCOUNT=<owner> in front, if the active account is
#                another one).
set -euo pipefail

PROJECT="${GCP_PROJECT_ID:?set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-europe-west8}"
REPO="${ARTIFACT_REPO:-domotica}"
BUILD_SA="${BUILD_SA:-domotica-build@${PROJECT}.iam.gserviceaccount.com}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REF="${1:-HEAD}"

SHA="$(git -C "${ROOT}" rev-parse --verify --quiet "${REF}^{commit}")" || { echo "commit sconosciuto: ${REF}" >&2; exit 1; }
TAG="$(git -C "${ROOT}" rev-parse --short "${SHA}")"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/engine:${TAG}"
for path in engine/Dockerfile cloudbuild.engine.yaml .gcloudignore; do
  git -C "${ROOT}" cat-file -e "${SHA}:${path}" 2>/dev/null || { echo "il commit ${TAG} non ha ${path}" >&2; exit 1; }
done

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT
git -C "${ROOT}" -c core.autocrlf=false archive "${SHA}" | tar -x -C "${WORK}"
printf '\n\033[1;34m== %s\033[0m\n' "Immagine del motore ${IMAGE} dal commit ${TAG} (copia pulita in ${WORK})"

if [ -n "${DRY_RUN:-}" ]; then
  echo "prova a secco: nessuna chiamata a Cloud Build"
  printf 'Immagine (non costruita): %s\n' "${IMAGE}"
  exit 0
fi
gcloud builds submit "${WORK}" --project "${PROJECT}" --config "${WORK}/cloudbuild.engine.yaml" \
  --substitutions "_IMAGE=${IMAGE}" --ignore-file "${WORK}/.gcloudignore" \
  --service-account "projects/${PROJECT}/serviceAccounts/${BUILD_SA}"

printf '\nImmagine pronta: %s\n' "${IMAGE}"

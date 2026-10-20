#!/usr/bin/env bash
# Builds the engine's image with Cloud Build and pushes it to Artifact Registry (P-60 step 3c). It does not touch the
# VM: installing or updating an apartment's engine there is scripts/engine-vm.sh (procedure in docs/motore-vm.md).
#
#   GCP_PROJECT_ID=<project> scripts/deploy-engine.sh
#
# Optional: GCP_REGION (default europe-west8), ARTIFACT_REPO (default domotica),
#           BUILD_SA (default domotica-build@<project>.iam.gserviceaccount.com): the account Cloud Build runs as (P-21).
# The image is <region>-docker.pkg.dev/<project>/<repo>/engine:<git short sha>; the script prints it at the end.
# Prerequisites: gcloud authenticated on the project (CLOUDSDK_CORE_ACCOUNT=<owner> in front, if the active account is
#                another one), a clean working copy (the tag must say which commit the image is).
set -euo pipefail

PROJECT="${GCP_PROJECT_ID:?set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-europe-west8}"
REPO="${ARTIFACT_REPO:-domotica}"
BUILD_SA="${BUILD_SA:-domotica-build@${PROJECT}.iam.gserviceaccount.com}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -n "$(git -C "${ROOT}" status --porcelain -- engine cloudbuild.engine.yaml)" ]; then
  echo "engine/ has uncommitted changes: commit them first, the image tag is the commit" >&2
  exit 1
fi
TAG="$(git -C "${ROOT}" rev-parse --short HEAD)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/engine:${TAG}"

printf '\n\033[1;34m== %s\033[0m\n' "Build engine image ${IMAGE} (Cloud Build)"
gcloud builds submit "${ROOT}" --project "${PROJECT}" --config "${ROOT}/cloudbuild.engine.yaml" \
  --substitutions "_IMAGE=${IMAGE}" --ignore-file "${ROOT}/.gcloudignore" \
  --service-account "projects/${PROJECT}/serviceAccounts/${BUILD_SA}"

printf '\nImmagine pronta: %s\n' "${IMAGE}"

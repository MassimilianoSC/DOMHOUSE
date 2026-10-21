#!/usr/bin/env bash
# The CI job "contratto-e-mock" (.github/workflows/conformita.yml) on this PC, in Linux: catches before the push what
# fails only there (E-16 DATA_DIR, E-17 a 1 ms race). It exports a commit with `git -c core.autocrlf=false archive`
# (the files exactly as the CI's checkout sees them: tracked only, LF), mounts it in a python:3.11-slim container as a
# non-root user and runs the job's steps: contract hash, dependencies, engine tests, engine start with ci/engine.vars
# and DATA_DIR in a temporary folder, conformance suite, scenario C14 (connector down). Nothing is written outside a
# temporary folder, removed at the end; nothing leaves the machine except the image pull.
#
#   bash scripts/ci-linux.sh            # HEAD (uncommitted changes are NOT tested: commit first)
#   bash scripts/ci-linux.sh <commit>   # any commit
#   bash scripts/ci-linux.sh --help
#
# Needs Docker running (Docker Desktop on Windows; Git Bash or Linux shell). Takes about 3 minutes.
# Output: a "PASSO <name>: ok" or "PASSO <name>: ROSSO" line per step, then "ESITO: <n> rossi su <m> passi".
# Exit code: 0 all green, 1 some step red, 3 Docker or git missing. scripts/run_tests.py runs it as the "linux" suite.
set -uo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi
REF="${1:-HEAD}"
IMAGE="python:3.11-slim"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

command -v git > /dev/null || { echo "PASSO preparazione: ROSSO (git non trovato)"; exit 3; }
command -v docker > /dev/null || { echo "PASSO preparazione: ROSSO (docker non trovato: installa Docker Desktop)"; exit 3; }
docker info > /dev/null 2>&1 || { echo "PASSO preparazione: ROSSO (Docker non risponde: avvia Docker Desktop)"; exit 3; }
SHA="$(git -C "$ROOT" rev-parse --short "$REF" 2>/dev/null)" || { echo "PASSO preparazione: ROSSO (commit $REF sconosciuto)"; exit 3; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
git -C "$ROOT" -c core.autocrlf=false archive "$SHA" | tar -x -C "$WORK" \
  || { echo "PASSO preparazione: ROSSO (git archive di $SHA non riuscito)"; exit 3; }
echo "ci-linux: commit $SHA in $IMAGE (utente non root)"

MOUNT="$WORK"
command -v cygpath > /dev/null && MOUNT="$(cygpath -w "$WORK")"     # Git Bash: Docker Desktop wants C:\...
USER_ID="$(id -u)"; GROUP_ID="$(id -g)"
[[ "$USER_ID" == "0" ]] && { USER_ID=1000; GROUP_ID=1000; }             # never root inside, as on the runner

# The steps of the job, one by one; each prints its PASSO line. The engine is stopped by its PID (no pkill in -slim).
MSYS_NO_PATHCONV=1 docker run -i --rm --user "$USER_ID:$GROUP_ID" -e HOME=/tmp/home -v "$MOUNT:/repo" -w /repo "$IMAGE" \
  bash -s <<'STEPS'
set -u
mkdir -p "$HOME"
RED=0; STEPS=0
step() { STEPS=$((STEPS+1)); if [ "$2" -eq 0 ]; then echo "PASSO $1: ok"; else echo "PASSO $1: ROSSO"; RED=$((RED+1)); fi; }
health() { python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/api/v1/health', timeout=2)" 2>/dev/null; }
finish() { echo "ESITO: $RED rossi su $STEPS passi"; [ "$RED" -eq 0 ]; exit $?; }

SUM="$(sed -n 's/^  CONTRACT_SHA256: *//p' .github/workflows/conformita.yml)"
echo "$SUM  contract/openapi.yaml" | sha256sum -c - ; step contratto $?

python -m venv /tmp/venv && . /tmp/venv/bin/activate \
  && pip install -q --disable-pip-version-check -r bff/requirements.txt -r contract/conformance/requirements.txt
rc=$?; step dipendenze $rc
[ $rc -eq 0 ] || finish

pytest engine -p no:cacheprovider -q 2>&1 | tail -25; step "prove del motore" "${PIPESTATUS[0]}"

TEMP="$(mktemp -d)"
set -a; . ci/engine.vars; set +a
HOST=127.0.0.1 PORT=8100 DATA_DIR="$TEMP/engine-data" python -m engine > /tmp/engine.log 2>&1 &
EPID=$!
for i in $(seq 1 30); do health && break || sleep 1; done
health; rc=$?; step "avvio del motore" $rc
if [ $rc -ne 0 ]; then tail -50 /tmp/engine.log; finish; fi

pytest contract/conformance --base-url http://127.0.0.1:8100/api/v1 --api-key "$API_KEY" -p no:cacheprovider -q 2>&1 \
  | tail -25
rc=${PIPESTATUS[0]}; step "conformità" $rc
[ $rc -eq 0 ] || tail -50 /tmp/engine.log

kill $EPID; wait $EPID 2>/dev/null
sleep 1
HOST=127.0.0.1 PORT=8100 DATA_DIR="$TEMP/engine-data-down" DOMOTICA_TEST_CONNECTOR_DOWN=1 \
  python -m engine > /tmp/engine-down.log 2>&1 &
DPID=$!
sleep 3
pytest contract/conformance --base-url http://127.0.0.1:8100/api/v1 --api-key "$API_KEY" -p no:cacheprovider -q \
  -m connector_down 2>&1 | tail -10
rc=${PIPESTATUS[0]}; step "C14 connector fermo" $rc
[ $rc -eq 0 ] || tail -50 /tmp/engine-down.log
kill $DPID; wait $DPID 2>/dev/null
finish
STEPS

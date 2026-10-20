#!/usr/bin/env bash
# The DOMHOUSE engine on the VM (P-60 step 3c): install, update and check one apartment's engine. It runs ON the VM,
# as root (sudo), with the VM's own identity: no gcloud needed there, only curl, python3 and docker (procedure and the
# commands to launch it from the PC: docs/motore-vm.md).
#
#   sudo bash engine-vm.sh install <apartment_id> <port> <image> [connector]   # first time; connector: simulated
#   sudo bash /opt/domhouse/engine-vm.sh update <apartment_id> <image>          # new image, same data
#   sudo bash /opt/domhouse/engine-vm.sh key <apartment_id>                     # rewrite the key file, restart
#   sudo bash /opt/domhouse/engine-vm.sh status <apartment_id>
#
# install copies this script and compose.yaml (found next to it) to /opt/domhouse, prepares /data/<apartment_id>
# (owner uid 10001, the container's user), writes /etc/domhouse/<apartment_id>.env with API_KEY from the Secret
# Manager secret langbrain-api-key-<apartment_id> and starts the container engine-<apartment_id>.
# The secret's value is read only to write that file (mode 600, root): never printed, logged or counted.
set -euo pipefail
set +x                                   # never trace: a traced line could show the key

OPT=/opt/domhouse
ETC=/etc/domhouse
ENGINE_UID=10001
METADATA=http://metadata.google.internal/computeMetadata/v1
SECRET_PREFIX="${SECRET_PREFIX:-langbrain-api-key-}"

die() { echo "errore: $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || die "lancialo con sudo"
for tool in curl python3 docker; do command -v "$tool" > /dev/null || die "manca $tool sulla VM"; done
docker compose version > /dev/null 2>&1 || die "manca docker compose sulla VM"

valid_id() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$ ]] || die "apartment_id non valido: $1"; }
valid_port() { [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le 65535 ] || die "porta non valida: $1"; }

token() {
  # an access token of the VM's service account (langbrain-vm@), from the metadata server
  curl -sf -H "Metadata-Flavor: Google" "${METADATA}/instance/service-accounts/default/token" |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])'
}

project() { curl -sf -H "Metadata-Flavor: Google" "${METADATA}/project/project-id"; }

write_key() {
  local apt="$1" secret="${SECRET_PREFIX}$1" tok url key
  step "Chiave dal segreto ${secret} -> ${ETC}/${apt}.env (permessi 600)"
  tok="$(token)" || die "token della VM non disponibile"
  url="https://secretmanager.googleapis.com/v1/projects/$(project)/secrets/${secret}/versions/latest:access"
  key="$(curl -sf -H "Authorization: Bearer ${tok}" "${url}" |
         python3 -c 'import base64, json, sys; print(base64.b64decode(json.load(sys.stdin)["payload"]["data"]).decode().strip())')" ||
    die "segreto ${secret} non leggibile dalla VM (esiste? langbrain-vm@ ha Secret Accessor su di lui?)"
  install -d -m 700 -o root -g root "${ETC}"
  (umask 077; printf 'API_KEY=%s\n' "${key}" > "${ETC}/${apt}.env.new")
  mv -f "${ETC}/${apt}.env.new" "${ETC}/${apt}.env"
  chmod 600 "${ETC}/${apt}.env"
  key=""
  echo "scritto ${ETC}/${apt}.env"
}

registry_login() {
  local image="$1" host
  host="${image%%/*}"
  step "Accesso ad Artifact Registry (${host}) con l'identità della VM"
  token | docker login -u oauth2accesstoken --password-stdin "https://${host}" > /dev/null ||
    die "login rifiutato: langbrain-vm@ ha Artifact Registry Reader sul repository?"
  echo "ok"
}

settings_file() { echo "${OPT}/$1.settings"; }

compose() {
  local apt="$1"; shift
  docker compose --env-file "$(settings_file "${apt}")" -f "${OPT}/compose.yaml" "$@"
}

wait_healthy() {
  local apt="$1" port code
  port="$(sed -n 's/^PORT=//p' "$(settings_file "${apt}")")"
  step "Attesa di http://127.0.0.1:${port}/api/v1/health"
  for _ in $(seq 1 30); do
    code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${port}/api/v1/health" || true)"
    if [ "${code}" = "200" ]; then
      curl -s "http://127.0.0.1:${port}/api/v1/health" | python3 -c \
        'import json, sys; h = json.load(sys.stdin); print("health 200:", h["status"], h["implementation"], "connector", h["connector"]["status"])'
      return 0
    fi
    sleep 2
  done
  echo "health non risponde 200 (ultimo codice: ${code:-nessuno}); ultime righe del log:" >&2
  docker logs --tail 20 "engine-${apt}" >&2 || true
  exit 1
}

start() {
  local apt="$1" image="$2"
  registry_login "${image}"
  step "Avvio di engine-${apt} con ${image}"
  compose "${apt}" pull
  compose "${apt}" up -d
  wait_healthy "${apt}"
}

cmd="${1:-}"; shift || true
case "${cmd}" in
  install)
    [ $# -ge 3 ] || die "uso: install <apartment_id> <port> <image> [connector]"
    apt="$1"; port="$2"; image="$3"; connector="${4:-simulated}"
    valid_id "${apt}"; valid_port "${port}"
    here="$(cd "$(dirname "$0")" && pwd)"
    [ -f "${here}/compose.yaml" ] || die "compose.yaml deve stare accanto a questo script"
    step "File del motore in ${OPT}"
    install -d -m 755 "${OPT}"
    [ "${here}" = "${OPT}" ] || install -m 755 "$0" "${OPT}/engine-vm.sh"
    [ "${here}" = "${OPT}" ] || install -m 644 "${here}/compose.yaml" "${OPT}/compose.yaml"
    printf 'APARTMENT_ID=%s\nPORT=%s\nCONNECTOR=%s\nENGINE_IMAGE=%s\n' "${apt}" "${port}" "${connector}" "${image}" \
      > "$(settings_file "${apt}")"
    cat "$(settings_file "${apt}")"
    step "Dati in /data/${apt} (proprietario ${ENGINE_UID})"
    install -d -m 750 -o "${ENGINE_UID}" -g "${ENGINE_UID}" "/data/${apt}"
    ls -ld "/data/${apt}"
    write_key "${apt}"
    start "${apt}" "${image}"
    ;;
  update)
    [ $# -eq 2 ] || die "uso: update <apartment_id> <image>"
    apt="$1"; image="$2"; valid_id "${apt}"
    [ -f "$(settings_file "${apt}")" ] || die "${apt} non è installato (manca $(settings_file "${apt}"))"
    previous="$(sed -n 's/^ENGINE_IMAGE=//p' "$(settings_file "${apt}")")"
    sed -i "s#^ENGINE_IMAGE=.*#ENGINE_IMAGE=${image}#" "$(settings_file "${apt}")"
    echo "immagine: ${previous} -> ${image} (per tornare indietro: update ${apt} ${previous})"
    start "${apt}" "${image}"
    ;;
  key)
    [ $# -eq 1 ] || die "uso: key <apartment_id>"
    apt="$1"; valid_id "${apt}"
    write_key "${apt}"
    compose "${apt}" up -d --force-recreate
    wait_healthy "${apt}"
    ;;
  status)
    [ $# -eq 1 ] || die "uso: status <apartment_id>"
    apt="$1"; valid_id "${apt}"
    cat "$(settings_file "${apt}")"
    docker ps --filter "name=engine-${apt}" --format '{{.Names}}  {{.Image}}  {{.Status}}'
    wait_healthy "${apt}"
    ;;
  *)
    die "uso: install | update | key | status (vedi l'intestazione dello script)"
    ;;
esac

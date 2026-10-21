#!/usr/bin/env bash
# The DOMHOUSE engine on the VM (P-60 step 3c): install, update and check one apartment's engine. It runs ON the VM,
# as root (sudo), with the VM's own identity: no gcloud needed there, only curl, python3 and docker (procedure and the
# commands to launch it from the PC: docs/motore-vm.md).
#
#   sudo bash engine-vm.sh install <apartment_id> <port> <image> [connector]   # first time; connector: simulated
#   sudo bash /opt/domhouse/engine-vm.sh update <apartment_id> <image>          # new image, same data
#   sudo bash /opt/domhouse/engine-vm.sh key <apartment_id>                     # rewrite the key file, restart
#   sudo bash /opt/domhouse/engine-vm.sh status <apartment_id>
#   sudo bash /opt/domhouse/engine-vm.sh backup <apartment_id>                  # a consistent copy of engine.db now
#   sudo bash /opt/domhouse/engine-vm.sh backup-all                             # every apartment (the daily timer)
#   sudo bash /opt/domhouse/engine-vm.sh restore <apartment_id> <file>          # put a copy back, restart
#   sudo bash /opt/domhouse/engine-vm.sh api <apartment_id> <METHOD> <path> [json]  # call the local engine
#   sudo bash /opt/domhouse/engine-vm.sh set <apartment_id> NOME=VALORE          # an engine setting, restart
#   sudo bash /opt/domhouse/engine-vm.sh unset <apartment_id> NOME               # back to its default, restart
#
# Settings (D-131, P-60 step 7d): the engine's own settings of one apartment (e.g. CONFIRM_ON_WATTS) live in
# /etc/domhouse/<apartment_id>.settings.env, no secrets, a second env_file of compose.yaml, optional. set and unset
# change only that file (the key's file is never touched, and "key" never touches this one), recreate the container
# and wait for health 200: if the engine does not come back (a value it refuses stops it), the previous file is put
# back and the container recreated again. status shows the file.
#
# install copies this script and compose.yaml (found next to it) to /opt/domhouse, prepares /data/<apartment_id>
# (owner uid 10001, the container's user), writes /etc/domhouse/<apartment_id>.env with API_KEY from the Secret
# Manager secret langbrain-api-key-<apartment_id>, installs the daily backup timer and starts engine-<apartment_id>.
# The secret's value is read only to write that file (mode 600, root): never printed, logged or counted; "api" reads
# it from that file to send it to the local engine, never shows it.
#
# Backups (D-118): SQLite's online backup API (python3's sqlite3 on the VM, on the file in /data/<apartment_id>: a
# consistent copy also while the engine writes), checked with PRAGMA integrity_check, in
# /data/<apartment_id>/backup/engine-<UTC date>.db, kept BACKUP_DAYS days; every day at 22:30 UTC, before the disk
# snapshot of 23:00, by the systemd timer domhouse-engine-backup.timer.
set -euo pipefail
set +x                                   # never trace: a traced line could show the key

OPT="${DOMHOUSE_OPT:-/opt/domhouse}"     # the two folders can be moved only by the tests
ETC="${DOMHOUSE_ETC:-/etc/domhouse}"
ENGINE_UID=10001
METADATA=http://metadata.google.internal/computeMetadata/v1
SECRET_PREFIX="${SECRET_PREFIX:-langbrain-api-key-}"
BACKUP_DAYS=7
BACKUP_AT="22:30:00 UTC"                 # before the daily snapshot of the disk (23:00 UTC)

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
engine_settings_file() { echo "${ETC}/$1.settings.env"; }

# names set and unset refuse: the key, and what install and update already write
RESERVED="API_KEY APARTMENT_ID CONNECTOR PORT HOST DATA_DIR ENGINE_IMAGE"

valid_setting_name() {
  [[ "$1" =~ ^[A-Z][A-Z0-9_]{0,63}$ ]] || die "nome di impostazione non valido: $1 (lettere maiuscole, cifre, _)"
  [[ " ${RESERVED} " != *" $1 "* ]] || die "$1 non si cambia con set/unset"
}

put_setting() {
  # put_setting <file> <name> [value]: the line NAME=value in the file, or no line for the name without a value
  local file="$1" name="$2" value="${3-}" tmp="$1.new"
  [ -d "$(dirname "${file}")" ] || install -d -m 700 "$(dirname "${file}")"   # made by install; 700 if missing
  touch "${file}"
  grep -v "^${name}=" "${file}" > "${tmp}" || true
  if [ -n "${value}" ]; then
    printf '%s=%s\n' "${name}" "${value}" >> "${tmp}"
  fi
  chmod 644 "${tmp}"
  mv -f "${tmp}" "${file}"
}

change_setting() {
  # change_setting <apartment_id> <name> [value]: the file changed, the container recreated, health 200 or back
  local apt="$1" name="$2" value="${3-}" file previous
  file="$(engine_settings_file "${apt}")"
  [ -f "$(settings_file "${apt}")" ] || die "${apt} non è installato (manca $(settings_file "${apt}"))"
  previous="$(mktemp)"
  if [ -f "${file}" ]; then cp -p "${file}" "${previous}"; fi
  put_setting "${file}" "${name}" "${value}"
  step "Impostazioni di ${apt} (${file})"
  cat "${file}"
  compose "${apt}" up -d --force-recreate
  if ( wait_healthy "${apt}" ); then
    rm -f "${previous}"
    return 0
  fi
  echo "il motore non è tornato su: rimetto le impostazioni di prima" >&2
  if [ -s "${previous}" ]; then cp -p "${previous}" "${file}"; else rm -f "${file}"; fi
  rm -f "${previous}"
  compose "${apt}" up -d --force-recreate
  ( wait_healthy "${apt}" ) || true
  die "impostazione ${name} non applicata"
}

compose() {
  local apt="$1"; shift
  docker compose --env-file "$(settings_file "${apt}")" -f "${OPT}/compose.yaml" "$@"
}

wait_healthy() {
  local apt="$1" port code
  port="$(sed -n 's/^PORT=//p' "$(settings_file "${apt}")")"
  step "Attesa di http://127.0.0.1:${port}/api/v1/health"
  for _ in $(seq 1 "${DOMHOUSE_HEALTH_TRIES:-30}"); do      # 30 tries, 2 s apart (fewer only in the tests)
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

db_of() { echo "/data/$1/engine.db"; }

backup() {
  local apt="$1" dir="/data/$1/backup" day file
  [ -f "$(db_of "${apt}")" ] || die "$(db_of "${apt}") non esiste (motore mai avviato?)"
  install -d -m 750 -o "${ENGINE_UID}" -g "${ENGINE_UID}" "${dir}"
  day="$(date -u +%Y-%m-%d)"
  file="${dir}/engine-${day}.db"
  python3 - "$(db_of "${apt}")" "${file}.tmp" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)                      # SQLite's online backup: consistent even while the engine writes (WAL)
ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
dst.close(); src.close()
sys.exit(0 if ok == "ok" else f"integrity_check: {ok}")
PY
  mv -f "${file}.tmp" "${file}"
  chown "${ENGINE_UID}:${ENGINE_UID}" "${file}"
  chmod 640 "${file}"
  find "${dir}" -maxdepth 1 -name 'engine-*.db' -mtime "+$((BACKUP_DAYS - 1))" -print -delete | sed 's/^/tolto (oltre 7 giorni): /'
  echo "backup ${apt}: ${file} ($(stat -c %s "${file}") byte, integrity_check ok)"
}

install_timer() {
  step "Backup quotidiano (${BACKUP_AT}): domhouse-engine-backup.timer"
  cat > /etc/systemd/system/domhouse-engine-backup.service <<UNIT
[Unit]
Description=DOMHOUSE engine: daily SQLite backup of every apartment (scripts/engine-vm.sh backup-all)

[Service]
Type=oneshot
ExecStart=/bin/bash ${OPT}/engine-vm.sh backup-all
UNIT
  cat > /etc/systemd/system/domhouse-engine-backup.timer <<UNIT
[Unit]
Description=DOMHOUSE engine: daily SQLite backup, before the disk snapshot of 23:00 UTC

[Timer]
OnCalendar=*-*-* ${BACKUP_AT}
Persistent=true

[Install]
WantedBy=timers.target
UNIT
  systemctl daemon-reload
  systemctl enable --now domhouse-engine-backup.timer > /dev/null
  systemctl list-timers domhouse-engine-backup.timer --no-pager | sed -n 1,2p
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
    install -d -m 750 -o "${ENGINE_UID}" -g "${ENGINE_UID}" "/data/${apt}" "/data/${apt}/backup"
    ls -ld "/data/${apt}"
    write_key "${apt}"
    install_timer
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
  backup)
    [ $# -eq 1 ] || die "uso: backup <apartment_id>"
    apt="$1"; valid_id "${apt}"
    backup "${apt}"
    ;;
  backup-all)
    shopt -s nullglob
    failed=0
    for settings in "${OPT}"/*.settings; do
      apt="$(basename "${settings}" .settings)"
      ( backup "${apt}" ) || { echo "backup ${apt} non riuscito" >&2; failed=1; }
    done
    exit "${failed}"
    ;;
  restore)
    [ $# -eq 2 ] || die "uso: restore <apartment_id> <file di backup>"
    apt="$1"; src="$2"; valid_id "${apt}"
    [ -f "$(settings_file "${apt}")" ] || die "${apt} non è installato"
    [ -f "${src}" ] || src="/data/${apt}/backup/${src}"
    [ -f "${src}" ] || die "file di backup non trovato: $2"
    python3 -c 'import sqlite3, sys; c = sqlite3.connect(sys.argv[1]); r = c.execute("PRAGMA integrity_check").fetchone()[0]; sys.exit(0 if r == "ok" else r)' "${src}" ||
      die "il file di backup non è integro"
    step "Ripristino di ${apt} da ${src}"
    compose "${apt}" stop
    db="$(db_of "${apt}")"; keep="/data/${apt}/backup/before-restore-$(date -u +%Y%m%dT%H%M%SZ).db"
    for ext in "" -wal -shm; do
      [ -f "${db}${ext}" ] && mv -f "${db}${ext}" "${keep}${ext}"
    done
    echo "il database di prima resta in ${keep}"
    install -m 640 -o "${ENGINE_UID}" -g "${ENGINE_UID}" "${src}" "${db}"
    compose "${apt}" up -d
    wait_healthy "${apt}"
    ;;
  api)
    [ $# -ge 3 ] || die "uso: api <apartment_id> <METHOD> <path> [json]"
    apt="$1"; method="$2"; path="$3"; body="${4:-}"; valid_id "${apt}"
    port="$(sed -n 's/^PORT=//p' "$(settings_file "${apt}")")"
    # the key goes from the root-only file to curl through a header file in memory: never on a command line or screen
    corr="$(python3 -c 'import uuid; print(uuid.uuid4())')"
    curl -s -w '\nHTTP %{http_code}\n' -X "${method}" -H @<(sed -n 's/^API_KEY=/X-API-Key: /p' "${ETC}/${apt}.env") \
      -H "X-Actor: system:vm-admin" -H "X-Correlation-Id: ${corr}" -H "Content-Type: application/json" \
      ${body:+--data "${body}"} "http://127.0.0.1:${port}/api/v1${path}"
    ;;
  set)
    [ $# -eq 2 ] && [[ "$2" == *=* ]] || die "uso: set <apartment_id> NOME=VALORE"
    apt="$1"; name="${2%%=*}"; value="${2#*=}"; valid_id "${apt}"; valid_setting_name "${name}"
    [[ "${value}" =~ ^[A-Za-z0-9._:/-]{1,128}$ ]] || die "valore non valido per ${name}: lettere, cifre e . _ : / -"
    change_setting "${apt}" "${name}" "${value}"
    ;;
  unset)
    [ $# -eq 2 ] || die "uso: unset <apartment_id> NOME"
    apt="$1"; name="$2"; valid_id "${apt}"; valid_setting_name "${name}"
    change_setting "${apt}" "${name}"
    ;;
  status)
    [ $# -eq 1 ] || die "uso: status <apartment_id>"
    apt="$1"; valid_id "${apt}"
    cat "$(settings_file "${apt}")"
    if [ -s "$(engine_settings_file "${apt}")" ]; then
      echo "impostazioni del motore ($(engine_settings_file "${apt}")):"
      cat "$(engine_settings_file "${apt}")"
    else
      echo "impostazioni del motore: tutte ai valori predefiniti"
    fi
    docker ps --filter "name=engine-${apt}" --format '{{.Names}}  {{.Image}}  {{.Status}}'
    wait_healthy "${apt}"
    ;;
  *)
    die "uso: install | update | key | set | unset | status | backup | backup-all | restore | api (vedi l'intestazione)"
    ;;
esac

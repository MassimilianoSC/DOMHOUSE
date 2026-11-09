#!/usr/bin/env bash
# The MQTT broker of the devices on the VM (D-196, D-199). It runs ON the VM, as root (sudo), with the VM's own
# identity, like engine-vm.sh: no gcloud there, only python3, openssl and docker. Procedure: docs/motore-vm.md.
#
#   sudo bash broker-vm.sh install <image> [tls_dir]                   # first time; needs the certificate
#   sudo bash /opt/domhouse/broker-vm.sh update <image>                # new image, same data
#   sudo bash /opt/domhouse/broker-vm.sh status
#   sudo bash /opt/domhouse/broker-vm.sh restart                       # everyone reconnects: reload is enough, usually
#   sudo bash /opt/domhouse/broker-vm.sh reload                        # SIGHUP: certificate, users and permissions
#   sudo bash /opt/domhouse/broker-vm.sh install-cert <fullchain> <privkey>   # checks them, puts them in place, reload
#   sudo bash /opt/domhouse/broker-vm.sh add-apartment <apartment_id>  # its accounts from Secret Manager
#   sudo bash /opt/domhouse/broker-vm.sh remove-apartment <apartment_id>
#   sudo bash /opt/domhouse/broker-vm.sh sync                          # rereads the secrets of every apartment
#   sudo bash /opt/domhouse/broker-vm.sh check                         # one line for the 5-minute watch
#
# Folders: /opt/domhouse/_broker (compose, configuration, settings), /etc/domhouse/_broker (tls, auth, the list of
# apartments), /data/_broker (the broker's persistence). The underscore on purpose: an apartment_id cannot start
# with it (engine-vm.sh valid_id), so these can never be taken for an apartment, nor can "broker" be one that clashes.
#
# Secrets: broker_accounts.py reads them with the VM's identity (langbrain-vm@, Secret Accessor) and writes only hashes.
# Nothing here prints a password; adding them to Secret Manager is broker-secrets.sh, on the PC.
#
# Certificate: fullchain.pem and privkey.pem in the TLS folder, owner 1883. install-cert is the way to replace them: a
# broken pair is refused before it touches the live files, because the broker cannot start without a valid one.
#
# Watch: check writes "broker ok cert_days=<n> ..." or "broker down (...)" and "broker cert expiring days=<n>" (under
# CERT_ALERT_DAYS) with the syslog tag domhouse-check; engine-vm.sh check-all calls it when the broker is installed.
set -euo pipefail
set +x                                   # never trace

OPT="${DOMHOUSE_OPT:-/opt/domhouse}"     # these folders can be moved only by the tests
ETC="${DOMHOUSE_ETC:-/etc/domhouse}"
DATA="${DOMHOUSE_DATA:-/data}"
BROKER_OPT="${OPT}/_broker"
BROKER_ETC="${ETC}/_broker"
BROKER_DATA="${DATA}/_broker"
SETTINGS="${BROKER_OPT}/broker.settings"
APARTMENTS="${BROKER_ETC}/apartments"
AUTH="${BROKER_ETC}/auth"
CONTAINER=domhouse-broker
BROKER_UID=1883
CERT_ALERT_DAYS=14                       # a 45-day certificate is renewed with 15 days left: one failed day is enough
ACCOUNTS="${OPT}/broker_accounts.py"

die() { echo "errore: $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || die "lancialo con sudo"
for tool in python3 openssl docker; do command -v "$tool" > /dev/null || die "manca $tool sulla VM"; done
docker compose version > /dev/null 2>&1 || die "manca docker compose sulla VM"

valid_id() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$ ]] || die "apartment_id non valido: $1"; }
installed() { [ -f "${SETTINGS}" ]; }
need_installed() { installed || die "il broker non è installato (manca ${SETTINGS})"; }
setting() { sed -n "s/^$1=//p" "${SETTINGS}"; }
tls_dir() { setting BROKER_TLS_DIR; }
tls_port() { setting BROKER_TLS_PORT; }
compose() { docker compose --env-file "${SETTINGS}" -f "${BROKER_OPT}/compose.yaml" "$@"; }
hup() { docker kill -s HUP "${CONTAINER}" > /dev/null; }

cert_problem() {
  # cert_problem <fullchain> <privkey>: prints what is wrong with the pair; nothing when it can be served
  local cert="$1" key="$2" a b
  [ -s "${cert}" ] || { echo "manca ${cert}"; return; }
  [ -s "${key}" ] || { echo "manca ${key}"; return; }
  openssl x509 -in "${cert}" -noout 2>/dev/null || { echo "${cert} non è un certificato valido"; return; }
  openssl x509 -in "${cert}" -noout -checkend 0 > /dev/null 2>&1 || { echo "${cert} è scaduto"; return; }
  a="$(openssl x509 -in "${cert}" -noout -pubkey 2>/dev/null | openssl sha256)" || true
  b="$(openssl pkey -in "${key}" -pubout 2>/dev/null | openssl sha256)" || true
  [ -n "${a}" ] && [ "${a}" = "${b}" ] || echo "la chiave ${key} non corrisponde al certificato"
}

fingerprint_of_stdin() { openssl x509 -noout -fingerprint -sha256 | sed 's/.*=//'; }

served_pem() { python3 "${ACCOUNTS}" probe 127.0.0.1 "$(tls_port)"; }

wait_healthy() {
  local state=""
  step "Attesa del broker"
  for _ in $(seq 1 "${DOMHOUSE_HEALTH_TRIES:-30}"); do
    state="$(docker inspect -f '{{.State.Health.Status}}' "${CONTAINER}" 2>/dev/null || true)"
    if [ "${state}" = "healthy" ] && served_pem > /dev/null 2>&1; then
      echo "broker sano: ${state}, porta TLS $(tls_port) risponde"
      return 0
    fi
    sleep 2
  done
  echo "il broker non è sano (stato: ${state:-nessuno}); ultime righe del log:" >&2
  docker logs --tail 20 "${CONTAINER}" >&2 || true
  exit 1
}

reload_broker() {
  # the certificate on disk is checked first; afterwards what the port serves must be that certificate
  local problem wanted served=""
  problem="$(cert_problem "$(tls_dir)/fullchain.pem" "$(tls_dir)/privkey.pem")"
  [ -z "${problem}" ] || die "ricarica non fatta: ${problem}"
  hup
  wanted="$(fingerprint_of_stdin < "$(tls_dir)/fullchain.pem")"
  for _ in $(seq 1 10); do
    served="$(served_pem 2>/dev/null | fingerprint_of_stdin 2>/dev/null || true)"
    if [ "${served}" = "${wanted}" ]; then
      echo "ricarica fatta: la porta $(tls_port) serve il certificato ${wanted}"
      return 0
    fi
    sleep 1
  done
  die "dopo la ricarica la porta non serve il certificato sul disco (servito: ${served:-nessuno})"
}

sync_accounts() {
  # the list of apartments may have just been changed by the caller: the broker reloads only if a file changed
  local out
  out="$(python3 "${ACCOUNTS}" sync "${APARTMENTS}" "${AUTH}")" || return 1   # a return: add-apartment must undo its line
  printf '%s\n' "${out}"
  if [ "$(printf '%s\n' "${out}" | tail -1)" = "changed" ] && [ "$(docker inspect -f '{{.State.Running}}' "${CONTAINER}" 2>/dev/null || true)" = "true" ]; then
    hup
    echo "utenti e permessi ricaricati"
  fi
}

put_files() {
  local here="$1"
  for file in compose.yaml mosquitto.conf broker_accounts.py compose.broker.yaml; do
    [ -f "${here}/${file}" ] || die "${file} deve stare accanto a questo script"
  done
  install -d -m 755 "${OPT}" "${BROKER_OPT}"
  [ "${here}" = "${OPT}" ] || install -m 755 "$0" "${OPT}/broker-vm.sh"
  install -m 644 "${here}/broker_accounts.py" "${OPT}/broker_accounts.py"
  install -m 644 "${here}/compose.broker.yaml" "${OPT}/compose.broker.yaml"
  install -m 644 "${here}/compose.yaml" "${BROKER_OPT}/compose.yaml"
  install -m 644 "${here}/mosquitto.conf" "${BROKER_OPT}/mosquitto.conf"
  # copied from a Windows PC they may carry \r line ends, which the broker would read as part of each value
  sed -i 's/\r$//' "${OPT}/broker_accounts.py" "${OPT}/compose.broker.yaml" "${BROKER_OPT}/compose.yaml" "${BROKER_OPT}/mosquitto.conf"
}

fix_tls_owner() {
  # the broker runs as 1883 and must read them; the key stays closed to everybody else
  chown "${BROKER_UID}:${BROKER_UID}" "$1" "$1/fullchain.pem" "$1/privkey.pem"
  chmod 750 "$1"
  chmod 644 "$1/fullchain.pem"
  chmod 640 "$1/privkey.pem"
}

check() {
  local state pem days
  state="$(docker inspect -f '{{.State.Health.Status}}' "${CONTAINER}" 2>/dev/null || echo assente)"
  pem="$(served_pem 2>/dev/null || true)"
  if [ "${state}" != "healthy" ] || [ -z "${pem}" ]; then
    watch_line "broker down (container: ${state}, porta TLS: $([ -n "${pem}" ] && echo risponde || echo muta))"
    return 0
  fi
  days=$(( ( $(date -d "$(printf '%s\n' "${pem}" | openssl x509 -noout -enddate | sed 's/^notAfter=//')" +%s) - $(date +%s) ) / 86400 ))
  watch_line "broker ok cert_days=${days}"
  if [ "${days}" -lt "${CERT_ALERT_DAYS}" ]; then watch_line "broker cert expiring days=${days}"; fi
}

watch_line() {
  logger -t domhouse-check "$*" 2>/dev/null || true
  echo "$*"
}

cmd="${1:-}"; shift || true
case "${cmd}" in
  install)
    [ $# -ge 1 ] && [ $# -le 2 ] || die "uso: install <image> [tls_dir]"
    image="$1"; tls="${2:-${BROKER_ETC}/tls}"
    here="$(cd "$(dirname "$0")" && pwd)"
    [ -d "${tls}" ] || die "manca la cartella del certificato ${tls}"
    problem="$(cert_problem "${tls}/fullchain.pem" "${tls}/privkey.pem")"
    [ -z "${problem}" ] || die "certificato: ${problem}"
    step "File del broker in ${OPT}"
    put_files "${here}"
    printf 'BROKER_IMAGE=%s\nBROKER_TLS_PORT=%s\nBROKER_TLS_DIR=%s\nBROKER_AUTH_DIR=%s\nBROKER_DATA_DIR=%s\n' \
      "${image}" "${DOMHOUSE_BROKER_PORT:-8883}" "${tls}" "${AUTH}" "${BROKER_DATA}" > "${SETTINGS}"
    cat "${SETTINGS}"
    step "Cartelle"
    install -d -m 700 "${ETC}"
    install -d -m 750 "${BROKER_ETC}"
    install -d -m 750 -o "${BROKER_UID}" -g "${BROKER_UID}" "${AUTH}" "${BROKER_DATA}"
    fix_tls_owner "${tls}"
    [ -f "${APARTMENTS}" ] || : > "${APARTMENTS}"
    step "Utenti e permessi"
    sync_accounts
    step "Avvio di ${CONTAINER} con ${image}"
    compose pull --quiet
    compose up -d
    wait_healthy
    ;;
  update)
    [ $# -eq 1 ] || die "uso: update <image>"
    need_installed
    image="$1"; previous="$(setting BROKER_IMAGE)"
    sed -i "s#^BROKER_IMAGE=.*#BROKER_IMAGE=${image}#" "${SETTINGS}"
    echo "immagine: ${previous} -> ${image} (per tornare indietro: update ${previous})"
    compose pull --quiet
    compose up -d
    wait_healthy
    ;;
  restart)
    need_installed
    compose restart
    wait_healthy
    ;;
  reload)
    need_installed
    reload_broker
    ;;
  install-cert)
    [ $# -eq 2 ] || die "uso: install-cert <fullchain> <privkey>"
    need_installed
    problem="$(cert_problem "$1" "$2")"
    [ -z "${problem}" ] || die "certificato rifiutato, resta quello di prima: ${problem}"
    tls="$(tls_dir)"
    install -m 640 -o "${BROKER_UID}" -g "${BROKER_UID}" "$2" "${tls}/privkey.pem.new"
    install -m 644 -o "${BROKER_UID}" -g "${BROKER_UID}" "$1" "${tls}/fullchain.pem.new"
    mv -f "${tls}/privkey.pem.new" "${tls}/privkey.pem"
    mv -f "${tls}/fullchain.pem.new" "${tls}/fullchain.pem"
    reload_broker
    ;;
  add-apartment)
    [ $# -eq 1 ] || die "uso: add-apartment <apartment_id>"
    need_installed
    valid_id "$1"
    if grep -qx "$1" "${APARTMENTS}"; then echo "$1 è già nell'elenco"; else printf '%s\n' "$1" >> "${APARTMENTS}"; fi
    sync_accounts || { grep -vx "$1" "${APARTMENTS}" > "${APARTMENTS}.new" || true; mv -f "${APARTMENTS}.new" "${APARTMENTS}"; exit 1; }
    ;;
  remove-apartment)
    [ $# -eq 1 ] || die "uso: remove-apartment <apartment_id>"
    need_installed
    valid_id "$1"
    grep -qx "$1" "${APARTMENTS}" || die "$1 non è nell'elenco"
    grep -vx "$1" "${APARTMENTS}" > "${APARTMENTS}.new" || true
    mv -f "${APARTMENTS}.new" "${APARTMENTS}"
    sync_accounts
    ;;
  sync)
    need_installed
    sync_accounts
    ;;
  check)
    need_installed
    check
    ;;
  status)
    need_installed
    cat "${SETTINGS}"
    docker ps --filter "name=^${CONTAINER}$" --format '{{.Names}}  {{.Image}}  {{.Status}}'
    docker stats --no-stream --format 'memoria {{.MemUsage}}  cpu {{.CPUPerc}}' "${CONTAINER}"
    echo "connessioni sulla porta TLS: $(docker exec "${CONTAINER}" cat /proc/net/tcp /proc/net/tcp6 2>/dev/null | awk '$2 ~ /:22B3$/ && $4 == "01"' | wc -l)"
    echo "appartamenti: $(wc -l < "${APARTMENTS}")"
    for file in devices connectors; do echo "utenti ${file}: $(wc -l < "${AUTH}/${file}.passwd")"; done
    check
    ;;
  *)
    die "uso: install | update | restart | reload | install-cert | add-apartment | remove-apartment | sync | check | status (vedi l'intestazione)"
    ;;
esac

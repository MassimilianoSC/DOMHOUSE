#!/usr/bin/env bash
# The MQTT broker of the devices on the VM (D-196, D-199). It runs ON the VM, as root (sudo), with the VM's own
# identity, like engine-vm.sh: no gcloud there, only python3, openssl and docker. Procedure: docs/motore-vm.md, G2.
#
#   sudo bash broker-vm.sh prepare-tls-disk                            # once: the keys' disk (C-12); safe to repeat
#   sudo bash broker-vm.sh cert-new <domain> <dns_zone> <dns_account>  # the first certificate, from Let's Encrypt
#   sudo bash broker-vm.sh install <image>                             # first time; needs the certificate
#   sudo bash /opt/domhouse/broker-vm.sh update <image>                # new image, same data
#   sudo bash /opt/domhouse/broker-vm.sh status
#   sudo bash /opt/domhouse/broker-vm.sh restart                       # everyone reconnects: reload is enough, usually
#   sudo bash /opt/domhouse/broker-vm.sh reload                        # SIGHUP: certificate, users and permissions
#   sudo bash /opt/domhouse/broker-vm.sh cert-renew                    # the daily timer: renews only when due
#   sudo bash /opt/domhouse/broker-vm.sh cert-revoke <key-compromise|superseded>   # revokes, then a new key and certificate
#   sudo bash /opt/domhouse/broker-vm.sh install-cert <fullchain> <privkey>   # a certificate from elsewhere; checks it first
#   sudo bash /opt/domhouse/broker-vm.sh add-apartment <apartment_id>  # its accounts from Secret Manager
#   sudo bash /opt/domhouse/broker-vm.sh remove-apartment <apartment_id>
#   sudo bash /opt/domhouse/broker-vm.sh sync                          # rereads the secrets of every apartment
#   sudo bash /opt/domhouse/broker-vm.sh check                         # one line for the 5-minute watch
#
# Folders: /opt/domhouse/_broker (compose, configuration, settings), /etc/domhouse/_broker (auth, the list of
# apartments, acme.settings), /data/_broker (the broker's persistence). The underscore on purpose: an apartment_id
# cannot start with it (engine-vm.sh valid_id), so these can never be taken for an apartment.
#
# Keys (C-12, D-207, D-208): the certificate's private key and the ACME account key live only on the disk attached as
# domhouse-tls (/dev/disk/by-id/google-domhouse-tls), which has no snapshot, mounted on /mnt/domhouse-tls: broker/ for
# what the broker serves, acme/ for lego. Owner 1883 (the broker's user), files 600, folders 700. No Google Cloud
# credential on the VM: lego uses the VM's identity to act as the DNS account. When that disk is not mounted nothing
# here writes a key, the broker does not start (its folder is missing and docker is told never to create it, the
# empty mount point is immutable) and check reports "broker down".
#
# Secrets: broker_accounts.py reads them with the VM's identity (langbrain-vm@, Secret Accessor) and writes only hashes.
# Nothing here prints a password; adding them to Secret Manager is broker-secrets.sh, on the PC.
#
# Watch: check writes "broker ok cert_days=<n> ..." or "broker down (...)" and "broker cert expiring days=<n>" (under
# CERT_ALERT_DAYS) with the syslog tag domhouse-check; engine-vm.sh check-all calls it when the broker is installed.
set -euo pipefail
set +x                                   # never trace

OPT="${DOMHOUSE_OPT:-/opt/domhouse}"     # these folders can be moved only by the tests
ETC="${DOMHOUSE_ETC:-/etc/domhouse}"
DATA="${DOMHOUSE_DATA:-/data}"
SYSTEMD="${DOMHOUSE_SYSTEMD:-/etc/systemd/system}"
TLS_DEVICE="${DOMHOUSE_TLS_DEVICE:-/dev/disk/by-id/google-domhouse-tls}"
TLS_MOUNT="${DOMHOUSE_TLS_MOUNT:-/mnt/domhouse-tls}"
BROKER_OPT="${OPT}/_broker"
BROKER_ETC="${ETC}/_broker"
BROKER_DATA="${DATA}/_broker"
SETTINGS="${BROKER_OPT}/broker.settings"
ACME_SETTINGS="${BROKER_ETC}/acme.settings"
APARTMENTS="${BROKER_ETC}/apartments"
AUTH="${BROKER_ETC}/auth"
TLS_DIR="${TLS_MOUNT}/broker"
ACME_DIR="${TLS_MOUNT}/acme"
# nofail: a missing disk must not stop the VM from booting (the broker alone stays down); before docker, so that at
# boot the broker finds its folder
TLS_MOUNT_OPTIONS="defaults,nofail,nodev,nosuid,noexec,x-systemd.device-timeout=30s,x-systemd.before=docker.service"
CONTAINER=domhouse-broker
BROKER_UID=1883
CERT_ALERT_DAYS=14                       # a 45-day certificate is renewed with 15 days left: one failed day is enough
ACCOUNTS="${OPT}/broker_accounts.py"
LEGO_IMAGE="goacme/lego:v5.6.0@sha256:6f1583fc026a455ea46a7a5858c576105bb69c2e2de69db391cab7f14750350c"
LETS_ENCRYPT="https://acme-v02.api.letsencrypt.org/directory"
ACME_ACCOUNT_ID=domhouse-broker          # no email: Let's Encrypt sends none, and no address leaves the VM

die() { echo "errore: $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || die "lancialo con sudo"
for tool in python3 openssl docker; do command -v "$tool" > /dev/null || die "manca $tool sulla VM"; done
docker compose version > /dev/null 2>&1 || die "manca docker compose sulla VM"

valid_id() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$ ]] || die "apartment_id non valido: $1"; }
installed() { [ -f "${SETTINGS}" ]; }
need_installed() { installed || die "il broker non è installato (manca ${SETTINGS})"; }
setting() { sed -n "s/^$1=//p" "${SETTINGS}"; }
acme_setting() { sed -n "s/^$1=//p" "${ACME_SETTINGS}"; }
tls_port() { setting BROKER_TLS_PORT; }
compose() { docker compose --env-file "${SETTINGS}" -f "${BROKER_OPT}/compose.yaml" "$@"; }
hup() { docker kill -s HUP "${CONTAINER}" > /dev/null; }

watch_line() {
  logger -t domhouse-check "$*" 2>/dev/null || true
  echo "$*"
}

tls_disk_problem() {
  # prints why the keys' disk cannot be used; nothing when it can
  mountpoint -q "${TLS_MOUNT}" 2>/dev/null || { echo "disco delle chiavi non montato su ${TLS_MOUNT}"; return; }
  [ -d "${TLS_DIR}" ] && [ -d "${ACME_DIR}" ] || echo "disco delle chiavi senza le cartelle broker e acme"
}

need_tls_disk() {
  local problem
  problem="$(tls_disk_problem)"
  [ -z "${problem}" ] && return 0
  logger -t domhouse-broker "fermo: ${problem}; le chiavi non vanno mai sul disco di avvio" 2>/dev/null || true
  die "${problem}: le chiavi stanno solo su quel disco (prepare-tls-disk, docs/motore-vm.md G2)"
}

secure_keys() {
  # C-12: the certificate's key and the ACME account key are readable only by the broker's user
  chown -R "${BROKER_UID}:${BROKER_UID}" "${TLS_DIR}" "${ACME_DIR}"
  find "${TLS_DIR}" "${ACME_DIR}" -type d -exec chmod 700 {} +
  find "${TLS_DIR}" "${ACME_DIR}" -type f -exec chmod 600 {} +
}

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
  problem="$(cert_problem "${TLS_DIR}/fullchain.pem" "${TLS_DIR}/privkey.pem")"
  [ -z "${problem}" ] || die "ricarica non fatta: ${problem}"
  hup
  wanted="$(fingerprint_of_stdin < "${TLS_DIR}/fullchain.pem")"
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

put_cert() {
  # put_cert <fullchain> <privkey>: a broken pair is refused before it touches the live files
  local problem
  problem="$(cert_problem "$1" "$2")"
  [ -z "${problem}" ] || die "certificato rifiutato, resta quello di prima: ${problem}"
  install -m 600 -o "${BROKER_UID}" -g "${BROKER_UID}" "$2" "${TLS_DIR}/privkey.pem.new"
  install -m 600 -o "${BROKER_UID}" -g "${BROKER_UID}" "$1" "${TLS_DIR}/fullchain.pem.new"
  mv -f "${TLS_DIR}/privkey.pem.new" "${TLS_DIR}/privkey.pem"
  mv -f "${TLS_DIR}/fullchain.pem.new" "${TLS_DIR}/fullchain.pem"
}

cert_in_place() {
  # the certificate in the broker's folder is live: reload when the broker is there, otherwise say what comes next
  if installed; then reload_broker; else echo "certificato pronto in ${TLS_DIR}: ora install"; fi
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

prepare_tls_disk() {
  # formats the disk only when it is empty, mounts it, writes its fstab line once; each step is skipped when done
  local dev fstype uuid line current source
  for tool in blkid mkfs.ext4 mountpoint findmnt chattr mount cmp; do command -v "$tool" > /dev/null || die "manca $tool sulla VM"; done
  [ -e "${TLS_DEVICE}" ] || die "manca il disco ${TLS_DEVICE}: va creato e collegato alla VM con --device-name=domhouse-tls"
  dev="$(readlink -f "${TLS_DEVICE}")"
  [ -b "${dev}" ] || die "${TLS_DEVICE} non è un disco (${dev})"
  if mountpoint -q "${TLS_MOUNT}"; then
    source="$(readlink -f "$(findmnt -n -o SOURCE --mountpoint "${TLS_MOUNT}")")"
    [ "${source}" = "${dev}" ] || die "su ${TLS_MOUNT} è montato ${source}, non ${dev}: non tocco niente"
  fi
  fstype="$(blkid -p -o value -s TYPE "${dev}" 2>/dev/null || true)"
  if [ -z "${fstype}" ]; then
    if [ -n "$(blkid -p -o value -s PTTYPE "${dev}" 2>/dev/null || true)" ] || ! cmp -s -n 1048576 "${dev}" /dev/zero; then
      die "${dev} non ha un file system ma non è vuoto: non lo formatto"
    fi
    step "Formattazione di ${dev} (era vuoto)"
    mkfs.ext4 -q -m 0 -L domhouse-tls "${dev}"
    fstype=ext4
  fi
  [ "${fstype}" = "ext4" ] || die "${dev} ha già un file system ${fstype}: non lo tocco"
  uuid="$(blkid -p -o value -s UUID "${dev}")"
  [ -n "${uuid}" ] || die "${dev}: UUID non leggibile"

  step "Montaggio automatico all'avvio (/etc/fstab)"
  line="UUID=${uuid} ${TLS_MOUNT} ext4 ${TLS_MOUNT_OPTIONS} 0 2"
  current="$(awk -v m="${TLS_MOUNT}" '$1 !~ /^#/ && $2 == m' /etc/fstab)"
  if [ -z "${current}" ]; then
    [ -f /etc/fstab.before-domhouse-tls ] || cp -p /etc/fstab /etc/fstab.before-domhouse-tls
    printf '%s\n' "${line}" >> /etc/fstab
    echo "aggiunta: ${line}"
  elif [ "${current}" = "${line}" ]; then
    echo "già presente: ${line}"
  else
    die "/etc/fstab ha già una riga per ${TLS_MOUNT} diversa da quella attesa: ${current}"
  fi

  if ! mountpoint -q "${TLS_MOUNT}"; then
    step "Montaggio su ${TLS_MOUNT}"
    install -d -m 755 "${TLS_MOUNT}"
    [ -z "$(ls -A "${TLS_MOUNT}")" ] || die "${TLS_MOUNT} sul disco di avvio non è vuota: controlla che non ci siano chiavi, poi svuotala"
    chattr +i "${TLS_MOUNT}"           # while unmounted nothing can be written there: no key ever lands on the boot disk
    if command -v systemctl > /dev/null; then systemctl daemon-reload; fi
    mount "${TLS_MOUNT}"               # through the fstab line: if it is wrong, it fails now and not at the next boot
  fi
  mountpoint -q "${TLS_MOUNT}" || die "${TLS_MOUNT} non risulta montato"
  chmod 755 "${TLS_MOUNT}"
  install -d -m 700 -o "${BROKER_UID}" -g "${BROKER_UID}" "${TLS_DIR}" "${ACME_DIR}"
  secure_keys
  echo "disco delle chiavi pronto: ${dev} UUID=${uuid} su ${TLS_MOUNT}, cartelle broker e acme (utente ${BROKER_UID}, 700)"
}

lego() {
  # lego in its container as the broker's user: it reads and writes only the ACME folder on the keys' disk
  local network="${DOMHOUSE_LEGO_NETWORK:-bridge}" test_args=() env_args=()
  [ -z "${DOMHOUSE_ACME_TEST:-}" ] || test_args=(--tls-skip-verify)    # tests only: a local Pebble
  [ "$1" != "run" ] || env_args=(-e "GCE_IMPERSONATE_SERVICE_ACCOUNT=$(acme_setting ACME_DNS_ACCOUNT)" -e "GCE_ZONE_ID=$(acme_setting ACME_DNS_ZONE)")
  [ -z "${DOMHOUSE_ACME_TEST:-}" ] || env_args=(-e EXEC_PATH=/bin/true)
  docker run --rm --user "${BROKER_UID}:${BROKER_UID}" --read-only --tmpfs /tmp --cap-drop ALL \
    --security-opt no-new-privileges:true --network "${network}" -v "${ACME_DIR}:/acme" "${env_args[@]}" "${LEGO_IMAGE}" \
    "$@" --path /acme --server "$(acme_setting ACME_SERVER)" --account-id "${ACME_ACCOUNT_ID}" --log.format text "${test_args[@]}"
}

acme_get() {
  # gets the certificate when it is missing or due; puts it in the broker's folder only when it is a new one
  local domain crt key dns_args=(--dns gcloud)
  domain="$(acme_setting ACME_DOMAIN)"
  [ -z "${DOMHOUSE_ACME_TEST:-}" ] || dns_args=(--dns exec --dns.propagation.wait 1s)   # Pebble accepts every challenge
  crt="${ACME_DIR}/certificates/${domain}.crt"; key="${ACME_DIR}/certificates/${domain}.key"
  if ! lego run --accept-tos -d "${domain}" --no-random-sleep "${dns_args[@]}"; then
    secure_keys
    watch_line "broker cert renew failed (${domain})"
    exit 1
  fi
  secure_keys
  if [ -f "${TLS_DIR}/fullchain.pem" ] && cmp -s "${crt}" "${TLS_DIR}/fullchain.pem"; then
    echo "certificato invariato: rinnovo non ancora dovuto"
    return 0
  fi
  put_cert "${crt}" "${key}"
  watch_line "broker cert new $(openssl x509 -in "${crt}" -noout -enddate)"
  cert_in_place
}

install_cert_timer() {
  step "Rinnovo quotidiano del certificato: domhouse-broker-cert.timer"
  cat > "${SYSTEMD}/domhouse-broker-cert.service" <<UNIT
[Unit]
Description=DOMHOUSE broker: renews the TLS certificate when due (broker-vm.sh cert-renew)
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash ${OPT}/broker-vm.sh cert-renew
UNIT
  cat > "${SYSTEMD}/domhouse-broker-cert.timer" <<UNIT
[Unit]
Description=DOMHOUSE broker: daily certificate renewal; a failure shows in the watch as days run out

[Timer]
OnCalendar=*-*-* 04:17:00
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
UNIT
  systemctl daemon-reload
  systemctl enable --now domhouse-broker-cert.timer > /dev/null
  echo "timer domhouse-broker-cert.timer attivo"
}

check() {
  local state pem days problem
  problem="$(tls_disk_problem)"
  if [ -n "${problem}" ]; then
    watch_line "broker down (${problem})"
    return 0
  fi
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

cmd="${1:-}"; shift || true
case "${cmd}" in
  prepare-tls-disk)
    [ $# -eq 0 ] || die "uso: prepare-tls-disk"
    prepare_tls_disk
    ;;
  install)
    [ $# -eq 1 ] || die "uso: install <image> (il certificato viene da cert-new o install-cert)"
    image="$1"
    here="$(cd "$(dirname "$0")" && pwd)"
    need_tls_disk
    problem="$(cert_problem "${TLS_DIR}/fullchain.pem" "${TLS_DIR}/privkey.pem")"
    [ -z "${problem}" ] || die "certificato: ${problem} (prima cert-new o install-cert)"
    step "File del broker in ${OPT}"
    put_files "${here}"
    printf 'BROKER_IMAGE=%s\nBROKER_TLS_PORT=%s\nBROKER_TLS_DIR=%s\nBROKER_AUTH_DIR=%s\nBROKER_DATA_DIR=%s\n' \
      "${image}" "${DOMHOUSE_BROKER_PORT:-8883}" "${TLS_DIR}" "${AUTH}" "${BROKER_DATA}" > "${SETTINGS}"
    cat "${SETTINGS}"
    step "Cartelle"
    install -d -m 700 "${ETC}"
    install -d -m 750 "${BROKER_ETC}"
    install -d -m 750 -o "${BROKER_UID}" -g "${BROKER_UID}" "${AUTH}" "${BROKER_DATA}"
    secure_keys
    [ -f "${APARTMENTS}" ] || : > "${APARTMENTS}"
    step "Utenti e permessi"
    sync_accounts
    install_cert_timer
    step "Avvio di ${CONTAINER} con ${image}"
    compose pull --quiet
    compose up -d
    wait_healthy
    ;;
  update)
    [ $# -eq 1 ] || die "uso: update <image>"
    need_installed
    need_tls_disk
    image="$1"; previous="$(setting BROKER_IMAGE)"
    sed -i "s#^BROKER_IMAGE=.*#BROKER_IMAGE=${image}#" "${SETTINGS}"
    echo "immagine: ${previous} -> ${image} (per tornare indietro: update ${previous})"
    compose pull --quiet
    compose up -d
    wait_healthy
    ;;
  restart)
    need_installed
    need_tls_disk
    compose restart
    wait_healthy
    ;;
  reload)
    need_installed
    need_tls_disk
    reload_broker
    ;;
  install-cert)
    [ $# -eq 2 ] || die "uso: install-cert <fullchain> <privkey>"
    need_tls_disk
    put_cert "$1" "$2"
    cert_in_place
    ;;
  cert-new)
    [ $# -eq 3 ] || die "uso: cert-new <domain> <dns_zone> <dns_account>"
    [[ "$1" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$ ]] || die "nome non valido: $1"
    [[ "$2" =~ ^[a-z][a-z0-9-]{0,62}$ ]] || die "zona Cloud DNS non valida: $2"
    [[ "$3" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z0-9-]+\.iam\.gserviceaccount\.com$ ]] || die "account DNS non valido: $3"
    need_tls_disk
    install -d -m 700 "${ETC}"
    install -d -m 750 "${BROKER_ETC}"
    printf 'ACME_DOMAIN=%s\nACME_DNS_ZONE=%s\nACME_DNS_ACCOUNT=%s\nACME_SERVER=%s\n' \
      "$1" "$2" "$3" "${DOMHOUSE_ACME_SERVER:-${LETS_ENCRYPT}}" > "${ACME_SETTINGS}.new"
    mv -f "${ACME_SETTINGS}.new" "${ACME_SETTINGS}"
    cat "${ACME_SETTINGS}"
    acme_get
    ;;
  cert-renew)
    [ $# -eq 0 ] || die "uso: cert-renew"
    if [ ! -f "${ACME_SETTINGS}" ]; then echo "nessun certificato automatico (manca ${ACME_SETTINGS}): niente da fare"; exit 0; fi
    need_tls_disk
    acme_get
    ;;
  cert-revoke)
    [ $# -eq 1 ] || die "uso: cert-revoke <key-compromise|superseded>"
    case "$1" in key-compromise) reason=1 ;; superseded) reason=4 ;; *) die "motivo non previsto: $1 (key-compromise o superseded)" ;; esac
    [ -f "${ACME_SETTINGS}" ] || die "manca ${ACME_SETTINGS}: questo certificato non viene da cert-new"
    need_tls_disk
    domain="$(acme_setting ACME_DOMAIN)"
    step "Revoca del certificato di ${domain}"
    lego certificates revoke --cert.name "${domain}" --reason "${reason}"
    secure_keys
    watch_line "broker cert revoked (${domain}, ${1})"
    step "Certificato nuovo con una chiave nuova"
    acme_get
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
    if [ -f "${ACME_SETTINGS}" ]; then cat "${ACME_SETTINGS}"; fi
    df -h --output=source,size,used,target "${TLS_MOUNT}" 2>/dev/null | tail -1 || true
    docker ps --filter "name=^${CONTAINER}$" --format '{{.Names}}  {{.Image}}  {{.Status}}'
    docker stats --no-stream --format 'memoria {{.MemUsage}}  cpu {{.CPUPerc}}' "${CONTAINER}"
    echo "connessioni sulla porta TLS: $(docker exec "${CONTAINER}" cat /proc/net/tcp /proc/net/tcp6 2>/dev/null | awk '$2 ~ /:22B3$/ && $4 == "01"' | wc -l)"
    echo "appartamenti: $(wc -l < "${APARTMENTS}")"
    for file in devices connectors; do echo "utenti ${file}: $(wc -l < "${AUTH}/${file}.passwd")"; done
    check
    ;;
  *)
    die "uso: prepare-tls-disk | cert-new | install | update | restart | reload | cert-renew | cert-revoke | install-cert | add-apartment | remove-apartment | sync | check | status (vedi l'intestazione)"
    ;;
esac

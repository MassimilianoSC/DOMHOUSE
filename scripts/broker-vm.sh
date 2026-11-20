#!/usr/bin/env bash
# The MQTT broker of the devices on the VM (D-196, D-199). It runs ON the VM, as root (sudo), with the VM's own
# identity, like engine-vm.sh: no gcloud there, only python3, openssl and docker. Procedure: docs/motore-vm.md, G2.
#
#   sudo bash broker-vm.sh prepare-tls-disk                            # once: the keys' disk (C-12); safe to repeat
#   sudo bash broker-vm.sh cert-new <domain> <dns_zone> <dns_account> [rsa2048|ec256]   # the first certificate
#   sudo bash broker-vm.sh install <image>                             # first time (needs the certificate) and to bring
#                                                                      # new files; restarts the broker if mosquitto.conf changed
#   sudo bash /opt/domhouse/broker-vm.sh update <image>                # new image, same data
#   sudo bash /opt/domhouse/broker-vm.sh status
#   sudo bash /opt/domhouse/broker-vm.sh restart                       # everyone reconnects: reload is enough, usually
#   sudo bash /opt/domhouse/broker-vm.sh reload                        # SIGHUP: certificate, users and permissions
#   sudo bash /opt/domhouse/broker-vm.sh cert-renew [force]            # the daily timer: renews only when due
#   sudo bash /opt/domhouse/broker-vm.sh cert-revoke <key-compromise|superseded>   # revokes, then a new key and certificate
#   sudo bash /opt/domhouse/broker-vm.sh cert-test                      # a whole renewal against the test server of Let's Encrypt: nothing replaced
#   sudo bash /opt/domhouse/broker-vm.sh install-cert <fullchain> <privkey>   # a certificate from elsewhere; checks it first
#   sudo bash /opt/domhouse/broker-vm.sh add-apartment <apartment_id>  # its accounts from Secret Manager
#   sudo bash /opt/domhouse/broker-vm.sh remove-apartment <apartment_id>
#   sudo bash /opt/domhouse/broker-vm.sh sync                          # rereads the secrets of every apartment
#   sudo bash /opt/domhouse/broker-vm.sh check                         # one line for the 5-minute watch
#   sudo bash /opt/domhouse/broker-vm.sh rifiuti                       # A5: the refused logins per device (read only)
#   sudo bash /opt/domhouse/broker-vm.sh limit                         # (re)applies the limit on new connections
#   sudo bash /opt/domhouse/broker-vm.sh network                       # the broker's networks as compose.yaml says
#                                                                      # (C2 subnet, E-38 range of the internal one)
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
# Certificate key (D-212): RSA-2048 unless acme.settings says ACME_KEY_TYPE=ec256. An RSA certificate depends only on
# ISRG Root X1 (leaf, YR1 or YR2, Root YR cross-signed by X1), the root a Shelly Gen4 is most likely to carry; the
# chain ending at X1 is asked for by name, so a change of Let's Encrypt's default chain does not change ours. An
# acme.settings without the line (the first certificate of 10 November was ECDSA) means RSA from the next renewal.
#
# Secrets: broker_accounts.py reads them with the VM's identity (langbrain-vm@, Secret Accessor) and writes only hashes.
# Nothing here prints a password; adding them to Secret Manager is broker-secrets.sh, on the PC.
#
# Watch: check writes "broker ok cert_days=<n> ..." or "broker down (...)" and "broker cert expiring days=<n>" (under
# CERT_ALERT_DAYS) with the syslog tag domhouse-check; engine-vm.sh check-all calls it when the broker is installed.
#
# Way in from the internet (D-209): every device has its own user, nobody enters without one, on both doors. Mosquitto
# writes one line for each refused login, "Client <client id> [<ip>:<port>] disconnected: not authorised." (it names
# the user only in its debug log, too large to keep on: each device's client id is set to its user name instead).
# Above AUTH_ALERT_PER_HOUR refused logins in the last hour, check writes "broker auth refused hour=<n> ..." for the
# alert. Mosquitto has no limit on failed logins: the limit is on new connections to 8883, per source address, in an
# nftables table of its own (inet domhouse_broker): beyond LIMIT_BURST at once and LIMIT_RATE after, that address's
# new connections are dropped until it slows down. No ban: the devices of an apartment share one public address, and a
# single relay with a wrong password must not lock out its neighbours; guessing a random 192-bit password is hopeless.
#
# Way out (C2, step 3 of the plan, 17 November): nothing in the broker starts a connection (devices and engines come
# in, lego runs on the host's network), so the same table drops every NEW connection out of the broker's default
# network, BROKER_SUBNET, both forwarded and to the VM itself; the answers of the connections that came in are not new.
# The subnet is fixed in engine/broker/compose.yaml; compose does not move an existing network, so install (and
# network) make it again, with the broker stopped for a moment, when Docker had given it another one.
# Internal network (E-38, 19 November): the broker listens for the engines on its fixed 172.30.83.2; the dynamic
# addresses come only from INTERNAL_IPAM's range, so no container started before the broker can take it. The same
# way: install (and network) make the network again when its range differs, the engines on it detached and attached
# again after the broker, which takes .2 first.
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
DEVICES="${BROKER_ETC}/devices"          # A3: the devices' fingerprints per apartment, written by the agent's executor
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
LETS_ENCRYPT_TEST="https://acme-staging-v02.api.letsencrypt.org/directory"   # cert-test: certificates nobody trusts, no weekly limit
ACME_ACCOUNT_ID=domhouse-broker          # no email: Let's Encrypt sends none, and no address leaves the VM
ACME_CHAIN="ISRG Root X1"               # the chain that ends at the root every client has; the default one today
LIMIT="${DOMHOUSE_LIMIT:-on}"            # "off" only on the unprivileged test bench, which shares the host's network
LIMIT_TABLE=domhouse_broker
LIMIT_FILE="${BROKER_OPT}/limit.nft"
LIMIT_RATE="30/minute"                   # per source address, after the first LIMIT_BURST
LIMIT_BURST=60                           # an apartment's relays reconnecting together after a power cut
BROKER_SUBNET=172.30.84.0/24             # C2: the default network of engine/broker/compose.yaml (the same subnet)
BRIDGE_NETWORK=domhouse-broker_default
INTERNAL_NETWORK=domhouse-broker-internal
INTERNAL_IPAM="172.30.83.0/24 172.30.83.128/25"   # E-38: subnet and ip_range of the internal network (compose.yaml)
AUTH_DEVICE_LINES="${DOMHOUSE_AUTH_DEVICE_LINES:-50}"    # A5: device lines per round at most; the rest in «other»
AUTH_ALERT_PER_HOUR="${DOMHOUSE_AUTH_ALERT_PER_HOUR:-100}"   # one relay with a wrong password retrying alone stays under
KEPT=""                                  # E-33: the apartments the last sync kept as they were (sync_accounts)

die() { echo "errore: $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || die "lancialo con sudo"
for tool in python3 openssl docker; do command -v "$tool" > /dev/null || die "manca $tool sulla VM"; done
docker compose version > /dev/null 2>&1 || die "manca docker compose sulla VM"

# project §2.1: lower case, digits and dashes only (the dot separates apartment and device in the broker's users)
valid_id() { [[ "$1" =~ ^[a-z0-9][a-z0-9-]{0,63}$ ]] || die "apartment_id non valido: $1"; }
lock_vm() {
  # A2 (project §6.1): one change at a time on the VM, the same lock as engine-vm.sh; the agent's executor holds it
  # for the whole order and says so with DOMHOUSE_LOCK_HELD=1 (taking it again here would wait for itself)
  if [ "${DOMHOUSE_LOCK_HELD:-}" = "1" ]; then return 0; fi
  install -d -m 755 "${OPT}"
  exec 8> "${OPT}/.engines.lock"
  flock -w 600 8 || die "un altro comando tiene il blocco della VM da oltre 10 minuti (${OPT}/.engines.lock): riprova più tardi"
}
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
  served_is "${wanted}" && { echo "ricarica fatta: la porta $(tls_port) serve il certificato ${wanted}"; return 0; }
  # D-212: from an ECDSA certificate to an RSA one (or back) the reload is not enough, Mosquitto keeps serving the old
  # one (OpenSSL holds one certificate per key type and prefers ECDSA): a restart, once, and everyone reconnects
  echo "la ricarica non basta (tipo di chiave cambiato?): riavvio del broker, i dispositivi si ricollegano"
  compose restart
  wait_healthy
  served_is "${wanted}" && { echo "riavvio fatto: la porta $(tls_port) serve il certificato ${wanted}"; return 0; }
  die "dopo ricarica e riavvio la porta non serve il certificato sul disco (servito: ${served:-nessuno})"
}

served_is() {
  # served_is <fingerprint>: true when the TLS port serves that certificate within 10 seconds (served: the last seen)
  for _ in $(seq 1 10); do
    served="$(served_pem 2>/dev/null | fingerprint_of_stdin 2>/dev/null || true)"
    [ "${served}" = "$1" ] && return 0
    sleep 1
  done
  return 1
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
  # the list of apartments may have just been changed by the caller: the broker reloads only if a file changed.
  # E-33: an apartment whose secrets cannot be read keeps its accounts («kept <apartment_id>»), the others are
  # updated; each kept one becomes a line of the watch, and KEPT tells the caller which ones
  local out kept
  out="$(python3 "${ACCOUNTS}" sync "${APARTMENTS}" "${AUTH}")" || return 1   # a return: add-apartment must undo its line
  printf '%s\n' "${out}"
  KEPT="$(printf '%s\n' "${out}" | sed -n 's/^kept //p')"
  for kept in ${KEPT}; do watch_line "broker sync kept ${kept}"; done
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
  # copied from a Windows PC they may carry \r line ends, which the broker would read as part of each value; all of
  # them, also two (a file converted twice, as git archive does on Windows)
  sed -i 's/\r*$//' "${OPT}/broker_accounts.py" "${OPT}/compose.broker.yaml" "${BROKER_OPT}/compose.yaml" "${BROKER_OPT}/mosquitto.conf"
}

prepare_tls_disk() {
  # formats the disk only when it is empty, mounts it, writes its fstab line once; each step is skipped when done
  local dev fstype uuid line current source old_uuid
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
    # after a restore from snapshot with a new keys' disk the line still names the old one: it is replaced only when
    # it is our own line and its disk is gone; any other line is someone else's, and is left alone
    old_uuid="$(printf '%s\n' "${current}" | awk 'NR == 1 {print $1}' | sed -n 's/^UUID=//p')"
    if [ -n "${old_uuid}" ] && [ "${current}" = "UUID=${old_uuid} ${TLS_MOUNT} ext4 ${TLS_MOUNT_OPTIONS} 0 2" ] \
       && [ -z "$(blkid -U "${old_uuid}" 2>/dev/null || true)" ]; then
      cp -p /etc/fstab "/etc/fstab.before-domhouse-tls-$(date +%Y%m%d%H%M%S)"
      awk -v m="${TLS_MOUNT}" -v l="${line}" '$1 !~ /^#/ && $2 == m {print l; next} {print}' /etc/fstab > /etc/fstab.domhouse-new
      cat /etc/fstab.domhouse-new > /etc/fstab && rm -f /etc/fstab.domhouse-new
      echo "sostituita (il disco ${old_uuid} non c'è più): ${line}"
    else
      die "/etc/fstab ha già una riga per ${TLS_MOUNT} diversa da quella attesa: ${current}"
    fi
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
  # E-31: on the host's network: the metadata server is closed to the containers' networks, and lego needs the VM's
  # token to act as the DNS account
  local network="${DOMHOUSE_LEGO_NETWORK:-host}" test_args=() env_args=()
  [ -z "${DOMHOUSE_ACME_TEST:-}" ] || test_args=(--tls-skip-verify)    # tests only: a local Pebble
  [ "$1" != "run" ] || env_args=(-e "GCE_IMPERSONATE_SERVICE_ACCOUNT=$(acme_setting ACME_DNS_ACCOUNT)" -e "GCE_ZONE_ID=$(acme_setting ACME_DNS_ZONE)")
  [ -z "${DOMHOUSE_ACME_TEST:-}" ] || env_args=(-e EXEC_PATH=/bin/true)
  docker run --rm --user "${BROKER_UID}:${BROKER_UID}" --read-only --tmpfs /tmp --cap-drop ALL \
    --security-opt no-new-privileges:true --network "${network}" -v "${ACME_DIR}:/acme" "${env_args[@]}" "${LEGO_IMAGE}" \
    "$@" --path /acme --server "$(acme_setting ACME_SERVER)" --account-id "${ACME_ACCOUNT_ID}" --log.format text "${test_args[@]}"
}

acme_get() {
  # gets the certificate when it is missing or due (or at once, with --renew-force as argument); puts it in the
  # broker's folder only when it is a new one
  local domain crt key key_type dns_args=(--dns gcloud)
  domain="$(acme_setting ACME_DOMAIN)"
  case "$(acme_setting ACME_KEY_TYPE)" in
    ""|rsa2048) key_type=RSA2048 ;;
    ec256) key_type=EC256 ;;
    *) die "ACME_KEY_TYPE non previsto in ${ACME_SETTINGS}: $(acme_setting ACME_KEY_TYPE) (rsa2048 o ec256)" ;;
  esac
  [ -z "${DOMHOUSE_ACME_TEST:-}" ] || dns_args=(--dns exec --dns.propagation.wait 1s)   # Pebble accepts every challenge
  crt="${ACME_DIR}/certificates/${domain}.crt"; key="${ACME_DIR}/certificates/${domain}.key"
  if ! lego run --accept-tos -d "${domain}" --no-random-sleep --key-type "${key_type}" --preferred-chain "${ACME_CHAIN}" \
       "${dns_args[@]}" "$@"; then
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

limit_rules() {
  # one transaction: the table is created if missing, emptied and written again, so a repeat leaves one copy
  cat <<NFT
# written by broker-vm.sh limit (D-209): new connections to the broker's TLS port, per source address
add table inet ${LIMIT_TABLE}
delete table inet ${LIMIT_TABLE}
table inet ${LIMIT_TABLE} {
  set sources4 { type ipv4_addr; flags dynamic, timeout; timeout 10m; size 65536; }
  set sources6 { type ipv6_addr; flags dynamic, timeout; timeout 10m; size 65536; }
  chain new_connections {
    type filter hook forward priority -5; policy accept;
    tcp dport 8883 ct state new add @sources4 { ip saddr limit rate over ${LIMIT_RATE} burst ${LIMIT_BURST} packets } counter drop comment "domhouse-broker-limit"
    tcp dport 8883 ct state new add @sources6 { ip6 saddr limit rate over ${LIMIT_RATE} burst ${LIMIT_BURST} packets } counter drop comment "domhouse-broker-limit"
  }
  chain egress_forward {
    type filter hook forward priority -5; policy accept;
    ip saddr ${BROKER_SUBNET} ct state new counter drop comment "domhouse-broker-egress"
  }
  chain egress_input {
    type filter hook input priority -5; policy accept;
    ip saddr ${BROKER_SUBNET} ct state new counter drop comment "domhouse-broker-egress"
  }
}
NFT
}

apply_limit() {
  # the published port reaches the container through docker's DNAT: the hook is forward, where the port is 8883
  command -v nft > /dev/null || die "manca nft sulla VM (sudo apt-get install -y nftables)"
  install -d -m 755 "${OPT}" "${BROKER_OPT}"
  limit_rules > "${LIMIT_FILE}"
  nft -f "${LIMIT_FILE}"
  echo "limite attivo: alla porta 8883, oltre ${LIMIT_BURST} collegamenti nuovi di fila e poi ${LIMIT_RATE} per indirizzo, il resto è scartato"
  echo "uscita chiusa: nessun collegamento nuovo parte dalla rete del broker (${BROKER_SUBNET})"
}

dropped() {   # comment: the packets dropped by the table's rules with that comment
  nft list table inet "${LIMIT_TABLE}" | awk -v c="\"$1\"" \
    'index($0, "comment " c) {for (i = 1; i < NF; i++) if ($i == "packets") s += $(i + 1)} END {print s + 0}'
}

ensure_network() {
  # C2: the default network on BROKER_SUBNET, where the way out is closed. Docker chose the subnet before 17 November,
  # and compose keeps an existing network as it is: the broker stops, the network is made again, compose makes it
  local current
  current="$(docker network inspect -f '{{range .IPAM.Config}}{{.Subnet}} {{end}}' "${BRIDGE_NETWORK}" 2>/dev/null \
    | awk '{print $1}' || true)"
  if [ -z "${current}" ]; then echo "rete ${BRIDGE_NETWORK}: la crea compose su ${BROKER_SUBNET}"; return 0; fi
  if [ "${current}" = "${BROKER_SUBNET}" ]; then echo "rete ${BRIDGE_NETWORK}: già su ${BROKER_SUBNET}"; return 0; fi
  echo "rete ${BRIDGE_NETWORK}: ${current} -> ${BROKER_SUBNET}; il broker si ferma un momento, i dispositivi si ricollegano"
  compose stop broker
  compose rm -f broker
  docker network rm "${BRIDGE_NETWORK}" > /dev/null
}

attach_engines() {   # attach_engines <name>...: the engines back on the internal network (dynamic address)
  local c
  for c in "$@"; do
    docker network connect "${INTERNAL_NETWORK}" "${c}"
    echo "${c}: di nuovo sulla rete interna"
  done
}

ensure_internal_network() {
  # E-38: the internal network with the range of INTERNAL_IPAM. Compose keeps an existing network as it is: the
  # broker stops, every container on the network is detached (the engines, and a probe of engine-vm.sh if one is
  # running), the network goes, compose makes it with the broker on .2, then the engines are attached again. A
  # network that cannot go (a container arrived meanwhile) puts everything back as it was
  local current names=() engines=() c
  current="$(docker network inspect -f '{{range .IPAM.Config}}{{.Subnet}} {{.IPRange}}{{end}}' "${INTERNAL_NETWORK}" \
    2>/dev/null | awk '{$1 = $1; print}' || true)"
  if [ -z "${current}" ]; then echo "rete ${INTERNAL_NETWORK}: la crea compose (${INTERNAL_IPAM})"; return 0; fi
  if [ "${current}" = "${INTERNAL_IPAM}" ]; then echo "rete ${INTERNAL_NETWORK}: già ${INTERNAL_IPAM}"; return 0; fi
  echo "rete ${INTERNAL_NETWORK}: «${current}» -> «${INTERNAL_IPAM}» (E-38); il broker si ferma un momento"
  mapfile -t names < <(docker ps -a --filter "network=${INTERNAL_NETWORK}" --format '{{.Names}}' \
    | grep -v -x -e "${CONTAINER}" -e '' || true)
  for c in "${names[@]}"; do
    case "${c}" in engine-*) engines+=("${c}") ;; esac
  done
  echo "motori sulla rete: ${engines[*]:-nessuno}"
  compose stop broker
  compose rm -f broker
  for c in "${names[@]}"; do docker network disconnect -f "${INTERNAL_NETWORK}" "${c}"; done
  if ! docker network rm "${INTERNAL_NETWORK}" > /dev/null; then
    compose up -d
    attach_engines "${engines[@]}"
    die "rete ${INTERNAL_NETWORK} non tolta (un container arrivato nel frattempo?): broker e motori rimessi com'erano; rilancia broker-vm.sh network"
  fi
  compose up -d                            # the network again, the broker on .2 before any engine
  attach_engines "${engines[@]}"
}

limit_active() { nft list table inet "${LIMIT_TABLE}" > /dev/null 2>&1; }

auth_refused_report() {
  # the refused logins of the last hour; above AUTH_ALERT_PER_HOUR, one line with the busiest address and client id
  local pairs n ip client
  pairs="$(auth_refused_pairs)"
  n="$(printf '%s' "${pairs}" | grep -c . || true)"
  [ "${n}" -gt "${AUTH_ALERT_PER_HOUR}" ] || return 0
  ip="$(printf '%s\n' "${pairs}" | cut -d' ' -f1 | sort | uniq -c | sort -rn | awk 'NR == 1 {print $2 "(" $1 ")"}')"
  client="$(printf '%s\n' "${pairs}" | cut -d' ' -f2- | sort | uniq -c | sort -rn | awk 'NR == 1 {print $2 "(" $1 ")"}')"
  watch_line "broker auth refused hour=${n} top_ip=${ip} top_client=${client}"
}

auth_refused_devices() {
  # A5 (docs/proposta-a5.md §2, answers 1210): for each device whose logins on 8883 were refused, one line per 5-minute
  # slot, "broker device refused apt=<apt> device=<device> slot=<start, UTC> count=<n> last=<UTC>", for the two last
  # COMPLETE slots: each slot is written by two rounds of check (a round late or missing loses nothing) and the server
  # counts a slot once. No address, no password. The client id is chosen by whoever connects: only <apt>.<device> with
  # the id rule, an apartment of the broker's list AND a user registered on the broker (auth/devices.passwd, its first
  # column only, never a fingerprint) is named; everything else is one "other" line per slot, without names (review A5,
  # point 1: invented names of a listed apartment, lab-01.x1…x500, would take the 50 lines and hide the real ones). Not «broker auth refused»: that is the alert of over 100 refusals an hour (broker-accessi-rifiutati.json),
  # which must not fire for one device. At most AUTH_DEVICE_LINES device lines per round, the rest added to "other" (a burst of invented names cannot
  # fill the logs). awk without intervals nor mktime, and the lists as variables, not files (review A5, point 6: never the
  # name of the input file): the VM's awk may be mawk
  local now slot s1 s2 apts users
  now="${DOMHOUSE_NOW_EPOCH:-$(date +%s)}"
  slot=$(( now / 300 * 300 ))
  s1="$(date -u -d "@$(( slot - 300 ))" +%Y-%m-%dT%H:%M:00Z)"
  s2="$(date -u -d "@$(( slot - 600 ))" +%Y-%m-%dT%H:%M:00Z)"
  apts="$(tr '\n' ' ' < "${APARTMENTS}")"
  users="$(cut -d: -f1 "${AUTH}/devices.passwd" 2>/dev/null | tr '\n' ' ' || true)"
  # second reading of A5, point 2: without users nobody can be named, and the page would show 0 unnoticed: a failure,
  # which check turns into «broker device refused error»
  if [ -z "${users// /}" ]; then
    echo "errore: elenco degli utenti del broker vuoto o illeggibile (${AUTH}/devices.passwd)" >&2
    return 1
  fi
  docker logs -t --since 20m "${CONTAINER}" 2>&1 | awk -v s1="${s1}" -v s2="${s2}" -v cap="${AUTH_DEVICE_LINES}" \
      -v apts="${apts}" -v users="${users}" '
    function ok(x) { return length(x) <= 64 && x ~ /^[a-z0-9][a-z0-9-]*$/ }
    BEGIN { n_a = split(apts, a, " "); for (i = 1; i <= n_a; i++) known[a[i]] = 1
            n_u = split(users, u, " "); for (i = 1; i <= n_u; i++) user[u[i]] = 1 }
    / New connection from .* on port 8883\.$/ { for (i = 1; i < NF; i++) if ($i == "from") outside[$(i + 1)] = 1; next }
    / disconnected: not authorised\.$/ {
      ts = $1
      if (ts !~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]/) next
      at = substr($0, index($0, "[") + 1); at = substr(at, 1, index(at, "]") - 1)
      client = $0; sub(/^.*Client /, "", client); sub(/ \[.*$/, "", client)
      if (!(at in outside) || client == "domhouse-check") next
      m = substr(ts, 15, 2) + 0
      s = substr(ts, 1, 14) sprintf("%02d", m - m % 5) ":00Z"
      if (s != s1 && s != s2) next
      dot = index(client, ".")
      apt = substr(client, 1, dot - 1); dev = substr(client, dot + 1)
      if (dot > 1 && ok(apt) && ok(dev) && (apt in known) && (client in user)) {
        k = s " " apt " " dev; n[k]++; t = substr(ts, 1, 19) "Z"; if (t > last[k]) last[k] = t
      } else other[s]++
    }
    END {
      lines = 0
      for (k in n) {
        split(k, f, " ")
        if (lines < cap + 0) { print "broker device refused apt=" f[2] " device=" f[3] " slot=" f[1] " count=" n[k] " last=" last[k]; lines++ }
        else other[f[1]] += n[k]
      }
      for (s in other) print "broker device refused other slot=" s " count=" other[s]
    }'
}

auth_refused_devices_report() {
  # A5: the lines above into syslog (tag domhouse-check): the log view of A5 holds only these, the server reads it
  local line
  auth_refused_devices | while IFS= read -r line; do watch_line "${line}"; done
}

auth_refused_pairs() {
  # "<ip> <client id>" for each refused login of the last hour that came in on 8883: the refusal line is matched to
  # its "New connection from <ip>:<port> on port 8883." line. Left out: the internal door (the container's own health
  # check refuses itself there every minute) and check's own probe, client id domhouse-check
  docker logs --since 1h "${CONTAINER}" 2>&1 | awk '
    / New connection from .* on port 8883\.$/ { for (i = 1; i < NF; i++) if ($i == "from") outside[$(i + 1)] = 1 }
    / disconnected: not authorised\.$/ {
      at = substr($0, index($0, "[") + 1); at = substr(at, 1, index(at, "]") - 1)
      client = $0; sub(/^.*Client /, "", client); sub(/ \[.*$/, "", client)
      if ((at in outside) && client != "domhouse-check") { ip = at; sub(/:[0-9]+$/, "", ip); print ip, client }
    }'
}

install_units() {
  step "Limite sui collegamenti a ogni avvio: domhouse-broker-limit.service"
  cat > "${SYSTEMD}/domhouse-broker-limit.service" <<UNIT
[Unit]
Description=DOMHOUSE broker: limit on new connections to 8883 per source address (broker-vm.sh limit, D-209)
After=network-pre.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash ${OPT}/broker-vm.sh limit

[Install]
WantedBy=multi-user.target
UNIT
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
  systemctl enable domhouse-broker-limit.service > /dev/null
  systemctl enable --now domhouse-broker-cert.timer > /dev/null
  echo "domhouse-broker-limit.service abilitato, timer domhouse-broker-cert.timer attivo"
}

check() {
  local state pem days problem
  problem="$(tls_disk_problem)"
  if [ -n "${problem}" ]; then
    watch_line "broker down (${problem})"
    return 0
  fi
  if [ "${LIMIT}" = "on" ] && ! limit_active; then          # lost (a flush of the firewall): put it back at once
    if (apply_limit > /dev/null 2>&1); then watch_line "broker limit restored"; else watch_line "broker limit missing"; fi
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
  # D-210: when the container last started; the run-in report counts the different values as restarts
  watch_line "broker started_at=$(docker inspect -f '{{.State.StartedAt}}' "${CONTAINER}" 2>/dev/null || echo '?')"
  auth_refused_report
  # review A5, point 2: a failure of the new part never fails check (check-all would write «broker down»); this line
  # matches neither the alert of «broker auth refused» nor the sink («broker device refused apt=»)
  auth_refused_devices_report || watch_line "broker device refused error"
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
    # 20 November (A2 C9.2): /etc/domhouse only made when missing, 755 root:root like agent-vm.sh. «install -d -m 700» on
    # the existing folder set 700, and the agent's reader (domhouse-agent) could no longer reach agent-lettore.conf at its
    # next start. The files inside keep their own modes (.env and keys 600, agent.conf 600, _broker 750)
    [ -d "${ETC}" ] || install -d -m 755 -o root -g root "${ETC}"
    install -d -m 750 "${BROKER_ETC}"
    install -d -m 750 -o "${BROKER_UID}" -g "${BROKER_UID}" "${BROKER_DATA}"
    # A3 N9: auth/ is root's with the broker's group: the agent's executor (root without CAP_DAC_OVERRIDE, group 1883)
    # writes as the folder's owner and re-reads the files (1883:1883 640) through the group; the broker reads them
    install -d -m 750 -o root -g "${BROKER_UID}" "${AUTH}"
    install -d -m 700 "${DEVICES}"
    secure_keys
    [ -f "${APARTMENTS}" ] || : > "${APARTMENTS}"
    step "Utenti e permessi"
    sync_accounts
    install_units
    step "Limite sui collegamenti nuovi"
    if [ "${LIMIT}" = "on" ]; then apply_limit; else echo "non applicato (DOMHOUSE_LIMIT=${LIMIT}, solo nelle prove)"; fi
    step "Avvio di ${CONTAINER} con ${image}"
    compose pull --quiet
    ensure_network
    ensure_internal_network
    compose up -d
    # mosquitto.conf is mounted as a single file and put_files replaces it with a new one: a broker already running
    # keeps reading the old one, also after a reload, and compose does not recreate it for a change of content. When
    # what the container reads is not the installed file, a restart (the lot 38 procedure, V3, 11 November)
    if docker exec "${CONTAINER}" cat /mosquitto/config/mosquitto.conf 2>/dev/null | cmp -s - "${BROKER_OPT}/mosquitto.conf"; then
      echo "il broker legge la configurazione installata"
    else
      echo "configurazione cambiata: riavvio del broker, i dispositivi si ricollegano"
      compose restart
    fi
    wait_healthy
    docker exec "${CONTAINER}" cat /mosquitto/config/mosquitto.conf | cmp -s - "${BROKER_OPT}/mosquitto.conf" \
      || die "dopo il riavvio il broker non legge ancora ${BROKER_OPT}/mosquitto.conf"
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
    [ $# -eq 3 ] || [ $# -eq 4 ] || die "uso: cert-new <domain> <dns_zone> <dns_account> [rsa2048|ec256]"
    key_type="${4:-rsa2048}"
    [[ "${key_type}" =~ ^(rsa2048|ec256)$ ]] || die "tipo di chiave non previsto: ${key_type} (rsa2048 o ec256)"
    [[ "$1" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$ ]] || die "nome non valido: $1"
    [[ "$2" =~ ^[a-z][a-z0-9-]{0,62}$ ]] || die "zona Cloud DNS non valida: $2"
    [[ "$3" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z0-9-]+\.iam\.gserviceaccount\.com$ ]] || die "account DNS non valido: $3"
    need_tls_disk
    [ -d "${ETC}" ] || install -d -m 755 -o root -g root "${ETC}"   # never another mode on it (A2 C9.2: the reader)
    install -d -m 750 "${BROKER_ETC}"
    printf 'ACME_DOMAIN=%s\nACME_DNS_ZONE=%s\nACME_DNS_ACCOUNT=%s\nACME_SERVER=%s\nACME_KEY_TYPE=%s\n' \
      "$1" "$2" "$3" "${DOMHOUSE_ACME_SERVER:-${LETS_ENCRYPT}}" "${key_type}" > "${ACME_SETTINGS}.new"
    mv -f "${ACME_SETTINGS}.new" "${ACME_SETTINGS}"
    cat "${ACME_SETTINGS}"
    acme_get --renew-force               # new means now: also over a valid one (another key type, another name)
    ;;
  cert-renew)
    [ $# -eq 0 ] || { [ $# -eq 1 ] && [ "$1" = "force" ]; } || die "uso: cert-renew [force]"
    if [ ! -f "${ACME_SETTINGS}" ]; then echo "nessun certificato automatico (manca ${ACME_SETTINGS}): niente da fare"; exit 0; fi
    need_tls_disk
    if [ $# -eq 1 ]; then acme_get --renew-force; else acme_get; fi   # force: the renewal tried once during the run-in (D-210)
    ;;
  cert-test)
    # after E-31: a whole renewal (lego on the host's network, the VM acting as the DNS account, the DNS challenge)
    # against Let's Encrypt's test server, in a folder of its own on the keys' disk, removed at the end. The certificate
    # the broker serves and the real ACME account are never touched: no device reconnects, no weekly limit is used
    [ $# -eq 0 ] || die "uso: cert-test"
    [ -f "${ACME_SETTINGS}" ] || die "manca ${ACME_SETTINGS}: nessun certificato automatico da provare"
    need_tls_disk
    domain="$(acme_setting ACME_DOMAIN)"
    test_dir="${TLS_MOUNT}/acme-test"
    rm -rf "${test_dir}"
    install -d -m 700 "${test_dir}"
    chown "${BROKER_UID}:${BROKER_UID}" "${test_dir}"
    step "Rinnovo di prova di ${domain} contro il server di prova di Let's Encrypt"
    if docker run --rm --user "${BROKER_UID}:${BROKER_UID}" --read-only --tmpfs /tmp --cap-drop ALL \
         --security-opt no-new-privileges:true --network "${DOMHOUSE_LEGO_NETWORK:-host}" -v "${test_dir}:/acme" \
         -e "GCE_IMPERSONATE_SERVICE_ACCOUNT=$(acme_setting ACME_DNS_ACCOUNT)" -e "GCE_ZONE_ID=$(acme_setting ACME_DNS_ZONE)" \
         "${LEGO_IMAGE}" run --accept-tos -d "${domain}" --no-random-sleep --key-type RSA2048 --dns gcloud \
         --path /acme --server "${LETS_ENCRYPT_TEST}" --account-id domhouse-broker-test --log.format text; then
      until="$(openssl x509 -in "${test_dir}/certificates/${domain}.crt" -noout -enddate 2>/dev/null || true)"
      rm -rf "${test_dir}"
      watch_line "broker cert test ok (${domain}${until:+, ${until}})"
    else
      rm -rf "${test_dir}"
      watch_line "broker cert test failed (${domain})"
      die "rinnovo di prova non riuscito: permesso sul DNS (docs/procedura-permesso-dns.md, D4)? rete? lego?"
    fi
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
    lock_vm
    # A3 §6.2: the file of fingerprints (empty) before the sync: an apartment of the app never reads an old secret
    ( umask 077; mkdir -p "${DEVICES}" )                  # 700 from the umask: no separate chmod
    [ -e "${DEVICES}/$1" ] || [ "$1" = "lab-01" ] || ( umask 077; : > "${DEVICES}/$1" )
    if grep -qx "$1" "${APARTMENTS}"; then echo "$1 è già nell'elenco"; else printf '%s\n' "$1" >> "${APARTMENTS}"; fi
    undo_line() { grep -vx "$1" "${APARTMENTS}" > "${APARTMENTS}.new" || true; mv -f "${APARTMENTS}.new" "${APARTMENTS}"; }
    sync_accounts || { undo_line "$1"; exit 1; }
    # E-33: a new apartment whose secrets cannot be read has no accounts to keep: it is not added
    if printf '%s\n' "${KEPT}" | grep -qx "$1"; then undo_line "$1"; die "segreti di $1 non leggibili dalla VM: non aggiunto (broker-secrets.sh add-apartment $1 fatto?)"; fi
    ;;
  remove-apartment)
    [ $# -eq 1 ] || die "uso: remove-apartment <apartment_id>"
    need_installed
    valid_id "$1"
    lock_vm
    # A2 (project §6.9): repeatable, «already removed» is a success; the file of fingerprints goes in any case
    if ! grep -qx "$1" "${APARTMENTS}"; then rm -f "${DEVICES}/$1"; echo "$1 non è nell'elenco: già tolto"; exit 0; fi
    grep -vx "$1" "${APARTMENTS}" > "${APARTMENTS}.new" || true
    mv -f "${APARTMENTS}.new" "${APARTMENTS}"
    rm -f "${DEVICES}/$1"
    sync_accounts
    ;;
  devices-from-auth)
    # A3 §6.4 (answer 1174): an apartment of the old «-devices» secret (lab-01) passes to its file of fingerprints:
    # the lines the broker uses today, no password read; the sync then changes nothing. The lines are printed for the
    # copy into the app (scripts/migra_credenziali.py): fingerprints, not passwords
    [ $# -eq 1 ] || die "uso: devices-from-auth <apartment_id>"
    need_installed
    valid_id "$1"
    lock_vm
    [ ! -e "${DEVICES}/$1" ] || die "${DEVICES}/$1 c'è già: niente da fare"
    ( umask 077; mkdir -p "${DEVICES}" )
    from_auth="${DEVICES}/.$1.nuovo"
    ( umask 077; sed -n "s/^$1\.\([^:]*\):\(.*\)$/\1 \2/p" "${AUTH}/devices.passwd" > "${from_auth}" )
    if [ ! -s "${from_auth}" ]; then rm -f "${from_auth}"; die "nessun dispositivo di $1 in ${AUTH}/devices.passwd"; fi
    mv -f "${from_auth}" "${DEVICES}/$1"
    echo "== impronte di $1 (${DEVICES}/$1)"
    cat "${DEVICES}/$1"
    sync_accounts
    ;;
  sync)
    need_installed
    lock_vm
    sync_accounts
    ;;
  check)
    need_installed
    check
    ;;
  rifiuti)
    [ $# -eq 0 ] || die "uso: rifiuti"
    need_installed
    auth_refused_devices
    ;;
  limit)
    [ $# -eq 0 ] || die "uso: limit"
    apply_limit
    ;;
  network)
    [ $# -eq 0 ] || die "uso: network"
    need_installed
    need_tls_disk
    ensure_network
    ensure_internal_network
    compose up -d
    wait_healthy
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
    echo "accessi rifiutati sulla 8883 nell'ultima ora: $(auth_refused_pairs | grep -c . || true)"
    if [ "${LIMIT}" = "on" ]; then
      if limit_active; then
        echo "collegamenti scartati dal limite: $(dropped domhouse-broker-limit)"
        echo "collegamenti in uscita dal broker scartati: $(dropped domhouse-broker-egress)"
      else
        echo "limite sui collegamenti assente: sudo bash /opt/domhouse/broker-vm.sh limit"
      fi
    fi
    check
    ;;
  *)
    die "uso: prepare-tls-disk | cert-new | install | update | restart | reload | cert-renew | cert-test | cert-revoke | install-cert | add-apartment | remove-apartment | devices-from-auth | sync | check | limit | network | status (vedi l'intestazione)"
    ;;
esac

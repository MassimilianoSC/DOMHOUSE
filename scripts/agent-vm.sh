#!/usr/bin/env bash
# Tool A, package A1 (docs/progetto-strumento-a-base.md §1): the order receiver on the VM. It WRITES on the VM: the
# committente runs it, as root, after step 2 of the plan, from a folder copied from the PC with the agent's files
# (scripts/agent-vm.sh and scripts/agent/). Never on the production VM's subscription from the shared VM (§5.4).
#
#   sudo AMBIENTE=staging SOTTOSCRIZIONE=projects/<p>/subscriptions/<s> RISULTATI=projects/<p>/topics/<t> \
#        bash agent-vm.sh install      # user domhouse-agent, code, configuration, the two services started
#   sudo bash agent-vm.sh status       # the two services and their last lines
#   sudo bash agent-vm.sh uninstall    # services stopped, code and units removed; journals and tombstones stay
#
# Installed: /opt/domhouse/agent/{comune,lettore,esecutore}.py (root, 644), /etc/domhouse/agent.conf (the executor's,
# root 600: environment, shared VM, the reader's user, staging's maximum of engines), /etc/domhouse/agent-lettore.conf
# (the reader's, root 644: environment, subscription, results topic), the two units in /etc/systemd/system. The
# folders /run/domhouse-agent and /var/lib/domhouse-{agent,executor} are made by systemd (RuntimeDirectory and
# StateDirectory of the units). Both configurations are checked by the agent's own readers BEFORE anything is
# installed: a wrong value installs nothing.
set -euo pipefail
set +x

ETC="${DOMHOUSE_ETC:-/etc/domhouse}"
OPT="${DOMHOUSE_OPT:-/opt/domhouse}"
UNITS="${DOMHOUSE_SYSTEMD:-/etc/systemd/system}"
LIB="${DOMHOUSE_LIB:-/var/lib}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${HERE}/agent"
USER_NAME="domhouse-agent"
# A3 (20 November, Q2.3 stopped): the executor's unit has SupplementaryGroups=domhouse-broker to re-read the broker's
# auth/ files (1883:1883 640); systemd refuses a gid no group has (status 216, EXIT_GROUP), and on the VM 1883 is only
# the user of Mosquitto's container: install makes a system group with that gid and this name
BROKER_GROUP="domhouse-broker"
BROKER_GID=1883
SERVICES=(domhouse-agent-esecutore.service domhouse-agent-lettore.service)
FILES=(comune.py lettore.py esecutore.py)

die() { echo "errore: $*" >&2; exit 1; }
say() { printf '== %s\n' "$*"; }

need_root() { [ "$(id -u)" = "0" ] || die "va lanciato da root (sudo)"; }

check_configs() {
  # check_configs <executor's file> <reader's file>: the agent's own readers, before anything is installed
  python3 -I -c '
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import esecutore, lettore
esecutore.read_config(Path(sys.argv[2]), uid_of=lambda name: 0, check_owner=False)
lettore.read_config(Path(sys.argv[3]))
' "${SRC}" "$1" "$2" 2>&1 | tail -1 | sed 's/^/configurazione non valida: /' >&2
  return "${PIPESTATUS[0]}"
}

cmd="${1:-}"
case "${cmd}" in
  install)
    need_root
    for f in "${FILES[@]}" "${SERVICES[@]}"; do [ -f "${SRC}/${f}" ] || die "manca ${SRC}/${f}"; done
    [ "${AMBIENTE:-}" = "staging" ] \
      || die "AMBIENTE deve essere staging: sulla VM condivisa la produzione non manda ordini (prod rifiutato, §5.4)"
    [ -n "${SOTTOSCRIZIONE:-}" ] || die "manca SOTTOSCRIZIONE (projects/<p>/subscriptions/<s>)"
    [ -n "${RISULTATI:-}" ] || die "manca RISULTATI (projects/<p>/topics/<t>)"
    work="$(mktemp -d)"
    trap 'rm -rf "${work}"' EXIT
    printf 'AMBIENTE=%s\nCONDIVISA=1\nLETTORE=%s\nMAX_MOTORI_STAGING=4\n' "${AMBIENTE}" "${USER_NAME}" > "${work}/agent.conf"
    printf 'AMBIENTE=%s\nSOTTOSCRIZIONE=%s\nRISULTATI=%s\n' "${AMBIENTE}" "${SOTTOSCRIZIONE}" "${RISULTATI}" \
      > "${work}/agent-lettore.conf"
    check_configs "${work}/agent.conf" "${work}/agent-lettore.conf" || die "SOTTOSCRIZIONE o RISULTATI non validi: niente installato"
    say "Gruppo ${BROKER_GROUP} (gid ${BROKER_GID})"
    by_name="$(getent group "${BROKER_GROUP}" || true)"
    by_gid="$(getent group "${BROKER_GID}" || true)"
    if [ -n "${by_name}" ]; then
      [ "$(printf '%s' "${by_name}" | cut -d: -f3)" = "${BROKER_GID}" ] \
        || die "il gruppo ${BROKER_GROUP} esiste con un gid diverso da ${BROKER_GID}: niente installato (si decide con o1)"
      echo "esiste già"
    elif [ -n "${by_gid}" ]; then
      die "il gid ${BROKER_GID} è già del gruppo «${by_gid%%:*}»: niente installato (si decide con o1)"
    else
      groupadd --system --gid "${BROKER_GID}" "${BROKER_GROUP}"
      echo "creato"
    fi
    say "Utente ${USER_NAME}"
    if getent passwd "${USER_NAME}" > /dev/null; then
      echo "esiste già"
    else
      useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "${USER_NAME}"
      echo "creato"
    fi
    say "Codice in ${OPT}/agent"
    install -d -m 755 -o root -g root "${OPT}/agent"
    for f in "${FILES[@]}"; do install -m 644 -o root -g root "${SRC}/${f}" "${OPT}/agent/${f}"; done
    say "Configurazione"
    install -d -m 755 -o root -g root "${ETC}"
    install -m 600 -o root -g root "${work}/agent.conf" "${ETC}/agent.conf"
    install -m 644 -o root -g root "${work}/agent-lettore.conf" "${ETC}/agent-lettore.conf"
    say "Servizi"
    for s in "${SERVICES[@]}"; do install -m 644 -o root -g root "${SRC}/${s}" "${UNITS}/${s}"; done
    systemctl daemon-reload
    for s in "${SERVICES[@]}"; do systemctl enable --now "${s}"; done      # the executor first: the reader needs it
    # R17: installing again must run the new code, not only put it on disk; the executor first, again
    for s in "${SERVICES[@]}"; do systemctl restart "${s}"; done
    echo "agente installato: ambiente ${AMBIENTE}"
    ;;
  status)
    for s in "${SERVICES[@]}"; do echo "${s}: $(systemctl is-active "${s}" 2>/dev/null || true)"; done
    for s in "${SERVICES[@]}"; do journalctl -u "${s}" -n 5 --no-pager 2>/dev/null || true; done
    ;;
  uninstall)
    need_root
    for ((i = ${#SERVICES[@]} - 1; i >= 0; i--)); do
      systemctl disable --now "${SERVICES[$i]}" 2>/dev/null || true             # the reader first
    done
    for s in "${SERVICES[@]}"; do rm -f "${UNITS}/${s}"; done
    systemctl daemon-reload
    rm -rf "${OPT}/agent"
    rm -f "${ETC}/agent.conf" "${ETC}/agent-lettore.conf"
    echo "agente tolto; restano i giornali e le lapidi in ${LIB}/domhouse-agent e ${LIB}/domhouse-executor"
    ;;
  *)
    die "uso: install | status | uninstall (vedi l'intestazione)"
    ;;
esac

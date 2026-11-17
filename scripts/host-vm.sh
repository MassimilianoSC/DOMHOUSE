#!/usr/bin/env bash
# The VM's host, three small files of our own (step 3 of the plan: the security check inside the VM, 17 November). It
# runs ON the VM, as root (sudo), like engine-vm.sh and broker-vm.sh. Procedure: docs/procedura-passo3-vm.md.
#
#   sudo bash host-vm.sh apply                        # writes the three files and applies them; copies itself to /opt
#   sudo bash /opt/domhouse/host-vm.sh confirm        # from a NEW connection: the sshd file stays (see below)
#   sudo bash /opt/domhouse/host-vm.sh check          # what is in force, one line each
#   sudo bash /opt/domhouse/host-vm.sh undo-sshd      # only the sshd file away (what the revert by itself runs)
#   sudo bash /opt/domhouse/host-vm.sh undo           # all three away, and the two sysctl values put back
#
# The files:
#   /etc/sysctl.d/90-domhouse.conf            kernel.kptr_restrict = 1, kernel.yama.ptrace_scope = 1 (Debian: 0, 0)
#   /etc/systemd/resolved.conf.d/90-domhouse.conf   LLMNR=no: systemd-resolved stops listening on 5355 everywhere
#   /etc/ssh/sshd_config.d/90-domhouse.conf   X11Forwarding no, AllowAgentForwarding no, MaxAuthTries 3. Debian's
#        sshd_config reads this folder first and the first value wins. AllowTcpForwarding stays as it is: the IAP
#        tunnels may need it.
# sshd: sshd -t before the reload (a wrong file is removed at once, nothing reloaded), and a revert by itself after
# REVERT_S unless "confirm" comes: a change that locked gcloud compute ssh out (MaxAuthTries 3 against a PC that
# offers many keys) puts itself back. confirm is run from a NEW connection, which proves that logging in still works.
# The values of the two sysctl keys before apply are kept in /opt/domhouse/host-vm.prima, for undo: removing the file
# alone would leave the new values in force until the next boot.
set -euo pipefail
set +x

SYSCTL_DIR="${DOMHOUSE_SYSCTL_DIR:-/etc/sysctl.d}"          # these folders can be moved only by the tests
RESOLVED_DIR="${DOMHOUSE_RESOLVED_DIR:-/etc/systemd/resolved.conf.d}"
SSHD_DIR="${DOMHOUSE_SSHD_DIR:-/etc/ssh/sshd_config.d}"
OPT="${DOMHOUSE_OPT:-/opt/domhouse}"
NAME=90-domhouse.conf
BEFORE="${OPT}/host-vm.prima"
KEYS=(kernel.kptr_restrict kernel.yama.ptrace_scope)
REVERT_UNIT=domhouse-sshd-ritorno
REVERT_S=600

die() { echo "errore: $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || die "lancialo con sudo"

apply_sysctl() {
  step "sysctl: ${SYSCTL_DIR}/${NAME}"
  if [ ! -f "${BEFORE}" ]; then                    # the values before our first apply, never overwritten
    for key in "${KEYS[@]}"; do echo "${key}=$(sysctl -n "${key}")"; done > "${BEFORE}"
  fi
  printf '# step 3 of the plan (17 November), scripts/host-vm.sh\nkernel.kptr_restrict = 1\nkernel.yama.ptrace_scope = 1\n' \
    > "${SYSCTL_DIR}/${NAME}"
  sysctl -p "${SYSCTL_DIR}/${NAME}"
}

apply_resolved() {
  step "systemd-resolved: ${RESOLVED_DIR}/${NAME}"
  printf '# step 3 of the plan (17 November), scripts/host-vm.sh\n[Resolve]\nLLMNR=no\n' > "${RESOLVED_DIR}/${NAME}"
  systemctl restart systemd-resolved
}

apply_sshd() {
  step "sshd: ${SSHD_DIR}/${NAME}"
  printf '# step 3 of the plan (17 November), scripts/host-vm.sh\nX11Forwarding no\nAllowAgentForwarding no\nMaxAuthTries 3\n' \
    > "${SSHD_DIR}/${NAME}"
  if ! sshd -t; then
    rm -f "${SSHD_DIR}/${NAME}"
    die "sshd -t rifiuta la configurazione: file tolto, sshd non ricaricato"
  fi
  # the revert is armed BEFORE the reload (review of 17 November): never an sshd changed without its way back. A
  # revert left from a previous apply is stopped first, and RemainAfterElapse=no lets the same unit name be used again
  systemctl stop "${REVERT_UNIT}.timer" 2> /dev/null || true
  systemctl stop "${REVERT_UNIT}.service" 2> /dev/null || true
  if ! systemd-run --unit="${REVERT_UNIT}" --on-active="${REVERT_S}" --timer-property=RemainAfterElapse=no \
       /bin/bash "${OPT}/host-vm.sh" undo-sshd > /dev/null; then
    rm -f "${SSHD_DIR}/${NAME}"
    die "il ritorno da solo non si arma: file di sshd tolto, sshd non ricaricato"
  fi
  systemctl reload ssh
  echo "sshd ricaricato. Fra $((REVERT_S / 60)) minuti il file si toglie da solo: da una connessione NUOVA lancia"
  echo "  sudo bash ${OPT}/host-vm.sh confirm"
}

undo_sshd() {
  rm -f "${SSHD_DIR}/${NAME}"
  systemctl reload ssh
  echo "file di sshd tolto, sshd ricaricato"
}

cmd="${1:-}"
case "${cmd}" in
  apply)
    install -d -m 755 "${OPT}" "${SYSCTL_DIR}" "${RESOLVED_DIR}" "${SSHD_DIR}"
    [ "$(cd "$(dirname "$0")" && pwd)" = "${OPT}" ] || install -m 755 "$0" "${OPT}/host-vm.sh"
    apply_sysctl
    apply_resolved
    apply_sshd
    ;;
  confirm)
    # only what is pending: after the revert by itself the file is gone, and "the file stays" would be false
    [ -f "${SSHD_DIR}/${NAME}" ] || die "niente da confermare: il file di sshd è già stato tolto (il ritorno da solo è scattato)"
    systemctl is-active --quiet "${REVERT_UNIT}.timer" \
      || die "niente da confermare: nessun ritorno in attesa (già confermato?)"
    systemctl stop "${REVERT_UNIT}.timer"
    echo "confermato: il file di sshd resta"
    ;;
  undo-sshd)
    undo_sshd
    ;;
  undo)
    rm -f "${SYSCTL_DIR}/${NAME}" "${RESOLVED_DIR}/${NAME}"
    if [ -f "${BEFORE}" ]; then
      while IFS='=' read -r key value; do
        [ -n "${key}" ] && sysctl -w "${key}=${value}"
      done < "${BEFORE}"
    fi
    systemctl restart systemd-resolved
    undo_sshd
    echo "tolti i tre file; valori di sysctl di prima rimessi"
    ;;
  check)
    for key in "${KEYS[@]}"; do echo "${key} $(sysctl -n "${key}")"; done
    sshd -T 2> /dev/null | grep -E '^(x11forwarding|allowagentforwarding|maxauthtries|allowtcpforwarding) ' || true
    echo "porte LLMNR 5355 in ascolto: $(ss -lntu | grep -c ':5355 ' || true)"
    ;;
  *)
    die "uso: apply | confirm | check | undo-sshd | undo (vedi l'intestazione)"
    ;;
esac

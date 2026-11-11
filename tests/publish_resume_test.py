"""D25 (P-83 review: case 1 gravity 2, cases 2 and 3 gravity 3): publish-all after a FERMO in the engine's step. The
second run read only the VM, and the VM already looked done: (1) engine-vm.sh update writes ENGINE_IMAGE before it
starts the engine, so a failed update left the new image in the file and the next run said «il motore è già
all'immagine», «invariato», exit 0, with the old image (or a new unhealthy one) running, also in later lots; (2)
engine-vm.sh installed but its timers failed: the next run saw the same hash and never reinstalled the timers; (3)
compose.yaml installed but the engine's recreation failed: «invariato». Now every step on the VM is written in the
state file before it starts (da-fare=motore|timer|compose) and marked done only when it succeeds (fatto=...): a step
not done is done again whatever the VM says; and the image the engine really runs (docker inspect) is compared with
the one in its settings, so a failed update is seen in any later run. A gcloud stand-in that behaves like the VM
(V-D25/test_d25.py), its assertions inverted."""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from publish_all_test import ENGINE, pub, steps  # noqa: E402,F401  (pub is the fixture)

GCLOUD = r'''#!/usr/bin/env bash
echo "gcloud $*" >> "$STUB_DIR/calls.log"
case "$*" in
  *"services describe domotica-bff-staging "*containers*) cat "$STUB_DIR/state-staging" 2>/dev/null ;;
  *"services describe domotica-bff "*containers*) cat "$STUB_DIR/state-prod" 2>/dev/null ;;
  *"services describe domotica-bff "*minScale*) cat "$STUB_DIR/values-prod" 2>/dev/null ;;
  *"compute scp"*) : ;;
  *"compute ssh"*)
    cmd="${*#*--command }"
    case "$cmd" in
      *"docker inspect"*) cat "$STUB_DIR/vm-running" 2>/dev/null ;;
      *ENGINE_IMAGE*) cat "$STUB_DIR/vm-image" ;;
      *engine-vm.sh*sha256sum*) cat "$STUB_DIR/vm-script-hash" ;;
      *compose.yaml*sha256sum*) cat "$STUB_DIR/vm-compose-hash" ;;
      *"install -m 644 ~/compose.yaml"*) cp "$STUB_DIR/wanted-compose-hash" "$STUB_DIR/vm-compose-hash"; echo compose-ok ;;
      *"install -m 755 ~/engine-vm.sh"*)
        cp "$STUB_DIR/wanted-script-hash" "$STUB_DIR/vm-script-hash"     # installed
        [ -f "$STUB_DIR/timers-fails" ] && exit 1                          # then the timers failed
        echo timer-ok ;;
      *"engine-vm.sh update"*)
        image="$(echo "$cmd" | awk '{for (i = 1; i <= NF; i++) if ($i == "update") print $(i + 2)}')"
        echo "$image" > "$STUB_DIR/vm-image"                               # engine-vm.sh writes it before start
        [ -f "$STUB_DIR/update-fails" ] && exit 1
        echo "$image" > "$STUB_DIR/vm-running"                             # running only when start succeeded
        echo update-ok ;;
    esac ;;
esac
exit 0
'''


def prepare(pub, running=None):
    (pub.stubs / "gcloud").write_text(GCLOUD, encoding="utf-8", newline="\n")
    for name, rel in (("wanted-script-hash", "scripts/engine-vm.sh"), ("wanted-compose-hash", "engine/compose.yaml")):
        data = (pub.root / rel).read_bytes().replace(b"\r", b"")
        (pub.stubs / name).write_text(f"{hashlib.sha256(data).hexdigest()}  -\n", encoding="utf-8")
    (pub.stubs / "vm-running").write_text(f"{ENGINE}{running or pub.on_vm}\n", encoding="utf-8")


def same(pub, which):
    (pub.stubs / f"vm-{which}-hash").write_text((pub.stubs / f"wanted-{which}-hash").read_text(), encoding="utf-8")


def test_case1_a_failed_engine_update_is_done_again_never_unchanged(pub):
    prepare(pub)
    same(pub, "script")
    same(pub, "compose")
    (pub.stubs / "update-fails").write_text("", encoding="utf-8")
    done, calls = pub()
    assert done.returncode != 0 and "non è tornato sano" in done.stdout + done.stderr
    done, calls = pub()                                      # the cause is still there: it fails again, it says so
    out = done.stdout + done.stderr
    assert done.returncode != 0 and "update" in steps(calls)
    assert "motore dev: invariato" not in out
    (pub.stubs / "update-fails").unlink()                    # the cause is gone
    done, calls = pub()
    out = done.stdout + done.stderr
    assert done.returncode == 0, out
    assert "update" in steps(calls) and f"motore dev: da {pub.on_vm} a {pub.lot}" in out
    assert "fatto=motore" in pub.state().splitlines()


def test_case1_in_a_later_run_the_running_image_tells_the_truth(pub):
    """No state file to help (another lot): the settings say the new image, the container runs the old one."""
    prepare(pub)
    same(pub, "script")
    same(pub, "compose")
    (pub.stubs / "vm-image").write_text(f"{ENGINE}{pub.lot}\n", encoding="utf-8")       # the file: the new one
    done, calls = pub()
    out = done.stdout + done.stderr
    assert done.returncode == 0, out
    assert "il motore è già all'immagine" not in out and "update" in steps(calls)
    assert f"gira con {pub.on_vm}" in out


def test_case2_timers_that_failed_are_installed_again(pub):
    prepare(pub)
    (pub.stubs / "vm-image").write_text(f"{ENGINE}{pub.lot}\n", encoding="utf-8")
    (pub.stubs / "vm-running").write_text(f"{ENGINE}{pub.lot}\n", encoding="utf-8")
    same(pub, "compose")
    (pub.stubs / "timers-fails").write_text("", encoding="utf-8")
    done, calls = pub()
    assert done.returncode != 0 and "engine-vm.sh timers sulla VM non è riuscito" in done.stdout + done.stderr
    (pub.stubs / "timers-fails").unlink()
    done, calls = pub()
    out = done.stdout + done.stderr
    assert done.returncode == 0, out
    assert "timers" in steps(calls) and "fatto=timer" in pub.state().splitlines()


def test_case3_a_compose_installed_but_not_applied_is_applied_again(pub):
    prepare(pub)
    (pub.stubs / "vm-image").write_text(f"{ENGINE}{pub.lot}\n", encoding="utf-8")
    (pub.stubs / "vm-running").write_text(f"{ENGINE}{pub.lot}\n", encoding="utf-8")
    same(pub, "script")
    (pub.stubs / "update-fails").write_text("", encoding="utf-8")
    done, calls = pub()
    assert done.returncode != 0 and "non è tornato sano dopo il nuovo compose.yaml" in done.stdout + done.stderr
    (pub.stubs / "update-fails").unlink()
    done, calls = pub()
    out = done.stdout + done.stderr
    assert done.returncode == 0, out
    assert "update" in steps(calls) and "motore dev: invariato" not in out
    assert "fatto=compose" in pub.state().splitlines()

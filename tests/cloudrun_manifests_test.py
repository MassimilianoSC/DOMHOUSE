"""P-66: the two Cloud Run manifests of the BFF stay aligned. bff/cloudrun.yaml (prod) went unpublished from 15 to 20
October while staging gained variables (FCM on, MOCK_TIME_SCALE): every variable and secret of one must be in the
other, and only the wanted differences remain. Read with regular expressions: no YAML library in the test setup."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGING = (ROOT / "bff" / "cloudrun.staging.yaml").read_text(encoding="utf-8")
PROD = (ROOT / "bff" / "cloudrun.yaml").read_text(encoding="utf-8")
# the values that must differ, and how (anything else: the same in both)
WANTED = {"APP_ENV": ("staging", "prod"), "INSTANCE_MODE": ("mock", "real")}


def env(manifest: str) -> dict[str, str]:
    """name -> value (or "secret:<name>") of the container's environment."""
    out = {}
    for m in re.finditer(r"^\s*- name: (\w+)[^\n]*\n\s*(value: ?(.*)|valueFrom:\s*\n\s*secretKeyRef:\s*\n\s*name: ([\w-]+))",
                         manifest, re.MULTILINE):
        name, value, secret = m.group(1), m.group(3), m.group(4)
        out[name] = f"secret:{secret}" if secret else (value or "").split("#")[0].strip().strip('"')
    return out


def annotation(manifest: str, key: str) -> str | None:
    m = re.search(rf"^\s*{re.escape(key)}: ['\"]?([^'\"\n#]*)", manifest, re.MULTILINE)
    return m.group(1).strip() if m else None


def test_same_variables_and_secrets():
    staging, prod = env(STAGING), env(PROD)
    assert set(staging) == set(prod), f"only staging: {set(staging) - set(prod)}; only prod: {set(prod) - set(staging)}"
    for name in staging:
        if name in WANTED:
            assert (staging[name], prod[name]) == WANTED[name], name
        else:
            assert staging[name] == prod[name], f"{name}: staging {staging[name]!r}, prod {prod[name]!r}"


def test_wanted_differences_of_prod():
    assert annotation(PROD, "run.googleapis.com/vpc-access-egress") == "private-ranges-only"
    assert "your-vpc-network" in PROD and "your-vpc-subnet" in PROD          # filled by deploy.sh (VPC_NETWORK, VPC_SUBNET)
    assert "network-interfaces" not in STAGING                              # staging has no VPC egress (D-28)
    for key in ("autoscaling.knative.dev/minScale", "autoscaling.knative.dev/maxScale", "run.googleapis.com/cpu-throttling",
                "run.googleapis.com/startup-cpu-boost"):
        assert annotation(STAGING, key) == annotation(PROD, key), key
    # one instance: the demonstration apartments keep their state in the BFF's memory (D-97), pushes not doubled (D-35)
    assert annotation(PROD, "autoscaling.knative.dev/maxScale") == "1"


def test_the_bff_writes_no_access_log_of_its_own():
    """P-71 (D-142): uvicorn's access log off; Cloud Run already logs each request, and paths may carry personal data."""
    from pathlib import Path
    dockerfile = (Path(__file__).resolve().parent.parent / "bff" / "Dockerfile").read_text(encoding="utf-8")
    cmd = next(line for line in dockerfile.splitlines() if line.startswith("CMD"))
    assert "uvicorn" in cmd and "--no-access-log" in cmd

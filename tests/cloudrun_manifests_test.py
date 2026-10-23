"""P-66: the two Cloud Run manifests of the BFF stay aligned. bff/cloudrun.yaml (prod) went unpublished from 15 to 20
October while staging gained variables (FCM on, MOCK_TIME_SCALE): every variable and secret of one must be in the
other, and only the wanted differences remain. Read with regular expressions: no YAML library in the test setup."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGING = (ROOT / "bff" / "cloudrun.staging.yaml").read_text(encoding="utf-8")
PROD = (ROOT / "bff" / "cloudrun.yaml").read_text(encoding="utf-8")
# the values that must differ, and how (anything else: the same in both)
WANTED = {"APP_ENV": ("staging", "prod"), "FIRESTORE_DATABASE": ("staging", "(default)"),     # P-67 (D-136)
          "CORS_ORIGINS": ("https://your-staging-site.web.app,https://your-staging-site.firebaseapp.com",
                           "https://your-gcp-project-id.web.app,https://your-gcp-project-id.firebaseapp.com"),
          "APP_PUBLIC_URL": ("https://your-staging-site.web.app", "https://your-gcp-project-id.web.app")}


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


def test_two_services_both_reaching_the_vm():
    """P-67 (D-136): staging is a service of its own, with the VM's dev engine reached as production reaches it."""
    assert re.search(r"^  name: domotica-bff$", PROD, re.MULTILINE)
    assert re.search(r"^  name: domotica-bff-staging$", STAGING, re.MULTILINE)
    for manifest in (PROD, STAGING):
        assert annotation(manifest, "run.googleapis.com/vpc-access-egress") == "private-ranges-only"
        assert "your-vpc-network" in manifest and "your-vpc-subnet" in manifest   # filled by deploy.sh
        assert env(manifest)["INSTANCE_MODE"] == "real"                     # mock:// works in every mode (D-97)
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


def test_d187_main_model_and_twin_on_another_model_in_both():
    """D-187: gemini-3.5-flash with its prices, the twin on gemini-3.5-flash-lite after 3 s with its prices, reasoning
    off, in staging and production; the BFF reads them (bff/config.py), in its own process."""
    import json
    import os
    import subprocess
    import sys

    want = {"AI_MODEL": "google/gemini-3.5-flash", "AI_PRICE_IN_EUR_PER_M": "1.50", "AI_PRICE_OUT_EUR_PER_M": "9.00",
            "AI_PRICE_CACHED_EUR_PER_M": "0.15", "AI_THINKING_BUDGET": "0", "AI_TWIN_MODEL": "google/gemini-3.5-flash-lite",
            "AI_HEDGE_AFTER_S": "3", "AI_TWIN_PRICE_IN_EUR_PER_M": "0.30", "AI_TWIN_PRICE_OUT_EUR_PER_M": "2.50",
            "AI_TWIN_PRICE_CACHED_EUR_PER_M": "0.03"}
    for manifest in (STAGING, PROD):
        assert {k: env(manifest)[k] for k in want} == want
    code = ("import json; from bff import ai_gateway; from bff.config import get_settings; s = get_settings(); "
            "print(json.dumps([s.ai_model, s.ai_twin_model, s.ai_hedge_after_s, s.ai_thinking_budget, s.ai_api, "
            "s.ai_location, ai_gateway.prices(), ai_gateway.prices(twin=True)]))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env={**os.environ, **want, "APP_ENV": "dev"},
                         capture_output=True, text=True, timeout=60)
    assert json.loads(out.stdout) == ["google/gemini-3.5-flash", "google/gemini-3.5-flash-lite", 3.0, 0, "nativo", "eu",
                                      [1.5, 9.0, 0.15], [0.3, 2.5, 0.03]], out.stderr

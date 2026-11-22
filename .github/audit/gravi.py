"""Known defects of the libraries, for the CI job «difetti-noti» (item 50 of cose-da-fare.md, answer 1222 = a).

It reads what pip-audit (server and engine) and yarn audit (site) found, prints every defect with its severity, and
exits 1 only when one is high or critical: the others are printed and the CI stays green.

    python .github/audit/gravi.py --pip pip-audit.json --yarn yarn-audit.json

- pip-audit gives the advisories without a severity: it is read from the OSV database (api.osv.dev), the record of the
  advisory or of its GitHub alias (GHSA-…), field database_specific.severity. When OSV does not answer, or has no
  severity, the defect is printed as «non classificato» and does not turn the CI red (the line says to look at it).
- yarn audit (yarn 1, --json) gives one line per advisory with its severity, and a summary.
- An audit that did not answer (no summary from yarn, no list from pip-audit) never passes as «nothing found»: exit 2.

Standard library only: the job installs nothing but pip-audit.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

SERIOUS = {"high", "critical"}
OSV_URL = "https://api.osv.dev/v1/vulns/{}"
LABEL = {"critical": "CRITICO", "high": "GRAVE", "moderate": "medio", "medium": "medio", "low": "basso", "info": "info", None: "non classificato"}


def osv_severity(vuln_id: str, aliases: list[str], fetch=None) -> str | None:
    """«low», «moderate», «high», «critical» from the GitHub advisory in OSV; None when it cannot be known."""
    fetch = fetch or _fetch_json
    for candidate in [vuln_id, *[a for a in aliases if a.startswith("GHSA-")]]:
        record = fetch(OSV_URL.format(candidate))
        severity = ((record or {}).get("database_specific") or {}).get("severity")
        if isinstance(severity, str) and severity:
            return severity.lower()
    return None


def _fetch_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=20) as answer:  # noqa: S310 - fixed https host
            return json.load(answer)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def pip_findings(report: dict, fetch=None) -> list[dict]:
    if not isinstance(report.get("dependencies"), list):
        raise NoAnswer("pip-audit non ha dato l'elenco delle librerie")
    found = []
    for dep in report.get("dependencies", []):
        for v in dep.get("vulns", []):
            found.append({
                "where": "python",
                "package": f"{dep.get('name')}=={dep.get('version')}",
                "id": v.get("id"),
                "severity": osv_severity(v.get("id", ""), v.get("aliases", []), fetch),
                "fix": ", ".join(v.get("fix_versions", [])) or "nessuna",
            })
    return found


class NoAnswer(Exception):
    """The audit did not run to the end (registry not reachable, wrong file): never read as «nothing found»."""


def yarn_findings(lines: list[str]) -> list[dict]:
    found, seen, summary = [], set(), False
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        summary = summary or item.get("type") == "auditSummary"
        if item.get("type") != "auditAdvisory":
            continue
        adv = item["data"]["advisory"]
        key = adv.get("github_advisory_id") or adv.get("id")
        if key in seen:  # yarn prints one line per path to the same advisory
            continue
        seen.add(key)
        found.append({
            "where": "sito",
            "package": f"{adv.get('module_name')} {adv.get('vulnerable_versions', '')}".strip(),
            "id": adv.get("github_advisory_id") or str(adv.get("id")),
            "severity": (adv.get("severity") or "").lower() or None,
            "fix": adv.get("patched_versions") or "nessuna",
        })
    if not summary:
        raise NoAnswer("yarn audit non ha dato il riepilogo: il registro npm non ha risposto?")
    return found


def report(findings: list[dict]) -> int:
    order = {"critical": 0, "high": 1, "moderate": 2, "medium": 2, "low": 3, "info": 4, None: 5}
    findings = sorted(findings, key=lambda f: (order.get(f["severity"], 5), f["where"], f["package"]))
    if not findings:
        print("Nessun difetto noto nelle librerie.")
        return 0
    for f in findings:
        print(f"{LABEL.get(f['severity'], f['severity']):>16}  {f['where']:<6}  {f['package']}  {f['id']}  (corretto in: {f['fix']})")
    serious = [f for f in findings if f["severity"] in SERIOUS]
    unknown = [f for f in findings if f["severity"] is None]
    print(f"\nDifetti noti: {len(findings)}; gravi o critici: {len(serious)}; non classificati: {len(unknown)}.")
    if unknown:
        print("I non classificati non fanno diventare rossa la CI: guardarli nel collegamento dell'avviso.")
    if serious:
        print("CI rossa: ci sono difetti gravi o critici. Si aggiorna la libreria (o1), con le prove.")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pip", action="append", default=[], help="JSON of pip-audit --format json")
    ap.add_argument("--yarn", action="append", default=[], help="output of yarn audit --json")
    args = ap.parse_args(argv)
    findings: list[dict] = []
    try:
        for path in args.pip:
            with open(path, encoding="utf-8") as f:
                findings += pip_findings(json.load(f))
        for path in args.yarn:
            with open(path, encoding="utf-8") as f:
                findings += yarn_findings(f.read().splitlines())
    except (NoAnswer, OSError, json.JSONDecodeError) as e:
        print(f"Controllo non riuscito, da rilanciare: {e}")
        return 2
    return report(findings)


if __name__ == "__main__":
    sys.exit(main())

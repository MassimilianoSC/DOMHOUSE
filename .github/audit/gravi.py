"""Known defects of the libraries, for the CI job «difetti-noti» (item 50 of cose-da-fare.md, answer 1222 = a).

It reads what pip-audit (server and engine) and yarn audit (site) found, prints every defect with its severity, and
exits 1 only when one is high or critical and not accepted: the others are printed and the CI stays green.

    python .github/audit/gravi.py --pip pip-audit.json --yarn yarn-audit.json --accettati .github/audit/accettati.yml

- pip-audit gives the advisories without a severity: it is read from the OSV database (api.osv.dev), the record of the
  advisory or of one of its aliases (GitHub GHSA-… first), field database_specific.severity. OSV not answering (network,
  rate limit, 5xx) is «da rilanciare», exit 2, never green (review D-1); OSV answering without a severity is
  «non classificato», printed, and does not turn the CI red.
- Libraries pip-audit skipped (skip_reason) are printed as «non controllate» (review D-2).
- yarn audit (yarn 1, --json) gives one line per advisory with its severity, and a summary.
- An audit that did not answer (no summary from yarn, no list from pip-audit) never passes as «nothing found»: exit 2.
- Accepted advisories (answer 1245 = a), .github/audit/accettati.yml: each entry has the advisory's id, the library,
  the day it was added, the expiry (at most 30 days after it) and a reason. Accepted and not expired: printed with its
  expiry and reason, it does not turn the CI red; expired, it counts again by itself. A wrong entry (no reason, more
  than 30 days, a date that is not one) turns the CI red.

Only the standard library and PyYAML (for the accepted list).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request

SERIOUS = {"high", "critical"}
OSV_URL = "https://api.osv.dev/v1/vulns/{}"
MAX_ACCEPT_DAYS = 30
LABEL = {"critical": "CRITICO", "high": "GRAVE", "moderate": "medio", "medium": "medio", "low": "basso", "info": "info", None: "non classificato"}


class NoAnswer(Exception):
    """The audit did not run to the end (registry or OSV not reachable, wrong file): never read as «nothing found»."""


class BadAccepted(Exception):
    """The list of accepted advisories has a wrong entry: the CI is red until it is corrected."""


def osv_severity(vuln_id: str, aliases: list[str], fetch=None) -> str | None:
    """«low», «moderate», «high», «critical» from OSV; None when OSV knows the advisory but gives no severity.
    Raises NoAnswer when OSV does not answer (review D-1)."""
    fetch = fetch or _fetch_json
    ghsa = [a for a in aliases if a.startswith("GHSA-")]
    others = [a for a in aliases if not a.startswith("GHSA-")]
    for candidate in [vuln_id, *ghsa, *others]:
        record = fetch(OSV_URL.format(candidate))
        severity = ((record or {}).get("database_specific") or {}).get("severity")
        if isinstance(severity, str) and severity:
            return severity.lower()
    return None


def _fetch_json(url: str) -> dict | None:
    """The OSV record, or None when OSV has none (404). Any other failure is OSV not answering: NoAnswer."""
    try:
        with urllib.request.urlopen(url, timeout=20) as answer:  # noqa: S310 - fixed https host
            return json.load(answer)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise NoAnswer(f"OSV ha risposto {e.code} per {url}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        raise NoAnswer(f"OSV non risponde ({e.__class__.__name__}) per {url}") from e


def pip_findings(report: dict, fetch=None) -> tuple[list[dict], list[str]]:
    """The defects, and the libraries pip-audit skipped (with why)."""
    if not isinstance(report.get("dependencies"), list):
        raise NoAnswer("pip-audit non ha dato l'elenco delle librerie")
    found, skipped = [], []
    for dep in report["dependencies"]:
        if dep.get("skip_reason"):
            skipped.append(f"{dep.get('name')}: {dep.get('skip_reason')}")
            continue
        for v in dep.get("vulns", []):
            found.append({
                "where": "python",
                "name": str(dep.get("name") or ""),
                "package": f"{dep.get('name')}=={dep.get('version')}",
                "id": v.get("id"),
                "aliases": list(v.get("aliases", [])),
                "severity": osv_severity(v.get("id", ""), v.get("aliases", []), fetch),
                "fix": ", ".join(v.get("fix_versions", [])) or "nessuna",
            })
    return found, skipped


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
            "name": str(adv.get("module_name") or ""),
            "package": f"{adv.get('module_name')} {adv.get('vulnerable_versions', '')}".strip(),
            "id": adv.get("github_advisory_id") or str(adv.get("id")),
            "aliases": list(adv.get("cves") or []),
            "severity": (adv.get("severity") or "").lower() or None,
            "fix": adv.get("patched_versions") or "nessuna",
        })
    if not summary:
        raise NoAnswer("yarn audit non ha dato il riepilogo: il registro npm non ha risposto?")
    return found


def _day(value, field: str, n: int) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as e:
        raise BadAccepted(f"voce {n}: «{field}» non è una data (AAAA-MM-GG): {value!r}") from e


def load_accepted(data, today: dt.date) -> list[dict]:
    """The entries of accettati.yml (already read as YAML), checked. Raises BadAccepted for a wrong one."""
    items = (data or {}).get("accettati") or []
    if not isinstance(items, list):
        raise BadAccepted("«accettati» deve essere un elenco")
    accepted = []
    for n, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise BadAccepted(f"voce {n}: non è una voce con id, libreria, inserito, scadenza, motivo")
        missing = [k for k in ("id", "libreria", "inserito", "scadenza", "motivo") if not str(item.get(k) or "").strip()]
        if missing:
            raise BadAccepted(f"voce {n}: manca {', '.join(missing)}")
        added = _day(item["inserito"], "inserito", n)
        until = _day(item["scadenza"], "scadenza", n)
        if added > today:
            raise BadAccepted(f"voce {n} ({item['id']}): «inserito» è nel futuro ({added.isoformat()})")
        if until < added or (until - added).days > MAX_ACCEPT_DAYS:
            raise BadAccepted(f"voce {n} ({item['id']}): la scadenza deve essere al massimo {MAX_ACCEPT_DAYS} giorni dopo l'inserimento")
        accepted.append({"id": str(item["id"]).strip(), "libreria": str(item["libreria"]).strip().lower(), "until": until, "motivo": str(item["motivo"]).strip()})
    return accepted


def _match(finding: dict, accepted: list[dict]) -> dict | None:
    ids = {finding["id"], *finding.get("aliases", [])}
    for a in accepted:
        if a["id"] in ids and a["libreria"] == finding.get("name", "").lower():
            return a
    return None


def report(findings: list[dict], skipped: list[str] | None = None, accepted: list[dict] | None = None, today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    accepted = accepted or []
    skipped = skipped or []
    order = {"critical": 0, "high": 1, "moderate": 2, "medium": 2, "low": 3, "info": 4, None: 5}
    findings = sorted(findings, key=lambda f: (order.get(f["severity"], 5), f["where"], f["package"]))
    for s in skipped:
        print(f"{'non controllata':>16}  python  {s}")
    if not findings:
        print("Nessun difetto noto nelle librerie." + (f" Librerie non controllate: {len(skipped)}." if skipped else ""))
        return 0
    serious, kept = [], []
    for f in findings:
        line = f"{LABEL.get(f['severity'], f['severity']):>16}  {f['where']:<6}  {f['package']}  {f['id']}  (corretto in: {f['fix']})"
        a = _match(f, accepted)
        if a and a["until"] >= today:
            line += f"  accettato fino al {a['until'].strftime('%d/%m/%Y')}, motivo: {a['motivo']}"
            kept.append(f)
        else:
            if a:
                line += f"  accettazione scaduta il {a['until'].strftime('%d/%m/%Y')}"
            if f["severity"] in SERIOUS:
                serious.append(f)
        print(line)
    unknown = [f for f in findings if f["severity"] is None]
    print(f"\nDifetti noti: {len(findings)}; gravi o critici non accettati: {len(serious)}; accettati: {len(kept)}; "
          f"non classificati: {len(unknown)}; librerie non controllate: {len(skipped)}.")
    if unknown:
        print("I non classificati non fanno diventare rossa la CI: guardarli nel collegamento dell'avviso.")
    if serious:
        print("CI rossa: ci sono difetti gravi o critici. Si aggiorna la libreria, con le prove (oppure, per al massimo "
              "30 giorni, si accetta l'avviso in .github/audit/accettati.yml con il motivo).")
        return 1
    return 0


def main(argv: list[str] | None = None, today: dt.date | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pip", action="append", default=[], help="JSON of pip-audit --format json")
    ap.add_argument("--yarn", action="append", default=[], help="output of yarn audit --json")
    ap.add_argument("--accettati", help="the list of accepted advisories (YAML)")
    args = ap.parse_args(argv)
    today = today or dt.date.today()
    try:
        accepted = []
        if args.accettati:
            import yaml  # only for the accepted list

            with open(args.accettati, encoding="utf-8") as f:
                accepted = load_accepted(yaml.safe_load(f), today)
    except (BadAccepted, OSError) as e:
        print(f"Elenco degli avvisi accettati da correggere: {e}")
        return 1
    findings: list[dict] = []
    skipped: list[str] = []
    try:
        for path in args.pip:
            with open(path, encoding="utf-8") as f:
                found, skip = pip_findings(json.load(f))
            findings += found
            skipped += skip
        for path in args.yarn:
            with open(path, encoding="utf-8") as f:
                findings += yarn_findings(f.read().splitlines())
    except (NoAnswer, OSError, json.JSONDecodeError) as e:
        print(f"Controllo non riuscito, da rilanciare: {e}")
        return 2
    return report(findings, skipped, accepted, today)


if __name__ == "__main__":
    sys.exit(main())

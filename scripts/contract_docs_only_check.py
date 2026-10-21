"""P-63 (D-107): proof that a new version of contract/openapi.yaml changes only documentation.

    python scripts/contract_docs_only_check.py <old openapi.yaml | git:<ref>> <new openapi.yaml>
    python scripts/contract_docs_only_check.py git:71734f7 contract/openapi.yaml

From both versions it removes what is documentation: every description, summary, example and examples, every
extension key x-* (x-youssouf, x-motore, x-features, ...) and info.version. What remains (paths, methods, parameters,
schemas, types, enums, required fields, responses, security) must be identical, or the script lists the differences
and exits 1. A key named like those inside a schema's "properties" is a field of the contract (e.g. the
"description" of an Approval) and is kept. Needs PyYAML (pip install pyyaml).
"""
import subprocess
import sys
from pathlib import Path

DOC_KEYS = {"description", "summary", "example", "examples"}


def load(source: str):
    try:
        import yaml
    except ImportError:
        sys.exit("serve PyYAML: pip install pyyaml")
    if source.startswith("git:"):
        root = Path(__file__).resolve().parent.parent
        text = subprocess.run(["git", "-C", str(root), "show", f"{source[4:]}:contract/openapi.yaml"],
                              check=True, capture_output=True, text=True, encoding="utf-8").stdout
    else:
        text = Path(source).read_text(encoding="utf-8")
    return yaml.safe_load(text)


def strip(node, parent_key: str | None = None):
    """The tree without documentation; under "properties" every key is a field and stays."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            documentation = key in DOC_KEYS or (isinstance(key, str) and key.startswith("x-"))
            if documentation and parent_key != "properties":
                continue
            out[key] = strip(value, key)
        return out
    if isinstance(node, list):
        return [strip(v, parent_key) for v in node]
    return node


def differences(old, new, path: str = "") -> list[str]:
    if isinstance(old, dict) and isinstance(new, dict):
        out = []
        for key in sorted(set(old) | set(new), key=str):
            here = f"{path}/{key}"
            if key not in new:
                out.append(f"{here}: solo nella versione vecchia")
            elif key not in old:
                out.append(f"{here}: solo nella versione nuova")
            else:
                out += differences(old[key], new[key], here)
        return out
    if isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            return [f"{path}: elenco di {len(old)} elementi diventato di {len(new)}"]
        return [d for i, (a, b) in enumerate(zip(old, new)) for d in differences(a, b, f"{path}[{i}]")]
    return [] if old == new else [f"{path}: {old!r} -> {new!r}"]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    old, new = (load(a) for a in argv)
    old_version, new_version = old.get("info", {}).get("version"), new.get("info", {}).get("version")
    old_tree, new_tree = strip(old), strip(new)
    for tree in (old_tree, new_tree):
        tree.get("info", {}).pop("version", None)
    found = differences(old_tree, new_tree)
    if found:
        print(f"NON solo documentazione: {len(found)} differenze fra {old_version} e {new_version}")
        for line in found[:200]:
            print(" ", line)
        return 1
    print(f"Solo documentazione: {old_version} -> {new_version}, alberi identici dopo aver tolto description, "
          f"summary, example(s), x-* e info.version")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

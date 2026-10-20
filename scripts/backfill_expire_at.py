"""P-54 (D-94), once: give `expire_at` to the Firestore documents saved before lot 11, with the same rules the BFF uses
when it writes them (bff/retention.py). Without --apply it only reads and counts; with --apply it writes the field only
where it is missing, so it can be run again safely. The TTL policies themselves are created with gcloud (see
bff/retention.py and the lot 11 notes); without them the field is simply ignored.

    REPOSITORY=firestore GCP_PROJECT_ID=<progetto> python scripts/backfill_expire_at.py            # reads, counts
    REPOSITORY=firestore GCP_PROJECT_ID=<progetto> python scripts/backfill_expire_at.py --apply    # writes where missing
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def _collections(repo):
    """(collection group name, Firestore collection) pairs; "audit" is a subcollection under every organisation."""
    from bff import retention

    for name in retention.COLLECTIONS:
        if name == "audit":
            async for t in repo._col("tenants").stream():
                yield name, t.reference.collection("audit")
        else:
            yield name, repo._col(name)


async def backfill(repo, apply: bool) -> dict[str, list[int]]:
    """{collection group: [documents without expire_at, documents written]}."""
    from bff import retention

    out: dict[str, list[int]] = {name: [0, 0] for name in retention.COLLECTIONS}
    async for name, col in _collections(repo):
        async for doc in col.stream():
            data = doc.to_dict() or {}
            if retention.FIELD in data:
                continue
            out[name][0] += 1
            if apply:
                await doc.reference.update({retention.FIELD: retention.COLLECTIONS[name](data)})
                out[name][1] += 1
    return out


def _firestore_repository():
    from bff.config import get_settings
    from bff.repository import get_repository

    if get_settings().repository != "firestore":
        raise SystemExit("Lancialo con REPOSITORY=firestore GCP_PROJECT_ID=<progetto>: il repository in memoria non ha nulla da aggiornare")
    return get_repository()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true", help="scrive expire_at dove manca (senza: legge e conta soltanto)")
    a = p.parse_args()
    counts = asyncio.run(backfill(_firestore_repository(), a.apply))   # one event loop for the async client
    for name, (missing, written) in counts.items():
        print(f"{name:16} senza expire_at: {missing:5}" + (f"   scritti: {written}" if a.apply else ""))
    total = sum(m for m, _ in counts.values())
    print("Nessun documento da aggiornare." if total == 0 else
          (f"Aggiornati {total} documenti." if a.apply else f"{total} documenti senza expire_at: rilancia con --apply."))


if __name__ == "__main__":
    main()

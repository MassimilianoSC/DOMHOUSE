"""scripts/list_demos.py (P-67, D-136): the demonstrations of today, read only, on the memory repository's seed."""
import asyncio
import importlib.util
from pathlib import Path

from bff.repository import get_repository

ROOT = Path(__file__).resolve().parent.parent


def _script():
    spec = importlib.util.spec_from_file_location("list_demos", ROOT / "scripts" / "list_demos.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_demonstrations_their_people_and_what_was_changed():
    repo = get_repository()
    before = asyncio.run(repo.list_apartments())
    text = "\n".join(asyncio.run(_script().collect(repo)))
    demos = [a for a in before if a.instance_url.startswith("mock://")]
    assert demos and all(f"({a.apartment_id})" in text for a in demos)
    assert "dimostrativi visti:" in text and "azioni amministrative registrate sui dimostrativi" in text
    assert "Regole e stati dei dimostrativi" in text
    assert asyncio.run(repo.list_apartments()) == before                  # nothing written

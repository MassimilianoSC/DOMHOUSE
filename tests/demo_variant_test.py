"""P-72 (D-154): the demonstration's variant written in its link, mock://builtin?variante=vuoto|occupato. The BFF
reads it, refuses an unknown one when the link is saved, sends it to the built-in demonstration engine as
X-Demo-Variant; that engine uses it when it builds the apartment (first call, «Ripristina»). Without a variant the rule
before P-72. On the VM (CONNECTOR=simulated) the same choice is the setting DEMO_VARIANT. In-process."""
import asyncio

import httpx
import pytest

from bff import instances
from bff.mock_instance.app import create_mock_app
from bff.repository import get_repository
from engine import core
from engine.config import ConfigError, load_config
from engine.connector.simulated import make_connector

KEY = "k" * 32


def run(coro):
    return asyncio.run(coro)


def test_the_variant_in_the_link():
    assert instances.demo_variant("mock://builtin?variante=vuoto") == "vuoto"
    assert instances.demo_variant(" mock://builtin?variante=Occupato ") == "occupato"
    assert instances.demo_variant("mock://builtin") is None
    assert instances.demo_variant("http://10.0.0.5:8080?variante=vuoto") is None       # only on a demonstration
    assert instances.instance_url_problem("mock://builtin?variante=vuoto") is None
    assert instances.instance_url_problem("mock://builtin?variante=pieno") == instances.MSG_BAD_VARIANT


def test_the_header_only_towards_the_demonstration_engine():
    apt = run(get_repository().get_apartment("apt-rimini-01"))
    h = run(instances.instance_headers(apt.model_copy(update={"instance_url": "mock://builtin?variante=vuoto"}), "system:prova"))
    assert h["X-Demo-Variant"] == "vuoto"
    assert "X-Demo-Variant" not in run(instances.instance_headers(apt, "system:prova"))   # mock://builtin, no variant


async def mode_of(app, apartment_id, variant=None):
    headers = {"X-API-Key": KEY, "X-Actor": "system:prova", "X-Correlation-Id": "11111111-1111-1111-1111-111111111111"}
    if variant:
        headers["X-Demo-Variant"] = variant
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/{apartment_id}/api/v1/apartment", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["mode"], r.json()["occupancy"]


def test_the_demonstration_engine_builds_the_apartment_in_its_variant_and_again_after_reset():
    app = create_mock_app(KEY)
    registry = app.state.registry

    async def scenario():
        out = [await mode_of(app, "apt-demo-1", "vuoto"),            # an id without «bologna», empty and cold
               await mode_of(app, "apt-bologna-9", "occupato"),      # the choice wins over the old rule
               await mode_of(app, "apt-demo-2"),                     # no variant: the rule before P-72 (occupied)
               await mode_of(app, "apt-bologna-8")]                  # (empty for «bologna»)
        out.append(await mode_of(app, "apt-demo-1", "occupato"))     # a built apartment does not change by itself
        registry.reset("apt-demo-1")                                 # «Ripristina»
        out.append(await mode_of(app, "apt-demo-1", "occupato"))
        for sim in registry.sims.values():
            for task in [sim.loop_task, sim.consumer_task, *sim.tasks]:
                if task is not None and not task.done():
                    task.cancel()
        return out
    modes = [m for m, _ in run(scenario())]
    assert modes == ["empty", "comfort", "comfort", "empty", "empty", "comfort"]


def test_demo_variant_on_the_vm():
    base = {"APARTMENT_ID": "apt-vm-01", "API_KEY": "k" * 16, "CONNECTOR": "simulated"}
    config = load_config({**base, "DEMO_VARIANT": "Vuoto"})
    assert config.settings["DEMO_VARIANT"] == "vuoto"
    connector = make_connector(config.for_connector())
    assert connector.variant == 1
    e = core.ApartmentEngine("apt-vm-01", connector, seed=True, settings=config.settings)
    assert e.mode == "empty"
    assert make_connector(load_config(base).for_connector()).variant == 0         # «auto»: by the id, as before
    with pytest.raises(ConfigError, match="DEMO_VARIANT must be one of: auto, vuoto, occupato"):
        load_config({**base, "DEMO_VARIANT": "pieno"})

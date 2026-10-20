"""instance_url normalization and checks (D-28), in both INSTANCE_MODE values; no BFF needed."""
import dataclasses

import pytest

from bff import instances
from bff.config import get_settings
from bff.repository import Apartment


@pytest.fixture
def mode(monkeypatch):
    def set_mode(value: str):
        settings = dataclasses.replace(get_settings(), instance_mode=value)
        monkeypatch.setattr(instances, "get_settings", lambda: settings)
    return set_mode


@pytest.mark.parametrize("raw, expected", [
    ("mock://builtin", "mock://builtin"),
    ("  MOCK://builtin ", "mock://builtin"),
    ("Mock://builtin", "mock://builtin"),
    ("HTTPS://Host.example:8443/x", "https://Host.example:8443/x"),
    ("10.198.0.2:8100", "http://10.198.0.2:8100"),
    ("domotica.esempio.it", "http://domotica.esempio.it"),
    ("", ""),
])
def test_normalize(raw, expected):
    assert instances.normalize_instance_url(raw) == expected


@pytest.mark.parametrize("raw", ["mock://builtin", " MOCK://builtin"])
def test_mock_mode_accepts_only_mock(mode, raw):
    mode("mock")
    assert instances.instance_url_problem(raw) is None


@pytest.mark.parametrize("raw", ["https://domotica.esempio.it", "http://10.198.0.2:8100", "10.198.0.2:8100", "mock", ""])
def test_mock_mode_refuses_the_rest(mode, raw):
    mode("mock")
    assert instances.instance_url_problem(raw) == instances.MSG_USE_MOCK


@pytest.mark.parametrize("raw", ["https://domotica.esempio.it", "http://10.198.0.2:8100", "10.198.0.2:8100", " HTTP://host ",
                                 "mock://builtin"])   # D-97: demonstration apartments also in production
def test_real_mode_accepts_http(mode, raw):
    mode("real")
    assert instances.instance_url_problem(raw) is None


@pytest.mark.parametrize("raw", ["ftp://host", "http://", "http://host:porta", ""])
def test_real_mode_refuses_the_rest(mode, raw):
    mode("real")
    assert instances.instance_url_problem(raw) == instances.MSG_BAD_URL


def test_secret_name_always_derived_from_apartment_id(mode, monkeypatch):
    # P-36 S3 (D-60): a stored instance_secret_name (e.g. the SMTP password's secret) must never be read
    import asyncio
    mode("real")
    read = []
    monkeypatch.setattr(instances, "_read_secret", lambda name: read.append(name) or "k")
    instances._secret_cache.clear()
    apt = Apartment(apartment_id="apt-s3", tenant_id="t", name="x", instance_url="http://10.198.0.2:8100",
                    instance_secret_name="smtp-app-password")
    assert asyncio.run(instances.api_key(apt)) == "k"
    assert read == ["langbrain-api-key-apt-s3"]


def test_base_url_without_scheme_is_http(mode):
    mode("real")
    apt = Apartment(apartment_id="apt-x", tenant_id="t", name="x", instance_url="10.198.0.2", port=8100)
    assert instances.base_url(apt) == "http://10.198.0.2:8100/api/v1"


@pytest.mark.parametrize("url, port, key", [
    ("http://10.198.0.2:8101", None, "10.198.0.2:8101"),
    ("HTTP://10.198.0.2:8101/api/v1", 9999, "10.198.0.2:8101"),   # the URL's port wins, as in base_url
    ("http://10.198.0.2", 8101, "10.198.0.2:8101"),
    ("https://Motore.Esempio.it", None, "motore.esempio.it:443"),
    ("mock://builtin", None, None),
    (" MOCK://builtin", 8100, None),
])
def test_link_key(url, port, key):
    assert instances.link_key(url, port) == key

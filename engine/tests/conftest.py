"""The engine's tests never use the default data folder (/data/<apartment_id>, E-16 and E-17): it does not exist on the
CI runner, and on a PC it would leave folders behind. Every test that starts an engine on disk gives it a DATA_DIR in
tmp_path; one that forgets fails here and everywhere, because the default points to a folder that cannot be created."""
import pytest

from engine import config


@pytest.fixture(autouse=True)
def no_default_data_folder(monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("the default DATA_DIR is not for tests: set DATA_DIR to a folder in tmp_path")
    monkeypatch.setattr(config, "DEFAULT_DATA_ROOT", str(blocker))
    monkeypatch.delenv("DATA_DIR", raising=False)


@pytest.fixture(autouse=True)
def a_winter_day(monkeypatch):
    """Item 15 (rereading of o1-stagione, a6, 23 November): the heating season follows the date, so every test runs on
    a fixed winter day, never on today's (from 16 April to 14 October the boilers would stay on the frost protection).
    A test about the season sets its own day on the class or on the engine."""
    from datetime import date

    from engine import core
    monkeypatch.setattr(core.ApartmentEngine, "_today", lambda self: date(2026, 1, 15))
    monkeypatch.delenv("MOCK_TODAY", raising=False)

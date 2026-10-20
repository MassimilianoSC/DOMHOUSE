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

"""catalog.py: a valid catalog, every check, and no value in any message (connector.md §2.7, §5).

Every wrong value below contains SENTINEL: the message must name the device and the field, never repeat it.
"""
import copy
from pathlib import Path

import pytest

from engine.connector.interface import Room
from engine.connector.shelly import catalog as catalog_module
from engine.connector.shelly.catalog import CatalogError, load_catalog, parse_catalog
from engine.connector.shelly.offline import load_thresholds
from engine.connector.shelly.translate import PROFILES

SENTINEL = "VALORE-SEGRETO-7f3a"
THRESHOLDS = load_thresholds()

VALID = {
    "rooms": [{"room_id": "camera", "name": "Camera"}, {"room_id": "soggiorno", "name": "Soggiorno"}],
    "devices": [
        {"device_id": "dev-presa-camera", "label": "Presa stufetta", "room_id": "camera",
         "capabilities": {"switch": {}, "power_meter": {}},
         "shelly": {"id": "shellyplugmg3-000000000001", "type": "plug"}},
        {"device_id": "dev-presa-soggiorno", "label": "Presa lampada", "room_id": "soggiorno",
         "capabilities": {"switch": None},
         "shelly": {"id": "shellyplugmg3-000000000002", "type": "plug", "channel": 0, "offline_after_s": 45}},
    ],
}


def catalog_with(change) -> dict:
    data = copy.deepcopy(VALID)
    change(data)
    return data


def refused(data, *expected: str) -> str:
    with pytest.raises(CatalogError) as info:
        parse_catalog(data, THRESHOLDS)
    message = str(info.value)
    assert SENTINEL not in message, message
    error = info.value
    assert error.__cause__ is None and (error.__context__ is None or error.__suppress_context__), \
        "never the original exception"
    for part in expected:
        assert part in message, message
    return message


def dev(data, n=0) -> dict:
    return data["devices"][n]


# --- valid -------------------------------------------------------------------------------------------------------

def test_valid_catalog():
    cat = parse_catalog(VALID, THRESHOLDS)
    assert cat.rooms == (Room("camera", "Camera"), Room("soggiorno", "Soggiorno"))
    first, second = cat.devices
    assert (first.device_id, first.label, first.room_id) == ("dev-presa-camera", "Presa stufetta", "camera")
    assert first.capabilities == {"switch": {}, "power_meter": {}} and first.links == {}
    assert (first.shelly_id, first.device_type, first.channel) == ("shellyplugmg3-000000000001", "plug", 0)
    assert first.offline_after_s == THRESHOLDS.by_type["plug"]          # the type's threshold
    assert second.offline_after_s == 45.0 and second.capabilities == {"switch": {}}   # the override; None -> {}
    assert first.profile is PROFILES["PlugMG3"]
    assert set(cat.by_shelly_id()) == {"shellyplugmg3-000000000001", "shellyplugmg3-000000000002"}


def test_valid_links_between_devices(monkeypatch):
    """Links are checked across the catalog; no supported model has heating yet, so the profile check is relaxed."""
    monkeypatch.setattr(catalog_module, "profile_for_catalog", lambda *a: PROFILES["PlugMG3"])

    def change(d):
        d["devices"].append({"device_id": "dev-caldaia", "label": "Caldaia", "room_id": "soggiorno",
                             "capabilities": {"heating": {"setpoint_min": 7, "setpoint_max": 23}},
                             "links": {"sensor_device_id": "dev-sensore"},
                             "shelly": {"id": "shelly1g4-000000000003", "type": "relay"}})
        d["devices"].append({"device_id": "dev-sensore", "label": "Sensore", "room_id": "soggiorno",
                             "capabilities": {"temperature": {}}, "shelly": {"id": "shellyblu-0004", "type": "blu_ht"}})
    cat = parse_catalog(catalog_with(change), THRESHOLDS)
    boiler = cat.by_device_id()["dev-caldaia"]
    assert boiler.links == {"sensor_device_id": "dev-sensore"}
    assert boiler.capabilities["heating"] == {"setpoint_min": 7, "setpoint_max": 23}
    assert cat.by_device_id()["dev-sensore"].offline_after_s == THRESHOLDS.by_type["blu_ht"]


# --- structure ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("data, expected", [
    (SENTINEL, "must be a mapping"),
    ([SENTINEL], "must be a mapping"),
    ({"rooms": [], "devices": VALID["devices"]}, "rooms must be a non-empty list"),
    ({"rooms": VALID["rooms"], "devices": []}, "devices must be a non-empty list"),
    ({"rooms": VALID["rooms"], "devices": SENTINEL}, "devices must be a non-empty list"),
    ({**VALID, "secret": SENTINEL}, "unknown key"),
])
def test_wrong_structure(data, expected):
    refused(data, expected)


def test_room_errors():
    refused(catalog_with(lambda d: d["rooms"].append({"room_id": "camera", "name": "Altra"})),
            "catalog room camera", "room_id is repeated")
    refused(catalog_with(lambda d: d["rooms"][0].pop("name")), "catalog room camera", "name")
    refused(catalog_with(lambda d: d["rooms"][0].update(room_id=7)), "catalog room #1", "room_id")
    refused(catalog_with(lambda d: d["rooms"].__setitem__(0, SENTINEL)), "catalog room #1", "mapping")
    refused(catalog_with(lambda d: d["rooms"][0].update(colour=SENTINEL)), "catalog room camera", "unknown key")


# --- devices -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("change, expected", [
    (lambda d: d["devices"].append(copy.deepcopy(dev(d))), "device_id is repeated"),
    (lambda d: dev(d).update(room_id=SENTINEL), "room_id is not a room of the catalog"),
    (lambda d: dev(d).pop("room_id"), "room_id is missing"),
    (lambda d: dev(d).update(label=""), "label is missing"),
    (lambda d: dev(d).update(capabilities={}), "capabilities must be a non-empty mapping"),
    (lambda d: dev(d).update(capabilities=SENTINEL), "capabilities must be a non-empty mapping"),
    (lambda d: dev(d).update(capabilities={SENTINEL: {}}), "not one of the eight of the contract"),
    (lambda d: dev(d).update(capabilities={"switch": SENTINEL}), "capabilities.switch must be a mapping"),
    (lambda d: dev(d).update(links={SENTINEL: "dev-presa-soggiorno"}), "links has a key"),
    (lambda d: dev(d).update(links=SENTINEL), "links must be a mapping"),
    (lambda d: dev(d).update(links={"sensor_device_id": SENTINEL}), "links.sensor_device_id needs the capability heating"),
    (lambda d: dev(d).update(links={"confirmation_device_id": SENTINEL}),
     "links.confirmation_device_id needs the capability climate"),
    (lambda d: dev(d).update(api_token=SENTINEL), "unknown key (api_token)"),
    (lambda d: dev(d).pop("shelly"), "shelly section is missing"),
    (lambda d: dev(d).update(shelly=SENTINEL), "shelly section is missing or not a mapping"),
    (lambda d: dev(d)["shelly"].pop("id"), "shelly.id is missing"),
    (lambda d: dev(d)["shelly"].update(id=f"{SENTINEL}/x"), "shelly.id must be one MQTT topic level"),
    (lambda d: dev(d)["shelly"].update(id=f"{SENTINEL}+"), "shelly.id must be one MQTT topic level"),
    (lambda d: dev(d)["shelly"].update(id=f" {SENTINEL}"), "shelly.id must be one MQTT topic level"),
    (lambda d: dev(d)["shelly"].update(password=SENTINEL), "unknown key (password)"),
    (lambda d: dev(d)["shelly"].update(channel=SENTINEL), "shelly.channel must be an integer"),
    (lambda d: dev(d)["shelly"].update(channel=-1), "shelly.channel must be an integer"),
    (lambda d: dev(d)["shelly"].update(channel=True), "shelly.channel must be an integer"),
    (lambda d: dev(d)["shelly"].pop("type"), "shelly.type is missing"),
    (lambda d: dev(d)["shelly"].update(type=SENTINEL), "shelly.type is not one of the known device types"),
    (lambda d: dev(d)["shelly"].update(offline_after_s=SENTINEL), "shelly.offline_after_s"),
    (lambda d: dev(d)["shelly"].update(offline_after_s=-5), "greater than zero"),
    (lambda d: dev(d)["shelly"].update(offline_after_s=float("nan")), "finite"),
    (lambda d: dev(d)["shelly"].update(type="relay"), "not supported by any Shelly model"),
    (lambda d: dev(d).update(capabilities={"switch": {}, "temperature": {}}), "not supported by any Shelly model"),
], ids=lambda x: x if isinstance(x, str) else None)
def test_device_errors_name_device_and_field(change, expected):
    refused(catalog_with(change), "catalog device dev-presa-camera", expected)


def test_device_without_id():
    refused(catalog_with(lambda d: dev(d).pop("device_id")), "catalog device #1", "device_id is missing")
    refused(catalog_with(lambda d: d["devices"].__setitem__(0, SENTINEL)), "catalog device #1", "must be a mapping")


def test_shelly_id_repeated_names_the_other_device_not_the_id():
    data = catalog_with(lambda d: dev(d, 1)["shelly"].update(id=dev(d)["shelly"]["id"]))
    message = refused(data, "catalog device dev-presa-soggiorno", "shelly.id is the same as device dev-presa-camera")
    assert "shellyplugmg3" not in message


def test_unsupported_model_says_what_is_supported():
    message = refused(catalog_with(lambda d: dev(d)["shelly"].update(type="energy_meter")),
                      "not supported by any Shelly model")
    assert "Shelly Plug M Gen3 (type plug: power_meter, switch)" in message


@pytest.mark.parametrize("target_change, expected", [
    (lambda d: dev(d, 2)["links"].update(sensor_device_id=SENTINEL), "links.sensor_device_id is not a device of the catalog"),
    (lambda d: dev(d, 2)["links"].update(sensor_device_id="dev-presa-camera"),
     "links.sensor_device_id points to a device without temperature"),
    (lambda d: dev(d, 2)["links"].update(sensor_device_id="dev-caldaia"), "links.sensor_device_id points to the device itself"),
])
def test_link_targets(monkeypatch, target_change, expected):
    monkeypatch.setattr(catalog_module, "profile_for_catalog", lambda *a: PROFILES["PlugMG3"])

    def change(d):
        d["devices"].append({"device_id": "dev-caldaia", "label": "Caldaia", "room_id": "soggiorno",
                             "capabilities": {"heating": {}, "temperature": {}} if "itself" in expected else {"heating": {}},
                             "links": {}, "shelly": {"id": "shelly1g4-000000000003", "type": "relay"}})
        target_change(d)
    refused(catalog_with(change), "catalog device dev-caldaia", expected)


# --- the file ----------------------------------------------------------------------------------------------------

VALID_YAML = """\
rooms:
  - {room_id: camera, name: Camera}
devices:
  - device_id: dev-presa-camera
    label: Presa stufetta
    room_id: camera
    capabilities: {switch: {}, power_meter: {}}
    shelly: {id: shellyplugmg3-000000000001, type: plug, channel: 0, offline_after_s: 90}
"""


def test_load_valid_file(tmp_path: Path):
    path = tmp_path / "catalog.yaml"
    path.write_text(VALID_YAML, encoding="utf-8")
    cat = load_catalog(path, THRESHOLDS)
    assert [d.device_id for d in cat.devices] == ["dev-presa-camera"] and cat.devices[0].offline_after_s == 90.0


@pytest.mark.parametrize("content, expected", [
    (None, "catalog file not found"),
    (f"rooms: [{{room_id: camera, name: {SENTINEL}}}\ndevices: [\n".encode(), "not valid YAML (line"),
    (f"# {SENTINEL}\n".encode("utf-16"), "not valid UTF-8"),
    (b"", "must be a mapping"),
    (f"!!python/object/apply:os.system ['{SENTINEL}']\n".encode(), "not valid YAML"),
])
def test_wrong_files(tmp_path: Path, content, expected):
    path = tmp_path / f"catalog-{SENTINEL}.yaml"
    if content is not None:
        path.write_bytes(content)
    with pytest.raises(CatalogError) as info:
        load_catalog(path, THRESHOLDS)
    assert expected in str(info.value) and SENTINEL not in str(info.value)
    assert str(tmp_path) not in str(info.value)


def test_folder_instead_of_file(tmp_path: Path):
    with pytest.raises(CatalogError, match="is a folder"):
        load_catalog(tmp_path, THRESHOLDS)

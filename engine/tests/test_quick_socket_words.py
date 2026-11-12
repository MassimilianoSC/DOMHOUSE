"""D17 (P-83 review, gravity 2): the assistant's quick answer (when the model does not answer: timeout, unavailable,
monthly cap) took «luce» and «stufetta» as words for any socket: «accendi la luce» switched on the only socket (a
heater), «spegni la stufetta» would switch off a «Presa frigorifero». Now «luce» is not a socket, and a socket is chosen
only when a word of its own name is in the phrase. Scenarios of the independent verification (V-D17/test_d17.py),
inverted.

Run: python -m pytest engine/tests -q
"""
from engine import assistant, core
from engine.connector.simulated import SimulatedConnector

PRESA = "dev-presa-camera"                    # «Presa stufetta camera» in the simulated apartment


def quick(text: str, label: str | None = None):
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    if label:
        e.devices[PRESA]["label"] = label
    proposals: list[dict] = []
    ok = assistant.Assistant(e, None).quick_proposal(text, proposals)
    return ok, proposals


def test_the_light_is_not_a_socket():
    for text in ("accendi la luce", "spegni la luce", "accendi la luce in camera"):
        assert quick(text) == (False, []), text


def test_a_socket_needs_a_word_of_its_name():
    assert quick("spegni la stufetta", label="Presa frigorifero") == (False, [])
    ok, props = quick("spegni la presa frigorifero", label="Presa frigorifero")
    assert ok and props[0]["device_id"] == PRESA and props[0]["body"]["action"] == "turn_off"


def test_the_heater_by_its_name_still_works():
    ok, props = quick("accendi la stufetta in camera")
    assert ok and props[0]["device_id"] == PRESA and props[0]["body"]["action"] == "turn_on"
    ok, props = quick("spegni la presa")
    assert ok and props[0]["device_id"] == PRESA                            # «presa» is in its name

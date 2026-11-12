"""D20 (P-83 review, gravity 2): the rules' recognizer (bff/rule_proposals.py recognize, used before the model) took any
form of «spegnere» as «turn the rule off», and looked at it before the number: the site's own example «la finestra
aperta spegne dopo 10 minuti» (and the rule's very name, «Finestra aperta spegne il clima») turned the window rule off
instead of changing its minutes; «antigelo: non spegnere sotto 9 gradi» turned the frost protection off. Now a rule is
turned off only by a command («spegni», «spegnere», «disattiva», «togli»), with no number and no negation in the
phrase. Phrases of the independent verification (V-D20/prova_d20.py), inverted."""
import copy

import pytest

from bff import rule_proposals as rp
from engine.core import DEFAULT_RULES


def recognize(text):
    return rp.recognize(text, {"updated_at": "2026-11-11T00:00:00Z", "rules": copy.deepcopy(DEFAULT_RULES)})[0]


@pytest.mark.parametrize("text", ["la finestra aperta spegne dopo 10 minuti",          # the site's example
                                  "finestra aperta spegne il clima dopo 10 minuti",
                                  "finestra aperta 10 minuti"])
def test_the_window_rules_minutes_change_and_it_stays_on(text):
    assert recognize(text) == [{"rule_id": "window_open_off", "params": {"minutes": 10}}], text


def test_a_negation_never_turns_a_rule_off():
    patches = recognize("antigelo: non spegnere sotto 9 gradi")
    assert not any(p.get("enabled") is False for p in patches or [])


def test_a_number_with_spegni_is_a_value_not_an_off():
    patches = recognize("dopo il check-out spegni tutto dopo 45 minuti")
    assert not any(p.get("enabled") is False for p in patches or [])
    assert patches == [{"rule_id": "checkout_eco", "params": {"minutes_after": 45}}]


@pytest.mark.parametrize("text, rule", [("spegni la regola della finestra", "window_open_off"),
                                        ("disattiva l'antigelo", "frost_protection"),
                                        ("togli l'avviso offline", "offline_alert")])
def test_a_command_without_a_number_still_turns_it_off(text, rule):
    assert recognize(text) == [{"rule_id": rule, "enabled": False}], text

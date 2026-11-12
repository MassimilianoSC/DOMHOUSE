"""D19 (P-83 review, gravity 3): with the feature «rules» turned off for an apartment (or its organisation), the proxy
answers 501 to GET/PUT /rules, but the routes of the rules proposed by the assistant and of the copy ignored it: an
operator could change the rules through /rules/proposal and /apply, an admin could copy rules onto it. Now proposal,
apply and the copy's source answer 501 «Funzione non disponibile» as the proxy does, and a destination without it is
refused («non disponibile») and never written. (Whether «ask» turned off should also keep the model out of the
proposals is a product decision, not here.) Same harness as tests/rule_proposals_test.py."""
import asyncio
import sys
from pathlib import Path

import pytest

from bff.repository import get_repository

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rule_proposals_test import ADMIN, BOLOGNA, OPERATOR, RIMINI, apply, engines, propose, post, run  # noqa: E402,F401

WITHOUT_RULES = ["apartment", "devices", "commands", "energy", "schedule", "approvals", "decisions", "ask"]


@pytest.fixture
def no_rules_on_bologna():
    repo = get_repository()
    apt = run(repo.get_apartment(BOLOGNA))
    before = apt.enabled_features
    apt.enabled_features = WITHOUT_RULES
    run(repo.upsert_apartment(apt))
    yield
    apt = run(repo.get_apartment(BOLOGNA))
    apt.enabled_features = before
    run(repo.upsert_apartment(apt))


def test_proposal_and_apply_answer_501_and_nothing_is_written(engines, no_rules_on_bologna):
    r = propose("finestra aperta 10 minuti", who=OPERATOR)
    assert r.status_code == 501 and r.json()["error"] == "not_implemented"
    r = apply({"based_on": "x", "rules": [{"rule_id": "window_open_off", "params": {"minutes": 10}}]}, who=OPERATOR)
    assert r.status_code == 501
    assert engines.puts == []


def test_the_copy_neither_reads_from_nor_writes_to_an_apartment_without_rules(engines, no_rules_on_bologna):
    r = run(post(f"/app/apartments/{BOLOGNA}/rules/copy/preview", {"to": [RIMINI]}, ADMIN))
    assert r.status_code == 501                                           # the source has no rules
    preview = run(post(f"/app/apartments/{RIMINI}/rules/copy/preview", {"to": [BOLOGNA]}, ADMIN)).json()
    row = preview["targets"][0]
    assert row["status"] == "refused" and "non disponibile" in row["message"]
    out = run(post(f"/app/apartments/{RIMINI}/rules/copy", {"to": [BOLOGNA], "from_based_on": preview["from"]["based_on"],
                                                           "based_on": {BOLOGNA: "x"}}, ADMIN)).json()
    assert out["results"][0]["outcome"] == "refused" and engines.puts == []


def test_with_the_feature_on_as_before(engines):
    r = propose("finestra aperta 10 minuti", who=OPERATOR)
    assert r.status_code == 200

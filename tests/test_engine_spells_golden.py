"""Scripted cast scenarios against tests/golden.json["casts"] (synthetic worlds, always run).
Regenerate with tools/update_golden.py when a change of the cast, carrier or combat rules is intended."""

import json
import os

import pytest

from spell_scenarios import SCENARIOS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = json.load(open(os.path.join(ROOT, "tests", "golden.json")))["casts"]


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_scenario_matches_golden(name):
    got = json.loads(json.dumps(SCENARIOS[name]()))
    assert got == GOLD[name]


def test_scenario_facts():
    """The readable part of the goldens: what each scenario shows."""
    staff = GOLD["staff_kill"]
    assert staff["died"] and staff["mana"] == {} and staff["released"] == staff["started"] >= 3          # free casts until the target died
    runs_out = GOLD["mana_runs_out"]
    assert runs_out["started"] == 2 and runs_out["mana"] == {"1": 1} and runs_out["died"] == []         # the third cast never starts (7 - 2 * 3)
    mix = GOLD["melee_and_cast"]
    assert mix["released"] >= 2 and len(mix["damage"]) > mix["released"] and mix["ended"] is not None   # melee blows and spell hits in one log

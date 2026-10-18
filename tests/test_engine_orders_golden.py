"""Scripted order scenarios against tests/golden.json["orders"] (synthetic worlds, always run).
Regenerate with tools/update_golden.py when a change of the order or movement rules is intended."""

import json
import os

import pytest

from orders_scenarios import SCENARIOS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = json.load(open(os.path.join(ROOT, "tests", "golden.json")))["orders"]


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_scenario_matches_golden(name):
    got = json.loads(json.dumps(SCENARIOS[name]()))
    assert got == GOLD[name]


def test_scenario_facts():
    """The readable part of the goldens: what each scenario shows."""
    assert GOLD["walk_reorder"]["cells"] == {"1": [12, 24]}                   # the re-order replaced the first walk
    assert GOLD["unreachable"]["no_way"] == 1 and GOLD["unreachable"]["fallback_ring"] > 1
    assert GOLD["walk_reorder"]["no_way"] == GOLD["crossing_off"]["no_way"] == 0
    assert GOLD["crossing_off"]["cells"] != GOLD["crossing_on"]["cells"]      # off: fallbacks spread, on: the shape
    assert GOLD["crossing_off"]["hash"] != GOLD["crossing_on"]["hash"]

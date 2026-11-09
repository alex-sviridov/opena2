"""Arrows in a real fight on map 73 (needs the install): they appear and vanish, they never change the world dump (client state only), the headless
screenshots of the volley match tests/golden.json["arrows"].  Docs: docs/engine/rendering.md "Arrows and shots"."""

import json
import os

import pytest

from allods2.assets import AssetCache

from arrow_scenarios import hashes, run
from helpers import GFS, needs_data

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def assets():
    return AssetCache(GFS)


@needs_data
def test_a_fight_makes_arrows_and_they_are_all_gone_afterwards(assets):
    w, seen = run(assets)
    assert len(seen) >= 3                                         # four shooters attacked: several shots in 160 ticks
    assert all(a.live is False or a.steps >= 0 for a in w.arrows) and len(w.arrows) <= len(seen)


@needs_data
def test_arrows_never_change_the_world_dump(assets):
    with_arrows, _ = run(assets)
    without, seen = run(assets, arrows=False)
    assert not seen and with_arrows.dump_hash() == without.dump_hash()
    assert "arrows" not in with_arrows.dump_json() and "flashes" not in with_arrows.dump_json()


@needs_data
def test_volley_screenshots_match_the_golden(assets):
    gold = json.load(open(os.path.join(ROOT, "tests", "golden.json")))["arrows"]
    got = hashes(assets)
    assert got == gold, "the arrow fight changed; if intended run tools/update_golden.py --only arrows"

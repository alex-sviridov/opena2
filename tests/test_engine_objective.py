"""The objective run (phase K12, engine/objective.py): 45 of 46 campaign maps reach "Mission Complete" when the oracle makes their trigger conditions
true by world edits; map 77 is the known miss (the escorted unit dies to the leader's squad, which the oracle cannot fight)."""

import os

import pytest

from allods2.cli import campaign_maps
from engine import objective as O
from helpers import GFS, needs_data

pytestmark = needs_data

MISS = {"77": "lost"}


def names():
    return [os.path.basename(p).rsplit(".", 1)[0] for p in campaign_maps(GFS)] if GFS else []


@pytest.mark.parametrize("name", names())
def test_the_objective_run_of_every_map(name):
    r = O.run(name, GFS)
    assert "crash" not in r, r.get("crash")
    assert r["result"] == MISS.get(name, "won"), (r["result"], r["edits"], r["stuck"])


def test_the_run_is_deterministic():
    a, b = O.run("86", GFS), O.run("86", GFS)
    assert (a["result"], a["tick"], a["edits"]) == (b["result"], b["tick"], b["edits"])


def test_a_counter_chain_gets_one_edit_per_round():
    """Map 86: three triggers (hero / knight / Dina) increment one counter; firing them together overshoots the value the next one waits for."""
    r = O.run("86", GFS)
    assert r["result"] == "won" and len({e[0] for e in r["edits"]}) == len(r["edits"]), r["edits"]


def test_a_phased_out_unit_is_a_position_marker_for_distance_checks():
    """Map 93: unit 2027 is phased out at the start and no trigger brings it back; the distance checks use its cell, so the run still wins."""
    r = O.run("93", GFS)
    assert r["result"] == "won" and any("2027" in e[3] for e in r["edits"]), r["edits"]


def test_a_unit_the_script_phases_in_later_has_to_be_waited_for():
    """Map 42: the dragon is phased out until the script brings it in; killing it before is no edit at all."""
    r = O.run("42", GFS)
    assert r["result"] == "won" and r["tick"] > 32, r


def test_defeat_triggers_protect_the_units_they_watch():
    """Map 30: 'Ensure elder' fails the mission when the elder dies; the oracle keeps the unit at full health."""
    s = O.run("30", GFS)
    assert s["result"] == "won"

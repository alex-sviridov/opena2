"""Map coverage report (phase K0, engine/coverage.py): the statuses come from the trigger code, the verdicts and the step order from synthetic rows
(always run), and a few maps of the install (skipped without it)."""

import os

import pytest

from allods2.common import INSTALL
from engine import coverage as C
from helpers import needs_data


def _row(name, counts, crash=""):
    return {"map": name, "title": "", "size": "80x80", "players": 2, "units": 3, "counts": counts,
            "smoke": {"crash": crash, "result": "", "tick": 10, "unsupported": [], "unbuilt": [], "casts": [], "errors": [], "unknown_units": 0, "warnings": []}}


def _feats():
    f = dict(C.FEATURES)
    f["check.99"] = C.Feature("check.99", "no such check", C.MISSING, C.BLOCKER, "tilefx")
    return f


def test_trigger_status_asks_the_trigger_code():
    assert [C.trigger_status("check", k) for k in (1, 5, 19)] == [C.BUILT] * 3
    assert [C.trigger_status("instant", k) for k in (2, 4, 6, 36)] == [C.BUILT] * 4
    assert [C.trigger_status("group", k) for k in (1, 4, 14)] == [C.BUILT] * 3
    assert C.trigger_status("check", 99) == C.MISSING and C.trigger_status("instant", 99) == C.MISSING and C.trigger_status("group", 99) == C.MISSING


def test_counted_no_ops_are_partial():
    assert C.script_feature("check", 25).status == C.PARTIAL and C.script_feature("check", 25).impact == C.BLOCKER
    assert C.script_feature("instant", 29).impact == C.GAMEPLAY
    assert C.script_feature("check", 5).status == C.BUILT and C.script_feature("check", 99).status == C.MISSING


def test_verdicts_distinguish_blockers_gameplay_and_polish():
    feats = _feats()
    assert C.verdict(_row("1", {"check.5": 2, "music.zones": 5}), feats) == "playable now"
    assert C.verdict(_row("2", {"use.well": 1}), feats) == "playable, gameplay gaps"
    assert C.verdict(_row("3", {"item.quest_pickup": 1}), feats) == "blocked"
    assert C.verdict(_row("4", {}, crash="AttributeError"), feats) == "blocked" and C.blockers(_row("4", {}, crash="x"), feats) == ["crash"]


def test_step_order_unblocks_first_then_gameplay_then_global():
    feats = _feats()
    rows = [_row("1", {"item.quest_pickup": 1}), _row("2", {"item.quest_pickup": 1, "check.99": 1}), _row("3", {"check.99": 1}),
            _row("4", {"use.well": 1}), _row("5", {})]
    order = C.proposed_order(rows, feats)
    assert [o[0] for o in order[:2]] == ["pickup", "tilefx"] or [o[0] for o in order[:2]] == ["tilefx", "pickup"]
    assert {m for o in order[:2] for m in o[1]} == {"1", "2", "3"}      # map 2 needs both: it is completed by the second of the two
    names = [o[0] for o in order]
    assert names[2] == "use_more"                                            # the map with a usable well: a gameplay step before any global one
    rest = names[3:]
    assert rest == sorted(rest, key=lambda st: C.STEPS[st].effort) and all(C.STEPS[st].glob for st in rest)


def test_docs_block_is_replaced_and_the_rest_kept(tmp_path):
    path = str(tmp_path / "coverage.md")
    C.write_docs(path, "first\n")
    text = open(path, encoding="utf-8").read()
    open(path, "w", encoding="utf-8").write("HEAD\n" + text + "TAIL\n")
    C.write_docs(path, "second\n")
    out = open(path, encoding="utf-8").read()
    assert out.startswith("HEAD\n") and out.endswith("TAIL\n") and "second" in out and "first" not in out and out.count(C.BEGIN) == 1


def test_csv_has_one_row_per_map_and_a_status_row(tmp_path):
    import csv
    feats = _feats()
    rows = [_row("1", {"check.99": 2}), _row("2", {})]
    path = C.write_csv(str(tmp_path / "c.csv"), rows, feats)
    data = list(csv.DictReader(open(path, encoding="utf-8")))
    assert [r["map"] for r in data] == ["status", "1", "2"] and data[0]["check.99"] == "missing/blocker" and data[1]["check.99"] == "2" and data[2]["check.99"] == ""
    assert data[1]["verdict"] == "blocked" and data[1]["blockers"] == "check.99"
    assert "map" in C.render(rows, feats) and "Proposed step order" in C.render(rows, feats)


@needs_data
def test_install_maps_scan_and_smoke():
    rows, feats = C.collect(INSTALL, ticks=40, only={"32", "21", "10", "103"})
    by = {r["map"]: r for r in rows}
    assert C.verdict(by["32"], feats) == "playable now"
    assert by["21"]["counts"]["item.quest_pickup"] == 1 and C.verdict(by["21"], feats) == "blocked"       # Quest Treasure: the exit checks for it
    assert by["10"]["counts"]["use.pointer"] >= 1 and C.verdict(by["10"], feats) == "playable, gameplay gaps"   # a signpost that only sends a message
    assert by["103"]["counts"]["use.scripted"] == 16 and C.blockers(by["103"], feats) == ["use.scripted"]      # the switch puzzle: check 21 on 16 switches
    assert all(not r["smoke"]["crash"] and r["smoke"]["tick"] == 40 for r in rows)
    assert by["32"]["counts"]["check.5"] and by["32"]["counts"]["instant.4"]

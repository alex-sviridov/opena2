"""J4: session recorder, crash log and replay (docs/superpowers/specs/2026-11-05-prototype-j4-design.md)."""

import dataclasses
import json
import os

import pytest

from engine import session
from engine.__main__ import main, replay_cmd
from engine.sim import Simulation
from engine.sim import commands as C

from helpers import needs_data


def sample(cls):
    kw = {}
    for f in dataclasses.fields(cls):
        if f.default is not dataclasses.MISSING:
            continue
        if f.name in ("unit_ids",):
            kw[f.name] = (7, 9)
        elif f.name == "cells":
            kw[f.name] = ((1, 2), (3, 4))
        elif f.name == "cell":
            kw[f.name] = (5, 6)
        else:
            kw[f.name] = 3
    return cls(**kw)


def test_every_command_round_trips_through_json():
    classes = session._command_classes()
    assert {"SelectUnits", "MoveUnits", "CastSpell", "PickUp", "MoveTo", "FollowPath"} <= set(classes)
    for name, cls in classes.items():
        cmd = sample(cls)
        again = session.decode_command(json.loads(json.dumps(session.encode_command(cmd))))
        assert again == cmd, name
    full = C.CastSpell(1, (4,), 2, target_id=5, cell=(7, 8))
    assert session.decode_command(json.loads(json.dumps(session.encode_command(full)))) == full


def test_the_ais_own_commands_are_not_stored():
    log = [(1, C.MoveUnits(1, (2,), (3, 4))), (2, C.MoveUnits(2, (5,), (6, 7), ai=True))]
    assert session.player_commands(log) == log[:1]


def test_a_crash_writes_the_traceback_and_the_final_record(tmp_path):
    rec = session.Recorder(str(tmp_path), "32", 5, 2)
    rec.start_logging()
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        text = session.crash_text()
    final = rec.finish("crash", text)
    assert final == {"reason": "crash"}
    log = (tmp_path / "engine.log").read_text()
    assert "boom" in log and "Traceback" in log
    assert json.loads((tmp_path / "final.json").read_text())["reason"] == "crash"


def run_session(directory, ticks=400):
    world, _ = session.build_game("scenario/32.alm", seed=11, vision=True)
    sim = Simulation(world, triggers=True, vision=True)
    rec = session.Recorder(str(directory), "scenario/32.alm", 11, 2)
    rec.attach(sim)
    hero = world.players[1].main_hero
    for _ in range(ticks):
        t = world.tick
        sim.step([C.MoveUnits(1, (hero,), (14, 68))] if t == 20 else [C.SelectUnits(1, (hero,))] if t == 5 else [])
    return rec, world


@needs_data
def test_a_recorded_session_replays_to_the_same_hash(tmp_path):
    rec, world = run_session(tmp_path)
    final = rec.finish("quit")
    assert (tmp_path / "session.json").exists()
    w2, got, recorded = session.replay_session(str(tmp_path))
    assert (got["tick"], got["hash"]) == (final["tick"], final["hash"]) == (world.tick, world.dump_hash())
    assert w2.units[w2.players[1].main_hero].x != 9             # the move order was replayed
    assert replay_cmd(type("A", (), {"session": str(tmp_path), "verify": True, "install": None})()) == 0


@needs_data
def test_verify_fails_on_another_hash_and_a_killed_session_still_replays(tmp_path, capsys):
    rec, world = run_session(tmp_path, 60)
    rec.finish("quit")
    args = type("A", (), {"session": str(tmp_path), "verify": True, "install": None})()
    f = json.loads((tmp_path / "final.json").read_text())
    f["hash"] = "0" * 64
    (tmp_path / "final.json").write_text(json.dumps(f))
    assert replay_cmd(args) == 1
    os.remove(tmp_path / "final.json")                          # killed: session.json only (flushed every 10 s)
    assert replay_cmd(args) == 2
    args.verify = False
    assert replay_cmd(args) == 0 and "tick" in capsys.readouterr().out


@needs_data
def test_play_crash_leaves_the_session_files(tmp_path, monkeypatch, capsys):
    from engine.backend_pygame import window

    def fake_run(world, tv, camera, layout, speed, title, sim_hook=None, frame_hook=None, **kw):
        sim = Simulation(world, ai=True, triggers=True, vision=True)
        sim_hook(sim)
        for _ in range(40):
            sim.step([])
        frame_hook(0, None, world)
        raise RuntimeError("renderer exploded")

    monkeypatch.setattr(window, "run", fake_run)
    out = tmp_path / "s"
    rc = main(["play", "32", "--out", str(out), "--seed", "4"])
    assert rc == 1
    final = json.loads((out / "final.json").read_text())
    assert final["reason"] == "crash" and final["tick"] == 40
    assert "renderer exploded" in (out / "engine.log").read_text()
    assert json.loads((out / "session.json").read_text())["seed"] == 4
    assert replay_cmd(type("A", (), {"session": str(out), "verify": True, "install": None})()) == 0

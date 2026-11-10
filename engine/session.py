"""Play sessions: the command log, the crash log and the replay (docs/superpowers/specs/2026-11-05-prototype-j4-design.md).

A session directory holds `session.json` (map, seed, difficulty, the player's commands by tick), `final.json` (tick, result,
world hash, why it ended) and `engine.log`.  The simulation is deterministic from the seed and the commands, so
`replay_session` reproduces the run and its `World.dump_hash`.  No pygame here.
"""

import dataclasses
import json
import logging
import os
import subprocess
import time
import traceback

from engine.sim import Simulation, replay
from engine.sim import commands as commands_mod
from engine.world import DEFAULT_DIFFICULTY, World

FORMAT = 1
FLUSH_SECONDS = 10.0
LOGGER = "engine"


def _subclasses(cls):
    for s in cls.__subclasses__():
        yield s
        yield from _subclasses(s)


def _command_classes():
    from engine.sim import movement, spells      # noqa: F401  (make sure every Command subclass is imported)
    return {c.__name__: c for c in _subclasses(commands_mod.Command)}


def _plain(v):
    return [_plain(x) for x in v] if isinstance(v, (tuple, list)) else v


def _tupled(v):
    return tuple(_tupled(x) for x in v) if isinstance(v, list) else v


def encode_command(cmd):
    return {"t": type(cmd).__name__, **{f.name: _plain(getattr(cmd, f.name)) for f in dataclasses.fields(cmd)}}


def decode_command(d):
    d = dict(d)
    cls = _command_classes()[d.pop("t")]
    return cls(**{k: _tupled(v) for k, v in d.items()})


def build_game(map_arg, install=None, seed=None, difficulty=DEFAULT_DIFFICULTY, vision=False, roster=None, reserve_ids=(), assets=None):
    """The world of a campaign map as the game starts it: the map script, the party at the drop cell, the AI.
    Returns `(world, assets)`; both `play` and `replay` come through here.  `roster` (`engine.party.Roster`) + `reserve_ids`: the campaign's carried
    party instead of the fresh one (`engine.campaign.CampaignGame.start_mission`)."""
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from engine.sim import triggers
    assets = assets or AssetCache(install)
    m = open_map(map_arg, install)
    world = World.from_map(m, assets, seed=seed, difficulty=difficulty, reserve_ids=reserve_ids)
    triggers.enable(world, m, assets=assets, roster=roster)
    if vision:
        from engine.sim import vision as vision_mod
        vision_mod.enable(world)
        vision_mod.vision_system(world, [])
    return world, assets


def git_id():
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=here, capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=here, capture_output=True, text=True,
                               timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return (rev + ("+dirty" if dirty else "")) if rev else "unknown"


def sessions_root():
    return os.environ.get("ALLODS2_SESSIONS") or os.path.join(os.path.expanduser("~"), ".allods2", "sessions")


def new_session_dir(map_arg, out=None):
    if out:
        os.makedirs(out, exist_ok=True)
        return out
    name = os.path.basename(str(map_arg).rstrip("/\\"))
    name = os.path.splitext(name)[0] or "map"
    d = os.path.join(sessions_root(), "%s-%s" % (name, time.strftime("%Y%m%d-%H%M%S")))
    os.makedirs(d, exist_ok=True)
    return d


def player_commands(log):
    """The log entries a replay needs: everything but the AI's own (it regenerates those)."""
    return [(t, c) for t, c in log if not getattr(c, "ai", False)]


class Recorder:
    """Writes the session files.  `attach(sim)` once the simulation exists; `frame()` from the main loop flushes every
    `FLUSH_SECONDS`; `finish(reason)` writes everything (also after a crash)."""

    def __init__(self, directory, map_arg, seed, difficulty, size=None, clock=time.monotonic):
        self.dir = directory
        self.header = {"format": FORMAT, "map": str(map_arg), "seed": seed, "difficulty": difficulty,
                       "size": list(size) if size else None, "engine": git_id(),
                       "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
        self.sim = None
        self.clock = clock
        self._next = clock() + FLUSH_SECONDS
        self._handler = None

    def path(self, name):
        return os.path.join(self.dir, name)

    def start_logging(self):
        h = logging.FileHandler(self.path("engine.log"), encoding="utf-8")
        h.setLevel(logging.INFO)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root = logging.getLogger(LOGGER)
        root.setLevel(logging.INFO)
        root.addHandler(h)
        self._handler = h

    def stop_logging(self):
        if self._handler is not None:
            logging.getLogger(LOGGER).removeHandler(self._handler)
            self._handler.close()
            self._handler = None

    def attach(self, sim):
        self.sim = sim
        self._write_commands()

    def frame(self, *_):
        if self.sim is not None and self.clock() >= self._next:
            self._next = self.clock() + FLUSH_SECONDS
            self._write_commands()

    def _atomic(self, name, obj):
        tmp = self.path(name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, separators=(",", ":"))
        os.replace(tmp, self.path(name))

    def _write_commands(self):
        log = player_commands(self.sim.log) if self.sim is not None else []
        self._atomic("session.json", {**self.header, "commands": [[t, encode_command(c)] for t, c in log]})

    def finish(self, reason, error=None):
        """Write session.json and final.json; `error` is a formatted traceback (goes to engine.log too)."""
        if error:
            logging.getLogger(LOGGER).error("crash:\n%s", error)
        final = {"reason": reason}
        if self.sim is not None:
            from engine.sim import triggers
            w = self.sim.world
            final.update(tick=w.tick, result=triggers.result(w), hash=w.dump_hash())
            self._write_commands()
        self._atomic("final.json", final)
        self.stop_logging()
        return final


def crash_text():
    return traceback.format_exc()


def load_session(path):
    p = os.path.join(path, "session.json") if os.path.isdir(path) else path
    with open(p, encoding="utf-8") as f:
        s = json.load(f)
    if s.get("format") != FORMAT:
        raise ValueError("%s: session format %r, expected %d" % (p, s.get("format"), FORMAT))
    s["commands"] = [(t, decode_command(c)) for t, c in s["commands"]]
    s["dir"] = os.path.dirname(p)
    return s


def replay_session(path, install=None, ticks=None, on_start=None, on_tick=None):
    """Run a recorded session headless.  Returns `(world, final)` with `final` = tick / result / hash as `Recorder.finish`
    writes them; `on_start(world, assets, session)` and `on_tick(world, commands)` (after each step) are the hooks of the audio log: with `on_tick` the sound events are kept for the consumer
    (they are not part of the hash); `ticks` defaults to the recorded final tick (the last command's tick + 1 when there is no final.json)."""
    from engine.sim import triggers
    s = load_session(path)
    final_path = os.path.join(s["dir"], "final.json")
    recorded = None
    if os.path.exists(final_path):
        with open(final_path, encoding="utf-8") as f:
            recorded = json.load(f)
    world, assets = build_game(s["map"], install, seed=s["seed"], difficulty=s["difficulty"], vision=True)
    sim = Simulation(world, triggers=True, vision=True, keep_sound_events=on_tick is not None)     # play runs with fog and the dump holds the fog bits
    if on_start is not None:
        on_start(world, assets, s)
    n = ticks if ticks is not None else (recorded["tick"] if recorded and "tick" in recorded
                                          else max((t for t, _ in s["commands"]), default=0) + 1)
    replay(sim, s["commands"], n, on_tick)
    return world, {"tick": world.tick, "result": triggers.result(world), "hash": world.dump_hash()}, recorded

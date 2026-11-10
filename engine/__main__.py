"""python -m engine play MAP starts a campaign map as the game does (map script, the hero of the map, monsters, fog, no debug flag) and records
the session in ~/.allods2/sessions/<map>-<time>/ (session.json = seed + commands, final.json = tick / result / world hash, engine.log =
reports and crash traceback; docs/superpowers/specs/2026-11-05-prototype-j4-design.md); `replay SESSION` runs it again headless, `--verify` checks the hash.

   python -m engine run MAP [--x PX --y PX] [--speed N] [--size 640x480|800x600|1024x768] [--install DIR]
   python -m engine screenshot MAP X Y DEST.png [--tick N] [--size WxH] [--interface [--select UID,...]]
                                                [--install DIR]
   python -m engine world-info MAP [--install DIR] [--strict]
   python -m engine world-dump MAP DEST.json [--install DIR]
   python -m engine minimap MAP DEST.png [--units] [--install DIR]
   python -m engine [shell] [--size WxH] [--speed N] [--start menu] [audio flags]   (the shell: logos, main menu, new game, quit; docs/engine/shell.md)
   python -m engine play MAP [--out DIR] [--size WxH] [--speed N] [--difficulty 1|2|3] [--seed N] [--hero-name NAME] [--install DIR]
   python -m engine replay SESSION [--verify] [--audio-log CSV] [--install DIR]
   (run and play also take --mute, --sfx-volume N, --music-volume N, --speech-volume N (0-100, this run only; settings file: docs/engine/audio.md 6) and --no-audio)
   python -m engine maps [--install DIR]           (the campaign maps: number, size, players, name)
   python -m engine coverage [GAME_DIR] [--ticks N] [--csv PATH] [--docs PATH|-] [--maps 10,32]
                                                   (map coverage report, phase K0: out/coverage.csv + docs/coverage.md)
   python -m engine objective [MAP ...] [--install DIR]   (the objective run, phase K12: does the script of the map reach "Mission Complete"?)
   python -m engine campaign [--through N] [--hero MF|FF|MM|FM] [--seed N] [--no-side] [--install DIR]
                                                   (phase L1: the missions chained in unlock order with the carried party; the objective run is the driver)

MAP as for `python -m allods2 map` (10, scenario/10.alm, or a file).  X, Y =
the viewport's top-left in world pixels (x = 32*col, y = 32*row - height).
`run` starts at the playable-area corner (256, 256) by default.  Arrow keys
or the mouse at the window edge scroll; F1/F2/F3 (Shift+F4 paths, Shift+F5 ai) toggle the debug overlays
passability / markers / depth, Ctrl+H the health bars of all units, Ctrl+L the floating damage numbers (on by default, as in the game).  --debug takes a comma list of those
names (screenshot: drawn in the PNG).  Objects and structures are drawn with the
game's default options; --no-* switch shadows, the BRIGHT2 light row, the b.256
smoothing, or both layers off.  `screenshot` writes a PNG
with no window (SDL dummy driver).  `run` always shows the original interface (G3b,
docs/engine/ui-layout.md): the map viewport, the right column with the minimap (click or drag moves
the camera; --no-minimap hides it), the original cursors, and mouse selection (left click or drag,
Shift toggles, right click clears); --size only 640x480 (default), 800x600 or 1024x768.
`screenshot --interface` renders that whole window headless (default 640x480; --select UID,...
selects those unit ids first); without --interface it renders the bare viewport as before.
`minimap` writes its base image (no pygame).  Docs: docs/engine/architecture.md.
J1 interface (docs/engine/ui-layout.md 11): Esc or the disk button opens the in-game menu (End Quest -> Exit leaves the game), the Pause key a
pause window, Tab / the mode button switches the info panel between portrait and stats, the command bar buttons act like the hotkeys; any open dialog
freezes the simulation.  `run --hero-name NAME` names the player's heroes (default Hero); `run --trace` shows the "No way" line (the exe's -trace flag).
`run --debug-move UID X,Y [X,Y ...]` (developer tool, not for players) walks map unit UID
through the given cells: each leg must be straight or diagonal from the previous cell (the unit's own
cell first); no pathfinding, no blocking.  `run --debug-moveto UID X,Y` orders a `MoveTo` (the original's
path finding); with `--debug paths` and the unit selected the overlay shows searched cells (blue), the static
path (yellow) and the current hop (green).  docs/engine/simulation.md.
`run --difficulty 1|2|3` = Easy/Medium(default)/Hard of the new-game screen (monster HP / to-hit / defence tweak, docs/engine/ai.md 10.1).
`run --debug-attack UID UID` (developer tool) makes the first unit attack the second; `--debug combat` prints one console line per blow; `--seed N`
fixes the RNG (default the clock, printed).  docs/engine/combat.md.
"""

import argparse
import os
import sys
import time

from engine.rng import DEFAULT_SEED
from engine.world import DEFAULT_DIFFICULTY, World


AUDIO_VIEW_PX = 480     # the replay's audio camera: the 640x480 viewport (docs/engine/audio.md 7)
BORDER_CELLS = 8        # the camera never shows the 8-cell map border (ui-layout.md section 3)


def _size(s):
    w, _, h = s.lower().partition("x")
    return int(w), int(h)


def _world(a):
    """The map's World (no pygame)."""
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    return World.from_map(open_map(a.map, a.install), AssetCache(a.install))


def world_info(a):
    """Entity counts, blocked cells, unknown types (spec "CLI")."""
    w = _world(a)
    r = w.report
    kinds = {}
    for (kind, tid), n in r.counts.items():
        kinds.setdefault(kind, []).append((tid, n))
    print("%s: %d x %d cells" % (w.name, w.width, w.height))
    print("entities: %d (%s)" % (len(w.objects), ", ".join(
        "%s %d" % (k, sum(n for _, n in kinds.get(k, ()))) for k in ("object", "structure", "bridge"))))
    for k in ("object", "structure", "bridge"):
        if k in kinds:
            print("%s types: %s" % (k, " ".join("%d:%d" % t for t in sorted(kinds[k]))))
    print("players %d, units %d (%d on blocked cells), ground piles %d" % (
        len(w.players), len(w.units), r.units_on_blocked, len(w.items)))
    print("blocked cells (walker mask 0x41): %d of %d" % (int((~w.walkable(1)).sum()), w.width * w.height))
    print("ignored outside the window: %d" % r.ignored_outside_window)
    print("unknown types: %d, unknown units: %d" % (len(r.unknown), len(r.unknown_units)))
    for uid, tid, sid, x, y in r.unknown_units:
        print("  unit uid %d type %d serverID %d at (%d, %d)" % (uid, tid, sid, x, y))
    for kind, tid, x, y in r.unknown:
        print("  %s type %d at (%d, %d)" % (kind, tid, x, y))
    if a.units:
        for u in sorted(w.units.values(), key=lambda u: u.uid):
            t = u.stats
            if t is None:
                print("  unit %d (unknown type, serverID %d) hp %d/%d" % (u.uid, u.server_id, u.hp, u.hp_max))
                continue
            print("  unit %d %s [%s] hp %d/%d mana %d speed %d turn %d scan %d dmg %s-%s def %d "
                  "xp %s windup %d recovery %d" % (
                      u.uid, t.name, t.kind, u.hp, u.hp_max, t.mana_max, t.speed, t.turn_rate, t.scan_range,
                      t.get("damage_min", "-"), t.get("damage_max", "-"), t.defence, t.get("xp", "-"),
                      t.windup, t.recovery))
    return 2 if (a.strict and r.unknown) else 0


def world_dump(a):
    w = _world(a)
    with open(a.dest, "w", encoding="ascii") as f:
        f.write(w.dump_json())
    print("%s: %d entities -> %s" % (w.name, len(w.objects), a.dest))
    return 0


def coverage_cmd(a):
    """Map coverage report (engine/coverage.py): the csv and the generated block of docs/coverage.md."""
    from allods2.common import ROOT
    from engine import coverage
    only = set(a.maps.split(",")) if a.maps else None
    docs = None if a.docs == "-" or only else (a.docs or os.path.join(ROOT, "docs", "coverage.md"))
    coverage.run(a.game_dir, a.ticks, a.csv, docs, only)
    return 0


def objective_cmd(a):
    """The objective run (engine/objective.py): one line per map and the world edits it needed."""
    from allods2.cli import campaign_maps
    from engine import objective
    names = a.maps or [os.path.basename(p).rsplit(".", 1)[0] for p in campaign_maps(a.install)]
    bad = 0
    for n in names:
        r = objective.run(n, a.install)
        bad += r["result"] != "won"
        print("map %-4s %-8s tick %-5d %d edits%s" % (n, r["result"], r["tick"], len(r["edits"]), "  " + r["crash"] if r.get("crash") else ""))
        for e in r["edits"]:
            print("    tick %-5d trigger %-3d check %-3d %s" % e)
    return 1 if bad else 0


def campaign_cmd(a):
    """The campaign spine (engine/campaign.py): one line per mission, then the maps never reached; exit 1 when a mission fails or a map that should be
    reachable is not."""
    from engine import campaign
    side = () if a.no_side else campaign.SIDE_VARS
    r = campaign.run_chain(a.install, a.through, a.hero, a.seed, side)
    print("played %d missions: %s" % (len(r["played"]), " ".join(str(n) for n in r["played"])))
    exp = campaign.NEVER_OFFERED
    print("not played: %s%s" % (" ".join(str(n) for n in r["unreachable"]) or "none",
                                "  (never offered by the campaign: %s; class slots of the other heroes: %s)" % (
                                    " ".join(map(str, exp)), " ".join(map(str, sorted(campaign.class_alternatives(a.hero)))))))
    for n, res, crash in r["failed"]:
        print("mission %d: %s%s%s" % (n, res, " " + crash if crash else "", "  (known oracle miss)" if n in campaign.ORACLE_MISS else ""))
    if r["unexpected"]:
        print("UNEXPECTED unreachable maps: %s" % " ".join(str(n) for n in r["unexpected"]))
    print("chain hash %s" % r["hash"])
    return 1 if r["hard_failed"] or r["unexpected"] else 0


def minimap_cmd(a):
    """Write the minimap image of a map (no pygame, no camera rectangle)."""
    from allods2.common import as_fs
    from allods2.graphics import write_png
    from allods2.cli import open_map
    from allods2.minimap import load_color_table, minimap_light, minimap_rgb
    m = open_map(a.map, a.install)
    rgb = minimap_rgb(m.runtime_terrain(), load_color_table(as_fs(a.install)), minimap_light(m.heights))
    if a.units:
        from allods2.assets import AssetCache
        from allods2.minimap import load_dot_colors
        from allods2.minimap import load_structure_sizes
        from engine.view.minimap import MinimapGeometry, draw_dots
        rgb = rgb.copy()
        geo, world, colors = MinimapGeometry(m.width, m.height), World.from_map(m, AssetCache(a.install)), load_dot_colors(as_fs(a.install))
        draw_dots(rgb, geo, world, colors, load_structure_sizes(as_fs(a.install)))
    write_png(a.dest, rgb)
    print("%s: %d x %d cells -> %s (%dx%d)" % (m.name, m.width, m.height, a.dest, rgb.shape[1], rgb.shape[0]))
    return 0


def _setup(a):
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from engine.view import Camera, DrawOptions, TerrainView
    from engine.ui import DebugFlags
    prebuilt = getattr(a, "prebuilt", None)             # (world, assets) of a campaign mission (`CampaignGame.start_mission`: script, party and AI done)
    if prebuilt is not None:
        world, assets = prebuilt
    else:
        assets = AssetCache(a.install)
        seed = getattr(a, "seed", None)
        if seed is None:
            seed = time.time_ns() & 0xFFFFFFFF if a.cmd == "run" else DEFAULT_SEED      # the exe seeds from the clock (simulation.md 10)
        m = open_map(a.map, a.install)
        world = World.from_map(m, assets, seed=seed, difficulty=getattr(a, "difficulty", DEFAULT_DIFFICULTY))
        if getattr(a, "triggers", False):               # the map script (docs/engine/triggers.md); implies the AI
            from engine.sim import triggers
            triggers.enable(world, m, assets=assets, party=getattr(a, "party", 0))
    tv = TerrainView(world, assets.tileset())
    w, h = a.size
    opts = DrawOptions(shadows=not a.no_shadows, lit=not a.no_light,
                       smoothing=not a.no_smoothing, objects=not a.no_objects)
    if getattr(a, "interface", True):
        from engine.ui import Layout
        a.layout = Layout.for_size(w, h)            # ValueError: unsupported size
        v = a.layout.viewport
        cam = Camera(v.w, v.h, world.width, world.height, a.x, a.y, border=BORDER_CELLS * 32)
    else:
        a.layout = None
        cam = Camera(w, h, world.width, world.height, a.x, a.y)
    return world, tv, cam, assets, opts, DebugFlags.parse(a.debug)


def debug_moveto_commands(world, args):
    """`--debug-moveto UID X,Y` -> [MoveTo]."""
    if not args:
        return []
    from engine.sim import MoveTo
    from engine.world import UNIT_ID_BASE
    try:
        uid = UNIT_ID_BASE + int(args[0])
        x, y = (int(v) for v in args[1].split(","))
    except (ValueError, IndexError):
        raise ValueError("--debug-moveto: give UID and X,Y") from None
    if uid not in world.units:
        raise ValueError("--debug-moveto: no unit with uid %s" % args[0])
    return [MoveTo(uid, x, y)]


def debug_attack_commands(world, args):
    """`--debug-attack UID UID` -> [AttackUnit]: the first unit (its owner's command) attacks the second."""
    if not args:
        return []
    from engine.sim import AttackUnit
    from engine.world import UNIT_ID_BASE
    try:
        a, t = (UNIT_ID_BASE + int(v) for v in args)
    except ValueError:
        raise ValueError("--debug-attack: give two unit uids") from None
    if a not in world.units or t not in world.units:
        raise ValueError("--debug-attack: no such unit uid")
    return [AttackUnit(world.units[a].owner, (a,), t)]


def debug_move_commands(world, args):
    """`--debug-move UID X,Y ...` -> [FollowPath]: straight or diagonal legs from the unit's cell."""
    if not args:
        return []
    from engine.sim import FollowPath, expand_line
    from engine.world import UNIT_ID_BASE
    uid = UNIT_ID_BASE + int(args[0])
    if uid not in world.units:
        raise ValueError("--debug-move: no unit with uid %s" % args[0])
    try:
        ends = [tuple(int(v) for v in c.split(",")) for c in args[1:]]
    except ValueError:
        raise ValueError("--debug-move: cells are X,Y") from None
    if not ends or any(len(c) != 2 for c in ends):
        raise ValueError("--debug-move: give UID and at least one X,Y cell")
    u = world.units[uid]
    return [FollowPath(uid, expand_line((u.x, u.y), ends))]


def audio_settings(a):
    """The settings file with the command-line overrides of this run (`--mute`, `--sfx-volume`, `--music-volume`, `--speech-volume`); never written."""
    from engine.audio import settings
    def pct(v):
        return None if v is None else max(0, min(100, v))
    return settings.load().override(mute=True if getattr(a, "mute", False) else None, sfx=pct(getattr(a, "sfx_volume", None)),
                                    music=pct(getattr(a, "music_volume", None)), speech=pct(getattr(a, "speech_volume", None)))


def make_audio(a, assets):
    """The pygame `Audio` of a run, or None with `--no-audio`.  No device = a silent Audio (never an error)."""
    if getattr(a, "no_audio", False):
        return None
    from engine.backend_pygame.audio import Audio
    return Audio(assets.fs, audio_settings(a))


def map_music_zones(a):
    """The music zones (section 12) of the map."""
    from allods2.cli import open_map
    return open_map(a.map, a.install).music[1]


class PartyCamera:
    """The replay's camera (audio.md 5: the log has none): centred on the viewing player's live units, a fixed 480 x 480 px view."""

    view_w = view_h = AUDIO_VIEW_PX
    x = y = 0.0

    def follow(self, world, viewer=1):
        us = [u for u in world.units.values() if u.owner == viewer and u.hp > 0]
        if us:
            self.x = sum(u.x for u in us) / len(us) * 32 + 16 - self.view_w / 2
            self.y = sum(u.y for u in us) / len(us) * 32 + 16 - self.view_h / 2


def replay_audio_log(path, install=None):
    """`(on_start, on_tick)` hooks for `session.replay_session`: the replay through the Director + `NullAudio` on the replay clock, writing the CSV `path`."""
    from engine.audio.audiolog import AudioLog
    from engine.audio.director import replay_ms
    from engine.backend_pygame.audio import NullAudio, replay_rate
    from engine.audio.settings import Settings
    state = {}
    rate = replay_rate()

    def on_start(world, assets, sess):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        state["f"] = open(path, "w", encoding="utf-8", newline="")
        header = ["audio log of session %s (map %s, seed %s, difficulty %s)" % (sess["dir"], sess["map"], sess["seed"], sess["difficulty"]),
                  "replay clock %d ticks per second, camera centred on the party (%d px square), default settings; UI sounds are not in a replay" % (rate, AUDIO_VIEW_PX)]
        state["log"] = AudioLog(state["f"], header)
        state["audio"] = NullAudio(assets.fs, Settings(), seed=sess["seed"], log=state["log"])
        state["cam"] = PartyCamera()
        state["audio"].start_mission(map_zones(sess, assets), None)

    def map_zones(sess, assets):
        try:
            from allods2.cli import open_map
            return open_map(sess["map"], install).music[1]
        except Exception:                           # noqa: BLE001  a replay never fails for its sound log
            return ()

    def on_tick(world, cmds):
        cam = state["cam"]
        cam.follow(world)
        state["audio"].frame(replay_ms(world.tick, rate), world, cam, cmds)

    def finish():
        if "f" in state:
            state["f"].close()
        return state["log"].rows if "log" in state else 0
    return on_start, on_tick, finish


def replay_cmd(a):
    """`replay SESSION`: tick, result and hash of the run; with `--verify` exit 1 on a hash different from final.json; `--audio-log CSV` also writes the audio log."""
    from engine import session
    on_start = on_tick = finish = None
    if getattr(a, "audio_log", None):
        on_start, on_tick, finish = replay_audio_log(a.audio_log, a.install)
    try:
        world, got, recorded = session.replay_session(a.session, a.install, on_start=on_start, on_tick=on_tick)
    except (OSError, ValueError, KeyError) as e:
        print("replay: %s" % e, file=sys.stderr)
        return 2
    print("tick %d result %s hash %s" % (got["tick"], got["result"] or "-", got["hash"]))
    if finish is not None:
        print("audio log: %d rows -> %s" % (finish(), a.audio_log))
    if a.verify:
        if not recorded or "hash" not in recorded:
            print("replay: no recorded hash (final.json missing or the session was killed)", file=sys.stderr)
            return 2
        if recorded["hash"] != got["hash"] or recorded["tick"] != got["tick"]:
            print("MISMATCH: recorded tick %s hash %s" % (recorded["tick"], recorded["hash"]), file=sys.stderr)
            return 1
        print("verified")
    return 0


class PlaySession:
    """One recorded play of a campaign map: the game's own start (map script, the map's hero, AI, fog) with the session files of `play`.  Used by
    `play_cmd` (it owns the window) and by the shell's game screen (`in_shell`: display and audio stay open, `run` returns why the mission ended).
    `start()` builds the World; `run()` plays; `finish()` writes final.json."""

    def __init__(self, a, parser=None, assets=None, audio=None, in_shell=False):
        from engine import session
        self.a, self.assets, self.audio, self.in_shell = a, assets, audio, in_shell
        a.cmd = "run"                                  # the run path's defaults, as a player has them
        a.x = a.y = 256
        a.no_shadows = a.no_light = a.no_smoothing = a.no_objects = False
        a.debug, a.triggers, a.party, a.interface = "", True, 0, True
        from engine.audio import settings as settings_mod
        self.settings = getattr(a, "settings", None) or settings_mod.load()      # the options screens' file (shell.md 5): speed, shadows, lighting, ...
        if getattr(a, "speed", None) is None:
            a.speed = self.settings.game_speed
        a.seed = a.seed if a.seed is not None else time.time_ns() & 0xFFFFFFFF
        from allods2.cli import resolve_map
        resolve_map(a.map, a.install)                  # a wrong MAP fails here, before a session directory exists
        try:
            self.directory = session.new_session_dir(a.map, a.out)
        except OSError as e:
            if parser is None:
                raise
            parser.error("session directory: %s" % e)
        self.rec = session.Recorder(self.directory, a.map, a.seed, a.difficulty, a.size)
        self.rec.start_logging()
        print("session %s (seed %d)" % (self.directory, a.seed))
        self.reason, self.error, self.world, self.sim = "quit", None, None, None
        self.option_services = None                    # the shell's services for the in-game options windows (None = the defaults)
        self.exit = None                               # the ui's quit reason when the loop ended (None = the window was closed)

    def start(self):
        a = self.a
        self.world, self.tv, self.camera, assets, self.opts, self.debug = _setup(a)
        self.assets = self.assets or assets
        from engine.backend_pygame.window import game_options
        self.opts = game_options(self.opts, self.settings)
        self.tv.set_time_flow(self.settings.day_night)
        hero = self.world.units.get(self.world.players[1].main_hero)
        if hero is not None:                       # start with the hero in view
            self.camera.move_to(hero.x * 32 - self.camera.view_w / 2, hero.y * 32 - self.camera.view_h / 2)
        from engine.sim import vision
        vision.enable(self.world)
        vision.vision_system(self.world, [])
        from allods2.common import as_fs
        from allods2.minimap import load_color_table, load_dot_colors, load_structure_sizes
        from engine.view import Minimap
        self.mm = Minimap(self.world, load_color_table(as_fs(a.install)), load_dot_colors(as_fs(a.install)),
                          load_structure_sizes(as_fs(a.install)))
        return self

    def run(self):
        """Play until the loop ends; returns the recorded reason (`victory`, `defeat`, `quit`)."""
        import re
        from engine.backend_pygame import window
        from engine.sim import triggers
        a, world = self.a, self.world
        mission = re.search(r"(\d+)(?:\.alm)?$", os.path.basename(a.map.rstrip("/\\")), re.I)
        audio = self.audio if self.audio is not None else (None if self.in_shell else make_audio(a, self.assets))
        sim = window.run(world, self.tv, self.camera, a.layout, a.speed, "Allods 2 - " + world.name, assets=self.assets, options=self.opts,
                         debug=self.debug, minimap=self.mm, ai=True, hero_name=a.hero_name,
                         mission_id=mission.group(1) if mission else None,
                         frame_hook=self.rec.frame, sim_hook=self.rec.attach, audio=audio, music_zones=map_music_zones(a),
                         in_shell=self.in_shell, settings=self.settings, option_services=self.option_services)
        self.exit = sim.ui.quit if getattr(sim, "ui", None) is not None else None
        self.reason = {"won": "victory", "lost": "defeat"}.get(triggers.result(world), "quit")
        return self.reason

    def crash(self, e):
        from engine import session
        self.reason = "interrupted" if isinstance(e, KeyboardInterrupt) else "crash"
        self.error = session.crash_text()
        print(self.error, file=sys.stderr)

    def finish(self):
        final = self.rec.finish(self.reason, self.error)
        print("session %s: %s, tick %s" % (self.directory, self.reason, final.get("tick", "-")))
        print("replay: python -m engine replay %s --verify" % self.directory)
        return final


def play_cmd(a, parser):
    """`play MAP`: the game's own start (map script, the map's hero, AI, fog, Medium), session files in a known place; straight into the map (debug / J4)."""
    play = PlaySession(a, parser)
    try:
        play.start()
        play.run()
    except BaseException as e:                     # a crash or Ctrl+C: the session is still written
        play.crash(e)
    play.finish()
    return 1 if play.reason == "crash" else 0


def shell_cmd(a, parser):
    """No command (or `shell`): the shell, as the original starts: videos, main menu, new game, quit (docs/engine/shell.md)."""
    from engine.backend_pygame import shell as backend
    return backend.run(a, parser, PlaySession, make_audio, audio_settings)


def add_audio_flags(q):
    q.add_argument("--mute", action="store_true", help="silence the run (the stored volumes stay)")
    q.add_argument("--sfx-volume", type=int, metavar="N", help="effects volume 0-100 for this run (settings file: docs/engine/audio.md 6)")
    q.add_argument("--music-volume", type=int, metavar="N", help="music volume 0-100 for this run")
    q.add_argument("--speech-volume", type=int, metavar="N", help="voice volume 0-100 for this run")
    q.add_argument("--no-audio", action="store_true", help="no sound device at all")


def build_parser():
    p = argparse.ArgumentParser(prog="python -m engine")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("map")
    r.add_argument("--x", type=int, default=256)
    r.add_argument("--y", type=int, default=256)
    r.add_argument("--speed", type=int, default=4, choices=range(9))
    r.add_argument("--size", type=_size, default=(640, 480))
    r.add_argument("--install")
    s = sub.add_parser("screenshot")
    s.add_argument("map")
    s.add_argument("x", type=int)
    s.add_argument("y", type=int)
    s.add_argument("dest")
    s.add_argument("--tick", type=int, default=0)
    s.add_argument("--size", type=_size, default=None)
    s.add_argument("--interface", action="store_true", help="render the full window (640x480 default)")
    s.add_argument("--select", default="", metavar="UID,...", help="with --interface: unit ids to select")
    s.add_argument("--fog", action="store_true", help="fog of war as after the first refresh: the first player's units reveal their sight (docs/engine/vision.md)")
    s.add_argument("--install")
    for q in (r, s):
        q.add_argument("--no-shadows", action="store_true")
        q.add_argument("--no-light", action="store_true")
        q.add_argument("--no-smoothing", action="store_true")
        q.add_argument("--no-objects", action="store_true")
        q.add_argument("--debug", default="", metavar="LIST", help="passability,markers,depth,paths,combat,ai")
    i = sub.add_parser("world-info")
    i.add_argument("map")
    i.add_argument("--install")
    i.add_argument("--strict", action="store_true")
    i.add_argument("--units", action="store_true", help="list each unit with its template stats")
    d = sub.add_parser("world-dump")
    d.add_argument("map")
    d.add_argument("dest")
    d.add_argument("--install")
    m = sub.add_parser("minimap")
    m.add_argument("map")
    m.add_argument("dest")
    m.add_argument("--install")
    m.add_argument("--units", action="store_true", help="add the unit dots")
    r.add_argument("--no-minimap", action="store_true")
    r.add_argument("--no-fog", action="store_true", help="draw the whole map (the game's fog of war is on by default, docs/engine/vision.md)")
    r.add_argument("--trace", action="store_true", help="show the \"No way\" message line (the exe's -trace flag; off by default)")
    r.add_argument("--hero-name", default="Hero", help="name of the player's heroes in the info panel and level-up lines (default Hero)")
    r.add_argument("--no-ai", action="store_true", help="monsters do not think (docs/engine/ai.md)")
    r.add_argument("--triggers", action="store_true", help="run the map script (docs/engine/triggers.md); a fresh campaign party is placed at the drop cell (--party)")
    r.add_argument("--party", type=int, default=0, choices=(0, 1, 2, 3), help="with --triggers: heroes placed at map start (Start_MF, Fighter_Hero, Mage_Hero; 0 = as many as the map script names, a fresh campaign has only the first)")
    r.add_argument("--debug-move", nargs="+", metavar="UID_OR_CELL",
                   help="developer tool: UID X,Y [X,Y ...] walks the unit along straight legs")
    r.add_argument("--debug-moveto", nargs="+", metavar="UID_OR_CELL",
                   help="developer tool: UID X,Y orders a path-found move (use with --debug paths)")
    r.add_argument("--debug-attack", nargs=2, metavar="UID", help="developer tool: the first unit attacks the second (use with --debug combat)")
    r.add_argument("--difficulty", type=int, choices=(1, 2, 3), default=DEFAULT_DIFFICULTY,
                   help="game difficulty option 1 easy, 2 medium (default, no tweak), 3 hard: the new-game screen's "
                        "Easy/Medium/Hard (docs/engine/ai.md 10.1)")
    r.add_argument("--seed", type=int, help="RNG seed (default: the clock, printed; the exe seeds from it too)")
    pl = sub.add_parser("play", help="play a campaign map and record the session")
    pl.add_argument("map")
    pl.add_argument("--out", help="session directory (default ~/.allods2/sessions/<map>-<time>)")
    pl.add_argument("--size", type=_size, default=(640, 480))
    pl.add_argument("--speed", type=int, default=None, choices=range(9), help="game speed 0-8 (default: the settings file, 4)")
    pl.add_argument("--difficulty", type=int, choices=(1, 2, 3), default=DEFAULT_DIFFICULTY)
    pl.add_argument("--seed", type=int)
    pl.add_argument("--hero-name", default="Hero")
    pl.add_argument("--install")
    sh = sub.add_parser("shell", help="the game as the original starts: videos, main menu, new game, quit (the default command)")
    sh.add_argument("--size", type=_size, default=(640, 480), help="640x480 (default), 800x600 or 1024x768; the menus are centred 640x480 pictures")
    sh.add_argument("--speed", type=int, choices=range(9), default=None, help="game speed 0-8 for this run (default: the settings file)")
    sh.add_argument("--hero-name", default="Hero")
    sh.add_argument("--seed", type=int)
    sh.add_argument("--out", help="session directory of the games played (default ~/.allods2/sessions/<map>-<time>)")
    sh.add_argument("--start", choices=("startup", "menu"), default="startup", help="first screen (default startup: the logos, then the menu)")
    sh.add_argument("--install")
    add_audio_flags(sh)
    mp = sub.add_parser("maps", help="list the campaign maps")
    mp.add_argument("--install")
    cv = sub.add_parser("coverage", help="what stands between each campaign map and full playability (out/coverage.csv, docs/coverage.md)")
    cv.add_argument("game_dir", nargs="?", help="the game install (default: ALLODS2_INSTALL or samples/allods2_en_gog)")
    cv.add_argument("--ticks", type=int, default=1600, help="smoke run length per map (default 1600 = 100 s of game time)")
    cv.add_argument("--csv", help="output csv (default out/coverage.csv)")
    cv.add_argument("--docs", help="docs page whose generated block is rewritten (default docs/coverage.md; '-' = skip)")
    cv.add_argument("--maps", help="comma list of map numbers (partial run: writes the csv only)")
    ob = sub.add_parser("objective", help="the objective run: does the script of each campaign map reach Mission Complete (world edits stand in for the player)?")
    ob.add_argument("maps", nargs="*", help="map numbers (default: all campaign maps)")
    ob.add_argument("--install")
    ca = sub.add_parser("campaign", help="the campaign spine: chain the missions in unlock order with the carried party (the objective run drives each map)")
    ca.add_argument("--through", type=int, help="stop after this mission is finished (default: until the ending)")
    ca.add_argument("--hero", default="MF", choices=("MF", "FF", "MM", "FM"), help="the hero's template: gender + class (default MF); decides the class-slot missions")
    ca.add_argument("--seed", type=int, default=1)
    ca.add_argument("--no-side", action="store_true", help="do not take the optional goals that add missions 21 and 52")
    ca.add_argument("--install")
    rp = sub.add_parser("replay", help="run a recorded session again, headless")
    rp.add_argument("session", help="a session directory or its session.json")
    rp.add_argument("--verify", action="store_true", help="exit 1 when the world hash differs from final.json")
    rp.add_argument("--install")
    rp.add_argument("--audio-log", metavar="CSV", help="also run the sound model on the replay and write its log (docs/engine/audio.md 7)")
    add_audio_flags(r)
    add_audio_flags(pl)
    return p


def main(argv=None):
    p = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0].startswith("-") and argv[0] not in ("-h", "--help")):
        argv = ["shell"] + argv                    # `python -m engine` starts the shell
    a = p.parse_args(argv)
    from allods2.cli import MapNotFound
    try:
        return _dispatch(a, p)
    except MapNotFound as e:
        p.exit(2, "%s: error: %s\n" % (p.prog, e))


def _dispatch(a, p):
    if a.cmd == "maps":
        from allods2.cli import map_list
        return map_list(a)
    if a.cmd == "replay":
        return replay_cmd(a)
    if a.cmd == "coverage":
        return coverage_cmd(a)
    if a.cmd == "objective":
        return objective_cmd(a)
    if a.cmd == "campaign":
        return campaign_cmd(a)
    if a.cmd == "play":
        return play_cmd(a, p)
    if a.cmd == "shell":
        return shell_cmd(a, p)
    if a.cmd == "minimap":
        return minimap_cmd(a)
    if a.cmd == "world-info":
        return world_info(a)
    if a.cmd == "world-dump":
        return world_dump(a)
    if a.cmd == "run":
        a.interface = True
    else:
        a.size = a.size or ((640, 480) if a.interface else (1024, 768))
    if a.cmd == "screenshot":
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    try:
        world, tv, camera, assets, opts, debug = _setup(a)
    except ValueError as e:
        p.error(str(e))
    from engine.backend_pygame import render, window
    if (a.cmd == "run" and not a.no_fog) or getattr(a, "fog", False):
        from engine.sim import vision
        vision.enable(world)
        vision.vision_system(world, [])
    if a.cmd == "run":
        from allods2.common import as_fs
        from allods2.minimap import load_color_table, load_dot_colors, load_structure_sizes
        from engine.view import Minimap
        mm = None if a.no_minimap else Minimap(world, load_color_table(as_fs(a.install)),
                                               load_dot_colors(as_fs(a.install)), load_structure_sizes(as_fs(a.install)))
        try:
            commands = (debug_move_commands(world, a.debug_move) + debug_moveto_commands(world, a.debug_moveto)
                        + debug_attack_commands(world, a.debug_attack))
            print("seed %d" % world.seed)
        except ValueError as e:
            p.error(str(e))
        import re
        mission = re.search(r"(\d+)(?:\.alm)?$", os.path.basename(a.map.rstrip("/\\")), re.I)
        window.run(world, tv, camera, a.layout, a.speed, "Allods 2 - " + world.name,
                   assets=assets, options=opts, debug=debug, minimap=mm, commands=commands, ai=not a.no_ai or a.triggers,
                   trace=a.trace, hero_name=a.hero_name, mission_id=mission.group(1) if mission else None,
                   audio=make_audio(a, assets), music_zones=map_music_zones(a))
    elif a.interface:
        from engine.backend_pygame.interface import screenshot_window
        from engine.world import UNIT_ID_BASE
        ids = tuple(UNIT_ID_BASE + int(u) for u in a.select.split(",") if u)
        rgb = screenshot_window(tv, camera, a.layout, a.tick, a.dest, assets, opts, debug, ids)
        print("%s at (%d, %d) tick %d, selected %s -> %s (%dx%d)"
              % (world.name, camera.ix, camera.iy, a.tick, ids, a.dest, rgb.shape[1], rgb.shape[0]))
    else:
        rgb = render.screenshot(tv, camera, a.tick, a.dest, assets=assets, options=opts, debug=debug)
        print("%s at (%d, %d) tick %d -> %s (%dx%d)"
              % (world.name, camera.ix, camera.iy, a.tick, a.dest, rgb.shape[1], rgb.shape[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

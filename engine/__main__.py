"""python -m engine play MAP starts a campaign map as the game does (map script, the hero of the map, monsters, fog, no debug flag) and records
the session in ~/.allods2/sessions/<map>-<time>/ (session.json = seed + commands, final.json = tick / result / world hash, engine.log =
reports and crash traceback; docs/superpowers/specs/2026-11-05-prototype-j4-design.md); `replay SESSION` runs it again headless, `--verify` checks the hash.

   python -m engine run MAP [--x PX --y PX] [--speed N] [--size 640x480|800x600|1024x768] [--install DIR]
   python -m engine screenshot MAP X Y DEST.png [--tick N] [--size WxH] [--interface [--select UID,...]]
                                                [--install DIR]
   python -m engine world-info MAP [--install DIR] [--strict]
   python -m engine world-dump MAP DEST.json [--install DIR]
   python -m engine minimap MAP DEST.png [--units] [--install DIR]
   python -m engine play MAP [--out DIR] [--size WxH] [--speed N] [--difficulty 1|2|3] [--seed N] [--hero-name NAME] [--install DIR]
   python -m engine replay SESSION [--verify] [--install DIR]

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
    assets = AssetCache(a.install)
    seed = getattr(a, "seed", None)
    if seed is None:
        seed = time.time_ns() & 0xFFFFFFFF if a.cmd == "run" else DEFAULT_SEED      # the exe seeds from the clock (simulation.md 10)
    m = open_map(a.map, a.install)
    world = World.from_map(m, assets, seed=seed, difficulty=getattr(a, "difficulty", DEFAULT_DIFFICULTY))
    if getattr(a, "triggers", False):                   # the map script (docs/engine/triggers.md); implies the AI
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


def replay_cmd(a):
    """`replay SESSION`: tick, result and hash of the run; with `--verify` exit 1 on a hash different from final.json."""
    from engine import session
    try:
        world, got, recorded = session.replay_session(a.session, a.install)
    except (OSError, ValueError, KeyError) as e:
        print("replay: %s" % e, file=sys.stderr)
        return 2
    print("tick %d result %s hash %s" % (got["tick"], got["result"] or "-", got["hash"]))
    if a.verify:
        if not recorded or "hash" not in recorded:
            print("replay: no recorded hash (final.json missing or the session was killed)", file=sys.stderr)
            return 2
        if recorded["hash"] != got["hash"] or recorded["tick"] != got["tick"]:
            print("MISMATCH: recorded tick %s hash %s" % (recorded["tick"], recorded["hash"]), file=sys.stderr)
            return 1
        print("verified")
    return 0


def play_cmd(a, parser):
    """`play MAP`: the game's own start (map script, the map's hero, AI, fog, Medium), session files in a known place."""
    from engine import session
    a.cmd = "run"                                  # the run path's defaults, as a player has them
    a.x = a.y = 256
    a.no_shadows = a.no_light = a.no_smoothing = a.no_objects = False
    a.debug, a.triggers, a.party, a.interface = "", True, 0, True
    a.seed = a.seed if a.seed is not None else time.time_ns() & 0xFFFFFFFF
    try:
        directory = session.new_session_dir(a.map, a.out)
    except OSError as e:
        parser.error("session directory: %s" % e)
    rec = session.Recorder(directory, a.map, a.seed, a.difficulty, a.size)
    rec.start_logging()
    print("session %s (seed %d)" % (directory, a.seed))
    reason, error = "quit", None
    try:
        world, tv, camera, assets, opts, debug = _setup(a)
        hero = world.units.get(world.players[1].main_hero)
        if hero is not None:                       # start with the hero in view
            camera.move_to(hero.x * 32 - camera.view_w / 2, hero.y * 32 - camera.view_h / 2)
        from engine.backend_pygame import window
        from engine.sim import triggers, vision
        vision.enable(world)
        vision.vision_system(world, [])
        from allods2.common import as_fs
        from allods2.minimap import load_color_table, load_dot_colors, load_structure_sizes
        from engine.view import Minimap
        mm = Minimap(world, load_color_table(as_fs(a.install)), load_dot_colors(as_fs(a.install)),
                     load_structure_sizes(as_fs(a.install)))
        import re
        mission = re.search(r"(\d+)(?:\.alm)?$", os.path.basename(a.map.rstrip("/\\")), re.I)
        window.run(world, tv, camera, a.layout, a.speed, "Allods 2 - " + world.name, assets=assets, options=opts,
                   debug=debug, minimap=mm, ai=True, hero_name=a.hero_name,
                   mission_id=mission.group(1) if mission else None,
                   frame_hook=rec.frame, sim_hook=rec.attach)
        reason = {"won": "victory", "lost": "defeat"}.get(triggers.result(world), "quit")
    except BaseException as e:                     # a crash or Ctrl+C: the session is still written
        reason = "interrupted" if isinstance(e, KeyboardInterrupt) else "crash"
        error = session.crash_text()
        print(error, file=sys.stderr)
    final = rec.finish(reason, error)
    print("session %s: %s, tick %s" % (directory, reason, final.get("tick", "-")))
    print("replay: python -m engine replay %s --verify" % directory)
    return 1 if reason == "crash" else 0


def main(argv=None):
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
    pl.add_argument("--speed", type=int, default=4, choices=range(9))
    pl.add_argument("--difficulty", type=int, choices=(1, 2, 3), default=DEFAULT_DIFFICULTY)
    pl.add_argument("--seed", type=int)
    pl.add_argument("--hero-name", default="Hero")
    pl.add_argument("--install")
    rp = sub.add_parser("replay", help="run a recorded session again, headless")
    rp.add_argument("session", help="a session directory or its session.json")
    rp.add_argument("--verify", action="store_true", help="exit 1 when the world hash differs from final.json")
    rp.add_argument("--install")
    a = p.parse_args(argv)
    if a.cmd == "replay":
        return replay_cmd(a)
    if a.cmd == "play":
        return play_cmd(a, p)
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
                   trace=a.trace, hero_name=a.hero_name, mission_id=mission.group(1) if mission else None)
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

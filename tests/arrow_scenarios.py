"""A shooter fight on the campaign map 73 with arrows in flight: the source of `tests/golden.json["arrows"]` (`tools/update_golden.py`) and of
`tests/test_engine_arrows_maps.py`.  Needs the install.  K9: the client projectiles are view state, so the same fight with the arrow spawn switched
off ends in the same world dump hash."""

import hashlib
import math
import os

from engine.sim import AttackUnit, Simulation, xp
from engine.view import Camera, DrawOptions, TerrainView
from engine.world import World

SHOOTERS = 4                # the first four shooters of the map (units.reg Projectile 1-6)
TICKS = 160
SIZE = (640, 480)


def build(assets, install=None, seed=5):
    from allods2.cli import open_map
    w = World.from_map(open_map("73", install), assets, seed=seed)
    shooters = [u for u in w.units.values() if (s := assets.unit_set(u.type_id)) is not None and 0 < s.t.Projectile < 7][:SHOOTERS]
    cmds = []
    for u in shooters:
        foes = sorted((e for e in w.units.values() if xp.hostile(w, u, e)), key=lambda e: (math.hypot(e.x - u.x, e.y - u.y), e.id))
        cmds.append(AttackUnit(u.owner, (u.id,), foes[0].id))
    return w, shooters, cmds


def run(assets, install=None, arrows=True, frames=None):
    """Run the fight; returns (world, arrows seen, {name: camera tick} of the frames asked for as it goes).  `frames(w, name)` is called on the first
    tick with a live arrow and 3 ticks later (`volley`, `volley+3`)."""
    from engine.sim import effects
    w, shooters, cmds = build(assets, install)
    sim = Simulation(w, ai=True)
    seen = set()
    spawn = effects.spawn_arrow
    if not arrows:
        effects.spawn_arrow = lambda *a, **k: None
    try:
        first = None
        for i in range(TICKS):
            sim.step(cmds if i == 0 else [])
            for a in w.arrows:
                if a.live and not a.spell:              # the shooters' arrows only (a caster of the group makes a spell flight too)
                    seen.add((a.shooter, a.born))
            live = [a for a in w.arrows if a.live and not a.spell]
            if frames is not None and live and first is None:
                first = w.tick
            if frames is not None and first is not None and w.tick in (first, first + 3):
                frames(w, "volley" if w.tick == first else "volley+3")
    finally:
        effects.spawn_arrow = spawn
    return w, seen


def hashes(assets, install=None):
    """{"volley": sha256, "volley+3": sha256, "shots": n, "world": the world dump hash after the run}."""
    from engine.backend_pygame import render
    from engine.backend_pygame.sprites import SpriteCache
    from engine.backend_pygame.surfaces import SurfaceCache
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    out = {}
    cache = {}

    def frame(w, name):
        live = [a for a in w.arrows if a.live]
        a = min(live, key=lambda x: x.shooter)                                  # a stable choice
        if "tv" not in cache:
            tv = TerrainView(w, assets.tileset())
            cache.update(tv=tv, sc=SurfaceCache(tv), sp=SpriteCache(assets))
        cam = Camera(SIZE[0], SIZE[1], w.width, w.height, max((a.x >> 8) * 32 - SIZE[0] // 2, 0), max((a.y >> 8) * 32 - SIZE[1] // 2, 0))
        rgb = render.screenshot(cache["tv"], cam, w.tick, None, cache["sc"], assets, DrawOptions(), None, cache["sp"])
        out[name] = hashlib.sha256(rgb.tobytes()).hexdigest()

    w, seen = run(assets, install, True, frame)
    out["shots"] = len(seen)
    out["world"] = w.dump_hash()
    return out

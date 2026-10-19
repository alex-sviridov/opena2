"""Cost of a 15-unit fight with spell projectiles in flight on the campaign map 73 (docs/engine/combat.md 14).

    python tools/bench_fight.py [--ticks N] [--frames N] [--size WxH]

The party of four knights and the 11 nearest hostile units fight (AI on); the mage and four more units (two of the party, two enemies: the
command intake accepts any player) cast Fire Arrow at each other every 32 ticks, so several missiles with their smoke trails are in flight.
Prints ms per tick (mean / p95 / max, simulation only) and ms per frame (draw list + terrain + sprites on an off-screen surface, caches warm),
the number of missiles in flight, and the frame periods of 30 and 60 fps for comparison."""

import argparse
import math
import os
import statistics
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from allods2.assets import AssetCache  # noqa: E402
from allods2.cli import open_map  # noqa: E402
from allods2.common import as_fs, game_fs  # noqa: E402
from engine.backend_pygame.render import Caches, draw_frame  # noqa: E402
from engine.backend_pygame.sprites import SpriteCache  # noqa: E402
from engine.backend_pygame.surfaces import SurfaceCache  # noqa: E402
from engine.sim import AttackUnit, CastSpell, Simulation, combat, spells, xp  # noqa: E402
from engine.view import Camera, DrawOptions, TerrainView, build_draw_list  # noqa: E402
from engine.view.drawlist import build_terrain_items  # noqa: E402
from engine.world import World  # noqa: E402

FIRE_ARROW = 1
ENEMIES = 11


def build():
    a = AssetCache(game_fs())
    w = World.from_map(open_map("73"), a, seed=5)
    party = [u for u in w.units.values() if w.players[u.owner].human]
    mage = next(u for u in party if combat.combat_stats(w, u).mage)
    enemies = sorted((u for u in w.units.values() if xp.hostile(w, mage, u)), key=lambda u: math.hypot(u.x - mage.x, u.y - mage.y))[:ENEMIES]
    casters = [mage] + [u for u in party if u is not mage][:2] + enemies[:2]
    for u in casters:                               # everybody casts Fire Arrow: a mana pool, the book bit, the mage flag
        u.mana = u.mana_max = max(u.mana_max, 200)
        u.spellbook = (spells.known_mask(u) | (1 << FIRE_ARROW))
        combat.combat_stats(w, u).mage = True
    return a, w, party, enemies, casters


def commands(w, party, enemies, casters):
    if w.tick % 32:
        return []
    out = []
    for u in party + enemies:
        if u.hp <= 0 or u.id not in w.units:
            continue
        foes = [e for e in (enemies if u in party else party) if e.hp > 0 and e.id in w.units]
        if not foes:
            continue
        t = min(foes, key=lambda e: (math.hypot(e.x - u.x, e.y - u.y), e.id))
        out.append(CastSpell(u.owner, (u.id,), FIRE_ARROW, t.id) if u in casters else AttackUnit(u.owner, (u.id,), t.id))
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=400)
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--size", default="1024x768")
    args = ap.parse_args(argv)
    W, H = (int(v) for v in args.size.split("x"))
    a, w, party, enemies, casters = build()
    sim = Simulation(w, ai=True)
    mage = casters[0]
    cam = Camera(W, H, w.width, w.height, max(mage.x * 32 - W // 2, 0), max(mage.y * 32 - H // 2, 0))
    tv = TerrainView(w, a.tileset())
    caches = Caches(SurfaceCache(tv), SpriteCache(a))
    pygame.display.init()
    pygame.display.set_mode((W, H))
    surf = pygame.Surface((W, H))
    tick_ms, frame_ms, flying = [], [], []
    opts = DrawOptions()

    def frame():
        t0 = time.perf_counter()
        items = build_draw_list(w, cam, w.tick, a, opts)
        draw_frame(surf, caches, build_terrain_items(tv, cam, w.tick), items, cam)
        frame_ms.append((time.perf_counter() - t0) * 1000)

    frame()                                         # warm the caches
    frame_ms.clear()
    for _ in range(args.ticks):
        cmds = commands(w, party, enemies, casters)
        t0 = time.perf_counter()
        sim.step(cmds)
        tick_ms.append((time.perf_counter() - t0) * 1000)
        n = sum(1 for c in w.carriers if c.kind == "missile")
        flying.append(n)
        if w.tick % max(args.ticks // args.frames, 1) == 0 and n:
            frame()
    q = sorted(tick_ms)
    print("units %d, ticks %d, missiles in flight: max %d, mean %.2f" % (len(w.units), args.ticks, max(flying), statistics.mean(flying)))
    print("tick   ms: mean %.3f  p95 %.3f  max %.3f" % (statistics.mean(tick_ms), q[int(len(q) * 0.95)], q[-1]))
    if frame_ms:
        f = sorted(frame_ms)
        print("frame  ms (%dx%d, with missiles): mean %.2f  p95 %.2f  max %.2f over %d frames" % (W, H, statistics.mean(f), f[int(len(f) * 0.95)], f[-1], len(f)))
    print("budgets: 30 fps %.1f ms, 60 fps %.1f ms; the default speed steps one tick per 62.5 ms" % (1000 / 30, 1000 / 60))


if __name__ == "__main__":
    main(sys.argv[1:])

"""Shooter projectiles (ids 1-7, `FUN_00466e18`), the exe's projectile facing (`FUN_004608de`), the one-shot cast sprites (Teleport 0x36, Drain Life 0x3c)
and the status effects that draw nothing.  Synthetic worlds, always run.  Docs: docs/engine/rendering.md "Arrows and shots"."""

import pytest

from allods2.anim.projectiles import direction16
from engine.sim import effects
from engine.view import DrawOptions, build_draw_list
from engine.view import drawlist as dl
from engine.world import Arrow, Flash

from helpers import aset_of, projectile, sprite_file, unit_type
from test_engine_objects import cam
from test_engine_unit_draw import UnitAssets, uassets, unit, world_with

C = 256
SO = [57, 75, 45, 66, 44, 53, 52, 43, 68, 42, 80, 50, 81, 62, 73, 73]       # the crossbowman's table: 8 directions x (x, y)


class ShooterAssets(UnitAssets):
    """Unit type 5 shoots projectile 2 at its ShootDelay 1; type 6 has no projectile; projectile sets by id."""

    def __init__(self, psets=()):
        base = uassets()
        shooter = aset_of(unit_type(5, Projectile=2, ShootDelay=1, ShootOffset=SO, CenterX=64, CenterY=78))
        plain = aset_of(unit_type(6, ShootDelay=1, ShootOffset=SO))
        super().__init__({1: base.units[1], 5: shooter, 6: plain}, objects=base.objects, structures=base.structures)
        self.psets = {p.pid: p for p in psets}

    def projectile_set(self, pid):
        return self.psets.get(pid)


def fight(shooter_cell=(10, 10), target_cell=(15, 10), type_id=5):
    s, t = unit(1, *shooter_cell, type_id=type_id), unit(2, *target_cell, owner=2)
    w = world_with(s, t)
    w.assets = ShooterAssets()
    return w, s, t


def s_centre(u):
    return (u.x * C + u.sub_x, u.y * C + u.sub_y)


def run(w, ticks):
    log = []
    for _ in range(ticks):
        w.tick += 1
        effects.arrow_system(w)
        log.append([(a.live, a.x, a.y, a.age, a.steps, a.facing) for a in w.arrows])
    return log


# --- the projectile facing (FUN_004608de, CONFIRMED asm) ---------------------------------------------------------------------------------

@pytest.mark.parametrize("dx,dy,code", [
    (0, -9, 0), (3, -9, 1), (6, -6, 2), (9, -3, 3), (9, 0, 4),                  # north .. east (screen y grows south)
    (9, 3, 5), (6, 6, 6), (3, 9, 7), (0, 9, 8),                                 # east .. south
    (-3, 9, 9), (-6, 6, 10), (-9, 3, 11), (-9, 0, 12),                          # south .. west
    (-9, -3, 13), (-6, -6, 14), (-3, -9, 15),                                   # west .. north
])
def test_direction_codes(dx, dy, code):
    assert direction16(dx, dy) == code


def test_direction_band_edges_are_the_exes():
    assert direction16(4, -1) == 4 and direction16(3, -1) == 3          # a >= 4b: the axis; else 3a >= 4b: next band
    assert direction16(4, 3) == 5 and direction16(3, 4) == 7 and direction16(1, 4) == 8 and direction16(-1, 4) == 8
    assert direction16(1, -1) == 2 and direction16(-1, -1) == 14 and direction16(1, 1) == 6 and direction16(-1, 1) == 10
    assert sorted({direction16(x, y) for x in range(-40, 41, 3) for y in range(-40, 41, 3)}) == list(range(16))


def test_all_sixteen_facings_pick_their_own_frame():
    pset = projectile(2, sprites={"main": sprite_file(16)}, Phases=1, RotationPhases=16, A16=0, Palette=0)
    got = [pset.frame_at("flight", f, 0, age0=0) for f in range(16)]
    assert [r.index for r in got] == [(f - 8) & 15 for f in range(16)] and not any(r.mirrored for r in got)
    one = projectile(4, sprites={"main": sprite_file(1)}, Phases=1, RotationPhases=1, A16=0, Palette=1)      # the sling stone: one picture
    assert {one.frame_at("flight", f, 3, age0=0).index for f in range(16)} == {0}


# --- the arrow's life (FUN_00466e18 + FUN_0046c1d0) --------------------------------------------------------------------------------------

def test_arrow_spawns_on_the_shoot_delay_and_lands_on_the_targets_centre():
    w, s, t = fight()
    effects.spawn_arrow(w, s, t)
    assert len(w.arrows) == 1 and w.arrows[0].pid == 2 and w.arrows[0].born == w.tick + 1 and not w.arrows[0].live
    log = run(w, 12)
    assert log[0][0][0] and log[0][0][3] == 1                                  # the ShootDelay tick: made and already stepped once (age 1)
    steps = (5 * C) // 200                                                     # distance 5 cells = 1280 units: 6 steps
    assert steps == 6 and log[0][0][4] == steps - 1
    assert [e[0][3] for e in log[:6]] == [1, 2, 3, 4, 5, 6]
    last = log[5][0]
    assert (last[1], last[2]) == (s_centre(t)) and last[4] == 0                 # the last step lands exactly on the target's centre
    assert log[6] == []                                                         # removed on the step after the arrival
    assert not w.arrows


def test_arrow_start_is_the_shoot_offset_point():
    w, s, t = fight()
    assert effects.arrow_origin(w, s) == effects.shoot_origin(w, s)
    k = ((s.facing >> 4) - 8) & 14
    assert effects.arrow_origin(w, s) == (s_centre(s)[0] - (64 - SO[k]) * 8, s_centre(s)[1] - (78 - SO[k + 1]) * 8)


def test_arrow_faces_the_target_every_step_and_follows_a_moving_target():
    w, s, t = fight()
    effects.spawn_arrow(w, s, t)
    run(w, 2)
    assert w.arrows[0].facing == 4                                              # due east (the origin is a few pixels off the row: still the axis band)
    t.x, t.y = 10, 16                                                           # the target steps away to the south
    run(w, 1)
    a = w.arrows[0]
    assert (a.tx, a.ty) == s_centre(t) and a.facing in (6, 7, 8)                 # steering at the new position: south-ish


@pytest.mark.parametrize("cells", [0, 0.5])
def test_close_shots_make_no_arrow(cells):
    w, s, t = fight(target_cell=(10, 10))
    t.sub_x = int(cells * 200) if cells else 0                                  # under 200 units: trunc(dist / 200) = 0 -> the object is never made
    effects.spawn_arrow(w, s, t)
    run(w, 3)
    assert not w.arrows


def test_no_projectile_no_target_or_a_vanished_unit_make_no_arrow():
    w, s, t = fight(type_id=6)
    effects.spawn_arrow(w, s, t)
    assert not w.arrows                                                          # the type has no Projectile
    w, s, t = fight()
    effects.spawn_arrow(w, s, None)
    assert not w.arrows
    effects.spawn_arrow(w, s, t)
    del w.units[t.id]
    run(w, 2)
    assert not w.arrows                                                          # FUN_00466e18 returns when the target lookup fails


# --- drawing ---------------------------------------------------------------------------------------------------------------------------------

def pitems(items):
    return [i for i in items if i.kind == "sprite" and i.sprite and i.sprite[0] == "projectile"]


def test_arrow_draws_one_unshadowed_sprite_at_its_position_for_its_facing():
    w, s, t = fight()
    w.assets.psets = {2: projectile(2, sprites={"main": sprite_file(16)}, Phases=1, RotationPhases=16, A16=0, Palette=0)}
    effects.spawn_arrow(w, s, t)
    run(w, 3)
    a = w.arrows[0]
    items = build_draw_list(w, cam(), w.tick, w.assets, DrawOptions(shadows=True))
    got = pitems(items)
    assert len(got) == 1 and got[0].frame == (a.facing - 8) & 15 and got[0].blend == "opaque"
    assert not [i for i in items if i.kind == "shadow" and i.sprite and i.sprite[0] == "projectile"]       # CONFIRMED: no shadow
    # the sprite's anchor is the world position: no chest height
    assert got[0].sy + 32 == (a.y * 32 >> 8) - items_ground(w, a) - cam().y             # hotspot = Height / 2 = 32


def items_ground(w, a):
    from allods2.formats import objects as fobj
    return fobj.ground_height(w.heights, a.x, a.y, 1, 1)


def test_palette_arrow_gets_the_half_overlay_and_an_alpha_one_is_alpha():
    w, s, t = fight()
    w.assets.psets = {2: projectile(2, sprites={"main": sprite_file(16), "main_b": sprite_file(16)}, Phases=1, RotationPhases=16, A16=0, Palette=1)}
    effects.spawn_arrow(w, s, t)
    run(w, 3)
    got = pitems(build_draw_list(w, cam(), w.tick, w.assets, DrawOptions(shadows=False)))
    assert [i.blend for i in got] == ["opaque", "half"]
    w.assets.psets = {2: projectile(2, sprites={"main": sprite_file(16)}, Phases=1, RotationPhases=16, A16=1)}
    assert [i.blend for i in pitems(build_draw_list(w, cam(), w.tick, w.assets, DrawOptions(shadows=False)))] == ["alpha"]


def test_the_screen_lens_and_unspawned_or_missing_arrows_draw_nothing():
    w, s, t = fight()
    w.arrows.append(Arrow(7, s.id, t.id, 0, live=True, x=10 * C, y=10 * C, tx=15 * C, ty=10 * C, steps=3, age=1))
    assert not pitems(build_draw_list(w, cam(), 0, w.assets, DrawOptions(shadows=False)))                 # 7 = the lens
    w.arrows[:] = [Arrow(2, s.id, t.id, 5)]
    assert not pitems(build_draw_list(w, cam(), 0, w.assets, DrawOptions(shadows=False)))                 # not live
    w.arrows[:] = [Arrow(2, s.id, t.id, 0, live=True, x=10 * C, y=10 * C, tx=15 * C, ty=10 * C, steps=3, age=1)]
    out = build_draw_list(w, cam(), 0, w.assets, DrawOptions(shadows=False))
    assert not pitems(out) and out.missing >= 1


# --- the one-shot cast sprites and the effects that draw nothing ------------------------------------------------------------------------

def test_teleport_and_drain_life_sprites_live_their_exe_lifetimes():
    w, s, t = fight(type_id=5)
    effects.spawn_cast_fx(w, s, 23, None, (20, 12))
    assert [(f.pid, f.life, f.born) for f in w.flashes] == [(0x36, 21, w.tick)] * 2        # two objects: the caster's point and the destination
    assert w.flashes[0].pos == effects.shoot_origin(w, s, table=False) and w.flashes[1].pos == effects.shoot_origin(w, s, (20 * C + 128, 12 * C + 128), table=False)
    w.flashes.clear()
    effects.spawn_cast_fx(w, s, 26, t, None)
    assert [(f.pid, f.life, f.born, f.target) for f in w.flashes] == [(0x3c, 1, w.tick + 1, t.id)]
    for number in (1, 20, 21, 27, 28, 29, 24):                                              # Bless, Haste, Shield, Curse, Slow, Heal, ...: no sprite
        w.flashes.clear()
        effects.spawn_cast_fx(w, s, number, t, None)
        assert not w.flashes
    w.flashes[:] = [Flash(0x3c, 3, 1, None, t.id)]
    w.tick = 4
    effects.flash_system(w)
    assert not w.flashes


def test_flash_draws_on_its_ticks_only_with_the_exes_phase():
    w, s, t = fight()
    w.assets.psets = {0x36: projectile(0x36, sprites={"main": sprite_file(21)}, Phases=21, RotationPhases=1, A16=1, Width=96, Height=96)}
    w.flashes[:] = [Flash(0x36, 5, 21, (12 * C + 128, 12 * C + 128))]
    frames = []
    for tick in range(4, 28):
        got = pitems(build_draw_list(w, cam(), tick, w.assets, DrawOptions(shadows=False)))
        frames.append((tick, [i.frame for i in got]))
    assert [f for tk, f in frames if tk < 5 or tk > 25] == [[], [], []]
    assert [f[0] for tk, f in frames if 5 <= tk <= 25] == list(range(21))                  # phase = age - 1, first drawn age 1


# --- status effects: only Invisibility (12) and Stone Curse (18) change the picture (FUN_00460d4b has no other reader) -------------------------

def picture(mask, owner=1):
    u = unit(1, 10, 10, owner=owner)
    u.effect_mask = mask
    w = world_with(u)
    out = build_draw_list(w, cam(), 0, uassets(), DrawOptions(shadows=True))
    return [(i.kind, i.sprite, i.frame, i.sx, i.sy, i.blend, i.gray, i.shadow_level) for i in out]


@pytest.mark.parametrize("n", [n for n in range(1, 30) if n not in (12, 18)])
def test_every_other_status_effect_draws_exactly_like_no_effect(n):
    assert picture(1 << n) == picture(0)


def test_invisibility_and_stone_curse_do_change_the_picture():
    assert picture(1 << 12) != picture(0)                          # the viewer's own invisible unit: 50 % blit, no b shadow
    assert picture(1 << 18) != picture(0)                          # gray palette, frozen frame


def test_the_info_panel_has_no_status_icons():
    """`FUN_00460d4b`, the only reader of the client effect list, has callers in the map draw, the message loop, the unit draw and shadow, the pick, the
    minimap dots and the projectile tick (REA, rendering.md): none in the UI, so no status icon exists in the original's panel."""
    import inspect
    from engine.ui import info
    src = inspect.getsource(info)
    assert "effect_mask" not in src and "u.effects" not in src and ".effect_list" not in src


# --- the screen lens of projectile 7 (animation.md 4.5) ----------------------------------------------------------------------------------

def test_sonic_arrow_makes_a_lens_item_at_its_position_without_a_sprite():
    w, s, t = fight()
    w.arrows[:] = [Arrow(7, s.id, t.id, 0, live=True, x=12 * C, y=10 * C, tx=15 * C, ty=10 * C, steps=3, age=1)]
    items = build_draw_list(w, cam(), 0, w.assets, DrawOptions(shadows=False))
    lens = [i for i in items if i.kind == "lens"]
    assert len(lens) == 1 and not pitems(items)
    assert (lens[0].sx, lens[0].sy) == (12 * 32 - cam().x, 10 * 32 - cam().y)           # anchor: the world position, relief 0, altitude 0


def test_the_backend_applies_the_lens_in_place_in_draw_order(monkeypatch):
    import numpy as np
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    from allods2.anim.lens import apply_lens
    from engine.backend_pygame.scene import draw_items
    from engine.backend_pygame.sprites import Frame
    from engine.view.drawlist import DrawItem
    f = Frame(64, 64)
    f.arr[:] = np.random.RandomState(3).randint(0, 2 ** 24, f.arr.shape).astype(np.uint32)
    want = apply_lens(f.arr.copy(), 30, 28)
    draw_items(f, types_ns(), [DrawItem("lens", -1, None, 0, 30, 28, 0, 0)])
    assert (f.arr == want).all() and not (want == 0).all()


def types_ns():
    import types
    return types.SimpleNamespace(sprites=None, ball=None)


# --- structure targets (view+0x9d0 holds units and structures; FUN_0040403b files both) ----------------------------------------------------

def test_arrow_at_a_structure_flies_to_its_footprint_centre():
    from types import SimpleNamespace
    from engine.world import MapObject
    w, s, t = fight()
    w.assets.structures = dict(w.assets.structures or {})
    w.assets.structures[21] = SimpleNamespace(W=2, TH=3)                    # structures.reg TileWidth / TileHeight
    ob = MapObject(0x6800, "structure", 21, 15, 12, owner=3, hp=500, hp_max=500, uid=0x800, footprint=((0, 0, True),))
    w.add_object(ob)
    effects.spawn_arrow(w, s, ob)
    assert len(w.arrows) == 1 and w.arrows[0].target == ob.id
    log = run(w, 12)
    last = [e for e in log if e and e[0][4] == 0 and e[0][0]][0][0]
    assert (last[1], last[2]) == (ob.x * C + ob.sub_x - 128 + 2 * 128, ob.y * C + ob.sub_y - 128 + 3 * 128)    # pos - 0x80 + size * 0x80
    assert not w.arrows


# --- big units: units.reg TileSize drives `+0x5c / +0x60` (vtable slots 0x20 / 0x24 return it), the arrow starts from `+8` ---------------------

def big_world(size=2):
    w, s, t = fight()
    w.assets.units[7] = aset_of(unit_type(7, TileSize=size, Projectile=2, ShootDelay=1, ShootOffset=SO, CenterX=64, CenterY=78))
    t.type_id = 7
    return w, s, t


def test_a_big_target_is_aimed_at_its_footprint_centre():
    w, s, t = big_world(2)
    effects.spawn_arrow(w, s, t)
    log = run(w, 12)
    last = [e for e in log if e and e[0][0] and e[0][4] == 0][0][0]
    assert (last[1], last[2]) == (t.x * C + t.sub_x + 128, t.y * C + t.sub_y + 128)       # pos - 0x80 + 2 * 0x80
    w, s, t = big_world(3)
    assert effects.tile_size(w, t) == 3 and effects._target_centre(w, t) == (t.x * C + t.sub_x + 256, t.y * C + t.sub_y + 256)


def test_arrow_start_uses_the_unit_position_but_the_cast_start_the_footprint_centre():
    w, s, t = big_world(2)
    s.type_id = 7
    k = ((s.facing >> 4) - 8) & 14
    px, py = s.x * C + s.sub_x, s.y * C + s.sub_y
    assert effects.arrow_origin(w, s) == (px - (64 - SO[k]) * 8, py - (78 - SO[k + 1]) * 8)                # +8 / +0xc
    assert effects.shoot_origin(w, s) == (px + 128 - (64 - SO[k]) * 8, py + 128 - (78 - SO[k + 1]) * 8)     # +0x5c / +0x60


def test_the_lens_is_clipped_half_open_on_both_the_source_and_the_target_pixel():
    """`FUN_004a6b4b` tests every target and every source pixel with `PtInRect` (half-open: `right` / `bottom` are outside) against the clip rect."""
    import numpy as np
    from allods2.anim.lens import apply_lens
    pix = np.arange(40 * 30, dtype=np.uint32).reshape(30, 40)
    before = pix.copy()
    apply_lens(pix, 39, 0)                                         # the bulge's centre in the top-right corner: three quarters fall outside
    assert pix.shape == (30, 40)
    changed = np.argwhere(pix != before)
    assert len(changed) and changed[:, 0].min() >= 0 and changed[:, 1].max() <= 39
    pix2 = before.copy()
    apply_lens(pix2, 200, 200)                                     # nothing inside the frame: untouched
    assert (pix2 == before).all()

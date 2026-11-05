"""Unit effects (invisibility, stone curse) and cell effect sprites in the draw list.  Synthetic assets, always run.
Spec: docs/engine/rendering.md (unit effects, cell effects), docs/engine/effects.md 6.4."""

import numpy as np

from engine.view import DrawOptions, build_draw_list
from engine.view import drawlist as dl

from helpers import projectile, sprite_file
from test_engine_objects import cam
from test_engine_spell_draw import MissileAssets
from test_engine_unit_draw import uassets, unit, world_with

OPTS = DrawOptions(shadows=True)


def items(w, tick=0, a=None):
    return build_draw_list(w, cam(), tick, a or uassets(), OPTS)


def of(its, kind):
    return [i for i in its if i.kind == kind]


def test_invisible_enemy_is_not_drawn_at_all():
    u = unit(1, 10, 10, owner=2)
    u.hidden = True
    its = items(world_with(u))
    assert not its and not its.picks


def test_invisible_own_unit_is_half_with_the_light_main_shadow_only():
    w = world_with(unit(1, 10, 10))
    plain = items(w)
    u = w.units[next(iter(w.units))]
    u.effect_mask = 1 << 12
    its = items(w)
    main = [i for i in of(its, "sprite") if i.depth[-1] == 2]
    assert main and main[0].blend == "half"
    sh, sh0 = of(its, "shadow"), of(plain, "shadow")
    assert len(sh) == 1 and len(sh0) == 1                       # (the fake set has no `b` file; the real one loses its `b` shadow)
    assert sh[0].shadow_level != sh0[0].shadow_level            # 0x6226d0 (k2) in place of 0x6226cc (k1)
    assert [i.blend for i in of(plain, "sprite") if i.depth[-1] == 2] == ["opaque"]


def test_stone_curse_freezes_the_frame_and_selects_the_gray_table():
    w = world_with(unit(1, 10, 10, facing=0x40))
    u = next(iter(w.units.values()))
    u.effect_mask = 1 << 18
    its = items(w, tick=7)
    spr = of(its, "sprite")
    assert spr and all(i.gray for i in spr)
    ref = uassets().units[1].frame_at("idle", 4, 0)
    assert spr[0].frame == ref.index
    u.effect_mask = 0
    assert not any(i.gray for i in of(items(w, 7), "sprite"))


def test_stone_gate_is_death_stage_two_or_less():
    """`0x463b5c`: the gray frozen frame applies while the death stage byte is <= 2 (alive, dying body, first bones), not for later bones."""
    from engine.view.drawlist import death_stage
    assert [death_stage(h) for h in (1, 0, -10, -11, -20, -21)] == [0, 1, 1, 2, 2, 3]
    w = world_with(unit(1, 10, 10))
    u = next(iter(w.units.values()))
    u.effect_mask = 1 << 18
    for hp, gray in ((0, True), (-11, True), (-21, False)):
        u.hp = hp
        sprites = of(items(w), "sprite")
        assert (len(sprites) == 1 or not gray) and all(i.gray == gray for i in sprites), hp


# --- cell effects -----------------------------------------------------------------------------

class CellAssets(MissileAssets):
    def __init__(self, base, psets):
        super().__init__(base, next(iter(psets.values())))
        self.psets = psets

    def projectile_set(self, pid):
        return self.psets.get(pid)


def cell_assets():
    mk = lambda pid, n, w, h: projectile(pid, sprites={"main": sprite_file(n)}, Phases=n, RotationPhases=1, Width=w, Height=h)
    return CellAssets(uassets(), {15: mk(15, 11, 128, 128), 21: mk(21, 15, 64, 64), 43: mk(43, 1, 32, 64)})


def test_cell_effect_frames_positions_and_passes():
    w = world_with()
    w.cell_fx[(10, 10)] = [1, None, 2, 3, None, None]           # fire, poison, earth carriers
    a = cell_assets()
    c = cam()
    its = build_draw_list(w, c, 5, a, DrawOptions(shadows=False))
    fx = {i.sprite[1]: i for i in its if i.sprite and i.sprite[0] == "projectile"}
    assert set(fx) == {15, 21, 43}
    vx, vy = c.ix // 32, c.iy // 32
    col, row = 10 - vx, 10 - vy
    x, y = 32 * col + 16, dl.cell_fx_y(w.heights, vx, vy, col, row)
    assert y == 32 * row + 16                                   # flat ground: the cell centre
    n = abs(5 // 2 + x * y)
    assert fx[15].frame == 3 + n % 5 and fx[21].frame == n % 15 and fx[43].frame == 0
    assert (fx[15].sx, fx[15].sy) == (x - 64 - c.ix + 32 * vx, y - 64 - c.iy + 32 * vy)
    assert all(i.blend == "alpha" for i in fx.values())
    assert fx[15].depth[0] == fx[43].depth[0] == dl.PASS_CELL and fx[15].depth < fx[43].depth
    assert fx[21].depth[0] == dl.PASS_PROJECTILE


def test_poison_cloud_is_after_missiles_and_fire_after_the_cell_unit():
    w = world_with(unit(1, 10, 10))
    w.cell_fx[(10, 10)] = [1, None, 2, None, None, None]
    its = build_draw_list(w, cam(), 0, cell_assets(), DrawOptions(shadows=False))
    order = [i.sprite[0] for i in its if i.kind == "sprite"]
    assert order.index("unit") < order.index("projectile")


def test_cell_effect_hidden_by_fog():
    w = world_with()
    w.cell_fx[(10, 10)] = [1, None, None, None, None, None]
    w.fog = np.zeros((w.cells.shape[0] + 1, w.cells.shape[1] + 1), np.uint16)
    its = build_draw_list(w, cam(), 0, cell_assets(), DrawOptions(shadows=False))
    assert not [i for i in its if i.sprite and i.sprite[0] == "projectile"]


def test_one_pointer_per_cell_and_layer_the_last_registered_wins():
    """`FUN_00460591`: a layer array holds one object per cell; the registration walks the object map in hash order, so of two bodies of stage >= 2
    on one cell only the later-walked one is drawn (ids in one bucket: the newer registration is walked first, so the OLDER one wins)."""
    a, b = unit(1, 10, 10), unit(2, 10, 10)
    c = unit(3, 12, 10)
    for u in (a, b, c):
        u.hp = -15                                                  # stage 2: the bones layer
    w = world_with(a, b, c)
    drawn = {i.depth for i in of(items(w), "sprite")}
    assert len(drawn) == 2                                          # the cell shared by a and b shows one sprite, c its own
    live = world_with(unit(1, 10, 10), unit(2, 10, 10))             # living units share a layer too
    assert len(of(items(live), "sprite")) == 1
    mixed = world_with(unit(1, 10, 10), (lambda u: (setattr(u, "hp", -15), u)[1])(unit(2, 10, 10)))
    assert len(of(items(mixed), "sprite")) == 2                     # a living unit and bones are different layers

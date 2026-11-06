"""Burning-list sprites: firewall fire and steam (animation.md 4.6; draws `0x409406` / `0x40883f`).  Synthetic assets."""

from allods2.anim import ObjectSet

from engine.view import build_draw_list
from helpers import projectile, sprite_file
from test_engine_objects import FakeAssets, PLAIN, cam, flat_world, obj, orec


class Assets(FakeAssets):
    def __init__(self, objects):
        super().__init__(objects=objects)
        self.p = {8: projectile(8, Width=64, Height=96, sprites={"main": sprite_file(9)}),
                  15: projectile(15, Width=128, Height=128, sprites={"main": sprite_file(11)})}

    def projectile_set(self, pid):
        return self.p.get(pid)


def setup(water=False):
    dead = orec(ID=7, Index=0)
    s = ObjectSet(orec(Index=2, DeadObject=7), dead,
                  sprites={"main": sprite_file(4), "main_b": sprite_file(4), "dead": sprite_file(2), "dead_b": sprite_file(2)})
    a = Assets({5: s})
    w = flat_world([obj(1, 10, 10)])
    if water:
        w.cells[10, 10] |= 8 << 6
    w.burn_start[(10, 10)] = 100
    return w, a


def fx(w, a, tick):
    items = [i for i in build_draw_list(w, cam(), tick, a, PLAIN) if i.kind == "sprite" and i.sprite[0] == "projectile"]
    return [(i.sprite[1], i.frame, i.depth[3]) for i in items], items


def test_fire_frame_is_counter_over_two_placed_by_its_box_and_ends_at_22():
    w, a = setup()
    got, items = fx(w, a, 105)
    assert got == [(15, 2, 4)]
    assert (items[0].sx, items[0].sy) == (32 * 10 + 16 - 64, 32 * 10 + 16 - 64) and items[0].blend == "alpha"
    assert fx(w, a, 121)[0] == [(15, 10, 4)]
    assert fx(w, a, 122)[0] == [] and fx(w, a, 99)[0] == []


def test_fire_is_drawn_after_the_object():
    w, a = setup()
    items = sorted(build_draw_list(w, cam(), 100, a, PLAIN), key=lambda i: i.depth)
    assert [i.sprite[0] for i in items if i.kind == "sprite"][-1] == "projectile"


def test_cell_without_dead_object_has_no_entry():
    w, a = setup()
    ent = next(iter(w.objects.values()))
    ent.type_id = 6
    a.objects[6] = ObjectSet(orec(ID=6, Index=2), None, sprites={"main": sprite_file(4), "main_b": sprite_file(4)})
    assert fx(w, a, 100)[0] == []


def test_steam_on_water_until_counter_18_before_the_object():
    w, a = setup(water=True)
    assert fx(w, a, 104)[0] == [(8, 2, 2), (15, 2, 4)]
    assert fx(w, a, 117)[0] == [(8, 8, 2), (15, 8, 4)]
    assert fx(w, a, 118)[0] == [(15, 9, 4)]

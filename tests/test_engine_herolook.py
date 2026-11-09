"""The sprite folder of a hero (`FUN_0046a215`, docs/formats/animation.md 1.3, engine/herolook.py)."""

import pytest

from engine import herolook
from engine.session import build_game
from helpers import needs_data

pytestmark = needs_data


@pytest.fixture(scope="module")
def game():
    return build_game("32", seed=1)


def hero(game):
    w, a = game
    return w, a, w.units[w.players[1].main_hero]


def test_fighter_hero_in_plate_wears_the_heroes_folder(game):
    w, a, h = hero(game)
    # Start_MF: Iron Long Sword (weapon index 4 -> line 3 `swordsman`), no shield, Iron Plate Cuirass (material 0 -> material.reg `heroes`)
    assert herolook.look_key(w, a, h) == "heroes/swordsman"


def test_dying_hero_uses_unarmed(game):
    w, a, h = hero(game)
    hp, h.hp = h.hp, 0
    try:
        assert herolook.look_key(w, a, h) == "heroes/unarmed"
    finally:
        h.hp = hp


def test_no_armour_gives_heroes_l(game):
    w, a, h = hero(game)
    saved = dict(herolook._template_codes)
    herolook._template_codes[(h.stats.name, id(w.item_table))] = {1: 260}          # the sword only
    try:
        assert herolook.look_key(w, a, h) == "heroes_l/swordsman"
    finally:
        herolook._template_codes.clear()
        herolook._template_codes.update(saved)


def test_shield_appends_underscore_and_leather_material_is_light(game):
    w, a, h = hero(game)
    saved = dict(herolook._template_codes)
    # material 8 (leather) cuirass: `Material8/Path = heroes_l`; a shield (any code) adds `_`
    herolook._template_codes[(h.stats.name, id(w.item_table))] = {1: 260, 2: 0x201, 8: (8 << 12) | 0x412}
    try:
        assert herolook.look_key(w, a, h) == "heroes_l/swordsman_"
    finally:
        herolook._template_codes.clear()
        herolook._template_codes.update(saved)


def test_a_map_human_keeps_its_own_set(game):
    w, a = game
    u = next(u for u in w.units.values() if u.human and u.owner == 2)
    assert herolook.look_key(w, a, u) is None

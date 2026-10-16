"""Spell numbers and effect ids (docs/formats/palettes.md §7)."""

from allods2 import spells
from allods2.reg import load_reg

from helpers import GFS, needs

PROJ_REG = "graphics/projectiles/projectiles.reg"


def test_draw_effects():
    assert spells.effect_id("invisibility") == 0x20
    assert spells.effect_id("stone_curse") == 0x2c


def test_secondary_and_inverse():
    assert spells.effect_id("fire_ball", secondary=True) == 13
    assert spells.spell_of_effect(13) == ("fire_ball", True)
    assert spells.spell_of_effect(64) == ("curse", False)
    assert spells.spell_of_effect(4) is None


@needs("graphics", "projectiles", "projectiles.reg")
def test_projectiles_reg_ids_are_spells():
    reg = load_reg(PROJ_REG, GFS).to_dict()
    files = {v["ID"]: v["File"].lower() for k, v in reg.items() if k != "Global"}
    assert all(spells.spell_of_effect(i) for i in files if i >= 10)
    assert files[spells.effect_id("fire_arrow")] == "firebolt\\sprites"
    assert files[spells.effect_id("heal")] == "healing\\sprites"
    assert spells.effect_id("invisibility") not in files
    assert spells.effect_id("stone_curse") not in files

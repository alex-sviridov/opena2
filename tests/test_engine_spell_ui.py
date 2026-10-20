"""The cast key, the armed spell and the click dispatch (I4b).  Pure logic, always run.
Spec: docs/engine/click-to-move-research.md 1.2-1.5 (btn 5, the cast cursor), docs/data/spells.md 9c.1."""

import pytest

from engine.sim import CastSpell
from engine.ui.cursor import CursorState as S
from engine.ui.orders import CAST, OrderInput, castable_spell
from spell_helpers import FIRE_ARROW, spell_table
from test_engine_combat import fighter, world as base_world


def inp(state="own", sel=(0x6001,), spell=1):
    return OrderInput(1, 640, lambda: sel, lambda: state, spell_fn=lambda: spell)


def test_c_arms_the_cast_mode_with_the_spell_of_the_selection():
    o = inp(spell=3)
    assert o.key("c") == (None, None) and o.pending == CAST and o.spell == 3


@pytest.mark.parametrize("state,sel,spell", [("foreign", (0x6001,), 1), ("none", (), 1), ("own", (), 1), ("own", (0x6001,), 0)])
def test_c_does_nothing_without_an_own_selection_or_a_castable_spell(state, sel, spell):
    o = inp(state, sel, spell)
    assert o.key("c") == (None, None) and o.pending == 0


def test_c_without_a_spell_function_does_nothing_and_rearming_is_harmless():
    o = OrderInput(1, 640, lambda: (1,), lambda: "own")
    o.key("c")
    assert o.pending == 0
    o2 = inp()
    o2.key("c")
    o2.key("c")
    assert o2.pending == CAST


def test_release_on_a_unit_sends_cast_spell_and_resets_the_mode():
    o = inp(spell=1)
    o.key("c")
    what, cmd = o.release(S.CAST, (12, 12), 0x6002)
    assert what == "order" and cmd == CastSpell(1, (0x6001,), 1, 0x6002) and o.pending == 0


def test_release_on_the_ground_sends_nothing_but_resets_the_mode():
    o = inp()
    o.key("c")
    assert o.release(S.CAST, (12, 12), False) == ("order", None) and o.pending == 0
    o.key("c")
    assert o.release(S.CAST, (12, 12), None) == ("order", None) and o.pending == 0


def test_right_release_cancels_the_mode_and_keeps_the_selection():
    o = inp()
    o.key("c")
    assert o.right_release() is None and o.pending == 0         # no SelectUnits: the selection stays (R 1.5)


# --- which spell the selection can cast ---------------------------------------------------------------------

def mage(w, mana, book=1 << FIRE_ARROW):
    u = fighter(w, 1, 10, 15)
    u.combat.mage = True
    u.mana = u.mana_max = mana
    u.spellbook = book
    return u


def selected(w, *units):
    w.players[1].selection = tuple(u.id for u in units)


def test_castable_spell_needs_the_book_and_a_selection_not_the_mana():
    w = base_world()
    w.spell_table = spell_table()
    u = mage(w, 3)
    assert castable_spell(w, 1) == 0                            # not selected
    selected(w, u)
    assert castable_spell(w, 1) == FIRE_ARROW
    u.mana = 2
    assert castable_spell(w, 1) == FIRE_ARROW                   # one short of the cost: the exe's button mask has no mana in it (spells.md 9e.1)
    u.mana = 0
    assert castable_spell(w, 1) == FIRE_ARROW
    u.mana, u.spellbook = 3, 0
    assert castable_spell(w, 1) == 0                            # not in the book
    u.spellbook, u.hp = 1 << FIRE_ARROW, 0
    assert castable_spell(w, 1) == 0                            # dead
    w.spell_table = None
    u.hp = 10
    assert castable_spell(w, 1) == 0                            # no spell table


def test_a_non_mage_with_a_spell_needs_no_mana():
    w = base_world()
    w.spell_table = spell_table()
    u = mage(w, 0)
    u.combat.mage = False
    selected(w, u)
    assert castable_spell(w, 1) == FIRE_ARROW


def test_only_the_prototype_missiles_are_offered():
    from allods2.formats.spelldefs import FIELDS, SpellDef, SpellTable
    f = dict.fromkeys(FIELDS, -1)
    f.update(complication_level=0, mana_cost=1, sphere=3, item=0, target=1, delivery=2, max_range=7, speed=60, distribution=1, damage_min=5, damage_max=10)
    lightning = SpellDef(10, "Lightning", "Lightning", f)          # damage and unit target, but a chain draw: not offered
    w = base_world()
    w.spell_table = SpellTable([lightning])
    u = mage(w, 50, book=1 << 10)
    selected(w, u)
    assert castable_spell(w, 1) == 0

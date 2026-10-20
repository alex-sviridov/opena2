"""Scroll casts (commands 0x25 / 0x26), the scroll slot mask and Ctrl+A in the order input.  Synthetic worlds, always run.
Spec: docs/data/spells.md 9c.5, 9e."""

from dataclasses import replace

from allods2.formats.saves import Item
from engine.sim import CastScroll, Simulation, spells
from engine.ui import OrderInput, spellbook
from engine.sim import SetAutoSpell
from engine.world import CastReleased, CastStarted, Damage

from test_engine_ai_casting import mask, monster, world as cast_world

FIRE_ARROW, POISON_CLOUD = 1, 6
SCROLL = 0x0E00                                  # item class 14


def scroll(spell, charges=50, count=1):
    return Item(SCROLL | spell, count, 100, ((spells.CAST_SPELL_MOD, spell, charges),))


def setup(pack, known=()):
    w = cast_world()
    m = monster(w, 1, 20, 20, owner=1, known=mask(*known) if known else -1, mana=0, mind=30, skills=(30,) * 5)
    m.pack = tuple(pack)
    foe = monster(w, 2, 24, 20, owner=2, hp=400)
    return w, m, foe


def test_a_scroll_cast_takes_one_piece_pays_no_mana_and_uses_the_charges_as_level():
    w, m, foe = setup([scroll(FIRE_ARROW, 50, count=1)])
    sim = Simulation(w)
    sim.step([CastScroll(1, m.id, 0, target_id=foe.id)])
    assert m.pack == () and m.mana == 0
    for _ in range(80):
        sim.step()
    started = [e for e in w.fight_log if isinstance(e, CastStarted)]
    released = [e for e in w.fight_log if isinstance(e, CastReleased)]
    assert started and started[0].spell == FIRE_ARROW
    assert released and released[0].level == 50
    assert any(isinstance(e, Damage) and e.target == foe.id for e in w.fight_log)
    assert m.cast is None and m.mana == 0


def test_a_stack_loses_one_piece_and_a_bad_index_does_nothing():
    stack = Item(SCROLL | FIRE_ARROW, 3, 100, ((spells.CAST_SPELL_MOD, FIRE_ARROW, 50),))
    w, m, foe = setup([stack])
    sim = Simulation(w)
    sim.step([CastScroll(1, m.id, 5, target_id=foe.id)])
    assert m.pack == (stack,) and not m.order
    sim.step([CastScroll(1, m.id, 0, target_id=foe.id)])
    assert m.pack == (replace(stack, count=2),)


def test_an_item_without_a_cast_spell_first_effect_is_lost():
    junk = Item(SCROLL | 3, 1, 10, ((44, 5, 3),))
    w, m, foe = setup([junk, scroll(FIRE_ARROW)])
    Simulation(w).step([CastScroll(1, m.id, 0, target_id=foe.id)])
    assert len(m.pack) == 1 and m.pack[0].code == SCROLL | FIRE_ARROW and m.order == 0


def test_a_cell_cast_with_a_unit_spell_puts_the_scroll_back_and_a_cell_spell_goes_ahead():
    w, m, foe = setup([scroll(FIRE_ARROW), scroll(POISON_CLOUD)])
    sim = Simulation(w)
    sim.step([CastScroll(1, m.id, 0, cell=(25, 20))])
    assert len(m.pack) == 2 and m.order == 0                             # Fire Arrow targets a unit: refused, back in the pack
    sim.step([CastScroll(1, m.id, 1, cell=(25, 20))])
    assert len(m.pack) == 1 and m.order == spells.CELL_ORDER and m.cast_wrapper.item_count == 50


def test_only_the_players_own_living_unit_may_cast():
    w, m, foe = setup([scroll(FIRE_ARROW)])
    foe.pack = (scroll(FIRE_ARROW),)
    Simulation(w).step([CastScroll(1, foe.id, 0, target_id=m.id)])
    assert len(foe.pack) == 1 and foe.order == 0


def test_the_scroll_slot_mask_lists_the_spells_of_class_14_items_with_a_cast_spell():
    w, m, _ = setup([scroll(FIRE_ARROW), scroll(POISON_CLOUD), Item(0x0300 | 5, 1, 1, ()), Item(SCROLL | 9, 1, 1, ((44, 1, 1),))])
    expect = (1 << spellbook.slot_of_spell(FIRE_ARROW)) | (1 << spellbook.slot_of_spell(POISON_CLOUD))
    assert spellbook.scroll_slot_mask(m) == expect


def test_ctrl_a_sends_the_selected_slot_spell_to_the_selected_units_that_know_it():
    sel = (10, 11, 12)
    ordering = OrderInput(1, 1024, lambda: sel, lambda: "own", mask_fn=lambda: 0xFFFFFF)
    ordering.slot = spellbook.slot_of_spell(FIRE_ARROW)
    cmds = ordering.auto_cast(lambda uid, n: uid != 11)
    assert cmds == (SetAutoSpell(1, 10, FIRE_ARROW), SetAutoSpell(1, 12, FIRE_ARROW))
    ordering.slot = -1
    assert ordering.auto_cast(lambda uid, n: True) == ()
    assert ordering.auto_cast(lambda uid, n: True, hover_slot=spellbook.slot_of_spell(POISON_CLOUD))[0].spell == POISON_CLOUD

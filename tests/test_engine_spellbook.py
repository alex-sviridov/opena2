"""The spell panel's data side (J's spellbook window is built on it): the 24 slots, the enable mask, the F4-F12 shortcuts and the tooltip fields.
Spec: docs/data/spells.md 9e (CONFIRMED in allods2.exe: `FUN_004167c2`, `FUN_004c628f`, `FUN_0040c8a0` case 0x40ca16, `FUN_004c72f5`)."""

import pytest

from allods2.formats import spelldefs
from engine.sim import CastSpell
from engine.ui import spellbook as sb
from engine.ui.cursor import CursorState as S
from engine.ui.orders import CAST, OrderInput
from helpers import GFS, needs_data
from spell_helpers import full_table
from test_engine_ai_casting import monster, world as cast_world


def book(*ns):
    return sum(1 << n for n in ns)


# --- the slot table and the masks ----------------------------------------------------------------------------------

def test_the_slot_table_is_the_exes_byte_table_0x5f8124():
    assert sb.SLOT_SPELLS == (1, 2, 3, 4, 24, 20, 21, 26, 13, 12, 11, 10, 5, 6, 7, 8, 25, 22, 23, 27, 19, 18, 17, 16) and sb.SLOTS == 24
    assert [sb.slot_of_spell(n) for n in (1, 5, 16, 24, 27)] == [0, 12, 23, 4, 19]
    assert [sb.spell_of_slot(i) for i in (0, 4, 12, 23)] == [1, 24, 5, 16]
    for n in (9, 14, 15, 28, 29, 0, 30):
        assert sb.slot_of_spell(n) is None          # Acid Stream, Darkness, Light, Curse, Slow: no button


def test_the_book_bits_map_to_slot_bits_like_the_client_update():
    # 0x4103b7: obj+0x18 |= 0x5f8e98[n] for every bit n of obj+0x1c; the table gives slot 0 for spell 1, slot 12 for spell 5, slot 23 for spell 16
    assert sb.slot_mask_of_book(book(1)) == 1
    assert sb.slot_mask_of_book(book(5)) == 1 << 12
    assert sb.slot_mask_of_book(book(16, 24)) == (1 << 23) | (1 << 4)
    assert sb.slot_mask_of_book(book(9, 14, 15, 28, 29)) == 0
    assert sb.slot_mask_of_book(book(*sb.SLOT_SPELLS)) == (1 << 24) - 1


def test_the_mask_follows_the_book_only_not_the_mana_and_ors_over_the_selection():
    w = cast_world()
    a = monster(w, 1, 5, 5, owner=1)
    b = monster(w, 2, 6, 5, owner=1)
    c = monster(w, 3, 7, 5, owner=1)
    a.spellbook, b.spellbook, c.spellbook = book(1), book(5, 9), book(16)
    a.mana = a.mana_max = 0                                     # no mana at all: the button is still enabled
    assert sb.unit_slot_mask(a) == 1 and sb.unit_slot_mask(b) == 1 << 12
    assert sb.selection_slot_mask(w, (a.id, b.id)) == 1 | (1 << 12)
    c.hp = 0
    assert sb.selection_slot_mask(w, (a.id, b.id, c.id)) == 1 | (1 << 12)        # a dead unit adds nothing
    assert sb.selection_slot_mask(w, ()) == 0


# --- the F4-F12 shortcuts and the selected slot ----------------------------------------------------------------------

def orders(mask=1 | (1 << 12), state="own", sel=(0x6001,)):
    box = {"mask": mask}
    o = OrderInput(1, 640, lambda: sel, lambda: state, mask_fn=lambda: box["mask"])
    return o, box


def test_f_key_unbound_does_nothing():
    o, _ = orders()
    assert o.fkey(4) is None and o.pending == 0 and o.slot == -1 and o.hotkeys == [None] * 9


def test_a_slot_click_selects_only_an_enabled_slot():
    o, _ = orders()
    assert o.select_slot(12) and o.slot == 12
    assert not o.select_slot(3) and o.slot == 12                # 0x4c7580: the bit must be in view+0x148 | +0x150
    assert not o.select_slot(-1)


def test_ctrl_f_binds_the_selected_slot_and_f_selects_and_arms_the_cast():
    o, _ = orders()
    o.select_slot(12)
    assert o.fkey(5, ctrl=True) is None and o.hotkeys[1] == 12   # F5 = table index 1; Ctrl+F also arms (the arm test does not look at Ctrl)
    assert o.pending == CAST and o.spell == 5
    o.pending = 0
    o.select_slot(0)
    assert o.fkey(5) is None and o.slot == 12 and o.pending == CAST and o.spell == 5


def test_ctrl_f_without_a_selected_slot_binds_nothing_and_a_bound_slot_is_unbound_from_the_other_keys():
    o, _ = orders()
    o.fkey(4, ctrl=True)
    assert o.hotkeys == [None] * 9
    o.select_slot(0)
    o.fkey(4, ctrl=True)
    o.fkey(12, ctrl=True)                                       # the same slot on another key moves the binding (0x4c73a2 loop: clear every other entry holding it)
    assert o.hotkeys[8] == 0 and o.hotkeys[0] is None


def test_f_key_of_a_disabled_slot_selects_it_but_does_not_arm():
    o, box = orders()
    o.select_slot(12)
    o.fkey(6, ctrl=True)
    o.pending = 0
    box["mask"] = 1                                             # the selection lost the spell (another selection)
    o.fkey(6)
    assert o.slot == 12 and o.pending == 0


def test_f_key_arms_nothing_for_a_foreign_or_empty_selection():
    for state, sel in (("foreign", (0x6001,)), ("none", ()), ("own", ())):
        o, _ = orders(state=state, sel=sel)
        o.select_slot(12)
        o.fkey(7, ctrl=True)
        o.pending = 0
        o.fkey(7)
        assert o.pending == 0 and o.hotkeys[3] == 12


def test_shift_holds_back_the_panel_message():
    o, _ = orders()
    o.select_slot(12)
    o.fkey(4, ctrl=True)
    o.select_slot(0)
    o.pending = 0
    o.fkey(4, shift=True)                                       # no 0x417: the selection stays slot 0; the arm test still uses the bound slot
    assert o.slot == 0 and o.pending == CAST and o.spell == 1
    o.fkey(8, ctrl=True, shift=True)
    assert o.hotkeys[4] is None                                 # Shift+Ctrl neither binds


def test_f_keys_out_of_range_are_ignored():
    o, _ = orders()
    o.select_slot(0)
    assert o.fkey(3, ctrl=True) is None and o.fkey(13, ctrl=True) is None and o.hotkeys == [None] * 9


def test_the_cast_click_uses_the_selected_slot_and_needs_its_bit():
    o, box = orders()
    o.select_slot(12)
    o.fkey(4, ctrl=True)
    what, cmd = o.release(S.CAST, (12, 12), 0x6002)
    assert what == "order" and cmd == CastSpell(1, (0x6001,), 5, 0x6002) and o.pending == 0
    o.fkey(4)
    box["mask"] = 1                                             # FUN_004195fa: nothing is sent unless the mask has the bit
    assert o.release(S.CAST, (12, 12), 0x6002) == ("order", None)


def test_a_cast_click_with_no_selected_slot_sends_nothing():
    o, _ = orders()
    o.select_slot(12)
    o.fkey(4, ctrl=True)
    o.slot = -1                                                 # 0x41784a: FUN_0041f370 < 0
    o.pending = CAST
    o.spell = 0
    o.fkey(4, shift=True)                                       # armed (the bound slot is enabled) but the panel selection is -1
    assert o.pending == CAST and o.spell == 0
    assert o.release(S.CAST, (12, 12), 0x6002) == ("order", None)


def test_c_uses_the_selected_slot_else_the_stand_in_and_needs_a_nonempty_mask():
    o = OrderInput(1, 640, lambda: (0x6001,), lambda: "own", spell_fn=lambda: 1, mask_fn=lambda: 1)
    o.key("c")
    assert o.pending == CAST and o.spell == 1                   # no slot: the fixed stand-in
    o.pending = 0
    o.mask_fn = lambda: (1 << 12) | 1
    o.select_slot(12)
    o.key("c")
    assert o.pending == CAST and o.spell == 5                   # the panel's selection wins
    o.pending = 0
    o.mask_fn = lambda: 0
    o.key("c")
    assert o.pending == 0                                       # btn 5 disabled: neither +0x148 nor +0x150


# --- the tooltip fields -------------------------------------------------------------------------------------------

def fake_world(table=None):
    w = cast_world()
    w.spell_table = table or full_table()
    return w


def caster(w, uid, mask, skill, mind):
    u = monster(w, uid, 5 + uid, 5, owner=1, power=skill, mind=mind)
    u.spellbook = mask
    return u


def test_nothing_without_a_spell_table_or_a_book():
    w = fake_world()
    u = caster(w, 1, 0, 30, 0)
    assert sb.spellbook(w, (u.id,)) == []
    w.spell_table = None
    u.spellbook = book(1)
    assert sb.spellbook(w, (u.id,)) == []


def test_entries_are_ordered_by_slot_and_skip_spells_without_a_slot():
    w = fake_world()
    u = caster(w, 1, book(16, 9, 5, 1), 30, 0)
    assert [(e.slot, e.number) for e in sb.spellbook(w, (u.id,))] == [(0, 1), (12, 5), (23, 16)]


needs_real = needs_data


def real_world():
    from allods2.formats import spelldefs as sd
    w = cast_world()
    w.spell_table = sd.load(GFS)
    return w


def labels():
    from allods2.text import decode_text
    return decode_text(GFS.read("main/text/main.txt")).split("\r\n")


def spells_lines():
    from allods2.text import decode_text
    return decode_text(GFS.read("main/text/spells.txt")).split("\r\n")


@needs_real
def test_fire_arrow_of_one_and_two_casters_hand_computed():
    # Fire Arrow: mana 3, range 7, damage 5..10.  skill 40 + mind 20 - 30 = level 30: m = 30/30 + 1 = 2.0, lo = 10, spread = ftol(20 - 10) = 10, range 7 + 1
    w = real_world()
    a = caster(w, 1, book(1), 40, 20)
    (e,) = sb.spellbook(w, (a.id,))
    assert (e.slot, e.number, e.name, e.mana_cost) == (0, 1, "Fire Arrow", 3)
    assert e.damage == (10, 20) and e.range == (8, 8) and e.duration is None and e.extra is None
    # a second caster of level 60 (skill 70): m = 3.0, lo = 15, spread = 15, range 7 + 2: sums for the damage, min / max for the range
    b = caster(w, 2, book(1), 70, 20)
    (e,) = sb.spellbook(w, (a.id, b.id))
    assert e.damage == (25, 50) and e.range == (8, 9) and e.members == 2
    assert sb.tooltip(e, labels()).endswith("#Damage: 25-50#Range: 8-9")
    assert sb.tooltip(sb.spellbook(w, (a.id,))[0], labels()).endswith("#Mana cost: 3#Damage: 10-20#Range: 8")


@needs_real
def test_the_byte_wrap_of_the_wrapper_level_and_the_clamped_helper_level():
    # skill 5 + mind 10 - 30 = -15: FUN_0051951d adds in a byte, so the wrapper level is 241 (m = 241/30 + 1 = 9.0333: lo 45, spread 45, range 7 + 8);
    # the helpers get the clamped level 0 (Haste speed 0/15 + 1 = 1)
    w = real_world()
    u = caster(w, 1, book(1, 21), 5, 10)
    e1, e21 = sb.spellbook(w, (u.id,))
    assert e1.number == 1 and e1.damage == (45, 90) and e1.range == (15, 15)
    assert e21.number == 21 and e21.speed == (1, 1)


@needs_real
def test_haste_protection_prismatic_bless_stone_curse_shield_rows():
    w = real_world()
    u = caster(w, 1, book(21, 4, 11, 20, 18, 27), 50, 10)        # every school 50 (spell_power): level 30
    by = {e.number: e for e in sb.spellbook(w, (u.id,))}
    assert by[21].speed == (3, 3)                                  # 30 / 15 + 1
    assert by[21].duration == (2791, 2791)                         # ftol(10 * 1.1^30 * 16) = ftol(2791.9)
    assert by[4].resistance == (15, 15) and by[4].range == (6, 6)  # 30 / 2; range 5 + 1
    assert by[11].rays == (3, 3) and by[11].damage == (10, 30)     # min(7, 30/20 + 2); damage 5..15 at m = 2: lo 10, spread ftol(30 - 10) = 20
    assert by[20].max_probability == (44, 44)                      # 30 * 4 / 5 + 20
    assert by[18].duration == (0, 144) and by[18].duration_lo == 0 # 30 * 15 * 16 * 2 / 100; the minimum is forced to 0
    assert by[27].absorption == (6, 6)                             # 30 / 10 + 3
    assert by[27].duration == (5583, 5583)                         # ftol(20 * 1.1^30 * 16) = ftol(5583.8)


def test_tooltip_strings_use_the_exes_formats():
    e = sb.SpellEntry(0, 21, "Haste", "Haste (Homing)#Increases speed", "Increases speed", 10, range_lo=5, range_hi=5, duration_lo=2791, duration_hi=2791,
                      extra=(sb.L_SPEED, 3, 3))
    lab = {k: "L%d" % k for k in range(256)}
    assert sb.tooltip(e, lab) == "Haste (Homing)#Increases speed#L117: 10#L123: 5#L124: 174.4#L182: 3"
    e.duration_lo, e.extra = 0, (sb.L_SPEED, 2, 5)
    assert sb.tooltip(e, lab).endswith("#L124:   0.0 -174.4#L182: 2...5")
    e.extra = (sb.L_RESISTANCE, 15, 20)
    assert sb.tooltip(e, lab).endswith("#L183: +15...+20")
    e.extra = (sb.L_MAX_PROB, 44, 44)
    assert sb.tooltip(e, lab).endswith("#L185: +44%")
    e.extra = (sb.L_ABSORPTION, 6, 9)
    assert sb.tooltip(e, lab).endswith("#L217: 6-9")
    e.extra = (sb.L_RAYS, 4, 4)
    assert sb.tooltip(e, lab).endswith("#L186: 4")


@needs_real
def test_the_tooltip_text_is_the_spells_txt_line_of_the_slot_plus_the_rows():
    w = real_world()
    u = caster(w, 1, book(1), 40, 20)
    (e,) = sb.spellbook(w, (u.id,), spells_lines())
    assert sb.tooltip(e, labels()) == "Fire Arrow (Homing)#Inflicts Fire damage to a single target#Mana cost: 3#Damage: 10-20#Range: 8"
    (e2,) = sb.spellbook(w, (u.id,))                                # without the lines it is rebuilt from the table
    assert e2.text == "Fire Arrow (Homing)#Inflicts Fire damage to a single target"


@needs_real
def test_spells_txt_line_k_describes_the_spell_of_slot_k():
    w = real_world()
    lines = spells_lines()
    for slot, n in enumerate(sb.SLOT_SPELLS):
        head = lines[slot].partition(" (")[0].lower().replace(" ", "")
        want = spelldefs.DESCRIPTION_ALIAS.get(w.spell_table.get(n).display_name.lower(), w.spell_table.get(n).display_name.lower()).replace(" ", "")
        assert head == want, (slot, n, head, want)

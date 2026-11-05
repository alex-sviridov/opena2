"""Info panel readers (docs/engine/ui-layout.md 11.1): who is shown, text rows, portrait recipe.  Synthetic, always run."""

from allods2.formats.unitstats import HUMAN, MONSTER, UnitType
from engine.ui import MainText
from engine.ui import info as I
from engine.sim import xp
from engine.world import Player, World

from test_engine_death import hero, mon, unit, world

TEXTS = MainText(["t%02x" % i for i in range(0x100)])
NAMES = ["n%d" % i for i in range(80)]


def rows(w, u, **kw):
    return {(r.text): r for r in I.text_rows(w, u, TEXTS, NAMES, 1, **kw)}


def test_shown_unit_prefers_the_hovered_one_unless_a_modal_is_open():
    w = world()
    a, b = unit(w, 1, 5, 5), hero(w, 2, 6, 5)
    w.players[1].selection = (b.id,)
    assert I.shown_unit(w, 1, a.id) is a and I.shown_unit(w, 1) is b and I.shown_unit(w, 1, a.id, modal=True) is b
    w.players[1].selection = (a.id, b.id)
    assert I.shown_unit(w, 1) is None and I.selection_summary(w, 1) == ("many", 2)
    w.players[1].selection = ()
    assert I.selection_summary(w, 1) == ("none", None)


def test_count_rows_use_the_exes_strings_and_offsets():
    none = I.count_rows("none", 0, TEXTS)
    assert [(r.text, r.x, r.y, r.flags) for r in none] == [("t2f", 0x48, 0x36, I.CENTRE), ("t30", 0x48, 0x42, I.CENTRE)]
    many = I.count_rows("many", 3, TEXTS)
    assert [(r.text, r.y) for r in many] == [("t31", 0x36), ("t32", 0x42), ("3", 0x4E)]


def test_hero_rows_follow_the_table_and_have_no_level_or_owner_row():
    w = world()
    h = hero(w, 1, 5, 5)
    h.mana, h.mana_max = 0, 0
    r = I.text_rows(w, h, TEXTS, NAMES, 1, "Ann")
    by = {(x.text, x.y): x for x in r}
    assert ("Ann", 0x12) in by and by[("Ann", 0x12)].flags == I.CENTRE and by[("Ann", 0x12)].x == 0x48
    assert by[("t13", 0x2C)].x == 0x73 and by[("t14", 0x40)].x == 0x73                         # Health, Mana labels
    assert by[("%d/%d" % (h.hp, h.hp_max), 0x36)].table == "value" and ("0/0", 0x4A) in by      # Mana is drawn for non-casters
    assert by[("t0f", 0x2C)].flags == I.LEFT and by[("t0f", 0x2C)].table == "label" and by[("t0f", 0x2C)].x == 6
    assert any(x.text == "30" and x.x == 0x50 and x.flags == I.RIGHT and x.y == 0x2C for x in r)      # Body value right-aligned at 0x50
    texts = [x.text for x in r]
    assert not any(t.lower().startswith("level") for t in texts)
    assert ("t1b", 0x70) in by and by[("t1b", 0x70)].table == "header" and by[("t1c", 0x70)].x == 0x4A
    assert [by[("t%02x" % (0x1E + k), 0x7A + 10 * k)].text for k in range(5)] == ["t1e", "t1f", "t20", "t21", "t22"]   # fighter skill labels
    assert [by[("t%02x" % (0x29 + k), 0x7A + 10 * k)].x for k in range(5)] == [0x4A] * 5
    assert ("t23", 0xAE) in by and ("t2e", 0xBA) in by and ("%d" % h.xp_total, 0xBA) in by         # Weight, XP (hero, d == 7)


def test_unnamed_human_gets_the_type_line_and_the_mercenary_or_enemy_tag():
    w = world()
    o = hero(w, 1, 5, 5, owner=2)                                    # a human of the other player, not hostile in this world
    o.stats = UnitType(HUMAN, 1, "Bandit", 1, 3, {"token_size": 1, "mana_max": -1}, (), ())
    o.type_id = 3
    a = {(x.text, x.y) for x in I.text_rows(w, o, TEXTS, NAMES, 1)}
    assert ("n3", 0x1C) in a and ("t54", 0x12) in a                  # unit type 3 line + Mercenary
    w.players[2].relations = (1, 0)                                  # war toward player 1
    a = {(x.text, x.y) for x in I.text_rows(w, o, TEXTS, NAMES, 1)}
    assert ("t53", 0x12) in a and ("t54", 0x12) not in a             # Enemy (hostile, type < 0x40)


def test_detail_levels_gate_the_rows():
    w = world()
    m = unit(w, 1, 5, 5, owner=2)
    full = {x.y for x in I.text_rows(w, m, TEXTS, NAMES, 1, know_all=True)}
    cut = I.text_rows(w, m, TEXTS, NAMES, 1, know_all=False)
    assert {x.text for x in cut} <= {"n1"} | {""} and I.detail(w, 1, m, know_all=False) == 0
    assert 0xD2 in full and 0x70 in full
    own = unit(w, 2, 6, 5, owner=1)
    assert I.detail(w, 1, own, know_all=False) == 7


def test_monster_damage_bit7_is_times_15_and_mages_show_no_dmg_row():
    w = world()
    m = unit(w, 1, 5, 5, owner=2, lo=0x82)
    m.combat.record.sp = 2
    d = rows(w, m)
    assert "30-60" in d and d["30-60"].x == 0x46 and d["30-60"].y == 0x58
    m.combat.mage = True
    assert "t17" not in rows(w, m)                                    # Dmg / Attack labels need `not mage`


def test_item_picture_names():
    assert I.item_picture_name(0xC1E) == "0012030"                    # material 0, class 12, quality 0, index 30 (ui-layout 11.7: P11)
    assert I.item_picture_name(0x104) == "0001004"
    assert I.item_picture_name(0x813) == "0008019"
    assert I.item_picture_name(0xA1A) == "0010026"
    assert I.item_picture_name((2 << 12) | (14 << 8) | 0x35) == "0214053"      # scroll: "%02d%02d%03d"
    assert I.item_picture_name((1 << 12) | (3 << 8) | (2 << 5) | 7) == "0103207"


def test_portrait_is_a_doll_for_humans_and_an_infowindow_bmp_otherwise():
    w = world()
    h = hero(w, 1, 5, 5)
    kind, files = I.portrait(w, h)
    assert kind == "doll" and files[0] == "graphics/interface/heroback/backm.256" and files[1] == "graphics/equipment/mfighter/1.256"
    h.stats = UnitType(HUMAN, 1, "Fighter_Hero", 1, 1, {"token_size": 1, "mana_max": 40, "gender": 1}, (), ())
    kind, files = I.portrait(w, h)
    assert files[0].startswith("graphics/equipment/fmage/")        # a female mage: no hero back, `fmage` body folder
    g = unit(w, 2, 6, 5, owner=2)
    g.face = 2
    assert I.portrait(w, g, lambda u: "goblin") == ("bmp", "graphics/infowindow/goblin2.bmp")
    g.face = 1
    assert I.portrait(w, g, lambda u: "goblin") == ("bmp", "graphics/infowindow/goblin.bmp") and I.portrait(w, g) is None


def test_reading_the_panel_never_caches_combat_stats_in_the_unit():
    w = world()
    h = hero(w, 1, 5, 5)
    h.combat = None
    I.text_rows(w, h, TEXTS, NAMES, 1)
    assert h.combat is None


# --- field sources of the text rows (ui-layout 11.1: sight word `+0x10a`, resistances `+0x15c`, XP `+0x110`, second name `+0xf8`) ----

def _lvl1_hero(w):
    """Level-1 male fighter of ui-layout 11.7: Body 40, Reaction 36, Mind 25, Spirit 17, skills (0, 20, 0, 0, 0, 0), no equipment bonus."""
    from engine.sim.combatstats import ArmourBlock, AttackRecord, CombatStats
    h = hero(w, 1, 5, 5, skills=(0, 20, 0, 0, 0, 0))
    h.combat = CombatStats(AttackRecord(skill=78, lo=12, sp=7), ArmourBlock(43, 4), human=True, attrs=(40, 36, 25, 17))
    h.combat.block.prot = [0, 8, 8, 8, 8, 8]
    return h


def test_human_sight_is_the_recompute_word_with_one_decimal():
    """`FUN_0051366b` `0x513a37`-`0x513a54`: `ftol(((mind + reaction) / 25 + 4) * 256)` (constants 25.0, 4.0, 256.0 at `0x5d0880`/`0x5d0830`/`0x5d0888`);
    the panel prints `word >> 8` and `((word & 255) * 10) >> 8`.  Level-1 hero: (25 + 36) / 25 + 4 = 6.44 -> 1648 = 0x670 -> `6.4`."""
    w = world()
    h = _lvl1_hero(w)
    assert I.sight_word(h, h.combat) == 1648 == 0x670
    assert (I.sight_word(h, h.combat) & 0xFF) * 10 >> 8 == 4
    assert rows(w, h)["6.4"].x == 0x6A and rows(w, h)["6.4"].y == 200 and rows(w, h)["6.4"].flags == I.RIGHT
    h.combat.scan_bonus = 2                                          # an item with scanRange +2: the bonus word `+0xe4 = 2 << 8` is added by `FUN_005113e7`
    assert I.sight_word(h, h.combat) == 1648 + 512 and "8.4" in rows(w, h)
    h.fx.scan_direct = -2                                            # Darkness on a human also lowers `+0xa4` directly
    assert "6.4" in rows(w, h)


def test_monster_sight_is_its_scan_byte_with_a_zero_fraction():
    w = world()
    m = unit(w, 2, 8, 8, owner=2, stats=mon(scan_range=7))
    assert I.sight_word(m, m.combat) == 7 << 8 and "7.0" in rows(w, m, know_all=True)
    m.fx.scan = -2                                                   # Light: `+0xa4 -= value << 8`
    assert I.sight_word(m, m.combat) == 5 << 8


def test_resistance_rows_are_protections_1_to_5_in_the_label_order_fire_water_air_earth_astral():
    """Client `+0x15c + k` <- server `+0xc4 + 2k` = `prot[1 + k]` (`0x469ba8`; the recompute loops `+0xc2 + 2i`, i = 1..5, the send order of mask 0x1000000)."""
    w = world()
    h = _lvl1_hero(w)
    h.combat.block.prot = [99, 8, 9, 10, 11, 12]                     # prot[0] (physical) is never shown
    r = I.text_rows(w, h, TEXTS, NAMES, 1)
    shown = [next(x.text for x in r if x.x == 0x8C and x.y == 0x7A + 10 * k) for k in range(5)]
    assert shown == ["8", "9", "10", "11", "12"] and "99" not in [x.text for x in r]
    assert [next(x.text for x in r if x.x == 0x4A and x.y == 0x7A + 10 * k) for k in range(5)] == ["t29", "t2a", "t2b", "t2c", "t2d"]


def test_xp_row_is_the_sum_of_the_five_pools_and_follows_awards():
    """Client `+0x110` = `+0x16c + .. + 0x17c` (five pools; the pump `0x40fdbe` sums them after every update message, `FUN_004699d2` at creation)."""
    w = world()
    h = _lvl1_hero(w)
    assert I.xp_shown(h) == sum(h.xp) == h.xp_total and rows(w, h)[str(sum(h.xp))].y == 0xBA
    before = sum(h.xp)
    xp.award(w, h, 100, 1)
    assert sum(h.xp) > before and I.xp_shown(h) == sum(h.xp) and str(sum(h.xp)) in rows(w, h)


def test_hero_name_splits_at_the_bar_into_two_lines():
    """The client splits the server's `+0x80` string at `|` (`FUN_0040d9b2`, mask 0x80000000): first part `+0xec` (T+0x12), rest `+0xf8` (T+0x1c)."""
    w = world()
    h = _lvl1_hero(w)
    r = I.text_rows(w, h, TEXTS, NAMES, 1, "Ann|Smith")
    by = {(x.text, x.y): x for x in r}
    assert by[("Ann", 0x12)].x == 0x48 and by[("Smith", 0x1C)].flags == I.CENTRE and by[("Smith", 0x1C)].table == "label"
    plain = {(x.text, x.y) for x in I.text_rows(w, h, TEXTS, NAMES, 1, "Ann")}
    assert ("Ann", 0x12) in plain and not any(y == 0x1C for _, y in plain)


# --- the mage's Dmg row (ui-layout 11.1: the wielded staff's spell, level = its count) -----------------------------------------------

def _mage(w, wspell, human=True, uid=9):
    from spell_helpers import spell_table
    w.spell_table = spell_table()
    m = hero(w, uid, 5, 5)
    m.human = human
    m.combat.mage, m.combat.human, m.combat.weapon_spell, m.combat.attrs = True, human, wspell, (30, 30, 30, 30)
    return m


def test_mage_dmg_row_is_the_staff_spell_at_the_item_count_and_has_no_attack_row():
    w = world()
    m = _mage(w, (1, 1))                                          # Wood Staff {castSpell=Fire_Arrow:1}: 5 * (1/30 + 1) = 5, spread 5
    r = I.text_rows(w, m, TEXTS, NAMES, 1)
    by = {(x.text, x.y): x for x in r}
    assert by[("t17", 0x58)].x == 6 and by[("t17", 0x58)].table == "label"
    assert by[("5-10", 0x58)].x == 0x46 and by[("5-10", 0x58)].flags == I.RIGHT and by[("5-10", 0x58)].table == "value"
    assert not any(x.text in ("t19",) for x in r) and not any(x.y == 0x62 and x.x in (6, 0x46) for x in r)   # no Attack row for a mage
    assert I.staff_damage(w, m, I.combat_of(w, m)) == (5, 10)
    m.combat.weapon_spell = (1, 50)                                # level 50: m = 2.667 -> 13 .. 26 (skill and Mind do not enter)
    assert I.staff_damage(w, m, I.combat_of(w, m)) == (13, 26)


def test_mage_dmg_row_is_absent_without_a_damaging_staff_spell():
    w = world()
    for k, ws in enumerate((None, (99, 5))):                      # no weapon spell, a spell number the table lacks
        m = _mage(w, ws, uid=20 + k)
        assert not any(x.text == "t17" for x in I.text_rows(w, m, TEXTS, NAMES, 1))
    m = _mage(w, (1, 1), human=False, uid=30)                              # the client fills the item slots of humans only
    assert I.staff_damage(w, m, I.combat_of(w, m)) is None
    f = hero(w, 10, 6, 6)                                          # a fighter keeps the weapon Dmg / Attack rows
    assert any(x.text == "t19" and x.y == 0x62 for x in I.text_rows(w, f, TEXTS, NAMES, 1))

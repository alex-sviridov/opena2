"""Player-owned casters (phase K2): the party-AI byte (message 0x46 sub 3), the caster scan `FUN_0056bc7b`, the selected spell (Ctrl+A, message 0x46
sub 4) with `FUN_0056b059` and the range `FUN_0056ac5b`.  Synthetic worlds, always run.  Spec: docs/engine/ai.md 12.8."""

from engine.sim import AttackUnit, CastSpell, SetAutoCast, SetAutoSpell, Simulation, Stop, ai, combat
from engine.world import CastStarted

from test_engine_ai import EAST
from test_engine_ai_casting import emitted, mask, monster, world as cast_world

HEAL, SHIELD, BLESS, HASTE, FIRE_ARROW, INVIS = 24, 27, 20, 21, 1, 12
ALL = ai.AUTO_HEAL | ai.AUTO_BUFF | ai.AUTO_PROT


def world(seed=1, flags=ai.AUTO_HEAL | ai.FRIEND_OWN, **kw):
    w = cast_world(seed)
    w.players[1].autocast = flags
    return w


def mage(w, uid=1, x=20, y=20, known=(HEAL,), mana=50, owner=1, **kw):
    return monster(w, uid, x, y, owner=owner, known=mask(*known), mana=mana, mind=40, skills=(0,) * 5, **kw)


def casts(w):
    return [(c.spell_id, c.target_id) for c in emitted(w) if isinstance(c, CastSpell)]


# --- the byte and the commands (message 0x46 sub 3 and 4) -------------------------------------------------------------------------

def test_the_party_ai_byte_starts_at_zero_and_a_command_stores_the_low_byte():
    w = world(flags=0)
    sim = Simulation(w)
    assert w.players[1].autocast == 0
    sim.step([SetAutoCast(1, 0x138)])
    assert w.players[1].autocast == 0x38
    sim.step([SetAutoCast(9, 5)])                                       # unknown player: ignored
    assert w.players[1].autocast == 0x38


def test_the_selected_spell_toggles_and_only_the_players_own_units_take_it():
    w = world()
    m = mage(w, 1)
    foe = mage(w, 2, 30, 30, owner=2)
    sim = Simulation(w)
    sim.step([SetAutoSpell(1, m.id, FIRE_ARROW)])
    assert m.auto_spell == FIRE_ARROW
    sim.step([SetAutoSpell(1, m.id, HEAL)])                              # another spell replaces it
    assert m.auto_spell == HEAL
    sim.step([SetAutoSpell(1, m.id, HEAL)])                              # the same one switches it off
    assert m.auto_spell == 0
    sim.step([SetAutoSpell(1, foe.id, HEAL), SetAutoSpell(1, 99999, HEAL)])
    assert foe.auto_spell == 0


def test_defaults_leave_the_dump_unchanged_and_set_values_show():
    w = world(flags=0)
    m = mage(w)
    base = w.dump_hash()
    w.players[1].autocast = 8
    assert w.dump_hash() != base
    w.players[1].autocast = 0
    m.auto_spell = 1
    assert w.dump_hash() != base
    m.auto_spell = 0
    assert w.dump_hash() == base


# --- level 8: heal ---------------------------------------------------------------------------------------------------------------

def test_flag_clear_or_low_mana_ends_in_mode_0_and_casts_nothing():
    w = world(flags=0)
    m = mage(w, known=(HEAL, SHIELD))
    m.hp = 10
    m.mode_go = True
    ai.idle(w, m)
    out = emitted(w)
    assert [type(c) for c in out] == [Stop] and not m.mode_go
    w2 = world(flags=ai.AUTO_HEAL)
    n = mage(w2, known=(HEAL,), mana=4)
    n.hp = 10
    ai.idle(w2, n)
    assert casts(w2) == []


def test_a_wounded_mage_heals_itself_then_shields_itself_then_heals_the_worst_friend():
    w = world()
    m = mage(w, known=(HEAL, SHIELD))
    ally = mage(w, 2, 22, 20, known=())
    m.hp = 20
    ai.idle(w, m)
    assert casts(w) == [(HEAL, m.id)]
    m.hp = m.hp_max
    ai.idle(w, m)
    assert casts(w) == [(SHIELD, m.id)]
    m.effect_mask |= 1 << SHIELD
    ally.hp = 5
    ai.idle(w, m)
    assert casts(w) == [(HEAL, ally.id)]
    ally.hp = ally.hp_max
    ai.idle(w, m)
    assert casts(w) == []                                                # mode 0, nothing else at level 8


def test_the_friend_heal_needs_a_second_friend_in_the_list_and_range():
    w = world()
    m = mage(w, known=(HEAL,))
    far = mage(w, 2, 20 + 5, 20, known=())
    far.hp = 5
    ai.idle(w, m)
    assert casts(w) == [(HEAL, far.id)]                                  # Heal range is wide enough here ...
    sp = w.spell_table.get(HEAL)
    w2 = world()
    m2 = mage(w2, known=(HEAL,))
    ai.idle(w2, m2)                                                      # alone: the list holds only itself
    assert casts(w2) == []
    assert sp.max_range >= 5


def test_friend_kinds_follow_the_low_bits_of_the_byte():
    w = world(flags=ai.AUTO_HEAL)
    w.players[1].relations = (18, 1, 0) + (0,) * 13                      # player 3 neutral
    m = mage(w, known=(HEAL,))
    own = mage(w, 2, 22, 20, known=())
    neutral = mage(w, 3, 21, 21, owner=3, known=())
    for u in (own, neutral):
        u.hp = 3
    assert ai.friend_of(w, m, m) and not ai.friend_of(w, m, own) and not ai.friend_of(w, m, neutral)
    w.players[1].autocast = ai.AUTO_HEAL | ai.FRIEND_OWN
    assert ai.friend_of(w, m, own) and not ai.friend_of(w, m, neutral)
    w.players[1].autocast = ai.AUTO_HEAL | ai.FRIEND_NEUTRAL
    assert ai.friend_of(w, m, neutral) and not ai.friend_of(w, m, own)
    w.players[1].relations = (18, 1, 2) + (0,) * 13                      # player 3 allied
    assert not ai.friend_of(w, m, neutral)
    w.players[1].autocast = ai.AUTO_HEAL | ai.FRIEND_ALLY
    assert ai.friend_of(w, m, neutral)
    foe = mage(w, 4, 23, 20, owner=2, known=())
    w.players[1].autocast = 0xFF
    assert not ai.friend_of(w, m, foe)                                   # at war: never a friend


# --- level 0x10: Bless, Haste -----------------------------------------------------------------------------------------------------

def test_bless_goes_to_non_mages_then_haste_and_the_20_tick_freshness_applies():
    # the first friend of the list is the caster itself (a mage: no Bless, Haste on itself), then the fighter
    w = world(flags=ai.AUTO_HEAL | ai.AUTO_BUFF | ai.FRIEND_OWN)
    m = mage(w, known=(BLESS, HASTE))
    fighter = monster(w, 3, 22, 20, owner=1)
    ai.idle(w, m)
    assert casts(w) == [(HASTE, m.id)]
    m.effect_mask |= 1 << HASTE
    ai.idle(w, m)
    assert casts(w) == [(BLESS, fighter.id)]
    fighter.effect_mask |= 1 << BLESS
    ai.idle(w, m)
    assert casts(w) == []                                                # Bless was aimed at it a moment ago (mark 20 within 20 ticks): skipped
    w.tick += 30
    ai.idle(w, m)
    assert casts(w) == [(HASTE, fighter.id)]


def test_buffs_need_ten_mana_and_the_level_bit():
    w = world(flags=ai.AUTO_HEAL | ai.AUTO_BUFF)
    m = mage(w, known=(HASTE,), mana=9)
    ai.idle(w, m)
    assert casts(w) == []
    w2 = world(flags=ai.AUTO_HEAL)
    n = mage(w2, known=(HASTE,))
    ai.idle(w2, n)
    assert casts(w2) == []


# --- level 0x20: protections, Invisibility ----------------------------------------------------------------------------------------

def test_protections_in_order_then_invisibility_on_a_friend_and_on_itself():
    w = world(flags=ALL | ai.FRIEND_OWN)
    m = mage(w, known=(13, 4, INVIS), mana=200)
    other = mage(w, 2, 22, 20, known=())
    ai.idle(w, m)
    assert casts(w) == [(13, m.id)]
    m.effect_mask |= 1 << 13
    ai.idle(w, m)
    assert casts(w) == [(4, m.id)]
    m.effect_mask |= 1 << 4
    other.effect_mask |= (1 << 13) | (1 << 4)
    ai.idle(w, m)
    assert casts(w) == [(INVIS, other.id)]                               # a friend other than itself, relation word & 3 != 0 (the same owner: 0x12)
    other.effect_mask |= 1 << INVIS
    ai.idle(w, m)
    assert casts(w) == [(INVIS, m.id)]
    m.hidden = True
    ai.idle(w, m)
    assert casts(w) == []


def test_protections_need_forty_mana():
    w = world(flags=ALL | ai.FRIEND_OWN)
    m = mage(w, known=(13,), mana=39)
    ai.idle(w, m)
    assert casts(w) == []


def test_a_cast_by_the_scan_is_a_brain_mode_8_cast_and_marks_the_target():
    w = world()
    m = mage(w, known=(HEAL,))
    m.hp = 10
    ai.idle(w, m)
    assert m.mode_cast and m.cast_target == m.id and m.ai_cast
    assert (m.ai.spell_mark, m.ai.spell_tick) == (HEAL, w.tick)


# --- the selected spell (Ctrl+A) ---------------------------------------------------------------------------------------------------

def test_the_selected_attack_spell_replaces_the_melee_attack_when_affordable():
    w = world(flags=0)
    m = mage(w, known=(FIRE_ARROW,), rng=1)
    foe = monster(w, 2, 24, 20, owner=2)
    m.auto_spell = FIRE_ARROW
    ai.engage(w, m, foe)
    assert casts(w) == [(FIRE_ARROW, foe.id)] and m.mode_cast and not m.mode_attack
    m2 = mage(w, 3, 20, 24, known=(FIRE_ARROW,), mana=0)
    m2.auto_spell = FIRE_ARROW
    ai.engage(w, m2, foe)                                               # cost > mana: the melee mode 5 (and then the scan: flag 0 -> mode 0)
    assert casts(w) == []
    m3 = mage(w, 4, 20, 26, known=(HEAL,))
    m3.auto_spell = FIRE_ARROW
    ai.engage(w, m3, foe)                                               # not in the book
    assert casts(w) == []


def test_the_range_is_the_selected_spells_when_usable():
    w = world()
    m = mage(w, known=(FIRE_ARROW,), rng=1)
    assert combat.attack_range(w, m) == 1
    m.auto_spell = FIRE_ARROW
    sp = w.spell_table.get(FIRE_ARROW)
    from engine.sim import spells
    assert combat.attack_range(w, m) == spells.wrapper_range(sp, spells.Wrapper(FIRE_ARROW), spells.unit_level(m, sp)) & 0xFF > 1
    m.mana = 0
    assert combat.attack_range(w, m) == 1
    m.mana = 50
    m.auto_spell = HEAL
    assert combat.attack_range(w, m) == 1                                # not in the book


def test_selected_heal_shield_and_summon_cases():
    w = world(flags=ai.FRIEND_OWN)
    m = mage(w, known=(HEAL, SHIELD, 25), mana=200)
    foe = monster(w, 5, 26, 20, owner=2)
    ally = mage(w, 2, 22, 20, known=())
    m.auto_spell = HEAL
    ai.engage(w, m, foe)
    assert casts(w) == [] and not m.mode_cast                            # everyone healthy: mode 0
    ally.hp = 4
    ai.engage(w, m, foe)
    assert casts(w) == [(HEAL, ally.id)]
    m.auto_spell = SHIELD
    ai.engage(w, m, foe)
    assert casts(w) == [(SHIELD, m.id)]
    m.effect_mask |= 1 << SHIELD
    ai.engage(w, m, foe)
    assert casts(w) == []                                                # active Shield: 0, the melee goes on (then the scan: mode 0 at flag 0)
    m.auto_spell = 25
    ai.engage(w, m, foe)
    assert casts(w) == [(25, m.id)] and not m.ai_cast                    # no brain+0x60


def test_selected_curse_goes_to_the_target_or_to_a_foe_that_lacks_it():
    w = world(flags=0)
    m = mage(w, known=(28,))
    foe = monster(w, 2, 24, 20, owner=2)
    other = monster(w, 3, 25, 21, owner=2)
    m.auto_spell = 28
    ai.engage(w, m, foe)
    assert casts(w) == [(28, foe.id)]
    foe.effect_mask |= 1 << 28
    ai.engage(w, m, foe)
    assert casts(w) == [(28, foe.id)]                                    # another foe lacks it: still aimed at the target (the quirk)
    other.effect_mask |= 1 << 28
    ai.engage(w, m, foe)
    assert casts(w) == []


def test_area_spells_need_more_foes_than_friends_in_the_square():
    w = world(flags=0)
    m = mage(w, known=(6,), mana=200)
    f1 = monster(w, 2, 26, 20, owner=2)
    monster(w, 3, 27, 20, owner=2)
    m.auto_spell = 6
    ai.engage(w, m, f1)
    assert casts(w) == [(6, f1.id)]
    w2 = world(flags=0)
    n = mage(w2, known=(6,), mana=200)
    g1 = monster(w2, 2, 26, 20, owner=2)
    for i in range(3):
        mage(w2, 10 + i, 27, 19 + i, known=())                           # three friends in the radius-2 square round the foe
    n.auto_spell = 6
    ai.engage(w2, n, g1)
    assert casts(w2) == []


def test_a_player_attack_order_runs_the_same_decision_when_the_ai_is_on():
    w = world(flags=0)
    m = mage(w, known=(FIRE_ARROW,), rng=1)
    foe = monster(w, 2, 24, 20, owner=2)
    m.auto_spell = FIRE_ARROW
    sim = Simulation(w)
    for _ in range(40):
        sim.step([AttackUnit(1, (m.id,), foe.id)] if _ == 0 else [])
    assert any(isinstance(e, CastStarted) and e.caster == m.id and e.spell == FIRE_ARROW for e in w.fight_log)

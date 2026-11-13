"""The campaign spine (phase L1, docs/engine/campaign.md, triggers.md 11): Scenario.dll's completion cases and town dialogue, the roster carry-over, the
recruits, the mercenary variants, the death hook; the chain over the real maps (skipped without the install).  The synthetic tests always run."""

import pytest

from allods2.formats import saves as SV
from allods2.formats import unitstats as U
from engine import campaign as CG
from engine import party as PT
from engine.sim import campaign as C

from helpers import GFS, needs_data
from test_engine_ai import unit, world
from test_engine_party import Assets, Types
from test_progression import human


def word(t, a, b):
    return (t << 28) | (b << 16) | a


def done(camp, *missions):
    for m in missions:
        camp.vars[0x380 + m] = 1


def complete(camp, n, v=None):
    camp.vars.update(v or {})
    camp.available.append((C.MISSION, n))
    camp.enter((C.MISSION, n))
    return camp.leave()


# --- Scenario.dll completion cases (11.1 item 6) --------------------------------------------------------------------------------------

def test_mission_21_follows_var_0x304_not_0x303():
    c = C.Campaign.new_game()
    complete(c, 20, {0x303: 1})
    assert (C.MISSION, 21) not in c.available and (C.TOWN, 2) in c.available
    c = C.Campaign.new_game()
    complete(c, 20, {0x304: 1})
    assert (C.MISSION, 21) in c.available


def test_case_50_sets_0x303_and_adds_mission_52_when_var_0x30c():
    c = C.Campaign.new_game()
    complete(c, 50)
    assert c.get(0x303) == 1 and (C.MISSION, 52) not in c.available and (C.TOWN, 3) in c.available
    c = C.Campaign.new_game()
    complete(c, 50, {0x30C: 1})
    assert (C.MISSION, 52) in c.available


def test_cases_60_and_70_set_their_variables():
    c = C.Campaign.new_game()
    complete(c, 60)
    assert c.get(0x306) == 1 and (C.MISSION, 80) in c.available
    c = C.Campaign.new_game()
    assert complete(c, 70) == -1 and c.get(0x302) == 1 and c.get(0x309) == 1
    c = C.Campaign.new_game()
    c.vars[0x30A] = 1
    assert complete(c, 70) == 3                                     # 80 was done first: cutscene 3


def test_the_cases_put_mercenaries_on_offer():
    c = C.Campaign.new_game()
    for n, hero, town in ((20, 1, 2), (50, 3, 3), (60, 6, 2), (70, 4, 3), (100, 7, 2)):
        complete(c, n)
        assert c.get(0x213 + hero) == 1 and c.get(0x227 + hero) == town, n


def test_the_completion_loop_promotes_a_hired_mercenary_and_clears_every_hire_flag():
    c = C.Campaign.new_game()
    c.vars.update({0x214: 1, 0x215: 2, 0x216: 1, 0x217: 0, 0x200: 1, 0x201: 1, 0x203: 1})
    complete(c, 31)
    assert (c.get(0x214), c.get(0x215), c.get(0x216), c.get(0x217)) == (2, 2, 1, 0)      # hired 1 -> 2, hired 2 -> 2, not hired 1 -> 1, 0 stays 0
    assert all(c.get(0x200 + k) == 0 for k in range(20))
    complete(c, 20)                                                 # a marker made by a case is not promoted in the same call
    assert c.get(0x214) == 1 and c.get(0x228) == 2


# --- town dialogue (11.2) --------------------------------------------------------------------------------------------------------------

def test_enter_inn_words_of_chapter_10_and_the_mission_10_offer():
    c = C.Campaign.new_game()
    assert c.enter_inn_words(1) == [0x000900CF, 0x0008083C, 0x300A0205]
    assert (C.MISSION, 10) not in c.available
    c.talk_to(0x300A0205)
    assert (C.MISSION, 10) in c.available and c.get(0x301) == 1
    for w in (0x000900CF, 0x0008083C):                              # type 0 NPC words do nothing
        c.talk_to(w)
    assert c.available == [(C.TOWN, 1), (C.MISSION, 10)]


def test_enter_inn_words_by_chapter_and_gates():
    c = C.Campaign.new_game()
    c.vars[0x300] = 30
    assert c.enter_inn_words(2) == [word(3, 0x16, 30), word(3, 0x83C, 31), word(0, 0x83E, 39)]
    done(c, 31)
    assert word(3, 0x83C, 31) not in c.enter_inn_words(2)
    c.vars[0x300] = 40
    assert c.enter_inn_words(3) == [word(3, 0x16, 40), word(0, 0x83C, 48), word(3, 0x7DF, 41), word(3, 0x83F, 42), word(3, 0x7D4, 43)]
    c.vars[0x300] = 50
    assert c.enter_inn_words(2) == [word(0, 0x17, 49), word(3, 0x7E3, 53)]
    c.vars[0x300] = 20
    assert c.enter_inn_words(2) == []


def test_town_3_rows_and_the_class_slot():
    c = C.Campaign.new_game()
    c.vars.update({0x300: 70, 0x303: 1, 0x306: 1, 0x302: 1})
    assert c.enter_inn_words(3) == [word(3, 0x2A8, 70), word(3, 0x2A9, 71), word(0, 5, 79), word(0, 0x2A3, 78)]
    c.vars.update({0x300: 60, 0x380 + 53: 1, 0x380 + 63: 1})
    for mage, female, s in ((False, False, 0), (False, True, 1), (True, True, 2), (True, False, 3)):
        w = c.enter_inn_words(2, mage, female)
        assert word(3, 0x7E6, 74 + s) in w and word(3, 0x16, 62) in w
    done(c, 74)
    assert word(3, 0x7E6, 84) in c.enter_inn_words(2)
    done(c, 84)
    assert word(3, 0x7E6, 93) in c.enter_inn_words(2)


def test_mercenary_words_and_talk_to_toggle():
    c = C.Campaign.new_game()
    c.vars[0x300] = 30
    c.offer_mercenary(1, 2)
    assert c.enter_inn_words(2)[-1] == (1 | 0x10000000) and (1 | 0x10000000) not in c.enter_inn_words(3)      # listed only in its own town
    c.talk_to((1 << 28) | 1)
    assert c.get(0x200) == 1 and c.enter_inn_words(2)[-1] == (1 | 0x10000000 | 1 << 31)
    c.talk_to((1 << 28) | 1)
    assert c.get(0x200) == 0
    c.vars[0x214] = 2
    assert c.enter_inn_words(2)[-1] == (1 | 0x20000000)


def test_talk_to_special_words():
    c = C.Campaign.new_game()
    c.talk_to(word(3, 0x16, 30))
    assert (C.MISSION, 30) in c.available and (c.get(0x215), c.get(0x229)) == (1, 2)
    c.talk_to(word(0, 5, 79))
    assert (c.get(0x218), c.get(0x22C), c.get(0x306)) == (1, 3, 2)
    c.talk_to(word(0, 0x2A3, 0x4E))
    assert c.get(0x302) == 2
    n = len(c.available)
    c.talk_to(word(3, 0x16, 51))                                    # 51 is named by no word: not a known location
    c.talk_to(word(3, 0x16, 83))
    assert len(c.available) == n


# --- the unlock order ---------------------------------------------------------------------------------------------------------------

def test_unlock_order_from_the_start():
    g = CG.CampaignGame()
    g.new_game()
    assert g.camp.available == [(C.MISSION, 10)] and g.next_mission() == 10        # town 1 left the list after the visit
    order = []
    for _ in range(40):
        n = g.next_mission()
        if n is None:
            break
        order.append(n)
        g.camp.enter((C.MISSION, n))
        g.camp.leave()
        g.visit_towns()
    assert order[:9] == [10, 20, 30, 31, 40, 41, 42, 43, 32]                       # 21 only with Var(0x304)
    assert 21 not in order and 51 not in order and 83 not in order and order[-1] == 110


def test_the_chapter_decides_which_mission_the_first_visit_offers():
    g = CG.CampaignGame()
    g.new_game(visit=False)
    assert g.camp.available == [(C.TOWN, 1)]
    g.visit_towns()
    assert g.camp.available == [(C.MISSION, 10)]


def test_a_hero_choice_sets_the_class_variables():
    for key, mage, female in (("MF", 0, 0), ("FF", 0, 1), ("MM", 1, 0), ("FM", 1, 1)):
        g = CG.CampaignGame()
        g.new_game(CG.HeroChoice(key))
        assert (g.camp.get(0x308), g.camp.get(0x30D)) == (mage, female) and g.roster[0].server_id == PT.START[key] and g.roster[0].net_id == 1


# --- synthetic worlds: roster, carry-over, recruit, death hook -------------------------------------------------------------------------

class Mercs(Types):
    def __init__(self):
        super().__init__()
        if True:
            self.t.update({10020 + k: human("2MercenaryKnight%d" % k, 10020 + k, skill_blade=25 + 9 * k, movement_type=1, face=1) for k in range(0, 10)})
        self.m = {10030: human("3Druid", 10030, movement_type=1, face=1), 10034: human("3Druid60", 10034, movement_type=1, face=1)}

    def lookup(self, human_, sid):
        return self.t.get(sid) if human_ else self.m.get(sid)


class MercAssets(Assets):
    def __init__(self):
        self.types = Mercs()


def placed(roster_entries, w=None):
    w = w or world()
    out = PT.place_party(w, MercAssets(), [(24, 24)], roster=PT.Roster(roster_entries))
    return w, out


def fresh_roster():
    return [PT.RosterEntry(0x15, 10210, True, 1, None, PT.HeroSpec(name="Aldor")), PT.RosterEntry(0x16, 10220, True, 2)]


def test_roster_placement_main_hero_first_then_list_order_ids_and_numbers():
    w, out = placed(fresh_roster() + [PT.RosterEntry(2, 10020, True, 7)])
    assert [u.server_id for u in out] == [10210, 10220, 10020] and [u.net_id for u in out] == [1, 2, 7]
    assert w.players[1].main_hero == out[0].id and [PT.hero_number(u) for u in out] == [0x15, 0x16, 2] and out[0].name == "Aldor"
    assert (out[0].x, out[0].y) == (24, 24)


def test_a_fresh_party_is_unchanged_by_the_roster_parameter():
    w1, w2 = world(), world()
    a = PT.place_party(w1, Assets(), [(20, 24)], count=3)
    b = PT.place_party(w2, Assets(), [(20, 24)], count=3, roster=None)
    assert [(u.id, u.x, u.y, u.net_id) for u in a] == [(u.id, u.x, u.y, u.net_id) for u in b] and w1.dump_hash() == w2.dump_hash()


def test_carry_over_round_trip_and_cleanup():
    w, out = placed(fresh_roster() + [PT.RosterEntry(2, 10020, True, 7)])
    main, knight, merc = out
    main.xp, main.xp_total = (50, 9, 8, 7, 6), 80
    main.skills = (0, 30, 5, 4, 3, 2)
    main.name = "Aldor"
    sword = SV.Item(0x0101, 1, 77, ((44, 3, 4),))
    main.pack = (SV.Item(0x0202, 3), sword)
    main.equipment = (sword,) + (SV.Item(),) * 11
    main.hp, main.mana = 1, 0
    main.effects.append(object())
    main.order, main.target, main.mode_attack = 3, 99, True
    summon = unit(w, 90, 30, 30, 1)
    summon.server_id = 555
    monster = unit(w, 91, 31, 31, 2)
    w.players[1].gold, w.players[1].kills_monsters = 1234, 7
    w.remove_unit(knight.id)                                        # the dead are gone
    g = CG.CampaignGame()
    g.camp = C.Campaign.new_game()
    g.roster = fresh_roster()
    g.net_ids.used |= {1, 2}
    new = g.carry_over(w)
    assert [e.number for e in new] == [0x15] and 2 not in g.net_ids.used and 1 in g.net_ids.used
    assert (g.gold, g.kills_monsters) == (1234, 7)
    s = new[0].state
    assert (s.xp, s.xp_total, s.skills, s.name, s.pack, s.equipment) == (main.xp, 80, (0, 30, 5, 4, 3, 2), "Aldor", main.pack, main.equipment)
    # the next map places it again: HP / mana at the maxima, nothing applied, no orders, same id
    w2 = world()
    u, = PT.place_party(w2, MercAssets(), [(20, 20)], roster=PT.Roster(g.roster, g.gold, 0, g.kills_monsters, 0))
    assert u.hp == u.hp_max > 0 and u.mana == u.mana_max and not u.effects and u.order == 0 and u.target is None and not u.mode_attack
    assert (u.xp, u.skills, u.name, u.pack, u.equipment, u.net_id, PT.hero_number(u)) == (main.xp, (0, 30, 5, 4, 3, 2), "Aldor", main.pack, main.equipment, 1, 0x15)
    assert w2.players[1].gold == 1234 and w2.players[1].kills_monsters == 7
    assert monster.id in w.units and not any(x.hero_no == 2 for x in w2.units.values())


def test_a_hero_handed_over_by_the_map_is_carried_and_a_map_unit_keeps_its_free_id_field():
    w, out = placed(fresh_roster())
    mage = unit(w, 77, 40, 40, 1)
    mage.server_id, mage.human = 10230, True
    g = CG.CampaignGame()
    g.camp = C.Campaign.new_game()
    g.roster = fresh_roster()
    g.net_ids.used |= {1, 2}
    new = g.carry_over(w)
    assert [e.number for e in new] == [0x15, 0x16, 0x17] and new[2].net_id == mage.id


def test_leave_mission_order_recruit_and_the_death_hook():
    w, out = placed(fresh_roster())
    g = CG.CampaignGame()
    g.camp = C.Campaign.new_game()
    g.net_ids.used |= {1, 2}
    g.roster = fresh_roster()
    g.camp.available = [(C.MISSION, 40)]
    g.camp.enter((C.MISSION, 40))
    g.camp.vars[0x305] = 0x16
    w.tick = 16 * 5
    res = g.leave_mission(w)
    assert g.camp.times == [5] and res.recruit == 0x17 and g.numbers() == [0x15, 0x16, 0x17]     # Mage_Hero only after 40
    assert {e.net_id for e in g.roster} == {1, 2, 3}
    w, out = placed(g.roster)                                                                    # the next map places the whole roster
    assert [u.server_id for u in out] == [10210, 10220, 10230]
    g.camp.available = [(C.MISSION, 41)]
    g.camp.enter((C.MISSION, 41))
    g.leave_mission(w)
    assert g.numbers() == [0x15, 0x16, 0x17]                                                     # 41 recruits nothing
    w, out = placed(g.roster)
    g.camp.available = [(C.MISSION, 40)]
    g.camp.enter((C.MISSION, 40))
    g.leave_mission(w)
    assert g.numbers().count(0x17) == 1                                                          # absent-only
    g.roster = [e for e in g.roster if e.number != 0x17]
    g.camp.vars[0x300] = 50
    g.camp.available = [(C.TOWN, 2)]
    g.visit_towns()
    assert 0x17 in g.numbers()                                                                   # T0/0x17:49 at chapter 50, he is absent
    assert g.leave_mission(w, "lost").kind == "main_menu"


def test_the_story_hero_in_an_inn_word_is_created_once_and_the_dead_one_again():
    g = CG.CampaignGame()
    g.new_game(visit=False)
    g.camp.vars[0x300] = 30
    g.camp.available = [(C.TOWN, 2)]
    g.visit_towns()
    assert g.numbers() == [0x15, 0x16] and g.roster[1].server_id == 10220 and g.roster[1].net_id == 2
    g.visit_towns()
    assert g.numbers() == [0x15, 0x16]
    g.roster.pop()                                                  # he died: the next visit that lists him creates him fresh
    g.visit_towns()
    assert g.numbers() == [0x15, 0x16] and g.roster[1].state is None


def test_mercenary_hire_policy_and_flags():
    g = CG.CampaignGame(hire=lambda words, camp: [w & 0xFFFF for w in words])
    g.new_game(visit=False)
    g.camp.vars.update({0x300: 30})
    g.camp.offer_mercenary(1, 2)
    g.camp.available = [(C.TOWN, 2)]
    g.visit_towns()
    assert g.camp.get(0x200) == 1 and g.hired() == [1]
    g2 = CG.CampaignGame()
    g2.new_game(visit=False)
    g2.camp.vars.update({0x300: 30})
    g2.camp.offer_mercenary(1, 2)
    g2.camp.available = [(C.TOWN, 2)]
    g2.visit_towns()
    assert g2.hired() == []                                         # no hire by default


def test_a_re_offered_mercenary_cannot_be_hired_and_a_hire_costs_nothing():
    g = CG.CampaignGame(hire=lambda words, camp: [w & 0xFFFF for w in words])
    g.new_game(visit=False)
    g.camp.vars.update({0x300: 30})
    g.camp.offer_mercenary(1, 2)
    g.camp.offer_mercenary(2, 2)
    g.camp.vars[0x215] = 2                                          # mercenary 2 is re-offered (marker 2)
    g.camp.available = [(C.TOWN, 2)]
    g.gold = 7
    g.visit_towns()
    assert g.camp.get(0x200) == 1 and g.camp.get(0x201) == 0       # type 1 hired, type 2 refused (0x49b812)
    assert g.gold == 7                                              # no price in the exe


def test_mercenary_template_by_chapter():
    t = Mercs()
    assert CG.mercenary_template(t, 2, 50) == (10023, True)         # the worked example of 11.3: knight at C = 50
    assert CG.mercenary_template(t, 2, 20) == (10020, True)
    assert CG.mercenary_template(t, 2, 10) == (10020, True)         # 9999 + 20 = 10019 is absent: the base
    assert CG.mercenary_template(t, 2, 110) == (10029, True)
    assert CG.mercenary_template(t, 3, 30) == (10030, False)        # monsters table, no variant 10031: the base
    assert CG.mercenary_template(t, 3, 60) == (10034, False)
    assert CG.mercenary_template(t, 9, 50) is None


def test_death_hook_needs_hp_minus_11_and_has_no_owner_test():
    w, out = placed(fresh_roster() + [PT.RosterEntry(2, 10020, True, 7)])
    merc = out[2]
    c = C.Campaign.new_game()
    c.vars[0x215] = 1
    merc.hp = -10
    CG.death_hook(w, c)
    assert c.get(0x215) == 1
    merc.hp = -11
    CG.death_hook(w, c)
    assert c.get(0x215) == 0
    c.vars[0x215] = 2
    w.remove_unit(merc.id)
    w.corpses[merc.id] = merc                                       # a removed body still decaying: the hook looks at the corpses
    CG.death_hook(w, c)
    assert c.get(0x215) == 0


def test_a_hired_mercenary_that_vanished_from_the_world_is_dead_for_the_campaign():
    w, out = placed(fresh_roster() + [PT.RosterEntry(2, 10020, True, 7)])
    g = CG.CampaignGame()
    g.camp = C.Campaign.new_game()
    g.camp.vars.update({0x215: 1, 0x201: 1})
    g.mercenaries = {out[2].id: 2}
    w.remove_unit(out[2].id)
    g.death_hook(w)
    assert g.camp.get(0x215) == 0


def test_fresh_hero_spec_budget_and_school():
    w = world()
    types = MercAssets()
    ok = PT.HeroSpec((40, 36, 25, 17), 1)
    assert sum(PT.attribute_cost(v) for v in ok.attributes) <= PT.BUDGET
    big = PT.HeroSpec((60, 60, 60, 60))
    assert sum(PT.attribute_cost(v) for v in big.attributes) > PT.BUDGET
    u, = PT.place_party(w, types, [(20, 20)], roster=PT.Roster([PT.RosterEntry(0x15, 10210, True, 1, None, big)]))
    assert [u.stats.get(k) for k in PT.ATTRS] == [25, 25, 25, 25]
    w = world()
    u, = PT.place_party(w, types, [(20, 20)], roster=PT.Roster([PT.RosterEntry(0x15, 10210, True, 1, None, PT.HeroSpec((40, 36, 25, 17), 3))]))
    assert u.skills[3] == 20 and u.skills[5] == 10 and u.skills[1] == 0 and u.best_school == 3 and u.hp == u.hp_max


def test_creation_call_skill_order_and_staff_text():
    """FUN_00514f59 (CONFIRMED): school skill 20, then shooting 10 (index 5), so school 5 ends with 10; the staff string."""
    assert PT.school_skills(3, 7) == (7, 0, 0, 20, 0, 10)
    assert PT.school_skills(5) == (0, 0, 0, 0, 0, 10)
    assert PT.school_skills(0, 7) == (20, 0, 0, 0, 0, 10)
    assert PT.school_equipment_text(2, False) == "Iron Axe"
    assert PT.school_equipment_text(5, False) == "Uncommon Wood Long Bow"
    assert PT.school_equipment_text(1, True) == "Wood Staff {castSpell=Fire_Arrow:20}"
    assert PT.school_equipment_text(4, True, True) == "Uncommon Wood Staff {castSpell=Diamond_Dust:20}"


# --- the real maps ---------------------------------------------------------------------------------------------------------------------

@needs_data
def test_mercenary_variant_of_the_real_data():
    types = CG.CampaignGame(GFS).assets.unit_stats()
    assert CG.mercenary_template(types, 2, 50) == (10023, True)
    assert CG.mercenary_template(types, 2, 20) == (10020, True)
    assert CG.mercenary_template(types, 3, 60)[1] is False and CG.mercenary_template(types, 1, 30) == (10011, True)


@needs_data
def test_the_chain_is_deterministic_and_the_party_is_carried():
    a = CG.run_chain(GFS, through=43, log=lambda *x: None)
    b = CG.run_chain(GFS, through=43, log=lambda *x: None)
    assert a["hash"] == b["hash"] and a["played"] == [10, 20, 21, 30, 31, 40, 41, 42, 43] and not a["failed"]
    g = a["game"]
    assert g.numbers() == [0x15, 0x16, 0x17] and all(e.state is not None for e in g.roster)
    assert g.camp.get(0x304) == 1 and g.camp.get(0x300) == 50 and g.camp.get(0x380 + 40) == 1


@needs_data
def test_a_mission_starts_with_the_carried_roster():
    g = CG.CampaignGame(GFS)
    g.new_game()
    w, _ = g.start_mission()
    heroes = [u for u in w.units.values() if u.owner == 1]
    assert [u.server_id for u in heroes] == [10210] and w.script.scenario_vars is g.camp.vars
    g.roster[0].state = None
    g.leave_mission(w)
    assert g.next_mission() == 20 and g.roster[0].state is not None and g.roster[0].state.hp_max > 0


@needs_data
def test_the_whole_campaign_chain():
    r = CG.run_chain(GFS, log=lambda *x: None)
    assert r["game"].camp.get(0x300) == 0x78 and not r["hard_failed"] and not r["unexpected"]
    assert set(r["unreachable"]) == set(CG.NEVER_OFFERED) | CG.class_alternatives("MF")
    assert r["played"][:3] == [10, 20, 21] and r["played"][-1] == 110 and len(r["played"]) == 34
    assert r["game"].camp.get(0x309) == 1 and r["game"].camp.get(0x30A) == 1


@needs_data
def test_maps_70_and_80_read_the_campaign_variables():
    import logging
    from engine import objective
    logging.disable(logging.WARNING)
    try:
        for n, var in ((70, 0x30A), (80, 0x309)):
            fired = []
            for v in (0, 1):
                g = CG.CampaignGame(GFS)
                g.new_game()
                g.camp.available.append((C.MISSION, n))
                g.camp.vars.update({0x300: n, var: v})
                w, _ = g.start_mission(n)
                assert objective.run(str(n), GFS, world=w)["result"] == "won"
                fired.append({t.position for t in w.script.triggers if w.script.fired[t.position]})
            assert fired[0] != fired[1], n
    finally:
        logging.disable(logging.NOTSET)


@needs_data
def test_female_mage_staff_is_uncommon_and_male_is_plain():
    """`FUN_00514f59` (triggers 9.3): 'Uncommon ' only for the female mage templates (gender 1); 20 charges."""
    from allods2.assets import AssetCache
    codes = {}
    for key in ("MM", "FM"):
        g = CG.CampaignGame(GFS, assets=AssetCache(GFS))
        g.new_game(CG.HeroChoice(key, None, 5, "X"))
        world, _ = g.start_mission(10)
        hero = next(u for u in world.units.values() if u.human and u.owner == 1 and PT.hero_number(u) == 0x15)
        codes[key] = hero.equipment[0]
    assert codes["MM"].code != codes["FM"].code and codes["MM"].mods == codes["FM"].mods == ((41, 26, 20),)


@needs_data
def test_grind_phase_gives_the_carried_hero_xp_and_stays_deterministic():
    """`objective.run(grind=)` / `--grind`: the heroes fight the nearest war-hostile units first, the edits wait; the XP comes from the real combat code."""
    runs = [CG.run_chain(GFS, through=20, grind=900, log=lambda *a: None) for _ in range(2)]
    assert runs[0]["played"] == [10, 20] and not runs[0]["failed"] and runs[0]["hash"] == runs[1]["hash"]
    hero = runs[0]["game"].roster[0].state
    idle = CG.run_chain(GFS, through=20, log=lambda *a: None)["game"].roster[0].state
    assert sum(hero.xp) > sum(idle.xp) == 0 or max(hero.skills[1:]) > max(idle.skills[1:])
    assert runs[0]["hash"] != CG.run_chain(GFS, through=20, log=lambda *a: None)["hash"]       # the idle chain is untouched by the option (default 0)


@needs_data
def test_a_recorded_campaign_mission_replays_with_the_carried_party(tmp_path):
    """The session files of a campaign mission hold the campaign's state at the mission start (`campaign.pkl`), so `replay --verify` rebuilds the carried party
    (a fresh one would give another hash)."""
    from engine import session
    from engine.sim import MoveUnits, Simulation
    r = CG.run_chain(GFS, through=10, grind=900, log=lambda *a: None)
    game = r["game"]
    assert game.roster[0].state is not None                                   # a carried hero (XP from the grind)
    blob = game.snapshot()
    world, _ = game.start_mission(20, seed=5, vision=True)                     # fog on, as `play` runs
    sim = Simulation(world, triggers=True, vision=True)
    rec = session.Recorder(str(tmp_path), "20", 5, game.difficulty)
    rec.save_campaign(blob)
    rec.attach(sim)
    hero = next(u for u in world.units.values() if u.owner == 1 and PT.hero_number(u) == 0x15)
    cmds = [MoveUnits(1, (hero.id,), (hero.x + 3, hero.y + 2))]
    for t in range(120):
        sim.step(cmds if t == 10 else [])
    final = rec.finish("quit")
    got_world, got, recorded = session.replay_session(str(tmp_path), GFS)
    assert recorded["tick"] == got["tick"] == 120
    assert recorded["hash"] == got["hash"]                                    # the same world, tick for tick
    h2 = next(u for u in got_world.units.values() if u.owner == 1 and PT.hero_number(u) == 0x15)
    assert h2.skills == hero.skills and h2.xp == hero.xp and h2.skills != (0,) * 6
    fresh, _ = CG.CampaignGame(GFS, seed=5).new_game(CG.HeroChoice("MF"), visit=True), None
    fw, _ = fresh.start_mission(10, seed=5, vision=True)
    assert fw.dump_hash() != got_world.dump_hash()                           # a fresh party / other mission is another world: the snapshot is what carries the party

"""L10c: the typed server stream (`allods2/formats/serverstream.py`) and town saves <-> `CampaignGame` (`engine/savegame.py`; docs/formats/saves.md 6, 7;
docs/engine/save.md).  Synthetic tests always run; the campaign round trips need the install."""

import struct
from dataclasses import replace

import pytest

from allods2.formats import saves as S
from allods2.formats import serverstream as SS
from allods2.formats.mfc import ArchiveError
from engine import campaign as CG
from engine import party as PT
from engine import savegame as SG
from engine.sim import campaign as C
from helpers import GFS, needs_data
from test_engine_party import Assets, Types
from test_progression import human


# --- the typed stream -----------------------------------------------------------------------------------------------------------------

def eff(kind, value, ptr):
    return SS.Effect(SS.Base(SS.raw12(SS.VT_EFFECT), 0, 0, 0, 0, 0, 0, ptr, 0), kind, 0, value, 0)


def item(code, ptr, effects=(), count=1, new=False):
    return SS.Item(SS.Base(SS.raw12(SS.VT_ITEM, 0, int(new)), 0, code & 31, 0, int(new), 0, 600, ptr, 0x111), list(effects), code, count, 2, 1, 2, 3, 4, 5)


def hero(n, ptr, owner, weapon=None, shield=None, pack=(), spells=None, humanoid=True):
    slots = [weapon, shield] + [None] * 10
    u = SS.Unit(base=SS.Base(SS.raw12(SS.VT_HUMANOID, n, 0), n, 26, 3, 0, 0, 0, ptr, owner), effects=[eff(9, 0x00050003, ptr + 1)], list1c8=[1, 2, 3],
                brain_list=[0xFFFF], weapon=weapon, second=shield, name="Hero %d" % n, words=tuple(range(14)), w_a4=-300, packed=0x01000000 | n,
                pack=SS.Pack(list(pack), 0x7FFF, 7), spells=spells, d5c=5, b48=9, blk_a6=bytes(range(0x18)), mover=bytes(range(0xB4)), brain=bytes(range(0xB8)),
                hum=SS.Humanoid(bytes(range(0x18)), slots) if humanoid else None)
    return u


def synthetic():
    sword, shield = item(0x104, 0x7000, [eff(41, 0x1405, 0x7001), eff(44, 0x0201, 0x7002)]), item(0x205, 0x7010)
    book = SS.Spellbook.from_mask(0b101000, 3)
    h1 = hero(1, 0x1000, 0x500, sword, shield, [item(0xE05, 0x7020, count=3), item(0x305, 0x7030, new=True)], book)
    h2 = hero(2, 0x2000, 0x500)
    h3 = hero(3, 0x3000, 0x500, humanoid=False)
    grp = SS.Group([4, 5], bytes(range(0x50)), [9], [h1, h2], 6, 0x1000, 0x2000)
    grp2 = SS.Group(units=[h3])
    p = SS.Player("Aldor", 1, 2, bytes(range(8)), 2, 0, 3, 123456, 4, 5, 77, 8, 9, 10, 11, 1, 0x500, bytes(range(256)) * 10, [grp, grp2], bytes(range(0x24)))
    p2 = SS.Player("AI", d2c=1, ptr=0x600)
    return SS.ServerStream(12, 34, "map", tuple(range(11)), 0, 2, 5, [p, p2], [h1, h2, h3], 0, b"", (SS.BADFACE, SS.BADFACE), bytes(range(200)) * 2)


def test_typed_round_trip_is_byte_exact_and_keeps_identity():
    s = synthetic()
    raw = s.pack()
    assert len(raw) % 2 == 0
    t = SS.ServerStream.parse(raw)
    assert t == s and t.pack() == raw
    h1 = t.players[0].groups[0].units[0]
    assert t.container[0] is h1 and t.container[1] is t.players[0].groups[0].units[1]       # the container re-names the units by back-reference
    assert h1.weapon is h1.hum.slots[0] and h1.second is h1.hum.slots[1]                     # `+0x74` and slot 1 are one object
    assert h1.hum is not None and t.container[2].hum is None                                   # Humanoid vs plain Unit class
    assert h1.spells.mask == 0b101000 and h1.number == 1


def test_object_pointers_use_mfc_tags():
    raw = synthetic().pack()
    # class names appear once each (a new class record the first time, `0x8000 | index` after)
    assert raw.count(b"Humanoid") == 1 and raw.count(b"Item") == 1 and raw.count(b"Effect") == 1 and raw.count(b"Player") == 1
    assert raw.count(struct.pack("<HH", 0xFFFF, 1)) >= 6


def test_gold_and_kills_are_xored_statistics_are_clamped():
    p = SS.Player(gold=1000, kills_monsters=5, hero_deaths=0x9999, kills_players=2)
    w = SS.MfcWriter()
    p.write_body(w)
    raw = w.getvalue()
    assert struct.pack("<I", 1000 ^ SS.XOR_WORD) in raw and struct.pack("<I", 5 ^ SS.XOR_WORD) in raw
    assert struct.pack("<HH", 0x7FFF, 2) in raw


def test_odd_stream_is_padded_and_the_pad_is_kept():
    s = SS.ServerStream(map_name="m")                      # head 8 + 2 + 44 + 4 + ... : make the length odd
    raw = s.pack()
    assert len(raw) % 2 == 0
    t = SS.ServerStream.parse(raw)
    assert t.pack() == raw
    s2 = SS.ServerStream(map_name="ab")
    raw2 = s2.pack()
    assert SS.ServerStream.parse(raw2).pack() == raw2 and len(raw2) % 2 == 0


def test_mission_branch_stays_raw_and_round_trips():
    for blob in (b"", b"\1\2\3", b"\x55" * 11):
        s = synthetic()
        s.loaded, s.mission_raw = 1, blob
        raw = s.pack()
        t = SS.ServerStream.parse(raw)
        assert t.loaded == 1 and t.mission_raw == blob and t.pack() == raw and t == s
    with pytest.raises(ValueError):
        SS.ServerStream(mission_raw=b"x").pack()


def test_mission_branch_without_the_tail_words_is_refused():
    raw = SS.ServerStream(loaded=1, mission_raw=b"abc").pack()
    bad = raw.replace(struct.pack("<II", SS.BADFACE, SS.BADFACE), b"\0" * 8)
    with pytest.raises(ArchiveError):
        SS.ServerStream.parse(bad)


def test_truncated_and_bad_streams_raise_archive_errors():
    raw = synthetic().pack()
    with pytest.raises(ArchiveError):
        SS.ServerStream.parse(raw[:-300])
    # an Effect where a Player is required
    w = SS.MfcWriter()
    w.u32(0), w.u32(0), w.cstring(""), [w.u32(0) for _ in range(11)], w.u32(0), w.u32(2), w.u32(0)
    w.count(1)
    e = eff(1, 1, 1)
    w.object(e, SS.C_EFFECT, e.write)
    with pytest.raises(ArchiveError):
        SS.ServerStream.parse(w.getvalue())


def test_other_object_classes_round_trip():
    from allods2.formats.mfc import MfcReader, MfcWriter
    objs = [(SS.SackObj(SS.Base(ptr=1), 7, SS.Pack([item(0x104, 9)], 1, 2)), SS.C_SACK, "Sack"), (SS.SpellEffectObj(SS.Base(ptr=2), 3, 4), SS.C_SPELLEFFECT, "SpellEffect"),
            (SS.VirtualCasterObj(SS.Base(ptr=3), 5, b"abcdef"), SS.C_CASTER, "VirtualCaster"),
            (SS.BuildingObj(SS.Base(ptr=4), bytes(range(0x16)), 1, 2, 3, 4, 5, 6, 7, 8, 9), SS.C_BUILDING, "Building")]
    for o, cls, name in objs:
        w = MfcWriter()
        w.object(o, cls, o.write_body)
        t = MfcReader(w.getvalue()).object(SS.CLASSES, name)
        assert t == o


def test_effect_value_mapping_matches_the_a2c_records():
    for mods in [((41, 5, 20),), ((44, 3, 7),), ((46, 1, 200), (9, 4, 0))]:
        for kind, a, b in mods:
            assert SG.value_mod(kind, SG.mod_value(kind, a, b)) == (kind, a, b)
    it = S.Item(0x104, 1, 600, ((41, 5, 20), (44, 2, 3)), True)
    obj = SG.item_object(it, None, 0x99, lambda c=iter(range(1, 99)): next(c))
    assert [e.value for e in obj.effects] == [5 | 20 << 16, 2 | 3 << 8] and obj.base.d08 == 1 and obj.base.d1c == 600 and obj.base.link == 0x99
    assert SG.stored_item(obj) == it
    assert SG.item_object(S.Item(0, 0), None, 0, lambda: 1) is None and SG.stored_item(None) == SG.gear.EMPTY


# --- town saves over a synthetic game ------------------------------------------------------------------------------------------------------

class IndexedTypes(Types):
    """The party tests' three hero templates with distinct data.bin indexes (the file names a template by it)."""

    def __init__(self):
        super().__init__()
        self.t = {sid: replace(t, index=i + 1, server_id=sid) for i, (sid, t) in enumerate(self.t.items())}

    def __iter__(self):
        return iter(self.t.values())


class FakeAssets(Assets):
    def __init__(self):
        self.types = IndexedTypes()

    def items(self):
        raise KeyError("no item table")


def new_game(hero="MF", **kw):
    g = CG.CampaignGame(None, assets=FakeAssets())
    g.new_game(CG.HeroChoice(hero, **kw), visit=False)
    return g


def test_synthetic_new_game_round_trip():
    g = new_game(attributes=(40, 36, 25, 17), school=2, name="Aldor")
    g.gold, g.hero_deaths, g.kills_monsters, g.kills_players = 4321, 2, 77, 3
    g.camp.set(0x301, 7)
    g.camp.set(0x380, 1)
    g.camp.shop[3] = [[499, 0, 100, 2, 0x13C7D318], [1, 2, 3, 4, 5], [0] * 5, [9, 8, 7, 6, 5]]
    g.camp.available = [(C.TOWN, 2), (C.MISSION, 20), (C.MISSION, 30)]
    g.camp.times = [3, 4]
    sv = g.to_save("slot text")
    raw = sv.pack()
    sv2 = S.parse_save(raw)
    assert sv2.pack() == raw and sv2.tail.description == "slot text"
    st = SS.ServerStream.parse(sv2.stream)
    assert st.loaded == 0 and st.tick == 0 and st.block == 0 and st.scenario == 0 and st.words == (0,) * 11 and st.debug == bytes(400)
    p = st.players[0]
    assert (p.gold, p.kills_monsters, p.hero_deaths, p.kills_players, p.name, p.main_hero) == (4321, 77, 2, 3, "Aldor", g.roster[0].net_id)
    g2 = CG.CampaignGame.from_save(sv2, assets=FakeAssets())
    assert SG.comparable(g2) == SG.comparable(g)
    assert g2.to_save("slot text").pack() == raw
    assert g2.camp.times == [7] and g2.camp.location is None and g2.description == "slot text"
    assert sv2.tail.scenario.variables[0x301] == 7 and sv2.tail.mission_tail == (7, 0)
    assert [l.index for l in sv2.tail.scenario.locations] == [2, 20, 30] and sv2.tail.scenario.shop_block(3, 3) == (9, 8, 7, 6, 5)


def test_scenario_block_defaults_and_current_location():
    c = C.Campaign.new_game()
    c.enter((C.TOWN, 1))
    sc = SG.scenario_state(c, {(C.TOWN, 1): (10, 20)})
    assert sc.current == 0 and sc.variables[0x300] == 10 and sc.locations[0] == S.Location(1, C.TOWN, struct.pack("<4i", 10, 20, 10, 20))
    assert sc.shop_block(1, 0) == (0, 1500, 100, 2, 0x1381CC03) and sc.shop_block(0, 0) == (0,) * 5
    c.available = [(C.MISSION, 10), (C.TOWN, 2)]
    c.location = (C.TOWN, 2)
    assert SG.scenario_state(c).current == 1                  # the position of the current location in the list
    back = SG.apply_scenario(C.Campaign(), SG.scenario_state(c))
    assert back.available == c.available and back.location is None and back.vars == {0x300: 10}


def test_client_state_hotkeys_and_knowledge_are_kept():
    g = new_game()
    g.client_state = S.ClientState(name="Zed", view_x=5, view_y=6, spellbook_shortcuts=[1, 2], groups={1: [4, 5]}, options={**{k: 0 for k in S.OPTION_KEYS}, "Speed": 4})
    g.hotkeys = [S.Hotkey(i, 2, b"ab" * i) for i in range(9)]
    g.knowledge = bytes(range(256)) * 10
    g2 = CG.CampaignGame.from_save(g.to_save("d"), assets=FakeAssets())
    assert g2.client_state == g.client_state and g2.hotkeys == g.hotkeys and g2.knowledge == g.knowledge


def test_a_mission_save_is_not_a_town_save():
    sv = new_game().to_save()
    s = SS.ServerStream.parse(sv.stream)
    s.loaded, s.mission_raw = 1, b"\0" * 6
    with pytest.raises(ValueError, match="mission save"):
        CG.CampaignGame.from_save(S.SaveGame(s.pack(), sv.tail), assets=FakeAssets())
    with pytest.raises(ValueError, match="Invalid save file"):
        CG.CampaignGame.from_save(b"\0" * 40)


def test_hero_fields_go_to_the_unit_offsets():
    g = new_game(attributes=(40, 36, 25, 17), school=3, name="Aldor")
    st = SS.ServerStream.parse(g.to_save().stream)
    u = st.players[0].groups[0].units[0]
    assert u.hum is not None and u.name == "Aldor" and u.number == 0x15 and u.base.id == g.roster[0].net_id and u.base.w0c == 1 and u.base.w0e == 3
    assert u.words[:4] == (40, 36, 25, 17) and u.words[8] == u.words[9] and u.words[10] == 100 and u.words[13] == 50       # HP = max, regeneration 100 / 50
    pools = struct.unpack("<6I", u.hum.block)
    assert pools[0] == 3 and sum(pools[1:]) == u.d130
    assert struct.unpack_from("<6h", u.blk_a6, 2)[3] == 20                 # school 3 skill 20 (the creation call)
    assert u.pack is not None and u.pack.d1c == 0x7FFF and u.mover[:2] == b"\x40\x40" and u.brain[0x71] == 1


def test_recruited_hero_is_saved_and_numbers_survive():
    g = new_game()
    g.recruit(0x16)
    g.recruit(0x17)
    g2 = CG.CampaignGame.from_save(g.to_save(), assets=FakeAssets())
    assert g2.numbers() == [0x15, 0x16, 0x17] and [e.net_id for e in g2.roster] == [e.net_id for e in g.roster]
    assert g2.net_ids.used == g.net_ids.used and SG.comparable(g2) == SG.comparable(g)


def test_hero_entry_inverts_hero_unit_for_bonuses_pack_and_book():
    g = new_game()
    e = g.roster[0]
    s = SG.hero_state(g, e)
    s.attr_bonus, s.skill_bonus, s.spellbook, s.auto_spell = (1, 0, 2, 0), (0, 3, 0, 0, 0, 1), 0b1010, 3
    s.wimpy_hp, s.withdraw_hp = 30, 10
    s.pack = (S.Item(0xE05, 3), S.Item(0x305, 1, 450, ((41, 5, 20),), True))
    s.pack_index = 1
    gear = SG.gear
    gear.sync_carried(s)
    e2 = PT.RosterEntry(e.number, e.server_id, True, e.net_id, s)
    types = IndexedTypes()
    u = SG.hero_unit(g, e2, s, None, 1, lambda c=iter(range(0x100, 0x9999, 0x10)): next(c))
    back = SG.hero_entry(u, types).state
    for k in ("skills", "xp", "best_school", "hp_max", "mana_max", "spellbook", "pack", "pack_index", "skill_bonus", "attr_bonus", "auto_spell", "wimpy_hp", "withdraw_hp",
              "type_id", "face", "move_type", "carried", "carried_mods"):
        assert getattr(back, k) == getattr(s, k), k
    assert back.stats.fields["body"] == s.stats.fields["body"] and back.name == s.name


# --- the campaign at several chapters (needs the install) -----------------------------------------------------------------------------------

def chain(through, hero="MF"):
    return CG.run_chain(None, through=through, hero=hero, log=lambda *a: None)["game"]


def same_campaign(g):
    """save -> bytes -> load: the comparable state is equal and a second save is byte-identical."""
    raw = g.to_save("chapter").pack()
    g2 = CG.CampaignGame.from_save(raw)
    assert SG.comparable(g2) == SG.comparable(g)
    assert g2.to_save("chapter").pack() == raw
    return g2


@needs_data
@pytest.mark.parametrize("through", [10, 20, 40, 60, 100])
def test_scripted_campaign_round_trips_at_each_chapter(through):
    g = chain(through)
    g2 = same_campaign(g)
    assert g2.camp.get(C.CHAPTER) == g.camp.get(C.CHAPTER) and g2.camp.available == g.camp.available
    assert [e.number for e in g2.roster] == [e.number for e in g.roster] and g2.next_mission() == g.next_mission()


@needs_data
@pytest.mark.parametrize("hero", ["FF", "MM", "FM"])
def test_other_classes_round_trip(hero):
    g = chain(30, hero)
    same_campaign(g)
    assert g2_mage(g) == (hero[1] == "M")


def g2_mage(g):
    return CG.CampaignGame.from_save(g.to_save().pack()).is_mage


@needs_data
def test_a_new_game_before_any_mission_materialises_the_hero():
    g = CG.CampaignGame(None)
    g.new_game(CG.HeroChoice("MF", (40, 36, 25, 17), 1, "Aldor"))
    assert g.roster[0].state is None
    g2 = same_campaign(g)
    s = g2.roster[0].state
    assert s.name == "Aldor" and s.hp_max == 116 and len([i for i in s.equipment if i.code]) >= 1 and g.roster[0].state is None      # the original is not touched


@needs_data
def test_equipment_pack_and_gold_of_a_played_hero_survive():
    g = chain(40)
    g.gold, g.kills_monsters = 98765, 321
    e = g.roster[0]
    assert any(i.code for i in e.state.equipment)
    g2 = same_campaign(g)
    s1, s2 = e.state, g2.roster[0].state
    assert [(i.code, i.count, tuple(i.mods)) for i in s1.equipment] == [(i.code, i.count, tuple(i.mods)) for i in s2.equipment]
    assert [(i.code, i.count) for i in s1.pack] == [(i.code, i.count) for i in s2.pack] and s1.xp == s2.xp and s1.skills == s2.skills
    assert (g2.gold, g2.kills_monsters) == (98765, 321)


def play(game, count):
    """Continue a campaign `count` missions with the objective run as the player: [(mission, result, tick, chapter, available)]."""
    from engine import objective
    seq = []
    for _ in range(count):
        n = game.next_mission()
        if n is None:
            break
        world, _a = game.start_mission(n)
        r = objective.run(str(n), None, seed=1, world=world, side=CG.SIDE_VARS)
        out = game.leave_mission(world, "won")
        seq.append((n, r["result"], r["tick"], game.camp.get(C.CHAPTER), tuple(game.camp.available), out.kind, tuple(game.numbers())))
        if out.kind == "ending":
            break
    return seq


@needs_data
@pytest.mark.parametrize("through, more", [(20, 4), (60, 4)])
def test_continuing_after_a_load_plays_the_same_missions(through, more):
    g = chain(through)
    loaded = CG.CampaignGame.from_save(g.to_save("save").pack())
    assert play(g, more) == play(loaded, more)
    assert SG.comparable(g)["vars"] == SG.comparable(loaded)["vars"]


def stripped(world):
    """The world dump without what a save cannot keep: the template-equipment heroes get an explicit loadout (`gear` entries, same stats) and an explicit
    zero script variable is the same as an absent one."""
    d = world.dump()
    for u in d["units"]:
        for part in u:
            if isinstance(part, dict):
                part.pop("gear", None)
    d["script"]["vars"] = [kv for kv in d["script"]["vars"] if kv[1]]
    return d


@needs_data
def test_a_saved_hero_starts_the_next_mission_in_the_same_world():
    g = chain(40)
    g2 = CG.CampaignGame.from_save(g.to_save().pack())
    n = g.next_mission()
    w1, _ = g.start_mission(n)
    w2, _ = g2.start_mission(n)
    assert stripped(w1) == stripped(w2)
    h1 = [(u.hero_no, u.hp_max, u.mana_max, u.skills, u.xp, u.name) for u in w1.units.values() if u.human and u.owner == 1]
    assert h1 == [(u.hero_no, u.hp_max, u.mana_max, u.skills, u.xp, u.name) for u in w2.units.values() if u.human and u.owner == 1]

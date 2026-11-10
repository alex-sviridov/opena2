"""The campaign spine, headless (docs/engine/campaign.md; layer 4: no windows, no pygame).

`CampaignGame` keeps what the server and Scenario.dll keep between the maps of a single-player campaign: the variable array and the location
list (`engine.sim.campaign.Campaign`), the human's roster (the heroes that go from map to map), his gold and statistics, the server's free-id
table.  It starts a mission from that state (`start_mission`: the same world as `play`, but the carried party instead of a fresh one), ends it
(`leave_mission`: the carry-over of `FUN_004ebd5f`, `ScenarioLeaveLocation`, the recruit of `FUN_004f312a`) and stands in for the town the player
would visit (`visit_towns`: `ScenarioEnterInn` / `ScenarioTalkTo`, triggers.md 11.2 / 11.5 item 4).
"""

from dataclasses import dataclass

from engine import party as PT
from engine.netids import LIMIT, NetIds
from engine.sim import campaign as C
from engine.world import DEFAULT_DIFFICULTY

STORY = C.STORY_HEROES          # hero numbers 0x15..0x1e: story heroes (the main hero is 0x15)
MAIN_NUMBER = 0x15


@dataclass
class HeroChoice:
    """The character the creation screen hands to `FUN_004f254b`: the template key (`MF` male fighter, `FF` female fighter, `MM` male mage, `FM`
    female mage), optional attributes / school (None = the template's own) and the name."""
    start: str = "MF"
    attributes: tuple = None
    school: int = None
    name: str = "Hero"


def mercenary_template(types, n, chapter):
    """`(server_id, is_human)` of mercenary `n` at chapter `chapter` (triggers.md 11.3, template choice steps 1 and 3), or None when the number has no
    template.  `types` = `AssetCache.unit_stats()`."""
    base = 10000 + 10 * n
    human = types.lookup(True, base) is not None
    if not human and types.lookup(False, base) is None:
        return None
    sid = base
    if any(types.lookup(human, base + j) is not None for j in range(1, 10)):       # a variant series: the record of the chapter, when there is one
        v = 10 * n + 9998 + chapter // 10
        if types.lookup(human, v) is not None:
            sid = v
    return sid, human


def death_hook(world, camp):
    """The client's hero-death write (triggers.md 11.4, exe `0x41050f`): a unit with a hero number 1..20 whose HP the client sees at -11 or below
    (death stage >= 2) sets `Var(0x213 + n)` := 0 (no owner test).  Looks at the units and at the corpses (the removal is at HP <= -10)."""
    for u in list(world.units.values()) + list(world.corpses.values()):
        n = PT.hero_number(u) if u.hero_no or u.human else 0
        if 1 <= n <= C.MERCENARIES and u.hp <= -11:
            camp.set(C.MERC_MARK + n - 1, 0)


def is_hero(u, human_player):
    """A unit the carry-over keeps (`+0xe` in 0x21..0x3f): the party's own heroes, hero number 0x15..0x1e, owned by the human."""
    return u.owner == human_player.id and u.human and PT.hero_number(u) in STORY


class CampaignGame:
    """One single-player campaign.  `hire(words, camp)` = the mercenary hire policy of the town stand-in: returns the mercenary numbers to hire from
    the offered words (default: none; a hire has no price, a type 2 offer cannot be hired)."""

    def __init__(self, install=None, hire=None, seed=1, difficulty=DEFAULT_DIFFICULTY, assets=None):
        self.install = install
        self.hire = hire or (lambda words, camp: ())
        self.seed, self.difficulty = seed, difficulty
        self._assets = assets
        self.camp = C.Campaign()
        self.roster = []                    # [PT.RosterEntry], list order = the player's unit list order (main hero first)
        self.gold = self.hero_deaths = self.kills_monsters = self.kills_players = 0
        self.net_ids = NetIds()             # the server's free-id table: the roster's `unit+4`
        self.mission = None                 # the running mission number
        self.mercenaries = {}               # unit id -> hero number of the hired units of the running mission
        self.log = []                       # one line per town visit / recruit (stand-in transcript)

    # --- assets / small helpers ------------------------------------------------------------------------------------------------

    @property
    def assets(self):
        if self._assets is None:
            from allods2.assets import AssetCache
            self._assets = AssetCache(self.install)
        return self._assets

    @property
    def is_mage(self):
        return bool(self.camp.get(0x308))

    @property
    def is_female(self):
        return bool(self.camp.get(0x30D))

    def numbers(self):
        return [e.number for e in self.roster]

    # --- a new campaign ----------------------------------------------------------------------------------------------------------

    def new_game(self, hero=None, visit=True):
        """`ScenarioNewGame` (variables zero, chapter 10, town 1 available and entered) and the creation call `FUN_004f254b` (the hero is built when the first
        map places the party; its free id is taken now, before any map is loaded).  `Var(0x308)` / `Var(0x30d)` = mage / female (the creation screen,
        exe `0x4896dc`).  `visit`: the stand-in town visit that makes mission 10 available (`TalkTo(0x300a0205)`)."""
        hero = hero or HeroChoice()
        key = hero.start
        self.camp = C.Campaign.new_game()
        self.camp.set(0x308, int(key[1] == "M"))
        self.camp.set(0x30D, int(key[0] == "F"))
        self.net_ids = NetIds()
        spec = PT.HeroSpec(hero.attributes, hero.school, hero.name)
        self.roster = [PT.RosterEntry(MAIN_NUMBER, PT.START[key], True, self.net_ids.alloc(), None, spec)]
        self.gold = self.hero_deaths = self.kills_monsters = self.kills_players = 0
        self.mission, self.mercenaries, self.log = None, {}, []
        if visit:
            self.visit_towns()
        return self

    # --- the town stand-in -------------------------------------------------------------------------------------------------------

    def recruit(self, n):
        """`FUN_004f312a` for a story hero `n` (0x15..0x1e): nothing when a unit of the list already has the number, else the base template
        `10000 + 10 n` (never a chapter variant) is appended to the roster with a free id.  Returns the entry or None."""
        if n not in STORY or n in self.numbers():
            return None
        sid = 10000 + 10 * n
        if self._assets is not None or self.install is not None:
            if self.assets.unit_stats().lookup(True, sid) is None:
                return None
        e = PT.RosterEntry(n, sid, True, self.net_ids.alloc())
        self.roster.append(e)
        self.log.append("recruit hero %#x (template %d)" % (n, sid))
        return e

    def visit_towns(self):
        """What the player does in the towns after a mission, as a stand-in (11.5 item 4): every town in the available list is entered; the story
        heroes among the offered words are created (the inn handler `0x48ba81`); every type 0 / 3 word is accepted by `TalkTo` (DECISION: the
        outcome only adds missions and sets markers); mercenary words are hired as the `hire` policy says (`TalkTo` of a type 1 word; a type 2 word is refused, as the Accept click does); the town is
        left (town 1 leaves the list, `ScenarioLeaveLocation`)."""
        camp = self.camp
        for kind, town in [loc for loc in camp.available if loc[0] == C.TOWN]:
            camp.enter((kind, town))
            words = camp.enter_inn_words(town, self.is_mage, self.is_female)
            for w in words:
                if (w >> 28) & 7 in (0, 3) and (w & 0xFFFF) in STORY:
                    self.recruit(w & 0xFFFF)
            for w in words:
                if (w >> 28) & 7 in (0, 3):
                    camp.talk_to(w)
            offers = [w for w in words if (w >> 28) & 7 in (1, 2)]
            for n in self.hire(offers, camp):
                # the Accept click (0x49b812, CONFIRMED): only a type 1 word hires (TalkTo); a type 2 word (re-offered) shows the reject text, no TalkTo.
                # No price exists in the exe: no gold is checked or deducted.
                if any((w & 0xFFFF) == n and (w >> 28) & 7 == 1 for w in offers) and not camp.get(C.MERC_HIRED + n - 1):
                    camp.talk_to((1 << 28) | n)
            self.log.append("town %d: %s" % (town, ", ".join("%08x" % w for w in words)))
            camp.leave()

    # --- missions ----------------------------------------------------------------------------------------------------------------

    def next_mission(self):
        """The next mission of the campaign order: the first mission of the available list (unlock order), None when there is none."""
        return next((i for k, i in self.camp.available if k == C.MISSION), None)

    def hired(self):
        """The mercenaries the start-mission message `0x468` creates: `k + 1` ascending for `Var(0x200 + k)` and `Var(0x214 + k)` both non-zero."""
        c = self.camp
        return [k + 1 for k in range(C.MERCENARIES) if c.get(C.MERC_HIRED + k) and c.get(C.MERC_MARK + k)]

    def start_mission(self, n=None, seed=None, vision=False):
        """The world of mission `n` (default: `next_mission()`) as the game starts it (`FUN_0048c8a3`): `ScenarioEnterLocation`, the mercenaries hired and
        alive (`FUN_004f36c0`, template by the chapter), the map, the script, the AI and the party placement with the carried roster (main hero
        first, the other heroes in list order, the mercenaries after).  Returns `(world, assets)`."""
        from engine.session import build_game
        n = self.next_mission() if n is None else n
        if (C.MISSION, n) not in self.camp.available:
            raise ValueError("mission %s is not in the available list %s" % (n, self.camp.available))
        self.camp.enter((C.MISSION, n))
        self.mission = n
        ids = NetIds()
        ids.used = set(self.net_ids.used)
        mercs = []
        types = self.assets.unit_stats()
        for k in self.hired():
            t = mercenary_template(types, k, self.camp.get(C.CHAPTER))
            if t is not None:
                mercs.append(PT.RosterEntry(k, t[0], t[1], ids.alloc()))
        roster = PT.Roster(list(self.roster) + mercs, self.gold, self.hero_deaths, self.kills_monsters, self.kills_players)
        world, assets = build_game(str(n), self.install, seed=self.seed if seed is None else seed, difficulty=self.difficulty, vision=vision,
                                   roster=roster, reserve_ids=ids.used, assets=self.assets)
        if world.script is not None:
            world.script.scenario_vars = self.camp.vars         # one array: the map's SetVar / GetVar are Scenario.dll's (maps 20 / 50 / 70 / 80 / 110)
        by_net = {m.net_id: m.number for m in mercs}
        self.mercenaries = {u.id: by_net[u.net_id] for u in world.units.values() if u.net_id in by_net and u.owner == self._human(world).id}
        return world, assets

    @staticmethod
    def _human(world):
        return next((p for _, p in sorted(world.players.items()) if p.human), None)

    def death_hook(self, world):
        """`death_hook` plus the mercenaries of the mission that are no longer in the world: a removed body that decayed to HP -11 is dead for the
        campaign, one that is still fresher (the mission ended first) is not (INFERRED, triggers.md 11.4); a body that is gone has decayed."""
        death_hook(world, self.camp)
        for uid, n in self.mercenaries.items():
            if uid not in world.units and uid not in world.corpses:
                self.camp.set(C.MERC_MARK + n - 1, 0)

    def carry_over(self, world):
        """`FUN_004ebd5f` steps 5-6 (saves.md 4): the heroes of the human's list (hero number 0x15..0x1e) keep their level / XP / skills / pools / items /
        spells / name / number / free id (`engine.party.capture`), everything else of the list goes (summons, monsters, mercenaries), the dead (removed from
        the list) are gone, HP and mana return to the maxima when the next map places them, applied effects / orders / targets do not exist in the carried
        state; gold and statistics move to the campaign.  Returns the new roster."""
        owner = self._human(world)
        heroes = [u for u in world.units.values() if is_hero(u, owner)]
        old = {e.net_id: e for e in self.roster}
        new, seen = [], set()
        for e in self.roster:                                     # list order first (the main hero leads), then heroes the map handed over
            u = next((h for h in heroes if h.oid == e.net_id), None)
            if u is not None:
                seen.add(u.id)
                new.append(self._entry(u, e.net_id))
        for u in heroes:
            if u.id not in seen:
                new.append(self._entry(u, u.oid))
        for nid, e in old.items():
            if nid not in {x.net_id for x in new}:
                self.net_ids.free(nid)                           # the dead: `FUN_004f8d3d` at the removal
        for e in new:
            if 0 < e.net_id < LIMIT:
                self.net_ids.used.add(e.net_id)
        self.roster = new
        self.gold, self.hero_deaths = owner.gold, owner.hero_deaths
        self.kills_monsters, self.kills_players = owner.kills_monsters, owner.kills_players
        return new

    @staticmethod
    def _entry(u, net_id):
        return PT.RosterEntry(PT.hero_number(u), u.server_id, u.human, net_id, PT.capture(u))

    def leave_mission(self, world, result="won"):
        """The end of the running mission.  `result` "won": the death hook, the carry-over, `ScenarioLeaveLocation` (triggers.md 11.1 order, which also
        clears the hire flags), the recruit of `Var(0x305)`, then the town stand-in (`visit_towns`) unless the campaign is over.  Any other result (defeat,
        left by the menu) is the main menu: no carry-over.  Returns the `sim.campaign.Outcome`."""
        if result != "won":
            return C.Outcome("main_menu")
        self.death_hook(world)
        self.carry_over(world)
        out = C.complete(self.camp, world.tick)
        if out.recruit:
            self.recruit(out.recruit)
        self.mission, self.mercenaries = None, {}
        if out.kind != "ending":
            self.visit_towns()
        return out

    # --- reports -----------------------------------------------------------------------------------------------------------------

    def summary(self):
        """`number:name Lxx eN pM` per roster entry: the best skill (the level), equipped and pack items."""
        out = []
        for e in self.roster:
            s = e.state
            if s is None:
                out.append("%#x:%s (new)" % (e.number, e.spec.name if e.spec and e.spec.name else e.server_id))
                continue
            eq = ("e%d" % sum(1 for i in s.equipment if i is not None and i.code)) if s.equipment else "etpl"      # () = the template's own strings
            out.append("%#x:%s L%d %s p%d" % (e.number, s.name or s.stats.name, max(s.skills[1:] or (0,)), eq, len(s.pack)))
        return "; ".join(out)

    def state_hash(self):
        """A digest of the campaign state (variables, locations, roster states, gold): the chain hash adds the world hashes."""
        import hashlib
        h = hashlib.sha256()
        h.update(repr((sorted(self.camp.vars.items()), self.camp.available, self.camp.times, self.gold, self.hero_deaths, self.kills_monsters,
                       self.kills_players, sorted(self.net_ids.used))).encode())
        for e in self.roster:
            s = e.state
            h.update(repr((e.number, e.server_id, e.net_id) + ((s.skills, s.xp, s.hp_max, s.mana_max, s.name,
                                                               [(i.code, i.count, i.mods) for i in s.equipment if i is not None],
                                                               [(i.code, i.count, i.mods) for i in s.pack]) if s is not None else ())).encode())
        return h.hexdigest()


# --- the chain (python -m engine campaign) ------------------------------------------------------------------------------------------

SIDE_VARS = (0x304, 0x30C)          # the optional goals that add missions: map 20 "Get mission 21", map 50 "Give 52 mission" (triggers.md 11.1)
ORACLE_MISS = {77: "its escort dies to the leader's squad: a fight the oracle cannot make (docs/coverage.md)"}
NEVER_OFFERED = (51, 83)            # named by no completion case and no dialogue word (triggers.md 11.2)


def class_alternatives(start):
    """The class-slot missions a hero of this class never sees (triggers.md 11.2): of 74-77 / 84-87 / 93-96 only `base + s`, of 81 / 82 only one."""
    mage, female = start[1] == "M", start[0] == "F"
    s = (2 if female else 3) if mage else (1 if female else 0)
    out = {b + k for b in (74, 84, 93) for k in range(4) if k != s}
    out.add(82 if mage else 81)
    return out


def run_chain(install=None, through=None, hero="MF", seed=1, side=SIDE_VARS, log=print, hire=None, prefer=(), probe=None):
    """Chain the missions in unlock order with the objective run as the driver: start the mission from the carried roster, make its win conditions
    true (`engine.objective.run` on the world `start_mission` built, so the maps read the campaign's variables), end it (`leave_mission`).  A mission the
    oracle does not win (`ORACLE_MISS`: map 77) is completed anyway so the order goes on (DECISION: the chain tests the campaign state machine, not the
    fight).  `through`: stop after that mission is finished; `prefer`: missions to play first whenever they are available (the player's choice in the world
    map: map 80 before 70); `probe(n, game, world)`: called on a fresh start of each mission before the oracle runs (the report's idle runs).  Returns a dict (`played`, `failed`, `unreachable`, `unexpected`, `hash`, `game`)."""
    import hashlib
    from allods2.cli import campaign_maps
    from engine import objective
    game = CampaignGame(install, hire=hire, seed=seed)
    game.new_game(HeroChoice(hero))
    h = hashlib.sha256()
    played, failed = [], []
    while True:
        n = next((m for m in prefer if (C.MISSION, m) in game.camp.available and m not in played), game.next_mission())
        if n is None or n in played:
            break
        before = game.summary()
        if probe is not None:
            probe(n, game, game.start_mission(n)[0])
        world, _ = game.start_mission(n)
        r = objective.run(str(n), install, seed=seed, world=world, side=side)
        won = r["result"] == "won"
        if not won:
            failed.append((n, r["result"], r.get("crash", "")))
        out = game.leave_mission(world, "won")          # forced when the oracle failed
        h.update(repr((n, r["result"], r["tick"], world.dump_hash(), game.state_hash())).encode())
        played.append(n)
        log("mission %-3d %-8s tick %-5d %2d edits | party: %s | chapter %d, %s%s" % (
            n, r["result"] if won else r["result"].upper() + (" (known oracle miss, completed anyway)" if n in ORACLE_MISS else " (completed anyway)"),
            r["tick"], len(r["edits"]), before, game.camp.get(C.CHAPTER), out.kind,
            ", cutscene %d" % out.cutscene if out.cutscene >= 0 else ""))
        if through is not None and n == through or out.kind == "ending":
            break
    allmaps = sorted(int(__import__("os").path.basename(p).rsplit(".", 1)[0]) for p in campaign_maps(install))
    unreachable = [m for m in allmaps if m not in played]
    expected = set(NEVER_OFFERED) | class_alternatives(hero)
    unexpected = [m for m in unreachable if m not in expected] if through is None else []
    return {"played": played, "failed": failed, "unreachable": unreachable, "unexpected": unexpected, "hash": h.hexdigest(), "game": game,
            "hard_failed": [f for f in failed if f[0] not in ORACLE_MISS]}

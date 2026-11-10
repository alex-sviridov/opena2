# The campaign spine (L1)

Headless campaign state: what the server and Scenario.dll keep between the missions of a single-player game, and the chain that plays them in unlock order.
Facts and routines: [triggers 11](triggers.md#11-the-end-of-the-mission-scenariodll-and-the-client-flow) (completion cases, `EnterInn` / `TalkTo`, recruits, death
variables, 11.5 = what L1 needed), [saves 4](../formats/saves.md#4-carry-over-between-campaign-maps-single-player-confirmed) (carry-over, `FUN_004ebd5f`),
[triggers 9](triggers.md#9-the-party-at-map-start-fun_004f2c83) (party placement, `FUN_004f254b`). Code: `engine/campaign.py` (layer 4, no windows),
`engine/sim/campaign.py` (Scenario.dll state), `engine/party.py` (roster placement), `engine/objective.py` (driver). Tests: `tests/test_engine_campaign_spine.py`,
`tests/test_engine_campaign.py`. Everything below follows 11.x unless marked.

## 1. API

| Call | What |
|---|---|
| `Campaign.enter_inn_words(town, is_mage, is_female)` | `ScenarioEnterInn` (11.2 tables): the dialogue words of the inn at the current chapter, then the mercenary offers |
| `Campaign.talk_to(word)` | `ScenarioTalkTo`: type 0 (orc offer, `0x302 := 2`), type 1 (hire toggle), type 3 (the offered mission joins the list; `Var(0x301)`, the knight offer) |
| `Campaign.offer_mercenary(n, town)` | the markers a completion case writes (`Var(0x213 + n)`, `Var(0x227 + n)`) |
| `Campaign.leave()` | fixed per 11.1: step order (hire-flag loop before the case), cases 20 (`Var(0x304)`) / 50 / 60 / 70, the mercenary offers of cases 20 / 50 / 60 / 70 / 100 |
| `sim.campaign.complete(camp, tick)` | the part of `0x41d` after the carry-over (time, leave, recruit number, next screen); `press` calls it |
| `CampaignGame(install, hire=None, seed, difficulty)` | one campaign: `camp`, `roster` (list of `party.RosterEntry`), `gold` + statistics, `net_ids` (the server's free-id table), `mercenaries` |
| `.new_game(HeroChoice(start, attributes, school, name), visit=True)` | `ScenarioNewGame` + `FUN_004f254b`: the main hero is a roster entry with a `HeroSpec` (built when the first map places it), its free id taken now; `Var(0x308)` / `Var(0x30d)` from the template; the town 1 visit (`TalkTo(0x300a0205)`) |
| `.visit_towns()` | the town stand-in (11.5 item 4): every town in the available list is entered, story heroes of the words created, every type 0 / 3 word accepted, mercenaries hired by the `hire(words, camp)` policy (default none), the town left |
| `.next_mission()` / `.hired()` | the first mission of the available list (unlock order) / mercenaries with hire flag and marker both set |
| `.start_mission(n=None, seed=None)` | `ScenarioEnterLocation`, mercenaries (template by chapter), `session.build_game(roster=, reserve_ids=)`; the script's `scenario_vars` is the campaign's dict |
| `.leave_mission(world, result)` | `"won"`: death hook, `carry_over`, `complete`, recruit of `Var(0x305)`, `visit_towns`; anything else = main menu, no carry-over |
| `.carry_over(world)` | `FUN_004ebd5f` steps 5-6 on the world |
| `party.place_party(.., roster=Roster)` | the carried party instead of a fresh one; `triggers.enable(.., roster=)` and `build_game(.., roster=)` pass it; `play MAP` and `enable(party=)` are untouched |
| `run_chain(install, through, hero, seed, side, prefer, probe)` / `python -m engine campaign` | the chain with the objective run as driver |

`RosterEntry(number, server_id, human, net_id, state, spec)`: `number` = `+0x14c`, `state` = a deep copy of the unit's carried fields (`party.CARRY`: template,
attributes, skills, XP pools, best school, spell book, name, equipment, pack, pack index, carried items, bonus caches, kill list, hero number), `spec` = the creation
arguments of a hero that never stood in a world. HP and mana are not stored: the next placement sets them to the maxima (step 6); effects, orders, targets,
the death flag do not exist in the state. `Unit.hero_no` (new field, not dumped) = the number a recruit / hire wrote (monsters have no reduced id).

## 2. DECISIONs

1. **Roster = records, not units** (`RosterEntry.state`): a Unit belongs to a world; the state carries every item, XP pool and skill (tested round trip). The
   free id (`Unit.net_id`) of every roster entry stays; the campaign owns the server's id table, a mission's world starts with those bits taken
   (`World.from_map(reserve_ids=)`, so ground piles take the later ids as in the game where the party exists before the map loads) and the mercenaries'
   ids are drawn from a copy of it (freed with them). A hero handed over by a map script (map 40's Mage_Hero, owner changed) is carried with `net_id = unit.id`
   (a map unit's id is `0x6000 + uid`, never in the table).
2. **Carried = hero number 0x15..0x1e owned by the human** (the exe tests `+0xe` in 0x21..0x3f, which the hero constructor flag gives exactly these). Every
   other unit of the human (summons, mercenaries, units a script gave him) is deleted; a hero not in the world (dead, removed) is gone and its id freed.
3. **Visit policy** (11.5 item 4): accept every offer (`TalkTo` of every type 0 / 3 word), no mercenary hired by default; the `hire` policy can hire type 1 offers only (CONFIRMED `0x49b812`: the Accept click of a type 2 word shows the reject text and makes no `TalkTo`; a hire has no price, no gold is read or written: `0x49b812`, `0x49b989` hold no gold access). A town is visited after every mission end while it is in
   the available list; the visit order is the list order. INFERRED: the order of the blocks inside `EnterInn` after the chapter jump table (chapter rows, town-3 rows,
   town-2 rows, mercenaries) (the "type 2 hired with a type 1 word" guess was wrong, see above): the order of the available list follows it, nothing else does.
4. **Mission order** = the first mission of the available list, i.e. unlock order. CONFIRMED (triggers 11.2 "The available list"): the list is the DLL's, appended at the tail in the
   order of the events (completion unlocks, `TalkTo` type 3), never sorted; the real world map places the missions at fixed positions and the player clicks one, so the list order
   decides only the no-town start (`0x486d4f`, the head) and the screen's initial focus. The player chooses on the world map; `run_chain(prefer=(80,))` plays map 80
   before 70 (tested: the chain still reaches the same 34 maps).
5. **Optional goals** (`SIDE_VARS`): `objective.run(side=(0x304, 0x30c))` first makes the map-20 "Get mission 21" and map-50 "Give 52 mission" triggers fire
   (check 6 hero-to-unit, and a new edit for check 4 parameter 6, the hostage's HP), so the optional missions 21 and 52 are in the chain; `--no-side` drops them.
6. **Oracle failures**: a mission the oracle does not win is still completed (state machine test, not a fight): only map 77 (`ORACLE_MISS`), which the default hero
   never offers (the class slot of a male mage; run `--hero MM`).
7. **Death hook** = `death_hook(world, camp)`: unit or corpse with a hero number 1..20 at HP <= -11 sets `Var(0x213 + n) := 0` (no owner test); `CampaignGame.death_hook`
   also marks a hired mercenary that is neither in `units` nor in `corpses` (its body decayed). A body still fresher than -11 at the mission end is not dead (INFERRED, 11.4).
   The UI of L2 should call `death_hook` from its per-tick step.
8. **Fresh hero** (`HeroSpec`): attributes when `0x8c - sum(cost) >= 0` else 25 each (CONFIRMED 9.3); a school sets skills (school 20, then shooting 10, others 0: school 5 ends with 10,
   CONFIRMED `FUN_00514f59`), recomputes the pools / best school, and replaces the weapon (school 1-5 weapon, mage: `[Uncommon ]Wood Staff {castSpell=<spell>:20}`, CONFIRMED, triggers 9.3). The default
   (`MF`, no spec fields) is the `Start_MF` template, exactly what `place_party` builds today.
9. `Var(0x308)` / `Var(0x30d)` (mage / female) are set from the template key at `new_game` (the creation screen's writes, exe `0x4896dc` / `0x489700`).
10. The gold of a mission start is the carried gold; the section 5 `money` of the map is not added (it was not before either).

## 3. The chain (python -m engine campaign)

`python -m engine campaign [--through N] [--hero MF|FF|MM|FM] [--seed N] [--no-side] [--install DIR]`: for each mission (first of the available list): the world of
`start_mission`, the objective run on it (the same world: maps read the campaign variables, the carried party stands on the drop cell), `leave_mission`. One line
per map (party summary: `number:name L<best skill> e<equipped items> p<pack stacks>`), then the maps never played; exit 1 when a mission is not won (except `ORACLE_MISS`)
or a map that should be reachable is not (`51`, `83` and the class-slot maps of the other classes are expected). Chain hash = sha256 over (mission, result, tick, world
hash, campaign state hash) per mission.

Result with the default hero (`MF`, seed 1, 5 s): **34 missions, all won by the oracle**, order 10 20 21 30 31 40 41 42 43 32 50 60 53 52 61 63 70 71 80 73 72 62 74
82 90 91 92 84 100 102 101 103 93 110, chapter 120 and the ending (cutscene 4). Not played: 51, 83 (never offered) and 75-77, 81, 85-87, 94-96 (class slots of the other
three classes). The party: main hero (Start_MF, skill 20), Fighter_Hero from the first visit at chapter 30, Mage_Hero after mission 40; items change only through the
oracle's pickups (pack stacks 1 -> 6).

### What changes with the carried party
* **The six idle-lost maps** (43, 60, 70, 92, 102, 110: a standing party is lost within 1600 ticks): **still lost** with the carried party (probe run on the chain).
  The headless chain gains no XP (the oracle's kills do not credit a hero), so the party is the fresh level-1 party; only a real play or an XP-crediting oracle
  can move them.
* **The objective results** (result, tick, edits) of all 34 maps are identical to the fresh-party runs: the oracle does not depend on the roster.
* **Maps 70 and 80** read `Var(0x30a)` / `Var(0x309)`, which only the completion cases write (11.1): with the flag the triggers that fire differ (map 70: triggers 17 and
  20; map 80: 2-10, and the heroes' items), the win does not. The chain plays 70 before 80 (80 sees `0x309` = 1, cutscene code 3 after 80); `prefer=(80,)` reverses it.
* **Maps whose scripts name heroes 2 / 3**: the carried party has them (Fighter_Hero from chapter 30, Mage_Hero after 40 or at chapter 50), a fresh party made them from
  the script's references; before chapter 30 the roster has only the main hero (maps 10, 20, 21) as a fresh party did.
* **Unreachable**: 51 and 83 only (plus the other classes' slot maps). Map 21 needs `Var(0x304)` (the optional trigger of map 20), map 52 `Var(0x30c)` (map 50).

## 4. Open questions

* XP in the headless chain: a fight-crediting oracle (or a play-through) is needed before the carried levels mean anything; the idle-lost maps depend on it.

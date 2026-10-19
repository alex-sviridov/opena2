# Open questions

Index of everything not yet known; each spec's "Open questions" section is
the source of truth (rules in CLAUDE.md: add a line when raised, delete it
from both places when answered).

## Animation

- Town scenes: draw code and timing are resolved ([animation §4.11](formats/animation.md)).
  Left: the hover-region numbers of the fighter/mage/shopie sprites and
  the druid `man`/`woman` variant choice.
  [animation](formats/animation.md#open-questions)
- World-map Cross: where `+0x134` is reset to 0 on a new click.
  [animation](formats/animation.md#open-questions)

## data.bin

- Human and structure fields in code (`FUN_004a65b0`, `FUN_004a65d0`
  users; column names known). [databin](formats/databin.md#open-questions)

- Unit stat table: hero carry-over. [units](data/units.md#open-questions)

## Progression

- Hero state between campaign maps (saves, `.a2c`). Start: `FUN_00514920`, `FUN_004ea6ab` (record -> hero), `FUN_004ee7cb` (blob parser), writer `0x4eab4a`. [progression](data/progression.md#open-questions)

## Items

- None open. Related and not started: `.a2c` characters and saves, the `Scenario.dll` state machine beyond the shop table.
  [items](data/items.md#open-questions)

## Spells

- Spell button enable masks (view `+0xd0` object `+0x148` / `+0x150`: how the bits follow the spellbook and mana), cell-target command `0x1f` (`FUN_0057033d`), Stop (`FUN_0056dbc6`) during a cast. [spells](data/spells.md#11-open-questions)
- Minion brain modes (`brain+0x20` 1 = Summon, 3 = Control Spirit). Start `FUN_005709d9`, `FUN_00570b8b`.
  [spells](data/spells.md#11-open-questions)
- Spellbook tooltip rows Speed / Sight array pairing. Start `FUN_00416615`, `FUN_004c628f`. [spells](data/spells.md#11-open-questions)

## Combat (I1)

- Monster damage = template + equipped weapon: confirm in play. [combat](engine/combat.md#open-questions)
- Special attacks (`FUN_0056a981`), the AI mage casting (`FUN_0056b059`, `FUN_0056bc7b`), the caster lists `server+0xaa8`/`0xac8` (answered in the doc, AI spell use is phase K; the player-side cast is built, [combat §14](engine/combat.md#14-spell-casts-i4a)). [ai](engine/ai.md#11-phase-k-list-ranged-and-casters)
- Main shell: which main-menu entry and which screen-state chain lead to state `0x425` (new single-player game; only known entry: state `0x438` index 6..9 of the widget `this+0x134`), and whether the Easy/Medium/Hard radios (panel `this+0x374`, resource `0x466`) share the screen with the name edit of town.txt tips 9/10 (INFERRED); needed before an engine new-game screen. [ai](engine/ai.md#101-difficulty-tweak-fun_00561bf9-0x561e200x561f0b-confirmed)
- AI: the group orders 1, 2, 5, `0x11`, `0x13`, `0xff` and the G / L / swarm commands are built ([ai §14.1](engine/ai.md#141-implementation-and-the-asm-details-it-rests-on-confirmed-unless-marked)); missing: the scripted group sub-commands 10, 11, 14, 15 ([triggers §4](engine/triggers.md#4-instants-fun_00574f3f); 1-5, 17, 18 and the sleeping flag `+0x48` are built), the summon spell's guard group (`0x51a8d7`); the quest-accept path that sends a squad with order 2 ([ai §15](engine/ai.md#15-sleeping-squads-record-0x45--0x48-and-the-quest-that-sends-a-group-order-2)); (creature `+0x4c` flags, `FUN_0053a5a0` = mage, the `0x8000` RNG divisor and the difficulty tweak, including which single-player screen sets it (new game: Easy/Medium/Hard, saved in the save file), are answered in ai §6 / §10.1; the flee list is creature-only, hostile structures never trigger a flee, and the hidden flag `0x1000` is the Invisibility effect: answered in ai §4 / §9, engine `Unit.hidden` has no setter until the effect system). [ai](engine/ai.md#open-questions)
- Client reaction on message `0x73` beyond the number (view unit vtable `+0x74`); the recovery-timer byte wrap. [combat](engine/combat.md#open-questions)

## Not started (from the reversing plan)

- Part 5 leftovers: event classes of unit `behaviour` bits 1, 2, 4, section 9 per-cell payload.
  [map](formats/map.md#open-questions)
- Section 12 music: the reader of the next-theme global `0x5f1a08` and the callers of `FUN_004754e9`; section 11
  inn / shop fields (multiplayer only). [map](formats/map.md#open-questions)
- Unit struct: group AI, orders 0x16/0x1a, structure damage `0x516ea0`.
  [unit-struct](engine/unit-struct.md#open-questions)
- Line of sight tables and the `FUN_00559536` gate; block-layer dynamic bits
  and per-class `movementType` (`FUN_00557a89`, vtable `+0x20`). [map](formats/map.md#open-questions)
- Dirt mark: caller of the clear `FUN_00559ce5` (the `+0x5c` byte is answered: damage spread, [spells](data/spells.md#4-effect-handlers)).
  [map](formats/map.md#open-questions)
- Structure registration at load: does a unit-made cell record exist before the structures (then
  `FUN_00559890` skips the refresh)? `FUN_005508a0` callers.
  [map](formats/map.md#open-questions)
- `famehall.dat`, saves (`game%d.sav`; the
  client state is a [`.reg`](formats/reg.md#writing) tree, `FUN_0048dc9f`), `.a2c`
  characters. [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- Text conventions of `main/text/*.txt` (line lists, `#key` sections,
  `mission%d.txt`). [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)

## Engine

- Day/night light recomputation in the engine. [architecture](engine/architecture.md#open-questions)
- Interface (G3b): how the exe clears a selection (right button `0x40f`, Esc? engine: right click);
  which bottom bar shows first; mouse-manager `+0x9c`; purpose of the 30 px top strip; `FUN_004b011e` (text vs
  human panel) and command-bar contents; hover brightness; structure pick rects; order command bytes and the squad
  voice. [ui-layout](engine/ui-layout.md#open-questions); start at `FUN_0040b2b8`, `FUN_004175c7`.
- Engine terrain scroll hitch (~27 ms per new cell row/column): pre-warm or flat-cell fast path.
  [architecture](engine/architecture.md#open-questions)
- Unregistering a structure (`FUN_0055995a`) clears cells held by another structure; engine releases only
  its own cells. [architecture](engine/architecture.md#open-questions)
- [Cell effects](engine/rendering.md#open-questions) (answered: spell-area sprites, registered by [spells §4](data/spells.md#4-effect-handlers); drawing needs the spell system), unit invisibility / stone curse / hover, message 0x74 (flag 0x80); start at `FUN_004632a1`.
- [Engine object drawing](engine/rendering.md#open-questions): burnt ground, light-map lights on objects; start at `FUN_00404a2a`.
- [Engine minimap](engine/rendering.md#open-questions): final channel pass `0x4ac030`, fog background surface `DAT_00626be0`, fog gate of the unit dots; start at `FUN_004ac414`.
- Movement and orders (H1, H3) [simulation](engine/simulation.md#open-questions): the empty-dynamic-list step at a centre after a failed hop (`FUN_00555c7e`) and whether a stale dynamic list (turn over 32 ticks) occurs with real turn rates;
  Haste/Slow vs the group speed byte (phase I); group
  the engine side of the group orders 1, 2, 5, 0x11, 0x13 (decoded, [ai §14](engine/ai.md#14-the-other-group-orders)),
  tick counters after loading a save (`FUN_004e9b95`, branch of `FUN_004eb715`); the server's handling of the client's type-100 message (`FUN_004f515d`).
- Handoff to combat (phase I) [simulation §9](engine/simulation.md#9-handoff-to-combat-phase-i): wiring the decoded follow driver (7.4: `follow_fallback`, `FUN_0055574d`) to brain modes 4/5/6/8 and orders `0x19`/`0x1b`, orders `0x17`/`0x19`..`0x1d` and their group handlers, voice, the consolidated VERIFY IN GAME list (§9 items 1-10).
- Order planning spike (H3 bench) [simulation §8.7](engine/simulation.md#87-tests-end-states-measured): a 20-unit order on the 256 x 256 map costs ~0.46 s in one tick (pure-Python planner); worker-thread or faster planner, results must stay bit-identical.
- x87 control word for the follow-fallback slope [simulation §7.4](engine/simulation.md#74-read-but-not-implemented-needs-ordersai-of-phase-i): only the follower-on-target-centre `0/0` case depends on it; starting routine CRT start-up before `FUN_00557f08`.
- Pathfinding (H2) [simulation §7](engine/simulation.md#open-questions): stored occupant/stamp slots with release quirks (`FUN_0055073f`, `FUN_0055be86` callers `0x558b7c`/`0x56a5df`, [7.4](engine/simulation.md#74-read-but-not-implemented-needs-ordersai-of-phase-i)).
- Guarding computer-player groups [simulation](engine/simulation.md#open-questions): group order `0x12` handler `FUN_005728fa` (reader of `brain+0x16`) and the home-cell restart `FUN_0056c8af`/`brain+0x9c`; spell record `+9`/`+0xc` as range/cost in `FUN_0056ac5b` (`FUN_0051c391`).
- Click to move UI (H3 stage B): message colour/position of the message line and the formation text lifetime ([rendering §14](engine/rendering.md)); cursor kept for pending modes 3/7.
- Click to move (H3 research) [research §9](engine/click-to-move-research.md#9-open-questions): voice unit selection `FUN_0041da16`, `FUN_0041f090`/`41f0e0` (neighbours of `Ctrl+F`), single-player server connection list (`FUN_00500f0e`, `0x50155f`; AI "No way" drop), heap block after the `+0xb8` table (`FUN_00582a10`; last-row read of `FUN_00417f31`), detection level `FUN_00556dcd` and the spell branches of the retreat post step `FUN_00573713` (`FUN_0056bb0d` kind `0x17`, `FUN_0056cb8c`).
- Cell record effect fields `+0x34..+0x39` (Teleport `0x17` -> `brain+0xb0`, `FUN_0055a96c`; no writer found) [unit-struct](engine/unit-struct.md#open-questions): starting routine `FUN_0055f3e0` callers that copy a record from a stream (`0x55f6b0`).
- Phantom units (9 on blocked cells, never created by the server) and HP-0 units: engine keeps and draws them; decide with the phase H sim. [architecture §9](engine/architecture.md#9-world-state)
- Death/corpses/loot (I2) [combat §12.11](engine/combat.md#1211-open-questions): the quest kinds that listen to the server event queue (event 4 = unit removed, `FUN_0052e198`, `FUN_0052eac8`; not the triggers); hero-death follow-ups ([combat §12.11](engine/combat.md#1211-open-questions) 1: `owner+0x38` writer, dialog latch `[this+0x3e8]` reset; start: callers of `FUN_00505347`); summon-cap job `+0x148` draw order (CMap iteration order, `0x545a60` hash; `FUN_0052bbb7`); item effects (`{castSpell=..}`) of dropped template equipment are lost in the 16-bit pile code (what the pile / pickup keeps for an item with effects: start `FUN_00529ac2`, `FUN_0052a71d`); sound tables (unit sound set entries, hero voices, UI sound `0x627740[0xf]`; [combat §12.11](engine/combat.md#1211-open-questions) 4).
- Triggers [triggers](engine/triggers.md#open-questions): the party roster of later maps and the creation screen's message `0x48` ([§9](engine/triggers.md#9-the-party-at-map-start-fun_004f2c83), start `FUN_004ea6ab`, `FUN_004f6af6` case); where single player posts the ready message (`FUN_0041c50d`); `FUN_0055641c`; the by-name second loop of `FUN_00562518`; the free-cell test `FUN_005563ca` / `FUN_0055c5a0` of `FUN_00510089`; the window message `0x41d` and the mission-complete dialog (`0x486ddb`, Scenario variable `0x300`); the text of message `0xb6` values (`0x433` handler); Scenario.dll initial variables (`ScenarioNewGame`) and campaign use; the member loop of instant 22 (`FUN_005782ba` over a list `FUN_004f0568` changes).

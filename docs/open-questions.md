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

## Progression

- Equipment effects of a loaded hero (the engine keeps `Unit.equipment` / `Unit.pack` but has no equip system): [saves §3.6](formats/saves.md#36-building-a-hero-from-a-record-fun_004ea6ab-confirmed-order).

## Items

- None open. Related and not started: the `Scenario.dll` state machine beyond the shop table and the save block.
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
- Saves ([saves](formats/saves.md#open-questions)): the server stream's object serialisers (`FUN_0052d16b`, `FUN_0052c3da`, `FUN_0052d5cb`, `FUN_00550008`, `FUN_0052d5b2`, `FUN_0053bbd0`, `FUN_0057a951`, start `FUN_004ec732`) and its 11 option words; which server messages make the client rewrite the `.a2c` (message pump sites `0x411aa2`, `0x4122d7`, `0x41054f`, `0x414a9c`, `0x40ee51`), the `0xa00` settings block and the `+0x2f` byte; whether single player ever uses a stored character's items (VERIFY IN GAME); `famehall.dat` fields `b`, `c` and its writer's caller; save slot roles (`game9998/9999/0000`, `FUN_004f515d` -> `FUN_004e9816` at `0x4f723d`).
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
- Movement and orders (H3) [simulation](engine/simulation.md#open-questions): the engine side of the group orders 1, 2, 5, 0x11, 0x13 (decoded, [ai §14](engine/ai.md#14-the-other-group-orders)); the empty-list step, Haste vs the group byte, the type-100 message and the connection list are answered ([simulation §11](engine/simulation.md#11-exe-answers-follow-up-of-h1-h3)).
  Haste/Slow vs the group speed byte (phase I); group
  the engine side of the group orders 1, 2, 5, 0x11, 0x13 (decoded, [ai §14](engine/ai.md#14-the-other-group-orders)),
  the server's handling of the client's type-100 message (`FUN_004f515d`).
- Handoff to combat (phase I) [simulation §9](engine/simulation.md#9-handoff-to-combat-phase-i): wiring the decoded follow driver (7.4: `follow_fallback`, `FUN_0055574d`) to brain modes 4/5/6/8 and orders `0x19`/`0x1b`, orders `0x17`/`0x19`..`0x1d` and their group handlers, voice, the consolidated VERIFY IN GAME list (§9 items 1-10).
- Order planning spike (H3 bench) [simulation §8.7](engine/simulation.md#87-tests-end-states-measured): a 20-unit order on the 256 x 256 map costs ~0.35 s in one tick (pure-Python planner, 0.46 s before the 7.5 re-expansion skip; still 5x the 62.5 ms tick); worker-thread or faster planner, results must stay bit-identical.
- Guarding computer-player groups [simulation](engine/simulation.md#open-questions): group order `0x12` handler `FUN_005728fa` (reader of `brain+0x16`) and the home-cell restart `FUN_0056c8af`/`brain+0x9c`; spell record `+9`/`+0xc` as range/cost in `FUN_0056ac5b` (`FUN_0051c391`).
- Click to move (H3 research) [research §9](engine/click-to-move-research.md#9-open-questions): heap block after the `+0xb8` table (`FUN_00582a10`; last-row read of `FUN_00417f31`), detection level `FUN_00556dcd` and the spell branches of the retreat post step `FUN_00573713` (`FUN_0056bb0d` kind `0x17`, `FUN_0056cb8c`); the per-order voice slots (sound engine).
- Cell record effects ([unit-struct](engine/unit-struct.md#open-questions)): writer `FUN_0055ba36` found (callers `0x564280` map load, `0x57853b` scenario instant `FUN_0057847e`); left: which map section / instant feeds them and whether any campaign map uses one (engine has no cell effects).
- Phantom units (9 on blocked cells, never created by the server) and HP-0 units: engine keeps and draws them; decide with the phase H sim. [architecture §9](engine/architecture.md#9-world-state)
- Death/corpses/loot (I2) [combat §12.11](engine/combat.md#1211-open-questions): the quest kinds that listen to the server event queue (event 4 = unit removed, `FUN_0052e198`, `FUN_0052eac8`; not the triggers); hero-death follow-ups ([combat §12.11](engine/combat.md#1211-open-questions) 1: `owner+0x38` writer, dialog latch `[this+0x3e8]` reset; start: callers of `FUN_00505347`); summon-cap job `+0x148` draw order (CMap iteration order, `0x545a60` hash; `FUN_0052bbb7`); item effects (`{castSpell=..}`) of dropped template equipment are lost in the 16-bit pile code (what the pile / pickup keeps for an item with effects: start `FUN_00529ac2`, `FUN_0052a71d`); sound tables (unit sound set entries, hero voices, UI sound `0x627740[0xf]`; [combat §12.11](engine/combat.md#1211-open-questions) 4).
- Triggers [triggers](engine/triggers.md#open-questions): where single player posts the ready message (`FUN_0041c50d`); `FUN_0055641c`; the by-name second loop of `FUN_00562518`; the free-cell test `FUN_005563ca` / `FUN_0055c5a0` of `FUN_00510089`; the window message `0x41d` and the mission-complete dialog (`0x486ddb`, Scenario variable `0x300`); the text of message `0xb6` values (`0x433` handler); Scenario.dll initial variables (`ScenarioNewGame`) and campaign use; the member loop of instant 22 (`FUN_005782ba` over a list `FUN_004f0568` changes).

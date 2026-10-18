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

- Unit stat table: damage kinds 1/2 → elements, protection/resistance scaling, negative damage spread
  (`0x516f6f`); hero carry-over. [units](data/units.md#open-questions)

## Progression

- Hero state between campaign maps (saves, `.a2c`). Start: `FUN_00514920`. [progression](data/progression.md#open-questions)

## Items

- None open. Related and not started: `.a2c` characters and saves, the `Scenario.dll` state machine beyond the shop table.
  [items](data/items.md#open-questions)

## Spells

- Client cast command path (range / mana / known-spell checks before messages `0x1e`/`0x1f`, `0x25`/`0x26`). Start `FUN_005702be`.
  [spells](data/spells.md#11-open-questions)
- Minion brain modes (`brain+0x20` 1 = Summon, 3 = Control Spirit). Start `FUN_005709d9`, `FUN_00570b8b`.
  [spells](data/spells.md#11-open-questions)
- Spellbook tooltip rows Speed / Sight array pairing. Start `FUN_00416615`, `FUN_004c628f`. [spells](data/spells.md#11-open-questions)

## Not started (from the reversing plan)

- `.alm` triggers (sections 7, 10–12); the server reader `FUN_00534ad4` parses all of them
  (switch on the section id). Sections 0–6, 8, 9 are done. [map](formats/map.md#open-questions)
- Part 5 leftovers: event classes of unit `behaviour` bits 1, 2, 4, section 9 per-cell payload.
  [map](formats/map.md#open-questions)
- Section 12 zones (INFERRED music) and the 8000–9999 slot codes of sections 7 and 11.
  [map](formats/map.md#open-questions)
- Unit struct: group AI, damage resolution, orders 0x16/0x18/0x19/0x1a.
  [unit-struct](engine/unit-struct.md#open-questions)
- Line of sight tables and the `FUN_00559536` gate; block-layer dynamic bits
  and per-class `movementType` (`FUN_00557a89`, vtable `+0x20`). [map](formats/map.md#open-questions)
- Dirt mark: caller of the clear `FUN_00559ce5` (the `+0x5c` byte is answered: damage spread, [spells](data/spells.md#4-effect-handlers)).
  [map](formats/map.md#open-questions)
- Structure registration at load: does a unit-made cell record exist before the structures (then
  `FUN_00559890` skips the refresh)? Do triggers name only structures? `FUN_005508a0` callers.
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
- Trigger references to world ids: section 11 is keyed by structure uid (`0x6000 + uid`, CONFIRMED),
  section 7 slots are coded numbers 8000–9999 (INFERRED class × 100 + index), section 3 cells have no exe
  id (engine ids `0x10000 + n` are ours). Left: decode section 7 (`FUN_00562745` `0x562a88`).
  [architecture](engine/architecture.md#open-questions)
- Unregistering a structure (`FUN_0055995a`) clears cells held by another structure; engine releases only
  its own cells. [architecture](engine/architecture.md#open-questions)
- [Cell effects](engine/rendering.md#open-questions) (answered: spell-area sprites, registered by [spells §4](data/spells.md#4-effect-handlers); drawing needs the spell system), unit invisibility / stone curse / hover, message 0x74 (flag 0x80); start at `FUN_004632a1`.
- [Engine object drawing](engine/rendering.md#open-questions): burnt ground, light-map lights on objects; start at `FUN_00404a2a`.
- [Engine minimap](engine/rendering.md#open-questions): final channel pass `0x4ac030`, fog background surface `DAT_00626be0`, fog gate of the unit dots; start at `FUN_004ac414`.
- Movement and orders (H1, H3) [simulation](engine/simulation.md#open-questions): the empty-dynamic-list step at a centre after a failed hop (`FUN_00555c7e`) and whether a stale dynamic list (turn over 32 ticks) occurs with real turn rates;
  Haste/Slow vs the group speed byte (phase I); the regeneration job vs its `tick & 3` test (`FUN_0052bbb7`, `0x50fc5a`); group
  handlers for orders 1, 3, 5, 0x13 and the computer players' branch of the pass (`FUN_00570087`: `57275f`, `57309d`, `572e1e`, `57311c`),
  retreat post pass `FUN_00573713`; tick counters after loading a save (`FUN_004e9b95`, branch of `FUN_004eb715`); the server's handling of the client's type-100 message (`FUN_004f515d`).
- Handoff to combat (phase I) [simulation §9](engine/simulation.md#9-handoff-to-combat-phase-i): wiring the decoded follow driver (7.4: `follow_fallback`, `FUN_0055574d`) to brain modes 4/5/6/8 and orders `0x19`/`0x1b`, orders `0x17`/`0x19`..`0x1d` and their group handlers, voice, the consolidated VERIFY IN GAME list (§9 items 1-10).
- Order planning spike (H3 bench) [simulation §8.7](engine/simulation.md#87-tests-end-states-measured): a 20-unit order on the 256 x 256 map costs ~0.46 s in one tick (pure-Python planner); worker-thread or faster planner, results must stay bit-identical.
- x87 control word for the follow-fallback slope [simulation §7.4](engine/simulation.md#74-read-but-not-implemented-needs-ordersai-of-phase-i): only the follower-on-target-centre `0/0` case depends on it; starting routine CRT start-up before `FUN_00557f08`.
- Pathfinding (H2) [simulation §7](engine/simulation.md#open-questions): stored occupant/stamp slots with release quirks (`FUN_0055073f`, `FUN_0055be86` callers `0x558b7c`/`0x56a5df`, [7.4](engine/simulation.md#74-read-but-not-implemented-needs-ordersai-of-phase-i)).
- Guarding computer-player groups [simulation](engine/simulation.md#open-questions): group order `0x12` handler `FUN_005728fa` (reader of `brain+0x16`) and the home-cell restart `FUN_0056c8af`/`brain+0x9c`; spell record `+9`/`+0xc` as range/cost in `FUN_0056ac5b` (`FUN_0051c391`).
- Click to move UI (H3 stage B): minimap move row (R 1.6 quirk, [ui-layout §8](engine/ui-layout.md)); message colour/position of the message line and the formation text lifetime ([rendering §14](engine/rendering.md)); cursor kept for pending modes 3/7.
- Click to move (H3 research) [research §9](engine/click-to-move-research.md#9-open-questions): voice unit selection `FUN_0041da16`, `FUN_00417f31` beyond the view width (minimap move row), hotkey gating `view+0x80`/`client+0xc0`, `brain+0x50/+0x6c/+0x38` meaning, AI-owned "No way" messages (`0x92`, `+7`).
- Phantom units (9 on blocked cells, never created by the server) and HP-0 units: engine keeps and draws them; decide with the phase H sim. [architecture §9](engine/architecture.md#9-world-state)

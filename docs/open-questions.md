# Open questions

Index of everything not yet known; each spec's "Open questions" section is
the source of truth (rules in CLAUDE.md: add a line when raised, delete it
from both places when answered).

## Animation

- Town scenes: draw code and timing are resolved ([animation §4.11](formats/animation.md)). Left: the hover-region numbers of the
  fighter/mage/shopie sprites and the druid `man`/`woman` variant choice. [animation](formats/animation.md#open-questions)
- World-map Cross: where `+0x134` is reset to 0 on a new click. [animation](formats/animation.md#open-questions)

## data.bin and items

- Human and structure fields in code (`FUN_004a65b0`, `FUN_004a65d0` users; column names known). [databin](formats/databin.md#open-questions)
- Items: none open. Related and not started: the `Scenario.dll` state machine beyond the shop table and the save block. [items](data/items.md#open-questions)

## Progression

- None open ([progression](data/progression.md#open-questions)).

## Combat and death

- Sound (K10 answered the tables, the attenuation, the registry options, the speech names and the music zones; [sound](formats/sound.md#open-questions)): the server events behind the unchanged-HP blow sound, the shop-speech trigger, the unreferenced / missing speech names, `0x5f1a04`; the engine plays sound and music (K11, [audio](engine/audio.md)): open items in the next line.
- Audio K11 ([audio](engine/audio.md#open-questions), starting routines `FUN_0041da16`, `0x467e42`, `FUN_0041b311`): the callers of table ids 3-6 / 11-13 and which `message` (15) sites fire in single player; fog gating of unit sounds and the view state `+0x78 == 1`; which object defs are n44 / n34 / n58 and the first `rand` of the ambience; the town window sounds and the speech test sample; the pickup / retreat / swarm bank offsets; the hurt kind from the old or the new HP (`0x467e42` / `0x467f60`); the DirectSound pan law and the 74 % default against the real mixer (by ear); the exact gapless music switch.
- Attack order aimed at a structure: answered (accepted, fought like a creature; [combat 5.5](engine/combat.md)); only the mage / spell-carrier branch against a structure is untraced.

## Campaign

- L1 ([campaign](engine/campaign.md#4-open-questions), starting routines `0x1000286b`, `0x1000192f`, `0x49b8a6`, `FUN_00514f59`): the school-5 skill order of the creation call; XP in the headless chain (a fight-crediting oracle).

## AI

- Retreat of a unit that can cast Teleport (`FUN_0056cb8c`, range `unit+0xa5`; engine flees on foot); the game start does not send the option messages `0x46` (`FUN_0048c8a3`). [simulation 8.3a](engine/simulation.md#83a-retreat-key-r-bar-button-8-and-the-retreat-mode-ctrl-w)
- Party options message `0x46`: sub `0x80` (`FUN_00578910`) is not built; the registry default of `AutoCasting` on a first run. [ai](engine/ai.md#open-questions)
- Caster follow branch `FUN_00569968`: the word `+0xa0` (a spell-list unit under defend heals the leader; engine: plain scan). [ai](engine/ai.md#open-questions)
- AI casting ([ai §12](engine/ai.md#12-casters-and-special-attacks-confirmed-unless-marked-engine-127)): whether `FUN_00519483` scales the book wrapper in place (`+9` range; also [spells](data/spells.md#11-open-questions)); `FUN_005551d6` in the revive `FUN_00510534`. [ai](engine/ai.md#open-questions)
- (answered K5b) Quest side of [ai §15.2](engine/ai.md#152-the-quest-that-sends-a-group-order-2): the quest system is multiplayer only (no quest is generated in single player, [items §14](data/items.md#14-quests-and-the-item-upgrade-message-0x38)); nothing to build.
- (answered K5b) Quest system (accept `FUN_0052f8e2`, board, rewards), quest events: multiplayer only, see [items §14](data/items.md#14-quests-and-the-item-upgrade-message-0x38); the engine needs none.

## Spells

- [Effects](engine/effects.md#open-questions): the structure branch of the carriers (`vtable +0x34`, `FUN_00559b7f`); the human scan's recompute triggers besides the stat switch; the client effect messages (`FUN_005044ba`, `FUN_00504498`, `FUN_005045a5`).
- Backpack window leftovers (K5b answered: text flag 8, message `0x46e`, the doll item on the cursor, Ctrl+F): the open sound, releases over the minimap / heads / window 8, the window `0x4ba` of message `0x463` (map 10), the hero-screen lists' gold cell (phase K, hero_ui). [ui-layout 11.13](engine/ui-layout.md#open-questions)

## Triggers and scenario

- [Triggers](engine/triggers.md#open-questions): the word `window+0x160` of the three shop windows (`TalkTo` at `0x4b9117` / `0x4bec83` / `0x4c0995`) and the town-screen readers of Var(0x301) / Var(0x302) (`0x4cad3c`, `0x4cdd0a`, `0x4bf096`); (the hire price: none, answered); the purpose of Var(0x307). Instants 29 / 30 stay documented no-ops (the effect system exists now: [effects](engine/effects.md)).
- Scenario event classes: unit `behaviour` bits 1, 2, 4 and the three scenario booleans `+0x194` / `+0x198` / `+0x19c` (`FUN_005303ed`). [map](formats/map.md#open-questions), [unit-struct](engine/unit-struct.md#open-questions)

## Movement and orders

- Player commands `0x1b` (follow / defend) and `0x1d` (patrol), use `0x24`, cast at a cell `0x1f`, town: simulation side built ([ai §14.2](engine/ai.md#142-the-unit-orders-of-the-scripted-sub-commands-10-11-14-15-confirmed)), no engine command or UI issue yet (the item commands `0x21` pickup, `0x22` move item, `0x23` drop gold are built: `PickUp`, `MoveItem`, `DropGold`; the pickup click issues `PickUp` (K5, [items](engine/items.md)); the pack window issues the others); the squad voice; the consolidated VERIFY IN GAME list. [simulation](engine/simulation.md#open-questions), [simulation §9](engine/simulation.md#9-handoff-to-combat-phase-i)
- Click to move: heap block after the `+0xb8` table (`FUN_00582a10`; last-row read of `FUN_00417f31`); the per-order voice slots. [research §9](engine/click-to-move-research.md#9-open-questions)

## Interface

- Shell (L0): the PreCreate level default / torches / hover fade / generator panel layout. [shell](engine/shell.md#open-questions)
- Chat input line (built, [ui-layout](engine/ui-layout.md#open-questions)): the cheat byte `+0xa78` origin (`FUN_0053dd90`, gate of `#show map` in `FUN_004f3d68`), the chat row's text composition (`0x413814`); capture `ClipCursor` rect with an open bar; info-panel quest markers (`main` `0x159`-`0x15e`, `FUN_004180c6`); squad voice samples. Start at `FUN_0040b2b8`, `FUN_004175c7`.
- Spell book window leftovers: colour key of SpellBook / SpellBack / caps, rounding of the level-4 veil `FUN_004565cd`, `view+0x14` at 800x600, map-row recompute `FUN_0041b121`, the left release's cell cast `FUN_0041918e` (table `0x5f1810`). [ui-layout 11.12](engine/ui-layout.md#1112-spell-book-window-bottom-bar-id-3-class-fun_004c61e7-vtable-0x5cf918-confirmed-unless-marked)
- Heads / hero arrows: receivers of messages `0x414` / `0x415` (the hero windows `FUN_0049a428` / `FUN_0049bd95` / `FUN_0049e187`?) and the hero list `FUN_00472460` flags. [ui-layout](engine/ui-layout.md#open-questions)
- Text windows (pause, failed): justified paragraph drawing (`FUN_0045e01d`, `FUN_0045da67`), the scroll bar (`FUN_004da54d`), the complete path with chapter var `>= 0x78`. [ui-layout 11.4](engine/ui-layout.md#114-in-game-menu-pause-freeze)
- Tips window (message `0x45b`, `tips:`): draw of `FUN_004deca4`; no install mission uses the tag. [ui-layout 11.5](engine/ui-layout.md#115-on-screen-messages)
- Info-panel knowledge table: character-file load / write-back (`Knowledge(blob)` / `to_blob`) and the exact engine mapping of client relation bit 8 (`FUN_0041e860`). [ui-layout](engine/ui-layout.md#open-questions) (`FUN_004ea6ab`, `0x4141fa`)
- Info panel: whether the new-game name field accepts `|`. [ui-layout open questions](engine/ui-layout.md#open-questions)
- Message list: quest-event lines (multiplayer only, no work), alternative message colour tables `0x61fb08` / `0x61fba8`. [ui-layout 11.5](engine/ui-layout.md#115-on-screen-messages)
- Character generator ([chargen](engine/chargen.md#open-questions)): the fifth class (bow / astral) is unpickable (`0x42d1a3`, `0x42b220`); what the lower-right quadrant shows (`0x42e1ed`); the hint window's rect and TipsMode check box (`0x4deca4`, `0x42dba8`); the idle shimmer (`0x42b406`); tooltip placement of slot 5 (`0x429b01`); child `0x458`'s 4 px rect (`0x42a0f1`); Esc at shell level (`FUN_004852d8`); Reset pool 100 reaching 45 x4 (verify in play).

## Rendering and engine

- [Engine drawing](engine/rendering.md#open-questions): the Lightning / Prismatic Spray bolts (28 / 30) are built and CONFIRMED ([effects §11](engine/effects.md): ShootDelay spawn, ShootOffset origin, the exact line).  Fire explosion (projectile 13), its lights, steam and burnt ground are built (CONFIRMED `FUN_0046c1d0`, `FUN_005045a5`).  (Burning trees: resolved, [rendering](engine/rendering.md#open-questions).)  Fog gating of burning-cell fire/steam, explosions and bolts: resolved (none; steam needs Lighting, fire needs a map object).  Renderer speed: only a dirty-rectangle re-fog remains, blocked by the screen-anchored fog quads under horizontal scroll ([architecture](engine/architecture.md), round 5).
- K9 drawing (arrows, status effects, flights, Teleport, the lens: built, CONFIRMED), leftovers in [rendering](engine/rendering.md#open-questions): a caster still busy in an earlier client action gets no cast animation or projectile (`0x4151c1` busy test `0x415258`, melee / shoot start `0x413427`; not modelled), the lens border pixels (`FUN_004a6b4b`, `view+0xf4`), and the by-eye VERIFY IN GAME list of [Arrows and shots](engine/rendering.md#arrows-and-shots-k9) (not compared yet).
- (answered) Unit flag `+0x1b8 & 0x80` at the mission start: `FUN_0052be01` sends nothing, see [rendering](engine/rendering.md#open-questions).
- Renderer speed: the densest 1024x768 view is now ~19.5 ms mean (terrain layer cache and per-object item memo; was 26.5), still 11 ms, scrolling ~26 ms; shadow batching was measured and gives nothing (cost is per covered pixel, overlapping pairs). A static-scene cache is left. [architecture](engine/architecture.md#open-questions)
- Unregistering a structure (`FUN_0055995a`) clears cells held by another structure; the engine releases only its own cells. [architecture](engine/architecture.md#open-questions)

## Formats and not started

- Section 12 music: answered in [sound §5](formats/sound.md#5-music-confirmed-unless-noted) (`0x4754e9` picks the nearest zone and writes `0x5f1a08`); left: nothing for the music (never reset after use, sound §5); section 11 inn / shop fields (multiplayer only). [map](formats/map.md#open-questions)
- Line of sight tables and the `FUN_00559536` gate; block-layer dynamic bits and per-class `movementType` (`FUN_00557a89`, vtable `+0x20`). [map](formats/map.md#open-questions)
- Dirt mark: caller of the clear `FUN_00559ce5` (the `+0x5c` byte is answered: damage spread, [spells](data/spells.md#4-effect-handlers)). [map](formats/map.md#open-questions)
- Structure registration at load: does a unit-made cell record exist before the structures (then `FUN_00559890` skips the refresh)? `FUN_005508a0` callers. [map](formats/map.md#open-questions)
- Text conventions of `main/text/*.txt` (line lists, `#key` sections, `mission%d.txt`). [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)

## Saves

- Saves ([saves](formats/saves.md#open-questions)): the server stream's object serialisers (`FUN_0052d16b`, `FUN_0052c3da`, `FUN_0052d5cb`, `FUN_00550008`, `FUN_0052d5b2`, `FUN_0053bbd0`, `FUN_0057a951`, start `FUN_004ec732`) and its 11 option words; the `+0x2f` byte; whether single player ever uses a stored character's items (VERIFY IN GAME); `famehall.dat` fields `b`, `c`; slot `game0000.sav` (read by the server start when `server+0x1ac != 0`, writer unknown) and `game9998.sav` (no sender).
- Phase K save/load UI and writers: the Save / Load / Delete dialogs (`FUN_0043ebf6`, `FUN_0043deaf`, list `FUN_0043dc54`), the `game%d.sav` writer `FUN_0048dc9f` (+ loader `FUN_0048db37`), the mission-start auto-save `game9999.sav` "Restart last mission" (message `0x442` from `FUN_0048c8a3(0)`), the `famehall.dat` write at exit; single player never writes a `.a2c` ([ui-layout 11.4](engine/ui-layout.md#114-in-game-menu-pause-freeze)).
- [Items K5](engine/items.md#open-questions): the client sound of the item notice `FUN_00504b3a` / gold message `0x67`; `unit +0xe4` (the pack index of message `0x21`, INFERRED 0x7FFF); several selected units on a pickup.

## Structures

- Using a structure ([structures](engine/structures.md#open-questions)): verify in game the use-walk stop cells, a far use click failing (structures 2.1, answered in the exe) and that the hovered well's panel redraws as the charges fall (8.1); the "Saving Place" branch (`FUN_0044fff0(0x68f628) == 4`, `FUN_0050155f`). `FUN_0050f12c` case `0xf`.

- Campaign missions in the shell: `replay SESSION --verify` rebuilds a fresh party, so a recorded campaign mission after the first does not verify; the sessions would need the roster (docs/engine/shell.md 3.4).
- Game Options radios / AutoCast mode: the radio picture (`radiob.256` frames 4 / 5) and the Minimum / Average / Maximum bit encoding (`0` / `0x10` / `0x30`) are INFERRED (docs/engine/shell.md 5.3); the Retreat default Never is INFERRED.

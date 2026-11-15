# Open questions

Index of everything not yet known; each spec's "Open questions" section is
the source of truth (rules in CLAUDE.md: add a line when raised, delete it
from both places when answered).

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

- L1 ([campaign](engine/campaign.md#4-open-questions)): how close the grind phase's XP is to a player's (an upper bound; only a play-through tells).

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

## Town mode

- Town scenes ([town-scenes 8](engine/town-scenes.md#8-open-questions), starting routine `0x41d15e` story window): the scene's NPC click still only voices page 1 (the dialogue window exists since L7: `engine.inn.Dialogue`, to be hosted by `TownScene`); Save / Load windows not built; whether the exe keeps the scene loop under the main menu after Exit to Main Menu (no close hook on that path).

- **Guessed for now (town.md 7), still to verify:** info panel position at 800x600 / 1024x768; `backinv*` colour meaning (which of g / b / s a cell takes); the map path-edge tracer (the shop's numbers, grid draw, shelf rects and prices are answered: town-shop 9).


- Inn dialogue ([town-inn 5](engine/town-inn.md#5-open-questions)): the left sheet's derived stat rows for a person (the exe shows every `FUN_0046aa1d` row at detail 7; the engine shows the template's four attributes / HP / mana / defence: a world-free `CombatStats` builder is missing).
- Hero panels = the Inn windows ([town-hero 8](engine/town-hero.md#8-open-questions)): the info panel's name / book / mode rows in the campaign inn and its final rect at 800x600 / 1024x768 (`0x49e451`, ctor `0x4adf45`: the shift `640 - width` is CONFIRMED, the mission-time rect and mode flag are run-time state); (figure cells and "HIRED": answered in L7, town-inn 6).

## Triggers and scenario

- [Triggers](engine/triggers.md#open-questions): the owner race of the two gate-animation readers of Var(0x301) (`0x4cd0fb`, `0x4cdd0a`, decoded: gate animation only; the shop's `window+0x160` and `Var(0x302)` are answered in [town-shop](engine/town-shop.md)); (the hire price: none, answered). Instants 29 / 30 stay documented no-ops (the effect system exists now: [effects](engine/effects.md)).
- Scenario event classes: unit `behaviour` bits 1, 2, 4 and the three scenario booleans `+0x194` / `+0x198` / `+0x19c` (`FUN_005303ed`). [map](formats/map.md#open-questions), [unit-struct](engine/unit-struct.md#open-questions)

- Shop windows ([town-shop 8 / 9](engine/town-shop.md#9-l8-rea-round-2026-11-15), built in L8): the Yes / No shopkeeper clips, shelf highlights and shelf-turn animations (`0x4baa98`, `0x4bae3e`, `0x4baf3f`, `0x4bb040`), the shop tooltips (`0x4b37f7`, `0x4bb2c4`, `0x4bccf8`), the equip path of a drop on the doll (server `0x4f5d27`; refused for now), the insert order of a returned item inside its shelf (`0x52151c`) and the two lists per block, the pack region's hover rule (`+0x144`), the druid / Kaarg animation tables, a lost mission's DLL shop update (the L1 flow).

## Movement and orders

- Player commands `0x1b` (follow / defend) and `0x1d` (patrol), use `0x24`, cast at a cell `0x1f`, town: simulation side built ([ai §14.2](engine/ai.md#142-the-unit-orders-of-the-scripted-sub-commands-10-11-14-15-confirmed)), no engine command or UI issue yet (the item commands `0x21` pickup, `0x22` move item, `0x23` drop gold are built: `PickUp`, `MoveItem`, `DropGold`; the pickup click issues `PickUp` (K5, [items](engine/items.md)); the pack window issues the others); the squad voice; the consolidated VERIFY IN GAME list. [simulation](engine/simulation.md#open-questions), [simulation §9](engine/simulation.md#9-handoff-to-combat-phase-i)
- Click to move: heap block after the `+0xb8` table (`FUN_00582a10`; last-row read of `FUN_00417f31`); the per-order voice slots. [research §9](engine/click-to-move-research.md#9-open-questions)

## Interface

- Chat input line (built, [ui-layout](engine/ui-layout.md#open-questions)): the cheat byte `+0xa78` origin (`FUN_0053dd90`, gate of `#show map` in `FUN_004f3d68`), the chat row's text composition (`0x413814`); capture `ClipCursor` rect with an open bar; info-panel quest markers (`main` `0x159`-`0x15e`, `FUN_004180c6`); squad voice samples. Start at `FUN_0040b2b8`, `FUN_004175c7`.
- Spell book window leftovers: colour key of SpellBook / SpellBack / caps, rounding of the level-4 veil `FUN_004565cd`, `view+0x14` at 800x600, map-row recompute `FUN_0041b121`, the left release's cell cast `FUN_0041918e` (table `0x5f1810`). [ui-layout 11.12](engine/ui-layout.md#1112-spell-book-window-bottom-bar-id-3-class-fun_004c61e7-vtable-0x5cf918-confirmed-unless-marked)
- Heads panel flags: the meaning of the unit flags `+0x1b8 & 0x10 / & 2 / & 0x20 / & 0x40` and the extra panel's 24 rows at 800x600 (INFERRED black). [ui-layout](engine/ui-layout.md#open-questions), [town-hero 8](engine/town-hero.md#8-open-questions) (`FUN_00472460`)
- Text windows (pause, failed): justified paragraph drawing (`FUN_0045e01d`, `FUN_0045da67`), the scroll bar (`FUN_004da54d`), the complete path with chapter var `>= 0x78`. [ui-layout 11.4](engine/ui-layout.md#114-in-game-menu-pause-freeze)
- Tips window of the mission message `0x45b` (`tips:`) and the town / shop / inn `#tips1..4, 11, 12` windows: callers not built (the window itself is `engine/shell/tipswin.py`, rect of `0x45b`: (10, 20, 370, 188)); no install mission uses the tag. [ui-layout 11.5](engine/ui-layout.md#115-on-screen-messages)
- Info-panel knowledge table: character-file load / write-back (`Knowledge(blob)` / `to_blob`) and the exact engine mapping of client relation bit 8 (`FUN_0041e860`). [ui-layout](engine/ui-layout.md#open-questions) (`FUN_004ea6ab`, `0x4141fa`)
- Info panel: whether the new-game name field accepts `|`. [ui-layout open questions](engine/ui-layout.md#open-questions)
- Message list: quest-event lines (multiplayer only, no work), alternative message colour tables `0x61fb08` / `0x61fba8`. [ui-layout 11.5](engine/ui-layout.md#115-on-screen-messages)

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

- Saves ([saves](formats/saves.md#open-questions)): consumers / meaning of the 11 option words (`server+0x174..0x1a0`; defaults 0, `FUN_004e957b`); the 60-byte values of the `map+0x54084` map and the script blocks; meanings of unit / item / effect fields; MFC counter start and class-record widths (VERIFY by a real save); `.reg` kinds of the tail's id arrays and acceptance of `build_reg` trees (INFERRED); the `+0x2f` byte; whether single player ever uses a stored character's items (VERIFY IN GAME); `famehall.dat` fields `b`, `c`; mission-list entry meaning (`FUN_004a8f96`); which UI path writes `game0000.sav`; instant captured by `game9998.sav`.
- Phase K save/load UI and writers: the Save / Load / Delete dialogs (`FUN_0043ebf6`, `FUN_0043deaf`, list `FUN_0043dc54`), the `game%d.sav` writer `FUN_0048dc9f` (+ loader `FUN_0048db37`), the mission-start auto-save `game9999.sav` "Restart last mission" (message `0x442` from `FUN_0048c8a3(0)`), the `famehall.dat` write at exit; single player never writes a `.a2c` ([ui-layout 11.4](engine/ui-layout.md#114-in-game-menu-pause-freeze)).
- [Items K5](engine/items.md#open-questions): the client sound of the item notice `FUN_00504b3a` / gold message `0x67`; `unit +0xe4` (the pack index of message `0x21`, INFERRED 0x7FFF); several selected units on a pickup.

## Structures

- Using a structure ([structures](engine/structures.md#open-questions)): verify in game the use-walk stop cells, a far use click failing (structures 2.1, answered in the exe) and that the hovered well's panel redraws as the charges fall (8.1); the "Saving Place" branch (`FUN_0044fff0(0x68f628) == 4`, `FUN_0050155f`). `FUN_0050f12c` case `0xf`.


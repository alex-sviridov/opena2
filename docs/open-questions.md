# Open questions

Index of everything not yet known; each spec's "Open questions" section is
the source of truth (rules in CLAUDE.md: add a line when raised, delete it
from both places when answered).

## data.bin and items

- Items: none open. Related and not started: the `Scenario.dll` state machine beyond the shop table and the save block. [items](data/items.md#open-questions)

## Progression

- None open ([progression](data/progression.md#open-questions)).

## Combat and death

- Audio K11 ([audio](engine/audio.md#open-questions), starting routines `FUN_0041da16`, `FUN_0041b311`): the `0xb9` diplomacy line (needs the run-time diplomacy matrix); by ear: the DirectSound pan law and the 74 % default against the real mixer, the exact gapless music switch.

## Campaign

- L1 ([campaign](engine/campaign.md#4-open-questions)): how close the grind phase's XP is to a player's (an upper bound; only a play-through tells).

## AI

- (answered K5b) Quest side of [ai §15.2](engine/ai.md#152-the-quest-that-sends-a-group-order-2): the quest system is multiplayer only (no quest is generated in single player, [items §14](data/items.md#14-quests-and-the-item-upgrade-message-0x38)); nothing to build.
- (answered K5b) Quest system (accept `FUN_0052f8e2`, board, rewards), quest events: multiplayer only, see [items §14](data/items.md#14-quests-and-the-item-upgrade-message-0x38); the engine needs none.

## Spells

- Backpack window leftovers: the open sound, the hero-screen lists' gold cell (phase K, hero_ui), the content of the window `0x4ba` of message `0x463` (map 10; opener decoded). [ui-layout 11.13](engine/ui-layout.md#open-questions)

## Town mode

- Town scenes ([town-scenes 8](engine/town-scenes.md#8-open-questions), starting routine `0x41d15e` story window): the scene's NPC click opens the story window (`engine/shell/storywin.py`, page 1 voiced, Ok pages; speakers = roster heroes / dummy doll only, the scene has no person list).
- Hero panels ([town-inn 6](engine/town-inn.md#6-l7-round-rea-0x497adf-0x499783), narrowed, needs a run of the exe): whether the info panel's mode flag toggled with Tab in a mission is what the next inn shows (the exe keeps `+0x70` across; the engine's inn always opens in picture mode).

## Triggers and scenario

- [Triggers](engine/triggers.md#open-questions): (the owner race of the `Var(0x301)` readers: answered, all human scene; the shop's `window+0x160` and `Var(0x302)` are answered in [town-shop](engine/town-shop.md)); (the hire price: none, answered). Instants 29 / 30 stay documented no-ops (the effect system exists now: [effects](engine/effects.md)).

- Shop windows ([town-shop 8 / 11](engine/town-shop.md#11-third-rea-round-2026-11-16)): the two lists per block of the server's shelf object (`0x52151c` calls the list at `block + 0xc`, then the one at `block + 4`; which feeds the client's shelf message is not traced), the timed effects of a potion dropped on the doll (not modelled).

## Movement and orders

- Player commands: built (`0x1b` defend, `0x24` use, `0x1f` cast at a cell; patrol `0x1d` is unreachable from the exe's UI); left: the consolidated VERIFY IN GAME list. [simulation](engine/simulation.md#open-questions), [simulation §9](engine/simulation.md#9-handoff-to-combat-phase-i)
- Click to move: none open (the heap read is a DECISION, [research §9](engine/click-to-move-research.md#9-open-questions); the voice slots are built in K11).

## Interface

- Chat input line (built, [ui-layout](engine/ui-layout.md#open-questions)): the relation test `FUN_0054fb7f` against `0x69049c` in the server echo; the open-book cast branch of the chooser has no drag override. Squad voice samples: see [audio](engine/audio.md). Start at `FUN_0040b2b8`, `FUN_004175c7`. (Cheat byte, chat row composition, `ClipCursor`: answered, [ui-layout 11.5](engine/ui-layout.md#115-on-screen-messages).)
- Spell book window leftovers: colour key of SpellBook / SpellBack / caps, the content of shade-table row 4 behind the veil `FUN_004565cd` (the formula is decoded), whether `view+0x14` is H at 800x600 (map-row recompute `FUN_0041b121` decoded). [ui-layout 11.12](engine/ui-layout.md#1112-spell-book-window-bottom-bar-id-3-class-fun_004c61e7-vtable-0x5cf918-confirmed-unless-marked)
- Heads panel: the extra panel's 24 rows at 800x600 (INFERRED black) and TextBackL's strip position at 1024. [ui-layout](engine/ui-layout.md#open-questions), [town-hero 8](engine/town-hero.md#8-open-questions) (`FUN_00472460`; the unit flags are answered)
- Text windows (pause, failed): the scroll bar's sprite file (class `0x5d00e8`, paint `0x4da80f`, structure decoded) and the first-line indent field `+0x80` (INFERRED 0). [ui-layout 11.4](engine/ui-layout.md#114-in-game-menu-pause-freeze)
- Tips window of the mission message `0x45b` (`tips:`): the receiver builds it (rect (10, 20, 370, 188)); no install mission uses the tag, so not built (the town / shop / inn / chargen / new-game callers are all built). [ui-layout 11.5](engine/ui-layout.md#115-on-screen-messages)
- Info-panel knowledge table: character-file load / write-back (`Knowledge(blob)` / `to_blob`) and the server's composition of the relation word whose bit 8 the client reads (`FUN_0041e860`, client side answered). [ui-layout](engine/ui-layout.md#open-questions) (`FUN_004ea6ab`)
- Message list: quest-event lines (multiplayer only, no work).

## Rendering and engine

- [Engine drawing](engine/rendering.md#open-questions): the Lightning / Prismatic Spray bolts (28 / 30) are built and CONFIRMED ([effects §11](engine/effects.md): ShootDelay spawn, ShootOffset origin, the exact line).  Fire explosion (projectile 13), its lights, steam and burnt ground are built (CONFIRMED `FUN_0046c1d0`, `FUN_005045a5`).  (Burning trees: resolved, [rendering](engine/rendering.md#open-questions).)  Fog gating of burning-cell fire/steam, explosions and bolts: resolved (none; steam needs Lighting, fire needs a map object).  Renderer speed: only a dirty-rectangle re-fog remains, blocked by the screen-anchored fog quads under horizontal scroll ([architecture](engine/architecture.md), round 5).
- K9 drawing (arrows, status effects, flights, Teleport, the lens: built, CONFIRMED), leftovers in [rendering](engine/rendering.md#open-questions): a move / turn message arriving during a cast or attack animation replaces it (CONFIRMED: `0x6b` / `0x6d` start unconditionally), so the ShootDelay event would not fire (not modelled; the busy test of attack / shoot / cast and the busy clock are built and answered), and the by-eye VERIFY IN GAME list of [Arrows and shots](engine/rendering.md#arrows-and-shots-k9) (not compared yet).
- (answered) Unit flag `+0x1b8 & 0x80` at the mission start: `FUN_0052be01` sends nothing, see [rendering](engine/rendering.md#open-questions).
- Renderer speed: the densest 1024x768 view is now ~19.5 ms mean (terrain layer cache and per-object item memo; was 26.5), still 11 ms, scrolling ~26 ms; shadow batching was measured and gives nothing (cost is per covered pixel, overlapping pairs). A static-scene cache is left. [architecture](engine/architecture.md#open-questions)
- Who deletes a structure object in single player (the unregister `FUN_005200bd` is its destructor; the engine never removes one, so the cell-clearing quirk is not modelled). Narrowed: the deleting destructors `0x543630` / `0x543660` (slot 1 of vtables `0x5d12a8` / `0x5d12e8`) are only called virtually, hundreds of shared call sites; needs a run; the creature loop `FUN_0052b459` is units only (corpse list, no delete). [architecture](engine/architecture.md#open-questions)

## Formats and not started

- Section 12 music: answered in [sound §5](formats/sound.md#5-music-confirmed-unless-noted) (`0x4754e9` picks the nearest zone and writes `0x5f1a08`); left: nothing for the music (never reset after use, sound §5); section 11 inn / shop fields (multiplayer only). [map](formats/map.md#open-questions)

## Saves

- Saves ([saves](formats/saves.md#open-questions)): the item armour block of the accumulators (saves 6.12), player / item field meanings (saves 6.6 / 6.9); the cell records' carrier slot pointers after a load (`FUN_0055c420` is a no-op, narrowed).
- Saves, L10c ([saves 7](formats/saves.md#open-questions), starting routine `FUN_004ec732` / `ScenarioLoad` `0x10003686`): the INFERRED parts of the town save (one player / one group, derived unit blocks, Item `+0xc`, player `0x24` block); VERIFY IN GAME against an original town save.
- Save / Load / Delete windows (L10d, [save-ui](engine/save-ui.md#open-questions)): the selected-row colours and the scroll bar's sprite file (list geometry / frame colours and the menu closing are answered, [save-ui 6](engine/save-ui.md#6-answered-by-the-rea-round-of-the-open-questions-confirmed-unless-marked)); VERIFY IN GAME list: [save-ui 5](engine/save-ui.md#5-verify-in-game-users-real-game-check).
- Saves, L10f ([save](engine/save.md#open-questions)): VERIFY IN GAME only: [save 10](engine/save.md#10-verify-in-game-one-list-the-users-real-game-check) (the exe's main-menu return after a failed load is kept as a DECISION, [save-ui 6](engine/save-ui.md#6-answered-by-the-rea-round-of-the-open-questions-confirmed-unless-marked)).
- Mission saves, L10e-B ([saves 7.1](formats/saves.md#71-l10e-b-the-mission-save-mapping-enginemissionsavepy-tests-testenginemissionsavepy-testenginemissionsaveshellpy), starting routine `FUN_004ec732` / `FUN_0048c2e9`): built and tested here; VERIFY IN GAME that the exe loads its own mission saves and that the DECISION words (group `+0x1c`, unit `+0x44`) do no harm there (the engine side is tested: save -> load -> step equals an uninterrupted run). Single player never writes a `.a2c` ([ui-layout 11.4](engine/ui-layout.md#114-in-game-menu-pause-freeze)).
- [Items K5](engine/items.md#open-questions): the 16-bit cell wrap of the `P` scan at the map edge; the content of the window `0x4ba` (message `0x463`, opener `FUN_0048b1f9`).

## Structures

- Using a structure ([structures](engine/structures.md#open-questions)): verify in game the use-walk stop cells, a far use click failing (structures 2.1, answered in the exe) and that the hovered well's panel redraws as the charges fall (8.1).
- Cutscenes, m1 ([cutscenes](engine/cutscenes.md#open-questions), [REA notes](engine/cutscenes-rea.md#open-questions)): the audio channel order / cache markers are checked by stream ends only (the DLL is packed); the 640x360 blit's source x / y (needs eyes); frame dropping in `smackw32.dll`; VERIFY IN GAME: [cutscenes 7](engine/cutscenes.md#7-verify-in-game-nothing-watched-yet).
- Shop, second round ([shop-rea2](engine/shop-rea2.md#open-questions)): the writer of the `0x80` identify box (INFERRED dead), the Kaarg fire bitmap order (lite / burn / cicle INFERRED); VERIFY IN GAME: the human shelf clips, idle and Yes / No clips, the Kaarg brazier, price numbers.

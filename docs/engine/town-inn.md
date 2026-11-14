# Town mode: the Inn dialogue (hire, dismiss, talk; L3, mode bit `4`)

REA of the GOG `allods2.exe` (sha256 in [formats/README.md](../formats/README.md)). Marks: **CONFIRMED** (routine address given) / **INFERRED**.
Part of the L3 town spec ([design](../superpowers/specs/2026-11-13-l3-town-spec-design.md)). The window frame, panels, mode bits, the three buttons' dispatch and the person strip are [town-hero.md](town-hero.md); the `EnterInn` word table, `TalkTo` and the hire / dismiss effect on the roster are [triggers 11.2](triggers.md#112-town-dialogue-enterinn-and-talkto); the speech file names are [sound.md](../formats/sound.md). None of that is repeated: this doc owns the **handlers behind the three buttons** (text keys, flags, sounds, order of effects). Single player only (`client+0x5d8 == 2`).

## 1. The four handlers (CONFIRMED, one `this` = the inn window, `+0xb8` person index, `+0xc0` mercenary units, `+0xe8` NPC units, `+0xfc` words, `+0x68` the dialogue / text target)

All four first resolve the person's **word**: `unit = list[...]`, `i = FUN_0049ab92(unit)` (the index of the first word whose low 16 bits equal the unit's `+0x1dc`; -1 if none), `word = +0xfc[i]`. `A = word & 0xffff`, type `T = word & 0x70000000`.

| handler | called by | text key shown (`FUN_0041d15e` on the text target `+0x68`) | word change | `TalkTo` | sound slot |
|---|---|---|---|---|---|
| **Accept** `0x49b812` | button 0 when bit 31 clear | `T == 0x10000000` (a type-1 offer): `npc<A>accept<C>` (`0x5f43c8`); any other `T` (type 2, "cannot be hired"): `npc<A>reject<C>` (`0x5f43d8`) | type 1 only: `word \|= 0x80000000` (taken) | type 1 only: `TalkTo(word)` **after** the bit is set | `+0x98` Add (`SFX\Add.wav`), **both** branches |
| **Dismiss** `0x49b989` | button 0 when bit 31 set | none (no text) | `word &= 0x7fffffff` | `TalkTo(word)` with bit 31 clear | `+0x9c` NoAdd |
| **Talk** `0x49ba28` | button 1, person is an NPC (`+0xb8 >= count(+0xc0)`; the NPC word index is `+0xe8[+0xb8 - count]`) | `npc<A>talk<B>` (`0x5f43e8`) with `B = (word >> 16) & 0xfff` | none | `TalkTo(word)` (unmodified: bit 31 is ignored by the DLL) | `+0xb4` Talk |
| **About** (inline in `0x496bba`, button 1, person is a mercenary) | button 1 | `npc<A>about` (`0x5f40c0`, `A` = the unit's `+0x1dc` u16, **not** read from the word) | none | none | `+0xb4` Talk |

`C` in the accept / reject key is **`Var(0x300)`, the chapter** (`ScenarioGetVar(0x300)`, pointer `0x62729c`), not the word's `B` field: the text variant of a hire is chosen by the chapter, so the same mercenary answers differently as the campaign advances (CONFIRMED: `push 0x300; call [0x62729c]` at `0x49b8af` / `0x49b925`). Talk uses the word's own `B`.
Afterwards each handler plays its sound through `FUN_00438570(&slot)` (one-shot, priority `0x80`, [town-hero 6](town-hero.md#6-sounds-music-and-tips)); the window then redraws (`0x497223`, which draws the Hire button as Dismiss when bit 31 of the selected mercenary's word is set: `0x4972d9`; the caption switch uses the interface-string id `0x103` for the taken state: INFERRED from the `push 0x103` at `0x4972e2`).

Consequences for the headless model (all CONFIRMED by the above):
- The player's click is a **toggle** per mercenary: Accept sets bit 31 and calls `TalkTo`; Dismiss clears it and calls `TalkTo` with the same word again (`TalkTo` flips `Var(0x1ff + A)`, [triggers 11.2](triggers.md#112-town-dialogue-enterinn-and-talkto)). The handlers read neither gold nor party size ([town-hero 5](town-hero.md#5-data-read--written)); any limit would have to come from `TalkTo` / the server (not checked).
- A type-2 person (cannot be hired) shows its reject text and plays **Add.wav** all the same; nothing changes.
- Type 0 / 3 words reach `TalkTo` **only** through the Talk handler, once per click (repeat clicks repeat the call; what a repeated `TalkTo` does is [triggers 11.2](triggers.md#112-town-dialogue-enterinn-and-talkto)).
- The text keys are looked up in `main/text/town.txt` (47 talk, 41 accept, 41 reject, 7 about sections, [sound.md](../formats/sound.md)); a missing key is shown as the engine's missing-text line (INFERRED, nothing in the handlers tests it).

## 2. Exit and hero arrows

**Exit** (button 2, release; press plays `+0xb0` Out.wav at once): `0x49b69b` sends the window **`0x445`** and, only when `client+0x404 == 4` exactly, posts **`0x42e`** to the client (back to the town scene), the same path as ESC ([town-hero 1](town-hero.md#1-purpose-and-entry-exit)).
**Hero arrows** `0x414` / `0x415` (`0x49b77c` previous, `0x49b6e5` next): `0x405` to the view `+0x68`, the index `+0xbc` over the hero list `+0xd4` steps by one and **wraps** (next: `>= count -> 0`; previous: `0 -> last` via `0x4a0dd0`), the new hero gets vtable `+0x14(1)` (select), then `FUN_004167c2` (the pack view follows the hero). The arrows change the **selected hero shown in the info panel**, never the person strip's `+0xb8`.

## 3. Sounds of the three classes (CONFIRMED paths; `+0x88` loads, `+0x8c` frees)

**Correction to [town-hero 3](town-hero.md#3-widgets-and-resources):** the slot `+0x8c` routines (`0x49bc86`, `0x49c210`, `0x49f122`) are the **free** counterparts (`FUN_00438480` per slot), not an ambient player; the loaders are `+0x88` = `0x49bb47` / `0x49c05f` / `0x49ef88` (`FUN_004384f0(path, &slot)` per slot).

| slot | human (`0x49bb47`) | druid (`0x49c05f`) | Kaarg (`0x49ef88`) |
|---|---|---|---|
| `+0x84..+0x94` | `Town\Inn\` `drink`, `glotok`, `steam`, `water`, `chair` | (none) | (none) |
| `+0x98` / `+0x9c` | `Add` / `NoAdd` | same | same |
| `+0xa0` | `Town\Shop\nofit` | same | same |
| `+0xa4` (enter) | `Town\Inn\enter` | `Town_druid\Inn\din1` | `Town_kaarg\Inn\Kin1` (**file missing in the install**) |
| `+0xa8` | `Town\Inn\Helper` | same | same |
| `+0xac` | `Town\Shop\Breath` | (none) | (none) |
| `+0xb0` / `+0xb4` | `Out` / `Talk` | same | same |
| `+0x140..+0x14c` | (none) | `Town_druid\Inn\DWater1..4` | `Town_kaarg\Inn\Kdish1..4` |
| `+0x150..+0x168` | (none) | `DDruid3`, `Ddruid4`, `Ddruid41`, `Dforest2`, `Dbird4`, `Dbird41`, `Dbird42` | `Kman2`, `Kman3`, `Kvox5`, `Kvox6`, `Kvox7`, `Kvox8` |

(all under `SFX\`; 18 of 19 spot-checked files exist in the install, the Kaarg enter sound `Kin1.wav` does not: the load simply yields no sound, INFERRED; `FUN_004384f0` is not decoded for a missing file.) The ambient / event scheduler is 3c.

## 3b. Buttons: rects and captions (CONFIRMED, answers old open question 1)

The three panels are created by `0x49a65e` with rects (id, l, t, r, b) relative to the window origin `O`: left sheet `0x44d` (0, 0, 160, 480), buttons panel `0x44e` (480, 0, 640, 238), centre `0x450` (160, 0, 480, 480) (the ctor `0x496076` of the buttons panel takes the same arguments; the panel's own button rects below are in **window** coordinates, ctor `0x496172`, `RECT(l, t, r, b)` via `0x41e210`):

| button | rect (relative to `O`) | caption, `main.txt` line (list `0x622600` = `main.txt`, the same list as chargen's Accept `0xee`) |
|---|---|---|
| 0 Hire / Fire | (484, 44, 624, 90) | ctor: `0xf3` "Hire/Fire"; at every refresh `0x497223`: person is not a mercenary or nobody selected -> **empty string**; mercenary with bit 31 clear -> `0x102` "Hire"; bit 31 set -> `0x103` "Fire" |
| 1 Talk | (484, 91, 624, 137) | `0xf2` "Talk" (set at every refresh and in the ctor) |
| 2 Exit | (484, 138, 624, 184) | `0xe8` "Exit" |

Hit test `0x497123` walks the three rects in order (`window + 0x90 + 16 i`, point = mouse minus the window origin). Draw (`0x4966aa`): per button the face bitmap `+0x84` (idle) or `+0x78` (pressed / hovered: the pressed index `+0xc0` equals the hovered `+0xc4`) over the rect, the caption centred in the rect (font `0xa`, colour table `0x620ec0` idle / `0x620dc4` pressed). `0x497223` also redraws after the Hire / Fire click (the caption flips Hire <-> Fire because the word's bit 31 changed). The info-panel mode, the stat sheet and portrait: [town-hero 2](town-hero.md#2-layout-per-resolution).

## 3c. Sounds in the centre panel: the animation scheduler (CONFIRMED for the human class `0x497adf`; answers open question 2)

`FUN_004a0ff0(slot)` = play the slot **looped** (`FUN_0045aa2f(vol, 0, loop = 1, prio 0x80, 0)`) unless `FUN_0045a964` says it plays already; the window's draw slot (`0x49a8f3`) calls it every draw for `+0x90` (human: `water.wav`), so the **ambient is one looping sample re-armed every frame**; `FUN_00438570` is the same without the loop. The one-shots come from the centre panel's draw (statics `0x6275ec` flags, `0x627604` next delay, `0x6275c4` last-event time, `0x6275f4` / `0x627608` timers; `timeGetTime` = IAT `0x6cf074`):
- **Steam**: every draw, if `now - [0x627608] > 10000` ms: play `+0x8c` (steam), stamp.
- **Candle and cauldron** objects (`+0x280` at (x+0x30, y), `+0x2b0` at (x+0x104, y+0xa0)): placed each draw, advanced one frame (`0x401658`) when `now - [0x6275f4] > 100` ms.
- **Idle event**: delay `D = rand() / 16 + 3000` ms (`0x583290`; recomputed after each event). When `now - [0x6275c4] > D`: **D odd -> tender animation 1** (the object `+0x310` at (x+0x50, y+0x98), "drink": it plays `+0x84` drink when its frame equals 30 (`0x4a0fa0`), steps every > 83 ms forward to the end, then backward to frame 0, then the event ends and plays `+0x88` glotok); **D even -> tender animation 2** (object `+0x2e0` at the same place, forward once; at the start plays `+0x94` chair and `+0xac` Breath together); at the end a new `D` is drawn.
- Druid (`0x49ce4f`) and Kaarg (`0x49f353`) classes use the same pattern (100 ms steps, frame-30 triggers, `D = rand`-based): druid: a water-drop object (`+0x3d0`) at frame 0 plays one of `DWater1..4` (`+0x140..+0x14c`, `FUN_004a0fd0(4) + 1`) every 100 ms step; random events pick kind `(D & 3) + 1` (4 -> 3): kind 1 plays `+0x154` (Ddruid4), kind 2 `+0x150` (DDruid3), and a druid object (`+0x400` at (x+0x28, y+0x80)) plays `+0x158` (Ddruid41) at its frame 30; the bird / forest slots follow the same scheme (INFERRED from the slot offsets used: not traced to the last frame number). Kaarg uses `+0x154` / `+0x150` (Kman) the same way.

## 3d. A missing sound file (CONFIRMED structure, answers open question 3)

`FUN_004384f0(slot, path)` only allocates a 0x14-byte sound object holding the path (`FUN_0045a1a2`): **no file is read at load**. The first play (`FUN_0045aa2f`) calls the lazy loader `0x45a3f4` when the object has no buffers; if that leaves them null nothing is played and nothing is reported. So the absent `Kin1.wav` is **silent, not an error** (the Kaarg inn has no entry sound).

## 4. What the headless side can test, what needs eyes

Headless (pure, from the tables): the word lookup (`FUN_0049ab92`), the four handlers' state changes (bit 31 toggle, `TalkTo` calls and their order, chapter-dependent text keys), the key strings against `town.txt`, the sound slot per action; the equivalent of "a player who clicks everyone" is already `CampaignGame.visit_towns()` (L1), so the build step's test is: the window's click sequence yields the same `TalkTo` words and the same roster as `visit_towns` for the same policy.
Needs your eyes / ears: the text pages as the dialogue window shows them (wrapping, speech pairing), the Hire / Dismiss caption swap, the sounds, the person strip's feel.

## 5. Open questions

1. The druid / Kaarg schedulers beyond the slot-to-trigger table of 3c (the exact frame numbers of the bird / forest events; `0x49d259`-`0x49d7a9`, `0x49f6xx`-`0x49fcb0`).
2. The person strip's hit rectangles and arrow schedule ([town-hero 8](town-hero.md#8-open-questions) 5, unchanged).

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

(all under `SFX\`; 18 of 19 spot-checked files exist in the install, the Kaarg enter sound `Kin1.wav` does not: the load simply yields no sound, INFERRED; `FUN_004384f0` is not decoded for a missing file.) The ambient players of the druid / Kaarg classes pick among `+0x140..` (open question 2).

## 4. What the headless side can test, what needs eyes

Headless (pure, from the tables): the word lookup (`FUN_0049ab92`), the four handlers' state changes (bit 31 toggle, `TalkTo` calls and their order, chapter-dependent text keys), the key strings against `town.txt`, the sound slot per action; the equivalent of "a player who clicks everyone" is already `CampaignGame.visit_towns()` (L1), so the build step's test is: the window's click sequence yields the same `TalkTo` words and the same roster as `visit_towns` for the same policy.
Needs your eyes / ears: the text pages as the dialogue window shows them (wrapping, speech pairing), the Hire / Dismiss caption swap, the sounds, the person strip's feel.

## 5. Open questions

1. Caption strings of the three buttons and of the "taken" state (`push 0x103` at `0x4972e2`, table `0x622600`, `FUN_0041f350`): which `main.txt` ids, and the button rects `window+0x90 + 16 i` (set where, `0x4966aa` draws them only). Start `0x4972d9`-`0x497330`, the panel's load.
2. The ambient sound players of the three classes (timers, random choice among `+0x140..`, `FUN_004a0ff0`): [town-hero 8](town-hero.md#8-open-questions) 6, unchanged.
3. What the missing `Kin1.wav` does at load (`FUN_004384f0`, `0x4384f0`).
4. The person strip's hit rectangles and arrow schedule ([town-hero 8](town-hero.md#8-open-questions) 5, unchanged).

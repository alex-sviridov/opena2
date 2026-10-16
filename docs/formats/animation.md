# Animation: how sprite frames become animations

Data checks use the English install (paths compared case-insensitively).
Parts: 1 sources (where each datum comes from); 2 layout of unit/monster/
hero frames (formulas in [units](units.md)); 3 timing rules; 4 the
`allods2/anim` API; 5 whole-install check, engine use, handoff to combat.
**VERIFY IN GAME** items are collected in §3.6.

## 1. Sources

### 1.1 Summary

| Information | Source | Status |
|---|---|---|
| Frames per action, phase lists, per-phase durations | `units.reg`, `structures.reg`, `objects.reg`, `projectiles.reg` | CONFIRMED (§1.2) |
| Frame layout inside a sprite file | hard-coded per class draw routine | CONFIRMED |
| Current phase | per-object counters advanced by the class tick (vtable `+0x3c`) | CONFIRMED |
| Tick rate | game speed → table in `FUN_00492068` | CONFIRMED |
| Hero sprite folder → unit type | string table in `FUN_0046f688` | CONFIRMED |
| Action durations | `obj+0xa8` ticks left, set when an action starts; projectiles: hard-coded switch; move/turn: in-process server (§3.4) | CONFIRMED |
| Sprite headers | **no** animation data, only `w, h, size` per frame | CONFIRMED (`FUN_00426da9`) |

Not a source: no `.txt/.ini/.cfg` in the install mentions phases, frames,
speeds or directions (English and cp1251; only spell descriptions match
"anim"; CONFIRMED by grep). No binary table keyed by sprite file; every
sprite-kind table is a `.reg` read by name; `world/data/data.bin` (not
decoded) is read by none of the loaders/draws below. `video/*/*.reg` hold
only fade ranges (`Common/startx`, `FadingN/startframe`, `endframe`,
`startfade`, `endfade`) for absent videos. Shop animations
(`movies/shop*/` numbered `.bmp`) are not covered.

### 1.2 Registry loaders and record layouts

All loaders read with `FUN_004efddf` (int with default), `FUN_004ef802`
(string), `FUN_004f03c9` (int array). A **sequence** is built from
`…Time`/`…Frame` arrays: each frame value is appended `Time[i]` times
(`FUN_004028e0`), so one element = one tick (CONFIRMED, same loop in all
four). Sequence objects hold the element array at `+4`
(`FUN_00402a30`/`FUN_00402a50`: `elem(i) = [seq+4] + 4·i`); the element
count is in a separate record field.

#### `units.reg`: `FUN_0047f108`

See [units](units.md). Sequences `MoveAnim` `T+0x3c` (length `T+0x50`),
`AttackAnim` `T+0x54` (`T+0x68`), `IdleAnim` `T+0x6c` (`T+0x80`)
(CONFIRMED `0x48004b`–`0x480323`); also the block phase counts, `Flip`,
`Dying`, and event ticks `ShootDelay` `T+0x11c`, `AttackDelay` `T+0x120`.

#### `structures.reg`: `FUN_00482e99`

`graphics\structures\structures.reg`; `Global/Count` records
`Structure<n>`, 0xa4 bytes, stored by ID in table `0x62caf8`
(`FUN_00484850`). CONFIRMED fields (offset; default −1 unless noted):
`File` → `graphics\structures\<File>.256` (+`b.256`, `FUN_00482b5c`);
`ID` +0x0c; `TileWidth` W +0x10; `TileHeight` TH +0x14; `FullHeight` FH
+0x18; `Phases` +0x1c; `SelectionX1/Y1/X2/Y2` rect +0x20; `ShadowY` +0x30
(0); `AnimMask` +0x34 (string of `W·FH + 1` bytes, read only if
`Phases > 1`); A = count of non-`-` mask chars +0x38 (0); sequence length
+0x3c (0); `AnimTime/AnimFrame` sequence +0x40 (only if `Phases > 1`,
else empty); `Picture` +0x54 (16 chars); `Indestructible` +0x64 (0);
`DescText` +0x68 (32 chars); `VariableSize` +0x88, `Usable` +0x8c,
`Flat` +0x90, `LightRadius` +0x94, `LightPulse` +0x98 (all 0). The sprite
object's `+0x4` is the file's frame count (`FUN_00426da9` stores the
trailer count; read by `FUN_0043ae10`).

#### `objects.reg`: `FUN_0047e4a0`

`graphics\objects\objects.reg`; `Global/FileCount` entries
`Files/File<n>` (lazy sprite files, `FUN_0047ed0d`), then
`Global/ObjectCount` records `Object<n>`, 0x6c bytes, appended to list
`0x630d90`. `Parent` is an object **ID**: each int defaults to the
parent's value, and an empty `AnimationTime`/`AnimationFrame` is read from
the parent's section. CONFIRMED fields (default parent's or −1): `ID`
+0x04; (n) +0x08; `File` +0x0c (index into `Files`); `Index` +0x10 (first
frame); `Phases` +0x14; `Width`, `Height` +0x18/+0x1c; `CenterX`,
`CenterY` +0x20/+0x24; `AnimationTime/Frame` sequence +0x28 (length
+0x3c); `FireObject` +0x40; `DeadObject` +0x44; `InMapEditor` +0x48 (0);
`DescText` +0x4c (31 chars, "").

#### `projectiles.reg`: `FUN_004824cc`

`graphics\projectiles\projectiles.reg`; `Global/Count` records
`Projectile<n>`, 0x3c bytes, stored by ID in table `0x62cb10`
(`FUN_004849f0`). **No time array**: timing is in code (§1.4). CONFIRMED
fields: `File`, `A16` → `graphics\projectiles\<File>` `.16a` if `A16`
else `.256` (`FUN_004820a6`; `A16` default 0); `Phases` +0x10 (−1); `ID`
+0x14 (−1); `RotationPhases` +0x18 (16; only `== 1` is tested: no
directions); `Width`, `Height` +0x1c/+0x20 (64); `SFX` +0x24, `Palette`
+0x28, `Homing` +0x2c, `Flip` +0x30 (0). The same loader loads
`projectiles.pal` → `DAT_00630efc`, `projectile_.pal` → `DAT_00630f00`
(16 levels, mode 2) and the trail sprites
`graphics\projectiles\smoke0|1\sprites.16a` → `DAT_0062cb58[0..1]`.

### 1.3 Draw routines: inputs and layout

| Kind | Draw | Inputs | Layout (hard-coded) |
|---|---|---|---|
| Unit | `FUN_00468640` (vtable `0x5d7780` `+0x28`) | type `T` (`obj+0x24`), state `obj+0x78`, facing `obj+0x70`, phase `obj+0x74`, death stage `obj+0x184` | §2, [units](units.md#frame-layout) |
| Hero | same, own sprites `obj+0x1c0`/`+0x1c4` | as unit; `T` from `FUN_0046f688` | as unit |
| Structure | `FUN_004669e8` (vtable `0x5d76d0` `+0x28`); shadow `FUN_00466c2f` (`+0x2c`) | record (`obj+0x24` = ID), cell col/row, phase `obj+0x74`, HP `obj+0x104`, option `DAT_005fb974` | §4.2 |
| VariableSize structure | `FUN_004679f3` (vtable `0x5d8c50`), `FUN_00467bdb` (`0x5d8ca8`), slot `+0x28` | cell in the structure, view clock `view+0xa88` | 9 / 14 pieces (§4.2) |
| Object | inline in view draw `FUN_00406fea` (`0x408b24`–`0x408d33`) | record (map cell byte − 1), cell X/Y, view clock, tile flags | §4.3 |
| Projectile | `FUN_00471fee` (vtable `0x5d78a0` `+0x28`) | record (`obj+0x24` = ID), facing `obj+0x70`, phase `obj+0x74` | §4.4 |

**Hero sprite → unit type** (CONFIRMED `FUN_0046f688`): folder =
`graphics\units\` + (`heroes` if `obj+0x1b8 & 2`, else `heroes_l`, or the
armour material's path from `material.reg` when `obj+0x1a4 ≠ 0`) + `\` +
weapon name (`FUN_00479ba3`) + `_` with a shield; dying heroes (state 6)
use `unarmed`, which with flag 2 becomes `mage_st`/`mage`. The name sets
`obj+0x24` to a `units.reg` ID: `unarmed` 1, `unarmed_` 2, `swordsman` 3,
`swordsman_` 4, `swordsman2h` 5, `axeman` 7, `axeman_` 8, `axeman2h` 9,
`clubman` 10, `clubman_` 11, `pikeman` 12, `pikeman_` 13,
`archer`/`bowman` 14, `xbowman` 15, `mage` 23, `mage_st` 24. Hero layout
and timing come from those types.

### 1.4 Timing

**Tick.** Window message `0x401` (handler `FUN_0040c2b9`; `0x402` draws
via `FUN_00406fea`) → `FUN_0040bdc1`: view clock `view+0xa88` += 1, then
every object's tick (vtable `+0x3c`). `FUN_0048e7d0` posts `0x401` in a
fixed-step loop: one tick each time `timeGetTime() ≥ base + period·(n+1)`
(`n` = `app+0x424`, wraps at 16 and re-bases `app+0x42c`). Period
`app+0x430 = 1000 / rate` ms, set by `FUN_00492068(speed)` (speed clamped
0..8, rate from a jump table; values §3.1). `FUN_0048e62f` is a second
poster sending one `0x401` per call. Per-kind phase rules: §3.2.

**Unit tick** `FUN_0046b5ef` (vtable `0x5d7780` `+0x3c`): `obj+0xa8` =
ticks left in the action, `obj+0x8c` (byte) = action, copied to draw
state `obj+0x78`; `obj+0x9c` = tick counter in the action. CONFIRMED:

| Action | Phase index `obj+0x74` | Events (§2.4) |
|---|---|---|
| 0 idle | `IdlePhases = 0`: 0; else `(++obj+0x9c) mod T+0x80` | |
| 1 move | distance-driven, below | |
| 3 attack | `obj+0x9c`, then +1 | `AttackDelay` → vtable `+0x64` |
| 5 turn | stand frame; facing steps toward `obj+0x8d·16` over the remaining ticks | |
| 6 dying | `obj+0x9c − 1` after +1 (draw uses `/2`) | |
| 7 shoot | `obj+0x9c` | `ShootDelay` with `Projectile ≠ 0` → `+0x58`; `AttackDelay` → `+0x64` |
| 8 cast | `obj+0x9c` | `AttackDelay` → `+0x60`; `ShootDelay` (tick 0 when `obj+0xac == 0x36`) → `+0x5c` |

Actions 2 and 4 are never set: the only writers of `obj+0x8c` are the
message handler `FUN_0040dac9` (0, 1, 3, 5, 6, 7, 8), projectile spawners
(1), object initialisers (0) and save restore `FUN_00492961` (stored
byte); the tick has no case for them (CONFIRMED, every
`mov byte [reg+0x8c]`).

**Projectile flight time** (CONFIRMED hard-coded switch, `FUN_0046c4f1`,
`FUN_0046c28b`): `obj+0xa8` = `dist / 200` for IDs 10, 0x12, 0x28 (and
every `FUN_0046c28b` projectile), `dist / 384` for 12, 13 for 0x1c/0x1e,
21 for 0x36, 1 for 0x38/0x3c, else 0; `dist = √(dx² + dy² + c)` in map
units, `c` = `_DAT_005d7618`.

**Move phase** (CONFIRMED `FUN_0046b5ef` case 1, `0x46b760`–`0x46b8c5`).
`obj+0x90/+0x94/+0x98` = distance still to go (x, y, z); each tick moves
`step = remaining / obj+0xa8` (integer) and subtracts it, then

```
odometer = ftol(odometer + sqrt(step_x² + step_y² + 0.0))   // obj+0x9c
phase    = odometer / 16                                    // obj+0x74
```

and the draw takes `moveSeq[phase mod moveLen]` (`0x468cef`:
`idiv [T+0x50]`): one element per 16 map units moved, whatever the speed.
`obj+0x9c` is not reset by the move message `0x6b`; it carries over from
the idle counter (0 only for types without idle animation), so the first
move phase can vary. Positions are 1/256 cell (`cell = pos >> 8`,
`FUN_004674dd`), so the common `MoveAnimTime` 8 × 2 (33 of 62 types, 16
elements) covers one cell per cycle (INFERRED, arithmetic). The other
branch (`obj+0x24 < 0`) picks 8 phases from accumulated |x| (`obj+0xa0`)
or |y| (`obj+0xa4`) per 25, 26 or 32 units, ±8 jitter on draw position
`obj+0x2c/+0x30`; unreachable: `FUN_0046dd6a` loads the type as unsigned
16-bit and heroes get fixed IDs (INFERRED leftover).

### 1.5 Action durations from server messages

Message loop `FUN_0040dac9` (called before each tick by `FUN_0048e7d0`;
type = byte `msg+9`, switch tables `0x417d45` → `0x417c39`, case =
type − 3). CONFIRMED:

| Msg | Action | Duration `obj+0xa8` | Site |
|---|---|---|---|
| 0x6b | 1 move | `msg[+0xd]` (u8, server) | `0x41333a` |
| 0x6d | 5 turn | `msg[+0xd]` (u8) | `0x4135ad` |
| 0x71 | 3 attack | `T+0x68` (AttackAnim length) | `0x41371f` |
| 0x72 | 7 shoot | `T+0x68` | `0x4139a3` |
| 0x86, 0x8a | 8 cast (caster) | `T+0x68` | `0x415b65`, `0x41604b` |
| 0x86, 0x8b | 1 (new projectile) | `msg[+0xf]` (u16) | `0x415942`, `0x415e64` |
| 0x8c | 1 (new projectile) | 13 | `0x4162b1` |
| 0x6c, 0x6e–0x70 | 6 dying / 0 | death stage, below | `0x410ba8`, `0x410c67` |
| speed msg | — | game speed = `msg[+0xa]` → `FUN_00492068` | `0x417b97` |

**Death stage** `obj+0x184` (CONFIRMED, case at `0x40f422`), recomputed
on these messages from HP `obj+0x104` (s16): > 0 → 0 alive; ≤ 0 → 1
corpse; < −10 → 2; < −20 → 3; < −40 → 4; < −600 → 5 (not drawn). Stages
2–4 = bones frames `stage − 2`. 0 → 1: action 6 for `2 × DyingPhases`
ticks of the `Dying` type (`0x410ba8`), 2 ticks per frame (draw uses
`obj+0x74 / 2`). Staying at 1: action 6 for 4 ticks (`0x410c67`, §3.3
twitch). Back to 0: action 0 (revived). Heroes reload their sprite
(`FUN_0046f688`) on both changes.

**Hero dying** (CONFIRMED `FUN_0046f688`, `0x46904b`–`0x469081`): with
action 6 the folder becomes `unarmed` (type 1, `Flip`, 129 frames) or,
for `obj+0x1b8 & 2`, `mage_st` (type 24, 216 frames). The hero draw always
indexes its own sprite `obj+0x1c0` with the `T`/`T2` formulas and draws
nothing past the file's end (`0x469070`). Largest dying/corpse/bones
index: 116 (type 1), 194 (type 24), inside both files.

**Default game speed** (CONFIRMED): `FUN_0048750d` sets `app+0x434 = 4`
(16 ticks/s); profile loaders `FUN_004923a7`/`FUN_00492961` read
`GameOptions/Speed` from `game%d.sav` (`app+0x248`, built by
`FUN_0048a922` as `9999 − n`), current value as default;
`FUN_004f8233` keeps `DAT_0069d010` in 0..8, else 4. +/− hotkeys
(`FUN_0048a097`, `FUN_00499d05`, `FUN_00499d2f`) step by one.

### 1.6 Visibility gates

`obj+0x7c` (returned by `FUN_004206c0`) = structure visibility, recomputed
by `FUN_004667ff` from tile bits `0xc000` under its cells: 0 if any cell
has `0xc000`, else 1 if one has `0x8000`, else 2 (CONFIRMED). Structures
animate only at 0 (`FUN_004676d2`), flat structures draw only below 2
(`0x408011`), objects animate only on `0xc000` cells (`0x408ba3`).

**Fog update** (CONFIRMED; tile bits 14–15 of [terrain](terrain.md),
never set in shipped maps). `FUN_0040bdc1` calls `FUN_0040c212` when
`clock & 0x1f == 0` (every 32 ticks, `0x40be20`): clear `0x4000` on every
tile, then vtable `+0x48` on every object in view list `view+0x9d0`.
Structures (`0x5d76d0`) use `FUN_00465e36` directly; ground/flying units
(`0x5d7780`, `0x5d7810`) use `FUN_00472f70`, which calls it only while
death stage `< 3`. `FUN_00465e36` does nothing unless sight
`s16 obj+0x10a ≠ 0` and `FUN_00420610(owner)` accepts the owner
(INFERRED: me, or a player sharing vision). It fills a 41 × 41 mask at
`view+0x17e4` via a2mgr Ordinal_93 (→ `FUN_10023720(cellX obj+0x38,
cellY obj+0x3c, sight, callbacks 0x10033cc0/0x10033c60)`, copies 0x1a44
bytes), then for each entry `> 0` at `(i, j)` ORs `0xc000` into the 2 × 2
tiles at column `x + w/2 − 20 + i`, row `y + h/2 − 20 + j` (`w, h` =
vtable `+0x20/+0x24`). So `0xc000` = seen in the last refresh, `0x8000`
alone = explored (never cleared), 0 = never seen. Structure/object
animation freezes outside sight, up to 32 ticks after a unit leaves.

### 1.7 Map placement of objects

The objects draw reads its cell byte from map layer `+0x14`
(`FUN_00420680` on `view+0x80`, `0x407b0d`) = `.alm` section 3: 0 = none,
`b` = object list index `b − 1` (= its `ID`; IDs equal their
`Object<n>` index for all 192). CONFIRMED. The loader copies only rows
`8 … h−5`, columns `8 … w−9` ([terrain](terrain.md#heights)); everything
outside stays 0 and is never read (CONFIRMED, loader window + data check):

- 83 cells in 9 of the 216 maps hold bytes 193–255 (past the list), all
  outside the window.
- Burning trees: 7 objects (`Object1, 4, 7, 10, 13, 16, 19`, files
  `<tree>ire<tree>`) are absent from the install and the `data/version`
  manifest, yet 11 maps place them (206 cells, e.g.
  `sb_an_waterfall_1_3.alm` 62), all outside the window. Loading would
  go `FUN_0047edf3` → `FUN_00426da9` → `FATAL ERROR: can't load`,
  `AfxMessageBox`, abort (`0x426e0b`–`0x426e42`); a2mgr's file-open hook
  (`FUN_004ebe03`, `0x4ebeda` → Ordinal_1, `0x100339be`: tries
  `data\patch\<path>`, `data\<path>`, then the original lookup) has no
  substitute. Sprites load lazily on first draw
  (`FUN_00420720`/`FUN_00420750`), so they are never requested. The 7
  matching dead trees have `FireObject = −2`, which the ambient-sound scan
  `FUN_0041d158` counts as burning (INFERRED: fire crackle).

## 2. Layout: unit, monster and hero sprites

Tools: `tools/anim_contact.py` → `out/contact/anim_<name>_raw.png` (every
frame, index, coloured by block) and `anim_<name>_layout.png` (one row per
block and direction, labelled with facings). Specimens `hero_swordsman`
(`heroes/swordsman`, type 3), `goblin` (64), `dragon` (71, `Flip`).
Check: `tools/validate_units.py`.

### 2.1 Block order

Action-major, then direction-major: stand block, then for each action all
phases of sprite direction 0, then direction 1, …. `S, R` = 16, 8
(9, 5 with `Flip`); `B M A D Bn I` = `MoveBeginPhases`, `MovePhases`,
`AttackPhases`, `DyingPhases`, `BonePhases`, `IdlePhases` (CONFIRMED,
[units](units.md#frame-per-state-fun_00468640); every file, §2.5):

| Block | Frames | Index of (dir `i`, phase `p`) | Drawn for |
|---|---|---|---|
| stand | `S` | `i16` | idle without `IdlePhases`, turn (5), frozen units |
| move | `(B+M)·R` | `S + i·(B+M) + p` | action 1, `p = B + MoveAnim[…]`; the `B` begin phases are never drawn |
| attack | `A·R` | `S + (B+M)·R + i·A + p` | actions 3, 7 **and** 8 (shared), `p = AttackAnim[obj+0x74]` |
| dying | `D·R` | `S + (B+M+A)·R + i·D + p` | action 6, `p = obj+0x74 / 2`; corpse `p = D − 1` |
| tail | `Bn·R` or `I·R` | `S + (B+M+A+D)·R + i·I + p` | `I ≠ 0`: idle animation (dragon, bat, bee, ghost, succubus, star; no bones); else bones, `p` = stage − 2 |

Dying and tail blocks exist only in a file whose type names itself in
`Dying`; others draw death from the `Dying` type's file.

Specimens (CONFIRMED counts; blocks checked by eye: direction 0 faces the
viewer, `R/2` (4 with `Flip`) shows the back, rows repeat the pose):

| Specimen | Type | S | R | stand | move (B+M) | attack | dying | tail | total |
|---|---|---|---|---|---|---|---|---|---|
| `heroes/swordsman` | 3 | 16 | 8 | 0–15 | 16–95 (2+8) | 96–151 (7) | — | — | 152 |
| `monsters/goblin` | 64 | 16 | 8 | 0–15 | 16–95 (2+8) | 96–175 (10) | 176–223 (6) | 224–247 (3 bones) | 248 |
| `monsters/dragon` | 71 | 9 | 5 | 0–8 | 9–63 (3+8) | 64–98 (7) | 99–128 (6) | 129–163 (7 idle) | 164 |

Example (goblin, `d = 12`, left): stand `(12 − 8) & 15 = 4`; animated
direction `((12 − 8) & 14) >> 1 = 2`; attack phase 4 = `16 + 80 + 2·10 +
4 = 120`; corpse `176 + 2·6 + 5 = 193`; bones stage 2 (stride
`IdlePhases = 0`, [units](units.md) quirk) = `224`.

### 2.2 Directions

Facing `d` (`obj+0x70`, 0..15) counts **clockwise from screen-up**.
CONFIRMED: move message `0x6b` copies direction byte `msg+0xc` into
`obj+0x8d` and steps by tables `0x6023b0` (dx) / `0x6023f0` (dy), 16 ints,
non-zero only at even `d`: 0 (0,−1), 2 (1,−1), 4 (1,0), 6 (1,1), 8 (0,1),
10 (−1,1), 12 (−1,0), 14 (−1,−1) (map y grows down). The tick sets
`obj+0x70 = obj+0x8d` for move/attack/shoot/cast (`0x46b837`, `0x46bfc4`,
`0x46c05f`); a turn steps `obj+0xc4` (0..255) toward `obj+0x8d·16` by
`diff / ticks left` and sets `obj+0x70 = obj+0xc4 >> 4` (`0x46c0a3`).

```
                       d 0  up / north            stand i16   anim i8
              d 14      |      d 2                 d 8  -> 0    d 8,9   -> 0
                   \    |    /                     d 10 -> 2    d 10,11 -> 1
        d 12 ------- [unit] ------- d 4            d 12 -> 4    d 12,13 -> 2
        left       /    |    \      right          d 14 -> 6    d 14,15 -> 3
              d 10      |      d 6                 d 0  -> 8    d 0,1   -> 4
                       d 8  down / south           d 2  -> 10   d 2,3   -> 5
                            (faces the viewer)     d 4  -> 12   d 4,5   -> 6
                                                   d 6  -> 14   d 6,7   -> 7
   i16 = (d - 8) & 15           i8 = ((d - 8) & 14) >> 1
```

Sprite direction 0 = `d 8`: front view, facing down the screen; sprite
directions run clockwise (0 down, i16 2 down-left, 4 left, 8 back, 12
right). CONFIRMED by the tables and the art of all three specimens (this
corrects an earlier INFERRED "direction 0 from behind"). Odd facings occur
only through turns; animated states round down to even.

### 2.3 Mirroring (`Flip = 1`)

`Flip` files store the left half plus both poles: stand `i16` 0..8 (down →
left → up), animated `i8` 0..4. CONFIRMED (`FUN_00468640`; frozen case
`0x468f0c`–`0x468f35`): facings 8…15, 0 use them as stored (animated:
`d` 8–15, 0–1); `d` 1..7 draw `16 − i16` (7..1) mirrored, animated `d`
2–7 draw `8 − i8` (3..1) mirrored. The draw sets a mirror flag
(`[ebp-0x48]`) passed as last argument to the blit (vtable `+0x14/+0x34`,
`0x4691c8`, `0x469215`, `0x469333`) → leftward blitter `FUN_0045a64d`
([sprites](sprites.md)). **Hotspot** (CONFIRMED): `left = obj.x −
((CenterX − Width/2) + frame_w/2)` is computed before the flag is read
(`0x469136`), so a mirrored frame flips in place about its centre column;
the `CenterX − Width/2` offset is not negated. Every `Flip` type has
`CenterX = Width/2`, so nothing shifts; the only non-zero x offsets (−1:
mainnecro, skeletons, necromant, druid) are non-`Flip`. 11 of 62 types
use `Flip`: unarmed 1, troll 68, troll_good 102, ghost 69, bat 70, dragon
71, bee 73, squirrel 74, legg 75, turtle 76, star 108. Projectiles use the
same rule with `i16` and 9 stored directions (§4.4).

### 2.4 Attack events: hit and release frames

Attack/shoot/cast messages set `obj+0x9c = 0` (e.g. `0x41374d`). Each tick
compares `obj+0x9c` with the delays **before** taking the phase from it,
so an event fires on tick `delay`, drawn on phase `AttackAnim[delay]`;
delays ≥ sequence length never fire; delay 0 fires on the first tick.
CONFIRMED:

| Action | `ShootDelay` (`T+0x11c`) | `AttackDelay` (`T+0x120`) |
|---|---|---|
| 3 attack | — | `+0x64` = `FUN_0046d145`: `Sound[0]` at the unit (volume by distance) |
| 7 shoot | if `Projectile ≠ 0`: `+0x58` = `FUN_0046c28b`, spawn `T.Projectile` | `+0x64`, sound |
| 8 cast | `+0x5c` = `FUN_0046c4f1`, spawn the spell's projectile (`obj+0xac`; spell `0x36` at tick 0); not gated on `Projectile` | `+0x60` = `FUN_0046d21b`: sound `500 + obj+0xac` |

No damage here: HP arrives in server messages (§1.5); the server code
(`0x4f0000` up) never reads the `units.reg` table `0x62cb40`. So the delays
are the client's impact-sound and release frames; the server hits
`+0x134` ticks after sending the attack (§3.4).

Event phases per type (`phase = AttackAnim[delay]`, CONFIRMED arithmetic;
Len = attack sequence length = action ticks):

| Types (ID) | Len | AttackDelay → phase | ShootDelay → phase | Projectile |
|---|---|---|---|---|
| swordsman 3, 4; clubman 10, 11 | 11 | 4 → 2 | — | 0 |
| swordsman2 5; axeman_2hd 9; troll 68, 102; ogre 66 | 14 | 6 → 3 | — | 0 |
| axeman 7, 8 | 12 | 5 → 2 | — | 0 |
| pikeman 12, 13; cavalrypike 21 | 10 | 4 → 2 | — | 0 |
| cavalrysword 19; zombie_f3/f4 84, 85; skeleton_f1–f4 89–92 | 14 | 4 → 2 | — | 0 |
| zombie_f1/f2 82, 83 | 12 | 4 → 2 | — | 0 |
| archer 14; skeleton_a1–a4 93–96 | 25 | 19 → 6 | 21 → 7 | 1 |
| xbowman 15; zombie_a2–a4 86–88 | 24 | 7 → 1 | 9 → 2 | 2 |
| orc 65, orc_good 101 | 28 | 20 → 6 | 22 → 7 | 3 |
| goblin 64 | 10 | 4 → 4 | — | 0 |
| goblin_s 79 | 14 | 6 → 3 | 10 → 5 | 4 |
| orc_s 80 | 15 | 4 → 1 | — | 0 |
| orc_sh 81 | 24 | 4 → 1 | 6 → 2 | 0 |
| bat 70 | 8 | 2 → 1 | 2 → 1 | 7 |
| succubus 105 | 16 | 6 → 3 | 6 → 3 | 7 |
| legg 75 | 14 | 2 → 1 | — | 0 |
| bee 73 | 8 | 2 → 1 | — | 0 |
| mage 23, mage_st 24 | 12 | 8 → 4 | 8 → 4 | 0, 10 |
| dragon 71 | 14 | 8 → 4 | 8 → 4 | 12 |
| mainnecro 72, skeleton_m3/m4 97, 98, necromant 99, druid 100 | 14 | 6 → 3 | 6 → 3 | 0 |
| catapult1 26 / catapult2 27 | 18 / 16 | 4 → 2 | 0 → 0 (releases on first tick) | 5 / 6 |
| unarmed 1, 2; squirrel 74; ghost 69; turtle 76; wolf 103; spider 104; dino 106; star 108 | 14, 11, 10, 12, 10, 12, 6, 14, 14 | 0 → 0 | 0 → 0 | 0 |
| sheep 107 | 0 | (no attack) | | 0 |

### 2.5 Check against every file

`tools/validate_units.py` (CONFIRMED): all 90 unit sprite files covered,
60 named by `units.reg` types and 30 hero files
(`heroes*/<weapon>/sprites.256`, type from `FUN_0046f688`). Hero files
hold `S + (B+M+A+I)·R` frames (no dying/bones: dying heroes switch to
`unarmed`/`mage_st`), except `unarmed` and `mage_st`, which have them.
59 of 62 types and 30 of 30 hero files exact. Exceptions:

| File | Frames | Layout | Cause |
|---|---|---|---|
| `humans/swordsman/swordsman` (Unit0, ID 3) | 152 | 152 | matches, but key `File0 ` has a trailing space, so the game never finds it ([reg](reg.md)) |
| `humans/unarmed/sprites` as Unit33 (ID 2, no `Flip`) | 129 | 152 | it is the `Flip` layout of Unit21 (ID 1); Unit33 indexes up to 207. The non-`Flip` 152-frame body exists only as `heroes*/unarmed_`. Game data bug |
| `monsters/sheep/sprites` (ID 107) | 144 | 136 | below |

**Sheep** (INFERRED from the art): stand 0–15 and move 16–79 (8 × 8)
match. 80–119 are 8 directions × **5** phases (direction `k` at `80 + 5k`:
80 front, 90 left, 100 back, 110 right), 120–143 are 8 × 3 bones (each
starting with a bloody body). With `DyingPhases = 4` the game uses stride
4: from direction 1 on, dying frames drift into the neighbour's phases;
corpse = `80 + 4i + 3`; bones (stride `IdlePhases = 0`, direction 0 only)
= 112–114, whole bodies of direction 6. Reproduced as is.

## 3. Timing

All in ticks; §1.4–§1.5 hold the derivations.

### 3.1 The game tick

**Clock** (CONFIRMED `FUN_0048e7d0`, `0x48e7e4`–`0x48e89f`): one
fixed-step loop on `timeGetTime` (import `0x6dc0b0`).
`QueryPerformanceCounter` (`0x5692cb`, `0x584f1e`) and `GetTickCount` are
not used for it; the server `FUN_004f967a` reads `GetTickCount` only to
time itself (`+0x1b8`). Each pass:

```
loop:
    due = base + period · (n + 1)          // app+0x42c, app+0x430, app+0x424
    if timeGetTime() < due: stop
    if n == 0: base = timeGetTime()        // re-base once per 16 ticks
    n = (n + 1) & 15
    server.step()                          // FUN_004f967a (DAT_0060e684)
    client.read_messages(100)              // FUN_0040dac9: actions, durations
    post 0x401 → FUN_0040bdc1               // view clock +0xa88 ++, every object's tick
```

| speed | 0 | 1 | 2 | 3 | 4 (default) | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| ticks/s | 8 | 10 | 12 | 14 | 16 | 20 | 24 | 28 | 32 |
| period ms (`1000/rate`, integer) | 125 | 100 | 83 | 71 | 62 | 50 | 41 | 35 | 31 |
| actual rate | 8 | 10 | 12.05 | 14.08 | 16.13 | 20 | 24.39 | 28.57 | 32.26 |

The server steps exactly once per client tick, in the same loop. Late
ticks run back to back only until `n` wraps: the re-base drops older
backlog (≤ 15 extra ticks after a stall). Jitter: each block of 16 runs at
`X, X+2P, X+3P, …, X+16P`, then tick 0 of the next block immediately (gap
0); average one tick per period. Changing speed (`FUN_00492068`; network
`0x417b97`) resets `n = 0`, `base = GetTickCount()`
(`0x49213a`–`0x492152`); INFERRED: both clocks count ms since boot, so
this only shifts the first tick. The exe never calls `timeBeginPeriod`
(VERIFY 3.6 #1).

### 3.2 What advances each kind of animation

`clock` = `view+0xa88`; `seq` = the kind's registry sequence. All
CONFIRMED.

| Kind | Phase rule | Gate | Source |
|---|---|---|---|
| Terrain water (sets 8–11) | set `8 + ((s + (x+1)·y + (clock >> 2)) & 3)`: 1 frame / 4 ticks, 16-tick loop | `DAT_005fb974` ("Object animations", [lighting §6](../mechanics/lighting.md#6-options)) | [terrain](terrain.md) |
| Structure | `k = seq[obj+0x74]`; `obj+0x74 = (obj+0x74 + 1) mod len` per tick if the sequence is non-empty and `FUN_004206c0() == 0` | visible and `DAT_005fb974`, else frozen | `FUN_004676d2` (vtable `0x5d76d0` `+0x3c`) |
| VariableSize bridge | bottom edge `8 + (clock & 3)`: 1 frame / tick | none | `FUN_00467bdb` |
| Object | `Index + seq[(clock + X + X·Y) mod len]` (no tick routine) | cell `0xc000` (else `Index`); option off: frame **0** | `0x408b24` (§4.3) |
| Projectile (default) | `obj+0x9c` (age) += 1; `(age / 2) mod Phases`: 1 frame / 2 ticks, loops for the flight | — | `FUN_00471643` (vtable `0x5d78a0` `+0x3c`) |
| Projectile 0x1c/0x1e | `age − 1` = 0…12 → 4 3 2 1 0 1 2 1 0 1 2 3 4 (`0x471fba`); other ages keep the value; once, 13 ticks | — | §4.4 |
| Projectile 0x17, hit IDs (0x10, 0x14, 0x18, 0x22, 0x2c–0x32, 0x38, 0x3c, 0x3e–0x42); 0x36 | `age` (0x36: `age − 1`), 1 frame / tick, once (INFERRED: removed when time ends) | — | |
| Unit idle (`IdlePhases ≠ 0`) | `idleSeq[(++obj+0x9c) mod idleLen]` | — | `0x46b6ab` |
| Unit stand (`IdlePhases = 0`) | stand frame, counter zeroed every tick | — | `0x46b6db` |
| Unit move | `moveSeq[(odometer / 16) mod moveLen]` (§1.4) | — | |
| Unit attack/shoot/cast | `attackSeq[t]`, `t` = 0, 1, … | — | |
| Unit turn | stand frame of the stepping facing | — | |
| Unit dying | phase `t / 2`, `t` = 0 … `2D − 1` | — | |

At 16.13 ticks/s: water frame every 248 ms (cycle ≈ 1 s); 6-phase
projectile loop 12 ticks ≈ 0.74 s; 6-phase death ≈ 0.74 s; goblin attack
(Len 10) 0.62 s.

### 3.3 Unit actions: duration, then back to idle

**Rule** (CONFIRMED `FUN_0046b5ef`, `0x46b647`–`0x46b724`,
`0x46c1c5`–`0x46c1e4`): a message sets `obj+0x8c` and `obj+0xa8` (§1.5)
during `read_messages`, before the same pass's tick. Each tick with
`obj+0xa8 > 0` runs the action, copies it to `obj+0x78`, decrements
`obj+0xa8`: an action of length `N` is drawn on exactly `N` ticks. On the
first tick with `obj+0xa8 == 0` the state becomes 0 (idle). Nothing
repeats without a new server message.

| Action | Length `N` | Shown | After |
|---|---|---|---|
| 1 move | `msg[+0xd]` = server ticks per cell | distance-driven cycle | idle, unless the next `0x6b` arrives in the same pass |
| 5 turn | `msg[+0xd]` = server turn ticks | stand frame of the stepping facing | idle |
| 3, 7, 8 | `T+0x68` | `AttackAnim[0 … N−1]`, events §2.4 | idle |
| 6 dying | `2 · DyingPhases` of `Dying` type | dying 0 … D−1, 2 ticks each | idle + stage 1 = corpse `D − 1` held; later bones by HP |

After an action, with `IdlePhases ≠ 0` the idle counter continues from
the action's last `obj+0x9c` (arbitrary start phase); otherwise stand,
counter zeroed each tick (CONFIRMED `0x46b6ab`–`0x46b6f2`).

Walk continuity: one `0x6b` per cell; the odometer is not reset between
cells (CONFIRMED, no write to `+0x9c` on `0x6b`), so walking continues
the cycle. INFERRED: a step arriving one pass late shows one tick of
stand/idle (VERIFY #2).

Corpse re-hit twitch (CONFIRMED path `0x410c67`): a death-stage message
leaving the stage at 1 sets action 6 for 4 ticks **without** resetting
`obj+0x9c`. Without idle animation the counter is 0, so dying phases 0,
0, 1, 1 replay, then the corpse again. With idle animation the counter is
arbitrary and the draw (`0x468e8f`, no clamp) indexes past the dying block
(VERIFY #3).

### 3.4 Where the speeds come from

The client plays what the server sends.

**Walk: ticks per cell** (CONFIRMED `FUN_00563185`; sender `FUN_00519b30`
→ `FUN_0050cd3c` writes `msg[+0xd] = mover+0xaa`; the server marks the
unit busy until `tick + msg[+0xd]`, `unit+0x138`):

```
base  = template_speed (unit+0x70 → +0x3c → byte +0x44) if non-zero,
        else unit speed stat (s16 unit+0x8c)                 // FUN_0056314a
dir8  = (angle + 16) >> 5                                    // 8 compass steps
if ground unit (vtable +0x20 == 1):
    v = base · SpeedMultiplier                               // map.reg, 8
    δ = clamp(h[from] − h[to], −32, 32)                      // signed cell heights, map+0x944f4
    v = v + v·δ/64  (downhill faster, uphill slower; v·|δ| >> 6)
    c = (cost[from] + cost[to]) >> 1, or 8 if 0               // per-cell terrain cost
    v = v / c
else:
    v = base                                                 // (base·8)/8, fliers ignore terrain
v = clamp(v, 1, 63)                                          // units per tick (1/256 cell)
step_x, step_y = v·dx, v·dy, each × 0.707 (truncated) when diagonal
ticks_per_cell = ceil(256 / |step_x or, if 0, step_y|)      // mover+0xaa
```

Terrain costs (CONFIRMED `FUN_0055dd41`: `world/data/map.reg`, section
`Terrain`, keys `Cost<name>`, into `map+0x54147…`):

| Terrain | Land | Grass | Flowers | Sand | Cracked | Stones | Savanna | Mountain | Water | Road |
|---|---|---|---|---|---|---|---|---|---|---|
| `Cost` (file) | 8 | 8 | 8 | 14 | 6 | 12 | 8 | 16 | 8 | 6 |
| default in code | 8 | 8 | 9 | 14 | 6 | 12 | 11 | 16 | 8 | 6 |

`SpeedMultiplier` (`Path Finding`, default 8) = 8; with cost 8 it cancels
(flat grass: `v = base`).

**Per-cell cost** (CONFIRMED `FUN_0055e616` → `FUN_0055e93d`): at map load
the server fills three 256 × 256 byte arrays indexed `(y << 8) + x`:
`cost` (`map+0`, read by `FUN_00564137`/`FUN_00569a40`), `flags`
(`map+0x10000`), and a signed byte at `map+0x944f4` (the slope term's
height). From tile word `v & 0x3ff` ([terrain](terrain.md)):

```
if (v & 0x300) == 0x200:                 # sets 8–11, water
    cost = 8
    type = 9 water if row < 8, except row 4 strip 1 → 1 land; row ≥ 8 → 0xff
elif row < 14:
    (A, B) = pair[set]                   # map+0x54126 + 2·set
    m = blend[strip][row]                # map+0x540a6 + 16·strip + row
    cost = B, (A + 3B)>>2, (A + B)>>1, (3A + B)>>2, A   for m = 1..5   # costs from map.reg
    type = A if m > 2 else B
else:
    type = 0xff, cost = 8
cost[cell] = cost if type < 13 else Cost[0] (= 0xff, impassable)
flags[cell] = 1 if v & 0x2000 (dirt overlay), type == 8 (mountain) or water; 5 if the map's +0x10 byte ≠ 0
```

Pairs `(A, B)` per set: 0 Grass/Land, 1 Cracked/Land, 2 Sand/Land,
3 Savanna/Land, 4 Stones/Land, 5 Cracked/Stones, 6 Flowers/Savanna,
7 Mountain/Stones, 12 Road/Land (types 1 Land … 10 Road in table order).
Blend codes `blend[strip][row]`, rows 0–13:

```
strip 0: 2 3 2 4 3 4 2 2 2 2 4 4 4 4
strip 1: 3 5 3 3 1 3 2 4 2 2 4 2 4 4
strip 2: 2 3 2 4 3 4 2 4 2 2 4 2 4 4
strip 3: 5 5 5 5 5 5 2 2 2 2 4 4 4 4
```

INFERRED: the input map has the client's `+0xc` tiles, its `+0x10` byte
marks blocked cells (flag 5, e.g. objects) and `+0x14` is the height
copied to `map+0x944f4`. Flag `0x20` (tested by `FUN_00564137`) is set
elsewhere (not traced).

Example (flat grass, `base` 18 = hero with default `+0x86 = 30`:
`12 + 30/5`): orthogonal 15 ticks/cell = 0.93 s; diagonal
`trunc(18·0.707) = 12` → 22 ticks; road (6): `v = 24`, 11 ticks; sand
(14): `v = 10`, 26 ticks. **Walk animation**: one element per 16 units,
so the common 16-element `MoveAnim` plays one cycle per orthogonal cell
whatever `v`; frames/s = `rate · v / 32`; a diagonal cell (362 units)
plays 1.41 cycles (CONFIRMED arithmetic).

**Speed stat** `unit+0x8c` (server):

| Source | Rule | Status |
|---|---|---|
| hero defaults | `FUN_00518863`: `+0x8c = 10`, turn rate `mover+0xa = 8`, attack bytes `+0x134 = 8`, `+0x135 = 4` | CONFIRMED |
| hero recompute | `FUN_0051d2a7` (`0x51d6b4`–`0x51d7fa`): `s = A` if `A < 12` else `12 + A/5`, `A = s16 +0x86`; `+10` when `+0xe` is 0x13 or 0x15; if load `+0x90 ≥` capacity `+0x92`: `s −= load / capacity`, min 6; then effect block `+0xd4` adds its delta (`FUN_0051b023`) | CONFIRMED; INFERRED `+0x86` = Reaction/Dexterity, `+0xe` mount/class id |
| monsters | stat block virtual `FUN_0051aed6` (`+0x8c = block+4`) | CONFIRMED write; values from `data.bin` |
| effects (Haste/Slow, …) | effect kind 17 (`FUN_00527122` case 0x11, `0x527757`): `delta = strength · effect+0x40`; heroes add to modifier `+0xd8` (recomputed), others to `+0x8c` | CONFIRMED path; spells/magnitudes are data (open) |

**Spell projectile flight time** (CONFIRMED `FUN_0052365f` →
`FUN_0050ce4e`/`FUN_0050cf32`; `0x86` with target object, `0x8b` with
target point): `msg[+0xc] = 2·spell + 8` (projectile ID), `msg[+0xd]` =
target object ID (u16), `msg[+0xf]` = flight ticks (u16) → new
projectile's `obj+0xa8`:

```
if spell.param[5] == 2:                     // missile-type spell
    ticks = trunc(sqrt(dx² + dy²)) / spell.param[7]   // FUN_005206ea; positions = cell·256 + fraction
    if spell == 10 (lightning): ticks = 5      // the code also tests 11, which never gets here
else:
    ticks = 0
```

`spell.param[k]` = template parameter array (`FUN_00421110(k)` on
`template+0x3c+8`) from `data.bin`; `param[7]` = missile speed in 1/256
cell per tick. Spell 11 (`spell+8` byte `0x0b`) goes via `FUN_005238cb`
and sends no `0x86`. Arrows and catapult shots are client-timed
(`dist / 200`, §1.4).

**Turn** (CONFIRMED `FUN_00560444`; `FUN_00519b30` type `0x6d`,
`msg[+0xd] = mover+0xa4`): byte angles (256 = full circle);
`diff = |target − current|` folded to ≤ 128. If `diff < 33` (or
`256 − diff < 33`, ~45°) the facing snaps, 1 tick; else
`ceil(diff / turn_rate)`, `turn_rate = mover+0xa` (8 for heroes; 180° =
16 ticks ≈ 1 s). Client: `facing256 += (target − facing256) / ticks_left`
per tick (§2.2).

**Attack cadence and hit time** (CONFIRMED `FUN_00518d2f`, server unit
update; order `unit+0x54` = 3 attack, `0xd` cast at unit, `0xe` cast at
point; phase `unit+0x58`, countdown byte `unit+0x6c`):

```
phase 0 (start):  attack: FUN_0052076b → FUN_0050d730 sends 0x71 (unit+0x12c < 2, melee)
                          or 0x72 (shoot); extra = (dist·256 + 128) / 200 if dist > 1
                  cast:   FUN_0052365f sends 0x86/0x8b (mana is checked and spent there)
                  countdown = +0x134 (+ extra); phase = 5
phase 5 (windup): countdown −= 1; at 0:
                  attack → FUN_0052085b: the HIT (FUN_00520927 on units,
                           FUN_00520b16 on structures)
                  cast   → FUN_00523a46 (unit) / FUN_00523a7f (point): the spell effect
                  countdown = +0x135 + rand(0..3) + hero_delay [+ spell param[0] for
                              a weapon's spell]; phase = 7
phase 7 (recovery): countdown −= 1; at 0: phase = 0, ready flag +0x136 = 1
hero_delay = clamp((weapon+0x4a + (30 − unit+0x86)·5) / 12, 0, 12)   // heroes with a weapon (+0x74)
rand(n) = rand()·(n+1) >> 15                                        // FUN_005296f6
```

Melee damage lands `+0x134` ticks after `0x71`; ranged later by
`(dist·256 + 128)/200`, matching the client's arrow `dist / 200`; spell
effects `+0x134` after the cast. One attack = `+0x134 + extra + +0x135 +
rand(0..3) + hero_delay` + 1 tick for the phase-0 pass (INFERRED: one
call per server tick). `0x71/0x72` also set `unit+0x138 = tick + +0x134 +
+0x135` (`FUN_0050cd3c`/`FUN_0050cdcd`); for melee that sum is also in
`msg[+0xd]`, ignored by the client (it plays `AttackAnim`). Heroes'
`+0x134/+0x135` come from the weapon (`FUN_00532dee`: item params 12 and
13, kept when −1; defaults 8 and 4, `FUN_00518863`); monsters' from data
(open). Sound (client `AttackDelay`) and hit are on different ticks: hero
swordsman sound at tick 4, damage at 8. INFERRED: a cycle longer than the
animation shows stand frames between swings; a shorter one restarts at
phase 0 (handler zeroes `+0x9c`) (VERIFY #4).

### 3.5 Summary of loop, once and hold

Loop forever: unit idle/stand (while idle); structure, object, water,
bridge edge (while visible / option on); projectile flight (`Phases`, 2
ticks/frame, until its time ends). Loop by distance: unit walk while move
messages come, then stand. Once, then idle: attack, shoot, cast, turn.
Once: projectile hit effects (1 frame/tick). Once then hold: dying (2
ticks/frame) → corpse; bones replace it as HP falls (stages 2–4), nothing
at stage 5.

### 3.6 VERIFY IN GAME (collected)

1. Menu speed 0..8 → 8…32 ticks/s (stopwatch a 10-cell walk at two speeds;
   ratio `rate₁ / rate₂`); whether speed 8 really gives 32/s given system
   timer quantisation (≈1 or ≈15.6 ms, no `timeBeginPeriod`).
2. One stand frame or none at cell borders on a long straight walk.
3. Corpse twitch: hit a fresh corpse (HP 0 … −10) with an area spell.
4. Hero swordsman (`AttackAnim` 11, cycle 8 + 4 + 0..3 + 1 = 13–16 +
   `hero_delay`) shows ≥ 2–5 stand frames between swings; target HP drops
   ~0.5 s after the swing starts (tick 8), after the clang (tick 4).
5. Hero walking 10 grass vs 10 road cells ≈ `15 : 11` (base 18; measure
   the speed stat first).
6. Haste/Slow change walk time but not attack animation length.
7. Water ripples every ~¼ s at default speed; water, buildings, trees stop
   with Options → "Object animations" off, which also switches off
   "Dynamic lighting".
8. Fireball on a forest: flames last ~1.4 s, shorter while the mouse
   moves (§4.6).

## 4. Implementation

`allods2/anim/` gives every animated class one API (`base.py`):
`aset.actions` (name → `Action`: per-tick phases, loop/once/hold, events),
`aset.frame_at(action, facing, tick)` → `FrameRef` (frame, mirror,
anchor, or pieces of a composite frame), `aset.draw(canvas, ref, x, y)`
with the game's blit modes, `aset.preview_clip`.
`anim.load_set("<kind>:<id>", data_dir)` (unit/structure/object/
projectile, or a bare unit key). Time in ticks (`tick_at_ms` converts).
Previews: `python -m allods2 anim preview KEY DEST`
(`allods2/anim/preview.py`): one GIF per action and facing at the tick
period on a checkerboard, a cross on the anchor, plus a still grid
`out/contact/anim_<name>_grid.png`; `anim preview-all DEST` writes
`DEST/<class>/<name>/<action>[_dNN].gif` and `grid.png` for every set
(`anim.all_keys`). Data check (CONFIRMED): every unit set, all 179
structures, all 31 projectiles and 185 of 192 objects stay inside their
files; exceptions Unit33 (§2.5) and the 7 missing burning trees (§1.7).
Whole-install check: §5.1.

### 4.1 Units, monsters, heroes

`load_unit_set(key)` (units.reg ID, hero folder `heroes/swordsman`, or
unit file/folder `monsters/goblin`) returns the type's actions (`stand`,
`idle`, `move`, `attack` shared by shoot/cast, `dying`, `corpse`,
`bones1..3`); `frame_at` follows §3.5. `move` is distance-driven and takes
the server's ticks per cell. The walk preview scrolls by the real
displacement; the anchor cross turns red on impact, yellow on release.

- Death frames are placed with the unit's own `T` (INFERRED; every type
  and its `Dying` type have equal `CenterX/Y`, `Width`, `Height`, so it
  cannot be observed).
- Heroes use the player tables from `humans/human.pal` like every
  `Palette = 0` type (CONFIRMED, [palettes §4](palettes.md)).
- Not modelled: turn action, corpse twitch (§3.3), the `obj+0x24 < 0`
  walk branch.

### 4.2 Structures and bridges

**Placement** (CONFIRMED `FUN_004669e8`): the view draw calls the
structure once per screen cell. Local column `c = cell x − obj+0x38`; the
routine draws that column's pieces bottom-up, 32 px apart, from row
`(cell y − obj+0x3c) + FH − TH` (all rows when the local row is 0, one row
otherwise), at `(32·x, 32·y − obj+0x10 − obj+0x6c)`. So the file is
`W × FH` pieces of 32 × 32 whose bottom `TH` rows cover the footprint;
piece `(col, row)` sits at `(32·col, 32·(row − (FH − TH)))` from the
footprint's top-left. Pieces use the file's own table (`+0x18`); the
`b.256` piece at 50 % with the main table when Smoothing is on.

**Frame** of piece `cell = col + row·W` (CONFIRMED, all 179 records):
destroyed (`obj+0x104 < 1` and not `Indestructible`) → `count − W·FH +
cell` (the last `W·FH` frames); `k = seq[obj+0x74] ≠ 0` (k = 0 without a
sequence or with `DAT_005fb974 == 0`) and mask char not `-` → `W·FH +
(k−1)·A +` rank among animated cells; else `cell`. Files hold `W·FH +
(Phases − 1)·A` frames (60 structures) or that plus `W·FH` destroyed
frames (117); the two bridges exactly 9 and 14. The nine destructible
structures without a destroyed block (Cave, Pyramids 1–4, Dragon's nest,
Plagat Inn 3, Towers 1–2) look unchanged when destroyed, except the
towers, which freeze on their last animation phase. Example: Church (ID
11, W 4, FH 5, mask `--------++----------`, A 2, 6 phases of 4 ticks):
cell 9 at `k = 3` draws `20 + 2·2 + 1 = 25`.

`StructureSet.frame_at("intact", 0, t, start=0, animate=True)` uses
`seq[(start + t) mod len]`; `animate=False` = frozen (not visible, or
option off). 2-phase records without `AnimTime` (inns, towers, castle, …)
never animate.

**Bridges** (CONFIRMED): map loader `0x4abf1b` builds structure ID `0x21`
(vertical wooden bridge) as class `0x5d8c50` and `0x25` (horizontal) as
`0x5d8ca8`, size in cells from the map record (`+0xa`, `+0xc` →
`obj+0x144/+0x148`). Piece by local cell `(x, y)`:

| Cell | ID 0x21 (`FUN_004679f3`) | ID 0x25 (`FUN_00467bdb`) |
|---|---|---|
| top-left, top-right | 0, 2 | 0, 3 |
| top edge | 1 | `1 + (x & 1)` |
| bottom-left, bottom-right | 6, 8 | 7, 13 |
| bottom edge | 7 | `x` odd: 12; even: `8 + (clock & 3)` |
| left, right edge | 3, 5 | 4, 6 |
| inside | 4 | 5 |

Each piece is drawn at `(32·x, 32·y)` like a 1 × 1 structure; the 0x25
bottom edge animates every tick with no visibility/option gate.

### 4.3 Objects

**Placement** (CONFIRMED `0x40924f`–`0x4092d3`): anchor = cell centre,
`left = 32·X + 16 − ((CenterX − Width/2) + w/2)`, `top = 32·Y + 16 −
((CenterY − Height/2) + h/2) − relief`, with the object's own record even
when its dead object is drawn. Blit `+0x14` with the file's table,
`b.256` at 50 % (`+0x34`) when Smoothing is on.

**Frame** (CONFIRMED `0x408b24`–`0x408d46`), in order: cell fully visible
(`& 0xc000 == 0xc000`) and a sequence → `Index + seq[(clock + X + X·Y)
mod len]` (absolute cell X/Y, so neighbours are out of step); tile bit
`0x2000` and `DeadObject ≠ −1` → frame 0 of the dead object's `File` (its
`Index` ignored); else `Index`; finally, option off → frame **0** of the
file (`0x408d3c`; quirk: an object with `Index ≠ 0` shows another
object's picture). Data (CONFIRMED): `Index + max(AnimationFrame)` is in
range for every object, and in all 135 present files the highest index
used is the last frame. Example: Pine 1 (ID 0, 7 phases of 4 ticks) at
(10, 3), clock 5: `(5 + 10 + 30) mod 28 = 17` → `seq[17] = 4`.
`ObjectSet` actions: `anim`, `still`, `dead`.

### 4.4 Projectiles and spell effects

**Placement** (CONFIRMED `FUN_00471fee`): `left = x − Width/2`, `top = y −
Height/2 − z − obj+0x10`, record size (default 64), not frame size.

**Age** (CONFIRMED): `obj+0x9c` += 1 at the start of each tick
(`0x47187f`). Unit-fired projectiles (`FUN_0046c28b`, `FUN_0046c4f1`)
start at 0 (`0x46c493`, `0x46c935`: first drawn tick has age 1);
message-created ones (0x86 `0x415911`, 0x8b `0x415e33`, 0x8c `0x41628c`)
start at −1. The tick returns "remove" when `obj+0xa8` is 0 on entry
(`0x4716bd`).

**Phase by ID** (tick switch `0x4718c7`, table `0x471f84`):

| IDs | Phase `obj+0x74` | Notes |
|---|---|---|
| default | `(age / 2) mod Phases` | moves toward the target each tick |
| 0x0d (fire explosion) | default | on the 3 × 3 cells around: at age 4 queues (list `view+0xa94`) each cell without bit `0x2000` holding an object with a `DeadObject` or being water (sets 8–11); at age 8 sets `0x2000` (burnt ground) except on water cells without an object (`0x471a32`–`0x471ce4`) |
| 0x17 (blizzard hail) | `age` | sound `0x20b` at age 8 |
| 0x1c (lightning), 0x1e (prismatic) | ping-pong (§3.2) | lifetime 13 |
| 0x36 (teleport) | `age − 1` | lifetime 21 |
| 0x10 0x14 0x18 0x22 0x2c 0x2e 0x30 0x32 0x3e 0x40 0x42 | `age` | follow the target; add effect `ID << 16 \| 0xffff` |
| 0x38, 0x3c | `age` | follow the target; set effect `ID << 16 \| 0x20` |

**Draw** (`FUN_00471fee`, switch on `ID − 7`, table `0x472530`): frame
`phase + Phases·d`, `d = (facing − 8) & 15`, folded to `16 − d` mirrored
when `Flip` and `d > 8` (`Flip` files hold 9 directions); just `phase`
when `RotationPhases == 1`. Data (CONFIRMED): 28 of 28 present files hold
`Phases · dirs` frames except `healing` (8 frames, 7 phases, last unused).
By ID:

| ID | Draw |
|---|---|
| 7 | screen lens (§4.5), no sprite |
| 0x17 | `phase < 8`: frame 8 at `top − (28 − 4·phase)` (stone falling 4 px/tick); else frame `phase − 8` |
| 0x1c | frame `phase` at every point of list `obj+0x11c` (`(x − 8, y − 8)`) |
| 0x1e | frame `phase + 5·colour` (point byte +6) at every list point |
| 0x36 | frame `phase`, no direction |
| 0x38 (heal) | nothing |
| others, `A16 = 1` | `.16a` alpha (`+0x18`, file palette): `src·(a+1)/16 + dst·(15−a)/16` |
| others, `Palette ≠ 0` | opaque (`+0x18`, own table), then `b.256` at 50 % with its all-zero palette = darkens by half ([sprites](sprites.md)) |
| others, `Palette = 0` | opaque `+0x14` with `projectiles.pal` |

So spell effects use **no additive blending**. IDs 10/12 also draw a
smoke trail (§5.1).

`ProjectileSet` has one action, `flight` (default rule, loops) or
`effect` (special rules, once). `frame_at(action, facing, t, age0=None)`:
`age0` defaults to 0 for IDs < 8 and −1 for spell IDs (INFERRED; the
spawner decides). Previews play one `flight` cycle, `effect` for its fixed
lifetime or `Phases` ticks (server lifetimes are data, §3.4).

### 4.5 The screen lens (projectile 7)

CONFIRMED (`FUN_004adfc0(R = 20, d = 16)` at `0x479d9d`, table
`FUN_004ae0df`, draw `FUN_004ae2cb`; global `0x62b61c`): bat and succubus
missiles (`Projectile = 7`) bend the picture behind them. CRT `atan`
(`0x58ede4`, `fpatan`), `sin` (`0x58eb74`, `fsin`):

```
n    = trunc(sqrt(R² − (R − d)²))                 = trunc(sqrt(384)) = 19
k(0) = 1;   k(r) = r / (R · sin(atan(r / (R − d))))  = sqrt(r² + 16) / 20
T[i][j] = (trunc(i·k(r) + 0.5), trunc(j·k(r) + 0.5)),  r = trunc(sqrt(i² + j²) + 0.5),
          or (i, j) when r ≥ n
draw: for i = n−1 … 0, j = n−1 … 0, for (a, b) in (+,+), (+,−), (−,+), (−,−):
          screen[y + b·j][x + a·i] = screen[y + b·T[i][j].y][x + a·T[i][j].x]
          (in place; skipped when either pixel is outside the clip rectangle)
```

Anchor `(x, y − z − obj+0x10)`. `k < 1`: a magnifying bulge of radius 19.
Example `T[18][0]`: `k = sqrt(340)/20 = 0.922` → `(17, 0)`.
`allods2/anim/lens.py`.

### 4.6 Burning cells

CONFIRMED (list `view+0xa94`; update `FUN_0040c199`; draws `0x40892e`,
`0x4094ad`; light: [lighting §3](../mechanics/lighting.md#3-light-map-view--0xa8-confirmed)).
Fire and steam are entries `{cell x | y << 8, counter}`, not objects:

| Step | Rule |
|---|---|
| added | fire explosion (projectile 0x0d at age 4, §4.4) and server message at `0x4155cd` (`FUN_0041dfd3`: cells whose object has a `DeadObject`) |
| counter | +1 per `FUN_0040b35f` call: once per view draw (`0x40aeaa`) and per view message 0x40e / 0x40f (`0x40c3fe`, `0x40c477`); removed at 22 |
| steam | water cell (sets 8–11), counter < 18: projectile 8 (`steam`, 9 frames `.16a`), frame `counter >> 1`, `left = 32·X + 16 − Width/2`, `top = 32·Y + 16 − relief − Height/2` (record 64 × 96) |
| fire | cell with an object, after the object: projectile 0x0f (`firewall`, 11 frames `.16a`), frame `counter >> 1`, same placement (record 128 × 128) |
| light | radius 1, value `36 24 12 0 12 0 12 0 20 28 36` by `counter >> 1` |

INFERRED: one view draw per tick → 22 ticks (1.4 s); mouse messages make
it burn faster (VERIFY #8).

### 4.7 Terrain water

CONFIRMED ([terrain](terrain.md)): rule in §3.2; frozen at set 8 with
the option off. No lava or other animated terrain (13 sets, none else
cycles). `WaterSet` draws a window of map cells; `load_water_set("auto")`
picks the first map window (name order) that is 40–70 % water.

### 4.8 Cursors

CONFIRMED (table `FUN_00480f17`; class `FUN_00480d20`, vtable `0x5d7a90`;
mouse manager `0x60e6c0`: set `FUN_004289d3`, step/draw `FUN_00428c10`,
`0x4291f4`). Each cursor = `(file, hot x, hot y, period ms)`; class
stores sprite `+4`, hot spot `+8/+0xc`, frame count `+0x10`, period
`+0x14`. `.16a` files load with FADE16, others as `.256` with
`(1, 1, 0)`. Manager: frame `+0x24`, last step time `+0x30`:

```
now = timeGetTime()
if now − last > period:  last = now;  frame = (frame + 1) mod count
draw frame (+0x18, own table) at (mouse x − hot x, mouse y − hot y)
```

Steps on the first poll more than `period` ms later (`cursor_frame`
models a 1 ms poll: one frame per `period + 1` ms); setting a cursor
resets the frame; period 2000000000 = still.

| Cursor | Hot spot | Period ms | Frames |
|---|---|---|---|
| default | 4, 4 | still | 1 |
| move, swarm | 2, 3 | 100 | 11 |
| attack | 3, 3 | 100 | 10 |
| select | 3, 3 | 100 | 1 |
| defend | 16, 16 | 100 | 8 |
| patrol | 8, 25 | 100 | 8 |
| cast | 16, 16 | 100 | 14 |
| pickup | 16, 12 | 66 | 11 |
| dice, wait | 16, 16 | 100 | 15, 10 |
| backpack | 16, 16 | 100 | 1 |
| arrow0–7 (map scroll) | 16,6 · 23,9 · 26,16 · 23,24 · 16,28 · 8,24 · 5,16 · 8,9 | still | 1 |
| sdefault (`.16a`), smove, sattack, sdefend, spatrol, scast (`.256`) | 1,1 / 0,0 | still | 1 |
| cantput, town | 38,36 / 16,16 | still | 1 |

Loose `cursors/{attack,cast,defend,move,patrol,pickup}.256` and
`d/l/ld/lu/r/rd/ru/u.256` are named nowhere in the exe: unused leftovers,
four truncated.

### 4.9 Other UI sequences

All `.16a` (FADE16), loaders CONFIRMED, timing **not traced** (previews:
100 ms/frame, marked untimed):

| Sprite | Frames | Loader |
|---|---|---|
| `interface/chrgen/cube` (chargen dice) | 16 | `FUN_004313db` (`+0x8c`) |
| `interface/chrgen/PreCreate/Blind` | 15 | `FUN_004364c3` |
| `Global.Map/MissionFlag`, `YourFlag` | 9, 4 | `FUN_00474320` |
| `interface/inn/<unit>/sprites` (hire previews) | 8 (unit26: 5) | not found: no path string in exe or a2mgr |

`FUN_00474320` also names `Global.Map/Flag1`, `Flag`, `Cross`,
`FlagOnMap`, absent from this install.

### 4.10 Survey: everything that animates

| Class | Metadata | Layout | Timing | Draw | API |
|---|---|---|---|---|---|
| units, monsters, heroes | `units.reg` | §2 | ticks; walk by distance | opaque + 50 % overlay, mirrored | `UnitSet` |
| structures | `structures.reg` | piece grid, `AnimMask` | `AnimTime/Frame` | opaque + 50 % overlay | `StructureSet` |
| bridges | map record size | 9 / 14 pieces | `clock & 3` | opaque | `BridgeSet` |
| map objects | `objects.reg` | `Index + seq` | `clock + X + X·Y` | opaque + 50 % overlay | `ObjectSet` |
| projectiles, spell effects | `projectiles.reg` + per-ID code | `phase + Phases·dir` | `age / 2`, ping-pong, `age` | `.16a` alpha, opaque, 50 % shadow, lens | `ProjectileSet` |
| burning cells | list `view+0xa94` | firewall / steam | counter per view draw, 22 | `.16a` alpha | `BurningSet` |
| water | tile sets 8–11 | 4 sets | `clock >> 2` | tile copy | `WaterSet` |
| cursors | exe table | `.16a` / `.256` | ms, `timeGetTime` | alpha / opaque | `CursorSet` |
| other UI | exe loaders | `.16a` | not traced | alpha | `UiSequenceSet` |

## 5. Verification and engine use

### 5.1 Whole-install check

`allods2/anim/coverage.py` (`verify(data_dir)`; CLI
`tools/validate_anim.py [-v]`; test `tests/test_anim_integration.py`)
loads every `anim.all_keys` key; per action asks every facing (16 for
directional sets) and every tick of one pass, plus 8 past the end (loop,
idle, hold only: `once` objects are removed). Checks each `FrameRef`
(integer anchor, blits inside the file, events inside the action), draws
every preview frame and the trails, then requires every multi-frame or
0-byte sprite file under `graphics/` to be read by a set or match an
`EXCLUSIONS` entry (an entry matching nothing fails, so the list stays
current).

CONFIRMED (English 1.30): 546 sets, 168,335 frame requests, 49,311 drawn
frames, no error. Of 695 multi-frame or empty sprite files, 668 are read
and 27 excluded:

| Category | Files | Why |
|---|---|---|
| not animated (10) | `font1–3.16`, `font4.16a` | glyph sheets ([fonts](fonts.md)) |
| | `interface/lm`, `radiob`, `scrlbars`, `subobj.256` | UI widget sheets |
| | `backpack/sprites.256` + `b.256` | dropped sack: frame = `obj+0x24` (0–5), no clock (CONFIRMED `0x46647f`). The same draw shows `global.map/yourflag` (`obj+0x24 = 6`), `missionflag` (7) or both (8), frame 0, at `(x − 20, y − 60)` / `(x − 5, y − 57)` (globals `0x630e70`/`0x630e74`, loaded at `0x47d29e`/`0x47d2fc`) |
| never loaded (9) | `cursors/attack.256`, `cursors/pickup.256` | not in the cursor table (§4.8) |
| | `projectiles/firebolt/sprites.256` + `b.256` | firebolt has `A16 = 1` |
| | `projectiles/diamonddust`, `freeze`, `smallxpl` | no `projectiles.reg` record; the folder name occurs only in the `data/version` manifest (CONFIRMED, byte search of exe, a2mgr.dll, all data) |
| | `units/humans/swordsman/swordsman.256` + `b.256` | `File0 ` trailing space (§2.5) |
| empty (8) | `cursors/move\|patrol\|cast\|defend.256`, `equipment/[fm]fighter/primary/0[01]05002.256` | 0 bytes |

One set reads past its file, as the game does: ID 2 (Unit33,
`KNOWN_OUT_OF_RANGE`); the game draws nothing there. Outside sprite files
only terrain water animates.

**Projectile trails** (CONFIRMED tick `0x471e43`–`0x471ee6`, draw
`0x4723a4`–`0x4724d5`; list size `0x4204a0`, remove-at `0x5a9378`, append
`0x4028e0`): firebolt (10) and fireball (12) keep list `obj+0x144`. Each
tick, before moving, drop the oldest point if 6 are held, then append the
position packed `(y << 16 | x)` in map units. Draw point `i` with frame
`i` of `smoke0` (10) / `smoke1` (12), oldest first, `.16a` alpha with the
file palette, at `((p & 0xffff) >> 3, p >> 19)` map pixels minus half of
frame 0's size minus the projectile's current `obj+0x6c + obj+0x10`. (x ≥
65536 would spill into y; impossible on maps ≤ 256 cells.) API:
`ProjectileSet.record_trail(points, x, y)` per tick, then
`trail(points)` → `[(FrameRef, (px, py))]` or
`draw_trail(canvas, points, ox, oy, z)`.

### 5.2 How the engine should use this

- **One clock**: fixed-step loop at `period_ms(speed)` (default 16/s);
  per tick apply server messages, then the client tick. `frame_at` takes
  ticks, except cursors and UI sequences (`aset.clock == "ms"`).
- **Load once per type**: cache one set per key
  (`anim.load_set(key, data_dir)`, sprites lazy). Per-object state is a
  few engine-owned integers mirroring the game:

  | Object | State | Call |
  |---|---|---|
  | unit / hero | action, `t` since start, facing, idle counter `start` (`obj+0x9c`), odometer, death stage | `frame_at(action, facing, t, start=…, ticks_per_cell=…)` |
  | structure | phase counter `start`, visible | `frame_at("intact" \| "destroyed", 0, t, start=…, animate=visible and option)` |
  | object | cell (X, Y), visible | `frame_at("anim", 0, clock, x=X, y=Y, animate=…)` or `"dead"` |
  | projectile | `age0`, facing, trail points | `frame_at(…, age0=…)`, `record_trail` |
  | water, bridge edge | none | `WaterSet.cell_sets(clock)`, `BridgeSet.frame_at("bridge", 0, clock)` |

- **Actions come from server messages** (§1.5); count the length down and
  return to idle (§3.3). `frame_at` continues `attack` into idle and
  `dying` into corpse past the end.
- **Draw with `FrameRef`**: `aset.draw`; `aset.extent(ref)` for depth
  sorting/culling. Anchors: units/objects at object/cell centre,
  structures at footprint top-left. Pass relief and flying height as `z`.
- **Events**: `ref.events` (`impact`, `release`, `light=<v>`) only on the
  firing tick; fire once; a renderer skipping ticks must catch up.
- **Options**: "Object animations" off → `animate=False`; Smoothing off →
  `smoothing=False`; fog freezes structures/objects outside sight (§1.6).
- Re-run `tools/validate_anim.py` after any change under `allods2/anim/`.

### 5.3 Handoff to combat

1. **The server decides hits** (§3.4, CONFIRMED `FUN_00518d2f`): melee
   `+0x134` after `0x71`, arrows `+0x134` + `(dist·256 + 128)/200`;
   recovery `+0x135 + rand(0..3)` + hero delay. `units.reg` is client
   only (§2.4).
2. **Hit frames**: `UnitSet.attack_events(kind)` gives `impact` at
   `AttackDelay` and `release` at `ShootDelay` (rules and table §2.4).
3. **Attack, shoot, cast share `AttackAnim`** (`T+0x68` ticks), differing
   only in events. **Gap**: `UnitSet` has one `attack` action whose
   events are shoot's when the type has a projectile, else attack's; a
   melee `0x71` from an archer or any cast needs
   `attack_events("attack" | "cast")` (§5.4 #1).
4. **Cast release** = `ShootDelay` tick; projectile ID `2·spell + 8` (+9
   secondary, `allods2/spells.py`); flight from `msg+0xf` (`dist /
   param7`, lightning 5), `0x8c` projectiles 13 ticks; `age0` 0
   unit-fired, −1 message-created (§4.4). Remove `once` effects at end of
   life (the API does not clamp).
5. **Death and corpses** (§1.5, §3.3): stage from HP; 0 → 1 plays
   `dying` for `2·DyingPhases`, then `corpse` held; 2–4 → `bones1..3`;
   back to 0 = revived. Heroes use the `unarmed`/`mage_st` body
   (`UnitSet.td`) and reload on both changes. The twitch is **not
   modelled**: call `frame_at("dying", f, k)` for `k < 4`, then `corpse`;
   with an idle animation the game reads past the dying block (reproduce
   or leave as open quirk).
6. **No death frames**: `td is None`, no `dying` action; check
   `actions`.
7. **Burning cells** (`BurningSet`, §4.6): 22 ticks fire / 18 steam, light
   per frame; created by spell code (combat).
8. **Invisibility**: effect `0x20` (relation bit 8, [sprites](sprites.md));
   combat owns the flag; needs a translucent unit draw (§5.4).
9. **Open server timing**: monster `+0x134/+0x135`, spell `param[7]` (in
   `data.bin`); take them from messages until decoded.

### 5.4 Suggested engine work on the animation layer

In order of need; none required by the coverage check.

1. `shoot` and `cast` actions on `UnitSet` (attack phases, own events);
   closes §5.3 #3; changes preview counts.
2. Turn action and corpse twitch (§4.1).
3. A per-object animator in the game layer owning the §5.2 state, driven
   by decoded server messages (what `FUN_0046b5ef` does per tick);
   testable by replaying message sequences.
4. Translucent/hidden unit draws (effect `0x20`, bit 8) and per-player
   palettes in the draw path (`UnitSet.player` exists).
5. Lens (post-process) and trails (need map positions) in previews.
6. Dropped sacks and mission flags (`0x46647f`, §5.1) as a small static
   `AnimationSet`.
7. UI sequence timing (open) before the chargen and world-map screens.

## Open questions

- Sight mask algorithm (line of sight, radius shape): a2mgr Ordinal_93 →
  `FUN_10023720`, callbacks `0x10033cc0`/`0x10033c60`; and what the
  original exe did before a2mgr replaced it. [§1.6](#16-visibility-gates)
- Data-driven speeds: monster `+0x8c`, turn rate `mover+0xa`, monster
  `+0x134/+0x135`, `template+0x44` override, spell `param[5]`/`param[7]`,
  which spells create effect kind 17 (Haste/Slow) and their strength; all
  `world/data/data.bin` ([§3.4](#34-where-the-speeds-come-from);
  `FUN_0051aed6`, `FUN_00527122`).
- Server map fill `FUN_0055e616`: input layers `+0x10`/`+0x14`; who sets
  cell flag `0x20` (`FUN_00564137` path). [§3.4](#34-where-the-speeds-come-from)
- UI sequence timing (chrgen cube, PreCreate Blind, world-map flags) and
  the inn picture loader (`FUN_004313db`, `FUN_004364c3`,
  `FUN_00474320`). [§4.9](#49-other-ui-sequences)
- `weapon+0x4a` and `unit+0x86` in the hero recovery delay (INFERRED:
  weapon speed and a hero stat). [§3.4](#34-where-the-speeds-come-from)

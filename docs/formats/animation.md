# Animation: how sprite frames become animations

Binary: `allods2.exe` English 1.30, sha256
`2a8bdf9dc69276cc8d4fee561a7473a6b0f709cf9758abddaf2cd3b1fdfdfe43`.
Addresses were read in REA (Ghidra 12.1.4) and in an `objdump` listing.
Data checks use the English install in `samples/` (paths compared
case-insensitively, as on Windows).

Part 1 ("Sources") records **where** each piece of animation information
comes from. Part 2 ("Layout") maps every frame index of a unit, monster
or hero sprite to (action, direction, phase), with the facing convention,
mirroring and the attack event frames. The draw formulas themselves are
in [units](units.md). Per-kind timing for structures, objects and
projectiles is still to be written as a spec.

## 1. Sources

### 1.1 Summary

| Information | Source | Status |
|---|---|---|
| Frames per action, phase lists, per-phase durations | `.reg` registries: `units.reg`, `structures.reg`, `objects.reg`, `projectiles.reg` | CONFIRMED (loaders below) |
| Frame layout inside a sprite file (blocks, directions, mirroring) | hard-coded in each class's draw routine | CONFIRMED |
| Which phase is current | per-object counters advanced by the class's tick routine (vtable `+0x3c`) | CONFIRMED |
| Tick rate | game-speed setting → table in `FUN_00492068` | CONFIRMED |
| Hero sprite folder → unit type | hard-coded string table in `FUN_0046f688` | CONFIRMED |
| Action durations (move, attack, cast, …) | `obj+0xa8` remaining ticks, set when an action starts; projectiles: hard-coded switch | CONFIRMED (projectiles); units INFERRED from server messages |
| Per-sprite headers | carry **no** animation data: only `w`, `h`, `size` per frame ([sprites](sprites.md)) | CONFIRMED (`FUN_00426da9`) |

Searched and **not** a source:

- Text/config files: no `.txt`/`.ini`/`.cfg` in the install mentions
  phases, frames, speeds or directions (English and cp1251); only spell
  descriptions match "anim". **CONFIRMED** (grep over the install).
- Binary tables keyed by sprite file: none found; every sprite-kind table
  is a `.reg` file read by name. `world/data/data.bin` is not decoded yet
  ([inventory](../inventory.md)); it is not read by any of the loaders
  or draw routines below.
- `video/*/*.reg` hold only fade ranges (`Common/startx`, `FadingN/
  startframe`, `endframe`, `startfade`, `endfade`) for videos absent from
  this install. Shop animations (`movies/shop*/` numbered `.bmp`) are not
  covered here.

### 1.2 Registry loaders and record layouts

All loaders read the registry with `FUN_004efddf` (int with default),
`FUN_004ef802` (string) and `FUN_004f03c9` (int array). A **sequence**
is built from an `…Time` and a `…Frame` array: each frame value is
appended `Time[i]` times (`FUN_004028e0` = append), so one sequence
element = one tick. **CONFIRMED** (same loop in all four loaders).
Sequence objects hold the element array at `+4`
(`FUN_00402a30`/`FUN_00402a50`: `elem(i) = [seq+4] + 4·i`); the loaders
also store the element count in a separate record field.

#### `units.reg`: `FUN_0047f108`

See [units](units.md) for the full table. Correction to the offsets
there (**CONFIRMED**, `0x48004b`–`0x480323`):

| Keys | Sequence object | Length field |
|---|---|---|
| `MoveAnimTime/Frame` | `T+0x3c` | `T+0x50` |
| `AttackAnimTime/Frame` | `T+0x54` | `T+0x68` |
| `IdleAnimTime/Frame` | `T+0x6c` | `T+0x80` |

Frame counts per block (`MovePhases`, `MoveBeginPhases`, `AttackPhases`,
`DyingPhases`, `BonePhases`, `IdlePhases`), `Flip`, `Dying`, and the
event ticks `ShootDelay` (`T+0x11c`) and `AttackDelay` (`T+0x120`) also
come from here.

#### `structures.reg`: `FUN_00482e99`

Registry `graphics\structures\structures.reg`; `Global/Count` records
`Structure<n>`, 0xa4 bytes each, stored by ID in the table at
`0x62caf8` (`FUN_00484850`). **CONFIRMED**:

| Key | Record | Default |
|---|---|---|
| `File` | sprite `graphics\structures\<File>.256` (+`b.256`), `FUN_00482b5c` | — |
| `ID` | +0x0c | −1 |
| `TileWidth` (W) | +0x10 | −1 |
| `TileHeight` | +0x14 | −1 |
| `FullHeight` (FH) | +0x18 | −1 |
| `Phases` | +0x1c | −1 |
| `SelectionX1/Y1/X2/Y2` | rect +0x20 | −1 |
| `ShadowY` | +0x30 | 0 |
| `AnimMask` | +0x34 (string of `W·FH + 1` bytes, read only if `Phases > 1`) | — |
| (count of non-`-` mask chars, A) | +0x38 | 0 |
| (sequence length) | +0x3c | 0 |
| `AnimTime/AnimFrame` | sequence +0x40 (only if `Phases > 1`) | empty |
| `Picture` | +0x54 (16 chars) | |
| `Indestructible` | +0x64 | 0 |
| `DescText` | +0x68 (32 chars) | |
| `VariableSize` | +0x88 | 0 |
| `Usable` | +0x8c | 0 |
| `Flat` | +0x90 | 0 |
| `LightRadius`, `LightPulse` | +0x94, +0x98 | 0 |

The sprite object's `+0x4` is the file's frame count (`FUN_00426da9`
stores the trailer count there; read back by `FUN_0043ae10`).

#### `objects.reg`: `FUN_0047e4a0`

Registry `graphics\objects\objects.reg`; `Global/FileCount` entries
`Files/File<n>` (lazy sprite files, `FUN_0047ed0d`), then
`Global/ObjectCount` records `Object<n>`, 0x6c bytes, appended to the
list at `0x630d90`. `Parent` is an object **ID**; with a parent each
int defaults to the parent's value and an empty `AnimationTime` or
`AnimationFrame` is read from the parent's section. **CONFIRMED**:

| Key | Record | Default |
|---|---|---|
| `ID` | +0x04 | −1 |
| (n) | +0x08 | — |
| `File` | +0x0c (index into `Files`) | parent / −1 |
| `Index` | +0x10 (first frame in the file) | parent / −1 |
| `Phases` | +0x14 | parent / −1 |
| `Width`, `Height` | +0x18, +0x1c | parent / −1 |
| `CenterX`, `CenterY` | +0x20, +0x24 | parent / −1 |
| `AnimationTime/AnimationFrame` | sequence +0x28 | parent's if empty |
| (sequence length) | +0x3c | |
| `FireObject` | +0x40 | parent / −1 |
| `DeadObject` | +0x44 | parent / −1 |
| `InMapEditor` | +0x48 | 0 |
| `DescText` | +0x4c (31 chars) | "" |

#### `projectiles.reg`: `FUN_004824cc`

Registry `graphics\projectiles\projectiles.reg`; `Global/Count`
records `Projectile<n>`, 0x3c bytes, stored by ID in the table at
`0x62cb10` (`FUN_004849f0`). There is **no time array**: projectile
timing is in code (§1.4). **CONFIRMED**:

| Key | Record | Default |
|---|---|---|
| `File`, `A16` | sprite `graphics\projectiles\<File>` `.16a` if `A16` else `.256` (`FUN_004820a6`) | `A16` 0 |
| `Phases` | +0x10 | −1 |
| `ID` | +0x14 | −1 |
| `RotationPhases` | +0x18 (only `== 1` is tested: no directions) | 16 |
| `Width`, `Height` | +0x1c, +0x20 | 64 |
| `SFX` | +0x24 | 0 |
| `Palette` | +0x28 | 0 |
| `Homing` | +0x2c | 0 |
| `Flip` | +0x30 | 0 |

The same loader loads `projectiles.pal` → `DAT_00630efc`,
`projectile_.pal` → `DAT_00630f00` (shade tables, 16 levels, mode 2)
and the trail sprites `graphics\projectiles\smoke0|1\sprites.16a` →
`DAT_0062cb58[0..1]`.

### 1.3 Draw routines: inputs and layout

| Kind | Draw | Inputs | Layout (all hard-coded) |
|---|---|---|---|
| Unit | `FUN_00468640` (vtable `0x5d7780` slot `+0x28`) | type `T` (`obj+0x24`), state `obj+0x78`, facing `obj+0x70`, phase index `obj+0x74`, death stage `obj+0x184` | [units](units.md#frame-layout): stand 16\|9, then per direction Begin+Move, Attack, Dying, bones/idle; `Flip` mirrors |
| Hero | same `FUN_00468640` with its own sprites `obj+0x1c0`/`+0x1c4` | as unit; `T` chosen by `FUN_0046f688` (below) | as unit |
| Structure | `FUN_004669e8` (vtable `0x5d76d0` slot `+0x28`); shadow `FUN_00466c2f` (slot `+0x2c`) | record (`obj+0x24` = ID), cell column/row, phase index `obj+0x74`, hit points `obj+0x104`, option `DAT_005fb974` | below |
| VariableSize structure | `FUN_004679f3` (vtable `0x5d8c50` slot `+0x28`) and `FUN_00467bdb` (vtable `0x5d8ca8` slot `+0x28`) | cell position in the structure, view clock `view+0xa88` | 9 pieces (corners, edges, centre); 14 pieces with bottom-edge frames `8 + (clock & 3)` |
| Object | inline in the view draw `FUN_00406fea` (`0x408b24`–`0x408d33`) | record (map cell byte − 1), cell X/Y, view clock `view+0xa88`, tile flags | below |
| Projectile | `FUN_00471fee` (vtable `0x5d78a0` slot `+0x28`) | record (`obj+0x24` = ID), facing `obj+0x70`, phase index `obj+0x74` | below |

**Structure** (**CONFIRMED** `FUN_004669e8`; data check
**CONFIRMED** on all 179 records): the file is a grid of tile pieces,
`cell = col + row·W`, `W·FH` frames for the intact building. With
`k = seq[obj+0x74]` (0 when the structure has no sequence or when
`DAT_005fb974 == 0`), a cell whose `AnimMask` char is not `-` draws
frame `W·FH + (k − 1)·A + (number of non-`-` chars before it)` when
`k ≠ 0`. When `obj+0x104 < 1` and not `Indestructible`, the cell draws
frame `count − W·FH + cell` (the file's last `W·FH` frames). Files hold
`W·FH + (Phases − 1)·A` frames (60 structures) or that plus `W·FH`
destroyed frames (117); the two VariableSize bridges have exactly 9 and
14 pieces. The nine destructible structures without a destroyed block
(Cave, Pyramids 1–4, Dragon's nest, Plagat Inn 3, Towers 1–2) therefore
look unchanged when destroyed, except the towers, which freeze on their
last animation phase. CONFIRMED (draw formula + frame counts).

**Object** (**CONFIRMED** `0x408b24`–`0x408d33`; data: every object's
`Index + max(AnimationFrame)` is inside its file, and for all 135
present files the highest index used is the last frame): when the
sequence is not empty and the cell is fully visible (`& 0xc000 ==
0xc000`), frame = `Index + seq[(clock + X + X·Y) mod len]` with `X`, `Y`
the absolute cell column/row and `clock = view+0xa88`, so neighbouring
trees are out of step. If the tile has bit `0x2000` and `DeadObject ≠
−1`, the dead object's file is drawn with index 0 and phase 0.

**Projectile** (**CONFIRMED** `FUN_00471fee`; data: 28 of 28 present
files hold `Phases · dirs` frames except `healing` (8 frames, 7 phases,
last unused)): `d = (obj+0x70 − 8) & 15`; with `Flip` and `d > 8`,
`d = 16 − d` mirrored (files with `Flip` hold 9 directions); frame =
`obj+0x74 + Phases · d`, or just `obj+0x74` when `RotationPhases == 1`.
Hard-coded special draws by ID: 7 (`FUN_004ae2cb`), 0x17, 0x1c and
0x1e (several sprites placed from a list), 0x36, 0x38 (nothing). IDs 10
and 12 (`firebolt`, `fireball`) also draw a trail of up to 6 points
with `smoke0|1` frame = trail index.

**Hero sprite → unit type** (**CONFIRMED** `FUN_0046f688`): the folder
is `graphics\units\` + (`heroes` if flag `obj+0x1b8 & 2`, else
`heroes_l`, or the armour material's path from `material.reg` when
`obj+0x1a4 ≠ 0`) + `\` + weapon name (`FUN_00479ba3`) + `_` with a
shield; dying heroes (state 6) use `unarmed`, and with flag 2
`unarmed` becomes `mage_st`/`mage`. The name then sets `obj+0x24` to a
`units.reg` ID: `unarmed` 1, `unarmed_` 2, `swordsman` 3, `swordsman_` 4,
`swordsman2h` 5, `axeman` 7, `axeman_` 8, `axeman2h` 9, `clubman` 10,
`clubman_` 11, `pikeman` 12, `pikeman_` 13, `archer`/`bowman` 14,
`xbowman` 15, `mage` 23, `mage_st` 24. So hero frame layout and timing
come from those `units.reg` types.

### 1.4 Timing

**Tick.** Window message `0x401` → `FUN_0040bdc1` (from the handler
`FUN_0040c2b9`; `0x402` draws via `FUN_00406fea`). `FUN_0040bdc1`
increments the view clock `view+0xa88` and calls every object's tick
(vtable `+0x3c`). `FUN_0048e7d0` posts `0x401` in a fixed-step loop:
one tick each time `timeGetTime() ≥ base + period·(n + 1)` (`n` =
`app+0x424`, wraps at 16 and re-bases `app+0x42c`). The period
`app+0x430 = 1000 / rate` ms is set by `FUN_00492068(speed)` with speed
clamped to 0..8 and rate from a jump table: **CONFIRMED**

| speed | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| ticks/s | 8 | 10 | 12 | 14 | 16 | 20 | 24 | 28 | 32 |
| period ms | 125 | 100 | 83 | 71 | 62 | 50 | 41 | 35 | 31 |

(`FUN_0048e62f` is a second poster that sends one `0x401` per call.)

**Per-kind phase counters** (all **CONFIRMED**):

| Kind | Tick | Phase index |
|---|---|---|
| Structure | `FUN_004676d2` (vtable `0x5d76d0` `+0x3c`) | `obj+0x74 = (obj+0x74 + 1) mod len` if the sequence is not empty and `FUN_004206c0() == 0` |
| Object | none | from the view clock in the draw (§1.3) |
| Unit | `FUN_0046b5ef` (vtable `0x5d7780` `+0x3c`) | see below |
| Projectile | `FUN_00471643` (vtable `0x5d78a0` `+0x3c`) | `obj+0x9c += 1`; default `obj+0x74 = (obj+0x9c / 2) mod Phases`; ID 0x1c/0x1e: hard-coded ping-pong 4,3,2,1,0,1,2,3,2,1,0,…; 0x36: `obj+0x9c − 1`; 0x17 and the hit IDs (0x10, 0x14, 0x18, 0x22, 0x2c–0x32, 0x38, 0x3c, 0x3e–0x42): `obj+0x9c` |

**Unit tick** `FUN_0046b5ef`: `obj+0xa8` = ticks left in the current
action, `obj+0x8c` (byte) = the action, copied to the draw state
`obj+0x78`; `obj+0x9c` = tick counter in the action.

| `obj+0xa8` / action | Phase index `obj+0x74` | Events |
|---|---|---|
| 0 (idle) | `T.IdlePhases = 0`: 0; else `(++obj+0x9c) mod T+0x80` (idle sequence length) | |
| 1 move | distance-driven, see *Move phase* below | |
| 3 attack | `obj+0x9c`, then `+1` | at `obj+0x9c == T.AttackDelay` → vtable `+0x64` |
| 5 turn | (stand frame) facing steps toward `obj+0x8d·16` over the remaining ticks | |
| 6 dying | `obj+0x9c − 1` after `+1` (draw uses `/2`) | |
| 7 shoot | `obj+0x9c` | `ShootDelay` with `Projectile ≠ 0` → `+0x58`; `AttackDelay` → `+0x64` |
| 8 cast | `obj+0x9c` | `AttackDelay` → `+0x60`; `ShootDelay` (tick 0 when `obj+0xac == 0x36`) → `+0x5c` |

**Projectile flight time** (`FUN_0046c4f1`, `FUN_0046c28b`):
`obj+0xa8` = `dist / 200` for IDs 10, 0x12, 0x28 (and every
`FUN_0046c28b` projectile), `dist / 384` for 12, 13 for 0x1c/0x1e, 21
for 0x36, 1 for 0x38/0x3c, else 0, with `dist = √(dx² + dy² + c)` in
map units (`c` = `_DAT_005d7618`). **CONFIRMED** (hard-coded switch).

Actions 2 and 4 are never set: the only writers of the action byte
`obj+0x8c` are the message handler `FUN_0040dac9` (values 0, 1, 3, 5, 6,
7, 8), the projectile spawners (1), the object initialisers (0) and the
save-game restore `FUN_00492961` (a stored byte). The tick has no case
for them. **CONFIRMED** (every `mov byte [reg+0x8c]` in the exe).

**Move phase** (`FUN_0046b5ef` case 1, assembly `0x46b760`–`0x46b8c5`;
**CONFIRMED**). `obj+0x90/+0x94/+0x98` hold the distance still to go
(x, y, z); each tick moves `step = remaining / obj+0xa8` (integer
division) and subtracts it. Then

```
odometer = ftol(odometer + sqrt(step_x² + step_y² + 0.0))   // obj+0x9c
phase    = odometer / 16                                    // obj+0x74
```

and the draw takes `moveSeq[phase mod moveLen]` (`0x468cef`:
`idiv [T+0x50]`). So the walk cycle advances one sequence element per 16
map units moved, not per tick: a unit walks in step whatever its speed.
`obj+0x9c` is not reset when a move starts (the move message `0x6b` does
not write it): it carries over from the idle counter, which is 0 only for
types without an idle animation, so the first move phase can vary. Positions are in 1/256
of a cell (`cell = pos >> 8`, `FUN_004674dd`), so the common
`MoveAnimTime` of 8 × 2 (33 of 62 types, 16 elements) covers exactly one
cell per cycle (INFERRED, arithmetic). The other branch, taken when
`obj+0x24 < 0`, picks 8 phases from the accumulated |x| (`obj+0xa0`) or
|y| (`obj+0xa4`) movement per 25, 26 or 32 units, with ±8 jitter on the
draw position `obj+0x2c/+0x30`. No unit can take it from the network:
`FUN_0046dd6a` loads the type as an unsigned 16-bit value, and heroes
get fixed IDs from `FUN_0046f688`. **INFERRED**: unreachable leftover.

### 1.5 Action durations from server messages

The message loop `FUN_0040dac9` (called before each tick by
`FUN_0048e7d0`; message type = byte `msg+9`, switch tables `0x417d45`
→ `0x417c39`, case = type − 3) sets the action and its length in ticks.
**CONFIRMED**:

| Msg | Action `obj+0x8c` | Duration `obj+0xa8` | Site |
|---|---|---|---|
| 0x6b | 1 move | `msg[+0xd]` (u8, from the server) | `0x41333a` |
| 0x6d | 5 turn | `msg[+0xd]` (u8) | `0x4135ad` |
| 0x71 | 3 attack | `T+0x68` = AttackAnim sequence length | `0x41371f` |
| 0x72 | 7 shoot | `T+0x68` | `0x4139a3` |
| 0x86, 0x8a | 8 cast (caster) | `T+0x68` | `0x415b65`, `0x41604b` |
| 0x86, 0x8b | 1 (new projectile) | `msg[+0xf]` (u16) | `0x415942`, `0x415e64` |
| 0x8c | 1 (new projectile) | 13 | `0x4162b1` |
| 0x6c, 0x6e–0x70 | 6 dying / 0 | see death stage | `0x410ba8`, `0x410c67` |
| speed msg | — | game speed = `msg[+0xa]` → `FUN_00492068` | `0x417b97` |

Attack, shoot and cast therefore last exactly one pass of the attack
sequence; move and turn lengths come from the server.

**Death stage** (`obj+0x184`, case at `0x40f422`; **CONFIRMED**) is
recomputed from hit points `obj+0x104` (signed 16-bit) on these
messages:

| HP | > 0 | ≤ 0 | < −10 | < −20 | < −40 | < −600 |
|---|---|---|---|---|---|---|
| stage | 0 alive | 1 corpse | 2 | 3 | 4 | 5 (not drawn) |

Stages 2–4 are the three bones frames (`stage − 2`, [units](units.md)).
On a change to stage 1 from 0: action 6 for `2 × DyingPhases` ticks of
the `Dying` type (`0x410ba8`), which plays each dying frame for 2 ticks
(the draw uses `obj+0x74 / 2`). Staying at stage 1: action 6 for 4 ticks
(`0x410c67`). Back to stage 0: action 0 (revived). Heroes reload their
sprite (`FUN_0046f688`) on both changes.

**Hero dying** (**CONFIRMED** `FUN_0046f688`, `0x46904b`–`0x469081`):
with action 6 a hero's sprite folder becomes `unarmed` (type 1, `Flip`,
129 frames) or, for flag `obj+0x1b8 & 2` heroes, `mage_st` (type 24,
216 frames). The hero draw always indexes its own sprite `obj+0x1c0`
with the `T`/`T2` formulas and draws nothing when the index is past the
file's end (`0x469070`). Data check: the largest dying/corpse/bones
index is 116 for type 1 and 194 for type 24, inside both files, so
heroes die with the unarmed (or staff-mage) body.

**Default game speed** (**CONFIRMED**): `FUN_0048750d` sets
`app+0x434 = 4` (16 ticks/s, 62 ms); the profile loaders `FUN_004923a7`
and `FUN_00492961` read `GameOptions/Speed` from the profile
`game%d.sav` (`app+0x248`, built by `FUN_0048a922` as `9999 − n`) with
the current value as default; `FUN_004f8233` keeps `DAT_0069d010` in
0..8, else 4. The +/− hotkeys (`FUN_0048a097`, `FUN_00499d05`,
`FUN_00499d2f`) step it by one.

### 1.6 Visibility gates

`obj+0x7c` (`FUN_004206c0` returns it) is a structure's visibility,
recomputed by `FUN_004667ff` from the tile bits `0xc000` under its
cells: 0 if any cell has `0xc000`, else 1 if one has `0x8000`, else 2.
**CONFIRMED**. Structures animate only at 0 (`FUN_004676d2`), flat
structures are drawn only below 2 (`0x408011`), and objects animate
only on cells with `0xc000` (`0x408ba3`). **INFERRED**: `0xc000` =
visible now, `0x8000` = explored, 0 = never seen (fog of war); these are
the "never set in shipped maps" bits 14–15 of [terrain](terrain.md),
set at run time.

### 1.7 Map placement of objects

The objects draw reads its cell byte from the map's `+0x14` layer
(`FUN_00420680` on `view+0x80`, `0x407b0d`), which is `.alm` section 3
([terrain](terrain.md)). Byte 0 = no object, byte `b` = object list
index `b − 1` (= its `ID`; IDs equal their `Object<n>` index for all
192). **CONFIRMED**. Data: in the 216 maps, 83 cells in 9 maps hold
bytes 193–255, past the list (INFERRED: map-pack errors; the game would
read past the array).

Burning trees: 7 objects (`Object1, 4, 7, 10, 13, 16, 19`, files
`<tree>ire<tree>`) are absent from the install and from the
`data/version` manifest, yet 11 of the 216 maps place them (e.g.
`sb_an_waterfall_1_3.alm`, 62 cells). Their file would be loaded by
`FUN_0047edf3` → `FUN_00426da9`, which stops with `FATAL ERROR: can't
load` for a missing file (CONFIRMED for that routine). The 7 matching
dead trees have `FireObject = −2`, which the ambient-sound scan
`FUN_0041d158` counts as burning (INFERRED: fire crackle).

## 2. Layout: unit, monster and hero sprites

Tools: `tools/anim_contact.py` writes `out/contact/anim_<name>_raw.png`
(every frame in file order, index under it, coloured by the block the
layout assigns) and `anim_<name>_layout.png` (one row per block and
direction, labelled with the facings that use it). Specimens:
`hero_swordsman` (`heroes/swordsman`, type 3), `goblin` (type 64),
`dragon` (type 71, `Flip`). Check: `tools/validate_units.py`.

### 2.1 Block order

A file is **action-major, then direction-major**: the stand block, then
for each action block all phases of sprite direction 0, then all of
direction 1, and so on. With `S` stand frames and `R` directions (`S, R`
= 16, 8 without `Flip`, 9, 5 with it), and `B M A D Bn I` = the type's
`MoveBeginPhases`, `MovePhases`, `AttackPhases`, `DyingPhases`,
`BonePhases`, `IdlePhases` (**CONFIRMED**, `FUN_00468640` formulas in
[units](units.md#frame-per-state-fun_00468640); every file checked, §2.5):

| Block | Frames | Index of (direction `i`, phase `p`) | Drawn for |
|---|---|---|---|
| stand | `S` | `i16` (one per stand direction, no phases) | idle without `IdlePhases`, turn (action 5), frozen units |
| move | `(B+M)·R` | `S + i·(B+M) + p` | action 1 with `p = B + MoveAnim[…]`; the `B` begin phases are stored but never drawn |
| attack | `A·R` | `S + (B+M)·R + i·A + p` | actions 3 attack, 7 shoot **and** 8 cast (one shared block), `p = AttackAnim[obj+0x74]` |
| dying | `D·R` | `S + (B+M+A)·R + i·D + p` | action 6, `p = obj+0x74 / 2`; corpse = `p = D − 1` |
| tail | `Bn·R` or `I·R` | `S + (B+M+A+D)·R + i·I + p` | `I ≠ 0`: idle animation; else bones, `p` = death stage − 2 |

The dying and tail (bones) blocks exist only in a file whose type names
itself in `Dying`; other types draw their death from the `Dying` type's
file. With `I ≠ 0` the tail block is an idle animation (dragon, bat,
bee, ghost, succubus, star) and the type has no bones frames.

Specimens (**CONFIRMED** frame counts; block contents checked by eye on
the contact sheets: each block's direction 0 faces the viewer, direction
`R/2` (or 4 with `Flip`) shows the back, every row repeats the same pose
sequence):

| Specimen | Type | S | R | stand | move (B+M) | attack | dying | tail | total |
|---|---|---|---|---|---|---|---|---|---|
| `heroes/swordsman` | 3 | 16 | 8 | 0–15 | 16–95 (2+8) | 96–151 (7) | — | — | 152 |
| `monsters/goblin` | 64 | 16 | 8 | 0–15 | 16–95 (2+8) | 96–175 (10) | 176–223 (6) | 224–247 (3 bones) | 248 |
| `monsters/dragon` | 71 | 9 | 5 | 0–8 | 9–63 (3+8) | 64–98 (7) | 99–128 (6) | 129–163 (7 idle) | 164 |

Worked example (goblin, facing `d = 12`, left): stand frame `(12 − 8) & 15
= 4`; animated direction `((12 − 8) & 14) >> 1 = 2`; attack phase 4 =
`16 + 80 + 2·10 + 4 = 120`; corpse = `176 + 2·6 + 5 = 193`; bones stage 2
(bones stride `IdlePhases = 0`, quirk in [units](units.md)) = `224`.

### 2.2 Directions

The facing `d` (`obj+0x70`, 0..15) counts **clockwise from screen-up**.
**CONFIRMED**: the move message `0x6b` copies its direction byte
(`msg+0xc`) into `obj+0x8d` and takes the step from the tables
`0x6023b0` (dx) / `0x6023f0` (dy), 16 ints each, non-zero only at even
`d`: `d = 0 → (0, −1)`, `2 → (1, −1)`, `4 → (1, 0)`, `6 → (1, 1)`,
`8 → (0, 1)`, `10 → (−1, 1)`, `12 → (−1, 0)`, `14 → (−1, −1)` (map y grows
down the screen). The unit tick sets `obj+0x70 = obj+0x8d` for move,
attack, shoot and cast (`0x46b837`, `0x46bfc4`, `0x46c05f`); a turn
(action 5) steps `obj+0xc4` (0..255) toward `obj+0x8d · 16` by
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

Sprite direction 0 is therefore `d = 8`: the unit faces **down the
screen, toward the viewer** (front view), and sprite directions run
clockwise on screen: 0 down, 2 (i8 1) down-left, 4 (i8 2) left, 8 (i8 4)
up/back, 12 (i8 6) right. **CONFIRMED** (tables above) and matching the
art on all three specimens (stand 0 front, 4 facing left, 8 back, 12
facing right). This corrects the earlier INFERRED "direction 0 seen from
behind" in [units](units.md#facing). Odd facings occur only through
turns; animated states round them down to the even facing.

### 2.3 Mirroring (`Flip = 1`)

Files with `Flip` store only the left half of the circle plus the two
poles: stand `i16` 0..8 (down → left → up) and animated `i8` 0..4.
**CONFIRMED** (`FUN_00468640`, also `0x468f0c`–`0x468f35` for the frozen
case):

| Facings `d` | Stand frame | Animated direction |
|---|---|---|
| 8 (down) … 0 (up) through 12 (left) | `i16` 0..8 as stored | `d` 8–15, 0–1: `i8` 0..4 as stored |
| 1..7 (up-right … down-right) | `16 − i16` (= 7..1), **mirrored** | `d` 2–7: `8 − i8` (= 3..1), **mirrored** |

The draw sets a mirror flag (`[ebp-0x48]`) and passes it as the last
argument to the sprite blit (vtable `+0x14`/`+0x34`, `0x4691c8`,
`0x469215`, `0x469333`), which uses the leftward blitter `FUN_0045a64d`
([sprites](sprites.md)). **Hotspot**: the position does not depend on
the flag: `left = obj.x − ((CenterX − Width/2) + frame_w/2)` is computed
before the flag is read (`0x469136`), so a mirrored frame is flipped in
place inside the same box, about its own centre column; the
`CenterX − Width/2` offset is not negated. **CONFIRMED**. In the data
every `Flip` type has `CenterX = Width/2` (offset 0), so no unit is
shifted by this; the only non-zero x offsets (−1: mainnecro, skeletons,
necromant, druid) are on non-`Flip` types. 11 of 62 types use `Flip`:
unarmed 1, troll 68, troll_good 102, ghost 69, bat 70, dragon 71, bee 73,
squirrel 74, legg 75, turtle 76, star 108.

Projectiles use the same rule with `i16` and 9 stored directions
(§1.3).

### 2.4 Attack events: hit and release frames

The attack, shoot and cast messages set `obj+0x9c = 0` (e.g. `0x41374d`).
Each tick `FUN_0046b5ef` compares `obj+0x9c` with the type's delays
**before** taking the phase from it (`obj+0x74 = obj+0x9c`, then `+1`),
so an event fires on tick `delay` and is drawn on attack phase
`AttackAnim[delay]`. Delays at or past the sequence length never fire.
**CONFIRMED**:

| Action | `ShootDelay` (`T+0x11c`) | `AttackDelay` (`T+0x120`) |
|---|---|---|
| 3 attack (melee) | — | vtable `+0x64` = `FUN_0046d145`: play `Sound[0]` at the unit (volume by distance) |
| 7 shoot | if `Projectile ≠ 0`: `+0x58` = `FUN_0046c28b`, spawn projectile `T.Projectile` (release) | `+0x64`, sound |
| 8 cast | `+0x5c` = `FUN_0046c4f1`, spawn the spell's projectile (`obj+0xac`); spell `0x36` at tick 0 instead | `+0x60` = `FUN_0046d21b`: play sound `500 + obj+0xac` |

Damage is not applied here: hit points arrive from the server in
messages (§1.5), and the server code (`0x4f0000` up) never reads the
`units.reg` table `0x62cb40` or these fields. So `AttackDelay` /
`ShootDelay` are the client's impact-sound and projectile-release frames;
the server's own hit timing is not known yet (open question).

Event phases per type (`phase = AttackAnim[delay]`, from `units.reg`;
**CONFIRMED** arithmetic). "Len" = attack sequence length = action
duration in ticks:

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
| catapult1 26 / catapult2 27 | 18 / 16 | 4 → 2 | 0 → 0 | 5 / 6 |
| unarmed 1, 2; squirrel 74; ghost 69; turtle 76; wolf 103; spider 104; dino 106; star 108 | 14, 11, 10, 12, 10, 12, 6, 14, 14 | 0 → 0 | 0 → 0 | 0 |
| sheep 107 | 0 | (no attack) | | 0 |

Delay 0 fires on the first tick. The catapults have `ShootDelay = 0` with
a projectile, so a shoot action releases on its first tick. Casters with
`Projectile = 0` still spawn the spell projectile on cast (the cast path
does not test `Projectile`).

### 2.5 Check against every file

`tools/validate_units.py` compares each file's frame count with the
layout (**CONFIRMED** on the install): all 90 unit sprite files are
covered: 60 named by `units.reg` types and 30 hero files
(`heroes*/<weapon>/sprites.256`, type from `FUN_0046f688`'s folder
table). Hero files hold `S + (B+M+A+I)·R` frames (no dying or bones:
dying heroes switch to `unarmed`/`mage_st`), except `unarmed` and
`mage_st`, which also hold their dying and bones blocks. Result: 59 of
62 types and 30 of 30 hero files exact. Exceptions:

| File | Frames | Layout | Cause |
|---|---|---|---|
| `humans/swordsman/swordsman` (Unit0, ID 3) | 152 | 152 | matches, but `units.reg` key `File0 ` has a trailing space, so the game never finds it ([reg](reg.md)) |
| `humans/unarmed/sprites` as Unit33 (ID 2, no `Flip`) | 129 | 152 | the file is the `Flip` layout of Unit21 (ID 1); Unit33 indexes up to 207. The non-`Flip` 152-frame body exists only as `heroes*/unarmed_`. Data bug in the game. |
| `monsters/sheep/sprites` (ID 107) | 144 | 136 | see below |

**Sheep** (INFERRED from the art, `_layout` sheet): stand 0–15 and move
16–79 (8 × 8) match. Frames 80–119 are 8 directions × **5** phases
(direction `k` starts at `80 + 5k`: 80 front, 90 left, 100 back, 110
right), and 120–143 are 8 × 3 bones (each starts with a bloody body).
`units.reg` says `DyingPhases = 4`, so the game indexes the dying block
with stride 4: from direction 1 on, dying frames drift into the
neighbouring direction's phases; the corpse is `80 + 4i + 3`; and the
bones (stride `IdlePhases = 0`, so direction 0 only) are frames
112–114, which are whole bodies of direction 6, not bones. The game is
reproduced as is ([CLAUDE.md](../../CLAUDE.md): match quirks).

## Open questions

- Who writes the tile visibility bits `0xc000` at run time (fog update).
  [§1.6](#16-visibility-gates)
- How this install avoids the `FATAL ERROR` for the 11 maps that place
  burning trees (a2mgr redirect, or the files lived in a `.res`).
  [§1.7](#17-map-placement-of-objects)
- Meaning of the `msg[+0xd]`/`msg[+0xf]` durations on the server side
  (how the server derives move time from unit speed).
- When the server applies melee damage and launches projectiles: it does
  not read `units.reg` (`AttackDelay`/`ShootDelay` are client-only,
  [§2.4](#24-attack-events-hit-and-release-frames)); start from the server
  sender of message `0x71`/`0x72` and `world/data/data.bin`.

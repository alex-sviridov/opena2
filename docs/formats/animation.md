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
in [units](units.md). Part 3 ("Timing") states how fast every kind of
animation plays as rules and formulas: the game tick, what advances each
phase counter, where the speeds come from (including the in-process
server's walk and turn times), and which actions loop, hold or return to
idle. Items marked **VERIFY IN GAME** need a check in the running
original.

## 1. Sources

### 1.1 Summary

| Information | Source | Status |
|---|---|---|
| Frames per action, phase lists, per-phase durations | `.reg` registries: `units.reg`, `structures.reg`, `objects.reg`, `projectiles.reg` | CONFIRMED (loaders below) |
| Frame layout inside a sprite file (blocks, directions, mirroring) | hard-coded in each class's draw routine | CONFIRMED |
| Which phase is current | per-object counters advanced by the class's tick routine (vtable `+0x3c`) | CONFIRMED |
| Tick rate | game-speed setting → table in `FUN_00492068` | CONFIRMED |
| Hero sprite folder → unit type | hard-coded string table in `FUN_0046f688` | CONFIRMED |
| Action durations (move, attack, cast, …) | `obj+0xa8` remaining ticks, set when an action starts; projectiles: hard-coded switch; move/turn ticks computed by the in-process server (§3.4) | CONFIRMED |
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
| Projectile | `FUN_00471643` (vtable `0x5d78a0` `+0x3c`) | `obj+0x9c += 1`; default `obj+0x74 = (obj+0x9c / 2) mod Phases`; ID 0x1c/0x1e: hard-coded ping-pong (§4.4); 0x36: `obj+0x9c − 1`; 0x17 and the hit IDs (0x10, 0x14, 0x18, 0x22, 0x2c–0x32, 0x38, 0x3c, 0x3e–0x42): `obj+0x9c` |

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
only on cells with `0xc000` (`0x408ba3`).

**Fog update** (**CONFIRMED**). These are the bits 14–15 of
[terrain](terrain.md), never set in the shipped maps. The client tick
`FUN_0040bdc1` calls `FUN_0040c212` when `clock & 0x1f == 0` (every 32
ticks, `0x40be20`). It clears bit `0x4000` on every tile, then calls
vtable `+0x48` on every object in the view list `view+0x9d0`.

- Structures (`0x5d76d0`) use `FUN_00465e36` directly. Ground and flying
  units (`0x5d7780`, `0x5d7810`) use `FUN_00472f70`, which calls it only while
  the death stage `obj+0x184 < 3`.
- `FUN_00465e36` does nothing unless the sight `s16 obj+0x10a ≠ 0` and
  `FUN_00420610(owner)` accepts the owner (INFERRED: me, or a player who
  shares vision with me).
- It then fills a 41 × 41 mask at `view+0x17e4` through a2mgr
  Ordinal_93. That export calls `FUN_10023720(cellX obj+0x38, cellY
  obj+0x3c, sight, callbacks 0x10033cc0/0x10033c60)` and copies 0x1a44
  bytes.
- For every mask entry `> 0` at `(i, j)` it ORs `0xc000` into the 2 × 2
  tiles at column `x + w/2 − 20 + i` and row `y + h/2 − 20 + j`
  (`w`, `h` = vtable `+0x20`/`+0x24`).

So `0xc000` = seen in the last refresh. `0x8000` alone = seen before,
because the fog update never clears it (explored). 0 = never seen. Animation
therefore freezes for structures and objects outside current sight, and
the frozen state can last up to 32 ticks after a unit leaves.

### 1.7 Map placement of objects

The objects draw reads its cell byte from the map's `+0x14` layer
(`FUN_00420680` on `view+0x80`, `0x407b0d`), which is `.alm` section 3
([terrain](terrain.md)). Byte 0 = no object, byte `b` = object list
index `b − 1` (= its `ID`; IDs equal their `Object<n>` index for all
192). **CONFIRMED**. Data: in the 216 maps, 83 cells in 9 maps hold
bytes 193–255, past the list. All 83 lie outside the window the loader
copies into the layer (rows `8 … h−5`, columns `8 … w−9`,
[terrain](terrain.md)), so the game never reads them. **CONFIRMED**
(loader window + data check over all maps).

Burning trees: 7 objects (`Object1, 4, 7, 10, 13, 16, 19`, files
`<tree>ire<tree>`) are absent from the install and from the
`data/version` manifest, yet 11 of the 216 maps place them (e.g.
`sb_an_waterfall_1_3.alm`, 62 cells). Their file would be loaded by
`FUN_0047edf3` → `FUN_00426da9`, which stops with `FATAL ERROR: can't
load` for a missing file: `AfxMessageBox` then abort (`0x426e0b`–`0x426e42`,
CONFIRMED). a2mgr hooks the file open (`FUN_004ebe03`, `0x4ebeda` →
Ordinal_1, `0x100339be`): it tries `data\patch\<path>`, then
`data\<path>`, then the original lookup, with no substitute for a
missing file. The game survives because all 206 placed cells lie
**outside** the copied window (rows `8 … h−5`, columns `8 … w−9`): the
object layer holds 0 there, so the sprite is never requested
(`FUN_00420720`/`FUN_00420750` load lazily on first draw). **CONFIRMED**
(loader window + data check). The 7 matching
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
the server applies the hit `+0x134` ticks after it sends the attack
([§3.4](#34-where-the-speeds-come-from)).

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

## 3. Timing

Everything in this part is in ticks. §1.4–§1.5 hold the derivations;
this part gives the rules a reimplementation follows.

### 3.1 The game tick

**Clock** (**CONFIRMED** `FUN_0048e7d0`, `0x48e7e4`–`0x48e89f`). The game
has one fixed-step loop driven by `timeGetTime` (import `0x6dc0b0`).
`QueryPerformanceCounter` (`0x5692cb`, `0x584f1e`) and `GetTickCount` are
not used for it; the in-process server (`FUN_004f967a`) reads
`GetTickCount` only to measure its own run time (`+0x1b8`). Each pass:

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

| Rule | Value |
|---|---|
| period | `1000 / rate` ms, integer division (`FUN_00492068`) |
| rate (ticks/s) by speed 0..8 | 8, 10, 12, 14, **16**, 20, 24, 28, 32 (default speed 4) |
| actual rate | `1000 / period`: 8, 10, 12.05, 14.08, 16.13, 20, 24.39, 28.57, 32.26 |
| server ↔ client | the server steps exactly once per client tick, in the same loop: one tick for both |
| catch-up | late ticks run back to back in the same pass, but only until `n` wraps to 0: the re-base drops any older backlog (at most 15 extra ticks after a stall) |
| jitter | the re-base makes each block of 16 ticks run at `X, X+2P, X+3P, …, X+16P`, then tick 0 of the next block runs immediately after (gap 0). The average stays one tick per period |

Changing the speed (`FUN_00492068`; also the network message `0x417b97`)
resets `n = 0` and `base = GetTickCount()` (`0x49213a`–`0x492152`).
INFERRED: `GetTickCount` and `timeGetTime` count the same milliseconds
since boot on Windows, so mixing them only shifts the first tick.

**VERIFY IN GAME:** the speed 0..8 options in the menu map to 8…32
ticks/s (stopwatch a 10-cell walk at two speeds; the ratio should be
`rate₁ / rate₂`). The exe never calls `timeBeginPeriod`, so the tick may
be quantised by the system timer (≈1 or ≈15.6 ms); measure whether speed 8
really gives 32 ticks/s.

### 3.2 What advances each kind of animation

`clock` = view counter `view+0xa88` (+1 per tick). `seq` = the
registry sequence of the kind (one element per tick, §1.2).

| Kind | Phase rule | Loops? | Gate | Status |
|---|---|---|---|---|
| Terrain water (sets 8–11) | set `8 + ((s + (x+1)·y + (clock >> 2)) & 3)`: one frame per **4 ticks**, 4 frames | loops (period 16 ticks) | `DAT_005fb974` (option "Object animations", [lighting §6](../mechanics/lighting.md#6-options)) | CONFIRMED ([terrain](terrain.md)) |
| Structure | `k = seq[obj+0x74]`, `obj+0x74 = (obj+0x74 + 1) mod len` each tick | loops | visible (`obj+0x7c == 0`) and `DAT_005fb974`; else frozen | CONFIRMED `FUN_004676d2` |
| VariableSize bridge | bottom edge `8 + (clock & 3)`: one frame per tick | loops (4 ticks) | — | CONFIRMED `FUN_00467bdb` |
| Object (trees, …) | `Index + seq[(clock + X + X·Y) mod len]` | loops | cell bits `0xc000` both set (else frame `Index`); `DAT_005fb974` off: frame **0** of the file (`0x408d3c`) | CONFIRMED `0x408b24` |
| Projectile (default) | `(age / 2) mod Phases`, `age` +1 per tick: one frame per **2 ticks** | loops for the flight | — | CONFIRMED `FUN_00471643` |
| Projectile 0x1c/0x1e | `age − 1` = 0…12 indexes 4 3 2 1 0 1 2 1 0 1 2 3 4 (table `0x471fba`), other ages keep the value | once (13 ticks) | — | CONFIRMED |
| Projectile 0x17 and hit IDs | `age` (0x36: `age − 1`), one frame per tick | plays once (INFERRED: the object is removed when its time ends) | — | CONFIRMED phase rule |
| Unit idle (`IdlePhases ≠ 0`) | `idleSeq[(++obj+0x9c) mod idleLen]` | loops | — | CONFIRMED `0x46b6ab` |
| Unit stand (`IdlePhases = 0`) | stand frame, counter reset to 0 every tick | — | — | CONFIRMED `0x46b6db` |
| Unit move | `moveSeq[(odometer / 16) mod moveLen]`, distance-driven (§3.3) | loops | — | CONFIRMED |
| Unit attack / shoot / cast | `attackSeq[t]`, `t` = 0, 1, … one per tick | once, then idle | — | CONFIRMED |
| Unit turn | stand frame of the current facing, facing stepped per tick | once, then idle | — | CONFIRMED |
| Unit dying | dying phase `t / 2`, `t` = 0 … `2D − 1`: one frame per **2 ticks** | once, then **holds** the corpse | — | CONFIRMED |

Worked examples at the default 16.13 ticks/s: water changes frame every
248 ms (a 4-frame cycle ≈ 1 s); a projectile with 6 phases loops every
12 ticks ≈ 0.74 s; a 6-phase death takes 12 ticks ≈ 0.74 s; the goblin's
attack (`Len` 10) takes 0.62 s.

### 3.3 Unit actions: duration, then back to idle

**Rule** (**CONFIRMED** `FUN_0046b5ef`, `0x46b647`–`0x46b724` and
`0x46c1c5`–`0x46c1e4`): a message sets the action `obj+0x8c` and its
length `obj+0xa8` (§1.5) during `read_messages`, before the tick of the
same pass. Each tick with `obj+0xa8 > 0` runs the action's case, copies
the action to the draw state `obj+0x78` and decrements `obj+0xa8`. So an
action of length `N` is drawn on exactly `N` ticks. On the first tick
with `obj+0xa8 == 0` the state becomes **0 (idle)** whatever the action
was. No action repeats by itself: walking, attacking or casting again
needs a new server message.

| Action | Length `N` (ticks) | Phases shown | After the last tick |
|---|---|---|---|
| 0 idle | — | idle loop or stand | — |
| 1 move | `msg[+0xd]` = server ticks for one cell (§3.4) | distance-driven walk cycle | idle, unless the next `0x6b` arrives in the same pass |
| 5 turn | `msg[+0xd]` = server turn ticks (§3.4) | stand frame of the stepping facing | idle |
| 3 attack, 7 shoot, 8 cast | `AttackAnim` sequence length (`T+0x68`) | `AttackAnim[0 … N−1]`, events at `AttackDelay`/`ShootDelay` (§2.4) | idle |
| 6 dying | `2 · DyingPhases` of the `Dying` type | dying `0 … D−1`, two ticks each | idle state + death stage 1 = **corpse** frame `D − 1` (held); later bones by HP (§1.5) |

Idle after an action: with `IdlePhases ≠ 0` (dragon, bat, bee, ghost,
succubus, star) the idle counter continues from the action's last value
(`obj+0x9c` is not reset), so the idle loop starts at an arbitrary
phase; otherwise the stand frame is shown and the counter is zeroed each
tick. **CONFIRMED** (`0x46b6ab`–`0x46b6f2`).

Walk continuity: the server sends one `0x6b` per cell (§3.4). The
odometer `obj+0x9c` is not reset between cells, so a unit that keeps
walking continues its cycle. **CONFIRMED** (no write to `+0x9c` on
`0x6b`). INFERRED: when the server's next step arrives one pass late, the
unit shows one tick of stand/idle between cells. **VERIFY IN GAME:**
watch a long straight walk for a one-frame "stand" flicker at cell
borders.

Corpse re-hit quirk (**CONFIRMED** code path, `0x410c67`): a death-stage
message that leaves the stage at 1 sets action 6 for 4 ticks **without**
resetting `obj+0x9c`. For a type without an idle animation the counter
was zeroed by the idle ticks, so the unit replays dying phases 0, 0, 1, 1
and then lies down again (a "twitch"). With an idle animation the counter
is arbitrary and the draw (`0x468e8f`, no clamp) indexes past the dying
block. **VERIFY IN GAME:** hit a fresh corpse (HP between 0 and −10)
with an area spell and watch for the twitch.

### 3.4 Where the speeds come from

The client never computes a walk or turn speed: it plays what the server
sends. The server's numbers are:

**Walk: ticks per cell** (**CONFIRMED** `FUN_00563185`, sender
`FUN_00519b30` → `FUN_0050cd3c` writes `msg[+0xd] = mover+0xaa`, and the
server marks the unit busy until `tick + msg[+0xd]`, `unit+0x138`):

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

Terrain costs (**CONFIRMED** `FUN_0055dd41` reads
`world/data/map.reg`, section `Terrain`, keys `Cost<name>` with
defaults, into `map+0x54147…`; values are this install's file):

| Terrain | Land | Grass | Flowers | Sand | Cracked | Stones | Savanna | Mountain | Water | Road |
|---|---|---|---|---|---|---|---|---|---|---|
| `Cost` (file) | 8 | 8 | 8 | 14 | 6 | 12 | 8 | 16 | 8 | 6 |
| default in code | 8 | 8 | 9 | 14 | 6 | 12 | 11 | 16 | 8 | 6 |

`SpeedMultiplier` (`Path Finding`, default 8) = 8 in the file. With cost 8
the multiplier cancels: on flat grass `v = base`.

**Per-cell cost** (**CONFIRMED** `FUN_0055e616` → `FUN_0055e93d`). At map
load the server fills three 256 × 256 byte arrays, indexed `(y << 8) + x`:
`cost` (`map+0`, read by `FUN_00564137`/`FUN_00569a40`), `flags`
(`map+0x10000`) and a per-cell signed byte at `map+0x944f4` (the one the
slope term reads). From the tile word `v` (terrain [tiles](terrain.md),
`v & 0x3ff`):

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

Terrain pairs `(A, B)` per tile set (`FUN_0055dd41`): 0 Grass/Land,
1 Cracked/Land, 2 Sand/Land, 3 Savanna/Land, 4 Stones/Land,
5 Cracked/Stones, 6 Flowers/Savanna, 7 Mountain/Stones, 12 Road/Land
(type numbers 1 Land … 10 Road as in the cost table). Blend codes:

| strip \ row | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 2 | 3 | 2 | 4 | 3 | 4 | 2 | 2 | 2 | 2 | 4 | 4 | 4 | 4 |
| 1 | 3 | 5 | 3 | 3 | 1 | 3 | 2 | 4 | 2 | 2 | 4 | 2 | 4 | 4 |
| 2 | 2 | 3 | 2 | 4 | 3 | 4 | 2 | 4 | 2 | 2 | 4 | 2 | 4 | 4 |
| 3 | 5 | 5 | 5 | 5 | 5 | 5 | 2 | 2 | 2 | 2 | 4 | 4 | 4 | 4 |

INFERRED: the map object passed in has the client layout's `+0xc` tiles
but its `+0x10` byte marks blocked cells (flag 5, e.g. objects) and its
`+0x14` byte is the height copied to `map+0x944f4` (the slope term
clamps differences to ±32, as for heights). Flag `0x20` (tested by
`FUN_00564137`) is set elsewhere (not traced).

Worked example (flat grass, `base` 18 = a hero with the default `+0x86 = 30`: `12 + 30/5`): orthogonal `v = 18`,
`ceil(256/18) = 15` ticks per cell = 0.93 s at 16.13 ticks/s; diagonal
`step = trunc(18 · 0.707) = 12`, `ceil(256/12) = 22` ticks. On road
(cost 6): `v = 18·8/6 = 24`, 11 ticks. On sand (14): `v = 10`, 26 ticks.

**Walk animation speed** follows from §1.4: one sequence element per 16
units moved, so the common `MoveAnimTime` 8 × 2 (16 elements) plays one
full cycle per orthogonal cell, whatever `v` is. Frames per second =
`rate · v / 32` for those types; a diagonal cell (362 units) plays 1.41
cycles. **CONFIRMED** arithmetic from the two formulas.

**Speed stat** `unit+0x8c` (server):

| Source | Rule | Status |
|---|---|---|
| hero defaults | `FUN_00518863`: `+0x8c = 10`, turn rate `mover+0xa = 8`, attack bytes `+0x134 = 8`, `+0x135 = 4` | CONFIRMED |
| hero recompute | `FUN_0051d2a7` (`0x51d6b4`–`0x51d7fa`): `s = A` if `A < 12` else `12 + A/5`, with `A = s16 +0x86`; `+10` when `+0xe` is 0x13 or 0x15; when load `+0x90 ≥` capacity `+0x92`: `s −= load / capacity`, minimum 6; then the effect block `+0xd4` adds its speed delta (`FUN_0051b023`) | CONFIRMED code; INFERRED: `+0x86` is the hero's Reaction/Dexterity stat, `+0xe` a mount/class id |
| monsters | written through the stat block virtual `FUN_0051aed6` (`+0x8c = block+4`) | CONFIRMED write; values from `world/data/data.bin` (not decoded) |
| effects (Haste/Slow, …) | effect kind 17 (`FUN_00527122` case 0x11, `0x527757`): `delta = strength · effect+0x40`; heroes add it to the modifier `+0xd8` (recomputed), others to `+0x8c` directly | CONFIRMED path; which spells use kind 17 and their magnitudes are data (open) |

**Spell projectile flight time** (**CONFIRMED** `FUN_0052365f` →
`FUN_0050ce4e`/`FUN_0050cf32`, message `0x86` with a target object or
`0x8b` with a target point). The server writes `msg[+0xc] = 2·spell + 8`
(projectile ID), `msg[+0xd]` = the target's object ID (u16), and
`msg[+0xf]` = flight ticks (u16), which the client copies to the new
projectile's `obj+0xa8` (§1.5):

```
if spell.param[5] == 2:                     // missile-type spell
    ticks = trunc(sqrt(dx² + dy²)) / spell.param[7]   // FUN_005206ea; positions = cell·256 + fraction
    if spell == 10 (lightning): ticks = 5      // the code also tests 11, which never gets here
else:
    ticks = 0
```

`spell.param[k]` is the spell template's parameter array (`FUN_00421110(k)`
on `template+0x3c+8`), loaded from `world/data/data.bin` (not decoded), so
`param[7]` is a missile speed in 1/256 cell per tick. Spell 11 (the
`spell+8` byte `0x0b`) takes another path (`FUN_005238cb`) and sends no
`0x86`. Arrows and catapult shots are timed by the client (`dist / 200`,
§1.4), not by this message.

**Turn: ticks** (**CONFIRMED** `FUN_00560444`, sender `FUN_00519b30`
with type `0x6d`, `msg[+0xd] = mover+0xa4`): angles are bytes (256 = full
circle). `diff = |target − current|`, folded to `≤ 128`. If the first
check finds `diff < 33` (or `256 − diff < 33`, within ~45°) the facing
snaps and the turn lasts **1** tick; otherwise `ticks = ceil(diff /
turn_rate)` with `turn_rate = mover+0xa` (8 for heroes). Example: a hero
turning 180° takes `128 / 8 = 16` ticks ≈ 1 s. The client spreads the
change evenly: `facing256 += (target − facing256) / ticks_left` per tick
(§2.2).

**Attack cadence and hit time** (**CONFIRMED** `FUN_00518d2f`, the
server unit update; order `unit+0x54` = 3 attack, `0xd` cast at a unit,
`0xe` cast at a point; phase `unit+0x58`, countdown byte `unit+0x6c`):

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

So the server applies melee damage `+0x134` ticks after it sends `0x71`.
A ranged hit lands later by the arrow's flight time `(dist·256 + 128)/200`,
which matches the client's own arrow flight `dist / 200` (§1.4). Spell
effects land `+0x134` ticks after the cast message. One attack takes
`+0x134 + extra + +0x135 + rand(0..3) + hero_delay` ticks, plus one tick
for the phase-0 pass. INFERRED: one call per server tick.

The `0x71`/`0x72` message also sets `unit+0x138 = tick + +0x134 +
+0x135` (`FUN_0050cd3c`/`FUN_0050cdcd`). For melee that sum is also in
`msg[+0xd]`, which the client ignores: it plays the `AttackAnim` length
(§1.5). Heroes' `+0x134`/`+0x135` come from the equipped weapon
(`FUN_00532dee`: item parameters 12 and 13, kept when −1); defaults are
8 and 4 (`FUN_00518863`). Monsters' values come from data (open). With
the client's `AttackDelay` sound and the server's hit on different ticks,
the impact sound can come before or after the HP change. For example, a
hero swordsman's sound plays at tick 4 and the damage lands at tick 8.

INFERRED: if the cycle is longer than the client animation the unit
stands for the difference between swings; if shorter, the next `0x71`
restarts the animation at phase 0 (the handler zeroes `+0x9c`).
**VERIFY IN GAME:** a hero swordsman (`AttackAnim` 11 ticks, default
cycle 8 + 4 + 0..3 + 1 = 13–16 ticks, plus `hero_delay`) should show at
least 2–5 stand frames between swings. The target's HP bar should drop about half a second
after the swing starts (tick 8), after the clang (tick 4).

### 3.5 Summary of loop, once and hold

| Animation | Behaviour |
|---|---|
| unit idle animation, stand | loops forever while idle |
| unit walk | loops (by distance) while move messages keep coming; stand when they stop |
| unit attack, shoot, cast, turn | play once (one pass of the sequence or the turn), then idle |
| unit dying | plays once (2 ticks per frame), then holds the corpse frame; bones frames replace it as HP falls (death stage 2–4), nothing at stage 5 |
| structure, object, water, bridge edge | loop forever (while visible / animation on) |
| projectile in flight | loops `Phases` (2 ticks per frame) until the flight time ends |
| projectile hit effects (0x17, hit IDs) | play once, one frame per tick |

### 3.6 VERIFY IN GAME (collected)

1. Speed setting → ticks/s table (§3.1), and the effective rate at
   speed 8 given the system timer.
2. One stand frame or none at cell borders on a long walk (§3.3).
3. Corpse "twitch" when a fresh corpse is hit again (§3.3).
4. A hero swordsman shows at least 2–5 stand frames between swings, and the
   target's HP drops after the clang (§3.4).
5. Walk times: a hero crossing 10 grass cells vs 10 road cells should
   take about `15 : 11` (with base 18; measure the hero's speed stat first).
6. Haste/Slow change walk time but not the attack animation length
   (client `AttackAnim` is fixed; only the server cadence could change).
7. Water ripples every ~¼ s at the default speed, and water, buildings
   and trees stop when Options → "Object animations" is off; "Dynamic
   lighting" switches off with it.

## 4. Implementation

`allods2/anim/` gives every animated class the same API (`base.py`):
`aset.actions` (name → `Action`: per-tick phases, loop / once / hold,
events), `aset.frame_at(action, facing, tick)` → `FrameRef` (frame,
mirror flag, anchor, or the pieces of a composite frame),
`aset.draw(canvas, ref, x, y)` with the game's blit modes, and
`aset.preview_clip`. `anim.load_set("<kind>:<id>", data_dir)` loads any
of them. Time is in ticks (`tick_at_ms` converts at a game speed).
Previews: `python -m allods2 anim preview KEY DEST` (`allods2/anim_preview.py`):
one GIF per action and facing at the tick period on a checkerboard, a
cross on the anchor, plus a still grid `out/contact/anim_<name>_grid.png`.
Data check (**CONFIRMED**): every unit set, all 179 structures, all 31
projectiles and 185 of 192 objects stay inside their files; the
exceptions are Unit33 (§2.5) and the 7 burning trees whose files are
missing (§1.7).

### 4.1 Units, monsters, heroes

`load_unit_set(key)` (key = units.reg ID, hero folder `heroes/swordsman`,
or unit file/folder `monsters/goblin`) returns the actions the type has
(`stand`, `idle`, `move`, `attack` shared by shoot and cast, `dying`,
`corpse`, `bones1..3`); `frame_at` follows §3.5. `move` is
distance-driven (§1.4) and takes the server's ticks per cell. The walk
preview scrolls the checkerboard by the real displacement; the anchor
cross turns red on the impact tick and yellow on the release tick.

Choices and notes:

- Death frames (INFERRED) are placed with the unit's own type `T`. Every type and its
  `Dying` type have equal `CenterX/Y`, `Width`, `Height`, so this cannot
  be observed.
- Hero sprites use the player tables built from `humans/human.pal`, like
  every `Palette = 0` type (**CONFIRMED**, [palettes §4](palettes.md)): the
  `heroes*/human.pal` files are never opened.
- Not modelled: the turn action (stand frame of a stepping facing, §2.2),
  the corpse re-hit twitch (§3.3), and the `obj+0x24 < 0` walk branch.

### 4.2 Structures and bridges

**Placement** (**CONFIRMED** `FUN_004669e8`): the view draw calls the
structure once per screen cell with the cell's column and row. The local
column is `c = cell x − obj+0x38`; the routine draws the pieces of that
column bottom-up, 32 px apart, from row `(cell y − obj+0x3c) + FH − TH`
(all rows when the local row is 0, one row otherwise), at
`(32·x, 32·y − obj+0x10 − obj+0x6c)`. So the file is a picture of
`W × FH` pieces of 32 × 32 whose bottom `TH` rows cover the footprint,
and piece `(col, row)` sits at `(32·col, 32·(row − (FH − TH)))` from the
footprint's top-left corner. Pieces use the file's own palette (`+0x18`),
the `b.256` piece at 50 % with the main table when Smoothing is on.

Frame of piece `cell = col + row·W` (§1.3): destroyed → `count − W·FH +
cell`; `k = seq[obj+0x74] ≠ 0` and mask char not `-` → `W·FH + (k−1)·A +`
rank of the cell among the animated ones; else `cell`. Worked example,
Church (ID 11, `W = 4`, `FH = 5`, mask `--------++----------`, `A = 2`,
6 phases of 4 ticks): cell 9 at `k = 3` draws `20 + 2·2 + 1 = 25`.

`StructureSet.frame_at("intact", 0, t, start=0, animate=True)` uses
`seq[(start + t) mod len]`; `animate=False` is the frozen state (not
visible, or "Object animations" off). The 2-phase records without
`AnimTime` (inns, towers, castle, …) have an empty sequence and never
animate.

**Bridges** (**CONFIRMED**): the map loader (`0x4abf1b`) builds structure
ID `0x21` (vertical wooden bridge) as class `0x5d8c50` and ID `0x25`
(horizontal) as `0x5d8ca8`, with the width and height in cells from the
map record (`+0xa`, `+0xc`, stored at `obj+0x144`/`+0x148`). Piece by
local cell `(x, y)`, `w × h`:

| Cell | ID 0x21 (`FUN_004679f3`) | ID 0x25 (`FUN_00467bdb`) |
|---|---|---|
| top-left, top-right | 0, 2 | 0, 3 |
| top edge | 1 | `1 + (x & 1)` |
| bottom-left, bottom-right | 6, 8 | 7, 13 |
| bottom edge | 7 | `x` odd: 12; even: `8 + (clock & 3)` |
| left, right edge | 3, 5 | 4, 6 |
| inside | 4 | 5 |

Each piece is drawn at `(32·x, 32·y)` like a 1 × 1 structure. The ID 0x25
bottom edge animates one frame per tick from the view clock, with no
visibility or option gate.

### 4.3 Objects

**Placement** (**CONFIRMED** `0x40924f`–`0x4092d3`): the anchor is the cell
centre, `left = 32·X + 16 − ((CenterX − Width/2) + w/2)`, `top = 32·Y +
16 − ((CenterY − Height/2) + h/2) − relief`, with the object's own record
even when its dead object's frame is drawn. Blit `+0x14` with the file's
table, the `b.256` overlay at 50 % (`+0x34`) when Smoothing is on.

**Frame** (**CONFIRMED** `0x408b24`–`0x408d46`), in order: cell fully
visible and a sequence → `Index + seq[(clock + X + X·Y) mod len]`; tile bit
`0x2000` and `DeadObject ≠ −1` → frame 0 of the dead object's `File`
(its `Index` is ignored); else `Index`; finally, with "Object animations"
off, frame **0** of the file whatever was chosen (quirk: an object with
`Index ≠ 0` then shows another object's picture). Worked example, Pine 1
(ID 0, 7 phases of 4 ticks) at cell (10, 3), clock 5: `(5 + 10 + 30) mod
28 = 17` → `seq[17] = 4`.

`ObjectSet` actions: `anim`, `still`, `dead`.

### 4.4 Projectiles and spell effects

**Placement** (**CONFIRMED** `FUN_00471fee`): `left = x − Width/2`, `top =
y − Height/2 − z − obj+0x10`, with the record's `Width`/`Height` (default
64), not the frame size.

**Age** (**CONFIRMED**): `obj+0x9c` is incremented at the start of each
tick (`0x47187f`), before the phase rule. Projectiles a unit fires
(`FUN_0046c28b`, `FUN_0046c4f1`) start at 0 (`0x46c493`, `0x46c935`), so
their first drawn tick has age 1; the ones server messages create (0x86
`0x415911`, 0x8b `0x415e33`, 0x8c `0x41628c`) start at −1. The tick returns
"remove" when `obj+0xa8` (ticks left) is 0 on entry (`0x4716bd`).

**Phase by ID** (tick switch `0x4718c7`, table `0x471f84`):

| IDs | Phase `obj+0x74` | Notes |
|---|---|---|
| default | `(age / 2) mod Phases` | moves toward the target each tick |
| 0x0d (fire explosion) | default | on the 3 × 3 cells around it: at age 4 queues (list `view+0xa94`) each cell without bit `0x2000` that holds an object with a `DeadObject` or is water (sets 8–11); at age 8 sets bit `0x2000` (burnt ground) except on water cells without an object (`0x471a32`–`0x471ce4`) |
| 0x17 (blizzard hail) | `age` | at age 8 plays sound `0x20b` |
| 0x1c (lightning), 0x1e (prismatic) | `age − 1` = 0…12 → 4 3 2 1 0 1 2 1 0 1 2 3 4 (`0x471fba`); other ages keep the value | lifetime 13 |
| 0x36 (teleport) | `age − 1` | lifetime 21 |
| 0x10 0x14 0x18 0x22 0x2c 0x2e 0x30 0x32 0x3e 0x40 0x42 | `age` | follow the target; add effect `ID << 16 | 0xffff` to it |
| 0x38, 0x3c | `age` | follow the target; set effect `ID << 16 | 0x20` |

**Draw** (`FUN_00471fee`; switch on `ID − 7`, table `0x472530`): frame
`phase + Phases·d` with `d = (facing − 8) & 15`, folded to `16 − d`
mirrored when `Flip` and `d > 8`; just `phase` when `RotationPhases == 1`.
Then by ID:

| ID | Draw |
|---|---|
| 7 | the screen lens below, no sprite |
| 0x17 | `phase < 8`: frame 8 at `top − (28 − 4·phase)` (a stone falling 4 px per tick); else frame `phase − 8` |
| 0x1c | frame `phase` of its own sprite at every point of the list `obj+0x11c` (`(x − 8, y − 8)`) |
| 0x1e | frame `phase + 5·colour` (point byte +6) at every list point |
| 0x36 | frame `phase`, no direction |
| 0x38 (heal) | nothing |
| others, `A16 = 1` | `.16a` alpha blit (`+0x18`) with the file's palette: `src·(a+1)/16 + dst·(15−a)/16` ([sprites](sprites.md)) |
| others, `Palette ≠ 0` | opaque (`+0x18`, own table), then the `b.256` overlay at 50 % with its own all-zero palette = darkens by half ([sprites](sprites.md)) |
| others, `Palette = 0` | opaque `+0x14` with `projectiles.pal` |

So spell effects use **no additive blending**: all of them are `.16a`
alpha sprites, plus the lens and the 50 % shadow overlays. IDs 10 and 12
(firebolt, fireball) also draw a trail of up to 6 points with
`smoke0|1` frame = trail index (`0x4723a4`–`0x4724d5`).

`ProjectileSet` has one action, `flight` (default rule, loops) or
`effect` (the special rules, once). `frame_at(action, facing, t,
age0=None)`: `age0` defaults to 0 for IDs below 8 and −1 for spell IDs
(INFERRED default; the spawner decides). Previews play one cycle of
`flight`, and `effect` for its fixed lifetime or `Phases` ticks (the
server's lifetimes come from data, §3.4).

### 4.5 The screen lens (projectile 7)

**CONFIRMED** (`FUN_004adfc0(R = 20, d = 16)` at `0x479d9d`, table
`FUN_004ae0df`, draw `FUN_004ae2cb`; global `0x62b61c`): bat and succubus
missiles (unit `Projectile = 7`) bend the picture behind them. The CRT
calls are `atan` (`0x58ede4`, `fpatan`) and `sin` (`0x58eb74`, `fsin`):

```
n    = trunc(sqrt(R² − (R − d)²))                 = trunc(sqrt(384)) = 19
k(0) = 1;   k(r) = r / (R · sin(atan(r / (R − d))))  = sqrt(r² + 16) / 20
T[i][j] = (trunc(i·k(r) + 0.5), trunc(j·k(r) + 0.5)),  r = trunc(sqrt(i² + j²) + 0.5),
          or (i, j) when r ≥ n
draw: for i = n−1 … 0, j = n−1 … 0, for (a, b) in (+,+), (+,−), (−,+), (−,−):
          screen[y + b·j][x + a·i] = screen[y + b·T[i][j].y][x + a·T[i][j].x]
          (in place; skipped when either pixel is outside the clip rectangle)
```

The anchor is `(x, y − z − obj+0x10)`. `k < 1`, so every pixel takes one
nearer the centre: a magnifying bulge 19 px in radius. Worked example:
`T[18][0]`: `r = 18`, `k = sqrt(340)/20 = 0.922`, `(17, 0)`; the pixel 18 px
right of the centre shows the one 17 px right. `allods2/anim/lens.py`.

### 4.6 Burning cells

**CONFIRMED** (list `view+0xa94`; update `FUN_0040c199`; draws `0x40892e`,
`0x4094ad`; light [lighting §3](../mechanics/lighting.md#3-light-map-view--0xa8-confirmed)).
Fire and steam on map cells are not objects or projectiles but entries
`{cell x | y << 8, counter}` of one list:

| Step | Rule |
|---|---|
| added | by the fire explosion (projectile 0x0d at age 4: the 3 × 3 cells with a burnable object or water, §4.4) and by the server message handled at `0x4155cd` (`FUN_0041dfd3`: cells whose object has a `DeadObject`) |
| counter | +1 per call of `FUN_0040b35f`: once per view draw (`0x40aeaa`) and once per view message 0x40e / 0x40f (`0x40c3fe`, `0x40c477`); the entry is removed when it reaches 22 |
| steam | water cell (tile set 8–11) with counter < 18: projectile 8 (`steam`, 9 frames `.16a`), frame `counter >> 1`, at `left = 32·X + 16 − Width/2`, `top = 32·Y + 16 − relief − Height/2` (record 64 × 96) |
| fire | cell with an object, after the object: projectile 0x0f (`firewall`, 11 frames `.16a`), frame `counter >> 1`, same placement (record 128 × 128) |
| light | radius 1 at the cell, value `36 24 12 0 12 0 12 0 20 28 36` by `counter >> 1` |

INFERRED: with one view draw per game tick the fire burns 22 ticks
(1.4 s at the default speed); mouse messages to the view make it burn
faster. **VERIFY IN GAME**: a fireball on a forest; the flames should
last about 1.4 s and look shorter while the mouse moves.

### 4.7 Terrain water

**CONFIRMED** ([terrain](terrain.md), `FUN_00404eb5`): only tile sets 8–11
animate; a water cell of set `s` at absolute cell `(x, y)` draws set
`8 + ((s + (x+1)·y + (clock >> 2)) & 3)` (one frame per 4 ticks, a 16-tick
loop, neighbouring cells out of step), frozen at set 8 when "Object
animations" is off. There is no lava or other animated terrain in Allods 2
(13 sets, none else cycles). `WaterSet` draws a window of map cells;
`load_water_set("auto")` picks the first map window in name order that is
40–70 % water (shore and open water).

### 4.8 Cursors

**CONFIRMED** (table `FUN_00480f17`; class `FUN_00480d20`, vtable
`0x5d7a90`; mouse manager object `0x60e6c0`: set `FUN_004289d3`, step and
draw `FUN_00428c10`, `0x4291f4`). Each cursor is `(file, hot x, hot y,
period ms)`; the class stores the sprite (`+4`), hot spot (`+8`, `+0xc`),
frame count (`+0x10`) and period (`+0x14`). Files ending `.16a` load with a
FADE16 table, the others as `.256` with `(1, 1, 0)`. The manager keeps the
frame at `+0x24` and the last step time at `+0x30`:

```
now = timeGetTime()
if now − last > period:  last = now;  frame = (frame + 1) mod count
draw frame (+0x18, own table) at (mouse x − hot x, mouse y − hot y)
```

So a cursor steps on the first poll more than `period` ms after the
previous step (`cursor_frame` models a 1 ms poll: one frame per
`period + 1` ms); setting a cursor resets the frame to 0. Period
2000000000 = still.

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
| arrow0–7 (map scroll, by direction) | 16,6 · 23,9 · 26,16 · 23,24 · 16,28 · 8,24 · 5,16 · 8,9 | still | 1 |
| sdefault (`.16a`), smove, sattack, sdefend, spatrol, scast (`.256`) | 1,1 / 0,0 | still | 1 |
| cantput, town | 38,36 / 16,16 | still | 1 |

The loose `cursors/{attack,cast,defend,move,patrol,pickup}.256` and
`d/l/ld/lu/r/rd/ru/u.256` files are never named by the exe (no string),
so they are unused leftovers; four of them are truncated.

### 4.9 Other UI sequences

Multi-frame UI sprites (all `.16a`, FADE16), **CONFIRMED** loaders, timing
**not traced** (previews use 100 ms per frame and are marked untimed):

| Sprite | Frames | Loader |
|---|---|---|
| `interface/chrgen/cube` (character creation dice) | 16 | `FUN_004313db` (`+0x8c`) |
| `interface/chrgen/PreCreate/Blind` | 15 | `FUN_004364c3` |
| `Global.Map/MissionFlag`, `YourFlag` | 9, 4 | `FUN_00474320` |
| `interface/inn/<unit>/sprites` (hire previews) | 8 (unit26: 5) | not found: no path string in the exe or a2mgr |

`FUN_00474320` also names `Global.Map/Flag1`, `Flag`, `Cross` and
`FlagOnMap`, which are absent from this install.

### 4.10 Survey: everything that animates

| Class | Metadata | Layout | Timing | Draw | API |
|---|---|---|---|---|---|
| units, monsters, heroes | `units.reg` | §2 | ticks, distance for walk (§3) | opaque + 50 % overlay, mirrored | `UnitSet` |
| structures | `structures.reg` | piece grid, `AnimMask` | `AnimTime/Frame` per tick | opaque + 50 % overlay | `StructureSet` |
| bridges | map record size | 9 / 14 pieces | bottom edge `clock & 3` | opaque | `BridgeSet` |
| map objects | `objects.reg` | `Index + seq` | `clock + X + X·Y` | opaque + 50 % overlay | `ObjectSet` |
| projectiles, spell effects | `projectiles.reg` + per-ID code | `phase + Phases·dir` | `age / 2`, ping-pong, `age` (§4.4) | `.16a` alpha, opaque, 50 % shadow, screen lens; no additive blend | `ProjectileSet` |
| burning cells | list `view+0xa94` | firewall / steam frames | counter per view draw, 22 | `.16a` alpha | `BurningSet` |
| water | tile sets 8–11 | 4 sets | `clock >> 2` | tile copy | `WaterSet` |
| cursors | exe table | `.16a` / `.256` | ms, `timeGetTime` | alpha / opaque | `CursorSet` |
| other UI | exe loaders | `.16a` | not traced | alpha | `UiSequenceSet` |

`python -m allods2 anim preview-all DEST` writes
`DEST/<class>/<name>/<action>[_dNN].gif` and `grid.png` for every set
(`anim.all_keys`).

## Open questions

- The sight mask algorithm (line of sight, radius shape): a2mgr
  Ordinal_93 → `FUN_10023720` with callbacks `0x10033cc0`/`0x10033c60`;
  and what the original exe did before a2mgr replaced it.
  [§1.6](#16-visibility-gates)
- Data-driven speed values: monster speed `+0x8c`, turn rate
  `mover+0xa`, attack bytes `+0x134/+0x135` for monsters, the
  `template+0x44` speed override, spell `param[5]`/`param[7]` (missile
  type and speed for flight time), and which spells create effect kind 17
  (Haste/Slow) with what strength; all from `world/data/data.bin`
  ([§3.4](#34-where-the-speeds-come-from); `FUN_0051aed6`,
  `FUN_00527122`).
- Server map fill `FUN_0055e616`: which layers its input `+0x10`/`+0x14`
  are, and who sets cell flag `0x20` (`FUN_00564137` path).
  [§3.4](#34-where-the-speeds-come-from)
- Frame timing of the UI sequences (chrgen cube, PreCreate Blind,
  world-map flags) and the loader of the inn unit pictures
  (`FUN_004313db`, `FUN_004364c3`, `FUN_00474320`). [§4.9](#49-other-ui-sequences)
- What `weapon+0x4a` and `unit+0x86` are in the hero recovery delay
  (INFERRED: weapon speed and a hero stat; [§3.4](#34-where-the-speeds-come-from)).

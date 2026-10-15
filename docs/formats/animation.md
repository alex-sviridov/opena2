# Animation: how sprite frames become animations

Binary: `allods2.exe` English 1.30, sha256
`2a8bdf9dc69276cc8d4fee561a7473a6b0f709cf9758abddaf2cd3b1fdfdfe43`.
Addresses were read in REA (Ghidra 12.1.4) and in an `objdump` listing.
Data checks use the English install in `samples/` (paths compared
case-insensitively, as on Windows).

Part 1 ("Sources") records **where** each piece of animation information
comes from. Part 2 (the per-kind frame and timing rules, written as a
spec to implement) is not written yet. Unit frame layout and draw are
already specified in [units](units.md).

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
14 pieces.

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
| 1 move | from the step distance; formula not yet read in full (`FUN_0046b5ef` case 1) | |
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

**INFERRED**: unit action lengths (`obj+0xa8` for units) arrive from the
server with each action (written by the message handlers around
`FUN_00464f02`); not traced yet.

## Open questions

- The move-phase formula in `FUN_0046b5ef` case 1: the `obj+0x24 < 0`
  branch steps 8 phases per 25/26/32 map units with y jitter; the other
  branch uses `obj+0x9c >> 4`. Which objects take which branch.
- Where unit action durations (`obj+0xa8`) come from (server messages,
  `FUN_00464f02`), and the default game speed.
- Nine destructible structures have no destroyed block; destroyed, they
  would show their last `W·FH` frames. Whether the game ever lets their
  HP reach 0.
- Hero dying/bones frames: hero files (e.g. `swordsman_`, 152 frames)
  lack the dying block of the matching unit type (208); which file the
  hero draw uses for `T2`.
- What `FUN_004206c0` (structure tick guard, also tested before drawing
  flat structures) returns.
- Seven burning-tree objects (`<tree>\fire\f<tree>`) reference files
  absent from this install.

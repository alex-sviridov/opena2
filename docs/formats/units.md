# Unit animation: `units.reg` → `.256` frame indices

Binary: `allods2.exe` English 1.30, sha256
`2a8bdf9dc69276cc8d4fee561a7473a6b0f709cf9758abddaf2cd3b1fdfdfe43`.
Addresses were read in REA (Ghidra 12.1.4) and in the x86 listing.
Implementation: `allods2/units.py` (on `allods2/reg.py`, [reg](reg.md)).
Validation: `tools/validate_units.py`. Contact sheet:
`tools/unit_contact.py` → `out/contact/units.png`; per-file labelled sheets:
`tools/anim_contact.py` → `out/contact/anim_<name>_{raw,layout}.png`.

Each unit type names one sprite file (`.256` + `b.256` smoothing overlay,
[sprites](sprites.md)). Its frames are laid out in fixed blocks; the draw
routine `FUN_00468640` computes a frame index from the unit's state,
facing and animation step. Heroes use the same code with their own
paper-doll sprites (`+0x1c0`/`+0x1c4`).

## `units.reg`: `FUN_0047f108`

**CONFIRMED.** `Global/FileCount` files `Files/File<n>` each become a lazy
file object (`FUN_00480717`) with path `"graphics\units\" + value`; on
first use `FUN_004807fd` loads `<path>.256` and `<path>b.256`. Then
`Global/UnitCount` records `Unit<n>` (0x14c bytes each) are read:

| Key | Record | Default without Parent |
|---|---|---|
| `ID` | +0x04 | −1 |
| (n) | +0x08 | — |
| `File` | +0x0c | −1 |
| `Index` | +0x10 | −1 |
| `MovePhases` | +0x14 | −1 |
| `MoveBeginPhases` | +0x18 | −1 |
| `AttackPhases` | +0x1c | −1 |
| `DyingPhases` | +0x20 | −1 |
| `BonePhases` | +0x24 | −1 |
| `IdlePhases` | +0x28 | 0 |
| `Width`, `Height` | +0x2c, +0x30 | −1 |
| `CenterX`, `CenterY` | +0x34, +0x38 | −1 |
| `SelectionX1/Y1/X2/Y2` | rect objects | −1 |
| `MoveAnimTime/Frame` | sequence +0x3c, length +0x50 | from parent if empty |
| `AttackAnimTime/Frame` | sequence +0x54, length +0x68 | from parent if empty |
| `IdleAnimTime/Frame` | sequence +0x6c, length +0x80 | from parent if empty |
| `Dying` | +0x94 (unit **ID** whose frames are used for dying and bones) | 0 |
| `Palette` | +0x98 (count) | 0 |
| `Sound` | +0xdc (array) | from parent if empty |
| `TileSize` | +0xf0 | 1 |
| `Projectile` | +0xf4 | 0 |
| `InfoPicture` | +0xf8 (16 chars) | from parent if empty |
| `ShootOffset` | +0x108 (array) | from parent if empty |
| `ShootDelay`, `AttackDelay`, `Z` | +0x11c, +0x120, +0x124 | 0 |
| `Flip` | +0x128 | 0 |
| `DescText` | +300 (32 chars) | "" |

`Parent` is a unit **ID**; with a parent, every int defaults to the
parent's value, and arrays/strings are copied from the parent when the
child has none. **Palettes**: for `k < Palette` the parser loads the 0x400
bytes at 0x36 of `<sprite folder>\palette.pal`, `palette2.pal`,
`palette3.pal`, … into `+0xbc[k]` (shade tables built on demand with 16
levels, mode 2, tinted, `FUN_00473010`). With `Palette = 0` the draw uses
the owner's player palette from `human.pal` (`FUN_00473550`).
**Sequences**: each `(AnimTime[i], AnimFrame[i])` pair appends the frame
value `AnimTime[i]` times, giving a per-tick list (e.g. times `2 2 1`,
frames `0 1 2` → `0 0 1 1 2`).

## Frame layout

With `S` stand frames and `R` animated directions:

| Flip | S | R |
|---|---|---|
| 0 | 16 | 8 |
| 1 | 9 | 5 |

```
[0, S)                                  stand, one per facing
S + i·(Begin+Move) + p                  move, direction i, phase p
S + (Begin+Move)·R + i·Attack + p       attack
S + (Begin+Move+Attack)·R + i·Dying + p dying            (file of the Dying type)
S + (Begin+Move+Attack+Dying)·R + …     bones / idle     (shared block)
```

**CONFIRMED** (data, `tools/validate_units.py`): with the rule that a file
carries the dying and bones blocks only when `Dying` is its own ID, 59 of
the 62 types have exactly this many frames. The three others:

- Unit0 (ID 3): its `File0 ` key has a trailing space and is not found
  ([reg](reg.md)); its file `humans\swordsman\swordsman.256` (152 frames)
  does match the layout.
- Unit33 (ID 2) uses the 129-frame `humans\unarmed` file without `Flip`,
  while Unit21 uses it with `Flip = 1` (and matches). Without Flip the
  formulas index up to 207, past the file. A data bug in the game.
- Unit60 (sheep): 144 frames; the file's dying block has 5 phases per
  direction where `DyingPhases = 4`, so the game's dying and bones
  indices are misaligned (INFERRED from the art,
  [animation §2.5](animation.md#25-check-against-every-file)).

## Facing

The object's facing `d` (+0x70) is 0..15. **CONFIRMED**
(`FUN_00468640`):

```
stand:    i = (d − 8) & 15;         if Flip and i > 8: i = 16 − i, mirrored
animated: i = ((d − 8) & 14) >> 1;  if Flip and i > 4: i = 8 − i,  mirrored
```

Mirrored frames are drawn by the variant blitter `FUN_0045a64d`, which
writes each row from `x + w − 1` leftward, i.e. a horizontal flip at the
same position (**CONFIRMED**; so do `FUN_0045a8e7` (50 %), `FUN_0045dee0`
(`.16a`) and `FUN_0045ad81` (darken), [sprites](sprites.md)).
**CONFIRMED** (move step tables `0x6023b0`/`0x6023f0`): `d` counts
clockwise from screen-up (0 up, 4 right, 8 down, 12 left), so sprite
direction 0 (`d = 8`) faces down the screen, toward the viewer, and
sprite directions run clockwise. Diagram, hotspot under mirroring and
the per-file check: [animation §2](animation.md#2-layout-unit-monster-and-hero-sprites).

## Frame per state: `FUN_00468640`

`T` = the unit's type, `T2` = the type with ID `T.Dying`. `obj+0x78` is
the state, `obj+0x184` the death stage (nothing is drawn at ≥ 5),
`seq` the current value of the state's sequence (`FUN_00402a30`).
**CONFIRMED**:

| State (`+0x78`) | Condition | Frame |
|---|---|---|
| 0 | `T.Idle ≠ 0` | `S + (B+M+A+D)·R + i·Idle + seq` |
| 0 | stage 0 (or `T2.Bone = 0`) | stand `i16` |
| 0 | stage 1 | `T2`: `S + (B+M+A)·R + i·D + D − 1` (corpse) |
| 0 | stage 2..4 | `T2`: `S + (B+M+A+D)·R + i·T2.Idle + stage − 2` (bones) |
| 1 | — | `S + i·(B+M) + B + seq` (move) |
| 3, 7, 8 | — | `S + (B+M)·R + i·A + seq` (attack) |
| 5 | — | stand `i16` |
| 6 | — | `T2`: `S + (B+M+A)·R + i·D + obj[+0x74]/2` (dying) |

States 2 and 4 are never set by any code path ([animation](animation.md#14-timing)).
(B = MoveBeginPhases, M = MovePhases, A = AttackPhases, D = DyingPhases,
all of the type named; the begin phases are skipped by state 1.) Quirk:
the bones stride is `IdlePhases` (the assembly at 0x468bd9 / 0x468c34
reads `+0x28`), so units with `IdlePhases = 0` always show direction 0's
bones although the files store bones for every direction. While
`FUN_0046600b()` finds an active effect and the stage is < 3, the stand
frame `i16` is used whatever the state (INFERRED: a frozen/petrified unit).

## Placement

**CONFIRMED** (`FUN_00468640`, `+0x20`/`+0x24` = frame width/height):

```
left = obj.x − ((CenterX − Width/2) + frame_w/2)
top  = obj.y − ((CenterY − Height/2) + frame_h/2) − obj[+0x6c] − obj[+0x10]
```

`b.256` overlays use the same formula with their own frame size and are
drawn with the 50 % blit when Smoothing is on ([sprites](sprites.md)).

## Other fields

All **CONFIRMED** in `allods2.exe` (every read of the field found by
scanning for the type table `0x62cb40`), with data from this install's
`units.reg`:

| Field | Use | Data |
|---|---|---|
| `Index` | read into a local by the draw `FUN_00468640` (`0x4686e4`, `0x4698a1`, `0x46a7d3`) and never used; only otherwise read as a parent default | 0 in all 62 types |
| `TileSize` | returned by the unit vtable `+0x20` and `+0x24` (`FUN_0046856d`, `FUN_00468591`) as the unit's width and height in cells; used e.g. to centre the sight stamp ([animation §1.6](animation.md#16-visibility-gates)) | 1; 2 for troll, troll_good, ogre, star; 3 for dragon |
| `Z` | only tested `≠ 0`: such a type is created as a flying unit (`0x1e4`-byte object, constructor `FUN_00471419`, vtable `0x5d7810`) by the create message (`0x40fb9a`) and the save loader (`0x4ac7e3`); the value itself is not used | 96 for bat, dragon, succubus; 0 otherwise |
| `ShootOffset` | 8 `(x, y)` pairs, one per animated direction `k = (d − 8) & 14`: a projectile starts at `x = unit.x − (CenterX − SO[k])·8`, `y = unit.y − (CenterY − SO[k+1])·8` (map units; 8 per sprite pixel; `FUN_0046c28b` `0x46c375`, `FUN_0046c4f1` `0x46c6e4`) | set in 26 `Unit<n>` sections (others inherit from `Parent` or have none); all 64 (sprite centre) for bat and succubus |
| `SelectionX1/Y1/X2/Y2` | mouse-pick rectangle in sprite-box pixels: the view draw (`0x4087ba`–`0x408886`) offsets it by `(obj+0x64 − CenterX, obj+0x68 − CenterY − obj+0x6c − obj+0x10)` and registers it for the unit (`FUN_00404e40`) while the death stage is `< 2` | |
| `Palette` | 0: owner's colour from `human.pal`; 1: the type's palette 0; `> 1`: palette `obj+0x28 − 1` (`0x468f4b`–`0x468fb5`, `FUN_00473010`) | 5 for most monsters; 2–7 for undead, necromant, druid, troll_good |

`obj+0x28` for monsters (types `≥ 0x40`) is a byte sent by the server: the
create message (`DAT_0060e4c8`, `0x40fc89`) and the full state
(`msg+0x4b`, `0x46ee80`) both pass it to `FUN_0046f540`, which stores it
as is (heroes use the same byte for their portrait/flags). So each
monster's colour variant is chosen by the server (open: from map or
data.bin). The unit constructor (`FUN_0046838e`) first sets it to the
type ID.

## Worked example

Unit1 (ID 4, Human Swordsman with shield; Parent 3) inherits B = 2, M = 8,
A = 7 and has D = 4, Bone = 3, Flip 0, Dying = 4 (itself). File
`humans\swordsman_\swordsman_`: 16 + 8·(10 + 7 + 4 + 3) = 208 frames.
Walking with facing d = 10 at sequence value 3: `i = (2 & 14) >> 1 = 1`,
frame = 16 + 1·10 + 2 + 3 = 31. Its corpse at d = 10: 16 + 17·8 + 1·4 + 3
= 159.

## Open questions

- Where the server takes a monster's palette variant byte (`obj+0x28`,
  sent in the create message): map unit records or `data.bin`.

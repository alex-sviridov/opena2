# Unit animation: `units.reg` → `.256` frame indices

Code: `allods2/units.py` (on `allods2/reg.py`). Tools:
`tools/validate_units.py`; `tools/unit_contact.py` →
`out/contact/units.png`; `tools/anim_contact.py` (labelled per-file
sheets, [animation §2](animation.md#2-layout-unit-monster-and-hero-sprites)).

Each type names one sprite file (`.256` + `b.256` overlay,
[sprites](sprites.md)) laid out in fixed blocks; `FUN_00468640` computes
the frame from state, facing and phase. Heroes use the same code with
their paper-doll sprites (`+0x1c0`/`+0x1c4`).

## `units.reg`: `FUN_0047f108`

CONFIRMED. `Global/FileCount` files `Files/File<n>` become lazy file
objects (`FUN_00480717`, path `"graphics\units\" + value`; first use
`FUN_004807fd` loads `<path>.256` and `<path>b.256`). Then
`Global/UnitCount` records `Unit<n>`, 0x14c bytes. Fields (offset;
default without Parent −1 unless noted): `ID` +0x04; (n) +0x08; `File`
+0x0c; `Index` +0x10; `MovePhases` +0x14; `MoveBeginPhases` +0x18;
`AttackPhases` +0x1c; `DyingPhases` +0x20; `BonePhases` +0x24;
`IdlePhases` +0x28 (0); `Width`, `Height` +0x2c/+0x30; `CenterX`,
`CenterY` +0x34/+0x38; `SelectionX1/Y1/X2/Y2` rect objects;
`MoveAnimTime/Frame` sequence +0x3c, length +0x50; `AttackAnim…` +0x54,
+0x68; `IdleAnim…` +0x6c, +0x80; `Dying` +0x94 (unit **ID** whose frames
are used for dying and bones; 0); `Palette` +0x98 (count; 0); `Sound`
+0xdc (array); `TileSize` +0xf0 (1); `Projectile` +0xf4 (0);
`InfoPicture` +0xf8 (16 chars); `ShootOffset` +0x108 (array);
`ShootDelay`, `AttackDelay`, `Z` +0x11c/+0x120/+0x124 (0); `Flip` +0x128
(0); `DescText` +300 (32 chars, ""). Sequences, arrays and strings are
taken from the parent when empty.

`Parent` is a unit **ID**: every int defaults to the parent's value.
**Palettes**: for `k < Palette` the parser loads 0x400 bytes at 0x36 of
`<sprite folder>\palette.pal`, `palette2.pal`, … into `+0xbc[k]` (shade
tables on demand, 16 levels, mode 2, tinted, `FUN_00473010`); with
`Palette = 0` the draw uses the owner's `human.pal` palette
(`FUN_00473550`). **Sequences**: each `(AnimTime[i], AnimFrame[i])`
appends the frame `AnimTime[i]` times (times `2 2 1`, frames `0 1 2` →
`0 0 1 1 2`).

## Frame layout

`S` stand frames, `R` animated directions: `Flip` 0 → 16, 8; `Flip` 1 →
9, 5. Blocks in order: stand, move (`B+M` per direction), attack, dying,
bones/idle; dying and bones exist only in a file whose type has
`Dying` = its own ID. CONFIRMED (data, `tools/validate_units.py`): 59 of
62 types exact; exceptions Unit0 (`File0 ` trailing space, [reg](reg.md)),
Unit33 (129-frame `humans\unarmed` without `Flip`; Unit21 uses it with
`Flip` and matches; indexes up to 207) and the sheep (dying block has 5
phases, `DyingPhases = 4`); details
[animation §2.5](animation.md#25-check-against-every-file).

## Facing

`d` (+0x70) 0..15, clockwise from screen-up (0 up, 4 right, 8 down, 12
left; CONFIRMED by step tables `0x6023b0`/`0x6023f0`). CONFIRMED
(`FUN_00468640`):

```
stand:    i = (d − 8) & 15;         if Flip and i > 8: i = 16 − i, mirrored
animated: i = ((d − 8) & 14) >> 1;  if Flip and i > 4: i = 8 − i,  mirrored
```

Sprite direction 0 (`d = 8`) faces the viewer. Mirrored = horizontal flip
in place via the leftward blitters ([sprites](sprites.md)). Diagram and
hotspot: [animation §2.2–2.3](animation.md#2-layout-unit-monster-and-hero-sprites).

## Frame per state: `FUN_00468640`

`T` = type, `T2` = type with ID `T.Dying`; `obj+0x78` state, `obj+0x184`
death stage (nothing drawn at ≥ 5); `seq` = current value of the state's
sequence (`FUN_00402a30`); B, M, A, D = MoveBegin, Move, Attack, Dying
phases of the type named. CONFIRMED:

| State | Condition | Frame |
|---|---|---|
| 0 | `T.Idle ≠ 0` | `S + (B+M+A+D)·R + i·Idle + seq` |
| 0 | stage 0 (or `T2.Bone = 0`) | stand `i16` |
| 0 | stage 1 | `T2`: `S + (B+M+A)·R + i·D + D − 1` (corpse) |
| 0 | stage 2..4 | `T2`: `S + (B+M+A+D)·R + i·T2.Idle + stage − 2` (bones) |
| 1 | — | `S + i·(B+M) + B + seq` (move; begin phases skipped) |
| 3, 7, 8 | — | `S + (B+M)·R + i·A + seq` (attack) |
| 5 | — | stand `i16` |
| 6 | — | `T2`: `S + (B+M+A)·R + i·D + obj[+0x74]/2` (dying) |

States 2 and 4 are never set ([animation §1.4](animation.md#14-timing)).
Quirk: the bones stride is `IdlePhases` (asm `0x468bd9`/`0x468c34` read
`+0x28`), so `IdlePhases = 0` units always show direction 0's bones,
though files store all directions. While `FUN_0046600b()` finds an active
effect and stage < 3, stand `i16` is used whatever the state (INFERRED:
frozen/petrified).

## Placement

CONFIRMED (`FUN_00468640`; `+0x20/+0x24` = frame w/h, `FUN_00426c16` /
`FUN_00426c41`):

```
left = obj.x − ((CenterX − Width/2) + frame_w/2)          // obj.x = obj+0x64
top  = obj.y − ((CenterY − Height/2) + frame_h/2) − obj[+0x6c] − obj[+0x10]
```

`obj+0x6c` is height above ground (INFERRED). `b.256` overlays use the
same formula with their own frame size, 50 % blit when Smoothing is on.

## Other fields

All CONFIRMED (every read found by scanning for type table `0x62cb40`);
data from this install's `units.reg`:

| Field | Use | Data |
|---|---|---|
| `Index` | read into a local by `FUN_00468640` (`0x4686e4`, `0x4698a1`, `0x46a7d3`), never used; else only a parent default | 0 in all 62 |
| `TileSize` | unit vtable `+0x20/+0x24` (`FUN_0046856d`, `FUN_00468591`): width/height in cells; e.g. centres the sight stamp ([animation §1.6](animation.md#16-visibility-gates)) | 1; 2 troll, troll_good, ogre, star; 3 dragon |
| `Z` | only tested `≠ 0`: creates a flying unit (`0x1e4`-byte object, constructor `FUN_00471419`, vtable `0x5d7810`) in the create message (`0x40fb9a`) and save loader (`0x4ac7e3`) | 96 bat, dragon, succubus; else 0 |
| `ShootOffset` | 8 `(x, y)` pairs by `k = (d − 8) & 14`: projectile starts at `x = unit.x − (CenterX − SO[k])·8`, `y = unit.y − (CenterY − SO[k+1])·8` (map units, 8 per pixel; `FUN_0046c28b` `0x46c375`, `FUN_0046c4f1` `0x46c6e4`) | set in 26 sections (others inherit or none); all 64 for bat and succubus |
| `SelectionX1/Y1/X2/Y2` | mouse-pick rect in sprite-box pixels: view draw (`0x4087ba`–`0x408886`) offsets it by `(obj+0x64 − CenterX, obj+0x68 − CenterY − obj+0x6c − obj+0x10)` and registers it (`FUN_00404e40`) while stage `< 2` | |
| `Palette` | 0: owner's `human.pal` colour; 1: palette 0; `> 1`: palette `obj+0x28 − 1` (`0x468f4b`–`0x468fb5`, `FUN_00473010`) | 5 most monsters; 2–7 undead, necromant, druid, troll_good |

`obj+0x28` for monsters (types `≥ 0x40`) is a server byte: create message
(`DAT_0060e4c8`, `0x40fc89`) and full state (`msg+0x4b`, `0x46ee80`) pass
it to `FUN_0046f540`, stored as is (heroes use it for portrait/flags);
the constructor `FUN_0046838e` first sets it to the type ID.

Server side (CONFIRMED): the unit message builder `FUN_0050ac91` writes,
under flag `0x20`, the type ID (`FUN_0054a7b0`, client `0x60e4c4` →
`obj+0x24`) and then the server unit byte `+0x4b` (`0x50b180`, client
`0x60e4c8` → `obj+0x28`). For monsters `+0x4b` is data.bin monster
param 30 (`FUN_0051b12f`, [databin](databin.md#parameter-maps)): 1–7,
usually the `.N` suffix of the record (`Goblin_Pike.3` → 3, but undead
`F_Zombie.2…4` → 1, `.5` → 2); 65 records use 1 (palette 0). The hero
builder (`0x51e7e5`–`0x51e829`) stores its own value and ORs a flag into
bit 7. `MONSTER["paletteVariant"]`.

## Worked example

Unit1 (ID 4, swordsman with shield, Parent 3) inherits B 2, M 8, A 7;
D 4, Bone 3, Flip 0, Dying 4 (itself). File `humans\swordsman_\swordsman_`:
16 + 8·(10 + 7 + 4 + 3) = 208 frames. Walking, d = 10, seq 3:
`i = (2 & 14) >> 1 = 1` → 16 + 10 + 2 + 3 = 31. Corpse at d = 10:
16 + 17·8 + 4 + 3 = 159.

## Open questions

None.

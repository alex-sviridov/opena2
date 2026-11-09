# Spell effects (phase K2): effect objects, the per-tick effect pass, carriers of buffs and areas

GOG 1.01 `allods2.exe` (sha256 in [formats/README](../formats/README.md)); addresses are VAs. Tags as in CLAUDE.md: **CONFIRMED** = read in
the exe with REA (routine given), **INFERRED** = anything else. Related: [spells §4, §6, §9b](../data/spells.md) (handlers, level, field
patterns), [unit-struct](unit-struct.md) (fields), [combat §5.2, §16.5](combat.md) (Bless / Curse in `take_hit`, the Invisibility break),
[ai §12](ai.md) (the effect bits the AI reads), [simulation §11.1](simulation.md) (Haste vs the group speed byte).
Engine: `engine/sim/effects.py` (§9).

## 1. Summary

A spell that is not a damage spell builds an **effect object** in `FUN_00519db8` (§3), wraps it in a **carrier** (point: one unit; area:
cells; §6) and the carrier calls the effect's **apply** (`vtable +0x3c` = `FUN_0051ce12`) on each unit it reaches. Apply puts a copy in
the unit's **effect list** (`unit+0x20`), sets bit `1 << id` of the **effect mask** `unit+0x144` and changes the stats once (`+0x40`);
the same spell again **merges** (max value, max time) instead of stacking. Every creature tick runs the list first (`FUN_0050f12c`
`0x50f162`-`0x50f1b7`): each effect counts its ticks down (`+0x38` = `FUN_0051cc9f`), a continuous one (Poison) acts every 8 ticks, and at 0
the stat change is undone (`+0x44`), the bit cleared and the object removed. All CONFIRMED.

## 2. The effect object (class vtable `0x5d1178`, 0x48 bytes)

Constructors: plain `FUN_0051ca4d` (kind 0 = no stat), from modifier text `FUN_0051caa0(text)` (one term parsed by `FUN_0051e8fa`, §2.2),
copy `FUN_0051cb98` (used by apply). Base object `FUN_0050d493`. CONFIRMED.

| Offset | Type | Meaning | Tag |
|---|---|---|---|
| `+0x0c` | u16 | **id** = the spell number (the switch writes it); the list search key (`FUN_005106f4`), the mask bit `1 << (id & 31)` | CONFIRMED `0x51ce12`, `0x5106f4` |
| `+0x0e` | u16 | client effect id `2n + 8` (the cast action's projectile; its lifetime is 0 for every id but the flights, Teleport, Heal and Drain Life, so **no unit-attached sprite is ever drawn**, [rendering: Status effects](rendering.md#status-effects-k9); palettes in [palettes](../formats/palettes.md)) | CONFIRMED |
| `+0x3c` | u8 | **kind** = stat index of the text (`0x5f8f50`, [databin](../formats/databin.md#stat-names-and-modifier-text)); 0 for plain effects | CONFIRMED `0x51e8fa` |
| `+0x3d` | u8 | flags: 1 duration, 2 continuous, 4 charges, 8 single use (text time part `FUN_0051f29c`; `permanent` = 0); 0x80 finished (`FUN_00542540`) | CONFIRMED |
| `+0x40` | s16 (s32 for flags 0) | **value** | CONFIRMED |
| `+0x42` | u16 | **ticks left**; text time `N` -> `N << 4`; `>= 0x2581` (9601) never counts down | CONFIRMED `0x51cc9f` |
| `+0x44` | ptr | caster (Poison XP credit) | CONFIRMED |

"Timed" = flags & 3 (`FUN_0051cc53`).

### 2.1 Virtual slots

| Slot | Routine | What |
|---|---|---|
| `+0x38` tick | `FUN_0051cc9f(unit)` | only timed: (a) continuous and `ticks & 7 == 0` -> pulse (`+0x40`) + client update; (b) if `ticks < 0x2581`: `ticks -= 1`; at 0: not continuous -> undo (`+0x44`); bit `1 << id` cleared; flags `|= 0x80` (the caller removes it) |
| `+0x3c` apply | `FUN_0051ce12(unit)` | §4 |
| `+0x40` pulse / start | `FUN_0051d175(unit)` | id 6 Poison: `d = -value`; if water protection `+0xc6 != 0`: `d = ftol(d * (100 - p) / 100.0 + 0.5)`; if `d != 0`: HP `+0x94 -= d` (no cap, no death test here), caster XP credit (vtable `+0x6c(unit, d, 6)`) unless the caster's HP `< 0` (`FUN_00542770`, then the caster is dropped). Id 15 Light: **non-humans** only, scan `+0xa4 -= value << 8`. Id 14 Darkness: **humans** only, `+0xe4 += value << 8` and `+0xa4 += value << 8`. Others: `+0x48(unit, +1)` |
| `+0x44` undo | `FUN_0051d337(unit)` | the reverse of `+0x40` for 14 / 15; nothing for 6; else `+0x48(unit, -1)` |
| `+0x48` stat switch | `FUN_0051d436(unit, sign)` | §5 |

### 2.2 Text parsing (`FUN_0051e8fa`)

One term only: name before `=`, value, time after `:`; a text with several terms (Stone Curse `absorbtion=+5:duration 8,defence=-20:duration 8`)
gives **one** object, the first term (absorption +5): CONFIRMED (one object per `FUN_0051caa0`; the term split is not traced character by
character: INFERRED which term, the kind index stored is the first name). The handler then overwrites value and ticks for every spell but
Poison / Light / Darkness (§3).

## 3. The handlers (`FUN_00519db8` switch, `L` = level, [spells §6](../data/spells.md#6-level-and-scaling))

`P(L) = ftol(1.1^L * p14 * 16.0)` stored as u16 (x87 `pow`, `0x5845c9`; constant 16.0 at `0x5d08a8`). All CONFIRMED (case addresses).

| Spell | Case | Object | id | kind | flags | value | ticks |
|---|---|---|---|---|---|---|---|
| 4 8 13 19 Protection from Fire / Water / Air / Earth | `0x51b385` | text | n | 21 / 22 / 23 / 24 (protection fire..earth) | `|= 1` | `L / 2` | `P(L)` |
| 6 Poison Cloud | `0x51a206` | text `health=-2:continuous 8` | 6 | 6 | 2 (continuous) | `ftol(-2 * (L / 45.0 + 1))` | 128 (text) |
| 12 Invisibility | `0x51b927` | plain | 12 | 0 | `|= 1` | 0 | `L << 4`; 0 -> no effect |
| 14 Darkness | `0x51b2de` | text `scanRange=-2:duration 1` | 14 | 19 (unused, id path) | 1 | `-1 - L/30` | 16 (text) |
| 15 Light | `0x51b239` | text `scanRange=2:duration 1` | 15 | 19 | 1 | `L/30 + 1` | 16 |
| 17 Wall of Earth | `0x51b1de` | plain, **id 0** | 0 | 0 | 0 | 0 | 0 (the carrier skips it, §6.3) |
| 18 Stone Curse | `0x51b6ae` | text (first term: absorption) | 18 | 16 | `|= 1` | 5 (text) | `L * 240 * (learned ? 2 : 1) / 100` (C division); on a creature then `rand(0..ticks * (100 - protEarth) / 100)` (`FUN_0051fa25`); 0 -> no effect |
| 20 Bless, 28 Curse | `0x51b82c` | plain | 20 / 28 | 0 | `|= 1` | `L*4/5 + 20` | `P(L)` |
| 21 Haste, 29 Slow | `0x51b589` | text `speed=+-2:duration 30` | 21 / 29 | 17 (speed) | `|= 1` | `L/15 + 1`, negated for 29 | `P(L)` |
| 27 Shield | `0x51b484` | text `absorbtion=+5:duration 30` | 27 | 16 (absorption) | `|= 1` | `L/10 + 3` | `P(L)` |
| other non-damage numbers (default) | `0x51ba22` | plain | n | 0 | 0 | 0 | 0 |

Teleport 23, Heal 24, Summon 25, Drain Life 26, Control Spirit 22 return before a carrier (spells §4, §9b). The damage branch (spells with
`min' + spread' > 0` except 24 / 26) builds `Effect_DirectDamage` (class `0x5d11d0`, apply `FUN_0051e65b` = take-damage) instead.

**Carrier choice (after the switch, `0x51baa0`).** `distribution == 1` -> **point carrier** `FUN_005178d4(effect)` (a cast at a cell, i.e.
no target unit, prints "Spell: oops, can't cast point effect" and does nothing); else **area carrier** `FUN_00517c1a(effect, centre, radius)`
(§6) with lifetime `+0x50 = p11 << 4`, and when non-zero `+0x50 += (L << 4) / 10` and mode `+8 = 1`; `distribution == 5` -> mode 2,
`+0x50 = 0`; direction `+0x4e = FUN_00556b2c(caster, centre) >> 5` (8-way). `delivery == 1` -> appended to the active list at once
(`FUN_00542e60`); `delivery == 2` -> a missile `FUN_00518d1e` that appends it on landing (spells §9c.3). Caster `+0x3c` and the effect's
`+0x44` := the caster; hostile byte `+0x41 = (defensive == 0)`. CONFIRMED `0x51baa0`-`0x51bea7`.

## 4. Apply = `FUN_0051ce12(unit)` (this = the carrier's template)

```
unit+0x150 := 0                                           # client update mask (§7)
if timed(this) and this.id in (20, 28):                   # Bless / Curse cancel each other
    e = first effect in the list with id 28 (for a Bless) / 20 (for a Curse)
    if e: clear bit 1 << e.id; e.undo(unit); remove + delete e; message; return     # the new one is NOT added
if not timed(this):  this.pulse(unit)                     # permanent / single use: changes the stats at once, no list entry
else:
    e = first effect in the list with this.id
    if e is None:
        c = copy(this); if c.id != 6: c.pulse(unit)       # the stat change starts now (Poison waits for its first tick)
        append c to the list (tail); set bit 1 << id; client effect message if id != 0
    else:                                                 # merge, never stacks
        e.undo(unit); e.value = max(e.value, this.value) (signed s16); e.ticks = max(e.ticks, this.ticks) (u16)
        if e.id != 6: e.pulse(unit)
message 0xffb
```

CONFIRMED. Consequences: a second cast refreshes the time to the larger one and keeps the larger value; a weaker **Slow** (`-3`) over a
stronger one (`-5`) *raises* the value to `-3` (signed max: quirk); a Curse on a blessed unit only removes the Bless (and vice versa).

## 5. Stat switch `FUN_0051d436(unit, sign)` (the kinds spells reach)

Amount `a = sign * value` (s16 value for timed / charges / single use, else s32). First, for every kind: `if unit+0xd8 > 24: unit+0xd8 := 0`.
Then by kind, then `vtable +0x58` (the recompute: humans `FUN_0051366b`, monsters `FUN_005118be` = mana regeneration only). CONFIRMED.

| Kind | Monster (vtable `+0x30 == 0`) | Human | Mask `+0x150` |
|---|---|---|---|
| 0 (Bless, Curse, Invisibility, default) | nothing | nothing | - |
| 15 defence | `+0xbe = max(0, +0xbe + a)` | bonus `+0xfe += a` | 0x4000 |
| 16 absorption (Shield, Stone Curse) | `+0xc0 += a` | bonus `+0x100 = max(0, +0x100 + a)` | 0x8000 |
| 17 speed (Haste, Slow) | `+0x8c += a` | bonus `+0xd8 += a` | 0x80000 |
| 19 scan range | `+0xa4 += a << 8` | bonus `+0xe4 += a << 8` | 0x40000 |
| 20..25 protection phys, fire, water, air, earth, astral | bonus `+0x102 + 2k = max(0, .. + a)` | same | 0x1000000 |

The bonus block `+0xd4..+0x113` is merged into the live fields only by `FUN_005113e7`, whose two callers are the monster set-up
(`0x511f58`) and the human recompute (`0x513eaa`): **on monsters the protection spells change nothing** (the bonus words are never read
again; only the mask bit is set). Human recompute: speed `+0x8c = base + bonus`, and when the sum is negative the bonus is zeroed
(`FUN_005113e7`); scan `+0xa4 = base + bonus`; the armour block bonus is added and capped as in [combat §6](combat.md). CONFIRMED.

## 6. Carriers

### 6.1 Point carrier `FUN_00517949` (class `0x5d10a0`)

As for damage ([spells §9c.3](../data/spells.md#9c3-release-carriers-damage)): a creature target still in the world (`+0x14 != 0`) gets the
apply; then, for a hostile spell with a caster: victim `+0x40` (last attacker) := caster and `+0x48` := id, and the hit reaction
`FUN_0056e6b8(caster, victim, 0)`. Carrier done. CONFIRMED.

### 6.2 Area carrier `FUN_00517c1a` / tick `FUN_00517cfe` (class `0x5d10e0`)

Fields: `+8` mode, `+0x48` effect, `+0x4c` stamped, `+0x4d` radius `r` (param 9), `+0x4e` direction, `+0x4f` step, `+0x50` lifetime
(s16), centre = the target cell (a unit: its cell; size > 1: centre - 1 in 1/256, INFERRED rounding). Tick (CONFIRMED):

- mode 2 (field: Blizzard, Acid Stream) -> `FUN_0051806c`, [spells §9b](../data/spells.md#9b-field-carriers-summons-raising-tooltip).
- mode 0 (`+0x50 == 0`: **Fire Ball**) -> `FUN_00518833` once (first `FUN_005045a5(c, 1)`: the client explosion, [rendering](rendering.md#structure-pick-rects-and-dynamic-lights-confirmed-engine-drawlistpick_cell-lightspy)): for every cell of the square `|dx|, |dy| <= r` round the centre, `FUN_00518681` on
  the ground occupant (`rec+4`), the air occupant (`rec+8`) and the structure; a damage effect with spread > 0 also clears the cell
  effects (`FUN_005189b5`, §6.4) and scorches the ground (`FUN_00559c28`, server dirt bit; no reader); done. The *client* burnt-ground bit is another thing: tile bit `0x2000` set by the Wall of Fire cell flag ([rendering](rendering.md#unit-and-cell-effects)), built (`World.scorch`).
- mode 1 (lifetime): first visit (`+0x4c == 0`) **stamps** the shape (`FUN_00518024`: `distribution == 4` wall `FUN_005182b6`, else
  diamond `FUN_005183a2` = cells of the square with `|dx| + |dy| <= r + 1`), no countdown. Later visits: `+0x50 == 0` -> unstamp the square
  (`FUN_00518594`) and done; else `+0x50 -= 1` and when `+0x50 & 15 == 0` every cell of the square that holds **this** carrier
  (`FUN_0055a8f8`) gets `FUN_00518681` on its **ground occupant only** (`FUN_00551edb` = `rec+4`; flyers are not reached).

**Wall shape** (`FUN_00517ec3` with tables `0x5f8400` (10 cells: `dx = -2..2` at `dy = 1` and at `dy = 0`) and `0x5f84a8` (9 cells:
`(-2,2) (-1,1) (0,0) (1,-1) (2,-2) (-1,2) (0,1) (1,0) (2,-1)`), by direction `d`: 0 table A with `dy` negated; 1 table B with `dy` negated; 2
table A with x and y swapped; 3 table B; 4 table A with `dx` negated; 5 table B with `dx` negated; 6 table A swapped with `dx` negated; 7 table
B with both negated. **The radius is not used** by the wall (the old spells §2 remark "r cells each way" was wrong). CONFIRMED.

**Stamp of one cell** `FUN_005184bf(x, y, dmg)`: skipped on a structure cell whose static block byte has bit 4; Wall of Earth (17) only on a
cell without a ground occupant; else `FUN_0055a37a` puts the carrier into the cell record's effect slot of its spell (§6.4, the newest carrier
wins the slot), then the interaction `FUN_005189b5` and (damage with spread) the scorch. CONFIRMED.

### 6.3 `FUN_00518681(unit)`: an area reaches a unit

Nothing for no unit or **Wall of Earth (17)**. Fire Ball (2): a copy of the damage effect with min' and spread' (bytes `+0x5b`, `+0x5c`)
**divided by `size * size`** of the unit (vtable `+0x1c`, integer division) is applied (`FUN_0051e65b`): a 2x2 unit takes a quarter per cell
of it in the square. Others: the effect's apply (`+0x3c`). Then, unless the spell is 15 (Light), for a creature and a caster: the last
attacker `+0x40` := caster (cleared when the caster is gone; **not for Darkness 14**) and `+0x48` := id; the hit reaction
`FUN_0056e6b8(caster, unit, 1)` when both are in the world. **No friend / foe test, no hostile flag**: every area hits everyone in it,
the caster included. CONFIRMED.

The third argument 1 of the hit reaction ("area") changes the relation update `FUN_0057977a`: the attacker -> victim war bit is set for
neutral owners as before; the victim -> attacker bit is set only when the victim's brain counter `+0xac > 10`, or its HP `< max / 2`, or it
is dead (state 0x10); every area hit between neutral owners adds 1 to that counter. So an ally caught in a fire wall turns hostile only
after 11 hits or below half HP. CONFIRMED `0x57977a`.

### 6.4 Cell effect slots

Drawing of the slots and of the unit effects 12 / 18: [rendering: Unit and cell effects](rendering.md#unit-and-cell-effects).

The cell record is [unit-struct: cell record](unit-struct.md#cell-record-effect-confirmed). 
Record slots `rec+0x14 + 4k`, k by spell (`FUN_00518ba3`): Wall of Fire 3 -> 0, Poison Cloud 6 -> 2, Wall of Earth 17 -> 3, Light 15 -> 4,
Darkness 14 -> 5 (others: error "Invalid Area Effect", slot 0). The record exists while any slot is used (`0x20` bit of the static byte);
it saved the cost and block bytes at creation (`FUN_005508a0`) and restores them on deletion (`FUN_00550966`). After every stamp / unstamp
`FUN_00550a96` rebuilds the cell: **cost byte `<<= 2` (u8) once per used slot** (`FUN_0055f350` returns 1), and a Wall of Earth slot sets
block bits `| 5` in the static and the live layer (the cell is blocked like an object). Interactions when a cell is stamped
(`FUN_005189b5`): fire (2, 3) removes a Poison Cloud from the cell (slot 2); Poison on a fire-wall cell (slot 0) removes itself; Light and
Darkness on the same cell remove each other **and** themselves. Unstamp (`FUN_0055a533`) clears the slot only when it holds this carrier.
CONFIRMED.

### 6.5 Script access: check 25, instants 29 and 30 (CONFIRMED, engine `engine/sim/effects.py`)

- **Check 25 `FUN_005777d3`**: `rec = FUN_0055a82c(n0 + n1 * 0x100)` (the cell's record when the static byte has bit `0x20`, else none): `FUN_0055f3e0` is a hash-map lookup (`FUN_0055ff70`: key hash `FUN_00422210` modulo the bucket count, chain walk) whose hit copies the stored record into the working buffer `world+0x5402c`; value 1 when the dword at `rec + 0x14 + n2 * 4` is non-zero. The record (0x3c bytes, `FUN_005508a0` creates it, `FUN_0054f89a` clears it): `+0` saved cost byte, `+1` saved block byte, `+2` used-slot count, `+0x14..+0x2b` six carrier slots, `+0x34..+0x39` the trap effect, `+0x3a` the cell's index word. So `n2` 0-5 are the slots; the index is not range-tested, 6 / 7 read `+0x2c` / `+0x30` (never written: 0), 8 the trap's first four bytes, 9 target x, y + the index word (1 for any record). CONFIRMED the lookup and the offsets; the engine (`tile_layer`) reads layers 0-9 that way, above 9 it answers 0 (DECISION; the scratch fields past the record are not traced, no map uses a layer above 3). Pure state: it is
  evaluated at every pass of the trigger evaluator and carries no history, so a wall that expired or was burnt away reads 0 again. Engine `effects.tile_layer`; the cell record's slots are `World.cell_fx`
  (part of `dump()`, so of the replay hash).
- **Instant 29 `FUN_00578696`** (the slots only ever hold mode-1 lifetime carriers: CONFIRMED, `FUN_0055a37a` <- `FUN_0055a325` <- `FUN_005184bf` <- the two shape stampers `0x5182b6` / `0x5183a2` only; Fire Ball (mode 0) and the fields (mode 2) never stamp): for each of the 6 slots of the cell's record whose carrier's spell id (`+0xc`) equals `n2`, `carrier +0x50 := n3` (low word). The area tick (`0x517d45`) reads `+0x50` as
  **unsigned** (`XOR EAX, EAX; MOV AX`; branch `<= 0` = zero), so 32768 counts down 32768 ticks (long enough to count as permanent), then unstamps as usual; the `& 15` pulse follows the new
  value. Engine `effects.set_tile_duration` (`Carrier.life` is kept as s16: the same countdown). Nothing else changes (no stamp, no effect).
- **Instant 30 `FUN_0057871f`**: every effect of the unit's list (`+0x20`) whose id (`+0xc`) is `n0` gets ticks `+0x42 := n1` (low word); the mask bit and the stat change stay (>= 0x2581 never counts down).
  Engine `effects.set_unit_duration`.
- What the three maps need ([structures §6](structures.md)): 93 a Wall of Fire on both rows (check 25 layer 0, `v70` and `v71`); 94 Wall of Earth, where row 113 / 117 want (63, 65, 67) walled and row 115 only
  (65, 115): straight walls from the north / south, and the **diagonal** shape (§6.2 table B; from the east side: caster at x + 4, directions 5-7) in the middle, found by a direction search over the exact shapes; 95 two Poison Clouds
  made by instant 21 at the start, made long-lived by instant 29 once `v74 = 3`, burnt away by Wall of Fire (§6.4) on the checked cells. The tests solve each with scripted `CastSpell` commands. **Timing** (CONFIRMED formula `0x51bcb7`: lifetime = `area_duration * 16 + level * 16 / 10` ticks; Wall of Fire / Earth and Poison Cloud have `area_duration` 10, so 161-320 ticks at level 1-100, 256 at level 60): map 94's three walls must stand together, but one hero's cast (19 ticks) plus the walk between the three cast positions (about 150 ticks each) outlasts the first wall, so the puzzle wants several casters (or scrolls) at once; with a debug teleport between the casts it solves.

## 7. The effect pass and the effect mask

- Creature tick `FUN_0050f12c`: unless state 0x10, **first** iterate the list in order: `+0x38` tick, then remove the effect if finished
  (`FUN_00542540`, `FUN_0053af60`). This runs for dying units too (before the HP <= 0 branch). Carriers run before the creature pass
  (spells §9c.3), so an effect applied by a point carrier at tick `A` is ticked in the same tick: it is active (bit set) from the carrier pass
  of `A` and its bit is cleared in the creature pass of `A + ticks - 1`. CONFIRMED order.
- `unit+0x144` = the effect mask (`1 << id`; zeroed by the constructors `0x50e201`, `0x50ea66`). The **client update mask** is `unit+0x150`
  (`FUN_0051d436` ORs the stat classes; `FUN_00502019(unit, 0, +0x150, 0xffb)` sends it): the old unit-struct text that put the stat classes
  and "AI order 4 waits on 0x40000" in `+0x144` mixed the two. CONFIRMED.
- Readers of `+0x144` (asm scan, CONFIRMED): `take_hit` Bless 20 / Curse 28 ([combat §16.5](combat.md)); the swing start and the cast at another
  unit end Invisibility (12, `+0x42 := 1`); the AI pool and flee lists hide bit 12 (`0x567a8c` ff.); **Stone Curse bit 18 (`0x40000`)**: the
  Brain tick `0x56dd24` sets brain order 4 when the brain order is 0 (a step, swing or cast in progress finishes first), order 4 sets state
  0x1b and waits until the bit clears (`0x56dfca`): **the unit does nothing while stoned** (no step, no attack, no cast); the target score
  `FUN_005711ea` adds 0x7f (min 1) for a stoned target (`0x5713c7`); the idle mage checks Shield 27 (`0x56b390`) and the friend buffs
  (`FUN_0057a999`); the human caster scan `FUN_0056bc7b` bits 4 8 12 13 19 20 21 27; the flee tests `& 0xc` (bits 2, 3: never set, damage
  effects are not listed: dead tests, INFERRED); the trigger effect check (`0x577872`); `FUN_0057a608` (bit 18; no caller: dead code).

## 8. Worked examples

- **Shield** at level `L = 40`: value `40/10 + 3 = 7`, ticks `ftol(1.1^40 * 20 * 16) = 14482` (>= 9601: never counts down
  until the unit dies or the mission ends: a quirk of the u16 limit). At `L = 10`: `ftol(2.5937 * 320) = 829` ticks.
- **Haste** `L = 30`: value 3, ticks `ftol(1.1^30 * 10 * 16) = 2791`; a monster's speed `+0x8c` rises by 3 at once and drops by 3 when it ends.
- **Poison Cloud** `L = 30`: value `ftol(-2 * 1.667) = -3`; a unit with water protection 50 loses `ftol(3 * 50 / 100.0 + 0.5) = 2` HP per pulse,
  16 pulses (ticks 128, 120 .. 8) when it leaves the cloud at once. The cloud lives `5*16 + 480/10 = 128` ticks and re-applies every 16.
- **Stone Curse** `L = 50` learned: `50 * 240 * 2 / 100 = 240` ticks, then `rand(0..240 * (100 - pe) / 100)` on the creature.

## 9. Engine (`engine/sim/effects.py`)

| Exe | Engine |
|---|---|
| effect object | `world.Effect` (id, kind, flags, value, ticks, caster) in `Unit.effects` (list order = the exe's list) |
| `+0x144` | `Unit.effect_mask`; `Unit.hidden` mirrors bit 12, `Unit.bless` / `Unit.curse` the values of the 20 / 28 effects (the chances `take_hit` reads) |
| `FUN_0051ce12` / `51cc9f` / `51d175` / `51d337` / `51d436` | `effects.apply` / `tick` (`tick_unit` = the list pass) / `_pulse` / `_undo` / `_switch` + `_recompute` |
| monster `+0x8c` / `+0xc0` / `+0xbe` / `+0xa4`; human bonus `+0xd8` / `+0x100` / `+0xfe` / `+0xe4` / `+0x102..` | `Unit.fx` (`world.EffectStats`): `movement.unit_speed` (and so the human turn rate), `combatstats.unit_combat_stats(fx=)` (a human's bonus enters the recompute; a monster's deltas are applied to its cached record and kept on a rebuild), `ai._scan_range` (`effects.scan_range`, byte wrap) |
| switch case + carrier choice of `FUN_00519db8` | `effects.make_effect`, `effects.release` (called by `spells.cast_release` / `cast_release_cell`; returns None for what it does not build) |
| point / area / field carriers | `Carrier(kind="point", effect=...)`, `kind="area"` (mode 0 / 1) and `"field"` with `centre`, `radius`, `mode`, `life`, `stamped`, `direction`, `step`; a missile with a `centre` lands as its area (`effects.landed`); `spells.carrier_system` dispatches (`point_tick`, `area_tick`, `field_tick`, `reach`) |
| cell record effect slots, `FUN_00550a96` | `World.cell_fx` ((x, y) -> 6 carrier uids), `World.set_cell_fx`: the record's saved cost byte `<< 2` per used slot into `World.cost` (copied before the first write), Wall of Earth `| 5` in `World._cell_value` / `rebuild_block` |
| Brain order 4 (Stone Curse) | `effects.stone_check` (after the sleep pre-check; a step in progress, the engine's form of brain order 3, finishes first) and `effects.brain_stone` in `movement._tick_inner` |
| `FUN_0057977a(.., area)` | `ai.on_hit(.., area=True)` / `declare_war(.., area, victim)`, counter `AiState.area_hits` (`brain+0xac`) |
| `FUN_00513128(victim, dmg, spell)` | `xp.damage_credit(.., spell=)`: spell damage pays a mage into the sphere, a non-mage nothing (also fixed for the phase I missiles and Drain Life) |
| trigger check 25 (`0x5777d3`), instants 29 / 30 | `effects.tile_layer` / `set_tile_duration` / `set_unit_duration` (§6.5) |
| trigger check 26 (`0x577857`) | reads `Unit.effect_mask` |

Dumps: a unit's `effects` entry, the carriers' area fields, `cell_fx` and `AiState.area_hits` are written only when present, so the older goldens
are unchanged (tested). DECISIONS (INFERRED): a removed caster counts as gone for the Poison credit and the carriers' attacker bookkeeping;
a human's absorption clamp is applied to the effects' part of the bonus word (no spell lowers it); when a human's speed would turn negative
the bonus is zeroed at once (the exe keeps the negative value until the next recompute); a cell's position is its centre; structures are
not targets; the server scorch bit and the client effect messages are not modelled (the client burnt-ground bit of Wall of Fire is: `World.scorch`). Tests: `tests/test_engine_effects.py` (synthetic: handlers, merge,
cancel, expiry, 0x2581, Poison, monster / scan hooks, Invisibility, Stone Curse, point / area / field carriers, cell slots and costs, walls,
Fire Ball, Blizzard / Acid timing, Teleport, the area war counter, the AI's single Shield, a deterministic fight), `tests/test_engine_effects_maps.py`
(install: data.bin values, the human hooks on a map 73 knight), `tests/test_engine_ai_casting_maps.py` (map 73 casters: one Shield per mage,
Bless on friends, nothing unbuilt).

## 10. Cell record effects ("traps") and the hidden caster (CONFIRMED, engine `engine/sim/traps.py`)

**The record.** Bytes `+0x34..+0x39` of the cell record ([unit-struct](unit-struct.md#cell-record-effect-confirmed)) hold one effect
`(spell, power, sx, sy, tx, ty)`. Writer `FUN_0055ba36(cell, effect)`: copies the 6 bytes, making the record when missing (`FUN_005508a0`);
**refused** when the live layer has bit 0 at the cell (static block: water, rock, structure ground, border). Nothing clears it, and
`FUN_005513b6` counts a record with `+0x34 != 0` as non-empty, so it outlives every unit that passes: **a trap fires every time**. Feeders:

| Feeder | Cell | Effect |
|---|---|---|
| map section 9 (`FUN_00562745`, `0x5641c5`-`0x564280`): unclaimed record, `a` or `b` != 0, kind `u16 +0x10` < 4 | `(a, b)` low bytes | `(c & 0xff, byte +0x18 = (c >> 16) & 0xff, pair0.id, pair0.value, pair1.id, pair1.value)`, low bytes (pairs: 6-byte elements, `FUN_0054ce40`) |
| instant 25 "Set trap" (`FUN_0057847e`) | `(n2, n3)` | `(n0, n1, n2, n3, n2, n3)` when `n4 == 0`, else `(n0, n1, n4, n5, n6, n7)` |

Census (all 46 maps): section 9: 76.alm 15 spell traps (Fire Arrow / Fire Ball / Ice Missile / Poison Cloud, power 50..100, source = target =
the trap cell), 93-96 16 Teleport records (spell 23, power 100; 93's `(98, 72)` lies on a blocked cell and is refused; several point at their own
cell, which can never teleport, below); instant 25: 53 (`(15, 121)` -> `(13, 22)`), 93-96 (two each), all Teleport. No unit starts on a trap cell.

**Readers.**
1. `FUN_005503af` (the per-cell occupant place of `FUN_0055020a`: entering a cell at a border crossing, a teleport, placement): for movement
   classes 1 and 2 only (class 3 takes `0x5505c3`, no effect test), for each footprint cell in the loop order, **before** the slot test (so it
   fires also on the cell where a lost first-come race stops the loop). Spell `0x17`: `brain+0xb0 := ty << 8 | tx`. Any other spell:
   `FUN_00519408` (a constant 1, called directly) then `FUN_004f0832(sx, sy, unit, spell, power)`: a hidden caster casts at the unit (the cell
   branch `FUN_004f086f` there is dead).
2. `FUN_00555b38` at the step end (unit at a centre, after the `FUN_0055be86` pair and the list clear, `0x555c22`-`0x555c72`): the record of the
   unit's own cell, if spell `0x17`: `FUN_0055a96c(unit, tx, ty)` now. No class test: a flyer is teleported here too (its place never sets
   `+0xb0`).
3. The Brain tick under brain order 0 at a centre, before the mode switch (`0x56e01b`-`0x56e087`): `+0xb0 != 0` -> `FUN_0055a96c(unit, lo, hi)`,
   then `+0xb0 := 0` whatever the result.

`FUN_0055a96c` (also the Teleport spell and instant 27): free test `FUN_0055a928` = `FUN_0055c5a0(unit, cell, 0)` and `(.., 1)` (the footprint
against the mover mask in the static and the live layer; the unit's own stamps count, so its own cell is never free); not free: return,
nothing changes. Else release (`FUN_00553891`), position = the cell centre (`FUN_0054fbf7`), place (`FUN_0055020a`, which reads the target's
record), then **`FUN_0056dba1` = cancel + stand** (order `0xc`, anchor the new cell, Brain mode 0, `brain+0x50 := 0`, so a move group's pass
restarts the unit towards its destination). Timeline of a walker crossing a Teleport trap: border crossing -> `+0xb0` set; step end -> teleported
and standing; next tick the Brain tick tries `+0xb0` again (its own cell: not free) and clears it. A trap whose target is blocked or occupied
leaves the walk going; `+0xb0` is dropped at the next centre.

**The hidden caster** `FUN_004f06ac(sx, sy, spell, power)`: a 0x208 monster object (constructor `FUN_0050dc2b`, vtable `0x5d0eb0`, slot `0x18` =
`FUN_0050f12c`), id `+4 = 0`, no player, position = the source cell's centre (`FUN_0054f9b9`; it is never placed in the cell slots: it blocks
nothing), the defaults of `FUN_0050ec60` (HP 30, order `0xb`), Mind `+0x88 = 30`, the spell's sphere skill word = power (level = power - 30 + 30),
a one-spell book (`FUN_0051906d`, `FUN_0051c29e`), `+0x64` = the spell, windup `+0x134 = 1`, recovery `+0x135 = 1`; the constructor
`FUN_0050e173` draws `rand(128)` (facing) and sets `+0x136 = 1`. The caller sets state `0xd` + target `+0x5c` (`FUN_004f0832`: traps, instant
24) or state `0xe` + cell `+0x60/+0x61` (`FUN_004f086f`: instant 21, power `n5`, 99 when 0). It joins the transient list `server+0x2c`, ticked
in step 2 of every server tick (`FUN_004f04cf`: after the command drain, before the area effects and the creatures, [simulation §2](simulation.md#2-update-order-inside-a-server-tick)),
deleted after the tick in which `+0x136` is set. Its tick is the creature tick: the state switch's cast phases (spells.md 9c.2): phase 0
start (no mana: not a mage), release one tick later (`FUN_00519d7f` / `FUN_00519db8`, so the missile starts at the source cell), recovery
`1 + rand(0..3) + complication`, then done. A start that fails (target gone) leaves `+0x136` at 1: deleted after one tick. Timeline of a spell
trap: tick T (the victim's creature tick) the caster is made; T+1 the cast starts; T+2 the release (a missile from the trap cell itself
lands at once: flight 0).

**Engine.** `World.cell_effects` ((x, y) -> 6 bytes, dumped while non-empty), `traps.set_record` (installs the reader `CellSlots.on_enter`,
called by `CellSlots.place` per footprint cell before the slot test), `traps.load_map` (section 9, run by `triggers.enable` = the compiler),
instant 25 / 21 / 24 in `triggers.run_instant`; `Unit.teleport_to` (`brain+0xb0`, dumped while set); `traps.step_end` and `traps.pending` in
`movement._tick_inner`; `World.transients` + `traps.transient_system` (between the selection and the carrier systems; dumped while non-empty);
`effects.teleport` now ends with the stand (`FUN_0056dba1`, `0x55a9f8`; it was missing). DECISIONS (INFERRED): the hidden caster's Brain tick
does nothing (order `0xb`, mode 0, no group; not traced); its carriers name caster 0, which no lookup finds, so it is no attacker (no last-attacker
mark, no XP, no AI reaction), as for a removed caster; `FUN_00511959` in its constructor (called only for a non-empty name list) is not reached.
Tests: `tests/test_engine_traps.py` (synthetic: refusal, layout, teleport timeline, failed teleport, repeat, flyer, spell trap timeline and level,
dropped target, footprint, instant 21; install: maps 93 (section 9 teleport, a walker through `(21, 20)`), 76 (a Fire Arrow trap), 53 (instant 25)).

## 11. Prismatic Spray chain and the Lightning / Spray bolts (CONFIRMED unless tagged; engine `spells.spray_chain`, `ai.spray_targets`, `effects.spawn_bolt`, `lights.bolt_*`)

**Cast (server).** `FUN_00519998` phase 0, spell 11 (`0x519b8e`, no target test): `FUN_00519483(caster)` recomputes the wrapper (`FUN_005195b1`) from the caster's
own level (`skill[sphere] - 30 + Mind`; wrapper `+9` = range, + `L/30`), then `FUN_00519c04(caster, target)`: `L` = the item's `castSpell` count (`unit+0x68 != 0`,
`')'` effect word `+0x42`) else `FUN_00511913(sphere)`; `count = min(7, L/20 + 2)` (so 2..7); `FUN_00579ddf(caster, target, list, count, wrapper+9)` fills the
list; `FUN_00504391` sends the client message (below); then `FUN_00519db8(caster, unit, 0, 0)` runs **at once on every list entry** (cast XP per call
for a mage, Lightning-style missile carrier with the 10-tick server flight, `0x51be87`). Mana is spent once (`0x5199d6`). The release `FUN_00519d7f` skips spell 11.
Engine: `spells.cast_start` -> `spray_chain` (`SpellCast.chain`), `release_on` (the former body of `cast_release`).

**The list `FUN_00579ddf` (this = order manager `0x66832c`, `+0xa50` = pathing).** (1) list cleared; (2) `FUN_0056e6b8(caster, target, 0)` first
([ai §8](ai.md#8-hit-reaction-fun_0056e6b8attacker-victim-0-confirmed), with the AI on); (3) `FUN_00571c4d(caster+0x70)` builds the group's pool ([ai §4](ai.md): at-war
units on the cells the group sees, creation order, hidden ones need a detector; the dying only when no living one is there); empty pool: the list is just the target;
(4) score `FUN_00579d62(caster, u)` = `(FUN_00556dcd(caster, u) & 0xff) << 8` + `FUN_0055aa21(caster facing, FUN_005568e4(caster, u))` as a word (the gap level of
[ai §4](ai.md) and the turn of the score `FUN_005711ea`); keep when `score <= wrapper+9 << 8` (gap level below the range, or equal with no turn); a second pool `+0xa88`
(dead list) is scored `dist << 8` but is always empty here ([ai §4](ai.md) step 6); (5) `count` rounds: best = `0xfffa`, each unit with a score strictly below the best
becomes the best (ties keep the earlier unit; best is stored as a word), then the picked unit's score is set to `0xffdc`; (6) list = target, then each pick that is
not the target and has index and word below `0xfde8`; (7) cut to `count` entries from the tail (`FUN_0057b080` = remove tail). So the target always leads and
takes a round when it is in the pool. Engine `ai.spray_targets` / `spray_distance`.

**Client messages.** `FUN_00504391` writes `0x8a` (`msg+0xa` u32 = list length + 1, `+0xe` u16 = caster id, `+0x10..` the target ids, `unit+4` of each); a caster
whose unit `+0xe` (type word) is 0, i.e. the hidden caster of a script ([§10](#10-cell-record-effects-traps-and-the-hidden-caster-confirmed-engine-enginesimtrapspy)), sends `0x8c` with the caster's cell instead
(`x | y << 8`). Handler `0x8a` (`0x4156cf`): the caster's view gets action 8, `+0xa8` = its type's `+0x68`, `+0x9c = 0`, list `+0xb0` = the ids, `+0x8e` = the first id,
`+0xac = 0x1e`, unless it is already busy (`+0xa8 != 0`). Handler `0x8c` (`0x415812`) instead creates projectile 30 at that cell at once (lifetime 0xd, age -1). Lightning
sends the plain `0x86` ([spells §9c](../data/spells.md); handler `0x4151c1`): view `+0xac` = 28, `+0x8e` = the target id, **no list** (`+0xb0` is not touched).

**The bolt object (`FUN_0046707e`, cast action 8 at the unit type's ShootDelay frame).** The cast message (`0x8a`, or the plain `0x86` of Lightning) starts the caster's action 8 (`obj+0x9c = 0`) unless the view is busy (`+0xa8 != 0`, `0x415258`); the action's tick `n` fires the event when `n == ShootDelay` (`UnitSet.attack_events("cast")["release"]`, [animation §2.4](../formats/animation.md#24-attack-events-hit-and-release-frames); data: mage / mage_st 8, necromant / druid / mainnecro 6, dragon 8; a delay at or past the attack sequence never fires). The routine first looks up the view of the target id `+0x8e` and **returns, making nothing, when that lookup fails** (`0x4670d9`). It creates projectile `view+0xac` (28 / 30) at the caster's **shoot origin** (CONFIRMED `0x46718c`-`0x4672e0`): with a ShootOffset table on the unit type (`FUN_0041e1d0` non-empty, and projectile id != 0x36) `x = view+0x5c - (CenterX - SO[k]) * 8`, `y = view+0x60 - (CenterY - SO[k+1]) * 8` with `k = (direction - 8) & 14`, direction = `view+0x70` = `facing >> 4` (`view+0x5c / +0x60` = footprint centre in 1/256 cell = position + (TileSize - 1) * 128, units.reg `TileSize`, CONFIRMED `0x4631ce`; the engine used 1 for the 2 x 2 / 3 x 3 casters before K9's follow-up); else `centre - CenterX + (Sel+0x8c - Sel+0x84) / 2` (INFERRED field names: SelectionX2 - X1, an almost unmoved point). The projectile's altitude `obj+0x10` stays 0 (constructor), the ground relief `obj+0x6c` is the one `FUN_0046025d` interpolates at the origin. It copies the target id `+0x8e` and the id list `+0xb0` (`FUN_0046dbc0` = word-vector assign, the caster's list is **not** cleared), lifetime `+0xa8 = 0xd` for 0x1c / 0x1e (the age starts at 0, so the first drawn age is 1; ages 1..13, removed when `+0xa8` is 0 on entry), phase `+0x74` by age 4 3 2 1 0 1 2 1 0 1 2 3 4 (`FUN_0046c1d0`: index `age - 1`, above 12 the phase is left alone); no flight, no move.
Each tick `FUN_0046d46a` (vtable `+0x50`) rebuilds the point list `+0x11c` (8-byte records: x word, y word, word 0, **variant byte at `+6`**, byte 0; `FUN_004c9ba0`) with a temporary polyline object per line (class `FUN_004c78b0`): Lightning one line from `(obj+0x54, obj+0x58 - obj+0x6c - obj+0x10)` (the projectile's own screen position, i.e. the shoot origin minus its ground relief) to `(view+0x64, view+0x68 - view+0x6c - view+0x10)` of the target (its footprint centre minus its ground relief and its altitude `U+0x10`: **the foot of the target, no chest height**; skipped when the view lookup fails), variant 0x1c; the Spray one line per list entry with `index % 7` as the variant, the temporary object cleared (`FUN_0046dc80`) after each. Draw (`FUN_0046cb7b` cases 0x1c / 0x1e): one sprite at every point, `(x - 8, y - 8)`, frame `phase` (28) or `phase + 5 * variant` (30). Light (`FUN_0046d0ef`): `phase * 10` into the 2 x 2 vertices of each point's cell `(x >> 5, FUN_00417f31(x, y))` ([lighting §3](../mechanics/lighting.md)). **The old reading "Lightning has no points, no light and no body" was wrong**: its single line is built from the target id alone. The stale `+0xb0` list of an earlier Spray never reaches Lightning (case 0x1c does not read it).

**The line (`FUN_004c8863` build, `FUN_004c819d` control line, `FUN_004c8069` spline; CONFIRMED asm, engine `engine/view/boltline.py`).** Doubles; `rand` is the C runtime generator `FUN_00583290` (`holdrand * 214013 + 2531011`, `(holdrand >> 16) & 0x7fff`, the thread's seed set once from `timeGetTime` at `0x45ae54` / `0x51fa02` / `0x57af92`): **not the game's own RNG stream and not reproducible**, so the engine takes a repeatable generator per (bolt, tick, line) (`lights.bolt_seed`, never `world.rng`).
1. *Build* (`FUN_004c8863(x1, y1, x2, y2, variant)`): `L = hypot(x2 - x1, y2 - y1)` (`FUN_00584ea0`, stored `+0x60`); the control line is made for the **horizontal** `(x1, y1) .. (x1 + L, y1)`; `(ux, uy) = (dx, dy) / L`; with `(x0, y0)` = the first sample, every sample `(x, y)` becomes `X = trunc((x - x0) * ux + x0 - (y - y0) * uy)`, `Y = trunc((y - y0) * ux + ((x - x0) * uy + y0))` (`FUN_00582c0c` = `fistp`, round toward zero) and a record `(X, Y, 0, variant, 0)`. L = 0: no sample (the exe would divide by zero).
2. *Control line* (`FUN_004c819d(x1, y1, x2, y2)`, `L` from `+0x60`; `+0x58 = 0.03 * L`): the lists are cleared; `s = +1` if `rand & 1` else `-1`; arrays `t = [0]`, `off = [0]`, `acc = cum = 0`; repeat { `jump = (rand % 7) * s`; `step = (rand % 50) * 0.01`; if `|jump| > 2` **and** `step > 0.15`: `cum += jump` clamped to +-3, `off += [cum]`, `acc += step`, `t += [acc]`, `s = -s` } while `acc < 0.7` (two draws every iteration, kept or not); if the last `t >= 1.0` it is removed from both arrays; append `t = 1`, `off = 0`. Points: `P0 = (x1, y1)`; for `i = 1 .. n-2`: `Q_i = (t_i * dx + x1, off_i * 0.03 * L + (t_i * dy + y1))`; the list is `P0, Q_1, mid(Q_1, Q_2), Q_2, mid(Q_2, Q_3), Q_3, ..., Q_{n-2}, (x2, y2)` (`mid(P, Q)` = `(Q - P) / 2 + P` against the **last appended** point). The spline `FUN_004c8069` is run on the triples (0,1,2), (2,3,4), ...: the quadratic `y = (A x + B) x + C` through the three points (coefficients from the three `x_i^2` and the determinant `D = (x3 - x2) x1^2 + (x1 - x3) x2^2 + (x2 - x1) x3^2`, `A = -((y3 - y2) x1 + (y1 - y3) x2 + (y2 - y1) x3) / D`, `B = ((y3 - y2) x1^2 + ...) / D`, `C = -(...) / D`) sampled at `x = xa, xa + 6, ...` while `x < xc` (the line ends up to 6 px short of the target). **Retry**: if any sample's `|y - y1| > 0.15 * L` the whole line is discarded and rebuilt (recursive call; fresh draws). The engine caps the retries at 200 (DECISION).
3. The x87 keeps 80-bit intermediates: a sample can differ from the engine's by one pixel in a rare rounding case (INFERRED, not observable).

**Cell-form Spray (no target) = a crash in the exe (CONFIRMED asm).** `FUN_00519998` reaches spell 11 with `target = 0` for a cell cast (state `0xe`): `FUN_00519c04` -> `FUN_00579ddf(caster, 0, ...)` seeds the list with the null target (`0x57a144` / `0x579e3e` `AddTail(target)`), after `FUN_0056e6b8(caster, 0, 0)` has already read `[victim + 0x1c4]` (`0x56e6c6`: access violation at `0x1c4`); even past that, `FUN_00504391` reads `[entry + 4]` of every list entry (`0x504440`). So no valid cell-form Spray exists; the engine keeps a counted no-op (`stub_release`). The **`0x8b` / `0x8c` forms are something else** (K9 follow-up: `FUN_005041d6` / `FUN_005042ba` pick `0x8b` instead of `0x86` exactly when the caster's type word `+0xe` is 0, so a hidden caster's missile spell is drawn from its cell at once with the message's flight ticks, [rendering](rendering.md#arrows-and-shots-k9)): the `0x8c` form is sent when the *caster's* type word is 0 (the hidden caster of a script / trap, [§10](#10-cell-record-effects-traps-and-the-hidden-caster-confirmed-engine-enginesimtrapspy)) with a unit target: `msg+0xe` = the caster's cell (`x | y << 8`), ids from `+0x10`; handler `0x415812` makes projectile 30 **at once** on the cell centre `(256 x + 128, 256 y + 128)`, altitude 0, `+0x8e` = the first id, the list copied, age `+0x9c = -1` (drawn ages 0 .. 12, phase 0 at age 0), lifetime 13, no ShootDelay and no ShootOffset. A hidden caster's Lightning (`0x86`) finds no caster view (`0x4151f8` -> `0x415f53`): no bolt.

**Timing (K9 follow-up, CONFIRMED `FUN_00488aa1`: server step `0x4f08c0`, then the message loop `0x40d9b2`, then the view tick `0x401`).** An object made in step `t` (cast action tick, or a message) is ticked once in that same step, so the frame drawn after it, when the engine's `world.tick` is already `t + 1`, shows exe age 1 (cast action) or age 0 (the message-made forms, age -1 at creation): `lights.bolt_age(b, tick) = tick - born + age0` for `tick in born + 1 .. born + 13`. Before this the bolts, the fire explosions and the one-shot sprites were drawn one frame early in the animation (first frame skipped, last frame at the end of the life).

**Engine.** `World.bolts` (`Bolt`: `born` may lie in the future, `age0`; client only, not dumped), `effects.spawn_bolt` (called by `spells.cast_start`, the message time: `born = tick + ShootDelay`, `effects.shoot_delay`; hidden caster: at once, `age0 = -1`), `effects.shoot_origin`, `effects.bolt_system` (drops a bolt after 13 ticks, and on the spawn tick when the first target is gone), `lights.bolt_age` / `bolt_phase` / `bolt_segments` (the exact line, `boltline.build`) / `bolt_cells` / `pick_row` (the row finder, CONFIRMED asm), `lights.light_map` (the bolt light), `drawlist._bolts`; the carriers of spells 10 / 11 draw no flying missile. CONFIRMED (K9 follow-up, `FUN_0046617c`): the caster's position and facing may be sampled at the cast start although the exe samples them at the ShootDelay tick, because the cast action's tick (case 8) only counts and fires its events (ShootDelay `+0x5c`, AttackDelay `+0x60`, Teleport at tick 0): it writes neither the position (`+8 / +0xc`, only the render copy `+0x2c / +0x30`) nor the facing `+0x70` (cases 1, 3, 5, 7 do), and a move / turn / attack message cannot replace the running action (the starts test `+0xa8 == 0`, `0x415258`); the shoot action (case 7) copies the facing saved at the message `+0x8d` every tick, also constant. INFERRED (DECISIONS): a caster still busy in an earlier action ignores the message (not modelled), the Selection field names of the empty-ShootOffset fallback, the retry cap, the repeatable generator, the x87 rounding. Tests: `tests/test_engine_bolts.py`.

## Open questions

- The structure branch of the carriers (`vtable +0x34`, area cells' structure `FUN_00559b7f`): structures as targets are not modelled.
- Human scan: Darkness adds to `+0xa4` directly *and* to the bonus `+0xe4`, so until the next recompute the human loses twice the value (engine: the direct part is kept until the next stat-switch recompute; other recompute triggers such as level-ups are INFERRED to reset it too and are not hooked).

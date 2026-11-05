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
| `+0x0e` | u16 | client effect id `2n + 8` (unit-attached sprite, [palettes](../formats/palettes.md)) | CONFIRMED |
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
- mode 0 (`+0x50 == 0`: **Fire Ball**) -> `FUN_00518833` once: for every cell of the square `|dx|, |dy| <= r` round the centre, `FUN_00518681` on
  the ground occupant (`rec+4`), the air occupant (`rec+8`) and the structure; a damage effect with spread > 0 also clears the cell
  effects (`FUN_005189b5`, §6.4) and scorches the ground (`FUN_00559c28`, dirt bit; drawing only); done.
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

The cell record is [unit-struct: cell record](unit-struct.md#cell-record-effect-confirmed). 
Record slots `rec+0x14 + 4k`, k by spell (`FUN_00518ba3`): Wall of Fire 3 -> 0, Poison Cloud 6 -> 2, Wall of Earth 17 -> 3, Light 15 -> 4,
Darkness 14 -> 5 (others: error "Invalid Area Effect", slot 0). The record exists while any slot is used (`0x20` bit of the static byte);
it saved the cost and block bytes at creation (`FUN_005508a0`) and restores them on deletion (`FUN_00550966`). After every stamp / unstamp
`FUN_00550a96` rebuilds the cell: **cost byte `<<= 2` (u8) once per used slot** (`FUN_0055f350` returns 1), and a Wall of Earth slot sets
block bits `| 5` in the static and the live layer (the cell is blocked like an object). Interactions when a cell is stamped
(`FUN_005189b5`): fire (2, 3) removes a Poison Cloud from the cell (slot 2); Poison on a fire-wall cell (slot 0) removes itself; Light and
Darkness on the same cell remove each other **and** themselves. Unstamp (`FUN_0055a533`) clears the slot only when it holds this carrier.
CONFIRMED.

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
| trigger check 26 (`0x577857`) | reads `Unit.effect_mask` |

Dumps: a unit's `effects` entry, the carriers' area fields, `cell_fx` and `AiState.area_hits` are written only when present, so the older goldens
are unchanged (tested). DECISIONS (INFERRED): a removed caster counts as gone for the Poison credit and the carriers' attacker bookkeeping;
a human's absorption clamp is applied to the effects' part of the bonus word (no spell lowers it); when a human's speed would turn negative
the bonus is zeroed at once (the exe keeps the negative value until the next recompute); a cell's position is its centre; structures are
not targets; the scorch (dirt) and all client messages are not modelled. Tests: `tests/test_engine_effects.py` (synthetic: handlers, merge,
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

## Open questions

- The Prismatic Spray chain `FUN_00519c04` (targets from `FUN_00579ddf(caster, target, list, min(7, L/20 + 2), range)`): not decoded; spell 11 stays a counted no-op.
- The structure branch of the carriers (`vtable +0x34`, area cells' structure `FUN_00559b7f`): structures as targets are not modelled.
- Human scan: Darkness adds to `+0xa4` directly *and* to the bonus `+0xe4`, so until the next recompute the human loses twice the value (engine: the direct part is kept until the next stat-switch recompute; other recompute triggers such as level-ups are INFERRED to reset it too and are not hooked).
- Client side: the effect messages (`FUN_005044ba`, `FUN_00504498`, cell effect `0x87` `FUN_005045a5`) and their drawing (Invisibility, Stone Curse sprite, cell sprites) are not built.

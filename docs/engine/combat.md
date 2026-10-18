# Combat (phase I1): attack order, approach, swing, hit and damage

How a unit ordered to attack an enemy walks into range, swings with the exe's timing and hurts it with the exe's formulas.
Marks as in CLAUDE.md (**CONFIRMED** = read in the GOG `allods2.exe` with REA, routine given; **INFERRED** otherwise). Exe
build: sha256 in [formats/README.md](../formats/README.md). No decompiled code here: formulas are written as math.
Ranged and spell attacks share the code up to the damage call (section 5), so they are listed where they differ; spells,
death, XP and AI retaliation are other phases (section 10). RNG: [simulation §10](simulation.md#10-rng). Struct offsets:
[unit-struct](unit-struct.md); click side: [click-to-move-research](click-to-move-research.md); stats: [units](../data/units.md),
[items](../data/items.md), [progression](../data/progression.md).

## 1. Pipeline

| Step | Exe | Engine |
|---|---|---|
| click on an enemy unit with the attack cursor -> client command `0x19` (`+0xe` = target id) | `FUN_00418cb3`, [research §1.3](click-to-move-research.md) | `AttackUnit(player_id, unit_ids, target_id)` |
| server intake: target lookup, new group, `FUN_00570946` | `0x4f52a6`..`0x4f57d3` | `orders.attack_group` |
| per member: validity matrix, order 3 (`FUN_0056d1be`) | `FUN_005711ea`, `FUN_0056d1be` | `combat.can_attack`, `combat.set_attack` |
| every 16 ticks (`tick & 15 == 6`): order executor sets Brain mode 5 | `FUN_00569321` -> `FUN_0056acc8` | `orders.group_pass` calls `combat.refresh_attack` |
| every tick: Brain mode 5: in range -> swing, else approach | `FUN_0056eab5` | `movement._tick_inner` -> `combat.attack_mode` |
| every tick: state 3 phases (start, wind-up, recovery) | `FUN_0050f12c` case 3 | `combat.swing_tick` |
| at the end of the wind-up: range test, hit roll, damage, HP | `FUN_00516c1f` -> `FUN_00516ceb` -> `FUN_00516f6f` | `combat.resolve_attack`, `combat.take_hit` |

## 2. The attack order

### 2.1 Intake (`FUN_004f515d`, CONFIRMED)

Command `0x19` has an **object target** (class 3: `0x19`, `0x1b`, `0x1e`, `0x25`). After the usual intake of the unit ids
([simulation §8.1](simulation.md#81-commands-and-intake-r-31-32-41)) the target id (`msg+0xe`, u16) is looked up in the
creature table (`FUN_0052b2bd`), else in the structure table (`FUN_0052bfa3`); neither found -> the command is dropped.
No test of the target's side, HP or visibility: a dead or friendly unit is a legal target (Ctrl+click on an own unit is a
real attack). A new group is created as for every command; `FUN_00570946(group, target)`:

1. `FUN_00570e83`: for every member `FUN_0056dbfb` (cancel: target facing := facing, state := 0, `brain+0x50 := 0`) and
   `brain+0x38 := 0` (dead field); group order := 0.
2. For every member in list order: cost `FUN_005711ea(member, target)`; **`0xffffff` -> `FUN_0056dba1`** (cancel + order `0xc`
   stand, the member stays in the group); otherwise `FUN_0056d1be(member, target)`: a member that **is** the target is stopped
   the same way (`FUN_0056dba1`); else cancel, **order := 3**, `brain+0xc := target`, `brain+0x14 := range` (`FUN_0056ac5b`),
   **`brain+0x8` (mode) := 0**, `brain+0x9` (brain order) untouched.

The group order stays 0, so the member is driven by the group pass executor (2.3), **not by Brain mode 5 at once**.

### 2.2 Validity (`FUN_005711ea`, CONFIRMED)

`0xffffff` ("cannot attack") when the matrix byte is 0. The matrix is a 4 x 4 byte table built in the constructor of the order
manager (`0x56827a`..`0x568310`, object `0x66832c`), indexed `row * 4 + column`:

| row (attacker class) \ column (target class) | 0 | 1 | 2 | 3 |
|---|--:|--:|--:|--:|
| 0 (attacker range > 1: shooters and casters) | 2 | 1 | 2 | 4 |
| 1 (movementType 1, ground) | 4 | 2 | 1 | **0** |
| 2 (movementType 2, ghost / bee) | 2 | 1 | 4 | **0** |
| 3 (movementType 3, flyer) | 2 | 1 | 2 | 4 |

Target class = its movementType (`FUN_0055f330` = vtable `+0x20`), **but 0 when it is a ground unit with range > 1**. A
shooter (`FUN_0056ac5b(attacker) > 1`) always reads row 0. Result: **melee ground units and ghosts cannot attack flyers**
(the order is refused silently: the unit just stands); everything else is allowed. The other values only weight the
computer players' target choice (cost = `gap << 8 + turn cost`, x1.5 / x0.75 for some small units, `+0x7f` when the target
has status bit `0x40000`); a player's order uses only the zero test.

### 2.3 The executor (`FUN_00569321` case 3, every 16 ticks, CONFIRMED)

At `tick & 15 == 6` (before the command drain of that tick) the group pass runs the executor of every member of a group whose
order is 0. For order 3: if the target's state is `0x10` (removed) the unit is stopped (`FUN_0056dbc6`: cancel, order `0xc`,
anchor = own cell, `brain+0x50 := 1`); then `FUN_0056acc8(unit, target)`:
- target flag `+0x4c & 8` (immune): guard scan instead (not modelled);
- monsters only: up to three special attacks (`brain+0x7c..0x84`, probabilities `+0x88..+0x90` against a raw `rand()`) may take
  over (spells: phase K);
- otherwise **Brain mode := 5, `brain+0xc := target`, `brain+0x14 := FUN_0056ac5b`** (range). Mages (`+0x4c & 4`) and
  ranged units first try a spell (`FUN_0056b059`, `FUN_0057a769`, `FUN_0056bc7b`): not modelled (INFERRED: they then fall
  back to the same mode 5).

So **a freshly ordered unit starts its attack at the next `tick & 15 == 6`**, 0 to 15 ticks after the command (the command
itself only sets order 3 and mode 0). The same executor re-sets mode 5 every 16 ticks, which undoes a mode 0 left by a
failure (2.5).

### 2.4 Range (`FUN_0056ac5b`, CONFIRMED)

`range = spell range` when the selected special `brain+0x78` names a spell the unit can pay for, else the creature byte
`+0x12c`. `+0x12c` starts at 1 and each equipped weapon adds `weapon range - 1` (`FUN_005290cc`; monsters too, weapon strings
are equipped in the monster constructor `FUN_00511959`); bows are 4-6 ([items §2](../data/items.md)).

### 2.5 End of the order

- Target state `0x10` (removed after the corpse is gone, [I2]): executor stops the unit (2.3).
- Self target: stop at once (2.1). Pathing failure (`mover+0x98`, no way to the target): Brain mode := 0, then the exe runs the
  **auto target scan** `FUN_0056ed4e` (nearest visible enemy becomes the new target, mode 6); the engine sets mode 0 only
  (DECISION, section 9), the executor restores mode 5 after at most 16 ticks.
- A new command cancels the order, but **never a swing in progress** (cancel does not touch `brain+0x9` or the phase).

## 3. Approach and swing (Brain mode 5, `FUN_0056eab5`, CONFIRMED)

Runs in the Brain tick while the brain order (`+0x9`) is 0 and mode is 5 ([unit-struct §8.2](unit-struct.md)):

```
if in_range(unit, target, range):  swing (3.3), state := 3
else:                              approach (3.4), state := 1
```

### 3.1 In range (`FUN_0055532d`)

`facing == octant(unit -> target)  and  gap(unit, target) <= range`. The at-centre test it makes first is discarded. The facing
must **equal** the octant (a multiple of 32), so a unit that arrives with another facing turns first (3.4).

`gap` (`FUN_00556dcd`, = `pathfinding.follow_distance`): with centres `c = cell*256 + sub + (size-1)*128` (`size` = token size
`vtable +0x1c`), per axis `max(|c_a - c_b| - (size_a + size_b) * 128, 0)`, then `(max over axes >> 8) + 1`: 1 = touching
(also on a diagonal), 2 = one free cell between, etc. (16-bit centres).

`octant` (`FUN_005568e4`): `dx = c_target.x - c_unit.x`, `dy` likewise (16-bit wrap). Quadrants by sign, each split with the
ratio rule `|major| < 2 |minor|` -> diagonal; result `dir8 * 32` (0 north ... clockwise); ties (`dx == 0`, `|dx| == |dy|`)
fall on the "dx <= 0" side. Equals `movement.facing_to` for adjacent cells.

### 3.2 Facing the target

`FUN_00556d78` = `FUN_00556454(unit, octant)`: the normal turn ([simulation §4.3](simulation.md)); the follow driver does it
when it finds the unit already in distance but not facing.

### 3.3 Swing start (`FUN_0056e8c3`)

Brain order := 1 (swing), `brain+0x15 := 0`, state := 3, creature `+0x5c := target` (the swing's target, fixed for its whole
length).

### 3.4 Approach (`FUN_0056ea52`)

The follow driver `FUN_0055574d(unit, target, range)` ([simulation §7.4](simulation.md#74-read-but-not-implemented-needs-ordersai-of-phase-i):
two layers, re-plan when the target cell changed or every `len/3 + 1` consumed waypoints, hop plans with the follow fallback,
turn to the target instead of planning when `gap <= range`), then state := 1; when the unit is not at a cell centre afterwards
(mid-step) brain order := 3 (step in progress) so the mode is not re-run before the step ends. No separate "give up" timer
exists: the approach ends when in range, when the planner reports no way (2.5) or when the order is replaced.

## 4. The swing (state 3, `FUN_0050f12c`, CONFIRMED)

Per tick: effects, HP test, then the **Brain tick first** (`FUN_0056dca2`), then the state switch. Brain order 1 each tick:
state := 3, `brain+0x15 += 1`, and when `brain+0x15 > 2` and the done flag `+0x136 != 0`: brain order := 0, state := 0.
State 3 uses the phase `+0x58` and the byte timer `+0x6c`:

| Phase | Tick | Action |
|---|---|---|
| 0 (start) | `A` (same tick as 3.3) | client message `0x71` (melee) / shoot message (range > 1) `FUN_00504ab8`; `+0x136 := 0`; phase := 5; timer := `+0x134` + **extra**; `extra = (d * 256 + 128) / 200` (integer) only when `d = attack_gap(unit, target) > 1` (arrows in flight; 5.1) |
| 5 (wind-up) | `A+1`.. | timer -= 1 (byte); at 0: **`FUN_00516c1f` resolves the hit (section 5)**, phase := 7, timer := `+0x135 + L + rand(0..3)` |
| 7 (recovery) | after the hit | timer -= 1; at 0: phase := 0, `+0x136 := 1` |

`L` (humans with a weapon, `+0x74`): `clamp((weapon weight + (30 - Reaction) * 5) / 12, 0, 12)` with weapon weight = `+0x4a` and
Reaction = `+0x86`, integer division truncating, applied to the clamp's argument as signed; 0 for monsters and unarmed humans.
`+0x134` / `+0x135`: monster data.bin windup / recovery; humans default 8 / 4 and the **weapon's** params 12 / 13 when not -1
(`FUN_005290cc`; monsters keep their own). The timer is a **byte**: a start value of 0 wraps to 255 ticks (INFERRED from the
byte arithmetic; reachable with recovery 0, L = 0 and rand 0).

**Timeline** for wind-up `W`, recovery timer `R = +0x135 + L + rand(0..3)` (drawn at the hit tick):

| Tick | Event |
|---|---|
| `A` | Brain mode 5 in range -> brain order 1, state 3; phase 0: message `0x71`, timer = `W` |
| `A + W` | timer reaches 0: **hit resolved, damage applied**; recovery timer = `R` |
| `A + W + R` | phase 0, done flag 1 |
| `A + W + R + 1` | Brain: `+0x15 > 2` and flag -> brain order 0, state 0 (no mode run this tick) |
| `A + W + R + 2` | mode 5 again: if still in range **and facing**, the next swing starts here (`A' = A + W + R + 2`) |

Period of a standing fight = `W + R + 2` ticks (`+0x15 > 2` is always true by then for `W + R >= 3`). Example, `Orc_Sword`
(windup 11, recovery 4, monster so `L = 0`): first hit 11 ticks after the swing starts, period `11 + (4..7) + 2 = 17..20`. The
swing is never interrupted: a new order or a moving target changes nothing until the flag is set; the hit then simply fails
the range test (5.1) when the target has left.

## 5. Hit resolution

### 5.1 The gate (`FUN_00516c1f` -> `FUN_00516ceb`, CONFIRMED)

At the end of the wind-up the target in `+0x5c` is dispatched by class: creature `FUN_00516ceb`, structure `FUN_00516ea0`
(structure HP `+0x42`, `FUN_005201b2`; not modelled), anything else logs "I don't know how to attack". For a creature:

1. Nothing happens unless target and attacker exist, both have an owner, the attacker's HP `+0x94 > 0` and
   `attack_gap(attacker, target) <= range` (`+0x12c`). **No test of the target's HP, side or visibility.**
2. `attack_gap` (`FUN_005169de`): centres as in 3.1 (16-bit), `D = max(|dx|, |dy|)` (Chebyshev, 1/256 cells),
   `D' = D - (size_a + size_b - 2) * 128`; result `1` when `D' <= 384`, else `(D' + 64) >> 8`, i.e. 1 up to `D' = 447`, 2 from 448
   (1.75 cells), 3 from 704. Size 1 vs 1: a target that stepped three quarters of a cell away is still hit.
3. `dmg = take_hit(target, record of the attacker, attacker)` (5.2); `target.HP -= dmg` (s16).
4. The attacker's weapon spell (`+0x74` with a castSpell effect, mana/charges permitting) is cast at the target when
   `dmg > 0` and the target still has HP > 0 (or the spell is type 2): spells, phase K.
5. Message `0x73` to the clients (`FUN_00504b1d` -> `FUN_00503672`) when the target had HP > 0 before **or** has HP > -10 now:
   carries the new HP (section 8).
6. Experience: slot `0x6c` of the attacker (`FUN_00513128`) when `dmg > 0`, the target had HP > 0 before and has HP > -10 after
   ([progression §4](../data/progression.md#4-xp-sources)). Not applied in I1 (section 9).

### 5.2 `take_hit` (`FUN_00516f6f`, CONFIRMED; vtable `+0x54` of every creature class)

Inputs: the attacker's **attack record** (creature `+0xa6`, 0x18 bytes) and the defender's **armour block** (`+0xbe`, 0x16 bytes).

| Record byte | Creature | Field |
|---|---|---|
| `+0x00` s16 | `+0xa6` | attack skill `T` (to-hit) |
| `+0x0e` / `+0x0f` | `+0xb4` / `+0xb5` | physical `min`, `spread` (max = min + spread) |
| `+0x10` | `+0xb6` | attack type `k` 0..5: 0 none, 1 blade, 2 axe, 3 bludgeon, 4 pike, 5 shooting (the weapon's `attack_type`) |
| `+0x11` / `+0x12` | `+0xb7` / `+0xb8` | second part `min2`, `spread2` (monster damage kind 1; zero for humans) |
| `+0x13` / `+0x14` / `+0x15` | `+0xb9` / `+0xba` / `+0xbb` | elemental `emin`, `espread`, element `e` 1..5 = fire, water, air, earth, astral |

| Defender | Creature | Field |
|---|---|---|
| defence `D` | `+0xbe` s16 | |
| absorption `Ab` | `+0xc0` s16 | |
| protection `P[e]` | `+0xc4 +2(e-1)` s16 | fire, water, air, earth, astral (`+0xc2` physical is never read) |
| resistance `Rs[k]` | `+0xce + k` u8 | percent per attack type 1..5 (monsters' `res_blade` ... `res_shooting`; `+0xce` is always 0) |
| flag `+0x4c & 8` | | immune: returns 0 at once |

Attacker flags: `+0x4c & 0x10` ("sure hit", monster damage kind 3: bats, bees, spiders) and the status effects Bless (spell
bit 20) / Curse (bit 28) with their chance `c` (`effect +0x40`). `human(a)` = attacker vtable `+0x30`.

Draw order (each `rand(n)` = `FUN_0051fa25`, [simulation §10](simulation.md#10-rng); `rand(0)` draws nothing):

```
lo, sp = min, spread
if bit7(lo) and not human(a):  lo = (lo & 0x7f) * 15;  sp = sp * 15            # large natural damage is stored /15
fixed = False
if Bless on a:  draw d1 = rand(100); if c > d1:  lo += sp;  fixed = True       # Bless: maximum damage
if Curse on a:  draw d2 = rand(100); if c > d2:  fixed = True                  # Curse: minimum damage
if not fixed:   phys = lo + rand(sp)   else  phys = lo
roll = rand(200) - 100                                                          # -100 .. +100, 201 values
hit  = (T + roll > D)  or  a.sure_hit  or  (roll >= 90)
dmg1 = phys if hit else 0
if dmg1 > 0:
    if not a.sure_hit: dmg1 -= Ab                                              # absorption; then max(dmg1, 0)
    if Rs[k] != 0:     dmg1 = trunc(dmg1 * (100 - Rs[k]) / 100 + 0.75)         # x87 doubles 100.0 and 0.75, truncation
total = dmg1
if min2 + sp2 > 0:                                                              # not gated by the hit roll
    dmg2 = min2 + rand(sp2)
    if P[water] != 0:  dmg2 = max(trunc(dmg2 * (100 - P[water]) / 100 + 0.75), 0)
    total += dmg2
if (emin + espread > 0) and ((T + roll > D) or (min + spread == 0)):            # needs the roll, not the 90 rule or sure hit
    dmg3 = emin + rand(espread)
    dmg3 = max(trunc(dmg3 * (100 - P[e]) / 100 + 0.75), 0) if P[e] != 0 else dmg3
    (e outside 1..5: error "Unknown magic damage type")
    if dmg3 > 0: total += dmg3
side effects: if attacker has a template (+0x3c != 0): defender.last_attacker := attacker (+0x40),
              defender.last_element := e if attacker is a mage (+0x4c & 4) else 0 (+0x48); AI reaction FUN_0056e6b8 (not modelled)
return max(total, 0)
```

Notes:
- The roll test is `T + roll > D` first; the `roll >= 90` rule only matters when that fails. **There is no "roll < -90 never
  hits" rule** (the branch exists but changes nothing; [spells §5](../data/spells.md) and [overview §3](../data/overview.md) said
  otherwise and are corrected). The hit chance is therefore `#{roll in [-100, 100] : T + roll > D or roll >= 90} / 201`, always
  at least 11/201 = 5.5 %.
- A weapon that deals only elemental damage (`min + spread == 0`) uses the elemental part with the roll as to-hit.
- `rand(sp)` with `sp == 0` draws nothing; `bVar` order above is the order of the draws, which matters for replay.
- Damage is an integer, can be 0 (absorption), never negative. HP is an s16.

### 5.3 Worked examples (stats from data.bin and `items.md`, weapon bonuses added as in section 6)

**A. `Orc_Sword` hits `Ogre`.** Orc_Sword: to-hit 50, damage 8..16 (min 8, spread 8), weapon Bronze Long Sword (blade, to-hit +3,
damage 4..8 = min 4, spread 4) -> record `T = 53`, `min = 12`, `spread = 12` (12..24), `k = 1`. Ogre: `D = 70`, `Ab = 5`, no
resistance. Hit when `53 + roll > 70` i.e. `roll >= 18`: 83 of 201 rolls = **41.3 %**. Damage `12 + rand(0..12) - 5` = **7..19**
(mean 13). Cycle: windup 11, recovery 4..7 -> a hit every 17..20 ticks.

**B. `Goblin_Pike` hits `Troll`.** Record `T = 15 + 1 = 16`, `min = 4 + 4 = 8`, `spread = 4 + 4 = 8`, `k = 4` (Bronze Pike is a pike). Troll:
`D = 100`, `Ab = 10`, `Rs[pike] = 30`. Hit when `16 + roll > 100` i.e. `roll >= 85`: 16 of 201 = **7.96 %** (the 90 rule is inside
it). Raw `8 + rand(0..8)` = 8..16, minus 10 -> -2..6, clamped at 0, then `trunc(x * 0.7 + 0.75)`: x = 1..6 gives 1, 2, 2, 3, 4, 4. Damage per hit
is therefore one of 0, 0, 0, 1, 2, 2, 3, 4, 4 (equally likely, `rand(8)` has 9 values): **0..4, 1/3 of the hits do nothing**.

## 6. Stats that feed the record (what the engine must build)

Both unit families end with the same layout. The record and the armour block are first filled from the unit's own data, then the
equipment bonus accumulators (`+0xd4`.., filled by equipping items and by effects) are **added** once (`FUN_005113e7`: attack
bonus block `+0xe6` into the record by `FUN_00515a6c`, armour bonus block `+0xfe` into `+0xbe` by `FUN_00515617`).

**Monsters** (init `FUN_00511959`, loader `FUN_005114f3`, CONFIRMED structure; the loader reads the data.bin params in order):
`T` = to-hit; physical `min`/`spread` = `damage_min`, `damage_max - damage_min` (or `/15` scaled with bit 7 when `min >= 128` or
`spread > min + 255`); damage kind 1 -> `min2/spread2`, kind 2 -> `emin/espread` stored negated (unused by the data), kind 3 ->
sure-hit flag and the physical bytes; `D`, `Ab`, `P[1..5]`, `Rs[1..5]` from the template. Then **the equipment strings are
equipped before the merge** (`FUN_005290cc` for the weapon): the weapon adds its `damage_min`/`spread`, `to_hit`, `defence` to the
bonus block, sets the attack type `k`, adds `range - 1` to `+0x12c`, and its element bytes replace the elemental bytes; other items
add their armour bonuses and their modifier effects (`defence`, `absorbtion`, `protection*`, `toHit`, `damage*`, attributes) by
`FUN_0051d436`. Windup / recovery stay the template's. The merge is **byte arithmetic** (`min`, `spread` are u8 sums): for a monster whose damage was
stored scaled (bit 7 set, tiers 5 of the big monsters) the weapon's `min` / `spread` are added to the scaled byte and therefore
count x15 as well (Orc_Sword.5, 262..517, weapon +9 / +9: stored 0x91 / 17 -> 0x9a / 26 -> 390..780). **Consequence:** a monster hits for
template damage **plus** its weapon (Orc_Sword 12..24, not 8..16) and its attacks carry the weapon's type, so `res_*` applies. CONFIRMED order; whether the designers' numbers
already include the weapon is not knowable from the exe: VERIFY IN GAME (section 11, item 1).

**Humans** (recompute `FUN_0051366b`, [progression §3](../data/progression.md#3-what-a-skill-up-changes)): record base `T = ftol((1.1^Body +
1.1^Reaction) / 5)`, `min = spread = ftol(1.1^Body / 20)`; skills `+0xa8+2s` copied from the permanent skills, clamped to 100, plus the
skill bonus block `+0xe8`; weapon school `k != 0` -> `T += 3 * skill[k]`, `min += skill[k] / 5`; elemental bytes zero (the bonus block
supplies them); `D = Reaction / 3`; `P[e] = Spirit / 2` for e = 1..5; `Ab = 0`; `Rs = 0`; then the merge, then `P[e] := clamp(min(P[e],
Spirit/2 + 70), 0, 100)`. Equipment (strings of the template, slot 0 weapon, 1 shield, 2-9 armour, [items §9](../data/items.md)) sets the
weapon type, adds weapon `damage_min`/`spread`/`to_hit`/`defence`, armour `defence`/`absorption`, and the modifier effects of every piece
(kind = data.bin stat index: 12 toHit `+0xe6`; 13, 43, 49 damage min `+0xf4`; 14 damage max `+0xf5`; 15 defence, 16 absorption, 20-25
protections into block B (`+0xfe`..), 44-48 elemental damage (min, spread, element); 2-5 attributes). Weapon `range` raises `+0x12c`;
weapon windup / recovery replace `+0x134` / `+0x135`.

Unmodelled effect kinds are listed in section 10.

## 7. Engine mapping

Files: `engine/rng.py`, `engine/sim/combatstats.py`, `engine/sim/combat.py`, `engine/sim/movement.py` (creature tick `_tick_unit`, `follow_drive`),
`engine/sim/orders.py` (`attack_group`, `_pass_orders`), `engine/view/damage.py`, tests `test_engine_rng`, `_combatstats`, `_combat_formulas`, `_combat`,
`_combat_data`, `_combat_window`, `_damage_numbers`. Brain order 3 (a step in progress) is `mover.step_ticks`; the swing is `Unit.brain_order == 1`.

| Piece | Place |
|---|---|
| `Rng` | `engine/rng.py` (layer 3, so `World` can own it; re-exported by `engine/sim/rng.py`), `World.rng` |
| record / block / `take_hit` / gaps / octant / timers: pure functions | `engine/sim/combat.py` |
| stat builder (template + equipment strings + skills -> record, block, range, windup) | `engine/sim/combatstats.py` |
| order 3 setup, executor, Brain mode 5, swing phases | `engine/sim/combat.py`, hooked from `orders.py` and `movement.py` |
| follow driver | `engine/sim/movement.py` (`_follow_drive`, uses `pathfinding.plan_dynamic(follow=)`, `follow_distance`) |
| command | `AttackUnit` in `engine/sim/commands.py` |
| cursor, click, damage numbers | `engine/ui/`, `engine/view/`, backend |

## 8. Client side

- Message `0x71` (melee start): unit id, direction; the client starts the attack animation at once (`AttackAnim` ticks, hit frame at
  `AttackDelay`, [animation §3.4, §5.3](../formats/animation.md)); a second message while one plays only logs "Overriding ...".
  The server's hit is `W` ticks after it (section 4).
- Message `0x73` ("Take damage"): carries the target's new HP; the client sets the HP and, when the **"Flying damage" option**
  (`view+0xabc`, **default on**, registry `GameOptions\FlyingHP`, toggled by **Ctrl+L**, message `main.txt` `0x66`/`0x67`) is on and the new
  HP is below the old, creates a floating number `old HP - new HP` (`FUN_0045c4ea`): text `%d` in the font of the unit's owner colour
  (ramp `0x61fac8 + 32 * owner colour`), start offset `x = +16 * size` for a unit of the local player or `-16 * size` otherwise,
  `y = -48 * size` (above the unit's draw height), each view tick (`+1` per sim tick) `y -= 2` and `x += 1` (local player's unit) or `x -= 1`;
  removed after 1000 ms of wall time; two numbers for the same unit in the same view tick are summed; not drawn while the unit is
  hidden. The engine draws these numbers by default (the original does) and keeps the debug log behind `--debug combat`.
- Attack cursor over an enemy: `sattack` (existing cursor table); over a structure or ground it stays a move ([research §1.3](click-to-move-research.md)).

## 9. Decisions (I1)

1. **HP clamp:** death is I2. `take_hit` is exact, HP is stored as the exe does (s16, may go below 0 internally); the engine clamps
   it at 0, logs `died` once, and an order 3 whose target has HP <= 0 stops at once (the exe keeps hitting the corpse until it is removed:
   I2 restores that).
2. **Retaliation, XP, weapon spells, mage spells, structure targets, ranged hit sound/arrows:** not in I1 (section 10).
3. **Pathing failure under order 3:** mode 0 (no auto scan), restored by the executor.
4. **Difficulty:** the map-load tweak of monster to-hit/defence (`[0x6044c4+0xd8]`, [unit-struct §1](unit-struct.md)) is not applied
   (normal difficulty, mode 2 = skip).
5. **Seed:** per game, explicit (section 2 of simulation §10).
6. **Ranged attacks** (range > 1) use the same code: wind-up + `extra`, no projectile in the simulation; the visual arrow is a view matter (not drawn yet).
7. **Stats are built lazily** (`combat_stats(world, unit)`, from `Unit.stats`, `World.item_table`, `Unit.skills`) and cached in `Unit.combat`; a skill-up or an
   equipment change must clear it (progression hook, later). A unit without a template fights with all-zero stats.
8. **Units without HP get no Brain tick** (`_tick_unit` returns): death states are I2.
9. **Intake** creates the group (and moves the members into it) before the target lookup, as the exe does; a command for an unknown or structure target
   therefore leaves the orders untouched but changes the groups.

## 10. Not modelled (kept for later phases)

Death, corpse, removal and XP (I2); AI reaction `FUN_0056e6b8` (defender alert message, `brain+0x54/+0x58/+0x94`), the guard scan and auto
target scan (`FUN_0056a1fb`, `FUN_0056ed4e`), special-attack rolls (`FUN_0056a981`), mage casting (`FUN_0056b059`); effects: Bless / Curse
bits (the `take_hit` inputs exist, nothing sets them), Invisibility ending on attack (`FUN_00516b2f`: effect kind 12 flag `+0x42 := 1`),
Haste/Slow; item modifier kinds other than those in section 6 (speed, scan range, mana, regeneration, castSpell on a weapon); equipment
swapping in play; structure targets (`FUN_00516ea0`); client hit reaction animation (`vtable +0x74` of the view unit); sound.

## 11. VERIFY IN GAME

1. A monster with a weapon (a Goblin_Pike) hits a known target 20 times: do the damage values span `template + weapon` (8..16 before
   absorption) or only the template (4..8)? Count hits and misses against the predicted rate (5.3).
2. The hero (known Body/Reaction, weapon, blade skill) hits a monster 20 times: record hit/miss, damage range, interval between hits
   (predicted `W + R + 2` with `R = recovery + hero delay + 0..3`), the first hit `W` ticks after the swing animation starts.
3. Order an attack while standing next to the target: the swing starts within 16 ticks (next `tick & 15 == 6`), not at once.
4. Order a hero to attack a flyer (bat) with a sword: refused; with a bow: allowed.
5. Target walks away mid-swing: the hit is lost when the centres are 1.75 cells or more apart (size 1, Chebyshev) at the hit tick; the attacker follows afterwards.
6. Ctrl+L toggles the floating damage numbers; the number equals the HP lost; colour = the victim's owner colour.
7. A hit with damage 0 (high absorption) still shows nothing (message `0x73` carries the same HP: no number).
8. Sure-hit monsters (bats, bees, spiders) never miss and ignore absorption.

## Open questions

1. Monster weapon bonuses: confirm in play that `damage = template + weapon` (11.1); the code order says yes.
2. `FUN_005106d2(0x14/0x1c)` effect lookups and the `FUN_00516b2f` invisibility flag need the effect system (K).
3. `FUN_0056ed4e` auto scan and `FUN_0056a1fb` guard scan (target choice, visibility) - AI phase.
4. What the client does on `0x73` besides the number (`vtable +0x74` of the view unit: pain animation or flash).
5. Whether the timer byte really wraps at 0 (a recovery of 0) - needs a data row or a spell effect that produces it.

## 12. Death, corpses, loot, XP and regeneration (I2 research)

All CONFIRMED in the GOG `allods2.exe` with REA unless marked INFERRED. Counters: **tick** = `server+4` (`+1` at the start of `FUN_004f8521`, once per
server tick, 16 per second at the default speed); **block** = `server+0`, the 16-tick block counter (`+1` after `tick & 15 == 15`, `0x4f0ab7`).
The HP-regeneration slot reads the **block**, not the tick (12.5). Per tick the order is: `FUN_004f08c0` (the job at `tick & 15 == 12`, `FUN_0052bbb7`,
runs before the increment) -> `FUN_004f8521` (tick `+= 1`, command drain, group pass `FUN_004f04cf`) -> `FUN_0052b459` (creature loop).

### 12.1 Pipeline and tick timeline

Creature loop `FUN_0052b459`, for every unit in list order, each tick: (a) clear `+0x40` (last attacker) when its owner is gone; (b) effect-bit diff to
the clients (`+0x1a4/+0x1a6`); (c) **if state != 0x10: vtable `+0x18` = `FUN_0050f12c` (the creature tick)**; (d) **if state == 0x10 now: removal** (12.3) in the
same tick, same loop pass. So `0x10` and the removal are the same tick.

Creature tick `FUN_0050f12c`, order of the steps (HP is the s16 at `+0x94`; "dead" = HP <= 0, **0 counts**):

| Step | What | Mark |
|---|---|---|
| 1 | state == 0x10: return | C |
| 2 | every effect of the list `+0x20`: vtable `+0x38(unit)`, dropped when finished | C |
| 3 | HP <= 0 branch (below) **replaces the whole alive branch: the Brain tick (`FUN_0056dca2`) and the state switch are not run for a dead unit** | C |
| alive | message mask `0x10` for the owner's main hero (`owner+0x38 == unit`) when `FUN_0050fc3e == 0x50` exactly (80 ticks since the last step ended; re-sends position/facing); Brain tick; state switch | C |

HP <= 0 branch, every tick it holds (`T0` = first such tick):

| Tick | Action |
|---|---|
| `T0` (`+0x13c == 0`) | `order +0x50 := 0`, `state +0x54 := 0`; `+0x13c := 1`; `FUN_00510745` (cancels a pending spell: the `+0x68` effect when it is a spell effect of this unit, not a cast in its animation, and `+0x64` carrier is freed); **defence word `+0xbe := +0xbe / 2`** (signed truncating); dying timer `+0x6c := dying_time - 1` (byte; `vtable +0x74`: monsters `FUN_0050f048` = data.bin p33, humans `FUN_00512526` = p23 or 8 when absent / -1); mask `0x4001` (HP + defence) sent to all players that may see it (`FUN_00502019`) |
| `T0 + j`, `j >= 1` | order := 0, state := 0 again; if timer (as **signed char**) `< 1`: [movementType (`+0x4a`) `> 1`: HP := -1000]; if HP `< -9`: **state := 0x10, `FUN_00510a70` (12.3)**; else (timer still `>= 1`): timer `-= 1` |

So the earliest removal is tick `T0 + D` for dying time `D` (timer at `T0 + j` before the decrement is `D - j`): Orc_Sword (D = 14) `T0 + 14`, Goblin_Pike (12) `T0 + 12`, Ogre (8) `T0 + 8`,
Troll (18) `T0 + 18`. `D = 0` (timer -1) removes at `T0 + 1`. "dying_time - 1" is the ticks-of-countdown offset; it is **not** the animation length (the client plays
`2 * DyingPhases` ticks, [animation §3.3](../formats/animation.md)). `T0` is the tick of the victim's own creature tick after the HP was written: the same tick as the killing
hit when the victim is later in the unit list than the attacker, else the next tick (INFERRED from the list order of the loop; the hit runs in the attacker's tick).

**The ground-unit trap (movementType 1, CONFIRMED by code reading, VERIFY IN GAME).** After the timer, a ground unit with HP in `-9 .. 0` is **not** removed.
Only HP <= -10 removes it, and the only thing that lowers HP is (a) further hits (attackers still swing, 12.2) and (b) the regeneration slot (12.5): for HP `< 0`
it does `HP -= 1` once per **4 blocks = 64 ticks** (`block & 3 == 0`; message mask 1 each time). So from HP `h < 0` it needs
`(-h - 9)` decrements, i.e. up to `64 * (-h - 9)` ticks (HP -1: 576 ticks = 36 s; HP -9: one decrement, at most 64 ticks). **HP exactly 0 is never decremented: the
unit stays a "dead" blocker forever** (footprint held, targetable, brain frozen) until someone hits it. Flyers and ghosts (movementType > 1) skip all this (HP := -1000).

Order that matters for the engine at the first tick: effects tick, then orders cleared, defence halved, timer set, notify. Nothing else is touched at `T0`: group membership,
`brain+0x8/+0xc/+0x14` (mode, target, range), `brain+0x9` (a swing in progress keeps its value but the swing is dead, since state is 0 every tick), the footprint stamps,
the occupant slot, the owner's unit list. A **revived** unit (HP > 0 again, e.g. healed) takes the alive branch; `+0x13c` stays 1, so its **next** death skips the `T0` block
(no cancel, no defence halving, no notify, **stale timer**): only the "timer < 1" path runs (INFERRED consequence of CONFIRMED code; VERIFY IN GAME).

### 12.2 Orders, groups, attackers, followers, casters, selection

| Subject | Behaviour | Mark |
|---|---|---|
| the dying unit's own order | order := 0 and state := 0 every tick while dead; order `0x10` set at removal. Its group order is not touched | C |
| its group | membership stays until removal (12.3: `FUN_0051618e` takes it out of the owner's list and the group; the group is deleted when empty and not computer owned, INFERRED reading of `FUN_0052afd2` / `FUN_00539d50`) | C / I |
| attacker, order 3, Brain mode 5 | `FUN_00569321` stops the unit only when the target's **state is 0x10**; `FUN_0056eab5` (in range -> swing, else approach) and the hit gate `FUN_00516ceb` test **neither HP nor state of the target** ([5.1](#51-the-gate-fun_00516c1f---fun_00516ceb-confirmed)). So attackers keep swinging at the dying body and at a ground corpse that is stuck at HP -9..0, and each hit lowers HP (no XP: the XP rule needs HP > 0 before the hit, message `0x73` needs HP > -10 now). They stop at the next `tick & 15 == 6` executor pass **after the removal**: `FUN_0056dbc6` (cancel, order `0xc`, anchor = own cell, `brain+0x50 := 1`); no auto scan (`FUN_0056ed4e` is only the pathing-failure branch). A swing already started still lands on the corpse | C |
| the corpse object after removal | the object stays alive: it moves to a corpse list (`FUN_0052b22a(world+0x7c list)`) and keeps state 0x10, so lookups still succeed: attack commands on it are accepted ([2.1](#21-intake-fun_004f515d-confirmed)) and the executor then sees 0x10 and stops | C |
| followers / casters / mode 4,6,8 | same: they hold the target pointer and only the state `0x10` check ends them (executor pass at 16-tick granularity); a caster with the corpse as target casts normally until then | I (same executor) |
| owner's unit list / counts | `FUN_0051618e` at the removal tick: the unit leaves the owner's list; nothing at `T0` | C |
| player's selection (client) | not found in the routines read. The client draws and counts by **death stage** (`obj+0x184`, recomputed from HP): `FUN_00416717` marks own units with stage <= 1 and flag `+0x1b8 & 0x80 == 0` (INFERRED: the selectable set), `FUN_00472460` draws the own-unit portraits / sidebar only at stage 0. So the unit leaves the selectable / portrait set at the **first HP message with HP <= 0 (stage 1)**, i.e. at `T0` + latency, not at removal | I |

### 12.3 Removal (`FUN_00510a70`, called at state 0x10) and the world list

In order (`FUN_00510a70`): (1) if `+0x148 != 0` (a group-key mark, 12.6): HP := -10000, `+0x148 := 0`; (2) **state := 0x10, order := 0x10**; (3) `FUN_00553891` =
release the stamps (`FUN_0055be86(unit, 0, 2)`) + lift the occupant (`FUN_00550697`) and `FUN_005551d6`; (4) equipment into the loot bag (12.4); (5) the loot roll (12.4);
(6) effects: every effect of `+0x20` for which `FUN_0051cc53` holds gets `+0x42 := 1` and is ticked once / dropped; (7) **main hero of the owner** (`owner+0x38 == unit`):
`owner+0xa54 += 1` (hero deaths), mask `0x2400000`, `FUN_004e9e97` (a savegame writer guarded by `[0x6044c4+0x74] != 0`: **no-op in single player**), **HP := -50**;
(8) single player (`[0x6044c4+0x74] == 0`), owner computer-flag `+0x2c == 0` (the human) and unit type `0x21..0x3f`: `owner+0x40 := server_id - 0x13`, client message `0xb4`
(hero died; the game-over / death dialog trigger, INFERRED meaning); (9) `FUN_005110b8` (corpse decay step, 12.6).
Then, still inside `FUN_0052b459` the same tick: (a) unit removed from owner list and group (`FUN_0051618e`) and from the creature list (`FUN_0053afb0`), added to the corpse list;
(b) effects of `+0x20` get `+0x42 := 1`, `+0x44 := 0` and one more tick; (c) **kill credit** (12.7); (d) client events via the queue `0x68d360` (`FUN_0052e07e`): type 4 =
"unit removed" (`id`, `unit_type << 16 | face << 24 | killer owner id`), type 5 for `+0x70`, type `0xf` for the local human owner when `owner+0xa60 != 0`;
(e) movementType > 1: id slot freed (`FUN_004f8d3d(id)`, `+4 := 0`), so flyers / ghosts vanish for lookups; **ground units keep their id** until corpse stage 5.

**Release timing (answers 1):** footprint stamps, occupant slot and the creature-list entry are released at the removal tick (`T0 + D` or later, 12.1), **not** at HP <= 0.
Until then the dying unit blocks its cell and is a path blocker (verdict 0: HP < 1, [simulation §7.4](simulation.md)). After it, the corpse never blocks (it is out of the
spatial tables; the client keeps drawing the body).

### 12.4 Loot and drops (`FUN_00510a70`, steps 4-5)

Order inside the function, with the exact `rand` calls (`rnd(n)` = `FUN_0051fa25`, 0..n inclusive, [items §11](../data/items.md#11-random-generation)):

| # | Step | Condition | Draws |
|---|---|---|---|
| 1 | slot `+0x78` item -> `vtable +0x48` (unequip) -> into the unit's loot bag `+0x7c` (`FUN_00529ac2`) | slot non-empty | - |
| 2 | slot `+0x74` item (the weapon) likewise | slot non-empty and template parameter 15 != 0 (monster p15 = defence; INFERRED why) | - |
| 3 | vtable `+0x4c`: humans (`FUN_00512697`) unequip slots 1..12 into the bag; monsters: no-op | - | - |
| 4 | bag **cleared** (old bag destroyed, new empty one) | summoned (`+0x1a0 != 0`) **or** template name contains the text `NPC` (`FUN_0059e063(name + 4, "NPC")`) | - |
| 5 | gold: `rnd(100) < p38` -> `gold = p39 + rnd(p40)` | `unit_type >= 0x40` (monsters; heroes 0x21..0x3f never roll) and not summoned | `rnd(100)`; then `rnd(p40)` only when it hit |
| 6 | item: `rnd(100) < p41` -> build a generator (`FUN_005254e7`: min = p42, max = p43, count 100, stack 1, flags p44), run it (`FUN_00525f67`), pick `rnd(len - 1)`, set its quantity `+0x42 := 1`, add to the bag | same | `rnd(100)`; then the generator's own draws ([items §11](../data/items.md#11-random-generation)); then `rnd(len - 1)` (only when `len != 0`) |
| 7 | **drop**: if the bag has `> 0` items or `gold != 0`: `FUN_005109f5` -> `FUN_0052acf6(cell +0x10, bag, gold, flag)`; a new empty bag is created | - | - |

The gold is **not a coin item**: it is a number on the pile object (`pile+0x3c += gold`); `flag` = (unit is the owner's main hero) -> pile `+0x44`. `FUN_0052ab07`: the pile at the unit's
own cell is looked up (`FUN_00553ab3(cell)`); if one exists the bag is merged into it, else a new pile object (`FUN_0052a71d(cell, bag)`) is created and registered with
`FUN_0052ad3d` -> `FUN_005538c7`; **if registration fails the pile (items and gold) is deleted**. Whether `FUN_005538c7` searches a neighbouring free cell is not read (open question).
Probabilities (comparison `p38 > rnd(100)`; `rnd(100)` has 101 values, so chance = `p38 / 101`, not `p38 %`): e.g. Orc_Sword p38 = 80: 79.2 %; gold `90 + rnd(270)`; item p41 = 30: 29.7 %, window 180..540, flags `826802175` (`0x3147ffff`). Goblin_Pike: gold 60 -> 59.4 %, `30 + rnd(90)`, no item (p41 = 0: never, since `rnd(100) >= 0`).
Heroes and human NPCs (types `0x21..0x3f`): no roll, but **all equipment (slots 0..12 as above) and the carried bag drop** unless the template name contains `NPC` or they are summoned.
A hero (player unit) dying: bag + equipment drop at its cell, deaths counter, HP -50, message `0xb4`; there is no other game-over code in this routine (the end of the game is
the client / script reaction to `0xb4`, not read; open question).

### 12.5 Regeneration (vtable `+0x14`, `FUN_0050fc5a`) and the open question 3 of simulation.md

Called for every creature (all three class vtables `0x5d0eb0`, `0x5d0f40`, `0x5d0fb8` point to it) **once per block**, from the job `FUN_0052bbb7` at `tick & 15 == 12`.
The counter it tests is `*[0x6044c4]` = the **block** counter. Resolution: **HP regeneration of a unit with id `i` runs on the blocks `b` with `b & 3 == i & 3`: once per 4 blocks = every 64 ticks, and each unit
has its own phase**; mana regeneration has no id test and runs **every block (16 ticks)**; the "HP < 0 loses 1" rule runs when `b & 3 == 0` (every 64 ticks, all units together). The older text in
unit-struct §3 ("every 4th tick", `tick & 3`) was wrong (correction below).

| Case | Rule |
|---|---|
| state 0x10 | nothing |
| HP < 0 | if `b & 3 == 0`: HP -= 1, mask 1. HP == 0: nothing. No mana regen |
| HP > 0 | `k = 3` if `FUN_0050fc3e > 80` (ticks since the last step ended: `+0x138 = tick + step_ticks` is written by the move message `0x6b`, `FUN_00504xxx` at `0x504122`; other writers of the same shape at `0x5041ba`, `0x504292`, `0x504369`, `0x50446f`, INFERRED turn / other messages; created as 0), else `k = 1`. There is **no "recently attacked" test**: only movement counts |

HP part, when HP `< maxHP` (`+0x96`) and `regen` (`+0x98`) `!= 0` and `b & 3 == id & 3`: with `acc` = byte `+0xa2` (hundredths of a HP), `bonus` = s16 `+0xde`:

```
t   = HP*100 + acc + floor( maxHP * 2 * (100 + bonus) * k / regen )        (integer division, trunc)
acc = t mod 100 ;  HP = min( floor(t / 100), maxHP ) ;  mask 1 to the owner
```

Mana part (no `b` test, no id test, any HP > 0): when mana `+0x9a < maxMana +0x9c`: `t = mana*100 + acc2 + floor( maxMana * (100 + bonus2) * k / manaRegen(+0x9e) )`, `acc2` = byte `+0xa3`,
`bonus2` = `+0xe2`; same split and clamp; mask 2. (Note: no factor 2 for mana; a monster with mana below max and `manaRegen == 0` would divide by zero: not reachable with the shipped data, INFERRED.)

Worked example (data.bin, 16 ticks per second): **Orc_Sword** maxHP 80, regen 100, bonus 0: gain per application `80*2*100*1/100 = 160` hundredths = 1.60 HP; one application per 64 ticks (4 s);
HP 0 -> 80 takes 50 applications = 3200 ticks (200 s); resting (`k = 3`, 80 ticks without a step): 4.80 HP per 64 ticks, about 17 applications (68 s). **Goblin_Pike** (40 / 50): also 1.60 HP. **Ogre** (200 / 150): `200*200/150 = 266` -> 2.66 HP per 64 ticks. The first
application of a new unit happens on the first block with `b & 3 == id & 3` after tick 12. Dead units never regenerate; a unit with HP > 0 that is `state != 0x10` does, in any state (fighting included).

### 12.6 Corpse decay (`FUN_005110b8`, from the same job) and what the client draws

The job also calls `FUN_005110b8` for every unit of the **corpse list** (and `FUN_00510a70` for the group-key marks below). Per job run (once per block): `if HP > -10001`: when `block` is even,
HP `-= 1` (every **32 ticks**); heroes of type `0x21..0x24` stop at HP -61 (`> -61` test), every other type continues. Server corpse stage `+0x13c`: HP `< -10` -> 2, `< -20` -> 3, `< -40` -> 4, `< -600` -> 5;
at stage 5 HP := `-10001` (stops the decay) and, for movementType < 2, the id is freed (`FUN_004f8d3d`); a stage change sends mask 1 (HP) to the clients. The object itself is **never deleted** from the corpse list.
The client's death stage is the same function of the HP ([animation §3.3](../formats/animation.md)), so the draw changes exactly at those HP values:

| Event (ground unit removed at HP ~ -10) | Time after removal | Client picture |
|---|---|---|
| HP <= 0 message (`T0`) | - | dying animation `2 * DyingPhases` ticks, then corpse frame held |
| HP -11 (stage 2) | <= 32 ticks | bones 1 |
| HP -21 (stage 3) | + 320 ticks (20 s) | bones 2 |
| HP -41 (stage 4) | + 960 ticks (1 min) | bones 3 |
| HP -601 (stage 5) | + 18,880 ticks (19.7 min) | not drawn (gone) |
| flyers / ghosts (HP := -1000) | first job after removal (<= 16 ticks) | not drawn quickly; id freed |
| heroes (`0x21..0x24`) | never past -61 | bones 3 forever |

Nothing is time based on the client: only the HP messages. There is no fade; the corpse changes its **graphic** (corpse -> bones -> gone). A corpse stays in the corpse list, not in the spatial tables / creature list (minimap
dots and the sidebar only count stage 0; INFERRED from `FUN_00472460`). Corpse is not selectable (stage > 1, INFERRED `FUN_00416717`) but is still a legal attack target by id for a ground unit (12.2).
**Group-key marks** (`FUN_0052bbb7` tail, INFERRED purpose: a population cap per group key `+0x148`): each job counts the units per key and, for each key with count `n`, with probability `n %` (`rand(100) < n`)
marks it; every unit of a marked key is removed via `FUN_00510a70` (HP := -10000). Whether campaign maps use `+0x148` is not known (open question).

### 12.7 XP at a kill

The kill credit is paid **at the removal tick** (12.3 (c), `0x52b6c7`..`0x52b84a`), not at HP <= 0. Chain: `victim+0x40` (last attacker, written by `take_hit` **at every hit** that has an
attacker template, the last one wins, [5.2](#52-take_hit-fun_00516f6f-confirmed-vtable-54-of-every-creature-class)) must be an object whose owner exists (else cleared, `0x52b4b0`). Killer type `0x21..0x3f` and HP not < 0
(`FUN_00542770`) -> killer vtable `+0x68` (`FUN_00512fcb`, humans only; monsters' slot `0x5423e0` is a stub) with `(victim, spell byte +0x48)`. Details, amount (`0.5 * victim.xp` through the repeat-kill discount), repeat list, schools:
[progression §4](../data/progression.md#4-xp-sources); not repeated here. Only the unit in `+0x40` gets the kill credit (no party / group share); the others got per-damage XP only. Kill counters:
victim type `0x21..0x3f` -> `owner+0xa4c += 1`, `[killer-owner + ...]` message `0x94` if `[0x6044c4+0x74] != 0` (net, ignore); else `owner+0xa48 += 1`; message `0x2000000` to the killer's owner; per-owner kill table byte
`owner+0x44+server_id` (cap 14) incremented, a message `FUN_00505582` when the new value is even (bestiary-style counter, INFERRED). A non-hero killer (monster) gets nothing (a log line only when the victim is a human type).
Level-up when a skill threshold is crossed: `FUN_005128cb`, effects in [progression §3](../data/progression.md#3-what-a-skill-up-changes) (client event `FUN_005052d2` event 2 only for the human owner, stat message with flag `0x100 << (k-1) | 0x3000c`); no
extra effect object, sound or floating text was found in these routines (client reaction not read: open question).

### 12.8 Corrections made to older text

1. unit-struct §3 (vtable `+0x14`): "every 4th tick (`[0x6044c4] & 3 == id & 3`)" and "HP<0 loses 1 per 4 ticks": the counter is the 16-tick **block**; real periods 64 ticks (HP regen per unit, HP<0 loss), 16 ticks (mana).
2. simulation.md open question 3 resolved (above).
3. unit-struct `+0x138`: was UNKNOWN: tick at which the last move step ends (`tick + step ticks`); `+0x13c`: also the server corpse stage 1..5.
4. combat §9.1 stays valid for I1; I2 restores the exe behaviour (keep swinging at HP <= 0 until state `0x10`).

### 12.9 Engine plan facts (for I2)

State on a kill: HP <= 0 -> next creature tick `T0` (12.1) -> `T0 + D` check -> (ground: HP must be <= -10: decay 1 per 64 ticks on `block & 3 == 0`, HP 0 never) -> removal block of 12.3 -> corpse list:
decay `-1` per 32 ticks on even blocks with the stage table of 12.6. Do not release the footprint before the removal; do not stop attackers before the executor sees state `0x10`.

### 12.10 VERIFY IN GAME

1. A ground monster killed to HP exactly 0 (set up by damage or a debugger): stays standing as an unremoved body indefinitely? Kill to HP -1..-9: how long until it disappears (predicted `64 * (-h - 9)` ticks max, in 64-tick steps on `block & 3 == 0`).
2. A bat / bee / ghost (movementType > 1) vanishes `D` ticks after the killing hit; a ground corpse stays and turns to bones after about 32 ticks of decay, bones 2 after 20 s, bones 3 after 1 min, gone after about 20 min.
3. Dying animation length vs `dying_time`: the dying/corpse draw uses `2 * DyingPhases`; the server removal is `D` ticks after the killing tick.
4. Loot: gold `base + rnd(spread)` with chance `p38 / 101`; item only with `p41 > 0`; no drop from summoned units and from templates named `*NPC*`; the pile appears on the unit's own cell; a second kill on the same cell adds to the pile.
5. Attackers keep hitting a corpse until it is removed, then walk away / stand at the next 16-tick pass; no XP for hits on a dying unit.
6. Regeneration rate of an idle Orc_Sword: 1.6 HP per 4 s (x3 after 5 s of standing still); two same-id-class units regenerate in the same block; mana every second.
7. XP: kill credit appears at the removal moment (after the death animation), once, for the unit of the last hit.
8. The hero dying in single player: items on the ground at its cell, game-over reaction.

### 12.11 Open questions

1. Client reaction to the remove event (queue `0x68d360` type 4 -> message `0x80`/others): does the client delete its unit object (ground corpses are still drawn) and when does it drop the unit from the selection list (start: `FUN_0052e07e`, `FUN_005052d2`, `FUN_00416717`)?
2. `FUN_005538c7` (pile registration): does it pick a free neighbouring cell when the unit's cell cannot hold a pile (and what holds a pile: water, structures)?
3. Message `0xb4` (hero died) handler and the single-player game-over condition (starting routine: client dispatcher of message `0xb4`).
4. The group-key mark `+0x148` (population cap job at the end of `FUN_0052bbb7`): who writes it (map loader / spawner) and whether any campaign map uses it.
5. Writers of `+0x138` other than the move message (`0x5041ba`, `0x504292`, `0x504369`, `0x50446f`, `0x50ea4b`) and the exact meaning of the resting multiplier.
6. Meaning of "template parameter 15 != 0" gating the weapon drop (`FUN_00510a70`, `0x510b50`).
7. Client floating text / sound / effect at a kill and at a level-up (not found in the server routines).

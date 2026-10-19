# Combat (phases I1, I2): attack order, approach, swing, hit, damage, death, XP, loot and regeneration

How a unit ordered to attack an enemy walks into range, swings with the exe's timing and hurts it with the exe's formulas.
Marks as in CLAUDE.md (**CONFIRMED** = read in the GOG `allods2.exe` with REA, routine given; **INFERRED** otherwise). Exe
build: sha256 in [formats/README.md](../formats/README.md). No decompiled code here: formulas are written as math.
Ranged and spell attacks share the code up to the damage call (section 5), so they are listed where they differ; spells and
AI retaliation are other phases (section 10); death, corpses, loot, XP and regeneration are I2 (sections 12-13). RNG: [simulation §10](simulation.md#10-rng). Struct offsets:
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
- target flag `+0x4c & 8` (off the map, [ai §6](ai.md#6-attack-and-return-execution-confirmed)): guard scan instead (no such units in the engine);
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

- Target state `0x10` (the unit was removed, 12.3): executor stops the unit (2.3); until then it keeps swinging (12.2).
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
   ([progression §4](../data/progression.md#4-xp-sources)). Applied since I2 (`xp.damage_credit`, section 13).

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
| flag `+0x4c & 8` | | off the map: returns 0 at once |

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
              defender.last_element := e if attacker is a mage (+0x4c & 4) else 0 (+0x48); AI reaction FUN_0056e6b8 (modelled in [ai §8](ai.md#8-hit-reaction-fun_0056e6b8attacker-victim-0-confirmed) when the AI is on)
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

1. **HP clamp (I1 only, removed in I2):** `take_hit` is exact; I1 clamped HP at 0 and stopped attackers at once. I2 stores the exe's HP (below 0 allowed)
   and attackers keep hitting the body until the executor sees state `0x10` (12.2, section 13).
2. **Retaliation, XP, weapon spells, mage spells, structure targets, ranged hit sound/arrows:** not in I1 (section 10).
3. **Pathing failure under order 3:** mode 0 (no auto scan), restored by the executor.
4. **Difficulty:** the map-load tweak of monster to-hit/defence (`[0x6044c4+0xd8]`, [unit-struct §1](unit-struct.md)) is implemented as an option (hard: to-hit and defence +50 via `monster_stats(hard=)`); the default is mode 2 = skip, so the shipped behaviour is unchanged ([ai §10.1](ai.md#101-difficulty-tweak-fun_00561bf9-0x561e200x561f0b-confirmed)).
5. **Seed:** per game, explicit (section 2 of simulation §10).
6. **Ranged attacks** (range > 1) use the same code: wind-up + `extra`, no projectile in the simulation; the visual arrow is a view matter (not drawn yet).
7. **Stats are built lazily** (`combat_stats(world, unit)`, from `Unit.stats`, `World.item_table`, `Unit.skills`) and cached in `Unit.combat`; a skill-up or an
   equipment change must clear it (progression hook, later). A unit without a template fights with all-zero stats.
8. **Units with HP <= 0 get no Brain tick**: `_tick_unit` runs the dying branch (`sim/death.py`, section 13).
9. **Intake** creates the group (and moves the members into it) before the target lookup, as the exe does; a command for an unknown or structure target
   therefore leaves the orders untouched but changes the groups.

## 10. Not modelled (kept for later phases)

AI reaction `FUN_0056e6b8` (defender alert message, `brain+0x54/+0x58/+0x94`), the guard scan and auto
target scan (`FUN_0056a1fb`, `FUN_0056ed4e`), special-attack rolls (`FUN_0056a981`), mage casting (`FUN_0056b059`); effects: Bless / Curse
bits (the `take_hit` inputs exist, nothing sets them), Invisibility ending on attack (`FUN_00516b2f`: effect kind 12 flag `+0x42 := 1`),
Haste/Slow; item modifier kinds other than those in section 6 (speed, scan range, mana, regeneration, castSpell on a weapon); equipment
swapping in play; kill counters, bestiary byte, message `0x94`; the summon-cap job (`+0x148`, 12.6; needs the Summon spell); structure targets (`FUN_00516ea0`); client hit reaction animation (`vtable +0x74` of the view unit); sound.

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
| player's selection (client) | CONFIRMED (`FUN_0040d9b2`, the client message handler, death-stage block `0x410495`-`0x4108f6`; the selected flag is `obj+0x80`). The stage is recomputed from the HP of **every** message that carries HP (`obj+0x184`, [animation §3.3](../formats/animation.md)). **Stage 1 (HP -10..0): the unit stays selected** (case 1 `0x4105e4` only starts the dying animation). **Stages 2-4 (HP <= -11): `if obj+0x80`: vtable `+0x14(0)` (deselect) and the selection summary refresh `FUN_004167c2`** (`0x4108dd`-`0x4108f6`); stage 5 (HP < -600): the same, then the object is removed from the view map (`FUN_0041fff0`) and deleted (vtable `+0x4(1)`, `0x4109ad`, ids < `0x6000`). So the unit leaves the selection at the first message with HP <= -11: the `T0` message (`0x4001`) for an overkill, otherwise the decay HP message after the removal (up to 32 ticks later, 12.6), **not** at `T0`/HP <= 0 and not at the removal. The hotkey `E` (`FUN_00416717`, select-all) selects the own units of stage <= 1 whose flag `+0x1b8 & 0x80` is clear, deselecting the rest | C |
| the unit-removed event (`FUN_0052e07e(4, id, ...)`) | CONFIRMED: **not a client message.** `FUN_0052e07e` appends a 0x1c-byte node (type, a, b) to the list at `server+0x20` (object `0x68d360`); `FUN_0052e122` (from the job `FUN_004f08c0`) drains it (`FUN_0052e0c4`) and calls every registered listener's vtable `+0x14(type, a, b)` (`FUN_0052e198`). The listeners are the map script / trigger conditions (e.g. `FUN_0052eac8`: type 4 compares the dead unit id with the listener's unit). Event 4 args: unit id, killer's main-hero id (human owners) \| unit type `<< 16` \| `+0x4b << 24`; types 5 and 0xf are queued at the same removal under other conditions (a `+0x70` carrier field; the owner's `+0xa60`), meaning not read. `FUN_005052d2` is the client message `0x92` sender (level-up, skill message), unrelated to removal. The client gets **no removal message**: it only sees HP messages (12.6) | C |
| picking / hover / click target (client) | CONFIRMED: the view draw registers a pick rect for an object only while `obj+0x184 < 2` (`0x4087c2`, `0x409de8` -> `FUN_00404d99`). So a **stage-1 body (HP -10..0, dying or fresh corpse) is hoverable and clickable** (hostile owner: attack cursor, INFERRED from ui-layout §6 hover flags; the hover flags test no HP); stage >= 2 bones are not hoverable (a ground click goes to the ground). Attack commands by id are accepted for any lookup hit (above) | C |

### 12.3 Removal (`FUN_00510a70`, called at state 0x10) and the world list

In order (`FUN_00510a70`): (1) if `+0x148 != 0` (a summoned minion picked by the cap job, 12.6): HP := -10000, `+0x148 := 0`; (2) **state := 0x10, order := 0x10**; (3) `FUN_00553891` =
release the stamps (`FUN_0055be86(unit, 0, 2)`) + lift the occupant (`FUN_00550697`) and `FUN_005551d6`; (4) equipment into the loot bag (12.4); (5) the loot roll (12.4);
(6) effects: every effect of `+0x20` for which `FUN_0051cc53` holds gets `+0x42 := 1` and is ticked once / dropped; (7) **main hero of the owner** (`owner+0x38 == unit`, CONFIRMED test; step 8 does not need it):
`owner+0xa54 += 1` (hero deaths), mask `0x2400000` (`FUN_00502019`, `0xffb`), `FUN_004e9e97` (a savegame writer guarded by `[0x6044c4+0x74] != 0`: **no-op in single player**), **HP := -50**;
(8) single player (`[0x6044c4+0x74] == 0`), owner computer-flag `+0x2c == 0` (the human) and unit type `0x21..0x3f` (**any** hero of the human, not only the main hero):
`owner+0x40 := (byte)(server_id - 0x13)`, server message `0xb4` via `FUN_00505347(0xb4, owner+0x40, 0, owner)` (CONFIRMED; effect in 12.3a); (9) `FUN_005110b8` (corpse decay step, 12.6).
Then, still inside `FUN_0052b459` the same tick: (a) unit removed from owner list and group (`FUN_0051618e`) and from the creature list (`FUN_0053afb0`), added to the corpse list;
(b) effects of `+0x20` get `+0x42 := 1`, `+0x44 := 0` and one more tick; (c) **kill credit** (12.7); (d) client events via the queue `0x68d360` (`FUN_0052e07e`): type 4 =
"unit removed" (`id`, `unit_type << 16 | face << 24 | killer owner id`), type 5 for `+0x70`, type `0xf` for the local human owner when `owner+0xa60 != 0`;
(e) movementType > 1: id slot freed (`FUN_004f8d3d(id)`, `+4 := 0`), so flyers / ghosts vanish for lookups; **ground units keep their id** until corpse stage 5.

### 12.3a Hero death: message `0xb4`, the dialog and the game (CONFIRMED unless marked, allods2.exe sha256 in formats/README.md)

- **Delivery.** `FUN_00505347` fills the message block `0x68f610` (type at `+9`, sender id `+7`, value byte `+0xa`) and hands it to `FUN_0050164f`. The client message dispatcher `FUN_0040d9b2` (case `0xb4` of its message switch) does only
  `PostMessage(mainwnd, 0x433, 0xff, 0)` (`FUN_0041e3f0`); the value byte `owner+0x40` is **ignored** for `0xb4` (case `0xb6` forwards `msg+10` as the `0x433` wParam, case `0xb5` posts `0x430`).
- **Window handler** (`FUN_004852d8`, the game window proc, `0x485377` entry). `0x433`: `[this+0x43c] := wParam`; `0xff` posts `0x431`. (`0xfe`, `0xfd`, `0xfa` and other values are the `0xb6` results: other dialogs / `event_%d` text; not read.)
  `0x431`: only if `[this+0x3e8] == 0` (a one-shot latch, set here; no reset in this proc) **and** the game mode `[this+0x5d8] == 2` (in a game): builds the dialog `FUN_0044d1e2(1, 0x20, 100, 0x260, 0x17c)` (class vtable `0x5ccf78`, base text window `FUN_00444243`; text = table entry `0x8d`),
  registers it as modal through `FUN_0048b33b` (`[this+0x404] |= 8`, window stored in `[this+0x124]`). Its init (`FUN_0044d237`) makes two buttons: command `0x445` (interface string `0x2c`) and `0x446` (string `0x23`); the second one is **disabled when no `\game*.sav` file exists** (`FUN_0043ff4a`, `FindFirstFile` in the saves directory).
- **Buttons.** A click sets the dialog result (`FUN_004441c1`: window `+0x60 := id`) and posts window message `0x44c` -> `FUN_004891d8` (dialog-closed handler): the branch for `[this+0x124]` clears the modal bit `8`, then
  `0x445` -> posts `0x41e` = `FUN_0048f2e5` (end the running game: stop the server / sim) + post `0x421` = `FUN_0048b569` (back to the **main menu**: closes the game windows, plays `music_menu.wav`);
  `0x446` -> posts `0x418` = opens the **load-game window** (`FUN_0043deaf`, class `0x5cbdc8`, init `FUN_0043df48` lists the `.sav` files by header magic `0x26677342`, buttons `0x479` / `0x475` / `0x47a`; INFERRED as the load list from the file scan and the layout).
  There is no "continue" button: the only ways on are load a save or leave to the menu. The dialog is deleted afterwards.
- **The simulation stops.** The game tick (`FUN_00481ccb` -> `FUN_00488aa1` -> `FUN_004f08c0`) runs only if `[this+0x404] & 1` and, in mode 2, `[this+0x404] & 0x4008 == 0` (CONFIRMED condition): the modal bit `8` set by the dialog **freezes the sim** until it is closed.
- **Defeat rule.** `FUN_00510a70` has no all-heroes-dead or main-hero-dead test of its own: **any** hero of the human reaching state 0x10 (not only the main hero) opens this dialog, so the death of one hero is the single-player defeat. Whether a map script can lose the
  game otherwise (`0xb6` results) is not read. Computer-owned heroes and monsters never send `0xb4`.
- **Counters.** `owner+0xa54` (hero deaths, main hero only) is a statistics value: listed with `+0xa48`, `+0xa4c`, `+0xa58` in the player statistics text (`FUN_004828d7`, format string `0x43`; also `FUN_004e9e97` / `FUN_0052d1c5` serialise it; INFERRED meaning of the neighbours). `owner+0x40` is the byte `server_id - 0x13` of the last hero that died; no reader found (only a write of another object's `+0x40` in `FUN_004891d8`).
- **Revival.** Not possible: the unit is at state/order 0x10 (the executor stops it), it left the owner list and group (12.3 a), its stamps are released and the HP is -50 (main hero) and decays towards the stage-5 removal; no code path in `FUN_00510a70` / the corpse list restores a unit. The way back is a saved game (the dialog's load button). The main-hero pointer `owner+0x38` is not cleared by the death.
- Engine: `Player.main_hero / hero_deaths / death_code / defeat_dialog`, `HeroDied` fight-log event (section 13). The dialog and the freeze belong to the UI layer (not built).

**Release timing (answers 1):** footprint stamps, occupant slot and the creature-list entry are released at the removal tick (`T0 + D` or later, 12.1), **not** at HP <= 0.
Until then the dying unit blocks its cell and is a path blocker (verdict 0: HP < 1, [simulation §7.4](simulation.md)). After it, the corpse never blocks (it is out of the
spatial tables; the client keeps drawing the body).

### 12.4 Loot and drops (`FUN_00510a70`, steps 4-5)

Order inside the function, with the exact `rand` calls (`rnd(n)` = `FUN_0051fa25`, 0..n inclusive, [items §11](../data/items.md#11-random-generation)):

| # | Step | Condition | Draws |
|---|---|---|---|
| 1 | slot `+0x78` item -> `vtable +0x48` (unequip) -> into the unit's loot bag `+0x7c` (`FUN_00529ac2`) | slot non-empty | - |
| 2 | slot `+0x74` item (the weapon) likewise | slot non-empty and the **weapon item's class parameter 15 (`suitable_for`) != 0** (CONFIRMED `0x510b3f`-`0x510b58`, below) | - |
| 3 | vtable `+0x4c`: humans (`FUN_00512697`) unequip slots 1..12 into the bag; monsters: no-op | - | - |
| 4 | bag **cleared** (old bag destroyed, new empty one) | summoned (`+0x1a0 != 0`) **or** template name contains the text `NPC` (`FUN_0059e063(name + 4, "NPC")`) | - |
| 5 | gold: `rnd(100) < p38` -> `gold = p39 + rnd(p40)` | `unit_type >= 0x40` (monsters; heroes 0x21..0x3f never roll) and not summoned | `rnd(100)`; then `rnd(p40)` only when it hit |
| 6 | item: `rnd(100) < p41` -> build a generator (`FUN_005254e7`: min = p42, max = p43, count 100, stack 1, flags p44), run it (`FUN_00525f67`), pick `rnd(len - 1)`, set its quantity `+0x42 := 1`, add to the bag | same | `rnd(100)`; then the generator's own draws ([items §11](../data/items.md#11-random-generation)); then `rnd(len - 1)` (only when `len != 0`) |
| 7 | **drop**: if the bag has `> 0` items or `gold != 0`: `FUN_005109f5` -> `FUN_0052acf6(cell +0x10, bag, gold, flag)`; a new empty bag is created | - | - |

**What the bag holds and the weapon gate (CONFIRMED).** The `0x510b3f` code is `push 0xf; ECX = [weapon + 0x3c] + 8; call 0x41e7e0` (the same parameter-vector accessor `FUN_005290cc` uses for class parameters 5, 12-14), i.e. the gate reads the **item's class record parameter 15 (`suitable_for`, [items §2](../data/items.md))**, not a creature template column (the monster template p15 = defence is irrelevant). Class values: 1 fighters, 2 mages, 0 nobody; every natural weapon of the data is 0 (Flame Thrower, Sonic Beam, Boulder Thrower), every real weapon, bow, staff and pike is 1 or 2. So a natural weapon never lands in the pile; a real one always does. The shield (`+0x78`) has no gate.
The bag `+0x7c` holds, in this order: (a) the **carried section 8 group** (`FUN_00564072`: for a group linked to a unit, each member slot 0 -> `FUN_00529ac2` into the pack; slot != 0 would equip through vtable `+0x44`, never in the data) - it does **not** contain the equipped weapon; (b) at death the shield, then the weapon, from `+0x78` / `+0x74`; (c) humans: slots 1..12 (`FUN_00512697`, index = the armour class `Slot` 4..12). The equipped objects are created **from the template equipment strings** in the unit constructor and never exist in the carried group: monsters `FUN_00511959` loop over the 2 strings, `Shield` in the text -> shield object (`FUN_00527e23`, 0x6c) else weapon object (`FUN_00528808`, 0x88), then vtable `+0x44` (equip; weapon `FUN_005290cc` sets `+0x74` and returns the old one to the pack); humans `FUN_005145d1` (callers `0x514377`, `0x5143e4`), strings 0 weapon, 1 shield, 2..9 armour (`FUN_005273f0`), skipped when its parameter `param_3 != 0` or the name test at `0x5146d2` matches (INFERRED: a hero restored from a save / campaign state). `FUN_00527a13` (armour equip) returns at once for a non-human carrier; the monster data has no armour or shield strings.
Install results (`equipment_codes`, GOG data.bin): of 97 monster templates with an equipment string 79 drop their weapon and 18 do not (Bat_Sonic 1-5, Catapult, CatapultBase, MercenaryCatapult, Dragon 1-5, Succubus 1-5); Ogre, Troll, Ghost, Bee, Wolf, ... have no string. A killed Orc_Sword drops `0x1104` (Bronze Long Sword) always, plus its carried group, gold 79.2 % (`90 + rnd(270)`) and one generated item 29.7 %; Goblin_Pike drops `0x110f` (Bronze Pike) + gold 59.4 %; Ogre drops only gold (89 %, p38 = 90) and a generated item (p41 = 40); Dragon only gold and the item; Orc_Shaman a Shaman Staff (`0x810e`; the `castSpell` text is not in the code). Fighter_Hero drops the Two Handed Sword plus 5 armour pieces (`0x2126, 0x2730, 0x2833, 0x2936, 0x2a3a, 0x2c3e`).
The gold is **not a coin item**: it is a number on the pile object (`pile+0x3c += gold`); `flag` = (unit is the owner's main hero) -> pile `+0x44`. `FUN_0052ab07`: the pile at the unit's
own cell is looked up (`FUN_00553ab3(cell)`); if one exists the bag is merged into it, else a new pile object (`FUN_0052a71d(cell, bag)`) is created and registered with
`FUN_0052ad3d` -> `FUN_005538c7`; **if registration fails the pile (items and gold) is deleted**.
**Pile placement (CONFIRMED, `FUN_005538c7`, `FUN_0052ad3d`, `FUN_00553ad1`): there is no search for a neighbouring cell.** Only the cell given is tried:
(1) `FUN_00553ab3(cell)` -> `FUN_00553ad1`: a pile exists when bit `0x20` of the static layer (`+0x10000`) is set, the cell record is found and its pile slot (`+0x5403c`) is non-zero; then the bag is merged (items stacked, `pile+0x3c += gold`) **whatever the cell's blocking**.
(2) Otherwise `FUN_005538c7(pile)` fails when bit 0 of the **live layer** (`+0x20000`) is set (`FUN_00550a96`: water / mountain / building ground, any structure stamp `|= 5`, the map border; tree cells set bit 2 only and unit stamps `0x40` / `0x80` do not count, so they hold piles).
Else it makes the cell record if missing (`FUN_005508a0`) and stores the pile in the empty slot (`FUN_00550a53` rebuilds the cell); a record whose slot is already taken refuses (unreachable after step 1).
(3) On refusal `FUN_0052ad3d` calls the pile's deleting destructor (vtable `+4`, arg 1: its bag goes with it) and `FUN_0052ab07` returns 0; the gold is dropped, `FUN_0052acf6` skips the client notice (`FUN_00503672`). The rolls were already drawn. A flyer or ghost dying over water / mountain loses its loot.
The map loader uses the same routine: `FUN_00564072` calls `FUN_0052ab07(cell, pack, extra, 0)` for each ground group after all units and structures exist (and the random fill `FUN_00564b5a` too), so section 8 piles obey the same rule (no install map has a group on a blocked cell; checked against the engine's block layer).
Probabilities (comparison `p38 > rnd(100)`; `rnd(100)` has 101 values, so chance = `p38 / 101`, not `p38 %`): e.g. Orc_Sword p38 = 80: 79.2 %; gold `90 + rnd(270)`; item p41 = 30: 29.7 %, window 180..540, flags `826802175` (`0x3147ffff`). Goblin_Pike: gold 60 -> 59.4 %, `30 + rnd(90)`, no item (p41 = 0: never, since `rnd(100) >= 0`).
Heroes and human NPCs (types `0x21..0x3f`): no roll, but **all equipment (slots 0..12 as above) and the carried bag drop** unless the template name contains `NPC` or they are summoned.
A hero (player unit) dying: bag + equipment drop at its cell, then 12.3 steps 7-8 (main hero: deaths counter and HP -50; any hero of the human: message `0xb4`, which opens the modal load / quit dialog and freezes the sim, 12.3a).
The items stay on the ground at the hero's cell (pile rules above) and survive in the world while the dialog is up.

### 12.5 Regeneration (vtable `+0x14`, `FUN_0050fc5a`) and the open question 3 of simulation.md

Called for every creature (all three class vtables `0x5d0eb0`, `0x5d0f40`, `0x5d0fb8` point to it) **once per block**, from the job `FUN_0052bbb7` at `tick & 15 == 12`.
The counter it tests is `*[0x6044c4]` = the **block** counter. Resolution: **HP regeneration of a unit with id `i` runs on the blocks `b` with `b & 3 == i & 3`: once per 4 blocks = every 64 ticks, and each unit
has its own phase**; mana regeneration has no id test and runs **every block (16 ticks)**; the "HP < 0 loses 1" rule runs when `b & 3 == 0` (every 64 ticks, all units together). The older text in
unit-struct §3 ("every 4th tick", `tick & 3`) was wrong (correction below).

| Case | Rule |
|---|---|
| state 0x10 | nothing |
| HP < 0 | if `b & 3 == 0`: HP -= 1, mask 1. HP == 0: nothing. No mana regen |
| HP > 0 | `k = 3` if `FUN_0050fc3e > 80` else `k = 1` (CONFIRMED `0x50fc5a`-`0x50fc9e`, see "The rest clock" below). There is **no "recently attacked" test**: being hit never touches `+0x138` |

**The rest clock `creature+0x138` (CONFIRMED, exe sha256 in formats/README.md; every store to `[reg+0x138]` of the byte image was enumerated).** `FUN_0050fc3e` (`0x50fc3e`) = `[0x6044c4 + 4]` (the tick) minus `+0x138`, a plain `SUB`
(dword). Its three callers: the regeneration slot `FUN_0050fc5a` (`0x50fc8d`: `CMP EAX, 0x50; JLE` = **signed**, `k = 3` only when the difference is `> 80`; a `+0x138` in the future
gives a negative difference, so `k = 1`; no unsigned or wrap handling), the move sender (`0x504107`, result discarded) and the creature tick `FUN_0050f12c` (`0x50f2e1`, HP > 0 branch: when the sim object `[0x6044c4]` and its `+0x74`
are non-zero, the unit has an owner and `owner+0x38 == unit` (main hero), and the difference is **exactly** `0x50` it sends the client message mask `0x10` once, i.e. re-sends position/facing 80 ticks after the last action;
`[0x6044c4+0x74]` is the same flag the kill counters test, 12.7, INFERRED net-game). Writers (all stores; the formal ctor/copy ones included):

| Where | Value written | When |
|---|---|---|
| `0x504122` in `FUN_005040c4` (client message sender) | `tick + (u8)arg` | move step message `0x6b`: arg = `2 * mover+0xae` = the step ticks (call at `0x51007e`); turn message `0x6d`: arg = `(mover[1] + 8) >> 4` (**dir16 of the target facing, 0..16, not a duration**; call at `0x50ffcd` from `FUN_0050ff2d`, sent in a state-1 tick when the 16-bit position is unchanged and `mover+1` changed during the tick, `FUN_00558b3d`); melee swing start `0x71` (call at `0x504b12` in `FUN_00504ab8`: arg = `+0x134 + +0x135`, truncated to a byte) |
| `0x5041ba` in `FUN_00504155` (message `0x72`) | `tick + +0x134 + +0x135` (dword) | swing start of a unit whose `+0x12c` (attack range) is `> 1` (`FUN_00504ab8`, sole caller `0x516c16`, `FUN_00516b2f`) |
| `0x504292` `FUN_005041d6` (message `0x86`), `0x504369` `FUN_005042ba` (`0x86` / `0x8b`), `0x50446f` `FUN_00504391` (`0x8a` / `0x8c`) | `tick` (now) | cast start, guarded by vtable `+0x2c` of the caster, which is `1` in all three creature vtables (`0x542410` / `0x542720`): always written. Callers `0x519bd7`, `0x519bf3` (`FUN_00519998`, the cast start) and `0x519d23` (`FUN_00519c04`, chain spells) |
| `0x50e3d8` `FUN_0050e173` | `0` | creature init |
| `0x50ea4b` `FUN_0050e48e` | copy of the source's `+0x138` | the whole-object copy (vtable `+0x3c`) |

Nothing else stores it (also checked: no `add`/`inc`/arith forms, other stores at the same offset belong to unrelated client classes). So **walking, turning (any tick that changes the target facing without moving), a melee / ranged swing start and a cast
start reset the rest state; being hit, standing, or the later phases of a swing do not.** A swing's value is `tick + wind-up + recovery`, i.e. in the future for the whole swing (the difference is negative, so `k = 1`, until 80 ticks after that);
a cast writes the current tick, a turn writes `tick + dir16` (so the turn value is a few ticks in the future). Quirks kept: the melee byte truncation (`windup + recovery > 255` wraps; unreachable in the data: the largest sum is 40), and the resend test is `== 0x50`, so it fires only if no other writer ran in between.

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

### 12.5b Human regeneration

Humans (class `0x254`, vtable `0x5d0f40`; heroes and human NPCs) use the same slot `FUN_0050fc5a` (vtable `+0x14`, CONFIRMED by the table at `0x5d0f40`), but data.bin group 6 has no regen columns, so the rates are **constants from the shared creature base constructor**:

| Field | Value | Evidence |
|---|---|---|
| HP regen `+0x98` | **100** | written only by the base creature init `FUN_0050ec60` (`movw $0x64,+0x98` at `0x50ed18`), reached by the human ctor `0x512133` -> `FUN_0050dc2b` -> `FUN_0050e173` -> `FUN_0050ec60`. CONFIRMED |
| mana regen `+0x9e` | **50** | same routine (`movw $0x32,+0x9e` at `0x50ed50`). CONFIRMED |
| nobody overwrites them | | the human ctor `FUN_005121e1` (sets Body/Reaction/Mind/Spirit 30, maxHP/HP 50, speed 16, `+0x134=8`, `+0x135=4`), the loader `FUN_005145d1` / its stream routine `FUN_00514cf2` (reads `+0x84..+0x8a`, `+0x96`, `+0x9c`, `+0x8c`, skills; not `+0x98`/`+0x9e`) and the recompute `FUN_0051366b` (writes `+0x84..+0x8a`, `+0x8c`, `+0x90`, `+0x92`, `+0x96`, `+0x9c`, `+0xa0`, `+0xa4`, `+0xa6`; no `+0x98`/`+0x9e`) contain no write; a scan of every `mov ...,0x98/0x9e(%reg)` in the exe finds only the base init and the object copy (`0x50e8f7`, `0x50e933`). CONFIRMED (scan: INFERRED to the extent that an indexed write could be missed) |

So regen is **independent of Body / Spirit / Mind** except through max HP / max mana (recompute, [progression §3](../data/progression.md#3-what-a-skill-up-changes)). With `bonus = +0xde` (effect kind 8, HP) / `+0xe2` (kind 11, mana), both 0 without effects, and `k` = 1 or 3 (resting) from 12.5:

```
HP   per application (every 64 ticks, own phase) :  floor( maxHP   * 2 * (100 + bonus) * k / 100 )  hundredths of a HP
mana per application (every 16 ticks)            :  floor( maxMana * (100 + bonus2)   * k /  50 )  hundredths of a mana
without effects:  HP +2 % of maxHP * k per 4 s ;  mana +2 % of maxMana * k per 1 s     (k = 3 after 80 ticks without a step)
```

A regen of 0 means "no regeneration" only for HP (explicit `+0x98 != 0` test in `FUN_0050fc5a`); the mana part has **no** zero test (division by `+0x9e`), not reachable for humans (always 50). Mana only moves when `+0x9a < +0x9c`; a fighter with `+0x9c == 0` never regenerates mana. Max HP / mana below are for total XP 0 (`G = 0`), no equipment bonus, attributes below their caps (INFERRED for the data values, the formulas are CONFIRMED in progression §3):

| Unit | Body / Spirit | maxHP | HP gain (k=1) | maxMana | mana gain (k=1) |
|---|---|--:|---|--:|---|
| Fighter_Hero | 41 / 21 | 122 | 244 hundredths = 2.44 HP / 64 ticks (7.32 resting) | n/a (template mana -1: no mage, INFERRED) | - |
| Mage_Hero | 14 / 44 | 14 | 28 hundredths = 0.28 HP / 64 ticks | 146 | 292 hundredths = 2.92 mana / 16 ticks (8.76 resting) |

Dying time (vtable `+0x74` = `FUN_00512526`, CONFIRMED `0x5d0f40`/`0x5d0fb8` slot `+0x74`): template param 23 when the template exists, else -1; -1 becomes **8**. Fighter_Hero has `dying_time = -1` -> 8 (timer `+0x6c` = 7); Mage_Hero has 12 -> 12 (timer 11); removal per 12.1 / 12.3.

### 12.6 Corpse decay (`FUN_005110b8`, from the same job) and what the client draws

The job also calls `FUN_005110b8` for every unit of the **corpse list** (and `FUN_00510a70` for the summon-cap marks below). Per job run (once per block): `if HP > -10001`: when `block` is even,
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

Nothing is time based on the client: only the HP messages. There is no fade; the corpse changes its **graphic** (corpse -> bones -> gone). CONFIRMED client side (`FUN_0040d9b2` `0x41040f`-`0x410495`): the client never receives a removal; its unit object lives on after the server removal
(the server corpse list, 12.2) and is **deleted at death stage 5** (HP < -600; `FUN_0041fff0` + vtable `+0x4(1)`, ids < `0x6000`) - that is why ground corpses are still drawn until then. Counting rules, CONFIRMED: minimap dot
(`FUN_00465f3f`) and pick rect need stage < 2 (a stage-1 body keeps its dot and stays hoverable; bones have neither); the sidebar portrait list (`FUN_00472460`: own CUnits with flag `+0x1b8 & 1` or `& 0x10`) needs stage == 0, so a dying hero leaves it at HP <= 0;
the selection summary (`FUN_004167c2`) counts the objects with the selected flag, which stage 2 clears (12.2). Bones are not selectable by the select-all hotkey (stage <= 1 only, `FUN_00416717`) and the selection marker is drawn while stage < 5.
**Master mark `+0x148`** (summon cap; the "group key" of earlier drafts is the **master's object id**). All CONFIRMED by REA (every `48 01 00 00` displacement in `0x4f0000..0x580000` was checked):
- **Writers (the only four):** `FUN_0050e173` creature init `:= 0` (`0x50e3e5`; reached by the map loader's ctor chain `FUN_005143e4` -> `FUN_00512133` -> `FUN_0050dc2b`); `FUN_0050e48e` copy (vtable `+0x3c`, `0x50ea76`/`0x50ea7c`, copies the source's value); the spell effect `FUN_00519db8`: **Summon (25)** `:= caster+0x04` (the caster's object id, `0x51a839`, right after `+0x1a0 := 1`) and **Control Spirit (22)** `:= 0` (`0x51b0e1`); `FUN_00510a70` step 1 clears it (`0x510ab9`). Neither the map loader `FUN_00561bf9` / `FUN_00562745` (it only sets `+0x194..+0x1a0` from the map unit's behaviour bits, [unit-struct](unit-struct.md)) nor the spawner `FUN_005303ed` writes it.
- **Readers:** (a) the job `FUN_0052bbb7` (below); (b) removal `FUN_00510a70` step 1 (`0x510a9b`); (c) creature loop `FUN_0052b459` at the removal tick: script event 4 ("unit removed", `FUN_0052e07e(4, id)`) is sent **only if `+0x148 == 0`**, so a removed minion raises no event 4 (`0x52bad1`); (d) `FUN_0052be6e` (count of live wandering-type monsters: types `0x40 < t < 99` minus a few, HP > -10, requires `+0x148 == 0`; script counter) and (e) the monster-group spawner `FUN_005303ed` (candidate monsters for an encounter must have `+0x148 == 0`, `0x5306f5`): minions are excluded from both.
- **Job rules** (no tick test inside; called at `tick & 15 == 12`, [simulation](simulation.md)): pass 1 walks the creature list `0x672f64` in list order; each creature with key != 0 increments `count[key]` (MFC `CMap`, block size 10, `FUN_00545780` / `0x5459d0` operator[] / `FUN_005457e0` lookup). Pass 2 walks the map (`FUN_0053d920` / `FUN_0053d940`): for **each key** one world-RNG draw `r = FUN_0051fa4e(100)` (`rnd1`, 1..100); if `r < count` the key is marked (value := -1) - so the chance is `(count - 1) / 100` (1 minion: never; 2: 1 %; ... a draw is spent per key even for a single minion). Pass 3 walks the creature list again: the **first** creature of a marked key (value -1 -> -2) is removed with `FUN_00510a70` (HP := -10000, key cleared, state 0x10; no corpse), the other minions of that key are untouched. So one minion at most per master per job (every 16 ticks).
- **Reachability:** the key is non-zero only for units made by the Summon spell during play (hero or any caster of spell 25); a map file cannot set it (the loader creates every unit through `FUN_0050e173`, key 0; saved games are out of scope). **No campaign map can produce a non-zero `+0x148`**; the job is a no-op on all 46 maps until the Summon spell exists in the engine. Spell level and flags: [spells §9b](../data/spells.md).

### 12.7 XP at a kill

The kill credit is paid **at the removal tick** (12.3 (c), `0x52b6c7`..`0x52b84a`), not at HP <= 0. Chain: `victim+0x40` (last attacker, written by `take_hit` **at every hit** that has an
attacker template, the last one wins, [5.2](#52-take_hit-fun_00516f6f-confirmed-vtable-54-of-every-creature-class)) must be an object whose owner exists (else cleared, `0x52b4b0`). Killer type `0x21..0x3f` and HP not < 0
(`FUN_00542770`) -> killer vtable `+0x68` (`FUN_00512fcb`, humans only; monsters' slot `0x5423e0` is a stub) with `(victim, spell byte +0x48)`. Details, amount (`0.5 * victim.xp` through the repeat-kill discount), repeat list, schools:
[progression §4](../data/progression.md#4-xp-sources); not repeated here. Only the unit in `+0x40` gets the kill credit (no party / group share); the others got per-damage XP only. Kill counters:
victim type `0x21..0x3f` -> `owner+0xa4c += 1`, `[killer-owner + ...]` message `0x94` if `[0x6044c4+0x74] != 0` (net, ignore); else `owner+0xa48 += 1`; message `0x2000000` to the killer's owner; per-owner kill table byte
`owner+0x44+server_id` (cap 14) incremented, a message `FUN_00505582` when the new value is even (bestiary-style counter, INFERRED). A non-hero killer (monster) gets nothing (a log line only when the victim is a human type).
Level-up when a skill threshold is crossed: `FUN_005128cb`, effects in [progression §3](../data/progression.md#3-what-a-skill-up-changes) (client event `FUN_005052d2` event 2 only for the human owner, stat message with flag `0x100 << (k-1) | 0x3000c`); no
extra effect object, sound or floating text exists in these server routines. **Client side, CONFIRMED** (`FUN_0040d9b2` case `0x92`, sub-type `*(msg+0xa) == 2`, `0x40e2a3`-`0x40e68e`; allods2.exe sha256 in formats/README.md):
- **Message line only.** `k = low16(msg+0xe)` (the school 1..5), unit id = `high16`. Text = `main.txt[0x81 + k]` ("Blade skill improved" ... "Shooting skill improved"), or `[0x86 + k]` ("Fire" ... "Astral skill improved") when the leveled unit has the flag `+0x1b8 & 2` (mage; INFERRED meaning, the two text ranges match weapon / spell schools). In a game (`[this+0x5d8] == 2`) the unit is looked up (`FUN_0041d95e`) and the line becomes `text + " (" + unit name (+0xec) + ")"`. Shown by `FUN_004021fe(text, [0x5f17f4], 0xbb8)`: the view's message line (`this+0xa28`), **3000 ms** - the same call as "No way" ([ui-layout](ui-layout.md)).
- **Sound.** If the client option word `[this+0x404] & 1` is set: `FUN_0045aa2f` on the sound object `*FUN_00420eb0(0xf)` of the global table `0x627740` (entry 0xf), position base `[0x622698]`, volume 100, no pan: a non-positional UI sound shared by all the sub-type 3..8, 0x10.. lines (new player, player left, ...); "No way" (sub-type 1) plays none. Which file entry 0xf is: open question.
- **No** floating text over the hero, **no** effect sprite, **no** info-panel flash in this handler (the stat-change message `FUN_00502019(0xffb)` was not traced to its client handler: INFERRED to be a plain value refresh like the HP message, no flash).
- Kill: **no kill-count notification** is drawn. Message `0x94` (case `0x94`): player-vs-player kill line `"<killer> <text 0x50> <victim> <text 0x51>"`-style (`s_%s_%s_%s_%s_%s`, texts via `FUN_00474733(0x50/0x51)`) into the message line; `0x94` is only sent when `[0x6044c4+0x74] != 0` (net game), so single player never shows it. Single player shows nothing for a kill besides the victim's own death animation / sound (12.6).
- **Unit sounds** (vtable `+0x74` of the view unit, `FUN_00467e42(k)`, CONFIRMED): `k = 0` blow that did not change HP (0x73 with equal HP), `k = 1` damaged, HP >= max/2, `k = 2` damaged, HP < max/2 (both `k = 1, 2` limited to once per 1500 ms per unit, `+0x1bc`), `k = 3` death (death stage 0 -> 1, `0x4106be`; the stage 1 -> HP update re-entry plays `k = 2`, `0x4107ad`). The sound is the unit type's sound set entry `k + 1` (monsters and humans with `flags & 0x11 == 0 && type > 0x17`), else for heroes the three voice samples at `FUN_00468094()+0x50/+0x54/+0x58`; played positional (`FUN_0041b1f8` screen position, volume `(10000 - FUN_00582c40(x)) / 100`, base `[0x6226a0]`). Which `units.reg` / data.bin field supplies the entries: open question.
- **Loot drop (message `0x7a`, `0x40e...` case): CONFIRMED no sound.** The handler creates the item pile object (`FUN_004601cd`, position update `FUN_0046025d`) and sets its frame from byte `+0xd` (cap 5, the backpack-frame-by-gold picture); neither routine calls `FUN_0045aa2f`.
- **Scenario hook.** At death stage >= 2 the client calls scenario.dll export 2 (`[0x627298]`, `0x41050f`) with `0x213 + obj+0x1dc` (type < 0x15): a script notification, no visual.
- **Hero hint.** When the local main hero (`this+0x3f6c`, mode != 2 test as `FUN_0040d9b2` `0x4105xx`) of unit class 4 reaches death stage 2-4 from stage < 4, two message-line texts `main.txt[0x44]`, `[0x45]` (the shop-table captions) are printed through `FUN_004021fe` (INFERRED to be a leftover; not drawn).

### 12.8 Corrections made to older text

1. unit-struct §3 (vtable `+0x14`): "every 4th tick (`[0x6044c4] & 3 == id & 3`)" and "HP<0 loses 1 per 4 ticks": the counter is the 16-tick **block**; real periods 64 ticks (HP regen per unit, HP<0 loss), 16 ticks (mana).
2. simulation.md open question 3 resolved (above).
3. unit-struct `+0x138`: was UNKNOWN, then "tick at which the last move step ends": it is the rest clock written by the move, turn, swing and cast messages (12.5); `+0x13c`: also the server corpse stage 1..5.
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
8. The hero dying in single player: items on the ground at its cell; the dialog (12.3a) appears at the removal tick with the sim frozen; its buttons (quit to menu / load).

### 12.11 Open questions

1. Who writes the main-hero pointer `owner+0x38`, who resets the dialog latch `[this+0x3e8]`, who sends `0xb5` / `0xb6` (results `0xfe`, `0xfd`, `0xfa`: victory / defeat scripts?) and what `owner+0x40` is read for (start: callers of `FUN_00505347`: `0x4f0b71`, `0x4f0c67`, `0x4f3d68`, `0x4f515d`, `0x4f856a`, `0x505d02`, `0x516238`, `0x5162f6`).
2. Summon-cap job (12.6): MFC `CMap` iteration order decides the order of the per-key RNG draws when two or more masters have minions: confirm the table size (default 17, lazy `InitHashTable`) and the hash (`0x545a60`, INFERRED `key >> 4`), new node at the head of its bucket chain (CONFIRMED `0x545a0f`-`0x545a46`); then implement it with the Summon spell (`FUN_00519db8` case 25).
3. What the pile, pickup and the equip path keep of a dropped template item's effect text (`{castSpell=Fire_Arrow:5}` on shaman staves): the engine's pile code is 16 bits and loses it (start: `FUN_00529ac2`, `FUN_0052a71d`, item object `+0x50` effects).
4. Sound tables (the engine has no audio): which `.res` / data.bin entries are the unit sound set entries `k + 1` (`FUN_00467e42`, template `+0x24` -> `FUN_00420e30` -> `FUN_00402880`), the hero voice samples (`FUN_00468094 +0x50..+0x58`) and the UI sound `0x627740[0xf]` of the skill-up line (start: `FUN_00420e30`, `FUN_00420eb0`, `0x481967` scenario.dll ordinal loader).
5. Map-script listeners of the server event queue (`0x68d360 + 0x20`, `FUN_0052e198` vtable `+0x14`): which condition classes consume event 4 (unit removed), 5 and 0xf, and what the campaign scripts do with them (start: `FUN_0052eac8`, the listeners built by `FUN_0052e3eb`).

## 13. Engine (I2): death, corpses, XP, loot, regeneration

Design and assumptions: [spec](../superpowers/specs/2026-10-18-death-design.md). Files: `engine/sim/death.py` (`dying_tick`, `remove_dead`, `drop_loot`, `decay_step`),
`engine/sim/vitals.py` (`vitals_system`: the `tick & 15 == 12` job, first system of the step), `engine/sim/xp.py` (`award`, `damage_credit`, `kill_credit`, `level_up`),
`engine/world.py` (`DEAD`, `World.corpses`, `find_unit`, `bury`, `death_stage`, events `Removed`, `LevelUp`, `Loot`; `Unit.death_seen/death_tick/step_end/hp_acc/mana_acc/carried/kill_list`),
view `engine/view/drawlist.py` (`unit_frame` by death stage, corpses drawn, bodies pickable while stage < 2, hover and mana bars), `engine/backend_pygame/interface.py` (`info_rows`).
Tests: `tests/test_engine_death.py`.

| Rule (C§12) | Engine |
|---|---|
| 12.1 HP <= 0 branch, `T0`, countdown, `HP < -9` removal | `death.dying_tick` from `movement._tick_unit`; `Unit.timer` is the exe's `+0x6c`; the unit stays in `world.units` (blocks) until `remove_dead` |
| 12.2 attackers | `combat.refresh_attack` / `attack_mode` use `World.find_unit`; only a missing id or state `0x10` stops them; `resolve_attack` hits any target, HP unclamped, `Damage` logged by the `0x73` rule |
| 12.3 removal | `World.bury` (spatial index, group, selections; ground units to `World.corpses`, flyers / ghosts dropped), loot, one decay step, `Removed`, kill credit |
| 12.3a hero death | `death.remove_dead`: step 7 for `Player.main_hero` (`hero_deaths += 1`, HP -50), step 8 for any hero of the human (`death_code = (server_id - 0x13) & 0xff`, `defeat_dialog`, `HeroDied` after `Removed`) |
| 12.4 loot | `drop_loot`: world RNG in the exe's order; the pile is an `Item` on the unit's cell, merged into an existing one, else created unless `World.pile_blocked` (then deleted, no neighbour search; `World.place_pile`); carried codes from the section 8 group, then the template equipment codes (`combatstats.equipment_codes`); generated item code `GenItem.code & 0xFFFF` |
| 12.5 regeneration | `vitals.regen`: HP on `block & 3 == id & 3`, drain on `block & 3 == 0`, mana every block; monsters p5 / p7, humans 100 / 50 (12.5b); `k = 3` when `tick - Unit.step_end > 80` (signed; writers: `movement._start_step` step, `movement._tick_unit` turn `tick + dir16`, `combat.swing_tick` swing `tick + windup + recovery`; casts: with the spell system) |
| 12.6 corpses | `decay_step` on even blocks; stages and draw: `drawlist.unit_frame` (dying from `death_tick`, then bones 1-3, nothing at stage 5) |
| 12.7 XP | `xp.damage_credit` (per hit), `xp.kill_credit` at the removal tick (last hitter, hero with HP >= 0), `xp.award` (Mind, repeat list, off-school, span cap, pool), `xp.level_up` (max HP / mana recompute, combat stats cleared, `LevelUp` event) |

Decisions and assumptions (INFERRED unless marked): `Unit.step_end` is written by the move step, the turn (when the target facing changes in a tick without movement), the swing start (`windup + recovery`, byte-truncated for range <= 1) exactly as the exe's stores (CONFIRMED, 12.5); the cast writers (`tick`) are added with the spell system; the main-hero resend at difference `0x50` is a client notification and is not modelled; the client skill-up line (12.7) is drawn by `engine/ui/orders.level_up_messages` (message line, 3000 ms, view layer only); the skill-up sound, unit hit / death sounds (12.7) and the scenario hook are **not drawn / played yet** (no audio in the engine); no floating text, effect or kill notification exists in single player (CONFIRMED 12.7); the summon-cap job (`+0x148`, 12.6) is not modelled: no campaign map can set the key and the Summon spell does not exist yet; hero = human with a hero template name; effect / equipment bonuses of regeneration are 0; the loot bag is the `carried` group plus the template equipment (`combatstats.equipment_codes`: shield, weapon only when its class parameter 15 != 0, human armour slots ascending; CONFIRMED 12.4), item effect texts are not kept in the pile code; the pile
is always on the unit's own cell (CONFIRMED, no search; refused on a blocked cell); a level-up keeps the current HP / mana; a hero of the human player that reaches state 0x10 logs `HeroDied` (message `0xb4`, 12.3a) and sets `Player.defeat_dialog` / `death_code`, the main hero (`Player.main_hero`, INFERRED = first hero of the human at load) also counts `hero_deaths` and gets HP -50; the modal dialog and the sim freeze are UI work, not engine; the selection drop (CONFIRMED stage >= 2, plus a DECISION to drop at removal, <= 32 ticks early);
corpses are drawn before living units; a body is pickable and has a minimap dot while its death stage is < 2 (CONFIRMED). HP stays a Python int (the exe's s16 never wraps within the HP range of play).

## 14. Spell casts (I4a)

Research: [spells §9c](../data/spells.md#9c-the-cast-chain-of-a-unit-target-spell-i4a-research-rea-of-the-gog-exe) (CONFIRMED chain). Design: [spec](../superpowers/specs/2026-10-19-spell-cast-design.md),
plan [I4a](../superpowers/plans/2026-10-19-i4a-spell-cast-sim.md). Files: `engine/sim/spells.py`, `engine/sim/commands.py` (`CastSpell`), `engine/world.py` (`SpellCast`, `Carrier`, `World.carriers`,
`World.spell_table`, `Unit.cast/cast_target/cast_wrapper/mode_cast/spellbook`, events `CastStarted`, `CastReleased`), `engine/sim/combatstats.py` (`CombatStats.weapon_spell`), tests
`tests/test_engine_spells_math.py`, `tests/test_engine_spells_cast.py`, helper `tests/spell_helpers.py` (a synthetic Fire Arrow, no install).

| Rule (spells §9c) | Engine |
|---|---|
| 9c.1 command `0x1e`, order `0xd` | `CastSpell(player_id, unit_ids, spell_id, target_id)`; `orders.orders_system` -> `intake` (a new group), `spells.cast_group`: `_cancel_group`, then per member that has the spell in its book (`spells.wrapper_of`, `known_mask`) `spells.set_cast` (cancel, order `0xd`, `cast_target`, `cast_wrapper`, `range` = wrapper range, Brain mode 0). Members without the spell are only cancelled |
| 9c.1 group pass | `orders._pass_orders`: order `0xd` -> `spells.refresh_cast` (Brain mode 8 = `Unit.mode_cast`, range refreshed); at `tick & 15 == 6` like an attack |
| 9c.2 mode 8 | `movement._tick_inner` -> `spells.cast_mode`: out of range (facing + gap level, `in_cast_range`, the melee test) -> `follow_drive` and state 1; else `brain_order = 2`, `Unit.cast = SpellCast`, then `stop_unit` (state 0, order `0xc`) |
| 9c.2 brain order 2 | `spells.brain_cast`: state `0xd`, count, ends when count > 2 and the done flag is set (a Stop or a new order cannot interrupt it) |
| 9c.2 phases | `spells.cast_tick` (state `0xd` of `movement._tick_unit`, and state 3 for a staff mage via `combat.swing_tick`): phase 0 `cast_start` (mana check and spend for a mage's learned spell, `CastStarted`, `step_end := tick`), phase 5 windup (`CombatStats.windup`) then `cast_release`, phase 7 recovery `st.recovery + hero_delay + rand(0..3) + complication` (the complication only for a learned spell) |
| 9c.3 release | `cast_release`: cast XP (`xp.award(int(0.5 * mana + 0.5), school = sphere)`, learned spells of mages), level (`unit_level` or the item count), a missile `Carrier` with `flight_ticks` of the distance **now**, `CastReleased` |
| 9c.3 carriers | `spells.carrier_system` runs **before** `movement_system` (carriers pass, then creature pass); a missile counts down and appends a point carrier to the same pass, `apply_point`: `take_hit_detail` with the elemental record (`spell_record`), HP, last attacker, `ai.on_hit`, `xp.damage_credit`, `Damage` / `Died` |
| Staff | `CombatStats.weapon_spell` = `(spell, count)` from the wielded weapon's `castSpell=` effect; `combat.swing_tick` hands a mage's swing to `cast_tick` (level = count, no mana, no complication) |

View and UI (I4b, plan [I4b](../superpowers/plans/2026-10-19-i4b-spell-cast-view-ui.md)): `Carrier.start` / `flight` / `aim` make the missile a pure function of the tick;
`drawlist._carriers` (pass 6 = projectiles, `PASS_PROJECTILE`) draws the missile (`ProjectileSet.frame_at("flight", facing16, age, age0=-1)`, `.16a` alpha blend of
`SpriteCache` / `sprites.blend_alpha`: `min(src * (a + 1) / 16 + dst * (15 - a) / 16, 255)`) and its 6-point smoke trail (frames 0..5 of the smoke file, oldest first, **after the body**: the trail
loop at `0x46cf31` follows the body draws, CONFIRMED by call order); the position is the straight line from the release position to the target's current position over `flight` ticks
(`missile_position`), age = `tick - born`, so the missile reaches the target on the last tick before the damage. `AssetCache.projectile_set(pid)`; projectile id = `2 * spell + 8`. The cast animation is
the attack action restarted at the cast start (`cast_start`: `action = "attack"`, animation.md 2.4 shares the block). UI: `C` (the original key of button 5) arms `pending = CAST` with the spell
`castable_spell` finds (the lowest unit-target damage spell in a selected unit's book that its mana pays; the spellbook window is a J item), the cast cursor exists already, a click on a unit sends
`CastSpell` (`OrderInput.release`, cmd `0x1e`), a click on the ground sends nothing (cell casts are phase K) and the mode resets either way, right release cancels it and keeps the selection (R 1.5).
There is no clickable command bar in the engine yet: the panel button of the spec belongs to the command bar of J1. VERIFY IN GAME (INFERRED here): missile spawn height (`MISSILE_Z` = 28 px) and
facing rounding, the trail not drawn when the carrier is younger than one tick, that the cast button is disabled when the mana is short, `C` + click instead of the spellbook.

Timeline (tests): order at tick T0; the next `tick & 15 == 6` is `P`; `CastStarted` at `P + 1`; `CastReleased` at `P + 1 + windup`; the damage at `release + max(flight, 1)` with
`flight = trunc(sqrt(dx^2 + dy^2)) / speed` (positions in 1/256 cell, Fire Arrow speed 200: 8 ticks at 7 cells).

Decisions (INFERRED unless marked): the cast order has no cell variant yet (`0xe`, `0x1f`: phase K); a missing target id stops the unit like an attack does; a caster is "gone" when it left `world.units`;
spell damage goes through the exe's own `take_hit_detail` (the to-hit roll is drawn even for a spell, CONFIRMED structure of `FUN_00516f6f`); level of a monster caster is 0 (`spell_power`/skills are not
loaded for monsters, AI casting is phase K); the target `brain+0xa4/+0xa8` stamps (AI buff logic) and the Invisibility break of the caster (`FUN_005106d2(0xc)`) need the effect system and are not modelled;
a staff has no charge counter; pack items (scroll command `0x25`) do not exist yet. VERIFY IN GAME: spells §9c.4.

## Open questions

1. Monster weapon bonuses: confirm in play that `damage = template + weapon` (11.1); the code order says yes.
2. `FUN_005106d2(0x14/0x1c)` effect lookups and the `FUN_00516b2f` invisibility flag need the effect system (K).
3. `FUN_0056ed4e` auto scan and `FUN_0056a1fb` guard scan (target choice, visibility) - AI phase.
4. What the client does on `0x73` besides the number (`vtable +0x74` of the view unit: pain animation or flash).
5. Whether the timer byte really wraps at 0 (a recovery of 0) - needs a data row or a spell effect that produces it.
6. I2 open questions are in 12.11; assumptions in section 13 (hero test).

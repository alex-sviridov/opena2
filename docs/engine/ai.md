# Monster AI (phase I3)

REA-checked against the GOG `allods2.exe` (sha256 in [formats/README](../formats/README.md)). Facts are **CONFIRMED** (decompiled or
disassembled at the given address) or **INFERRED**. Conventions: `u` = creature, `brain` = `u+0x1c4`, `mover` = `u+0x1c0`, `pos` = `u+0x10`;
`DAT_006044c4` = server object (`[+0]` = 16-tick block counter, `[+4]` = tick, see [simulation §1](simulation.md)); `pf` = path finder
object (`server+0xa50`). Related: [combat](combat.md), [simulation §8-9](simulation.md), [click-to-move §4.4-4.5](click-to-move-research.md),
[unit-struct](unit-struct.md), [units](../data/units.md).

## 1. What the original does (summary)

There is **no per-monster aggro radius, leash timer or alert flag**. Monsters are the units of computer-owned players
(`player+4 != 1`) and are driven by **squad groups** (the map's per-owner `squad` number, [map.md part 5](../formats/map.md)): at map load every
non-human squad gets group order `0x12` (`FUN_00570aba`, called from `FUN_00562745` at `0x5629c5`). The group handler `FUN_005728fa` runs
inside the group pass `FUN_0056fe4d` at `tick & 15 == 6`, i.e. **every 16 ticks, all groups in the same tick** (no stagger by unit id;
players in id order, groups in creation order, members in list order). Everything below is the body of that handler plus the per-unit
routines it calls. The brief's states map onto it as follows:

| Brief | Original |
|---|---|
| idle / guard | member in brain mode 0 / `0xb` at its anchor `brain+0`, running the guard scan `FUN_0056a1fb` (§7) |
| alerted / chasing | a target `brain+0x20` was assigned by the group scan (§4-5): `FUN_0056acc8` sets brain mode 5 (attack with approach) |
| attacking | mode 5 in range: swing (I1, [combat](combat.md)) |
| returning | `FUN_0056c8af(u, anchor)`: brain mode 1 towards `brain+0` once the group has no target for the member (§6) |
| fleeing | post step `FUN_00573713` after every handler (wimpy / withdraw HP thresholds, §9) and the hit-reaction run-away cell (§8) |
| group alert | the **pool** is group wide: one member that sees a hostile gives every member a target (§4) |
| leash | none: the radius `+0x2d` only limits which hostiles enter the pool (§3), the anchor is the post (§6) |

## 2. Group record and set-up (CONFIRMED)

Group record = `group+0x3c` (shared with the command groups, [click-to-move §4.4](click-to-move-research.md)); AI fields:

| Off | Meaning | Writers |
|---|---|---|
| `+0x00` u16 | home word (unused by members) | `FUN_0057026e` := `+0x28` |
| `+0x20` u8 | group order, `0x12` | `FUN_00570aba` |
| `+0x24/+0x28` | centroid: `+0x24` = `(cy16 << 16) + cx16` (16-bit mean positions, `cell*256+sub`), `+0x28` = `(cy16 >> 8) << 8 \| (cx16 >> 8) & 255` (cell word) | `FUN_0056f850`, every pass `FUN_0056fa63` (same maths) |
| `+0x2a` | max over members of Chebyshev(cell, centroid cell) | same |
| `+0x2b` | max member `scan_range` (`u+0xa5`) | same |
| `+0x2c` | max over members of (that distance + `scan_range`) | same |
| `+0x2d`, `+0x38` | pool radius (cells) and its base | init (below); `+0x2d` rewritten once, §3 |
| `+0x30`, `+0x34` | "seen once" flag and pass counter | handler |

**Init `FUN_00570aba(group, 0)`** (map load, single player, new game): `FUN_00570e83` (cancel every member, group order := 0); every member
`FUN_0056d4ba` (cancel, order `0xb`, anchor `brain+0` := own cell when at a cell centre else `mover+6`, brain mode 0); group order := `0x12`;
`FUN_0057026e`: `FUN_0056f850` (the stats above), `+0x2d = +0x38 := +0x2c`; then `if +0x2d < MinimalGuardRange: +0x2d = +0x38 := 0x14`
(20); `+0x39 := 0`. `MinimalGuardRange` = registry key `Scanning\MinimalGuardRange` read at `0x5683a7` (`FUN_004e6f9f`) with default 10; the
install's `world/data/map.reg` has no such key (only `ScanShift`), so **10** (CONFIRMED by scanning the file). The human's squads get
group order 3 instead (`FUN_00562745`).

## 3. The group pass `FUN_005728fa` (CONFIRMED, asm `0x5728fa`-`0x572d54`)

Per pass, in this order:

1. `FUN_0056fa63`: recompute the centroid, `+0x2a/+0x2b/+0x2c`.
2. `FUN_00571c4d` **build the pool** (§4): visible, living hostiles into the list at `server+0xa68`.
3. `FUN_00567e92(centroid word, +0x2d)`: delete every pool unit whose Chebyshev distance (`FUN_00558fe9`) from the centroid **cell** is `> +0x2d`.
4. `FUN_0057240b`: per member, `brain+0x20` := the pool unit with the smallest `FUN_005711ea` score (§5), strict `<` (first wins), or 0 when the
   pool is empty or every score is `0xffffff`. (A debug record is posted through `FUN_0057b210` when the log flags are set: no effect.)
5. `if +0x30 == 0 { +0x2d := +0x38 + 4 + rand(-1..1) (FUN_005726f7); +0x34 := 0 } else { +0x34++ }; +0x30 := 1`. `rand(-1..1)` =
   `FUN_0057aff0(-1, 1)` = `rand15 * 3 / 0x8000 - 1` (the CRT `rand`, world RNG). So the radius is the base + 3..5 **after the first
   pass**, and the pass counter is otherwise unused. (The `+0x30 == 0` empty-group branch with `FUN_0057272c` is unreachable for a
   non-empty group.)
6. Per member `m` in list order (`FUN_0055f240` = next), with `B = m.brain`, `blk = [DAT_006044c4]` (block counter, u16), `tk = [DAT_006044c4+4]`
   (tick), `dB = |B+0x16 - blk|` (`FUN_00582c40` = abs, **unsigned 16 bit stamp minus block, then abs**):

```
if hp != hp_max and dB < 30:                  go(m, B.hitcell)         # +0x9c
elif dB < 10:                                 go(m, B.hitcell)
elif B.target != 0:                           FUN_0056acc8(m, target)  # attack, §6
elif hp != hp_max and |B.hit_tick - tk| < 10: go(m, B.hitcell)         # recently hit, nobody to fight
else:                                         # the +0x9e wander branch at 0x572bb1 is dead code (xor eax,eax; test; je)
    if cell(m) == B.anchor and at_centre(m):  guard scan FUN_0056afac(m, 1) = FUN_0056afd9   # §7
    else:                                     go(m, B.anchor)          # return to the post
go(m, c) = FUN_0056c8af: brain mode := 1, brain+0xa := c   (order, group and target untouched)
```

`B+0x16` is the **path-failure stamp** written by the follow planner ([simulation §7.4](simulation.md): `block` counter when a mode-5 unit
cannot get within range of its target); `B.hitcell`/`hit_tick` come from the hit reaction (§8). `hitcell` is 0 until the first hit, so a
failure stamp on a never-hit unit sends it to cell (0, 0) (clamped by the mode-1 mover): **INFERRED quirk, VERIFY IN GAME**.
After the handler, the post step `FUN_00573713` runs for every member of every group (§9).

## 4. The pool `FUN_00571c4d` and the sight map (CONFIRMED)

1. Clear the visibility grid (`pf+0x2a008`, 256x256 bytes, `FUN_00553681`).
2. For every member: `FUN_00553329(m, cell word)` = **`FUN_00552c28`**, the sight flood, marks cells (§4.1). If the owner is computer controlled
   (`owner+0x2c != 0`) and `brain+0x58 != 0` (the **attacker's cell** stored by the hit reaction): grid[`brain+0x58`] += 1; `brain+0x5a++`;
   `if brain+0x5a > 20: brain+0x58 := 0`. So a hit reveals the attacker's cell to its group for 21 passes (336 ticks) even outside sight.
3. Every creature of the world (`pf+0xa456c` list) whose **cell word** has a non-zero grid byte is added to the pool.
4. `FUN_00567a16(first member, pool, 0)`: delete units the owner is **not at war with** (`relations[owner][other] & 1 == 0`, matrix
   `server+0xa8bc`, `[a*0x46 + 8 + b]`); and delete a unit with flag `+0x144 & 0x1000` (hidden) unless some member detects it
   (`reach_gap(hidden, member) <= member.brain+0x71`, `see_invisible`, data.bin p36). No effect sets `0x1000` yet, so the engine ignores the clause.
5. `FUN_00567ddf`: delete pool units with HP < 1.
6. When the pool is empty and `FUN_0044fc20` of the second list (`server+0xa88`, filled by caster code) is non-empty, those units are added:
   phase K (the list is empty for melee monsters).

### 4.1 Sight flood `FUN_00552c28` + `FUN_00552af8` (CONFIRMED)

Tables built once by `FUN_005536a4` (`ScanShift` = 7 from `Scanning\ScanShift`, `1 << 7 = 128`), 41x41 window, offset `(i, j)` in -20..20:
`cost(i, j) = trunc(sqrt(i²+j²) * 128 / max(|i|, |j|))` (128 straight, 181 diagonal; the centre 0); parent step `par(i, j)` (toward the centre) by
`a = |i|, b = |j|`: `b < a>>1` -> along x only; `a*2 < b` -> along y only; else diagonal (each axis one step toward 0); overrides
`par(+1, 0) = (-1, 0)`, `par(-1, 0) = (+1, 0)`. Flood from observer cell `o` with scan range `s` (`u+0xa5`), observer height `h0 = heights[o]`:

```
acc = {}                                              # memset 0, window 64x64
acc[0,0] = (s << 7) + 64 ; visible[o] = 1
for k in 1..19:                                       # not 20
    dark = True
    for j in -k..k:                                   # four cells per j, in this order
        for (i2, j2) in ((j, -k), (j, k), (-k, j), (k, -j)):
            if cell o+(i2,j2) inside [8, size-9] (FUN_00559536 / pf+0x58eb8..bb):
                acc[i2,j2] = acc[(i2,j2)+par(i2,j2)] - (cost(i2,j2) + (heights[o+(i2,j2)] - h0))   # FUN_00552af8, heights signed byte
                if acc[i2,j2] > 0: visible[...] = 1 ; dark = False
    if dark: break
```

Unwritten `acc` entries are 0 (so a parent outside the map is dark). Radius on flat ground ~ `s` cells; higher ground between observer and cell
shortens it, lower ground lengthens it (negative height step adds light). `FUN_00552929` is the variant without the +64 and is used by
other callers (not the AI). The sight flood is the **only** vision rule: no facing cone, no fog, no per-owner map knowledge.

## 5. Target score `FUN_005711ea(me, cand)` (CONFIRMED, asm `0x5711ea`-`0x5713f5`)

```
d     = Chebyshev(cell(cand), cell(me))                    # FUN_00558fe9, cells (no footprint)
cls   = cand.movement_class                                # vtable +0x20 -> +0x4a: 1 walker, 2 ghost/bee, 3 flyer
if cls == 1 and attack_range(cand) > 1: cls = 0           # FUN_0056ac5b(cand): a ranged walker
if attack_range(me) > 1:  pref = T[cls];  d = d - range(me) + 1 if d > range(me) else 1      # shooter: row 0, distance past its range
else:                     pref = T[me.movement_class*4 + cls]
T = [2,1,2,4,  4,2,1,0,  2,1,4,0,  2,1,2,4]                # server+0xa54, built at 0x56827a..0x568310
ang   = FUN_0055aa21(me.facing, octant(me, cand))          # |a-b|, folded to <= 0x80 (a byte)
score = d * 256 + ang
pref 0 -> 0xffffff (not a target)
pref 1 -> if size(me) < 2 and mind(me) >= 15: score += score >> 1          # worse for a clever small unit
pref 4 -> if size(me) < 2 and mind(me) >= 15: score -= score >> 2          # better
if cand.flags & 0x40000: score = max(score + 0x7f, 1)      # effect bit: engine has no effects yet
```

The table values are *classes*, not weights: 0 = never a target (a melee walker or ghost never targets a flyer), 2 = plain, 1 = a 50 % worse score
and 4 = a 25 % better score, both only for a small unit (size < 2) with mind >= 15. A melee walker (row 1) therefore favours ranged walkers (4) and
penalises ghosts only through 1 -> cand class 2 (value 1). The smallest score wins: **nearest in cells, then smallest facing change**. `me.facing` is `mover+0` (the current direction byte, `Unit.facing`), `octant` is `FUN_005568e4`.
`mind` = `u+0x88`, size = vtable `+0x1c` = `u+0x49` (token size).

## 6. Attack and return execution (CONFIRMED)

`FUN_0056acc8(m, t)` (the member has a target): if the target's `+0x4c & 8` (player-hero flag) is set -> guard scan `FUN_0056afac(m, 0)`; special
attacks (spell slots `brain+0x7c+4i`, probability `rand15 < brain+0x88+4i`, last slot that passes; `FUN_0056a981`) -> **phase K**; if no spell:
`m == t` -> no target; target 0 -> `FUN_00567988` (nearest enemies list) -> guard scan; for a non-computer owner `FUN_0057a769`; for monsters
(`owner+0x2c == 0` branch is the *human-owner* branch; monsters take the else): `brain mode := 5`, `brain+0xc := t`, `brain+0x14 := FUN_0056ac5b(m)`
(range); a **ranged** unit (`FUN_0053a5a0`, range byte `< 2`) calls `FUN_0056bc7b` (caster scan: phase K). Mode 5 is the I1 melee driver
(`attack_mode`, [combat §2.3](combat.md)); the follow planner stamps `brain+0x16` when the target is out of reach (§3). Order, anchor and group of
the unit are unchanged (an AI attack is **not** order 3).

Returning: `go(m, anchor)` every pass until `cell == anchor` at a centre; then mode 0 and the guard scan.

## 7. Guard scan `FUN_0056a1fb` (CONFIRMED)

Run for a member standing on its anchor (§3 last branch), for any unit that reaches order `0xc`/`0x17`/`0xb` idle, and by the retreat step. Candidates
are the single-unit pool built by `FUN_00569fd4` (same steps as §4 with only this unit's sight flood, then `FUN_00567a16`, `FUN_00567ddf`).
`best` starts empty with `bestgap = range + 1` (`range = FUN_0056ac5b`, byte arithmetic); for each candidate `c` with `FUN_005711ea(u, c) !=
0xffffff`: `g = reach_gap(u, c)` (`FUN_00556dcd`), `+1` if `class(c) == 3 and class(u) != 3`, `a = FUN_0055aa21(facing octant(u,c), u.facing)`;
`g < bestgap` -> take; `g == bestgap and g <= range and a <= besta` -> take. After the loop `range < bestgap -> none`. A hit -> `FUN_0056c840`
(brain mode 6 / spell `FUN_0056b059`; melee: mode 6 = `FUN_0056eff3`, target `brain+0xc`, range `brain+0x14`); none -> `FUN_0056afd9`: melee monsters
brain mode 0 (a ranged or caster unit: `FUN_0056c592`/mode `0xb`, phase K). So a guard scan only engages enemies **within the unit's attack range**
(adjacent for melee); the long-range noticing is the group pool.

## 8. Hit reaction `FUN_0056e6b8(attacker, victim, 0)` (CONFIRMED)

Called at the end of `take_hit` (`0x517520`, also `0x517a5b`, `0x51881d`, `0x51a4d8`, `0x579e06`) when both creatures have an owner: victim brain
`+0x54 := 1`; `+0x58 := cell word of the attacker` (the revealed cell, §4.2), `+0x5a := 0`; an event record via `FUN_0057977a` / `FUN_0057b210`
(`world+0xbd98`, type 1; log/UI only: no consumer changes AI state, INFERRED); `+0x94 := attacker`, `+0x98 := tick`; and `+0x9c` := the cell **10
cells beyond the victim on the ray attacker -> victim**: `d = victimpos16 - attackerpos16` per axis (`cell*256+sub`), `s = 10.0 / max(|dx|, |dy|)`
(double division by the int; a zero denominator is `inf`/NaN as in x87, ftol -> `0x80000000`), `cell = (victim.cy + trunc(dy*s)) << 8 | (victim.cx + trunc(dx*s))`
(16-bit truncation, no clamp here; the mode-1 order clamps to the map). Mapped to the brief: **a hit unit with no target runs away from its attacker
for 10 ticks after the hit** (§3 branch 4) and a unit whose pursuit failed goes to that cell. The reaction is not gated by HP or damage > 0.

## 9. Fleeing: post step `FUN_00573713` (CONFIRMED, [click-to-move §4.5](click-to-move-research.md))

After the handler, for each member: `HP <= brain+0x44` (wimpy, data.bin p35, halved on difficulty mode 1) and a hostile within 10 cells (`FUN_0056cb0c`)
-> `FUN_0056c9bc`; elif `HP <= brain+0x40` (withdraw, p34) and a hostile within 2 cells -> `FUN_0056ce0f`. Both (units without a spell list): living
hostiles in the list -> `go(m, flee)` where `flee = FUN_00558b92(m, mean position of the hostiles, 3)` (3 cells away along the dominant axis, clamped to
[8, size-9]); none -> guard scan (`FUN_0056ce0f`: also when the list is empty). The hostile list is `FUN_0054ec6a(cell, r)` (objects in the Chebyshev
square of radius `r`) then `FUN_00567a16` (§4.4). **Not** a state: the unit keeps its order and target; the next pass's branch table (§3) overrides
the cell again (`brain+0xa`), so while the HP test holds the unit flees every 16 ticks, then the pool target pulls it back.

## 10. Engine mapping (DECISIONS)

* `engine/sim/ai.py`: `AiGroup` (per `(owner, squad)`), per-unit `AiState` in `World` (`world.ai`, dumped only when the AI is enabled so old goldens and
  hashes hold). `Simulation(ai=True)` adds `ai_system`; it runs at `tick & 15 == 6` **before** the command drain, like the exe's group pass.
* **Commands.** The AI issues `MoveUnits(ai=True)` for `FUN_0056c8af`, `AttackUnit(ai=True)` for the mode-5 attack and `Stop(ai=True)` for the guard
  scan's mode 0 / set-stand. The `ai` flag selects the **brain-level** executor (`orders.apply_ai`): no command group, no cancel of the unit's order, the
  AI group membership is kept - exactly what the exe's direct brain writes do. Plain (player) commands are unchanged. Commands are logged
  `(tick, cmd)` in `Simulation.log`; `replay(..., ai="log")` applies them from the log, `ai="regen"` (default when the sim has the AI) drops logged AI
  commands and regenerates them: both give the same state hash (tested).
* Opt-in: `engine run` enables the AI (`--no-ai` to disable); tests that use monsters as dummies keep the old behaviour by default.
* Optimisation allowed by "1:1, but faster": the sight flood is memoised per pass per (cell, scan, height field) and written with numpy-free integer
  loops; the pool is built from the spatial index (`world.units`) restricted to the group's visible cells, not by scanning all creatures. Results are identical.
* RNG: the only draw is `rand(-1..1)` at the first pass of each group (§3.5), in group creation order.
* Not modelled (INFERRED needed or phase K): hidden units (`0x1000`), the `0x40000` scan-range effect bit, spells, the second list, caster scan,
  special attacks `FUN_0056a981`, structures as targets, group orders other than `0x12`/3.

## 11. Phase K list (ranged and casters)

`FUN_0056bc7b` (caster scan: heal `0x18`, `0x1b`, buffs `0x14/0x15`, attack spells `0xd/0x13/4/8/0xc` with mana gates 5/10/40), `FUN_0056c592`/
`FUN_0056c72b`/`FUN_0056969c` (cast executors), `FUN_0056a981` (special attack rolls), `FUN_0056b059`, `FUN_0056bb0d/53/2e`, the pool's second list
(`server+0xa88`), `FUN_0056eff3` mode 6 for ranged units, `FUN_0057a769` / `FUN_0057a999`, group orders 1, 5, `0x11`, `0x13`, `0xff` (`FUN_00572xxx`).

## 12. VERIFY IN GAME

1. Think rate: a monster standing still reacts within 16 ticks (1-2 s at speed 0-8) of a hero entering its sight; two monsters of one squad react in the **same** tick.
2. Notice distance: stand at 5, 7, 9, 12 cells from a sleeping `Goblin_Pike` (`scan_range` from data.bin) in the open: it should notice at about its `scan_range`
   on flat ground and not through a ridge higher than the observer's cell.
3. Group alert: attack one member of a squad from outside the others' sight: the others get a target after the next pass **only if** the attacker is in
   some member's sight or the hit mark (21 passes) reveals the attacker's cell; the whole squad (not only neighbours) reacts.
4. Pool radius: a hero visible to one member but more than `+0x2d` cells (3-5 beyond the squad's reach, at least 20) from the squad centroid is ignored.
5. Return: lure a monster 20+ cells away and out of sight; it walks back to its own start cell (anchor), not the squad's centroid.
6. Run-away after a hit with no target: hit a monster from out of its sight (bow) and note it runs 10 cells away from the shooter for about 10 ticks.
7. Flee: `Goblin_Pike` at HP <= 10 of 40 with the hero within 10 cells steps away 3 cells every 16 ticks (wimpy); an `Orc_Bow` backs off from anything within 2 cells.
8. Never-hit unit whose target is unreachable (across water) stamps `+0x16` and walks to cell (0, 0)-ish: does it?
9. A melee monster never targets a flyer; a hero on a ridge higher than the monster is noticed later.

## Open questions

* Contents and writers of the second list `server+0xa88` / `0xaa8` (caster and "remembered" units); `FUN_0057977a` consumer of the event record.
* Meaning of the stale stamp `+0x16` when a unit is never hit (`hitcell` = 0) - quirk 3 above.
* Group orders `0x11`, `0x13` handlers (`FUN_00572ec4`, `FUN_0057311c`) and the sacks/pickup order of computer players.

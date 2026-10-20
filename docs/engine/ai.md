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
| idle / guard | member on its anchor `brain+0` in brain mode `0xb`, the idle look-around `FUN_0056e5bc` (§6.1); set by `FUN_0056afd9` |
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
group order 3 instead (`FUN_00562745`, [§14](#14-the-other-group-orders)).

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
    if cell(m) == B.anchor and at_centre(m):  FUN_0056afac(m, 1) = FUN_0056afd9: brain mode 0xb (computer owner), §6.1
    else:                                     go(m, B.anchor)          # return to the post
go(m, c) = FUN_0056c8af: brain mode := 1, brain+0xa := c   (order, group and target untouched)
```

**Brain constructor `FUN_00569003` (CONFIRMED, 0xb8 bytes):** `memset(brain, 0, 0xb8)`, then only `+0x8 = 0`, `+0x9 = 0`, `+0x4c = 0`,
`+0x71 = 1`, `+0x16 = 0xffdc`, and `+0xb4` := a new 0x1c-byte object (`FUN_005420f0(10)`). So `+0x20` (target), `+0x54`, `+0x58`, `+0x5a`,
`+0x94`, `+0x98`, `+0x9c` (hit cell), `+0x9e`, `+0xa0` all start at **0**; only `+0x16` is non-zero (a never-stamped unit has `dB` ~65 500,
never below 10 or 30).

**Writers of `+0x16` (CONFIRMED, whole-exe scan of stores to `[reg+0x16]`): only the ctor and `0x54e2bd`**, the class-0x12 clause of
`FUN_0054d76e` ([simulation §7.4](simulation.md)): static request (`param_6 != 0`) whose destination was not reached, **group order
`0x12` and brain mode 5** (attack approach), and `FUN_00556f56(fallback, dest, size) > FUN_0056ac5b(unit)` -> `+0x16 := [DAT_006044c4]` (block
counter). Nothing in that clause looks at hits. **Writer of `+0x9c`: only `0x56e8b4` in the hit reaction `FUN_0056e6b8` (§8).** Spell casts,
missile launch and `FUN_0056c72b` write neither. Hence **yes: a never-hit unit that attacks an unreachable target (mode 5, e.g. across water)
stamps `+0x16`, and at the next pass (dB < 10, undamaged) branch 1/2 runs `go(m, 0)`: brain mode 1 to cell word 0 = cell (0, 0)**.

What the exe does with cell word 0 (CONFIRMED): `FUN_0056e4ac` -> `FUN_00555411` has no special case for 0; dest (0, 0) is a normal Chebyshev
distance, then `FUN_0054d72d`/`FUN_0054d76e` floods from the unit, (0, 0) stays unlabelled, so the fallback `FUN_005585f4(dest, radius = gap/4 + 4)`
scans rings 1..radius-1 round (0, 0) in 16-bit packed cell arithmetic (negative offsets wrap to the far side of the 256x256 label grid, which is
unlabelled) and takes the labelled cell of the first non-empty ring with the smallest label; the unit **walks to the reachable cell nearest the
map corner it can find**. If no ring cell is labelled the plan is empty (`FUN_005421b0`), the executor sets `mover+0x98 = 1` (failure) and
the unit stays; "No way" (message 0x92) is posted when the end cell is > 1 from (0, 0). No crash, no clamp. The stamp lasts 10 blocks (16 ticks each),
so the walk is re-ordered by each pass in that window, then the unit returns to its post (branch 5). The engine now passes the raw cell (no clamp).

After the handler, the post step `FUN_00573713` runs for every member of every group (§9).

## 4. The pool `FUN_00571c4d` and the sight map (CONFIRMED)

1. Clear the visibility grid (`pf+0x2a008`, 256x256 bytes, `FUN_00553681`).
2. For every member: `FUN_00553329(m, cell word)` = **`FUN_00552c28`**, the sight flood, marks cells (§4.1). If the owner is computer controlled
   (`owner+0x2c != 0`) and `brain+0x58 != 0` (the **attacker's cell** stored by the hit reaction): grid[`brain+0x58`] += 1; `brain+0x5a++`;
   `if brain+0x5a > 20: brain+0x58 := 0`. So a hit reveals the attacker's cell to its group for 21 passes (336 ticks) even outside sight.
3. Every creature of the world (`pf+0xa456c` list; CONFIRMED `0x571c4d`: members come from the group's own list, candidates from this creature list, so structures are never squad members or
   pool candidates; `FUN_0056acc8` has no structure branch either: its `unit+0x14 -> +0x2c` test is the owner's computer flag, choosing the caster check `FUN_0056b059` or the human one
   `FUN_0057a769`; the engine's "structures as targets" gap is therefore not an exe feature) whose **cell word** has a non-zero grid byte is added to the pool.
4. `FUN_00567a16(first member, pool, 0)`: delete units the owner is **not at war with** (`relations[owner][other] & 1 == 0`, matrix
   `server+0xa8bc`, `[a*0x46 + 8 + b]`); and delete a unit with flag `+0x144 & 0x1000` (hidden) unless some member detects it
   (`reach_gap(hidden, member) <= member.brain+0x71`, `see_invisible`, data.bin p36). The list walked for "some member" is `*(first member + 0x70)`, the owner's group object.
   **Hidden flag CONFIRMED**: `+0x144 & 0x1000` is bit `1 << 12` of the effect-kind mask: the generic effect application `FUN_0051ce12` ORs `1 << kind` into `+0x144`
   (`0x51d10a`; no caller found, reached through the effect vtable), expiry `FUN_0051cc9f` (`0x51cdd5`) and replacement clear it (`0x51cf13`); kind 12 is **Invisibility**
   ([spells](../data/spells.md), `0x51b927`; it ends on the owner's attack, `FUN_00516b2f`). Other `+0x144` writers are the init to 0 (`0x50e201`), the copy (`0x50ea66`) and bits `0x100000` / `0x10000000`
   (`0x517041`, `0x5170a0`). The same flag is read by the caster selectors (`FUN_0056bc7b` `0x56c47a`, `0x56c54f`; `FUN_00567c56` `0x567cd3`) and the UI target pick (`FUN_0057a307` `0x57a3bb`).
   **Level**: `FUN_00556dcd` = `(max over x, y of max(0, |centre distance| - (size_a + size_b) * 128) >> 8) + 1` (centre of a size-n footprint = `pos + (n-1)*128`, 1/256 cells): 1 touching,
   2 one free cell between. With the default `see_invisible` 1 (data.bin p36; -1 or humans keep 1; monsters have 0..10, mostly 3) a hidden hero is invisible to the pool unless a squad member touches it
   (p36 = 3 sees it two free cells away). A hidden unit that is not at war is dropped anyway (the relation test comes first). Engine: `Unit.hidden` (the setter, the Invisibility effect, does not exist yet),
   `ai.reach_gap`, `ai.see_invisible`, the clause in `_hostiles_on` and `_enemies`.
5. `FUN_00567ddf`: delete pool units with HP < 1.
5b. `FUN_00567ddf` does not only delete: it **moves** every pool unit with HP < 1 (`creature+0x94` word) from the pool list (`server+0xa68`) into the **dead list `server+0xa88`**
   (list object `+0xa84`; cleared first). CONFIRMED `0x567ddf`.
6. When the pool is empty and the dead list is non-empty (`FUN_0044fc20`), the dead list is **put back into the pool** and cleared (`0x571e27`-`0x571e90`, same code
   in `FUN_00569fd4` `0x56a165`, `FUN_00571e9b`, `FUN_0056ed4e`, `FUN_00571c4d`, `FUN_0057184f`, `FUN_0057224e`). So `+0xa88` = "at-war units in sight that are dying/dead but
   still in the creature list"; a **melee monster with only dying enemies in sight keeps a (dying) target** (it finishes the body, which `death.py` keeps until HP < -9) instead of
   losing it. The list is empty otherwise, not "caster code" (the earlier reading was wrong). Engine: `ai._hostiles_on` returns the living, else the dying ones.

**Caster lists `server+0xaa8` / `0xac8`** (CONFIRMED `0x567c56`, callers `FUN_0056b059`, `FUN_0056bc7b`): the caster first builds the unfiltered pool with `FUN_00571e9b`
(sight flood as §4, no `FUN_00567a16` relation filter, still `FUN_00567ddf`), then `FUN_00567c56(caster, &server+0xa64)` clears both lists and sorts each pool unit (skipping brain state `0x10`
and undetected hidden units) by `FUN_0057994d(caster, unit)`: at war -> `+0xac8` (targets of attack spells), else -> `+0xaa8` (**allies / neutrals / itself: heal `0x18` and buff
targets**, picked by lowest `hp/hp_max`). Only the human-owner mage code (`FUN_0056b059`, `FUN_0056bc7b`, §12.6) reads them; melee monsters and the computer branch never do.
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

`FUN_0056acc8(m, t)` (the member has a target): if the target's `+0x4c & 8` is set -> guard scan `FUN_0056afac(m, 0)`. **Bit 8 = the unit is off the map** (CONFIRMED: set only by `FUN_005102a3` = remove from the grid `FUN_00553891` + `|= 8` + two `FUN_005053a8` view calls; cleared by `FUN_00510318` / `FUN_005103ae` = put back on the map, which log "Unit can't enter / return to map"; callers in the scenario/group code `0x521099`, `0x52f813` (`FUN_0052f8e2`), `0x57821e`, `0x57824e`, `0x5787f2`; any creature class, not a hero flag, not an immunity); the engine has no off-map units, so the test never fires (nothing to model); special
attacks (spell slots `brain+0x7c+4i`, probability `rand15 < brain+0x88+4i`, last slot that passes; `FUN_0056a981`) -> §12.2-12.3; if no spell:
`m == t` -> no target; target 0 -> `FUN_00567988` (nearest enemies list) -> guard scan; a **mage** (`FUN_0053a5a0` = `return +0x4c & 4`, CONFIRMED; see below) first tries the cast path (human owner,
`owner+0x2c == 0`: `FUN_0056b059`; computer owner: `FUN_0057a769`; §12.4, §12.6); otherwise (every melee unit): `brain mode := 5`, `brain+0xc := t`, `brain+0x14 := FUN_0056ac5b(m)`
(range); a human-owned **mage** with range byte `< 2` calls `FUN_0056bc7b` (caster scan, §12.6). Mode 5 is the I1 melee driver
(`attack_mode`, [combat §2.3](combat.md)); the follow planner stamps `brain+0x16` when the target is out of reach (§3). Order, anchor and group of
the unit are unchanged (an AI attack is **not** order 3).

**`+0x4c` creature flags (CONFIRMED)**: bit 2 = has a spell list (monster: template `spell_1` (p48) `> 0`, `0x511c0a`; human: spellbook built, `0x51203b`); bit 4 = **mage** (monster: template `known_spells` (p56) neither 0 nor -1, written `|= 6` at `0x511dd6`; human: `maxMana +0x9c != 0`, `0x514907` / `0x512050`); bit 8 = off the map (above); bit 0x10 = sure hit (monster damage kind 3). Bit 1 is set by no creature writer. `FUN_0053a5a0` is therefore *not* "has a spell list": the 38 `.4` / `.5` template variants with `spell_1 > 0` (`Goblin_Pike.4`, `Ogre.5`, ...) have bit 2 only and use `FUN_0056a981` (special attacks), not the mage path. **Goblin_Pike (`spell_1` -1, `known_spells` 0) and every other melee monster: always 0.** Mage templates (64 of 241 monster records: Dragon, Orc_Shaman, `M_Skeleton.3-5`, Necromancer, Druid*, Necro*, Succubus*, MercenaryDruid*) and every human with mana are the units that reach `FUN_0057a769` / `FUN_0056c592` (computer owners) or `FUN_0056b059` / `FUN_0056bc7b` / `FUN_0056b025` (human owners), §12. The map unit `behaviour` bits (`+0x194/+0x19c/+0x198/+0x1a0`) are unrelated to `+0x4c`.

Returning: `go(m, anchor)` every pass until `cell == anchor` at a centre; then `FUN_0056afd9` (§6.1).

### 6.1 Idle look-around, brain mode `0xb` (`FUN_0056e5bc`, CONFIRMED)

`FUN_0056afd9` (`owner+0x2c != 0` = computer controlled) sets brain mode `0xb`; the mode body runs **every tick**. With `cur = mover+0` (facing) and `tgt =
mover+1` (target facing): if `cur == tgt`: when `brain+0x54 == 0` and `rand15() > 0xcc` (99.4 % of the ticks) the state is 0 and nothing else happens;
otherwise `tgt := cur + 0x21 + rand15 * 0xbe / 0x8000` (byte), `brain+0x54 := 0`, start the turn (`FUN_00556454`), state 1. If `cur != tgt` the turn continues,
state 1. So an idle monster turns on the spot about every 165 ticks by 33..222 units of 256, and **at once** after a hit (`brain+0x54 := 1`, §8). This is
the only per-tick RNG use of the AI: one `rand15` per settled idle monster per tick, in creature order (the divisor `0x8000` is CONFIRMED: the order manager's embedded RNG helper is constructed by `0x57af80` (called from the manager ctor at `0x568143`), which stores `0x8000` at offset 0 and seeds `srand(time)`; `FUN_0057afd0(n) = rand15 * n / [this]`, `rand15` = MSVC LCG `0x343fd`/`0x269ec3`, `>> 16 & 0x7fff`; nothing else writes it; `engine/sim/ai.py` already uses `rand15 * 0xbe >> 15`).

### 6.2 Mover event and auto scan (`0x56e1b0`, `FUN_0056ed4e`, CONFIRMED)

When the mover raises its event flag (`mover+0x98`: the planner failed or the path is exhausted) a unit under order `0xb` gets mode 0 and the auto scan: among
the creatures within `FUN_0056ac5b` cells (a candidate is listed only if its distance is `<=` the nearest listed so far, the quirk of `0x56ed4e`), the hostile
living one with the smallest facing change (`<=`, the last of equals wins; start 300) becomes `brain+0xc` in mode 6 (the same driver as 5); none: mode `0xb`.

## 7. Guard scan `FUN_0056a1fb` (CONFIRMED)

Not run by the handler itself: it is the scan of `FUN_0056afac(u, 0)`, used by the retreat step (§9), by `FUN_0056acc8` and by the group pass of the human's stopped units (group order 4, [§14](#14-the-other-group-orders)) and of empty-order groups (`0xff`); the stand-ground pass (order 3) does **not** use it. Candidates
are the single-unit pool built by `FUN_00569fd4` (same steps as §4 with only this unit's sight flood, then `FUN_00567a16`, `FUN_00567ddf`).
`best` starts empty with `bestgap = range + 1` (`range = FUN_0056ac5b`, byte arithmetic); for each candidate `c` with `FUN_005711ea(u, c) !=
0xffffff`: `g = reach_gap(u, c)` (`FUN_00556dcd`), `+1` if `class(c) == 3 and class(u) != 3`, `a = FUN_0055aa21(facing octant(u,c), u.facing)`;
`g < bestgap` -> take; `g == bestgap and g <= range and a <= besta` -> take. After the loop `range < bestgap -> none`. A hit -> `FUN_0056c840`
(brain mode 6 / spell `FUN_0056b059`; melee: mode 6 = `FUN_0056eff3`, target `brain+0xc`, range `brain+0x14`); none -> `FUN_0056afd9`: melee monsters
brain mode 0 (a ranged or caster unit: `FUN_0056c592`/mode `0xb`, phase K). So a guard scan only engages enemies **within the unit's attack range**
(adjacent for melee); the long-range noticing is the group pool.

## 8. Hit reaction `FUN_0056e6b8(attacker, victim, 0)` (CONFIRMED)

Called at the end of `take_hit` (`0x517520`, also `0x517a5b`, `0x51881d`, `0x51a4d8`, `0x579e06`) when both creatures have an owner: victim brain
`+0x54 := 1`; `+0x58 := cell word of the attacker` (the revealed cell, §4.2), `+0x5a := 0`; `FUN_0057977a(relations, attacker, victim, 0)` first: **a hit between neutral owners (`rel & 3 == 0`) sets the war bit attacker->victim, and victim->attacker likewise** (CONFIRMED; `declare_war` in the engine; a human attacker also posts a notice via `FUN_00504e87`, not modelled); then an event record via `FUN_0057b210`
(`world+0xbd98`, type 1, appended to the list `server+0xbbec`; write-only, it changes no AI state, see the event records paragraph below); `+0x94 := attacker`, `+0x98 := tick`; and `+0x9c` := the cell **10
cells beyond the victim on the ray attacker -> victim**: `d = victimpos16 - attackerpos16` per axis (`cell*256+sub`), `s = 10.0 / max(|dx|, |dy|)`
(double division by the int; a zero denominator is `inf`/NaN as in x87, ftol -> `0x80000000`), `cell = (victim.cy + trunc(dy*s)) << 8 | (victim.cx + trunc(dx*s))`
(16-bit truncation, no clamp here; the mode-1 order clamps to the map). Mapped to the brief: **a hit unit with no target runs away from its attacker
for 10 ticks after the hit** (§3 branch 4) and a unit whose pursuit failed goes to that cell. The reaction is not gated by HP or damage > 0.

**Event records (CONFIRMED by an asm scan of the whole exe for `0xbbec`/`0xbbf0`/`0xbbf4`/`0xbbf8`/`0xbbfc`).** The list is a member of the server (order manager `0x66832c`) at `+0xbbec` (class vtable `0x5d1ba0`: head `+4`, tail `+8`, count `+0xc`; records are `0x54` bytes copied from the staging block `world+0xbd98`: type `+0`, `+0x2c` first unit/creature, `+0x30` second operand). The only references to `+0xbbec` are: constructor `0x5681ef` (`0x57b1b0`), destructor `0x56843c` (`0x57b330`, plus the unwind funclets `0x5c8266`/`0x5c8305`), the clear `0x57488a` (`FUN_0057485b`, after `FUN_00574ba1`, every tick) and four appends through `FUN_0057b210`: type 2 and type 3 in the cast-request function (`0x56dee4`, `0x56df53`, inside `FUN_0056dca2`: type 2 when the caster's `+0x1c4` brain count byte `+0x15` reaches 3 and `+0x5c` is set, operand = `+0x64`; type 3 otherwise, with two more operands `+0xbd9c`/`+0xbda0`), type 1 in `FUN_0056e6b8` (`0x56e755`: `+0xbdc4` = attacker, `+0xbdc8` = victim) and type 4 in `FUN_0057240b` (`0x5724d6`, one operand `+0xbdc4`, gated by a flag byte). The fifth caller of `0x57b210` is the list's own copy method `0x57b390` (vtable slot 2: a stream serialiser/copier of the list) which nothing in the exe calls for this list. Nothing iterates the list: `FUN_00574ba1` (trigger evaluation), `FUN_00574f3f` and the Scenario code never touch `+0xbbec..+0xbbfc`, no AI routine reads it. So: a per-tick event queue that is filled and flushed with no consumer in this exe build (a debug/log or unfinished hook); the Scenario "unit attacked/killed" style conditions are NOT fed by it, they must read creature state instead (`+0x94` last attacker / `+0x98` tick of the victim brain and the death paths are the candidates, INFERRED, for the future trigger phase). No squad alert or target change depends on the records. The engine need not model them.

## 9. Fleeing: post step `FUN_00573713` (CONFIRMED, [click-to-move §4.5](click-to-move-research.md))

After the handler, for each member: `HP <= brain+0x44` (wimpy, data.bin p35, halved on difficulty mode 1) and a hostile within 10 cells (`FUN_0056cb0c`)
-> `FUN_0056c9bc`; elif `HP <= brain+0x40` (withdraw, p34) and a hostile within 2 cells -> `FUN_0056ce0f`. Both (units without a spell list): living
hostiles in the list -> `go(m, flee)` where `flee = FUN_00558b92(m, mean position of the hostiles, 3)` (3 cells away along the dominant axis, clamped to
[8, size-9]); none -> guard scan (`FUN_0056ce0f`: also when the list is empty). The hostile list is `FUN_0054ec6a(cell, r)` (the **occupants** of the Chebyshev
square of radius `r`, scan order: centre, then each ring) then `FUN_00567a16` (§4, step 4).
**Creatures only (CONFIRMED `0x54ec6a`, `0x551edb`, `0x5503af`)**: a cell counts when bit `0x20` of `pf+0x10000` is set ("has a cell record"), and the entry is the record's occupant slot
rec`+4` (`FUN_00551edb`), written only by `FUN_005503af` for ground movement classes 1, 2 (class 3 flyers go to rec`+8`, never listed) from `FUN_0055020a`, whose callers all pass a creature
(`0x510089` placement, `0x54eee7` teleport, `0x554bf8`/`0x554fd2` movement, `0x55a96c`). Structures live in rec`+0xc`, piles in another slot, carriers/sacks are piles: none is listed, so **a hostile
structure never makes a monster flee**. The list is **not de-duplicated** (`FUN_0053c5c0` appends): a unit of footprint `n x n` is listed once per footprint cell (anchored at its own cell,
`FUN_0055020a`) inside the square and the first unit to enter a shared cell holds the slot; the flee point (the mean position) is weighted accordingly. Dead bodies are occupants too. The owner test
(`FUN_0057994d`, `obj+0x14 -> +4`) is only ever applied to creatures there. **Not** a state: the unit keeps its order and target; the next pass's branch table (§3) overrides
the cell again (`brain+0xa`), so while the HP test holds the unit flees every 16 ticks, then the pool target pulls it back.

## 10. Engine mapping (DECISIONS)

* `engine/sim/ai.py`: `AiGroup` (per `(owner, squad)`, `World.ai_groups`), per-unit `AiState` (`Unit.ai`, `Unit.mode_look`), dumped only when the AI is
  enabled so old goldens and hashes hold. `Simulation(ai=True)` adds `ai_system`; it runs at `tick & 15 == 6` **before** the command drain, like the exe's group pass.
* **Commands.** The AI issues `MoveUnits(ai=True)` for `FUN_0056c8af`, `AttackUnit(ai=True)` for the mode-5 attack and `Stop(ai=True)` for `FUN_0056afd9` (mode `0xb`). The `ai` flag selects the **brain-level** executor (`orders.apply_ai`): no command group, no cancel of the unit's order, the
  AI group membership is kept - exactly what the exe's direct brain writes do. Plain (player) commands are unchanged. Every AI command goes through
  `ai.emit` (apply at once + `World.ai_emitted`), `Simulation.step` appends them to `Simulation.log` as `(tick, cmd)`. `replay()` of a sim that has the AI drops
  the logged AI commands and regenerates them (same hash, tested); a sim without the AI applies them from the log in the drain (approximate: the
  events of §6.2 happen inside the movement tick, the drain is before it).
* Opt-in: `Simulation(world, ai=True)`; `engine run` enables it (`--no-ai` disables, Shift+F5 / `--debug ai` draws the overlay: sight = the aggro area, the ring at
  the pool radius, the post, the target, a label with mode / order / target uid / radius / stamp). Tests that use monsters as dummies keep the old behaviour.
* Deviations (all invisible in the 46 maps' normal play, none changes the rules above): an event-raised mode (§6.2) runs its body one tick later than the
  exe's direct call; (a go cell is passed raw, as the exe does: cell (0, 0) for a never-hit unit, §3); a target that
  disappears ends mode 5 (and an AI's mode 8) without stopping the unit (INFERRED, the exe's pointer); casters: §12.7 (the human-owner scan
  `FUN_0056bc7b` and the Teleport flee are not built); the effect bit `0x40000` is not modelled (`0x1000` hidden: the clause is, `Unit.hidden` has no setter yet); the difficulty tweak is implemented behind `World.from_map(difficulty=...)` (default 2 = off, section 10.1); the target flag `+0x4c & 8` test of `FUN_0056acc8` is not modelled (off-map units do not exist in the engine).
### 10.1 Difficulty tweak (`FUN_00561bf9` `0x561e20`-`0x561f0b`, CONFIRMED)

`[0x6044c4+0xd8]` is the game option "difficulty": the server ctor `0x4e97bf` stores **2**; the only setter is `0x493d80`, called from `FUN_004891d8` (`0x48972f`) with `selector + 1`. **Who reaches it in single player (CONFIRMED, REA)**: `FUN_004891d8` is not a lobby window but the main shell window's handler of message `0x44c` ("a child panel closed", dispatch `FUN_004852d8`, class vtable `0x5ce0d8`, ctor `0x481efc`; `this+0x5d8` = game kind: 2 = single player, 1 / 3 / 0 = network client / host / join). The server object (and so the option) is created only by `FUN_0048ab76` (ctor `0x4e957b` -> `0x4e97bf`, then `0x4eb356`), whose five callers are the game-kind starters: kind 2 by screen state `0x425` (`0x48c0e2`) and state `0x419` (`0x48db37`); kind 3 / 1 / 0 by `0x48f156` / `0x48f1e2` / `0x48ef1f` (network). **New game = state `0x425`** (loads `main\text\town.txt`, kind 2, selector `this+0x598 := 1`), then `FUN_0048f4e2` shows the setup panel `this+0x374` (resource `0x466`, class ctor `0x43270d`): name, option index `+0x208`, and **three radio buttons Easy / Medium / Hard** (`0x434fa1/0x434fdb/0x435014` write `+0x20c := 0/1/2`; their tooltips `0x437533` use main.txt lines 247..249 only when kind == 2; town.txt tip 9 says "select the easy level if you play for the first time"). OK on that panel copies the values (`0x4891d8` `this+0x374` branch: selector `FUN_00493ce0` -> `this+0x598`) and shows the confirm panel `this+0x36c` (`FUN_0048f3f0`); OK on `this+0x36c` with kind 2 runs `0x40d480`, `0x49183e`, the two option flags, **`if ([0x6044c4]) setter(this+0x598 + 1)`** and enters state `0x42e` (the game). So **the player chooses Easy (1) / Medium (2, preselected) / Hard (3) once, at the start of a new single-player game; every map of the campaign then uses it** (nothing re-creates the server between missions; the value is read per unit by `FUN_00561bf9`). **Load game = state `0x419`** (list dialog `this+0x13c`, OK `0x445`): `FUN_0048db37` makes a kind-2 server (default 2), then `FUN_004e9b95` reads the saved server state through `FUN_004ec732`, which restores `+0xd8` **only if the saved value is 1..3** (`0x4ecad4`-`0x4ecae9`), so the difficulty lives in the save file (written by `0x4ec8a1`) and is not asked again. Other paths (`0x444bcc`, class `0x44498d` with vtable `0x5cc438`) are dead code (no constructor call). Network host / join / lobby (kinds 0, 1, 3) reach the same panels but are out of scope. Mapping to the engine: `engine run MAP --difficulty 1|2|3` = Easy / Medium (default, no tweak) / Hard; there is no per-map difficulty and the map header does not carry one. It is not the map header: `field_88` is only the multiplayer advert level ([map.md](../formats/map.md)). The tweak runs only for units whose map flag `0x10` is clear (monsters; heroes take the other branch), when the mode is not 2 and settings `+0x74 == 0` (single-player map, `field_84 == 1`). Mode 1 (easy): max HP = trunc(template HP x 0.5 `0x5d1b00`), HP = max HP, brain `+0x44` (wimpy) `>>= 1`. Mode 3 (hard; the code branch is "else", so 0 would act the same, never stored): to-hit `+0xa6` and defence `+0xbe` += `0x32`, max HP = trunc(x 1.5 `0x5d1b08`). It scales the template value; a map HP override replaces it afterwards, and the monster recompute is additive so the +50 survives. Engine: `World.from_map(m, assets, difficulty=2)` (`DEFAULT_DIFFICULTY`), `Unit.tweak` (0 / 1 / 3), `combatstats.monster_stats(hard=)`, `ai.post_step` (wimpy). Default 2 changes nothing: no golden or hash moves. Not modelled: the client-side damage scaling (x0.5 easy / x1.5 hard, `FUN_00502019`) and the `[0x6044c4+0x174]` multiplayer filter.

* Optimisation allowed by "1:1, but faster": the sight flood is memoised per pass per (cell, scan, height field) and written with numpy-free integer
  loops; the pool is built from the spatial index (`world.units`) restricted to the group's visible cells, not by scanning all creatures. Results are identical.
* RNG: the group pass draws `rand(-1..1)` at the first pass of each group (§3.5), in group creation order, and the caster draws of §12 (slot rolls,
  the mage's `rand(100)` and pick, the idle friend / spell picks) in member order inside the handlers; the look-around (§6.1) draws per tick.
* Not modelled: the Invisibility effect that sets `Unit.hidden`, the `0x40000` scan-range effect bit, the human-owner caster code (`FUN_0056b059` with a selected
  spell, `FUN_0056bc7b`) and the Teleport flee (§12.6), the effects of the non-damage spells (§12.7: counted in `World.unbuilt_casts`). The other group orders are built ([§14.1](#141-implementation-and-the-asm-details-it-rests-on-confirmed-unless-marked)).

## 11. Tests and code

`engine/sim/ai.py` (+ hooks: `orders.orders_system`, `movement._tick_inner/_tick_unit/follow_drive`, `combat.resolve_attack/attack_mode`, `Simulation`),
`tests/test_engine_ai.py` (sight, score, notice / ignore, chase and return, squad alert, pool radius, 16-tick rate, hit reaction, hit-mark reveal, flee, look-around, 10-monster replay hash, log, overlay).
Casting (§12): `tests/test_engine_ai_casting.py` (slot rolls and their draws, Teleport distance, target kinds, mage pick / mana / defensive filter / the
30 % rethink, idle heal / Shield / friend buff and the Curse quirk, mode 8 repeat, mode 9 and command `0x1f`, Heal, revive, Drain Life, stubs,
determinism) and `tests/test_engine_ai_casting_maps.py` (map 73, needs the install).

## 12. Casters and special attacks (CONFIRMED unless marked; engine: §12.7)

`B` = brain (`u+0x1c4`). "Wrapper of n" = `FUN_0051c391(n)` on the unit's spellbook `u+0x140` (0 when unknown; record `+8` number, `+9` range, `+0xa`
defensive, `+0xc` mana cost, [spells §3](../data/spells.md)). "Cast at a unit" = `B+0x60 := 1` then **`FUN_0056c72b(u, t, w)`**: `t == 0` -> the nearest enemy
(`FUN_00567988`) or friend (`FUN_005679cf`, `w+0xa != 0`) of the square of radius `mover+8` (5) round `u`, none -> guard scan; else **Brain mode 8**, `B+0x28 := t`,
`B+0x30 := w`, the target's `B+0xa4 := spell number`, `B+0xa8 := tick` (the "recently enchanted" stamp read by `FUN_0056bc7b`), `B+0x14 :=` wrapper range. "Cast at a
cell" = `B+0x60 := 1` then **`FUN_0056969c(u, cell, w)`**: Brain mode 9, `B+0x3c := cell`, `B+0x30 := w`, `B+0x14 :=` wrapper range. Neither touches the order
(`+0x50`, so an AI caster keeps order `0xb`), the group or `B+0x0c`.

### 12.1 Creature set-up (`FUN_005114f3`, monsters; `0x511586`-`0x511f44`)

* `+0x9c` max mana := data.bin `manaMax`, **`+0x9a` mana := `+0x9c`** (`0x5115a5`), `+0xa0 := +0x9a`. Mind `+0x88` = template `mind`.
* `p48 > 0` (`spell_1`): `+0x4c |= 2`, a spellbook `+0x140` is created. For i = 0..2: `s = p(48+2i)`, `q = p(49+2i)`; if `s > 0`: wrapper `FUN_0051906d(s)` added to the
  book (`FUN_0051c29e`), **`B+0x7c+4i := s`, `B+0x88+4i := q * 0x147`** (`0x511d36`, `0x511d4f`); unused slots stay 0 (brain memset).
* Skills `+0xa8+2k` (k = 1..5) := `p54` (`spell_power`) for every monster (`0x511d64`-`0x511d94`).
* `p56` (`known_spells`) neither 0 nor -1: `+0x4c |= 6` (**mage**), a **new** spellbook replaces `+0x140` with the wrapper of every bit n = 1..29, and the skills
  `+0xaa..+0xb2` := `p57..p61` (raw words, -1 kept) (`0x511dd6`-`0x511f44`). No template has both a slot and a mask.
* `B+0x78` (the default spell, read by `FUN_0056ac5b` and `FUN_0056b059`) is written only for heroes (creation `0x4f30f5`, record load `0x4ead58`, the client's
  spell-select command `0x4f69c5`/`0x4f69e3`): **0 for every map unit**, so their `FUN_0056ac5b` range is the attack range `u+0x12c`.

So the install has two kinds of spell users (§6): **special-attack monsters** (bit 2 only: `.4` / `.5` variants, slots with probabilities 1..20, mana 0, the slot
spells in the book, level `p54 - 30 + mind`) and **mages** (bits 2 + 4: Dragon, Orc_Shaman, `M_Skeleton.3-5`, Necro*, Druid*, Succubus*, MercenaryDruid*, and every human
with mana; level `skill[sphere] - 30 + mind`). A mage pays mana at the cast start ([spells 9c.2](../data/spells.md)), a special attack is free.

### 12.2 `FUN_0056acc8(u, t)` with spells (the attack decision of every group handler, §6)

```
if t.flags(+0x4c) & 8:  guard scan; return                      # off the map (not modelled, §10)
pick = 0
for i in 0, 1, 2:                                               # one rand15 per USED slot, in slot order
    if B.slot[i] != 0 and rand15() < B.prob[i]:  pick = B.slot[i]     # FUN_0057afc0 = rand(); the LAST passing slot wins
if pick:
    if pick != 23 or Chebyshev(cell t, cell u) > 2:  FUN_0056a981(u, t, pick); return      # 12.3
    # Teleport with the target within 2 cells: fall through
if u == t: t = 0
if t == 0: t = first of FUN_00567988(u, cell u) (radius mover+8 = 5); none -> guard scan; return
if owner(u)+0x2c == 0:                                           # human owner
    if mage(u) and FUN_0056b059(u, t): return                    # 12.6
    B.mode = 5; B+0xc = t; B+0x14 = FUN_0056ac5b(u)
    if mage(u) and B+0x14 < 2: FUN_0056bc7b(u)                   # 12.6
else:                                                            # computer owner: monsters and computer-owned humans
    if mage(u) and FUN_0057a769(u, t): return                    # 12.4
    B.mode = 5; B+0xc = t; B+0x14 = FUN_0056ac5b(u)
```

The probability is `p * 0x147` against `rand15` (0..0x7fff): `p = 10` passes 3270 of 32768 (9.98 %), `p = 1` 0.998 %. `FUN_0056ac5b(u)` = the wrapper range of
`B+0x78` when that spell is in the book and `mana >= cost`, else `u+0x12c` (monsters: always `u+0x12c`, 12.1). `mage(u)` = `FUN_0053a5a0` = `+0x4c & 4`.

### 12.3 Special attack `FUN_0056a981(u, t, n)`

`w` = wrapper of n; **`w == 0` -> return** (nothing, `B+0x60` untouched, and `FUN_0056acc8` has already returned: the unit keeps its previous mode this pass). Else by n
(jump table `0x56abe7`), then **`B+0x60 := 1`** for every n:

| n | Target | Call |
|---|---|---|
| 1 5 10 11 16 18 26 28 29 | the enemy | `FUN_0056c72b(u, t, w)` |
| 2 3 6 7 14 15 17 | the enemy's cell (`t+0x10` cell word) | `FUN_0056969c(u, cell t, w)` |
| 4 8 12 13 19 20 21 24 25 27 | itself | `FUN_0056c72b(u, u, w)` |
| 9 | the cell next to `u` towards `t`: `o = FUN_005568e4(u, t) >> 5`, `(x u + dx[o], y u + dy[o])` (byte arithmetic, tables `pf+0x58e88/0x58e90`) | `FUN_0056969c` |
| 23 | (`Chebyshev > 2` again) the first cell of the 3 x 3 square round `t`, rows `y-1..y+1` outer, columns `x-1..x+1` inner (packed `cell t - 0x101 + row*0x100 + col`), where `FUN_0055cd50(u, cell)` holds (every footprint cell of `u` clear of the live layer `pf+0x20000` under the mover mask `mover+5`); none (or the packed word 0) -> nothing | `FUN_0056969c` |
| 22, others | nothing | - |

No mana test (a special-attack monster has no mana mage bit: the cast is free) and no range test (the Brain mode approaches to the wrapper range).

### 12.4 Computer-owned mage engaging: `FUN_0057a769(u, t)`

```
if mind(u+0x88) < 60 or (r = rand(100)) > 29:                   # rand(n) = FUN_0057afd0(n) = rand15 * n / 0x8000; drawn only when mind >= 60
    L = [wrapper n for n in 1..28 if known and w.cost <= mana and w.defensive(+0xa) == 0]     # spell 29 (Slow) is never picked here
    k = rand(len(L))                                             # drawn even when L is empty (rand15 * 0)
    if L empty: return 0                                         # -> mode 5 (melee / shooting)
    cast at a unit (u, t, L[k]); return 1
else:                                                            # mind >= 60 and r <= 29 (30 %)
    FUN_0056acc8(u, t); return 0                                 # recursion: the whole decision again (new slot and r draws) ...
```

... and since it returns 0 the **outer** `FUN_0056acc8` then sets mode 5: a clever mage (mind >= 60) melees / shoots in 30 % of the passes, after the inner call
spent its draws and wrote its cast fields (the outer mode-5 write wins). There is no range, line-of-sight or target-kind test: a cell spell (Fire Ball, Poison Cloud,
Blizzard, ...) is cast **at the unit** (state `0xd`, `FUN_00519d7f` -> `FUN_00519db8(u, t, 0, 0)`).

### 12.5 Computer-owned mage idle: `FUN_0056afd9` -> `FUN_0056c592(u)`

`FUN_0056afd9` (computer owner) sets mode `0xb` and, for a mage, calls `FUN_0056c592`:

```
if book(u+0x140) == 0 or mana <= 10: return
h = wrapper 24 (Heal); if h == 0: return
if hp != hp_max: cast at a unit (u, u, h); return
S = occupants of the square of radius h.range round u (FUN_0054ec6a: centre, then per ring k the cells (x+i, y+k), (x+i, y-k) for i = -k..k and,
    for |i| != k, (x+k, y+i), (x-k, y+i); ground occupant slot only, dying bodies included)
S -= units whose owner u's owner is not allied with (relation bit 2; a player's word for itself is 0x12) and undetected hidden ones (FUN_00567b2d)
best = the first unit of S with the smallest (int)(hp / hp_max)        # C integer division (idiv): 0 for every wounded or dying unit, 1 at full HP
if best < 1.0: cast at a unit (u, best, h)
else: FUN_0057a999(u, S)
```

`FUN_0057a999(u, S)` (here always with `hp == hp_max`): `w = wrapper 27` (Shield); if `w != 0` and the effect bit `1 << 27` of `u+0x144` is clear -> cast at a unit
(u, u, w). Otherwise `k = rand(|S|)` (always drawn), `f` = the k-th unit of S (none when S is empty); `f == 0` or `f`'s owner object differs from u's -> 0. If `f`
is wounded and `u` knows Heal -> heal `f` (unreachable after `FUN_0056c592`). Else, only when `mana == max mana`: `L = [wrapper n, n = 1..28, known, cost <= mana,
defensive, n not 24 / 27]`, `k = rand(|L|)` (always drawn); **when L is empty the wrapper variable still holds the loop's last lookup, the wrapper of 28 (Curse) or 0**
(quirk: a mage that knows Curse and no other defensive spell curses its friend); that wrapper, unless 0 or already active on `f` (`f+0x144 & 1 << n`), is cast at `f`.

### 12.6 Human-owned mages (the player's units) and the flee step

* `FUN_0056b059(u, t)`: returns 0 unless `B+0x78` (the hero's selected spell, 12.1) is set and castable (`FUN_0056bb0d(n)` = the wrapper when `cost <= mana`);
  then by that spell: 1 5 10 11 16 26 -> cast at `t`; 2 (radius 1, round the cell ahead of each unit that is between cells) and 3 6 7 (radius 2) -> per at-war unit of
  the caster list `server+0xac8` count the occupants of the square round it (at war +1; others -1, the caster itself -100) and cast at `t` when the best count is > 0;
  18 / 28 -> cast at `t` when `t` lacks the effect bit, else when some at-war unit of the list lacks it (quirk: still at `t`); 24 -> the friend (`FUN_0056bb53`) with the
  smallest `(int)(hp / hp_max)` is healed when `< 1`, else mode 0 and 1 is returned; 25 -> at itself (without `B+0x60`); 27 -> Shield at itself unless active; 22 and
  the rest -> 0.
* `FUN_0056bc7b(u)` (human mage in mode 5 with range < 2, and the human idle `FUN_0056b025`; "castable n" = `FUN_0056bb0d` = known and `cost <= mana`; "in range" =
  `FUN_0056bc2e` = Chebyshev cells `<=` wrapper range; "friend" = `FUN_0056bb53`: not at war and not allied with owner flag 4, allied with flag 2, the same owner with
  flag 1, or itself; "fresh" = target `B+0xa4 != 20 || |B+0xa8 - tick| > 20` (it compares with 20 = Bless for every spell)). The flag byte is the owner's party-AI
  byte (player `+0x34` record `+0x20`, starts `0xff` in `FUN_005691c7`, replaced by a client command, `0x4f6945`, operand `+0xe`; the client side is not traced).
  Order: mana < 5 or flag 8 clear -> mode 0. `hp < max` and castable 24 -> heal itself. Shield bit (`+0x144 & 1 << 27`) clear and castable 27 -> Shield itself.
  Caster lists (§4); castable 24 and a list count > 1 -> the friend in range with the smallest `(int)(hp / hp_max)`, healed when `< 1`. Flag 0x10 clear or mana < 10
  -> mode 0. Per friend of `server+0xaa8`: Bless 20 (`FUN_00542c90` and not effect 20, fresh, in range), then Haste 21 (not effect 21, fresh, in range). Flag 0x20 clear or
  mana < 40 -> mode 0. Per friend: 13, 19, 4, 8 (the protections, not already active, in range, fresh), 12 Invisibility (not hidden, not itself, relation `& 3 != 0`,
  fresh). Then Invisibility on itself if castable and not hidden, else mode 0. Every cast is "cast at a unit".
* Flee (`FUN_00573713`, §9) for a unit **with a spellbook** that can cast Teleport (23, `cost <= mana`): `FUN_0056cb8c` (wimpy) / `FUN_0056cef3` (withdraw) take the
  flee cell `scan + 1` / `scan - 1` cells away (`FUN_00558b92`) and teleport there (cast at a cell); the Invisibility branch after it is unreachable (both tests ask
  for spell 23; INFERRED: the second was meant to be 12). Without Teleport the normal flee runs. Only `Orc_Sword.4/5` have Teleport in the book (a slot spell) and their mana is 0 < 60, so this never fires
  for a template unit (a human mage with Teleport and 60 mana would).
* Mode 9 / order `0xe`: the group pass runs `FUN_0056969c(u, B+0x3c, B+0x30)` for order `0xe` (`FUN_00569321`); command `0x1f` -> `FUN_0057033d(group, x, y)`
  -> per member with a wrapper `FUN_0056d446` (cancel, order `0xe`, `B+0x3c := y << 8 | x`, wrapper, range, mode 0); only spells with `target == 2` (`FUN_0051941a`).

### 12.7 The cast Brain modes for an AI caster

Mode 8 (`FUN_0056ebc0`) and mode 9 (`FUN_0056ec3f`) start the cast (`FUN_0056e906` / `FUN_0056e986`: brain order 2, state `0xd` / `0xe`) and call the stop
`FUN_0056dbc6` **only when `B+0x60 == 0`** (a player's cast). An AI cast has `B+0x60 == 1`: the mode stays 8 / 9, so when the brain order ends (3 ticks after the
done flag) the **same spell is cast again at the same target / cell** until the next group pass replaces the mode, exactly like the melee mode 5. A short mana
check fails silently and retries every 3 ticks. Only the cancel `FUN_0056d969` clears `B+0x60` (`0x56da27`). Mode 9 is: in range = `facing == FUN_00556b2c(u, cell)`
and `Chebyshev(cell u, cell) <= B+0x14` (`FUN_0055539a`); else `FUN_0056e4ac(u, cell, range)` = the move driver `FUN_00555411(u, cell, range)` towards the cell, which at
a cell centre within `range` only turns to the cell (`FUN_00556da2`), and state 1.

**Engine (`engine/sim/ai.py`, `spells.py`)**: `engage` = 12.2 (computer branch built; the human branch keeps mode 5: `FUN_0056b059` is exact as a no-op because the
engine has no selected spell, `FUN_0056bc7b` is not built), `special_attack` = 12.3, `caster_attack` = 12.4, `mage_idle` / `friend_cast` = 12.5 (called by `idle`), the
casts are `CastSpell(..., ai=True)` commands (unit or cell) applied by `ai.apply` (mode 8 / 9 with `Unit.ai_cast`), the Brain mode 9 and state `0xe` are
`spells.cell_mode` / `cast_tick`. Effects: `+0x144` effect bits other than Invisibility do not exist in the engine (no effect system), so "already active" is always false.
The Teleport flee (12.6) is not built (no shipped template can reach it).

## 13. VERIFY IN GAME

1. Think rate: a monster standing still reacts within 16 ticks (1-2 s at speed 0-8) of a hero entering its sight; two monsters of one squad react in the **same** tick.
2. Notice distance: stand at 5, 7, 9, 12 cells from a sleeping `Goblin_Pike` (`scan_range` from data.bin) in the open: it should notice at about its `scan_range`
   on flat ground and not through a ridge higher than the observer's cell.
3. Group alert: attack one member of a squad from outside the others' sight: the others get a target after the next pass **only if** the attacker is in
   some member's sight or the hit mark (21 passes) reveals the attacker's cell; the whole squad (not only neighbours) reacts.
4. Pool radius: a hero visible to one member but more than `+0x2d` cells (3-5 beyond the squad's reach, at least 20) from the squad centroid is ignored.
5. Return: lure a monster 20+ cells away and out of sight; it walks back to its own start cell (anchor), not the squad's centroid.
6. Run-away after a hit with no target: hit a monster from out of its sight (bow) and note it runs 10 cells away from the shooter for about 10 ticks.
7. Flee: `Goblin_Pike` at HP <= 10 of 40 with the hero within 10 cells steps away 3 cells every 16 ticks (wimpy); an `Orc_Bow` backs off from anything within 2 cells.
8. Never-hit unit whose target is unreachable (across water) stamps `+0x16` and walks to the reachable cell nearest the map corner (0, 0) for up to ~10 blocks (CONFIRMED statically, §3): does it look like that?
9. A melee monster never targets a flyer; a hero on a ridge higher than the monster is noticed later.
10. Idle monsters turn on the spot about every 3 seconds, and a monster hit from behind turns at once.
11. G (guard): the selected units stop on their cell (the cell being entered when mid-step), then attack any enemy that comes within about the sight of the group (radius at least 10 cells,
    +3..5 after the first pass) and walk back to that post afterwards; the default (T) never leaves its cell.
12. L (stand still): the units never attack on their own and never move after the command, even with an enemy adjacent; they fight only when ordered.
13. Swarm (S then click, or Ctrl+click): the group walks as in a move, but engages every enemy it sees on the way (stops to fight, then resumes the walk to the clicked cell).
14. Wander (scripted only, no shipped map known to use it): a squad ordered to wander picks a cell 20 cells away in one of 8 directions every 51 passes or when it is within 9 cells; in the exe
    the members themselves walk to their own old destination (or the map corner (0, 0)), not to the picked cell (§14.1): does a scripted wander squad visibly walk to a corner?

15. Special attacks: a `Squirrel.4` (Fire Arrow, probability 10) switches to Fire Arrow on about one pass in ten and then casts it (free) every few ticks until the next pass, otherwise bites; an `Orc_Sword.4` teleports next to a hero
    more than 2 cells away (the effect is not built in the engine).
16. A computer mage (Orc_Shaman, Necro*) keeps casting the same spell at its target every few ticks between passes (mode 8 stays), heals itself when hurt and, idle at full HP,
    casts Shield on itself (the engine has no effects: it recasts Shield every pass and burns mana; in the game the active Shield stops that).
17. A mage with mind >= 60 (Dragon) melees in about 30 % of the passes even with mana.

## 14. The other group orders (CONFIRMED, `FUN_005700f3` dispatch; engine: implemented, see the end of this section)

Group order = `record+0x20`; the pass `FUN_00570087` visits every player's groups (`FUN_005700f3`: empty group -> `0xff`, handler, then the post step §9 on every
member). "Pool" = `FUN_00571c4d` over the members (§4), "assign" = `FUN_0057240b` (each member's lowest `FUN_005711ea` score in the pool, §5, no radius filter unless
stated), "act" = per member in list order: target -> `FUN_0056acc8` (§6), no target -> the line given. `idle` = `FUN_0056afd9`: a computer owner gets brain mode `0xb`
(§6.1), a human's non-caster brain mode 0 (`FUN_0056b025`; a mage runs the caster scan `FUN_0056bc7b`, §12.6). `go(m, c)` = `FUN_0056c8af` (§3).

| Order | Handler | Per pass (every 16 ticks) | Set by |
|---|---|---|---|
| `0` | `FUN_0056fe34` -> `FUN_005692d5` | each member runs its own order executor (attack order 3 etc., [combat](combat.md)) | cmds `0x14` (R), `0x19` attack, `0x1b` follow, `0x1d` patrol; scripted attack/follow |
| `1` guard | `57275f` | the §3 machinery of `0x12` without the hit / stamp branch table: centroid stats, pool, radius filter (`+0x2d`), assign, first-pass radius growth (§3.5); act: no target -> if cell == anchor `brain+0` and at a centre `idle`, else `go(m, anchor)` | cmd `0x17` G (`FUN_005709d9`, members order `0xb` via `FUN_0056d4ba`, radius floor `MinimalGuardRange` = 10); scripted guard (sub-command 1, radius byte) |
| `2` go & hold | `572d57(group, dest = +0x0a)` | pool, assign (no radius); act: no target -> if cell == dest and at a centre `idle`, else `go(m, dest)` | scripted sub-command 2 (`FUN_005708bc`: cancel, `+0x0a := y << 8 \| x`, members keep their order); the **quest** classes `0xb` / `0xc` when the human accepts them (`FUN_0052f8e2` cases `0xb`, `0xc`; not a map object, [§15.2](#152-the-quest-that-sends-a-group-order-2)) |
| `3` stand ground | `57309d` | pool, **`FUN_005725a8`** assign with `FUN_005713f8` (the reach-limited score below), no radius filter, no pass counter; act: no target -> `idle`, target -> `FUN_0056acc8` (brain mode 5, the unit's order stays `0xc`) | cmd `0x18` T (`FUN_00570b8b`: members order `0xc` on the own cell), map load for every human squad (`FUN_00562745` via `FUN_00570f2b` = cancel + `570b8b`), scripted sub-command 3 |
| `4` move | `573198` | [click-to-move §4.4](click-to-move-research.md); a **stopped** member (`brain+0x50`) runs the guard scan `FUN_0056a1fb` (§7) every pass | cmd `0x16` move, scripted sub-command 4 |
| `5` swarm | `572e1e(group, dest = +0x0a)` | pool; **pool empty -> `573198(group, dest)`** (walk to `dest` as a move group, scan for the stopped); else assign (no radius), act: no target -> `FUN_0056afac(m, 1)` = `idle`, target -> `FUN_0056acc8` | cmd `0x1a` (`FUN_0057063e`: formation offsets in `brain+0x24/0x26`, `+0x44` speed, `+0x0a := dest`), scripted sub-command 5 |
| `0x11` wander | `572ec4` | `d` = max Chebyshev distance of the members from `+0x0a`; **if `d < 10` or the counter `+0x15 > 0x32`**: `+0x0a :=` the cell 20 cells away in a random one of the 8 directions (`rand(0..7)`, redrawn until it is inside the playable rectangle), counter := 0; then `572e1e(group, +0x0a)` and counter++ | scripted sub-command 17 (`FUN_005708ff`: `+0x0a :=` the first member's cell, counter := 0) |
| `0x12` computer guard | `5728fa` | §3 | `FUN_00570aba` at map load (every non-human squad), by `520a5e` (summon: creates the group, then runs the stored instant), `560d9b` (scripted unit creation, likewise), scripted sub-command 18 (radius byte) |
| `0x13` stand still | `57311c` | `idle` for every member (no pool, no target, no scan: never fights unless attacked and ordered) | cmd `0x12` L (`FUN_00570bde`: members order `0x17` via `FUN_0056d572`) |
| `0xff` empty | `573159` | every member `FUN_0056afac(m, 0)` = guard scan (§7). An empty group is forced to it (`FUN_005700f3`), so it only runs for a member joined to such a group; a **fresh group record starts at 0** (`FUN_0052b06f` -> ctor `0x52ae43` -> record ctor `0x5690ee`: memset 0, `+0x20 = 0`, `+0x45 = 1`; the earlier reading of `0xff` was the player's own 0x24-byte record, `FUN_005691c7` from the player ctor `FUN_00515cd8`, CONFIRMED) | - |

Scripted orders are the trigger-side "instant" of type 6 (`FUN_00574f3f` switch -> `FUN_00577cee`, sub-command in `+8`; `FUN_00574ba1` runs the instants of the
triggers whose conditions hold; [triggers §4](triggers.md#4-instants-fun_00574f3f), built for all sub-commands). The sub-commands 10 / 11 / 14 / 15 (attack, defend, patrol, follow) leave the group at
order **0** and give each member a unit order: `570946` / `570c84` / `570d26` / `570cd5`, [§14.2](#142-the-unit-orders-of-the-scripted-sub-commands-10-11-14-15-confirmed). So a script can replace a computer squad's `0x12` by 1 (guard), 2 (go and hold), 3, 4, 5 or `0x11` (wander).
No path sets 2 / `0x11` / `0x13` / `0xff` on a human squad except a script or an object effect (2) and the L key (`0x13`).

**Stand ground (3) answers "do idle heroes attack what stands next to them?"** Yes, through **the pool and the score, not the guard scan** (`FUN_0056a1fb` is not
called by `57309d`): every 16 ticks (`tick & 15 == 6`, same tick for all groups) each member of a stand-ground group takes the lowest score over the hostile living
units (relation bit 1) inside the **union of the members' sight floods** (§4.1; a unit with `scan_range` 0 sees only its own cell). `FUN_005713f8(me, cand)`:
`d` = Chebyshev distance of the cells; candidate class as in §5; **melee** (`range < 2`): preference table `PREFERENCE[class(me) * 4 + class(cand)]`; **ranged**: table row
by the candidate class, `d := d - range + 1` if `d > range` else 1; **`d >= 2` or preference 0 -> `0xffffff` (not a target)**; else `score = d * 256 + facing change`, doubled for
preference 1, halved for 4 (none of §5's mind / HP / `0x40000` terms). So a melee unit targets only an **adjacent cell** (cell distance <= 1), a ranged unit anything
within its attack range, that it can see; then brain mode 5 on it (the swing starts when facing and `reach_gap <= range`, §6 / [combat §2.3](combat.md)). No target ->
brain mode 0 (which also ends a chase started by the previous pass). The unit never walks to a target beyond its reach, but mode 5 may step after an adjacent target for
up to 16 ticks. The pass uses the unit's *cell*, not its footprint gap, for the cutoff. Without a spell list nothing else differs between human and computer owners.
The reaction lag is the monsters' (up to 16 ticks, all groups in the same tick). A human group after a move command (order 4) get the real guard scan (the unit stopped by the
arrival `FUN_0056dbc6`, `brain+0x50 == 1`): range `FUN_0056ac5b` (adjacent for melee), candidates = the unit's **own** sight, `reach_gap` order (§7), brain mode 6 (`FUN_0056c840`).

Engine: `ai.stand_pass` (`orders.group_pass`, behind `world.ai_on`), `ai.score_stand`, the human `idle` (mode 0), `ai._stand_squads` at `enable` (the stand groups of the human squads),
the guard scan for stopped members of move groups (`orders._pass_move`). With the AI off nothing changes. DECISIONS: the human's brain mode 6 of the guard scan is the mode-5
driver (as for monsters); spell-list units (casters) take the non-caster branch; the `+0x4c & 8` flag test of `FUN_0056acc8` is skipped (§10); the final clause of `FUN_0056a1fb`
(`FUN_0055be86` re-stamp when `mover+0x80` differs) is not modelled.

### 14.1 Implementation and the asm details it rests on (CONFIRMED unless marked)

Engine: `ai.run_group` (the dispatch `FUN_005700f3` for one non-empty group, then the post step §9 for every member when the AI is on) is called by `ai_system` for the squads
(`AiGroup`) and by `orders.group_pass` for the command groups (`OrderGroup`; same AI fields `centre/spread/reach/radius/base/seen/passes/counter/target`, dumped only when non-zero).
Handlers: `ai.guard_pass` (`57275f`), `hold_pass` (`572d57`), `swarm_pass` (`572e1e`), `wander_pass` (`572ec4`), `handler` (`5728fa`), the still pass (`57311c`: `idle` for every member)
and the empty pass (`573159`: `guard_scan`); 3 and 4 as before. Orders 1 / 2 / 3 / 0x11 / 0x12 / 0x13 / 0xff run only with the AI on (like the stand-ground pass); **5 and 0x11 also with the AI
off** (the pool is empty then: they walk as a move group, which is what the exe does without enemies). The wake gate (§15.1) applies to the squads as before.

* `57275f` = `5728fa` without the branch table: `56fa63` stats, `571c4d` pool, `567e92(centroid word, +0x2d)`, `57240b`, the `+0x30` / `5726f7` radius growth (`rand(-1..1)`), then per member
  target -> `56acc8`, else (cell == `brain+0`, at a centre) `56afac(m, 1)` else `56c8af(m, brain+0)`. `572d57(group, +0x0a)`: `571c4d`, `57240b` (no radius, no stats), per member target -> `56acc8`,
  else cell == dest at a centre -> `56afac(m, 1)` else `go(dest)`. `572e1e`: `571c4d`; pool empty (`44fc20` on `server+0xa68`, after the dead list is put back) -> `573198(group, dest)`, else `57240b` and
  per member target -> `56acc8` else `56afac(m, 1)`. `57311c`: `56afd9` per member. `573159`: `56afac(m, 0)`.
* **`573198` goes to `brain+0xa` of each member**, not to its `dest` argument (`0x5732e3`: `56c8af(u, u.brain+0xa)`; `dest` only feeds the blocked-target test `55cd50` and `brain+0xa == dest`).
  A swarm gives every member its own destination (formation, `56d032`), so it works; a **wander group never writes the members' `brain+0xa`**, so a member that never had a move order
  walks to cell word 0 = cell (0, 0) (`brain` is memset 0, `0x569003`), the unit that had one keeps walking to its old destination: the retargeting of `+0x0a` only changes which pool-free
  passes count (`d`, the counter). **Wander as shipped is a half-finished feature** (INFERRED: no shipped map script is known to use sub-command 17, `FUN_005708ff`); the engine copies it
  (the move pass treats a missing destination as cell (0, 0)).
* Wander (`572ec4`): `d` = max `558fe9(cell, +0x0a) & 0xff`; `d < 10` or the byte `+0x15 > 0x32` retargets: loop `k = rand(0..7)` (`FUN_0057aff0(0, 7)` = `rand15 * 8 / 0x8000`; engine `rng.rand(7)`, inclusive),
  `x = byte(+0x0a) + dx[k] * 20`, `y = byte(+0x0b) + dy[k] * 20` with the direction tables `pf+0x58e88 / +0x58e90` = `dx 0,1,1,1,0,-1,-1,-1`, `dy -1,-1,0,1,1,1,0,-1` (up, clockwise; written
  `0x553e4e`-`0x553eeb`), repeated until `minX <= x <= maxX`, `minY <= y <= maxY` (`pf+0x58eb8..bb` = 8 and size - 9); then `+0x15 := 0`; `572e1e(group, +0x0a)`; `+0x15++`.
  `5708ff` (scripted): `570e83`, order `0x11`, `+0x0a :=` first member's cell word (`54ff9e`), counter 0.
* Commands (all `FUN_004f515d`, `0x4f5468` etc.): cmd `0x17` G = `5709d9(group, 0)`: `570e83`, members `56d4ba` (cancel, order `0xb`, anchor `mover+6` when `551383` says off-centre else
  the own cell, brain mode 0), group order 1, `57026e` (`56f850` stats, `+0x2d = +0x38 := +0x2c`, home word), radius arg 0 -> if `+0x2d < server+0xa8b8` (`MinimalGuardRange`, 10) then
  `+0x2d = +0x38 := 10`; `+0x39 := 0`. **`570aba` (squads) is the same code with group order `0x12` and the floor 20 (`0x14`)** (`0x570b6d`); a radius byte raises both. Cmd `0x12` L = `570bde`: members `56d572`
  (order `0x17`, anchor own cell, mode 0), group order `0x13`. Cmd `0x1a` = `5709b8` -> `57063e` = the move code `5703c0` (formation, minspeed) with group order 5 and `+0x0a := y << 8 | x`.
  Scripted setters (`577d1d`-`577e34`, jump table `0x577e57`): sub-commands 1 `5709d9(radius +0xc)`, 2 `5708bc(x +0xc, y +0x10)`, 3 `570b8b`, 4 `5703c0`, 5 `57063e`, 17 `5708ff`, 18 `570aba(radius +0xc)`.
  `5708bc`: `570e83`, order 2, `+0x0a := y << 8 | x`; the members keep order and mode.
* Engine API: commands `Guard`, `StandStill`, `Swarm` (`engine/sim/commands.py`; `orders.intake` + `guard_group` / `still_group` / `move_group(swarm=True)`); `ai.set_group_order(world, group, order, target)`
  (orders 1 radius, 2 / 4 / 5 `(x, y)`, 3, 0x11, 0x12 radius, 0x13) = the Scenario instant `FUN_00577cee` without the trigger side; `ai.find_squad(world, owner, squad)` finds the group; hotkeys G, L
  and the swarm click in `engine/ui/orders.py` (`engine/backend_pygame/window.py` maps the keys). Member executors: `movement.set_guard` (0xb), `set_still` (0x17).
* DECISIONS / deviations: a pool-driven unit (group order 1, 2, 5, 0x11, 0x12) whose target id vanished ends mode 5 and keeps its order (`ai.pool_driven`; the same INFERRED rule as for squads, §10);
  the exe's `FUN_0056ed4e` auto scan at a mover event runs for every order except 1, `0xa`, `0x18`, the engine does it for order `0xb` only; `ai_system` (squads) and `orders.group_pass` (command
  groups) are two loops, the exe has one list per owner in creation order (visible only when a player owns both kinds and both draw the dice in one pass); computer-owned command groups never sleep;
  the retarget loop is capped at 1000 draws (the exe would hang on a map under 40 cells).
  The AI-off swarm uses `orders._pass_move` (no pool); `stand_pass` still builds its pool without the hidden-unit detectors (no hidden setter yet).
* Callers of the guard / stand-ground setters (CONFIRMED): the summon spell makes a group of one minion and calls `5709d9(group, 0)` (`0x51a8d7`, group order 1 = the player's G command); Control Spirit calls `570f2b` (`0x51b1a2`, cancel + `570b8b`, group order 3). Both are built
  (`spells.summon_release` / `raise_release`, [spells §9b](../data/spells.md#9b-field-carriers-summons-raising-tooltip)); the other callers of `570f2b` (`0x4f0637` the owner change, built in `triggers.change_owner`; `0x4f3105`, `0x4f34d9`, `0x4f39c8`, `0x4f8c6b`, `0x52fdba`) are the new-unit / load paths and are not separate features.

### 14.2 The unit orders of the scripted sub-commands 10, 11, 14, 15 (CONFIRMED)

All four start with `570e83` (cancel every member, group order := 0), then loop over the members; the members run their **own order executor** in the group pass of order 0 (`FUN_00569321`, the jump table `0x5695c8`: order 3 `56acc8`, 8 `5696e8`, `0xa` `569b62`, `0xb` `569cc9` -> `56a5fc`, `0xc` `56a1fb`, `0x11` `569857`; before it: orders 3 / 8 / `0x11` whose target / leader is in state `0x10` -> `56dbc6` stop, `0x569361`).

| Sub | Setter | Member order | Fields |
|---|---|---|---|
| 10 attack `u` | `570946` -> `56d1be(m, u)` | 3 (the normal attack order, [combat §2](combat.md)) | members whose score `5711ea` is `0xffffff` get `56dba1` (stand); the member that is the target stands too |
| 11 defend `u`, `n1` | `570c84` -> `56d5b9(m, u, n1)` | 8 | leader `brain+0x10`, range `brain+0x70` = `n1` (3 when 0); `m == u`: stand |
| 15 follow `u`, `n1` | `570cd5` -> `56d638(m, u, n1)` | `0x11` | the same fields |
| 14 patrol `x`, `y` | `570d26` -> `56d6b7(m, x, y)` | `0xa` | anchor `brain+0` := own cell; waypoint list `brain+0xb4` := [own cell, `y << 8 \| x`] (`5421b0` clear, `55f170` AddHead, `542300` AddTail); current waypoint `brain+2` := the tail (`55f0f0`), flag `brain+4` := 0; `x`, `y` are not clamped |

Executors, every 16 ticks (`d` = `FUN_00551463` of the two cells = Chebyshev distance, `range` = `brain+0x70`):
* **Follow `0x11` (`569857`)**: `range < d` -> Brain mode 4 (`56c960(m, leader, range)`: mode := 4, `brain+0x18` := leader, `brain+0x14` := range); else `d < 2` -> step away (`558b92(m, leader cell origin (x*256, y*256), range)` = the ray from the leader through the member, `range` cells, clamped like the flee step, then `56c8af`); else the guard scan `56afac(m, 0)`.
* **Defend 8 (`5696e8`)**: `range < d` -> mode 4; else a unit with a spell list (`+0x140 != 0`) runs `569968`: spell `0x18` (Heal) is wanted when `+0xa0 == 0` and the leader's HP `+0x94` < max `+0x96`, or when `+0xa0 < +0x9c + 3` and the leader's HP < max / 2; if the unit knows it (`51c391`) and its mana `+0x9a` >= the wrapper's `+0xc` it casts it at the leader (`brain+0x60 := 1`, `56c72b`, Brain mode 8) and nothing else happens, otherwise `56a73b(m, leader)` (the word `+0xa0` is UNKNOWN: `unit-struct` marks it "copied"); a unit without a spell list goes straight to `56a73b(m, leader)`: the hostiles in the square of radius `mover+8` (5) round the **leader** (`567945`: `54ec6a` + relation filter `567a16` with the leader as reference + `567f49` which deletes class-3 units when the leader's range `56ac5b` is < 2), class-3 candidates first: the smallest `reach_gap` (`556dcd(m, c)`, first on a tie) -> `56acc8`; else the smallest gap overall (initial `0xff`, strict `<`) -> `56acc8`; **no hostile at all -> guard scan**. After it: if the Brain mode is not 5, 6, 8, 9 and `d < 2` the same step away as above.
* **Patrol `0xa` (`569b62`)**: Brain mode := 0; if `brain+4` the anchor `brain+0` := the own cell and `brain+4` := 0; then `56a5fc` = the order-`0xb` executor: anchor 0 -> own cell; distance to the anchor >= the scan range byte `+0xa5` -> go back (`56c8af`); hostiles in the square of radius 5 round the **anchor** (`567988`, unit as reference): the first -> `56acc8`; none: off the anchor -> go back, else guard scan. Afterwards, **if the mode is 0 or `0xb`** (no fight, no walk): `brain+4` := 1; at the waypoint (`cell == brain+2`) the next one (`57b020` = CList::Find of the first equal entry, `GetNext`, wraps to the head) -> `brain+2`; `56c8af(m, brain+2)`. A unit with scan range 0 always satisfies `d >= 0`, goes back to its anchor and **never patrols** (faithful quirk, hero-like test units).
* **Mode 4 (`56ea52(m, target)`)**: the follow driver `55574d` towards `brain+0x18` within `brain+0x14`, state := 1, brain order 3 (a step) when at a cell centre: the approach half of mode 5.

Engine (`engine/sim/follow.py`): `Unit.leader` / `follow_range` / `mode_follow` / `follow_target` / `patrol` / `patrol_wp` / `patrol_walk`; `set_defend`, `set_follow`, `set_patrol`, `defend_group` / `follow_group` / `patrol_group`, `orders.attack_group` (10); executors `exec_defend` / `exec_follow` / `exec_patrol` from `orders._pass_orders` (so also for squads: `ai.run_group` order 0); `mode_follow` is cleared by every other mode setter and ticked in `movement._tick_inner`. DECISIONS: the scans (guard scan, defend scan, enemies round the anchor) run only with the AI on (an AI-off sim has no enemies, as `_pass_move`); a spell-list unit takes the plain `56a73b` branch (no Heal at the leader: `+0xa0` unknown, the cast path `spells.apply_cast` exists); a leader the world freed stops the follower like a dead one. Tests `tests/test_engine_follow.py`, `test_engine_triggers_maps.py` (maps 30 / 53 / 70).

## 15. Sleeping squads (record `+0x45` / `+0x48`) and the quest that sends a group (order 2)

### 15.1 The awake map (CONFIRMED)

Two different fields are called "`+0x48`": the **GroupAI record** (`group+0x3c`, 0x50 bytes, ctor `0x5690ee`) and the **group object** (the owner's group, `group+0x48` / `+0x4c`).

* **Record `+0x45` = awake** (default 1, `0x569134`). `server+0xbbe8` is the "no sleeping" switch: 0 = sleeping on. The server constructor ends with 0 (`0x568da9`; the `< 0x78` test at `0x568d85` is overwritten), `0x568255` clears it, the only other writer is a debug toggle (`0x57896a`, log strings at `0x5ff6d8` / `0x5ff6f0`). So in the shipped game **sleeping is on**.
* **Recompute `FUN_0055b5f1`**: at map load (`0x4f212b`), at the start of every group pass (`FUN_0056fe4d` `0x56fe9c`, only when `bbe8 == 0`, i.e. each `tick & 15 == 6`) and after a summon spell (`0x51a8e8`, `0x51b1b3`). Steps: (1) `FUN_0055b879` zeroes the block table and sets `+0x45 := 0` in **every group of every computer player** (owner `+0x2c != 0`), and clears every creature's `+0x1a4`; (2) `FUN_0055aca2` per creature: a unit of a **human** owner (`+0x2c == 0`) ORs the owner's player mask (`owner+0x32`) into the 5 x 5 blocks (8 x 8 cells each, index `(x >> 3, y >> 3)`, table `+0x400`, stride `0x88`, one pad block) centred on its block; a computer unit with `HP < max HP` (`+0x94 < +0x96`) sets `+0x45 := 1` (wounded squads stay awake); the main hero of each human is passed too; (3) `FUN_0055b406` per creature: if the block under it is marked (a human within two blocks, so 16..23 cells) -> `+0x45 := 1` and `creature+0x1a4 :=` the mask; otherwise, **if record `+0x48 != 0` -> `+0x45 := 1`** (never sleeps); (4) the corpse list and `FUN_0055b507` only copy the mask. The older 16-cell variants `0x55aab4` / `0x55ab75` are not called by it.
* **Gates**: `FUN_00570087` (group pass) runs `FUN_005700f3` only if `+0x45 != 0` (so a sleeping squad gets neither handler nor post step); `FUN_0056dca2` pre-check (a) (`0x56dcb0`-`0x56dce7`): `bbe8 == 0` and `+0x45 == 0` and Brain order (`brain+9`) 0 -> `state := 0x1b` and the whole Brain tick is skipped (no mode executor, no look-around, no mover event). A member with a Brain order (swing 1, cast 2, **step in progress 3**) is not stopped, so steps finish. Human squads keep `+0x45 = 1` (never cleared).
* **Meaning of record `+0x48`: "kept awake" (never sleeps)**; it changes nothing but this test (`0x55b4c3`, the only reader of the record field; every other `+0x48` read in the scan is another class). Writers: `FUN_00562745` (the Scenario instant compiler, run at map load, `0x56314e`-`0x563a3b` and `0x5632d4` etc.): for every instant and every check (type `< 0x10002`), the **first** resolved parameter of kind 2 (group, `FUN_005626bc` "Can't resolve group"; the second only when the first is null) and **every** resolved parameter of kind 4 (unit or hero, `FUN_00562274`, its group `creature+0x70`; re-read in `0x562f9e`-`0x5632f4`: the unit tail runs after each unit argument, so both the first and the second unit are flagged) are taken, and that squad gets `record+0x48 := 1`, **except for checks of type 1** ("how many units contains this group"; [triggers §2.2](triggers.md#22-runtime-record-instants-and-checks-share-it-confirmed-by-the-writes)): a script that mentions a squad keeps it awake; the quest accept below; cleared by `FUN_005781a7` (instant 39 "Suspend group", called from `FUN_00574f3f`). So **plain map-loaded monster squads that no script names have `+0x48 = 0` and do sleep**; the engine sets `AiGroup.keep_awake` when it compiles the map script (`triggers.enable`, [triggers §8](triggers.md#8-engine-enginesimtriggerspy)) and leaves it False without it.
* **Group-object `+0x48` / `+0x4c`** are quest flags, not sleep: the squad creator copies them from the creation record bits 4 / 8 (masks `0x5feecc` = 4, `0x5feed0` = 8; `560d9b` at `0x56118a` / `0x5611b6`, through creature `+0xc4` / `+0xc8`) and the summon `520a5e` (`0x520c20`, `0x520c2f`) copies the source creature's; their only readers are the quest generator `FUN_005303ed` (`0x530f8e` `+0x48`, `0x5317c6` `+0x4c`). The squad creators write the **flag value (0 or 1)**, not a constant 1.

Engine: `ai.wake` (map load in `enable`, and at every `ai_system` pass before the handlers), `ai.asleep` (called from `movement._tick_unit` before the Brain tick; sets `ai.SLEEP_STATE` 0x1b, clears it at the next awake tick), `AiGroup.awake` / `keep_awake`, `World.ai_sleep` (= `bbe8 == 0`, default True; the synthetic test worlds of `tests/test_engine_ai.py` switch it off). The block test is on the cell `(x >> 3, y >> 3)` of members and human units (`hp > 0`; dying human bodies mark in the original until removed, not modelled). Effect on a map: a monster squad farther than 23 cells from every human unit (and unhurt) does not look around, does not react and a chase it was running with Brain order 0 stops; it wakes when a human unit comes within 16..23 cells (before its sight, at most 12 cells, matters), so the visible change is the idle look-around and the pass timing of distant squads. Not modelled: the debug toggle, `+0x1a4`; the scripted `keep_awake` comes with `triggers.enable`.

### 15.2 The quest that sends a group (order 2)

`FUN_0052f8e2(hero, id)` is the server handler of a client message (type `0x3a` by the jump-table index of `FUN_004f515d`, `0x4f6437`; the other callers are a loop over the players, `0x4ebe5b`, and `FUN_004f515d`) of the **human** player (`hero` found by the message's unit id and owner, the object `this` by `hero+0x10`): for `id <= 0xff` it is "use inventory item" (potions / scrolls, kinds `-3`, `-2`, `-1`); for **`id >= 0x100` it is the answer to a pending quest** (items.md §14): `FUN_004a1050(id)` finds the quest record the generator `FUN_005303ed` (`this+0xe0` table, flag `+0x10 = 3` "offered") put on offer after the hero asked a quest giver (message `0x38`, `FUN_0052f813`), then the quest leaves the offer list (`FUN_0052e27d`), becomes open (`+0x10 := 0`), is registered (`FUN_0052e212`) and the vtable `+0x28` **quest kind** selects a side effect:

| Kind | Quest class (ctor) | Offered when (generator) | Effect on accept |
|---|---|---|---|
| `0xb` | `0x5480e0` | a creature of another owner with the map-unit behaviour bit 2 (`+0x19c`), visible to the player (relation bit 1 matrix `0xa8c4`), type range allowed by the giver's flags, strength window `best skill * 3 - 50 < FUN_00510a26 < best skill * 3 + 75`, and no quest of kind `0xc` on it yet; reward `level * 3` | its squad (`creature+0x70`): `record+0x48 := 1`, then **group order 2** to the cell of `this+0x10` (`FUN_005708bc`, `0x530220`-) |
| `0xc` | `0x548190` | a squad whose group-object `+0x4c != 0` (creation flag bit 8), visible, strength window, no quest on it; reward `max level * 6` | every player's squad with `group+0x1c == quest+0x14` (the first match): `record+0x48 := 1`, group order 2 to `this+0x10` (`0x530159`-) |
| `4`, `5`, `6` | other classes | `FUN_004f0568`, a created object `FUN_00522ee0(0xe, ...)`, `FUN_00549370` | not group orders |

So the "map-object effect" of the earlier INFERRED line does not exist: it is the **acceptance of a generated quest** of a human hero (`this` = the **quest giver**, CONFIRMED by the object's fields: the quest tables `this+0x88` / `+0xa4` / `+0xe0` / `+0xe4`, the id `this+0x4` that `FUN_0052e198` events carry, and the destination read from `this+0x10` by `54ffb0` / `54ffc0` at `0x5301c1`-`0x5301e8`, so the squad is called to the giver's cell; the giver is a creature-class object), and the squads it calls are those flagged by **map-unit behaviour bit 2 or creation-record bit 8**. `map.md`: only behaviour bit 8 occurs in the shipped maps, so kind `0xb` is never offered there; kind `0xc` needs squads created by `560d9b` / `520a5e` with record bit 8, which the shipped scripts were not scanned for. Order 2 therefore never runs on the squads the engine already has (order `0x12`), and nothing here changes their behaviour except the `keep_awake := 1` that makes the called squad run while far from the humans. The engine has **no quest system** (the generator `FUN_005303ed`, the hero's ask message `0x38`), so this path is not built; the setters it ends in (`FUN_005708bc` = `orders.hold_group`, `keep_awake`) exist for the script. The quest completion events (kinds posted by `FUN_0057e87a` etc.) are not decoded.

## Open questions

* The unit word `+0xa0` read by the caster follow branch `FUN_00569968` (defend / `0x11` of a unit with a spell list heals the leader; engine: plain scan). The sacks/pickup order (`P` key, cmd `0x13`, `FUN_00419f2a`) is not a group handler.
* The quest side of [§15.2](#152-the-quest-that-sends-a-group-order-2): whether the shipped scripts ever create squads with creation-record bit 8 (kind `0xc`), the completion events of kinds `0xb` / `0xc` (`FUN_0057e87a`), and the three non-group kinds `4`-`6`; the engine has no quest system.
* Party-AI flag byte of a human player (player `+0x34` record `+0x20`, default `0xff`, §12.6): which client option / command writes it (`0x4f6945`, operand `+0xe`) and its single-player
  value; needed before `FUN_0056bc7b` (human mages healing / buffing on their own) is built. Start: the command case of `0x4f6945` in `FUN_004f515d`, its client sender.
* Book wrapper range: does `FUN_00519483` scale the spellbook's own wrapper (so `+9` is the range of the last cast's level) or a copy? The engine uses the range at the caster's
  current level everywhere (`spells.wrapper_range`). Start `0x519483`, `0x5195b1`.
* Revive `FUN_00510534` (Heal of a dying unit): `FUN_005551d6(position)` and whether the recompute (vtable `+0x58`) rebuilds defence after the `<<= 1` (engine: rebuilt).

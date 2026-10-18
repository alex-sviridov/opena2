# Click to move: from the mouse click to the walking unit (research)

Research notes for phase H3 (orders) and the order phases after it. Everything was read in the GOG `allods2.exe`
(sha256 in [formats/README](../formats/README.md), image base `0x400000`) with REA and the objdump listing;
**the decompiler's `in_ECX` is unreliable, so every `this`/field below was read from the assembly.** Marks:
**CONFIRMED** (routine address given) or **INFERRED**. Companion docs: [simulation](simulation.md) §3, §4, §7;
[ui-layout](ui-layout.md) §6-§8; [unit-struct](unit-struct.md) §8, §9. "Out of scope now" = needed only by
attack, follow, pickup, use, cast (phases I/K).

Corrections to the older docs found on the way are collected in §10 (applied in H3 stage A to simulation, ui-layout, unit-struct and animation).

## 1. The input path in the game view

### 1.1 Mouse messages (CONFIRMED)

The window procedure `0x485377` hands `WM_MOUSEMOVE/LBUTTONDOWN..RBUTTONDBLCLK` (`0x200`..`0x206`) to the top window;
the generic dispatcher `FUN_004d4769` offers them to the child under the pointer first (minimap, command bar, info
panel, inventory/spellbook), and calls the **view's own virtual handlers** only when no child took it. The view's vtable
(base `0x5cb088`) gives the real handlers:

| Message | vtable slot | Routine | What it does |
|---|---|---|---|
| `0x200` move | `+0x4c` | `0x40c7dd` | **right button held (wParam bit 2): scroll the camera** by `delta/8` cells per move message (`(d + ((d>>31)&7)) >> 3`, truncating, delta against the mouse manager's previous point `0x604500 +0x10/+0x14`), via message `0x406`; sets `view+0xd8 = 1` ("right drag happened"). Nothing else: no order. |
| `0x201` L down | `+0x54` | `0x40c4ae` | only in game state 1 (`client+0x404 == 1`), when the mouse manager has no capture (`FUN_0041e730`, `+0x9c == 0`) and `view+0x80 != 0`: `FUN_0048acbc` (ClipCursor to the view's rect), `FUN_0042748f(point)` = begin capture: `mgr+0x9c = 1`, press point stored at `mgr+0x6c`. |
| `0x202` L up | `+0x58` | `0x40c5d1` | **the left click / drag-release.** If `mgr+0x9c`: `FUN_00427501` (end capture, `+0x9c = 0`), `FUN_0048ad61` (ClipCursor back), `FUN_0040b2b8` (cursor chooser, §1.3, now without the "dragging" override), `FUN_004175c7(point)` (§1.2). Then the "carry an item" tail (`client+0x3f4`, drops via `FUN_0041a6cd/41a20c`). |
| `0x203` L dbl-click | `+0x5c` | `0x40c5ad` | calls the L-down handler again: a double click is press, release, press, release; no special double-click action exists. |
| `0x204` R down | `+0x60` | `0x40c50a` | sets window flag 8 (vtable `+0x20/+0x24`); no order. |
| `0x205` R up | `+0x64` | `0x40c53a` | **if `view+0xd8 == 0` (no right-drag since the press) and state 1: post message `0x405` to the view**; then `view+0xd8 = 0`, flag 8 cleared. `0x405` → `FUN_00416388` (§1.5). The command bar (`0x4adb09`) and the info panel (`0x4af0dc`) also post `0x405` to the view on their right-button-up. |

`0x40e` / `0x40f` are **not** mouse messages: the keyboard handler `0x40ccb6` sends them for `I`/`~`/space (`0x40e`) and
`B`/`Q`/space (`0x40f`) to toggle the inventory and spellbook windows (`FUN_0041ae4f/41adc2`, `41b077/41af4a`); only as a
side effect, if a left-button capture is still open (`mgr+0x9c`), `0x40c2d4`/`0x40c34d` close it exactly like a release
(`427501`, `48ad61`, `40b2b8`, `4175c7`). Press `I` while holding the left button = a release at the stored point.

### 1.2 What a left release does: `FUN_004175c7` (CONFIRMED, asm)

```
rect = [press point (mgr+0x6c) .. release point], normalised; if empty: inflate by (1,1)   # FUN_0041e2b0 / 41e4d0
thr  = screenW * 10 / 640                                                                 # DAT_00621418; 10 px at 640
if rect.width > thr or rect.height > thr:  FUN_00417986(rect)            # drag select (ui-layout §8)
elif view+0x140 == 0 (nothing selected):   FUN_00417986(rect)            # click select
else:
    c = current cursor id (FUN_0041e6b0 on 0x604500), set by the chooser a moment ago
    dispatch on c (compares with the cursor table of ui-layout §6, FUN_0041f2e0 = id of a cursor object):
        attack  0x626cc4: if view+0x9a8 != 0 and the hovered object (view+0x994) is a CUnit: FUN_00418cb3(9a8)  # cmd 0x19, out of scope
                          else FUN_00418bc3(9ac, 9b0)                                        # MOVE (cmd 0x16)
        swarm   0x626cc0: FUN_00418d78(9ac, 9b0)                                             # cmd 0x1a
        move    0x626cbc: FUN_00418bc3(9ac, 9b0)                                             # cmd 0x16
        patrol  0x626cd0: FUN_004190be(9ac, 9b0)                                             # cmd 0x1d
        defend  0x626cc8: if 9a8 != 0: FUN_00418fc1(9a8)                                     # cmd 0x1b (follow/guard a unit), else nothing
        select  0x626ccc: FUN_00417986(rect)
        pickup  0x626cd8: FUN_00419d8e(9ac, 9b0)                                             # cmd 0x21
        town    0x626d18: FUN_0041a0b5(9a8)                                                  # cmd 0x24 (enter / use a structure)
        cast    0x626cd4: spell = FUN_0041f370(); if spell >= 0:
                          9a8 == 0 or not a CUnit (or FUN_004c72c5()==0): FUN_0041918e(9ac, 9b0, spell+1)   # cmd 0x1f
                          else FUN_004195fa(9a8, spell+1)                                    # cmd 0x1e on an object
                          then if view+0x9b4 == 5 and the spellbook is open (FUN_0041aef1): close it (FUN_0041b077)
        anything else (default, arrow0..7, cantput, wait, ...): no order
    if view+0x9b4 != 0:  view+0x9b4 = 0; FUN_004c7287(); post 0x40b to the command bar (clear its highlight)
```

`9a8/9ac/9b0` are refreshed every frame by the hover routine `FUN_004180c6` (also called inside the chooser): `9a8` =
id (u16, `obj+4`) of the hovered object or 0, `9ac = (mouseX >> 5) + view+0x5c`, `9b0 = row(mouse) + view+0x60`
(`FUN_00417f31`, ui-layout §6 "item cell"), `view+0x994` = hovered object pointer. `FUN_004180c6` returns early (fields stay
stale) when the pointer is outside the view rect; ClipCursor keeps it inside during a press.

The pending-mode reset runs after **every** dispatch of this branch, also when the cursor was one that issued nothing
(the arrow cursors at the screen border, default); it does not run when the click was a select/drag at the top.

### 1.3 Which cursor is current at the click (chooser `FUN_0040b2b8`, CONFIRMED)

Runs every frame in the view draw and once more at the release (§1.1). Modifier globals: Ctrl `0x6227d8`, Shift
`0x6227dc`, Alt `0x6227e0`. Hover flags `h` (ui-layout §6): `1` unit, `2` air unit, `0x20` structure (`0x800` also when the
template is enterable), `4` hovered owner hostile, `0x40` visible item on the cell, `0x400` fogged. Order of tests:

1. Screen border (x or y within the edge band): arrow cursors; clicks there issue nothing (but still run the pending reset).
2. Mouse outside the view rect: hover only. Over the open inventory/spellbook window: default.
3. **No pending mode (`view+0x9b4 == 0`)**
   - spellbook open (`FUN_0041aef1`) and a spell selected (`FUN_0041f370 >= 0`), selection has spells (`view+0x148/0x150`)
     and no foreign unit: *cast branch* (cursor cast by default; out of scope, details in the decompile).
   - otherwise, with `n = view+0x140`, `s = view+0x144` (bits: 1 unit, 2 air, 4 foreign, 0x20 structure):
     - `n == 0`: `h & 0x23` ? select : default.
     - `s & 0x24` (foreign or structure selected): same (select / default). **No orders from a foreign or structure selection.**
     - own non-structure units: `single = (n == 1 and s & 1)`, `hero = single and sel.obj+0x1b8 & 1`,
       `pickup = hero and (h == 0x40 or (view+0x994 == sel and h & 0x40))`, `town = hero and h & 0x800`:

| Pointer over | No modifier | Ctrl | Alt (Ctrl+Alt) |
|---|---|---|---|
| ground (`h & 0x23 == 0`, not hostile) | **move**; pickup when `pickup` | swarm | move (Ctrl wins: swarm) |
| own / allied / neutral unit or structure (`h & 4 == 0`, `h & 0x23`) | select; pickup when `pickup`; town when `town` | attack (force attack on a friend) | move |
| hostile unit (`h & 4`, `h & 0x20 == 0`) | **attack** | swarm | move |
| hostile structure (`h & 4`, `h & 0x20`) | select | select | move |

     Shift never changes the cursor here (it only toggles selection in `FUN_00417986`).
   - finally, while a left capture is open with a non-empty drag rect: default (the rubber-band state); at the release the
     capture is already closed, so the real cursor stands.
4. **Pending mode**: cursor by `view+0x9b4`: 1 attack, 2 move, 4 defend, 5 cast (fogged `h & 0x400` -> move), 6 swarm,
   8 patrol; other values (3, 7) leave the cursor unchanged. Hover flags, Ctrl and Alt are ignored.
5. Open dialog windows 2/3 under the pointer: default. A carried item (`client+0x3f4`): the item's cursor (`+0x400`), the
   backpack cursor `0x626d24` over the hero.
6. `FUN_0047b8f5(cursor)` sets it only when it differs from the current one (animation frame reset).

So the clicked action follows the cursor, not the hover directly: **an `attack` cursor over ground or a structure
issues a plain move (cmd `0x16`); the swarm cursor targets the cell under the pointer even over a unit.**

### 1.4 The pending target mode `view+0x9b4`

Set in exactly one place, `FUN_00418a02(btn)` (CONFIRMED, asm `0x418a02`-`0x418ba8`); `btn` comes from the command bar
(message `0x40c`, `btn = wParam + 1`, handler `0x40c295`), the hotkeys of `FUN_0040c8a0` (WM_KEYDOWN; only in state 1,
`view+0x80 != 0`, no text-input focus `client+0xc0`, **no Ctrl**, `view+0x140 != 0`, `view+0x144 & 0x24 == 0`) and the
F4-F12 spell shortcuts (`btn 9/10` -> 5):

```
mode = 5 if btn in (9, 10) else btn
if view+0x9b4 == 5 and mode != 5 and spellbook open: close it
mask = FUN_0041757b():  0 if foreign selected (view+0x144 & 4); else 0xef | (0x10 if view+0x148 or view+0x150)
if (mask >> (btn-1)) & 1 or btn == 10:  view+0x9b4 = mode; post 0x40d(btn-1) to the command bar (highlight)
else: return                                                     # button disabled, nothing happens
switch btn:                                                     # immediate commands clear the mode again
   3: FUN_00418e51  -> cmd 0x17 ; view+0x9b4 = 0 ; post 0x40b
   7: FUN_00418f09  -> cmd 0x18 ; view+0x9b4 = 0 ; post 0x40b
   8: FUN_00419e72  -> cmd 0x14 ; view+0x9b4 = 0 ; post 0x40b
   5: open the spellbook (FUN_0041af4a) unless open
   others (1, 2, 4, 6): the mode stays armed
```

| Key (README) | btn | Effect | Persistent mode | Out of scope? |
|---|---|---|---|---|
| `A` attack | 1 | arm | 1 -> attack cursor | click-on-ground = move, on a unit = cmd 0x19 (I) |
| `M` move | 2 | arm | 2 -> move cursor | **in scope** |
| `G` guard | 3 | cmd `0x17` at once | - | stop family (§5) |
| `D` defend | 4 | arm | 4 -> defend cursor (click on a unit = cmd 0x1b) | I |
| `C` cast | 5 | spellbook + arm | 5 | K |
| `S` swarm | 6 | arm | 6 -> swarm cursor, cmd `0x1a` at the cell | I |
| `T` stand ground | 7 | cmd `0x18` at once | - | stop family |
| `R` retreat | 8 | cmd `0x14` at once | - | stop family |
| `L` stand still, `P` pick up all sacks | - | `FUN_00419ffd` cmd `0x12`, `FUN_00419f2a` cmd `0x13` (keys, not via `418a02`) | - | stop family / K |

Mode 8 (patrol cursor) is therefore **unreachable from the UI**: the only setter clears it in the same call (patrol
`0x1d` can still be issued by the cursor code if some path leaves 8 armed: none found). With nothing selected the mask is
still `0xef`, so a mode can be armed without a selection (the click then selects, `4175c7`).

Cleared (`view+0x9b4 = 0`, each followed by `FUN_004c7287` and message `0x40b`): after any order click (§1.2) and after a
minimap order (§1.6); right click (§1.5); a click selection/drag selection (`FUN_00417986`, `0x417e86`); when a selected
object disappears (`0x40be67`, `0x414881`); the immediate commands above; view init (`0x402cba`). Esc is not involved (it opens the menu).

### 1.5 The right button (answers ui-layout §8 open question) (CONFIRMED)

Right *release* without a right-drag -> message `0x405` -> `FUN_00416388`:
- `view+0x9b4 != 0`: leave the cast mode cleanly (close the spellbook if mode 5), `FUN_004c7287`, `view+0x9b4 = 0`, post `0x40b`. **The selection is kept.**
- else: for every object in the selection set (`view+0x9d0`, hash order) call its vtable slot `+0x14(0)` (= unselect), then
  `FUN_004167c2` recomputes `view+0x138/0x140/0x144`. **Right click = deselect everything; it never issues an order.**
Right *drag* = camera scroll (§1.1) and neither cancels nor deselects.

### 1.6 Minimap clicks (CONFIRMED, minimap vtable base `0x5cee10`)

Left press `0x4ad00e` (also called on every `WM_MOUSEMOVE` while the left button is held, `0x4ad4b1`), right press `0x4ad32f`
(every move with the right button held too).
- **Right press: always a camera jump** (message `0x406`, ui-layout §4 formula).
- Left press acts by the *current minimap cursor* (chosen on hover by `FUN_004accb4`): the pointer must be inside the
  map image, **and** `view+0x140 != 0` and no foreign/structure selection (`0x144 & 0x24`), else `sdefault` = camera jump.
  With own units selected the cursor is `smove` (`0x626d00`), or by pending mode: 1/6 -> `sattack` (`0x626d04`), 2 -> `smove`,
  4 -> `sdefend` (`0x626d08`), 5 -> `scast` (`0x626d10`), 8 -> `spatrol` (`0x626d0c`).
- `smove` -> `FUN_00418bc3(x, y)` = **a move order, with no pending mode needed**; `sattack` -> unit at the cell
  (`FUN_0040c046`) ? `FUN_00418cb3` (attack) : `FUN_00418d78` (swarm); `sdefend` -> unit ? `FUN_00418fc1`; `spatrol` -> `FUN_004190be`;
  `scast` -> only looks up the unit, sends nothing. Then `view+0x9b4 = 0` and `0x40b`.
- Cell of a minimap click: `x = ((mx - off_x - panel.left) >> z) + 8` (z = minimap zoom shift `+0x68`, `z < 0` clamps to 0
  and doubles instead: `x = (mx - off_x - panel.left) * 2 + 8`), `off_x = 0x48 - (((imgW - 16) << z) >> 1)`, y alike with `0x52`
  (the image centre of ui-layout §4).
- **Quirk (CONFIRMED code, INFERRED effect):** `FUN_00418bc3` ignores its second argument; it recomputes the target row
  from the **mouse position** with the main view's row finder, `y = FUN_00417f31(0x604510, 0x604514) + view+0x60`
  (`0x418c13`-`0x418c31`). From the main view this equals `9b0`; from the minimap the mouse is over the right panel, so the
  row is read at `column = mx >> 5` outside the view's vertex grid and the move order goes to the wrong row. Swarm, attack,
  patrol and defend use both arguments correctly. VERIFY IN GAME.

### 1.7 Target cell of a normal click

`x = (mx >> 5) + view+0x5c`, `y = FUN_00417f31(mx, my) + view+0x60` (relief-aware row, ui-layout §6), both in the same cell
space as the server's unit cells (the pathfinder border of 8 cells is included; `obj+0x38/+0x3c` of a client unit are compared with it in the chooser).
No fog, passability or distance test on the client: a move can be ordered into fog, water, a wall.

## 2. The wire message

Built in a static object `0x6904b8` (vtable `0x5d0c30`; ctor `0x50bb82` -> base `0x50ba7d`), sent by `FUN_0050164f` through
the net hub `0x670e50`; the serialiser (`0x50bbf8`) writes **`msg+9 .. msg+9 + 10 + 2n`**. The receive side (`FUN_005056f1`,
by command byte) deserialises into the same object and sets the category byte `msg+4`: 1 = no target (cmds 0x12-0x14, 0x17, 0x18),
2 = cell target (0x16, 0x1a, 0x1c, 0x1d, 0x1f, 0x21, 0x24, 0x26), 3 = object target (0x19, 0x1b, 0x1e, 0x25) (CONFIRMED table
`0x505c42`/`0x505b02`; `FUN_004f515d` requires `msg+4 >= 1` for the player-command path).

| Offset | Size | Field |
|---|---|---|
| `+4` | u8 | category (receiver-assigned, above) |
| `+5` | u16 | issuing player id (`view+0x9cc` -> `+4`) |
| `+7` | u16 | recipient (0 = broadcast) |
| `+9` | u8 | **command byte** |
| `+0xa` | u16 | cell x (cmds 0x16, 0x1a, 0x1c, 0x1d, 0x1f, 0x21); sub-code for cmd 0x46 |
| `+0xc` | u16 | cell y |
| `+0xe` | u16 | target object id (0x19, 0x1b, 0x1e, 0x24, 0x25); pickup: `selected.obj+0xe4` |
| `+0x10` | u8/u16 | spell index (cast) |
| `+0x12` | u8 | n = number of unit ids (`FUN_0050bbb8` appends; **stops at 253**) |
| `+0x13` | n x u16 | selected unit ids (`obj+4`), in iteration order of the selection hash set `view+0x9d0` (only objects with the selected flag `obj+0x80`) |

**Move = command `0x16`** (`FUN_00418bc3`): `+0xa = 9ac`, `+0xc = row(mouse) + view+0x60`, `+0xe` unused, n ids. No queue,
shift or modifier byte exists in any order message (the packet has no flags field): CONFIRMED by reading all senders
(`0x418bc3`-`0x41a9d1`). After the send the client plays the acknowledgement voice (§6.2); **the client keeps no state about
the order** (no destination, no marker field).

Other senders (all CONFIRMED, out of scope except stop): `0x17` `FUN_00418e51`, `0x18` `FUN_00418f09`, `0x14` `FUN_00419e72`,
`0x13` `FUN_00419f2a`, `0x12` `FUN_00419ffd` (ids only); `0x19` attack `FUN_00418cb3` (`+0xe`); `0x1a` swarm `FUN_00418d78` (x, y);
`0x1b` follow `FUN_00418fc1` (`+0xe`); `0x1d` patrol `FUN_004190be` (x, y); `0x21` pickup `FUN_00419d8e`; `0x24` use `FUN_0041a0b5`
(`+0xe` structure id); `0x1e/0x25` cast on object, `0x1f/0x26` cast at cell (`FUN_004195fa`, `FUN_0041918e`); `0x46` options:
`+0xa = 2` formation, value in `+0xe` (`FUN_0041a617`).

Transport: the hub serialises into a per-connection packet buffer (`0x5000a1`, 0xa8-byte chunks) even in single player; the
server pops its queue (`0x6831a8`) in `FUN_004f84c6`. **Latency (CONFIRMED, answered):** the hubs are cross-linked local connections; the
send flushes at once into the server queue (`FUN_00504bb7` -> `FUN_005017e6` -> `FUN_0050036a`), so the command is applied by the next server
step with no extra tick; details and addresses in [simulation §1.1](simulation.md#11-command-path-latency-and-the-counter-at-start-confirmed-rea-on-the-gog-exe).

## 3. Server: command intake and the order

### 3.1 `FUN_004f515d(msg)`, called from the drain `FUN_004f84c6` (CONFIRMED)

The drain runs at the start of `FUN_004f8521`, **before any unit is updated in that tick** (simulation §2); the group pass
(`tick & 15 == 6`, §4.2) runs earlier still, at the top of `FUN_004f08c0` (before the tick counter is incremented).

```
if msg.category(+4) < 1 -> system messages (not player orders)
if world object 0x66832c == 0: drop
n = msg[+0x12];   if n == 0: drop
u0 = FUN_004f3a19(msg.player(+5), msg.ids[0])          # player lookup in 0x68d2c4 (FUN_004f3ba9; log if unknown) then
                                                       # the unit in THAT player's own unit set (player+0x24, FUN_0052b2bd);
                                                       # dead/removed (state 0x10) -> 0
if u0 == 0: drop the whole command
owner = u0.owner (+0x14);  group = FUN_0052b06f(owner+0x28)     # see below
FUN_0052af8c(group, u0);  FUN_00510745(u0)
for i in 1 .. n-1: u = FUN_004f3a19(player, ids[i]); if u: FUN_0052af8c(group, u); FUN_00510745(u)   # invalid ids skipped silently
FUN_0053d690(owner+0x28, group)                        # append the group to the owner's group list
(cmd 0x1e/0x1f: spell check; msg.category 3: resolve the target object, drop if missing)
dispatch (jump table 0x4f8286, cmd - 0x12):
   0x16, 0x1c -> FUN_005703c0(group, x = byte msg+0xa, y = byte msg+0xc)      # move
   0x1a       -> FUN_005709b8 -> FUN_0057063e(group, x, y)                    # swarm (same formation code, group order 5)
   0x17 FUN_005709d9(group,0)  0x18 FUN_00570b8b  0x12 FUN_00570bde  0x14 FUN_00570c31  0x13 FUN_0056dafe(unit)  # stop family
   0x19 FUN_00570946  0x1b FUN_00570c84  0x1d FUN_00570d26  0x1e FUN_005702be  0x1f FUN_0057033d  0x21 (item lookup, then ...)  0x24 FUN_0056d22b
```

**Validation, exactly:** (a) the command must name at least one id and the **first** id must be a living unit owned by the
claimed player (else nothing happens); later ids that fail the same test are skipped; (b) `x`, `y` are the low bytes of the
u16 fields; (c) **no** passability, range, fog or occupancy test at command time: the only coordinate treatment is the clamp
in `FUN_0056d032` (§3.3); (d) a unit with HP <= 0 but state != 0x10 is accepted (its death tick resets the order, INFERRED);
(e) the player id is trusted as sent (no connection check in single player).

`FUN_0052b06f`: walks the owner's group list, **deletes every empty group** (`0x545710(g, 1)` scalar-deleting destructor)
and allocates a fresh group (`0x50` bytes, ctor `0x52ae43`, with its group record at `+0x3c`, 0x50 bytes, ctor `0x5690ee`,
`+0x45 = 1`). So **every player command creates a new group**; `FUN_0052af8c` first removes the unit from its previous
group (`unit+0x70`, `FUN_0052afd2`), appends it at the tail (`FUN_0053d840` = `FUN_0053c5c0`), sets `unit+0x70 = group` and
`group+0x44 = unit.owner`. Group iteration order (`FUN_0055f220` head / `FUN_0055f240` next) = packet order. A unit ordered
alone leaves its old group; the old group keeps its order and its remaining members.

### 3.2 `FUN_005703c0(group, x, y)` and `FUN_0057063e` (the two are the same code except the final group order)

```
formation = 1;  minspeed = 250                                     # byte
FUN_00570e83(group):                                               # cancel every member
      for u in group: FUN_0056dbfb(u); u.brain+0x38 = 0
      group.record+0x20 = 0                                        # group order := 0
mode = group.owner(+0x44) -> +0x34 -> byte +0x1f                   # the player's FORMATION MODE: 0 off, 1 on, 2 auto (§4.1)
if mode == 2:
      c = FUN_0056f850(group)                                      # centroid, §4.1
      cx, cy = cell of c;   for u in group: if cheb(u.cell, (cx,cy)) > server+0xa724 (= 2): formation = 0
elif mode != 0:  c = FUN_0056f850(group); cx, cy = cell of c       # mode 1: always
else: formation = 0
FUN_00570e83(group)  again
for u in group:                                                    # packet order
      if formation:
            u.brain+0x24 = u.cell.x - cx;  u.brain+0x26 = u.cell.y - cy        # s16 offsets
            FUN_0056d032(u, x + off_x, y + off_y)                  # NOT masked here, see the wrap quirk in §3.3
            minspeed = min(minspeed, low byte of s16 u+0x8c)       # only if (s16)speed < current
      else: FUN_0056d032(u, x, y)
if formation: group.record+0x44 = minspeed                        # group speed (§4.3)
group.record+0x20 = 4                                              # (swarm: 5)  group order = "group move"
group.record+0xa  = (y & 0xff) << 8 | (x & 0xff)                   # group target, NOT clamped
```

`cheb` = `FUN_00558fe9`: `max(|dx|, |dy|)` of two packed cells. `server+0xa724 = 2` is set in the constructor (`0x56824b`).

### 3.3 The order itself: `FUN_0056d032(unit, x, y)` (CONFIRMED)

```
FUN_0056dbfb(unit)                      # cancel, §3.4
x := (x & 0xff);  if x < minX: x = minX;  if x > maxX: x = maxX            # pathfinder +0x58eb8 / +0x58eba
y := (y & 0xff);  if y < minY: y = minY;  if y > maxY: y = maxY            # +0x58eb9 / +0x58ebb
   minX = minY = 8;  maxX = mapW - 9, maxY = mapH - 9      # +0x50000/+0x50004 = Map width/height fields (set 0x554692; 8 = the border)
unit+0x50      = 1                      # order: move to cell
unit.brain+0xa = y << 8 | x             # destination
unit.mover+0x90 = 0                     # "arrived" flag cleared
unit.brain+0x08 = 1                     # Brain mode: go to cell
```
Nothing else: the reserved cell, the plan lists, `mover+0x74/0x76/0x78/9` and the step in progress are untouched.
**Quirk:** the unit's `x+off`/`y+off` are masked with `& 0xff` before the clamp, so a formation member whose target would be
`< 0` wraps to `256 + v`, which the clamp then pins to `maxX/maxY` (the far edge of the map). Only reachable when the click
is closer to the map edge than the member's offset. Clamping is per axis.

### 3.4 Cancel and what a new order does to a unit mid-step (CONFIRMED)

`FUN_0056dbfb(unit)` = `FUN_0056d969(unit)` then `unit.brain+0x50 := 0` (this is *brain* `+0x50`, the **stopped flag**: set to 1 only by
`FUN_0056dbc6`, read only by the group pass `FUN_00573198` (§4.4); not the unit's order at `unit+0x50`, which the issuer overwrites next;
all writers and readers: [unit-struct §8.1](unit-struct.md#81-field-table), CONFIRMED by a scan of every access reached from `creature+0x1c4`).
`FUN_0056d969`:
1. `mover[1] := mover[0]` (target facing := current facing: a turn in progress stops at the facing it has);
2. if `mover+0x80` (the reserved cell, u16) != 0 **and the unit is at a cell centre** (`FUN_00551383`) **and** the reserved cell
   != the unit's own cell: `FUN_00558b75(pf, unit)` = restamp the footprint on the own cell (release the reservation).
   Mid-step the reservation is **kept** (released by the step end);
3. `brain+0x14 = FUN_0056ac5b(unit)` (default range), `brain+0x60 = 0`, `mover+0x7c = 0`, `unit+0x54 (state) = 0`.

The step itself is never aborted: the Brain low-level order `brain+9 == 3` ("step in progress") is not touched, and the Brain
tick (`FUN_0056dca2`, asm `0x56df83`) keeps calling `FUN_00555b38` for it every tick, sets state 1 and, **when the unit is at a
centre afterwards, clears `brain+9` and sets state 0 without starting anything else that tick.**

Timeline for a move order arriving in tick T:
| Unit at the start of T | What happens |
|---|---|
| idle at a centre (`brain+9 == 0`) | drain: cancel + order 1/mode 1. Same tick, Brain mode 1: `0x56e4ac` -> `0x555411`: **static plan from the current cell, first step starts in T** (simulation §4.2). |
| mid-step | the old step finishes at its normal tick (position and facing keep going, the reservation of the entered cell stays). On the tick of the snap to the centre: `brain+9 = 0`, state 0, **no new step**. Tick T+k+1: mode 1 -> `0x56e4ac`: the static plan is made from the **new** cell (forced when `mover+0x74 != dest`: `mover+9 = 0xff`; if the destination equals the old one the old static list is reused). |
| turning in place (mode 10 / turn ticks) | `mover[1] := mover[0]` ends the turn at once; mode becomes 1 in the same call; the step starts the same tick (a centre, so no mid-step wait). |
| order and step end in the same tick | commands are drained first; the step end of T happens in the creature tick of T; so the new order starts walking in T+1 (above). |

Discard of the old plans: the **dynamic** list dies at every step end anyway (`FUN_00555b38`); the **static** list is replaced at
the first centre tick after the order if `mover+0x74 != dest` or `mover+9 > StaticRefreshRate`
(`FUN_00555411` step 2), otherwise it is trimmed on the way. `mover+0x98` (event flag) and `mover+0x90` are reset by the order.

## 4. Groups: formation, speed, the group pass

### 4.1 Formation mode (the player option) and the centroid

- Client option `[GameOptions] Formation` (default 1; the key `Ctrl+F` cycles it `0 -> 1 -> 2 -> 0` with `FUN_0041f040` and shows
  `main.txt` `0x61 + value`: 0 "Formation is Off", 1 "Formation set to Auto", 2 "Formation is On") is sent with cmd `0x46`
  sub-code 2 (`FUN_0041a617`); the server maps it at `0x4f688c`-`0x4f68f8`: **client 0 -> server 0 (off), 1 -> 2 (auto), 2 -> 1 (on)**
  and stores it in `player+0x34 -> +0x1f` (`FUN_005737ba`; the record ctor `0x5691c8` defaults to 2 = auto, so AI players are
  auto; `FUN_005737db` (toggle) has no caller).
- `FUN_0056f850(group)`: `n` = member count (byte, `FUN_0044fc20`; 0 -> returns 0); `sx = sum of the 16-bit x positions`
  (`FUN_0054ff5b`, cell*256 + sub) and `sy` likewise, `cx16 = sx / n`, `cy16 = sy / n` (**unsigned truncating division of the
  sums**); centroid cell `(cx16 >> 8, cy16 >> 8)`. It also stores in the group record `+0x24 = cy16<<16 | cx16`, `+0x28` = packed
  centroid cell, `+0x2a` = max Chebyshev distance of a member from the centroid cell, `+0x2b` = max `member+0xa5`, `+0x2c` = max
  of (distance + `+0xa5`). Members may be mid-step: the sub-cell offset counts.
- Mode `auto` keeps the formation only if **every member is within Chebyshev distance 2** (`server+0xa724`) of the centroid
  cell; `on` always; `off` never.
- Formation target of member `u`: `(clickX + (u.cellX - cx), clickY + (u.cellY - cy))`, then the §3.3 wrap/clamp. This is a
  rigid translation of the whole group shape; **there is no nearest-free-cell search, no ring order and no leader**: the first
  id only decides which player's group list receives the group.

### 4.2 Without formation (`off`, or `auto` with a spread-out group)

All members get the same destination cell T. There is no spreading algorithm: units go to T; the first to arrive occupies it
and the rest are handled by the pathfinder fallbacks already documented ([simulation §7.1, §7.2, §7.4](simulation.md)): the dynamic
hop plan to a blocked T leaves `field[T]` unlabelled, `FUN_005585f4` (radius 8) picks the cheapest labelled cell of the first
non-empty ring around T, and the static plan of an unreachable T uses the radius `dist>>2 + 4` fallback. Units that cannot
improve end with the event flag (`mover+0x98`) -> `FUN_0056dc24` (cancel + order `0xc`), or are stopped by the group pass below.
How many fit is therefore not a number: one per free cell the fallback finds, in creature-list order of the planning (not packet order).

### 4.3 Group speed `+0x44`

`group.record+0x44` = minimum of `(byte)(s16 unit+0x8c)` over the members, start value 250, **written only when the formation is
active** (otherwise it stays at its initial 0 of the fresh group). `FUN_0055915a(unit)`: base speed =
`group.record+0x44` if non-zero else `s16 unit+0x8c`; it feeds `FUN_00559195` (simulation §4.1). The value is fixed for the group's life
(Haste/Slow after the order do not change it); the group itself ends when emptied and deleted by the next command's `FUN_0052b06f`.
`FUN_00570e22` (which would zero it) has no caller. The pass also sets `brain+0x6c := 1` for every non-stopped member of such a group
(`0x5732d3`); nothing reads that field (CONFIRMED scan), so formation changes nothing there beyond the speed base.

### 4.4 The group pass (`FUN_0056fe4d`, tick & 15 == 6) (CONFIRMED)

Called at the top of the server step when the tick counter *before* the increment satisfies `& 15 == 6` (before that step's
command drain), with `this = 0x66832c`, argument `0x68d2c4` (players). For each player (`FUN_0057b120/53da40`) `FUN_00570087`
visits each of the player's groups; `FUN_005700f3(group)` first sets the group order to `0xff` if the group is empty (`FUN_0057375a`),
then dispatches on the **group order** (`record+0x20`, table `0x570232`, bytes `0x57025a`):
0 -> run `FUN_0056fe34(unit)` for every member (= `FUN_00569321`, the per-unit order executor, via `FUN_005692d5`);
1 -> `57275f`; 2 -> `572d57`; 3 -> `57309d`; **4 -> `FUN_00573198(group, record+0xa)`**; 5 -> `572e1e`; 0x11 `572ec4`; 0x12 `5728fa`;
0x13 `57311c`; 0xff -> `573159`. Afterwards, **whatever the group order** (all values, also `0xff`, fall through to `0x570220`), `FUN_0057377d` runs `FUN_00573713` on every member (§4.5).

**`FUN_00573198` (group order 4 = move), for each member `u` in list order:**
```
(c = FUN_0056f850(group), unused)
if u.cell == u.brain+0xa and u at a centre and u.brain+0x50 == 0:   FUN_0056dbc6(u); u.mover+0x90 = 0       # ARRIVED -> stop
elif u.mover+0x90 != 0 and u.mover+0x76 == u.cell:                  FUN_0056dbc6(u); u.mover+0x90 = 0       # arrived at the end of its plan (fallback cell)
if u.brain+0x50 != 0:                                               FUN_0056afac(u, 0)                      # stopped units: guard scan (FUN_0056a1fb)
else:
      if group.record+0x44 != 0: u.brain+0x6c = 1                   # write-only, see unit-struct 8.1
      FUN_0056c8af(u, u.brain+0xa)                                  # brain mode := 1, dest := brain+0xa   (RESTARTS parked units;
                                                                    #  NO test of the unit's order: also a unit the failure turned into 0xc)
      if FUN_0055cd50(pf, u, groupTarget) == 0                      # the size x size footprint at the group target is not free (live layer, unit's mask)
         and u.brain+0xa == groupTarget and cheb(u.cell, groupTarget) < 2:
            FUN_0056a1fb(u)                                         # stand/guard scan: sets mode 0 (human non-ranged, FUN_0056b025) -> the unit stops next to a blocked target
```
`FUN_0056dbc6(u)` = cancel + `FUN_0056dba1` (cancel again, then **order := 0xc, anchor = own cell, mode 0** via `FUN_0056d52b`) + `brain+0x50 := 1`.

So: **arrival ends order 1 at the next group pass (up to 16 ticks later), by converting the unit to order 0xc (stand/guard)**;
until then the unit stands with order 1, mode 1, state 0/1 and the "arrived" flag set. A unit parked by the blocker rule
(simulation §7.4: mode 0/10) is **restarted every 16 ticks** by `FUN_0056c8af` (this resolves simulation open question 5: no "parked
for good"; it waits for the pass, which re-runs the blocker verdict). The same rule never restarts a unit whose group order is not 4
(swarm = 5 is handled by `572e1e`, not decoded). **A failed unit is restarted too:** the failure (§7) leaves order `0xc` with `brain+0x50 == 0`,
so every 16 ticks the pass sets its Brain mode back to 1 with the old `brain+0xa` and it plans again (a unit that failed standing on the tail
of its plan has `mover+0x90 = 1` and is stopped by the second test instead). Under order `0xc` a new failure only sets mode 0 (§7).

### 4.5 The post step `FUN_00573713`: retreat and withdraw

CONFIRMED (asm `0x573713`-`0x573757`, `0x56cb0c`, `0x56cd11`, `0x56c9bc`, `0x56ce0f`, `0x567a16`, `0x54ec6a`, `0x558b92`, `0x56f765`):
```
FUN_00573713(unit):                          # after the group's handler, for every member of every group, every 16 ticks
    if   HP(s16 unit+0x94) <= brain+0x44 and enemies(unit, mover+8 + 5 = 10)  nonempty:  FUN_0056c9bc(unit)   # "wimpy" retreat
    elif HP(s16 unit+0x94) <= brain+0x40 and enemies(unit, 2)                  nonempty:  FUN_0056ce0f(unit)   # "withdraw"
enemies(u, r):  54ec6a = all objects in the cells within Chebyshev r of u's cell (cell-table bit 0x20, occupant 551edb),
                then 567a16 deletes the ones the owner is not at war with (relation matrix server+0xa8bc,
                [owner.index*0x46 + 8 + other.index] & 1 == 0), and keeps a hidden enemy (obj+0x144 & 0x1000) only when some
                member of u's group detects it (0x556dcd level <= that member's brain+0x71)
56c9bc / 56ce0f, units WITHOUT a spell list (unit+0x140 == 0; INFERRED = spells/abilities):
    live = enemies with HP > 0 (56c9bc; 56ce0f needs only a non-empty list)
    if live:  p = 56f765(list) = mean of the 16-bit positions (packed y<<16 | x)
              flee = 558b92(pf, u, p, 3): the point 3 cells beyond u on the ray p -> u along the dominant axis (x87 float32 slope),
                     per axis clamped to [8, size-9]
              FUN_0056c8af(u, flee)             # brain mode := 1, brain+0xa := flee   (the unit's order is NOT touched)
    else:     FUN_0056afac(u, 0)                # guard scan
units WITH a spell list: a cast of spell kind 0x17 (FUN_0056bb0d, FUN_0056969c / FUN_0056c72b / FUN_0056cb8c), else the same flee
```
**Effect on a move group.** The handler `FUN_00573198` restarts the unit towards `brain+0xa` first, then `FUN_00573713` overwrites mode and
`brain+0xa` with the flee cell in the same pass: the unit leaves its route for a cell 3 cells away from the hostiles, the pass after that
sees `cell == brain+0xa`, ends the order (`FUN_0056dbc6`: order 0xc, stopped), and the group target is never resumed. The blocked-target rule
also stops matching (`brain+0xa != group target`). While hostiles stay near and the HP test holds the unit flees again every 16 ticks.

**Who can trigger it.** Thresholds (unit-struct §8.1): monsters carry data.bin p34/p35 (`Orc_Bow` withdraw 90 >= hp_max 60: always true, so an
archer withdraws from any hostile within 2 cells; `Goblin_Pike` wimpy 10 of 40 HP); **human-player units have 0 in both** (their templates have no
such parameters and the retreat-mode message writes 0 for `+0x40`), and an HP > 0 unit never satisfies `HP <= 0`. A human unit can trigger only
after the player cycles the retreat mode (`Ctrl+W`, registry `WimpyMode`, default 0): then `+0x44 = maxHP * 10 / 100` or `* 30 / 100` for the
units existing at that moment (the client resends the stored mode at game start). Player-owned monsters created later keep their data.bin values. So in
single player with the default option a human unit's move is never overridden; AI-owned units (phase I) and the retreat option are the only users.


## 5. Stop

There is no "Stop" button or message; four stand-type commands cancel a move (README names in brackets):

| Cmd | Key | Routine | Per-unit order | Group order | Effect on a walking unit |
|---|---|---|---|---|---|
| `0x17` | `G` (guard, button 3) | `FUN_005709d9` | `FUN_0056d4ba`: order `0xb`, anchor = `mover+6` (the cell being entered) when off-centre else the own cell, brain mode 0 | 1 (+ limit bytes `record+0x2d/+0x38/+0x39`) | finishes the current step (stands on the next cell), plans dropped (mode 0) |
| `0x18` | `T` (stand ground, button 7) | `FUN_00570b8b` | `FUN_0056d52b`: order `0xc`, anchor = own cell (`FUN_0054ff9e`), mode 0 | 3 | same: step finishes, no further plan; guard scan afterwards |
| `0x12` | `L` (stand still) | `FUN_00570bde` | `FUN_0056d572`: order `0x17`, anchor own cell | `0x13` | same |
| `0x14` | `R` (retreat, button 8) | `FUN_00570c31` | `FUN_0056da4f`: order `0x16` | 0 | same; executor `56c9bc` |

All first run `FUN_00570e83` and the unit's cancel (§3.4): `brain` mode set to 0, state 0, target facing = facing; the in-progress step
runs to its centre (Brain order 3); the static list/`mover+0x74` stay (harmless: a later move to the same cell reuses the remaining static path).
`FUN_0056dba1` (cancel + order `0xc`) is the internal "stop" used by failure (`mover+0x98`, `FUN_0056dc24`, which leaves `brain+0x50` at 0) and
by `FUN_0056dbc6` (arrival and the group pass: the same plus `brain+0x50 := 1`).

## 6. Feedback

### 6.1 Cursor and marker
- The cursor while ordering is simply the chooser's result (`move` for a plain click; §1.3). There is no "order given" cursor state.
- **No click marker, flag or ground animation exists** (CONFIRMED for the order path: `FUN_00418bc3`, `FUN_004175c7`, the
  server order functions store nothing the client could draw; the client never stores the destination; INFERRED globally: the exe's
  `graphics\...` string table has cursors, interface bitmaps, `Global.Map\Flag*` (world map only) and `Ball.bmp` (selection bar caps),
  no marker/target sprite). The only visible reaction is the units walking, the voice, and the command-bar highlight clearing.

### 6.2 Acknowledgement voice
`FUN_0041da16(view)` picks one unit of the selection (living, HP `obj+0x104 > 0`; heroes (`obj+0x1b8 & 1`) first, then units flagged
`0x10`, then units with `obj+0x1dc` in 1..20; random pick `rand * count / 0x7fff` inside the first non-empty class: INFERRED reading of
`0x41da95`-`0x41dce0`). After a move/patrol/swarm/etc. order the picked unit's vtable method plays its voice (`move`: slot `+0x6c` =
`0x4682a6`; swarm `+0x70`, attack `+0x68`, stand `+0x78`, pickup `+0x84`). `0x4682a6`: at most once per 3000 ms per unit
(`obj+0x1bc`), random sample from the template list (`template+0x64` entries at `+0x24`), pan/volume from the unit's position relative to the
view. For the move order the call is skipped when `voice_obj+0x78 == 1` (`0x418c99`). Out of scope for now (no sound engine in the recreation yet).

### 6.3 "No way" (message `0x92`, string `0x81`)
`FUN_005052d2(1, 0, owner)` (-> `FUN_00505347`, type `0x92`, packet `0x68f610`: `+9 = 0x92`, `+7 = owner player id`, `+0xa = 1`)
is posted by the **static** planner (`FUN_0054d76e`, `0x54e1fd`/`0x54e230`) when the target was unreachable and the fallback end cell is
more than 1 cell from the target (more than 2 when the target cell is a building cell, `FUN_00559bc9`), i.e. at every static re-plan of
every affected unit (also each unit of a formation, and AI units; the message is addressed to the owner id). Client handler `0x40e21d`,
sub-code 1 (`0x40e266`): if `DAT_00622810 != 0` (**constant 1**, its only writer is `0x48128d`; so always) it shows `main.txt` line `0x81` =
**"No way"** in the message line of the view (`FUN_004021fe`, colour `0x5f17f4`, **3000 ms**). It does not change the route and plays no sound.
`main.txt` also holds `0x61`-`0x63` (formation) and `0x5e`-`0x60` (retreat mode) shown by `Ctrl+F` / `Ctrl+W`.

## 7. Other dynamic details

- **Order of a tick** (simulation §2 corrected): `server+4` is tested for `& 15` *before* `FUN_004f8521` increments it, so the group pass of "tick 6" runs at the
  top of the step whose body then sees the counter 7. Inside the body: drain commands, then creatures in creation order.
- **`FUN_00569321` ("order 1 auto-stop")** is not a per-tick executor of order 1. It is reached only through `FUN_0056fe34 -> FUN_005692d5` (group order 0
  members, once per 16 ticks) and `FUN_005692d5` is also what the computer players' branch calls. For order 1 it does what the move group handler does:
  `order == 1 and mover+0x90 and mover+0x76 == cell -> FUN_0056dbc6`. For orders 3 and 8/0x11 it stops when the target is state `0x10` (dead).
  A group-order-4 member never goes through it.
- **Failure ends the order immediately** (not at the pass): `mover+0x98` (set by `FUN_00555411`/hop planners when no path exists) is consumed at the end of the
  Brain tick (`0x56e1b0`): order 1 -> `FUN_0056dc24` (cancel + order `0xc`, **`brain+0x50` stays 0**, so the next pass restarts the unit, §4.4); any other order
  except `0xa`/`0x18` -> brain mode 0 and the auto target scan `FUN_0056ed4e` (no enemy: mode 0; mode `0xb` for computer players).
- `brain+0xb0` is not a move destination but a pending **teleport** target (cell record effect `0x17`, consumed at a centre by `FUN_0055a96c` before the mode
  runs, `0x56e024`); nothing in the exe writes the record field, so it never fires in single player (unit-struct §8.1, INFERRED).
- Right-drag scroll and edge scroll are independent of orders.

## 8. What each later phase needs

| Phase | Command | Needs | Notes |
|---|---|---|---|
| H3 (now) | `0x16` move | §1-§5 | minimap left click as `smove`, right button, groups/formation/speed, group pass restart/arrival, stop family, "No way" |
| I | `0x19` attack (`+0xe`), `0x1a` swarm (formation + group order 5), `0x1b` follow (group `570c84`), `0x1d` patrol, `0x17/0x18` guard/stand-ground executors (`56a1fb`, `569cc9`) | cursor table §1.3, hotkeys §1.4 | the `attack` cursor over a non-unit is a move |
| J | `0x21` pickup (`x, y`, `+0xe`), `0x24` use/enter (structure id), pickup cursor/town cursor conditions | `h == 0x40`, `h & 0x800` | server `0x4f54ac`, `0x4f563f`, orders 2 and 0xf |
| K | `0x1e/0x25` cast on object, `0x1f/0x26` at cell, spellbook cast branch of the chooser, F4-F12 shortcuts (`btn 9/10`) | §1.3 cast branch | |

## 9. Open questions

1. Group handlers for orders 5 (swarm `572e1e`), 1/3/0x13 (`57275f`, `57309d`, `57311c`) and the computer players' branch of the pass.
2. `FUN_00556dcd` (detection level used by `FUN_00567a16` for hidden enemies) and the spell branches of the post step (`FUN_0056bb0d` kind `0x17`, `FUN_0056cb8c`, `FUN_0056969c`).
3. `FUN_00417f31` for columns beyond the view width (minimap move order y): array overrun behaviour (§1.6).
4. Voice-unit selection `FUN_0041da16` and the per-order voice slots (class lists, exact rule).
5. Whether the AI-owned "No way" messages are dropped by the single local client (recipient filter `0x92`, `+7`).
6. `view+0x80`, `client+0xc0` exact meaning (hotkey gating), and `FUN_0041f090`/`41f0e0` neighbours of `Ctrl+F`.

## 10. Corrections to the existing docs (applied)

- [ui-layout §8](ui-layout.md#8-selection): "message `0x40e` left, `0x40f` right: INFERRED" is wrong: the release messages are
  `WM_LBUTTONUP` (view slot `+0x58`, `0x40c5d1`) and `WM_RBUTTONUP` (`0x40c53a` -> `0x405`); `0x40e/0x40f` toggle the inventory/spellbook. The open
  question "how the exe clears a selection" is answered by §1.5. §6/§8 should add: pending-mode table §1.4, the minimap move order §1.6.
- [simulation §3](simulation.md#3-unit-state-machine) "an order issuer first cancels ... order := 0": the cancel writes `brain+0x50 := 0`, not `unit+0x50`.
- [simulation §7.4](simulation.md#74-read-but-not-implemented-needs-ordersai-of-phase-i) and open questions 1, 5: `FUN_00569321` is not reached "from the type-0 group message
  only"; a move group is driven by `FUN_00573198` (§4.4), which ends the order at arrival (up to 16 ticks after the snap) and **restarts parked units every 16 ticks**.
- [unit-struct §9](unit-struct.md#9-orders-0x50) column "Per-tick executor `FUN_00569321`": it is the group-order-0 executor, run every 16 ticks; msg `0x1c` shares `0x16`'s code.
- [animation §3.6](../formats/animation.md): "group order byte `+0x44`" is only non-zero in formation (§4.3).
- [simulation §8.3](simulation.md#83-cancel-timeline-group-pass-stop-r-34-44-5-7) (and the engine): the failure stop is `FUN_0056dc24`, not `FUN_0056dbc6`: it leaves `brain+0x50` at 0, so the group pass restarts the failed unit (§4.4, §7); fixed in the engine with `Unit.mode_go`.

## VERIFY IN GAME

1. **Right button.** Select units, press `A`, right click: pending cursor returns to normal, selection stays. Right click again: selection clears. Right-drag the map: it scrolls (1 cell per 8 px, same direction as the mouse) and afterwards a right release does NOT deselect.
2. **Attack cursor over ground.** Press `A`, click on empty ground: units walk there (plain move, no attack-move). `A` + click on an enemy unit: attack. `A` + click on an enemy structure: move.
3. **Ctrl/Alt.** Ctrl+click ground: swarm cursor and swarm order; Alt+click on an enemy unit: walk, no attack; Ctrl+click on an own unit: attack your own unit.
4. **Minimap.** With units selected and no key pressed, left click in the minimap: move order (cursor `smove`); drag with the left button held: a stream of orders. Check the target row against the click (expect a wrong row, §1.6). Without a selection: camera jump. Right click: always camera.
5. **Formation.** Ten units in a line, `Ctrl+F` to Off/Auto/On, order a walk across open ground: Off = all aim at one cell (pile up), On = the shape is translated, Auto = shape only if all are within 2 cells of the centre. Group speed with a slow member in On/Auto-formed groups.
6. **Arrival delay.** Order a walk of a few cells, then watch for the "arrived" state: the unit becomes a guard (order 0xc: it reacts to enemies in range) up to 16 ticks (about 1 s) after it stops.
7. **Re-order mid-step.** Order, then re-order to the opposite side in the middle of a cell step: the unit finishes its current step (never reverses mid-cell), then turns and goes; same destination twice: no hitch.
8. **Parked units resume.** Two units head-on in a one-wide corridor: the one that waits restarts within 16 ticks if the other leaves.
9. **"No way".** Order a walk into the middle of a lake: text "No way" for about 3 s on the message line; a unit that reaches a cell next to the target (distance 1) prints nothing.
10. **Stop commands.** `G`, `T`, `L`, `R` during a walk: all finish the current step; afterwards `T`/`G` units fight enemies in range, `L` units do not.
11. **No marker.** Order a walk and look for any ground sprite at the destination (none expected).
12. **Edge wrap.** Select a wide group near the west edge, Formation On, click within 2 cells of the edge: members whose offset is larger than the click column should run to the far east edge (the `& 0xff` wrap).
13. **Failed units retry.** Order a walk into a spot where a unit ends with "No way" short of the target (a crowded corridor, a unit standing on the target): the unit stops (order 0xc) but walks on within 16 ticks whenever the way has cleared, and prints "No way" again at each failed retry; only arrival (or a new order) ends it for good.
14. **Retreat mode.** `Ctrl+W` to mode 1/2 (text `0x5f`/`0x60`), then wound a unit below 10 %/30 % of its maximum HP with enemies within 10 cells during a walk: it should turn away at the next group pass (every ~1 s) and stop 3 cells beyond its position; with mode 0 it never does (§4.5).
15. Stage B UI items: see [design spec, Stage B](../superpowers/specs/2026-10-18-click-to-move-design.md) (VERIFY IN GAME additions a-g).

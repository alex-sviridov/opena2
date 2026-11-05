# Vision and fog of war (J2)

Code: `allods2/vision.py` (sight mask, tile-bit helpers: pure, integer only), `engine/sim/vision.py` (the refresh system),
`engine/view/fog.py` (fog levels for the overlay, minimap blocks), gates in `engine/view/drawlist.py` and `engine/view/minimap.py`,
overlay in `engine/backend_pygame/render.py`. Tests `tests/test_engine_vision*.py`. Facts: CONFIRMED = read in the GOG allods2.exe with REA
(this session, sha256 in formats/README.md), INFERRED otherwise. Fog drawing itself (levels, quads, blend rows) is
[lighting §3-4.1](../mechanics/lighting.md#3-fog-levels-fun_0040403b) and is reused as is.

## 1. What the exe does (all client side)

The AI's sight flood ([ai §4.1](ai.md#41-sight-flood-fun_00552c28--fun_00552af8-confirmed)) is a different, server-side routine and never
touches the player's map knowledge. The player's fog is **client state** kept in the map's tile words (`bit 0x4000` = seen at the last refresh,
`0x8000` = explored, never cleared; `0xc000` both = in sight).

| Rule | Where | |
|---|---|---|
| Initial state: all cells 0 (never seen). Load clears only bit 13 (`& 0xdfff`); shipped maps carry no fog bits | `FUN_004a449c` `0x4a53f7`, `0x4a5cad` | CONFIRMED |
| Only the viewer's own units/structures reveal: `FUN_0041e860(owner)` tests bit 8 of the per-player word table `view+0x38`; the only writer gives bit 8 to the viewer's own entry (`0x3a`) and keeps `old & 0x68` for the rest. Allied/vision relation bit `0x10` is stored, read by nothing | `FUN_004891d8` `0x48a66b`-`0x48a733`, `FUN_0041e860` | CONFIRMED |
| Full refresh when `clock & 0x1f == 0` (clock incremented first, so the first refresh is at clock 32): clear `0x4000` on all tiles, then every object's vtable `+0x48` (`0x4000 \| 0x8000` into the 2x2 tiles of every mask cell `> 0`). View `+0xdc` (minimap dirty) set | `FUN_0040bcd8` `0x40bd37`, `FUN_0040c129` | CONFIRMED (first-refresh timing INFERRED) |
| Reveal function: needs `FUN_0041e860(owner)` and sight `s16 obj+0x10a != 0`; mask centred on cell `obj+0x38/+0x3c` + footprint half; stores the revealed cell in `obj+0xc8/+0xcc`. No test for invisibility or flying | `FUN_00460b76` | CONFIRMED |
| Units and flyers reveal only while death stage `obj+0x184 < 3` (`FUN_0046df20`); structures and projectiles reveal with no stage gate | vtable `+0x48` of `0x5cd5d0`, `0x5cd660`, `0x5cd520` | CONFIRMED |
| A moving own unit reveals at once (not waiting for the 32-tick refresh) when its position differs from `obj+0xc8/+0xcc` (`FUN_00460ae0`, vtable `+0x44`, tested when `obj+0x54 & 0x1f == 0x10` and `obj+0x58 & 0x1f == 0x10`, i.e. at a cell centre) | `FUN_00460ae0` | CONFIRMED (centre test = INFERRED reading of the pixel fields) |
| Sight value `obj+0x10a` (8.8): units = server `+0xa4` (humans `((mind + reaction) / 25 + 4) * 256` + bonus, monsters `scan << 8`), Light adds `(L/30 + 1) << 8`, Darkness subtracts; structures = `data.bin structures scanRange << 8`; projectiles 0 | `0x469b60`, `0x40fb08`, `0x4a49f0`, `0x4a5b85` | CONFIRMED (projectile 0 INFERRED) |

### 1.1 Sight mask `FUN_00403ca0` (client; formulas in [animation §1.6](../formats/animation.md#16-visibility-gates))

Same shape as the server flood but its own routine: 41 x 41 window, `cost(dx, dy)` and parent step tables, `M(0,0) = (sight >> 1) + 64` (sight is
the 8.8 word, so a fractional human sight counts; the server flood uses `(scan << 7) + 64`), rings 1..19 (stop after a ring with no `M >= 1`),
`M(c) = M(pred c) - cost(c) - (H(c) - H(unit))`, only cells with `7 <= x < w - 7`, `7 <= y < h - 7` (server flood: 8..w-9). A cell is visible when `M > 0`.
Shape: a rounded square/octagon-like blob (cost 128 straight, 181 diagonal), no facing; **height blocks softly** (each height unit costs one
point, uphill shortens, downhill lengthens), no hard line-of-sight test and no object blocking. Engine: `vision.sight_mask`, integer math only
(`int(sqrt) ` tables built once like `ai._build_tables`, `int` arithmetic after), results cached per `(x, y, sight)`.

## 2. What is hidden in each state

Cell fog level ([lighting §3](../mechanics/lighting.md)): 0 seen (`0xc000`), 8 explored (`0x8000`), 16 never seen. The overlay darkens
everything already drawn (terrain, objects, units, items, **projectiles and spell effects**, bars): level 16 black, level 8 halves each pixel,
blended per vertex (soft edges half a cell down-right). The fog pass runs after all object layers and selection bars and before the HUD (CONFIRMED).

Per-object visibility `S` (`obj+0x7c`, recomputed every view tick; CONFIRMED `FUN_00468762`, `FUN_00461460`, `FUN_004609ca`):

| Object | `S` | Drawn | Pickable |
|---|---|---|---|
| Unit/flyer of the viewer | 0 | yes | yes |
| Other unit/flyer | 0 iff any of the 4 tiles `(x,y) (x+1,y) (x,y+1) (x+1,y+1)` of its first cell has `0xc000`, else 1 | **only when S = 0**, shadow too (nothing dimmed: it simply vanishes); with Invisibility only if the owner is the viewer | only drawn ones (pick rects are registered by the draw). A **selected** foreign unit whose S becomes 1 is deselected at once (`obj+0x80 := 0`, redraw flag `+0x114`; engine `sim/vision._drop_hidden_selection`) |
| Corpse (layer `+0x9c`; a dead unit is still the same `CUnit`) | the unit rule, nothing corpse-specific: cell test, own corpses always (CONFIRMED `FUN_00468762`; both layer arrays `+0x98`/`+0x9c` are drawn by the same loops of `FUN_00406f43` (`0x4087c2`-`0x409de8`) through vtable `+0x28`, and the unit draw `FUN_004632a1` is the S = 0 one). **Not remembered**: S is recomputed every tick, so a body in an explored-only cell is gone and reappears when sight returns. Unit flag `+0x1b8 & 0x80` (set / cleared by client message `0x69`/`0x74`, byte `msg+9 == 't'`) forces S = 1 for **every** owner, own too: such a unit is never drawn or picked (it is no corpse flag) | S = 0 | no |
| Structure of the viewer | 0 | yes | yes |
| Other structure | footprint scan: any cell with `0xc000` -> 0; else a cell with exactly `0x8000` -> 1; else 2 | S < 2 (explored: frozen animation, behind the half fog); never seen: not drawn | only S = 0 |
| Ground item pile | - | only when the 4 corner tiles OR to exactly `0xc000` | the cursor's item flag `0x40` needs the same test; `0x400` (fogged) is the complement |
| Map objects (trees, rocks) | - | always (the overlay darkens them); animation only on `0xc000` cells | - |
| Projectiles, spell effects | - | always drawn, hidden only by the overlay (level 16 black) | - |
| Own selected unit | - | bars when selected; the show-all-HP bars need S = 0 | - |

Targeting by click: rectangle picking, hover and the order cursor all work from the registered pick rects, so **a hostile unit in fog cannot be
hovered, selected, attacked or cast on by click** (CONFIRMED `FUN_004180c6`, `FUN_00417986` which also demands `owner == viewer`).
Correction of [combat §15](combat.md): the click on a *fogged cell* still becomes a move; only units/structures are hidden. The server has
no sight test on player orders (its sight flood has only AI callers: `0x553329`, `0x56d6b7`); the engine keeps that (the view filters, the
sim does not).

## 3. Minimap (`FUN_004ac414`)

Per cell block (`1 << k` pixels), OR of the four tile bits: no `0xc000` bit at all -> the block shows the panel background pixel
(`CrystalR.bmp`, `DAT_00626be0`); exactly `0x8000` -> `((panel >> 1) & M) + ((map >> 1) & M)` (565: `M = 0x7bef`, per channel `floor(a/2) + floor(b/2)`);
otherwise the map pixel. Rebuilt only when `view+0xdc` is set (refresh or a reveal). The light pass `0x4ac030`-`0x4ac413` is the image build
([rendering §12](rendering.md#12-minimap)), not fog; the fog background surface `DAT_00626be0` is the panel bitmap. Dots (vtable `+0x34`, drawn after the image): units (stage <= 1, flag `0x80` clear, not invisible
unless own; `0x465f3f`) and structures/bridges (`0x46213e`, rectangle of the footprint) only when the 4 tiles at their cell OR to `0xc000`; **no ownership gate** (allies and enemies get dots when seen, own units
with sight 0 get none; the engine draws structure dots too, `minimap.draw_structure_dots`); colour palette entry 164 of the owner's row. Minimap right-click orders have no fog test.

## 4. Options, cheats, saves

* No fog option in the GOG exe (no "fog" string among the options). `#show map` / `#hide map` (cheat level `> 0x32`, message `0xaa` value 1/0):
  1 sets global `0x62280c` and ORs `0xc000` into all tiles (refresh skipped while set); 0 clears the flag only (tiles keep `0x8000`: everything explored).
  Value 2 only calls `FUN_0041e3f0(0x430, 0)`, a `PostMessage` of window message `0x430` to the client's window (`this+0x1c`): no fog effect (CONFIRMED).
  CONFIRMED. Engine: `vision.reveal_all(world)`, `vision.hide_all(world)` (debug keys, not a cheat chat).
* Saves: `game%d.sav` section `Fog` (`FirstState`, `Data` = run lengths of bit `0x8000` over all tiles), written `0x48e537`-`0x48e629`, read
  `0x48d699`-`0x48d795` only with `InBattle`; bit `0x4000` is recomputed at the next refresh. The engine saves/loads when phase K builds save/load (state: `World.fog`).
* DECISION: `engine run` draws fog (the game always does); `--no-fog` switches it off. `engine screenshot`/world defaults stay fog-free so the existing
  goldens keep their meaning; `--fog` opts in. `Simulation(world, vision=True)` after `vision.enable(world, viewer)`.

## 5. Engine design

* Status: built (J2). Update cost on a 256 x 256 map with 24 own units: 24 cold masks about 11 ms once (cached per `(x, y, sight)`), a full refresh about 4 ms warm (`tests/test_engine_vision_view.py`, limit 15 ms).
* DECISION: the very first `vision_system` pass reveals every own observer at once (no stored cell yet = a changed cell, the exe's `+0xc8/+0xcc` start unequal), instead of waiting for tick 32; VERIFY IN GAME 1 decides.
* Not built: save/load of `World.fog` (needs the phase K writers), a debug key for `reveal_all` / `hide_all`, frozen animation of explored structures follows `animate=False` only.
* `World.fog`: `(h, w) uint16` tile words (bit constants `FOG_SEEN = 0x4000`, `FOG_EXPLORED = 0x8000`), `None` = no fog (everything visible);
  `World.fog_viewer` = player id (1); `World.fog_rev` counter (bumped on any change, minimap/overlay caches key on it); entities' last revealed cell in
  `vision` side table `world.fog_cells` (`obj+0xc8/+0xcc`). `dump()` adds `"fog"` (a crc of the array) only when on.
* `vision_system(world, commands)` runs after movement (a reveal happens in the same tick the unit reaches the cell centre in the exe; the exe's view clock
  is our tick, J1 convention): (1) per own living unit with stage < 3 and `sight != 0` whose cell differs from the stored one: reveal now; (2) when
  `(tick + 1) & 31 == 0`: clear `0x4000` everywhere, reveal for every own unit and own structure with `scanRange != 0`. Integer math only, no RNG,
  nothing else reads the grid, so the sim hash is unchanged except the optional `fog` entry.
* View: `fog.object_state(world, ent)` and `fog.cell_visible(world, x, y)` implement section 2; `drawlist` skips hidden units/shadows/items/structures before it
  registers pick rects (so picking, hover and `SelectionInput` need no change); `fog.levels(world, camera)` builds the overlay input for
  `lighting.draw_fog`; `minimap.apply_fog` per section 3.
* Backend: `draw_frame` packs the frame to 16 bit, `draw_fog`, unpacks (the exe renders at 16 bit, 565 assumed) after the items and before the HUD;
  skipped when `world.fog is None`.

## VERIFY IN GAME

1. First refresh at clock 32: is the start screen black for about a second, or do the hero's cells show at once (maybe revealed by the move path or a mission-start call)?
2. A unit that stands still: does it reveal only at the 32-tick refresh? Does a walking hero reveal every cell (the `0x1f == 0x10` centre test) or only after a step?
3. Sight radius of the hero (about `(mind + reaction)/25 + 4` cells) and the effect of a hill between hero and target; Light/Darkness spells.
4. Explored-but-unseen structures: drawn frozen at half brightness and not clickable; never-seen ones absent.
5. Corpses and item piles in explored-only cells: gone (both rules are exact, CONFIRMED).
6. A projectile or spell effect flying through fog: visible at all? (exe: drawn, then darkened.)
7. Monsters' dots on the minimap appear only while seen; the explored area is a 50 % mix with the panel picture, unseen area the panel picture.
8. The cheat availability in single player (message `0xaa` value 2 is only a window-message post, section 4).

## Answered round (REA, GOG exe)

* **Flying damage numbers in fog (CONFIRMED)**: the HP handler of message `0x73` (`0x4128c6`) tests only the option `view+0xabc` and the HP drop; it creates the number whatever the fog says. The per-number routine `FUN_0045c6cd` (called by the list walker `FUN_0045c756` from the view draw `0x40a913`) first drops the number after 1000 ms of wall time, then draws nothing while the unit's `+0x7c` (the visibility `S` above) is non-zero, so a number over a hidden unit lives its full second invisible and reappears if the unit becomes visible again. Engine: `window.floating_entries` skips hidden units.
* **Vtable `+0x44` of the unit class** (`0x5cd5d0` slot 17 = `FUN_0046def0`): when the death stage byte `+0x184` is < 3, `FUN_00460ae0` (reveal the unit's sight mask at once). CONFIRMED callers: the unit tick `FUN_0046617c` at `0x466291` (the branch that stores `+0x34 := -1`) and `0x466d7f` (after `+0xa8` is copied); `0x4608d2` is the shim `FUN_004608c3` (the vtable `+0x48` of the full refresh: reveal, return 1), and `0x45ab87` belongs to a sound class, not to units.
* **Per-player word bits `0x20` / `0x40` (CONFIRMED)** (table `view+0x38`, `FUN_0041e470`): the server relation message (`FUN_004891d8` `0x48a66b`) keeps `old & 0x68` and rebuilds the rest; the client relation handler (`0x4141a0`-`0x4146xx`) compares the old and new words and posts message lines through `FUN_0041f350` (`main.txt`): bit `0x20` = "alliance announced" (lines `0x8e` / `0x8f` "Player ... is now in alliance with you", `0x90` / `0x91` "is no longer in alliance with you"), bit `0x40` = "war announced" (`0x94` / `0x95` "is now in war with you", `0x92` / `0x93` "is no longer in war with you"), bit 8 (vision, `FUN_0041e860`) announces with lines `0x46`-`0x49` of the other text table `FUN_00474733` (not read); each line also plays UI sound entry `0xf` (`FUN_0045aa2f`) with a 3000 ms message. Bits are memory of the last announced state; they gate nothing else. The engine has no player-relation change at run time, so nothing is built.
* **Client messages `0x69` / `0x74` and unit flag `0x80`**: see [rendering](rendering.md#unit-and-cell-effects) (sender `FUN_005053a8`).

## Open questions

* None open in this spec (the relation announcement lines above are not built: no run-time relation change in the engine).

# Interface frame, cursor, picking and selection (G3b): design

Date 2026-10-17. Facts and addresses: [ui-layout](../../engine/ui-layout.md) (REA, CONFIRMED / INFERRED marked there).
This spec fixes what the engine builds and the DECISIONs where the exe has no answer.

## Goal

The first full command round-trip: UI -> `SelectUnits` command -> simulation -> `world.players[p].selection` -> view
(marker, info panel). Plus the original screen layout around the map, the original cursor, and rectangle picking.
Out of scope: orders (move, attack, pickup), squads, structures as pick targets, real fonts (G3c), command bar
contents, portraits, bottom bars, fog.

## Where the user's brief and the exe differ (the exe wins)

| Brief | Exe (ui-layout.md) | Engine |
|---|---|---|
| pick by sprite pixels | **rectangle** picking: per-object `Selection` rect, topmost registered first, 3x3 mouse box (section 7) | rectangles; tests use overlapping rects |
| select own units only | a click selects **any non-structure unit** (info only if foreign); drag and Shift select own only | same; the sim rule is "all own, or exactly one foreign" |
| drag rectangle drawn | no rubber band exists | none drawn; the drag rule (> screenW*10/640 px, overlap > 10 px^2) is implemented |
| minimap inset by 8 px | flush at the column corner (W-160, 0) | exe position |
| edge scroll 4 px, 600 px/s | border test x==0, y==0, x>=W-2, y>=H-2; one whole cell per tick; panels irrelevant | exe rule |
| selection marker circle / bracket | HP bar (+ mana bar) with 4x4 end caps on the pick rect's top edge, no circle | HP bar and caps |

## Components

```
engine/ui/layout.py     Layout.for_size(w, h): named Rects + graphic paths (data table citing ui-layout.md sections)
engine/ui/cursor.py     CursorState enum, choose_cursor(CursorInput) -> CursorState (pure)
engine/ui/selection.py  SelectionInput: press/move/release -> click or drag -> SelectUnits (pure, needs a Picker)
engine/ui/scroll.py     ScrollInput: exe edge rule, whole cells per tick, border clamp
engine/ui/minimap.py    MinimapPanel placed from layout.minimap (+ exe centre (72, 82))
engine/sim/commands.py  Command, SelectUnits, CommandLog; CommandQueue stays
engine/sim/selection.py selection system: applies SelectUnits to world.players[p].selection
engine/view/pick.py     PickRect, pick_at(picks, x, y), pick_in_rect(picks, rect, own=...)
engine/view/drawlist.py unit pick rects registered in draw order (DrawList.picks); selection bars as DrawItems
engine/backend_pygame/  interface.py (panel blits), cursor.py (CursorSet frames, hide OS cursor), text.py (draw_text)
```

Import rules stay as in architecture.md: `ui` and `view` know no pygame, `view` does not import `ui` or `sim`,
the backend wires them. The UI never writes the world; it only produces `Command`s and camera / cursor state.

### Layout (`engine/ui/layout.py`)

`Rect(x, y, w, h)` (frozen, `right`, `bottom`, `contains`, `intersects`). `Layout.for_size(w, h)` accepts 640x480,
800x600, 1024x768 (`ValueError` otherwise) and returns named rects: `screen`, `viewport` (0, 0, W-160,
H//32*32), `strip_*`, `minimap`, `bar_panel`, `info_panel`, `extra_panel`, `bottom_bar`, each with the graphic
paths of ui-layout.md section 2 (`Panel(name, rect, graphics)`; `graphics` may depend on state: `bar_panel` picks Heads
or CommandBar from the selection, section 2). Values are one table, each row commented with the routine address;
there are no layout numbers elsewhere. The camera is built from `layout.viewport` size; `border = 8 cells`.
`Camera(border=...)` clamps to `[border, map - border - view]` (default 0 keeps all earlier tests valid).

### Scroll

`ScrollInput(period_ms)`: `direction(keys, mouse, screen_w, screen_h)` per ui-layout.md section 5 (mouse `None` =
outside the window = no edge scroll). `update(camera, dt_ms, keys, mouse)` accumulates frame time and moves the camera
`TILE` px per tick period (62 ms at the default speed) per active axis; the camera stays on whole cells. The old
600 px/s / 4 px zone DECISION is removed from architecture.md section 8.

### Cursor

Original cursors from `allods2.anim.load_cursor_set`. `choose_cursor` is a pure function of: mouse, screen size,
viewport contains mouse, hovered unit (or `None`), hover over an item cell, selection summary (`none`, `own(n)`,
`foreign`), whether the single selected unit is a hero (`Unit.human`), hostile flag, modifiers. G3b result
states: 8 arrows (screen border first), `default`, `select` (hover over a non-structure unit when nothing is
selected, the selection is foreign, or the hovered unit is not hostile), `pickup` (exactly one own hero selected,
hovering a cell with an item pile, ui-layout.md section 6). Remaining exe states are listed there for later phases;
with an own selection and a hostile unit / bare ground the cursor stays `default` until orders exist (DECISION).
Hot spots and frame timing come from the cursor set (wall clock ms). The backend hides the OS cursor
(`pygame.mouse.set_visible(False)`) and draws the frame at `mouse - hotspot` last, over everything.

### Commands and the log

```python
@dataclass(frozen=True)
class Command: pass                          # base

@dataclass(frozen=True)
class SelectUnits(Command):
    player_id: int
    unit_ids: tuple[int, ...]
    toggle: bool = False                      # Shift: toggle each id in the current selection
```

`Simulation.step(commands)` appends `(tick, command)` for every command it receives to `Simulation.log`
(`tick` = `world.tick` before the increment; rejected commands are logged too: the log is the *input*). Systems
receive `(world, commands)` as today; the selection system is the first and is installed by default.

Selection rules (the sim is the authority; the UI also filters, so a rejected command means a bug or a replay of a
changed world):

- Unknown ids, non-units and dead / removed ids are dropped. A command whose player does not exist is rejected.
- `toggle=False` (set): the result is accepted if **every** id is owned by the player, or it is **exactly one** unit of
  another owner (foreign, info only). Anything else (mixed, several foreign) is rejected and the selection is
  unchanged. An empty tuple clears the selection.
- `toggle=True`: only own ids are toggled, and only while the current selection is not foreign; otherwise rejected.
- Stored as `Player.selection: tuple[int, ...]` (command order, no duplicates). `World.remove_unit` drops the id from
  every selection. `World.dump()` adds a `selection` key to a player **only when it is non-empty**, so the existing
  goldens stay valid; `dump_hash` covers it.
- `Player.foreign_selection` is derived (`selection` non-empty and the first unit's owner is not the player).

### Picking (`engine/view/pick.py`, `drawlist.py`)

Each drawn unit registers one `PickRect(entity, dep, x1, y1, x2, y2)`: the unit type's `SelectionX1..Y2` offset by
`(px - CenterX, py - CenterY - z - alt)` (the same anchor, ground height and flyer altitude the sprite uses;
mirrored frames are not flipped: INFERRED, the exe's formula has no mirror term). Registration order = draw order
(sort by the sprite's depth key); units whose stage is dying or dead are not registered (no death stage yet: all
units register). `DrawList.picks` holds them in that order.

- `pick_at(picks, x, y)`: the last pick whose rect intersects the box `(x-1, y-1, x+1, y+1)` (half-open), or `None`.
- `pick_in_rect(picks, rect, min_area=11)`: all picks whose intersection area with `rect` is greater than 10.
- Coordinates are viewport pixels (viewport origin is (0, 0) in every mode).

### Selection input (`engine/ui/selection.py`)

`SelectionInput(screen_w, picker)`: `press(x, y)` stores the corner; `release(x, y, shift)` -> `SelectUnits | None`.
Drag when the corner distance exceeds `T = screen_w * 10 // 640` in x or y, else click. Click: `pick_at`; no hit or a
structure -> `None`; hit -> `SelectUnits(player, (id,))` (set). Drag: `pick_in_rect` filtered to the player's own
units; none -> `None` (selection kept); else `SelectUnits(player, ids)`. Shift -> `toggle=True` with the same ids,
own units only. A click on a hostile unit while an own selection exists is ignored for now (it will be an attack
order, ui-layout.md section 8). Right click -> `SelectUnits(player, ())` (DECISION: the exe's way to deselect is
untraced). Only the left button over the viewport starts a selection; the minimap and panels take their own clicks.

### Marker and info panel

- Marker: for each selected unit still in the draw list, items `bar` (HP) at the pick rect's top edge: track
  `x1+4..x2-4`, 4 rows, colours and fill rule of ui-layout.md section 9, the 4x4 `Ball.bmp` caps. `DrawOptions.health_bars`
  (Ctrl+H, default off) adds the bars of all units. No mana bar and no name or squad number yet (the world has no mana,
  hero names or squads of the right kind).
- Info panel (strip graphics from the layout): with exactly one selected unit, the backend draws, via
  `text.draw_text(surface, text, x, y, colour, align)` (the single text entry point G3c replaces, pygame default font
  until then): the unit title (units.reg key until text tables exist: DECISION) at (centre x = panel.w - 88, y 0x1c);
  `HP cur/max` at (0x73, 0x36) with its label at 0x2c; the owner's player name at (6, 0xe0) (DECISION, the exe shows
  relation texts instead). No selection: nothing. Several: the count. Portrait not drawn.
- The frame blits the layout's graphics at their rects (no state except strip B / bar panel choice) over a black
  window. Pixel format: the BMP decoder of `allods2.graphics.bmp` -> RGB arrays; blits without colour key.

### CLI and loop

`engine run MAP` always shows the interface; `--size` accepts only the three modes (default 640x480). `engine
screenshot ... --interface [--select UID,...]` renders the full window (a headless frame), the old behaviour (viewport
only, parity with `render_3d`) stays when `--interface` is absent. The main loop gains: layout-driven camera,
`SelectionInput` events, `choose_cursor` each frame, `Simulation(world, systems=[selection_system])`, `queue.put` of UI
commands, cursor draw last.

## Tests (headless, `SDL_VIDEODRIVER=dummy`)

1. Layout: each mode's rects lie inside the screen; the panels do not overlap each other or the viewport; viewport =
   (0, 0, W-160, H//32*32) and its cell size is 15x15 / 20x18 / 27x24; strips adjoin the viewport's right edge; the
   minimap rect is at (W-160, 0) with the image centre at +(72, 82); unknown sizes raise.
2. Scroll: edge rule at x==0, W-2, y==0, H-2 (and none at 1 or W-3 / inside a panel's left edge), one cell per tick
   period, border clamp, keys.
3. Cursor: border arrows (all eight), default, select, pickup, no-select cases; the table of ui-layout.md section 6 as cases.
4. Picking: synthetic `PickRect` lists; overlapping rects -> the later one wins; a point outside the top rect but inside
   the one behind picks the one behind; the 3x3 box edge cases; drag area threshold (10 vs 11 px^2); real units: the
   rect of a unit of the install lies around its sprite (skips without the install).
5. Selection: scripted command sequences on a small synthetic world and on map 10: select own, select foreign (accepted
   alone), mixed (rejected, unchanged), toggle, empty clears, removed unit leaves the selection; the log holds `(tick,
   command)`; replaying the log on a fresh world gives the same `dump_hash` and the same selection.
6. Selection input: click vs drag threshold per mode, Shift toggle, right click, miss keeps the selection.
7. Screenshot: full interface at 640x480, map 10, camera centred on a human-owned unit that is selected: golden hash in
   `tests/golden.json["interface"]` (regenerate with `tools/update_golden.py`); the text uses pygame's bundled font, so
   the golden is tied to the pinned pygame-ce version (noted in the test).

## Docs and bookkeeping

Update architecture.md (commands, command log, selection rules, layers table, section 8 scroll, main loop) and
rendering.md (cursor drawing, selection marker, picking, minimap position). Replace the INFERRED minimap position in
rendering.md section 12. Add the open questions of ui-layout.md to docs/open-questions.md. CLAUDE.md: "Known so far"
gets an Engine G3b line and `Next: G3c (fonts)`.

## Open questions

See ui-layout.md "Open questions". Engine-only: whether hover brightness (row 0) should be drawn in G3b (decided no:
it needs the light-row plumbing for the hovered unit; the cursor and the info panel already show hover).

"""Unit, monster and hero animation: which frame to draw at a given tick.

Spec: docs/formats/animation.md (part 2 layout, part 3 timing) and
docs/formats/units.md.  Frame indices come from the draw FUN_00468640
(allods2.units), phases from the unit tick FUN_0046b5ef,
action lengths from the message loop FUN_0040dac9.

Time is in game ticks (one sequence element per tick); `tick_at_ms`
converts wall time at a game speed.  Walking is distance-driven: the walk
cycle advances one element per 16 map units moved (256 units = one cell,
8 units = one screen pixel), so `move` takes the ticks per cell.

    aset = load_animation_set(64, data_dir)            # goblin
    ref = aset.frame_at("attack", 12, tick)            # facing 12 = left
    left, top = aset.placement(ref, x, y)
    aset.draw(canvas, ref, x, y)

One code path serves units, monsters and heroes; the only per-type rules
are the ones the spec records (hero dying sprites, the Dying type).
"""

import math
import os
from dataclasses import dataclass, field

from . import units as U
from .graphics import SpriteFile, load_human_palettes, load_pal_file

# FUN_00492068: ticks per second by game speed 0..8; period = 1000 // rate ms.
TICK_RATES = (8, 10, 12, 14, 16, 20, 24, 28, 32)
DEFAULT_SPEED = 4                       # FUN_0048750d
FACINGS = range(16)                     # obj+0x70, clockwise from screen-up
COMPASS = (8, 10, 12, 14, 0, 2, 4, 6)   # one facing per stored animated direction, front first
CELL_UNITS = 256                        # map units per cell (pos >> 8)
UNITS_PER_PIXEL = 8                     # units.md ShootOffset
MOVE_UNITS_PER_ELEMENT = 16             # odometer / 16
HERO_SPEED = 18                         # animation.md §3.4 worked example (+0x86 = 30)


def period_ms(speed=DEFAULT_SPEED):
    return 1000 // TICK_RATES[speed]


def tick_at_ms(ms, speed=DEFAULT_SPEED):
    """Ticks elapsed after `ms` milliseconds of the fixed-step loop
    (FUN_0048e7d0), ignoring its 16-tick re-base jitter."""
    return int(ms) // period_ms(speed)


def walk_ticks_per_cell(v=HERO_SPEED, diagonal=False):
    """Server walk time for one cell at speed v units/tick (FUN_00563185):
    ceil(256 / step), with step = trunc(v * 0.707) on a diagonal."""
    v = max(1, min(63, v))
    step = int(v * 0.707) if diagonal else v
    return -(-CELL_UNITS // step)


def _trunc_div(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def walk_odometer(facing, tick, ticks_per_cell, start=0):
    """Client odometer obj+0x9c after `tick + 1` ticks of walking cell after
    cell (FUN_0046b5ef case 1): each tick moves remaining // ticks_left on
    each axis and adds the truncated length of that step.  Returns
    (odometer, (x, y) moved in map units)."""
    dx, dy = U.step(facing & 0xE)
    odo, px, py = start, 0, 0
    for k in range(tick + 1):
        left = ticks_per_cell - k % ticks_per_cell
        if left == ticks_per_cell:
            rx, ry = dx * CELL_UNITS, dy * CELL_UNITS
        sx, sy = _trunc_div(rx, left), _trunc_div(ry, left)
        rx, ry = rx - sx, ry - sy
        px, py = px + sx, py + sy
        odo = int(odo + math.sqrt(sx * sx + sy * sy))
    return odo, (px, py)


@dataclass
class Action:
    """One animation of a unit type.

    phases: one element per tick (per 16 map units for `move`), each a phase
        within the action's sprite block.
    end: "loop"; "idle" (play once, then the idle state, animation.md §3.3);
        "hold" (static, or the last phase held: corpse, bones).
    clock: "tick" or "distance".
    events: name -> tick (attack: AnimationSet.attack_events).
    source: "main" or "death" (dying, corpse and bones are drawn from the
        Dying type's file).
    """
    name: str
    phases: list
    end: str = "loop"
    clock: str = "tick"
    events: dict = field(default_factory=dict)
    source: str = "main"

    @property
    def ticks(self):
        return len(self.phases)


@dataclass(frozen=True)
class FrameRef:
    """A frame to draw.  hotspot = the anchor (object position) inside the
    frame box, the same whether mirrored or not (mirroring flips the frame
    in place, animation.md §2.3).  action/phase = what is shown, which can
    differ from the action asked for after a once-action has ended."""
    source: str
    index: int
    mirrored: bool
    hotspot: tuple
    action: str
    phase: int
    events: tuple = ()


class AnimationSet:
    """Actions of a unit type and its frames.

    t: the units.reg type of the main file; td: the type whose file and
    layout give dying, corpse and bones (None: no death frames).
    sprites: {"main": SpriteFile, "death": SpriteFile}; may be filled lazily
    through `paths`.
    """

    def __init__(self, name, t, td=None, sprites=None, paths=None, palettes=None):
        self.name = name
        self.t = t
        self.td = td
        self.paths = dict(paths or {})
        self._sprites = dict(sprites or {})
        self.palettes = dict(palettes or {})
        self.actions = self._build_actions()

    # -- description ------------------------------------------------------

    @property
    def directions(self):
        """Stored animated directions: 8, or 5 with Flip (the rest mirror)."""
        return self.t.dirs

    @property
    def stand_directions(self):
        return self.t.stand_frames

    @property
    def idle_action(self):
        return "idle" if "idle" in self.actions else "stand"

    def attack_events(self, kind="attack"):
        """Event ticks of the shared attack block per action kind (§2.4):
        attack (3): impact sound at AttackDelay; shoot (7): also the
        projectile release at ShootDelay when Projectile != 0; cast (8):
        spell sound at AttackDelay, spell projectile at ShootDelay.  Delays
        at or past the sequence length never fire."""
        t = self.t
        n = len(t.sequence("Attack"))
        ev = {"impact": t.AttackDelay}
        if kind == "cast" or (kind == "shoot" and t.Projectile):
            ev["release"] = t.ShootDelay
        return {k: v for k, v in ev.items() if 0 <= v < n}

    def _build_actions(self):
        t, td = self.t, self.td
        acts = [Action("stand", [0])]
        if t.IdlePhases and t.sequence("Idle"):
            acts.append(Action("idle", t.sequence("Idle")))
        if t.MovePhases > 0 and t.sequence("Move"):
            acts.append(Action("move", t.sequence("Move"), clock="distance"))
        seq = t.sequence("Attack")
        if t.AttackPhases > 0 and seq:
            ev = self.attack_events("shoot" if t.Projectile else "attack")
            acts.append(Action("attack", seq, end="idle", events=ev))
        if td is not None and td.DyingPhases > 0:
            d = td.DyingPhases
            acts.append(Action("dying", [k // 2 for k in range(2 * d)], end="hold", source="death"))
            acts.append(Action("corpse", [d - 1], end="hold", source="death"))
            for k in range(max(td.BonePhases, 0)):
                acts.append(Action("bones%d" % (k + 1), [k], end="hold", source="death"))
        return {a.name: a for a in acts}

    # -- sprites ----------------------------------------------------------

    def sprites(self, source="main"):
        if source not in self._sprites:
            self._sprites[source] = SpriteFile.load(self.paths[source])
        return self._sprites[source]

    def overlay(self, source="main"):
        """The b.256 smoothing overlay, or None."""
        key = source + "_b"
        if key not in self._sprites:
            p = self.paths.get(key)
            self._sprites[key] = SpriteFile.load(p) if p and os.path.isfile(p) else None
        return self._sprites[key]

    # -- frame selection --------------------------------------------------

    def frame(self, action, facing, phase):
        """(source, index, mirrored) of `action` at a phase value."""
        t, td, d = self.t, self.td, facing & 0xF
        a = self.actions[action]
        if action == "stand":
            i, m = U.stand_frame(t, d)
        elif action == "idle":
            i, m = U.idle_frame(t, d, phase)
        elif action == "move":
            i, m = U.move_frame(t, d, phase)
        elif action == "attack":
            i, m = U.attack_frame(t, d, phase)
        elif action in ("dying", "corpse"):
            i, m = U.dying_frame(td, d, phase)
        else:                                   # bones<k>: death stage k + 1
            i, m = U.bones_frame(td, d, phase + 2)
        return a.source, i, m

    def ref(self, action, facing, phase, events=()):
        """FrameRef of `action` at a phase value."""
        source, i, m = self.frame(action, facing, phase)
        return FrameRef(source, i, m, self.hotspot(source, i), action, phase, tuple(events))

    def frame_at(self, action, facing, tick, *, start=0, ticks_per_cell=None):
        """The frame `action` shows on its tick `tick` (0 = first tick).

        idle: counter `start` (obj+0x9c) then +1 per tick, element
              (start + tick + 1) mod len (0x46b6ab).
        move: odometer from `start`, walking cell after cell in `facing`
              at `ticks_per_cell` (default walk_ticks_per_cell());
              element (odometer // 16) mod len.
        attack: element `tick`; past the end, the idle state with the
              counter continuing from len (§3.3).
        dying: phase tick // 2; past the end, the corpse.
        stand, corpse, bones: static.
        """
        a = self.actions[action]
        if action == "idle":
            return self.ref(action, facing, a.phases[(start + tick + 1) % a.ticks])
        if action == "move":
            if ticks_per_cell is None:
                ticks_per_cell = walk_ticks_per_cell(diagonal=bool(facing & 2))
            odo, _ = walk_odometer(facing, tick, ticks_per_cell, start)
            return self.ref(action, facing, a.phases[(odo // MOVE_UNITS_PER_ELEMENT) % a.ticks])
        if a.end == "loop":
            return self.ref(action, facing, a.phases[tick % a.ticks])
        if tick < a.ticks:
            ev = [k for k, v in a.events.items() if v == tick]
            return self.ref(action, facing, a.phases[tick], ev)
        if a.end == "idle":
            after = tick - a.ticks
            if self.idle_action == "idle":
                return self.frame_at("idle", facing, after, start=a.ticks)
            return self.ref("stand", facing, 0)
        if action == "dying":
            return self.ref("corpse", facing, self.actions["corpse"].phases[0])
        return self.ref(action, facing, a.phases[-1])

    def frames(self, action, facing):
        """Every (source, index, mirrored) the action can draw at a facing."""
        return sorted({self.frame(action, facing, p) for p in self.actions[action].phases})

    def missing_frames(self):
        """[(action, facing, source, index)] past the end of their file:
        the game draws nothing there (heroes, 0x469070)."""
        out = []
        for name in self.actions:
            for d in FACINGS:
                for source, i, _ in self.frames(name, d):
                    if i >= len(self.sprites(source)):
                        out.append((name, d, source, i))
        return out

    # -- placement and drawing --------------------------------------------

    def hotspot(self, source, index):
        """Anchor inside the frame box (units.md Placement):
        ((CenterX - Width/2) + w/2, (CenterY - Height/2) + h/2).  Uses the
        unit's own type T also for death frames; INFERRED, but every type
        and its Dying type share CenterX/Y, Width and Height in the data."""
        sf = self.sprites(source)
        if index >= len(sf):
            return (0, 0)
        return self.anchor(sf[index].width, sf[index].height)

    def anchor(self, w, h):
        """Hotspot of any w x h frame of this type (also b.256 overlays,
        which use the same formula with their own size)."""
        t = self.t
        return ((t.CenterX - t.Width // 2) + w // 2, (t.CenterY - t.Height // 2) + h // 2)

    def placement(self, ref, x, y, z=0):
        """Top-left of the frame for an object at screen (x, y)."""
        return x - ref.hotspot[0], y - ref.hotspot[1] - z

    def palette(self, source="main", player=0, variant=0):
        """RGB palette per units.md: Palette = 0 -> human.pal player colour,
        else palette<variant>.pal of the type's folder."""
        key = (source, player, variant)
        if key not in self.palettes:
            spec = self.paths.get(source + "_pal")
            if spec is None:
                return self.sprites(source).palette
            kind, files = spec
            path = files[min(variant, len(files) - 1)] if kind == "pal" else files[0]
            self.palettes[key] = (load_pal_file(path) if kind == "pal"
                                  else load_human_palettes(path)[player])
        return self.palettes[key]

    def draw(self, canvas, ref, x, y, palette=None, smoothing=True, z=0):
        """Draw a frame anchored at (x, y) the way FUN_00468640 does: the
        sprite (mirrored in place when ref.mirrored), then its b.256 overlay
        at 50 % with the main sprite's palette."""
        sf = self.sprites(ref.source)
        if ref.index >= len(sf):
            return
        pal = palette if palette is not None else self.palette(ref.source)
        left, top = self.placement(ref, x, y, z)
        canvas.draw_256(sf[ref.index], left, top, pal, mirror=ref.mirrored)
        ov = self.overlay(ref.source) if smoothing else None
        if ov is not None and ref.index < len(ov):
            o = ov[ref.index]
            ax, ay = self.anchor(o.width, o.height)
            ox, oy = x - ax, y - ay - z
            canvas.draw_256_translucent(o, ox, oy, pal, mirror=ref.mirrored)


# --------------------------------------------------------------------------
# Loading from the install
# --------------------------------------------------------------------------

def _palette_spec(t, data_dir, folder_kind=None):
    if t.Palette > 0:
        return ("pal", t.palette_paths(data_dir))
    # INFERRED for heroes: the hero folders carry their own human.pal.
    sub = folder_kind or "humans"
    return ("human", [os.path.join(data_dir, U.UNITS_DIR, sub, "human.pal")])


def _norm(p):
    return p.replace("\\", "/").lower().strip("/")


def load_animation_set(key, data_dir, types=None):
    """AnimationSet for a units.reg ID (int or digits), a hero folder
    ("heroes/swordsman", "heroes_l/archer") or a unit file / folder relative
    to graphics/units ("monsters/goblin", "humans/axeman/axeman").

    Heroes (FUN_0046f688): type from the folder name; dying, corpse and
    bones come from heroes/mage_st (type 24) or heroes_l/unarmed (type 1).
    Others: dying from the type named by Dying.
    """
    if types is None:
        types = U.load_unit_types(os.path.join(data_dir, U.UNITS_DIR, "units.reg"))
    ids = U.by_id(types)
    root = os.path.join(data_dir, U.UNITS_DIR)
    k = str(key)
    parts = _norm(k).split("/")
    if parts[0] in ("heroes", "heroes_l") and len(parts) >= 2:
        kind, folder = parts[0], parts[1]
        t = ids[U.HERO_TYPES[folder]]
        dfolder = "mage_st" if kind == "heroes" else "unarmed"
        td = ids[U.HERO_TYPES[dfolder]]
        paths = {}
        for src, f in (("main", folder), ("death", dfolder)):
            base = os.path.join(root, kind, f, "sprites")
            paths[src], paths[src + "_b"] = base + ".256", base + "b.256"
        paths["main_pal"] = paths["death_pal"] = _palette_spec(t, data_dir, kind)
        return AnimationSet("%s_%s" % (kind, folder), t, td, paths=paths)
    if k.lstrip("-").isdigit():
        t = ids[int(k)]
    else:
        want = _norm(os.path.splitext(k)[0])
        match = [t for t in types if t.file and want in (_norm(t.file),
                                                         _norm(t.file).rpartition("/")[0])]
        if not match:
            raise KeyError("no units.reg type uses %r" % key)
        t = match[0]
    if not t.file:
        raise FileNotFoundError("Unit%d (ID %d) names no reachable sprite file" % (t.index, t.id))
    td = ids.get(t.Dying)
    if td is not None and not td.file:
        td = None
    paths = {}
    for src, ty in (("main", t), ("death", td)):
        if ty is None:
            continue
        paths[src], paths[src + "_b"] = ty.sprite_paths(data_dir)
        paths[src + "_pal"] = _palette_spec(ty, data_dir)
    name = os.path.basename(os.path.dirname(t.file.replace("\\", "/"))) or t.file
    return AnimationSet(name, t, td, paths=paths)


def unit_keys(data_dir, types=None):
    """Every animation set in the install: units.reg IDs with a file, then
    the hero folders."""
    if types is None:
        types = U.load_unit_types(os.path.join(data_dir, U.UNITS_DIR, "units.reg"))
    keys = [t.id for t in types if t.file]
    root = os.path.join(data_dir, U.UNITS_DIR)
    for kind in ("heroes", "heroes_l"):
        for f in sorted(os.listdir(os.path.join(root, kind))):
            if os.path.isfile(os.path.join(root, kind, f, "sprites.256")):
                keys.append("%s/%s" % (kind, f))
    return keys


__all__ = ["Action", "AnimationSet", "COMPASS", "DEFAULT_SPEED", "FACINGS",
           "FrameRef", "TICK_RATES", "load_animation_set", "period_ms", "tick_at_ms",
           "unit_keys", "walk_odometer", "walk_ticks_per_cell"]

"""Unit types (graphics/units/units.reg) and unit animation frame indices.

Spec: docs/formats/units.md.  Parser FUN_0047f108, sprite files FUN_00480717
/ FUN_004807fd, frame selection and placement in the unit draw FUN_00468640.
"""

import os
from dataclasses import dataclass, field

from .graphics import load_human_palettes, load_pal_file
from .reg import load_reg

UNITS_DIR = "graphics/units"

# key -> (record offset, default when the unit has no Parent), FUN_0047f108
INT_FIELDS = [
    ("File", 0x0C, -1), ("Index", 0x10, -1),
    ("MovePhases", 0x14, -1), ("MoveBeginPhases", 0x18, -1),
    ("AttackPhases", 0x1C, -1), ("DyingPhases", 0x20, -1),
    ("BonePhases", 0x24, -1), ("IdlePhases", 0x28, 0),
    ("Width", 0x2C, -1), ("Height", 0x30, -1),
    ("CenterX", 0x34, -1), ("CenterY", 0x38, -1),
    ("SelectionX1", None, -1), ("SelectionY1", None, -1),
    ("SelectionX2", None, -1), ("SelectionY2", None, -1),
    ("Dying", 0x94, 0), ("Palette", 0x98, 0), ("Flip", 0x128, 0),
    ("TileSize", 0xF0, 1), ("Projectile", 0xF4, 0),
    ("ShootDelay", 0x11C, 0), ("AttackDelay", 0x120, 0), ("Z", 0x124, 0),
]
ARRAY_FIELDS = ["Sound", "ShootOffset", "MoveAnimTime", "MoveAnimFrame",
                "IdleAnimTime", "IdleAnimFrame", "AttackAnimTime", "AttackAnimFrame"]
STRING_FIELDS = ["DescText", "InfoPicture"]


@dataclass
class UnitType:
    index: int                      # n in "Unit<n>"
    id: int                         # "ID"
    parent: int = -1                # parent unit ID
    values: dict = field(default_factory=dict)
    file: str = ""                  # "Files/File<File>" (may be "" when not found)

    def __getattr__(self, name):
        try:
            return self.__dict__["values"][name]
        except KeyError:
            raise AttributeError(name)

    @property
    def stand_frames(self):
        return 9 if self.Flip else 16

    @property
    def dirs(self):
        return 5 if self.Flip else 8

    def sequence(self, name):
        """Per-tick frame list of Move/Idle/Attack (see expand_sequence)."""
        return expand_sequence(self.values[name + "AnimTime"], self.values[name + "AnimFrame"])

    def sprite_paths(self, data_dir):
        base = os.path.join(data_dir, UNITS_DIR, self.file.replace("\\", "/"))
        return base + ".256", base + "b.256"

    def palette_paths(self, data_dir):
        """palette.pal, palette2.pal, ... in the sprite's folder (Palette > 0)."""
        folder = os.path.dirname(self.sprite_paths(data_dir)[0])
        return [os.path.join(folder, "palette%s.pal" % ("" if k == 0 else k + 1))
                for k in range(self.Palette)]

    def palette_spec(self, data_dir):
        """("pal", [palette<N>.pal]) when Palette > 0, else ("human",
        [human.pal]).  The exe opens only graphics\\units\\humans\\human.pal
        (units.reg loader 0x480380), also for heroes; heroes*/human.pal is
        never read."""
        if self.Palette > 0:
            return "pal", self.palette_paths(data_dir)
        return "human", [human_pal_path(data_dir)]

    def palette(self, data_dir, player=0, variant=0):
        """RGB palette per units.md: human.pal player colour (Palette = 0),
        else palette<variant>.pal of the type's folder."""
        return load_palette_spec(self.palette_spec(data_dir), player, variant)


def human_pal_path(data_dir):
    return os.path.join(data_dir, UNITS_DIR, "humans", "human.pal")


def load_palette_spec(spec, player=0, variant=0):
    kind, files = spec
    if kind == "pal":
        return load_pal_file(files[min(variant, len(files) - 1)])
    return load_human_palettes(files[0])[player]


def expand_sequence(times, frames):
    """FUN_0047f108: each (time, frame) pair adds `frame` `time` times."""
    return [f for t, f in zip(times or [], frames or []) for _ in range(t)]


def load_unit_types(path):
    """All Unit<n> records with Parent inheritance as the game builds them.
    Parent is a unit ID; ints default to the parent's value, arrays and
    strings are taken from the parent only when the child has none."""
    reg = load_reg(path)
    count = reg.get("Global/UnitCount", 0)
    files = reg["Files"]
    types, by_id = [], {}
    for n in range(count):
        sec = "Unit%d" % n
        uid = reg.get(sec + "/ID", -1)
        parent_id = reg.get(sec + "/Parent", -1)
        parent = by_id.get(parent_id) if parent_id != -1 else None
        vals = {}
        for key, _, default in INT_FIELDS:
            base = parent.values[key] if parent else default
            vals[key] = reg.get(sec + "/" + key, base)
        for key in ARRAY_FIELDS + STRING_FIELDS:
            own = reg.get(sec + "/" + key)
            if not own and parent:
                own = parent.values[key]
            vals[key] = own if own is not None else ([] if key in ARRAY_FIELDS else "")
        t = UnitType(n, uid, parent_id, vals)
        t.file = files.get("File%d" % vals["File"], "") or ""
        types.append(t)
        by_id[uid] = t
    return types


def unit_types(data_dir):
    """load_unit_types of the install's graphics/units/units.reg."""
    return load_unit_types(os.path.join(data_dir, UNITS_DIR, "units.reg"))


def by_id(types):
    return {t.id: t for t in types}


# --------------------------------------------------------------------------
# Directions.  The object's facing d (+0x70) is 0..15, clockwise from
# north (screen up): 0 up, 4 right, 8 down, 12 left.  Move steps per facing
# from the tables 0x6023b0 / 0x6023f0 (used by msg 0x6b): even d only.
# The sprite order starts at d = 8 (front view).  FUN_00468640.
# --------------------------------------------------------------------------

STEP = {0: (0, -1), 2: (1, -1), 4: (1, 0), 6: (1, 1),
        8: (0, 1), 10: (-1, 1), 12: (-1, 0), 14: (-1, -1)}


def step(d):
    """(dx, dy) in cells of a move with facing d; odd d give (0, 0)."""
    return STEP.get(d & 0xF, (0, 0))


def dir16(d, flip):
    """Stand frames: (index, mirrored).  With Flip, 9..15 mirror 7..1."""
    i = (d - 8) & 0xF
    if flip and i > 8:
        return 16 - i, True
    return i, False


def dir8(d, flip):
    """Animated states: (index, mirrored), 8 directions or 5 with Flip."""
    i = ((d - 8) & 0xE) >> 1
    if flip and i > 4:
        return 8 - i, True
    return i, False


# --------------------------------------------------------------------------
# Frame index per state, FUN_00468640.  Block order in the file:
#   stand (16 | 9) | move (Begin+Move)·dirs | attack·dirs | dying·dirs |
#   bones / idle ·dirs
# --------------------------------------------------------------------------

def _mb(t):
    return t.MovePhases + t.MoveBeginPhases


def stand_frame(t, d):
    return dir16(d, t.Flip)


def move_frame(t, d, phase):
    """State 1: phase = current MoveAnim sequence value (after the Begin phases)."""
    i, m = dir8(d, t.Flip)
    return t.stand_frames + i * _mb(t) + t.MoveBeginPhases + phase, m


def attack_frame(t, d, phase):
    """States 3, 7, 8: phase from the AttackAnim sequence."""
    i, m = dir8(d, t.Flip)
    return t.stand_frames + _mb(t) * t.dirs + i * t.AttackPhases + phase, m


def idle_frame(t, d, phase):
    """State 0 when IdlePhases != 0."""
    i, m = dir8(d, t.Flip)
    base = t.stand_frames + (_mb(t) + t.AttackPhases + t.DyingPhases) * t.dirs
    return base + i * t.IdlePhases + phase, m


def dying_frame(td, d, step):
    """State 6 with the type named by Dying: step = obj+0x74 / 2."""
    i, m = dir8(d, td.Flip)
    return td.stand_frames + (_mb(td) + td.AttackPhases) * td.dirs + i * td.DyingPhases + step, m


def corpse_frame(td, d):
    """State 0, death stage 1: the last dying phase."""
    return dying_frame(td, d, td.DyingPhases - 1)


def bones_frame(td, d, stage):
    """State 0, death stage 2..4.  The game uses IdlePhases as the direction
    stride, so with IdlePhases = 0 every direction shows direction 0."""
    i, m = dir8(d, td.Flip)
    base = td.stand_frames + (_mb(td) + td.AttackPhases + td.DyingPhases) * td.dirs
    return base + i * td.IdlePhases + stage - 2, m


def expected_frames(t):
    """Frames the blocks above need.  Dying and bones are drawn from the
    type named by Dying, so a file carries them only when Dying is its own
    ID; bones and idle share the last block."""
    own_death = t.Dying == t.id
    dying = max(t.DyingPhases, 0) if own_death else 0
    tail = t.IdlePhases or (max(t.BonePhases, 0) if own_death else 0)
    return t.stand_frames + (_mb(t) + t.AttackPhases + dying + tail) * t.dirs


def center_anchor(cx, cy, width, height, w, h):
    """Anchor inside a w x h frame of a record with CenterX/Y, Width,
    Height (units, objects): ((CenterX - Width/2) + w/2, (CenterY -
    Height/2) + h/2)."""
    return (cx - width // 2) + w // 2, (cy - height // 2) + h // 2


def placement(t, x, y, frame_w, frame_h, z=0):
    """Top-left of a frame for an object at screen (x, y), FUN_00468640."""
    ax, ay = center_anchor(t.CenterX, t.CenterY, t.Width, t.Height, frame_w, frame_h)
    return x - ax, y - ay - z


# --------------------------------------------------------------------------
# Heroes.  FUN_0046f688 picks graphics/units/<heroes|heroes_l>/<weapon>/
# sprites.256 and the units.reg type from the folder name.  Hero files carry
# no dying/bones blocks: dying heroes switch to unarmed / mage_st.
# --------------------------------------------------------------------------

HERO_TYPES = {"unarmed": 1, "unarmed_": 2, "swordsman": 3, "swordsman_": 4,
              "swordsman2h": 5, "axeman": 7, "axeman_": 8, "axeman2h": 9,
              "clubman": 10, "clubman_": 11, "pikeman": 12, "pikeman_": 13,
              "archer": 14, "bowman": 14, "xbowman": 15, "mage": 23, "mage_st": 24}
HERO_DYING = ("unarmed", "mage_st")


def hero_expected_frames(t, folder):
    """Frames in heroes*/<folder>/sprites.256 for its type t (data rule)."""
    if folder in HERO_DYING:
        return expected_frames(t)
    return t.stand_frames + (_mb(t) + t.AttackPhases + t.IdlePhases) * t.dirs


# --------------------------------------------------------------------------
# Action events, FUN_0046b5ef.  The action counter obj+0x9c is 0 at the
# start of an attack/shoot/cast and is compared with the delays before the
# phase is taken from it, so an event shows on attack phase seq[delay].
# --------------------------------------------------------------------------

def event_phase(t, delay):
    """AttackAnim phase drawn on the tick an event with this delay fires,
    or None when the delay is past the sequence (the event never fires)."""
    seq = t.sequence("Attack")
    return seq[delay] if 0 <= delay < len(seq) else None

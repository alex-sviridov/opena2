"""Animation API: which frame each animated thing shows at a given time, and
how it is drawn.  Spec: docs/formats/animation.md.

Classes (one AnimationSet subclass each, same surface, see base.py):
    units / monsters / heroes   units.UnitSet         load_unit_set
    structures, bridges         structures.*Set       load_structure_set
    map objects                 objects.ObjectSet     load_object_set
    projectiles, spell effects  projectiles.*Set      load_projectile_set
    terrain water               terrain.WaterSet      load_water_set
    burning cells (fire/steam)  effects.BurningSet    load_burning_set
    cursors                     ui.CursorSet          load_cursor_set
    other UI sequences          ui.UiSequenceSet      load_ui_set
load_set("<kind>:<id>", fs) picks the loader by prefix; fs is an a2res FS
(None = the game's, allods2.common.game_fs) and file names are game paths.
"""

from ..common import as_fs
from .base import (CELL, CELL_UNITS, COMPASS, DEFAULT_SPEED, FACINGS, TICK_RATES,
                   UNITS_PER_PIXEL, Action, AnimationSet, FrameRef, Part, period_ms,
                   tick_at_ms)
from .lens import apply_lens, lens_table
from .objects import ObjectSet, load_object_records, load_object_set
from .projectiles import ProjectileSet, load_projectile_records, load_projectile_set
from .structures import (BridgeSet, StructureSet, load_structure_records,
                         load_structure_set)
from .effects import BurningSet, load_burning_set
from .terrain import WaterSet, find_water_window, load_water_set
from .ui import (CURSORS, CursorSet, UiSequenceSet, cursor_frame, cursor_name, load_cursor_set,
                 load_ui_set, ui_sequence_paths)
from .units import (HERO_SPEED, MOVE_UNITS_PER_ELEMENT, UnitSet, load_unit_set,
                    unit_keys, walk_odometer, walk_ticks_per_cell)

KINDS = {"unit": load_unit_set, "structure": load_structure_set,
         "object": load_object_set, "projectile": load_projectile_set,
         "water": load_water_set, "burning": load_burning_set,
         "cursor": load_cursor_set, "ui": load_ui_set}


def load_set(key, fs=None):
    """Any animation set by key: "<kind>:<id>" with kind in KINDS
    (e.g. "structure:11", "object:0", "projectile:12"), or a unit key
    (units.reg ID, hero folder, unit file/folder) without a prefix."""
    fs = as_fs(fs)
    kind, sep, rest = str(key).partition(":")
    if sep and kind in KINDS:
        return KINDS[kind](rest, fs)
    return load_unit_set(key, fs)


def all_keys(fs=None):
    """{class folder: [load_set key]} of everything animated in the game."""
    fs = as_fs(fs)
    objs = load_object_records(fs)
    return {
        "units": [str(k) for k in unit_keys(fs)],
        "structures": ["structure:%d" % i for i in sorted(load_structure_records(fs))],
        "objects": ["object:%d" % i for i in sorted(objs)
                    if fs.isfile("graphics/objects/" + objs[i]["file"] + ".256")],
        "projectiles": ["projectile:%d" % i for i in sorted(load_projectile_records(fs))],
        "terrain": ["water:auto"],
        "effects": ["burning:"],
        "cursors": ["cursor:" + cursor_name(c[0]) for c in CURSORS],
        "ui": ["ui:" + n for n, _, _ in ui_sequence_paths(fs)],
    }


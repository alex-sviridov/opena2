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
load_set("<kind>:<id>", data_dir) picks the loader by prefix.
"""

import os

from ..common import find_file
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
from .units import (HERO_SPEED, MOVE_UNITS_PER_ELEMENT, UnitSet, load_animation_set,
                    load_unit_set, unit_keys, walk_odometer, walk_ticks_per_cell)

KINDS = {"unit": load_unit_set, "structure": load_structure_set,
         "object": load_object_set, "projectile": load_projectile_set,
         "water": load_water_set, "burning": load_burning_set,
         "cursor": load_cursor_set, "ui": load_ui_set}


def load_set(key, data_dir):
    """Any animation set by key: "<kind>:<id>" with kind in KINDS
    (e.g. "structure:11", "object:0", "projectile:12"), or a unit key
    (units.reg ID, hero folder, unit file/folder) without a prefix."""
    kind, sep, rest = str(key).partition(":")
    if sep and kind in KINDS:
        return KINDS[kind](rest, data_dir)
    return load_unit_set(key, data_dir)


def all_keys(data_dir):
    """{class folder: [load_set key]} of everything animated in the install."""
    objs = load_object_records(data_dir)
    return {
        "units": [str(k) for k in unit_keys(data_dir)],
        "structures": ["structure:%d" % i for i in sorted(load_structure_records(data_dir))],
        "objects": ["object:%d" % i for i in sorted(objs)
                    if find_file(os.path.join(data_dir, "graphics/objects"), objs[i]["file"] + ".256")],
        "projectiles": ["projectile:%d" % i for i in sorted(load_projectile_records(data_dir))],
        "terrain": ["water:auto"],
        "effects": ["burning:"],
        "cursors": ["cursor:" + cursor_name(c[0]) for c in CURSORS],
        "ui": ["ui:" + n for n, _, _ in ui_sequence_paths(data_dir)],
    }


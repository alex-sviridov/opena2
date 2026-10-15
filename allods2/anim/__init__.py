"""Animation API: which frame each animated thing shows at a given time, and
how it is drawn.  Spec: docs/formats/animation.md.

Classes (one AnimationSet subclass each, same surface, see base.py):
    units / monsters / heroes   units.UnitSet         load_unit_set
    structures, bridges         structures.*Set       load_structure_set
    map objects                 objects.ObjectSet     load_object_set
    projectiles, spell effects  projectiles.*Set      load_projectile_set
load_set("<kind>:<id>", data_dir) picks the loader by prefix.
"""

from .base import (CELL, CELL_UNITS, COMPASS, DEFAULT_SPEED, FACINGS, TICK_RATES,
                   UNITS_PER_PIXEL, Action, AnimationSet, FrameRef, Part, find_file,
                   period_ms, tick_at_ms)
from .lens import apply_lens, lens_table
from .objects import ObjectSet, load_object_records, load_object_set
from .projectiles import ProjectileSet, load_projectile_records, load_projectile_set
from .structures import (BridgeSet, StructureSet, load_structure_records,
                         load_structure_set)
from .units import (HERO_SPEED, MOVE_UNITS_PER_ELEMENT, UnitSet, load_animation_set,
                    load_unit_set, unit_keys, walk_odometer, walk_ticks_per_cell)

KINDS = {"unit": load_unit_set, "structure": load_structure_set,
         "object": load_object_set, "projectile": load_projectile_set}


def load_set(key, data_dir):
    """Any animation set by key: "<kind>:<id>" with kind in KINDS
    (e.g. "structure:11", "object:0", "projectile:12"), or a unit key
    (units.reg ID, hero folder, unit file/folder) without a prefix."""
    kind, sep, rest = str(key).partition(":")
    if sep and kind in KINDS:
        return KINDS[kind](rest, data_dir)
    return load_unit_set(key, data_dir)


__all__ = ["KINDS", "load_set",
    "CELL", "CELL_UNITS", "COMPASS", "DEFAULT_SPEED", "FACINGS", "TICK_RATES",
    "UNITS_PER_PIXEL", "Action", "AnimationSet", "FrameRef", "Part", "find_file",
    "period_ms", "tick_at_ms", "apply_lens", "lens_table",
    "ObjectSet", "load_object_records", "load_object_set",
    "ProjectileSet", "load_projectile_records", "load_projectile_set",
    "BridgeSet", "StructureSet", "load_structure_records", "load_structure_set",
    "HERO_SPEED", "MOVE_UNITS_PER_ELEMENT", "UnitSet", "load_animation_set",
    "load_unit_set", "unit_keys", "walk_odometer", "walk_ticks_per_cell",
]

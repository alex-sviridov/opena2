"""Asset cache: decoded game assets loaded once and shared (no pygame).

Pixel data stays numpy; converting it to a display format is the job of the
renderer that needs it.  Spec: docs/engine/architecture.md section 2.
"""

from .common import as_fs
from .graphics import SpriteFile
from .graphics.terrain import TerrainSet


class AssetCache:
    def __init__(self, fs=None):
        """`fs`: an a2res FS or install folder (None = the default install)."""
        self.fs = as_fs(fs)
        self._tileset = None
        self._sprites = {}
        self._databin = None
        self._unit_stats = None
        self._items = None
        self._spells = None
        self._progression = None
        self._objects_reg = None
        self._structures_reg = None
        self._object_sets, self._structure_sets = {}, {}
        self._unit_sets, self._unit_types = {}, None

    def tileset(self):
        """The terrain strips and dirt.bmp (`TerrainSet`)."""
        if self._tileset is None:
            self._tileset = TerrainSet.load(self.fs)
        return self._tileset

    def sprite(self, path):
        """The `SpriteFile` at game path `path`; frames via `to_rgba(i, palette)`."""
        sf = self._sprites.get(path)
        if sf is None:
            sf = self._sprites[path] = SpriteFile.load(path, self.fs)
        return sf

    def databin(self):
        """data.bin (`DataBin`), loaded once."""
        if self._databin is None:
            from .databin import databin
            self._databin = databin(self.fs)
        return self._databin

    def unit_stats(self):
        """The unit and monster stat table (`formats.unitstats.UnitTable`), loaded once."""
        if self._unit_stats is None:
            from .formats import unitstats
            self._unit_stats = unitstats.build(self.databin())
        return self._unit_stats

    def items(self):
        """The item definition table (`formats.itemdefs.ItemTable`, display names included), loaded once."""
        if self._items is None:
            from .formats import itemdefs
            from .common import as_fs
            self._items = itemdefs.build(self.databin(), itemdefs.load_names(self.fs))
        return self._items

    def spells(self):
        """The spell definition table (`formats.spelldefs.SpellTable`, display texts included), loaded once."""
        if self._spells is None:
            from .formats import spelldefs
            self._spells = spelldefs.build(self.databin(), spelldefs.load_texts(self.fs))
        return self._spells

    def progression(self):
        """The XP curve and hero start templates (`formats.progression.Progression`), loaded once."""
        if self._progression is None:
            from .formats import progression
            self._progression = progression.build(self.unit_stats(), self.spells())
        return self._progression

    def map_reg(self):
        """`(costs, speed_multiplier)` from `world/data/map.reg` (docs/formats/animation.md 3.4):
        the 11-entry terrain cost table and [Path Finding] SpeedMultiplier (default 8)."""
        from . import reg
        from .formats import passability as pas
        r = reg.load_reg("world/data/map.reg", self.fs)
        return pas.costs_from_reg(r), int(r.get("Path Finding/SpeedMultiplier", 8))

    def objects_reg(self):
        """objects.reg records by ID with Parent inheritance (`anim.objects.load_object_records`)."""
        if self._objects_reg is None:
            from .anim.objects import load_object_records
            self._objects_reg = load_object_records(self.fs)
        return self._objects_reg

    def structures_reg(self):
        """structures.reg records by ID (`anim.structures.load_structure_records`)."""
        if self._structures_reg is None:
            from .anim.structures import load_structure_records
            self._structures_reg = load_structure_records(self.fs)
        return self._structures_reg

    def object_set(self, oid):
        """The `ObjectSet` of objects.reg ID `oid`, loaded once; None for an unknown ID."""
        if oid not in self._object_sets:
            from .anim.objects import load_object_set
            reg = self.objects_reg()
            self._object_sets[oid] = load_object_set(oid, self.fs, reg) if oid in reg else None
        return self._object_sets[oid]

    def structure_set(self, type_id, size=None):
        """The `StructureSet` (or `BridgeSet` for VariableSize records, sized `size` =
        (w, h) cells) of structures.reg ID `type_id`, loaded once; None when unknown."""
        key = (type_id, size)
        if key not in self._structure_sets:
            from .anim.structures import BridgeSet, StructureSet, structure_paths
            rec = self.structures_reg().get(type_id)
            if rec is None:
                aset = None
            elif rec.get("VariableSize"):
                w, h = size or (0, 0)
                aset = BridgeSet(rec, w, h, paths=structure_paths(rec, self.fs), fs=self.fs)
            else:
                aset = StructureSet(rec, paths=structure_paths(rec, self.fs), fs=self.fs)
            self._structure_sets[key] = aset
        return self._structure_sets[key]

    def unit_types(self):
        """units.reg records by ID (`allods2.units`), loaded once."""
        if self._unit_types is None:
            from . import units
            self._unit_types = units.by_id(units.unit_types(self.fs))
        return self._unit_types

    def unit_set(self, type_id):
        """The `UnitSet` of units.reg ID `type_id`, loaded once; None when the ID is unknown
        or names no sprite file."""
        if type_id not in self._unit_sets:
            from .anim.units import load_unit_set
            t = self.unit_types().get(type_id)
            self._unit_sets[type_id] = None if t is None or not t.file else \
                load_unit_set(type_id, self.fs, list(self.unit_types().values()))
        return self._unit_sets[type_id]

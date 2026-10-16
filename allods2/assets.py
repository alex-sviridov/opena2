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
        self._objects_reg = None
        self._structures_reg = None
        self._object_sets, self._structure_sets = {}, {}

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

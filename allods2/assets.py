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

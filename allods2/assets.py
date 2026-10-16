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

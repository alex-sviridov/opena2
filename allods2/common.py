"""Shared helpers: the game data source, C arithmetic.

The game data is read through an a2res file system (a2res.FS).  `game_fs()`
mounts the GOG install's .res archives: $ALLODS2_INSTALL, else
samples/allods2_en_gog in the repository.  Paths are game paths
(`graphics/units/units.reg`).  OUT is the gitignored output folder.
"""

import os

import a2res
from a2res import join  # noqa: F401  (re-exported: game path join)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.environ.get("ALLODS2_INSTALL") or os.path.join(ROOT, "samples", "allods2_en_gog")
OUT = os.path.join(ROOT, "out")

_game = None


def have_install(install=INSTALL):
    return os.path.isfile(os.path.join(install, "graphics.res"))


def game_fs():
    """The default install's ResFS, mounted once per process."""
    global _game
    if _game is None:
        _game = a2res.ResFS(INSTALL)
    return _game


def as_fs(source=None):
    """FS for `source`: None -> game_fs(); an FS as is; a folder with .res
    archives -> ResFS; another folder -> DirFS (loose tree, e.g. tests)."""
    return game_fs() if source is None else a2res.open_fs(source)


def read(path, fs=None):
    """Bytes (memoryview) of `path` in `fs`; fs None = a plain OS path."""
    return (fs or a2res.OS).read(path)


def campaign_maps(fs=None):
    """Game paths of the single-player campaign maps (scenario/<n>.alm),
    in numeric order."""
    fs = as_fs(fs)
    names = [n for n in fs.listdir("scenario") if n.lower().endswith(".alm")]
    return ["scenario/" + n for n in sorted(names, key=lambda n: (len(n), n))]


def cdiv(a, b):
    """C integer division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def find(fs, path):
    """`path` (normalised) when it is a file in `fs`, else None."""
    p = a2res.norm(path)
    return p if fs.isfile(p) else None

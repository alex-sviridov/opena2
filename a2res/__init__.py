"""a2res: Allods 2 (Rage of Mages II) `.res` archives and a read-only game
file system over them.  Standard library only; no dependency on allods2.

    from a2res import ResFS
    fs = ResFS("samples/allods2_en_gog")
    data = fs.read("graphics/units/units.reg")     # memoryview, no copy
    fs.listdir("graphics/units/monsters")

Spec: docs/formats/res.md.
"""

from .archive import (DELETED, DIR_INLINE, ENTRY, HEADER, NAME_MAX, SIGNATURE, SORTED,
                      T_SECTION, Entry, ResArchive)
from .fs import (ARCHIVES, FS, OS, ChainFS, DirFS, MemoryFile, OSFS, ResFS, basename,
                 dirname, join, norm, open_fs, splitext)


def extract(archive, dest):
    """Write every file of a ResArchive under dest/<stem>/...; returns the
    file count.  Only for inspection: the library reads archives directly."""
    import os
    n = 0
    for path, e in archive.walk():
        out = os.path.join(dest, archive.name, *path.split("/"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(archive.read_entry(e))
        n += 1
    return n

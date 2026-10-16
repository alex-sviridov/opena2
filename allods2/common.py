"""Shared helpers: install paths, case-insensitive file lookup, C arithmetic.

INSTALL / DATA default to the English install under samples/ in the
repository; $ALLODS2_INSTALL and $ALLODS2_DATA override them.  OUT is the
gitignored output folder.
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.environ.get("ALLODS2_INSTALL") or os.path.join(
    ROOT, "samples", "Allods2_en_251005", "Allods2_en")
DATA = os.environ.get("ALLODS2_DATA") or os.path.join(INSTALL, "data")
OUT = os.path.join(ROOT, "out")


def find_file(root, rel):
    """Path of `rel` (backslashes allowed) under `root`, matching each
    component case-insensitively as Windows does; None when absent."""
    path = root
    for part in rel.replace("\\", "/").split("/"):
        if not part:
            continue
        exact = os.path.join(path, part)
        if os.path.exists(exact):
            path = exact
            continue
        try:
            names = {n.lower(): n for n in os.listdir(path)}
        except OSError:
            return None
        if part.lower() not in names:
            return None
        path = os.path.join(path, names[part.lower()])
    return path


def cdiv(a, b):
    """C integer division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q

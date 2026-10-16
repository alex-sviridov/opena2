"""Regenerate tests/golden.json: SHA-256 of the `world-dump` JSON of a few maps.

    python tools/update_golden.py [INSTALL_DIR]

The hashes are derived values (no game data), so the file is committed.  Run it
only when a change of the world state is intended.  Spec:
docs/superpowers/specs/2026-10-16-world-state-design.md "Tests".
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from allods2.assets import AssetCache  # noqa: E402
from allods2.cli import open_map  # noqa: E402
from engine.world import World  # noqa: E402

MAPS = ("10", "20", "52")
GOLDEN = os.path.join(ROOT, "tests", "golden.json")


def golden_hash(spec, install=None):
    return World.from_map(open_map(spec, install), AssetCache(install)).dump_hash()


def main(argv):
    install = argv[1] if len(argv) > 1 else None
    out = {m: golden_hash(m, install) for m in MAPS}
    with open(GOLDEN, "w", encoding="ascii") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    for m, h in out.items():
        print("%s %s" % (m, h))


if __name__ == "__main__":
    main(sys.argv)

"""Regenerate tests/golden.json: SHA-256 of the `world-dump` JSON of a few maps, and
of the RGB bytes of fixed engine screenshots (key "screenshots").

    python tools/update_golden.py [INSTALL_DIR]

The hashes are derived values (no game data), so the file is committed.  Run it
only when a change of the world state or of the drawing is intended.  Specs:
docs/superpowers/specs/2026-10-16-world-state-design.md and
2026-10-16-object-drawing-design.md "Tests".
"""

import hashlib
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

# Parity positions (map, viewport x, y in world px, kinds that must be in view): trees,
# a structure, a bridge and water meet.  The engine screenshot at shadows=False, lit=False
# equals the E4 reference (`map render --relief`) pixel for pixel.
PARITY = {
    "10-forest": ("10", 256, 256, ("object",)),
    "10-shore-rock": ("10", 1056, 740, ("object", "structure")),
    "10-camp": ("10", 1184, 804, ("object", "structure")),
    "52-bridge": ("52", 2656, 2884, ("object", "bridge")),
    "52-bridge-2": ("52", 3136, 2692, ("bridge",)),
    "52-village": ("52", 2752, 292, ("object", "structure")),
}
# name -> (map, x, y, tick, plain): "plain" = shadows=False, lit=False (the parity
# render); the others use the game's default options (regression, not parity).
SHOTS = {"parity-" + k: (v[0], v[1], v[2], 0, True) for k, v in PARITY.items()}
SHOTS["full-10-shore-rock"] = ("10", 1056, 740, 0, False)
SHOTS["full-52-village"] = ("52", 2752, 292, 0, False)


def golden_hash(spec, install=None):
    return World.from_map(open_map(spec, install), AssetCache(install)).dump_hash()


def rgb_hash(rgb):
    return hashlib.sha256(rgb.tobytes()).hexdigest()


def shot_hashes(install=None):
    """{name: sha256 of the 1024 x 768 RGB bytes} of SHOTS (needs pygame-ce)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from engine.backend_pygame import render
    from engine.backend_pygame.sprites import SpriteCache
    from engine.backend_pygame.surfaces import SurfaceCache
    from engine.view import Camera, DrawOptions, TerrainView
    assets = AssetCache(install)
    envs, out = {}, {}
    for name, (spec, x, y, tick, plain) in SHOTS.items():
        if spec not in envs:
            w = World.from_map(open_map(spec, install), assets)
            tv = TerrainView(w, assets.tileset())
            envs[spec] = (w, tv, SurfaceCache(tv), SpriteCache(assets))
        w, tv, tc, sc = envs[spec]
        cam = Camera(1024, 768, w.width, w.height, x, y)
        opts = DrawOptions(shadows=False, lit=False) if plain else DrawOptions()
        out[name] = rgb_hash(render.screenshot(tv, cam, tick, None, tc, assets, opts, None, sc))
    return out


def main(argv):
    install = argv[1] if len(argv) > 1 else None
    out = {m: golden_hash(m, install) for m in MAPS}
    out["screenshots"] = shot_hashes(install)
    with open(GOLDEN, "w", encoding="ascii") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    for m, h in out.items():
        if isinstance(h, dict):
            for k, v in h.items():
                print("%s %s" % (k, v))
        else:
            print("%s %s" % (m, h))


if __name__ == "__main__":
    main(sys.argv)

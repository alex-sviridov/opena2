"""Builders and skip markers shared by the tests."""

import os
import struct

import pytest

from allods2 import units as U
from allods2.anim import UnitSet
from allods2.anim.projectiles import ProjectileSet
from allods2.common import DATA
from allods2.graphics import PALETTE_FLAG, SpriteFile


def needs(*rel, base=DATA):
    """Skip unless <base>/<rel> exists (base defaults to the install's data/)."""
    path = os.path.join(base, *rel)
    return pytest.mark.skipif(not os.path.exists(path), reason="game files not present: " + path)


needs_data = needs("graphics", "units", "units.reg")
needs_graphics = needs("graphics")


def container(sprites, palette=None):
    """Sprite container bytes: [palette] {w, h, size, data}* trailer."""
    body = b"".join(struct.pack("<III", w, h, len(d)) + d for w, h, d in sprites)
    trailer = len(sprites)
    if palette is not None:
        body = bytes(palette) + body
        trailer |= PALETTE_FLAG
    return body + struct.pack("<I", trailer)


def sprite_file(n, pixels=(0, 1, 2, 3)):
    """n identical 4x1 frames; index 0 = transparent (skip), others literal;
    palette entries 1..3 = red 60, 120, 180."""
    assert pixels[0] == 0 and 0 not in pixels[1:]
    pal = bytearray(1024)
    for i in range(1, 4):
        pal[4 * i:4 * i + 3] = bytes((0, 0, 60 * i))        # BGR0
    data = bytes([0x81, len(pixels) - 1, *pixels[1:]])
    return SpriteFile.parse(container([(len(pixels), 1, data)] * n, pal))


def unit_type(uid=50, **kw):
    """A units.reg type: 1 + 4 move, 3 attack, 2 dying, 1 bones phases."""
    vals = {k: d for k, _, d in U.INT_FIELDS}
    vals.update({k: [] for k in U.ARRAY_FIELDS})
    vals.update(DescText="", InfoPicture="", MovePhases=4, MoveBeginPhases=1, AttackPhases=3,
                DyingPhases=2, BonePhases=1, IdlePhases=0, Width=128, Height=128,
                CenterX=64, CenterY=70, Dying=uid,
                MoveAnimTime=[2, 2, 2, 2], MoveAnimFrame=[0, 1, 2, 3],
                AttackAnimTime=[1, 2, 1], AttackAnimFrame=[0, 1, 2],
                AttackDelay=1, ShootDelay=9)
    vals.update(kw)
    t = U.UnitType(0, uid, -1, vals)
    t.file = "synthetic"
    return t


def aset_of(t, **kw):
    """UnitSet of t over a sprite file with exactly the frames t lays out."""
    sf = sprite_file(U.expected_frames(t))
    return UnitSet("synthetic", t, t, sprites={"main": sf, "death": sf}, **kw)


def projectile(pid, sprites=None, **kw):
    rec = dict(ID=pid, File="p", Phases=4, RotationPhases=16, Width=64, Height=64,
               Palette=1, Flip=0, A16=1)
    rec.update(kw)
    return ProjectileSet(rec, sprites=sprites or {"main": sprite_file(64)})

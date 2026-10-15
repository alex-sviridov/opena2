"""python -m allods2 gfx export, on a hand-built sprite file."""

import struct

from PIL import Image

from allods2 import cli


def test_gfx_export_one_png_per_sprite(tmp_path):
    pal = bytearray(1024)
    pal[4:8] = bytes((10, 20, 30, 0))
    body = b"".join(struct.pack("<III", 2, 1, len(d)) + d
                    for d in (b"\x02\x01\x01", b"\x81\x01\x01"))
    src = tmp_path / "x.256"
    src.write_bytes(bytes(pal) + body + struct.pack("<I", 2 | 0x80000000))
    assert cli.main(["gfx", "export", str(src), str(tmp_path / "o")]) == 0
    a = Image.open(tmp_path / "o" / "x_000.png")
    b = Image.open(tmp_path / "o" / "x_001.png")
    assert a.mode == "RGBA" and list(a.get_flattened_data()) == [(30, 20, 10, 255)] * 2
    assert list(b.get_flattened_data()) == [(0, 0, 0, 0), (30, 20, 10, 255)]

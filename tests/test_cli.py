"""python -m allods2 gfx export, on a hand-built sprite file."""

import numpy as np
import pytest
from PIL import Image

from allods2 import cli

from helpers import container


@pytest.fixture
def src(tmp_path):
    pal = bytearray(1024)
    pal[4:8] = bytes((10, 20, 30, 0))
    path = tmp_path / "x.256"
    path.write_bytes(container([(2, 1, b"\x02\x01\x01"), (2, 1, b"\x81\x01\x01")], pal))
    return path


def test_gfx_export_one_png_per_sprite(tmp_path, src):
    assert cli.main(["gfx", "export", str(src), str(tmp_path / "o")]) == 0
    a = Image.open(tmp_path / "o" / "x_000.png")
    b = Image.open(tmp_path / "o" / "x_001.png")
    assert a.mode == "RGBA" and list(a.get_flattened_data()) == [(30, 20, 10, 255)] * 2
    assert list(b.get_flattened_data()) == [(0, 0, 0, 0), (30, 20, 10, 255)]


def test_gfx_export_index_and_sheet(tmp_path, src):
    assert cli.main(["gfx", "export", str(src), str(tmp_path / "one.png"), "--index", "1"]) == 0
    assert np.asarray(Image.open(tmp_path / "one.png"))[0].tolist() == [[0, 0, 0, 0], [30, 20, 10, 255]]
    assert cli.main(["gfx", "export", str(src), str(tmp_path / "s.png"), "--sheet", "--cols", "1"]) == 0
    sheet = np.asarray(Image.open(tmp_path / "s.png"))
    assert sheet.shape == (4, 3, 4)                     # 2 rows of (2 + 1) x (1 + 1) cells
    assert sheet[2, :2, 3].tolist() == [0, 255]

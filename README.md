# allods2

Analysis and reimplementation of the data formats of Allods 2 / Rage of
Mages 2 (Nival).

```
allods2/        core library (numpy, Pillow; no pygame)
  graphics/     sprites, palettes, BMP, PNG output, compositing
docs/formats/   format documentation, with references into allods2.exe
tests/          pytest suite
tools/          command-line utilities
samples/        local game install - never committed
```

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[game,dev]'
```

Put a game install under `samples/`. The tests and tools expect
`samples/Allods2_en_251005/Allods2_en/`; set `ALLODS2_INSTALL` (install root)
or `ALLODS2_DATA` (its `data/` directory) to point them elsewhere
(`allods2/common.py`). Tests that need game files are skipped when the
install is absent.

## Usage

```sh
.venv/bin/pytest
.venv/bin/python -m allods2 gfx export samples/.../graphics/units/heroes/archer/sprites.256 out/archer.png --sheet
.venv/bin/python tools/validate_sprites.py
```

```python
from allods2 import graphics as gfx

sf = gfx.SpriteFile.load(".../units/monsters/bat/sprites.256")
gfx.write_png("out/bat0.png", sf.to_rgba(0))   # (h, w, 4) uint8 array
```

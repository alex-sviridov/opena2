# allods2

Analysis and reimplementation of Allods 2 / Rage of Mages II:
Necromancer (Nival), single player, from the GOG release.

```
a2res/          stand-alone .res archive library + game file systems
allods2/        core library (numpy, Pillow; no pygame), reads through a2res
  graphics/     sprites, palettes, BMP, fonts, terrain, lighting, PNG output
  anim/         animation API for every animated class
docs/formats/   format documentation, with references into allods2.exe
docs/inventory.md  install survey, binary triage, plan
tests/          pytest suite
tools/          command-line utilities
samples/        local game install - never committed
```

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[game,dev]'
```

Put the GOG install at `samples/allods2_en_gog/` (or point
`ALLODS2_INSTALL` at it). The game data stays in its ten `.res` archives:
`a2res` memory-maps them and every loader reads through it, so nothing is
unpacked ([docs/formats/res.md](docs/formats/res.md)). Tests that need
game files are skipped when the install is absent.

## Usage

```sh
.venv/bin/pytest
.venv/bin/python tools/validate_res.py
.venv/bin/python tools/validate_sprites.py
.venv/bin/python -m allods2 res ls graphics/units/monsters
.venv/bin/python -m allods2 gfx export graphics/units/heroes/archer/sprites.256 out/archer.png --sheet
.venv/bin/python -m allods2 anim preview monsters/bat out/bat
```

```python
from allods2 import graphics as gfx
from allods2.common import game_fs

fs = game_fs()                                         # the install's ResFS
sf = gfx.SpriteFile.load("graphics/units/monsters/bat/sprites.256", fs)
gfx.write_png("out/bat0.png", sf.to_rgba(0))           # (h, w, 4) uint8 array

import a2res                                           # the archives alone
fs = a2res.ResFS("samples/allods2_en_gog")
data = fs.read("world/data/data.bin")                  # memoryview, no copy
```

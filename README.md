# allods2

An open reimplementation of **Allods 2 / Rage of Mages II: Necromancer** (Nival, 2000), single player, written in Python.
It reads the game's own data files, works out how the original behaves, and re-creates that behaviour in a new engine.
The project is a prototype: one campaign map is playable from start to finish ([docs/prototype.md](docs/prototype.md)).

## You need your own copy of the game

This repository contains **no original game files**: no archives, sprites, sounds, maps, texts or tables, and no data
extracted from them. It also contains **no decompiled code**: the behaviour is documented in our own words (with the
addresses of the routines it was checked against) and implemented from those notes. Without a legal copy of the game the
engine has nothing to load. It is developed against the GOG release (`allods2.exe` 1.01, ten `.res` archives).

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[engine,dev]'
```

Put the GOG install at `samples/allods2_en_gog/` or point `ALLODS2_INSTALL` at it. The archives stay as they are:
`a2res` maps them and every loader reads through it, so nothing is unpacked.

## Play

```sh
.venv/bin/python -m engine play 32            # campaign map 32, with the hero of the map
.venv/bin/python -m engine replay ~/.allods2/sessions/<session> --verify
```

`play` records the session (seed, your commands, final world hash, a log with any crash traceback) in
`~/.allods2/sessions/`; `replay` runs it again without a window and checks that the world ends in the same state.
Controls and what is built: [docs/prototype.md](docs/prototype.md).

## Layout

```
a2res/          stand-alone .res archive library
allods2/        file formats, decoders, data models (numpy, Pillow; no pygame)
engine/         the game: world, simulation, view, UI; only engine/backend_pygame imports pygame-ce
docs/           specifications: formats, mechanics, engine (each fact marked CONFIRMED or INFERRED)
tests/          pytest suite (tests that need the game files skip without them)
tools/          command-line utilities
```

Tests: `.venv/bin/pytest`.

## Documentation

The folder indexes ([engine](docs/engine/README.md), formats, mechanics, data) list the specs. Each states how a fact was established and what is still
open; open questions are collected in [docs/open-questions.md](docs/open-questions.md).

## Licence and rights

No licence has been chosen yet. Allods 2 and Rage of Mages are the property of their owners; this
project is not affiliated with them and is not a way to obtain the game.

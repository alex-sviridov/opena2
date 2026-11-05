# J4: one original map from start to finish (prototype)

**Goal.** Map 32 (`scenario/32.alm`, the J3 map) is played from start to finish by the user; the session is recorded and replays to the same world hash. Bug pass, comparison with the original, close-out docs follow the user's play-through.

## Decisions (agreed 2026-11-05)

- Map **32**. `python -m engine play 32` = `run` with the map script, party (hero from the map data), AI, fog, difficulty Medium; no debug flag. The `run` developer options stay on `run`.
- Session directory `~/.allods2/sessions/<map>-<YYYYmmdd-HHMMSS>/` (`--out DIR` overrides; `ALLODS2_SESSIONS` overrides the root), printed at start and at exit:
  - `session.json`: format version, map, seed, difficulty, size, install-independent engine id (`git rev-parse HEAD`, `+dirty`), and `commands` = `[tick, {"t": ClassName, ...fields}]`. AI-issued commands (`ai=True`) are not stored: replay regenerates them (`simulation.replay`).
  - `final.json`: tick, result (`won` / `lost` / null), `dump_hash`, exit reason (`quit`, `victory`, `defeat`, `crash`).
  - `engine.log`: python logging of `engine.*` at INFO (the "not implemented" reports), and the traceback of a crash.
- The log is written at exit, on a crash (`finally`), and every ~10 s of wall time (a hard kill loses at most that).
- `python -m engine replay <session dir | session.json> [--verify] [--window]`: headless by default, prints tick, result, hash; `--verify` exits 1 when the hash differs from `final.json`. `--window` = visual playback is **not** built (VERIFY: user did not ask; a replay shows through `screenshot`-like tools only if needed by a bug).
- Replay steps the same systems as play (triggers, AI, **fog**): the world dump holds the fog bits, so a replay without fog gives another hash (found by the first smoke run).
- Bug pass: each reported issue is reproduced with `replay`, written as a failing test (a trimmed log or a scripted scenario), fixed, and the spec checked and corrected where the cause was a spec error (CONFIRMED / INFERRED marks as in CLAUDE.md).

## Components

| Unit | Does | Depends on |
|---|---|---|
| `engine/session.py` (no pygame) | `encode_command` / `decode_command` (registry of `Command` subclasses, tuples restored), `build_game(map, install, seed, difficulty)` (shared by play and replay), `Recorder` (attach sim, periodic flush, `finish(reason)`), `replay_session(path)` | `engine.sim`, `allods2.assets` |
| `engine/__main__.py` | `play`, `replay` sub-commands; logging setup; crash handling | session, window |
| `engine/backend_pygame/window.py` | `run(..., sim_hook=)` hands the `Simulation` out, `frame_hook` drives the flush | |
| docs | `docs/prototype.md`, README rewrite, CLAUDE.md status | |

## Tests

Command round trip for every `Command` subclass; a headless session on map 32 saved by the `Recorder` replays to the same hash (win scenario); crash path writes the traceback and the log; `replay --verify` exit codes; the existing 123 test files stay green.

## Close-out (after the user's play-through)

All tests pass, golden tests reviewed; the user's recorded run replays to the same hash (the session is kept as an uncommitted artifact; a short synthetic one is the committed test); `docs/prototype.md` (works, how to run, known differences, phase K backlog by value: inventory, more spells, full triggers, campaign, full UI, sound / music, save / load, multiplayer); public README (what it is, needs the user's own game copy, no original files or decompiled code); CLAUDE.md Status "Prototype complete", Next = first phase K item.

## Open questions

- Visual replay (`--window`) is deferred.

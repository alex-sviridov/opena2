# m1: cutscenes (Smacker 2 videos)

Status: **m1 done** (decoder, fades, player screen, start-up chain, chapter triggers, Cut Scenes window); **nothing watched or heard yet: VERIFY IN GAME (section 7)**.
What the exe does (REA, CONFIRMED with routine addresses): [cutscenes-rea.md](cutscenes-rea.md). Headers and the `.reg` fade engine: [shell.md 6](shell.md#6-videos-confirmed-headers-read-from-videores-moviesres-holds-only-shop--inn-bitmap-animations).
Facts below are CONFIRMED when they cite the REA file, **INFERRED** otherwise (the decoder is checked by its output, not against `smackw32.dll`, which is packed).

## 1. Steps

| Step | What | Where |
|---|---|---|
| m1a | Smacker 2 decoder (video, palette, audio), C block loop | `allods2/formats/smacker.py`, `allods2/native/smk.c`, `tools/validate_smk.py`, `tests/test_smacker.py` |
| m1b | frame source: code -> files, `.reg` fades, `Run` | `engine/cutscene.py`, `tests/test_engine_cutscene.py` |
| m1c | `Cutscene` screen, `Video` scene op, `Services.pcm`, start-up chain, mission-victory / town-leave triggers, seen mask | `engine/shell/cutscene.py`, `startup.py`, `machine.py`, `backend_pygame/*`, `tests/test_engine_cutscene_shell.py` |
| m1d | the CUT SCENES window (main menu button 2) | `engine/shell/cutlist.py` |

## 2. The Smacker 2 file (INFERRED from the output: all 8 files decode, each frame's block stream ends within 4 bytes of its chunk (teleport frame 105: 31), audio length = video length to the sample frame)

Little-endian; the bit stream is read **LSB first**.

| Offset | Field |
|---|---|
| 0 | `SMK2`; width, height, frames (u32 each); frame time i32 (> 0 ms, < 0 hundredths of a ms: -6666 = 66.66 ms = 15 fps); flags u32 (bit 0 ring frame; bits 1 / 2 Y-interlace / double: refused) |
| 24 | audio sizes u32 x 7; tree size u32; mmap / mclr / full / type unpacked sizes u32 x 4 (unused here) |
| 72 | audio rates u32 x 7: low 24 bits Hz, high byte flags `0x80` packed, `0x40` present, `0x20` 16-bit, `0x10` stereo (`0xf0` = packed 16-bit stereo, 22,050 Hz) |
| 100 | dummy u32; frame sizes u32 x frames (bit 0 = key, low 2 bits masked); frame types u8 x frames (bit 0 palette, bit `1 + t` audio track t) |
| then | the tree block (`tree size` bytes) and the frames back to back (the sizes tile the file exactly) |

**Trees.** Four (mmap, mclr, full, type), each: present bit; low-byte tree (present bit, tree, end bit), high-byte tree (same), three 16-bit **escape values** `e0 e1 e2`, the 16-bit tree, end bit. A small tree: bit 0 = leaf (8 bits follow), bit 1 = node (left, right). The 16-bit tree has the same shape; a leaf is `lo | hi << 8` from the two small trees, and a leaf equal to `e[k]` is a **cache marker k**. Decoding a code: walk the bits to a leaf; a marker gives `cache[k]`; if the value differs from `cache[0]` the cache shifts (`c2 = c1; c1 = c0; c0 = v`). **The cache starts at zero at every frame** (the header values are only the escapes; reading them as the start values breaks every frame with a busy block stream, found on teleport / crown).

**Frame chunk.** Palette chunk (type bit 0): size byte `n`, `4n - 1` bytes of codes over a copy of the last palette: `0x80 | k` skips `k + 1` colours, `0x40 | k` + index copies `k + 1` colours from the old palette, else a 6-bit R, then G, B bytes (`(v << 2) + (v >> 4)`). Audio chunks (one per set type bit 1..7): size u32 (incl. itself), then the data. Video: the rest.

**Video blocks.** 4x4 blocks in raster order. Per run: a type code `t`: kind = `t & 3` (0 mono, 1 full, 2 skip, 3 fill), run = `RUNS[(t >> 2) & 63]` (1..59, 128, 256, 512, 1024, 2048), fill colour `t >> 8`. Mono: colour code (`hi` = colour of 1 bits, `lo` = 0 bits) then a map code (bit `4 r + c`); full: per row two codes, the first = pixels 2, 3 (low byte first), the second = pixels 0, 1; skip keeps the previous picture.

**Audio (packed).** u32 unpacked size, then bits: present, stereo, 16-bit; `2^(stereo + bits16)` small trees (present bit, tree, end bit); the predictors (right channel first, 16 bits LSB first); then per sample a delta (low byte tree, high byte tree of the channel) added to the channel predictor, channels interleaved. The first frame carries 94,080 bytes (one second plus), later frames 5,880 bytes (22,050 / 15 x 4).

**Cost.** Python reference 75 ms per frame; the C block loop (`smk.c`, built on first use like the other native libraries, `ALLODS2_NATIVE`) plus the Python audio decode 13 ms per frame against the 66.7 ms budget. `tools/validate_smk.py` decodes the whole install with the Python path, checks the stream ends and the audio length, and compares the C pictures hash for hash.

## 3. The frame source (`engine/cutscene.py`)

`video_paths(fs, code)` = `video\<cutpaths.txt line code>\NN.smk` for NN = 1.. while the file exists (the exe tries all 99 and skips gaps, REA 1; only `01` exists). `Fades` = shell.md 6 exactly (a record starts on `startframe`, `fade += (end - start) / len` in float32, palette = `trunc(byte * fade)`, a finished fade keeps its palette until the Smacker palette changes). `Run.step()` returns the next `CutFrame` (pixels, faded palette, audio).

## 4. The player and its triggers

| Rule | Source |
|---|---|
| Music is hard-stopped when a chapter video call starts, and not restarted; the next screen asks for its own | REA 1 |
| The seen-mask bit (`videos_seen`, bit n = code n; bit 0 always set) is set and the settings saved **before the first frame**, abort or not | REA 1, 4 |
| Cursor hidden, black screen around the picture; 640x480 pictures at the screen's menu origin, 640x360 pictures 60 px down (`0x493df0`); never doubled | REA 2 |
| Key down (incl. Alt), left or right button **press** abort **everything** still to play; releases, moves, the wheel, the middle button do nothing | REA 2 |
| Start-up: publisher, then nival, then the intro; an abort anywhere goes to the menu (it skips the rest, incl. the intro) | REA 3 |
| Mission victory: the code `ScenarioLeaveLocation` returned (>= 0) plays before the next screen; leaving a town (`0x42d`): same | REA 6 |
| Every due frame is decoded (the delta frames need them) and the newest shown; the last frame ends the video at once | REA 2 (the exe spins `SmackWait`, never skips) |
| The video audio ignores the volume sliders in the exe (no volume call); **DECISION**: the engine plays it at full volume but is silent when `mute` is set (`--mute`) | REA 2 |

Engine flow: `TownCore` events `("cutscene", code)` -> `Shell.pending_cuts` (`drain_town`, also called by the game screen right after `mission_over`) -> `Shell.go` redirects the next move through the `cutscene` screen (`then` = the screen it was going to) when `Services.video` is true. Without a video backend (`Services.video` False: the tests, `--no-video`) nothing is redirected and the start-up logs `video skipped: <name>` as before. `Services.pcm(samples, rate)` queues the audio on the last mixer voice (`Audio.pcm`), `pcm_stop` cuts it; `Video(pixels, palette, x, y)` is the scene op (palette lookup in the backend). Not built: the network switch (`0x436`, play intro + close).

## 5. The CUT SCENES window (`engine/shell/cutlist.py`, REA 5)

Main menu button 2 (enabled whenever videos play; the exe enables it by the CD / registry check only). A 392x360 dialog centred over the menu picture: heading `dialogs 0x99` ("View Cutscenes"), list = one row per set bit of the mask in ascending order titled by `cutscene.txt` line = bit number, Ok at `w/7 .. 3w/7` and Cancel at `4w/7 .. 6w/7` (y `h-0x3c`, height 24). Row 0 is selected at first, then the last Ok's row. Ok plays a video and re-opens the list, Cancel / Esc = the menu. **QUIRK kept:** Ok passes the **row index**, not the bit number (`ROW_IS_CODE`), so with the sparse mask of the druids' ending (bits 0-3, 5) row 4 replays the knights. Up / Down / PageUp / PageDown move the selection (CONFIRMED, list slot `0x4d8fdb`, [REA 5](cutscenes-rea.md)); a double click only selects (the `0x444` it posts has no handler here); Enter = Ok (INFERRED: not a list key, so the default button); the exe has no wheel code, the engine's wheel scroll is a DECISION (convenience).

## 6. Decisions

1. The Python decoder is the reference, the C loop an optional accelerator (same pattern as the planner / blend / ADPCM). No third-party video library: the decoder is written from the format, checked by the exact stream ends and by looking at frames.
2. `Using VxD` lives in the settings file (`videos_seen`), forced `>= 1` as the exe does.
3. Video audio is at full volume except under `mute` (the exe has no volume call).

## 7. VERIFY IN GAME (nothing watched yet)

- The three logos and the intro play at 15 fps with their audio in sync; a key press or click in the first logo goes straight to the menu.
- The picture position of the 640x360 chapter videos (60 px down) against the original; fades at the start and end of intro / chapters.
- After mission 10 / 30 / 70 or 80 / 110 the right video plays, then the map; a key skips it.
- The CUT SCENES window lists what was seen; Ok plays the row and returns; the music after a video from the list (the exe leaves it off until the menu).
- The audio channel order (left / right) and the loudness.

## Open questions

- Audio details cannot be checked against the exe or the DLL (`smackw32.dll` is packed and the exe only hands it the file): the channel order of stereo (left / right, VERIFY BY EAR) and the cache rule of rarely used markers (frames decode to the exact stream end, which a wrong rule would break: that check stands).
- The rest of [cutscenes-rea.md "Open questions"](cutscenes-rea.md): the 640x360 blit's `srcx` / `srcy` (needs eyes) and frame dropping in `smackw32.dll` (not answerable from the exe).

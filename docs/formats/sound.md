# Sound and music

Code: `allods2/formats/sound.py` (decoder, `Sound`, `to_wav`), `allods2/formats/soundtable.py` (sound ids, voice banks,
purpose by folder). Tools: `tools/survey_sound.py` (census and byte accounting), `python -m allods2 sound export-all DEST`,
`python -m allods2 data export sounds DEST.json`. Tests: `tests/test_sound.py`.
Addresses are in the GOG `allods2.exe` (sha256 in [README](README.md)); `FUN_` names are Ghidra's.

**Evidence.** Decoder: every one of the 1,599 audio files of the install decodes with no leftover byte
(CONFIRMED by the decoder consuming all of them). Engine side: routines read with REA (K10 research); a fact is **CONFIRMED** when
a routine address is given, **INFERRED** otherwise.

## 1. Survey (CONFIRMED, `tools/survey_sound.py`)

There is **no custom audio format**: every audio file is a standard RIFF/WAVE `.wav`; no other audio extension exists
(no `.mp3`, `.ogg`, `.mid`, tracker, `.snd`). Music is also `.wav`; there is no CD audio ([§5](#5-music)).

| Folder (archive) | Files | Bytes (min .. max) | Format |
|---|---:|---|---|
| `music/` (`music.res`) | 21 | 3.4 .. 12.2 MB | PCM 16-bit stereo 22,050 Hz, `fmt data` |
| `sfx/` (`sfx.res`) | 445 | 44 B .. 336 KB | 391 PCM + 1 PCM (44,100 Hz) mono, 53 MS ADPCM mono 22,050 Hz |
| `speech/` (`speech.res`) | 1,133 | 90 B .. 880 KB | 145 + 2 (44,100 Hz) PCM mono, 986 MS ADPCM mono 22,050 Hz |

Total 1,599 files, 560 PCM + 1,039 ADPCM, 9,869 s (2.74 h) of audio.
Every RIFF size is exact and the chunks end at the file end (no pad, no trailing bytes). Chunk layouts: `fmt fact data` (1,039,
all ADPCM), `fmt data` (541), `fmt data LIST` (16), `fmt LIST data` (3); the `LIST` chunks are metadata and ignored by the game's
reader (§3). Loose files: none (the install's only non-archive audio-like file is `Music.ini`, §5).

What the names suggest (the `purpose` column of `out/sound/index.csv`, `soundtable.purpose`):

| Path | Files | Use |
|---|---:|---|
| `sfx/` root (`click00`, `error`, `message`, `letter1`, ...) | 81 | UI, messages (table ids 1-16 and loose) |
| `sfx/units/`, `sfx/magic/`, `sfx/ambient/` | | weapons, hits, deaths, spell sounds, river |
| `sfx/monsters/<name>/{easy,hard,dead,attack}` | | monster voices |
| `sfx/characters/<bank>/...` | | hero and class voices ([§4.2](#42-hero-and-class-voices)) |
| `sfx/town*/`, `sfx/chrgen/` | | town inns / shops, character creation |
| `speech/{talk,accept,reject,about,town}/` | 491 / 95 / 65 / 7 / 95 | NPC dialogue lines ([§4.3](#43-speech)) |
| `speech/{shop,shop_druid,shop_kaarg}/` | 145 / 91 / 144 | shopkeeper lines |
| `music/` | 21 | B00..B16 + `menu`, `map`, `chrgen`, `credit` |

## 2. File format (CONFIRMED: all 1,599 decode exactly)

Plain RIFF/WAVE (`RIFF size WAVE` then chunks, each padded to even length):

| Chunk | Content |
|---|---|
| `fmt ` (16 B) | PCM: `wFormatTag=1, channels, rate, byterate, blockAlign = channels*2, bits=16` |
| `fmt ` (50 B) | MS ADPCM: the 16 bytes with `tag=2, bits=4, blockAlign=512`, then `cbSize=32, wSamplesPerBlock=1012, wNumCoef=7` and 7 `(coef1, coef2)` int16 pairs = the standard table `(256,0) (512,-256) (0,0) (192,64) (240,0) (460,-208) (392,-232)` (identical in every file) |
| `fact` (4 B) | ADPCM only: frame count |
| `data` | PCM: little-endian int16 frames; ADPCM: 512-byte blocks, the last one short |
| `LIST` | ignored metadata (19 files) |

### 2.1 MS ADPCM (mono, 4-bit)

Block of `blockAlign` bytes: `predictor u8` (index into the 7 pairs), `delta i16`, `sample1 i16`, `sample2 i16`, then 4-bit codes,
**high nibble first**. Output of a block: `sample2`, `sample1`, then one sample per code (2 + 505 * 2 = 1012 frames per 512-byte block):

    p  = (s1*c1 + s2*c2) >> 8        (arithmetic shift)
    s  = clamp16(p + signed(q) * delta)           signed(q) = q - 16 if q >= 8
    delta = max(16, (ADAPT[q] * delta) >> 8)      s2 = s1; s1 = s
    ADAPT = 230 230 230 230 307 409 512 614 768 614 512 409 307 230 230 230

Quirks (CONFIRMED on the install):
- A **partial final block** holds `2 + 2*(bytes - 7)` frames.
- `fact` is the true length: 52 files whose data is whole blocks have a shorter `fact` (the last block is padded: the decoder
  trims to `fact`); in ~500 files with a partial final block `fact` is **one frame more** than the block can hold (the encoder
  counted the padding nibble); the decoder keeps the decodable frames. Any other difference is an error.
- **9 files have an empty `data` chunk** (44 or 90 bytes: `sfx/town_druid/{dout,inn/din1,shop/ddruid5,shop/ddruid6,shop/din2}`,
  `speech/shop_kaarg/effects/{07,08,10,11}`): they decode to a zero-frame `Sound` and play silence.
- `delta` is unbounded in the decoder (64-bit arithmetic). A driver keeping it in 16 bits would differ only after a runaway
  `delta`, which the install's data never reaches on real speech (INFERRED; see VERIFY BY EAR).
- Check used by the test: a block header restates its first two samples, so the previous block should end near `sample2`. It does
  in 98 % of the ~156,000 block boundaries; the rest are noisy consonants coded with predictor 2 (coefficients 0, 0: no prediction), where
  neighbouring samples are uncorrelated. A wrong `ADAPT` table (found and fixed during K10) breaks ~100 % and fills the file with
  full-scale noise.

## 3. How the exe plays a file (CONFIRMED, REA)

| Routine | Role |
|---|---|
| `FUN_0045ade7(hwnd, 16 voices, NULL)` (called `0x482446` from `0x4823e2`) | `DirectSoundCreate` (ordinal 1), `SetCooperativeLevel(3)` (exclusive), primary buffer set to 22,050 Hz stereo 16-bit (falls back 8-bit, mono, 11,025 Hz); default secondary format PCM 22,050 mono 16 at `0x61f628`; voice table `0x61f63c` (16 x 0x10 bytes: priority +4, buffer +8, owner +0xc); failure or `-nomusic` zeroes `0x6226a8` (sound off) |
| `0x45a1a2(path)` | sound object constructor: stores the path only |
| `0x45a3f4` | lazy loader: own RIFF reader on the virtual file system, static buffer (flags `0xea`, else `0xe6`); **tag 1 copied in 64 KB chunks; tag 2 decoded by Windows** (`acmStreamOpen` / `Size` / `PrepareHeader` / `Convert`, msacm32); then 15 `DuplicateSoundBuffer` copies = 16 voices per sound |
| `0x45aa2f(this; volume_mB, pan, freq, priority, loop)` | play: lazy load (a missing file fails silently and is retried at every play), free duplicate by `GetStatus & 1` (all busy = dropped), `0x45ab9c` claims a global voice (steals the lowest priority below the new one, else dropped), SetVolume / SetPan / SetFrequency / Play |
| `0x41b1f8(x, y, &vol, &pan)` | positional mix on the view (no DirectSound 3D): pan `dx*4000 / (half_view_width << 8)` clamped +-10000; volume from the distance to the view (`exp` thunk `0x583260`, INFERRED form), floor -10000 mB; callers use priority `(10000 - |vol|) / 100` |
| `0x622698` / `0x6226a0` | SFX and speech volume in mB, added to every play; slider curve `0x45b3a3` (INFERRED `-R*((R-pos)/R)^2`, R = 10000); the SFX slider test plays `sfx[0x64]` at priority `0xdc` |
| registry (`0x43c979`, key `SOFTWARE\Rage of Mages 2`) | `SoundRandom`, `SoundMusPos`, `SoundSfxPos`, `SoundSpeechPos`, `MusicEnabled` (`0x5f0610`...`0x5f0644`) |

So the engine must decode ADPCM itself (the exe asks the Windows ACM; the output is the standard MS ADPCM decode, §2.1) and
treat every sound as a static 16-voice sound with volume, pan and a priority byte.

## 4. Sound ids and variants

### 4.1 The id table (CONFIRMED)

`sfx/sfx.reg` (`Global/SfxCount = 660`, section `Sfx`, keys `Sfx<n>` -> path under `sfx\` without extension). The loader `0x4c4a48` fills the
slot array `0x627740` (661 slots), lookup `FUN_00420eb0` is an unchecked index; null slots are skipped by the players
(`0x467e1a`, `0x415189`). 200 keys exist (ids 1-8, 11-16, 50, 90, 100-160, 200-245, 300-..., spell sounds 500 + projectile id,
see [spells §7](../data/spells.md)); `out/data/sounds.json` (`data export sounds`) has them all: 192 point to an existing file,
**8 point to a missing file** (`monsters\daemon\{dead,easy,hard}`, `monsters\{skeleton,mage_skel,necrom,succubus,zombie}\attack`):
the loader has no existence check, the load fails at every play: silent. One id = one file; there is no variant list in this table.

Unit sounds: `graphics/units/units.reg` `UnitN/Sound` = 5 ids read at `0x47a653` into the unit type at `+0xdc`:
`[attack, hit material, easy wound, hard wound, dead]` (slot meanings 0, 2, 3, 4 CONFIRMED by the players `0x467cd2` / `0x467f60`; slot 1 =
"metal / soft hit" INFERRED from the values 200 / 210). All 61 sets resolve to existing ids (`sounds.json["unit_sound_sets"]`).
No per-sound volume or priority exists in the data: the priority is computed from the distance (§3), the volume only from the options.

### 4.2 Hero and class voices

Not in `sfx.reg`. Bank constructor `0x4c5038` builds 15 banks (0x6c bytes at `0x627758 + k*0x6c`) from `sfx\characters\<bank>\...`:
`select/N.wav`, `attack/N`, `move/N`, `swarm/N` (N = 1..4), `retreat/1`, `pickup/1`, `defend/1`, `easy`, `hard`, `dead`. **Variants:** the
constructor probes N = 1, 2, ... until the first missing file and stores the counts (+0x5c...); a voice plays `rand(count-1)`. So the
variant count is the number of consecutive files on disk (`sounds.json["hero_banks"]`: aldor select 3, others 1-2).
Bank order (CONFIRMED): aldor, sagita, hildarius, galinel, igles, dina, xbow, knight, druid, troll, orc, mage. Chooser `0x468094` on the
unit type `+0x1dc`: types 1-6 = xbow, knight, druid, troll, orc, mage; 21 = the hero by flags `+0x1b8` (bit 4 / bit 2 select aldor,
sagita, hildarius, galinel), 22 = igles, 23 = dina; other units use generic `m`/`f` + `_fighter` / `_mage` / `_peasant` banks (no such
folders exist: silent, INFERRED). Players: `0x4681c8` attack, `0x4682a6` move, `0x468383` swarm, `0x468460` select, `0x46853d` defend,
`0x4685f4` retreat, `0x4686ab` pickup; each has a per-unit cooldown at `unit+0x1bc` (3000 ms; select 2000 ms); `0x467f60(1|2|3)` plays
easy / hard / dead of a hero bank.

### 4.3 Speech

Dialogue player `0x4dc84c` builds `speech\<name>.wav` (priority `0x80`, volume `0x6226a0`):

| Folder | Format | VA |
|---|---|---|
| `talk` | `talk\%04d%c%sp%02d` | `0x5f75ac` |
| `about` | `about\%04dt000p%02d` | `0x5f75c8` |
| `accept` / `reject` / `town` | `<dir>\%04d%c%sp%02d` | `0x5f75f0` / `0x5f761c` / `0x5f764c` |
| shop | `speech\%s\effects\%.2d`, `\books\%.2d`, `\s%.2di%.2dp%d` (`%s` = `shop`, `shop_druid`, `shop_kaarg`; p random 1-3; `0x4b5ffa`) | `0x5f5460`... |

`%04d` = NPC id (21 = the party hero), `%c` = `t` (neutral) or the hero class letter when the speaker is the hero (`f` flags 0, `m` bit 2,
`a` bit 4, `s` both), `%s` = 3-digit code from the script token, `p%02d` = line number inside the dialogue (counter at `this+0x68`). The
meaning of the code inside the scripts and of `s` / `i` in shop names is INFERRED (item category / index).

### 4.4 Files nothing loads

The exe holds ~130 literal `SFX\...` paths (UI, town, shop, inn, chrgen). Left unused by table, banks and literals (INFERRED from the
REA name scan): `mess_in`, `mess_out`, `print`, `chrgen/fire`, `sheep2`, `sheep3`, `spider/attack2`, `wolf/attack1`, `wolf/pitchup/*`,
`town/inn/breath`, `town/point1`, `town/point2`, `units/catapult/*` (10), `units/horse/move`. Paths in the exe whose file is missing
(silent): `town_druid/{ddruid1,ddruid2,dlizard1-4,dtree4}`, `town_kaarg/inn/kin1`, `town_kaarg/shop/kin2`, `town/school/point`.

## 5. Music (CONFIRMED unless noted)

Music is the 21 PCM stereo `.wav` files of `music.res`; **no CD audio** (no MCI or mixer import, no CD option), nothing to skip.
Player class `0x459acd(bufsize)` (object at app+0xc8): streaming DirectSound buffer of two halves (`0xac000` bytes, `0x56000` when the
low-memory flag `0x6227f0` is set), refilled by the callback `0x4592fc` -> `0x459313` from the main loop (`0x4011f4`, `0x426bf0`), **no thread**.
`0x45977d(index)` opens a track (rebuilds the buffer if the format changed); `0x459a5f(playlist)` stores a playlist and starts at
`rand() % count`, then plays sequentially (`(i+1) % n`, or the same track when the loop flag `+0x18` is set); `0x459ec5` plays only if
`0x6226ac` (MusicEnabled) is set; no crossfade (stop fades with `0x459d68(2000 ms, 8000)`).

| Screen | Playlist | Routine |
|---|---|---|
| main menu | `music\menu.wav` | `0x48b569` |
| world / campaign map | `music\map.wav` (INFERRED screen) | `0x48b419` |
| town | `b14`, `b16`, `b15` | `0x48bbc0` |
| credits | `music\credit.wav` | `0x48be11` |
| character creation | `music\chrgen.wav` | `0x48f4e2` (push `0x48f67b`) |
| a mission | all 17 `b00`..`b16` (table `0x5f3bc8`, 0x10 per entry, `0x492536`-`0x492620`) | random start, then in order |

Map music zones ([map §12](map.md)): `0x4754e9(viewX, viewY)` picks the nearest zone containing the view and one of its 4 theme ids
(`zone+0xc..0x18`, -1 = none) at random into `0x5f1a08`; a value >= 0 is started at the mission start (`0x4926a9`, `0x45a030`) and when the
view moves (`0x40bd8b`); when a track ends `0x459067` takes `0x5f1a08` if >= 0, else the next track. `Music.ini` (17 `Melody<n>` titles)
is **not read by the game** (no such string in `allods2.exe`); the map editor reads it for its zone dialog: `Melody<n>` = `b<n-1>.wav`
(INFERRED from the counts).

## Open questions

- Registry hive of the sound options and what `SoundRandom` does (`0x43c979`).
- The distance-attenuation formula (`0x41b1f8`): `exp` base and constants; the slider range R.
- The hit-material slot (unit sound set slot 1): the call site that plays it (`0x467cd2` second block).
- Whether `0x5f1a08` is reset after a zone theme is used; which screen `0x48b419` really is (map vs. campaign map).
- Meaning of the 3-digit code of dialogue names and `s` / `i` of shop names (Scenario.dll scripts, `main/text/mission*.txt`).
- ADPCM `delta` width in the Windows ACM driver (only matters for pathological blocks).

## VERIFY BY EAR

Listen to these first (`python -m allods2 sound export-all out/sound`):
1. **PCM stereo music**: `out/sound/music/menu.wav` (40 s, the only stereo files: left / right must not be swapped or doubled).
2. **PCM mono 22,050 SFX**: `out/sound/sfx/click00.wav`, `sfx/units/sword.wav` (0.2 s).
3. **PCM mono 44,100 Hz** (3 files): find them with `awk -F, '$4==44100' out/sound/index.csv` (must not sound slowed or sped up).
4. **MS ADPCM SFX**: `out/sound/sfx/characters/dina/attack/1.wav`, `sfx/characters/galinel/select/2.wav` (loudest, most likely to
   expose a wrong delta rule: should be a clean voice, no hiss or full-scale noise).
5. **MS ADPCM speech**: `out/sound/speech/about/0001t000p01.wav`, `speech/talk/0021f040p09.wav` (long, many blocks: a block-boundary
   click would show a wrong header order).
6. **Partial last block / fact trim**: any ADPCM file's last 50 ms must end cleanly (no click or a spurious tick).

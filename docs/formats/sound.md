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
- `delta` is unbounded in the decoder (64-bit arithmetic). **CONFIRMED on the data:** the largest `delta` reached in any of the
  1,039 ADPCM files is 16,284 (never above 32,767), so a Windows ACM driver keeping `delta` in 16 or 32 bits decodes every file
  identically.
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
| `0x45aa2f(this; volume_mB, pan, loop, priority, freq)` (order corrected in K11, [audio §1](../engine/audio.md#1-corrections-to-soundmd-found-in-k11-confirmed-0x45aa2f-read-again); no caller passes a frequency) | play: lazy load (a missing file fails silently and is retried at every play), free duplicate by `GetStatus & 1` (all busy = dropped), `0x45ab9c` claims a global voice (steals the lowest priority below the new one, else dropped), SetVolume / SetPan / SetFrequency / Play |
| `0x41b1f8(x, y, &vol, &pan)` | positional mix on the view, **no DirectSound 3D** (formulas in §3.1) |
| `0x622698` / `0x6226a0` | SFX and speech volume in mB, added to every play; slider curve `0x45b3a3` (INFERRED `-R*((R-pos)/R)^2`, R = 10000); the SFX slider test plays `sfx[0x64]` at priority `0xdc` |
| registry (loader `0x43c978`, writer `0x43ca2b`; open `0x440bb7`, `0x440cd2`) | **`HKEY_LOCAL_MACHINE`**`\SOFTWARE\Rage of Mages 2` (CONFIRMED: only `0x80000002` pushes in that code; opened with `KEY_READ` only, so the write likely fails without admin rights, INFERRED), five **DWORD** values read / written inline with `RegQueryValueExA` / `RegSetValueExA` (no wrappers; return codes ignored; a missing value keeps the constructor default of the settings object `0x622688`, `0x476130`): `SoundMusPos` -700 (+8, range 5000 at +0xc), `SoundSfxPos` -700 (+0x10 / +0x14), `SoundSpeechPos` -700 (+0x18 / +0x1c), `MusicEnabled` 1 (+0x24), `SoundRandom` 0 (+0). **`SoundRandom` is vestigial**: stored by the options dialog (`0x43daa5`) and persisted, but nothing reads it (INFERRED from a full search of the readers). A further DWORD (name at `0x5f075c`) lands in `0x5f1a04`, forced to >= 1, meaning unknown |

### 3.1 Positional volume and pan (CONFIRMED, `0x41b1f8`)

World units are 256 per cell; `view[+0x5c], [+0x60]` = the camera's top-left cell, `view[+0x64], [+0x68]` = the view size in cells:

    cx = (view.x << 8) + (view.w << 7)      cy = (view.y << 8) + (view.h << 7)         (the view's centre)
    dx = X - cx                              dy = Y - cy                                (dy is not scaled for the isometric view)
    pan    = clamp(trunc(dx * 4000 / (view.w << 8)), -10000, 10000)                    (screen edge = +-2000)
    dist   = sqrt(dx^2 + dy^2)
    volume = trunc(max(-(exp(dist / 2048) - 1) * 100, -10000))                        (mB; 1 cell = dist 256 -> r = cells / 8)

`exp` is CONFIRMED (the thunk `0x583260` -> `0x58cea1`, `fldl2e` / `fscale`). Constants 4000, 256, 8, 1, 100, -10000 at `0x5cb120`-`0x5cb148`.
There is **no cutoff** in the function: the volume floor -10000 mB (silent) is reached at `dist` ~ 9452 (about 37 cells), 8 cells = -1.7 dB,
16 cells = -6.4 dB, 30 cells = -41.5 dB. Callers use priority `(10000 - |volume|) / 100` (0..100), the play call adds the global SFX volume
`[0x622698]` (speech: `[0x6226a0]`) and `0x45aa2f` clamps at -10000. 15 call sites: `0x41514e`, `0x41565c`, `0x415a82` (in `0x40d9b2`), the unit
sound helpers `0x467cd2`, `0x467da8`, `0x467e42`, the hero voices `0x468094`-`0x4686ab`, and `0x46c1d0`. Hero order / select / wound / death voices add the **speech** volume `[0x6226a0]`. Engine side: [audio](../engine/audio.md). Non-positional UI sounds call `0x45aa2f`
directly with pan 0 (INFERRED).

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
`[attack, blow, easy wound, hard wound, dead]`; every id is used **verbatim** (a plain vector index `0x402880` into the table `0x627740`; **no
random choice among consecutive ids**: `metal1..3`, `easy1..4` are different units' ids, not variants). All 61 sets resolve to existing ids
(`sounds.json["unit_sound_sets"]`). The view-unit vtable `0x5cd660` has the players (CONFIRMED, REA K10):

| Slot | Event | Routine |
|---|---|---|
| [0] | the swing lands: the per-tick animate `0x46617c` (modes 3 and 7) when the frame counter `+0x9c` equals the type's hit frame `type+0x120` | `0x467cd2` (vtable `+0x64`) |
| [1] | the victim's "Take damage" command (`0x412a6c`, the dispatcher `0x4121b0`-`0x412b49`) arrives with **the same HP as the view's** (a blow that cost nothing: absorbed / parried, = `k = 0`); the victim's own list; never rate-limited | `0x467e42(0)` (`+0x74`) |
| [2] / [3] | HP changed, old HP > -10: easy when the old view HP >= max/2, else hard (`k = 1` / `2`); 1500 ms cooldown at `view+0x1bc` | `0x467e42(1|2)` -> `0x467f60` |
| [4] | the death animation starts (mode 6, `0x4106be`; `k = 3`) | `0x467e42(3)` |
| cast | a cast animation reaches its frame: `sfx 500 + view+0xac` (spell id; spell `0x36` at frame 0) | `0x467da8` (`+0x60`) |

Heroes (`view+0x1b8 & 0x11` or type word `+0x1dc <= 0x17`) take easy / hard / dead from the hero bank (§4.2) instead. Arguments: `0x41b1f8`
at `(view+8, view+0xc)`, volume = attenuation + `[0x622698]` (`[0x6226a0]` on the wound / dead path), priority per §3.1, no frequency. A null
object or an empty Sound list is skipped. No per-sound volume or priority exists in the data. Which server events send a "Take damage" with
unchanged HP is not traced (the slot-[1] sound is rare).

### 4.2 Hero and class voices

Not in `sfx.reg`. Bank constructor `0x4c5038` builds 15 banks (0x6c bytes at `0x627758 + k*0x6c`) from `sfx\characters\<bank>\...`:
`select/N.wav`, `attack/N`, `move/N`, `swarm/N` (N = 1..4), `retreat/1`, `pickup/1`, `defend/1`, `easy`, `hard`, `dead`. **Variants:** the
constructor probes N = 1, 2, ... until the first missing file and stores the counts (+0x5c...); a voice plays `rand(count-1)` (inclusive, `0..count-1`: every file is reachable). So the
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

**Where the names come from (CONFIRMED, REA + `main/text/town.txt`).** The dialogue window (`FUN_004dd05b`) looks up the text section `#<key>`
(key kept at `this+0x6c`) and `0x4dc84c` voices each page. Keys: `npc%dtalk%d` (`0x49b8bf`; the second number from `[0x62729c](0x300)`),
`npc%daccept%d` / `npc%dreject%d`, `npc%dabout` (`0x496d75`), and the town keys (`kaargwoman30`, `kaargguard100`, `druidinnkeeper100`,
...). `town.txt` holds 47 talk, 41 accept, 41 reject and 7 about sections; mission `#event` texts are not voiced. Each page starts with a
tag such as `<NPC=2004, part=1>` or `<npc=21, iammale, iamfighter, part=3>` (`0x4dd226`):

    name   = folder + '/' + '%04d' % npc + letter + code + 'p%02d' % line      (+ '.wav'; played only if the file exists)
    npc    = the tag's npc= (0 when absent);   line = the tag's part= (about: the page counter)
    code   = the digits after talk / accept / reject in the key, zero-padded to 3 (about: '000'; town keys: the trailing digits)
    letter = 't', or when the page has an iam* tag or npc == 21 the hero class: flags bit 4 = female, bit 2 = mage:
             neither 'f', mage 'm', female 'a', both 's'

Examples: `speech/talk/2004t043p01.wav` = section `#npc2004talk43`, page `part=1`; `speech/about/0001t000p01.wav` = `#npc1about` page 1;
`speech/talk/0021f040p09.wav` = the hero's page 9 of a `talk40` section. Coverage of the rule against `town.txt`: all 7 about, 447 / 491
talk, 61 / 95 accept, 57 / 65 reject, 91 / 95 town files are hit; 59 expected names have no file (silent) and 44 + 34 + 8 + 4 existing
files are never produced by the rule (INFERRED: other keys or unused).

**Shop speech** (`0x4b5ffa`, from the shop window handler; 30 % chance per trigger, `rand(100) < 30`, `game+0x5d8 == 2`, carried object kind
6..8; folder by `this+0x20ac`: `game+0x100` -> `shop_kaarg`, `game+0xfc` -> `shop_druid`, else `shop`). For the carried item: (1)
`effects/%.2d` = the first effect of kind 2..11, 21..25, 27..31, 33..37 (files exist for 02-11, 21-25, 27-31); else (2) `books/%.2d` when the
item teaches a spell (effect kind 0x2a; the number is the effect value, spell id not checked); else (3) `s%.2di%.2dp%d` with
`s = (item code >> 8) & 0xf` (class field: 1 armour, 2, 6..10, 12), `i = code & 0x1f` (index in the class), `p = rand(3) + 1`. Which shop action
triggers it (buy / sell / put) is not traced.

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
`0x6226ac` (MusicEnabled) is set; no crossfade (stop fades with `0x459d68(2000 ms, 8000)`). The screen playlists are set by messages to the host window (`0x4852d8`): `0x421` menu (only
when the state `+0x404` is 0), `0x425` character creation, `0x428` credits, `0x42e` and `0x468` town (`0x48bbc0`, also loads `main\text\town.txt`),
`0x41d` and `0x42d` map. None sets the loop flag (`0x459fe1` sets it, `0x4dd029` is its only caller), so a one-track playlist repeats through
`(i+1) % n` and the town list cycles b14, b16, b15.

| Screen | Playlist | Routine |
|---|---|---|
| main menu | `music\menu.wav` | `0x48b569` |
| world / campaign map | `music\map.wav` (INFERRED screen; messages `0x41d`, `0x42d`) | `0x48b419` |
| town | `b14`, `b16`, `b15` | `0x48bbc0` |
| credits | `music\credit.wav` | `0x48be11` |
| character creation | `music\chrgen.wav` | `0x48f4e2` (push `0x48f67b`) |
| a mission | all 17 `b00`..`b16` (table `0x5f3bc8`, 0x10 per entry, `0x492536`-`0x492620`) | random start, then in order |

Map music zones ([map §12](map.md); all CONFIRMED, REA K10): `0x4754e9(viewX, viewY)` scans the zones (`0x622798`: centre x, y and radius in
`<< 8` units, 4 theme ids at `+0xc..0x18`, -1 = none; zones at centre (0, 0) or with four -1 are skipped), keeps the nearest zone whose
distance is below its radius and rolls `rand` until a theme is not -1, storing it in `0x5f1a08`. A theme id is an **index into the mission
playlist** (the 17 entries B00..B16, vector at player `+0x40`; no other table). The game view calls it when `(tick & 15) == 0`
(`0x40bd8b`, sound on, view+0x3f6c set): a new random theme every 16 ticks while the view is inside a zone, nothing cached per zone; **outside
all zones nothing is written** (the old value stays). In a mission the value is stored only: the current track is not interrupted; the end
of the track (`0x459067` EOF path, `0x459198`) opens `0x45977d(0x5f1a08)` gaplessly when it is >= 0, else the next track. It is **never
cleared after use** (only `0x459a5f` resets it to -1, a new playlist), so the last theme repeats at every later track end until another zone
overwrites it. At the mission start (`0x492620` `0x459a5f`, then `0x492688` `0x4754e9`) a theme >= 0 switches at once (`0x4926a9`,
`0x45a030`). The track-change message `0x467` and the error message `0x486` do not touch it. `Music.ini` (17 `Melody<n>` titles)
is **not read by the game** (no such string in `allods2.exe`); the map editor reads it for its zone dialog: `Melody<n>` = `b<n-1>.wav`
(INFERRED from the counts).

## Open questions

- The meaning of the DWORD at `0x5f1a04` (value name `0x5f075c`) loaded next to the sound options, and of `0x6226a8` / `0x6226ac` beyond
  "sound / music on" (`0x43c978`, `0x459ec5`).
- Whether the zone theme draw `rand(3)` (`0x4756a3`) yields 0..2 or 0..3 (a fourth theme slot at `zone+0x18` may never be picked).
- Which server events send a "Take damage" with unchanged HP (the slot-[1] blow sound), and what the shop window action is that triggers
  the 30 % shop speech (`0x4b5ffa`).
- The 59 dialogue names with no file and the files the rule never produces (§4.3); whether `books/NN` is a spell id.
- The host window of the `0x467` track-change message (`0x43d8a4`) and the exact screens of `0x48b419` / `0x48bbc0` (INFERRED map / town).

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

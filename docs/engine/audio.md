# Audio in the engine (K11)

Goal: the engine sounds and plays music the way the exe does. Formats, the id table, the positional formula and the music player are in
[formats/sound.md](../formats/sound.md); this page is the engine side: **where the exe triggers sounds (with addresses), the playback
rules, the music state machine, the layers, settings, tests, VERIFY BY EAR**. Marks: **CONFIRMED** = routine read with REA (K10 + K11
research, allods2.exe sha256 in [formats/README](../formats/README.md)), **INFERRED** otherwise. Code: `engine/audio/` (pure, no pygame) and
`engine/backend_pygame/audio.py` (mixer glue). Tests: `tests/test_engine_audio*.py`. Status: slices 1 and 2 built (§9, §10).

## 1. Corrections to sound.md found in K11 (CONFIRMED, `0x45aa2f` read again)

* Signature `0x45aa2f(sound; volume_mB, pan, LOOP, PRIORITY, FREQ)`: arg 3 is the loop flag (DirectSound `Play` flags, nonzero =
  looping), arg 4 the priority byte, arg 5 the frequency. **No caller ever passes a frequency**, so pitch never changes.
* `0xdc` (220) is a **priority**, not a table id. Table ids are the argument of the lookup `FUN_00420eb0(id)` (array `0x627740`, id = `sfx.reg`
  key number). The UI priority `0xdc` beats every positional priority (max 100) and the town / speech priority `0x80`: a UI click always gets a voice.
* Hero order / select voices and the wound / death voices use the **speech** volume `[0x6226a0]`; unit attack / cast / projectile sounds and the UI use the
  **SFX** volume `[0x622698]`.
* The variant draw `FUN_0051fa25(count - 1)` is **inclusive** (`0..count-1`, simulation §10), so every file of a hero bank is reachable
  (the K10 remark that the last file is never picked was wrong).
* Only the ambience (§3.4) and the town scene loops (`0x4a0ff0`, out of scope: towns) pass loop = 1.

## 2. Trigger points

Positional = `0x41b1f8` at the object's position: attenuation `att` (mB, <= 0) and pan ([§4.1](#41-positional-mix)); priority `(10000 - |att|) / 100`; the
play adds the bus volume. Flat = pan 0, no attenuation.

### 2.1 Unit sounds (client view-unit vtable `0x5cd660`; reached only through virtual calls)

| Event | Address | Sound | Variant | Bus | Gating |
|---|---|---|---|---|---|
| swing / shot lands (animate modes 3 and 7 at the type's hit frame `type+0x120`) | `0x46617c` -> `0x467cd2` | `units.reg Sound` slot [attack] (blow slot is the victim's) | none | SFX | slot non-null |
| cast animation frame (mode 8) | `0x46617c` -> `0x467da8` | `sfx[500 + spell id]` (`view+0xac`) | none | SFX | slot non-null |
| blow that cost no HP (`0x73` with equal HP) | `0x412a6c` -> `0x467e42(0)` | slot [blow] | none | SFX | never throttled |
| HP changed, old HP > -10, old >= max/2 (k=1) / < max/2 (k=2) | `0x467e42(1/2)` -> `0x467f60` | slot [easy] / [hard]; heroes: bank `easy` / `hard` | none | speech | 1500 ms per unit (`view+0x1bc`) |
| death animation starts (`k=3`) | `0x4106be` -> `0x467e42(3)` | slot [dead]; heroes: bank `dead` | none | speech | none |
| skill-up (`0x92` sub-type 2) | `0x40e689` | table id 15 `message` | none | SFX flat, prio 100 | option word `[client+0x404] & 1` |

Footsteps: **none**; the walk mode (`0x46617c` mode 1) has no sound call. Item pick-up and gold: **no sound** (message `0x67` and the item notice `0x6a`
have none; the only audible reaction is the hero's pickup voice, §2.3). Structure uses: none ([structures §4](structures.md)). Loot drop: none
([combat §12.7](combat.md)). Ghost / flyer units use the same slots.

### 2.2 Spell and projectile sounds (server-message pump `FUN_0040d9b2`)

| Event | Address | Sound | Notes |
|---|---|---|---|
| spell object made, one target (`0x86`) / `0x8b` / `0x8c` (projectile forced to `0x1e`) | `0x4151b7`, `0x4156c5`, `0x415ae7` | `sfx[500 + projectile id]` | positional at the object; skipped for id 23 and for null slots |
| Blizzard (id 23) | `0x46c955` in `FUN_0046c1d0` | `sfx[523]` | at stepper step 8 (`+0x27 == 8`), positional |

**There is no impact / explosion sound** (cases `0x10 0x14 ...` of the stepper only add effects) and the shooters' arrow stepper `FUN_00466e18` has none:
a bow's sound is the attack slot of the swing (§2.1). The cast of the unit-target spell therefore plays twice in the original: the caster's `0x467da8` at
the cast frame and the object's `0x86` sound at creation (same id `500 + n`; CONFIRMED both exist, both are built).

### 2.3 Order and selection voices (`FUN_0041da16`, 13 senders)

Returns without a voice unless `client+0x5d8 == 2` and the voice option `DAT_00622778 != 0`. It picks **one random alive selected unit** (`size * rand() / 0x7fff`)
from the first non-empty of three arrays (A flag `+0x1b8 & 1`, B humans `& 0x10`, C unit type `+0x1dc` in 1..0x14), calls the unit's voice slot:

| Command (sender, cmd byte) | Voice slot -> routine | Bank samples | Skip rule |
|---|---|---|---|
| move `0x418bc3` (0x16) | `+0x6c` -> `0x4682a6` | `move/N` | skipped when the view's `+0x78 == 1` (asm `0x418c99`) |
| swarm `0x418d78` (0x1a) | `+0x70` -> `0x468383` | `swarm/N` | same skip |
| patrol `0x4190be` (0x1d), use structure `0x41a0b5` (0x24) | `+0x6c` | `move/N` | no skip test |
| attack unit `0x418cb3` (0x19) | `+0x68` -> `0x4681c9` | `attack/N` | |
| guard `0x418e51` (0x17), stop `0x418f09` (0x18), follow `0x418fc1` (0x1b), `0x419ffd` (0x12) | `+0x78` -> `0x46853d` | `defend/1` | |
| retreat `0x419e72` (0x14) | `+0x7c` -> `0x4685f4` | `retreat/1` | |
| pickup `0x419d8e` (0x21), `0x419f2a` (0x13) | `+0x84` -> `0x4686ab` | `pickup/1` | `0x419f2a` uses the first selected unit with flag `+0x1b8 & 1` |
| selection release `0x417986` | `+0x80` -> `0x468460` | `select/N` | only own units (`client+0x144 & 1`, `& 4 == 0`) |

Players: `now - view+0x1bc >= 3000 ms` (select **2000 ms**), else nothing; the stamp is rewritten **before** the sample lookup, so an empty slot still starts
the cooldown, and all seven voices **share one stamp per unit**. Sample = `bank[list + rand(count-1)]`; playback positional at the unit, volume + speech bus,
priority from the attenuation. Bank = `FUN_00468094` (`soundtable`, [sound §4.2](../formats/sound.md#42-hero-and-class-voices)); a unit with no
bank (generic `m_fighter`...) is silent. Bank offsets for pickup / retreat / swarm were read from 3 of 7 players only (INFERRED layout).

### 2.4 Ambience (`FUN_0041b311`, from the game-view draw `0x406f43` every frame, and message `0x485`)

Work only when the camera cell changed or the timer `view+0x49c0` expired. Scan window x in `[vx - vw, vx + 2 vw]`, y likewise, clamped `[8, size-8]`:

| Source | Test | Sound | Loop | Volume / pan |
|---|---|---|---|---|
| river | terrain type `(tile & 0x1fff) >> 6` in 8..11 | `sfx[50]` | yes | `max over cells of -(exp(floor(d / 8)) - 1) * 100` (`d` = integer cell distance from the view centre, `FUN_00583260` = exp) + SFX; pan = mean of `clamp((x - cx) * 2000 / vw, +-2000) * v_i / 10000` |
| fire wall | cell record flag `& 8` (`FUN_004203e0(view+0xa08)`) | `sfx[90]` | yes | same |
| trees / objects | object def tests `+0x44 < 0 && +0x40 == -2` (n44), else `+0x14 >= 2` (n34), else n58 | random one-shot below | no | SFX only (**no attenuation**), pan = mean |

Loops are kept between passes: a playing loop only gets new volume / pan, and stops when its source count is 0; all stop at the mission teardown
(`0x41bddd` from `0x48da92`). One-shot id: `base = 600`; `if n34 <= rand(10): base = 620`; `if n34 + n58 <= rand(10): base += 20`; night (`hour < 4 || hour > 19`, hour
`= (((clock >> 4) + 360) / 60) % 24`, clock = `client+0x408`) adds 10; `id = base + rand(10)` re-rolled until the slot exists (ids 600-609 / 610-619 forest day / night, 620-629 /
630-635 steppe, 640-647 / 650-658 north). Next one-shot at `now + 5000 + rand/7` ms. INFERRED: the first `rand` is `rand(10)`; which object defs are n44 (probably fire / burning trees).

### 2.5 UI and message sounds (flat, priority `0xdc` unless marked)

| Call site | Event | Table id -> file |
|---|---|---|
| `0x4d5c41` (generic button class, press only) | any button pressed | 2 `click01` |
| `0x40c295` (`FUN_0040c1d0`, msg `0x40c`) | command-bar button | 8 `click04` |
| `0x41adc2`, `0x41ae4f`, `0x41af4a`, `0x41b077` | backpack (`0x40e`) / spell book (`0x40f`) opened or closed | 7 `ibook` |
| `0x4ae89e`, `0x4aebc8` (`0x4aefb1`, `0x4af022`, `0x4af0a3`) | info-panel mode / menu / backpack / book buttons (on release) | 1 `click00` |
| `0x486f74` (msg `0x430`) | mission-complete dialog opens (not when already playing; skipped when `Var 0x300 >= 0x78`) | 14 `mcomplet` |
| `0x48707e` (msg `0x431`, `state+0x176 == 2`) | mission-failed dialog opens (not when already playing) | 16 `mfailed` |
| `0x485ff7` / `0x48604a` / `0x48609d` (msg `0x433` wParam `0xfe` / `0xfd` / `0xfa`) | script sub-objective failed / done / new-mission note | 16 / 14 / 14 (`campaign.message_action` already returns `("sound", slot, 0xDC)`) |
| `FUN_0040d9b2` cases `0x92` (sub 2, 5-8, `0x10`...), `0x91`, `0x93`, `0xb9` | a message-line text is posted | 15 `message`, **priority 0x64**; sub 1 "No way", 3, 4 and the gold line are silent |
| `0x43d8a4` msg `0x474` | options slider test buttons | SFX: 100 (`units/sword`), prio `0xdc` |

Table ids 3-6 and 11-13 (`click02`, `click03`, `click_ok`, `error`, `letter1-3`) have no direct caller (open question: probably literal-path
wrappers of the town / dialog windows, out of scope).

### 2.6 Not built (documented)

Town scenes and shops (`0x438570` / `0x4a0ff0` loops, enter / leave sounds, NPC speech `0x4dc84c`, shop speech `0x4b5ffa`): there are no town scenes yet (phase K
backlog); the speech *names* are specified in [sound §4.3](../formats/sound.md#43-speech) and the player will reuse the same mixer. Script instant 37
"set music node" does nothing in the exe ([triggers §instants](triggers.md)).

## 3. Playback rules

### 3.1 Voices and priority (CONFIRMED `0x45aa2f`, `0x45ab9c`, `0x45ade7`)

* 16 global voices (table `0x61f63c`: priority byte, buffer, owner). A sound object owns 16 duplicate buffers (`DuplicateSoundBuffer`), so **the same
  sound can overlap itself up to 16 times**; a 17th simultaneous play of one sound is dropped.
* Play: lazy load (a missing file fails silently and is retried every play); find a free duplicate (`GetStatus & 1` clear), else **drop**; claim a global
  voice: a free voice, else **steal the voice with the lowest priority if that is lower than the new priority** (strictly), else **drop**. Equal priority never steals.
* `volume = clamp(att + bus_mB, -10000, 0)`, pan as computed (not clamped at play), no frequency change. A sound at -10000 mB is still played (silently) and
  still occupies a voice.
* No fade, no queue, no "oldest first" rule other than the order voices are scanned (CONFIRMED lowest priority; ties: the first scanned, INFERRED lowest index).

### 3.2 Positional mix (CONFIRMED `0x41b1f8`, [sound §3.1](../formats/sound.md#31-positional-volume-and-pan-confirmed-0x41b1f8))

`cx = (vx << 8) + (vw << 7)`, `cy = (vy << 8) + (vh << 7)`, `dx = X - cx`, `dy = Y - cy`; `pan = clamp(trunc(dx * 4000 / (vw << 8)), +-10000)`;
`volume = trunc(max(-(exp(sqrt(dx^2 + dy^2) / 2048) - 1) * 100, -10000))`. No distance cutoff, no visibility test, no stereo law beyond DirectSound's pan.
The engine uses `vx, vy` = the camera's top-left cell and `vw, vh` = the view size in cells.

### 3.3 Volumes (CONFIRMED registry layer, [sound §3](../formats/sound.md#3-how-the-exe-plays-a-file-confirmed-rea))

Three buses: SFX `[0x622698]`, speech `[0x6226a0]`, music (the player's volume object). Registry defaults `SoundMusPos` / `SoundSfxPos` / `SoundSpeechPos` = -700 mB,
`MusicEnabled` 1. A bus value is added to every play (§3.1). Pause, modal dialogs, the ESC menu and the result dialogs **do not stop** sounds or music; the ambience
keeps running while the simulation is frozen. No focus-loss handling. **No in-play volume or mute key exists** (the hotkey table has none).

### 3.4 Gating by visibility (INFERRED)

The exe's sounds come from client view objects. Sounds of unit events (swing, cast frame, hit, death, order / select voices) are played only while the unit
exists as a drawn view object; the engine's rule: a unit event is dropped when its cell is **not currently seen** (fog bit `0x4000`, [vision](vision.md)); the
player's own units are always seen. Spell-object sounds (§2.2) come from server messages and are never fog-gated. There is no on-screen test: a sound far
off screen is only attenuated (-41 dB at 30 cells). VERIFY BY EAR.

## 4. Music

### 4.1 State machine (CONFIRMED, [sound §5](../formats/sound.md#5-music-confirmed-unless-noted))

| Event | Action |
|---|---|
| main menu (`0x421`, state `+0x404 == 0`) | playlist `[menu]`, random start (one track), repeats |
| world / campaign map (`0x41d` -> `0x42d` -> `0x48b419`) | `[map]` |
| town (`0x42e`, `0x468`) | `[b14, b16, b15]`, random start, sequential, wraps |
| credits / character creation | `[credit]` / `[chrgen]` |
| mission start (`0x4924cd`) | playlist `[b00..b16]`, random start `rand % 17`, sequential, wraps (never loops one track); a zone theme >= 0 switches **at once** |
| every 16 ticks in a mission (`0x40bd8b`) | `0x4754e9`: nearest zone (`dist < radius`), roll `rand` among its 4 theme slots until not -1; store the theme (`0x5f1a08`); outside all zones nothing is written |
| track end (`0x459067`, `0x459198`) | if the stored theme >= 0, open that playlist index **gaplessly** (it is never cleared), else the next track |
| victory (`0x41d`) | hard stop of the music (`0x48da92`), mission torn down, then `[map]` |
| defeat dialog (`0x431`), complete dialog (`0x430`), pause, menu | **music continues** |
| quit to menu (`0x421`) | new playlist: the old one is hard-stopped (`0x459f2f`) |
| options: music off (`0x478`) | fade 2000 ms (`0x459d68(2000, 8000)`) if playing; music on (`0x477`) starts the current playlist |

No crossfade and no silence gap between tracks; the only fade is the music-off one. Mission playlist order is the B00..B16 table `0x5f3bc8`; a theme id **is the index** into it.
`MusicEnabled` 0 or `-nomusic` = never started. The engine has no menu / map / town screens yet: the player exposes `set_playlist(name)` for them and
the mission rules above are the ones wired.

Engine: `engine/audio/music.py` `MusicState` (pure: `start_mission(zones)`, `tick(tick, view_cell)`, `track_ended()`, `stop()`, `set_enabled`), returning `Track(index | name)` decisions;
`backend_pygame/audio.py` `MusicPlayer` streams the `.wav` through `pygame.mixer.music` (PCM stereo 22,050, no decode needed) and calls `track_ended()` on the end event.
The audio layer's own RNG makes the start track, the zone roll and the one-shot ambience draws (audio never touches `World.rng`; the original's client draws share the
CRT stream, which our replays cannot reproduce anyway, [simulation §10](simulation.md#10-rng)).

## 5. Architecture

```
sim (engine/sim)              view / ui                       audio layer (engine/audio, pure)         backend_pygame/audio.py
World.sound_events  ------->  Director.drain(world, camera)   Voicebank / soundtable / ids              pygame.mixer channels
 SoundEvent(tick, kind,       UI: ui_sound(id, prio)          VoiceMixer (16 voices, priority)  ----->  Channel.set_volume(l, r)
 uid, x, y, sound, bus)       commands -> voices (own RNG)    MusicState, Ambience                        mixer.music streaming
                              Settings (volumes, mute)        AudioLog (csv)
```

* **Sim** emits `SoundEvent`s into `World.sound_events` (like `World.events`: **not** in `dump()` / the hash, cleared by the consumer; headless runs that never
  drain it must not grow it: `Simulation` keeps the last tick's events only, `keep_sound_events=False` default drops them at the next step). Kinds: `swing`, `cast`, `spell`
  (object creation), `blizzard`, `hurt` (k 0-3, hero flag in the event), `death`, `skillup`. Position = unit / object position in 1/256 units, `uid`, `sound` = a table id (int) or a bank key
  `("hero", bank, slot)`. The sim never draws random numbers for sound (every sim-side sound has exactly one candidate; variants belong to the audio layer).
* **Director** (`engine/audio/director.py`, pure): per frame it takes the events, the camera, the fog and a clock, applies §3.4 gating, the 1500 ms hurt throttle, the
  hero cooldowns (shared stamp, select 2000 ms), converts voice commands, computes volume / pan / priority (§3.2), and feeds the `VoiceMixer`. Replay and the live game share it:
  the clock is the wall clock live and `tick * 1000 / ticks_per_second` in a replay; the replay camera is centred on the player's party (DECISION: the log has no camera).
* **View / UI** emits UI sounds with `Director.ui(id, priority)`: `GameUi` button presses, backpack / book toggles, dialog opens, message-line posts (`MessageLine.show` callers that play
  `message`), the `("sound", slot, 0xDC)` actions of `campaign.message_action`. UI sounds are not in the command log, so a replay's audio log has none of them
  (stated in its header).
* **Backend** `Audio` implements the `VoiceMixer` outputs on `pygame.mixer` (`init(22050, -16, 2, 512)`, `set_num_channels(16)`): a sound is decoded once by `allods2.formats.sound.to_wav` into a
  `mixer.Sound` (cached), each play takes the channel the model chose, volume `10^(mB/2000)`, left / right `= gain * 10^(-max(+-pan, 0) / 2000)` (DirectSound's pan law). A missing file or a
  mixer failure (no device) = silent, never an error (the exe's behaviour); `SDL_AUDIODRIVER=dummy` makes tests headless.
* A null device (`NullAudio`) runs the same model with no mixer, used by tests and `replay --audio-log`.

## 6. Settings

`~/.config/allods2-engine/settings.json` (`$XDG_CONFIG_HOME`, `ALLODS2_SETTINGS` overrides; never in the repo): `{"sfx": 74, "speech": 74, "music": 74, "mute": false, "music_enabled": true}`.
Volumes are 0-100 percent; the mB offset of a bus = `-10000 * ((100 - p) / 100)^2` (the slider curve `0x45b3a3`, INFERRED), so the exe's default -700 mB is about 74. `mute` silences the
mixer without changing the stored volumes. Command line (`run`, `play`): `--mute`, `--sfx-volume N`, `--music-volume N`, `--speech-volume N` override for the run only. No in-play keys (the original has none).
An unreadable or missing file = defaults; writes are atomic (temp file + rename).

## 7. Debug: audio log

`python -m engine replay SESSION --audio-log out/audio_log.csv`: headless replay through the Director + `VoiceMixer` with a `NullAudio` and the replay clock (§5). CSV columns:
`tick,time_ms,source,event,uid,sound,file,x,y,volume_mB,pan,priority,channel,result` where `result` is `played`, `stolen:<channel>` (a lower-priority voice was cut), `dropped:busy` (no free
duplicate) or `dropped:voices` (no voice), `dropped:fog`, `dropped:cooldown`. A `#` header line records the session, seed and that UI sounds are absent.

## 8. Tests (headless, `SDL_AUDIODRIVER=dummy`)

* `test_engine_audio_events.py`: scripted scenarios (a fight, a pick-up, a switch use, a spell) produce the expected `SoundEvent` sequence; golden `["audio"]` holds the hash of each list
  (`tools/update_golden.py --only audio`); the pick-up and the switch scenarios assert **no event** (§2.1).
* `test_engine_audio_mixer.py`: more events than 16 voices: priority stealing (strict), equal priority dropped, the 17th copy of one sound dropped, the UI `0xdc` always wins.
* `test_engine_audio_mix.py`: volume and pan at known camera distances equal §3.2 (8 cells -1.7 dB / 170 mB, 16 cells -6.4 dB, pan edge +-2000); mB -> gain.
* `test_engine_audio_world.py`: world-dump goldens and `replay --verify` unchanged with audio on or off.
* `test_engine_audio_music.py`: the music state machine: random start, wrap, zone theme switch at the mission start and at track end, theme never cleared, victory stop, defeat none.
* `test_engine_audio_voices.py`: cooldown 3000 / 2000 shared stamp, an empty slot still stamps, `rand(count-1)` inclusive, skip rule of move / swarm.
* `test_engine_audio_backend.py` (slice 2): `Audio` plays / stops / mutes with the dummy driver, no device = silence, `MusicPlayer` on a synthetic wav (start, end event, stale event, fade, stop, missing file, mute), the UI sound queue, the flags and settings overrides (settings file never written), the play loop with a `NullAudio`, `replay --audio-log` on a short scripted session of map 32 (CSV columns, `#` header, `--verify` hash identical with and without it).

## 9. Slice 1 as built (decisions where the spec was silent; all INFERRED unless marked)

Built (slice 1, no device): `engine/audio/{events,mix,mixer,voices,music,ambience,director,audiolog,settings}.py`, `engine/sim/sounds.py` (the emitters), tests `tests/test_engine_audio_*.py` +
`tests/audio_scenarios.py` (goldens `["audio"]`, `tools/update_golden.py --only audio`). Slice 2 is §10.

* **Sim emission points.** `swing`: `combat.swing_tick` at the wind-up end (the hit tick), when a target exists, sound = the attacker's units.reg slot [attack] (a bow's shot is the same call); a type with no data /
  empty slot emits nothing. `cast`: `spells.cast_tick` at the wind-up end (the release tick stands for the client's cast frame: the sim has no frame clock), `500 + spell number`. `spell`: `spells.cast_start` (the
  cast message) at the caster's position, `500 + 2n + 8` (the projectile id of every `0x86` / `0x8b` / `0x8c`; the sprite-less buffs still send it), and `effects.spawn_explosion` (message `0x86`, projectile 13 at the
  cell centre: `sfx[513]`); id 23 is skipped. Other area / field impacts send no `0x86` of their own in the engine. `blizzard`: `effects.field_tick` when `world.tick - c.born == 8` (our step 8; exact tick, a missile-delivered
  Blizzard would miss it), at the carrier's centre cell. `hurt`: `combat.log` for every `Damage` entry on a unit (all message-`0x73` sources: blows, spells, poison, Drain Life) and every `Healed` with amount > 0
  (an amount-0 heal sends nothing, INFERRED), old HP = `hp + amount` / `hp - amount`, kind by `events.hurt_kind`. **`hurt_kind` decides by the view's OLD HP (CONFIRMED K11 REA `0x412a77`-`0x412aa4`; the new HP is stored only at `0x412ace`), so the §2.1 row is right.** `death`: `death.dying_tick` at the first dying tick. `skillup`: `xp.level_up` (the Director plays it for the viewer's own heroes only; the
  option word `client+0x404 & 1` is not modelled). `sound_events` is not dumped; `Simulation` clears it at the start of each step unless `keep_sound_events=True` (then the consumer clears it: `Director.drain`).
* **Sound sets.** `units.reg Sound` through `world.assets.unit_types()` (Parent inheritance already applied), cached in `World.sound_sets`; a world with no assets emits no unit-slot events. Slots <= 0 are empty.
* **Voice bank (`voices.bank_of`).** Reduced server id (`10210 -> 21`, unit-struct `+0x14c`): 1-6 = xbow, knight, druid, troll, orc, mage; 22 (`Fighter_Hero`) = igles; 23 (`Mage_Hero`) = dina; 21 (`Start_*`)
  by the template name `Start_<M|F><F|M>`: MF aldor, FF sagita, MM hildarius, FM galinel (the exe reads flag bits; the name letters are our stand-in). Wound / death use the bank for every human with type word
  1..0x17; with no bank (types 7-20: the generic `Man_*`) they are **silent** (the exe's `<= 0x17` test, no fallback to `Sound`). Real data check: `Man_Unarmed` has server id 1, so it speaks with the xbow bank
  (VERIFY BY EAR: generic humans in the campaign).
* **Order voices.** Candidates = the command's alive units with a bank; heroes (type >= 21) first, else the classes (stand-in for the three flag arrays); index `min(size - 1, size * rand15 // 0x7fff)` from the audio RNG.
  The skip rule `+0x78 == 1` is the caller's `skip_voice` flag (default off). Only the viewer's own, non-AI commands speak; a select command speaks for its `unit_ids`.
* **Ambience.** Object classes from the `objects.reg` fields: n44 = `DeadObject < 0 and FireObject == -2` (the 21 dead-tree records), n34 = `Phases >= 2` (45 animated trees / bushes), n58 = the rest (126 stones etc.);
  only n34 / n58 enter the one-shot formula, any of the three makes a one-shot possible. Fire wall = a `cell_fx` entry with slot 0. Window bounds inclusive, clamped `[8, size - 8]`. Pan weight and the one-shot's pan:
  see `ambience.py` (weight `(10000 - |v|) / 10000`, one-shot pan 0). One-shot id offset `rand(9)` (ids come in blocks of 10). One timer serves the pass and the one-shot (`next = now + 5000 + rand15 // 7`).
* **Director.** View in cells from the camera: `x // 32`, `view_w // 32` (floored). Fog gating by `event.owner != viewer` and the tile's `0x4000` bit (no fog = everything heard). `dropped:missing` is a play with a null
  table slot or a file with no duration (no voice taken, as the exe). Mute is not applied by the model: the backend silences when `settings.mute` (the log shows the unmuted volume). Loop results: `played`, `updated`,
  `stopped`. A replay passes `replay_ms(tick, rate)`; the replay camera rule of §5 is the caller's.
* **Music zones** use the view centre in 1/256 cell units and `rand(3)` = 0..3 (inclusive, like every `FUN_0051fa25`); `stop` forgets the playlist.

## 10. Slice 2 as built (the backend, the wiring, the CLI; all INFERRED decisions unless marked)

Files: `engine/backend_pygame/audio.py` (`NullAudio`, `Audio`, `MusicPlayer`, `wav_duration_ms`), wiring in `backend_pygame/window.py` (`TapQueue`, the `audio=` / `music_zones=` arguments of `run`), `engine/ui/game.py` (the sound queue),
`engine/__main__.py` (flags, `replay --audio-log`), `engine/session.py` + `engine/sim/simulation.py` (`replay(on_tick=)`), tests `tests/test_engine_audio_backend.py`.

* **Layering.** `NullAudio(fs, settings, seed, log, viewer)` owns the soundtable, the hero banks and the `Director`; `frame(now_ms, world, camera, commands, ui_sounds)` = the director frame with the ambience pass, the UI sounds, the music ticks. `Audio` adds the output:
  every audible `Played` (`played`, `stolen`) starts `mixer.Channel(p.channel)` with the model's channel (16 channels = the 16 voices), `updated` sets the loop's volume / pan, `stopped` stops it. Gains = `mix.pan_gains(volume_mB, pan)`. Durations for the model are read from the wav headers
  (`wav_duration_ms`: data size / frame size, or the `fact` frame count of ADPCM), the decode to a cached `mixer.Sound` (`Sound.to_wav`) happens on the first play; a file with no samples has no duration (`dropped:missing`). Mute: nothing is started and the music volume is 0 (nothing is loaded);
  the log still shows the unmuted volumes. pygame is imported lazily (a `NullAudio` / the replay need none); the mixer failing to open sets `Audio.ok = False` and everything stays silent.
* **Music.** `MusicPlayer` loads `BytesIO(fs.read(path))` with `pygame.mixer.music.load(.., "wav")`, volume = `gain(bus_mB)`; `set_endevent(custom type)`; the window loop gives every event to `audio.handle_event`, which asks `MusicState.track_ended()` (ignored when nothing is current or the stream is
  still busy: a stop / fade / restart posts a stale event). **The track change at an end is not sample-gapless** (the next file is loaded when the event arrives, a few ms; `mixer.music.queue` would be gapless but cannot be re-decided by the state machine: VERIFY BY EAR). Zones: `Map.music[1]` (x, y, radius in cells -> `<< 8`);
  the view centre in 1/256 cells is `(camera px + view / 2) * 8`; `MusicState.tick` is called for every sim tick since the last frame (capped at 64), so the 16-tick roll survives a slow frame and a pause draws nothing. The default zone record (section 12 head) is not used (the exe's `0x4754e9` reads only the list).
  Victory: when the loop ends with `ui.quit == "victory"` the music is hard-stopped (`0x48da92`); the complete dialog, the defeat dialog, pause and the menu keep it playing.
* **Order / select voices.** The window's queue is a `TapQueue`: every command put (mouse orders, bar buttons, hotkeys, selection release) is also kept in `tap`; each frame the new ones go to `Director.frame(commands=)` (only the viewer's non-AI commands speak). The sim runs with `keep_sound_events=True` when audio is on.
* **UI sounds** (`GameUi.sound(id, priority)`, `take_sounds()`; the UI plays nothing itself): dialog button press (2) on an enabled button; command-bar button (8) when the press runs a button (`BarWindow.clicked`); info panel mode / menu / pack / book buttons (1) on the release, plus 7 for pack / book; pack and book toggles by key, button or
  Space (7; Space opening both plays it twice, as the two messages do); mission-complete (14) / failed (16) dialogs when pushed; the `("sound", slot, 0xDC)` actions of `message_action` (slots 16 / 14); the chat echo line (`0x91`, `message` 15 at priority 100). **Not duplicated:** the skill-up line plays no UI sound because the sim's `skillup` event
  already plays `message` for the viewer's own heroes (§2.1); the other `message` sites (`0x93`, `0xb9`, sub-types 5-8 / `0x10`) have no engine source yet. Option-toggle lines have none in the exe. Not built: the options slider test button (`0x474`, no options screen), town sounds.
* **CLI.** `run` / `play`: `--mute`, `--sfx-volume N`, `--music-volume N`, `--speech-volume N` (clamped 0-100, override the settings file for the run, which is only read, never written), `--no-audio` (no `Audio` at all). `replay SESSION [--verify] --audio-log CSV`: the sim of the replay keeps its sound events, after each step
  `NullAudio.frame` runs on the replay clock (`tick * 1000 // 16`: the default speed, the journal has no speed) with a `PartyCamera` (480 px square view centred on the viewer's live units), **default settings** (the log must not depend on the user's file), the audio seed = the session seed, the music started with the map's zones. The CSV has two `#` header lines then the §7 columns. Hash, tick and `--verify` are identical with and without the option (tested).
* **Measured.** 400 frames of map 32 with the dummy driver run at the same 7.0 s (60 fps cap) with and without audio; a `NullAudio` replay of 400 ticks adds a few rows (ambience one-shots, the select voice).

## VERIFY BY EAR

1. Hero voice gaps: after a move order, another order within 3 s is silent (shared stamp); select 2 s.
2. Fog gating (§3.4): do fighting units in fog make noise in the original? (our rule: no)
3. The double sound of a unit-target cast (caster frame + object creation, same id).
4. Ambience: river loudness against the camera distance, fire-wall loop, forest one-shots (night), the 5 s spacing.
5. Wound sounds: the 1500 ms throttle, heroes use the voice bus, the death sound once.
6. Music: random start track, sequential wrap, zone theme changes on entering a zone (and the old theme repeating at every track end afterwards), silence after victory, `map.wav` after.
7. DirectSound's pan law against §5 (left / right balance at a screen edge).
8. Volume defaults: -700 mB buses against the engine's 74 %.
9. Generic `Man_*` humans (server id 1-6) speaking with a class bank when wounded; `Man_Axe` etc. staying silent (§9).
10. The cast sound timing (release tick) and the double cast sound, spell-object sounds at the caster's position.

## Open questions

- Table ids 3-6, 11-13 callers (`click02`, `click03`, `click_ok`, `error`, `letter1-3`): probably town / dialog wrappers; which of the `message` (id 15) sites fire in single player.
- Whether sounds of units in fog play in the original (§3.4); the meaning of the view state `+0x78 == 1` that skips the move / swarm voice; the three arrays of `FUN_0041da16`.
- Which object defs count as n44 / n34 / n58 in the ambience scan, and the exact `rand` of its first draw.
- The town windows `0x4b978f`, `0x4be6b0`, `0x4c03c2` and the speech-test sample of the options dialog.
- Pickup / retreat / swarm bank offsets (INFERRED from the layout).
- Gapless track change at a track end (the next track is loaded on the end event); whether `Channel.set_volume(l, r)` of SDL_mixer reproduces DirectSound's pan law at the screen edge.
- The remaining `message` (id 15) sites (`0x93`, `0xb9`, sub-types 5-8 / `0x10` of `0x92`): they need message sources the engine does not have (quests, trade).

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
| blow that cost no HP (`0x73` with equal HP) | `0x412a6c` -> `0x467e42(0)` | slot [blow] | none | SFX | never throttled; sources in 2.1a |
| HP changed, old HP > -10, old >= max/2 (k=1) / < max/2 (k=2) | `0x467e42(1/2)` -> `0x467f60` | slot [easy] / [hard]; heroes: bank `easy` / `hard` | none | speech | 1500 ms per unit (`view+0x1bc`) |
| death animation starts (`k=3`) | `0x4106be` -> `0x467e42(3)` | slot [dead]; heroes: bank `dead` | none | speech | none |
| skill-up (`0x92` sub-type 2) | `0x40e689` | table id 15 `message` | none | SFX flat, prio 100 | `client+0x404 & 1` (CONFIRMED: the screen mask's mission bit, [shell](shell.md), not an option word; always set in a mission) |

#### 2.1a The wound kind and the unchanged-HP blow (CONFIRMED, K11 round 2)

`0x412a41`-`0x412ace` compares the message's HP (`msg+0xc`) with the view's HP (`view+0x104`, the **old** value; the new one is stored only at `0x412ace`):
equal -> `0x467e42(0)`; else old HP <= -10 -> nothing; else old < `(max - sign) / 2` -> `(2)` hard, else `(1)` easy (`0x467e42` is the whole routine,
`0x467f60` is only an address inside it; `param + 1` indexes the units.reg Sound list, so 0 = slot [1] blow, 1 = easy, 2 = hard, 3 = dead; the hero
branch tests `view+0x1b8 & 0x11` or type `+0x1dc <= 0x17`). `engine.audio.events.hurt_kind` already does exactly this.

**The server events behind message `0x73`** (the only builder is `FUN_00504b1d(creature, damage)` -> `FUN_00503672(.., 0x73)`; it ignores the damage argument,
the HP in the message is the creature's current HP): the melee / shot hit `FUN_00516ceb` (sends when the target was alive or is now above -10 **whatever the
damage was**, so a blow of damage 0 = a miss or a fully absorbed hit gives HP == view HP: the blow sound), the structure-target hit `FUN_00516ea0`, the spell /
projectile hit `FUN_0051e65b` (only when the damage is > 0), the poison / state tick `FUN_0051d175` (only when the amount is non-zero), a debug command
`0x4f826f` (`DAT_0066832c` set: HP - 1 and a refresh). So the unchanged-HP blow sound plays for every swing whose damage is 0; the engine's `combat.log`
emits a `Damage` entry for such swings (`res.damage == 0`), which gives `hurt_kind` 0: matches.
**In single player the server filters nothing by sight**: `FUN_00503672` sends `0x73` when `creature+0x1a4 & player+0x30` or when `server+0x74 == 0`, and
`FUN_004eb356(p)` stores `+0x74 = (p < 2)` with `p = client+0x5d8 = 2` in a single-player game (callers `0x48c112`, `0x48db9c`).

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

Returns without a voice unless `client+0x5d8 == 2` and the voice option `DAT_00622778 != 0`. It walks the view list `+0x9d0`, keeps the selected views
(`FUN_0041eb40`) with HP `+0x104 > 0`, files each into one of **three arrays** (CONFIRMED `0x41dae4`-`0x41db7f`) and picks **one random member**
(`size * rand() / 0x7fff`, so the last index is almost never reached) from the first non-empty of A, B, C:
A = flag `+0x1b8 & 1`; else, while A is still empty, a unit with flag `+0x1b8 & 0x10`: into B when `view+0x188 != 0`, into C when `+0x188 == 0` and B is still empty;
every other unit (A not empty yet, or no `0x10`) with type `+0x1dc` in 1..0x14 goes into B. (The order of the walk matters; what `+0x188` and the flag bits
1 / 0x10 are is open: the engine's "heroes first, then classes" is the stand-in.) It calls the unit's voice slot:

| Command (sender, cmd byte) | Voice slot -> routine | Bank samples | Skip rule |
|---|---|---|---|
| move `0x418bc3` (0x16) | `+0x6c` -> `0x4682a6` | `move/N` | skipped when the chosen view's `+0x78 == 1` (asm `0x418c99`): the unit was **already walking** (below) |
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
bank (generic `m_fighter`...) is silent. The bank layout read by the seven players is CONFIRMED (constructor `0x4c5038` and each player, [sound §4.2](../formats/sound.md#42-hero-and-class-voices)).
**The skip test `+0x78 == 1` (CONFIRMED):** `view+0x78` is overwritten at the end of every animate (`0x466d5f`) with the byte `view+0x8c` (the unit state, 1 = walking),
so the move / swarm voice is skipped when the chosen unit was **already walking** at the last tick; the skip happens in the caller, before the voice routine, so it
stamps no cooldown. The engine keeps the set of walking units at the end of each Director frame (`Director.walking`) and `Voices.voice(walking=)` tests the pick.

### 2.4 Ambience (`FUN_0041b311`, from the game-view draw `0x406f43` every frame, and message `0x485`)

Work only when the camera cell changed or the timer `view+0x49c0` expired. Scan window x in `[vx - vw, vx + 2 vw]`, y likewise, clamped `[8, size-8]`:

| Source | Test | Sound | Loop | Volume / pan |
|---|---|---|---|---|
| river | terrain type `(tile & 0x1fff) >> 6` in 8..11 | `sfx[50]` | yes | `max over cells of -(exp(floor(d / 8)) - 1) * 100` (`d` = integer cell distance from the view centre, `FUN_00583260` = exp) + SFX; pan = mean of `clamp((x - cx) * 2000 / vw, +-2000) * v_i / 10000` |
| fire wall | cell record flag `& 8` (`FUN_004203e0(view+0xa08)`) | `sfx[90]` | yes | same |
| trees / objects | object def (objects.reg, `+0x44` DeadObject, `+0x40` FireObject, `+0x14` Phases): `DeadObject < 0 && FireObject == -2` = n44, other `DeadObject < 0` = **nothing**, `DeadObject >= 0`: `Phases >= 2` = n34, else n58 | random one-shot below | no | SFX only (**no attenuation**), pan = mean of `trunc(pan_i * v_i / 10000)` |

Loops are kept between passes: a playing loop only gets new volume / pan, and stops when its source count is 0; all stop at the mission teardown
(`0x41bddd` from `0x48da92`). **Every ambience play passes priority `0xdc`** (`push 0xdc` at `0x41bbcb`, `0x41bd80`; the old formula from the attenuation was wrong).
Per source cell: `d = trunc(sqrt(dx^2 + dy^2))` from the view centre `(vx + (vw >> 1), vy + (vh >> 1))`, `v = max(0, trunc(10000 - (exp(d >> 3) - 1) * 100))`
(constants `1.0`, `100.0`, `10000.0` at `0x5cb138`/`40`/`50`), attenuation of a loop = `max(v_i - 10000)`, pan_i = `clamp(trunc(dx * 2000 / vw), +-2000)`, loop pan =
`trunc(sum(trunc(pan_i * v_i / 10000)) / count)` (CONFIRMED; the cell tests above are the exe's, `v` is 0 from 5 `d >> 3` on, so only the 40 nearest cells are audible).
The objects are counted **only on a timer pass** (`view+0x49c0` expired), the one-shot needs `total = n34 + n58 + n44 != 0`, and the timer is re-armed only
then (`0x41bdb0`; with no object in the window the exe rescans every frame, the engine retries every 250 ms, DECISION). One-shot id (CONFIRMED `0x41bc84`-`0x41bd7c`):
`r = rand(total - 1)` (inclusive, `FUN_0051fa25`); `base = 600; if n34 <= r: base = 620; if n34 + n58 <= r: base += 20` (forest 600 = n34 animated trees, 620 = n58
static bushes, 640 = n44 dead trees, each in proportion to its count); night (`hour < 4 || hour > 19`, hour `= (((clock >> 4) + 360) / 60) % 24`, clock = `client+0x408`)
adds 10; `id = base + rand(10)` with `push 0xa`, **inclusive 0..10** (a day roll can reach the block's first night id, 610 / 630 / 650), re-rolled until the slot exists
(ids 600-609 / 610-619 forest day / night, 620-629 / 630-635 steppe, 640-647 / 650-658 north). Pan = `trunc(sum of every counted object's weighted pan / total)`
(the argument order of the play is volume = SFX bus, pan, loop 0, priority `0xdc`). Next one-shot at `now + 5000 + rand/7` ms.

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
| `FUN_0040d9b2` cases `0x92` (sub 2, 5-8, `0x10`...), `0x91`, `0x93`, `0xb9` | a message-line text is posted | 15 `message`, **priority 0x64**; sub 1 "No way", 3, 4 and the gold line are silent; which fire in single player: below |
| `0x43d8a4` msg `0x474` | options slider test buttons | SFX: 100 (`units/sword`), prio `0xdc` |

**Table ids 3-6 and 11-13 (`click02`, `click03`, `click_ok`, `error`, `letter1-3`) are never played (CONFIRMED).** All 59 callers of the lookup `FUN_00420eb0` on
the table `0x627740` were listed: the constant ids are 1, 7, 8, 14, 15, 16, 50, 90, 100 and the sets `500 + n` / `600..658`; the variable ones are the generic button
class `0x4d5c41`, the projectile ids of `0x4151b7` / `0x4156c5` / `0x415ae7` and the ambience. The button class has a compiler quirk: its `switch (+0x70)` maps
`0x445` -> 4 (`click03`) and `0x45a` -> 1 (`click00`) but **every case falls through** (`0x4d5c71`-`0x4d5c7f` have no `break`), so the id is always the default **2**
(`click01`): `click03`, `click00` for those two window ids and the rest are dead. No town window uses the table ids either: the town scenes load their own
files by path (`FUN_004384f0`, [town-scenes](town-scenes.md)). So the table's ids 3-6 and 11-13 have no caller in the GOG exe.

**The `message` (15) sites in single player (CONFIRMED by sender and handler):** all `0x92` sites test `client+0x404 & 1` (a mission) and play at priority 100.
Fire: sub 2 (skill-up: built), **sub 5 / 6 / 7** (the typed cheat codes of the chat line, `FUN_004f3d68`: 5 `main.txt[0xde]` "Player X has decided to become
super-lame and cheat!", 6 `[0xe0]` "... is grasping at straws! This is not a code...try again.", 7 `[0xe2]` "... has succesfully entered a cheat code!"; the engine builds
sub 7 for `#show map` / `#hide map`: line (5000 ms) + sound; the cheat activation and the other codes are not modelled), `0x91` (chat echo: built). Never in single
player: sub 8 (an "Enemy N Mercenary" network line, `0x4f70e2`), sub `0x10` / `0x20` / `0x40` / `0x80` (quest events: the queue `0x68d360` is fed by the
multiplayer-only quest code `0x52f8e2`, [items 14](../data/items.md#14-quests-and-the-item-upgrade-message-0x38)), `0x93` (sent by `FUN_00505697` only inside the
`server+0x74 != 0` branch of the chat handler and by the "kicked from server" client routine `0x492a3a`: multiplayer). `0xb9` (the "Diplomacy changed: A > B" line, three
sites `0x414342`, `0x4144cd`, `0x414658`, sender `FUN_00504e87`) is reachable: at player start (`0x4f21a8`) and from script instant 10 "Change diplomacy"
([triggers](triggers.md)); it prints only for a player that is not computer controlled and whose stored relation word changed. The engine has no diplomacy matrix
and the instant is a no-op, so `0xb9` stays unbuilt.
**Item pick-up and gold (CONFIRMED, exhaustive):** the 58 callers of the play routine `0x45aa2f` were all listed; none belongs to the client cases `0x67` (gold: a text line
through `0x4021fe` only) or `0x6a` (`0x41356d`: removes the view entry; its server sender is `FUN_00504b3a`). The only audible reaction is the hero's pickup voice (2.3).
**The options speech-test button (`0x43da49`, wParam 8):** plays the sound object at `[0x627d48]`, which is `select/2` of the generic bank `m_fighter` (the array of two 0x6c
banks `0x627d40` built by `0x4c4bf1`-`0x4c4d5d` from `sfx\characters\<m|f>_fighter\...`); that folder does not exist in the install, so the **speech test is silent in the GOG
game** (a missing file fails silently, 3.1). The SFX test (wParam 7) plays table id 100 `units/sword`.

### 2.6 Not built (documented)

Town scenes and shops (`0x438570` / `0x4a0ff0` loops, enter / leave sounds, NPC speech `0x4dc84c`, shop speech `0x4b5ffa`; the town-window sounds are in 2.7): there are no town scenes yet (phase K
backlog; the shop sound slots and their files are in [town-shop 6](town-shop.md#6-sounds-music-and-tips)); the speech *names* are specified in [sound §4.3](../formats/sound.md#43-speech) and the player will reuse the same mixer. Script instant 37
"set music node" does nothing in the exe ([triggers §instants](triggers.md)).

### 2.7 Town window sounds and the shop speech (CONFIRMED)

* **`0x4be6b0` (druid shop load, vtable slot 32) and `0x4c03c2` (Kaarg shop load)** end like the human load: they start the scene sound `FUN_00438570` / loop `FUN_004a0ff0`
  and play the window sound object `+0xb0` once through `0x45aa2f` (speech volume `[0x6226a0]`, priority `0x80`) unless it is already playing (`0x4bebef`,
  `0x4c0901`); `+0xb0` is the shop's "start" clip (human `Shop\start.wav`, [town-shop 6](town-shop.md#6-sounds-music-and-tips)). **`0x4b978f`** (human shop, vtable slot 82)
  is the keeper idle player already described there: once 30 s + `FUN_004a0fd0(30000)` have passed since the last play (and no shelf animation `+0x240 & 0x70` runs) it replays `+0xb0`
  (same priority / bus) and arms the next with `FUN_004a0fd0(10000)`.
* **Shop speech `FUN_004b5ffa`** is the stock panel's override (vtable slot `0xa0`, panel vtable `0x5d0044`) of the base class's "take an item from this panel" virtual,
  called by the pick-up routines `0x4b242d` (`0x4b2544`) and `0x4b27ad` (`0x4b282b`): **picking up an item from a shelf** (carried item kind `+0x18` in 5..8, client
  mode `+0x5d8 == 2`) speaks with a **30 % chance** (`FUN_004a0fd0(100) < 30`, the CRT-backed draw): the folder by the town (`shop_kaarg` when the hero's town word equals
  `window+0x20ac`, `shop_druid` for `+0xfc`, else `shop`) and the first of `effects\%.2d` (`FUN_00438f3a`, an item's effect number), `books\%.2d` (`FUN_004b10b0`, a book's number), else
  `s%.2di%.2dp%d` (item class `FUN_0041e9e0` / index `FUN_00439e90`, `p = rand(3) + 1`); the previous speech object `window+0x20b0` is cut first, the new one plays at priority
  `0x80` on the speech bus, then the click slot `+0x20b4` plays. (INFERRED only that the virtual is the pick-up hook; the sequence is CONFIRMED.) `books\NN` is therefore a book number.

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

### 3.4 Gating by visibility (CONFIRMED: none)

Unit sounds are **not fog gated** in single player. The client calls the view-unit `animate` (vtable `+0x3c` = `0x46617c`) on every view of the object map
`view+0x9d0` each tick (`0x40bddb`); neither it nor its sound routines (`0x467cd2` swing, `0x467da8` cast frame, `0x467e42` wound / death) read the visibility `S`
(`view+0x7c`, set by the separate `+0x4c` = `0x468762` pass), and the server sends `0x73` for every creature (2.1a). A fight in the fog is heard, attenuated by the
distance only (no distance cutoff, no on-screen test: -41 dB at 30 cells). Spell-object sounds (2.2) come from server messages and are never gated either.
The engine plays every unit event (the former `dropped:fog` rule is gone).

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
`MusicEnabled` 0 or `-nomusic` = never started. The shell ([shell.md](shell.md)) requests `menu` (main menu, options) and `chrgen` (new game) through `set_playlist(name)`, the game screen starts the mission playlist and leaving a mission
calls `Audio.end_mission()`; there are no map / town / credits screens yet.

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
* **Director** (`engine/audio/director.py`, pure): per frame it takes the events, the camera and a clock, applies no fog gating (§3.4), the 1500 ms hurt throttle, the
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
duplicate) or `dropped:voices` (no voice), `dropped:cooldown`. A `#` header line records the session, seed and that UI sounds are absent.

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
  mission bit `client+0x404 & 1` is always set in a mission). `sound_events` is not dumped; `Simulation` clears it at the start of each step unless `keep_sound_events=True` (then the consumer clears it: `Director.drain`).
* **Sound sets.** `units.reg Sound` through `world.assets.unit_types()` (Parent inheritance already applied), cached in `World.sound_sets`; a world with no assets emits no unit-slot events. Slots <= 0 are empty.
* **Voice bank (`voices.bank_of`).** Reduced server id (`10210 -> 21`, unit-struct `+0x14c`): 1-6 = xbow, knight, druid, troll, orc, mage; 22 (`Fighter_Hero`) = igles; 23 (`Mage_Hero`) = dina; 21 (`Start_*`)
  by the template name `Start_<M|F><F|M>`: MF aldor, FF sagita, MM hildarius, FM galinel (the exe reads flag bits; the name letters are our stand-in). Wound / death use the bank for every human with type word
  1..0x17; with no bank (types 7-20: the generic `Man_*`) they are **silent** (the exe's `<= 0x17` test, no fallback to `Sound`). Real data check: `Man_Unarmed` has server id 1, so it speaks with the xbow bank
  (VERIFY BY EAR: generic humans in the campaign).
* **Order voices.** Candidates = the command's alive units with a bank; heroes (type >= 21) first, else the classes (stand-in for the three arrays of 2.3); index `min(size - 1, size * rand15 // 0x7fff)` from the audio RNG.
  The skip rule `+0x78 == 1` = the chosen unit was walking at the end of the previous frame (`Director.walking`, CONFIRMED meaning, 2.3); the `skip_voice` flag stays as an override. Only the viewer's own, non-AI commands speak; a select command speaks for its `unit_ids`.
* **Ambience.** Rules and constants are CONFIRMED in 2.4 (K11 round 2 replaced the earlier guesses: the classes, `rand(total - 1)`, `rand(10)` for the id offset, the pan mean, priority `0xdc`,
  objects counted only on timer passes). Object classes from the `objects.reg` fields (`ambience.object_class`): n44 21 records, n34 43, n58 22, the other 106 count for nothing. Fire wall = a `cell_fx` entry with slot 0. Window bounds
  inclusive, clamped `[8, size - 8]`. One timer serves the pass and the one-shot (`next = now + 5000 + rand15 // 7`, re-armed only when an object was counted; 250 ms retry otherwise, DECISION).
* **Director.** View in cells from the camera: `x // 32`, `view_w // 32` (floored). No fog gating (3.4). `dropped:missing` is a play with a null
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
2. ~~Fog gating~~ answered (3.4: the original plays unit sounds in fog); listen that a distant fight in the fog is just quiet.
3. The double sound of a unit-target cast (caster frame + object creation, same id).
4. Ambience: river loudness against the camera distance, fire-wall loop, forest one-shots (night), the 5 s spacing.
5. Wound sounds: the 1500 ms throttle, heroes use the voice bus, the death sound once.
6. Music: random start track, sequential wrap, zone theme changes on entering a zone (and the old theme repeating at every track end afterwards), silence after victory, `map.wav` after.
7. DirectSound's pan law against §5 (left / right balance at a screen edge).
8. Volume defaults: -700 mB buses against the engine's 74 %.
9. Generic `Man_*` humans (server id 1-6) speaking with a class bank when wounded; `Man_Axe` etc. staying silent (§9).
10. The cast sound timing (release tick) and the double cast sound, spell-object sounds at the caster's position.

## Open questions

- Gapless track change at a track end (the next track is loaded on the end event); whether `Channel.set_volume(l, r)` of SDL_mixer reproduces DirectSound's pan law at the screen edge (both by ear).
- What `view+0x1b8` bits 1 / 0x10 and `view+0x188` are (which hero lands in which of the three arrays of `FUN_0041da16`, 2.3).
- The `0xb9` "Diplomacy changed" line and the cheat-code activation / other cheat codes (`message` sub 5, 6): they need the diplomacy matrix and the cheat-code parser.

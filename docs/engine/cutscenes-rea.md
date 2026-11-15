# Cutscenes: what the exe does (REA round for the `cutscenes` step)

Facts are **CONFIRMED** (GOG `allods2.exe`, sha256 in [formats/README](../formats/README.md); routine address given) or **INFERRED**.
Format side (headers, fades, `.reg`): [shell 6](shell.md#6-videos). Triggers: [triggers 11](triggers.md), [town-worldmap 3](town-worldmap.md).
Corrections to shell.md 2 / 6 are in section 7.

## 1. `0x48f919(code)` (play the chapter videos, `this` = game object)

| Step (in order) | Fact | Routine |
|---|---|---|
| 1 | **Music is hard-stopped first, even when no video will play** (`game+0xc8` = music player; the same stop as "new playlist", [audio 157](audio.md)). Nothing in `0x48f919` restarts music: the next screen does (menu `0x421` -> `0x48b569` plays `music\menu.wav`). The Cut Scenes list (`0x43b`) restarts nothing, so music stays off while the list is open after a video (INFERRED from the absence of a call) | `0x459f2f` (called at `0x48f949`) |
| 2 | `if video.res is not mounted (0x5f17e4 == 0)`: **return now**: no mask bit, no registry write, no screen change (only the music stop happened) | `0x48f955` |
| 3 | `game+0x404 |= 0x2000` ("a video is playing") | `0x48f962` |
| 4 | **Seen mask** `0x5f1a04 |= 1 << code` (`code` is a 32-bit shift count) and at once **`0x440cd2` = the whole settings writer** (HKLM `SOFTWARE\Rage of Mages 2`: every option block + `Using VxD` = the mask). So the bit is set and persisted **before the first frame**; an abort does not undo it | `0x48f988-0x48f994`, `0x440cd2` |
| 5 | Loop `NN = 1 .. 99` (`cmp 0x64; jge`, `0x48f9b4`): path = `sprintf("video\%s\%02d.smk", cutpaths line [code], NN)` (`0x5f3ae8`; the line is `cutpaths.txt` line `code`, table object `0x6226b0`, accessor `0x474733`). **A missing file does not stop the loop**: it just goes on with the next NN (only `01` is installed, so the rest is 98 failed opens) | `0x48f9c1-0x48fa13` |
| 6 | On the **first file that opens** only: cursor update `0x4268c4`, **cursor hidden** (`0x426342`, object `0x604500`, hide counter: the software cursor is erased), **screen cleared to colour 0** (`0x456348(rect 0x621410..1c, 0)` between `0x452bde` / `0x452c3a` / `0x453788`; the whole screen rect, not just the 640x480 area). A flag makes this happen once | `0x48fa1b-0x48fa68` |
| 7 | Play the file with `0x48fc2e(path)` (section 2). Result 0 (aborted) -> **leave the NN loop** (the remaining NNs are skipped); result 1 -> next NN | `0x48fa87-0x48fa90` |
| 8 | After the loop: `game+0x404 &= ~0x2000`; **cursor shown again** (`0x426381`) if it was hidden; **screen cleared again** to colour 0 (same 4 calls). No redraw of the previous screen and no message is posted here: the callers redraw / post (menu `0x421`, list `0x43b`, town / map `0x48b419`) | `0x48fabb-0x48fb15` |

`ret 4`: one stack argument, `this` in ECX. There is no "play from the list with a different mask rule": the list calls the same routine.

## 2. The player `0x48fc2e(path)` and the per-frame step `0x4c399a`

| Fact | Routine |
|---|---|
| Set-up order: `0x4c3679` (ctor: `SmackUseMMX(1)`, **`SmackSoundUseDirectSound(0)`** = Smacker makes its own DirectSound, **no `SmackVolumePan` / `SmackSoundOnOff`-volume call exists in the exe** (imports at `0x6cf174-0x6cf2a4`: `SoundUseDirectSound`, `UseMMX`, `Wait`, `NextFrame`, `Blit`, `DoFrame`, `BlitSetPalette`, `BufferFocused`, `SoundOnOff`, `BlitOpen`, `Open`, `BlitClose`, `Close`, `BufferClose`, `ToBuffer`, `BufferOpen`) -> the video audio is **independent of the game's sound / music / speech settings** (full Smacker default volume, centre pan); the `SmackSoundOnOff(smk, 1)` at open only enables it) | `0x4c3679`, `0x4c3bee` |
| Surface: `0x4c37e8(DAT_0061b528)` stores the DirectDraw surface and derives the blit format with `0x4c3819`: 8-bit -> 0, **565 -> `0xc0000000`, 555 -> `0x80000000`**, anything else -> message box "Unsupported pixel format" (title "Smacker Error"), play aborts (the engine is 16 bpp, [shell 2](shell.md#2-startup-confirmed-initinstance-0x480cf2-0x4818d1)) | `0x4c3819` |
| **Position**: `0x493df0(X0, Y0 + 0x3c)` is set first (`X0 = 0x621420`, `Y0 = 0x621424`, the 640x480 centring offsets), then the `.smk` is opened and its size read (`0x4c3f89`); **if the height is `0x1e0` (480) the origin is reset to `(X0, Y0)`**, so 640x480 files sit at the 640x480 origin and 640x360 files at **`Y0 + 0x3c` = 60 px** (the letterbox). Origin / size are stored at `+0x358/0x35c` and `+0x350/0x354` of the player (that the blit uses them as the destination is INFERRED; pixel-exact check needs a real frame). The request size passed to the open is `0x280 x 0x168` = 640x360 | `0x48fc2e` (`0x48fc50-0x48fc9d`), `0x4c3ff1` |
| Open: whole file read into memory, `SmackOpen(buf, 0xff000, -1)`; `SmackBufferOpen(hwnd, 0, w, h, w, h)` + `SmackToBuffer` (centred in the buffer: `(buf - w) >> 1`); `SmackBlitOpen(format | 1)`, or `| 2` (2x pixel doubling, flag `+0x368 = 1`) when `2w <= dest width && 2h <= dest height`. **The installed files are 640 wide, so on 640 / 800 / 1024 screens the doubling never applies** | `0x4c3bee`, `0x4c3e95` |
| **Main loop** (`0x48fc2e`): `PeekMessageA(remove)` drains every queued message; **abort** (return 0) on `WM_QUIT 0x12`, `WM_CLOSE 0x10`, **`WM_LBUTTONDOWN 0x201`, `WM_RBUTTONDOWN 0x204`, `WM_KEYDOWN 0x100`, `WM_SYSKEYDOWN 0x104`**. So: **any key press (not release, not WM_CHAR), left or right button press**; the middle button, button releases, mouse moves and every other message do nothing (they are translated / dispatched normally). For QUIT / CLOSE the message is also dispatched first, so the application still quits after the abort. Then one frame step `0x4c399a(1)` | `0x48fc2e` (`0x48fcd5-0x48fe0c`) |
| **Frame step `0x4c399a(1)`** (bit 0 set): **busy-wait `while (SmackWait(smk))`** (`0x4c397d`; the wait for the next frame time, messages are NOT pumped inside it), `SmackBufferFocused` (false = window not focused: skip drawing, return 1, i.e. spin), fade / pan records (`0x4c4561`, `0x4c4618`, `0x4c38d1`, [shell 6](shell.md#6-videos)), `SmackBlitSetPalette` (scaled palette while a fade is active, else the raw palette only when it changed), **`SmackDoFrame`**, DirectDraw `Lock` (vtable `+100`) of the surface, `SmackBlit` (11 args: dest ptr / pitch from the lock, x, y, ...), `Unlock` (`+0x80`), and if **`frame == frameCount - 1` return 0 (finished)**, else `SmackNextFrame` + pan step `0x4c46d7`, return 1 | `0x4c399a` |
| **Late frames**: the exe never skips; `SmackWait` is spun until due, a late frame simply starts at once (`SmackWait` returns 0 when due or late) and every frame is decoded and shown in order (`DoFrame` / `NextFrame`, no `SmackSkip` use). So a slow machine plays slower; frame-dropping, if any, is inside smackw32 (the DLL is packed, not read) | `0x4c399a` (INFERRED for the library side) |
| End: the **last frame is shown and the step returns 0 at once** (no wait for its duration); a failed `Lock` / `Unlock` also returns 0 = "finished", not "aborted". `0x4c4543` / `0x4c3790` then free the fades and close Smacker. Result of the player: **1 = ran to the end, 0 = aborted by a message** | `0x48fe0c`, `0x4c3790`, `0x4c4543` |

## 3. The start-up chain `0x48fb2a` and its caller (`InitInstance`, `0x480c8d`)

| Fact | Routine |
|---|---|
| `0x48fb2a`: music stop (`0x459f2f`); no `video.res` -> return 0; else `game+0x404 |= 0x2000`, cursor update + hide, clear screen, `0x48fc2e("video\logos\publisher.smk")`; **only if it returned 1** `0x48fc2e("video\logos\nival.smk")`; then mask bit cleared, cursor shown, screen cleared; returns the result of the last player run (0 when either was aborted). It does **not touch the seen mask** | `0x48fb2a` |
| Caller: `if (!-startserver && !(two other switches at 0x5f3220 / 0x5f3228) && 0x48fb2a() != 0) 0x48f919(0)`; **then always post `0x421` (main menu)**. So: publisher aborted -> nival skipped **and intro skipped**; nival aborted (returns 0) -> intro skipped; any abort goes straight to the menu. A key press aborts only the clip that is running and the rest of the chain | `0x480c8d` (`InitInstance`; shell.md calls the region `0x4818a0`) |
| Intro = `0x48f919(0)`: sets bit 0 and writes the registry even if aborted (step 4 above) | `0x48f919` |

## 4. The seen mask (registry `Using VxD`, DWORD, `0x5f1a04`)

| Fact | Routine |
|---|---|
| **Initial value in the image = 1** (`01 00 00 00` at `0x5f1a04`). At start-up `0x440bb7` reads the value (`RegQueryValueEx`, 4 bytes) and **a stored 0 becomes 1**; with no key / no value the image value 1 stays. So **bit 0 (the intro) is always set**: a fresh install lists exactly one row | `0x440bb7` (`0x440c90-0x440cb1`) |
| Writers of bits: only `0x48f919` (`or 1 << code`, `0x48f988`); `0x487c48` is the reader in the list builder. Code 0 is set by the start-up intro and, redundantly, by the image default | `0x48f988`, `0x487c48` |
| Persistence: `RegSetValueEx("Using VxD", REG_DWORD, &mask)` inside `0x440cd2` (the all-settings writer), called **at every `0x48f919` that plays (step 4)** and at exit ([shell 3.2](shell.md#32-no-options-entry-in-the-main-menu-confirmed)). So the mask survives a crash and a quit before the video ends | `0x440cd2` (`0x440d7e`) |
| Semantics for the engine: a 32-bit bit set, bit n = "the chapter video n has been started at least once"; never cleared by the game; shared by all saves (it is an application setting, not part of `game%d.sav`) | - |

## 5. The Cut Scenes screen (`0x43b`, handler `0x487bfb` in `0x4852d8`; close handler `0x4891d8`)

| Fact | Routine |
|---|---|
| Entry: message `0x43b`. **No video.res -> post `0x421` (menu)** at once. Else build a string array: for `n = 0 .. 31`, if mask bit n is set, add the line n of **`cutscene.txt`** (text table object `0x622660`, loaded with `cutpaths.txt` at `0x6226b0` by `InitInstance` `0x4816cb` / `0x4816da`). **Rows = the set bits in ascending bit order; titles are by bit number**; no row for unseen chapters. A set bit past the last text line (the file has 6 lines) would show an empty / foreign string (not reachable: codes are 0..5) | `0x487bfb-0x487c72`, `0x474733` |
| Window: class `0x5cd008` (a text-window family dialog, derived from `0x5cc288`; ctor `0x44d428(id 0x11, 100, 0x1e, 0x21c, 0x1c2, rows)` -> `0x4431dd`: caption string `dialogs 0x99`, **case 1 = Ok + Cancel**), stored in `game+0x3c0`, shown modal by `0x48b33b` (mode bit 8). The ctor rect gives only the size 440x420; the common snap [ui-layout 11.4](ui-layout.md) makes it **392 x 360**, centred on the real screen (`(640-392)/2, (480-360)/2` = (124, 60) at 640x480) | `0x487c72-0x487cf5`, `0x4431dd`, `0x4dc4fc` |
| Layout (build slot `0x443238`, list builder = slot `+0x88` `0x44d475`; numbers relative to the window): heading label = `dialogs 0x99` (id 1, font1, centred flag 2) at `(0x28, 0x20)-(W-0x28, 0x38)`; list rect `(0x28, 0x44)-(W-0x28, h-0x70)`; the list widget (class vtable `0x5cffc8`, ctor `0x4d8417`, id 2, font `DAT_0061fac0`) takes that rect **minus 0x18 on the right**, **row pitch = font height + 4**, visible rows = `rect height / pitch` (`0x4d8417`), and a **scroll bar** (`0x4da54d`, id `0x29b`, 0x18 wide) fills the strip at its right. Buttons (case 1, y `h-0x3c .. h-0x24`): **Ok** (id 4, `dialogs 0` = "Ok", message `0x445`, flag `0x10` = default) at `w/7 .. 3w/7`, **Cancel** (id 5, `dialogs 1` = "Cancel", `0x446`) at `4w/7 .. 6w/7` | `0x443238`, `0x44d475`, `0x4d8417` |
| No background bitmap of its own: it is the standard dialog frame (`lm.256` frame + drop shadow, [ui-layout 11.4](ui-layout.md)) over the main-menu picture that stays on screen (INFERRED: the menu window is not hidden by the modal show; no `Image` is created by `0x487bfb`) | `0x487bfb` |
| **Selection**: the list widget keeps the selected row in `+0x88` (default -1); after creating it the builder sets it to the **global `DAT_00622820`** (`0x44f110`), initial value **0**, so **row 0 is selected on first open and the last selection is restored on every re-open** (the global is written only by Ok, below) | `0x44d475`, `0x622820` |
| **Ok** (`0x445`; the close handler `0x4891d8`, branch `+0x3c0`): `DAT_00622820 := list.selectedRow` (`0x44f0f0` on child id 2), then **`0x48f919(DAT_00622820)`**, then post **`0x43b`** again (the list re-opens, rebuilt from the mask). **Cancel / Esc (`0x446`) -> post `0x421`** (main menu); Esc is the class's slot-`0x6c` handler (`0x4dc595`) = `0x446`; Enter reaches the focused list first, then the default Ok button (INFERRED from the shared dialog code, ui-layout 11.4) | `0x48a7c9-0x48a81f` |
| **QUIRK (CONFIRMED)**: the argument of `0x48f919` is the **row index**, not the bit number; there is no row -> code mapping. With a contiguous mask (bits 0..k) the two are equal. With a sparse one (e.g. bits 0, 1, 2, 3, 5, the druids' ending without the knights') the list has 5 rows and row 4 plays code 4 (knights), so bit 5 is never replayable from the list unless bit 4 is also set. Engine: reproduce (original behaviour) or fix with a DECISION | `0x48a7f4-0x48a7fb` |
| Double click / Enter on a row / mouse wheel / scroll-bar drag: the list class's mouse slots (`0x5cffc8` slots `0x4d87..`, `0x4d8d14`, `0x4d8f89`) were **not decoded**; the shared list shows the same open question as [save-ui 5](save-ui.md) | open |
| Main menu button 2 (`CUT SCENES`, message `0x43b`): enable state = the menu's disabled mask `DAT_00627590` only (set to `0x35` = buttons 0, 2, 4, 5 off when the CD / registry check `0x62282c` fails, [shell 3.1](shell.md#31-main-menu-confirmed-class-0x5cec48-ctor-0x4a71d6-loader-0x4a7657-paint-0x4a7b3f-mouse-0x4a7d0d-0x4a813c-0x4a81a3)); `0x48b569` ORs `0x10` (LOAD) when no save exists. **It does not depend on the seen mask**: the button is always enabled on a normal install, and the list is simply short | `0x48b569` (`0x493bc0(DAT_00627590 [| 0x10])`) |

## 6. Triggers (all callers of `0x48f919`: `0x480c8d`, `0x4852d8`, `0x4891d8`)

| Site | Condition / argument | Routine |
|---|---|---|
| Start-up | `0x48f919(0)` after the publisher + nival chain returned 1 and none of the three skip switches is present | `0x480c8d` (`0x4818f1` region) |
| Mission victory, message `0x41d` | `code` = out-parameter of **`ScenarioLeaveLocation(&code)`** (Scenario.dll ordinal 6, pointer `0x627160`); played when **`code >= 0`** (`cmp [..], 0; jl`), after `SetPartyPoint`, the recruit and before the ending test `0x493da0` | `0x486c40-0x486cc8` |
| **Town leave, message `0x42d`** (NOT "world-map entry"): only when **`GetCurrentLocation` is a town (`0x473a20 == 2`)**: `SetPartyPoint`, `ScenarioLeaveLocation(&code)`, **`code >= 0` -> `0x48f919(code)`**, then if the town id is 1 `window+0x1b0 := 1` (the intro walk) | `0x487d34-0x487dd5` (call at `0x487daf`) |
| Cut Scenes list Ok | `0x48f919(selected row)` (section 5) | `0x48a7fb` |
| Message `0x436` | `0x48f919(0)` then `WM_CLOSE`: posted from one switch case at `0x485f5a` (a network-side path, not decoded; INFERRED out of scope) | `0x4878e9-0x4878f1` |

Which codes the DLL returns: [triggers 11.5](triggers.md#115-end-of-mission-flow) (10 -> 1, 30 -> 2, 70 / 80 -> 3 for the second of the pair, 110 -> 4 or 5). The town-leave site gets whatever the DLL returns for a town (no town case has been read there; INFERRED: always -1).

## 7. Corrections to the earlier notes

- shell.md 6 "`NN = 1, 2, ... while the file exists`": the loop **tries all 99 NNs and skips the missing ones** (`0x48f9b4`); only an abort stops it.
- shell.md 6 "world-map entry (`0x487daf`)": that site is **leaving a town** (message `0x42d`), as town-worldmap.md already says.
- shell.md 2 / 6 "aborts on a key press or a mouse button (either)": exact list in section 2 (key down incl. Alt-key down, left and right button **down**; not the middle button, not releases).
- shell.md 6 "sets bit `code` of the seen mask": it sets it **before** the first frame and **writes the registry then**.
- The Cut Scenes list passes the **row index** to the player (section 5 quirk), not the bit number.

## Open questions

- Double click / Enter / wheel behaviour of the list widget `0x5cffc8` (decode its mouse and key slots; the Load and Save lists share the base).
- Exact on-screen blit destination of the 640x360 clips (setters decoded; the `SmackBlit` argument registers `+0x358/0x35c` -> `x, y` mapping inferred): compare one real frame against the picture.
- Frame dropping inside `smackw32.dll` when late (the DLL is packed; the exe never skips).
- Music after a video from the Cut Scenes list: nothing restarts it until the menu `0x421` (INFERRED from the call graph); check in a real game.
- What the town-leave `ScenarioLeaveLocation(&code)` returns for towns 2 and 3 (any chapter video there?).
- Source of message `0x436` (play intro + close).

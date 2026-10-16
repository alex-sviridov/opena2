# Fonts: `fontN.dat` metrics + `fontN.16` / `fontN.16a` glyphs

Code: `allods2/graphics/font.py`. Tools: `tools/validate_fonts.py`;
`tools/font_contact.py` → `out/contact/fonts.png`.

A font = a sprite file with one glyph per character ([sprites](sprites.md),
`.16` or `.16a`) + a `.dat` with one width per glyph, same stem.

## Files

| Font | Glyphs | Cell (w × h) | Chars | `.dat` | Global (`FUN_00464849`) |
|---|---:|---|---|---:|---|
| `font1/font1.16` | 224 | 16 × 15 | 0x20–0xFF | 896 B | `DAT_00629c88` |
| `font2/font2.16` | 224 | 8 × 10 (char 0x80: 9 × 10) | 0x20–0xFF | 896 B | `DAT_0062a6c8` |
| `font3/font3.16` | 64 | 8 × 6 | 0x20–0x5F (digits, a few signs drawn) | 256 B | `DAT_0062aff8` |
| `font4/font4.16a` | 224 | 16 × 16 | 0x20–0xFF | 896 B | `DAT_0062af90` |

`font5/font5.ttf` is not opened by the exe. CONFIRMED (a2mgr
`FUN_1000ed30`): a2mgr loads it into a GDI+ private collection
(`GdipPrivateAddMemoryFont`; "FATAL ERROR: can't load …" and exit on
failure) and draws its own widgets' text with `GdipDrawString` (patch 28
removed SDL/SDL_ttf). Five lazy font objects (`0x1007b9f0`–`0x1007ba0c`)
in widget methods `0x10029d90`–`0x1002c610`, sizes 10, 12, 13, 14, render
the widget string (`+0x28`) into cached images (`+0x40/+0x44`), bold/italic
from `+0x48/+0x49`. INFERRED: a2mgr menu and login screens (nearby
resources `locale/ru/graphics/mainmenu/…`).

CONFIRMED (all four, `tools/validate_fonts.py`): each `.dat` is exactly 4
bytes per glyph, every glyph stream consumed exactly, no header.

## `.dat` layout

`u32 width[g]` at `4·g` for character `0x20 + g`.

- CONFIRMED (`FUN_0046365e` `.16`, `FUN_00463a16` `.16a`): the constructor
  appends `.16`/`.16a` (strings `0x5fb240`/`0x5fb24c`), loads the sprite
  (`FUN_00426ce8` → vtable `0x5d5370`, or `FUN_0042a71b` → `0x5d5488`),
  reads the **whole** `.dat` (`FUN_004ebe03`/`FUN_004ec0dc`; no length
  check). Object `{vtable, sprites, widths, spacing}`, spacing = 2 for all
  four (`FUN_00464849`).
- CONFIRMED (`FUN_00463a16`): font4 rebuilds its shade table with
  `FUN_00426be0(16, 4, 0)` (FADE16, [palettes §5](palettes.md)).
- CONFIRMED (data, 732 of 736 glyphs): `width[g]` = index of the glyph's
  **last drawn column** (0 for blank); ink starts at column 0, so with
  spacing 2 one empty column follows each glyph. The 4 exceptions have
  `last column + 1`: font1 0xB3, font2 0x80, font4 0x89 and 0xE0
  (INFERRED: three are the a2mgr remap targets below, probably redrawn by
  the patch).

## Character codes

NUL-terminated bytes; glyph `g = (map(c) − 0x20) & 0xFF`. `map` =
`FUN_00461da1` + a2mgr hook Ordinal_26 (`0x10003910`, from `0x461db6`).
CONFIRMED:

```
map(c):
    if DAT_0062c9c4 != 1: return c                 # remap off
    if c == 0xC1: return 0x80                      # a2mgr
    if c == 0xF0: return 0xE0                      # a2mgr
    if c == 0xF1: return 0x89                      # a2mgr
    if 0x80 <= c <= 0xAF: return c + 0x30          # exe
    if 0xE0 <= c <= 0xEF: return c + 0x10          # exe
    return c
```

INFERRED (glyph shapes): 0x20–0x7F ASCII, 0x80–0xA5 cp437 Latin (Ç ü é …
ñ Ñ), 0xB0–0xDF Cyrillic А–п, 0xE0 Ё, 0xE1 ß, 0xF0–0xFF р–я. With the
remap, text is cp866: А 0x80 → glyph 0xB0, р 0xE0 → 0xF0, Ё 0xF0 → 0xE0,
ё 0xF1 → 0x89 (the ë glyph). font2 has small capitals for lower case.

### The remap switch `DAT_0062c9c4`

CONFIRMED (`0x479d28`–`0x479d80`, a2mgr Ordinal_81 = `0x10012c70`): the exe
reads `data\main\id` (string `main\id` `0x5fbbe0`) and takes its **last
character − `'0'`** (shipped `russian 1` → 1). The storing instruction was
overwritten by `jmp [0x6de516]` → Ordinal_81, which writes `1` to
`0x62c9c4` (then redoes the overwritten `push 0x10`, returns to
`0x479d82`): the remap is **always on**; implementation default
`cyrillic=True`. INFERRED: the original stored the digit
(`mov [0x62c9c4], edx` fits the 6 bytes); the shipped `.old` exe is
patched the same way, so unverifiable.

Other users of the flag (CONFIRMED):

| Routine | Does |
|---|---|
| `FUN_0047a0f5` (+ a2mgr Ordinal_25 at `0x47a11e`) | one typed char cp1251 → cp866: `0xC0–0xEF − 0x40`, `0xF0–0xFF − 0x10`; a2mgr adds `0xA8 Ё → 0xF0`, `0xB8 ё → 0xF1`, `0x80` unchanged; others unchanged. Used by text inputs (6 callers, e.g. key filter `0x43d664` that a2mgr Ordinal_24 jumps to for `c ≥ 0x20, c ≠ 0x7F`) |
| `FUN_0047a169` | lower-case one cp866 byte: `0x80–0x8F + 0x20`, `0x90–0x9F + 0x50`, else C `tolower` |
| `FUN_00479f82` | same on a string (chat name completion `FUN_0043db33`) |

a2mgr's own edit fields (`0x1002a740`) apply the same 1251 → 866
conversion.

### 0xC1: the star

CONFIRMED (a2mgr `FUN_1002c700` via Ordinal_122 at `0x43bce4`; patch 28
"Names of magical items are now highlighted with different color depending
on item level"): a2mgr rebuilds the start of the item description in exe
buffer `0x624fb0`: optional colour escape, **N bytes 0xC1**, item name,
`%[*]`. 0xC1 maps to glyph 0x80, redrawn in **font2** as a five-pointed
star (a width exception); in font1/font4 it is still Ç.

Item property list at `+0xc`, count at `+9`; entry = `id` (u8) + value:
4 bytes for id 1, 3 bytes for 0x0d and 0x2c–0x30 (first byte used; these
count twice), else 1 byte. N = property **0x27** (0 if absent/negative).
The escape is written only when property **0x33** exists and
`(u16 item+6) & 0xfe00 ≠ 0xe00`: N = 1 → `%[234,102,102]`; 2 →
(79, 222, 93); ≥ 3 → (207, 53, 196); N = 0 with some property 1 = 2 →
(216, 191, 0); otherwise (158, 158, 217). INFERRED: 0x27 = item level /
stars, 0x33 = magic item (no `stats.txt` labels: server additions).
Ordinal_127 (`FUN_1002cba0`) appends `#<name> +N%` for property 0x1a
(patch 29, "Damage Bonus +%").

A byte past the glyph table (≥ 0x60 in font3, or < 0x20 when drawn) reads
past the game's tables (undefined); the implementation draws nothing and
advances by `spacing`.

## Measuring: `FUN_00461e19`

CONFIRMED, not hooked.

```
measure(s):
    total = 0
    for i over s:
        c = s[i]
        if c < 0x20: continue                      # control bytes count 0
        if c == '~':
            if s[i+1] != '~': continue             # lone '~' counts 0
            i += 1                                 # '~~' counts one '~'
        g = map(c) - 0x20
        total += width[g] + spacing
        if g == 0: total += height(glyph 0) >> 1   # space
    return total
```

`%[...]` escapes are **not** recognised here: they count as glyphs when
right-aligning or centring.

## Drawing a `.16` font: 0x4637f1 + a2mgr

CONFIRMED: `0x4637f1` (font vtable `0x5d74f0` slot 5) starts with
`jmp [0x6de5aa]` = a2mgr **Ordinal_125** (`0x10005a00`), which redoes the
prologue, saves the caller's colour table (arg 5), returns to `0x4637fa`;
in the loop `jmp [0x6de5ae]` at `0x4638b1` = **Ordinal_126**
(`0x10005dd0`) calls the escape parser `FUN_10005a20` before each
character. `colours` = 16-entry table of 16-bit pixels indexed by the
4-bit glyph pixels (blit `FUN_004593a1` via vtable `0x5d5370 + 0x34`).

```
draw16(x, y, s, flags, colours):
    original = colours
    if flags & 1: x -= measure(s)                  # right
    if flags & 2: x -= measure(s) >> 1             # centre
    if flags & 4: y -= width(glyph 0)              # bottom   (width, sic)
    if flags & 8: y -= width(glyph 0) >> 1         # middle   (width, sic)
    i = 0
    while i < strlen(s):
        i, colours = escape(s, i, colours, original)   # a2mgr, at most one per position
        if i >= strlen(s): break
        g  = map(s[i]) - 0x20
        g2 = map(s[i+1]) - 0x20                        # s[len] = NUL
        if g == 0x5e and g2 != 0x5e:                   # '~' + char: underline it
            line(x, y + height(0), x + width[g2], y + height(0), colours[15])
        else:
            if g == 0: x += height(glyph 0) >> 1       # space
            else: blit16(x, y, glyph g, colours)
            x += width[g] + spacing
            if g == 0x5e and g2 == 0x5e: i += 1        # '~~' draws one '~'
        i += 1
```

- CONFIRMED (`0x5d5370` slots 8/9 = `FUN_00426c16`/`FUN_00426c41`):
  `width(n)`/`height(n)` = sprite record n's `w`/`h`; vertical alignment
  really uses glyph 0's **width**, the space its **height** (equal for
  font4).
- CONFIRMED (`FUN_0045ba0c`): `line` = clipped Bresenham, one 16-bit
  colour; the underline is horizontal, `width[g2] + 1` px, one row below
  the cell, brightest colour; `~` does not advance the pen (INFERRED:
  button hotkey letter).

### Colour escapes (a2mgr `FUN_10005a20`)

CONFIRMED. Only when the caller passed a table (`original != 0`),
`s[i] == '%'`, `s[i+1] == '['`, and a `]` before the NUL. Body: `*` → back
to the caller's table; 3 chars, no comma → hex `R G B`, each `d·17` (`F80`
= 255, 136, 0); 6 chars, no comma → hex pairs; contains a comma → up to 3
decimal fields of ≤ 3 chars, missing = 0; anything else (or a negative,
i.e. unparsable, component) → not an escape, `%` drawn as a glyph. If the
caller's table is the default `0x62afb8` (`FUN_00463a06`, constant
(8, 8, 8), [palettes §6](palettes.md)) the escape is skipped but colour
unchanged; otherwise the new table is a static RGB565 ramp at `0x1007b644`:

```
for k in 0..15:
    r5 = (k·R / 15)·31 / 255
    g6 = (k·G / 15)·63 / 255
    b5 = (k·B / 15)·31 / 255
    ramp[k] = ((r5·0x40 | g6) << 5 | b5) & 0xFFFF          # integer division
```

Ordinal_126 runs once per position: of two consecutive escapes only the
first parses; the second `%` is drawn.

## Drawing a `.16a` font: `FUN_00463bbd`

CONFIRMED, vtable `0x5d7510` slot 5, not patched.

```
draw16a(x, y, s, flags, shade):
    alignment as draw16
    for c in s:
        g = map(c) - 0x20
        if g == 0: x += height(glyph 0) >> 1
        else: sprite.draw(x, y, g, shade, 0)       # vtable 0x5d5488 + 0x18
        x += width[g] + spacing
```

No `~` or `%[...]` handling (drawn as glyphs). The glyph blit
(`FUN_0042a740`) uses `shade` or, if null, the font's FADE16 table, and
the `.16a` blitter `FUN_0045db6b`. Callers pass a gradient row
([palettes §6](palettes.md)).

## Drop shadow: `FUN_004627f6`

CONFIRMED. Slot 6 of both font vtables returns the **shadow table**:
`.16` → `FUN_00463a06` → `0x62afb8` (constant (8, 8, 8)); `.16a` →
`FUN_00463d18`, a black-gradient row. Most text goes through:

```
draw_shadowed(x, y, s, flags, colours, off):
    draw(x + off, y + off, s, flags, shadow_table())   # slot 5
    draw(x,       y,       s, flags, colours)
```

Hence the escape parser leaves `0x62afb8` alone: the shadow keeps its
colour while the second pass is recoloured.

## Callers: colours and flags

CONFIRMED (all 152 `FUN_004627f6` call sites): with literal arguments
`off` is 1 almost everywhere; `flags` 0 (left), 1 (right) or 2 (centre),
8 (vertical middle) rare. Tables per kind of text:
[palettes §6](palettes.md#which-text-uses-which-table).

## Worked example

font1, grey ramp, `~Ok` at (0, 0), remap off: `~` + `O` (g 0x5e, 0x2f) →
underline x 0…`width[0x2f]` = 0…11 (12 px) at y 15 in colours[15], x
stays 0; `O` → glyph 0x2f at (0, 0), x = 0 + 11 + 2 = 13; `k` (0x4b) at
(13, 0), x = 13 + 7 + 2 = 22. `measure("~Ok")` skips the lone `~` and
also gives 22, so hotkey labels centre correctly. (Shipped font1 values;
`tests/test_fonts.py` checks the rules on synthetic fonts.)

## Open questions

- Where cp1251 locale files (`data/locale/*/*.txt`, Russian in 0xC0–0xFF)
  are converted to cp866 for the font map; typed input uses
  `FUN_0047a0f5`; no conversion found in the loader yet.

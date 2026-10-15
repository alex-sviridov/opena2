# Fonts: `fontN.dat` metrics + `fontN.16` / `fontN.16a` glyphs

Binary: `allods2.exe`, English 1.30 build, sha256
`2a8bdf9dc69276cc8d4fee561a7473a6b0f709cf9758abddaf2cd3b1fdfdfe43`, and the
community patch `a2mgr.dll`, sha256
`6bc57ebba86d4a2a7b8505bef9099c17652009fcb0f7a147fee6b2aa29077cc6`
(image base 0x10000000). Addresses were read in REA (Ghidra 12.1.4).
Implementation: `allods2/graphics/font.py`. Validation:
`tools/validate_fonts.py`. Contact sheet: `tools/font_contact.py` →
`out/contact/fonts.png`.

A font is two files with the same stem: a sprite file with one glyph per
character (the [sprite container](sprites.md), `.16` or `.16a` stream), and a
`.dat` table with one width per glyph.

## Files

| Font | Glyphs | Cell (w × h) | Chars | `.dat` | Global (FUN_00464849) |
|---|---:|---|---|---:|---|
| `font1/font1.16` | 224 | 16 × 15 | 0x20–0xFF | 896 B | `DAT_00629c88` |
| `font2/font2.16` | 224 | 8 × 10 (one glyph 9 × 10, char 0x80) | 0x20–0xFF | 896 B | `DAT_0062a6c8` |
| `font3/font3.16` | 64 | 8 × 6 | 0x20–0x5F (digits and a few signs drawn) | 256 B | `DAT_0062aff8` |
| `font4/font4.16a` | 224 | 16 × 16 | 0x20–0xFF | 896 B | `DAT_0062af90` |

`font5/font5.ttf` is a TrueType font used by a2mgr/SDL_ttf, not by these
routines (INFERRED: it is not referenced by allods2.exe).

**CONFIRMED** (all four files, `tools/validate_fonts.py`): each `.dat` is
exactly 4 bytes per glyph of its sprite file, and every glyph stream is
consumed exactly. There is no header and nothing left over.

## `.dat` layout

| Offset | Size | Field |
|---|---|---|
| 4·g | u32 LE | `width[g]` for character `0x20 + g` |

- **CONFIRMED** (`FUN_0046365e` for `.16`, `FUN_00463a16` for `.16a`): the font
  constructor appends `.16` / `.16a` (strings at 0x5fb240 / 0x5fb24c) to the
  stem, loads the sprite file (`FUN_00426ce8` → class vtable `0x5d5370`, or
  `FUN_0042a71b` → `0x5d5488`), then reads the **whole** `.dat` into a heap
  buffer (`FUN_004ebe03`/`FUN_004ec0dc`). The object is
  `{vtable, sprites, widths, spacing}`; FUN_00464849 passes `spacing = 2` for
  all four fonts. No length check, so the table size is implied by the
  sprite count.
- **CONFIRMED** (`FUN_00463a16`): font4 also rebuilds its sprite's shade table
  with `FUN_00426be0(16, 4, 0)`, i.e. 16 levels in mode 4 (FADE16,
  [palettes §5](palettes.md)).
- **CONFIRMED** (data, 732 of 736 glyphs): `width[g]` is the index of the
  glyph's **last drawn column**, or 0 for a blank glyph. Ink always starts at
  column 0. With spacing 2, every glyph is followed by one empty column.
- **CONFIRMED** (data): the 4 exceptions have `width = last column + 1`:
  font1 char 0xB3, font2 char 0x80, font4 chars 0x89 and 0xE0. **INFERRED**:
  three of them are exactly the targets of the a2mgr character remap below
  (0x80, 0x89, 0xE0), so they were probably redrawn by the patch.

## Character codes

Text is a NUL-terminated byte string. Glyph index `g = (map(c) − 0x20) & 0xFF`.

`map` is FUN_00461da1 with the a2mgr hook Ordinal_26 (0x10003910, jumped to
from 0x461db6). **CONFIRMED**:

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

**INFERRED** (glyph shapes in `out/contact/fonts.png`): the glyph set is
0x20–0x7F ASCII, 0x80–0xA5 cp437 Latin letters (Ç ü é … ñ Ñ), 0xB0–0xDF
Cyrillic А–п, 0xE0 Ё, 0xE1 ß, 0xF0–0xFF р–я. So with the remap on, text is
cp866 (DOS Cyrillic): cp866 А = 0x80 → glyph 0xB0, р = 0xE0 → 0xF0, Ё = 0xF0
→ 0xE0, ё = 0xF1 → 0x89 (the ë glyph). `DAT_0062c9c4` is probably the
Russian-language flag (not traced). font2 has small capitals in place of
lower case; font3 draws only `0`–`9` and a few signs.

A byte past the glyph table (any byte ≥ 0x60 in font3, or < 0x20 when drawn)
reads past the sprite and width tables in the game. The implementation draws
nothing and advances by `spacing` for such glyphs (our choice; the game's
result is undefined).

## Measuring: `FUN_00461e19`

**CONFIRMED.** Not hooked by a2mgr.

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

`%[...]` colour escapes (below) are **not** recognised here, so they count
as glyphs when the game right-aligns or centres a string containing them.

## Drawing a `.16` font: 0x4637f1 + a2mgr

The function at 0x4637f1 (font vtable `0x5d74f0` slot 5) was patched: its
first instruction is `jmp [0x6de5aa]` = a2mgr **Ordinal_125** (0x10005a00),
which redoes the overwritten prologue, saves the caller's colour table
(argument 5) in a local, and jumps back to 0x4637fa. Inside the loop,
`jmp [0x6de5ae]` at 0x4638b1 = **Ordinal_126** (0x10005dd0) calls the
escape parser `FUN_10005a20` before each character. **CONFIRMED.**

Arguments: `(x, y, text, flags, colours)`, where `colours` points at a
16-entry table of 16-bit pixels: the `.16` 4-bit glyph pixels index it
(blit `FUN_004593a1` via class vtable `0x5d5370 + 0x34`).

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

- **CONFIRMED** (`0x5d5370` slots 8 and 9 = `FUN_00426c16` / `FUN_00426c41`):
  `width(n)` / `height(n)` read the `w` / `h` of sprite record n. The
  alignment flags really use the **width** of glyph 0 for the vertical
  offset, and the space uses its **height**; for font4 (16 × 16) both agree.
- **CONFIRMED** (`FUN_0045ba0c`): `line` is a clipped Bresenham writing one
  16-bit colour. For the underline it is horizontal, `width[g2] + 1` pixels,
  one row below the cell, in the brightest colour of the current table.
  The `~` itself does not advance the pen. **INFERRED**: this marks the
  hotkey letter of a button label.

### Colour escapes (a2mgr `FUN_10005a20`)

**CONFIRMED.** Only when the caller passed a table (`original != 0`), and
only if `s[i] == '%'` and `s[i+1] == '['` with a `]` before the NUL:

| Body | Meaning |
|---|---|
| `*` | back to the caller's table (no-op if that is the default table `0x62afb8`) |
| 3 characters, no comma | hex digits `R G B`, each `d·17` (`F80` = 255, 136, 0) |
| 6 characters, no comma | hex pairs `RR GG BB` |
| contains a comma | up to 3 decimal fields of up to 3 characters; missing fields = 0 |
| anything else | not an escape; the `%` is drawn as a glyph |

A negative component (an unparsable field) also cancels the escape. When the
caller's table is the default `0x62afb8` (FUN_00463a06, the constant
(8, 8, 8) table of [palettes §6](palettes.md)) the escape is skipped over
but the colour does not change. Otherwise the new table is a static
16-entry RGB565 ramp at `0x1007b644`:

```
for k in 0..15:
    r5 = (k·R / 15)·31 / 255
    g6 = (k·G / 15)·63 / 255
    b5 = (k·B / 15)·31 / 255
    ramp[k] = ((r5·0x40 | g6) << 5 | b5) & 0xFFFF          # integer division
```

Because Ordinal_126 runs once per position, two escapes in a row only parse
the first; the second `%` is drawn as a glyph.

## Drawing a `.16a` font: `FUN_00463bbd`

**CONFIRMED.** Vtable `0x5d7510` slot 5; not patched.

```
draw16a(x, y, s, flags, shade):
    alignment as draw16
    for c in s:
        g = map(c) - 0x20
        if g == 0: x += height(glyph 0) >> 1
        else: sprite.draw(x, y, g, shade, 0)       # vtable 0x5d5488 + 0x18
        x += width[g] + spacing
```

No `~` or `%[...]` handling; both draw as glyphs. The glyph blit
(`FUN_0042a740`) uses the `shade` table passed in, or the font's own FADE16
table when it is null, and calls the `.16a` blitter `FUN_0045db6b`. Callers
pass a gradient shade-table row ([palettes §6](palettes.md)).

## Worked example

font1, colours = grey ramp, text `~Ok` at (0, 0), remap off:

| Step | Byte(s) | g | Action | x after |
|---|---|---|---|---|
| 1 | `~` + `O` | 0x5e, 0x2f | underline x = 0…`width[0x2f]` = 0…11 (12 pixels) at y = 15 in colours[15] | 0 |
| 2 | `O` | 0x2f | blit glyph 0x2f at (0, 0) | 0 + 11 + 2 = 13 |
| 3 | `k` | 0x4b | blit glyph 0x4b at (13, 0) | 13 + 7 + 2 = 22 |

`measure("~Ok")` skips the lone `~` and also gives 22, so centring works
for hotkey labels. (Values from the shipped font1; `tests/test_fonts.py`
checks the same rules on synthetic fonts.)

## Open questions

- What sets `DAT_0062c9c4` (the remap switch), and whether the English build
  ever turns it on.
- Why a2mgr maps cp866 0xC1 (box drawing `┴`) to glyph 0x80 (Ç).
- Which callers pass which colour tables (`0x5fb97c…0x5fb990`,
  [palettes §6](palettes.md)) and which flags.
- What `font5.ttf` is used for (a2mgr's SDL_ttf path).

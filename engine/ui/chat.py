"""The chat input line (class `FUN_0043b219`, id `0x4b0`, edit field `FUN_0043a1d8`; docs/engine/ui-layout.md 11.5 "Chat input line").  Pure state:
Enter opens it, the typed text is echoed by the backend at the line's rect, Enter submits, Esc cancels.  Single player: the submitted text is the
server's chat message `0x91` (`FUN_004f515d`): a text starting with `#` is a command (`#show map` / `#hide map`, cheat level > 0x32), anything else
is echoed into the message list as `name: text` (10000 ms, the sender's colour)."""

LINE_H = 30                 # the rect height the strip is created with (0, 0, W-160, 30), `FUN_00483129`
MAX_CHARS = 0xFF            # the text buffer is 0x100 bytes (`FUN_0043b3d7` clears it); the last byte stays the terminator
CHAT_MS = 10000             # `push 0x2710` at 0x4138b4
CHEAT_LEVEL = 0x32          # `FUN_0053dd90`: player byte `+0xa78` > 0x32
CHEAT_COMMANDS = {"#show map": True, "#hide map": False}       # message `0xaa` value 1 / 0 (`FUN_004f3d68`)


class ChatLine:
    """`open` = the strip's `+0x16c` (and game object `+0xc0`: while set every key goes to the line).  `y` = the rect top, fixed at activation."""

    def __init__(self, layout):
        self.layout = layout
        self.open = False
        self.text = ""
        self.history = []               # sent lines (INFERRED: `FUN_0043a435` stores on Enter, Up = `FUN_0043a452` recalls)
        self.y = 0

    def activate(self, bars_height=0):
        """`FUN_0048f36e` -> `FUN_0043b548` + `FUN_0043b3d7`: the rect moves to x 0, y = screen height - (30 + the heights of the open bottom windows ids 3
        and 2); the text is cleared."""
        self.y = self.layout.size[1] - (LINE_H + bars_height)
        self.text = ""
        self.open = True

    @property
    def rect(self):
        return (0, self.y, self.layout.size[0] - 160, LINE_H)

    def shown_text(self):
        """What `FUN_0043a9d8` draws: the buffer plus the `_` cursor (field `+0xa0` is 1 from the constructor on)."""
        return self.text + "_"

    def key(self, name, char=""):
        """`FUN_0043b495`: Enter -> ('send', text) (message `0x445`), Esc -> ('cancel',) (`0x446`), Up recalls the last sent line, Backspace and printable
        characters edit the text (the edit base, INFERRED).  Returns None for a plain edit."""
        if name == "return":
            text = self.text
            if text:
                self.history.append(text)
            self.open = False
            return ("send", text)
        if name == "escape":
            self.open = False
            return ("cancel",)
        if name == "up":
            if self.history:
                self.text = self.history[-1]
        elif name == "backspace":
            self.text = self.text[:-1]
        elif char and char.isprintable() and len(self.text) < MAX_CHARS:
            self.text += char
        return None

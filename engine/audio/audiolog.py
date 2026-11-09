"""The audio log CSV (docs/engine/audio.md 7): one row per request the Director resolved, with its fate.  Pure; the writer takes any text stream."""

import csv

COLUMNS = ("tick", "time_ms", "source", "event", "uid", "sound", "file", "x", "y", "volume_mB", "pan", "priority", "channel", "result")


class AudioLog:
    """`AudioLog(stream, header)`: writes `# header` lines (session, seed, "UI sounds are not in a replay"), then the column line, then rows."""

    def __init__(self, stream, header=()):
        self.out = stream
        for h in header:
            stream.write("# %s\n" % h)
        self.w = csv.writer(stream, lineterminator="\n")
        self.w.writerow(COLUMNS)
        self.rows = 0

    def row(self, tick, time_ms, source, event, uid, sound, file, x, y, volume, pan, priority, channel, result):
        self.w.writerow([tick, time_ms, source, event, uid, sound if not isinstance(sound, tuple) else "/".join(map(str, sound)), file, x, y,
                         volume, pan, priority, channel, result])
        self.rows += 1

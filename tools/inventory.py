"""Inventory a game install: every loose file and every file inside its .res
archives, with size, extension and first 16 bytes.

Usage: python tools/inventory.py [INSTALL_DIR] [-o out/inventory.csv]

Archive members are listed as `<stem>.res:<path>`.  The CSV holds file
headers taken from the game data, so it goes to the gitignored out/
directory and is never committed.
"""
import argparse
import csv
import os
import sys

import a2res
from allods2.common import INSTALL, OUT


def extension(name):
    return os.path.splitext(name)[1].lower().lstrip(".")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default=INSTALL)
    ap.add_argument("-o", "--output", default=os.path.join(OUT, "inventory.csv"))
    args = ap.parse_args(argv)
    if not os.path.isdir(args.root):
        print("not a directory: %s" % args.root, file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    count = 0
    with open(args.output, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["path", "size", "ext", "head16"])
        for dirpath, dirnames, filenames in os.walk(args.root):
            dirnames.sort()
            for name in sorted(filenames):
                p = os.path.join(dirpath, name)
                rel = os.path.relpath(p, args.root).replace(os.sep, "/")
                with open(p, "rb") as f:
                    head = f.read(16)
                w.writerow([rel, os.path.getsize(p), extension(name), head.hex(" ")])
                count += 1
                if name.lower().endswith(".res") and dirpath == args.root:
                    with a2res.ResArchive(p) as arc:
                        for path, e in arc.walk():
                            data = arc.read_entry(e)
                            w.writerow(["%s:%s" % (name, path), e.b, extension(path),
                                        data[:16].hex(" ")])
                            count += 1
                            del data
    print("%d files -> %s" % (count, args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())

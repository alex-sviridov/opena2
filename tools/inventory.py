"""Inventory every file under a game install: path, size, extension, first 16 bytes.

Usage: python tools/inventory.py [ROOT] [-o out/inventory.csv]

The CSV holds file headers taken from the game data, so it goes to the
gitignored out/ directory and is never committed.
"""
import argparse
import csv
import os
import sys
from pathlib import Path

# The install root (one level above data/), so exe/dll/cfg are included too.
DEFAULT_ROOT = Path("samples/Allods2_en_251005/Allods2_en")


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            yield Path(dirpath) / name


def extension(path: Path) -> str:
    # Lower-cased last suffix; "" for files such as data/version.
    return path.suffix.lower().lstrip(".")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("-o", "--output", type=Path, default=Path("out/inventory.csv"))
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print(f"not a directory: {args.root}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with args.output.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["path", "size", "ext", "head16"])
        for path in iter_files(args.root):
            with path.open("rb") as f:
                head = f.read(16)
            w.writerow([path.relative_to(args.root).as_posix(),
                        path.stat().st_size, extension(path), head.hex(" ")])
            count += 1
    print(f"{count} files -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

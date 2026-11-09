"""Optional native accelerators of the core library, built on demand with the system C compiler and loaded with ctypes.

Same rules as engine/native (docs/engine/simulation.md 7.5; the core cannot import `engine`): the library is compiled with
`gcc -O2 -shared -fPIC` the first time it is needed and whenever the source is newer (into this directory, else
`~/.cache/allods2/native`); any failure gives None and the callers use their pure-Python code, which stays the reference.
`ALLODS2_NATIVE=0` forces the Python code, `=1` requires the library (RuntimeError when it is unavailable).
"""

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ADPCM_SRC = os.path.join(HERE, "adpcm.c")
ADPCM_VERSION = 1               # A2_ADPCM_VERSION in adpcm.c
_SUFFIX = ".dll" if os.name == "nt" else (".dylib" if sys.platform == "darwin" else ".so")
_cache = {}
_errors = {}


def mode():
    v = os.environ.get("ALLODS2_NATIVE", "").strip()
    return v if v in ("0", "1") else ""


def build(src, name, force=False):
    """Path of an up-to-date shared library for `src` (compiled if needed); RuntimeError when that is impossible."""
    cc = next((shutil.which(c) for c in (os.environ.get("CC"), "gcc", "cc") if c and shutil.which(c)), None)
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    errors = []
    for d in (HERE, os.path.join(base, "allods2", "native")):
        lib = os.path.join(d, name + _SUFFIX)
        if not force and os.path.exists(lib) and os.path.getmtime(lib) >= os.path.getmtime(src):
            return lib
        if cc is None:
            raise RuntimeError("no C compiler (gcc / cc / $CC) found")
        try:
            os.makedirs(d, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=name + ".", suffix=_SUFFIX + ".tmp", dir=d)
            os.close(fd)
        except OSError as e:
            errors.append("%s: %s" % (d, e))
            continue
        try:
            p = subprocess.run([cc, "-O2", "-shared", "-fPIC", "-std=c99", "-o", tmp, src], capture_output=True, text=True)
            if p.returncode != 0:
                raise RuntimeError("%s failed:\n%s%s" % (cc, p.stdout, p.stderr))
            os.replace(tmp, lib)
            return lib
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    raise RuntimeError("cannot write the native library: " + "; ".join(errors))


def _load_adpcm():
    lib = ctypes.CDLL(build(ADPCM_SRC, "_adpcm"))
    if lib.a2_adpcm_version() != ADPCM_VERSION:
        lib = ctypes.CDLL(build(ADPCM_SRC, "_adpcm", force=True))
        if lib.a2_adpcm_version() != ADPCM_VERSION:
            raise RuntimeError("native adpcm version mismatch")
    p, i = ctypes.c_void_p, ctypes.c_int
    lib.a2_msadpcm.argtypes = [p, ctypes.c_int64, i, i, i, p, i, p, ctypes.c_int64]
    lib.a2_msadpcm.restype = ctypes.c_int64
    return lib


def load_adpcm():
    """The ctypes ADPCM library whatever ALLODS2_NATIVE says, or None (reason: `error()`); cached per process."""
    if "adpcm" not in _cache:
        try:
            _cache["adpcm"] = _load_adpcm()
        except Exception as e:                       # noqa: BLE001 - any failure means "use Python"
            _cache["adpcm"] = None
            _errors["adpcm"] = "%s: %s" % (type(e).__name__, e)
    return _cache["adpcm"]


def adpcm():
    """The library the decoder should use: None with ALLODS2_NATIVE=0 or when unavailable in auto mode."""
    if mode() == "0":
        return None
    lib = load_adpcm()
    if lib is None and mode() == "1":
        raise RuntimeError("ALLODS2_NATIVE=1 but the native ADPCM decoder is unavailable: %s" % _errors.get("adpcm"))
    return lib


def error(name="adpcm"):
    return _errors.get(name)

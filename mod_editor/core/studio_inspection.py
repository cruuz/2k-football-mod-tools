"""Run expensive disc-wide Build status checks outside the Qt interpreter."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
import subprocess
import sys
import threading

from . import platform_compat

#: How long the Studio waits for the disc read. A SOFTDRINK disc is a scale-out executable and its read is minutes of
#: work even with the validation memo below; a plain game disc takes well under a minute.
INSPECT_TIMEOUT_SECONDS = 900


# --------------------------------------------------------------------------------------------- the validation memo
#: The scale-out executable's structure checks that every status function repeats. A disc read asks ~150 status
#: functions about the same 12 MB executable, and each one re-ran these (about 0.1 s each, thousands of times: the
#: released v0.8 disc took 12 minutes to read, and the Rosters page did it on the GUI thread). They are pure functions
#: of the executable's bytes, so inside a ``memoised_validation()`` block each distinct executable is checked once.
_MEMOISED = ("validate_scale_structure", "_validate", "layout")
_MEMO_LOCK = threading.RLock()
_memo_depth = 0
_memo_originals: dict[str, object] = {}
_memo_values: dict[tuple, tuple] = {}
_memo_digests: dict[int, tuple] = {}
_MEMO_PAYLOADS = 6          # distinct executables kept (each one is held so its id cannot be reused)
_MEMO_VALUES = 30


def _payload_key(payload: bytes) -> tuple:
    """Content key of an immutable executable image; the same object is hashed once."""
    with _MEMO_LOCK:
        known = _memo_digests.get(id(payload))
        if known is not None and known[0] is payload:
            return known[1]
    key = (len(payload), hashlib.blake2b(payload, digest_size=16).digest())
    with _MEMO_LOCK:
        _memo_digests[id(payload)] = (payload, key)
        while len(_memo_digests) > _MEMO_PAYLOADS:
            del _memo_digests[next(iter(_memo_digests))]
    return key


def _memoised(name: str, function):
    def wrapper(payload, *args, **kwargs):
        if args or kwargs or type(payload) is not bytes:
            return function(payload, *args, **kwargs)
        key = (name, _payload_key(payload))
        with _MEMO_LOCK:
            hit = _memo_values.get(key)
        if hit is not None:
            return copy.deepcopy(hit[0])
        result = function(payload)                       # a refusal raises and is never remembered
        with _MEMO_LOCK:
            _memo_values[key] = (copy.deepcopy(result),)
            while len(_memo_values) > _MEMO_VALUES:
                del _memo_values[next(iter(_memo_values))]
        return result

    wrapper.__wrapped__ = function
    return wrapper


@contextlib.contextmanager
def memoised_validation():
    """Within the block, ``nfl2k5_xbe_space`` checks one executable's structure once instead of on every status call.

    Results are deep copies, only ``bytes`` are remembered (by content), a check that refuses is never remembered, and
    the memo is dropped when the outermost block ends. Re-entrant and safe beside other threads."""
    global _memo_depth
    from . import nfl2k5_xbe_space as space
    with _MEMO_LOCK:
        if _memo_depth == 0:
            for name in _MEMOISED:
                original = getattr(space, name)
                _memo_originals[name] = original
                setattr(space, name, _memoised(name, original))
        _memo_depth += 1
    try:
        yield
    finally:
        with _MEMO_LOCK:
            _memo_depth -= 1
            if _memo_depth == 0:
                for name, original in _memo_originals.items():
                    setattr(space, name, original)
                _memo_originals.clear()
                _memo_values.clear()
                _memo_digests.clear()


def inspect_source(source: Path, *, marks_pack: str = "") -> dict:
    # Use the configured interpreter, including the bundled Windows runtime.
    # The child imports from this installation, independent of working directory.
    root = platform_compat.io_path(platform_compat.absolute_path(__file__)).parents[2]
    program = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from mod_editor.core.studio_inspection import _main; _main(sys.argv[2], sys.argv[3])"
    )
    try:
        result = subprocess.run([sys.executable, "-c", program, str(root), str(platform_compat.io_path(source)),
                                 str(platform_compat.io_path(marks_pack)) if marks_pack else ""],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", timeout=INSPECT_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as exc:
        # the raw message is the whole command line: the interpreter, the inline program and the paths
        raise ValueError(f"Reading this disc's settings took longer than {INSPECT_TIMEOUT_SECONDS // 60} minutes, so "
                         "the Studio stopped waiting. Open the disc again to try once more.") from exc
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Disc inspection could not finish")
    state = json.loads(result.stdout)
    if not isinstance(state, dict):
        raise ValueError("Disc inspection returned an invalid result")
    if isinstance(state.get("throw"), dict):
        from .nfl2k5_throw_tuning import TuningSettings
        state["throw"] = TuningSettings(**state["throw"])
    return state


def _main(source, marks_pack=""):
    from mod_editor.core import mod_build, nfl2k5_official_marks
    with nfl2k5_official_marks.using_pack(marks_pack):
        state = mod_build.inspect(Path(source))
    # BuildPanel consumes this dataclass by attribute; preserve its type across
    # the child boundary instead of stringifying it (or failing JSON encoding).
    state["throw"] = asdict(state["throw"])
    print(json.dumps(state, ensure_ascii=True))

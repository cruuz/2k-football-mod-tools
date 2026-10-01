"""Run expensive disc-wide Build status checks outside the Qt interpreter."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
import subprocess
import sys

from . import platform_compat


def inspect_source(source: Path, *, marks_pack: str = "") -> dict:
    # Use the configured interpreter, including the bundled Windows runtime.
    # The child imports from this installation, independent of working directory.
    root = platform_compat.io_path(platform_compat.absolute_path(__file__)).parents[2]
    program = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from mod_editor.core.studio_inspection import _main; _main(sys.argv[2], sys.argv[3])"
    )
    result = subprocess.run([sys.executable, "-c", program, str(root), str(platform_compat.io_path(source)),
                             str(platform_compat.io_path(marks_pack)) if marks_pack else ""],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", timeout=180,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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

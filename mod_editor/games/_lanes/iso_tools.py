"""The repository's ISO9660 writer and verifier, reached the way a lane may.

Both live under ``tools/`` because they are the *repository's*, not a game's:
one bounded writer that replaces a file inside the extent it already owns, and
one verifier that imports none of it and re-derives the claim from the two
images.  A game package may not reach outside the contract at module level, so
every lane that writes an image has carried its own two-line import shim.  Five
copies of the same eight lines is five places for the ``parents[3]`` to be
wrong, so they are here once.

:func:`declared_ranges` is the other repeat: the writer's report carries its
declared byte ranges as either dataclasses or mappings depending on the path
that produced it, and every lane turned them into
:class:`~mod_editor.games.contract.DeclaredRange` the same way.

Nothing here reads a disc.  It resolves two module paths and converts one
report shape.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, List, Mapping, Sequence, Tuple

from mod_editor.games.contract import DeclaredRange

#: The repository root, four parents up from this file
#: (``mod_editor/games/_lanes/iso_tools.py``).
REPO_ROOT = Path(__file__).resolve().parents[3]
#: Where the two modules live.
TOOLS_DIRECTORY = REPO_ROOT / "tools"


def _tools_on_path() -> None:
    path = str(TOOLS_DIRECTORY)
    if path not in sys.path:
        sys.path.insert(0, path)


def iso_writer() -> Any:
    """``tools/ps2_iso9660_writer``, imported at call time.

    At call time and not at module level for two reasons: a game package may
    not reach outside the contract while it is being imported, and a lane that
    only ever catalogues should not pay for the import.
    """

    _tools_on_path()
    import ps2_iso9660_writer  # noqa: PLC0415

    return ps2_iso9660_writer


def iso_verifier() -> Any:
    """``tools/ps2_iso9660_verify``, imported at call time.

    The **independent** half: it imports none of the writer, and a lane's
    ``verify`` uses it for the image-level claim so that a writer bug cannot
    also be the thing that says the write was fine.
    """

    _tools_on_path()
    import ps2_iso9660_verify  # noqa: PLC0415

    return ps2_iso9660_verify


def declared_ranges(report: Mapping[str, Any]) -> Tuple[DeclaredRange, ...]:
    """The writer report's declared byte ranges, as the contract's own type.

    The report carries them as dataclasses when it comes straight from the
    writer and as mappings when it has been through JSON, and a lane must not
    care which.
    """

    out: List[DeclaredRange] = []
    for item in report.get("declared_ranges", ()):
        row = item if isinstance(item, Mapping) else item.as_dict()
        out.append(DeclaredRange(int(row["start"]), int(row["length"]),
                                 str(row.get("reason", ""))))
    return tuple(out)


def spans_cover(spans: Sequence[Tuple[int, int]], offset: int) -> bool:
    """Whether any ``(start, length)`` run covers *offset*.

    The inner loop of every verifier's "no byte changed outside what was
    declared" check, written once so the boundary condition is written once.
    """

    for start, length in spans:
        if start <= offset < start + length:
            return True
    return False


def first_undeclared(before: bytes, after: bytes,
                     spans: Sequence[Tuple[int, int]]) -> int:
    """The first byte index where *before* and *after* differ outside *spans*.

    ``-1`` when every difference is covered.  A length mismatch is not this
    function's business -- a caller that allows one has already decided what it
    means -- so the comparison stops at the shorter of the two.
    """

    for offset in range(min(len(before), len(after))):
        if before[offset] == after[offset]:
            continue
        if not spans_cover(spans, offset):
            return offset
    return -1


__all__ = [
    "REPO_ROOT",
    "TOOLS_DIRECTORY",
    "declared_ranges",
    "first_undeclared",
    "iso_verifier",
    "iso_writer",
    "spans_cover",
]

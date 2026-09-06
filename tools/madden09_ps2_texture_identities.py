#!/usr/bin/env python3
"""Pair a PCSX2 texture dump of Madden NFL 09 with the disc's own ``MMAP`` textures.

**The matcher moved; this file is the Madden 09 door to it.**  Everything this
tool did -- decode every ``MMAP`` surface on the disc, decode every PNG PCSX2
dumped, pair them on exact pixel equality, and re-derive each dumped name from
the disc bytes to check the rule -- now lives in
:mod:`ps2_texture_identities`, because NCAA Football 09 puts its art in exactly
the same ``TERF``/``MMAP`` containers and a second copy of a pixel matcher is a
second place for it to be wrong.  Which disc is being paired is a
``GameProfile`` there.

This file stays because its *name* is a fact several other files record: the
Madden lane's ``identity_tool``, its registry row, the release allowlist and
four documents cite it.  It chooses ``--game madden09_ps2`` and adds nothing
else, so every command that worked before works unchanged and writes the same
bytes::

    madden09_ps2_texture_identities.py --source DISC.iso --dump-dir DIR \\
        --out docs/product/measured/madden09_ps2/pcsx2-texture-identities.json
    madden09_ps2_texture_identities.py --source DISC.iso --index CACHE.jsonl \\
        --containers UNIFORMS.DAT,FIELDART.DAT
    madden09_ps2_texture_identities.py --selftest

The names this module re-exports -- ``scan_dump``, ``index_disc``, ``pair``,
``attribute_teams``, ``team_summary``, ``texture_bits``, ``replacement_name``,
``_NAME`` -- are the ones callers in this repository already use, and they are
the shared module's own objects rather than copies of them.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import ps2_texture_identities as _shared                                  # noqa: E402
from ps2_texture_identities import (                                      # noqa: E402,F401
    DiscTexture,
    DumpTexture,
    GameProfile,
    IdentityError,
    MatchReport,
    PSM_MASK,
    SHARED_SAMPLE,
    _NAME,
    _digests,
    attribute_teams,
    build_derivation_document,
    derivation_census,
    derivation_check,
    pair,
    read_dump_index,
    read_index,
    read_rgba_png,
    replacement_name,
    scan_dump,
    team_summary,
    texture_bits,
    write_dump_index,
    write_rgba_png,
)

#: The disc this door opens on.  Everything game-specific -- the containers
#: worth indexing, the two document paths, the schemas the lane expects and the
#: self-test token a validator greps for -- is on it.
GAME = _shared.profile("madden09_ps2")

#: The names this module published before the matcher was shared.  They are
#: the profile's fields, so a reader who greps for ``DEFAULT_CONTAINERS`` still
#: finds the list the tool actually indexes.
SCHEMA = GAME.identity_schema
INDEX_SCHEMA = "madden09_ps2_disc_texture_index/v1"
DEFAULT_OUT = GAME.identity_document
DEFAULT_CONTAINERS = GAME.default_containers
DERIVATION_SCHEMA = GAME.derivation_schema
DERIVATION_OUT = GAME.derivation_document


def index_disc(source: Path, containers_wanted: Sequence[str] = DEFAULT_CONTAINERS, *,
               progress=None):
    """:func:`ps2_texture_identities.index_disc` over Madden 09's containers."""

    return _shared.index_disc(source, containers_wanted, discs=GAME.discs, progress=progress)


def write_index(source: Path, path: Path,
                containers_wanted: Sequence[str] = DEFAULT_CONTAINERS, *,
                progress=None) -> int:
    """:func:`ps2_texture_identities.write_index` over Madden 09's containers."""

    return _shared.write_index(source, path, containers_wanted, discs=GAME.discs,
                               progress=progress)


def build_document(source: Path, dump_dir: Path, dumps, disc, report, **kwargs) -> dict:
    """:func:`ps2_texture_identities.build_document` for Madden 09."""

    kwargs.setdefault("game", GAME)
    return _shared.build_document(source, dump_dir, dumps, disc, report, **kwargs)


def selftest(tmp: Optional[Path] = None) -> int:
    """The shared self-test, on Madden 09's own synthetic disc."""

    return _shared.selftest(GAME, tmp)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """The shared command line with ``--game madden09_ps2`` already chosen."""

    return _shared.main(argv, game_id="madden09_ps2")


if __name__ == "__main__":
    raise SystemExit(main())

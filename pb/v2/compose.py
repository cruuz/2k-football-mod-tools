#!/usr/bin/env python3
"""Resource-level Build tail for one team PLAY book (beta 77, job p48o).

Runs, in Build's order (``mod_build.py`` playbook section), the writers that touch a
team book after its packs, on one in-memory 0x20 + 0x13390 resource:

1. complete offense pack (``apply_pack_to_resource``, native scoring when ``xbe`` is given)
2. defense pack (pinned to step 1's output)
3. position pools: the 37-book defensive category recode (``recoded_table``)
4. kickoff alignment: 2026 Kickoff / Kick Return slot blocks
5. dynamic kickoff returns: the three normal return plays
6. depth roles: X / Z / slot and nickel / dime ordinals from formation geometry
7. screen timing at level D (a no-op for books whose authored screens are pinned)

The repair (``tools/b77/p48o_repair.py``) and the league verifier use this, so a disc
repaired from v0.5 and a Studio Build from retail share one implementation.
Never touches an image; gameplay is unwitnessed.
"""
from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_depth_roles as roles  # noqa: E402
from mod_editor.core import nfl2k5_kickoff_returns as returns  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402
from mod_editor.core import nfl2k5_screen_timing as timing  # noqa: E402
import nfl2k5_playbook_position_recode as recode  # noqa: E402
from tools import nfl2k5_kickoff_alignment as align  # noqa: E402

STEPS = ("complete_offense", "defense", "position_pools", "kickoff_alignment", "kickoff_returns",
         "depth_roles", "screen_timing")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def position_pools(team: str, raw: bytes) -> bytes:
    book = recode.parse_book(team, SimpleNamespace(index=recode.BOOK_ENTRIES[team], virtual_offset=0), raw)
    table, _changes = recode.recoded_table(book)
    start = insp.RESOURCE_HEADER_SIZE + insp.CATEGORY_BASE
    return raw[:start] + table + raw[start + len(table):]


def kickoff_alignment(raw: bytes, kicker_depth_yd: float = align.DEFAULT_KICKER_DEPTH_YD) -> bytes:
    body = raw[insp.RESOURCE_HEADER_SIZE:]
    book = insp.parse_playbook_resource(raw)
    out = bytearray(raw)
    done = set()
    for f in book.formations:
        rec = insp.FORMATION_BASE + f.index * insp.FORMATION_SIZE
        type_code = (struct.unpack_from("<I", body, rec + 4)[0] >> 8) & 0x3F
        key = (f.name.strip(), type_code)
        if key == (align.KICKOFF_NAME, align.KICKOFF_TYPE):
            xz = align.kickoff_xz_2026(kicker_depth_yd)
        elif key == (align.KICK_RETURN_NAME, align.KICK_RETURN_TYPE):
            xz = align.KICK_RETURN_XZ_2026
        else:
            continue
        off = insp.RESOURCE_HEADER_SIZE + rec + align.SLOT_BASE
        out[off:off + align.SLOTS_SIZE] = align.with_xz(bytes(out[off:off + align.SLOTS_SIZE]), xz)
        done.add(key[0])
    if done != {align.KICKOFF_NAME, align.KICK_RETURN_NAME}:
        raise ValueError("expected one Kickoff and one Kick Return formation")
    return bytes(out)


def compose(team: str, retail: bytes, offense, defense, xbe=None, *, screen_level: str = "D"):
    """Return (final resource, receipt) for ``team`` from its retail resource and two packs."""
    receipt = {"team": team, "source_sha256": sha(retail), "steps": []}
    a = packs.apply_pack_to_resource(retail, offense, asset_id="book:" + team, xbe=xbe)
    receipt["steps"].append(dict(step="complete_offense", sha256=a.replacement_sha256,
                                 nodes=a.report["new_node_count"], names=a.report["name_pool_bytes"],
                                 native_scoring=a.report.get("native_scoring", {}).get("fault_count")))
    b = packs.apply_pack_to_resource(a.replacement, defense, asset_id="book:" + team, xbe=xbe)
    receipt["steps"].append(dict(step="defense", sha256=b.replacement_sha256, nodes=b.report["new_node_count"],
                                 native_scoring=b.report.get("native_scoring", {}).get("fault_count")))
    raw = position_pools(team, b.replacement)
    receipt["steps"].append(dict(step="position_pools", sha256=sha(raw)))
    raw = kickoff_alignment(raw)
    receipt["steps"].append(dict(step="kickoff_alignment", sha256=sha(raw)))
    raw, ret = returns.apply(raw)
    receipt["steps"].append(dict(step="kickoff_returns", sha256=sha(raw), status=ret.get("status")))
    normal = roles.normalise(raw)
    raw = normal.replacement
    receipt["steps"].append(dict(step="depth_roles", sha256=sha(raw), changed_bytes=normal.report.get("changed_bytes")))
    raw, screen = timing.apply(raw, screen_level)
    receipt["steps"].append(dict(step="screen_timing", sha256=sha(raw), status=screen["status"],
                                 already_applied=screen["already_applied"]))
    receipt["final_sha256"] = sha(raw)
    return raw, receipt, a, b

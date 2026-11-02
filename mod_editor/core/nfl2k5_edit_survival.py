"""Did every edit survive the build? (b791 h4, the post-build audit; "never silently drop a user edit")

b779-ce1 found by hand that one option replaced two of Coach Edwards' edited Eagles kits without a word (14 of 8,542
edited chunks). Build now checks this itself on every project build:

1. ``snapshot``: right after the project stage has written the user's replacements into the private copy, the
   SHA-256 of every chunk of each kit file the project edits, on that copy and on the source disc, plus every chunk of
   each stadium bundle it edits. Digests only; no bytes are kept.
2. ``audit``: after the finished disc is published, the same kit files (found by name, so a step that moves or grows
   them is harmless) and bundles are read again. A chunk the user changed (its digest differs from the source disc's)
   that is not byte for byte the same on the finished disc is named: back to the original, or changed by a later step.

``audit_step`` turns the result into a receipt step with ``user_notes``, which the Build summary shows
(``build_feedback.completion``). The audit never fails a finished build: if it cannot read something it says so.
Kit art outside the kit files (Team Select cards) and the other families are counted as not checked.
"""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Callable, Iterable

SCHEMA = "nfl2k5_edit_survival/v1"
STEP = "edit_survival"
MAX_NAMED = 24

_STADIUM = re.compile(r"^nfl2k5\.stadium\.o(\d+)\.", re.ASCII)


def sha(data) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def edited_pieces(asset_ids: Iterable[str]) -> dict:
    """{"kits": {selector: {chunk: [asset ids]}}, "stadiums": {outer index: [asset ids]}, "other": [asset ids]}."""
    from . import nfl2k5_project_check as check
    from .nfl2k5_uniform_equipment_writer import load_targets
    targets, _physical = load_targets()
    kits, stadiums, other = {}, {}, []
    for asset_id in asset_ids:
        asset_id = str(asset_id)
        target = targets.get(asset_id) if asset_id.startswith("tset:") else None
        place = (target.set_selector.upper(), target.chunk_index) if target is not None else check.uniform_chunk(asset_id)
        if place is not None:
            kits.setdefault(place[0], {}).setdefault(place[1], []).append(asset_id)
            continue
        match = _STADIUM.match(asset_id)
        if match:
            stadiums.setdefault(int(match.group(1)), []).append(asset_id)
            continue
        other.append(asset_id)
    return dict(kits=kits, stadiums=stadiums, other=other)


def _kit_chunks(target, selector):
    from nfl_txtr import parse_chunks
    from . import nfl2k5_moment_kits as kits
    name = kits.selector_name(selector)
    if not target.has(name):
        return None
    raw = target.get(name)
    return [sha(raw[c.offset:c.end_offset]) for c in parse_chunks(raw, allow_trailing=True)]


def _bundle_chunks(archive, outer):
    from nfl_txtr import parse_chunks
    if outer >= len(archive.entries):
        return None
    entry = archive.entries[outer]
    raw = archive.read(entry.virtual_offset, entry.size)
    return [sha(raw[c.offset:c.end_offset]) for c in parse_chunks(raw, allow_trailing=True)]


def _read(image, pieces, progress=None, label="") -> dict:
    """{"kits": {selector: [chunk digests] or None}, "stadiums": {outer: [...] or None}} of one disc image."""
    from . import nfl2k5_historic_styles as hs
    from . import nfl2k5_music_archive as archive
    from . import nfl2k5_roster_records as rr
    say = progress or (lambda *_: None)
    out = dict(kits={}, stadiums={})
    selectors = sorted(pieces["kits"])
    if selectors:
        with archive.Disc(Path(image), descriptors=()) as disc:
            target = hs.Target(disc)
            for number, selector in enumerate(selectors, 1):
                if number % 100 == 0:
                    say(f"Checking your edits {label}({number} of {len(selectors)} kit files)", number, len(selectors))
                out["kits"][selector] = _kit_chunks(target, selector)
    if pieces["stadiums"]:
        with rr._outer_image()(str(image)) as outer_image:
            for outer in sorted(pieces["stadiums"]):
                out["stadiums"][outer] = _bundle_chunks(outer_image, outer)
    return out


def snapshot(stage_image, asset_ids, *, source=None, progress: Callable | None = None) -> dict:
    """Digests of every chunk of the kit files and stadium bundles the project edits, on the project-stage copy
    (``stage_image``) and on the source disc (``source``; the edits are the chunks that differ)."""
    started = time.monotonic()
    pieces = edited_pieces(asset_ids)
    stage = _read(stage_image, pieces, progress, "after the texture stage ")
    original = _read(source, pieces, progress, "on your source disc ") if source else dict(kits={}, stadiums={})
    return dict(schema=SCHEMA, pieces=pieces, stage=stage, source=original, seconds=round(time.monotonic() - started, 1))


def _compare(kind, key, stage, source, final, ids_by_chunk) -> tuple:
    """(kept chunk count, [lost rows]) of one kit file or bundle."""
    kept, lost = 0, []
    if stage is None:
        return 0, []
    for index, digest in enumerate(stage):
        before = source[index] if source is not None and index < len(source) else None
        if before is not None and digest == before:
            continue                      # the user did not change this chunk
        after = final[index] if final is not None and index < len(final) else None
        if after == digest:
            kept += 1
            continue
        state = ("missing" if final is None else "back to the original" if after is not None and after == before
                 else "changed by a later build step")
        lost.append(dict(kind=kind, where=key, chunk=index, state=state,
                         asset_ids=sorted(ids_by_chunk.get(index, ()))))
    return kept, lost


def audit(snap: dict, final_image, *, progress: Callable | None = None) -> dict:
    """Compare the finished disc with the snapshot: {"kept", "lost": [...], "not_checked", "seconds"}."""
    started = time.monotonic()
    pieces = snap["pieces"]
    final = _read(final_image, pieces, progress, "on the finished disc ")
    kept, lost = 0, []
    for selector, stage in sorted(snap["stage"]["kits"].items()):
        k, rows = _compare("kit", selector, stage, snap["source"]["kits"].get(selector), final["kits"].get(selector),
                           {int(c): ids for c, ids in pieces["kits"].get(selector, {}).items()})
        kept += k
        lost.extend(rows)
    for outer, stage in sorted(snap["stage"]["stadiums"].items()):
        k, rows = _compare("stadium", int(outer), stage, snap["source"]["stadiums"].get(outer),
                           final["stadiums"].get(outer), {})
        for row in rows:
            row["asset_ids"] = sorted(pieces["stadiums"].get(outer, ()))
        kept += k
        lost.extend(rows)
    return dict(schema=SCHEMA, kept=kept, lost=lost, not_checked=len(pieces["other"]),
                kit_files=len(snap["stage"]["kits"]), bundles=len(snap["stage"]["stadiums"]),
                seconds=round(time.monotonic() - started + snap.get("seconds", 0), 1))


def piece_words(row) -> str:
    from . import nfl2k5_project_check as check
    chunk = row["chunk"]
    if row["kind"] == "kit":
        return f"{row['where']} {check.KIT_PIECES.get(chunk, 'piece ' + str(chunk))}"
    return f"stadium bundle {row['where']} piece {chunk}"


def user_notes(result: dict) -> list:
    """Plain sentences for the Build summary."""
    lost = result.get("lost") or []
    checked = result.get("kept", 0) + len(lost)
    notes = []
    if not checked and not result.get("not_checked"):
        return notes
    if checked and not lost:
        notes.append(f"Your edits: all {result.get('kept', 0):,} edited kit and stadium pieces are on the finished disc "
                     "exactly as the texture stage wrote them.")
    elif lost:
        named = ", ".join(f"{piece_words(row)} ({row['state']})" for row in lost[:MAX_NAMED])
        more = f" and {len(lost) - MAX_NAMED} more" if len(lost) > MAX_NAMED else ""
        notes.append(f"Your edits: {len(lost)} of {checked:,} edited pieces did not survive the build as you made them: "
                     f"{named}{more}. Please send this Build summary to the SOFTDRINK Discord.")
    if result.get("not_checked"):
        notes.append(f"Your edits: {result['not_checked']:,} edits outside the kit files and stadium bundles (Team Select "
                     "cards and other art) were not checked.")
    return notes


def audit_step(snap: dict | None, final_image, *, progress: Callable | None = None) -> dict:
    """The receipt step of the audit; never raises."""
    if snap is None:
        return dict(step=STEP, state="not_checked", user_notes=[])
    try:
        result = audit(snap, final_image, progress=progress)
    except Exception as exc:  # noqa: BLE001 - a finished disc is never failed by its own audit
        return dict(step=STEP, state="not_checked", reason=f"{type(exc).__name__}: {str(exc)[:300]}",
                    user_notes=["Your edits: the check that every edit is on the finished disc could not run "
                                f"({str(exc)[:200] or type(exc).__name__})."])
    return dict(step=STEP, state="all_kept" if not result["lost"] else "lost_edits", kept=result["kept"],
                lost=result["lost"][:400], lost_count=len(result["lost"]), not_checked=result["not_checked"],
                kit_files=result["kit_files"], bundles=result["bundles"], seconds=result["seconds"],
                user_notes=user_notes(result))

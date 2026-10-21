"""Moment-only venue text and dedicated Anniversary stadium bundle aliases.

The names retain the audit's INFERRED historical classification. Native readers
and isolation are checked offline; rendered presentation remains a lab check.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_moment_venues"
BUILD_CAPTION = UI_LABEL = "Historical Anniversary venue names"
CODE_SIZE, TABLE = 2304, 256
FILENAME_HOOK = ("filename", 0x62C96, bytes.fromhex("668974240c"))
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
MODE, SITUATION_FLAG, MOMENT = 0xE5FF80, 0xE6014C, 0xBF1858   # game mode (8), Situation mode flag (1), physical row
DATA = Path(__file__).resolve().parents[2] / "data/nfl2k5_moment_venues.json"
# Preview: after m1's record/cell getter, before native wide-string formatting.
# Name getter: the Stadium menu text callback 2C1640 tail-calls this.
# Game report: two stadium-name formatting branches, leaving physical reads alone.
# Intro/presentation: the second display-name pointer is at stadium+0x10.
HOOKS = (
    ("preview", 0x2C5A76, bytes.fromhex("8b008d4c2400")),
    ("name", 0x77540, bytes.fromhex("a164fee5008b00")),
    ("report", 0x127181, bytes.fromhex("e8da02f5ff")),
    ("report", 0x1271C1, bytes.fromhex("e89a02f5ff")),
    ("presentation", 0x1C08DF, bytes.fromhex("e87c6bebff")),
    ("presentation", 0x1C0910, bytes.fromhex("e84b6bebff")),
    ("presentation", 0x318557, bytes.fromhex("e804ef d5ff")),
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def rows():
    result = json.loads(DATA.read_text())["moments"]
    require([r["row"] for r in result] == list(range(1, 51)), "venue ordinal table")
    require(all(isinstance(r["venue"], str) and r["venue"].isascii()
                and 0 < len(r["venue"]) <= 64 and "\0" not in r["venue"] for r in result), "venue names")
    return result + [dict(row=51, date="2025-10-16", venue="Paycor Stadium",
                         classification="PFR / official gamebook", sources=[
                             "https://www.pro-football-reference.com/boxscores/202510160cin.htm"])]


def _gate(a, label, legacy, situation):
    """mode == 8 and a valid physical row, else jump to ``label`` (edx = the row; caller saved edx and flags).

    b777-sm2: the Situation mode is game mode 8 too, with the situation flag 0xE6014C = 1 (retail's own moment
    paths test it, e.g. 0x20C5C0 and 0x20C670). Its row word still holds 0 or the last moment played, so without
    the flag every alias also fired in Situation. ``(mode ^ 8) | flag`` is zero only for a moment, so one test
    covers both words (any non-zero flag counts as the Situation mode) in the same 28 bytes as the b776 gate.
    """
    if not situation:
        a.b("833d80ffe50008")
        a.j32("0f85", label)
        a.b("8b155818bf0083fa" + ("32" if legacy else "33"))
        a.j32("0f83", label)
        return
    a.b("8b15" + struct.pack("<I", MODE).hex() + "83f208" "0b15" + struct.pack("<I", SITUATION_FLAG).hex())
    a.j8("75", label)
    a.b("8b15" + struct.pack("<I", MOMENT).hex() + "83fa33")
    a.j8("73", label)


def code_for(va, spans=None, *, legacy=False, ball=None, situation=True):
    """The owner body and hook edits. ``situation=False`` rebuilds the b776 body (aliases also in Situation).
    ``ball=None`` follows the era ball switch (b777 ar1: the selector rides in this owner only when it is on)."""
    if ball is None:
        from . import nfl2k5_era_ball as era_ball
        ball = era_ball.enabled()
    situation = situation and not legacy
    spans = spans or [dict(va=va, size=CODE_SIZE, owner_offset=0)]
    require(spans[0]["size"] >= TABLE + 200, "venue entry/table must be contiguous")

    def address(offset, length):
        for part in spans:
            start = part["owner_offset"]
            if start <= offset and offset + length <= start + part["size"]:
                return part["va"] + offset - start
        return None

    a = _Asm(va)
    a.label("preview")
    a.b("8b00")  # displaced name dereference, also works with m1's venue cells
    a.call(va + 128)
    a.b("8d0c24")
    a.jmp_abs(0x2C5A7C)
    a.label("name")
    a.b("a164fee5008b00")
    a.jmp_abs(va + 128)
    for label, offset in (("report", 0), ("presentation", 16)):
        a.label(label)
        a.b("a164fee5009c52")
        _gate(a, label + "_done", legacy, situation)
        a.b("8d0495" + struct.pack("<I", va + TABLE - offset).hex())
        a.label(label + "_done")
        a.b("5a9dc3")
    body = bytearray(a.assemble())
    labels = dict(a.labels)
    require(len(body) <= 128, "venue wrapper budget")
    body.extend(b"\xcc" * (128 - len(body)))
    b = _Asm(va + 128)
    b.b("9c52")
    _gate(b, "done", legacy, situation)
    b.b("8b0495" + struct.pack("<I", va + TABLE).hex())
    b.label("done")
    b.b("5a9dc3")
    body.extend(b.assemble())
    selector = None
    if not legacy and ball:
        # b773-me1: the per-game ball palette choice (nfl2k5_era_ball) fills the gap before the table, which is in
        # the first owned span in every layout; the end of the owner has too little room on split layouts.
        from . import nfl2k5_era_ball as era_ball
        start = TABLE - era_ball.SELECTOR_SIZE
        require(len(body) <= start and address(start, era_ball.SELECTOR_SIZE) is not None, "ball selector room")
        body.extend(b"\xcc" * (start - len(body)))
        code, selector = era_ball.selector(address(start, era_ball.SELECTOR_SIZE))
        body.extend(code)
    body.extend(b"\xcc" * (TABLE - len(body)))
    selected = rows()[:50] if legacy else rows()
    body.extend(bytes(len(selected) * 4))
    texts = {}
    for i, row in enumerate(selected):
        name = row["venue"]
        if name not in texts:
            raw = (name + "\0").encode("utf-16le")
            while address(len(body), len(raw)) is None:
                require(len(body) < CODE_SIZE, "venue strings exceed owned spans")
                body.extend(b"\xcc")
            texts[name] = address(len(body), len(raw))
            body.extend(raw)
        struct.pack_into("<I", body, TABLE + 4 * i, texts[name])
    if not legacy:
        # Preserve the normal suffix and all physical stadium reads. Only mode 8
        # and a valid physical SITU row receive a00..a50 aliases. Stale ordinals
        # cannot affect Quick Game or franchise. The helper stays wholly inside
        # the last owned span; the 2304-byte owner does not grow or move.
        # b777-sm2: and never in the Situation mode (mode 8, situation flag 1):
        # there the alias named a00..a50 bundles that exist only for one
        # moment's time and weather, so the field and stadium failed to load
        # (Noah 10/20, Situation at MetLife: "players playing on a void").
        start = (len(body) + 15) & ~15
        require(address(start, 112) is not None, "filename helper crosses owned spans")
        body.extend(b"\xcc" * (start - len(body)))
        f = _Asm(address(start, 112))
        f.b("9c60" "833d80ffe50008")
        f.j32("0f85", "filename_done")
        if situation:
            f.b("833d" + struct.pack("<I", SITUATION_FLAG).hex() + "00")
            f.j32("0f85", "filename_done")
        f.b("a15818bf00" "83f833")
        f.j32("0f83", "filename_done")
        f.b("66c705d006b3006100" "31d2" "b90a000000" "f7f1")
        f.b("6683c030" "66a3d206b300" "6683c230" "668915d406b300")
        f.label("filename_done")
        f.b("619d668974240c")
        f.jmp_abs(FILENAME_HOOK[1] + len(FILENAME_HOOK[2]))
        labels["filename"] = address(start, 112) - va
        helper = f.assemble()
        require(len(helper) <= 112, "filename helper budget")
        body.extend(helper)
    require(len(body) <= CODE_SIZE, "venue text/filename budget")
    edits = []
    for label, site, before in HOOKS + (() if legacy else (FILENAME_HOOK,)):
        opcode = b"\xe8" if label in ("report", "presentation") else b"\xe9"
        edits.append((site, before, (opcode + struct.pack("<i", va + labels[label] - site - 5)).ljust(len(before), b"\x90")))
    if selector:
        edits.append(selector)
    return bytes(body).ljust(CODE_SIZE, b"\xcc"), edits


def allocation(payload):
    found = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not found:
        return None
    require(all(r["kind"] == "code" for r in found) and sum(r["size"] for r in found) == CODE_SIZE,
            "reserve moment venues in the complete owner union")
    found.sort(key=lambda r: r["owner_offset"])
    return dict(found[0], size=CODE_SIZE, spans=found)


def _recognize(payload):
    image, owned = XbeImage(payload), allocation(payload)
    body, edits = code_for(owned["va"] if owned else 0, owned["spans"] if owned else None)
    states = {"retail" if image.read(site, len(before)) == before else
              "applied" if owned and image.read(site, len(after)) == after else "foreign"
              for site, before, after in edits}
    mismatched = bool(owned) and states == {"applied"} and b"".join(
        image.read(r["va"], r["size"]) for r in owned["spans"]) != body  # b777 ar1: the other ball layout shares every hook
    if (states not in ({"retail"}, {"applied"}) or mismatched) and owned:
        old, old_edits = code_for(owned["va"], owned["spans"], legacy=True)
        if (all(image.read(site, len(after)) == after for site, _, after in old_edits)
                and image.read(FILENAME_HOOK[1], len(FILENAME_HOOK[2])) == FILENAME_HOOK[2]
                and b"".join(image.read(r["va"], r["size"]) for r in owned["spans"]) == old):
            return "legacy"
        # Every earlier complete owner this module wrote, upgraded in place by apply(): the other ball layout (b777
        # ar1: the era ball selector present when it is switched off, or absent when it is switched on) and the b776
        # body without the Situation test (b777-sm2), in either ball layout (the b776 disc: ball on, no flag test).
        from . import nfl2k5_era_ball as era_ball
        want_ball = era_ball.enabled()
        current = b"".join(image.read(r["va"], r["size"]) for r in owned["spans"])
        for ball, situation in ((not want_ball, True), (want_ball, False), (not want_ball, False)):
            previous, previous_edits = code_for(owned["va"], owned["spans"], ball=ball, situation=situation)
            hook_ok = ball or image.read(era_ball.HOOK[1], len(era_ball.HOOK[2])) == era_ball.HOOK[2]
            if (all(image.read(site, len(after)) == after for site, _, after in previous_edits) and hook_ok
                    and current == previous):
                return "previous"
    require(states in ({"retail"}, {"applied"}), "foreign/mixed venue hooks")
    state = next(iter(states))
    if owned:
        expected = (b"\xcc" * CODE_SIZE, body) if state == "retail" else (body,)
        require(b"".join(image.read(r["va"], r["size"]) for r in owned["spans"]) in expected, "foreign venue body")
    return state


def status(payload):
    try:
        return _recognize(payload)
    except (ValueError, KeyError, IndexError, TypeError, struct.error):
        return "foreign"


def underlying(payload):
    """m1 may normalize its overlapping preview guard only after full verification."""
    state = _recognize(payload)
    if state == "retail":
        return payload
    from . import nfl2k5_era_ball as era_ball
    out, image = bytearray(payload), XbeImage(payload)
    for _label, site, before in HOOKS + (FILENAME_HOOK, era_ball.HOOK):
        at = image.offset(site, len(before))
        out[at:at + len(before)] = before
    return seal(out)


def seal(out):
    for section in _sections(out):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(out, section)
    return bytes(out)


def apply(payload, *, enabled=True):
    before = _recognize(payload)
    desired = "applied" if enabled else "retail"
    if before == desired:
        return payload, dict(status="already_" + desired, owner=OWNER, changed_bytes=0)
    original = payload
    if allocation(payload) is None:
        require(space.status(payload) == "retail", "moment venues missing from complete owner union")
        payload, _ = space.apply(payload, REQUESTS)
    from . import nfl2k5_era_ball as era_ball
    owned = allocation(payload)
    body, edits = code_for(owned["va"], owned["spans"])
    if enabled:
        if before in ("legacy", "previous"):
            # _recognize has proved every byte of the old owner. Retire that
            # body before using the allocator's ordinary same-body guard.
            _, _, requests = space._validate(payload)
            cleared, image = bytearray(payload), XbeImage(payload)
            for part in owned["spans"]:
                at = image.offset(part["va"], part["size"])
                cleared[at:at + part["size"]] = b"\xcc" * part["size"]
            if space.is_scaleout(payload):
                space._seal_scaleout(cleared, requests)
            else:
                cleared[space.DIRECTORY:space._directory_end(requests)] = space._directory(
                    requests, space._code_bytes(cleared, requests))
            payload = seal(cleared)
        payload, _ = space.install_code(payload, OWNER, body)
    out, image = bytearray(payload), XbeImage(payload)
    for site, retail, installed in edits:
        at = image.offset(site, len(retail))
        out[at:at + len(retail)] = installed if enabled else retail
    if not any(site == era_ball.HOOK[1] for site, _, _ in edits):
        # b777 ar1: with the era ball off, a ball hook left by an earlier build goes back to the retail push.
        at = image.offset(era_ball.HOOK[1], len(era_ball.HOOK[2]))
        out[at:at + len(era_ball.HOOK[2])] = era_ball.HOOK[2]
    result = seal(out)
    require(status(result) == desired, "venue read-back failed")
    return result, dict(status=desired, owner=OWNER, rows=51, dedicated_field_aliases=True, runtime_witnessed=False,
                        data_sha256=hashlib.sha256(DATA.read_bytes()).hexdigest(),
                        changed_bytes=sum(a != b for a, b in zip(original, result)))

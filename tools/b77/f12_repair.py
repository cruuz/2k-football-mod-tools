#!/usr/bin/env python3
"""Job f12 (beta 77): put the 2026 league's years pro, and its career-stat slots, into the game's convention.

The game stores years pro with a rookie as 1 (the Player Card prints R for exactly that value; the Postseason rollover
adds 1 to every allocated non-prospect; the Preseason aging applies curve[y] - curve[y-1]; a player's k-th pro season
lives in career-stat history slot k).  The SOFTDRINK 2K28 v0.5 league build wrote nflverse ``years_exp`` (completed
seasons, rookie = 0), so every 2026 draftee read 0, every 2025 draftee read R, every veteran was one year low, and the
career-stat rookie season sat in slot 0.

This writer changes only what it owns, in the v0.5 main ROST resource (``vc_53450030/0`` outer entry 5, body at +0x20):

  1. byte +0x25 bits 0-4 of each cohort record (``years_pro`` += 1; bits 5-7 and every other byte of the record stay), and
  2. bits 23-27 (the slot, +1) of every history word of each cohort player's private stream; the stream length, the
     pointer, the terminator bit, the postseason/folded/deleted flags, the field id and the value are untouched.

The cohort is ``f12_cohort.json``: 2,072 primary records, each pinned by index, name, birth date and its current
years pro, and each cross-checked against nflverse when the file was built.  Nothing else in the pack is written.
default.xbe is not touched (the rollover and aging code are correct for the game's own convention).

Input must be the v0.5 ``vc_53450030/0`` (or its bare ROST body), the output of this writer (an idempotent replay), or
an exact composed input approved with ``--approved-input-sha256``; every pinned record must still match its pin or
the whole run is refused and nothing is written.

  python3 tools/b77/f12_repair.py --input PACK0 --output OUT --receipt RECEIPT.json [--approved-input-sha256 HEX]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_career_stats as cs  # noqa: E402
from mod_editor.core import nfl2k5_save_rost as sr  # noqa: E402

TOOL = "tools/b77/f12_repair.py"
SCHEMA = "nfl2k5_b77_f12_repair/v1"
COHORT_PATH = Path(__file__).with_name("f12_cohort.json")
COHORT_SCHEMA = "nfl2k5_b77_f12_cohort/v1"

V05_PACK0_SHA256 = "b2c48dd3a3e8c7b5e75a596f83b9f6ef64e6c7c00b613611ed5e9e88b790fd72"
V05_ROST_BODY_SHA256 = "854a1e73a339ed34f89984701d9e3bb7be4a7237bd5566a2818d6a07b1b05a27"
# filled from the deterministic output of this writer on the v0.5 inputs (see the receipt)
F12_PACK0_SHA256 = "f47a9bf5063dd13127869c95c260ac50be5ca89a571daa3795ff037eb154d57f"
F12_ROST_BODY_SHA256 = "97bbf021b8a6dbd743f163d86a71db6fc2483cd40740aafbbe8534bf75da35a9"

ROST_OUTER_INDEX = 5
OUTER_ENTRY_TABLE = 0x9C
RESOURCE_HEADER_SIZE = 0x20
BODY_SIZE_V05 = 593760
REFERENCE_YEAR = 2026
YEARS_PRO_BYTE = 0x25
YEARS_PRO_MASK = 0x1F
SLOT_SHIFT = 23
SLOT_MASK = 0x1F << SLOT_SHIFT
# the sample table of the receipt: named players the report discusses (first, last, birth date)
SAMPLES = (("Cam", "Ward", "2002-05-25"), ("Travis", "Hunter", "2003-05-18"), ("Jaxson", "Dart", "2003-05-13"),
           ("Fernando", "Mendoza", "2003-10-01"), ("Jeremiyah", "Love", "2005-05-31"),
           ("Patrick", "Mahomes", "1995-09-17"), ("Travis", "Kelce", "1989-10-05"), ("Aaron", "Rodgers", "1983-12-02"))


class RepairRefused(ValueError):
    """The input is not what this writer owns; nothing was written."""


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RepairRefused(message)


def load_cohort(path: Path = COHORT_PATH) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    require(data.get("schema") == COHORT_SCHEMA, "unknown cohort schema")
    require(data["columns"] == ["index", "first", "last", "birth_date", "old_years_pro", "basis"], "unexpected cohort columns")
    require(data["rost_body_sha256"] == V05_ROST_BODY_SHA256 and data["pack0_sha256"] == V05_PACK0_SHA256,
            "the cohort was not built from the v0.5 pack")
    rows = {}
    for index, first, last, birth, years_pro, basis in data["records"]:
        require(index not in rows and basis in data["basis_codes"] and 0 <= years_pro <= 30, f"bad cohort row {index}")
        rows[index] = (first, last, birth, years_pro, basis)
    require(len(rows) == data["counts"]["records"], "cohort size differs from its header")
    data["_rows"] = rows
    data["_file_sha256"] = sha(Path(path).read_bytes())
    return data


def locate_rost(pack: bytes) -> tuple[int, int]:
    require(len(pack) > 0x1000, "truncated outer archive")
    count, reserved, populated = struct.unpack_from("<3I", pack)
    require(6 <= count <= 100000 and not reserved and 1 <= populated <= 36, "unexpected outer archive header")
    _name, size, blocks = struct.unpack_from("<3I", pack, OUTER_ENTRY_TABLE + ROST_OUTER_INDEX * 12)
    offset = blocks * 0x800
    require(offset + size <= len(pack) and pack[offset:offset + 4] == b"ROST", "outer entry 5 is not a ROST resource")
    require(size >= RESOURCE_HEADER_SIZE + BODY_SIZE_V05, "the ROST resource is smaller than the v0.5 main roster")
    return offset, size


def changed_ranges(before: bytes, after: bytes, base: int = 0) -> list[list[int]]:
    ranges, start = [], None
    for i, (a, b) in enumerate(zip(before, after)):
        if a != b and start is None:
            start = i
        elif a == b and start is not None:
            ranges.append([base + start, base + i])
            start = None
    if start is not None:
        ranges.append([base + start, base + len(before)])
    return ranges


def plan(body: bytes, cohort: dict) -> dict:
    """Decode, pin-check and decide the state of the input. Raises RepairRefused for anything unexpected."""
    try:
        decoded = sr.decode(body, preamble=0, reference_year=REFERENCE_YEAR)
    except (sr.SaveRostError, ValueError) as exc:
        raise RepairRefused(f"the ROST body does not decode: {exc}") from exc
    rows = cohort["_rows"]
    states, players = set(), {}
    for index, (first, last, birth, old, _basis) in sorted(rows.items()):
        player = decoded.by_key.get(("primary", index))
        require(player is not None, f"cohort record {index} is absent")
        actual_birth = player.record.birth_date.isoformat() if player.record.birth_date else ""
        require((player.first, player.last, actual_birth) == (first, last, birth),
                f"record {index} is {player.first} {player.last} {actual_birth}, not the pinned {first} {last} {birth}")
        years_pro = player.record.values["years_pro"]
        if years_pro == old:
            states.add("old")
        elif years_pro == old + 1:
            states.add("new")
        else:
            raise RepairRefused(f"{first} {last} ({index}) has years pro {years_pro}; pinned {old} (or {old + 1} after the repair)")
        players[index] = player
    require(len(states) == 1, "the cohort is half repaired (both old and new years pro are present)")
    state = states.pop()
    # history streams: each cohort stream is private to cohort players, and consistent with the state
    cohort_keys = {("primary", index) for index in rows}
    starts: dict[int, tuple] = {}
    for key in cohort_keys:
        start = decoded.history_offsets.get(key)
        if start is None:
            continue
        require(start not in starts or starts[start] == decoded.history_words[key], "shared stream with different words")
        starts[start] = decoded.history_words[key]
    for key, start in decoded.history_offsets.items():
        require(key in cohort_keys or start not in starts, f"{key} shares a history stream with the cohort")
    for index, player in players.items():
        yp = player.record.values["years_pro"]
        words = decoded.history_words[("primary", index)]
        for raw in words:
            slot = cs.Word(raw).slot
            if state == "old":
                require(0 <= slot <= yp - 1, f"{player.first} {player.last}: history slot {slot} is at or after the current season ({yp})")
            else:
                require(1 <= slot <= yp - 1, f"{player.first} {player.last}: years pro is repaired but history slot {slot} is not")
    return {"decoded": decoded, "state": state, "players": players, "streams": starts}


def apply_plan(body: bytes, state_plan: dict) -> bytes:
    out = bytearray(body)
    decoded = state_plan["decoded"]
    for index, player in state_plan["players"].items():
        at = player.offset + YEARS_PRO_BYTE
        current = out[at] & YEARS_PRO_MASK
        out[at] = (out[at] & ~YEARS_PRO_MASK & 0xFF) | (current + 1)
    for start, words in sorted(state_plan["streams"].items()):
        for i, raw in enumerate(words):
            slot = (raw & SLOT_MASK) >> SLOT_SHIFT
            require(slot + 1 <= 31, "history slot overflow")
            struct.pack_into("<I", out, start + 4 * i, raw + (1 << SLOT_SHIFT))
    return bytes(out)


def allowed_mask(body_size: int, state_plan: dict) -> bytearray:
    """Bits the writer may change: years_pro bits 0-4 of +0x25 and bits 23-27 of each cohort history word."""
    mask = bytearray(body_size)
    for player in state_plan["players"].values():
        mask[player.offset + YEARS_PRO_BYTE] |= YEARS_PRO_MASK
    for start, words in state_plan["streams"].items():
        for i in range(len(words)):
            at = start + 4 * i
            mask[at + 2] |= 0x80       # slot bit 0 is dword bit 23 = byte 2 bit 7
            mask[at + 3] |= 0x0F       # slot bits 1-4 are dword bits 24-27 = byte 3 bits 0-3
    return mask


def prove_scope(before: bytes, after: bytes, state_plan: dict) -> dict:
    mask = allowed_mask(len(before), state_plan)
    escaped = [i for i, (a, b, m) in enumerate(zip(before, after, mask)) if (a ^ b) & ~m & 0xFF]
    require(not escaped, f"a write escaped the declared scope at body offsets {escaped[:8]}")
    outside_before = bytes(a & ~m & 0xFF for a, m in zip(before, mask))
    outside_after = bytes(a & ~m & 0xFF for a, m in zip(after, mask))
    require(outside_before == outside_after, "bits outside the declared scope differ")
    record_bytes = sorted(p.offset + YEARS_PRO_BYTE for p in state_plan["players"].values())
    streams = sorted((start, start + 4 * len(words)) for start, words in state_plan["streams"].items())
    merged = []
    for lo, hi in streams:
        if merged and merged[-1][1] == lo:
            merged[-1][1] = hi
        else:
            merged.append([lo, hi])
    return {"outside_scope_identical": True, "outside_scope_masked_sha256": sha(outside_before),
            "declared_record_years_pro_bytes": {"count": len(record_bytes), "mask": "0x1f", "body_offsets": record_bytes},
            "declared_history_word_ranges": {"count": len(merged), "words": sum(len(w) for w in state_plan["streams"].values()),
                                              "masks": {"byte2": "0x80", "byte3": "0x0f"}, "body_ranges": merged},
            "changed_bytes": sum(a != b for a, b in zip(before, after))}


def verify_result(before_plan: dict, after_body: bytes, cohort: dict) -> dict:
    """Independent read-back: decode the output and compare it with the input field by field."""
    after = plan(after_body, cohort)
    require(after["state"] == "new", "the output is not in the repaired state")
    before_decoded, after_decoded = before_plan["decoded"], after["decoded"]
    seasons = rookies = 0
    for index, old_player in before_plan["players"].items():
        new_player = after["players"][index]
        old_values, new_values = dict(old_player.record.values), dict(new_player.record.values)
        require(new_values["years_pro"] == old_values["years_pro"] + 1, f"record {index}: years pro")
        old_values["years_pro"] = new_values["years_pro"]
        require(old_values == new_values, f"record {index}: another field changed")
        old_words = before_decoded.history_words[("primary", index)]
        new_words = after_decoded.history_words[("primary", index)]
        require(len(old_words) == len(new_words), f"record {index}: stream length")
        for a, b in zip(old_words, new_words):
            wa, wb = cs.Word(a), cs.Word(b)
            require((wb.slot, wb.field, wb.phase, wb.deleted, wb.folded, b & 0xFFFF, b >> 31)
                    == (wa.slot + 1, wa.field, wa.phase, wa.deleted, wa.folded, a & 0xFFFF, a >> 31), f"record {index}: word")
            seasons += 1 if wb.field == 0 else 0
        rookies += 1 if new_values["years_pro"] == 1 else 0
    # every non-cohort player is identical, including the streams
    cohort_keys = {("primary", index) for index in cohort["_rows"]}
    for player in before_decoded.players:
        if player.key in cohort_keys:
            continue
        other = after_decoded.by_key[player.key]
        require(player.record.values == other.record.values, f"{player.key}: a non-cohort record changed")
        require(before_decoded.history_words[player.key] == after_decoded.history_words[player.key], f"{player.key}: stream changed")
    return {"games_rows_shifted": seasons, "rookies_after": rookies}


def sample_rows(before_plan: dict, after_plan: dict) -> list[dict]:
    rows = []
    names = {(p.first, p.last, p.record.birth_date.isoformat() if p.record.birth_date else ""): i
             for i, p in before_plan["players"].items()}
    for first, last, birth in SAMPLES:
        index = names.get((first, last, birth))
        if index is None:
            continue
        old, new = before_plan["players"][index], after_plan["players"][index]
        slots = lambda decoded, key: sorted({cs.Word(w).slot for w in decoded.history_words[key]})  # noqa: E731
        rows.append({"index": index, "name": f"{first} {last}",
                     "years_pro_before": old.record.values["years_pro"], "years_pro_after": new.record.values["years_pro"],
                     "history_slots_before": slots(before_plan["decoded"], ("primary", index)),
                     "history_slots_after": slots(after_plan["decoded"], ("primary", index))})
    return rows


def repair_body(body: bytes, *, cohort: dict | None = None, approved_input_sha256: tuple[str, ...] = ()) -> tuple[bytes, dict]:
    cohort = cohort or load_cohort()
    digest = sha(body)
    known = {V05_ROST_BODY_SHA256} | ({F12_ROST_BODY_SHA256} if F12_ROST_BODY_SHA256 else set())
    approved = digest not in known
    require(not approved or digest in approved_input_sha256,
            f"unexpected ROST body sha256 {digest}; pass --approved-input-sha256 for an exact composed input")
    state_plan = plan(body, cohort)
    if state_plan["state"] == "new":
        after_plan = state_plan
        out = body
        scope = {"outside_scope_identical": True, "changed_bytes": 0}
        receipt_state = "already_applied"
        sample = sample_rows(state_plan, after_plan)
        extra = {}
    else:
        out = apply_plan(body, state_plan)
        scope = prove_scope(body, out, state_plan)
        extra = verify_result(state_plan, out, cohort)
        after_plan = plan(out, cohort)
        receipt_state = "applied"
        sample = sample_rows(state_plan, after_plan)
    return out, {"schema": SCHEMA, "tool": TOOL, "state": receipt_state, "approved_composed_input": approved,
                 "cohort": {"file_sha256": cohort["_file_sha256"], "records": len(cohort["_rows"]),
                            "basis": cohort["counts"]["basis"], "club": cohort["counts"]["club"],
                            "free_agent": cohort["counts"]["free_agent"]},
                 "history": {"players_with_streams": sum(1 for i in state_plan["players"]
                                                          if state_plan["decoded"].history_words[("primary", i)]),
                             "streams": len(state_plan["streams"]),
                             "words": sum(len(w) for w in state_plan["streams"].values())},
                 "rookies": sum(1 for p in after_plan["players"].values() if p.record.values["years_pro"] == 1),
                 "before_rost_body_sha256": digest, "after_rost_body_sha256": sha(out), "scope": scope,
                 "verification": extra, "samples": sample}


def repair_pack0(pack: bytes, *, cohort: dict | None = None, approved_input_sha256: tuple[str, ...] = ()) -> tuple[bytes, dict]:
    digest = sha(pack)
    known = {V05_PACK0_SHA256} | ({F12_PACK0_SHA256} if F12_PACK0_SHA256 else set())
    composed = digest not in known
    require(not composed or digest in approved_input_sha256,
            f"unexpected pack 0 sha256 {digest}; pass --approved-input-sha256 for an exact composed input")
    offset, size = locate_rost(pack)
    body_at = offset + RESOURCE_HEADER_SIZE
    body = pack[body_at:offset + size]
    new_body, receipt = repair_body(body, cohort=cohort,
                                    approved_input_sha256=(sha(body),) if composed else ())
    out = pack[:body_at] + new_body + pack[offset + size:]
    require(len(out) == len(pack) and out[:body_at] == pack[:body_at] and out[offset + size:] == pack[offset + size:],
            "bytes outside the ROST body changed")
    scope = receipt["scope"]
    declared = {}
    if "declared_record_years_pro_bytes" in scope:
        declared = {"years_pro_bytes": {"mask": "0x1f", "pack_offsets": [body_at + o for o in
                                                                         scope["declared_record_years_pro_bytes"]["body_offsets"]]},
                    "history_words": {"masks": {"byte2": "0x80", "byte3": "0x0f"},
                                      "pack_ranges": [[body_at + lo, body_at + hi] for lo, hi in
                                                      scope["declared_history_word_ranges"]["body_ranges"]]}}
    changed = changed_ranges(body, new_body, body_at) if new_body != body else []
    receipt.update(disc_file="vc_53450030/0", before_file_sha256=digest, after_file_sha256=sha(out), size=len(out),
                   rost_resource_pack_offset=offset, rost_resource_size=size, rost_body_pack_offset=body_at,
                   outside_roster_identical=True, approved_composed_input=composed, declared_pack_scope=declared,
                   changed_byte_runs={"count": len(changed), "sha256_of_run_list": sha(json.dumps(changed).encode())})
    return out, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True, help="extracted vc_53450030/0, or a bare ROST body")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, default=COHORT_PATH)
    parser.add_argument("--approved-input-sha256", action="append", default=[])
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("the output must be a separate file")
    if args.output.exists() or args.receipt.exists():
        parser.error("output or receipt already exists; choose fresh paths")
    for digest in args.approved_input_sha256:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            parser.error("approvals must be exact lowercase SHA-256 values")
    raw = args.input.read_bytes()
    cohort = load_cohort(args.cohort)
    try:
        if len(raw) < 8_000_000 and raw[0x0C:0x10] == b"ROST":      # a bare ROST body; pack 0 is 194 MB
            out, receipt = repair_body(raw, cohort=cohort, approved_input_sha256=tuple(args.approved_input_sha256))
        else:
            out, receipt = repair_pack0(raw, cohort=cohort, approved_input_sha256=tuple(args.approved_input_sha256))
    except RepairRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)
    args.receipt.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"state": receipt["state"], "records": receipt["cohort"]["records"],
                      "history_words": receipt["history"]["words"], "changed_bytes": receipt["scope"]["changed_bytes"],
                      "before": receipt.get("before_file_sha256", receipt["before_rost_body_sha256"]),
                      "after": receipt.get("after_file_sha256", receipt["after_rost_body_sha256"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

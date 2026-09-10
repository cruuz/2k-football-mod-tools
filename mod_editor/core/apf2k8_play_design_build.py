"""Build verified MASTER and CPU SPLB entries, without writing game files."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Mapping

from . import apf2k8_play_codec as c
from . import apf2k8_splb_writer as splb
from .apf2k8_play_designer import compile_design, normalize_plan, sha
from .apf2k8_playbook_route_writer import apf_inner, apf_outer, apf_texture_patch
from .errors import ValidationError

CPU_PINS = {
    130: "18de1e3ee886aceba6535be2c8472d0af3f5554f8c9023d553068005416dd1f5",
    134: "2191bc3a494f58d279e79449abd6f619b83dd8b7170b86847ae445c930c4b428",
    259: "2fd2b7587127120f90cb5fb536abe6c2691303fda08ca544b1aeaa271e1b9016",
    369: "63a55ab11da38dcbdabc3107fa44d4aa26c1b61e0a1b6cfb0595cffdfac8a015",
    618: "67ef383cc1fcde7a44639fa761fbb4efbd82aa3d4560035d27abd704d30ae218",
    767: "d7a9c2f703d8892929184dce3fef10dd9e9dad29f7506121bfe7ec73ca4a3432",
    891: "9a145a97495f347ccef08b719d9e20cde4b9bf7b1546d03a7ca99f9545bc6e83",
    943: "8a23184ad5675ff5cc6c75fcfa92c3006537e8bfd2d730a6bccc122b1cb0dcca",
    957: "a2ce06b26b10dd3b9be637553fef01e4f961c9f74cfc162be35b5267fd301fa3",
    1405: "45ee87e572dfa573c82db722e95b45b4d999efea9d822276b73d1a832e939dcf",
    1411: "07ad3538b6ff994600b1f0b468bea0b962e758fa42444f242d89bc79f0a32797",
}

@dataclass(frozen=True)
class Resource:
    entry: object
    original: bytes
    body: bytes
    record: object


def parse_resource(entry, original: bytes) -> Resource:
    """Single file/single H7A block contract shared by MASTER and CPU books."""
    if len(original) != entry.size:
        raise ValidationError("Outer allocation size changed.")
    memory = apf_texture_patch.BytesReader(original)
    try:
        record = apf_inner.parse_iff(memory, entry)
        if record.warnings or record.footer is None or record.block_count != 1 or record.file_count != 1:
            raise ValidationError("Design requires one warning-free IFF file and block.")
        file = record.files[0]
        if len(file.parts) != 1 or file.parts[0].block_index != 0:
            raise ValidationError("Design IFF part ownership changed.")
        descriptor = record.blocks[0]
        if descriptor.wrapper is None or not descriptor.is_compressed:
            raise ValidationError("Design resource must be H7A compressed.")
        block = apf_inner.decode_block(memory, record, 0, 4 * 1024 * 1024)
        part = file.parts[0]
        if part.offset != 0 or part.length != len(block):
            raise ValidationError("Design resource must exclusively own its decoded block.")
        return Resource(entry, original, block, record)
    except (ValueError, IndexError) as exc:
        raise ValidationError(f"Invalid APF design IFF: {exc}") from exc


def read_resource(index: Path, outer: int) -> Resource:
    archive = apf_outer.parse_archive(Path(index))
    entry = archive.entries[outer]
    with apf_inner.ArchiveReader(archive) as reader:
        resource = parse_resource(entry, reader.read(entry, 0, entry.size))
    file = resource.record.files[0]
    if outer == 180:
        if entry.name_id != 487346054 or file.file_id != 0x33CDF8E3 or file.name != "mpb" or file.type_name != "PLAY" or file.type_hash != 0x681C330E or sha(resource.body) != c.MASTER_SHA256:
            raise ValidationError("MASTER retail identity/SHA-256 pin failed.")
    else:
        if outer not in splb.STOCK_BOOKS or not splb.STOCK_BOOKS[outer] or file.name != "spb" or file.type_name != "SPLB":
            raise ValidationError("Only named on-disc CPU books are writable.")
        book = splb.parse_book(resource.body, outer)
        if book.name != splb.STOCK_BOOKS[outer] or sha(resource.body) != CPU_PINS[outer]:
            raise ValidationError("CPU book identity pin failed.")
    return resource


def _safe_stream(payload: bytes, body: bytes, shift: int) -> bool:
    if apf_inner.decompress_h7a(payload, len(body), shift) != body:
        return False
    tokens, _ = apf_inner._parse_h7a_tokens(payload, len(body), shift)
    return all(t.kind != "match" or t.length <= t.distance for t in tokens)


def pack_resource(resource: Resource, body: bytes) -> tuple[bytes, dict]:
    if len(body) != len(resource.body):
        raise ValidationError("Design changed the fixed decoded resource allocation.")
    record, original, entry = resource.record, resource.original, resource.entry
    descriptor = record.blocks[0]
    shift = descriptor.wrapper.shift
    previous = original[descriptor.start_offset + 20:descriptor.start_offset + descriptor.stored_length]
    candidates = []
    preserved, _ = apf_inner.encode_h7a_preserving_tokens(previous, resource.body, body, shift)
    if _safe_stream(preserved, body, shift):
        candidates.append((preserved, "token preserving"))
    greedy = apf_texture_patch.compress_h7a(body, shift)
    best = apf_texture_patch.compress_h7a_best(body, shift, greedy=greedy)
    if _safe_stream(best, body, shift):
        candidates.append((best, "optimal" if len(best) < len(greedy) else "greedy"))
    if not candidates:
        raise ValidationError("No exact H7A stream satisfies the no-overlap rule.")
    payload, strategy = min(candidates, key=lambda pair: len(pair[0]))
    stored = struct.pack(">5I", apf_inner.H7A_MAGIC, len(body), 20 + len(payload), descriptor.unknown_10, shift) + payload
    header = bytearray(original[:record.header_size])
    struct.pack_into(">I", header, 0x08, len(header) + len(stored))
    struct.pack_into(">8I", header, 32, descriptor.name_hash, descriptor.type_hash, descriptor.unknown_08,
        len(body), descriptor.unknown_10, len(header), len(stored), descriptor.indexed)
    footer_end = record.file_length + 8 + record.footer.payload_size
    if any(original[footer_end:]):
        raise ValidationError("The outer allocation has a nonzero tail.")
    active = bytes(header) + stored + original[record.file_length:footer_end]
    if len(active) > entry.size:
        raise ValidationError(f"Design requires {len(active)} compressed allocation bytes; only {entry.size} are available.")
    replacement = active + bytes(entry.size - len(active))
    reparsed = parse_resource(entry, replacement)
    if reparsed.body != body or reparsed.record.files != record.files:
        raise ValidationError("Rebuilt IFF differs from the designed body or file ownership.")
    return replacement, {"outer": entry.table_index, "allocation_bytes": entry.size,
        "original_active_bytes": footer_end, "active_bytes": len(active), "free_bytes": entry.size - len(active),
        "payload_bytes": len(payload), "strategy": strategy, "h7a_round_trip_exact": True,
        "overlapping_matches": 0, "reparsed": True, "entry_sha256": sha(replacement)}


def compile_cpu_calls(source: bytes, outer: int, master_source: bytes, master_after: bytes, calls: list[dict], *, current: bytes | None = None) -> tuple[bytes, dict]:
    """Reuse SPLB's entry/tag writer; new formations use an explicit empty row.

    Existing rows must already name the requested formation. New rows inherit
    the donor trailer's unknown fields, get only the requested entries, and
    normalize word B to the destination personnel category. No user-save
    addressing exists in this module.
    """
    before_master, after_master = c.Book.from_bytes(master_source), c.Book.from_bytes(master_after)
    original_book = splb.parse_book(source, outer)
    if outer not in splb.STOCK_BOOKS or not splb.STOCK_BOOKS[outer] or original_book.name != splb.STOCK_BOOKS[outer]:
        raise ValidationError("Select a named CPU book.")
    working = bytearray(source)
    claimed = {}
    changes = []
    for call in calls:
        if call["outer"] != outer:
            raise ValidationError("CPU calls belong to different books.")
        pi, fi, ri = call["play"], call["formation"], call["record"]
        c.bounded(pi, 0, len(after_master.plays) - 1, "Callable play")
        c.bounded(fi, 0, len(after_master.formations) - 1, "Callable formation")
        c.bounded(ri, 0, 175, "CPU record")
        play_type = after_master.plays[pi].type_nibble
        if (original_book.name.startswith("O-") and play_type != 0) or (original_book.name.startswith("X-") and play_type != 1):
            raise ValidationError("Play side does not match the selected CPU book.")
        row = original_book.records[ri]
        signature = (fi, call["donor_record"])
        if ri in claimed and claimed[ri] != signature:
            raise ValidationError("A CPU record was assigned two different formations/donors.")
        if ri not in claimed:
            if row.entries:
                if row.formation_index != fi or call["donor_record"] is not None:
                    raise ValidationError("Use a matching populated CPU row or an explicit empty row.")
            else:
                donor = call["donor_record"]
                c.bounded(donor, 0, 175, "Donor CPU record for the empty row")
                donor_row = original_book.records[donor]
                if not donor_row.entries:
                    raise ValidationError("The CPU donor record must be populated.")
                source_fi = donor_row.formation_index
                c.bounded(source_fi, 0, len(before_master.formations) - 1, "Donor formation")
                formation = after_master.formations[fi]
                if formation.category_index != donor_row.category_index or formation.category_index != before_master.formations[source_fi].category_index:
                    raise ValidationError("New CPU row must retain the donor's personnel category.")
                # Require the same slot identity/order; coordinates and name can
                # change, but remapping players needs a separate proved writer.
                donor_formation = before_master.formations[source_fi]
                if formation.eligible_order != donor_formation.eligible_order or formation.slot_order != donor_formation.slot_order:
                    raise ValidationError("New CPU formation must preserve donor slot ordering.")
                at = splb.RECORD_BASE + ri * splb.RECORD_STRIDE + splb.TRAILER_OFFSET
                a, b = struct.unpack(">II", donor_row.trailer)
                struct.pack_into(">II", working, at, (a & 0xFFFFFF) | fi << 24, 1 << formation.category_index)
                mask = struct.unpack_from(">I", working, splb.BOOK_CATEGORY_MASK_OFFSET)[0]
                struct.pack_into(">I", working, splb.BOOK_CATEGORY_MASK_OFFSET, mask | (1 << donor_row.category_index))
            claimed[ri] = signature
        changes.append(splb.MembershipChange(outer, ri, pi, True))
    if not changes:
        raise ValidationError("No CPU calls were requested.")
    staged = bytes(working)
    compiled = splb.compile_book(splb.parse_book(staged, outer), changes, master_play_count=len(after_master.plays))
    splb.verify_book(staged, compiled.replacement, changes, master_play_count=len(after_master.plays))
    parsed = splb.parse_book(compiled.replacement, outer)
    allowed = {splb.BOOK_CATEGORY_MASK_OFFSET + i for i in range(4)}
    for ri, (fi, donor) in claimed.items():
        at = splb.RECORD_BASE + ri * splb.RECORD_STRIDE
        allowed.update(range(at, at + splb.ENTRY_BYTES))
        if donor is not None:
            allowed.update(range(at + splb.TRAILER_OFFSET, at + splb.RECORD_STRIDE))
        if donor is not None:
            expected_category = after_master.formations[fi].category_index
            if (parsed.records[ri].category_index != expected_category
                    or int.from_bytes(parsed.records[ri].trailer[4:], "big") != 1 << expected_category):
                raise ValidationError("CPU reparse retained donor personnel memberships.")
        if parsed.records[ri].formation_index != fi:
            raise ValidationError("CPU reparse did not resolve the requested formation.")
    if any(a != b and i not in allowed for i, (a, b) in enumerate(zip(source, compiled.replacement))):
        raise ValidationError("CPU creation changed an unowned byte.")
    if current is not None and current not in (source, compiled.replacement):
        raise ValidationError("Current CPU book differs from the baseline and requested design.")
    return compiled.replacement, {"outer": outer, "source_sha256": sha(source), "replacement_sha256": sha(compiled.replacement),
        "already_applied": current == compiled.replacement,
        "records": sorted(claimed), "personnel": [
            {"record_index": ri, "formation_after": fi,
             "category_before": original_book.records[ri].category_index,
             "category_after": parsed.records[ri].category_index,
             "word_b_before": int.from_bytes(original_book.records[ri].trailer[4:], "big"),
             "word_b_after": int.from_bytes(parsed.records[ri].trailer[4:], "big")}
            for ri, (fi, donor) in claimed.items()], "reparsed": True, "cpu_only": True, "user_save_written": False}


@dataclass(frozen=True)
class DesignBuild:
    entries: dict[int, bytes]
    report: dict


def build_design(index: Path, plan: Mapping) -> DesignBuild:
    plan = normalize_plan(plan)
    master = read_resource(index, 180)
    compiled = compile_design(master.body, plan)
    entries, reports = {}, []
    # Compile and verify every resource before the caller receives any writes.
    if compiled.replacement != master.body:
        entries[180], receipt = pack_resource(master, compiled.replacement)
        reports.append(receipt)
    for outer in sorted({r["outer"] for r in plan["cpu_calls"]}):
        resource = read_resource(index, outer)
        replacement, receipt = compile_cpu_calls(resource.body, outer, master.body, compiled.replacement, [r for r in plan["cpu_calls"] if r["outer"] == outer])
        if replacement != resource.body:
            entries[outer], transport = pack_resource(resource, replacement)
            reports.append({**receipt, **transport})
    return DesignBuild(entries, {"design": compiled.report, "resources": reports, "runtime_status": "UNWITNESSED", "user_saves_written": False})


def main() -> int:
    """Compile in memory and save only a derived verification receipt."""
    import argparse
    import json
    import os
    import tempfile
    from .apf2k8_play_designer import decode_plan

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path, help="Read-only retail 0A index")
    parser.add_argument("--plan", required=True, type=Path, help="User-authored design JSON")
    parser.add_argument("--receipt", required=True, type=Path, help="Derived JSON report; no game bytes")
    args = parser.parse_args()
    try:
        if args.receipt.resolve().is_relative_to(args.index.resolve().parent) or args.receipt.resolve() == args.plan.resolve():
            raise ValidationError("Save the receipt outside the retail tree and separately from the plan.")
        result = build_design(args.index, decode_plan(args.plan.read_bytes()))
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.receipt.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(result.report, stream, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(temporary, args.receipt)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"APF design refused: {exc}\n")
    print(f"APF_DESIGN_VERIFIED entries={sorted(result.entries)}; receipt={args.receipt}; UNWITNESSED in-game")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

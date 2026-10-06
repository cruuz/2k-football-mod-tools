#!/usr/bin/env python3
"""Scoped v0.4 XBE repair: base moves and season-aware Anniversary books.

Input/output are extracted default.xbe files, never a disc. The CLI accepts
the exact published input or its repaired result; integration on a stacked
file requires an explicit expected whole-file SHA256 as well as all native
owner guards. No original input is overwritten. Stadium resource repair is
provided separately by d2_clock_repair.py to avoid whole archive copies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_stock_books as books
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

V04_SHA256 = "5a9dc534b50c7f13b5124bfff9e39c99f96f62be4cc1de33309895c330c75f29"
FIXED_SHA256 = "0df3505a3e741deca1b5b2161afc2ae8fcc0c6debe8126ea03bd8c032263515f"
COMBINED_SHA256 = "477e9cbd109f3aefa4e09a09f8e05d606cf64c9a331a9f2de7dbdfa7f89113b0"
MOVE_MASK = 0x1EC0


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def restore_base_moves(payload):
    """Composes with other valid allocator owners; refuses unexpected own bytes."""
    state, settings = abilities._inspect(payload)
    if state != "applied" or not space.is_scaleout(payload):
        raise ValueError("Expected installed abilities rules v2 and sealed v3 allocator")
    allocation = abilities.allocation(payload)
    old_code, _ = abilities.code_for(allocation["va"], **settings)
    new_settings = dict(settings, lock_right_stick=False, lock_special_moves=False)
    new_code, _ = abilities.code_for(allocation["va"], **new_settings)
    if payload[allocation["raw"]:allocation["raw"] + allocation["size"]] != old_code:
        raise ValueError("Unexpected abilities owner bytes")
    config_at = allocation["raw"] + abilities.assembly.LABELS["unlocked_mask"]
    original_settings = abilities.read_settings(payload)
    requests = space._read_scale_directory(payload)
    buf = bytearray(payload)
    old = bytes(buf[config_at:config_at + 4])
    new = struct.pack("<I", struct.unpack("<I", old)[0] | MOVE_MASK)
    buf[config_at:config_at + 4] = new
    if bytes(buf[allocation["raw"]:allocation["raw"] + allocation["size"]]) != new_code:
        raise ValueError("Non-configuration owner change")
    if old != new:
        space._seal_scaleout(buf, requests)
    result = bytes(buf)
    if abilities.read_settings(result) != dict(original_settings, lock_right_stick=False,
                                                lock_special_moves=False):
        raise ValueError("Abilities repair postcondition failed")
    # The only derived metadata needed: RX content SHA256, directory SHA256,
    # and the two section SHA1 digests containing those modified bytes.
    scopes = [(config_at, config_at + 4, "base move permission mask"),
              (space.SCALE_DIRECTORY + 12, space.SCALE_DIRECTORY + 44,
               "allocator RX SHA256"),
              (space.DIRECTORY + len(space.SCALE_TAG) + 8,
               space.DIRECTORY + len(space.SCALE_TAG) + 40,
               "allocator directory SHA256")]
    image = XbeImage(payload)
    for section in image.sections:
        if any(section.raw <= at < section.raw + section.raw_size
               for at in (config_at, space.SCALE_DIRECTORY + 12)):
            scopes.append((section.header + 36, section.header + 56,
                           section.name + " section SHA1"))
    scopes.sort()
    cursor = 0
    outside_before, outside_after = hashlib.sha256(), hashlib.sha256()
    receipt_scopes = []
    for start, end, label in scopes:
        if start < cursor:
            raise ValueError("Overlapping repair scopes")
        outside_before.update(payload[cursor:start])
        outside_after.update(result[cursor:start])
        receipt_scopes.append(dict(label=label, file_offset=hex(start), size=end-start,
                                   before=payload[start:end].hex(), after=result[start:end].hex()))
        cursor = end
    outside_before.update(payload[cursor:])
    outside_after.update(result[cursor:])
    if len(result) != len(payload) or outside_before.digest() != outside_after.digest():
        raise ValueError("Unexpected byte outside declared repair scope")
    return result, dict(schema="b765.d2.xbe-repair.v1", disc_file="default.xbe",
                        status="applied" if old != new else "already_applied",
                        before_sha256=sha(payload), after_sha256=sha(result),
                        before_settings=original_settings, after_settings=abilities.read_settings(result),
                        scopes=receipt_scopes, size=len(result),
                        changed_bytes=sum(a != b for a, b in zip(payload, result)),
                        outside_scope_sha256=outside_before.hexdigest(), outside_scope_identical=True,
                        allocator_requests_unchanged=requests == space._read_scale_directory(result))


def repair_xbe(payload):
    """Apply both d2 XBE fixes without changing the allocator owner union."""
    original_layout = space.layout(payload)
    owned = books.allocation(payload)
    if owned is None or books.status(payload) not in ("needs_fix", "applied"):
        raise ValueError("Expected installed, recognized stock-book resolver")
    staged, move_receipt = restore_base_moves(payload)
    result, book_receipt = books.apply(staged)
    if space.layout(result) != original_layout:
        raise ValueError("Allocator layout changed during d2 repair")
    scopes = [(int(row["file_offset"], 16), int(row["file_offset"], 16) + row["size"], row["label"])
              for row in move_receipt["scopes"]]
    scopes.append((owned["raw"], owned["raw"] + books.TABLE,
                   "stock-book resolver instructions; alias table unchanged"))
    scopes.sort()
    cursor = 0
    outside_before, outside_after = hashlib.sha256(), hashlib.sha256()
    rows = []
    for start, end, label in scopes:
        if start < cursor:
            raise ValueError("Overlapping d2 repair scopes")
        outside_before.update(payload[cursor:start])
        outside_after.update(result[cursor:start])
        rows.append(dict(label=label, file_offset=hex(start), size=end-start,
                         before=payload[start:end].hex(), after=result[start:end].hex()))
        cursor = end
    outside_before.update(payload[cursor:])
    outside_after.update(result[cursor:])
    if len(result) != len(payload) or outside_before.digest() != outside_after.digest():
        raise ValueError("Unexpected byte outside combined d2 repair scope")
    changed = sum(a != b for a, b in zip(payload, result))
    return result, dict(schema="b765.d2.xbe-repair.v2", disc_file="default.xbe",
                        status="applied" if changed else "already_applied",
                        before_sha256=sha(payload), after_sha256=sha(result), size=len(result),
                        changed_bytes=changed, scopes=rows,
                        abilities=move_receipt, stock_books=book_receipt,
                        stock_book_owner=owned,
                        outside_scope_sha256=outside_before.hexdigest(), outside_scope_identical=True,
                        allocator_requests_unchanged=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-input-sha256", help="Required for a stacked integration input")
    args = parser.parse_args()
    if args.source.is_symlink() or not args.source.is_file():
        parser.error("Source must be a regular non-symlink XBE")
    if args.output.exists() or args.output.is_symlink() or args.receipt.exists() or args.receipt.is_symlink():
        parser.error("Choose new output and receipt paths")
    if args.output.absolute() == args.receipt.absolute():
        parser.error("Output and receipt must differ")
    with args.source.open("rb") as stream:
        payload = stream.read(16 * 1024 * 1024 + 1)
    accepted = {args.expected_input_sha256} if args.expected_input_sha256 else {V04_SHA256, FIXED_SHA256, COMBINED_SHA256}
    if sha(payload) not in accepted:
        parser.error("Unexpected source SHA256; no files written")
    result, receipt = repair_xbe(payload)
    receipt.update(source=str(args.source.absolute()), output=str(args.output.absolute()))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(args.output, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(result)
    with args.receipt.open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: receipt[k] for k in ("status", "before_sha256", "after_sha256", "changed_bytes")}))


if __name__ == "__main__":
    main()

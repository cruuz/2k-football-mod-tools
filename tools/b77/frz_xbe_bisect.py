#!/usr/bin/env python3
"""Build scoped v0.6 executable rollbacks and copy one into a diagnostic disc.

Allocator requests and placements stay at v0.6. Selected payloads/sites come
from the pinned v0.5 executable. Allocator seals and XBE digests are derived.
These are diagnostic artifacts, not game fixes or Studio build recipes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import nfl_uniform_color_xiso_direct_patch as xiso
from mod_editor.core import platform_compat
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import nfl2k5_cpu_money_downs as cpu
from mod_editor.core import nfl2k5_punter_holder as holder
from mod_editor.core import nfl2k5_moment_gun_weight as gun
from mod_editor.core import nfl2k5_stock_books as stock
from mod_editor.core import nfl2k5_letter_grades as grades
from mod_editor.core import nfl2k5_letter_grades_progress as progress
from mod_editor.core import nfl2k5_honors as honors
from mod_editor.core import nfl2k5_period_goalposts as posts
from mod_editor.core import nfl2k5_name_keyboard as keyboard
from tools.b77 import s7_repair, w1_repair

V05_HASH = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
V06_HASH = "b4fec92f4c03d129687405c406d9882387b731615d71eb4cca3a447304e74f30"
VARIANTS = {
    "X0": ("a4",),
    "X1": ("p9",),
    "X2": ("g2", "h1"),
    "X3": ("f4", "f4b", "f5", "s7", "k1", "v1b", "w1"),
}
ALIASES = {"a4pd": "a4", "f5b": "f5"}
# The progression stub calls the grade formatter. Honors keeps its own code
# and does not require a runtime cascade when allocator placements stay fixed.
DEPENDENTS = {"f4": {"f4b"}}
MODULES = {"a4": stock, "p9": cpu, "g2": abilities, "h1": holder,
           "f4": grades, "f4b": progress, "f5": honors, "k1": keyboard,
           "v1b": posts}
JOBS = frozenset((*MODULES, "s7", "w1"))
BINARY = getattr(os, "O_BINARY", 0)
CHUNK = 4 * 1024**2


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def expand(jobs):
    selected = {ALIASES.get(j, j) for j in jobs}
    require(bool(selected) and selected <= JOBS, "unknown or empty repair subset")
    while True:
        more = set().union(*(DEPENDENTS.get(j, set()) for j in selected))
        if more <= selected:
            return sorted(selected)
        selected |= more


def catalog(final):
    """Payload/site spans only. Metadata must never be copied from v0.5."""
    image = XbeImage(final)
    result = {job: [] for job in JOBS}

    def add(job, va, size, label):
        result[job].append(dict(job=job, label=label, va=va,
                                file_offset=image.offset(va, size), size=size))

    owned = {"a4": stock.OWNER, "p9": cpu.OWNER, "g2": abilities.OWNER,
             "f4": grades.OWNER, "f4b": progress.OWNER, "f5": honors.OWNER,
             "v1b": posts.OWNER}
    for job, owner in owned.items():
        for row in space.layout(final)["allocations"]:
            if row["owner"] == owner:
                add(job, row["va"], row["size"], owner + "/" + row["kind"])
    for label, (va, raw) in abilities.HOOKS.items():
        add("g2", va, len(raw), label)
    for label, (va, raw) in cpu.HOOKS2.items():
        add("p9", va, len(raw), label)
    add("a4", gun.SITE_VA, len(gun.RETAIL_SITE), "a4+a4pd shotgun rule")
    for job, sites in (("h1", holder.sites()), ("s7", s7_repair.OWNED),
                       ("k1", keyboard.SITES), ("w1", w1_repair.XBE_SITES)):
        for label, va, before, after in sites:
            add(job, va, len(after), label)
    allocation = grades.allocations(final)
    bands = tuple((r["minimum"], r["label"]) for r in grades.read_settings(final)["bands"])
    dynamic = {
        "f4": grades.sites(allocation["code"]["va"], allocation["read_only"]["va"], bands),
        "f4b": progress.sites(progress.allocation(final)["va"]),
        "f5": honors.sites(honors.allocations(final)["code"]["va"]),
        "v1b": posts.sites(posts.allocations(final)["code"]["va"],
                           posts.allocations(final)["read_only"]["va"]),
    }
    for job, sites in dynamic.items():
        for label, va, before, after in sites:
            add(job, va, len(after), label)
    return result


def changed_ranges(before, after):
    """Exact maximal runs of changed bytes, not just broad authorized spans."""
    require(len(before) == len(after), "size changed")
    runs, start = [], None
    for i, (a, b) in enumerate(zip(before, after)):
        if a != b and start is None:
            start = i
        elif a == b and start is not None:
            runs.append([start, i - start])
            start = None
    if start is not None:
        runs.append([start, len(before) - start])
    return runs


def verify_scope(final, result, spans):
    require(len(final) == len(result), "XBE size changed")
    restored = bytearray(result)
    for row in spans:
        at, size = row["file_offset"], row["size"]
        require(0 <= at < at + size <= len(final), "invalid declared span")
        restored[at:at + size] = final[at:at + size]
    require(bytes(restored) == final, "changed a byte outside declared spans")
    return sha(restored)


def digests_ok(raw):
    return all(raw[s.header_offset + 36:s.header_offset + 56] == section_digest(raw, s)
               for s in _sections(raw))


def build(before, final, jobs):
    require(sha(before) == V05_HASH and sha(final) == V06_HASH,
            "requires exact shipped v0.5 and final v0.6 executables")
    require(digests_ok(before) and digests_ok(final), "invalid source section digests")
    selected = expand(jobs)
    inventory = catalog(final)
    spans = sorted((dict(r) for j in selected for r in inventory[j]),
                   key=lambda r: r["file_offset"])
    for a, b in zip(spans, spans[1:]):
        require(a["file_offset"] + a["size"] <= b["file_offset"], "overlapping repair owners")
    old_image = XbeImage(before)
    old_allocations = space.layout(before)["allocations"]
    new_allocations = space.layout(final)["allocations"]
    for a in old_allocations:
        require(a in new_allocations, "an inherited allocator placement moved")
    _, _, requests = space._validate(final)
    buf = bytearray(final)
    for row in spans:
        at, size = row["file_offset"], row["size"]
        old = old_image.read(row["va"], size)
        require(old_image.offset(row["va"], size) == at, "v0.5 mapping differs")
        buf[at:at + size] = old
        row.update(kind="v05_restore", v05_sha256=sha(old),
                   final_sha256=sha(final[at:at + size]))
    space._seal_scaleout(buf, requests)
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    # Seals describe the retained v0.6 directory, including disabled allocations.
    # Only changed metadata fields are declared in the receipt.
    metadata = [(space.DIRECTORY, space.LIB_COPY - space.DIRECTORY, "allocator header seals"),
                (space.SCALE_DIRECTORY, space.PAGE, "allocator page seals")]
    metadata += [(s.header_offset + 36, 20, "section digest " + str(s.index)) for s in _sections(result)]
    for at, size, label in metadata:
        for local, length in changed_ranges(final[at:at + size], result[at:at + size]):
            spans.append(dict(file_offset=at + local, size=length, kind="derived", label=label))
    restored_hash = verify_scope(final, result, spans)
    require(space.status(result) == "applied" and digests_ok(result), "seals/digests failed")
    require(space.layout(result)["allocations"] == new_allocations, "allocator placements changed")
    require(space._read_scale_directory(result) == space._read_scale_directory(final), "requests changed")
    for job in JOBS - set(selected):
        for row in inventory[job]:
            at, size = row["file_offset"], row["size"]
            require(result[at:at + size] == final[at:at + size], "unselected repair changed: " + job)
    for row in spans:
        at, size = row["file_offset"], row["size"]
        row.update(after_sha256=sha(result[at:at + size]),
                   changed_bytes=sum(a != b for a, b in zip(final[at:at + size], result[at:at + size])))
        if row["kind"] == "v05_restore":
            require(row["after_sha256"] == row["v05_sha256"], "restore differs from v0.5")
    states = {j: dict(v05=m.status(before), v06=m.status(final), output=m.status(result))
              for j, m in MODULES.items()}
    runs = changed_ranges(final, result)
    return result, dict(schema="b77/frz-xbe-bisect/v1", selected=selected,
        v05_sha256=sha(before), v06_sha256=sha(final), sha256=sha(result), size=len(result),
        allocator_requests_and_placements_unchanged=True, allocator=space.status(result),
        section_digests_valid=True, unselected_payloads_identical=True,
        outside_scope_identical=True, restored_scope_sha256=restored_hash,
        changed_bytes=sum(n for _, n in runs), changed_ranges=runs,
        ranges=spans, owner_states=states, runtime_witness=False)


def read_xbe(path):
    fd = os.open(path, os.O_RDONLY | BINARY)
    try:
        size = os.fstat(fd).st_size
        if platform_compat.pread(fd, 4, 0) == b"XBEH":
            require(size <= 32 * 1024**2, "oversized XBE")
            offset, length = 0, size
        else:
            files, _ = xiso.parse_xdvdfs(fd, size)
            entry = files["default.xbe"]
            offset, length = entry.byte_offset, entry.size
        raw = platform_compat.pread(fd, length, offset)
        require(len(raw) == length, "short XBE read")
        return raw, offset
    finally:
        os.close(fd)


def check_room(parent, required):
    floor = 50 * 1024**3 if parent.stat().st_dev == Path("/").stat().st_dev else 0
    require(shutil.disk_usage(parent).free - required >= floor,
            "insufficient space, including the 50 GiB root reserve")


def write_new(path, raw):
    if path.exists():
        require(path.read_bytes() == raw, "refusing different existing output: " + str(path))
        return
    check_room(path.parent, len(raw))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | BINARY, 0o644)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def copy_with_xbe(source, output, replacement, offset, original):
    """Copy and read back every byte. Refuse source changes and existing output."""
    require(not output.exists(), "refusing existing output image")
    require(len(original) == len(replacement), "XBE replacement size differs")
    size = source.stat().st_size
    require(0 <= offset <= size - len(replacement), "XBE outside image")
    check_room(output.parent, size)
    src = os.open(source, os.O_RDONLY | BINARY)
    dst = None
    completed = False
    try:
        identity = os.fstat(src)
        require(platform_compat.pread(src, len(original), offset) == original, "source XBE changed")
        dst = os.open(output, os.O_RDWR | os.O_CREAT | os.O_EXCL | BINARY, 0o644)
        input_hash, output_hash, outside_hash = (hashlib.sha256() for _ in range(3))
        for at in range(0, size, CHUNK):
            if at % (256 * 1024**2) == 0:
                check_room(output.parent, size - at)
            wanted = min(CHUNK, size - at)
            raw = platform_compat.pread(src, wanted, at)
            require(len(raw) == wanted, "short source read")
            input_hash.update(raw)
            lo, hi = max(at, offset), min(at + wanted, offset + len(replacement))
            if lo < hi:
                patched = raw[:lo - at] + replacement[lo - offset:hi - offset] + raw[hi - at:]
                outside_hash.update(raw[:lo - at])
                outside_hash.update(raw[hi - at:])
            else:
                patched = raw
                outside_hash.update(raw)
            require(platform_compat.pwrite(dst, patched, at) == len(patched), "short output write")
            got = platform_compat.pread(dst, wanted, at)
            require(got == patched, "disc read-back differs")
            output_hash.update(got)
        os.fsync(dst)
        now = os.fstat(src)
        require((now.st_dev, now.st_ino, now.st_size, now.st_mtime_ns, now.st_ctime_ns) ==
                (identity.st_dev, identity.st_ino, identity.st_size, identity.st_mtime_ns, identity.st_ctime_ns),
                "source changed during copy")
        require(os.fstat(dst).st_size == size, "disc size changed")
        completed = True
        return dict(source=str(source), output=str(output), size=size,
                    source_sha256=input_hash.hexdigest(), sha256=output_hash.hexdigest(),
                    outside_xbe_sha256=outside_hash.hexdigest(), outside_xbe_identical=True,
                    full_readback_verified=True, xbe_image_offset=offset,
                    xbe_sha256=sha(replacement), runtime_witness=False)
    finally:
        os.close(src)
        if dst is not None:
            os.close(dst)
            if not completed:
                output.unlink()  # Only this call's exclusively created partial copy.


def disc(image, xbe, output):
    original, offset = read_xbe(image)
    require(offset != 0 and sha(original) == V06_HASH, "base disc must contain exact final v0.6 XBE")
    replacement, _ = read_xbe(xbe)
    receipt = json.loads(xbe.with_suffix(xbe.suffix + ".receipt.json").read_text())
    require(receipt["v06_sha256"] == V06_HASH and receipt["sha256"] == sha(replacement), "XBE receipt mismatch")
    verify_scope(original, replacement, receipt["ranges"])
    require(space.status(replacement) == "applied" and digests_ok(replacement), "invalid diagnostic XBE")
    receipt_path = output.with_suffix(output.suffix + ".receipt.json")
    require(not receipt_path.exists(), "refusing existing disc receipt")
    result = copy_with_xbe(image, output, replacement, offset, original)
    result["xbe_receipt"] = receipt
    write_new(receipt_path, json_bytes(result))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--v05", type=Path, required=True, help="XBE or v0.5 disc")
    prep.add_argument("--v06", type=Path, required=True, help="XBE or final/safe disc")
    prep.add_argument("--out-dir", type=Path, required=True)
    choice = prep.add_mutually_exclusive_group()
    choice.add_argument("--variant", choices=VARIANTS)
    choice.add_argument("--revert", help="comma-separated repair ids; a4 includes a4pd, f5 includes f5b")
    copy = sub.add_parser("disc")
    copy.add_argument("--image", type=Path, required=True)
    copy.add_argument("--xbe", type=Path, required=True)
    copy.add_argument("--output-image", type=Path, required=True)
    args = ap.parse_args()
    if args.command == "disc":
        result = disc(args.image, args.xbe, args.output_image)
        print(json.dumps({k: v for k, v in result.items() if k != "xbe_receipt"}, indent=2))
        return
    before, _ = read_xbe(args.v05)
    final, _ = read_xbe(args.v06)
    choices = ({"custom": args.revert.split(",")} if args.revert else
               {args.variant: VARIANTS[args.variant]} if args.variant else VARIANTS)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    check_room(args.out_dir, len(final) * len(choices) + 1024**2)
    for name, jobs in choices.items():
        raw, receipt = build(before, final, jobs)
        receipt["variant"] = name
        path = args.out_dir / (name + ".default.xbe")
        write_new(path, raw)
        write_new(path.with_suffix(path.suffix + ".receipt.json"), json_bytes(receipt))
        print(name, receipt["sha256"], receipt["changed_bytes"], "changed bytes; scope and digests valid", flush=True)


if __name__ == "__main__":
    main()

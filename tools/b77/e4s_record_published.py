#!/usr/bin/env python3
"""b77 e4s: pin the stadium scenes of the published SOFTDRINK 2K28 packs in the board kit's pins.

Coach Edwards' photo (4 October 2026) showed the boards step refusing a build over stadium scenes it did not know. The
kit now knows every stadium scene any published SOFTDRINK 2K28 pack ever carried, by hash, beside its own pins
(``published`` in ``data/nfl2k5_board_kit/pins/sXX.json``): such a scene reads ``applied`` at once, with no parsing.

    python3 tools/b77/e4s_record_published.py --retail "ESPN NFL 2K5 (USA).xiso.iso" \\
        --pack "SOFTDRINK 2K28 v0.3=SOFTDRINK-2K28-v0.3.2k5patch" --disc "SOFTDRINK 2K28 v0.5=v0.5.xiso.iso" \\
        [--write] [--report report.json]

* ``--pack LABEL=PATCH``: the published ``.2k5patch`` itself. Nothing is installed: each pack file is reconstructed from
  the retail image exactly as the installer writes it (``modpack_files._reconstruct``, every run hash-checked) and only
  the byte ranges of the kit's bundles are kept, so no 6 GB image is ever written.
* ``--disc LABEL=IMAGE``: a finished disc, read through the outer archive reader.

Every stadium span is read as carrying the boards by structure (the kit's own ``_renovated``) before its hash is kept;
a span that does not is reported and left out. Without ``--write`` nothing changes. The result is deterministic:
sorted JSON, LF endings, and running it twice changes nothing.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import struct
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from mod_editor.core import modpack_files as mf  # noqa: E402
from mod_editor.core import nfl2k5_board_kit as bk  # noqa: E402
from nfl_outer import ALIGNMENT, HEADER_SIZE, PACK_NAMES, PACK_SLOT_COUNT  # noqa: E402

PACK_FOLDER = "vc_53450030"
TABLE_ENTRY = struct.Struct("<III")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def kit_bundles():
    """{bundle name: the 2026 venue table's archive pin} for every bundle the kit renovates."""
    return {name: vp for venue in bk.pinned_venues() for name, vp in bk._venue_pins(venue).items()}


def read_from_pack(retail, pack, wanted):
    """{name: bundle bytes} as a pack's result image holds them, without writing the image."""
    out = {}
    with mf._open_source(retail) as source, zipfile.ZipFile(pack) as archive:
        layout = mf._layout(source)
        manifest = json.loads(archive.read("manifest.json"))
        rows = {row["path"]: row for row in manifest["files"]}

        def chunks(path):
            yield from mf._reconstruct(rows[path], source, layout.entries[path], archive, layout.entries)

        # the outer archive's table is in pack 0 of the RESULT: read just its head
        head = bytearray()
        need = HEADER_SIZE
        for at, data in chunks(f"{PACK_FOLDER}/0"):
            assert at == len(head), "pack 0 chunks are not contiguous"
            head += data
            if len(head) >= HEADER_SIZE and need == HEADER_SIZE:
                count, _reserved, _populated = struct.unpack_from("<III", head, 0)
                need = HEADER_SIZE + TABLE_ENTRY.size * count
            if len(head) >= need > HEADER_SIZE:
                break
        count, _reserved, populated = struct.unpack_from("<III", head, 0)
        blocks = struct.unpack_from(f"<{PACK_SLOT_COUNT}I", head, 12)
        packs, virtual = [], 0
        for ordinal in range(populated):
            size = blocks[ordinal] * ALIGNMENT
            packs.append((f"{PACK_FOLDER}/{PACK_NAMES[ordinal].lower()}", virtual, size))
            virtual += size
        placed = {}
        for name, vp in wanted.items():
            name_id, size, offset_blocks = TABLE_ENTRY.unpack_from(head, HEADER_SIZE + TABLE_ENTRY.size * vp["outer"])
            if name_id != vp["name_id"] or size != vp["size"]:
                raise ValueError(f"{name}: the pack's outer entry {vp['outer']} differs from the venue table")
            where = offset_blocks * ALIGNMENT
            path, start, _size = next(p for p in packs if p[1] <= where < p[1] + p[2])
            assert where + size <= start + _size, f"{name}: spans two packs"
            placed.setdefault(path, []).append((where - start, size, name))
        for path, ranges in sorted(placed.items()):
            ranges.sort()
            starts = [r[0] for r in ranges]
            buffers = {name: bytearray(size) for _a, size, name in ranges}
            filled = {name: 0 for _a, _s, name in ranges}
            for at, data in chunks(path):
                end = at + len(data)
                i = max(0, bisect.bisect_right(starts, end - 1) - 1)
                while i >= 0 and ranges[i][0] + ranges[i][1] > at:
                    lo, size, name = ranges[i]
                    a, b = max(at, lo), min(end, lo + size)
                    if a < b:
                        buffers[name][a - lo:b - lo] = data[a - at:b - at]
                        filled[name] += b - a
                    i -= 1
            for _lo, size, name in ranges:
                assert filled[name] == size, f"{name}: {filled[name]} of {size} bytes reconstructed"
                out[name] = bytes(buffers[name])
        result = manifest["result"]
    return out, dict(kind="pack", pack_sha256=file_sha(pack), result_sha256=result["sha256"],
                     tool=manifest.get("tool", {}).get("version"))


def read_from_disc(disc, wanted):
    ml = bk._ml()
    out = {}
    with ml._outer_image()(str(disc)) as archive:
        for name, vp in wanted.items():
            e = bk._entry(archive, vp)
            out[name] = archive.read(e.virtual_offset, e.size)
    return out, dict(kind="disc", size=Path(disc).stat().st_size)


def spans_of(bundles):
    """{name: (stadium span sha-256, carries the boards by structure)}."""
    rows = {}
    for name, data in sorted(bundles.items()):
        pin = bk._pin(name)
        rows[name] = (sha(data[pin["offset"]:pin["offset"] + pin["length"]]), len(data) == pin["size"] and bk._renovated(data, name))
    return rows


def collect(args, wanted):
    """Read every source named on the command line: ({label: {bundle: (span sha, carries the boards)}}, sources)."""
    labels, sources = {}, {}
    for kind, items in (("pack", args.pack), ("disc", args.disc)):
        for item in items:
            label, _, path = item.partition("=")
            started = time.time()
            if kind == "pack":
                bundles, source = read_from_pack(args.retail, path, wanted)
            else:
                bundles, source = read_from_disc(path, wanted)
            rows = spans_of(bundles)
            bad = sorted(n for n, (_h, ok) in rows.items() if not ok)
            print(f"{label} ({kind}): {len(rows)} bundles, {len(rows) - len(bad)} carry the boards, {len(bad)} do not "
                  f"({time.time() - started:.0f} s)", flush=True)
            if bad:
                print("   not recognised by structure:", ", ".join(bad[:12]), flush=True)
            if label in labels:
                same = all(labels[label][n][0] == h for n, (h, _ok) in rows.items())
                print(f"   {label} read as a pack and as a disc: {'identical' if same else 'DIFFERENT'}", flush=True)
                if not same:
                    raise SystemExit(1)
            labels.setdefault(label, rows)
            sources.setdefault(label, {})[kind] = source
    return labels, sources


def write_pins(labels, sources, pins_dir=None):
    """Merge what was read into the pins (``published`` per bundle, ``published_from`` per venue)."""
    pins_dir = Path(pins_dir or bk.PINS_DIR)
    table = {}
    for label, rows in labels.items():
        for name, (digest, ok) in rows.items():
            if ok:
                table.setdefault(name, {}).setdefault(digest, set()).add(label)
    for venue in bk.pinned_venues():
        path = pins_dir / f"{venue}.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        for row in doc["bundles"]:
            merged = {digest: sorted(names) for digest, names in (row.get("published") or {}).items()}
            for digest, names in table.get(row["name"], {}).items():
                merged[digest] = sorted(set(merged.get(digest, ())) | names)
            if merged:
                row["published"] = merged
        provenance = dict(doc.get("published_from") or {})
        for label, sourced in sources.items():
            # the published pack is the identity; a disc is kept only when no pack was given for its label
            kind = "pack" if "pack" in sourced else "disc"
            provenance[label] = {k: v for k, v in sourced[kind].items() if k != "kind"}
        doc["published_from"] = provenance
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--retail", help="the unmodified USA retail xiso every pack installs onto")
    ap.add_argument("--pack", action="append", default=[], metavar="LABEL=PATCH")
    ap.add_argument("--disc", action="append", default=[], metavar="LABEL=IMAGE")
    ap.add_argument("--write", action="store_true", help="update data/nfl2k5_board_kit/pins/*.json")
    ap.add_argument("--report", help="write a JSON report here")
    ap.add_argument("--from-report", help="skip the reading: use a report an earlier run wrote")
    args = ap.parse_args(argv)
    if args.from_report:
        doc = json.loads(Path(args.from_report).read_text(encoding="utf-8"))
        labels = {label: {n: (row["span_sha256"], row["carries_boards"]) for n, row in rows.items()}
                  for label, rows in doc["labels"].items()}
        sources = doc["sources"]
    else:
        if not args.retail or not (args.pack or args.disc):
            ap.error("--retail and at least one --pack or --disc are required (or --from-report)")
        labels, sources = collect(args, kit_bundles())
    if args.report:
        Path(args.report).write_text(json.dumps(dict(
            sources=sources, labels={label: {n: dict(span_sha256=h, carries_boards=ok) for n, (h, ok) in rows.items()}
                                     for label, rows in labels.items()}), indent=1, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    for label, rows in labels.items():
        print(f"{label}: {len({h for h, _ in rows.values()})} distinct stadium scenes in {len(rows)} bundles")
    if args.write:
        write_pins(labels, sources)
        print("pins updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

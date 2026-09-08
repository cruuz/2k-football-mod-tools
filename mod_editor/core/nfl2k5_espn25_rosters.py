"""Historic moments: real rosters. EXPERIMENTAL / UNWITNESSED.

Data only, on the 35 shared historic ROSTs used by the retail 25 moments.
Box-score starters and season numbers are sourced; shared-file gaps are listed.
No executable, scenario, team pointer, rating or appearance edit is made here.
The image adapter edits only a caller-owned disposable build copy. ``build_image``
provides copy-first publication. No whole image or archive pack is read into RAM.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
from typing import Mapping
import zlib

from . import nfl2k5_roster_records as rr

OWNER = "nfl2k5_espn25_rosters"
SCHEMA = OWNER + "/v1"
REQUESTS = ()
EVIDENCE = "EXPERIMENTAL / UNWITNESSED"
CAPTION = "Historic moments: real rosters"
HELP_TEXT = (
    "Retail: many historic players have position names in shared rosters. "
    "Patch: use Pro Football Reference game starters and season jersey numbers "
    "with the nflverse roster base. Short lists still need named reserves from "
    "nearby seasons. Shared teams cannot match every game. Requires the retail position layout. "
    "EXPERIMENTAL / UNWITNESSED. See the roster report before testing."
)
DEFAULT_ENABLED = False
DATA_DIR = Path(__file__).resolve().parents[2] / "data/nfl2k5_espn25_moment_rosters"
# Updated deliberately after deterministic offline regeneration; no runtime fetch.
DATASET_SHA256 = "9f2c1d1d67ef630300a081410129c71a53f9de54f4b02a89ec0cbe7087656ba8"
MAX_RESOURCE = 1024 * 1024
MAX_MANIFEST = 8 * 1024 * 1024
SITU_OUTER = 22
MAIN_OUTER = 5
RECORDS, STRIDE, COUNT = 0x44, 0x6C, 25
CSV_COLUMNS = ("pool", "index", "first", "last", "position", "jersey", "college") + rr.RATING_BYTE_ORDER


class Espn25RostersError(ValueError):
    """Unrecognized data, source or partial install; nothing may be written."""


def require(ok, message):
    if not ok:
        raise Espn25RostersError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_bounded(path, limit):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, f"{Path(path).name} exceeds {limit} bytes")
    return raw


def u32(data, at):
    require(0 <= at <= len(data) - 4, "word outside resource")
    return struct.unpack_from("<I", data, at)[0]


def rel(data, at):
    value = u32(data, at)
    require(value != 0, "missing relative pointer")
    return at + struct.unpack_from("<i", data, at)[0] - 1


def utf16(data, at, end=None):
    end = min(len(data), end if end is not None else at + 4096)
    require(0 <= at < end and at % 2 == 0, "text outside resource")
    for stop in range(at, end - 1, 2):
        if data[stop:stop + 2] == b"\0\0":
            return data[at:stop].decode("utf-16le")
    raise Espn25RostersError("unterminated bounded text")


def describe_context(main, situ, entries):
    """Independently decode the retail historical descriptors and moment bindings.

    Ordinary current-team roster edits may coexist. Historic descriptor changes,
    changed title/date/bindings and expanded SITU tables cannot use this dataset.
    Narrative text is used only by the offline generator, never to execute code.
    """
    require(32 < len(main) <= MAX_RESOURCE and main[:4] == b"ROST", "missing main ROST")
    body = main[32:]
    require(body[12:16] == b"ROST" and rel(body, 20) == 64 and u32(body, 0x98) == 75,
            "foreign historical descriptor layout")
    table = rel(body, 0x9C)
    require(0 <= table <= len(body) - 75 * 16, "historic descriptor table outside main ROST")
    by_id = {}
    for e in entries:
        by_id.setdefault(e.name_id, []).append(e.index)
    descriptors = []
    for index in range(75):
        at = table + index * 16
        year = struct.unpack_from("<H", body, at)[0]
        code, selector = utf16(body, at + 4, at + 12), utf16(body, rel(body, at + 12))
        kit = body[at + 2]
        filename = f"h-{code}-{year}-{selector}-{kit}.iff"
        identity = zlib.crc32(filename.upper().encode("utf-16le")) & 0xFFFFFFFF
        hits = by_id.get(identity, ())
        require(len(hits) == 1 and 113 <= hits[0] <= 187, "missing or duplicate historic archive identity")
        descriptors.append(dict(index=index, year=year, kit=kit, code=code,
                                selector=selector, filename=filename, id=identity, outer=hits[0]))
    by_team = {(d["selector"], d["year"]): d for d in descriptors}
    require(len(by_team) == 75 and len({d["outer"] for d in descriptors}) == 75,
            "duplicate historic descriptor")
    require(32 < len(situ) <= MAX_RESOURCE and situ[:4] == b"SITU" and
            u32(situ, 8) == COUNT and u32(situ, 16) == 0, "foreign SITU wrapper")
    size = u32(situ, 4)
    require(RECORDS + COUNT * STRIDE <= size <= len(situ) - 32, "SITU span outside entry")
    sb = situ[32:32 + size]
    require(sb[12:16] == b"SITU" and u32(sb, 64) == COUNT, "foreign SITU table")
    moments = []
    for i in range(COUNT):
        at = RECORDS + i * STRIDE
        m = {"moment": i, "title": utf16(sb, rel(sb, at)), "date": utf16(sb, rel(sb, at + 12)),
             "history": utf16(sb, rel(sb, at + 4)), "objective": utf16(sb, rel(sb, at + 8))}
        for side, pointer, year in (("away", 20, 28), ("home", 24, 32)):
            pair = (utf16(sb, rel(sb, at + pointer)), u32(sb, at + year))
            require(pair in by_team, "unrecognized moment name/year")
            m[side] = dict(by_team[pair])
        moments.append(m)
    colleges = rr.RosterDocument(body).colleges
    return {"descriptors": descriptors, "moments": moments, "colleges": colleges}


def context_sha(context):
    # Narratives may be edited without changing who loads; title/date may not.
    value = {**context, "moments": [{k: v for k, v in m.items() if k not in ("history", "objective")}
                                   for m in context["moments"]]}
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=True).encode())


def parse_csv(text):
    require(isinstance(text, str) and len(text.encode("utf-8")) <= 256 * 1024, "roster CSV exceeds 256 KiB")
    reader = csv.DictReader(io.StringIO(text), strict=True)
    require(tuple(reader.fieldnames or ()) == CSV_COLUMNS, "unexpected roster CSV columns")
    rows = list(reader)
    require(len(rows) == 53, "each historic roster requires 53 rows")
    names = set()
    for index, row in enumerate(rows):
        require(None not in row and None not in row.values(), "CSV row width differs from header")
        require(row["pool"] == "primary" and row["index"] == str(index), "CSV rows must be primary indices 0..52")
        first, last = row["first"], row["last"]
        require(first and last and rr.validate_name(first) == first and rr.validate_name(last) == last,
                "invalid player name")
        identity = (first.casefold(), last.casefold())
        require(identity not in names, "duplicate player name in one roster")
        names.add(identity)
        require(row["position"] in rr.POSITIONS, "invalid retail position")
        for field, maximum in (("jersey", 99), *((r, 255) for r in rr.RATING_BYTE_ORDER)):
            value = row[field]
            require(value.isascii() and value.isdigit() and str(int(value)) == value and int(value) <= maximum,
                    f"invalid {field}")
    return rows


def dataset():
    # Revalidate on every public operation, including a long-lived Studio's
    # availability refresh. A deleted or modified CSV must not use cached data.
    raw = read_bounded(DATA_DIR / "manifest.json", MAX_MANIFEST)
    require(sha(raw) == DATASET_SHA256, "historic roster manifest differs from the shipped dataset")
    manifest = json.loads(raw)
    require(manifest["schema"] == SCHEMA and len(manifest["resources"]) == 35,
            "foreign dataset schema/count")
    require(len({t["outer"] for t in manifest["resources"]}) == 35, "duplicate dataset resource")
    sheets = {}
    for target in manifest["resources"]:
        name = target["csv"]
        require(Path(name).name == name and name == target["filename"][:-4] + ".csv", "foreign CSV path")
        raw = read_bounded(DATA_DIR / name, 256 * 1024)
        require(sha(raw) == target["csv_sha256"], f"{name}: dataset digest mismatch")
        rows = parse_csv(raw.decode("utf-8"))
        require(len(target["players"]) == 53, "missing player provenance")
        for row, provenance in zip(rows, target["players"]):
            require(provenance["slot"] == int(row["index"]) and
                    (row["first"], row["last"]) == (provenance["first"], provenance["last"]),
                    "player identity differs from its provenance")
        sheets[target["outer"]] = rows
    return manifest, sheets


def resource_status(payload, target):
    if not isinstance(payload, (bytes, bytearray)) or len(payload) != target["size"]:
        return "foreign"
    digest = sha(payload)
    if digest == target["retail_sha256"]:
        return "retail"
    if digest == target["applied_sha256"]:
        return "applied"
    return "foreign"


def status(resources: Mapping[int, bytes]):
    """Status of the COMPLETE 35-resource transaction; raw XBE is foreign."""
    manifest, _ = dataset()
    if not isinstance(resources, Mapping) or set(resources) != {t["outer"] for t in manifest["resources"]}:
        return "foreign"
    states = {resource_status(resources[t["outer"]], t) for t in manifest["resources"]}
    return states.pop() if len(states) == 1 else "foreign"


def changed_spans(before, after):
    require(len(before) == len(after), "fixed-span writer cannot grow a resource")
    out, start = [], None
    for at in range(len(before) + 1):
        differs = at < len(before) and before[at] != after[at]
        if differs and start is None:
            start = at
        if not differs and start is not None:
            out.append({"offset": start, "before": before[start:at].hex(), "after": after[start:at].hex()})
            start = None
    return out


def compile_resource(raw, rows, colleges):
    """Existing name allocator + player encoder, inside the discovered retail pool.

    All names move to an existing first allocation before assigning final names;
    this releases the old placeholders through StringPool, avoiding fragmentation
    without inventing free bytes. CSV college text is translated to the main-table
    *index*, because C1030 does not interpret this field as a relative pointer.
    No generic college writer is called on a historic resource.
    """
    require(32 < len(raw) <= 16384 and raw[:4] == b"ROST" and u32(raw, 4) == len(raw) - 32 and
            u32(raw, 16) == 0, "historic ROST must be one complete uncompressed resource")
    document = rr.RosterDocument(raw[32:])
    require(len(document.players) == 53 and len(document.teams) == 1 and document.college_count == 0 and
            all(p.pool == "primary" for p in document.players) and document.teams[0].player_count == 53,
            "foreign historic roster layout")
    require(document.to_body() == raw[32:], "retail codec round trip differs")
    bounds = (document.names.start, document.names.end)
    original_values = [dict(p.record.values) for p in document.players]
    original_slots = tuple(document.teams[0].slots)
    require(len(rows) == 53, "expected 53 roster rows")
    seed = document.names.blocks[bounds[0]].text
    for p in document.players:
        document.set_name(p, "first", seed)
        document.set_name(p, "last", seed)
    # The importer accepts sparse CSVs. Only these supported editable cells are
    # submitted; ratings and positions are compared to their original slot below.
    stream = io.StringIO()
    writer = csv.DictWriter(stream, ["pool", "index", "first", "last", "jersey"],
                            extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    receipt = rr.import_csv(document, stream.getvalue(), delimiter=",")
    require(receipt["rows"] == 53 and not receipt["log"], "roster import refused: " + "; ".join(receipt["log"]))
    for p, row, old in zip(document.players, rows, original_values):
        require(row["pool"] == p.pool and int(row["index"]) == p.index, "roster slot identity changed")
        require(row["position"] == rr.POSITIONS[old["position"]] and
                all(int(row[k]) == old[k] for k in rr.RATING_BYTE_ORDER), "retail slot position/ratings changed")
        require((p.first, p.last) == (row["first"], row["last"]), "name import was incomplete")
        if row["college"]:
            require(colleges.count(row["college"]) == 1, "college must resolve exactly once in the main table")
            p.record.set("college_pointer", colleges.index(row["college"]))
    result = raw[:32] + document.to_body()
    require(len(result) == len(raw) and result[:32] == raw[:32], "resource wrapper/size changed")
    allowed = set(range(32 + bounds[0], 32 + bounds[1]))
    for p in document.players:
        for field in ("first_name_pointer", "last_name_pointer", "jersey", "college_pointer"):
            spec = rr.FIELD_BY_NAME[field]
            allowed.update(range(32 + p.offset + spec.offset, 32 + p.offset + spec.offset + spec.size))
    require(all(i in allowed for i, (a, b) in enumerate(zip(raw, result)) if a != b), "edit escaped owned roster fields")
    after = rr.RosterDocument(result[32:])
    require(tuple(after.teams[0].slots) == original_slots, "team pointer/depth order changed")
    for p, old in zip(after.players, original_values):
        require(all(p.record.values[k] == v for k, v in old.items()
                    if k not in ("first_name_pointer", "last_name_pointer", "jersey", "college_pointer")),
                "rating, appearance or other record bits changed")
    return result


def apply(resources: Mapping[int, bytes]):
    """Pure all-or-nothing compilation; replay is byte-identical with zero writes."""
    manifest, sheets = dataset()
    state = status(resources)
    require(state in ("retail", "applied"), "historic rosters refuse missing, mixed or foreign resources")
    output, receipts = {}, []
    for t in manifest["resources"]:
        before = bytes(resources[t["outer"]])
        after = before if state == "applied" else compile_resource(before, sheets[t["outer"]], manifest["colleges"])
        require(resource_status(after, t) == "applied", "compiled roster differs from the pinned profile")
        changes = changed_spans(before, after)
        output[t["outer"]] = after
        receipts.append({"outer": t["outer"], "filename": t["filename"], "size": t["size"],
                         "before_sha256": sha(before), "after_sha256": sha(after),
                         "changed_bytes": sum(len(c["before"]) // 2 for c in changes), "changes": changes,
                         "wrapper_identical": True, "compressed": False})
    return output, {"schema": SCHEMA, "owner": OWNER, "evidence": EVIDENCE,
                    "dataset_sha256": DATASET_SHA256, "before": state, "after": "applied",
                    "already_applied": state == "applied", "xbe_changed": False, "growth_bytes": 0,
                    "changed_bytes": sum(r["changed_bytes"] for r in receipts), "resources": receipts,
                    "lineups": "Season inference; see per-moment basis and per-player exceptions in manifest.json"}


apply_resources = apply
resources_status = status


def _read_archive(archive):
    manifest, _ = dataset()
    outputs, entries = {}, {}
    for t in manifest["resources"]:
        require(t["outer"] < len(archive.entries), "missing historic outer entry")
        e = archive.entries[t["outer"]]
        require(e.name_id == t["id"] and e.size == t["size"], "historic archive identity/size changed")
        entries[e.index] = e
        outputs[e.index] = archive.read(e.virtual_offset, e.size)
    context_raw = {}
    for index in (MAIN_OUTER, SITU_OUTER):
        e = archive.entries[index]
        require(32 < e.size <= MAX_RESOURCE, "context resource exceeds bounded read")
        context_raw[index] = archive.read(e.virtual_offset, e.size)
    context = describe_context(context_raw[5], context_raw[22], archive.entries)
    require(context_sha(context) == manifest["context_sha256"], "moment bindings or main college/descriptor table changed")
    return outputs, entries


def read_resources(source):
    """Bounded reads from a disc image or an extracted game/pack folder."""
    with rr._outer_image()(source) as archive:
        resources, _ = _read_archive(archive)
    return resources


def image_status(source):
    try:
        return status(read_resources(source))
    except (OSError, ValueError, IndexError, KeyError, struct.error):
        return "foreign"


def apply_to_image(path):
    """Final resource pass on a private build copy, with preflight and readback.

    Rejects every mixed/foreign state before writing. An I/O failure requires
    discarding the private copy; this function is not a power-loss transaction.
    Handles are closed before any caller publishes/replaces the file.
    """
    path = Path(path).resolve(strict=True)
    require(path.is_file(), "image adapter requires a private disc-image file")
    size = path.stat().st_size
    with rr._outer_image()(path, writable=True) as archive:
        original, entries = _read_archive(archive)
        output, receipt = apply(original)
        require(archive._read_table() == archive.entries, "archive table changed during roster preflight")
        current, rechecked = _read_archive(archive)
        require(path.stat().st_size == size and entries == rechecked and original == current,
                "image changed during roster preflight")
        spans = []
        for index, after in output.items():
            e = entries[index]
            segments = archive._segments(e.virtual_offset, e.size)
            spans.append({"outer": index, "virtual_offset": e.virtual_offset,
                          "segments": [{"pack": p.name, "image_offset": p.image_offset + off, "size": n}
                                       for p, off, n in segments]})
            if after != original[index]:
                require(archive.write(e.virtual_offset, after) == len(after), "short historic roster write")
        verified, _ = _read_archive(archive)
        require(path.stat().st_size == size and verified == output, "historic roster readback differs")
    receipt.update(image_size_before=size, image_size_after=size, image_spans=spans)
    return receipt


def build_image(source, output, *, receipt_path=None):
    """Copy-first publication; an optional receipt is staged before the image.

    Ordinary failures publish neither file. This is not a two-file power-loss
    transaction: a crash between replacements can leave the receipt alone.
    """
    source, output = Path(source).resolve(strict=True), Path(output).resolve()
    require(source.is_file() and source != output and not output.exists(), "output must be a new file distinct from the source image")
    receipt_output = Path(receipt_path).resolve() if receipt_path is not None else None
    if receipt_output is not None:
        require(receipt_output not in (source, output) and not receipt_output.exists(),
                "receipt must be a new path distinct from both images")
    def identity():
        st = source.stat()
        return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns
    source_identity = identity()
    apply(read_resources(source))  # Compile every resource before a large copy.
    require(shutil.disk_usage(output.parent).free - source.stat().st_size > 100 * 1024**3,
            "copy would leave less than 100 GiB free; no image created")
    with ExitStack() as stack:
        temporary = stack.enter_context(tempfile.TemporaryDirectory(prefix="espn25-rosters-", dir=output.parent))
        staged = Path(temporary).resolve() / "image.iso"
        staged_receipt = None
        if receipt_output is not None:
            # Opening the destination directory now rejects an unavailable
            # receipt path before copying, including paths on another volume.
            receipt_directory = stack.enter_context(tempfile.TemporaryDirectory(
                prefix="espn25-receipt-", dir=receipt_output.parent))
            staged_receipt = Path(receipt_directory).resolve() / "receipt.json"
        with source.open("rb") as src, staged.open("xb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        receipt = apply_to_image(staged)
        require(identity() == source_identity, "source changed during build; no image published")
        require(not output.exists(), "output appeared during build")
        if staged_receipt is not None:
            with staged_receipt.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(receipt, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            require(not receipt_output.exists(), "receipt appeared during build")
            os.replace(staged_receipt, receipt_output)
        try:
            os.replace(staged, output)
        except BaseException:
            if staged_receipt is not None:
                receipt_output.unlink()
            raise
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("status")
    inspect.add_argument("source", type=Path)
    commands.add_parser("validate-dataset")
    build = commands.add_parser("build")
    build.add_argument("source", type=Path)
    build.add_argument("output", type=Path)
    build.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "status":
        state = image_status(args.source)
        print(json.dumps({"owner": OWNER, "status": state, "evidence": EVIDENCE}))
        return 1 if state == "foreign" else 0
    if args.command == "validate-dataset":
        manifest, rows = dataset()
        print(json.dumps({"resources": len(rows), "players": sum(map(len, rows.values())),
                          "moments": len(manifest["moments"]), "sha256": DATASET_SHA256,
                          "evidence": EVIDENCE, "default_enabled": DEFAULT_ENABLED}))
        return 0
    receipt = build_image(args.source, args.output, receipt_path=args.receipt)
    print(f"{EVIDENCE}: wrote {args.output}; {receipt['changed_bytes']} roster bytes changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

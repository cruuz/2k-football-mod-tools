#!/usr/bin/env python3
"""Native Anniversary repair of the v0.4 0/F/default.xbe file set; no input writes.

An integrated file set requires --accepted-input-hashes. That manifest maps the
three names to SHA-256 values, or may be a previous receipt whose `files` rows
contain `after_sha256`. Passing the previous receipt permits a verified replay.
The original v0.4 image and retail source are opened read only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_anniversary_pack as packs
from mod_editor.core import nfl2k5_anniversary_kickoff as gate
from mod_editor.core import nfl2k5_era_rules as era
from mod_editor.core import nfl2k5_espn25_fields as fields
from mod_editor.core import nfl2k5_espn25_more_moments as mm
from mod_editor.core import nfl2k5_historic_styles as styles
from mod_editor.core import nfl2k5_moment_venues as venues
from mod_editor.core import nfl2k5_music_archive as archive
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

V04_DISC = Path("/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 2 (2026-10-03 depth portraits crowds test).xiso.iso")
RETAIL = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
BASELINE = {
    "0": "01e4e49d47dcc41fb54a3c0404fb988df9fe842bf7efdd46288a50190b233e21",
    "F": "03824a8a615c64b9dae270eb04b4e5f8780ad00ff6d376466e16e903551db0c4",
    "default.xbe": "5a9dc534b50c7f13b5124bfff9e39c99f96f62be4cc1de33309895c330c75f29",
}
OWNERS = {mm.OWNER, era.OWNER, venues.OWNER, gate.OWNER, "nfl2k5_xbe_space_directory"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as handle:
        return handle.read()


def write_new(path, raw):
    if path.exists():
        mm.require(read(path) == raw, f"refusing to replace different output: {path}")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def accepted_hashes(path):
    if path is None:
        return BASELINE
    doc = json.loads(read(path))
    mm.require(isinstance(doc, dict), "accepted input manifest must be an object")
    files = doc.get("files", doc)
    mm.require(isinstance(files, dict) and set(files) == set(BASELINE), "accepted manifest needs exactly 0/F/default.xbe")
    result = {}
    for name, row in files.items():
        mm.require(isinstance(row, (str, dict)), "invalid accepted file hash row")
        digest = row if isinstance(row, str) else row.get("sha256", row.get("after_sha256"))
        mm.require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "invalid accepted SHA-256")
        result[name] = digest
    return result


def legacy_data():
    doc = json.loads(read(ROOT / "data/nfl2k5_espn25_v04_profile.json"))
    used = list(dict.fromkeys(m[side] for m in doc["moments"] for side in ("away", "home")))
    mm.require(len(doc["moments"]) == 25 and len(used) == 48, "foreign v0.4 Anniversary profile")
    return mm.Data(doc["moments"], {k: doc["teams"][k] for k in used}, {})


def file_reader(pack0, pack_f, original):
    rows = packs.entries(pack0)
    by_id = {row[0]: row for row in rows}
    f_start = sum(struct.unpack_from("<16I", pack0, 12)[:15]) * 2048
    old = {e.name_id: e for e in original.archive_entries}

    def get(name=None, *, identity=None):
        identity = mm.name_id(name) if identity is None else identity
        mm.require(identity in by_id, f"resource absent from input directory: {name or hex(identity)}")
        _identity, size, sector = by_id[identity]
        at = sector * 2048
        if at + size <= len(pack0):
            return pack0[at:at + size]
        if f_start <= at and at + size <= f_start + len(pack_f):
            return pack_f[at - f_start:at - f_start + size]
        # The unchanged E pack contains the previous 48 moment team files.
        mm.require(identity in old and old[identity].size == size, "foreign source-only resource")
        entry = old[identity]
        return original.read_entry_range(entry, 0, entry.size)
    return get


def field_context(situ):
    import PIL
    import numpy
    core = ROOT / "mod_editor/core"
    code = set(core.glob("nfl2k5_modern*.py")) | set((ROOT / "tools").glob("nfl_*.py"))
    code.update(core / name for name in ("nfl2k5_espn25_fields.py", "nfl2k5_stadium_texture_writer.py",
                                        "nfl2k5_models.py", "nfl2k5_scne_builder.py", "nfl2k5_official_marks.py"))
    return dict(catalog_sha256=sha(read(fields.DATA)),
                art={str(p.relative_to(ROOT)): sha(read(p)) for p in sorted(fields.ART.rglob("*")) if p.is_file()},
                compiler={str(p.relative_to(ROOT)): sha(read(p)) for p in sorted(code)},
                variants=[fields.variant(situ, i) for i in range(51)],
                python=sys.version, pillow=PIL.__version__, numpy=numpy.__version__)


def compile_fields(get, retail_get, situ, cache, progress):
    """Cache only exact art/compiler contexts, source callback bundles and generated alias hashes."""
    if cache is None:
        resources, receipt = fields.compile_assets(get, retail_get, situ, progress=progress)
        receipt["cache"] = "disabled"
        return resources, receipt
    context = field_context(situ)
    expected = set()
    for row in fields.catalog():
        variant = fields.variant(situ, row["row"] - 1)
        expected.add((row["source_kind"], row["source_prefix"] + variant + ".iff"))
        expected.add(("retail", "s25" + variant + ".iff"))
        expected.update(("retail", fields.WORDMARKS[end["team"]] + "dd.iff") for end in row["endzones"])
        if row["center"] == "NFL" and row["season"] < 2008:
            expected.add(("retail", "s43dd.iff"))
    context["sources"] = [dict(kind=kind, name=name, sha256=sha((get if kind == "built" else retail_get)(name)))
                          for kind, name in sorted(expected)]
    key = sha(json.dumps(context, sort_keys=True, separators=(",", ":")).encode())
    folder = cache / key
    manifest = folder / "manifest.json"
    if manifest.exists():
        doc = json.loads(read(manifest))
        mm.require(doc.get("schema") == "a1_field_cache/v1" and doc.get("context") == context,
                   "foreign Anniversary field cache context")
        for row in doc["sources"]:
            mm.require(row["kind"] in ("built", "retail"), "foreign cached source kind")
            raw = (get if row["kind"] == "built" else retail_get)(row["name"])
            mm.require(sha(raw) == row["sha256"], "Anniversary field cache source changed: " + row["name"])
        resources = {}
        for name, digest in doc["aliases"].items():
            mm.require(re.fullmatch(r"a\d{2}[dan][drs]\.iff", name), "foreign cached alias name")
            resources[name] = read(folder / name)
            mm.require(sha(resources[name]) == digest, "Anniversary field cache artifact changed: " + name)
        expected = {f"a{i:02d}{fields.variant(situ, i)}.iff" for i in range(51)}
        comparison = field_context(situ)
        comparison["sources"] = context["sources"]
        mm.require(set(resources) == expected and comparison == context,
                   "incomplete or changed Anniversary field cache")
        receipt = dict(doc["receipt"], cache="verified_hit", cache_key=key)
        return resources, receipt
    sources = {}
    def tracked(kind, callback):
        def load(name):
            raw = callback(name)
            sources[(kind, name)] = sha(raw)
            return raw
        return load
    resources, receipt = fields.compile_assets(tracked("built", get), tracked("retail", retail_get), situ,
                                               progress=progress)
    comparison = field_context(situ)
    comparison["sources"] = context["sources"]
    mm.require(comparison == context, "Anniversary art/compiler changed during compilation; retry once stable")
    mm.require(sources == {(row["kind"], row["name"]): row["sha256"] for row in context["sources"]},
               "field compiler used an unexpected or changed source dependency")
    doc = dict(schema="a1_field_cache/v1", context=context, receipt=receipt,
               sources=[dict(kind=kind, name=name, sha256=digest) for (kind, name), digest in sorted(sources.items())],
               aliases={name: sha(raw) for name, raw in resources.items()})
    folder.mkdir(parents=True, exist_ok=True)
    for name, raw in resources.items():
        write_new(folder / name, raw)
    write_new(manifest, (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode())
    return resources, dict(receipt, cache="compiled", cache_key=key)


def new_teams(main, situ, data, get, retail):
    """Compile only the two new files; copy each existing scenario's preserved retail spare style."""
    old = legacy_data()
    previous = mm.table_entries(old)
    entries = mm.table_entries(data)
    mm.require([r[1] for r in entries[:48]] == [r[1] for r in previous] and len(entries) == 50,
               "new team identities must append after all 48 original files")
    doc = rr.RosterDocument(main[32:])
    counts = styles.franchise_styles(main)
    people = mm.main_people(main)
    photos = frozenset(p.record.values["photo_id"] for p in doc.players)
    sides = styles.situ_sides(situ)
    output, kits, receipts = {}, {}, []
    for key, filename, _entry, selector, identity in entries[48:]:
        team = data.teams[key]
        code = team["asset_code"]
        candidates = [row for row in sides[:100] if row[2] == selector and row[4] >= counts[code]]
        mm.require(candidates, f"no preserved spare kit for {selector}")
        donor = max(candidates, key=lambda row: row[3])
        spare = donor[4]
        mm.require(1 <= spare <= styles.MAX_STYLE, "invalid preserved spare kit")
        donor_entry = next(r for r in previous if old.teams[r[0]]["selector"] == selector
                           and old.teams[r[0]]["season"] == donor[3])
        donor_raw = get(donor_entry[1])
        donor_doc = rr.RosterDocument(donor_raw[32:])
        pair = struct.unpack_from("<HH", donor_raw, 32 + donor_doc.teams[0].offset + styles.TABLE + 4 * (spare - 1))
        mm.require(pair == styles.SPARE_YEARS, "existing moment lacks its preserved retail style pair")
        for side in "ha":
            get(f"{code}{side}{spare}.iff")  # prove both on-disc kits exist
        raw = mm.compile_team(retail.get(team["template"]), team, data.rosters[key], doc.colleges, identity,
                              people, appearance=(data.appearance or {}).get(key), main_photos=photos)
        raw = bytearray(mm._one_pool(raw))
        team_at = 32 + rr.RosterDocument(raw[32:]).teams[0].offset
        struct.pack_into("<HH", raw, team_at + styles.TABLE + 4 * (spare - 1), *pair)
        raw[team_at + styles.STYLE] = spare
        output[filename] = bytes(raw)
        kits[selector] = spare
        receipts.append(dict(name=filename, identity=identity, spare=spare, donor=donor_entry[1], pair=list(pair),
                             sha256=sha(raw), one_pool=True))
    return output, kits, receipts


def xbe_scope(before, after):
    image = XbeImage(before)
    old_layout, new_layout = space.layout(before), space.layout(after)
    mm.require(old_layout["allocations"] == new_layout["allocations"], "Anniversary relocated an allocation")
    allowed = []
    for row in old_layout["allocations"]:
        at, size = row["raw"], row["size"]
        if row["owner"] in OWNERS:
            allowed.append((at, size, row["owner"]))
        else:
            mm.require(before[at:at + size] == after[at:at + size], "unrelated XBE owner changed: " + row["owner"])
    code, dat = mm.allocations(before)
    allowed.extend((image.offset(va, len(raw)), len(raw), "moments/" + name)
                   for name, va, raw, _after in mm.sites(code["va"], dat["va"], 51))
    allowed.extend((image.offset(site, len(raw)), len(raw), "venues/" + name)
                   for name, site, raw in venues.HOOKS + (venues.FILENAME_HOOK,))
    allowed.extend((image.offset(va, size), size, "era/" + name) for name, va, size, _kind in era.specs())
    allowed.extend(((space.DIRECTORY, space.LIB_COPY - space.DIRECTORY, "allocator header seal"),
                    (space.META_START, space.SCALE_HEADER_END - space.META_START, "allocator section descriptors")))
    allowed.extend((section.header + 36, 20, "section digest") for section in image.sections)
    mm.require(len(before) == len(after), "XBE file grew")
    mask = bytearray(len(before))
    for at, size, _label in allowed:
        mask[at:at + size] = b"\1" * size
    changed = 0
    runs = []
    run_start = previous = None
    for at in range(0, len(before), 65536):
        left, right = before[at:at + 65536], after[at:at + 65536]
        if left != right:
            for offset, (a, b) in enumerate(zip(left, right)):
                if a != b:
                    position = at + offset
                    mm.require(mask[position], f"out-of-scope XBE byte {position:#x}")
                    if previous is None or position != previous + 1:
                        if previous is not None:
                            runs.append((run_start, previous + 1))
                        run_start = position
                    previous = position
                    changed += 1
    if previous is not None:
        runs.append((run_start, previous + 1))
    differences = []
    for start, end in runs:
        left, right = before[start:end], after[start:end]
        row = dict(raw_start=start, raw_end=end, size=end-start, before_sha256=sha(left), after_sha256=sha(right))
        if end-start <= 64:
            row.update(before_hex=left.hex(), after_hex=right.hex())
        differences.append(row)
    return dict(changed_bytes=changed, outside_scope_identical=True, unrelated_owner_bodies_identical=True,
                allocations_preserved=True, changed_runs=differences,
                ranges=[dict(raw=at, size=size, label=label) for at, size, label in allowed])


def transform(inputs, original, retail, *, progress=None, field_cache=None):
    data, old_data = mm.Data.load(), legacy_data()
    get = file_reader(inputs["0"], inputs["F"], original)
    main = get(identity=styles.ROSTER_OUTER_ID)
    situ = get(identity=mm.SITU_ID)
    count = struct.unpack_from("<I", situ, 8)[0]
    mm.require(count in (50, 51), "expected known fifty/51-row Anniversary collection")
    mm.require(mm.situ_rows(situ, old_data if count == 50 else data) == "applied", "foreign input Anniversary situations")
    teams, kits, team_receipts = new_teams(main, situ, data, get, retail)
    extended = packs.extend_situation(situ, data, main) if count == 50 else situ
    extended = bytearray(extended)
    for side, offset in (("away", 0x58), ("home", 0x5C)):
        selector = data.teams[data.moments[-1][side]]["selector"]
        struct.pack_into("<I", extended, 32 + mm.sc.RECORDS + 50 * mm.sc.STRIDE + offset, kits[selector])
    fixed, situation_receipt = fields.repair_situ(bytes(extended))
    mm.require(mm.situ_rows(fixed, data) == "applied", "repaired SITU failed recognition")
    resources, field_receipt = compile_fields(get, retail.get, fixed, field_cache, progress)
    additions = dict(teams, **resources)
    marker = b"Anniversary resource alignment; generated by 2K5 Mod Studio.\n"
    additions["a1_archive_alignment.bin"] = (marker * (2048 // len(marker) + 1))[:2048]
    out0, out_f, pack_receipt = packs.update_packs(inputs["0"], inputs["F"], additions, situation=fixed)
    xbe, moment_receipt = mm.apply(inputs["default.xbe"], data, legacy_data=old_data)
    xbe, era_receipt = era.apply(xbe)
    xbe, gate_receipt = gate.apply(xbe, gate.installed_tables(xbe), blocking=gate.installed_blocking(xbe))
    xbe, venue_receipt = venues.apply(xbe)
    mm.require(mm.status(xbe, data) == era.status(xbe) == venues.status(xbe) == "applied", "final XBE recognition failed")
    scope = xbe_scope(inputs["default.xbe"], xbe)
    return {"0": out0, "F": out_f, "default.xbe": xbe}, dict(
        moments=moment_receipt, era=era_receipt, kickoff=gate_receipt, venues=venue_receipt, xbe_scope=scope,
        situation=situation_receipt, teams=team_receipts, fields=field_receipt, packs=pack_receipt,
        physical_order_preserved=True, display_order=list(mm.display_order(data)),
        uniform_limitation="Cincinnati uses preserved retail 2004 kit 8; the 2025 White Bengal uniform is unavailable.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-disc", default=V04_DISC, type=Path)
    parser.add_argument("--retail-source", default=RETAIL, type=Path)
    parser.add_argument("--accepted-input-hashes", type=Path)
    parser.add_argument("--field-cache", type=Path, help="Owned scratch cache, validated against every source and artifact hash")
    args = parser.parse_args(argv)
    source, output = args.input_dir.resolve(), args.output_dir.resolve()
    mm.require(source != output, "output directory must differ from the read-only input")
    accepted = accepted_hashes(args.accepted_input_hashes)
    inputs = {}
    for name in BASELINE:
        path = source / name
        if not path.exists() and name in ("0", "F"):
            path = source / ("pack0" if name == "0" else "packF")
        inputs[name] = read(path)
        mm.require(sha(inputs[name]) == accepted[name], "unexpected input hash: " + name)
    with archive.Disc(args.source_disc, descriptors=()) as original, styles.Source(args.retail_source) as retail:
        entry = next(e for name, e in original.entries.items() if name.lower() == "default.xbe")
        mm.require(sha(original.read(entry.size, entry.byte_offset)) == BASELINE["default.xbe"], "unexpected v0.4 source executable")
        results, receipt = transform(inputs, original, retail, field_cache=args.field_cache,
                                     progress=lambda i, n, name: print(f"Field {i}/{n}: {name}", flush=True))
        # Replaying the pure transform proves idempotence before any output is written.
        again, replay = transform(results, original, retail, field_cache=args.field_cache)
        mm.require(results == again, "native Anniversary repair is not idempotent")
    receipt.update(schema="b765/a1_native_repair/v1", runtime_witnessed=False, idempotent=True,
                   replay_status=replay["packs"]["status"], accepted_input_manifest=bool(args.accepted_input_hashes),
                   files={name: dict(before_sha256=sha(inputs[name]), after_sha256=sha(results[name]),
                                     before_size=len(inputs[name]), after_size=len(results[name])) for name in BASELINE},
                   touched_disc_files=["vc_53450030/0", "vc_53450030/F", "default.xbe"])
    output.mkdir(parents=True, exist_ok=True)
    for name, raw in results.items():
        write_new(output / name, raw)
    write_new(output / "a1_receipt.json", (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({"status": "DONE", "output": str(output), "receipt": str(output / "a1_receipt.json")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Write per-uniform ``Unif`` packed colours into a copy of a PS2 NFL 2K5 disc.

This is the PS2 half of the Xbox ``nfl2k5.colors.unif_words`` capability.  Each
of the 634 physical uniform packages on ``SLUS-20919`` owns an eight-byte pair
inside its own ``Unif`` resource -- word 0 the facemask/faceshield tint, word 1
the ``HI_turtleneck`` tint.  Both are ``u32`` little-endian ARGB, so an edit is
a **same-size word poke**: nothing moves, nothing is reallocated, and the ISO
keeps its exact byte length.

Discipline, every rule enforced and each refusal saying so
---------------------------------------------------------
* **The source image is opened read-only and never written.**  A new image is
  produced by ``ps2_iso9660_writer.replace_files``, which copies the source --
  trailing slack included -- and patches inside the existing extents only.
* **Fixed allocation.**  A replacement word is exactly four bytes and a
  replacement span exactly eight; a target's ``Unif`` body stays 80 bytes and
  the pack file keeps its declared length to the byte.
* **No pointer may move.**  The colour offset is resolved through each object's
  own descriptor pointer, cross-checked against the Xbox writer's constant, and
  a target whose object does not decode is refused rather than guessed at.
* **Compressed bodies are refused.**  A poke into an LZ-compressed body would
  have to be recompressed back into the stored span.  No retail ``Unif`` chunk
  is compressed (0 of 634 measured), so this lane refuses instead of shipping an
  unexercised refit path.
* **Pinned targets.**  With ``--catalog``, every selector's live probe digest,
  descriptor offset and archive id must equal the catalogue's; a modded or
  mismatched image is refused, not silently written.
* Nothing is created until every check has passed, so a refusal leaves no
  destination behind.

Cost, because it is not obvious: ``replace_files`` works at *file* granularity
and each ``/VC_20919`` pack is 1 GiB, so an eight-byte poke stages and rewrites
a whole gibibyte.  That is the price of the fixed-allocation guarantee.  The
staging copy here is streamed rather than held, but the ISO writer does read
each staged pack into memory, so a recipe touching both packs that carry ``Unif``
resources (133 targets in ``/VC_20919/0.``, 501 in ``/1.``) costs about 2 GiB of
RAM.  Split such a recipe if that matters on the machine at hand.

Usage::

    nfl2k5_ps2_unif_color_patch.py --source <stock.iso> --destination <new.iso> \\
        --recipe <recipe.json> [--catalog <catalog.json>] [--receipt <receipt.json>]
    nfl2k5_ps2_unif_color_patch.py --source <stock.iso> --recipe <r.json> --dry-run
    nfl2k5_ps2_unif_color_patch.py --selftest

Recipe (``nfl2k5_ps2_unif_color_recipe/v1``)::

    {"schema": "nfl2k5_ps2_unif_color_recipe/v1",
     "edits": [{"selector": "09H0", "facemask": "#12FF34", "turtleneck": "FF001122"}]}

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import nfl2k5_ps2_unif_color_target_catalog as catalog_tool  # noqa: E402
import ps2_iso9660 as iso  # noqa: E402
import ps2_iso9660_writer as iso_writer  # noqa: E402


SCHEMA = "nfl2k5_ps2_unif_color_write/v1"
RECIPE_SCHEMA = "nfl2k5_ps2_unif_color_recipe/v1"
SERIAL = catalog_tool.SERIAL
SPAN_BYTES = catalog_tool.COLOUR_SPAN_BYTES
WORD_NAMES = catalog_tool.WORD_NAMES
WORD_BYTES = 4
COPY_CHUNK = 8 * 1024 * 1024
MAX_EDITS = 634


class ColorPatchError(ValueError):
    """A colour edit would have broken one of this writer's guarantees."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ColorPatchError(message)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# Recipe
# --------------------------------------------------------------------------

def load_recipe(path: Path) -> List[Dict[str, Any]]:
    """Read and fully validate a recipe; return its normalised edit list."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ColorPatchError("recipe %s cannot be read: %s" % (path, exc))
    return parse_recipe(document)


def parse_recipe(document: Any) -> List[Dict[str, Any]]:
    _require(isinstance(document, dict), "a recipe must be a JSON object")
    _require(document.get("schema") == RECIPE_SCHEMA,
             "recipe schema is %r, expected %r"
             % (document.get("schema"), RECIPE_SCHEMA))
    edits = document.get("edits")
    _require(isinstance(edits, list) and edits,
             "a recipe must carry a non-empty 'edits' list")
    _require(len(edits) <= MAX_EDITS,
             "%d edits is past the %d sanity cap" % (len(edits), MAX_EDITS))
    seen = set()
    parsed = []  # type: List[Dict[str, Any]]
    for ordinal, raw in enumerate(edits):
        _require(isinstance(raw, dict), "edit %d is not an object" % ordinal)
        unknown = set(raw) - {"selector", "facemask", "turtleneck", "note"}
        _require(not unknown,
                 "edit %d carries unknown keys %s; this writer only edits the two "
                 "proved words" % (ordinal, sorted(unknown)))
        selector = raw.get("selector")
        _require(isinstance(selector, str) and selector.strip(),
                 "edit %d has no selector" % ordinal)
        selector = selector.strip().upper()
        _require(selector not in seen,
                 "selector %s appears twice; one record may be written once"
                 % selector)
        seen.add(selector)
        words = {}  # type: Dict[str, int]
        for name in WORD_NAMES:
            if raw.get(name) is None:
                continue
            try:
                value = catalog_tool.parse_color(raw[name])
            except catalog_tool.CatalogError as exc:
                raise ColorPatchError(
                    "edit %d %s: %s. A packed colour word is exactly %d bytes; a "
                    "longer literal cannot fit the fixed span."
                    % (ordinal, name, exc, WORD_BYTES))
            words[name] = value
        _require(words,
                 "edit %d for %s changes neither facemask nor turtleneck"
                 % (ordinal, selector))
        parsed.append({"selector": selector, "words": words,
                       "note": raw.get("note")})
    return parsed


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------

def _pack_bases(image) -> Dict[str, Dict[str, int]]:
    bases = {}
    for letter, base, size, path in catalog_tool.discover_packs(image):
        bases[path] = {"offset": base, "size": size, "pack": letter}
    return bases


def _check_pinned(target: Dict[str, Any], pinned: Dict[str, Any]) -> None:
    for field in ("outer_index", "outer_name_id", "colour_offset_in_chunk",
                  "colour_offset_in_pack", "iso_path", "stored_size",
                  "probe_sha256"):
        _require(
            target.get(field) == pinned.get(field),
            "%s: the image disagrees with the pinned catalogue on %s (%r vs %r). "
            "This is not the stock disc the catalogue was built from; refusing to "
            "write into an unverified target."
            % (target.get("selector"), field, target.get(field), pinned.get(field)),
        )


def plan(source: Path, recipe: Sequence[Dict[str, Any]],
         pinned_catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Resolve every edit against the operator's own image.  Writes nothing."""
    source = Path(source)
    _require(source.is_file(), "source image %s is not a file" % source)
    live = catalog_tool.build_catalog(str(source))
    pinned_by_selector = {}
    if pinned_catalog is not None:
        _require(pinned_catalog.get("schema") == catalog_tool.SCHEMA,
                 "catalogue schema is %r, expected %r"
                 % (pinned_catalog.get("schema"), catalog_tool.SCHEMA))
        pinned_by_selector = {row["selector"]: row
                              for row in pinned_catalog.get("targets", [])
                              if row.get("selector")}

    image = iso.open_image(str(source))
    bases = _pack_bases(image)

    planned = []  # type: List[Dict[str, Any]]
    with open(str(source), "rb") as stream:
        for edit in recipe:
            try:
                target = catalog_tool.find_target(live, edit["selector"])
            except catalog_tool.CatalogError as exc:
                unsafe = [row for row in live["rejected"]
                          if row.get("selector") == edit["selector"]]
                if unsafe:
                    raise ColorPatchError(
                        "%s is an unsafe target: %s. Refusing rather than writing "
                        "into a record whose layout this capability has not proved."
                        % (edit["selector"], unsafe[0]["reason"]))
                raise ColorPatchError(
                    "%s. Selectors are the 634 catalogued uniform packages; an "
                    "out-of-range selector is refused rather than guessed at."
                    % exc)
            _require(
                not target["compressed"],
                "%s: its Unif body is LZ-compressed, so a same-size word poke "
                "would have to be recompressed back into the stored span. This "
                "lane refuses that: no retail Unif chunk is compressed."
                % target["selector"],
            )
            _require(
                target["matches_xbox_offsets"],
                "%s: its descriptor resolves the colour pair to chunk offset "
                "0x%x, not the proved 0x%x. Refusing to write into a target whose "
                "layout is not the one the capability proved."
                % (target["selector"], target["colour_offset_in_chunk"],
                   catalog_tool.XBOX_COLOUR_OFFSET),
            )
            _require(target["span_size"] == SPAN_BYTES,
                     "%s: span is %d bytes, expected %d"
                     % (target["selector"], target["span_size"], SPAN_BYTES))
            if pinned_by_selector:
                pinned = pinned_by_selector.get(target["selector"])
                _require(pinned is not None,
                         "%s is not in the pinned catalogue" % target["selector"])
                _check_pinned(target, pinned)

            pack = bases.get(target["iso_path"])
            _require(pack is not None,
                     "%s: the image has no %s" % (target["selector"],
                                                  target["iso_path"]))
            offset_in_pack = target["colour_offset_in_pack"]
            _require(
                0 <= offset_in_pack and offset_in_pack + SPAN_BYTES <= pack["size"],
                "%s: its span at %d+%d falls outside the %d-byte %s extent"
                % (target["selector"], offset_in_pack, SPAN_BYTES, pack["size"],
                   target["iso_path"]),
            )
            stream.seek(target["colour_offset_in_iso"])
            retail = stream.read(SPAN_BYTES)
            _require(len(retail) == SPAN_BYTES,
                     "%s: short read at the colour span" % target["selector"])
            _require(_digest(retail) == target["retail_span_sha256"],
                     "%s: the colour span changed while it was planned"
                     % target["selector"])
            before = list(struct.unpack("<II", retail))
            after = list(before)
            for index, name in enumerate(WORD_NAMES):
                if name in edit["words"]:
                    after[index] = edit["words"][name]
            replacement = struct.pack("<II", *after)
            _require(len(replacement) == SPAN_BYTES,
                     "%s: replacement is %d bytes, the span holds %d; fixed-"
                     "allocation writes never grow a record"
                     % (target["selector"], len(replacement), SPAN_BYTES))
            _require(replacement != retail,
                     "%s already uses those colours; refusing a write that would "
                     "declare a range and change nothing in it"
                     % target["selector"])
            planned.append({
                "selector": target["selector"],
                "outer_index": target["outer_index"],
                "outer_name_id": target["outer_name_id"],
                "iso_path": target["iso_path"],
                "offset_in_pack": offset_in_pack,
                "offset_in_iso": target["colour_offset_in_iso"],
                "span_size": SPAN_BYTES,
                "words_changed": sorted(edit["words"]),
                "before_sha256": _digest(retail),
                "after_sha256": _digest(replacement),
                "replacement": replacement,
                "note": edit.get("note"),
            })

    by_file = {}  # type: Dict[str, List[Dict[str, Any]]]
    for item in planned:
        by_file.setdefault(item["iso_path"], []).append(item)
    for path, items in by_file.items():
        items.sort(key=lambda row: row["offset_in_pack"])
        for left, right in zip(items, items[1:]):
            _require(
                left["offset_in_pack"] + left["span_size"] <= right["offset_in_pack"],
                "two edits overlap inside %s at %d and %d"
                % (path, left["offset_in_pack"], right["offset_in_pack"]),
            )
    return {
        "source": str(source),
        "serial": SERIAL,
        "edits": planned,
        "by_file": by_file,
        "packs": bases,
        "catalog_summary": live["summary"],
    }


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def _build_pack(source: Path, pack: Dict[str, int], items: Sequence[Dict[str, Any]],
                destination: Path) -> str:
    """Copy one pack extent out of the image and poke its spans; return sha256."""
    remaining = pack["size"]
    position = pack["offset"]
    digest = hashlib.sha256()
    with open(str(source), "rb") as reader, open(str(destination), "wb") as writer:
        while remaining:
            reader.seek(position)
            take = min(COPY_CHUNK, remaining)
            block = reader.read(take)
            _require(len(block) == take,
                     "short read while copying %d bytes of the pack extent" % take)
            writer.write(block)
            position += take
            remaining -= take
    written = destination.stat().st_size
    _require(written == pack["size"],
             "the staged pack is %d bytes but its extent holds %d; a fixed-"
             "allocation write may not change a file's size"
             % (written, pack["size"]))
    with open(str(destination), "r+b") as handle:
        for item in items:
            handle.seek(item["offset_in_pack"])
            handle.write(item["replacement"])
        handle.flush()
        os.fsync(handle.fileno())
    with open(str(destination), "rb") as handle:
        for block in iter(lambda: handle.read(COPY_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def apply(source, destination, recipe: Sequence[Dict[str, Any]], *,
          pinned_catalog: Optional[Dict[str, Any]] = None,
          work_dir=None) -> Dict[str, Any]:
    """Produce a new image carrying the recipe's colour edits."""
    import tempfile

    source = Path(source)
    destination = Path(destination)
    _require(not destination.exists(),
             "destination %s already exists; refusing to overwrite an image"
             % destination)
    prepared = plan(source, recipe, pinned_catalog)

    staged = {}
    holder = tempfile.TemporaryDirectory(
        dir=str(work_dir) if work_dir else str(destination.parent))
    try:
        for ordinal, (path, items) in enumerate(sorted(prepared["by_file"].items())):
            staging = Path(holder.name) / ("pack%02d.bin" % ordinal)
            sha = _build_pack(source, prepared["packs"][path], items, staging)
            staged[path] = {"path": staging, "sha256": sha}
        report = iso_writer.replace_files(
            source, destination,
            {path: item["path"] for path, item in staged.items()})
    finally:
        holder.cleanup()

    receipt = {
        "schema": SCHEMA,
        "serial": SERIAL,
        "source": str(source),
        "destination": str(destination),
        "files_replaced": sorted(prepared["by_file"]),
        "edits": [{key: value for key, value in item.items() if key != "replacement"}
                  for item in prepared["edits"]],
        "declared_ranges": [
            {"start": item["offset_in_iso"], "length": item["span_size"],
             "reason": "unif_color:%s" % item["selector"]}
            for item in sorted(prepared["edits"], key=lambda row: row["offset_in_iso"])
        ],
        "staged_pack_sha256": {path: item["sha256"] for path, item in staged.items()},
        "iso_write_report": iso_writer.report_to_json(report),
        "catalog_summary": prepared["catalog_summary"],
    }
    return receipt


def write_json(path: Path, document: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    with open(str(path), "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------

def selftest(tmp: Optional[str] = None) -> int:
    """Prove one edit lands and four bad ones are refused.  Needs no game data."""
    import tempfile

    failures = []  # type: List[str]

    def check(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    def refuses(name: str, call, needle: str) -> None:
        try:
            call()
        except ColorPatchError as exc:
            if needle.lower() not in str(exc).lower():
                failures.append("%s: refused with %r, expected %r" % (name, str(exc), needle))
            return
        failures.append("%s was not refused" % name)

    with tempfile.TemporaryDirectory(dir=tmp) as work:
        room = Path(work)
        source = room / "stock.iso"
        source.write_bytes(catalog_tool.build_synthetic_iso())
        pinned = catalog_tool.build_catalog(str(source))

        good = parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
            {"selector": "18H0", "facemask": "#00FF00"},
            {"selector": "18A0", "turtleneck": "FF010203"},
        ]})
        destination = room / "edited.iso"
        receipt = apply(source, destination, good, pinned_catalog=pinned)
        check(receipt["schema"] == SCHEMA, "receipt must be stamped")
        check(len(receipt["edits"]) == 2, "both edits must be declared")
        check(destination.stat().st_size == source.stat().st_size,
              "the image must keep its exact byte length")
        check(sum(row["length"] for row in receipt["declared_ranges"]) == 2 * SPAN_BYTES,
              "two eight-byte spans must be declared")

        after = destination.read_bytes()
        before = source.read_bytes()
        differing = sum(1 for left, right in zip(before, after) if left != right)
        check(0 < differing <= 2 * SPAN_BYTES,
              "at most sixteen bytes may differ, saw %d" % differing)
        target = catalog_tool.find_target(pinned, "18H0")
        words = struct.unpack_from("<II", after, target["colour_offset_in_iso"])
        check(words[0] == 0xFF00FF00, "the facemask word must carry the new colour")
        check(words[1] == struct.unpack_from(
            "<II", before, target["colour_offset_in_iso"])[1],
            "the untouched word must survive")

        refuses("an existing destination",
                lambda: apply(source, destination, good, pinned_catalog=pinned),
                "already exists")
        refuses("an out-of-range selector",
                lambda: apply(source, room / "a.iso",
                              parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                                  {"selector": "99A9", "facemask": "#000000"}]})),
                "out-of-range")
        refuses("a compressed Unif body that cannot be refit",
                lambda: apply(source, room / "b.iso",
                              parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                                  {"selector": "07H1", "facemask": "#000000"}]})),
                "recompressed back into the stored span")
        refuses("an over-length colour literal",
                lambda: parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                    {"selector": "18H0", "facemask": "FFAABBCCDD"}]}),
                "exactly 4 bytes")
        refuses("a no-op edit",
                lambda: apply(source, room / "c.iso",
                              parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                                  {"selector": "18H0", "facemask": "FFA29895"}]})),
                "already uses those colours")
        forged = json.loads(json.dumps(pinned))
        forged["targets"][0]["probe_sha256"] = "0" * 64
        refuses("a catalogue that disagrees with the image",
                lambda: apply(source, room / "d.iso",
                              parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                                  {"selector": forged["targets"][0]["selector"],
                                   "facemask": "#123456"}]}),
                              pinned_catalog=forged),
                "not the stock disc")
        for name in ("a.iso", "b.iso", "c.iso", "d.iso"):
            check(not (room / name).exists(),
                  "a refusal must not leave %s behind" % name)

        refuses("a recipe with the wrong schema",
                lambda: parse_recipe({"schema": "nope", "edits": []}),
                "recipe schema")
        refuses("an edit that changes nothing",
                lambda: parse_recipe({"schema": RECIPE_SCHEMA,
                                      "edits": [{"selector": "18H0"}]}),
                "changes neither")
        refuses("a duplicate selector",
                lambda: parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                    {"selector": "18H0", "facemask": "#111111"},
                    {"selector": "18h0", "turtleneck": "#222222"}]}),
                "appears twice")
        refuses("an unknown edit key",
                lambda: parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                    {"selector": "18H0", "visor": "#111111"}]}),
                "unknown keys")

    for failure in failures:
        print("FAIL: %s" % failure, file=sys.stderr)
    if failures:
        return 1
    print("NFL2K5_PS2_UNIF_COLOR_PATCH_SELFTEST_OK")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, help="stock SLUS-20919 ISO (read-only)")
    parser.add_argument("--destination", type=Path, help="new ISO to create")
    parser.add_argument("--recipe", type=Path, help="colour recipe JSON")
    parser.add_argument("--catalog", type=Path, help="pinned target catalogue JSON")
    parser.add_argument("--receipt", type=Path, help="write the receipt here")
    parser.add_argument("--work-dir", type=Path,
                        help="directory for staged pack files (defaults beside "
                             "the destination)")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan and report without creating anything")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--tmp", help="directory for self-test scratch files")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest(args.tmp)
    if not args.source or not args.recipe:
        parser.error("--source and --recipe are required unless --selftest is given")
    if not args.dry_run and not args.destination:
        parser.error("--destination is required unless --dry-run is given")

    try:
        recipe = load_recipe(args.recipe)
        pinned = None
        if args.catalog:
            pinned = json.loads(args.catalog.read_text(encoding="utf-8"))
        if args.dry_run:
            prepared = plan(args.source, recipe, pinned)
            document = {
                "schema": SCHEMA + "-dry-run",
                "source": prepared["source"],
                "files_replaced": sorted(prepared["by_file"]),
                "edits": [{key: value for key, value in item.items()
                           if key != "replacement"}
                          for item in prepared["edits"]],
            }
        else:
            document = apply(args.source, args.destination, recipe,
                             pinned_catalog=pinned, work_dir=args.work_dir)
    except (ColorPatchError, catalog_tool.CatalogError, iso_writer.IsoWriteError,
            iso.FormatError, OSError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.receipt:
        write_json(args.receipt, document)
    print("NFL2K5_PS2_UNIF_COLOR_PATCH_OK edits=%d files=%d%s"
          % (len(document["edits"]), len(document["files_replaced"]),
             " (dry run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

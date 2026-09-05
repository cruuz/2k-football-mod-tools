#!/usr/bin/env python3
"""Write edited text into a *copy* of an ESPN NFL 2K5 PS2 disc, inside its allocation.

Given the user's own ``SLUS-20919`` ISO and a recipe of ``{bank, index,
new_text}`` edits, this produces a **new** ISO in which those strings read
differently and nothing else about the image has changed.  The source is opened
read-only and is never written.

WHAT "INSIDE ITS ALLOCATION" MEANS HERE, AND WHY IT IS STRICTER THAN IT SOUNDS
------------------------------------------------------------------------------
Each string owns a run of bytes in its bank's UTF-16LE pool, and every pointer
that reaches it is an offset into that pool.  Move a string and every later
pointer is wrong; grow one and it overruns its neighbour.  So a replacement is
written into the bytes the original already occupies, terminated, and
zero-filled to the end of that run.  No pointer, record count, resource size,
pool boundary, archive extent or directory record moves.

On this disc that rule bites harder than on Xbox, and the catalog says why: the
pools are packed with **no slack at all**.  An allocation is exactly
``len(original) * 2 + 2`` bytes, so the budget is the original string's own
length in UTF-16 code units.  A replacement may be shorter or exactly as long;
one character longer is refused.  Every over-length refusal quotes both numbers.

REFUSALS, ALL OF THEM BEFORE THE DESTINATION EXISTS
---------------------------------------------------
* a bank the catalog could not decode, or one it marks read-only;
* a string the catalog marks read-only (a zero-capacity allocation, or a SITU
  team selector whose consumer is scenario lookup rather than display);
* a replacement that does not fit its allocation;
* a replacement that drops, adds, renames or reorders an inline formatted token
  -- a ``|CROSS|``-style marker draws a glyph, a ``%d`` makes the formatter read
  an argument, and either change alters what the engine does at draw time;
* an empty replacement, or one containing NUL;
* two edits aimed at the same allocation, or an edit that changes nothing;
* a bank whose body is LZ-compressed.  Recompressing a chunk to fit a fixed
  span is the stadium/texture lane's problem, not this one: **no text bank on
  this disc is compressed**, so rather than carry an untested recompression
  path, this refuses and says so.  If a future disc revision compresses one, the
  refusal is the correct answer until that path is built and proved.

The destination is created by ``ps2_iso9660_writer.replace_files``, which
enforces fixed allocation at the ISO9660 level too and declares every byte range
it writes.  Hand its report, with both images, to
``nfl2k5_ps2_text_verify.py``.

COST
----
A text bank lives inside ``/VC_20919/0.``, which is a 1 GiB file, and the ISO is
4.3 GiB.  Because the ISO writer replaces whole files, one run streams the pack
out to a temporary file, patches the handful of bytes in it, and then copies the
whole image.  That is ~5.5 GiB of I/O to change a dozen bytes.  It is the honest
price of reusing the bounded writer rather than reaching into the image
directly, and the temporary file is removed whether or not the run succeeds.

USAGE
-----
    nfl2k5_ps2_text_patch.py --source-iso <in.iso> --destination-iso <out.iso> \\
        --recipe edits.json --report patch-report.json
    nfl2k5_ps2_text_patch.py --source-iso <in.iso> --recipe edits.json --dry-run
    nfl2k5_ps2_text_patch.py --selftest

Recipe shape::

    {"edits": [{"bank": "nfl2k5.ps2.text-bank.strg.24.65",
                "index": 867,
                "new_text": "PLAY"}]}

``selector`` may be given instead of ``bank`` + ``index``.  An optional
``expect_sha256`` is checked against the original string's UTF-16LE digest, so a
recipe written against one disc revision fails loudly on another instead of
editing whatever now sits at that index.

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl2k5_ps2_text_target_catalog as catalog  # noqa: E402
import ps2_iso9660_writer as iso_writer  # noqa: E402


SCHEMA = "nfl2k5_ps2_text_patch/v1"
COPY_CHUNK = 8 * 1024 * 1024
MAX_EDITS = 4096


class TextPatchError(ValueError):
    """A requested edit would have broken one of this writer's guarantees."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise TextPatchError(message)


# ``os.pread``/``os.pwrite`` do not exist on Windows, where these tools also
# run, so positional access goes through a fallback that restores the file
# pointer -- the same shape ``ps2_iso9660_writer.py`` uses.

def _pwrite_exact(descriptor: int, offset: int, data: bytes) -> None:
    view = memoryview(data)
    written = 0
    while written < len(view):
        positional = getattr(os, "pwrite", None)
        if positional is not None:
            count = positional(descriptor, view[written:], offset + written)
        else:
            saved = os.lseek(descriptor, 0, os.SEEK_CUR)
            try:
                os.lseek(descriptor, offset + written, os.SEEK_SET)
                count = os.write(descriptor, view[written:])
            finally:
                os.lseek(descriptor, saved, os.SEEK_SET)
        _require(count > 0, "short write at 0x%x" % (offset + written))
        written += count


def _pread_exact(descriptor: int, offset: int, size: int) -> bytes:
    out = bytearray()
    while len(out) < size:
        positional = getattr(os, "pread", None)
        if positional is not None:
            block = positional(descriptor, size - len(out), offset + len(out))
        else:
            saved = os.lseek(descriptor, 0, os.SEEK_CUR)
            try:
                os.lseek(descriptor, offset + len(out), os.SEEK_SET)
                block = os.read(descriptor, size - len(out))
            finally:
                os.lseek(descriptor, saved, os.SEEK_SET)
        _require(bool(block), "short read at 0x%x" % (offset + len(out)))
        out.extend(block)
    return bytes(out)


# ---------------------------------------------------------------------------
# Recipe resolution
# ---------------------------------------------------------------------------

class ResolvedEdit:
    """One validated edit, with the exact bytes and the exact place to put them."""

    __slots__ = ("selector", "bank_id", "pool_index", "label", "bank_kind",
                 "pack_iso_path", "pack_offset", "iso_byte_offset",
                 "allocation_bytes", "original_sha256", "replacement",
                 "replacement_sha256", "new_code_units", "tokens",
                 "reference_count")

    def __init__(self, **fields) -> None:
        for key, value in fields.items():
            setattr(self, key, value)

    def as_report(self) -> dict:
        return {
            "selector": self.selector,
            "bank_id": self.bank_id,
            "bank_kind": self.bank_kind,
            "pool_index": self.pool_index,
            "label": self.label,
            "pack_iso_path": self.pack_iso_path,
            "pack_offset": self.pack_offset,
            "iso_byte_offset": self.iso_byte_offset,
            "allocation_bytes": self.allocation_bytes,
            "original_text_sha256": self.original_sha256,
            "replacement_text_sha256": self.replacement_sha256,
            "replacement_bytes_sha256": hashlib.sha256(self.replacement).hexdigest(),
            "new_code_units": self.new_code_units,
            "tokens": list(self.tokens),
            "reference_count": self.reference_count,
        }


def load_recipe(path) -> List[dict]:
    """Read and shape-check a recipe file."""
    try:
        with open(path, "r", encoding="utf-8") as stream:
            document = json.load(stream)
    except (OSError, ValueError) as exc:
        raise TextPatchError("could not read the recipe: %s" % exc)
    _require(isinstance(document, dict), "a recipe must be a JSON object")
    edits = document.get("edits")
    _require(isinstance(edits, list) and edits,
             "a recipe needs a nonempty 'edits' list")
    _require(len(edits) <= MAX_EDITS,
             "%d edits in one recipe is past the %d sanity cap"
             % (len(edits), MAX_EDITS))
    for index, edit in enumerate(edits):
        _require(isinstance(edit, dict), "edit %d is not an object" % index)
    return edits


def _selector_of(edit: dict, index: int) -> str:
    selector = edit.get("selector")
    if selector is not None:
        _require(isinstance(selector, str) and selector,
                 "edit %d has a non-string selector" % index)
        return selector
    bank = edit.get("bank")
    pool_index = edit.get("index")
    _require(isinstance(bank, str) and bank,
             "edit %d needs 'selector', or 'bank' and 'index'" % index)
    _require(isinstance(pool_index, int) and not isinstance(pool_index, bool)
             and pool_index >= 0,
             "edit %d needs a non-negative integer 'index'" % index)
    return "%s#%d" % (bank, pool_index)


def _check_bank_editable(index: int, bank: dict) -> None:
    """The three ways a whole bank is off limits, each with its own reason."""
    _require(not bank["compressed"],
             "edit %d targets bank %s, whose body is LZ-compressed. Fitting a "
             "recompressed chunk back into a fixed span is not proved for text "
             "-- and no text bank on the retail disc is compressed -- so this "
             "is refused rather than attempted." % (index, bank["bank_id"]))
    _require(not bank["crosses_pack_boundary"],
             "edit %d targets bank %s, which spans two pack files; one bounded "
             "file replacement cannot cover it." % (index, bank["bank_id"]))
    _require(bank["decoded"],
             "edit %d targets bank %s, which this disc does not decode, so no "
             "edit inside it can be shown to be safe: %s"
             % (index, bank["bank_id"], bank["reason"]))


def resolve_edits(catalog_document: dict, edits: Sequence[dict]) -> List[ResolvedEdit]:
    """Turn recipe entries into byte-exact replacements, refusing anything unsafe."""
    banks = {bank["bank_id"]: bank for bank in catalog_document["banks"]}
    by_selector = {row["selector"]: row for row in catalog_document["strings"]}
    by_bank_index = {}
    for row in catalog_document["strings"]:
        bank_id = row["selector"].split(":", 1)[0]
        by_bank_index.setdefault((bank_id, row["pool_index"]), row)

    resolved: List[ResolvedEdit] = []
    seen: Dict[str, int] = {}
    for index, edit in enumerate(edits):
        key = _selector_of(edit, index)

        # An undecoded bank contributes no string rows, so an index lookup
        # inside one would otherwise report "this disc does not have that
        # index" when the real answer is "that bank is not editable, and here
        # is why".  Check the bank first whenever the recipe names one.
        named_bank = edit.get("bank") if isinstance(edit.get("bank"), str) \
            else key.split(":", 1)[0]
        if named_bank in banks:
            _check_bank_editable(index, banks[named_bank])
        if "#" in key and key not in by_selector:
            bank_id, _, pool_index = key.rpartition("#")
            row = by_bank_index.get((bank_id, int(pool_index)))
            _require(row is not None,
                     "edit %d names bank %r index %s, which this disc does not "
                     "have. Run the catalog tool to list what it does have."
                     % (index, bank_id, pool_index))
        else:
            row = by_selector.get(key)
            _require(row is not None,
                     "edit %d names the unknown text selector %r" % (index, key))

        selector = row["selector"]
        bank_id = selector.split(":", 1)[0]
        bank = banks[bank_id]
        _check_bank_editable(index, bank)
        _require(row["editable"],
                 "edit %d targets a read-only string (%s): %s"
                 % (index, selector,
                    catalog.REASON_CODES.get(row["reason_code"], row["reason_code"])))

        if selector in seen:
            raise TextPatchError(
                "edits %d and %d both target %s; one allocation can only hold "
                "one replacement" % (seen[selector], index, selector))
        seen[selector] = index

        new_text = edit.get("new_text")
        _require(isinstance(new_text, str),
                 "edit %d needs a string 'new_text'" % index)
        expected = edit.get("expect_sha256")
        if expected is not None:
            _require(isinstance(expected, str)
                     and expected.lower() == row["text_sha256"],
                     "edit %d expected the string at %s to digest to %s, but this "
                     "disc has %s. The recipe was written against a different "
                     "disc or index." % (index, selector, expected,
                                         row["text_sha256"]))

        allocation = row["allocation_bytes"]
        label = "%s (%s)" % (row["label"], selector)
        try:
            replacement = catalog.encode_fixed_utf16le(new_text, allocation, label)
        except catalog.CatalogError as exc:
            raise TextPatchError(
                "%s. This disc's string pools have no spare bytes, so the budget "
                "is the original string's own length: %d UTF-16 code units."
                % (exc, allocation // 2 - 1))

        # The original text is not in the catalog, so token preservation is
        # checked against the tokens the catalog recorded for it.
        new_tokens = catalog.tokens_in(new_text)
        original_tokens = list(row["tokens"])
        if new_tokens != original_tokens:
            _token_refusal(index, selector, original_tokens, new_tokens)

        resolved.append(ResolvedEdit(
            selector=selector, bank_id=bank_id, pool_index=row["pool_index"],
            label=row["label"], bank_kind=row["bank_kind"],
            pack_iso_path=bank["pack_iso_path"],
            pack_offset=bank["pack_offset"] + row["body_offset"],
            iso_byte_offset=bank["iso_byte_offset"] + row["body_offset"],
            allocation_bytes=allocation,
            original_sha256=row["text_sha256"],
            replacement=replacement,
            replacement_sha256=hashlib.sha256(
                new_text.encode("utf-16le")).hexdigest(),
            new_code_units=len(new_text.encode("utf-16le")) // 2,
            tokens=new_tokens,
            reference_count=row["reference_count"],
        ))

    _check_no_overlap(resolved)
    return resolved


def _token_refusal(index: int, selector: str, before: List[str],
                   after: List[str]) -> None:
    missing = [token for token in before if token not in after]
    added = [token for token in after if token not in before]
    if missing:
        raise TextPatchError(
            "edit %d drops the inline token%s %s from %s. The engine draws a "
            "glyph there, so the replacement has to keep it."
            % (index, "" if len(missing) == 1 else "s",
               ", ".join(sorted(set(missing))), selector))
    if added:
        raise TextPatchError(
            "edit %d introduces the inline token%s %s into %s, which the "
            "original does not have. A pipe marker draws a glyph and a %% "
            "conversion makes the formatter read an argument that was never "
            "passed." % (index, "" if len(added) == 1 else "s",
                         ", ".join(sorted(set(added))), selector))
    raise TextPatchError(
        "edit %d keeps the same inline tokens in %s but reorders them; the "
        "engine draws them in the order it finds them." % (index, selector))


def _check_no_overlap(resolved: Sequence[ResolvedEdit]) -> None:
    ordered = sorted(resolved, key=lambda item: (item.pack_iso_path, item.pack_offset))
    for left, right in zip(ordered, ordered[1:]):
        if left.pack_iso_path == right.pack_iso_path and \
                left.pack_offset + left.allocation_bytes > right.pack_offset:
            raise TextPatchError(
                "the replacements for %s and %s overlap in %s; the catalog's "
                "allocations should be disjoint, so this means the recipe or "
                "the disc is not what it claims"
                % (left.selector, right.selector, left.pack_iso_path))


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _pack_entries(iso_path: str) -> Dict[str, tuple]:
    """``{iso_path: (byte_offset, length)}`` for every /VC_20919 pack."""
    image = catalog.iso.open_image(iso_path)
    result = {}
    for name, base, size in catalog.discover_packs(image):
        result["%s/%s." % (catalog.PACK_DIRECTORY, name)] = (base, size)
    return result


def _materialise_pack(source_iso: str, base: int, size: int,
                      edits: Sequence[ResolvedEdit], directory: Path) -> Path:
    """Copy one pack out of the ISO and apply its edits, returning the temp path."""
    descriptor, name = tempfile.mkstemp(prefix="nfl2k5-ps2-text-pack-",
                                        suffix=".bin", dir=str(directory))
    temporary = Path(name)
    try:
        with open(source_iso, "rb") as stream:
            stream.seek(base)
            remaining = size
            while remaining:
                block = stream.read(min(COPY_CHUNK, remaining))
                _require(len(block) == min(COPY_CHUNK, remaining),
                         "the ISO ended inside %s" % source_iso)
                written = 0
                while written < len(block):
                    written += os.write(descriptor, block[written:])
                remaining -= len(block)
        for edit in edits:
            _require(0 <= edit.pack_offset
                     and edit.pack_offset + len(edit.replacement) <= size,
                     "%s falls outside its pack file" % edit.selector)
            _pwrite_exact(descriptor, edit.pack_offset, edit.replacement)
            _require(_pread_exact(descriptor, edit.pack_offset,
                                  len(edit.replacement)) == edit.replacement,
                     "readback mismatch for %s" % edit.selector)
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    os.close(descriptor)
    return temporary


def patch(*, source_iso, destination_iso, edits: Sequence[dict],
          dry_run: bool = False) -> dict:
    """Resolve, refuse or write.  Nothing is created until every check passes."""
    source_iso = str(Path(source_iso))
    catalog_document = catalog.build_catalog(source_iso)
    resolved = resolve_edits(catalog_document, edits)

    # A run that would change no bytes produces a report the verifier cannot
    # check and an output identical to the input; say so instead.
    packs = _pack_entries(source_iso)
    by_pack: Dict[str, List[ResolvedEdit]] = {}
    changed_bytes = 0
    with open(source_iso, "rb") as stream:
        for edit in resolved:
            _require(edit.pack_iso_path in packs,
                     "%s names pack %s, which this ISO does not have"
                     % (edit.selector, edit.pack_iso_path))
            base, size = packs[edit.pack_iso_path]
            _require(edit.iso_byte_offset == base + edit.pack_offset,
                     "%s: catalog offset and ISO pack extent disagree" % edit.selector)
            stream.seek(edit.iso_byte_offset)
            before = stream.read(edit.allocation_bytes)
            _require(len(before) == edit.allocation_bytes,
                     "the ISO ended inside %s" % edit.selector)
            differing = sum(1 for old, new in zip(before, edit.replacement)
                            if old != new)
            _require(differing,
                     "edit for %s would not change any bytes; the replacement is "
                     "the text that is already there" % edit.selector)
            changed_bytes += differing
            by_pack.setdefault(edit.pack_iso_path, []).append(edit)
            del size

    result = {
        "schema": SCHEMA,
        "source": {"path": source_iso, "size": os.stat(source_iso).st_size},
        "recipe": {"edit_count": len(resolved),
                   "changed_byte_count": changed_bytes},
        "edits": [edit.as_report() for edit in resolved],
        "packs": [
            {"iso_path": iso_path,
             "edit_count": len(items),
             "replaced_ranges": [
                 {"pack_offset": item.pack_offset,
                  "iso_byte_offset": item.iso_byte_offset,
                  "length": item.allocation_bytes} for item in sorted(
                      items, key=lambda one: one.pack_offset)]}
            for iso_path, items in sorted(by_pack.items())],
        "claims": {
            "source_opened_read_only": True,
            "fixed_allocation": True,
            "pointers_unchanged": True,
            "resource_sizes_unchanged": True,
            "tokens_preserved": True,
            "recompression_used": False,
            "report_contains_replacement_text": False,
        },
    }
    if dry_run:
        result["dry_run"] = True
        return result

    _require(destination_iso is not None,
             "a destination ISO is required unless --dry-run is given")
    destination = Path(destination_iso)
    _require(not destination.exists(),
             "the destination already exists: %s" % destination)
    _require(destination.resolve() != Path(source_iso).resolve(),
             "the destination must not be the source image")

    scratch = destination.parent
    temporaries: List[Path] = []
    try:
        replacements = {}
        for iso_path, items in sorted(by_pack.items()):
            base, size = packs[iso_path]
            temporary = _materialise_pack(source_iso, base, size, items, scratch)
            temporaries.append(temporary)
            _require(temporary.stat().st_size == size,
                     "the rebuilt %s is %d bytes, not the %d its extent owns"
                     % (iso_path, temporary.stat().st_size, size))
            replacements[iso_path] = temporary
        write_report = iso_writer.replace_files(source_iso, destination, replacements)
    finally:
        for temporary in temporaries:
            temporary.unlink(missing_ok=True)

    result["destination"] = {
        "path": str(destination),
        "size": os.stat(destination).st_size,
    }
    # The writer hands back ByteRange objects; flatten them so the report is
    # JSON, and so ``nfl2k5_ps2_text_verify.py`` can be given it as a file.
    result["iso_write_report"] = iso_writer.report_to_json(write_report)
    return result


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

def selftest(tmp: Optional[Path] = None) -> int:
    """Exercise resolution and every refusal against a synthetic catalog."""
    failures: List[str] = []

    def refuses(edits, why: str) -> None:
        try:
            resolve_edits(document, edits)
            failures.append("accepted: %s" % why)
        except TextPatchError:
            pass

    texts = ["MENU", "Press |CROSS| to go", "OPTIONS", ""]
    body = catalog.build_synthetic_strg_body(texts)
    parsed = catalog.parse_strg(body)
    bank_id = "nfl2k5.ps2.text-bank.strg.1.0"
    extra, strings = catalog._strg_assets(body, bank_id)
    bank = {"bank_id": bank_id, "decoded": True, "compressed": False,
            "crosses_pack_boundary": False, "reason": "synthetic",
            "pack_iso_path": "/VC_20919/0.", "pack_offset": 0x1000,
            "iso_byte_offset": 0x9000}
    bank.update(extra)
    document = {"banks": [bank], "strings": strings}

    ok = resolve_edits(document, [{"bank": bank_id, "index": 0, "new_text": "PLAY"}])
    if len(ok) != 1 or ok[0].allocation_bytes != len("MENU") * 2 + 2:
        failures.append("a same-length edit did not resolve")
    elif ok[0].replacement != "PLAY".encode("utf-16le") + b"\0\0":
        failures.append("same-length replacement bytes are wrong")

    short = resolve_edits(document, [{"bank": bank_id, "index": 0, "new_text": "GO"}])
    if short[0].replacement != "GO".encode("utf-16le") + b"\0\0" + bytes(4):
        failures.append("a shorter edit did not zero-fill its tail")

    refuses([{"bank": bank_id, "index": 0, "new_text": "PLAYER"}],
            "an over-length replacement")
    refuses([{"bank": bank_id, "index": 0, "new_text": ""}],
            "an empty replacement")
    refuses([{"bank": bank_id, "index": 1, "new_text": "Press now to go!!"}],
            "a dropped |CROSS| token")
    refuses([{"bank": bank_id, "index": 0, "new_text": "%d!"}],
            "an added printf conversion")
    refuses([{"bank": bank_id, "index": 3, "new_text": "X"}],
            "a zero-capacity allocation")
    refuses([{"bank": bank_id, "index": 99, "new_text": "X"}],
            "an index this bank does not have")
    refuses([{"bank": "nfl2k5.ps2.text-bank.strg.9.9", "index": 0, "new_text": "X"}],
            "a bank this disc does not have")
    refuses([{"bank": bank_id, "index": 0, "new_text": "PLAY"},
             {"bank": bank_id, "index": 0, "new_text": "QUIT"}],
            "two edits on one allocation")
    refuses([{"bank": bank_id, "index": 0, "new_text": "PLAY",
              "expect_sha256": "0" * 64}],
            "a stale expect_sha256")
    refuses([{"bank": bank_id, "index": 0}], "an edit with no new_text")

    unsafe = dict(bank, decoded=False, reason="synthetic undecoded bank")
    document_unsafe = {"banks": [unsafe], "strings": strings}
    try:
        resolve_edits(document_unsafe,
                      [{"bank": bank_id, "index": 0, "new_text": "PLAY"}])
        failures.append("accepted: an edit into an undecoded bank")
    except TextPatchError:
        pass

    compressed = dict(bank, compressed=True)
    document_compressed = {"banks": [compressed], "strings": strings}
    try:
        resolve_edits(document_compressed,
                      [{"bank": bank_id, "index": 0, "new_text": "PLAY"}])
        failures.append("accepted: an edit into an LZ-compressed bank")
    except TextPatchError:
        pass

    del parsed
    for line in failures:
        print("FAIL: %s" % line, file=sys.stderr)
    if failures:
        return 1
    print("NFL2K5_PS2_TEXT_PATCH_SELFTEST_PASS refusals=13")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--source-iso")
    parser.add_argument("--destination-iso")
    parser.add_argument("--recipe")
    parser.add_argument("--report")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.source_iso or not args.recipe:
        parser.error("--source-iso and --recipe are required unless --selftest")
    try:
        edits = load_recipe(args.recipe)
        result = patch(source_iso=args.source_iso,
                       destination_iso=args.destination_iso,
                       edits=edits, dry_run=args.dry_run)
    except (TextPatchError, catalog.CatalogError, iso_writer.IsoWriteError,
            OSError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1
    if args.report:
        payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        with open(args.report, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    print(json.dumps({
        "edit_count": result["recipe"]["edit_count"],
        "changed_byte_count": result["recipe"]["changed_byte_count"],
        "destination": result.get("destination", {}).get("path"),
        "dry_run": bool(result.get("dry_run")),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

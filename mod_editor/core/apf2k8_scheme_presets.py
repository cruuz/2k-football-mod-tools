"""Authored CPU-book selections using only SPLB membership and audible tags.

Recipes describe desired membership and tags, so repeat application is a no-op.
Each tag move is compiled separately because the existing batch writer sorts
moves by source play: composing dependent swaps in one batch is not equivalent.
No record is emptied and no formation/personnel/MASTER data is changed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import zlib

from .errors import ValidationError
from . import apf2k8_splb_writer as splb
from .apf2k8_book_clone import rebuild_resource, compare_untouched_packs, compare_executable
from .apf2k8_book_identity import disc_book_identity_report, filename_id, read_resource
import playbook_inventory
import apf_outer


PROVIDER_KIND = "splb_scheme_preset"
RECIPE_SCHEMA = "apf2k8_scheme_preset/v1"
REPORT_SCHEMA = "apf2k8_scheme_preset_receipt/v1"
PRESET_ROOT = Path(__file__).resolve().parents[2] / "data" / "apf2k8" / "scheme_presets"
PRESET_IDS = ("wide-zone", "spread-to-run", "pro-power")


def load_preset(preset_id: str) -> dict:
    if preset_id not in PRESET_IDS:
        raise ValidationError("Choose Wide Zone, Spread-to-Run, or Pro Power")
    return decode_recipe((PRESET_ROOT / (preset_id + ".json")).read_bytes())


def decode_recipe(data: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValidationError(f"Duplicate preset field: {key}")
            result[key] = value
        return result
    try:
        recipe = json.loads(data.decode("utf-8"), object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise ValidationError(f"Invalid scheme preset JSON: {exc}") from exc
    validate_recipe(recipe)
    return recipe


def validate_recipe(recipe: dict) -> None:
    fields = {"schema", "id", "name", "book_type", "intent", "limitations", "play_names", "groups"}
    if not isinstance(recipe, dict) or set(recipe) != fields or recipe["schema"] != RECIPE_SCHEMA:
        raise ValidationError("Unsupported scheme preset schema/fields")
    if any(not isinstance(recipe[x], str) or not recipe[x] for x in
           ("id", "name", "book_type", "intent", "limitations")):
        raise ValidationError("Preset descriptions and book type must be nonempty text")
    if recipe["book_type"] not in {x for x in splb.STOCK_BOOKS.values() if x.startswith("O-")}:
        raise ValidationError("A scheme preset must target an existing CPU offense book")
    if not isinstance(recipe["groups"], list) or not recipe["groups"] or not isinstance(recipe["play_names"], dict):
        raise ValidationError("Preset requires record groups and a play-name census")
    seen = set()
    plays = set()
    for group in recipe["groups"]:
        if not isinstance(group, dict) or set(group) != {"records", "keep", "tags"}:
            raise ValidationError("Unsupported preset group fields")
        keep, tags = group["keep"], group["tags"]
        if (not isinstance(keep, list) or not 4 <= len(keep) <= splb.ENTRY_CAPACITY
                or any(type(x) is not int or not 0 <= x < 586 for x in keep)
                or len(set(keep)) != len(keep)):
            raise ValidationError("Preset membership requires 4..84 unique existing play IDs")
        if (not isinstance(tags, list) or len(tags) != 4
                or any(type(x) is not int for x in tags) or len(set(tags)) != 4 or not set(tags) <= set(keep)):
            raise ValidationError("Preset requires four distinct retained play targets for tags 0..3")
        if not isinstance(group["records"], list) or not group["records"]:
            raise ValidationError("Preset group has no formation records")
        for row in group["records"]:
            if (not isinstance(row, list) or len(row) != 3 or type(row[0]) is not int
                    or not 0 <= row[0] < 176 or type(row[1]) is not int or not 0 <= row[1] < 163
                    or not isinstance(row[2], str) or not row[2] or row[0] in seen):
                raise ValidationError("Preset record IDs must be unique and formations must be named")
            seen.add(row[0])
        plays.update(keep)
    if set(recipe["play_names"]) != {str(x) for x in plays} or any(
            not isinstance(x, str) or not x for x in recipe["play_names"].values()):
        raise ValidationError("Preset play-name census must exactly cover retained play IDs")


def _targets(recipe: dict) -> dict:
    return {row[0]: (row[1], row[2], group["keep"], group["tags"])
            for group in recipe["groups"] for row in group["records"]}


def verify_preset(before: bytes, after: bytes, recipe: dict, outer_index: int) -> dict:
    validate_recipe(recipe)
    original, output = splb.parse_book(before, outer_index), splb.parse_book(after, outer_index)
    targets = _targets(recipe)
    changed_records = []
    allowed = set()
    for index, (formation, name, keep, tags) in sorted(targets.items()):
        a, b = original.records[index], output.records[index]
        before_plays = {x.play_index for x in a.entries}
        if (a.formation_index != formation or b.formation_index != formation
                or not set(keep) <= before_plays or a.trailer != b.trailer):
            raise ValidationError("Preset changed formation/personnel or introduced a play")
        expected = [x.play_index for x in a.entries if x.play_index in keep]
        if [x.play_index for x in b.entries] != expected:
            raise ValidationError("Preset membership failed independent verification")
        if {x.y: x.play_index for x in b.entries if x.tagged} != dict(enumerate(tags)):
            raise ValidationError("Preset audible tags failed independent verification")
        old_x = {x.play_index: x.x for x in a.entries}
        if any(x.x != old_x[x.play_index] or (x.play_index not in tags and x.y != 4) for x in b.entries):
            raise ValidationError("Preset changed opaque entry X bits or untagged Y bits")
        at = splb.RECORD_BASE + index * splb.RECORD_STRIDE
        allowed.update(range(at, at + splb.ENTRY_BYTES))
        if a.entries != b.entries:
            changed_records.append({"record_index": index, "formation_index": formation,
                                    "formation": name, "before_count": len(a.entries), "after_count": len(b.entries),
                                    "removed_play_indices": [x.play_index for x in a.entries if x.play_index not in keep],
                                    "tags_before": {str(x.y): x.play_index for x in a.entries if x.tagged},
                                    "tags_after": {str(x.y): x.play_index for x in b.entries if x.tagged}})
    changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
    if len(before) != len(after) or not changed <= allowed:
        raise ValidationError("Preset changed bytes outside its selected entry regions")
    if any(a.entries and not b.entries for a, b in zip(original.records, output.records)):
        raise ValidationError("Preset emptied a formation")
    return {"changed_records": changed_records, "changed_byte_count": len(changed),
            "records_emptied": [], "formation_and_personnel_bytes_preserved": True,
            "only_existing_plays": True, "new_plays": 0}


def apply_preset(book: splb.SplbBook, recipe: dict, master: dict) -> tuple[bytes, dict]:
    validate_recipe(recipe)
    if book.name != recipe["book_type"]:
        raise ValidationError("Preset targets a different CPU book")
    plays = {x["index"]: x["name"] for x in master["plays"]}
    formations = {x["index"]: x["name"] for x in master["formations"]}
    for key, name in recipe["play_names"].items():
        if plays.get(int(key)) != name:
            raise ValidationError("MASTER play ID/name differs from the authored recipe")
    current = book
    writer_steps = 0
    for index, (formation, name, keep, tags) in sorted(_targets(recipe).items()):
        record = current.records[index]
        if record.formation_index != formation or formations.get(formation) != name:
            raise ValidationError("Book record/MASTER formation differs from the authored recipe")
        if not set(keep) <= {x.play_index for x in record.entries}:
            raise ValidationError("A preset play is missing from this book record")
        if not splb.retail_tag_shape(record.entries):
            raise ValidationError("Preset expects the four valid stock tagged slots")
        for tag, target in enumerate(tags):
            source = next(x.play_index for x in current.records[index].entries if x.y == tag)
            if source != target:
                step = splb.compile_book(current, [splb.TagMove(book.outer_index, index, source, target)])
                current = splb.parse_book(step.replacement, book.outer_index)
                writer_steps += 1
        removals = [splb.MembershipChange(book.outer_index, index, x.play_index, False)
                    for x in current.records[index].entries if x.play_index not in keep]
        if removals:
            step = splb.compile_book(current, removals)
            current = splb.parse_book(step.replacement, book.outer_index)
            writer_steps += 1
    verification = verify_preset(book.body, current.body, recipe, book.outer_index)
    return current.body, {"schema": REPORT_SCHEMA, "preset_id": recipe["id"], "name": recipe["name"],
                          "book_type": recipe["book_type"], "intent": recipe["intent"],
                          "limitations": recipe["limitations"], "writer_steps": writer_steps,
                          "source_sha256": hashlib.sha256(book.body).hexdigest(),
                          "output_sha256": hashlib.sha256(current.body).hexdigest(),
                          "verification": verification, "runtime_status": "UNWITNESSED",
                          "cpu_call_frequency_proved": False, "true_rpo_added": False}


@dataclass(frozen=True)
class CompiledPreset:
    outer_index: int
    entry_bytes: bytes
    replacement: bytes
    report: dict


def compile_preset(index_path: Path, recipe: dict) -> CompiledPreset:
    validate_recipe(recipe)
    source = read_resource(index_path, filename_id(recipe["book_type"]), "spb", "SPLB")
    book = splb.parse_book(source[3], source[1].table_index)
    # MASTER is located by its filename identity, including after clone insertion.
    master_source = read_resource(index_path, zlib.crc32(b"PLAYBOOK_MASTER.IFF"), "mpb", "PLAY")
    master = playbook_inventory.parse_apf_body(master_source[3], master_source[1].table_index, 0)
    replacement, report = apply_preset(book, recipe, master)
    packed, transport = rebuild_resource(source, replacement)
    repeated, repeated_report = apply_preset(splb.parse_book(replacement, book.outer_index), recipe, master)
    if repeated != replacement or repeated_report["verification"]["changed_records"]:
        raise ValidationError("Preset apply is not idempotent")
    report.update({"transport": transport, "idempotent_reapply": True,
                   "book_identity": disc_book_identity_report(index_path)})
    return CompiledPreset(book.outer_index, packed, replacement, report)


def build_presets_folder(index_path: Path, preset_ids: tuple[str, ...], destination: Path,
                         progress=lambda _message: None, *, expected_reports=None) -> dict:
    """Publish selected presets in a new copied game, with a full byte gate."""
    if not preset_ids or len(set(preset_ids)) != len(preset_ids):
        raise ValidationError("Select distinct scheme presets")
    index_path = Path(index_path).resolve()
    if Path(destination).is_symlink():
        raise ValidationError("Output directory must not be a symlink")
    destination = Path(destination).resolve()
    if (destination == index_path.parent or destination in index_path.parent.parents
            or index_path.parent in destination.parents):
        raise ValidationError("Choose a separate new output directory outside the source game")
    recipes = [load_preset(x) for x in preset_ids]
    compiled = [compile_preset(index_path, recipe) for recipe in recipes]
    if expected_reports is not None and [x.report for x in compiled] != list(expected_reports):
        raise ValidationError("Preset inputs changed since review; review the selection again")
    archive = apf_outer.parse_archive(index_path)
    destination.mkdir(parents=False, exist_ok=False)
    try:
        for pack in archive.packs:
            progress(f"Copying {pack.name}")
            shutil.copyfile(pack.path, destination / pack.name)
        xex = index_path.parent / "default.xex"
        if xex.is_file():
            shutil.copyfile(xex, destination / xex.name)
        allowed = []
        for result in compiled:
            entry = archive.entries[result.outer_index]
            cursor = 0
            for segment in entry.segments:
                with (destination / segment.pack_name).open("r+b") as stream:
                    stream.seek(segment.pack_offset)
                    stream.write(result.entry_bytes[cursor:cursor + segment.size])
                cursor += segment.size
            allowed.append((entry.virtual_offset, entry.virtual_end))
        progress("Verifying every copied pack byte and each preset record")
        output_index = destination / index_path.name
        output_archive = apf_outer.parse_archive(output_index)
        if [(x.name_id, x.virtual_offset, x.size) for x in archive.entries] != [
                (x.name_id, x.virtual_offset, x.size) for x in output_archive.entries]:
            raise ValidationError("Preset changed the archive directory")
        for recipe, result in zip(recipes, compiled):
            output = read_resource(output_index, filename_id(recipe["book_type"]), "spb", "SPLB")
            source = read_resource(index_path, filename_id(recipe["book_type"]), "spb", "SPLB")
            if hashlib.sha256(source[3]).hexdigest() != result.report["source_sha256"]:
                raise ValidationError("Preset source changed after compilation")
            verify_preset(source[3], output[3], recipe, result.outer_index)
            if output[5] != result.entry_bytes:
                raise ValidationError("Published preset differs from its verified transport")
        compared = compare_untouched_packs(archive, output_archive, allowed)
        receipt = {"schema": "apf2k8_scheme_preset_build/v1", "presets": [x.report for x in compiled],
                   "untouched_pack_bytes_compared": compared,
                   "executable": compare_executable(index_path.parent, destination),
                   "book_identity": disc_book_identity_report(output_index), "runtime_status": "UNWITNESSED"}
        (destination / "scheme-preset-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return receipt
    except BaseException:
        shutil.rmtree(destination)
        raise

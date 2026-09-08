"""Standalone final-book pairing and refusal proofs; bounded retail PLAY reads."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_play_intents as intents
from mod_editor.core import nfl2k5_playbook_pack as packs
from mod_editor.core import nfl2k5_play_library as library
from mod_editor.core import nfl2k5_depth_roles as roles
from mod_editor.core import nfl2k5_formation_play_writer as writer
from mod_editor.core import nfl2k5_read_option_runtime as read
from mod_editor.core import nfl2k5_qb_spy_runtime as spy
from mod_editor.core.errors import ValidationError

EXTRACT = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                             "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)"


class BookArchive:
    """Real fixed-size resources, bounded transport; no image or pack fixture."""
    def __init__(self, resources):
        recode = packs._outer_image()
        self.resources = {recode.BOOK_ENTRIES[team]: raw for team, raw in resources.items()}
        self.entries = [SimpleNamespace(index=i, size=0, virtual_offset=i * packs.RESOURCE_SIZE)
                        for i in range(max(recode.BOOK_ENTRIES.values()) + 1)]
        for i in self.resources:
            self.entries[i].size = packs.RESOURCE_SIZE
        self.reads = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def read_entry(self, index):
        self.reads.append(index)
        return self.resources[index]

    def entries_with_head(self, head):
        return [self.entries[i] for i, raw in self.resources.items() if raw.startswith(head)]

    def read(self, offset, size):
        index, inside = divmod(offset, packs.RESOURCE_SIZE)
        return self.resources[index][inside:inside + size]

    def write(self, offset, content):
        index, inside = divmod(offset, packs.RESOURCE_SIZE)
        raw = self.resources[index]
        self.resources[index] = raw[:inside] + content + raw[inside + len(content):]
        return len(content)


def pool_resource(resource):
    recode = packs._outer_image()
    book = packs.parse_playbook_resource(resource)
    body = resource[32:]
    return writer.compile_personnel_categories(resource, {
        cat.index: recode.recode_codes(library.category_positions(body, cat.index),
            body[roles.insp.CATEGORY_BASE + cat.index * roles.insp.CATEGORY_SIZE + 4])[0]
        for cat in book.categories})


def resolve(resources, pairs, progress=None):
    archive = BookArchive(resources)
    with patch.object(packs._outer_image(), "OuterImage", return_value=archive) as opened:
        result = intents.resolve_final_pairs("bounded PLAY archive", pairs, progress)
    return result, archive, opened


def clone_to(resource, donor, target):
    return writer.compile_formation_play_creations(resource, play_requests=[
        writer.PlayCreateRequest("book:MIN", donor, replace_index=target)]).replacement


class EmptyTests(unittest.TestCase):
    def test_empty_does_not_open_image(self):
        with patch.object(packs._outer_image(), "OuterImage", side_effect=AssertionError("opened")):
            self.assertEqual(intents.resolve_final_pairs("absent", []), [])
        self.assertEqual(intents.resolution_receipt([])["resolved_plays"], 0)

    def test_legacy_table_input_errors_remain_typed(self):
        for runtime in (read, spy):
            with self.subTest(runtime=runtime.__name__), self.assertRaises(ValueError):
                runtime.compile_intent_table([(b"", None)])


class FinalPairsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (EXTRACT / "vc_53450030/0").is_file():
            raise unittest.SkipTest("retail extracted PLAY archive absent; set NFL2K5_RETAIL_EXTRACTION")
        recode = packs._outer_image()
        with recode.OuterImage(EXTRACT) as archive:
            cls.raw = {team: archive.read_entry(recode.BOOK_ENTRIES[team]) for team in ("MIN", "ATL")}
        cls.option = packs.apply_pack_to_resource(cls.raw["MIN"],
            packs.load_pack(ROOT / "data/playbooks/softdrink_option.2k5book"), asset_id="book:MIN")
        requests = [r for r in intents.intent_requests(cls.option.replacement, cls.option.report)
                    if r.option_intent["preset"] != library.OPTION_PRESETS[0]]
        cls.reads = writer.compile_formation_play_creations(cls.option.replacement,
            play_requests=requests, allow_unchanged=True)
        raw = cls.raw["ATL"]
        book = packs.parse_playbook_resource(raw, asset_id="book:ATL")
        donor, fallback = library.spy_fallback(book, raw[32:], 23, 5, 4)
        cls.defense = writer.compile_formation_play_creations(raw, play_requests=[
            writer.PlayCreateRequest("book:ATL", donor, "SD QB Spy",
                assignments=tuple(tuple((op, tuple(v)) for op, v in fallback) if s == 5 else None
                                  for s in range(11)), spy_slots=(5,))],
            link_requests=[writer.FormationLinkRequest("book:ATL", 23, len(book.plays), 3)])
        cls.option_pair = (cls.option.replacement, cls.option.report)
        cls.read_pair = (cls.reads.replacement, cls.reads.report)
        cls.spy_pair = (cls.defense.replacement, cls.defense.report)
        cls.final = roles.normalise(pool_resource(cls.option.replacement)).replacement

    def test_real_depth_writer_preserves_every_read_descriptor_and_node(self):
        before = pool_resource(self.option.replacement)
        archive = BookArchive({"MIN": before})
        receipt = roles.apply_to_archive(archive, allow_custom=True)
        after = archive.read_entry(packs._outer_image().BOOK_ENTRIES["MIN"])
        self.assertEqual(after, self.final)
        self.assertEqual(receipt["changed_bytes"], 12)
        for pi in (155, 157):
            self.assertEqual(library.play_chains(before[32:], pi), library.play_chains(after[32:], pi))

    def test_all_supported_personnel_passes_and_exact_table_identity(self):
        source_table = read.compile_intent_table([self.option_pair])[0]
        variants = ((self.option.replacement, []),
                    (roles.normalise(self.option.replacement).replacement, ["depth_roles"]),
                    (pool_resource(self.option.replacement), ["position_pools"]),
                    (self.final, ["position_pools", "depth_roles"]))
        for final, passes in variants:
            with self.subTest(passes=passes):
                messages = []
                pairs, archive, opened = resolve({"MIN": final}, [self.option_pair], messages.append)
                self.assertEqual(len(archive.reads), 1)
                self.assertTrue(archive.closed)
                opened.assert_called_once_with("bounded PLAY archive")
                self.assertIn("8 authored plays", messages[0])
                self.assertEqual(pairs[0][0], final)
                self.assertEqual(pairs[0][1]["personnel_transforms"], passes)
                table, receipt = read.compile_intent_table(pairs)
                self.assertEqual(table, source_table)
                self.assertEqual(receipt["count"], 2)
                self.assertEqual({r["resource_sha256"] for r in receipt["records"]},
                                 {hashlib.sha256(final).hexdigest()})
                self.assertEqual(intents.resolution_receipt(pairs)["resolved_plays"], 8)

    def test_final_report_json_round_trip_replay_and_input_immutability(self):
        retained = copy.deepcopy([self.option_pair])
        snapshot = copy.deepcopy(retained)
        pairs, _, _ = resolve({"MIN": self.final}, retained)
        self.assertEqual(retained, snapshot)
        round_trip = [(pairs[0][0], json.loads(json.dumps(pairs[0][1])))]
        self.assertEqual(read.compile_intent_table(round_trip), read.compile_intent_table(pairs))
        again, _, _ = resolve({"MIN": self.final}, round_trip)
        self.assertEqual(read.compile_intent_table(again), read.compile_intent_table(pairs))

    def test_native_validator_is_not_relaxed_for_a_recoded_source(self):
        with self.assertRaisesRegex(ValidationError, "recoded"):
            writer.compile_formation_play_creations(self.final,
                play_requests=intents.intent_requests(*self.read_pair), allow_unchanged=True)

    def test_min_shotgun_reads_survive_pool_and_depth_roles(self):
        raw = self.raw["MIN"]
        book = packs.parse_playbook_resource(raw, asset_id="book:MIN")
        formation = next(f for f in book.formations if f.name == "Gun: Doubles Right")
        requests = []
        for preset, pi, name in zip(library.OPTION_PRESETS[1:], (134, 31),
                                    ("SD Gun Zone Read", "SD Gun RPO Slant")):
            design = library.make_option_design(book, raw[32:], formation.index, preset,
                opponent_formation_index=28, read_slot=2, receiver_slot=7)
            requests.append(writer.PlayCreateRequest("book:MIN", design.donor_play_index,
                name, assignments=design.chains, replace_index=pi, play_flags=design.play_flags,
                option_intent=design.intent))
        compiled = writer.compile_formation_play_creations(raw, play_requests=requests)
        final = roles.normalise(pool_resource(compiled.replacement)).replacement
        pairs, _, _ = resolve({"MIN": final}, [(compiled.replacement, compiled.report)])
        table, receipt = read.compile_intent_table(pairs)
        self.assertEqual(receipt["count"], 2)
        self.assertEqual(table, read.compile_intent_table([(compiled.replacement, compiled.report)])[0])
        self.assertEqual(set(pairs[0][1]["resolved_names"]), {"SD Gun Zone Read", "SD Gun RPO Slant"})

    def test_spy_and_read_compilers_accept_final_books_together(self):
        defense = roles.normalise(pool_resource(self.defense.replacement)).replacement
        pairs, _, _ = resolve({"MIN": self.final, "ATL": defense}, [self.option_pair, self.spy_pair])
        self.assertEqual([r["asset_id"] for _, r in pairs], ["book:ATL", "book:MIN"])
        for runtime, count in ((read, 2), (spy, 1)):
            table, receipt = runtime.compile_intent_table(pairs)
            self.assertEqual(receipt["count"], count)
            self.assertEqual(table, runtime.compile_intent_table([self.option_pair, self.spy_pair])[0])

    def test_unrelated_later_play_edit_is_allowed(self):
        final = writer.compile_formation_play_creations(self.final,
            play_requests=[writer.PlayCreateRequest("book:MIN", 24, "Unrelated play", replace_index=24)]).replacement
        pairs, _, _ = resolve({"MIN": final}, [self.read_pair])
        self.assertEqual(read.compile_intent_table(pairs)[0], read.compile_intent_table([self.read_pair])[0])

    def test_multiple_retained_compilations_for_one_team_merge(self):
        separate = []
        for request in intents.intent_requests(*self.read_pair):
            c = writer.compile_formation_play_creations(self.reads.replacement,
                play_requests=[request], allow_unchanged=True)
            separate.append((c.replacement, c.report))
        pairs, archive, _ = resolve({"MIN": self.final}, separate)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(len(archive.reads), 1)
        self.assertEqual(read.compile_intent_table(pairs)[1]["count"], 2)

    def test_unique_name_relocates_slot_and_compiles_final_index(self):
        moved = clone_to(self.final, 155, 156)
        moved = clone_to(moved, 24, 155)
        pairs, _, _ = resolve({"MIN": moved}, [self.read_pair])
        self.assertEqual({r["play_index"] for r in read.compile_intent_table(pairs)[1]["records"]}, {156, 157})
        self.assertEqual(pairs[0][1]["resolved_names"], ["SD Zone Read EXPERIMENTAL", "SD RPO EXPERIMENTAL"])

    def test_v5_rejects_duplicate_live_fingerprint_even_when_original_slot_matches(self):
        duplicate = clone_to(self.final, 155, 48)
        pairs, _, _ = resolve({"MIN": duplicate}, [self.read_pair])
        with self.assertRaisesRegex(intents.PlayIntentError, 'ambiguous loaded read fingerprint'):
            read.compile_intent_table(pairs)

    def test_v5_receipt_certifies_every_final_play_and_names_display_index(self):
        pairs, _, _ = resolve({"MIN": self.final}, [self.read_pair])
        _, receipt = read.compile_intent_table(pairs)
        self.assertEqual(receipt['identity_model'], 'loaded_team_book_fingerprints/v5')
        self.assertEqual(receipt['diagnostic_index'], 'final_resource_index')
        for row in receipt['records']:
            self.assertEqual(row['identity_matches'], [row['play_index']])
            self.assertEqual(row['diagnostic_index'], row['play_index'])
            self.assertGreater(row['plays_checked'], row['play_index'])

    def test_missing_renamed_and_ambiguous_plays_refuse(self):
        missing = clone_to(self.final, 24, 155)
        duplicate = clone_to(self.final, 155, 156)
        duplicate = clone_to(duplicate, 155, 160)
        duplicate = clone_to(duplicate, 24, 155)
        for final, reason in ((missing, "missing or renamed"), (duplicate, "ambiguous")):
            with self.subTest(reason=reason), self.assertRaisesRegex(intents.PlayIntentError,
                    "book:MIN: play 155 'SD Zone Read EXPERIMENTAL'.*" + reason):
                resolve({"MIN": final}, [self.read_pair])

    def test_all_assignment_descriptors_and_nodes_are_pinned(self):
        # Include the RPO receiver, not just the QB and back runtime hashes.
        for pi, slot in ((155, 0), (155, 10), (157, 7)):
            descriptor = 32 + 0x3404 + pi * 96 + slot * 8
            pointer = descriptor + 4
            node = pointer + struct.unpack_from("<i", self.final, pointer)[0] - 1
            for offset, reason in ((descriptor + 3, "descriptor"), (node + 2, "nodes")):
                final = bytearray(self.final)
                final[offset] ^= 1
                with self.subTest(pi=pi, slot=slot, reason=reason), self.assertRaisesRegex(
                        intents.PlayIntentError, f"book:MIN: play {pi} .*assignment {slot} {reason} changed"):
                    resolve({"MIN": bytes(final)}, [self.read_pair])

    def test_spy_descriptor_and_two_nodes_are_pinned(self):
        final = roles.normalise(pool_resource(self.defense.replacement)).replacement
        pi = self.defense.report["spy_intent"]["records"][0]["play_index"]
        descriptor = 32 + 0x3404 + pi * 96 + 5 * 8
        pointer = descriptor + 4
        node = pointer + struct.unpack_from("<i", final, pointer)[0] - 1
        for offset, reason in ((descriptor + 3, "descriptor"), (node + 8 + 6, "nodes")):
            changed = bytearray(final)
            changed[offset] ^= 1
            with self.assertRaisesRegex(intents.PlayIntentError, f"book:ATL: play {pi} .*assignment 5 {reason} changed"):
                resolve({"ATL": bytes(changed)}, [self.spy_pair])

    def test_unknown_personnel_pass_and_changed_opponent_geometry_refuse(self):
        category = library.formation_category(self.final[32:], 28)
        codes = library.category_positions(self.final[32:], category)
        codes[1] ^= 32
        changed = writer.compile_personnel_categories(self.final, {category: codes})
        with self.assertRaisesRegex(intents.PlayIntentError, "book:MIN: plays.*Personnel groups.*outside"):
            resolve({"MIN": changed}, [self.read_pair])
        record = library.formation_record(self.final[32:], 28)
        record.set_position(1, record.slots[1].x[0] + 10, record.slots[1].z[0])
        changed = bytearray(self.final)
        offset = 32 + roles.insp.FORMATION_BASE + 28 * roles.insp.FORMATION_SIZE
        changed[offset:offset + roles.insp.FORMATION_SIZE] = record.to_bytes()
        with self.assertRaisesRegex(intents.PlayIntentError, "book:MIN: plays.*signature mismatch"):
            resolve({"MIN": bytes(changed)}, [self.read_pair])

    def test_stale_malformed_and_duplicate_retained_pairs_refuse(self):
        for edit, message in ((lambda r: r.update(replacement_sha256="0" * 64), "pairing"),
                (lambda r: r.update(asset_id="MIN"), "asset id"),
                (lambda r: r.update(schema="foreign"), "schema"),
                (lambda r: r.update(new_play_indices=None), "resolved play indices"),
                (lambda r: r["option_intent"].update(schema="foreign"), "versioned"),
                (lambda r: r["option_intent"]["records"][0].update(play_index=True), "play index")):
            report = copy.deepcopy(self.reads.report)
            edit(report)
            with self.subTest(message=message), self.assertRaisesRegex(intents.PlayIntentError, message):
                resolve({"MIN": self.final}, [(self.reads.replacement, report)])
        with self.assertRaisesRegex(intents.PlayIntentError, "duplicate retained authored play"):
            resolve({"MIN": self.final}, [self.read_pair] * 2)

    def test_final_report_cannot_hide_changed_bytes_behind_a_new_hash(self):
        pairs, _, _ = resolve({"MIN": self.final}, [self.read_pair])
        for runtime in (read, spy):
            for key in ("replacement_sha256", "resolved_names", "native_compiler_report", "personnel_transforms"):
                report = copy.deepcopy(pairs[0][1])
                report[key] = "forged"
                with self.subTest(runtime=runtime.__name__, key=key), self.assertRaises(ValidationError):
                    runtime.compile_intent_table([(self.final, report)])
            changed = clone_to(self.final, 24, 155)
            report = copy.deepcopy(pairs[0][1])
            report["replacement_sha256"] = hashlib.sha256(changed).hexdigest()
            with self.assertRaises((ValidationError, ValueError)):
                runtime.compile_intent_table([(changed, report)])

    def test_non_intent_pair_does_not_reach_archive(self):
        compiled = writer.compile_formation_play_creations(self.raw["MIN"],
            play_requests=[writer.PlayCreateRequest("book:MIN", 0, "Unpaired", replace_index=0)])
        _, _, opened = resolve({}, [(compiled.replacement, compiled.report)])
        opened.assert_not_called()


if __name__ == "__main__":
    unittest.main()

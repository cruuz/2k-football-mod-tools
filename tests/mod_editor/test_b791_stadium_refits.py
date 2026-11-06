"""b791: a stadium refit never stops a build, and a refusal always says why.

Coach Edwards' beta-79 builds (13,340 texture edits, nearly every stadium option, custom colour levers) stopped four to
five hours in on "Couldn't make the disc. cannot keep the retail scratch word:" with nothing after the colon, twice.
Modern colour's fit_fixed_span recorded nothing when the retail decoder model refused a candidate. The one stream shape
that passes the padding and in-place overlap checks and still fails that model fills its slot to the last byte and ends
on a full group of eight tokens: the decoder at 0x4dc00 fetches one more flag byte from past its allocation. The four
candidates are near duplicates (the two fills share their first phase; greedy and optimal parses can coincide), so all
four could fail together.

Covered here: every candidate's reason; the rescue candidates (a fill stopping short, the full fill with its last
group's parity shifted, another offset width) on seed-reproducible synthetic spans, and against the retail decoder
itself under Unicorn; the three callers that used to stop the build (Modern Arrowhead with Modern colour, Modern
surfaces' divots and Washington loan, the practice field's divots) keeping their bytes with one plain line each; the
receipts and read-back staying applied; and mod_build carrying the lines into the build log and the receipt.
"""
from __future__ import annotations

import hashlib
import os
import random
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests"), str(Path(__file__).parent)]
import nfl_txtr as tx  # noqa: E402
import nfl_vc_lz_fill as fill  # noqa: E402
from mod_editor.core import nfl2k5_modern_color as colour  # noqa: E402
from mod_editor.core import nfl2k5_modern_surfaces as ms  # noqa: E402

GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
PACKS = GAME / "vc_53450030"
XBE = Path(os.environ.get("NFL2K5_RETAIL_XBE", str(GAME / "default.xbe")))
RETAIL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
BLANK = "cannot keep the retail scratch word: "

#: (seed, decoded size, offset bits, stored size, scratch word) of synthetic spans whose four standard candidates all
#: end on the last byte with a full final group (the decoder model refuses each for its final flag fetch), found by a
#: search over this generator; each is fitted by a different rescue route, or (``none``) by nothing at all.
CASES = {"shift": (31, 1346, 10, 279, 0), "short": (1, 1512, 10, 251, 16), "width": (16, 1516, 11, 271, 16),
         "none": (17, 1411, 10, 279, 0)}


def synthetic(seed, n):
    """Repeating motifs with a little noise: decoded bytes that compress like a small texture."""
    rng = random.Random(seed)
    motifs = [bytes(rng.randrange(256) for _ in range(rng.randrange(3, 24))) for _ in range(rng.randrange(2, 9))]
    out = bytearray()
    while len(out) < n:
        out += bytes(rng.randrange(256) for _ in range(rng.randrange(1, 6))) if rng.random() < 0.18 else rng.choice(motifs)
    return bytes(out[:n])


def span_for(n, bits, stored, scratch):
    """A compressed TXTR fixed span (wrapper and stream prefix; the old body is never read by the fitter)."""
    return (tx.HEADER.pack(b"TXTR", stored, 0, n, tx.COMPRESSED_SENTINEL, scratch, 0, 0)
            + struct.pack("<IIB", n, 3, bits) + bytes(stored - 9))


def case(name):
    seed, n, bits, stored, scratch = CASES[name]
    return synthetic(seed, n), span_for(n, bits, stored, scratch)


def blank_fitter(span, decoded, **_kwargs):
    """The exact error Coach Edwards saw: the fitter refusing with nothing after the colon."""
    raise tx.TxtrError(BLANK)


def _tokens(stream):
    return fill.parse_tokens(stream)[3]


class FitterReasons(unittest.TestCase):
    """fit_fixed_span names every candidate, and rescue fits what can be fitted."""

    def test_the_old_blank_refusal_now_names_every_candidate_and_the_decoder_reason(self):
        for name in CASES:
            decoded, span = case(name)
            with self.subTest(name):
                with self.assertRaises(tx.TxtrError) as caught:
                    colour.fit_fixed_span(span, decoded)
                message = str(caught.exception)
                self.assertTrue(message.startswith(BLANK))
                self.assertNotEqual(message.strip()[-1], ":", "a refusal never ends on an empty list")
                for label in ("greedy/trailing", "greedy/front", "optimal/trailing", "optimal/front"):
                    self.assertIn(label, message)
                self.assertIn("refused by the decoder check", message)
                self.assertIn(colour.FINAL_FETCH_REASON, message)

    def test_the_other_copies_of_the_fitter_name_decoder_refusals_too(self):
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from mod_editor.core import nfl2k5_usbank_model as um
        from mod_editor.core import nfl2k5_scne_builder as sb
        decoded, span = case("none")
        with self.assertRaises(sb.ScneBuildError) as caught:
            um.fit_keep_scratch(decoded, 0, len(decoded), span)
        self.assertIn("refused by the decoder check", str(caught.exception))
        self.assertNotEqual(str(caught.exception).strip()[-1], ":")
        with self.assertRaises(tx.TxtrError) as caught:
            ml.fit_span(span, decoded)
        message = str(caught.exception)
        self.assertIn("full fill: greedy/full fill: padding 0", message)
        self.assertIn("refused by the decoder check", message.split("; colour fitter:")[0])

    def test_each_rescue_route_fits_inside_the_retail_wrapper(self):
        expected = {"shift": "shifted", "short": "short", "width": None}
        for name, route in expected.items():
            decoded, span = case(name)
            seed, n, bits, stored, scratch = CASES[name]
            with self.subTest(name):
                rebuilt, info = colour.fit_fixed_span(span, decoded, rescue=True)
                self.assertTrue(info["rescue"])
                self.assertEqual((len(rebuilt), rebuilt[:32]), (len(span), span[:32]), "same size, wrapper byte-identical")
                if route:
                    self.assertIn(route, info["fill"])
                else:
                    self.assertIn("offset_bits", info)
                    self.assertNotEqual(info["offset_bits"], bits)
                self.assertLessEqual(info["padding_bytes"], scratch)
                self.assertLessEqual(info["alias_scratch"], scratch)
                tx.check_vc_lz_native(rebuilt[32:], stored, scratch, decoded)
                back, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt)[0])
                self.assertEqual(back, decoded)

    def test_a_span_with_no_room_at_all_stays_a_named_refusal(self):
        decoded, span = case("none")
        with self.assertRaises(tx.TxtrError) as caught:
            colour.fit_fixed_span(span, decoded, rescue=True)
        message = str(caught.exception)
        self.assertIn("full fill", message)
        self.assertIn("-bit", message, "the other offset widths were tried and named")

    def test_spans_the_standard_candidates_fit_keep_their_exact_bytes(self):
        for seed in (3, 5, 8, 13):
            decoded = synthetic(seed, 1200)
            greedy = tx.compress_vc_lz(decoded, stream_tag=3, offset_bits=11)[0]
            for extra, scratch in ((40, 16), (3, 16), (60, 128), (25, 0)):
                span = span_for(len(decoded), 11, len(greedy) + extra, scratch)
                try:
                    plain = colour.fit_fixed_span(span, decoded)
                except tx.TxtrError:
                    continue
                with self.subTest(seed=seed, extra=extra, scratch=scratch):
                    self.assertEqual(colour.fit_fixed_span(span, decoded, rescue=True), plain)

    def test_the_parity_shift_keeps_length_bytes_and_match_rules(self):
        decoded, span = case("shift")
        seed, n, bits, stored, scratch = CASES["shift"]
        encoded = tx.compress_vc_lz(decoded, stream_tag=3, offset_bits=bits)[0]
        full = fill.fill_stream(encoded, decoded, stored, slack=0)[0]
        self.assertEqual((len(full), len(_tokens(full)) % 8), (stored, 0), "the final-fetch shape")
        shifted = list(colour.shift_final_group(full, decoded))
        self.assertTrue(shifted)
        for stream in shifted:
            tokens = _tokens(stream)
            self.assertEqual(len(stream), len(full))
            self.assertEqual(len(tokens) % 8, 7, "the last group holds seven tokens: no extra flag fetch")
            self.assertEqual(tx.decompress_vc_lz(stream, n)[0], decoded)
            self.assertTrue(all(t[2] <= t[1] for t in tokens if t[0] == "M"), "no match longer than its distance")
        self.assertEqual(list(colour.shift_final_group(shifted[0], decoded)), [], "a stream that ends early is left alone")

    def test_the_final_fetch_is_the_only_extra_refusal_of_the_decoder_model(self):
        # Every stream the fitters make passes the overlap check first; of those, the model refuses exactly the ones
        # that end on the last byte with a full final group.
        rng = random.Random(791)
        refused = 0
        for _ in range(40):
            decoded = synthetic(rng.randrange(10 ** 6), rng.randrange(300, 900))
            bits = rng.choice((10, 11, 12))
            encoded = tx.compress_vc_lz(decoded, stream_tag=3, offset_bits=bits)[0]
            for scratch in (0, 16):
                stored = len(encoded) + rng.randrange(0, 24)
                if stored > len(decoded) + scratch:
                    continue
                for slack in (0, 1, 16):
                    if slack > max(scratch, 0) and slack:
                        continue
                    stream = fill.fill_stream(encoded, decoded, stored, slack=slack)[0]
                    padding = stored - len(stream)
                    if padding > scratch or tx.minimum_vc_lz_overlap_scratch(stream, stored, len(decoded)) > scratch:
                        continue
                    final_fetch = padding == 0 and len(_tokens(stream)) % 8 == 0
                    try:
                        tx.check_vc_lz_native(stream + bytes(padding), stored, scratch, decoded)
                        accepted = True
                    except tx.TxtrError as exc:
                        accepted = False
                        self.assertIn("read outside allocation", str(exc))
                    self.assertEqual(accepted, not final_fetch, (stored, scratch, slack, padding))
                    refused += not accepted
        self.assertGreater(refused, 0, "the sample reached the final-fetch shape")


try:
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_MEM_READ
    from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESP
except ImportError:
    Uc = None


@unittest.skipUnless(Uc is not None and XBE.is_file(), "Unicorn or the private retail default.xbe is absent")
class RetailDecoder(unittest.TestCase):
    """The retail decoder (default.xbe 0x4dc00) in the loader's in-place layout agrees with the model, refuses the
    final-fetch shape by reading past its allocation, and decodes every rescued span exactly."""

    STOP = 0x301F000

    @classmethod
    def setUpClass(cls):
        if not 0 < XBE.stat().st_size <= 16 * 1024 * 1024:
            raise AssertionError("the decoder proof needs a bounded retail executable")
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_XBE_SHA256:
            raise unittest.SkipTest("not the pinned retail executable")
        cls.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0x10000, 0x1600000)
        base = struct.unpack_from("<I", retail, 0x104)[0]
        count, table = struct.unpack_from("<II", retail, 0x11C)
        for i in range(count):
            _flags, va, _size, raw, rawsize = struct.unpack_from("<5I", retail, table - base + i * 0x38)
            if rawsize:
                uc.mem_write(va, retail[raw:raw + rawsize])
        uc.mem_map(0x2000000, 0x400000)
        uc.mem_map(0x3000000, 0x20000)
        cls.window = dict(lo=0, hi=0, outside=[])

        def on_read(_uc, _access, address, size, _value, _data):
            if 0x2000000 <= address < 0x2400000 and not (cls.window["lo"] <= address and address + size <= cls.window["hi"]):
                cls.window["outside"].append(address)
        uc.hook_add(UC_HOOK_MEM_READ, on_read)

    def decode(self, body, stored, scratch, expected):
        """(accepted, why): exact output and no read outside [destination, destination + size + scratch)."""
        uc, size, dest = self.uc, len(expected), 0x2100000
        end = dest + size + scratch
        source = end - stored
        uc.mem_write(0x2000000, b"\xEE" * 0x400000)
        uc.mem_write(source, body)
        self.window.update(lo=min(dest, source), hi=end, outside=[])
        uc.mem_write(0x3010000, struct.pack("<I", self.STOP))
        uc.reg_write(UC_X86_REG_ESP, 0x3010000)
        uc.reg_write(UC_X86_REG_ECX, source)
        uc.reg_write(UC_X86_REG_EDX, dest)
        uc.emu_start(0x4DC00, self.STOP, timeout=20_000_000, count=20_000_000)
        self.assertEqual(uc.reg_read(UC_X86_REG_EIP), self.STOP, "the decoder returned")
        if self.window["outside"]:
            return False, f"read {self.window['outside'][0] - end} bytes past its allocation"
        return bytes(uc.mem_read(dest, size)) == expected, "decoded"

    def model(self, body, stored, scratch, expected):
        try:
            tx.check_vc_lz_native(body, stored, scratch, expected)
            return True
        except tx.TxtrError:
            return False

    def test_the_cases_standard_streams_overread_and_their_rescues_decode(self):
        for name in ("shift", "short", "width"):
            decoded, span = case(name)
            seed, n, bits, stored, scratch = CASES[name]
            with self.subTest(name):
                encoded = tx.compress_vc_lz(decoded, stream_tag=3, offset_bits=bits)[0]
                standard = fill.fill_stream(encoded, decoded, stored, slack=min(scratch, 16))[0] \
                    if stored - len(encoded) > scratch else encoded
                self.assertEqual(len(standard), stored)
                accepted, why = self.decode(standard, stored, scratch, decoded)
                self.assertFalse(accepted)
                self.assertIn("past its allocation", why)
                rebuilt, _info = colour.fit_fixed_span(span, decoded, rescue=True)
                self.assertEqual(self.decode(rebuilt[32:], stored, scratch, decoded), (True, "decoded"))

    def test_model_and_retail_decoder_agree_on_every_candidate(self):
        rng = random.Random(20261102)
        checked = overreads = 0
        for _ in range(12):
            seed, n, bits = rng.randrange(10 ** 6), rng.randrange(400, 1100), rng.choice((10, 11, 12))
            decoded = synthetic(seed, n)
            encoded = tx.compress_vc_lz(decoded, stream_tag=3, offset_bits=bits)[0]
            for scratch in (0, 16, 64):
                stored = rng.randrange(len(encoded), len(encoded) + 24)
                if stored > n + scratch:
                    continue
                streams = []
                for stream in (encoded, fill.compress_optimal(decoded, stream_tag=3, offset_bits=bits)):
                    if len(stream) > stored:
                        continue
                    streams += [stream, fill.fill_stream(stream, decoded, stored, slack=0)[0],
                                fill.fill_stream(stream, decoded, stored, slack=min(scratch, 16))[0]]
                    streams += [s for _label, s in colour._rescue_streams(stream, decoded, stored, scratch)]
                for stream in streams:
                    padding = stored - len(stream)
                    if padding > scratch or tx.minimum_vc_lz_overlap_scratch(stream, stored, n) > scratch:
                        continue
                    body = stream + bytes(padding)
                    accepted, why = self.decode(body, stored, scratch, decoded)
                    self.assertEqual(self.model(body, stored, scratch, decoded), accepted, (seed, stored, scratch, why))
                    checked += 1
                    overreads += "past its allocation" in why
                try:
                    rebuilt, _info = colour.fit_fixed_span(span_for(n, bits, stored, scratch), decoded, rescue=True)
                except tx.TxtrError:
                    continue
                self.assertEqual(self.decode(rebuilt[32:], stored, scratch, decoded), (True, "decoded"))
        self.assertGreater(checked, 50)
        self.assertGreater(overreads, 0)


class _Entry:
    def __init__(self, size, offset=0, name_id=0):
        self.virtual_offset, self.size, self.name_id = offset, size, name_id


class _Archive:
    def __init__(self, data):
        self.data = bytes(data)

    def read(self, offset, size):
        return self.data[offset:offset + size]


class _MemoryImage:
    """An outer archive in memory: bundles at fixed spacing, readable and writable through the opener protocol."""
    SPACING = 1 << 22

    def __init__(self, bundles):
        self.names = list(bundles)
        self.store = {i: bytearray(data) for i, data in enumerate(bundles.values())}
        self.entries = [_Entry(len(data), i * self.SPACING) for i, data in enumerate(bundles.values())]

    def by_name(self):
        return {name: self.entries[i] for i, name in enumerate(self.names)}

    def opener(self, _path, writable=False):
        image = self

        class _Open:
            entries = image.entries

            def __enter__(self_):
                return self_

            def __exit__(self_, *exc):
                return False

            def read(self_, offset, size):
                index, at = divmod(offset, image.SPACING)
                return bytes(image.store[index][at:at + size])

            def write(self_, offset, data):
                assert writable, "the image was opened read-only"
                index, at = divmod(offset, image.SPACING)
                image.store[index][at:at + len(data)] = data
                return len(data)
        return _Open()


class SurfacesStep(unittest.TestCase):
    """Modern surfaces' build step with one bundle that cannot be surfaced: the other 287 are written, the kept one
    keeps its bytes, its receipt row says why, one plain line is returned, and the read-back is applied."""

    def run_step(self, failing):
        bundles = {name: bytes([i % 251]) * 64 + name.encode() for i, name in enumerate(ms.HOME_BUNDLES)}
        image = _MemoryImage(bundles)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        target = Path(folder.name) / "lab.iso"
        real_report, calls = ms.image_report, []

        def report(source, *, deep=False):
            calls.append(source)
            if len(calls) == 1:      # the step's own preflight: these synthetic bundles stand for unsurfaced ones
                return dict(state="retail", receipt=False, deep=deep, counts={}, bundles={})
            return real_report(source, deep=deep)

        def surface(data, name, *, indoor, colour_settings=None, overrides=None, **_options):
            if name == failing or (isinstance(failing, (set, frozenset)) and name in failing):
                raise tx.TxtrError(BLANK)
            out = b"S" + bytes(data[1:])
            return out, dict(look="grass_bermuda", light="day", rig="day", normal="full", detail_strength=0.2,
                             field=dict(palette_cap=256), edits=[dict(kind="field", offset=0, size=1,
                                                                      before=ms.sha(data[:1]), after=ms.sha(out[:1]))])
        patches = (mock.patch.object(ms, "_outer_image", lambda: image.opener),
                   mock.patch.object(ms, "home_entries", lambda archive: image.by_name()),
                   mock.patch.object(ms, "indoor_flags", lambda archive: {p: False for p in ms.HOME_PREFIXES}),
                   mock.patch.object(ms, "image_report", report),
                   mock.patch.object(ms, "surface_bundle", surface))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        result = ms.apply_to_image(target, workers=1)
        return image, bundles, target, result

    def test_one_bundle_that_cannot_be_surfaced_is_kept_and_named(self):
        image, bundles, target, result = self.run_step("s13ad.iff")
        self.assertEqual(result["state"], "applied")
        self.assertEqual(result["kept"], {"s13ad.iff": ["bundle"]})
        self.assertEqual(len(result["user_notes"]), 1)
        note = result["user_notes"][0]
        self.assertIn("Modern surfaces: Arrowhead Stadium (s13ad.iff) keeps its field and surface as it was", note)
        self.assertNotIn("—", note)
        index = image.names.index("s13ad.iff")
        self.assertEqual(bytes(image.store[index]), bundles["s13ad.iff"], "the kept bundle keeps its bytes")
        other = image.names.index("s10dd.iff")
        self.assertEqual(bytes(image.store[other])[:1], b"S", "the other bundles are surfaced")
        receipt = ms.read_receipt(target)
        row = receipt["bundles"]["s13ad.iff"]
        self.assertEqual(row["applied_sha256"], row["before_sha256"])
        self.assertEqual(row["kept"][0]["site"], "bundle")
        self.assertIn(BLANK.strip(), row["kept"][0]["reason"])
        self.assertEqual(ms.image_status(target), "applied")
        self.assertNotIn("s13ad.iff", result["detail_fallbacks"])

    def test_a_kept_bundle_still_reads_applied_after_a_later_writer(self):
        image, bundles, target, _result = self.run_step("s22nd.iff")
        receipt = ms.read_receipt(target)
        changed = bytearray(bundles["s22nd.iff"])
        changed[10] ^= 0xFF                              # broadcast greens, the late midfield, ...
        row = ms.bundle_report(_Archive(changed), "s22nd.iff", _Entry(len(changed)), receipt)
        self.assertEqual(row["state"], "applied", row)
        self.assertIn("kept as it was", row["reason"])

    def test_many_kept_bundles_give_a_short_summary_and_a_complete_receipt(self):
        failing = set(ms.HOME_BUNDLES[:12])
        _image, _bundles, target, result = self.run_step(failing)
        self.assertEqual(sorted(result["kept"]), sorted(failing))
        self.assertEqual(len(result["user_notes"]), ms.NOTE_LIMIT + 1)
        self.assertIn("4 more parts were kept as they were; the receipt beside the disc names each one and why",
                      result["user_notes"][-1])
        receipt = ms.read_receipt(target)
        self.assertEqual(sum(1 for row in receipt["bundles"].values() if row.get("kept")), 12)
        self.assertEqual(ms.image_status(target), "applied")

    def test_the_worker_keeps_a_bundle_whatever_it_raised(self):
        with mock.patch.object(ms, "surface_bundle", side_effect=KeyError("material")):
            name, out, rec = ms._job(("s29dd.iff", b"before", False, None, None))
        self.assertEqual((name, out), ("s29dd.iff", b"before"))
        self.assertEqual(rec["edits"], [])
        self.assertIn("Northwest Stadium (s29dd.iff)", rec["kept"][0]["user_note"])
        self.assertIn("could not be built", rec["kept"][0]["user_note"])
        self.assertIn("KeyError", rec["kept"][0]["reason"])


@unittest.skipUnless(PACKS.is_dir(), "retail extraction not available")
class RetailCallers(unittest.TestCase):
    """The callers on real retail bundles with the fitter refusing exactly as Coach Edwards saw it."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_roster_records as rr
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACKS)
        pins = {row["name"]: row for row in colour._pins()["bundles"]}
        cls.pins = pins
        cls.bundles = {}
        with rr._outer_image()(PACKS) as archive:
            for name in ("s10dd.iff", "s13nd.iff"):
                entry = archive.entries[pins[name]["outer"]]
                cls.bundles[name] = archive.read(entry.virtual_offset, entry.size)

    def test_surfaces_keeps_a_divot_layer_the_fitter_refuses(self):
        data = self.bundles["s10dd.iff"]
        with mock.patch.object(colour, "fit_fixed_span", side_effect=blank_fitter):
            out, rec = ms.surface_bundle(data, "s10dd.iff", indoor=False)
        sites = ms.bundle_sites(data)
        at, size = sites["divots"]
        self.assertEqual(out[at:at + size], data[at:at + size], "the divot layer keeps its bytes")
        self.assertEqual({e["kind"] for e in rec["edits"]}, {"field", "normal"}, "the surface itself is written")
        self.assertEqual([k["site"] for k in rec["kept"]], ["divots"])
        self.assertEqual(rec["kept"][0]["user_note"], "Modern surfaces: Lambeau Field (s10dd.iff) keeps its divot layer "
                         "as it was: the new colours leave no room in its fixed slot.")
        self.assertEqual(ms.bundle_report(_Archive(out), "s10dd.iff", _Entry(len(out)), None)["state"], "applied")

    def test_arrowhead_with_colour_keeps_the_art_when_no_graded_field_fits(self):
        from mod_editor.core import nfl2k5_modern_arrowhead as ah
        retail = self.bundles["s13nd.iff"]
        settings = colour.normalize_settings(None)
        settings["values"]["master.strength"] = 0.6
        with mock.patch.object(colour, "fit_fixed_span", side_effect=blank_fitter):
            graded, _edits = colour.modern_bundle(retail, outer_index=self.pins["s13nd.iff"]["outer"], settings=settings)
            out, edits = ah.combined_bundle(retail, graded, outer_index=self.pins["s13nd.iff"]["outer"],
                                            settings=settings, name="s13nd.iff")
        field = next(e for e in edits if e["kind"] == "field")
        kept = field["detail"]["kept"]
        self.assertEqual(kept["what"], "art without the colour grade")
        self.assertIn("256 colours", kept["reason"])
        self.assertIn("32 colours", kept["reason"], "the whole palette ladder was tried first")
        art_pins = {row["name"]: row for row in ah._pins()["bundles"]}["s13nd.iff"]
        pinned = {site["kind"]: site["applied"] for site in art_pins["sites"]}
        self.assertEqual(field["applied"], pinned["field"], "byte for byte the Arrowhead-only field")
        stadium = next(e for e in edits if e["kind"] == "stadium")
        self.assertEqual(stadium["applied"], pinned["stadium"])
        self.assertEqual(ah.combined_notes(edits), [
            "Modern Arrowhead: Arrowhead Stadium (s13nd.iff) keeps the Arrowhead field art without the colour grade on "
            "its field: your colour settings leave no room in its fixed slot."])
        self.assertEqual(len(out), len(retail))
        tint = next(e for e in _edits if e["kind"] == "tint")
        self.assertEqual(out[tint["offset"]:tint["offset"] + 4], graded[tint["offset"]:tint["offset"] + 4],
                         "the rest of the graded bundle stays graded")


@unittest.skipUnless(PACKS.is_dir(), "retail extraction not available")
class PracticeCallers(unittest.TestCase):
    """The practice field keeps a divot layer, or its whole field look, that cannot fit; the facility is still built."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_practice_field_model as pf
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACKS)
        cls.pf = pf
        cls.retail = pf.read_retail(GAME)["s32dd.iff"]
        cls.model = pf.model_bundle(cls.retail, "s32dd.iff", pf.build(venue="s32"), cameras=pf.practice_shots())

    def compose(self, *patches):
        from contextlib import ExitStack
        pf = self.pf
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(pf, "model_bundle", return_value=self.model))
            for patch in patches:
                stack.enter_context(patch)
            return pf.compose_bundle(self.retail, self.retail, "s32dd.iff")

    def test_a_divot_layer_the_fitter_refuses_keeps_its_bytes(self):
        # the divot layer's own refit refuses exactly as Coach Edwards saw it (its fitter, inside divots_span)
        real = ms.divots_span

        def divots_with_a_refusing_fitter(span, family, grass_mean=None):
            with mock.patch.object(colour, "fit_fixed_span", side_effect=blank_fitter):
                return real(span, family, grass_mean)
        out, info = self.compose(mock.patch.object(ms, "divots_span", divots_with_a_refusing_fitter))
        at, size = ms.bundle_sites(self.retail)["divots"]
        self.assertEqual(out[at:at + size], self.retail[at:at + size])
        self.assertEqual([k["site"] for k in info["kept"]], ["divots"])
        self.assertEqual(info["kept"][0]["user_note"], "Modern practice facility: the practice field (s32dd.iff) keeps its "
                         "divot layer as it was: the new colours leave no room in its fixed slot.")
        start, end = self.pf.stretch(self.retail)
        self.assertEqual(out[start:end], self.model[0][start:end], "the facility is built")
        field_at, field_size = ms.bundle_sites(self.retail)["field"]
        self.assertNotEqual(out[field_at:field_at + field_size], self.retail[field_at:field_at + field_size])

    def test_a_field_no_rung_fits_keeps_the_field_look_and_the_facility_is_built(self):
        from mod_editor.core import nfl2k5_scne_builder as sb
        refusal = mock.Mock(side_effect=sb.ScneBuildError("s32dd.iff: the practice field does not fit its span: " + BLANK))
        out, info = self.compose(mock.patch.object(self.pf, "field_span", refusal))
        sites = ms.bundle_sites(self.retail)
        for kind in ("field", "normal", "divots"):
            at, size = sites[kind]
            self.assertEqual(out[at:at + size], self.retail[at:at + size], kind)
        start, end = self.pf.stretch(self.retail)
        self.assertEqual(out[start:end], self.model[0][start:end])
        self.assertEqual([k["site"] for k in info["kept"]], ["field"])
        self.assertIn("keeps its field as it was (the facility around it is built)", info["kept"][0]["user_note"])
        self.assertIsNone(info["field"])


class ColourNotes(unittest.TestCase):
    def test_textures_kept_retail_get_one_line(self):
        edits = {"s13nd.iff": [dict(kind="field", unfit=BLANK + "x"), dict(kind="normal")],
                 "s10dd.iff": [dict(kind="divots", unfit="y")]}
        custom = colour.normalize_settings(None)
        custom["values"]["master.strength"] = 0.6
        self.assertEqual(colour.unfit_note(edits, custom),
                         "Modern colour: 2 stadium textures keep their retail colours (s10dd.iff divot layer, s13nd.iff "
                         "field): your colour settings leave no room in their fixed slots. The receipt beside the disc "
                         "names each one and why.")
        self.assertIsNone(colour.unfit_note({"s13nd.iff": [dict(kind="field")]}))
        many = {f"s{i:02d}dd.iff": [dict(kind="field", unfit="z")] for i in range(9)}
        self.assertIn("and 3 more", colour.unfit_note(many))


class BuildNotes(unittest.TestCase):
    """mod_build says each kept part in the build log and the receipt (and the step rows reach the finished dialog)."""

    def setUp(self):
        from test_mod_build_performance import synthetic_disc
        from mod_editor.core import mod_build
        self.mod_build = mod_build
        self.temp = tempfile.TemporaryDirectory(prefix="b791-notes-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "retail.iso"
        synthetic_disc(self.source)
        self.enterContext(mock.patch.object(mod_build, "_check_playbook_scoring", return_value={"synthetic": True}))
        self.enterContext(mock.patch("mod_editor.core.nfl2k5_unc_bowl_uniforms.apply_to_image",
                                     return_value={"synthetic": True}))

    def stand_ins(self):
        notes = {"colour": "Modern colour: 1 stadium texture keeps its retail colours (s13nd.iff field): x.",
                 "arrowhead": "Modern Arrowhead: Arrowhead Stadium (s13nd.iff) keeps the Arrowhead field art without "
                              "the colour grade on its field: x.",
                 "practice": "Modern practice facility: the practice field (s32dd.iff) keeps its divot layer as it was: x.",
                 "surfaces": "Modern surfaces: Arrowhead Stadium (s13ad.iff) keeps its divot layer as it was: x."}

        def colour_apply(target, *, progress=None, workers=None, settings=None, source_receipt=None, exclude=()):
            normalized = colour.normalize_settings(settings)
            receipt = {"schema": colour.RECEIPT_SCHEMA, "settings": normalized,
                       "settings_sha256": colour.settings_id(normalized), "state": "applied", "label": "colour",
                       "bundles": 0, "already_applied": 0, "rewritten": 0, "bundle_pins": {}, "edits": {},
                       "user_notes": [notes["colour"]]}
            colour._save_image_receipt(target, receipt)
            return receipt
        modules = {
            "nfl2k5_modern_color": types.SimpleNamespace(
                read_image_receipt=colour.read_image_receipt, receipt_path=colour.receipt_path,
                _save_image_receipt=colour._save_image_receipt, normalize_settings=colour.normalize_settings,
                settings_id=colour.settings_id, RECEIPT_SCHEMA=colour.RECEIPT_SCHEMA,
                xbe_status=lambda payload, settings=None: "retail",
                check_image_request=lambda source, settings=None, *, receipt=None: "retail",
                apply=lambda payload, *, enabled=True, settings=None, previous_settings=None: (payload, {"state": "applied"}),
                image_status=lambda source, *, receipt=None, exclude=None: "applied",
                verify=lambda payload, *, enabled=True, settings=None: None, apply_to_image=colour_apply),
            "nfl2k5_modern_arrowhead": types.SimpleNamespace(
                image_status=lambda source: "retail", verify=lambda source, *, enabled=True: None,
                apply_to_image=lambda target, *, progress=None, retail_source=None: {
                    "state": "applied", "bundles": 9, "edits": [], "user_notes": [notes["arrowhead"]]}),
            "nfl2k5_practice_field_model": types.SimpleNamespace(
                image_status=lambda source: "retail", check_request=lambda source: {"state": "retail"},
                apply_to_image=lambda target, **kw: {"state": "applied", "user_notes": [notes["practice"]]}),
            "nfl2k5_modern_surfaces": types.SimpleNamespace(
                image_status=lambda source, deep=False: "retail", check_request=lambda source: "retail",
                read_receipt=lambda source: None, receipt_path=ms.receipt_path, save_receipt=ms.save_receipt,
                apply_to_image=lambda target, **kw: {"state": "applied", "user_notes": [notes["surfaces"]]}),
            "nfl2k5_stadium_shadow": types.SimpleNamespace(
                OPTION_VENUES={}, apply_to_image=lambda target, venues, progress=None: {"state": "applied"}),
            # Broadcast greens follows Modern surfaces on every build; it needs real stadium packs, not this disc
            "nfl2k5_broadcast_greens": types.SimpleNamespace(
                receipt_path=lambda path: Path(str(path) + ".b791-greens.json"), save=lambda path, doc: None,
                apply_to_image=lambda target, progress=None, anniversary_receipt=None: {"state": "applied"}),
        }
        return notes, modules

    def test_every_kept_part_reaches_the_log_the_receipt_and_the_steps(self):
        mod_build = self.mod_build
        notes, modules = self.stand_ins()
        real = mod_build._core_module
        said = []
        plan = mod_build.BuildPlan(str(self.source), str(self.root / "out.iso"), modern_color=True,
                                   modern_arrowhead=True, modern_practice_field=True, modern_surfaces=True,
                                   catch_slider=True)
        with mock.patch.object(mod_build, "_core_module", side_effect=lambda name: modules.get(name) or real(name)):
            receipt = mod_build.build(plan, lambda message, done, total: said.append(message))
        for key in ("colour", "arrowhead", "practice", "surfaces"):
            with self.subTest(key):
                self.assertIn(notes[key], said, "the build log")
                self.assertIn(notes[key], receipt.get("user_notes", []), "the receipt")
                self.assertTrue(any(notes[key] in (step.get("user_notes") or ()) for step in receipt["steps"]),
                                "the step row the finished-disc dialog reads")
        from mod_editor.core import build_feedback
        _title, message = build_feedback.completion(receipt)
        for key in ("arrowhead", "practice", "surfaces"):
            self.assertIn(notes[key], message)


if __name__ == "__main__":
    unittest.main(verbosity=2)

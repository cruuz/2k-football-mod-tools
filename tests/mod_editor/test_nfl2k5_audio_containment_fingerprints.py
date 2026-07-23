"""Retail-free hostile tests for exact 2K5 PCM containment fingerprints."""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
import hashlib
import json
import struct
import unittest

from mod_editor.core.nfl2k5_audio_containment_fingerprints import (
    AudioContainmentFingerprintCancelled,
    AudioContainmentFingerprintError,
    PcmContainmentInventory,
    PcmContainmentPolicy,
    ShortCueAnchorShape,
    SourcePcmContainmentError,
    SourcePcmCueInput,
    build_private_containment_inventory,
)


SOURCE_BINDING = hashlib.sha256(b"synthetic non-retail source binding").hexdigest()
RATE = 32


def _mono(samples: list[int] | tuple[int, ...]) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


def _stereo(frames: list[tuple[int, int]]) -> bytes:
    flattened = [sample for frame in frames for sample in frame]
    return struct.pack(f"<{len(flattened)}h", *flattened)


def _sequence(frame_count: int, seed: int = 1) -> bytes:
    # Unique-enough deterministic non-retail PCM; every value is nonzero.
    values = []
    for frame in range(frame_count):
        value = ((frame * 977 + seed * 7_919) % 60_000) - 30_000
        values.append(value or 1)
    return _mono(values)


def _cue(
    owner: str,
    pcm: bytes,
    *,
    channels: int = 1,
    sample_rate: int = RATE,
    aliases: tuple[str, ...] = (),
) -> SourcePcmCueInput:
    owners = tuple(sorted((owner, *aliases)))
    return SourcePcmCueInput(
        owner_asset_ids=owners,
        channels=channels,
        sample_rate=sample_rate,
        frame_count=len(pcm) // (channels * 2),
        pcm16le=pcm,
    )


def _policy() -> PcmContainmentPolicy:
    return PcmContainmentPolicy(short_anchor_shapes=(
        ShortCueAnchorShape(1, RATE, 4),
        ShortCueAnchorShape(2, RATE, 4),
    ))


def _build(cues, *, expected_cues: int | None = None, **kwargs):
    materialized = cues if not isinstance(cues, (list, tuple)) else tuple(cues)
    if isinstance(materialized, tuple):
        cue_count = len(materialized)
        owner_count = sum(len(cue.owner_asset_ids) for cue in materialized)
    else:
        cue_count = expected_cues
        owner_count = kwargs.pop("expected_owner_count")
    return build_private_containment_inventory(
        SOURCE_BINDING,
        _policy(),
        materialized,
        expected_cue_count=cue_count if expected_cues is None else expected_cues,
        expected_owner_count=owner_count,
        **kwargs,
    )


def _replace_frame(pcm: bytes, frame: int, sample: int, channels: int = 1) -> bytes:
    result = bytearray(pcm)
    offset = frame * channels * 2
    result[offset:offset + 2] = struct.pack("<h", sample)
    return bytes(result)


class PcmContainmentBehaviorTests(unittest.TestCase):
    def test_middle_trim_and_arbitrarily_shifted_excerpt_are_found(self) -> None:
        source = _sequence(112, seed=3)
        inventory = _build((_cue("long", source),))

        middle = source[13 * 2:90 * 2]
        matches = inventory.find_contained_source_pcm(
            middle, channels=1, sample_rate=RATE, frame_count=77
        )
        self.assertTrue(matches)
        self.assertEqual(matches[0].kind, "long_window")

        prefix = _mono([17, -19, 23])
        shifted = prefix + middle
        shifted_matches = inventory.find_contained_source_pcm(
            shifted, channels=1, sample_rate=RATE, frame_count=80
        )
        self.assertTrue(shifted_matches)
        self.assertGreaterEqual(shifted_matches[0].candidate_frame_start, 3)

    def test_short_cue_padding_and_concatenation_are_found(self) -> None:
        short_a = _sequence(6, seed=7)
        short_b = _sequence(7, seed=11)
        inventory = _build((
            _cue("short-a", short_a),
            _cue("short-b", short_b),
        ))

        padded = _mono([0] * 5) + short_a + _mono([0] * 9)
        with self.assertRaises(SourcePcmContainmentError):
            inventory.reject_contained_source_pcm(
                padded, channels=1, sample_rate=RATE, frame_count=20
            )

        joined = short_a + _mono([123, -456, 789]) + short_b
        matches = inventory.find_contained_source_pcm(
            joined, channels=1, sample_rate=RATE, frame_count=16
        )
        self.assertGreaterEqual(len(matches), 2)
        self.assertEqual(
            {owner for match in matches for owner in match.owner_asset_ids},
            {"short-a", "short-b"},
        )

    def test_one_mutation_outside_an_intact_long_window_is_found(self) -> None:
        source = _sequence(96, seed=13)
        inventory = _build((_cue("long", source),))
        changed = _replace_frame(source, 95, -12_345)
        matches = inventory.find_contained_source_pcm(
            changed, channels=1, sample_rate=RATE, frame_count=96
        )
        self.assertTrue(matches)

    def test_all_zero_is_exempt_but_quiet_nonconstant_pcm_is_protected(self) -> None:
        zero = _mono([0] * 20)
        quiet = _mono([1, -1] * 10)
        inventory = _build((
            _cue("all-zero", zero),
            _cue("quiet", quiet),
        ))
        self.assertEqual(inventory.all_zero_owner_ids, ("all-zero",))
        self.assertFalse(inventory.find_contained_source_pcm(
            _mono([0] * 40), channels=1, sample_rate=RATE, frame_count=40
        ))
        with self.assertRaises(SourcePcmContainmentError):
            inventory.reject_contained_source_pcm(
                _mono([0] * 3) + quiet + _mono([0] * 2),
                channels=1,
                sample_rate=RATE,
                frame_count=25,
            )

    def test_shape_key_prevents_cross_channel_or_rate_matches(self) -> None:
        source = _sequence(20, seed=17)
        inventory = _build((_cue("mono", source),))
        self.assertFalse(inventory.find_contained_source_pcm(
            source,
            channels=1,
            sample_rate=RATE + 1,
            frame_count=20,
        ))
        stereo_bytes = source + source
        self.assertFalse(inventory.find_contained_source_pcm(
            stereo_bytes,
            channels=2,
            sample_rate=RATE,
            frame_count=20,
        ))

    def test_mutating_every_indexed_window_is_outside_the_exact_claim(self) -> None:
        # W=32 and S=8.  Altering every eighth frame intersects every indexed
        # quarter-second source window. Exact containment intentionally makes no
        # fuzzy/perceptual claim for this transformed candidate.
        source = _sequence(96, seed=23)
        changed = source
        for frame in range(0, 96, 8):
            changed = _replace_frame(changed, frame, 30_000 - frame)
        inventory = _build((_cue("long", source),))
        self.assertFalse(inventory.find_contained_source_pcm(
            changed, channels=1, sample_rate=RATE, frame_count=96
        ))

    def test_short_anchor_mutation_is_an_explicit_narrow_boundary(self) -> None:
        source = _sequence(6, seed=29)
        inventory = _build((_cue("short", source),))
        # The deterministic anchor starts at frame zero for this nonzero cue.
        # Changing one frame inside it defeats this containment record; the
        # separate full-cue hash store remains a different layer.
        changed = _replace_frame(source, 0, 12_345)
        self.assertFalse(inventory.find_contained_source_pcm(
            changed, channels=1, sample_rate=RATE, frame_count=6
        ))

    def test_sparse_nonzero_long_cue_gets_a_deterministic_fallback(self) -> None:
        # Grid windows are [0,8) and [8,16); the only nonzero sample is in the
        # one-frame tail, so normal grid indexing would otherwise protect none.
        source = _mono([0] * 16 + [1])
        inventory = _build((_cue("sparse", source),))
        self.assertEqual(inventory.fingerprint_count, 1)
        self.assertEqual(inventory.fingerprints[0].kind, "sparse_anchor")
        padded = _mono([0] * 5) + source + _mono([0] * 3)
        with self.assertRaises(SourcePcmContainmentError):
            inventory.reject_contained_source_pcm(
                padded, channels=1, sample_rate=RATE, frame_count=25
            )

    def test_same_digest_across_grid_and_sparse_kinds_retains_all_owners(self) -> None:
        shared_window = _mono([0] * 7 + [1])
        sparse = _mono([0] * 16 + [1])
        inventory = _build((
            _cue("grid-owner", shared_window),
            _cue("sparse-owner", sparse),
        ))
        matches = inventory.find_contained_source_pcm(
            shared_window,
            channels=1,
            sample_rate=RATE,
            frame_count=8,
        )
        self.assertEqual(
            {owner for match in matches for owner in match.owner_asset_ids},
            {"grid-owner", "sparse-owner"},
        )
        self.assertEqual(
            {match.kind for match in matches},
            {"long_window", "sparse_anchor"},
        )


class PcmContainmentContractTests(unittest.TestCase):
    def test_inventory_is_digest_shape_owner_metadata_only_and_round_trips(self) -> None:
        source = _sequence(80, seed=31)
        quiet = _mono([1, -1] * 10)
        inventory = _build((
            _cue("long-a", source, aliases=("long-alias",)),
            _cue("short-a", quiet),
            _cue("zero-a", _mono([0] * 20)),
        ))
        document = inventory.to_private_document()
        encoded = json.dumps(document, sort_keys=True).encode("utf-8")
        self.assertNotIn(source, encoded)
        self.assertEqual(document["privacy"]["audio_payload_bytes"], 0)
        self.assertFalse(inventory.shareable)
        self.assertTrue(inventory.private)
        forbidden = (
            "pcm16le", "wav", "path", "offset", "archive", "pack",
            "preimage", "encoded_payload",
        )
        self.assertFalse(any(word in encoded.decode("utf-8").lower() for word in forbidden))
        loaded = PcmContainmentInventory.from_private_document(document)
        self.assertEqual(loaded, inventory)

    def test_windows_never_cross_source_cue_boundaries(self) -> None:
        left = _sequence(20, seed=37)
        right = _sequence(20, seed=41)
        inventory = _build((_cue("left", left), _cue("right", right)))
        boundary = left[-4 * 2:] + right[:4 * 2]
        boundary_digest = hashlib.sha256(boundary).hexdigest()
        self.assertNotIn(
            boundary_digest,
            {row.pcm_sha256 for row in inventory.fingerprints},
        )

    def test_checksum_hit_is_never_authoritative_without_sha256(self) -> None:
        source = _sequence(6, seed=43)
        inventory = _build((_cue("short", source),))
        document = inventory.to_private_document()
        document["fingerprints"][0]["pcm_sha256"] = hashlib.sha256(
            b"different synthetic window"
        ).hexdigest()
        tampered = PcmContainmentInventory.from_private_document(document)
        # Rolling checksum still hits, but the mismatched SHA-256 refuses it.
        self.assertFalse(tampered.find_contained_source_pcm(
            source, channels=1, sample_rate=RATE, frame_count=6
        ))

    def test_malformed_pcm_shapes_and_too_short_cues_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            AudioContainmentFingerprintError, "byte length does not match"
        ):
            _build((SourcePcmCueInput(
                owner_asset_ids=("bad",),
                channels=1,
                sample_rate=RATE,
                frame_count=20,
                pcm16le=_mono([1] * 19),
            ),))
        with self.assertRaisesRegex(
            AudioContainmentFingerprintError, "channels must be 1 or 2"
        ):
            _build((SourcePcmCueInput(
                owner_asset_ids=("bad",),
                channels=3,
                sample_rate=RATE,
                frame_count=8,
                pcm16le=bytes(48),
            ),))
        # All-zero input does not get silently dropped before the authenticated
        # short-anchor minimum is enforced.
        with self.assertRaisesRegex(
            AudioContainmentFingerprintError, "shorter than.*short anchor"
        ):
            _build((_cue("too-short", _mono([0] * 3)),))

    def test_malformed_private_representation_fails_closed(self) -> None:
        inventory = _build((_cue("short", _sequence(20, seed=47)),))
        original = inventory.to_private_document()

        extra = deepcopy(original)
        extra["unknown"] = True
        with self.assertRaisesRegex(
            AudioContainmentFingerprintError, "missing or unknown"
        ):
            PcmContainmentInventory.from_private_document(extra)

        wrong_shape = deepcopy(original)
        wrong_shape["fingerprints"][0]["frame_count"] += 1
        with self.assertRaisesRegex(
            AudioContainmentFingerprintError, "shape conflicts"
        ):
            PcmContainmentInventory.from_private_document(wrong_shape)

        bad_digest = deepcopy(original)
        bad_digest["fingerprints"][0]["pcm_sha256"] = "0" * 63
        with self.assertRaisesRegex(AudioContainmentFingerprintError, "Invalid"):
            PcmContainmentInventory.from_private_document(bad_digest)

        incomplete = deepcopy(original)
        incomplete["fingerprints"] = []
        incomplete["counts"]["fingerprints"] = 0
        with self.assertRaisesRegex(
            AudioContainmentFingerprintError, "coverage is incomplete"
        ):
            PcmContainmentInventory.from_private_document(incomplete)

        bool_alias = deepcopy(original)
        bool_alias["privacy"]["private_user_cache"] = 1
        with self.assertRaisesRegex(
            AudioContainmentFingerprintError, "not private metadata-only"
        ):
            PcmContainmentInventory.from_private_document(bool_alias)

    def test_adler_collision_bucket_uses_direct_sha_lookup(self) -> None:
        source = _sequence(20, seed=49)
        original = _build((_cue("actual", source),))
        document = original.to_private_document()
        base = document["fingerprints"][0]
        rows = [deepcopy(base)]
        owners = ["actual"]
        for index in range(2_048):
            owner = f"collision.{index:04d}"
            row = deepcopy(base)
            row["owner_asset_ids"] = [owner]
            row["pcm_sha256"] = hashlib.sha256(
                f"synthetic-collision-{index}".encode("ascii")
            ).hexdigest()
            rows.append(row)
            owners.append(owner)
        rows.sort(key=lambda row: (
            row["kind"], row["channels"], row["sample_rate"],
            row["frame_count"], row["rolling_checksum"], row["pcm_sha256"],
            tuple(row["owner_asset_ids"]),
        ))
        document["fingerprints"] = rows
        document["source_owner_ids"] = sorted(owners)
        document["counts"] = {
            "all_zero_owners": 0,
            "fingerprints": len(rows),
            "source_cues": len(rows),
            "source_owners": len(owners),
        }
        inventory = PcmContainmentInventory.from_private_document(document)
        shape = (1, RATE, 8)
        checksum = int(base["rolling_checksum"], 16)
        bucket = inventory._by_shape_checksum[shape][checksum]
        self.assertIsInstance(bucket, Mapping)
        self.assertEqual(len(bucket), len(rows))
        matches = inventory.find_contained_source_pcm(
            source, channels=1, sample_rate=RATE, frame_count=20
        )
        self.assertTrue(matches)
        self.assertEqual(matches[0].owner_asset_ids, ("actual",))

    def test_owner_reference_bound_is_enforced_during_window_creation(self) -> None:
        source = _sequence(48, seed=53)  # Six quarter-second grid windows.
        cue = _cue(
            "alias.0",
            source,
            aliases=("alias.1", "alias.2", "alias.3"),
        )
        with self.assertRaisesRegex(
            AudioContainmentFingerprintError, "owner-reference count exceeds"
        ):
            build_private_containment_inventory(
                SOURCE_BINDING,
                _policy(),
                iter((cue,)),
                expected_cue_count=1,
                expected_owner_count=4,
                max_fingerprint_owner_references=10,
            )

    def test_record_bound_is_enforced_during_window_creation(self) -> None:
        with self.assertRaisesRegex(
            AudioContainmentFingerprintError, "fingerprint-record bound"
        ):
            build_private_containment_inventory(
                SOURCE_BINDING,
                _policy(),
                iter((_cue("many-windows", _sequence(48, seed=59)),)),
                expected_cue_count=1,
                expected_owner_count=1,
                max_fingerprint_records=2,
            )

    def test_one_pass_iterable_uses_authenticated_counts(self) -> None:
        class OnePass:
            def __init__(self) -> None:
                self.iterations = 0

            def __iter__(self):
                self.iterations += 1
                if self.iterations != 1:
                    raise AssertionError("cue stream was replayed")
                for index in range(3):
                    yield _cue(f"lazy-{index}", _sequence(20, seed=50 + index))

            def __len__(self):
                raise AssertionError("lazy cue stream was materialized/sized")

        stream = OnePass()
        inventory = _build(
            stream,
            expected_cues=3,
            expected_owner_count=3,
        )
        self.assertEqual(stream.iterations, 1)
        self.assertEqual(inventory.source_cue_count, 3)
        self.assertEqual(len(inventory.source_owner_ids), 3)

        with self.assertRaisesRegex(
            AudioContainmentFingerprintError, "ended before"
        ):
            _build(
                iter((_cue("one", _sequence(20, 60)),)),
                expected_cues=2,
                expected_owner_count=1,
            )
        with self.assertRaisesRegex(
            AudioContainmentFingerprintError, "more rows"
        ):
            _build(
                iter((
                    _cue("one", _sequence(20, 61)),
                    _cue("two", _sequence(20, 62)),
                )),
                expected_cues=1,
                expected_owner_count=1,
            )

    def test_progress_and_cancellation_are_deterministic(self) -> None:
        events = []
        inventory = _build(
            (_cue("long", _sequence(96, seed=67)),),
            progress=events.append,
            progress_interval_frames=8,
        )
        self.assertEqual(events[0].stage, "Indexing source PCM containment")
        self.assertEqual((events[0].completed_units, events[0].total_units), (0, 1))
        self.assertEqual(events[-1].stage, "Source PCM containment inventory ready")

        cancel_calls = 0

        def cancel_scan() -> bool:
            nonlocal cancel_calls
            cancel_calls += 1
            return cancel_calls >= 3

        scan_events = []
        with self.assertRaises(AudioContainmentFingerprintCancelled):
            inventory.find_contained_source_pcm(
                _sequence(1_000, seed=71),
                channels=1,
                sample_rate=RATE,
                frame_count=1_000,
                cancel=cancel_scan,
                progress=scan_events.append,
                progress_interval_frames=4,
            )
        self.assertEqual(scan_events[0].completed_units, 0)

        build_cancel_calls = 0

        def cancel_build() -> bool:
            nonlocal build_cancel_calls
            build_cancel_calls += 1
            return build_cancel_calls >= 3

        with self.assertRaises(AudioContainmentFingerprintCancelled):
            _build(
                (_cue("long", _sequence(96, seed=73)),),
                cancel=cancel_build,
                progress_interval_frames=8,
            )


class RollingChecksumIdentityTests(unittest.TestCase):
    def test_candidate_scan_checks_every_frame_for_mono_and_stereo(self) -> None:
        # Place each short anchor at offsets deliberately not aligned to source
        # stride.  A frame-by-frame candidate scan must still find both.
        mono = _sequence(20, seed=79)
        stereo_frames = [(index + 1, -(index + 2)) for index in range(20)]
        stereo = _stereo(stereo_frames)
        inventory = _build((
            _cue("mono", mono),
            _cue("stereo", stereo, channels=2),
        ))
        for offset in range(13):
            mono_prefix = _mono([100 + index for index in range(offset)])
            mono_candidate = mono_prefix + mono
            mono_matches = inventory.find_contained_source_pcm(
                mono_candidate,
                channels=1,
                sample_rate=RATE,
                frame_count=offset + 20,
            )
            self.assertIn(offset, {
                match.candidate_frame_start for match in mono_matches
                if "mono" in match.owner_asset_ids
            })

            stereo_prefix = _stereo([
                (100 + index, -200 - index) for index in range(offset)
            ])
            stereo_candidate = stereo_prefix + stereo
            stereo_matches = inventory.find_contained_source_pcm(
                stereo_candidate,
                channels=2,
                sample_rate=RATE,
                frame_count=offset + 20,
            )
            self.assertIn(offset, {
                match.candidate_frame_start for match in stereo_matches
                if "stereo" in match.owner_asset_ids
            })

    def test_nondivisible_sample_rate_uses_rational_quarter_second_grid(self) -> None:
        rate = 11_025
        frames = rate * 2
        source = _mono([
            (((index * 313) % 60_000) - 30_000) or 1
            for index in range(frames)
        ])
        policy = PcmContainmentPolicy((ShortCueAnchorShape(1, rate, 2_000),))
        inventory = build_private_containment_inventory(
            SOURCE_BINDING,
            policy,
            iter((_cue("rational", source, sample_rate=rate),)),
            expected_cue_count=1,
            expected_owner_count=1,
        )
        # floor(k*11025/4) through the last legal quarter-window start gives
        # eight distinct exact windows across this two-second cue.
        self.assertEqual(inventory.fingerprint_count, 8)
        shifted = _mono([77] * 17) + source[3_000 * 2:17_000 * 2]
        self.assertTrue(inventory.find_contained_source_pcm(
            shifted,
            channels=1,
            sample_rate=rate,
            frame_count=17 + 14_000,
        ))

    def test_500ms_arbitrary_excerpt_guarantee_and_499ms_boundary(self) -> None:
        # 1001 Hz is deliberately not divisible by four. W=floor(1001/4)=250,
        # max grid gap=251, and the exact guaranteed run is 500 frames.
        rate = 1_001
        source_frames = 2_750
        source = _mono([
            (((index * 197) % 60_000) - 30_000) or 1
            for index in range(source_frames)
        ])
        policy = PcmContainmentPolicy((ShortCueAnchorShape(1, rate, 100),))
        inventory = build_private_containment_inventory(
            SOURCE_BINDING,
            policy,
            iter((_cue("half-second", source, sample_rate=rate),)),
            expected_cue_count=1,
            expected_owner_count=1,
        )
        self.assertEqual(policy.long_window_frames(rate), 250)
        self.assertEqual(policy.guaranteed_excerpt_frames(rate), 500)

        # Exhaust every source start at the exact mathematical bound. Candidate
        # matching scans every frame, so none may fall between grid positions.
        guarantee = policy.guaranteed_excerpt_frames(rate)
        for start in range(source_frames - guarantee + 1):
            excerpt = source[start * 2:(start + guarantee) * 2]
            self.assertTrue(
                inventory.find_contained_source_pcm(
                    excerpt,
                    channels=1,
                    sample_rate=rate,
                    frame_count=guarantee,
                    max_matches=1,
                ),
                f"unprotected exact excerpt at source frame {start}",
            )

        # A 499 ms floor (499 frames here) is not guaranteed. Start 751 is one
        # frame after a grid window; the next 250-frame window ends just beyond
        # this excerpt. Any true >=500 ms PCM run rounds to at least 501 frames.
        too_short_frames = (rate * 499) // 1_000
        self.assertEqual(too_short_frames, 499)
        worst_start = 751
        too_short = source[
            worst_start * 2:(worst_start + too_short_frames) * 2
        ]
        self.assertFalse(inventory.find_contained_source_pcm(
            too_short,
            channels=1,
            sample_rate=rate,
            frame_count=too_short_frames,
        ))


if __name__ == "__main__":
    unittest.main()

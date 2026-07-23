#!/usr/bin/env python3
"""Strict synthetic and retail-corpus tests for the VC-LZ encoder."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nfl_outer import parse_archive
from nfl_txtr import (
    HEADER,
    TxtrError,
    compress_vc_lz,
    decode_chunk,
    decompress_vc_lz,
    rebuild_compressed_chunk_fixed_span,
)
from nfl_uniform_inventory import read_and_validate_span


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
INVENTORY = ROOT / "reports/assets/nfl2k5_resource_chunks_v2.json"
REPRESENTATIVE = (
    (3613, 1, 177024, 73530, 1, 12),
    (3685, 1, 177024, 74674, 3, 12),
    (3685, 3, 24192, 11497, 51, 12),
    (3685, 5, 26624, 19710, 1, 13),
    (3685, 6, 52608, 28138, 1, 12),
    (3685, 8, 94208, 55186, 2, 12),
    (3939, 1, 177024, 74679, 1, 12),
    (4246, 10, 14336, 11419, 1, 13),
)


def expect_txtr_error(callback, label: str) -> None:
    try:
        callback()
    except TxtrError:
        return
    raise AssertionError(f"{label} did not fail closed")


def synthetic_tests() -> None:
    cases = (
        b"ABC",
        b"A" * 4096,
        bytes(range(256)) * 9,
        (b"0123456789abcdef" * 257) + b"tail",
        bytes((index * 73 + 19) & 0xFF for index in range(8193)),
    )
    for source in cases:
        encoded, info = compress_vc_lz(source)
        repeated, repeated_info = compress_vc_lz(source)
        decoded, decode_info = decompress_vc_lz(encoded, len(source))
        assert encoded == repeated and info == repeated_info
        assert decoded == source and decode_info.consumed_bytes == len(encoded)
        assert info.verified_roundtrip and info.encoded_bytes == len(encoded)
        assert info.token_count == info.literal_count + info.match_count
        bounded, _ = compress_vc_lz(source, max_encoded_size=len(encoded))
        assert bounded == encoded
        expect_txtr_error(
            lambda: compress_vc_lz(source, max_encoded_size=len(encoded) - 1),
            "one-byte-short encoded-size bound",
        )

    expect_txtr_error(lambda: compress_vc_lz(b""), "empty source")
    expect_txtr_error(lambda: compress_vc_lz(b"abc", offset_bits=0), "offset bits 0")
    expect_txtr_error(lambda: compress_vc_lz(b"abc", offset_bits=16), "offset bits 16")
    expect_txtr_error(
        lambda: compress_vc_lz(b"abcabc", max_candidate_comparisons=0),
        "zero candidate bound",
    )
    expect_txtr_error(
        lambda: compress_vc_lz(b"abc" * 100, max_candidate_comparisons=1),
        "exhausted candidate bound",
    )


def retail_tests() -> None:
    archive = parse_archive(INDEX)
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    by_key = {
        (int(item["outer_index"]), int(item["chunk_index"])): item
        for item in inventory["chunks"]
    }
    tested_decoded_bytes = 0
    for outer, chunk_index, decoded_size, consumed_size, stream_tag, offset_bits in REPRESENTATIVE:
        record, span, decoded, decode_info = read_and_validate_span(
            archive, by_key[outer, chunk_index]
        )
        assert decode_info is not None
        assert len(decoded) == decoded_size
        assert decode_info.consumed_bytes == consumed_size
        assert int.from_bytes(span[HEADER.size + 4:HEADER.size + 8], "little") == stream_tag
        assert span[HEADER.size + 8] == offset_bits
        encoded, info = compress_vc_lz(
            decoded,
            stream_tag=stream_tag,
            offset_bits=offset_bits,
            max_encoded_size=record.stored_size,
        )
        original_stream = span[
            HEADER.size:HEADER.size + decode_info.consumed_bytes
        ]
        assert encoded == original_stream
        assert info.encoded_bytes == consumed_size and info.verified_roundtrip
        roundtrip, independent_info = decompress_vc_lz(encoded, decoded_size)
        assert roundtrip == decoded and independent_info.consumed_bytes == consumed_size
        tested_decoded_bytes += decoded_size

    target_item = by_key[3685, 1]
    record, target_span, target_decoded, decode_info = read_and_validate_span(
        archive, target_item
    )
    assert decode_info is not None and record.stored_size == 74688
    rebuilt, rebuild_info = rebuild_compressed_chunk_fixed_span(
        target_span, target_decoded
    )
    assert rebuild_info.recompressed_bytes == 74674
    assert rebuild_info.zero_padding_bytes == 14
    assert rebuild_info.compressed_stream_matches_template
    assert not rebuild_info.complete_span_matches_template
    assert rebuild_info.rebuilt_span_sha256 == \
        "a802389334ad0e895557a9047f24381eb0f3ed9eefc77a7572a87ac64f56c9a9"
    differences = [
        index for index, (before, after) in enumerate(zip(target_span, rebuilt))
        if before != after
    ]
    assert differences == list(range(74706, 74720))
    assert target_span[74706:] == b"\x3c" * 14 and rebuilt[74706:] == bytes(14)
    rebuilt_decoded, rebuilt_decode_info = decode_chunk(rebuilt, record.as_chunk())
    assert rebuilt_decoded == target_decoded
    assert rebuilt_decode_info is not None and rebuilt_decode_info.consumed_bytes == 74674

    # A non-identity palette-byte probe proves the primitive does more than
    # reproduce its input while remaining inside the same fixed body.
    palette_probe = bytearray(target_decoded)
    palette_probe_offset = 256 + 174720
    palette_probe[palette_probe_offset] ^= 0x55
    mutated_span, mutated_info = rebuild_compressed_chunk_fixed_span(
        target_span, bytes(palette_probe)
    )
    assert mutated_info.recompressed_bytes == 74675
    assert mutated_info.zero_padding_bytes == 13
    assert not mutated_info.template_decoded_matches_input
    assert not mutated_info.compressed_stream_matches_template
    assert mutated_info.rebuilt_span_sha256 == \
        "1a1ae6f6612563e0cf7736186cb5a10619c01e70eea405dab374e9d1e842a97a"
    mutated_decoded, mutated_decode_info = decode_chunk(
        mutated_span, record.as_chunk()
    )
    assert mutated_decoded == bytes(palette_probe)
    assert mutated_decode_info is not None and mutated_decode_info.consumed_bytes == 74675
    assert hashlib.sha256(mutated_decoded).hexdigest() == mutated_info.decoded_sha256

    expect_txtr_error(
        lambda: compress_vc_lz(
            target_decoded,
            stream_tag=3,
            offset_bits=12,
            max_encoded_size=74673,
        ),
        "Lions one-byte-short fixed body",
    )
    expect_txtr_error(
        lambda: rebuild_compressed_chunk_fixed_span(
            target_span, target_decoded[:-1]
        ),
        "short fixed-span decoded input",
    )
    damaged_header = bytearray(target_span)
    damaged_header[0x18] = 1
    expect_txtr_error(
        lambda: rebuild_compressed_chunk_fixed_span(
            bytes(damaged_header), target_decoded
        ),
        "nonzero fixed-span reserved word",
    )

    print(
        "NFL_VC_LZ_RETAIL_TESTS_PASS "
        f"chunks={len(REPRESENTATIVE)} decoded_bytes={tested_decoded_bytes} "
        "exact_streams=8 identity_fit=74674/74688 palette_probe_fit=74675/74688"
    )


def main() -> int:
    synthetic_tests()
    retail_tests()
    print("NFL_VC_LZ_COMPRESS_TESTS_PASS synthetic=5 deterministic=true bounded=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

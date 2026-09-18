"""Unmodified rc97 greedy codec, retained as a byte and bounds oracle."""
from nfl_txtr import *
from collections import defaultdict, deque
import struct
def compress_vc_lz(
    source: bytes,
    *,
    stream_tag: int = 3,
    offset_bits: int = 12,
    max_encoded_size: int | None = None,
    max_candidate_comparisons: int = 50_000_000,
    verify_roundtrip: bool = True,
) -> tuple[bytes, CompressInfo]:
    """Deterministically encode bytes for :func:`decompress_vc_lz`.

    The sampled retail streams are reproduced by an exhaustive, nearest-first
    search over the preceding ``(1 << offset_bits) - 1`` bytes.  Ties retain
    the nearest candidate.  Matches are limited to their backward distance
    because the title's decoder copies each match from high index to low index;
    unlike a conventional forward LZSS copy, an overlapping match would read
    target bytes before they have been written.

    ``max_encoded_size`` bounds the complete stream including its nine-byte
    prefix.  ``max_candidate_comparisons`` bounds adversarial search time.
    Both limits fail closed rather than emitting a partial stream.
    """

    if not source:
        raise TxtrError("VC-LZ cannot encode an empty output buffer")
    if len(source) > 0xFFFFFFFF:
        raise TxtrError("VC-LZ output exceeds its u32 size field")
    if not 0 <= stream_tag <= 0xFFFFFFFF:
        raise TxtrError(f"VC-LZ stream tag {stream_tag} is outside u32")
    if not 1 <= offset_bits <= 15:
        raise TxtrError(f"invalid offset bit count {offset_bits}")
    if max_encoded_size is not None and max_encoded_size < 10:
        raise TxtrError("VC-LZ encoded-size bound is shorter than a usable stream")
    if max_candidate_comparisons <= 0:
        raise TxtrError("VC-LZ candidate-comparison bound must be positive")

    length_bits = 16 - offset_bits
    maximum_distance = (1 << offset_bits) - 1
    maximum_length = ((1 << length_bits) - 1) + 3
    minimum_match = 3
    chains: dict[int, deque[int]] = defaultdict(deque)
    encoded = bytearray(struct.pack("<IIB", len(source), stream_tag, offset_bits))
    pending: list[tuple[bool, int, int]] = []
    position = 0
    literal_count = 0
    match_count = 0
    flag_bytes = 0
    maximum_distance_used = 0
    maximum_length_used = 0
    candidate_comparisons = 0

    def key_at(offset: int) -> int:
        return (
            source[offset]
            | (source[offset + 1] << 8)
            | (source[offset + 2] << 16)
        )

    def add_position(offset: int) -> None:
        if offset + minimum_match <= len(source):
            chains[key_at(offset)].append(offset)

    def flush_tokens() -> None:
        nonlocal flag_bytes
        if not pending:
            return
        flags = 0
        payload = bytearray()
        for token_index, (is_match, first, second) in enumerate(pending):
            if is_match:
                flags |= 1 << token_index
                code = first | ((second - minimum_match) << offset_bits)
                payload.extend(struct.pack("<H", code))
            else:
                payload.append(first)
        required = 1 + len(payload)
        if max_encoded_size is not None and len(encoded) + required > max_encoded_size:
            raise TxtrError(
                f"VC-LZ stream needs more than the {max_encoded_size}-byte bound"
            )
        encoded.append(flags)
        encoded.extend(payload)
        flag_bytes += 1
        pending.clear()

    while position < len(source):
        best_length = 0
        best_distance = 0
        remaining = len(source) - position
        if remaining >= minimum_match:
            candidates = chains.get(key_at(position))
            if candidates:
                cutoff = position - maximum_distance
                while candidates and candidates[0] < cutoff:
                    candidates.popleft()
                for candidate in reversed(candidates):
                    distance = position - candidate
                    if distance < minimum_match:
                        # A minimum three-byte non-overlapping match is
                        # impossible at distance one or two.
                        continue
                    candidate_comparisons += 1
                    if candidate_comparisons > max_candidate_comparisons:
                        raise TxtrError(
                            "VC-LZ candidate-comparison bound exceeded"
                        )
                    limit = min(maximum_length, remaining, distance)
                    length = minimum_match
                    while (
                        length < limit
                        and source[candidate + length] == source[position + length]
                    ):
                        length += 1
                    if length > best_length:
                        best_length = length
                        best_distance = distance
                    # No candidate can exceed the format's maximum length.
                    if best_length == maximum_length:
                        break

        if best_length >= minimum_match:
            pending.append((True, best_distance, best_length))
            consumed = best_length
            match_count += 1
            maximum_distance_used = max(maximum_distance_used, best_distance)
            maximum_length_used = max(maximum_length_used, best_length)
        else:
            pending.append((False, source[position], 0))
            consumed = 1
            literal_count += 1

        for consumed_offset in range(position, position + consumed):
            add_position(consumed_offset)
        position += consumed
        if len(pending) == 8:
            flush_tokens()

    flush_tokens()
    if max_encoded_size is not None and len(encoded) > max_encoded_size:
        raise TxtrError(
            f"VC-LZ stream is {len(encoded)} bytes, exceeds {max_encoded_size}"
        )

    verified = False
    if verify_roundtrip:
        decoded, decode_info = decompress_vc_lz(bytes(encoded), len(source))
        if decoded != source:
            raise TxtrError("VC-LZ encoder failed its internal round-trip check")
        if decode_info.consumed_bytes != len(encoded):
            raise TxtrError("VC-LZ decoder did not consume the complete encoded stream")
        verified = True

    info = CompressInfo(
        declared_output_size=len(source),
        stream_tag=stream_tag,
        offset_bits=offset_bits,
        length_bits=length_bits,
        encoded_bytes=len(encoded),
        token_count=literal_count + match_count,
        flag_bytes=flag_bytes,
        literal_count=literal_count,
        match_count=match_count,
        maximum_distance_used=maximum_distance_used,
        maximum_length_used=maximum_length_used,
        candidate_comparisons=candidate_comparisons,
        verified_roundtrip=verified,
    )
    return bytes(encoded), info


"""Retail-free fixed-allocation authoring for standalone NFL 2K5 AUDO slots.

The shipped ownership catalog describes every physical AUDO resource using
stable outer/chunk identity, allocation metadata, and cryptographic hashes.
This module authorizes all 849 non-Menu-Back physical rows for product editing.
Each target is selected by stable outer/chunk identity and rebound to its exact,
non-overlapping wrapper before writeback.  Duplicate names or decoded content
do not collapse distinct physical spans.  The old 152-row classification stays
intact as a compatibility marker for legacy complete replacement packs.

Only user-authored strict PCM16 WAV data is encoded.  Wrapper headers, resource
metadata, descriptors, tails, archive extents, and every byte outside the
selected payload stay unchanged.  The module contains no retail payload.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import Path
import re
import struct
import sys
from typing import Any
import wave


ROOT = Path(__file__).resolve().parents[2]
CAPACITY_REPORT = ROOT / "reports/assets/nfl2k5_audo_import_capacity.json"
CAPACITY_REPORT_SCHEMA = "nfl2k5_audo_import_capacity/v1"
CAPACITY_REPORT_SHA256 = (
    "1d9ebb31a8822d113ae0fc8ec028e4ff652ccb7cbcf9d6d1d870aa58ef65f556"
)
EXPECTED_RECORD_COUNT = 850
# ``EXPECTED_EDITABLE_COUNT`` remains the public loader parameter name, but its
# value now describes every generic non-Menu-Back physical slot.  The legacy
# classification count is deliberately separate so v1 complete packs can keep
# their original 152-plus-Menu-Back inventory.
EXPECTED_GENERIC_SLOT_COUNT = 849
EXPECTED_EDITABLE_COUNT = EXPECTED_GENERIC_SLOT_COUNT
EXPECTED_LEGACY_CLASSIFIED_COUNT = 152
EDITABLE_CLASSIFICATION = "structurally-encodable-owner-runtime-unproved"
GENERIC_CLASSIFICATIONS = frozenset({"export-only", EDITABLE_CLASSIFICATION})
MENU_BACK_SELECTOR = (3, 101)
ASSET_ID_RE = re.compile(r"nfl2k5\.audio\.audo\.o(\d{4})\.c(\d{4})\Z")
KEY_RE = re.compile(r"outer_(\d{4})_chunk_(\d{4})\Z")

HEADER_SIZE = 0x20
BLOCK_FRAMES = 64
CHANNEL_BLOCK_BYTES = 36
MAX_WAV_BYTES = 16 * 1024 * 1024
MAX_REPORT_BYTES = 16 * 1024 * 1024

IMA_INDEX_TABLE = (-1, -1, -1, -1, 2, 4, 6, 8)
IMA_STEP_TABLE = (
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130,
    143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449,
    494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411,
    1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026,
    4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442,
    11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
    27086, 29794, 32767,
)


class FixedAudoError(ValueError):
    """A catalog row, WAV, or fixed-allocation encode failed closed."""


@dataclass(frozen=True, slots=True)
class FixedAudoSlot:
    asset_id: str
    key: str
    name: str
    classification: str
    outer_index: int
    chunk_index: int
    channels: int
    sample_rate: int
    frame_count: int
    payload_size: int
    payload_sha256: str
    system_size: int
    system_sha256: str
    tail_size: int
    tail_sha256: str
    wrapper_pack_offset: int
    wrapper_size: int
    wrapper_sha256: str
    wrapper_header_sha256: str
    pack_path: str
    pack_sector: int
    pack_size: int
    pack_sha256: str
    payload_pack_offset: int
    payload_absolute_offset: int
    runtime_selector_owner: str
    runtime_visibility: str

    @property
    def selector(self) -> tuple[int, int]:
        return self.outer_index, self.chunk_index

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate

    @property
    def legacy_complete_pack_editable(self) -> bool:
        """Whether this generic slot belongs to the old 152-row v1 set."""

        return self.classification == EDITABLE_CLASSIFICATION

    @property
    def replacement_warning(self) -> str:
        """Honest semantic caveat attached to this exact physical target."""

        return generic_fixed_slot_warning(self.outer_index, self.chunk_index)


@dataclass(frozen=True, slots=True)
class StrictWav:
    channels: int
    sample_rate: int
    frame_count: int
    samples: tuple[int, ...]
    pcm_sha256: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FixedAudoError(message)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def asset_id(outer_index: int, chunk_index: int) -> str:
    return f"nfl2k5.audio.audo.o{outer_index:04d}.c{chunk_index:04d}"


def generic_fixed_slot_warning(outer_index: int, chunk_index: int) -> str:
    """Return the per-row caveat without weakening the physical-slot claim."""

    stable_id = asset_id(outer_index, chunk_index)
    return (
        f"Physical fixed-slot ownership is exact for {stable_id} "
        f"(outer {outer_index}, chunk {chunk_index}), but semantic cue identity "
        "and runtime selector ownership may be unknown. Replace changes only "
        "this physical slot; matching names or decoded content do not identify "
        "another slot."
    )


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"AUDO catalog has invalid {label}")
    return value


def load_editable_slots(
    report_path: Path = CAPACITY_REPORT,
    *,
    expected_sha256: str | None = CAPACITY_REPORT_SHA256,
    expected_record_count: int = EXPECTED_RECORD_COUNT,
    expected_editable_count: int = EXPECTED_EDITABLE_COUNT,
) -> tuple[FixedAudoSlot, ...]:
    """Load all authorized generic rows, excluding the separate Menu Back route."""

    path = report_path.expanduser()
    supplied = path.lstat()
    _require(path.is_file() and not path.is_symlink(),
             "AUDO ownership catalog must be a non-symlink regular file")
    _require(0 < supplied.st_size <= MAX_REPORT_BYTES,
             "AUDO ownership catalog size is outside the product limit")
    payload = path.read_bytes()
    _require(len(payload) == supplied.st_size,
             "AUDO ownership catalog changed while reading")
    if expected_sha256 is not None:
        _require(_digest(payload) == expected_sha256,
                 "AUDO ownership catalog differs from the shipped product version")
    try:
        document = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FixedAudoError("AUDO ownership catalog is invalid JSON") from exc
    _require(isinstance(document, dict) and
             document.get("schema") == CAPACITY_REPORT_SCHEMA,
             "AUDO ownership catalog schema is unsupported")
    records = document.get("records")
    _require(isinstance(records, list) and len(records) == expected_record_count,
             "AUDO ownership catalog record count differs")
    claims = document.get("claims", {})
    _require(
        claims.get("all_850_physical_spans_exact_and_nonoverlapping") is True
        and claims.get("all_850_structurally_encodable_at_same_allocation") is True
        and claims.get("source_modified") is False,
        "AUDO ownership catalog lacks its fixed-allocation/non-overlap proof",
    )
    packs_raw = document.get("source", {}).get("packs")
    _require(isinstance(packs_raw, list), "AUDO ownership catalog has no pack map")
    packs: dict[str, dict[str, Any]] = {}
    for raw in packs_raw:
        _require(isinstance(raw, dict) and isinstance(raw.get("name"), str),
                 "AUDO ownership catalog has an invalid pack row")
        name = raw["name"]
        _require(name not in packs, "AUDO ownership catalog repeats a pack")
        packs[name] = raw

    result: list[FixedAudoSlot] = []
    seen: set[str] = set()
    wrapper_ranges: list[tuple[int, int, str]] = []
    for row in records:
        _require(isinstance(row, dict), "AUDO ownership catalog contains a non-object row")
        key = row.get("key")
        matched = KEY_RE.fullmatch(key) if isinstance(key, str) else None
        _require(matched is not None, "AUDO row has an invalid key")
        outer_index, chunk_index = int(matched.group(1)), int(matched.group(2))
        if (outer_index, chunk_index) == MENU_BACK_SELECTOR:
            continue
        classification = row.get("classification")
        _require(
            classification in GENERIC_CLASSIFICATIONS,
            "Generic AUDO row has an unsupported legacy classification",
        )
        assert isinstance(classification, str)
        stable_id = asset_id(outer_index, chunk_index)
        _require(stable_id not in seen, "Generic AUDO stable ID is duplicated")
        seen.add(stable_id)

        fmt = row.get("format")
        chunk = row.get("chunk")
        hashes = row.get("hashes")
        spans = row.get("absolute_span")
        groups = row.get("groups")
        structural = row.get("structural_import")
        ownership = row.get("ownership")
        _require(all(isinstance(value, dict) for value in
                     (fmt, chunk, hashes, spans, groups, structural, ownership)),
                 f"Generic AUDO metadata is incomplete: {stable_id}")
        assert isinstance(fmt, dict) and isinstance(chunk, dict)
        assert isinstance(hashes, dict) and isinstance(spans, dict)
        assert isinstance(groups, dict) and isinstance(structural, dict)
        assert isinstance(ownership, dict)
        _require(
            groups.get("physical_span_shared") is False
            and structural.get("same_allocation") is True,
            f"Generic AUDO row lost its exact fixed-allocation boundary: {stable_id}",
        )
        _require(
            structural.get("metadata_change_required") is False
            and ownership.get("physical_resource_owner") == "exact outer/chunk/span"
            and ownership.get("fixed_slot_authorization") == "none",
            f"Generic AUDO physical ownership changed: {stable_id}",
        )
        runtime_selector_owner = ownership.get("runtime_selector_owner")
        runtime_visibility = ownership.get("runtime_visibility")
        _require(
            isinstance(runtime_selector_owner, str) and runtime_selector_owner
            and isinstance(runtime_visibility, str) and runtime_visibility,
            f"Generic AUDO runtime caveat metadata is missing: {stable_id}",
        )
        channels = _integer(fmt.get("channels"), "channels", 1)
        sample_rate = _integer(fmt.get("sample_rate"), "sample rate", 1)
        frame_count = _integer(fmt.get("frame_count"), "frame count", 1)
        payload_size = _integer(fmt.get("payload_allocation_bytes"), "payload size", 1)
        system_size = _integer(fmt.get("system_bytes"), "system size", 1)
        tail_size = _integer(fmt.get("tail_bytes"), "tail size")
        block_align = _integer(fmt.get("total_block_align"), "block alignment", 1)
        _require(
            channels in (1, 2)
            and fmt.get("codec_word") == "0x00000011"
            and _integer(fmt.get("block_frames"), "block frames", 1) == BLOCK_FRAMES
            and _integer(fmt.get("channel_block_bytes"), "channel block bytes", 1)
            == CHANNEL_BLOCK_BYTES
            and block_align == channels * CHANNEL_BLOCK_BYTES
            and payload_size % block_align == 0
            and frame_count == payload_size // block_align * BLOCK_FRAMES,
            f"Generic AUDO codec/allocation changed: {stable_id}",
        )
        contract = structural.get("authoring_contract")
        _require(
            contract == {
                "channels": channels,
                "exact_frame_count": frame_count,
                "format": "strict RIFF PCM16LE",
                "metadata_chunks_allowed": False,
                "sample_rate": sample_rate,
            },
            f"Generic AUDO authoring contract changed: {stable_id}",
        )

        pack_span = spans.get("pack")
        xiso_span = spans.get("xiso")
        _require(isinstance(pack_span, dict) and isinstance(xiso_span, dict),
                 f"Generic AUDO physical span is incomplete: {stable_id}")
        pack_path = pack_span.get("path")
        _require(isinstance(pack_path, str) and pack_path.startswith("vc_53450030/"),
                 f"Generic AUDO pack path is invalid: {stable_id}")
        pack_name = pack_path.rsplit("/", 1)[1]
        pack = packs.get(pack_name)
        _require(pack is not None, f"Generic AUDO pack is absent: {stable_id}")
        wrapper_pack_offset = _integer(pack_span.get("start"), "wrapper pack offset")
        wrapper_size = _integer(chunk.get("wrapper_span_bytes"), "wrapper size", 1)
        wrapper_end = _integer(pack_span.get("end"), "wrapper pack end", 1)
        payload_pack_offset = wrapper_pack_offset + HEADER_SIZE + system_size
        xiso_wrapper = _integer(xiso_span.get("start"), "XISO wrapper offset")
        file_extent = _integer(xiso_span.get("file_extent_start"), "XISO pack extent")
        payload_absolute = xiso_wrapper + HEADER_SIZE + system_size
        _require(
            wrapper_end == wrapper_pack_offset + wrapper_size
            and _integer(xiso_span.get("end"), "XISO wrapper end", 1)
            == xiso_wrapper + wrapper_size
            and xiso_span.get("path") == pack_path
            and file_extent + wrapper_pack_offset == xiso_wrapper
            and payload_pack_offset + payload_size + tail_size == wrapper_end
            and HEADER_SIZE + _integer(chunk.get("stored_body_bytes"), "stored body", 1)
            == wrapper_size,
            f"Generic AUDO span arithmetic changed: {stable_id}",
        )
        for field in (
            "payload_sha256", "system_sha256", "tail_sha256",
            "resource_span_sha256", "wrapper_header_sha256",
        ):
            _require(isinstance(hashes.get(field), str) and
                     re.fullmatch(r"[0-9a-f]{64}", hashes[field]) is not None,
                     f"Generic AUDO hash is invalid ({field}): {stable_id}")
        pack_size = _integer(pack.get("size"), "pack size", 1)
        pack_sector = _integer(pack.get("xiso_sector"), "pack sector")
        pack_hash = pack.get("sha256")
        _require(
            isinstance(pack_hash, str) and re.fullmatch(r"[0-9a-f]{64}", pack_hash)
            and _integer(pack.get("xiso_file_offset"), "pack file offset") == file_extent
            and _integer(xiso_span.get("file_sector"), "span pack sector") == pack_sector
            and wrapper_end <= pack_size,
            f"Generic AUDO pack identity changed: {stable_id}",
        )
        wrapper_ranges.append((xiso_wrapper, xiso_wrapper + wrapper_size, stable_id))
        result.append(FixedAudoSlot(
            asset_id=stable_id,
            key=key,
            name=str(row.get("name")),
            classification=classification,
            outer_index=outer_index,
            chunk_index=chunk_index,
            channels=channels,
            sample_rate=sample_rate,
            frame_count=frame_count,
            payload_size=payload_size,
            payload_sha256=str(hashes["payload_sha256"]),
            system_size=system_size,
            system_sha256=str(hashes["system_sha256"]),
            tail_size=tail_size,
            tail_sha256=str(hashes["tail_sha256"]),
            wrapper_pack_offset=wrapper_pack_offset,
            wrapper_size=wrapper_size,
            wrapper_sha256=str(hashes["resource_span_sha256"]),
            wrapper_header_sha256=str(hashes["wrapper_header_sha256"]),
            pack_path=pack_path,
            pack_sector=pack_sector,
            pack_size=pack_size,
            pack_sha256=pack_hash,
            payload_pack_offset=payload_pack_offset,
            payload_absolute_offset=payload_absolute,
            runtime_selector_owner=runtime_selector_owner,
            runtime_visibility=runtime_visibility,
        ))

    wrapper_ranges.sort()
    _require(all(left[1] <= right[0]
                 for left, right in zip(wrapper_ranges, wrapper_ranges[1:])),
             "Generic AUDO wrapper spans overlap")
    _require(len(result) == expected_editable_count,
             "Generic AUDO fixed-slot count differs")
    result.sort(key=lambda item: item.selector)
    return tuple(result)


def slot_map(report_path: Path = CAPACITY_REPORT) -> dict[str, FixedAudoSlot]:
    return {slot.asset_id: slot for slot in load_editable_slots(report_path)}


def parse_strict_wav(payload: bytes, slot: FixedAudoSlot) -> StrictWav:
    """Decode the exact PCM shape required by one fixed physical allocation."""

    _require(44 <= len(payload) <= MAX_WAV_BYTES, "WAV size is outside the input limit")
    _require(payload[:4] == b"RIFF" and payload[8:12] == b"WAVE",
             "input is not RIFF/WAVE")
    _require(struct.unpack_from("<I", payload, 4)[0] + 8 == len(payload),
             "RIFF size does not equal the complete WAV")
    chunks: list[tuple[bytes, bytes]] = []
    offset = 12
    while offset < len(payload):
        _require(offset + 8 <= len(payload), "truncated WAV chunk header")
        kind = payload[offset:offset + 4]
        length = struct.unpack_from("<I", payload, offset + 4)[0]
        start = offset + 8
        end = start + length
        _require(end <= len(payload), "WAV chunk exceeds the RIFF boundary")
        chunks.append((kind, payload[start:end]))
        offset = end + (length & 1)
        _require(offset <= len(payload), "WAV pad byte exceeds the RIFF boundary")
    _require(offset == len(payload), "WAV chunks do not tile the input")
    _require([kind for kind, _ in chunks] == [b"fmt ", b"data"],
             "strict WAV must contain exactly fmt then data; remove metadata chunks")
    fmt, pcm = chunks[0][1], chunks[1][1]
    _require(len(fmt) == 16, "strict WAV fmt chunk must use the 16-byte PCM form")
    tag, channels, rate, byte_rate, block_align, bits = struct.unpack("<HHIIHH", fmt)
    _require(tag == 1, "WAV must use integer PCM format tag 1")
    _require(channels == slot.channels,
             f"WAV must have exactly {slot.channels} channel(s)")
    _require(rate == slot.sample_rate,
             f"WAV must be exactly {slot.sample_rate:,} Hz")
    _require(bits == 16 and block_align == channels * 2 and
             byte_rate == rate * block_align,
             "WAV must be canonical little-endian PCM16")
    expected_pcm = slot.frame_count * slot.channels * 2
    _require(len(pcm) == expected_pcm,
             f"WAV must contain exactly {slot.frame_count:,} frames")
    samples = struct.unpack(f"<{slot.frame_count * slot.channels}h", pcm)
    return StrictWav(channels, rate, slot.frame_count, samples, _digest(pcm))


def read_strict_wav(path: Path, slot: FixedAudoSlot) -> tuple[bytes, StrictWav]:
    payload = path.read_bytes()
    return payload, parse_strict_wav(payload, slot)


def _expand_nibble(predictor: int, index: int, nibble: int) -> tuple[int, int]:
    step = IMA_STEP_TABLE[index]
    difference = step >> 3
    if nibble & 1:
        difference += step >> 2
    if nibble & 2:
        difference += step >> 1
    if nibble & 4:
        difference += step
    predictor = predictor - difference if nibble & 8 else predictor + difference
    predictor = max(-32_768, min(32_767, predictor))
    index = max(0, min(88, index + IMA_INDEX_TABLE[nibble & 7]))
    return predictor, index


def _choose_nibble(target: int, predictor: int, index: int) -> tuple[int, int, int]:
    step = IMA_STEP_TABLE[index]
    delta = target - predictor
    nibble = 8 if delta < 0 else 0
    magnitude = abs(delta)
    if magnitude >= step:
        nibble |= 4
        magnitude -= step
    if magnitude >= step >> 1:
        nibble |= 2
        magnitude -= step >> 1
    if magnitude >= step >> 2:
        nibble |= 1
    decoded, new_index = _expand_nibble(predictor, index, nibble)
    return nibble, decoded, new_index


def _encode_channel_block(samples: tuple[int, ...]) -> bytes:
    _require(len(samples) == BLOCK_FRAMES, "encoder block must contain 64 frames")
    initial_predictor = samples[0]
    best: tuple[int, int, list[int]] | None = None
    for initial_index in range(89):
        predictor = initial_predictor
        index = initial_index
        nibbles: list[int] = []
        squared_error = 0
        for target in samples[1:]:
            nibble, predictor, index = _choose_nibble(target, predictor, index)
            nibbles.append(nibble)
            squared_error += (target - predictor) ** 2
        final_nibble, _, _ = _choose_nibble(samples[-1], predictor, index)
        nibbles.append(final_nibble)
        candidate = squared_error, initial_index, nibbles
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    assert best is not None
    encoded = bytearray(struct.pack("<hH", initial_predictor, best[1]))
    encoded.extend(best[2][index] | (best[2][index + 1] << 4)
                   for index in range(0, 64, 2))
    _require(len(encoded) == CHANNEL_BLOCK_BYTES,
             "encoder emitted the wrong channel-block size")
    return bytes(encoded)


def _encode_vectorised(wav: StrictWav, slot: FixedAudoSlot) -> bytes | None:
    """The same exhaustive search, stepped in bulk. ``None`` if unavailable.

    Every block tries all 89 start indices and keeps the lowest-error one, which
    measures about 3 dB better than carrying the previous block's index forward
    and is not worth trading away.  In scalar Python it costs roughly 11 ms per
    64-frame block, so the longest slot in the corpus -- 370,624 frames of
    stereo -- takes around two minutes, which is far too slow to sit in front of
    a modder.

    ADPCM cannot be vectorised along time, because each sample needs the
    previous predictor.  The 89 candidates and the blocks themselves *are*
    independent, though, and stepping those together turns the whole encode into
    a fixed number of array operations regardless of length.  The output is
    byte-identical to the reference encoder below -- pinned by
    ``tests/mod_editor/test_2k5_fast_ima_matches_scalar.py`` -- so this is purely
    a speed path, and it disappears silently when NumPy is absent, exactly like
    the decoder's fast path in ``nfl2k5_audio_source_scan``.
    """

    try:
        import numpy  # noqa: F401
    except ImportError:
        return None

    tools = str(Path(__file__).resolve().parents[2] / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    try:
        import xbox_ima_encoder
    except ImportError:  # pragma: no cover - lean checkouts without tools/
        return None

    try:
        pcm = struct.pack(f"<{len(wav.samples)}h", *wav.samples)
        return xbox_ima_encoder.encode_stream(pcm, slot.channels)
    except (ValueError, struct.error):
        # Anything the fast path cannot express falls back to the reference
        # encoder rather than failing outright.
        return None


def encode_xbox_ima(wav: StrictWav, slot: FixedAudoSlot) -> bytes:
    _require((wav.channels, wav.sample_rate, wav.frame_count) ==
             (slot.channels, slot.sample_rate, slot.frame_count),
             "WAV shape differs from the selected AUDO slot")
    fast = _encode_vectorised(wav, slot)
    if fast is not None:
        _require(len(fast) == slot.payload_size,
                 "encoded Xbox IMA payload no longer fits the fixed allocation")
        return fast
    chunks: list[bytes] = []
    for first_frame in range(0, slot.frame_count, BLOCK_FRAMES):
        base = first_frame * slot.channels
        for channel in range(slot.channels):
            samples = tuple(
                wav.samples[base + frame * slot.channels + channel]
                for frame in range(BLOCK_FRAMES)
            )
            chunks.append(_encode_channel_block(samples))
    payload = b"".join(chunks)
    _require(len(payload) == slot.payload_size,
             "encoded Xbox IMA payload no longer fits the fixed allocation")
    return payload


def decode_xbox_ima(payload: bytes, slot: FixedAudoSlot) -> tuple[int, ...]:
    block_align = slot.channels * CHANNEL_BLOCK_BYTES
    _require(len(payload) == slot.payload_size and len(payload) % block_align == 0,
             "Xbox IMA payload shape differs from the selected slot")
    output: list[int] = []
    for block_start in range(0, len(payload), block_align):
        decoded_channels: list[list[int]] = []
        for channel in range(slot.channels):
            start = block_start + channel * CHANNEL_BLOCK_BYTES
            predictor, index = struct.unpack_from("<hH", payload, start)
            _require(index <= 88, "Xbox IMA step index exceeds 88")
            decoded = [predictor]
            for value in payload[start + 4:start + CHANNEL_BLOCK_BYTES]:
                for nibble in (value & 0x0F, value >> 4):
                    predictor, index = _expand_nibble(predictor, index, nibble)
                    if len(decoded) < BLOCK_FRAMES:
                        decoded.append(predictor)
            _require(len(decoded) == BLOCK_FRAMES,
                     "Xbox IMA block emitted the wrong frame count")
            decoded_channels.append(decoded)
        for frame in range(BLOCK_FRAMES):
            for channel in range(slot.channels):
                output.append(decoded_channels[channel][frame])
    _require(len(output) == slot.frame_count * slot.channels,
             "Xbox IMA payload decoded to the wrong sample count")
    return tuple(output)


def quality(source: tuple[int, ...], decoded: tuple[int, ...], slot: FixedAudoSlot) \
        -> dict[str, Any]:
    count = slot.frame_count * slot.channels
    _require(len(source) == len(decoded) == count, "quality sample count differs")
    errors = [left - right for left, right in zip(source, decoded, strict=True)]
    squared_error = sum(value * value for value in errors)
    signal_square = sum(value * value for value in source)
    snr = None
    if squared_error and signal_square:
        snr = 10.0 * math.log10(signal_square / squared_error)
    predictor_indices = (
        frame * slot.channels + channel
        for frame in range(0, slot.frame_count, BLOCK_FRAMES)
        for channel in range(slot.channels)
    )
    return {
        "channel_count": slot.channels,
        "frame_count": slot.frame_count,
        "sample_count": count,
        "squared_error_sum": squared_error,
        "maximum_absolute_error": max(abs(value) for value in errors),
        "rmse": math.sqrt(squared_error / count),
        "signal_rms": math.sqrt(signal_square / count),
        "snr_db": snr,
        "lossless_pcm": squared_error == 0,
        "block_predictor_samples_exact": all(
            source[index] == decoded[index] for index in predictor_indices
        ),
    }


def validate_source_wrapper(wrapper: bytes, slot: FixedAudoSlot) -> None:
    """Bind one catalog row to its complete retail wrapper before patching."""

    _require(len(wrapper) == slot.wrapper_size and
             _digest(wrapper) == slot.wrapper_sha256,
             "retail AUDO wrapper identity differs")
    _require(wrapper[:4] == b"AUDO" and
             _digest(wrapper[:HEADER_SIZE]) == slot.wrapper_header_sha256,
             "retail AUDO wrapper header differs")
    stored, system, payload_size, magic, scratch, reserved0, reserved1 = \
        struct.unpack_from("<7I", wrapper, 4)
    _require(
        stored + HEADER_SIZE == slot.wrapper_size
        and system == slot.system_size
        and payload_size == slot.payload_size
        and (magic, scratch, reserved0, reserved1) == (0, 0, 0, 0),
        "retail AUDO wrapper allocation fields differ",
    )
    body = wrapper[HEADER_SIZE:]
    system_bytes = body[:slot.system_size]
    payload = body[slot.system_size:slot.system_size + slot.payload_size]
    tail = body[slot.system_size + slot.payload_size:]
    _require(
        _digest(system_bytes) == slot.system_sha256
        and _digest(payload) == slot.payload_sha256
        and len(tail) == slot.tail_size
        and _digest(tail) == slot.tail_sha256,
        "retail AUDO system/payload/tail identity differs",
    )


__all__ = [
    "CAPACITY_REPORT",
    "CAPACITY_REPORT_SHA256",
    "EDITABLE_CLASSIFICATION",
    "EXPECTED_EDITABLE_COUNT",
    "EXPECTED_GENERIC_SLOT_COUNT",
    "EXPECTED_LEGACY_CLASSIFIED_COUNT",
    "FixedAudoError",
    "FixedAudoSlot",
    "StrictWav",
    "asset_id",
    "decode_xbox_ima",
    "encode_xbox_ima",
    "generic_fixed_slot_warning",
    "load_editable_slots",
    "parse_strict_wav",
    "quality",
    "slot_map",
    "validate_source_wrapper",
]

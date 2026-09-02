#!/usr/bin/env python3
"""Encode PCM16 into the Xbox IMA ADPCM that NFL 2K5 stores in every AUDO.

All 850 standalone NFL 2K5 AUDO records carry codec word ``0x00000011`` and the
36-byte-per-channel Xbox IMA block, so this is the one codec that stands between
a modder's audio file and the game.  Unlike the Xbox 360's XMA1 -- which has no
open encoder anywhere and forces APF 2K8 to borrow a user-supplied one -- IMA
ADPCM is fully specified, so 2K5 needs nothing external.  That is the whole
reason this module exists: it makes 2K5 audio replacement self-contained.

**Search strategy.**  A block stores its first sample verbatim plus a starting
step index, and every later sample is a 4-bit delta against a running predictor.
The starting index is a free choice, and it matters: searching all 89 rather
than carrying the previous block's index forward measures ~3 dB better SNR on
both tonal and transient material.  Three dB of an already-lossy 4-bit codec is
not something to give away for speed, so the exhaustive search is kept.

Doing it naively costs ~11 ms per 64-frame block -- around 110 s for a
30-second sound, which no GUI can sit through.  The fix is not a cheaper search
but a better-shaped one.  ADPCM cannot vectorise along time, because each
sample needs the previous predictor.  It vectorises beautifully along two other
axes that are genuinely independent: the 89 candidate start indices, and every
block in the stream (each block re-seeds from its own first sample).  Stepping
``blocks x 89`` together turns the whole encode into 63 array operations no
matter how long the sound is, and measures ~24x faster while producing
byte-identical output.

``encode_stream`` therefore prefers NumPy and falls back to an exact scalar
encoder, mirroring ``decode_xbox_ima_batch`` in
``mod_editor/core/nfl2k5_audio_source_scan.py``.  The two paths are pinned
against each other by ``tests/test_xbox_ima_encoder.py``; they must agree
byte-for-byte, not merely sound alike.
"""

from __future__ import annotations

import struct

CHANNEL_BLOCK_BYTES = 36
BLOCK_FRAMES = 64
NIBBLES_PER_BLOCK = 64
START_INDEX_CANDIDATES = 89
MAX_STEP_INDEX = 88

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


class XboxImaEncodeError(ValueError):
    """The supplied PCM cannot be encoded into whole Xbox IMA blocks."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise XboxImaEncodeError(message)


def block_align(channels: int) -> int:
    """Bytes one time block occupies for this channel count."""

    _require(channels in (1, 2), "Xbox IMA supports exactly one or two channels")
    return CHANNEL_BLOCK_BYTES * channels


def encoded_size(frame_count: int, channels: int) -> int:
    """Bytes ``frame_count`` frames will occupy once encoded."""

    _require(channels in (1, 2), "Xbox IMA supports exactly one or two channels")
    _require(
        frame_count >= 0 and frame_count % BLOCK_FRAMES == 0,
        f"Xbox IMA frame count must be a non-negative multiple of {BLOCK_FRAMES}",
    )
    return (frame_count // BLOCK_FRAMES) * block_align(channels)


def frames_for_payload(payload_size: int, channels: int) -> int:
    """How many PCM frames a payload of this size decodes to."""

    align = block_align(channels)
    _require(
        payload_size >= 0 and payload_size % align == 0,
        "Xbox IMA payload does not contain whole time blocks",
    )
    return (payload_size // align) * BLOCK_FRAMES


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
    index = max(0, min(MAX_STEP_INDEX, index + IMA_INDEX_TABLE[nibble & 7]))
    return predictor, index


def _choose_nibble(target: int, predictor: int, index: int) -> tuple[int, int, int]:
    step = IMA_STEP_TABLE[index]
    delta = target - predictor
    nibble = 8 if delta < 0 else 0
    magnitude = -delta if delta < 0 else delta
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


def encode_block_scalar(samples) -> bytes:
    """One 64-frame block, searching every start index. The reference path.

    A block holds 64 nibbles but only 63 of them become output frames: the first
    frame is the stored predictor, and the trailing nibble advances state that
    nothing reads.  It still has to be written, and the decoder in
    ``nfl2k5_audio_source_scan`` consumes it as padding, so it is emitted here
    the same way -- by re-coding the final sample.
    """

    _require(len(samples) == BLOCK_FRAMES, "Xbox IMA block frame count differs")
    initial_predictor = int(samples[0])
    _require(
        -32_768 <= initial_predictor <= 32_767,
        "PCM sample outside the signed 16-bit range",
    )

    best: tuple[int, int, list[int]] | None = None
    for initial_index in range(START_INDEX_CANDIDATES):
        predictor = initial_predictor
        index = initial_index
        nibbles: list[int] = []
        squared_error = 0
        for target in samples[1:]:
            nibble, predictor, index = _choose_nibble(int(target), predictor, index)
            nibbles.append(nibble)
            error = int(target) - predictor
            squared_error += error * error
        final_nibble, _, _ = _choose_nibble(int(samples[-1]), predictor, index)
        nibbles.append(final_nibble)
        candidate = (squared_error, initial_index, nibbles)
        if best is None or candidate[:2] < best[:2]:
            best = candidate

    assert best is not None
    encoded = bytearray(struct.pack("<hH", initial_predictor, best[1]))
    nibbles = best[2]
    _require(len(nibbles) == NIBBLES_PER_BLOCK, "Xbox IMA nibble count differs")
    encoded.extend(
        nibbles[position] | (nibbles[position + 1] << 4)
        for position in range(0, NIBBLES_PER_BLOCK, 2)
    )
    _require(len(encoded) == CHANNEL_BLOCK_BYTES, "Xbox IMA block size differs")
    return bytes(encoded)


def _encode_channel_scalar(samples, progress=None) -> list[bytes]:
    total = len(samples) // BLOCK_FRAMES
    blocks: list[bytes] = []
    for number, offset in enumerate(range(0, len(samples), BLOCK_FRAMES)):
        blocks.append(encode_block_scalar(samples[offset:offset + BLOCK_FRAMES]))
        if progress is not None and number % 32 == 0:
            progress(number, total)
    return blocks


def _encode_channel_numpy(samples, progress=None) -> list[bytes]:
    """Every block and every start index advanced together.

    Shapes are ``(blocks, 89)`` for the running state and ``(blocks, 89, 64)``
    for the nibbles, so the only sequential axis left is the 63 samples inside a
    block.
    """

    import numpy as np

    data = np.asarray(samples, dtype=np.int32)
    blocks = data.reshape(-1, BLOCK_FRAMES)
    count = blocks.shape[0]
    if count == 0:
        return []

    steps = np.asarray(IMA_STEP_TABLE, dtype=np.int32)
    adjustments = np.asarray(IMA_INDEX_TABLE, dtype=np.int32)

    predictor = np.repeat(
        blocks[:, :1].astype(np.int32), START_INDEX_CANDIDATES, axis=1
    )
    index = np.tile(
        np.arange(START_INDEX_CANDIDATES, dtype=np.int32), (count, 1)
    )
    squared_error = np.zeros((count, START_INDEX_CANDIDATES), dtype=np.int64)
    nibbles = np.zeros(
        (count, START_INDEX_CANDIDATES, NIBBLES_PER_BLOCK), dtype=np.uint8
    )

    def code(target_column):
        """Greedy 3-bit magnitude plus sign, exactly as ``_choose_nibble``."""

        target = target_column[:, None]
        step = steps[index]
        delta = target - predictor
        magnitude = np.abs(delta)

        nibble = np.where(delta < 0, 8, 0).astype(np.int32)

        take_step = magnitude >= step
        nibble += np.where(take_step, 4, 0)
        magnitude = magnitude - np.where(take_step, step, 0)

        half = step >> 1
        take_half = magnitude >= half
        nibble += np.where(take_half, 2, 0)
        magnitude = magnitude - np.where(take_half, half, 0)

        quarter = step >> 2
        nibble += np.where(magnitude >= quarter, 1, 0)
        return nibble, step, half, quarter, target

    for position in range(1, BLOCK_FRAMES):
        nibble, step, half, quarter, target = code(blocks[:, position])
        nibbles[:, :, position - 1] = nibble.astype(np.uint8)

        difference = step >> 3
        difference = difference + np.where(nibble & 1, quarter, 0)
        difference = difference + np.where(nibble & 2, half, 0)
        difference = difference + np.where(nibble & 4, step, 0)

        predictor = np.where(
            nibble & 8, predictor - difference, predictor + difference
        )
        np.clip(predictor, -32_768, 32_767, out=predictor)
        index = np.clip(index + adjustments[nibble & 7], 0, MAX_STEP_INDEX)

        error = (target - predictor).astype(np.int64)
        squared_error += error * error

        if progress is not None and position % 8 == 0:
            progress(position, BLOCK_FRAMES)

    # The trailing nibble re-codes the last sample and advances nothing.
    nibble, _, _, _, _ = code(blocks[:, BLOCK_FRAMES - 1])
    nibbles[:, :, NIBBLES_PER_BLOCK - 1] = nibble.astype(np.uint8)

    # ``argmin`` returns the first minimum and candidates sit in start-index
    # order, so this reproduces the scalar tie-break: lowest squared error, then
    # lowest start index.
    best = np.argmin(squared_error, axis=1)
    chosen = nibbles[np.arange(count), best]

    packed = (chosen[:, 0::2] | (chosen[:, 1::2] << 4)).astype(np.uint8)

    predictors = (blocks[:, 0].astype(np.int64) & 0xFFFF).astype(np.int64)
    indices = best.astype(np.int64) & 0xFFFF
    header = np.empty((count, 4), dtype=np.uint8)
    header[:, 0] = (predictors & 0xFF).astype(np.uint8)
    header[:, 1] = ((predictors >> 8) & 0xFF).astype(np.uint8)
    header[:, 2] = (indices & 0xFF).astype(np.uint8)
    header[:, 3] = ((indices >> 8) & 0xFF).astype(np.uint8)

    encoded = np.concatenate([header, packed], axis=1)
    raw = encoded.tobytes()
    return [
        raw[offset:offset + CHANNEL_BLOCK_BYTES]
        for offset in range(0, len(raw), CHANNEL_BLOCK_BYTES)
    ]


def encode_stream(pcm: bytes, channels: int, *, progress=None,
                  prefer_numpy: bool = True) -> bytes:
    """Encode interleaved PCM16 into Xbox IMA.

    ``pcm`` is little-endian interleaved PCM16, the shape every consumer here
    already speaks.  Channels are encoded independently and their 36-byte blocks
    are then interleaved channel-major within each time block, which is the
    layout ``decode_xbox_ima_batch`` reads back.
    """

    _require(isinstance(pcm, (bytes, bytearray)), "PCM input must be bytes")
    _require(channels in (1, 2), "Xbox IMA supports exactly one or two channels")
    frame_bytes = 2 * channels
    _require(len(pcm) % frame_bytes == 0, "PCM does not contain whole frames")
    frame_count = len(pcm) // frame_bytes
    _require(
        frame_count > 0 and frame_count % BLOCK_FRAMES == 0,
        f"PCM frame count must be a positive multiple of {BLOCK_FRAMES}; "
        f"got {frame_count}",
    )

    samples = struct.unpack(f"<{frame_count * channels}h", bytes(pcm))
    per_channel = [samples[channel::channels] for channel in range(channels)]

    encoder = _encode_channel_scalar
    if prefer_numpy:
        try:
            import numpy  # noqa: F401
        except ImportError:
            pass
        else:
            encoder = _encode_channel_numpy

    encoded_channels = [encoder(stream, progress) for stream in per_channel]
    block_count = frame_count // BLOCK_FRAMES
    for stream in encoded_channels:
        _require(len(stream) == block_count, "encoded block count differs")

    out = bytearray()
    for time_block in range(block_count):
        for stream in encoded_channels:
            out.extend(stream[time_block])

    _require(
        len(out) == encoded_size(frame_count, channels),
        "encoded payload size differs from the computed size",
    )
    return bytes(out)


def decode_stream(payload: bytes, channels: int) -> bytes:
    """Decode Xbox IMA back to interleaved PCM16.

    Present so an encode can be checked against what the game will actually
    hear, without importing the editor's scanner (which authenticates a pinned
    XISO and is the wrong tool for a loose buffer).
    """

    align = block_align(channels)
    _require(
        payload and len(payload) % align == 0,
        "Xbox IMA payload does not contain whole time blocks",
    )

    frames: list[list[int]] = []
    for offset in range(0, len(payload), align):
        columns: list[list[int]] = []
        for channel in range(channels):
            start = offset + channel * CHANNEL_BLOCK_BYTES
            predictor, index = struct.unpack_from("<hH", payload, start)
            _require(index <= MAX_STEP_INDEX, "encoded IMA step index exceeds 88")
            values = [predictor]
            emitted = 1
            for value in payload[start + 4:start + CHANNEL_BLOCK_BYTES]:
                for nibble in (value & 0x0F, value >> 4):
                    predictor, index = _expand_nibble(predictor, index, nibble)
                    if emitted < BLOCK_FRAMES:
                        values.append(predictor)
                        emitted += 1
            _require(emitted == BLOCK_FRAMES, "IMA block emitted frame count differs")
            columns.append(values)
        for position in range(BLOCK_FRAMES):
            frames.append([column[position] for column in columns])

    flat = [value for frame in frames for value in frame]
    return struct.pack(f"<{len(flat)}h", *flat)

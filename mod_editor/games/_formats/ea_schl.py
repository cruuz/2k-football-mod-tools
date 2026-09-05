"""EA's ``SCHl`` audio stream and ``BNKl`` sound bank, measured on Madden NFL 09 (PS2).

Every sound Madden NFL 09 (PS2) plays arrives through one of two shapes, and
both live inside the ``TERF`` containers :mod:`.ea_terf` already walks:

* an **``SCHl`` stream** -- a chunk chain ``SCHl`` (header) -> ``SCCl`` (block
  count) -> ``SCDl`` x N (audio blocks) -> ``SCEl`` (end).  A container member
  holds one or more of them, back to back, zero-padded between [M].
* a **``BNKl`` bank** -- one member holding a small directory of sounds, each
  with its own platform-tagged header and a flat run of PlayStation ADPCM [M].

**Evidence tags.**  **[M]** measured on the retail Madden NFL 09 (USA) disc
(SLUS-21770, boot ELF CRC 38014255), read-only; **[S]** sourced from a
reference outside this repository; **[A]** assumed, and said so.

What was measured, and how much of it
-------------------------------------
34,046 ``SCHl`` streams inside 11,389 container members across six containers
(``BGM.DAT`` 47, ``SOUNDDAT.DAT`` 248, ``SPCHDATA.DAT`` 16,626,
``SPCHFEDT.DAT`` 167, ``SPCHMAD1.DAT`` 12,475, ``SPCHMAD2.DAT`` 4,483), and
301 ``BNKl`` banks holding 967 sounds, all in ``SOUNDDAT.DAT`` [M].  Every one
of the 34,046 headers parses to a terminated tag list carrying a sample count,
and for every one of them the per-block sample counts sum to exactly that
number -- zero counter-examples [M].

The platform-tagged header
--------------------------
``SCHl``'s payload opens with a platform tag, and the tag decides both where
the tag list starts and how the *blocks* are byte-ordered [M]:

===========  =====================  ==================  =========
tag          bytes                  tag list starts at  block ints
===========  =====================  ==================  =========
``GSTR``     ``47 53 54 52`` + 4    chunk + 16          big-endian
``PT``       ``50 54`` + u16 LE     chunk + 12          little-endian
===========  =====================  ==================  =========

27,886 streams carry ``GSTR`` and 6,160 carry ``PT`` with platform code 5.
The endianness rule was not assumed: for each stream the ``SCCl`` block count
was read both ways and compared with the blocks actually walked, and the
matching order agreed with the platform tag in 34,046 of 34,046 [M].  Platform
code 5 is EA's PlayStation 2 [A] -- consistent with the disc, not proved by it.

The tag list is a flat sequence of ``tag`` bytes.  Four tags take no value
(``0xFC``, ``0xFD``, ``0xFE``, ``0xFF``); every other tag is followed by a
length byte and that many big-endian value bytes, and a length byte of
``0xFF`` escapes to a 4-byte big-endian length [M].  The escape is not a
nicety: 527 headers carry a tag ``0x14`` blob of 960 to 1,386 bytes, and a parser
without it mis-reads every one of them.

Tags measured on this disc, with counts over the 34,046 stream headers:

=====  ======  ==========================================================
tag    count   meaning
=====  ======  ==========================================================
0x06   34046   constant 101 on every stream; role not established [A]
0x0B     134   constant 2; role not established [A]
0x13    3863   constant 127; role not established [A]
0x14     527   variable-length blob, first four bytes a FourCC
               (``EMXP`` 525, ``CNYS`` 2); contents not established [A]
0x80   33896   version: 3 (33,883) or 2 (13) [M]
0x82     282   channel count; absent means 1 [M]
0x84   33487   sample rate in Hz [M]
0x85   34046   sample count, per channel [M]
0x88       -   offset of the sound's data (banks only) [M]
0x8C    6160   constant 4, on exactly the 6,160 ``PT`` streams [M]
0xA0   33896   codec: 4 (33,751) or 10 (145) [M]
0xFC    1054   no value; padding between tags [M]
0xFD   34046   no value; opens the info block [M]
0xFF   34046   no value; ends the header [M]
=====  ======  ==========================================================

``0x85`` is per channel: a stereo stream's decoded PCM holds
``sample_count * channels`` samples [M].

The codecs, and which of them this module decodes
-------------------------------------------------
======================  =======  ====================================
codec (tag ``0xA0``)    streams  what it is
======================  =======  ====================================
4                        33,751  a ~10:1 speech codec, **not decoded here**
10                          145  EA-XA ADPCM, decoded and encoded
absent                      150  EA-XA ADPCM, decoded and encoded
======================  =======  ====================================

Codec 4 carries 1.706 bits per sample over all 33,751 of them and
3,317,735,806 samples [M], which is a ~9.4:1 codec, and ffmpeg's ``ea``
demuxer refuses it by name (``revision2=4 is not implemented``) [M].  EA's speech codec of this
era is MicroTalk, and community tooling maps EA codec 4 to MicroTalk 10:1
[S].  No decoder for it exists in ffmpeg, so nothing here could be checked
against anything, and a codec written blind is a claim, not a decoder:
the lane refuses codec 4 with that sentence and
catalogues the sound anyway.  The other 295
streams -- every one of ``BGM.DAT`` and ``SOUNDDAT.DAT`` -- decode.

The ``SCDl`` block, and the EA-XA frame
--------------------------------------
A block's payload is ``[samples u32][data offset u32 per channel][data]``,
each channel's offset counted from ``(channels + 1) * 4`` bytes into the
payload, in the stream's byte order [M].  A channel's run is a sequence of
28-sample frames, and the frame comes in two shapes [M]:

* a control byte other than ``0xEE``: coefficient index in the high nibble,
  ``shift = 20 - low nibble``, then 14 bytes of two 4-bit residuals each, high
  nibble first.  ``next = clip16(((residual << shift) + c1 * s1 + c2 * s2) >>
  8)``, with ``(c1, c2)`` from the four-entry table below;
* a control byte of ``0xEE``: two big-endian ``int16`` predictor values, then
  28 big-endian ``int16`` samples, verbatim.  The raw samples are big-endian
  **whatever the stream's byte order is** -- the little-endian streams read
  them big-endian too, and reading them the stream's way byte-swaps every one
  [M].

The predictor state carries across frames and across blocks [M]; a channel's
run is padded to an even byte count [M].

The bank
--------
``BNKl`` is ``'BNKl'``, ``u16`` version (5 on every one of the 301 banks
[M]), ``u16`` sound count, ``u32`` header size, ``u32`` data size, ``u32``
zero, then one ``u32`` per sound.  ``header size + data size`` equals the
member's stored length in 301 of 301 [M].  **Each offset is counted from its
own slot**, not from the table -- the natural reading finds a header for the
first sound and garbage for the rest [M].  Each sound's header is a ``PT``
platform header whose tag ``0x88`` gives the offset of its data inside the
member [M].

**A stereo bank sound is planar, not frame-interleaved** [M].  Tag ``0x89``
is present on exactly the 183 stereo sounds of the retail disc and on none of
the 784 mono ones, and on all 183 it equals ``0x88`` plus half the sound's
data length: it is the offset of the **second channel's run**.  Two further
measurements say the same thing: every one of the 183 carries a non-zero VAG
flag byte in the frame just before that offset and in its last frame -- the
end of each channel's run -- and decoding the two runs as channels gives a
left/right correlation that beats the interleaved reading on 181 of 183
(often exactly 1.0, a mono sound stored twice).  An earlier reading of this
module had the frames alternating; it decoded each frame correctly and put
them in the wrong channels.

Bank sounds are **Sony PlayStation ADPCM** (VAG): 962 of 962 sounds whose
length can be derived carry exactly 0.5714 bytes per sample, which is 16 bytes
per 28 samples, and the second byte of every 16-byte frame is the VAG flag
byte (0 on 6,260 frames of the sample measured, 1 on 2) [M].  The frame is a
shift/filter byte, a flag byte, then 14 bytes of two residuals each, **low
nibble first**; ``next = (residual << 12 >> shift) + (s1 * f0 + s2 * f1) /
64``, the division truncating toward zero, and the predictor state keeps the
**unclipped** value while the sample emitted is clipped [M] -- both were
derived from ffmpeg's own output rather than assumed, and both matter: an
arithmetic shift instead of the truncating divide is wrong on half the
samples, and clipping the state is wrong wherever a sound saturates.

Standard library only; importable without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import array
import math
import struct
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games.contract import Refusal

# --------------------------------------------------------------------------
# Chunk vocabulary
# --------------------------------------------------------------------------

SCHL_MAGIC = b"SCHl"
SCCL_MAGIC = b"SCCl"
SCDL_MAGIC = b"SCDl"
SCEL_MAGIC = b"SCEl"
BNKL_MAGIC = b"BNKl"

#: The chunk tags a stream's chain is allowed to use.  Anything else ends the
#: walk rather than being guessed at.
STREAM_CHUNKS = (SCHL_MAGIC, SCCL_MAGIC, SCDL_MAGIC, SCEL_MAGIC)

CHUNK_HEADER_SIZE = 8

PLATFORM_GSTR = "GSTR"
PLATFORM_PT = "PT"

#: Where the tag list starts, counted from the ``SCHl`` chunk's own offset.
_TAGS_AT = {PLATFORM_GSTR: 16, PLATFORM_PT: 12}

#: ``True`` when the platform tag means big-endian block integers.  Measured
#: on 34,046 of 34,046 streams against the ``SCCl`` block count [M].
_BIG_ENDIAN = {PLATFORM_GSTR: True, PLATFORM_PT: False}

# --------------------------------------------------------------------------
# The tag list
# --------------------------------------------------------------------------

TAG_VERSION = 0x80
TAG_CHANNELS = 0x82
TAG_CODEC1 = 0x83
TAG_SAMPLE_RATE = 0x84
TAG_SAMPLE_COUNT = 0x85
TAG_LOOP_START = 0x86
TAG_LOOP_END = 0x87
TAG_DATA_OFFSET = 0x88
#: Present on exactly the stereo bank sounds, where it is the offset of the
#: second channel's run [M]; the older name is kept for callers that used it.
TAG_SECOND_CHANNEL = 0x89
TAG_LOOP_OFFSET = TAG_SECOND_CHANNEL
TAG_END_OFFSET = 0x8A
TAG_FLAGS = 0x8C
TAG_CODEC = 0xA0
TAG_PAD = 0xFC
TAG_INFO = 0xFD
TAG_INFO_ALT = 0xFE
TAG_END = 0xFF

#: Tags that carry no value byte at all [M].
VALUELESS_TAGS = frozenset({TAG_PAD, TAG_INFO, TAG_INFO_ALT, TAG_END})

#: A length byte of this value escapes to a 4-byte big-endian length [M].
LENGTH_ESCAPE = 0xFF

#: The longest value this module will read for one tag.  The largest measured
#: is a 1,386-byte ``0x14`` blob; the cap keeps a corrupt length from asking
#: for a gigabyte.
MAX_TAG_VALUE = 1 << 16

#: What each tag was measured to mean, for the catalogue and the document.
#: A tag whose value never varied on this disc says so, and says that its role
#: is not established rather than inventing one.
TAG_MEANINGS: Mapping[int, str] = {
    0x06: "constant 101 on every stream; role not established",
    0x08: "present in bank sounds; role not established",
    0x09: "present in bank sounds; role not established",
    0x0A: "present in bank sounds; role not established",
    0x0B: "constant 2; role not established",
    0x0E: "present in bank sounds; role not established",
    0x13: "constant 127; role not established",
    0x14: "variable-length blob opening with a FourCC; contents not established",
    TAG_VERSION: "version (2 or 3)",
    TAG_CHANNELS: "channel count; absent means 1",
    TAG_CODEC1: "codec, first form; not seen on this disc",
    TAG_SAMPLE_RATE: "sample rate in Hz",
    TAG_SAMPLE_COUNT: "sample count, per channel",
    TAG_LOOP_START: "loop start sample (banks)",
    TAG_LOOP_END: "loop end sample (banks)",
    TAG_DATA_OFFSET: "offset of this sound's data inside the bank member",
    TAG_SECOND_CHANNEL: "offset of the second channel's data: stereo bank sounds are "
                        "planar, and this tag is on exactly the stereo ones",
    TAG_END_OFFSET: "constant 0 on every bank sound of this disc; role not established",
    TAG_FLAGS: "constant 4 on every PT stream; role not established",
    TAG_CODEC: "codec (4 = a ~10:1 speech codec, 10 = EA-XA ADPCM)",
    TAG_PAD: "no value; padding between tags",
    TAG_INFO: "no value; opens the info block",
    TAG_INFO_ALT: "no value; seen only in banks",
    TAG_END: "no value; ends the header",
}

# --------------------------------------------------------------------------
# Codecs
# --------------------------------------------------------------------------

#: Tag ``0xA0`` value for EA-XA ADPCM [M].  A stream with no ``0xA0`` at all
#: decodes the same way: all 150 of them are 22,050 Hz ``GSTR`` streams whose
#: blocks parse and decode as EA-XA, byte for byte against ffmpeg [M].
CODEC_EAXA = 10

#: Tag ``0xA0`` value for the speech codec this module refuses [M].
CODEC_SPEECH = 4

CODEC_NAMES: Mapping[Optional[int], str] = {
    CODEC_EAXA: "EA-XA ADPCM",
    CODEC_SPEECH: "MicroTalk (EA speech, ~10:1)",
    None: "EA-XA ADPCM",
}

#: Why codec 4 is refused, in the sentence the page shows.
SPEECH_REFUSAL = (
    "this sound is stored in EA's MicroTalk speech codec (header codec 4), and this "
    "module has no decoder for it: ffmpeg carries none either, so a decoder written "
    "here could not be checked against anything and would be a guess wearing a "
    "result's clothes. The sound's rate, channel count and length are catalogued; "
    "its audio is not decoded."
)

#: EA-XA's two predictor coefficients per index.  Indices 0..3 are the only
#: ones this disc uses (measured over every frame of all 295 decodable
#: streams); a frame naming a higher index is refused rather than guessed.
EAXA_COEFFICIENTS: Tuple[Tuple[int, int], ...] = (
    (0, 0), (240, 0), (460, -208), (392, -220),
)

#: The control byte that introduces a verbatim 28-sample frame [M].
EAXA_RAW_FRAME = 0xEE

#: The header version (tag ``0x80``) whose blocks carry their own predictor
#: values -- two little-endian ``int16`` at the head of each channel's run --
#: instead of carrying the predictor across blocks [M].  13 streams of the
#: retail disc, all in ``SOUNDDAT.DAT``; ffmpeg calls them ``adpcm_ea_r1``.
EAXA_VERSION_PER_BLOCK_STATE = 2

EAXA_SAMPLES_PER_FRAME = 28
EAXA_FRAME_BYTES = 15
EAXA_RAW_FRAME_BYTES = 1 + 2 + 2 + 2 * EAXA_SAMPLES_PER_FRAME

#: Sony PS ADPCM's four predictor filters, scaled by 64 [S: the format's own
#: constants], each confirmed here by solving for them against ffmpeg's output
#: over 123,088 samples with zero residual error [M].
PSX_FILTERS: Tuple[Tuple[int, int], ...] = (
    (0, 0), (60, 0), (115, -52), (98, -55), (122, -60),
)
PSX_FRAME_BYTES = 16
PSX_SAMPLES_PER_FRAME = 28

#: How many samples one ``SCDl`` block carries when this module writes one.
#: The retail blocks run 1,876 to 7,344 samples [M]; 4,480 is a whole number
#: of 28-sample frames inside that range.
DEFAULT_BLOCK_SAMPLES = 4480


class SchlError(Refusal):
    """This module could not read what it was pointed at; the sentence says why."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise SchlError(message)


def _clip16(value: int) -> int:
    if value < -32768:
        return -32768
    if value > 32767:
        return 32767
    return value


# --------------------------------------------------------------------------
# The tag list
# --------------------------------------------------------------------------

def parse_tags(data: bytes) -> Tuple[Tuple[int, Optional[int], Optional[bytes]], ...]:
    """``(tag, value, blob)`` for each tag in *data*, stopping after ``0xFF``.

    ``value`` is the big-endian integer for a value of eight bytes or fewer and
    ``None`` for a longer one; ``blob`` is the raw bytes whenever there are any.
    A truncated tag ends the walk instead of raising: a header is a fixed-size
    chunk and its tail is padding.
    """

    out: List[Tuple[int, Optional[int], Optional[bytes]]] = []
    position = 0
    limit = len(data)
    while position < limit:
        tag = data[position]
        position += 1
        if tag in VALUELESS_TAGS:
            out.append((tag, None, None))
            if tag == TAG_END:
                break
            continue
        if position >= limit:
            break
        length = data[position]
        position += 1
        if length == LENGTH_ESCAPE:
            if position + 4 > limit:
                break
            length = int.from_bytes(data[position:position + 4], "big")
            position += 4
        if length > MAX_TAG_VALUE or position + length > limit:
            break
        blob = bytes(data[position:position + length])
        position += length
        value = int.from_bytes(blob, "big") if length <= 8 else None
        out.append((tag, value, blob))
    return tuple(out)


# --------------------------------------------------------------------------
# Stream headers
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class StreamHeader:
    """One ``SCHl`` header, as the bytes have it."""

    offset: int
    header_size: int
    platform: str
    platform_code: Optional[int]
    big_endian: bool
    tags: Tuple[Tuple[int, Optional[int], Optional[bytes]], ...]

    def value(self, tag: int) -> Optional[int]:
        for candidate, value, _blob in self.tags:
            if candidate == tag:
                return value
        return None

    @property
    def version(self) -> Optional[int]:
        return self.value(TAG_VERSION)

    @property
    def codec(self) -> Optional[int]:
        return self.value(TAG_CODEC)

    @property
    def codec_name(self) -> str:
        return CODEC_NAMES.get(self.codec, f"unknown codec {self.codec}")

    @property
    def channels(self) -> int:
        return int(self.value(TAG_CHANNELS) or 1)

    @property
    def sample_rate(self) -> Optional[int]:
        rate = self.value(TAG_SAMPLE_RATE)
        return int(rate) if rate else None

    @property
    def sample_count(self) -> int:
        return int(self.value(TAG_SAMPLE_COUNT) or 0)

    @property
    def decodable(self) -> bool:
        return self.codec in (None, CODEC_EAXA)

    @property
    def seconds(self) -> Optional[float]:
        rate = self.sample_rate
        if not rate:
            return None
        return self.sample_count / float(rate)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "platform_code": self.platform_code,
            "big_endian": self.big_endian,
            "header_size": self.header_size,
            "version": self.version,
            "codec": self.codec,
            "codec_name": self.codec_name,
            "channels": self.channels,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "tags": [tag for tag, _value, _blob in self.tags],
        }


@dataclass(frozen=True)
class Block:
    """One ``SCDl`` block: where it is, how long, and how many samples it carries."""

    offset: int
    size: int
    samples: int


@dataclass(frozen=True)
class Stream:
    """One ``SCHl`` .. ``SCEl`` run inside a container member."""

    index: int
    offset: int
    length: int
    header: StreamHeader
    blocks: Tuple[Block, ...] = ()
    declared_blocks: Optional[int] = None
    complete: bool = True

    @property
    def block_samples(self) -> int:
        return sum(block.samples for block in self.blocks)


def parse_stream_header(data: Any, offset: int, limit: int) -> StreamHeader:
    """The ``SCHl`` header at *offset*, or a refusal naming what was there."""

    _require(offset + CHUNK_HEADER_SIZE <= limit,
             f"there is no room for an SCHl header at byte {offset}.")
    magic = bytes(data[offset:offset + 4])
    _require(magic == SCHL_MAGIC,
             f"byte {offset} holds {magic!r}, not {SCHL_MAGIC!r}; this is not an EA "
             f"audio stream.")
    header_size, = struct.unpack_from("<I", data, offset + 4)
    _require(CHUNK_HEADER_SIZE + 4 <= header_size <= 65536 and offset + header_size <= limit,
             f"the SCHl header at byte {offset} declares itself {header_size} byte(s), "
             f"which does not fit.")
    tag_bytes = bytes(data[offset + 8:offset + 12])
    if tag_bytes == PLATFORM_GSTR.encode("ascii"):
        platform, code = PLATFORM_GSTR, None
    elif tag_bytes[:2] == b"PT":
        platform, code = PLATFORM_PT, struct.unpack_from("<H", data, offset + 10)[0]
    else:
        raise SchlError(
            f"the SCHl header at byte {offset} names platform {tag_bytes!r}; this "
            f"module reads the two Madden NFL 09 uses, {PLATFORM_GSTR!r} and 'PT'.")
    start = offset + _TAGS_AT[platform]
    tags = parse_tags(bytes(data[start:offset + header_size]))
    return StreamHeader(offset, header_size, platform, code,
                        _BIG_ENDIAN[platform], tags)


def iter_streams(data: Any, start: int, end: int, *,
                 with_blocks: bool = True) -> Tuple[Stream, ...]:
    """Every ``SCHl`` stream between *start* and *end*, headers first.

    Cataloguing never decodes: a stream costs its header plus one 8-byte read
    per chunk, so 34,046 streams over 1.1 GB of containers is a walk, not a
    decode.  ``with_blocks=False`` skips even the chunk walk, which is enough
    when only the first stream of a member is wanted.
    """

    out: List[Stream] = []
    position = start
    index = 0
    while position + CHUNK_HEADER_SIZE <= end:
        if bytes(data[position:position + 4]) != SCHL_MAGIC:
            # Streams inside one member are zero-padded apart [M]; anything
            # else ends the walk rather than being searched past.
            if data[position] != 0:
                break
            step = position
            while step < end and data[step] == 0:
                step += 1
            if step + 4 > end or bytes(data[step:step + 4]) != SCHL_MAGIC:
                break
            position = step
            continue
        try:
            header = parse_stream_header(data, position, end)
        except SchlError:
            break
        cursor = position + header.header_size
        blocks: List[Block] = []
        declared: Optional[int] = None
        complete = False
        order = ">I" if header.big_endian else "<I"
        while cursor + CHUNK_HEADER_SIZE <= end:
            tag = bytes(data[cursor:cursor + 4])
            size, = struct.unpack_from("<I", data, cursor + 4)
            if size <= 0 or tag not in STREAM_CHUNKS or tag == SCHL_MAGIC:
                break
            if cursor + size > end:
                break
            if tag == SCCL_MAGIC:
                declared, = struct.unpack_from(order, data, cursor + 8)
            elif tag == SCDL_MAGIC and with_blocks:
                samples, = struct.unpack_from(order, data, cursor + 8)
                blocks.append(Block(cursor, size, samples))
            cursor += size
            if tag == SCEL_MAGIC:
                complete = True
                break
            if not with_blocks and tag == SCCL_MAGIC:
                # Without the block walk there is no way to find the end, so
                # the caller gets the header and one stream only.
                cursor = end
                break
        out.append(Stream(index, position, cursor - position, header,
                          tuple(blocks), declared, complete))
        index += 1
        if not with_blocks:
            break
        position = cursor
    return tuple(out)


# --------------------------------------------------------------------------
# EA-XA ADPCM
# --------------------------------------------------------------------------

def _eaxa_residual_tables() -> Tuple[Tuple[Tuple[int, ...], ...], ...]:
    """``[shift][nibble] -> residual``, so the inner loop is two lookups."""

    out = []
    for low in range(16):
        shift = 20 - low
        out.append(tuple(((nibble - 16 if nibble > 7 else nibble) << shift)
                         for nibble in range(16)))
    return tuple(out)


_EAXA_RESIDUALS = _eaxa_residual_tables()


def decode_eaxa(data: Any, blocks: Sequence[Block], channels: int,
                big_endian: bool, version: Optional[int] = None) -> bytes:
    """Interleaved 16-bit PCM for *blocks*, decoded exactly as the format has it.

    Proved byte for byte against ffmpeg's ``adpcm_ea_r1``, ``adpcm_ea_r2`` and
    ``adpcm_ea_r3`` on every decodable stream of the retail disc; see the module
    docstring.  ``version`` is the header's tag ``0x80``: **2 puts two
    little-endian int16 predictor values at the head of every channel's run in
    every block**, 3 (and a header with no ``0x80`` at all) does not and carries
    the predictor across blocks instead [M].  Decoding a version-2 stream the
    version-3 way walks four bytes off and produces coefficient indices the
    format does not have -- which is how the difference was found.
    """

    _require(1 <= channels <= 8, f"a stream with {channels} channel(s) is not one this "
                                 f"module reads.")
    order = ">" if big_endian else "<"
    word = order + "I"
    raw_pair = ">h"
    per_block_state = version == EAXA_VERSION_PER_BLOCK_STATE
    planes = [array.array("h") for _ in range(channels)]
    state = [(0, 0) for _ in range(channels)]
    residuals = _EAXA_RESIDUALS
    coefficients = EAXA_COEFFICIENTS
    for block in blocks:
        base = block.offset + CHUNK_HEADER_SIZE
        payload = bytes(data[base:block.offset + block.size])
        _require(len(payload) >= 4 + 4 * channels,
                 f"the block at byte {block.offset} is too short for {channels} "
                 f"channel offset(s).")
        count, = struct.unpack_from(word, payload, 0)
        frames = count // EAXA_SAMPLES_PER_FRAME
        skip = (channels + 1) * 4
        for channel in range(channels):
            start, = struct.unpack_from(word, payload, 4 + 4 * channel)
            position = start + skip
            current, previous = state[channel]
            if per_block_state:
                _require(position + 4 <= len(payload),
                         f"the block at byte {block.offset} ends before channel "
                         f"{channel}'s predictor values.")
                # Little-endian whatever the block's own byte order is [M].
                current, = struct.unpack_from("<h", payload, position)
                previous, = struct.unpack_from("<h", payload, position + 2)
                position += 4
            out = planes[channel]
            append = out.append
            for _frame in range(frames):
                _require(position < len(payload),
                         f"the block at byte {block.offset} ends inside channel "
                         f"{channel}'s frames.")
                control = payload[position]
                position += 1
                if control == EAXA_RAW_FRAME:
                    _require(position + 4 + 2 * EAXA_SAMPLES_PER_FRAME <= len(payload),
                             f"the verbatim frame at byte {block.offset} is truncated.")
                    current, = struct.unpack_from(raw_pair, payload, position)
                    previous, = struct.unpack_from(raw_pair, payload, position + 2)
                    position += 4
                    for _step in range(EAXA_SAMPLES_PER_FRAME):
                        sample, = struct.unpack_from(raw_pair, payload, position)
                        position += 2
                        append(sample)
                    continue
                index = control >> 4
                _require(index < len(coefficients),
                         f"the frame at byte {block.offset} names coefficient set "
                         f"{index}; this format has {len(coefficients)}.")
                first, second = coefficients[index]
                table = residuals[control & 0x0F]
                _require(position + 14 <= len(payload),
                         f"the frame at byte {block.offset} is truncated.")
                for step in range(EAXA_SAMPLES_PER_FRAME):
                    if step & 1:
                        nibble = byte & 0x0F
                    else:
                        byte = payload[position]
                        position += 1
                        nibble = byte >> 4
                    value = table[nibble] + current * first + previous * second
                    value = value >> 8
                    if value < -32768:
                        value = -32768
                    elif value > 32767:
                        value = 32767
                    previous = current
                    current = value
                    append(value)
            state[channel] = (current, previous)
    return _interleave(planes)


def _interleave(planes: Sequence["array.array"]) -> bytes:
    if len(planes) == 1:
        return planes[0].tobytes()
    length = min(len(plane) for plane in planes)
    out = array.array("h", bytes(2 * length * len(planes)))
    for channel, plane in enumerate(planes):
        out[channel::len(planes)] = plane[:length]
    return out.tobytes()


def _deinterleave(pcm: bytes, channels: int) -> List["array.array"]:
    samples = array.array("h")
    samples.frombytes(pcm[:len(pcm) - len(pcm) % (2 * channels)])
    if channels == 1:
        return [samples]
    return [samples[channel::channels] for channel in range(channels)]


def encode_eaxa_frame(target: Sequence[int], current: int, previous: int
                      ) -> Tuple[bytes, int, int]:
    """One 15-byte frame for 28 samples, and the predictor state it leaves.

    The search is the decoder run backwards: for each of the four coefficient
    sets, the shift that just fits the largest residual is tried along with the
    next coarser one, and the pair with the smallest squared error wins.  Every
    candidate is *simulated with the decoder's own arithmetic*, so the state
    this returns is what a decoder will actually have.
    """

    best: Optional[Tuple[int, bytes, int, int]] = None
    for index, (first, second) in enumerate(EAXA_COEFFICIENTS):
        peak = 0
        sim_current, sim_previous = current, previous
        for wanted in target:
            ideal = (wanted << 8) - sim_current * first - sim_previous * second
            peak = max(peak, abs(ideal))
            sim_previous, sim_current = sim_current, wanted
        low_start = 0
        if peak:
            need = max(0, math.ceil(math.log2(peak / 8.0))) if peak > 8 else 0
            low_start = max(0, min(15, 20 - need))
        for low in {low_start, max(0, low_start - 1), min(15, low_start + 1)}:
            shift = 20 - low
            table = _EAXA_RESIDUALS[low]
            sim_current, sim_previous = current, previous
            nibbles: List[int] = []
            error = 0
            for wanted in target:
                ideal = (wanted << 8) - sim_current * first - sim_previous * second
                quantised = (ideal + (1 << (shift - 1))) >> shift
                if quantised < -8:
                    quantised = -8
                elif quantised > 7:
                    quantised = 7
                nibble = quantised & 0x0F
                value = (table[nibble] + sim_current * first + sim_previous * second) >> 8
                value = _clip16(value)
                error += (value - wanted) * (value - wanted)
                nibbles.append(nibble)
                sim_previous, sim_current = sim_current, value
            if best is None or error < best[0]:
                packed = bytearray([(index << 4) | low])
                for step in range(0, EAXA_SAMPLES_PER_FRAME, 2):
                    packed.append((nibbles[step] << 4) | nibbles[step + 1])
                best = (error, bytes(packed), sim_current, sim_previous)
    assert best is not None
    return best[1], best[2], best[3]


def encode_eaxa_blocks(pcm: bytes, channels: int, big_endian: bool, *,
                       block_samples: int = DEFAULT_BLOCK_SAMPLES,
                       version: Optional[int] = None) -> List[bytes]:
    """``SCDl`` chunk bytes for *pcm*, in the byte order the platform tag implies.

    ``version`` is written the way :func:`decode_eaxa` reads it: a version-2
    block opens each channel's run with the two little-endian ``int16``
    predictor values that channel starts from, and any other version carries the
    predictor across blocks instead [M].
    """

    _require(block_samples % EAXA_SAMPLES_PER_FRAME == 0 and block_samples > 0,
             f"a block must hold a whole number of {EAXA_SAMPLES_PER_FRAME}-sample "
             f"frames; {block_samples} does not.")
    planes = _deinterleave(pcm, channels)
    total = len(planes[0])
    order = ">I" if big_endian else "<I"
    per_block_state = version == EAXA_VERSION_PER_BLOCK_STATE
    state = [(0, 0) for _ in range(channels)]
    chunks: List[bytes] = []
    position = 0
    while position < total:
        count = min(block_samples, total - position)
        count -= count % EAXA_SAMPLES_PER_FRAME
        if count == 0:
            break
        runs: List[bytes] = []
        for channel in range(channels):
            current, previous = state[channel]
            body = bytearray()
            if per_block_state:
                body += struct.pack("<hh", current, previous)
            plane = planes[channel]
            for start in range(position, position + count, EAXA_SAMPLES_PER_FRAME):
                frame, current, previous = encode_eaxa_frame(
                    plane[start:start + EAXA_SAMPLES_PER_FRAME], current, previous)
                body += frame
            if len(body) % 2:
                body += b"\x00"
            state[channel] = (current, previous)
            runs.append(bytes(body))
        payload = bytearray(struct.pack(order, count))
        cursor = 0
        for run in runs:
            payload += struct.pack(order, cursor)
            cursor += len(run)
        for run in runs:
            payload += run
        chunks.append(SCDL_MAGIC + struct.pack("<I", CHUNK_HEADER_SIZE + len(payload))
                      + bytes(payload))
        position += count
    return chunks


def build_stream(pcm: bytes, *, channels: int, sample_rate: int, big_endian: bool,
                 version: int = 3, codec: Optional[int] = CODEC_EAXA,
                 block_samples: int = DEFAULT_BLOCK_SAMPLES) -> bytes:
    """A whole ``SCHl`` .. ``SCEl`` stream carrying *pcm*, in this disc's shape.

    The header is written in the same platform shape the stream it replaces
    used, so the only thing that changes about a replaced member is the audio
    and the four numbers that describe it.
    """

    _require(channels >= 1, "a stream needs at least one channel.")
    _require(sample_rate > 0, "a stream needs a positive sample rate.")
    blocks = encode_eaxa_blocks(pcm, channels, big_endian, block_samples=block_samples,
                                version=version)
    samples = sum(struct.unpack_from(">I" if big_endian else "<I",
                                     chunk, CHUNK_HEADER_SIZE)[0] for chunk in blocks)
    tags = bytearray([TAG_INFO])
    tags += bytes([TAG_VERSION, 1, version])
    if codec is not None:
        tags += bytes([TAG_CODEC, 1, codec])
    tags += bytes([TAG_CHANNELS, 1, channels])
    tags += bytes([TAG_SAMPLE_RATE, 3]) + int(sample_rate).to_bytes(3, "big")
    tags += bytes([TAG_SAMPLE_COUNT, 4]) + int(samples).to_bytes(4, "big")
    tags += bytes([TAG_END])
    if big_endian:
        body = PLATFORM_GSTR.encode("ascii") + b"\x01\x00\x00\x00" + bytes(tags)
    else:
        body = b"PT" + struct.pack("<H", 5) + bytes(tags)
    while (CHUNK_HEADER_SIZE + len(body)) % 4:
        body += b"\x00"
    head = SCHL_MAGIC + struct.pack("<I", CHUNK_HEADER_SIZE + len(body)) + body
    order = ">I" if big_endian else "<I"
    count = SCCL_MAGIC + struct.pack("<I", 12) + struct.pack(order, len(blocks))
    return head + count + b"".join(blocks) + SCEL_MAGIC + struct.pack("<I", 8)


# --------------------------------------------------------------------------
# Sony PS ADPCM, and the banks that carry it
# --------------------------------------------------------------------------

def decode_psx(data: bytes, channels: int, *,
               channel_offsets: Optional[Sequence[int]] = None) -> bytes:
    """Interleaved 16-bit PCM from PS ADPCM frames, one contiguous run per channel.

    A multi-channel sound is **planar**: channel 0's frames, then channel 1's
    [M] -- on the disc's stereo bank sounds tag ``0x89`` names the second run's
    offset and it sits at exactly half the data in 183 of 183.  *channel_offsets*
    gives each run's start inside *data*; when it is absent the data is split
    into equal runs.  Which run is the left channel is not established [A].
    """

    _require(1 <= channels <= 8, f"a sound with {channels} channel(s) is not one this "
                                 f"module reads.")
    if channel_offsets is None:
        run = len(data) // channels
        run -= run % PSX_FRAME_BYTES
        channel_offsets = [channel * run for channel in range(channels)]
    _require(len(channel_offsets) == channels,
             f"{len(channel_offsets)} channel offset(s) were given for {channels} channel(s).")
    ordered = sorted(int(offset) for offset in channel_offsets)
    _require(all(0 <= offset <= len(data) for offset in ordered),
             "a channel run starts outside the sound's data.")
    bounds = list(zip(ordered, ordered[1:] + [len(data)]))
    planes = [array.array("h") for _ in range(channels)]
    state = [(0, 0) for _ in range(channels)]
    filters = PSX_FILTERS
    frame_plan = []
    for channel, (start, end) in enumerate(bounds):
        for base in range(start, end - PSX_FRAME_BYTES + 1, PSX_FRAME_BYTES):
            frame_plan.append((channel, base))
    for channel, base in frame_plan:
        control = data[base]
        shift = control & 0x0F
        index = control >> 4
        _require(index < len(filters),
                 f"the frame at byte {base} names filter {index}; this format has "
                 f"{len(filters)}.")
        first, second = filters[index]
        current, previous = state[channel]
        append = planes[channel].append
        for step in range(PSX_SAMPLES_PER_FRAME):
            byte = data[base + 2 + (step >> 1)]
            nibble = (byte & 0x0F) if not (step & 1) else (byte >> 4)
            if nibble > 7:
                nibble -= 16
            accumulator = current * first + previous * second
            # C's integer division truncates toward zero; an arithmetic shift
            # does not, and the difference is one LSB on half the samples [M].
            accumulator = -((-accumulator) // 64) if accumulator < 0 else accumulator // 64
            value = ((nibble << 12) >> shift) + accumulator
            append(_clip16(value))
            previous = current
            # The state keeps the UNCLIPPED value; clipping it here is wrong
            # wherever a sound saturates [M].
            current = value
        state[channel] = (current, previous)
    return _interleave(planes)


def encode_psx_frame(target: Sequence[int], current: int, previous: int
                     ) -> Tuple[bytes, int, int]:
    """One 16-byte PS ADPCM frame, and the predictor state it leaves."""

    best: Optional[Tuple[int, bytes, int, int]] = None
    for index, (first, second) in enumerate(PSX_FILTERS):
        peak = 0
        sim_current, sim_previous = current, previous
        for wanted in target:
            accumulator = sim_current * first + sim_previous * second
            accumulator = (-((-accumulator) // 64) if accumulator < 0
                           else accumulator // 64)
            peak = max(peak, abs(wanted - accumulator))
            sim_previous, sim_current = sim_current, wanted
        needed = 0 if peak <= 0 else max(0, math.ceil(math.log2((peak + 1) / 8.0)) + 12 - 12)
        base_shift = 12 - min(12, needed) if peak else 12
        for shift in {max(0, min(12, base_shift)), max(0, min(12, base_shift - 1)),
                      max(0, min(12, base_shift + 1))}:
            sim_current, sim_previous = current, previous
            nibbles: List[int] = []
            error = 0
            for wanted in target:
                accumulator = sim_current * first + sim_previous * second
                accumulator = (-((-accumulator) // 64) if accumulator < 0
                               else accumulator // 64)
                ideal = wanted - accumulator
                quantised = int(round((ideal * (1 << shift)) / 4096.0))
                if quantised < -8:
                    quantised = -8
                elif quantised > 7:
                    quantised = 7
                value = ((quantised << 12) >> shift) + accumulator
                error += (_clip16(value) - wanted) ** 2
                nibbles.append(quantised & 0x0F)
                sim_previous, sim_current = sim_current, value
            if best is None or error < best[0]:
                packed = bytearray([(index << 4) | shift, 0])
                for step in range(0, PSX_SAMPLES_PER_FRAME, 2):
                    packed.append(nibbles[step] | (nibbles[step + 1] << 4))
                best = (error, bytes(packed), sim_current, sim_previous)
    assert best is not None
    return best[1], best[2], best[3]


def encode_psx(pcm: bytes, channels: int) -> bytes:
    """PS ADPCM frames for *pcm*: one contiguous run per channel, channel 0 first.

    The planar shape the disc's stereo bank sounds have [M]; the second run's
    offset is ``len(result) // channels``.
    """

    planes = _deinterleave(pcm, channels)
    total = len(planes[0]) - len(planes[0]) % PSX_SAMPLES_PER_FRAME
    out = bytearray()
    for channel in range(channels):
        current, previous = 0, 0
        for start in range(0, total, PSX_SAMPLES_PER_FRAME):
            frame, current, previous = encode_psx_frame(
                planes[channel][start:start + PSX_SAMPLES_PER_FRAME], current, previous)
            out += frame
    return bytes(out)


@dataclass(frozen=True)
class BankSound:
    """One sound inside a ``BNKl`` bank."""

    index: int
    header_offset: int
    header: StreamHeader
    data_offset: int
    data_length: int

    @property
    def channels(self) -> int:
        return self.header.channels

    @property
    def sample_rate(self) -> Optional[int]:
        return self.header.sample_rate

    @property
    def sample_count(self) -> int:
        return self.header.sample_count


@dataclass(frozen=True)
class Bank:
    """A ``BNKl`` member: a directory of sounds and the bytes behind it."""

    offset: int
    length: int
    version: int
    header_size: int
    data_size: int
    sounds: Tuple[BankSound, ...]
    #: Slots whose offset is zero: a hole in the directory, not a sound [M].
    empty_slots: int = 0


def parse_bank(data: Any, offset: int, length: int) -> Bank:
    """The ``BNKl`` bank at *offset*, directory only -- nothing is decoded."""

    _require(length >= 0x18 and bytes(data[offset:offset + 4]) == BNKL_MAGIC,
             f"byte {offset} does not open a {BNKL_MAGIC!r} bank.")
    version, count = struct.unpack_from("<HH", data, offset + 4)
    header_size, data_size = struct.unpack_from("<II", data, offset + 8)
    _require(0 < count <= 4096, f"this bank declares {count} sound(s), which is not a "
                                f"count this module trusts.")
    _require(0x14 + 4 * count <= header_size <= length,
             f"this bank's header is {header_size} byte(s), too small for its "
             f"{count} sound(s).")
    sounds: List[BankSound] = []
    starts: List[Optional[int]] = []
    for index in range(count):
        slot = offset + 0x14 + 4 * index
        relative, = struct.unpack_from("<I", data, slot)
        # Each offset is counted from its OWN slot, not from the table, and a
        # slot holding zero is an EMPTY one -- 11 of the 301 retail banks have
        # them, and reading zero as an offset lands back inside the table [M].
        starts.append(None if relative == 0 else slot + relative)
    filled = [start for start in starts if start is not None]
    for index, start in enumerate(starts):
        if start is None:
            continue
        _require(offset <= start < offset + header_size,
                 f"sound {index} of this bank points outside its own header.")
        later = [item for item in filled if item > start]
        end = min(later) if later else offset + header_size
        header = _bank_sound_header(data, start, end)
        sounds.append(BankSound(index, start - offset, header, 0, 0))
    resolved: List[BankSound] = []
    for index, sound in enumerate(sounds):
        begin = sound.header.value(TAG_DATA_OFFSET)
        if begin is None:
            resolved.append(sound)
            continue
        following = [s.header.value(TAG_DATA_OFFSET) for s in sounds[index + 1:]]
        following = [value for value in following if value is not None and value > begin]
        finish = min(following) if following else length
        resolved.append(BankSound(sound.index, sound.header_offset, sound.header,
                                  int(begin), max(0, int(finish) - int(begin))))
    return Bank(offset, length, version, header_size, data_size, tuple(resolved),
                empty_slots=sum(1 for start in starts if start is None))


def _bank_sound_header(data: Any, start: int, end: int) -> StreamHeader:
    tag_bytes = bytes(data[start:start + 4])
    _require(tag_bytes[:2] == b"PT",
             f"the bank sound at byte {start} names platform {tag_bytes!r}; the banks "
             f"on this disc all use 'PT'.")
    code, = struct.unpack_from("<H", data, start + 2)
    tags = parse_tags(bytes(data[start + 4:end]))
    return StreamHeader(start, end - start, PLATFORM_PT, code, False, tags)


def decode_bank_sound(data: Any, bank: Bank, sound: BankSound) -> bytes:
    """Interleaved 16-bit PCM for one bank sound."""

    _require(sound.data_length > 0,
             f"sound {sound.index} of this bank declares no data offset, so there is "
             f"nothing to decode.")
    begin = bank.offset + sound.data_offset
    payload = bytes(data[begin:begin + sound.data_length])
    offsets: Optional[List[int]] = None
    second = sound.header.value(TAG_SECOND_CHANNEL)
    if sound.channels == 2 and second is not None:
        # The second channel's run starts where tag 0x89 says; on the disc that
        # is exactly half the data in 183 of 183 stereo sounds [M].  A tag
        # pointing anywhere else is a sound this module does not understand,
        # and it is refused rather than decoded into two runs of the wrong
        # length.
        relative = int(second) - sound.data_offset
        _require(0 < relative < sound.data_length and relative % PSX_FRAME_BYTES == 0,
                 f"sound {sound.index} of this bank puts its second channel at byte "
                 f"{int(second)}, which is not a frame boundary inside its "
                 f"{sound.data_length}-byte data at {sound.data_offset}.")
        offsets = [0, relative]
    elif sound.channels != 1:
        _require(second is None,
                 f"sound {sound.index} of this bank has {sound.channels} channels and one "
                 f"second-channel offset; this module reads mono and stereo banks.")
    return decode_psx(payload, sound.channels, channel_offsets=offsets)


# --------------------------------------------------------------------------
# WAV
# --------------------------------------------------------------------------

def wav_bytes(pcm: bytes, sample_rate: int, channels: int) -> bytes:
    """A 16-bit PCM RIFF/WAVE file around *pcm*."""

    _require(sample_rate > 0 and channels > 0,
             "a WAV needs a positive sample rate and channel count.")
    block_align = 2 * channels
    header = b"".join((
        b"RIFF", struct.pack("<I", 36 + len(pcm)), b"WAVE",
        b"fmt ", struct.pack("<IHHIIHH", 16, 1, channels, sample_rate,
                             sample_rate * block_align, block_align, 16),
        b"data", struct.pack("<I", len(pcm)),
    ))
    return header + pcm


def read_wav(payload: bytes) -> Tuple[int, int, bytes]:
    """``(sample_rate, channels, 16-bit PCM)`` from an uncompressed WAV.

    Refuses a compressed or exotic WAV **by name** rather than converting it
    silently: 8-, 24- and 32-bit integer samples and 32-bit floats are widened
    or narrowed to 16-bit here, and anything else is a sentence.
    """

    _require(len(payload) >= 44 and payload[:4] == b"RIFF" and payload[8:12] == b"WAVE",
             "that file is not a WAV; export a sound first and edit the file it wrote.")
    position = 12
    fmt: Optional[Tuple[int, int, int, int]] = None
    data: Optional[bytes] = None
    while position + 8 <= len(payload):
        tag = payload[position:position + 4]
        size, = struct.unpack_from("<I", payload, position + 4)
        body = payload[position + 8:position + 8 + size]
        if tag == b"fmt " and len(body) >= 16:
            audio_format, channels, rate, _bps, _align, bits = struct.unpack_from(
                "<HHIIHH", body, 0)
            if audio_format == 0xFFFE and len(body) >= 40:
                audio_format, = struct.unpack_from("<H", body, 24)
            fmt = (audio_format, channels, rate, bits)
        elif tag == b"data":
            data = bytes(body)
        position += 8 + size + (size & 1)
    _require(fmt is not None and data is not None,
             "that WAV has no format or no data chunk; re-save it.")
    audio_format, channels, rate, bits = fmt  # type: ignore[misc]
    _require(audio_format in (1, 3),
             f"that WAV is stored in format {audio_format}, which is compressed; save it "
             f"as uncompressed PCM.")
    _require(1 <= channels <= 8, f"that WAV has {channels} channel(s); this lane takes 1 "
                                 f"to 8.")
    _require(rate > 0, "that WAV declares a sample rate of zero; re-save it.")
    return rate, channels, _to_int16(data, bits, audio_format)  # type: ignore[arg-type]


def _to_int16(data: bytes, bits: int, audio_format: int) -> bytes:
    if audio_format == 3:
        _require(bits == 32, f"that WAV holds {bits}-bit floats; this lane reads 32-bit "
                             f"floats or integer PCM.")
        floats = array.array("f")
        floats.frombytes(data[:len(data) - len(data) % 4])
        out = array.array("h", bytes(2 * len(floats)))
        for index, value in enumerate(floats):
            out[index] = _clip16(int(round(value * 32767.0)))
        return out.tobytes()
    if bits == 16:
        return bytes(data[:len(data) - len(data) % 2])
    if bits == 8:
        return array.array("h", [(byte - 128) << 8 for byte in data]).tobytes()
    if bits == 24:
        out = array.array("h", bytes(2 * (len(data) // 3)))
        for index in range(len(data) // 3):
            out[index] = struct.unpack_from("<h", data, index * 3 + 1)[0]
        return out.tobytes()
    if bits == 32:
        words = array.array("i")
        words.frombytes(data[:len(data) - len(data) % 4])
        return array.array("h", [value >> 16 for value in words]).tobytes()
    raise SchlError(f"that WAV holds {bits}-bit samples; this lane reads 8, 16, 24 or 32.")


def remix(pcm: bytes, have: int, want: int) -> bytes:
    """*pcm* with *want* channels: extra channels are averaged, one is copied."""

    if have == want:
        return pcm
    planes = _deinterleave(pcm, have)
    if want == 1:
        length = len(planes[0])
        out = array.array("h", bytes(2 * length))
        for index in range(length):
            out[index] = _clip16(sum(plane[index] for plane in planes) // have)
        return out.tobytes()
    if have == 1:
        return _interleave([planes[0]] * want)
    mono = remix(pcm, have, 1)
    return remix(mono, 1, want)


def resample(pcm: bytes, channels: int, source_rate: int, target_rate: int) -> bytes:
    """*pcm* at *target_rate*, by linear interpolation.

    Linear interpolation and nothing cleverer: it is what a user's replacement
    sound gets, it is said plainly on the page, and a windowed resampler would
    be a much larger claim to have to prove.
    """

    if source_rate == target_rate:
        return pcm
    _require(source_rate > 0 and target_rate > 0, "a resample needs positive rates.")
    planes = _deinterleave(pcm, channels)
    length = len(planes[0])
    if length == 0:
        return b""
    wanted = max(1, int(round(length * target_rate / float(source_rate))))
    step = (length - 1) / float(wanted) if wanted > 1 and length > 1 else 0.0
    out = []
    for plane in planes:
        made = array.array("h", bytes(2 * wanted))
        for index in range(wanted):
            position = index * step
            left = int(position)
            right = min(left + 1, length - 1)
            fraction = position - left
            made[index] = _clip16(int(round(plane[left] * (1.0 - fraction)
                                            + plane[right] * fraction)))
        out.append(made)
    return _interleave(out)


def measure(pcm: bytes) -> Dict[str, Any]:
    """Peak, RMS and saturation of a decoded sound: what a plausibility check reads."""

    samples = array.array("h")
    samples.frombytes(pcm[:len(pcm) - len(pcm) % 2])
    if not samples:
        return {"samples": 0, "peak": 0, "rms": 0.0, "saturated": 0,
                "longest_saturation_run": 0, "silent": True}
    peak = 0
    total = 0
    saturated = 0
    longest = 0
    run = 0
    for value in samples:
        magnitude = -value if value < 0 else value
        if magnitude > peak:
            peak = magnitude
        total += value * value
        if magnitude >= 32767:
            saturated += 1
            run += 1
            if run > longest:
                longest = run
        else:
            run = 0
    return {
        "samples": len(samples),
        "peak": peak,
        "rms": math.sqrt(total / len(samples)),
        "saturated": saturated,
        "longest_saturation_run": longest,
        "silent": peak == 0,
    }


def signal_to_noise(reference: bytes, made: bytes) -> Optional[float]:
    """SNR in dB of *made* against *reference*, or ``None`` when either is silent."""

    left = array.array("h")
    left.frombytes(reference[:len(reference) - len(reference) % 2])
    right = array.array("h")
    right.frombytes(made[:len(made) - len(made) % 2])
    length = min(len(left), len(right))
    if length == 0:
        return None
    signal = 0
    noise = 0
    for index in range(length):
        signal += left[index] * left[index]
        difference = left[index] - right[index]
        noise += difference * difference
    if signal == 0:
        return None
    if noise == 0:
        return float("inf")
    return 10.0 * math.log10(signal / noise)


# --------------------------------------------------------------------------
# Synthetic sources: what CI proves this on, with no game data anywhere near it
# --------------------------------------------------------------------------

def synthetic_pcm(samples: int, channels: int, *, sample_rate: int = 22050,
                  frequency: float = 220.0, amplitude: int = 12000) -> bytes:
    """A computed tone: a sine per channel, each channel a different partial."""

    out = array.array("h", bytes(2 * samples * channels))
    for channel in range(channels):
        step = 2.0 * math.pi * frequency * (channel + 1) / float(sample_rate)
        for index in range(samples):
            out[index * channels + channel] = _clip16(
                int(amplitude * math.sin(step * index)))
    return out.tobytes()


def synthetic_stream(*, samples: int = 4480, channels: int = 2, sample_rate: int = 22050,
                     big_endian: bool = True, codec: Optional[int] = CODEC_EAXA,
                     version: int = 3) -> bytes:
    """One ``SCHl`` stream carrying a computed tone."""

    pcm = synthetic_pcm(samples, channels, sample_rate=sample_rate)
    return build_stream(pcm, channels=channels, sample_rate=sample_rate,
                        big_endian=big_endian, codec=codec, version=version)


def synthetic_speech_stream(*, samples: int = 4480, sample_rate: int = 36000) -> bytes:
    """A stream that declares codec 4, so a lane's refusal has something to refuse.

    Its payload is computed noise, not speech: the point is the header, because
    nothing here can decode codec 4 and the lane must say so rather than try.
    """

    tags = bytearray([0x06, 1, 101, TAG_INFO])
    tags += bytes([TAG_VERSION, 1, 3])
    tags += bytes([TAG_SAMPLE_COUNT, 3]) + int(samples).to_bytes(3, "big")
    tags += bytes([TAG_CODEC, 1, CODEC_SPEECH])
    tags += bytes([TAG_SAMPLE_RATE, 3]) + int(sample_rate).to_bytes(3, "big")
    tags += bytes([TAG_END])
    body = PLATFORM_GSTR.encode("ascii") + b"\x01\x00\x00\x00" + bytes(tags)
    while (CHUNK_HEADER_SIZE + len(body)) % 4:
        body += b"\x00"
    head = SCHL_MAGIC + struct.pack("<I", CHUNK_HEADER_SIZE + len(body)) + body
    payload = bytearray(struct.pack(">I", samples) + struct.pack(">I", 0))
    payload += bytes((index * 37) & 0xFF for index in range(samples // 5))
    block = SCDL_MAGIC + struct.pack("<I", CHUNK_HEADER_SIZE + len(payload)) + bytes(payload)
    count = SCCL_MAGIC + struct.pack("<I", 12) + struct.pack(">I", 1)
    return head + count + block + SCEL_MAGIC + struct.pack("<I", 8)


def synthetic_bank(*, sounds: int = 2, samples: int = 1120, sample_rate: int = 24000,
                   channels: int = 1) -> bytes:
    """A ``BNKl`` bank of computed tones, in the shape the disc's banks have."""

    _require(sounds >= 1, "a synthetic bank needs at least one sound.")
    bodies = [encode_psx(synthetic_pcm(samples, channels, sample_rate=sample_rate,
                                       frequency=220.0 * (index + 1)), channels)
              for index in range(sounds)]
    headers: List[bytes] = []
    header_size = 0x14 + 4 * sounds
    for index in range(sounds):
        tags = bytearray([0x06, 1, 101, TAG_INFO])
        tags += bytes([TAG_VERSION, 1, 2])
        tags += bytes([TAG_SAMPLE_COUNT, 3]) + int(samples).to_bytes(3, "big")
        if channels != 1:
            tags += bytes([TAG_CHANNELS, 1, channels])
        tags += bytes([TAG_SAMPLE_RATE, 3]) + int(sample_rate).to_bytes(3, "big")
        tags += bytes([TAG_DATA_OFFSET, 4]) + b"\x00\x00\x00\x00"
        if channels == 2:
            # The disc's stereo shape: planar runs, the second one named by 0x89.
            tags += bytes([TAG_SECOND_CHANNEL, 4]) + b"\x00\x00\x00\x01"
        tags += bytes([TAG_END])
        while (4 + len(tags)) % 4:
            tags += bytes([TAG_PAD])
        headers.append(b"PT" + struct.pack("<H", 5) + bytes(tags))
    header_size += sum(len(item) for item in headers)
    while header_size % 16:
        header_size += 1
    starts = []
    cursor = header_size
    for body in bodies:
        starts.append(cursor)
        cursor += len(body)
    fixed: List[bytes] = []
    for header, start, body in zip(headers, starts, bodies):
        marker = bytes([TAG_DATA_OFFSET, 4]) + b"\x00\x00\x00\x00"
        replacement = bytes([TAG_DATA_OFFSET, 4]) + int(start).to_bytes(4, "big")
        header = header.replace(marker, replacement, 1)
        if channels == 2:
            marker = bytes([TAG_SECOND_CHANNEL, 4]) + b"\x00\x00\x00\x01"
            replacement = (bytes([TAG_SECOND_CHANNEL, 4])
                           + int(start + len(body) // 2).to_bytes(4, "big"))
            header = header.replace(marker, replacement, 1)
        fixed.append(header)
    out = bytearray(BNKL_MAGIC)
    out += struct.pack("<HH", 5, sounds)
    out += struct.pack("<II", header_size, cursor - header_size)
    out += struct.pack("<I", 0)
    offsets_at = 0x14
    table = bytearray()
    position = offsets_at + 4 * sounds
    for index, header in enumerate(fixed):
        table += struct.pack("<I", position - (offsets_at + 4 * index))
        position += len(header)
    out += table
    for header in fixed:
        out += header
    out += b"\x00" * (header_size - len(out))
    for body in bodies:
        out += body
    return bytes(out)


__all__ = [
    "Bank",
    "BankSound",
    "Block",
    "BNKL_MAGIC",
    "CODEC_EAXA",
    "CODEC_NAMES",
    "CODEC_SPEECH",
    "DEFAULT_BLOCK_SAMPLES",
    "EAXA_COEFFICIENTS",
    "EAXA_FRAME_BYTES",
    "EAXA_RAW_FRAME",
    "EAXA_SAMPLES_PER_FRAME",
    "EAXA_VERSION_PER_BLOCK_STATE",
    "PLATFORM_GSTR",
    "PLATFORM_PT",
    "PSX_FILTERS",
    "PSX_FRAME_BYTES",
    "PSX_SAMPLES_PER_FRAME",
    "SCCL_MAGIC",
    "SCDL_MAGIC",
    "SCEL_MAGIC",
    "SCHL_MAGIC",
    "SPEECH_REFUSAL",
    "STREAM_CHUNKS",
    "SchlError",
    "Stream",
    "StreamHeader",
    "TAG_CHANNELS",
    "TAG_CODEC",
    "TAG_DATA_OFFSET",
    "TAG_MEANINGS",
    "TAG_SAMPLE_COUNT",
    "TAG_SAMPLE_RATE",
    "TAG_SECOND_CHANNEL",
    "TAG_VERSION",
    "VALUELESS_TAGS",
    "build_stream",
    "decode_bank_sound",
    "decode_eaxa",
    "decode_psx",
    "encode_eaxa_blocks",
    "encode_eaxa_frame",
    "encode_psx",
    "encode_psx_frame",
    "iter_streams",
    "measure",
    "parse_bank",
    "parse_stream_header",
    "parse_tags",
    "read_wav",
    "remix",
    "resample",
    "signal_to_noise",
    "synthetic_bank",
    "synthetic_pcm",
    "synthetic_speech_stream",
    "synthetic_stream",
    "wav_bytes",
]

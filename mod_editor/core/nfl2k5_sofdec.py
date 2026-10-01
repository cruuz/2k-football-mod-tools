"""CRI Sofdec movie streams, the game's ``.mov`` resources. EXPERIMENTAL / UNWITNESSED.

All 30 retail movies in the USA archive are MPEG-1 program streams written by
CRI's SFM 2.21 muxer in strict 2,048-byte packs: MPEG-1 video on stream 0xE0,
CRI ADX ADPCM audio on stream 0xC0 (one stream carries AIX instead), behind four
header sectors (an audio and a video system header, the SofdecStream record and
the CRITAGS block).  ``parse`` walks that structure, ``problems`` lists every
retail muxing rule a stream breaks, and ``mux`` writes a new stream by the same
rules from an MPEG-1 video elementary stream and an ADX file.  Nothing here
decodes video or audio: the encoder tool and its round trip use ffmpeg.

Every rule below was read from the retail bytes and is re-proved against the
retail streams by the retail-gated tests, including a byte-exact remux of the
retail elementary streams.  The game's header stage (XBE 0x3CB940 -> 0x3CB8B0
-> 0x3CB750) reads only "SofdecStream" at sector 2 + 32 and bytes 0..14 of the
0xE0 stream entry; the CRI demuxer and decoder that run after it were not
executed, so the rest is retail practice copied exactly, not an observed need.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import struct

SECTOR = 2048
PACK_START = b"\0\0\1\xba"
END_START = b"\0\0\1\xb9"
SYSTEM, PADDING, PRIVATE_2, AUDIO, VIDEO = 0xBB, 0xBE, 0xBF, 0xC0, 0xE0

STREAM_RATE = 13356861      # SofdecStream +0xA2 (bytes/s) in every retail ADX stream
MUX_RATE = -(-STREAM_RATE // 50)  # 267,138 x 50 bytes/s: pack header and system header rate
AUDIO_PACK_TICKS = 3360     # one 2,016-byte ADX payload = 1,792 stereo samples at 48 kHz
VIDEO_HEADER = 12           # every video PES header, stuffed to one size
VIDEO_PAYLOAD = SECTOR - 12 - 6 - VIDEO_HEADER        # 2,018
AUDIO_HEADER = 7            # STD buffer (scale 0, size 4) + PTS
AUDIO_PAYLOAD = 2016        # 112 ADX blocks of 18 bytes
AUDIO_CLOSE = b"\0\0\1\xbe\0\1\x0f"                     # 7-byte padding PES ending each full audio pack
RECORD_SIZE = SECTOR - 12 - 6                           # 2,030-byte private stream 2 payload
CRITAGS_SIZE = 576
ADX_HEADER_SIZE = 288
ADX_BLOCK = 18
ADX_END = b"\x80\x01\x00\x0e" + bytes(14)
ADX_SAMPLE_RATE, ADX_CHANNELS = 48000, 2
SUPPORTED_SIZES = ((640, 480), (256, 144))              # boot/menu movies and Crib reels
BOOT_SIZE = (640, 480)      # the size the proved 10,171,344-byte boot allocation belongs to


def require(ok, message):
    if not ok:
        raise ValueError(message)


# ---------------------------------------------------------------- MPEG fields

def timestamp(raw, at=0):
    """A 33-bit PTS/DTS/SCR from its 5-byte marker-bit encoding."""
    b = raw[at:at + 5]
    return ((b[0] >> 1) & 7) << 30 | b[1] << 22 | (b[2] >> 1) << 15 | b[3] << 7 | b[4] >> 1


def timestamp_bytes(prefix, value):
    require(0 <= value < 1 << 33, "timestamp out of range")
    return bytes(((prefix << 4) | ((value >> 29) & 0x0E) | 1, (value >> 22) & 0xFF,
                  ((value >> 14) & 0xFE) | 1, (value >> 7) & 0xFF, ((value << 1) & 0xFE) | 1))


def rate_bytes(rate):
    require(0 < rate < 1 << 22, "mux rate out of range")
    return bytes((0x80 | rate >> 15, (rate >> 7) & 0xFF, ((rate << 1) & 0xFE) | 1))


SCR_TICKS_PER_PACK = 13799649782526   # x 1e-12: 90 kHz ticks per 2,048-byte pack, see scr()
SCR_OFFSET = 560642000000             # x 1e-12: half a tick (rounding) plus 9 bytes of arrival


def scr(index):
    """System clock reference of pack ``index``, 90 kHz: floor(i x 13.799649782526 + 0.560642).

    That is the arrival time of pack byte 9 (the byte holding the last SCR bit,
    as MPEG-1 defines it), rounded half up, at 13,356,860.71 bytes/s, a hair
    under the record's 13,356,861.  CRI's own floating-point arithmetic was not
    identified; this line reproduces every one of the 131,523 pack indices the
    29 retail ADX streams use (they all agree index by index), with at least
    3.5e-6 ticks to spare, and the retail-gated test re-proves it.
    """
    return (index * SCR_TICKS_PER_PACK + SCR_OFFSET) // 10 ** 12


def pack_header(index):
    return PACK_START + timestamp_bytes(2, scr(index)) + rate_bytes(MUX_RATE)


def pes(stream_id, body):
    require(len(body) <= 0xFFFF, "PES body too long")
    return b"\0\0\1" + bytes((stream_id,)) + struct.pack(">H", len(body)) + body


def padding(size):
    """A padding PES of exactly ``size`` bytes as CRI writes it: 0x0F then 0xFF fill."""
    require(size >= 7, "padding PES needs at least 7 bytes")
    return pes(PADDING, b"\x0f" + b"\xff" * (size - 7))


# ------------------------------------------------------ MPEG-1 video stream

@dataclass(frozen=True)
class Sequence:
    width: int
    height: int
    aspect: int
    frame_rate: int
    bit_rate: int
    vbv: int
    constrained: int
    intra_matrix: bool
    non_intra_matrix: bool
    size: int               # header bytes including loaded matrices


@dataclass(frozen=True)
class Picture:
    offset: int             # elementary-stream offset of the 00 00 01 00 start code
    kind: str               # "I", "P" or "B"
    temporal: int
    gop: int
    display: int            # display index over the whole stream
    vbv_delay: int
    unit: int               # where its access unit starts: the first sequence/GOP/user-data
                            # header after the previous picture's slices, else ``offset``


@dataclass
class Video:
    sequences: list = field(default_factory=list)   # (offset, Sequence)
    gops: list = field(default_factory=list)        # (offset, closed, broken, time_code_pictures, drop)
    pictures: list = field(default_factory=list)
    end_codes: list = field(default_factory=list)
    other: list = field(default_factory=list)       # (offset, code) of extension/user data


def sequence_header(es, at):
    require(es[at:at + 4] == b"\0\0\1\xb3" and len(es) >= at + 12, "no MPEG-1 sequence header")
    h = es[at:at + 12]
    intra = (h[11] >> 1) & 1
    non_intra = h[11] & 1 if not intra else (es[at + 11 + 64] & 1)
    return Sequence(width=h[4] << 4 | h[5] >> 4, height=(h[5] & 15) << 8 | h[6], aspect=h[7] >> 4,
                    frame_rate=h[7] & 15, bit_rate=h[8] << 10 | h[9] << 2 | h[10] >> 6,
                    vbv=(h[10] & 0x1F) << 5 | h[11] >> 3, constrained=(h[11] >> 2) & 1,
                    intra_matrix=bool(intra), non_intra_matrix=bool(non_intra),
                    size=12 + 64 * intra + 64 * non_intra)


def start_codes(es):
    at = es.find(b"\0\0\1")
    while at != -1 and at + 3 < len(es):
        yield at, es[at + 3]
        at = es.find(b"\0\0\1", at + 3)


def video(es):
    """Sequence, GOP and picture headers of an MPEG-1 video elementary stream."""
    es = bytes(es)
    out, base, gop_pictures, gop, pending = Video(), 0, 0, -1, None
    for at, code in start_codes(es):
        if code in (0xB3, 0xB8, 0xB2, 0xB5) and pending is None:
            pending = at
        if 0x01 <= code <= 0xAF:
            pending = None
        if code == 0xB3:
            out.sequences.append((at, sequence_header(es, at)))
        elif code == 0xB8:
            require(at + 8 <= len(es), "truncated GOP header")
            v = int.from_bytes(es[at + 4:at + 8], "big")
            if gop >= 0:
                base += gop_pictures
            gop, gop_pictures = gop + 1, 0
            # time code at 30 pictures per second (drop flag, h, m, marker, s, pictures)
            code = ((v >> 26 & 31) * 3600 + (v >> 20 & 63) * 60 + (v >> 13 & 63)) * 30 + (v >> 7 & 63)
            out.gops.append((at, v >> 6 & 1, v >> 5 & 1, code, v >> 31))
        elif code == 0x00:
            require(at + 8 <= len(es) and gop >= 0, "picture outside a GOP")
            b = es[at + 4:at + 8]
            kind = " IPBD"[(b[1] >> 3) & 7]
            require(kind in "IPB", "unsupported picture coding type")
            temporal = b[0] << 2 | b[1] >> 6
            out.pictures.append(Picture(at, kind, temporal, gop, base + temporal,
                                        (b[1] & 7) << 13 | b[2] << 5 | b[3] >> 3,
                                        at if pending is None else pending))
            gop_pictures, pending = gop_pictures + 1, None
        elif code == 0xB7:
            out.end_codes.append(at)
        elif code in (0xB2, 0xB5, 0xB4):
            out.other.append((at, code))
        else:
            require(0x01 <= code <= 0xAF, f"unexpected start code 0x{code:02x} in video")
    require(out.pictures, "no pictures in the video stream")
    return out


CLOCK_DENOMINATOR = 2997 * 2997     # exact picture times are numerators over this, in 90 kHz ticks


def picture_clock(seconds, frames):
    """Exact 90 kHz time of a time-code position, as a numerator over CLOCK_DENOMINATOR.

    CRI's time is (s + f / 29.97) x 30 / 29.97 seconds, where ``seconds`` is the
    GOP time code in whole seconds and ``frames`` the GOP time code's picture
    count plus the picture's temporal reference (it may pass 29).  So pictures
    step by about 3006.009 ticks and every time-code second is 90,090.09.
    """
    return 270000000 * (2997 * seconds + 100 * frames)


def picture_time(seconds, frames):
    """The stamped (rounded half up) form of ``picture_clock``."""
    return (2 * picture_clock(seconds, frames) + CLOCK_DENOMINATOR) // (2 * CLOCK_DENOMINATOR)


def display_clocks(v):
    """Exact time numerator of every display index, from each picture's own GOP time code."""
    clocks = {}
    for picture in v.pictures:
        seconds, frames = divmod(v.gops[picture.gop][3], 30)
        clocks[picture.display] = picture_clock(seconds, frames + picture.temporal)
    return clocks


def display_times(v):
    """Stamped presentation time of every display index."""
    return {d: (2 * n + CLOCK_DENOMINATOR) // (2 * CLOCK_DENOMINATOR) for d, n in display_clocks(v).items()}


def expected_timestamps(v):
    """CRI's 90 kHz stamps for each coded picture: (pts, dts or None).

    PTS is the picture's time-code time.  B pictures carry PTS only.  I and P
    pictures carry PTS and DTS, where DTS is the time of the display index after
    the previous anchor's (so the decoding clock runs one picture behind the
    display clock); the first anchor has DTS 0.  Proved over every picture of the
    retail streams by the retail-gated tests.
    """
    times, stamps, previous = display_times(v), [], None
    for picture in v.pictures:
        pts = times[picture.display]
        if picture.kind == "B":
            stamps.append((pts, None))
        else:
            stamps.append((pts, 0 if previous is None else times[previous + 1]))
            previous = picture.display
    return stamps


# ------------------------------------------------------------------- ADX audio

@dataclass(frozen=True)
class Adx:
    header: bytes
    blocks: bytes           # channel-interleaved 18-byte blocks, end block excluded
    samples: int
    channels: int
    sample_rate: int
    version: int


def adx(raw):
    raw = bytes(raw)
    require(len(raw) >= 36 and raw[:2] == b"\x80\x00", "not an ADX file")
    offset = struct.unpack_from(">H", raw, 2)[0]
    size = offset + 4
    require(raw[size - 6:size] == b"(c)CRI", "ADX copyright marker missing")
    encoding, block, bits, channels = raw[4:8]
    rate, samples = struct.unpack_from(">II", raw, 8)
    version = raw[0x12]
    require((encoding, block, bits) == (3, ADX_BLOCK, 4), "only standard 4-bit ADX (type 3) is supported")
    require(raw[0x13] == 0, "encrypted ADX is not supported")
    body = raw[size:]
    require(body.endswith(ADX_END), "ADX end block missing")
    blocks = body[:-len(ADX_END)]
    frame = ADX_BLOCK * channels
    require(len(blocks) % frame == 0, "ADX body is not whole stereo frames")
    require(len(blocks) // frame * 32 >= samples > (len(blocks) // frame - 1) * 32,
            "ADX sample count and block count disagree")
    return Adx(raw[:size], blocks, samples, channels, rate, version)


def adx_header(samples, *, channels=ADX_CHANNELS, sample_rate=ADX_SAMPLE_RATE, history=None):
    """The 288-byte version-4 ADX header every retail Sofdec audio stream starts with.

    The eight history bytes are the decoder's starting predictor state per
    channel (two samples each).  ffmpeg's encoder starts from zero, so its
    blocks are re-headed with zero history.
    """
    history = bytes(4 * max(2, channels)) if history is None else bytes(history)
    require(len(history) == 4 * max(2, channels), "ADX history must be 2 samples per channel")
    head = (b"\x80\x00" + struct.pack(">H", ADX_HEADER_SIZE - 4) + bytes((3, ADX_BLOCK, 4, channels)) +
            struct.pack(">II", sample_rate, samples) + struct.pack(">H", 500) + b"\x04\x00" + bytes(4) + history)
    return head.ljust(ADX_HEADER_SIZE - 6, b"\0") + b"(c)CRI"


def retail_adx(raw):
    """ADX re-headed as a retail Sofdec audio stream: v4 288-byte header, blocks, end block."""
    parsed = adx(raw)
    require(parsed.channels == ADX_CHANNELS and parsed.sample_rate == ADX_SAMPLE_RATE,
            "Sofdec audio must be 48,000 Hz stereo ADX")
    if parsed.version == 4 and len(parsed.header) == ADX_HEADER_SIZE:
        return parsed.header + parsed.blocks + ADX_END
    return adx_header(parsed.samples) + parsed.blocks + ADX_END


# --------------------------------------------------- SofdecStream / CRITAGS

def _name83(name):
    stem, _, ext = name.rpartition(".")
    require(stem and 0 < len(stem) <= 8 and len(ext) <= 3 and name.isascii(), f"not an 8.3 name: {name}")
    return (stem.ljust(8) + "." + ext.ljust(3)).encode("ascii")


def _entry_name(name):
    raw = name.encode("ascii")
    require(len(raw) == 12, f"stream entry names are 12 characters: {name}")
    return raw


def _date(value):
    require(len(value) == 12 and value.isdigit(), "dates are YYYYMMDDHHMM")
    return value.encode("ascii")


def record(*, name, date, frames, width, height, video_ms, audio_ms, video_name, video_date,
           audio_name, audio_date, rate=STREAM_RATE, channels=ADX_CHANNELS,
           sample_rate=ADX_SAMPLE_RATE, frame_rate=4):
    """The 2,030-byte SofdecStream record (sector 2's private stream 2 payload)."""
    out = bytearray(RECORD_SIZE)
    out[0x0E:0x26] = b"SofdecStream".ljust(24)
    out[0x26:0x28] = b"\x02\x15"
    out[0x2E:0x3A] = _name83(name)
    out[0x3A:0x46] = _date(date)
    out[0x4E:0x6E] = b"SFM Ver.2.21 2003-08-27 CRI-MW  "
    out[0x6E:0x7E] = struct.pack("<IIII", 2048, 0, 2, 2048)
    out[0x9E:0xA2] = b"\x03\x01\x01\x01"
    struct.pack_into("<IIII", out, 0xA2, rate, audio_ms, video_ms, frames)
    for at, entry_name, entry_date, tail in (
            (0x16E, "<SFM_P2>.TMP", date, b"\xbf"),
            (0x1AE, video_name, video_date,
             bytes((VIDEO, 0, 0xFF, 0xFF, width >> 4, (width & 15) << 4 | height >> 8, height & 0xFF,
                    frame_rate, 1, 0, 0, 0x10, 0, 0x0F, 3, 0))),
            (0x1EE, audio_name, audio_date,
             bytes((AUDIO, 0, 0, channels)) + struct.pack("<I", sample_rate))):
        out[at:at + 12] = _entry_name(entry_name)
        out[at + 12:at + 24] = _date(entry_date)
        out[at + 24:at + 24 + len(tail)] = tail
    return bytes(out)


def _slot(value, width):
    text = str(value).encode("ascii") + b"\0"
    require(len(text) <= width, "CRITAGS field overflow")
    return text.ljust(width, b" ")


def critags(frames, width, height):
    """The 576-byte CRITAGS block (sector 3): CRI's encoder tags, nine 64-byte rows.

    Only the frame count, the last frame index and the picture size vary between
    the retail streams; every other byte is the same in all 30.
    """
    require(0 < frames < 10 ** 8 and 0 < width < 10 ** 4 and 0 < height < 10 ** 4, "CRITAGS field out of range")
    rows = (
        b"CRITAGS\x000000230\x00SFVFTRS\x000000210\x00SFV\x00    200\x00    SFV:TOP\x0030\x00     ",
        b"000:00:00:00\x000V029970\x00" + _slot(frames, 10) + b"IPB\x00234\x000\x00  1   SFV:DCD\x0010\x00     ",
        _slot(frames, 10) + b"0\x00    SFV:ECD\x00f0\x00     CRI_SVE 3.80CRI\x00\x00" + b" " * 15,
        _slot(width, 5) + _slot(height, 5) + b"V0\x00       " + _slot(frames - 1, 12) +
        b"6000000\x006000000\x000\x00      N10000\x00 ",
        b"10000\x00 10000\x00 YN0\x00        NO\x00   0\x00    0\x00    0\x00  N1\x00   4\x00   2\x00   ",
        b"HCON\x000  0.0000\x00" + b" 1.0000\x00" * 6 + b" ",
        b"TMPGLib 1.95.14\x00SFV:SRC\x0030\x00     \x98\x06E\x00" + b" " * 12 + _slot(width, 5) + _slot(height, 5) +
        b"29970\x00",
        b"32\x00" + _slot(frames, 13) + b"SFV:BTM\x0040\x00     !  0 /#" + b" " * 25,
        b"Sofdec Elem Stm\x00200\x00        \x00\x00\x01\xb7SFVFTRE\x000000000\x00CRITAGE\x000000000\x00",
    )
    require(all(len(row) == 64 for row in rows), "CRITAGS layout drifted")
    return b"".join(rows)


def system_header(stream_id, *, rate=MUX_RATE):
    """Sector 0 names only the audio stream, sector 1 only the video stream."""
    if stream_id == AUDIO:
        bounds, entry = b"\x06\x20", bytes((AUDIO, 0xC0, 0x04))      # audio bound 1, 4 x 128 bytes
    else:
        bounds, entry = b"\x02\x21", bytes((VIDEO, 0xE0, 0x2E))      # video bound 1, 46 x 1024 bytes
    return pes(SYSTEM, rate_bytes(rate) + bounds + b"\xff" + entry)


# ----------------------------------------------------------------- the parser

@dataclass
class Packet:
    pack: int
    stream_id: int
    offset: int             # file offset of the PES start code
    length: int             # PES length field
    header: bytes           # bytes between the length field and the payload
    pts: int | None
    dts: int | None
    payload: int            # file offset of the payload
    payload_size: int


@dataclass
class Stream:
    size: int
    packs: list             # (scr, mux_rate) per pack
    layout: list            # per pack: tuple of (stream_id, PES length)
    packets: list           # every Packet in file order
    record: bytes
    critags: bytes
    end_sector: bool
    video_es: bytes
    audio_es: bytes


def parse(data):
    """Walk a Sofdec stream pack by pack.  Raises ValueError on any structural break."""
    data = memoryview(bytes(data))
    require(len(data) >= 6 * SECTOR and len(data) % SECTOR == 0, "not a whole number of 2,048-byte sectors")
    packs, layout, packets, video_parts, audio_parts = [], [], [], [], []
    end_sector = False
    for index in range(len(data) // SECTOR):
        at = index * SECTOR
        sector = data[at:at + SECTOR]
        if sector[:4] == END_START:
            require(index == len(data) // SECTOR - 1, "program end code before the last sector")
            require(all(b == 0xFF for b in sector[4:]), "end sector fill is not 0xFF")
            end_sector = True
            continue
        require(sector[:4] == PACK_START and sector[4] >> 4 == 2, f"pack {index} is not an MPEG-1 pack")
        b = bytes(sector[4:12])
        require(b[0] & 1 and b[2] & 1 and b[4] & 1 and b[5] & 0x80 and b[7] & 1, f"pack {index} marker bits")
        packs.append((timestamp(b), (b[5] & 0x7F) << 15 | b[6] << 7 | b[7] >> 1))
        p, units = 12, []
        while p < SECTOR:
            require(sector[p:p + 3] == b"\0\0\1" and p + 6 <= SECTOR, f"pack {index}: broken packet at +{p}")
            sid = sector[p + 3]
            length = struct.unpack(">H", sector[p + 4:p + 6])[0]
            require(p + 6 + length <= SECTOR, f"pack {index}: packet crosses the sector")
            units.append((sid, length))
            body = bytes(sector[p + 6:p + 6 + length])
            if sid in (VIDEO, AUDIO):
                q = 0
                while q < len(body) and body[q] == 0xFF:
                    q += 1
                require(q <= 16 and q < len(body), f"pack {index}: bad stuffing")
                if body[q] >> 6 == 1:
                    q += 2
                pts = dts = None
                if body[q] >> 4 == 2:
                    pts, q = timestamp(body, q), q + 5
                elif body[q] >> 4 == 3:
                    require(body[q + 5] >> 4 == 1, f"pack {index}: DTS prefix")
                    pts, dts, q = timestamp(body, q), timestamp(body, q + 5), q + 10
                else:
                    require(body[q] == 0x0F, f"pack {index}: bad PES header")
                    q += 1
                packets.append(Packet(index, sid, at + p, length, body[:q], pts, dts, at + p + 6 + q, length - q))
                (video_parts if sid == VIDEO else audio_parts).append(body[q:])
            elif sid in (PRIVATE_2, PADDING, SYSTEM):
                packets.append(Packet(index, sid, at + p, length, b"", None, None, at + p + 6, length))
            else:
                raise ValueError(f"pack {index}: unexpected stream 0x{sid:02x}")
            p += 6 + length
        layout.append(tuple(units))
    rec = next((p for p in packets if p.pack == 2 and p.stream_id == PRIVATE_2), None)
    tags = next((p for p in packets if p.pack == 3 and p.stream_id == PRIVATE_2), None)
    require(rec is not None and tags is not None, "SofdecStream record or CRITAGS block missing")
    return Stream(len(data), packs, layout, packets,
                  bytes(data[rec.payload:rec.payload + rec.payload_size]),
                  bytes(data[tags.payload:tags.payload + tags.payload_size]),
                  end_sector, b"".join(video_parts), b"".join(audio_parts))


def record_fields(raw):
    require(len(raw) >= 0x22E and raw[0x0E:0x1A] == b"SofdecStream", "no SofdecStream record")
    rate, audio_ms, video_ms, frames = struct.unpack_from("<IIII", raw, 0xA2)
    v, a = raw[0x1AE:0x1EE], raw[0x1EE:0x22E]
    return dict(name=raw[0x2E:0x3A].decode("ascii", "replace"), date=raw[0x3A:0x46].decode("ascii", "replace"),
                rate=rate, audio_ms=audio_ms, video_ms=video_ms, frames=frames,
                video_name=v[:12].decode("ascii", "replace"), video_date=v[12:24].decode("ascii", "replace"),
                video_id=v[24], width=v[28] << 4 | v[29] >> 4, height=(v[29] & 15) << 8 | v[30],
                frame_rate=v[31], audio_name=a[:12].decode("ascii", "replace"),
                audio_date=a[12:24].decode("ascii", "replace"), audio_id=a[24], audio_type=a[25],
                channels=a[27], sample_rate=struct.unpack_from("<I", a, 28)[0])


def digest(data):
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------ the muxer

def video_header(stamp):
    """The three 12-byte video PES headers CRI writes (stuffed to one size)."""
    pts, dts = stamp if stamp is not None else (None, None)
    if pts is None:
        return b"\xff" * 9 + b"\x60\x2e\x0f"
    if dts is None:
        return b"\xff" * 5 + b"\x60\x2e" + timestamp_bytes(2, pts)
    return b"\x60\x2e" + timestamp_bytes(3, pts) + timestamp_bytes(1, dts)


def audio_header(index):
    return b"\x40\x04" + timestamp_bytes(2, index * AUDIO_PACK_TICKS)


def end_stamp(v, times):
    """The stamp CRI gives the sequence end code: the last coded picture's form and PTS;
    after an anchor, DTS is the next picture time on that anchor's GOP time code."""
    last = v.pictures[-1]
    if last.kind == "B":
        return times[last.display], None
    seconds, frames = divmod(v.gops[last.gop][3], 30)
    return times[last.display], picture_time(seconds, frames + last.temporal + 1)


@dataclass(frozen=True)
class VideoPacket:
    size: int               # payload bytes
    stamp: tuple | None     # (pts, dts or None) or None
    clock: int | None       # coded index of the last access unit starting here (interleave clock)


def video_plan(v, es_size):
    """Split the video elementary stream into CRI's PES packets.

    Every packet but the last carries 2,018 bytes.  A packet carries the stamp of
    the first access unit that starts in it (a picture's unit starts at its GOP /
    sequence header when it has one; the sequence end code is a unit of its own).
    """
    require(v.end_codes and v.end_codes[-1] == es_size - 4, "video must end with the sequence end code")
    stamps, times = expected_timestamps(v), display_times(v)
    units = [(p.unit, stamps[k]) for k, p in enumerate(v.pictures)] + [(es_size - 4, end_stamp(v, times))]
    starts = [(p.unit, k) for k, p in enumerate(v.pictures)]
    packets, u, s, start = [], 0, 0, 0
    while start < es_size:
        end = min(start + VIDEO_PAYLOAD, es_size)
        stamp = None
        while u < len(units) and units[u][0] < end:
            if stamp is None and units[u][0] >= start:
                stamp = units[u][1]
            u += 1
        clock = None
        while s < len(starts) and starts[s][0] < end:
            clock = starts[s][1]
            s += 1
        packets.append(VideoPacket(end - start, stamp, clock))
        start = end
    return packets


def interleave(packets, audio_packs, clocks):
    """Pack order after the four header sectors: ("A", n) / ("V", j).

    Audio pack 0 leads.  After each video pack in which the access unit of coded
    picture c starts, audio packs follow while their PTS (n x 3360, exact) is
    strictly before the exact, unrounded time of display index c; the rest of
    the audio follows the last video pack.  (Two retail ties on the rounded
    stamps go opposite ways, which the unrounded comparison explains.)
    """
    order, a = [("A", 0)], 1
    for j, packet in enumerate(packets):
        order.append(("V", j))
        if packet.clock is not None:
            limit = clocks.get(packet.clock)
            while a < audio_packs and (limit is None or a * AUDIO_PACK_TICKS * CLOCK_DENOMINATOR < limit):
                order.append(("A", a))
                a += 1
    order.extend(("A", n) for n in range(a, audio_packs))
    return order


def _eighty_three(name):
    """A 12-character 8.3 entry name: long stems as Windows shortens them, short ones space padded."""
    stem, _, ext = name.rpartition(".")
    stem = stem.upper().replace(" ", "_")
    return (stem[:6] + "~1" if len(stem) > 8 else stem.ljust(8)) + "." + ext.upper()[:3].ljust(3)


def mux(video_es, audio, *, name="intro.mov", date="202609220000", video_name=None, audio_name=None,
        video_date=None, audio_date=None, video_ms=None, audio_ms=None):
    """A Sofdec stream from an MPEG-1 video elementary stream and a 48 kHz stereo ADX file.

    The video must already be what the game gets: one sequence header at the
    start, closed first GOP, contiguous 30-picture time codes, the sequence end
    code last (``tools/nfl2k5_intro_encode.py`` prepares ffmpeg's output).
    """
    video_es = bytes(video_es)
    v = video(video_es)
    require(len(v.sequences) == 1 and v.sequences[0][0] == 0, "video needs exactly one sequence header, at the start")
    seq = v.sequences[0][1]
    require((seq.width, seq.height) in SUPPORTED_SIZES, f"unsupported movie size {seq.width}x{seq.height}")
    require(seq.frame_rate == 4, "video must be 29.97 frames per second (frame_rate_code 4)")
    require(not v.other or all(code == 0xB2 for _, code in v.other), "MPEG-2 extensions are not MPEG-1 video")
    base = 0
    for g, (_, _, _, code, drop) in enumerate(v.gops):
        require(code == base and not drop, "GOP time codes must count pictures contiguously from zero")
        base += sum(1 for p in v.pictures if p.gop == g)
    require(v.gops[0][1] == 1, "the first GOP must be closed")
    require(v.pictures[0].kind == "I" and v.pictures[0].display == 0, "the stream must open on an I picture")
    audio_es = retail_adx(audio)
    parsed = adx(audio_es)
    frames = len(v.pictures)
    stem = name.rpartition(".")[0]
    video_name = video_name or _eighty_three(stem + ".SFV")
    audio_name = audio_name or _eighty_three(stem + ".SFA")
    rec = record(name=name, date=date, frames=frames, width=seq.width, height=seq.height,
                 video_ms=(frames * 1001 + 15) // 30 if video_ms is None else video_ms,
                 audio_ms=parsed.samples * 1000 // ADX_SAMPLE_RATE if audio_ms is None else audio_ms,
                 video_name=video_name, video_date=video_date or date,
                 audio_name=audio_name, audio_date=audio_date or date)
    packets = video_plan(v, len(video_es))
    chunks = [audio_es[at:at + AUDIO_PAYLOAD] for at in range(0, len(audio_es), AUDIO_PAYLOAD)]
    order = interleave(packets, len(chunks), display_clocks(v))
    out = bytearray()
    out += pack_header(0) + system_header(AUDIO)
    out += padding(SECTOR - len(out))
    out += pack_header(1) + system_header(VIDEO)
    out += padding(2 * SECTOR - len(out))
    out += pack_header(2) + pes(PRIVATE_2, rec)
    out += pack_header(3) + pes(PRIVATE_2, critags(frames, seq.width, seq.height))
    out += padding(4 * SECTOR - len(out))
    offsets, at = [], 0
    for packet in packets:
        offsets.append(at)
        at += packet.size
    for kind, n in order:
        index = len(out) // SECTOR
        if kind == "V":
            packet = packets[n]
            body = pes(VIDEO, video_header(packet.stamp) + video_es[offsets[n]:offsets[n] + packet.size])
        else:
            body = pes(AUDIO, audio_header(n) + chunks[n])
        sector = pack_header(index) + body
        rest = SECTOR - len(sector)
        require(rest == 0 or rest >= 7, "a pack cannot be closed with a padding packet")
        out += sector + (padding(rest) if rest else b"")
    out += END_START + b"\xff" * (SECTOR - 4)
    return bytes(out)


def fields_for_remux(stream):
    """The record fields ``mux`` cannot derive (names, dates, CRI's durations)."""
    f = record_fields(stream.record)
    return dict(name=f["name"].replace(" ", ""), date=f["date"], video_name=f["video_name"],
                audio_name=f["audio_name"], video_date=f["video_date"], audio_date=f["audio_date"],
                video_ms=f["video_ms"], audio_ms=f["audio_ms"])


def remux(data):
    """Rebuild a stream from its own elementary streams and record fields."""
    stream = parse(data)
    return mux(stream.video_es, stream.audio_es, **fields_for_remux(stream))


def first_difference(a, b):
    """(sector index, byte offset in sector, what) of the first difference, or None."""
    for index in range(min(len(a), len(b)) // SECTOR):
        x, y = a[index * SECTOR:(index + 1) * SECTOR], b[index * SECTOR:(index + 1) * SECTOR]
        if x != y:
            at = next(i for i in range(SECTOR) if x[i] != y[i])
            what = "pack clock" if 4 <= at < 12 else "packet layout or header" if at < 40 else "payload"
            return index, at, what
    return None if len(a) == len(b) else (min(len(a), len(b)) // SECTOR, 0, "length")


# ------------------------------------------------- preparing ffmpeg's output

RETAIL_ASPECT = 12          # aspect_ratio_information in every retail sequence header
RETAIL_VBV = 112            # vbv_buffer_size (x 16 kbit) in every retail sequence header
VBR_BIT_RATE = 0x3FFFF      # the variable-bit-rate marker every retail stream carries
RETAIL_MAX_PICTURE = 128865  # largest coded picture in the 640x480 retail streams (tips_defense I)


def picture_sizes(v, es_size):
    """Coded size of every picture: from its access unit start to the next one's."""
    units = [p.unit for p in v.pictures] + [es_size - 4 if v.end_codes else es_size]
    return [units[k + 1] - units[k] for k in range(len(v.pictures))]


def conform_video(es):
    """ffmpeg's MPEG-1 video brought to the retail streams' sequence-level form.

    ffmpeg repeats the sequence header before every GOP, leaves the end code
    off and writes its own aspect, bit-rate and VBV fields.  Every retail stream
    carries one sequence header (aspect code 12, the 0x3FFFF variable-rate
    marker, VBV size 112), vbv_delay 0xFFFF in every picture header, and ends
    with 00 00 01 B7.  Only those fixed-position header fields and the repeated
    headers change; no slice byte is touched.  When the last 2,018-byte video
    payload would leave 1 to 6 bytes in its pack (too few for a padding packet),
    zero bytes go before the end code (MPEG-1 next_start_code stuffing) so the
    last pack is exactly full.  Returns (stream, receipt).
    """
    es = bytearray(es)
    v = video(es)
    require(v.sequences and v.sequences[0][0] == 0, "video must start with a sequence header")
    first = v.sequences[0][1]
    head = bytes(es[:first.size])
    repeats = [at for at, _ in v.sequences[1:]]
    require(all(bytes(es[at:at + first.size]) == head for at in repeats), "repeated sequence headers differ")
    for at in reversed(repeats):
        del es[at:at + first.size]
    es[7] = RETAIL_ASPECT << 4 | es[7] & 15
    word = int.from_bytes(es[8:12], "big")
    es[8:12] = (VBR_BIT_RATE << 14 | 1 << 13 | RETAIL_VBV << 3 | word & 7).to_bytes(4, "big")
    v = video(es)
    for picture in v.pictures:
        at = picture.offset + 4
        es[at:at + 4] = (int.from_bytes(es[at:at + 4], "big") | 0xFFFF << 3).to_bytes(4, "big")
    if not (v.end_codes and v.end_codes[-1] == len(es) - 4):
        require(not v.end_codes, "sequence end code in the middle of the video")
        es += b"\0\0\1\xb7"
    stuffing = 0
    if 0 < VIDEO_PAYLOAD - len(es) % VIDEO_PAYLOAD < 7 and len(es) % VIDEO_PAYLOAD:
        stuffing = VIDEO_PAYLOAD - len(es) % VIDEO_PAYLOAD
        es[-4:-4] = bytes(stuffing)
    return bytes(es), dict(sequence_headers_removed=len(repeats), aspect_code=RETAIL_ASPECT,
                           vbv_buffer_size=RETAIL_VBV, bit_rate_field="0x3FFFF",
                           pictures=len(v.pictures), end_code_stuffing=stuffing)


# ------------------------------------------------------------- validation

HEADER_STAGE_READS = ((32, 128), (2080, 128), (4128, 128), (4496, 128), (4560, 128))
BOOT_ALLOCATION = 10171344  # native request for a 640x480 stream (retail boot movies, traced)


def header_stage(data):
    """The game's movie header stage, emulated from the traced XBE code.

    0x3CB940 reads 0x80 bytes at file offset 0x20; 0x3CB8B0 compares 12 bytes
    with "SofdecStream" and, when they differ, skips 0x780 and reads again (one
    try per sector); on a match it skips 0xF0 and reads 0x80 for 0x3CB750, which
    wants 0xE0 at buffer[8] and otherwise steps back 0x40 (a 64-byte stride over
    the stream entries).  Width is buffer[12] << 4 rounded up to 64, height
    buffer[13] << 8 | buffer[14].  Returns (reads, width, height).  The native
    tests run the real code; this lets the encoder report the same facts.
    """
    reads, at = [], 0x20
    while True:
        require(at + 0x80 <= len(data) and len(reads) < 64, "the header stage finds no SofdecStream record")
        reads.append((at, 0x80))
        buffer, at = bytes(data[at:at + 0x80]), at + 0x80
        if buffer[:12] == b"SofdecStream":
            break
        at += 0x780
    at += 0xF0
    while True:
        require(at + 0x80 <= len(data) and len(reads) < 96, "the header stage finds no video stream entry")
        reads.append((at, 0x80))
        buffer, at = bytes(data[at:at + 0x80]), at + 0x80
        if buffer[8] == VIDEO:
            break
        at -= 0x40
    return reads, -(-(buffer[12] << 4) // 64) * 64, buffer[13] << 8 | buffer[14]


def problems(data, *, size=BOOT_SIZE):
    """Every way ``data`` departs from the retail Sofdec rules; an empty list when it conforms.

    Checks what the game's header stage reads, the two elementary streams and
    the record, then the whole layout by rebuilding the stream from its own
    elementary streams with ``mux`` (which reproduces all 29 retail ADX streams
    byte for byte) and comparing.
    """
    found = []
    try:
        stream = parse(data)
        fields = record_fields(stream.record)
        v = video(stream.video_es)
        audio = adx(stream.audio_es)
    except (ValueError, IndexError, struct.error) as exc:
        return [f"structure: {exc}"]
    try:
        reads, width, height = header_stage(data)
        if tuple(reads) != HEADER_STAGE_READS:
            found.append(f"header stage reads {reads}, retail streams read {list(HEADER_STAGE_READS)}")
        if (width, height) != tuple(size):
            found.append(f"header stage sees {width}x{height}, expected {size[0]}x{size[1]}")
    except ValueError as exc:
        found.append(f"header stage: {exc}")
    if len(v.sequences) != 1 or v.sequences[0][0] != 0:
        found.append("video: needs exactly one sequence header, at the start")
    else:
        seq = v.sequences[0][1]
        if (seq.width, seq.height) != (fields["width"], fields["height"]):
            found.append("record picture size differs from the video")
        if (seq.width, seq.height) != tuple(size) or seq.frame_rate != 4:
            found.append(f"video is {seq.width}x{seq.height} rate code {seq.frame_rate}, expected "
                         f"{size[0]}x{size[1]} at 29.97 (code 4)")
        if (seq.aspect, seq.bit_rate, seq.vbv) != (RETAIL_ASPECT, VBR_BIT_RATE, RETAIL_VBV):
            found.append("video sequence header differs from retail (aspect 12, rate 0x3FFFF, VBV 112)")
    if fields["frames"] != len(v.pictures):
        found.append("record frame count differs from the video")
    if (fields["video_id"], fields["audio_id"], fields["audio_type"]) != (VIDEO, AUDIO, 0):
        found.append("record stream entries are not the retail ADX layout")
    if (fields["channels"], fields["sample_rate"], audio.channels, audio.sample_rate) != (2, 48000, 2, 48000):
        found.append("audio must be 48,000 Hz stereo ADX, and the record must say so")
    if audio.version != 4 or len(audio.header) != ADX_HEADER_SIZE:
        found.append("audio does not start with the retail 288-byte ADX v4 header")
    if not v.end_codes or v.end_codes[-1] != len(stream.video_es) - 4:
        found.append("video does not end with the sequence end code")
    largest = max(picture_sizes(v, len(stream.video_es)))
    if largest > RETAIL_MAX_PICTURE and tuple(size) == BOOT_SIZE:
        found.append(f"largest picture is {largest} bytes; the retail 640x480 streams stay within {RETAIL_MAX_PICTURE}")
    bad = next((i for i, (clock, rate) in enumerate(stream.packs) if clock != scr(i) or rate != MUX_RATE), None)
    if bad is not None:
        found.append(f"pack {bad}: clock or mux rate differs from the retail rule")
    if not stream.end_sector:
        found.append("no program end sector")
    try:
        difference = first_difference(bytes(data), remux(data))
        if difference:
            found.append("layout: sector {} byte {} differs from the retail muxing rules ({})".format(*difference))
    except ValueError as exc:
        found.append(f"layout: {exc}")
    return found


def summary(data):
    """Small facts for receipts: sizes, counts, duration and hashes."""
    stream = parse(data)
    fields = record_fields(stream.record)
    v = video(stream.video_es)
    audio = adx(stream.audio_es)
    return dict(bytes=len(data), sha256=digest(data), packs=len(stream.packs),
                width=fields["width"], height=fields["height"], pictures=len(v.pictures), gops=len(v.gops),
                seconds=round(len(v.pictures) * 1001 / 30000, 3), audio_samples=audio.samples,
                video_es_bytes=len(stream.video_es), audio_es_bytes=len(stream.audio_es),
                largest_picture=max(picture_sizes(v, len(stream.video_es))),
                header_sha256=digest(bytes(data[:4 * SECTOR])))

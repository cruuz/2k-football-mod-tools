#!/usr/bin/env python3
"""Swap any of the 850 standalone NFL 2K5 ``AUDO`` sounds inside a COPIED disc.

Menu clicks, crib mini-game effects and voices, draft-board whooshes, the
first-person heartbeat, the crowd chants / pre-cheer / boo / clap / rain beds
in ``gamedata.iff`` and the per-team huddle claps are standalone ``AUDO``
resources embedded in ``.iff`` packages inside the outer archive
``vc_53450030``.  One record is::

    +0x00  0x20-byte wrapper   "AUDO", stored_body_bytes, system_bytes, payload_bytes, 0, 0, 0, 0
    +0x20  system area         inner "AUDO" at +0x0C; self-relative pointers at +0x10 (UTF-16LE name,
                               e.g. "menu-back_01") and +0x14 (8-word descriptor at +0x40 or +0x60:
                               {ch, ch, 0x11, 0x35|0x75, bytes, 0, bytes/ch, rate})
    +0x20+system   payload     Xbox IMA ADPCM, 36 bytes per channel per 64-frame block
    ...            tail        0-12 bytes that follow the payload inside the stored body

The game finds a record by the CRC32 of its case-sensitive UTF-16LE name
(``FUN_00038600``) in whichever package is loaded, so a replacement that keeps
the wrapper, system area, descriptor and tail intact and only rewrites the
payload bytes -- the same block count, so the same byte length -- needs no other
change on the disc.  The exact allocation of every record (span, hashes,
channels, rate, frame count) is pinned by the audited catalog
``reports/assets/nfl2k5_audo_import_capacity.json``; this tool resolves each
record's span on the *target* disc through XDVDFS + the archive table and
refuses to write unless the wrapper still carries the retail metadata and (unless
``--force``) the retail payload.

``tools/nfl_audo_wav_xiso_workflow.py`` (the reviewed ``menu-back_01`` writer)
is untouched; this tool generalises the same rules to every record by name.

Sub-commands (only ``replace`` writes, in place, so point it at a copy)::

    list     XISO [--name GLOB] [--outer N] [--json]
    export   XISO --out DIR (--name GLOB ... | --key outer_0346_chunk_0095 ... | --all)
    replace  XISO --name NAME --wav clip.wav [--outer N | --all-matches] [--retail-packs DIR] [--receipt R.json]
    verify   XISO --name NAME --wav clip.wav [--decoded-dir DIR]

Names repeat across packages (``menu-back_01`` in ``global.iff`` and
``frontend.iff``; 340 ``oclapha_01`` huddle claps), so a name that matches more
than one record needs ``--outer N`` / ``--key`` to pick one, or ``--all-matches``
to write every one of them.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from nfl2k5_soundbank_swap import (  # noqa: E402
    BLOCK_FRAMES,
    CHANNEL_BLOCK_BYTES,
    CODEC_WORD,
    WRAPPER_SIZE,
    ClipEncoder,
    DiscSpan,
    SoundbankSwapError,
    XisoArchive,
    decode_payload,
    read_wav,
    refuse_retail_identity,
    retail_bytes_from_packs,
    sha256_bytes,
    snr_db,
    write_wav,
)

ROOT = TOOLS.parent
CATALOG_PATH = ROOT / "reports" / "assets" / "nfl2k5_audo_import_capacity.json"
CATALOG_SCHEMA = "nfl2k5_audo_import_capacity/v1"
CATALOG_SHA256 = "1d9ebb31a8822d113ae0fc8ec028e4ff652ccb7cbcf9d6d1d870aa58ef65f556"
KEY_RE = re.compile(r"outer_(\d{4})_chunk_(\d{4})\Z")
MONO_FLAGS = 0x35
STEREO_FLAGS = 0x75

PACKAGE_LABELS = {
    3: "global.iff (frontend UI, ticker, replay wipes)",
    9: "frontend.iff (menus, calendar, front office)",
    15: "audiotestmenu.iff",
    23: "fr.iff (draft board)",
    346: "gamedata.iff (crowd chants / pre-cheer / boo / clap / rain)",
    347: "FirstPerson.iff (heartbeat, breath)",
    4248: "crib.iff",
    4249: "cribah.iff (air hockey)",
    4250: "cribpf.iff (paper football)",
    4264: "crib_darts.iff",
    4266: "crib_intro.iff",
    4271: "crib_triviagame.iff",
}


class AudoSwapError(SoundbankSwapError):
    """Anything that must stop the tool before it touches the disc."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AudoSwapError(message)


def package_label(outer_index: int) -> str:
    label = PACKAGE_LABELS.get(outer_index)
    if label is not None:
        return label
    if 513 <= outer_index <= 852:
        return f"team crowd package (home side) #{outer_index - 513}"
    if 853 <= outer_index <= 1192:
        return f"team crowd package (away side) #{outer_index - 853}"
    return f"outer {outer_index}"


# --------------------------------------------------------------------------- catalog
@dataclass(frozen=True)
class AudoRecord:
    key: str
    outer_index: int
    chunk_index: int
    name: str
    classification: str
    channels: int
    sample_rate: int
    frame_count: int
    payload_size: int
    system_size: int
    tail_size: int
    wrapper_size: int
    descriptor_offset: int
    chunk_offset_in_outer: int
    pack_name: str
    pack_offset: int
    span_sha256: str
    header_sha256: str
    system_sha256: str
    payload_sha256: str
    tail_sha256: str
    duplicate_name_count: int
    equal_content_group: str | None

    @property
    def payload_offset_in_wrapper(self) -> int:
        return WRAPPER_SIZE + self.system_size

    @property
    def block_align(self) -> int:
        return CHANNEL_BLOCK_BYTES * self.channels

    @property
    def duration(self) -> float:
        return self.frame_count / self.sample_rate

    @property
    def package(self) -> str:
        return package_label(self.outer_index)

    def describe(self) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "outer_index": self.outer_index,
            "chunk_index": self.chunk_index,
            "package": self.package,
            "channels": self.channels,
            "sample_rate": self.sample_rate,
            "frames": self.frame_count,
            "blocks": self.payload_size // self.block_align,
            "bytes": self.payload_size,
            "duration_seconds": round(self.duration, 6),
            "system_bytes": self.system_size,
            "tail_bytes": self.tail_size,
            "wrapper_bytes": self.wrapper_size,
            "descriptor_offset": self.descriptor_offset,
            "pack": self.pack_name,
            "pack_offset": self.pack_offset,
            "duplicate_name_count": self.duplicate_name_count,
            "equal_content_group": self.equal_content_group,
            "catalog_classification": self.classification,
        }


def _int(value, label: str, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"catalog: invalid {label}")
    return value


def _hex(value, label: str) -> str:
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
             f"catalog: invalid {label}")
    return value


def load_catalog(path: Path = CATALOG_PATH, *, expected_sha256: str | None = CATALOG_SHA256
                 ) -> tuple[AudoRecord, ...]:
    """Every standalone AUDO record, with its allocation and retail hashes."""

    path = Path(path)
    _require(path.is_file() and not path.is_symlink(), f"catalog is not a regular file: {path}")
    payload = path.read_bytes()
    if expected_sha256 is not None:
        _require(sha256_bytes(payload) == expected_sha256,
                 f"catalog {path} differs from the audited version; pass --catalog explicitly to use it")
    document = json.loads(payload)
    _require(isinstance(document, dict) and document.get("schema") == CATALOG_SCHEMA, "catalog schema is unsupported")
    records = document.get("records")
    _require(isinstance(records, list) and records, "catalog has no records")
    packs = {row["name"]: row for row in document.get("source", {}).get("packs", []) if isinstance(row, dict)}
    result: list[AudoRecord] = []
    seen: set[str] = set()
    name_counts: dict[str, int] = {}
    for row in records:
        name_counts[str(row.get("name"))] = name_counts.get(str(row.get("name")), 0) + 1
    for row in records:
        key = row.get("key")
        matched = KEY_RE.fullmatch(key) if isinstance(key, str) else None
        _require(matched is not None, "catalog row has an invalid key")
        _require(key not in seen, f"catalog repeats {key}")
        seen.add(key)
        fmt, chunk, hashes, spans, groups, descriptor = (row.get(field) for field in
                                                         ("format", "chunk", "hashes", "absolute_span",
                                                          "groups", "descriptor"))
        _require(all(isinstance(value, dict) for value in (fmt, chunk, hashes, spans, groups, descriptor)),
                 f"catalog row {key} is incomplete")
        channels = _int(fmt.get("channels"), "channels", 1)
        sample_rate = _int(fmt.get("sample_rate"), "sample rate", 1)
        frame_count = _int(fmt.get("frame_count"), "frame count", 1)
        payload_size = _int(fmt.get("payload_allocation_bytes"), "payload size", 1)
        system_size = _int(fmt.get("system_bytes"), "system size", 1)
        tail_size = _int(fmt.get("tail_bytes"), "tail size")
        wrapper_size = _int(chunk.get("wrapper_span_bytes"), "wrapper size", 1)
        align = CHANNEL_BLOCK_BYTES * channels
        descriptor_offset = _int(descriptor.get("offset_in_body"), "descriptor offset", 0x10)
        _require(descriptor_offset + 32 <= system_size, f"catalog row {key}: descriptor escapes the system area")
        _require(channels in (1, 2) and fmt.get("codec_word") == "0x00000011"
                 and payload_size % align == 0 and frame_count == payload_size // align * BLOCK_FRAMES
                 and wrapper_size == WRAPPER_SIZE + system_size + payload_size + tail_size
                 and wrapper_size == WRAPPER_SIZE + _int(chunk.get("stored_body_bytes"), "stored body", 1),
                 f"catalog row {key}: allocation arithmetic is inconsistent")
        pack_span = spans.get("pack")
        _require(isinstance(pack_span, dict), f"catalog row {key}: no pack span")
        pack_path = str(pack_span.get("path"))
        _require(pack_path.startswith("vc_53450030/"), f"catalog row {key}: pack path is invalid")
        pack_name = pack_path.rsplit("/", 1)[1]
        pack_offset = _int(pack_span.get("start"), "pack offset")
        _require(_int(pack_span.get("end"), "pack end", 1) == pack_offset + wrapper_size,
                 f"catalog row {key}: pack span does not equal the wrapper size")
        pack = packs.get(pack_name)
        _require(pack is None or pack_offset + wrapper_size <= _int(pack.get("size"), "pack size", 1),
                 f"catalog row {key}: span escapes its pack")
        dup = groups.get("duplicate_name") or {}
        content = groups.get("equal_decoded_content") or {}
        _require(groups.get("physical_span_shared") is False, f"catalog row {key}: physical span is shared")
        result.append(AudoRecord(
            key=key,
            outer_index=int(matched.group(1)),
            chunk_index=int(matched.group(2)),
            name=str(row.get("name")),
            classification=str(row.get("classification")),
            channels=channels,
            sample_rate=sample_rate,
            frame_count=frame_count,
            payload_size=payload_size,
            system_size=system_size,
            tail_size=tail_size,
            wrapper_size=wrapper_size,
            descriptor_offset=descriptor_offset,
            chunk_offset_in_outer=_int(chunk.get("offset_in_outer"), "chunk offset"),
            pack_name=pack_name,
            pack_offset=pack_offset,
            span_sha256=_hex(hashes.get("resource_span_sha256"), "span hash"),
            header_sha256=_hex(hashes.get("wrapper_header_sha256"), "header hash"),
            system_sha256=_hex(hashes.get("system_sha256"), "system hash"),
            payload_sha256=_hex(hashes.get("payload_sha256"), "payload hash"),
            tail_sha256=_hex(hashes.get("tail_sha256"), "tail hash"),
            duplicate_name_count=int(dup.get("member_count", 1) or 1) if dup else name_counts[str(row.get("name"))],
            equal_content_group=str(content.get("group_id")) if content else None,
        ))
    ranges = sorted((r.pack_name, r.pack_offset, r.pack_offset + r.wrapper_size, r.key) for r in result)
    for left, right in zip(ranges, ranges[1:]):
        _require(left[0] != right[0] or left[2] <= right[1], f"catalog spans overlap: {left[3]} / {right[3]}")
    result.sort(key=lambda record: (record.outer_index, record.chunk_index))
    return tuple(result)


def select_records(records, *, names=None, keys=None, outer=None, all_records: bool = False) -> list[AudoRecord]:
    """Resolve --name globs / --key / --record selectors to catalog records, in disc order."""

    chosen: dict[str, AudoRecord] = {}
    if all_records:
        chosen = {record.key: record for record in records}
    for pattern in names or []:
        matched = [record for record in records
                   if fnmatch.fnmatchcase(record.name, pattern) or record.name == pattern]
        if not matched:
            lowered = pattern.casefold()
            matched = [record for record in records if record.name.casefold() == lowered]
        _require(bool(matched), f"no AUDO record is named {pattern!r}")
        for record in matched:
            chosen[record.key] = record
    for key in keys or []:
        text = str(key)
        if ":" in text and not text.startswith("outer_"):
            left, _, right = text.partition(":")
            _require(left.isdigit() and right.isdigit(), f"record selector must be OUTER:CHUNK, got {text!r}")
            text = f"outer_{int(left):04d}_chunk_{int(right):04d}"
        matched = [record for record in records if record.key == text]
        _require(bool(matched), f"no AUDO record has key {text!r}")
        chosen[matched[0].key] = matched[0]
    result = [record for record in chosen.values()]
    if outer is not None:
        result = [record for record in result if record.outer_index == outer]
    result.sort(key=lambda record: (record.outer_index, record.chunk_index))
    return result


# --------------------------------------------------------------------------- disc binding
@dataclass(frozen=True)
class ResolvedAudo:
    record: AudoRecord
    wrapper_spans: tuple[DiscSpan, ...]
    payload_spans: tuple[DiscSpan, ...]

    def describe(self) -> dict[str, object]:
        return {
            **self.record.describe(),
            "xiso_wrapper_spans": [span.describe() for span in self.wrapper_spans],
            "xiso_spans": [span.describe() for span in self.payload_spans],
        }


class AudoDisc(XisoArchive):
    """One XISO with every catalog record bound to its disc span."""

    def __init__(self, path: Path, *, writable: bool = False, records=None) -> None:
        super().__init__(path, writable=writable)
        try:
            self.records: tuple[AudoRecord, ...] = tuple(records) if records is not None else load_catalog()
        except Exception:
            self.close()
            raise

    def resolve(self, record: AudoRecord) -> ResolvedAudo:
        """Bind a record to this disc: pack extent + archive-table cross-check."""

        wrapper_spans = self.pack_spans(record.pack_name, record.pack_offset, record.wrapper_size)
        entry = self.entry(record.outer_index)
        via_entry = self.entry_spans(entry, record.chunk_offset_in_outer, record.wrapper_size)
        _require(via_entry == wrapper_spans,
                 f"{record.key}: the disc's archive table places outer {record.outer_index} chunk "
                 f"{record.chunk_index} elsewhere than the catalog's pack span")
        payload_spans = self.pack_spans(record.pack_name, record.pack_offset + record.payload_offset_in_wrapper,
                                        record.payload_size)
        return ResolvedAudo(record, wrapper_spans, payload_spans)

    def read_wrapper(self, resolved: ResolvedAudo) -> bytes:
        return self.read_spans(resolved.wrapper_spans)

    def read_payload(self, resolved: ResolvedAudo) -> bytes:
        return self.read_spans(resolved.payload_spans)


def check_wrapper(wrapper: bytes, record: AudoRecord, *, require_retail_payload: bool) -> dict[str, object]:
    """Prove the record's metadata is intact on this disc; return the identity facts."""

    _require(len(wrapper) == record.wrapper_size, f"{record.key}: wrapper read was short")
    header = wrapper[:WRAPPER_SIZE]
    magic, stored, system_size, payload_size, w4, w5, w6, w7 = struct.unpack_from("<4s7I", header, 0)
    _require(magic == b"AUDO" and stored == record.wrapper_size - WRAPPER_SIZE
             and system_size == record.system_size and payload_size == record.payload_size
             and (w4, w5, w6, w7) == (0, 0, 0, 0),
             f"{record.key}: AUDO wrapper header differs from the catalog")
    system = wrapper[WRAPPER_SIZE:WRAPPER_SIZE + record.system_size]
    payload = wrapper[record.payload_offset_in_wrapper:record.payload_offset_in_wrapper + record.payload_size]
    tail = wrapper[record.payload_offset_in_wrapper + record.payload_size:]
    _require(system[0x0C:0x10] == b"AUDO", f"{record.key}: inner AUDO marker missing")
    name = record.name.encode("utf-16le") + b"\0\0"
    name_at = 0x0F + struct.unpack_from("<i", system, 0x10)[0]
    _require(0 <= name_at and name_at + len(name) <= len(system) and system[name_at:name_at + len(name)] == name,
             f"{record.key}: system area does not name {record.name!r}")
    descriptor_at = 0x13 + struct.unpack_from("<i", system, 0x14)[0]
    _require(descriptor_at == record.descriptor_offset and descriptor_at + 32 <= len(system),
             f"{record.key}: descriptor pointer +0x{descriptor_at:x} differs from the catalog "
             f"(+0x{record.descriptor_offset:x})")
    ch, ch2, codec, flags, size, zero, per_channel, rate = struct.unpack_from("<8I", system, descriptor_at)
    _require((ch, ch2, codec, zero) == (record.channels, record.channels, CODEC_WORD, 0)
             and flags == (MONO_FLAGS if record.channels == 1 else STEREO_FLAGS)
             and size == record.payload_size and per_channel * record.channels == record.payload_size
             and rate == record.sample_rate,
             f"{record.key}: descriptor {(ch, ch2, codec, flags, size, zero, per_channel, rate)} "
             "differs from the catalog allocation")
    header_sha, system_sha, payload_sha, tail_sha = (sha256_bytes(part) for part in (header, system, payload, tail))
    _require(header_sha == record.header_sha256 and system_sha == record.system_sha256
             and len(tail) == record.tail_size and tail_sha == record.tail_sha256,
             f"{record.key}: wrapper header / system area / tail no longer carry the retail bytes")
    retail_payload = payload_sha == record.payload_sha256
    _require(retail_payload or not require_retail_payload,
             f"{record.key}: the payload on this disc is not the retail one "
             f"(disc {payload_sha[:16]}..., retail {record.payload_sha256[:16]}...); pass --force to overwrite anyway")
    return {"retail_payload": retail_payload, "payload_sha256": payload_sha, "system_sha256": system_sha,
            "tail_sha256": tail_sha}


# --------------------------------------------------------------------------- operations
def replace_records(disc_path: Path, records, wav_path: Path, *, retail_packs: Path | None = None,
                    force: bool = False, guards=None, allow_trim: bool = True, fade_ms: float = 10.0,
                    strict: bool = False, catalog=None) -> dict[str, object]:
    """Encode ``wav_path`` into every selected record's payload and write in place; returns a receipt."""

    disc_path = Path(disc_path)
    refuse_retail_identity(disc_path, guards)
    _require(bool(records), "nothing selected")
    channels, rate, pcm = read_wav(wav_path)
    encoder = ClipEncoder(channels, rate, pcm, allow_trim=allow_trim, fade_ms=fade_ms, strict=strict)
    with AudoDisc(disc_path, writable=True, records=catalog) as disc:
        prepared: list[tuple[ResolvedAudo, bytes, bytes, dict[str, object], str]] = []
        for record in records:
            resolved = disc.resolve(record)
            wrapper = disc.read_wrapper(resolved)
            facts = check_wrapper(wrapper, record, require_retail_payload=not force)
            gate = "catalog-hashes" if facts["retail_payload"] else "forced"
            if retail_packs is not None:
                retail = retail_bytes_from_packs(Path(retail_packs), resolved.payload_spans)
                before = wrapper[record.payload_offset_in_wrapper:record.payload_offset_in_wrapper + record.payload_size]
                _require(retail == before or force,
                         f"{record.key}: the disc no longer carries the retail packs' bytes; pass --force")
                gate = "catalog-hashes+retail-packs" if retail == before else "forced"
            encoded, _fit, _decoded = encoder.encode(_as_payload(resolved))
            prepared.append((resolved, wrapper, encoded, facts, gate))

        rows: list[dict[str, object]] = []
        for resolved, wrapper, encoded, facts, gate in prepared:
            record = resolved.record
            disc.write_spans(resolved.payload_spans, encoded)
            after_wrapper = disc.read_wrapper(resolved)
            expected_wrapper = (wrapper[:record.payload_offset_in_wrapper] + encoded
                                + wrapper[record.payload_offset_in_wrapper + record.payload_size:])
            _require(after_wrapper == expected_wrapper, f"{record.key}: read-back after write does not match")
            _encoded, fit, decoded = encoder.encode(_as_payload(resolved))
            reference = encoder.shaped(record.channels, record.sample_rate)
            rows.append({
                **resolved.describe(),
                "retail_gate": gate,
                "before_payload_sha256": facts["payload_sha256"],
                "after_payload_sha256": sha256_bytes(encoded),
                "after_wrapper_sha256": sha256_bytes(after_wrapper),
                "decoded_pcm_sha256": sha256_bytes(decoded),
                "metadata_preserved": True,
                "clip_frames": fit.source_frames,
                "padded_silence_frames": fit.padded_frames,
                "trimmed_frames": fit.trimmed_frames,
                "fade_out_frames": fit.fade_frames,
                "encode_snr_db": round(snr_db(reference[:len(fit.pcm)], decoded[:len(fit.pcm)]), 2),
                **encoder.conversions(_as_payload(resolved)),
            })
        disc.fsync()
        receipt = {
            "schema": "nfl2k5_audo_swap_receipt/v1",
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "xiso": str(disc_path),
            "xiso_size": disc.image_size,
            "records": [record.key for record in records],
            "names": sorted({record.name for record in records}),
            "wav": str(Path(wav_path)),
            "wav_sha256": sha256_bytes(Path(wav_path).read_bytes()),
            "wav_channels": channels,
            "wav_sample_rate": rate,
            "wav_frames": len(pcm) // (channels * 2),
            "allow_trim": allow_trim,
            "fade_ms": fade_ms,
            "descriptors_changed": False,
            "record_count": len(rows),
            "payloads": rows,
        }
    return receipt


def _as_payload(resolved: ResolvedAudo):
    """Adapt a record to the shape ``ClipEncoder`` keys on (channels, rate, frames, size)."""

    from nfl2k5_soundbank_swap import Payload

    record = resolved.record
    return Payload("audo", record.chunk_index, record.outer_index, record.name, 0, record.channels,
                   record.sample_rate, 0, record.payload_size, 0, resolved.payload_spans)


def verify_records(disc_path: Path, records, wav_path: Path, *, decoded_dir: Path | None = None,
                   allow_trim: bool = True, fade_ms: float = 10.0, catalog=None) -> dict[str, object]:
    channels, rate, pcm = read_wav(wav_path)
    encoder = ClipEncoder(channels, rate, pcm, allow_trim=allow_trim, fade_ms=fade_ms)
    rows: list[dict[str, object]] = []
    with AudoDisc(disc_path, records=catalog) as disc:
        for record in records:
            resolved = disc.resolve(record)
            wrapper = disc.read_wrapper(resolved)
            facts = check_wrapper(wrapper, record, require_retail_payload=False)
            expected, fit, _decoded = encoder.encode(_as_payload(resolved))
            actual = wrapper[record.payload_offset_in_wrapper:record.payload_offset_in_wrapper + record.payload_size]
            decoded = decode_payload(actual, record.channels)
            reference = encoder.shaped(record.channels, record.sample_rate)
            if decoded_dir is not None:
                Path(decoded_dir).mkdir(parents=True, exist_ok=True)
                write_wav(Path(decoded_dir) / f"{record.key}_{record.name}.wav", decoded, record.channels,
                          record.sample_rate)
            rows.append({
                **resolved.describe(),
                "matches_encoded_clip": actual == expected,
                "metadata_preserved": True,
                "retail_payload": facts["retail_payload"],
                "disc_payload_sha256": sha256_bytes(actual),
                "expected_payload_sha256": sha256_bytes(expected),
                "clip_frames": fit.source_frames,
                "decoded_snr_db_vs_clip": round(snr_db(reference[:len(fit.pcm)], decoded[:len(fit.pcm)]), 2),
            })
    return {"all_match": all(row["matches_encoded_clip"] for row in rows), "record_count": len(rows),
            "payloads": rows}


def export_records(disc: AudoDisc, records, out_dir: Path) -> list[dict[str, object]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for record in records:
        resolved = disc.resolve(record)
        raw = disc.read_payload(resolved)
        pcm = decode_payload(raw, record.channels)
        name = f"{record.key}_{record.name}.wav"
        write_wav(out_dir / name, pcm, record.channels, record.sample_rate)
        rows.append({"file": name, "payload_sha256": sha256_bytes(raw),
                     "retail_payload": sha256_bytes(raw) == record.payload_sha256, **resolved.describe()})
    (out_dir / "manifest.json").write_text(json.dumps(rows, indent=2))
    return rows


# --------------------------------------------------------------------------- CLI
def _catalog(args: argparse.Namespace) -> tuple[AudoRecord, ...]:
    path = getattr(args, "catalog", None)
    if path:
        return load_catalog(Path(path), expected_sha256=None)
    return load_catalog()


def _selection(args: argparse.Namespace, records) -> list[AudoRecord]:
    return select_records(records, names=getattr(args, "name", None), keys=getattr(args, "key", None),
                          outer=getattr(args, "outer", None), all_records=bool(getattr(args, "all", False)))


def _cmd_list(args: argparse.Namespace) -> int:
    records = _catalog(args)
    rows = _selection(args, records) if (args.name or args.key or args.outer is not None) else list(records)
    if args.json:
        print(json.dumps([record.describe() for record in rows], indent=2))
        return 0
    print(f"{'key':24s} {'name':28s} {'ch':>2s} {'rate':>6s} {'seconds':>8s} {'bytes':>8s} {'dup':>4s}  package")
    for record in rows:
        print(f"{record.key:24s} {record.name:28s} {record.channels:2d} {record.sample_rate:6d} "
              f"{record.duration:8.3f} {record.payload_size:8d} {record.duplicate_name_count:4d}  {record.package}")
    print(f"{len(rows)} record(s)")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    records = _catalog(args)
    selected = _selection(args, records)
    _require(bool(selected), "give --name / --key / --outer or --all")
    with AudoDisc(Path(args.xiso), records=records) as disc:
        rows = export_records(disc, selected, Path(args.out))
    print(f"exported {len(rows)} record(s) to {args.out}")
    return 0


def _pick_for_write(args: argparse.Namespace, records) -> list[AudoRecord]:
    selected = _selection(args, records)
    _require(bool(selected), "give --name NAME or --key KEY")
    if len(selected) > 1 and not args.all_matches:
        listing = "\n".join(f"  {record.key}  {record.name}  ({record.package})" for record in selected)
        raise AudoSwapError(f"{len(selected)} records match; narrow with --outer N / --key, or pass "
                            f"--all-matches to write every one:\n{listing}")
    return selected


def _cmd_replace(args: argparse.Namespace) -> int:
    records = _catalog(args)
    selected = _pick_for_write(args, records)
    receipt = replace_records(Path(args.xiso), selected, Path(args.wav),
                              retail_packs=Path(args.retail_packs) if args.retail_packs else None,
                              force=args.force, guards=args.guard, allow_trim=not args.no_trim,
                              fade_ms=args.fade_ms, strict=args.strict, catalog=records)
    text = json.dumps(receipt, indent=2)
    if args.receipt:
        Path(args.receipt).write_text(text)
    if args.quiet:
        print(f"wrote {receipt['record_count']} record(s): {', '.join(receipt['records'])}")
    else:
        print(text)
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    records = _catalog(args)
    selected = _selection(args, records)
    _require(bool(selected), "give --name NAME or --key KEY")
    result = verify_records(Path(args.xiso), selected, Path(args.wav),
                            decoded_dir=Path(args.decoded_dir) if args.decoded_dir else None,
                            allow_trim=not args.no_trim, fade_ms=args.fade_ms, catalog=records)
    print(json.dumps(result, indent=2))
    return 0 if result["all_match"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def selectors(p: argparse.ArgumentParser, *, with_xiso: bool = True) -> None:
        if with_xiso:
            p.add_argument("xiso")
        p.add_argument("--name", action="append", help="sample name or glob, e.g. chantdef1, 'menu-*' (repeatable)")
        p.add_argument("--key", action="append", help="outer_0346_chunk_0095 or 346:95 (repeatable)")
        p.add_argument("--outer", type=int, help="restrict to one package (outer index)")
        p.add_argument("--catalog", help=argparse.SUPPRESS)   # tests: alternative capacity JSON

    p = sub.add_parser("list", help="list the catalog (optionally filtered)")
    selectors(p, with_xiso=False)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("export", help="decode records to PCM16 WAV")
    selectors(p)
    p.add_argument("--all", action="store_true")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_export)

    p = sub.add_parser("replace", help="write one WAV into the selected record(s) IN PLACE (use a copy!)")
    selectors(p)
    p.add_argument("--wav", required=True)
    p.add_argument("--all-matches", action="store_true", help="write every record the selectors match")
    p.add_argument("--retail-packs", help="extracted retail vc_53450030 folder for an extra byte comparison")
    p.add_argument("--force", action="store_true", help="overwrite a payload that is no longer the retail one")
    p.add_argument("--guard", action="append", help="path(s) that must never be written (retail image)")
    p.add_argument("--no-trim", action="store_true", help="refuse clips longer than the allocation")
    p.add_argument("--fade-ms", type=float, default=10.0)
    p.add_argument("--strict", action="store_true", help="refuse rate/channel conversions")
    p.add_argument("--receipt", help="write the JSON receipt here too")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=_cmd_replace)

    p = sub.add_parser("verify", help="check record(s) hold exactly the encoded WAV")
    selectors(p)
    p.add_argument("--wav", required=True)
    p.add_argument("--decoded-dir", help="also write what the game will play, decoded from the disc")
    p.add_argument("--no-trim", action="store_true")
    p.add_argument("--fade-ms", type=float, default=10.0)
    p.set_defaults(func=_cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except SoundbankSwapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

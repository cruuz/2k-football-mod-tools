"""Transactional same-length music copies and authored-only format-2 recipes.

Uses the commentary AUSB reader/span mapper and fixed-slot Xbox IMA validator.
Only complete authored encoded slots become payloads, with no diff coalescing
or original banks. Tier 2 uses registered byte_runs/v1 (reader 2); tier 3 needs
a separate semantic rebuild operation when offsets move.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import os
from pathlib import Path
import tempfile

from . import modpack, platform_compat
from .nfl2k5_ausb_fixed_slots import (
    CanonicalStreamingSlot, StreamingPackSpan, verify_xbox_ima_stream,
)
from .nfl2k5_music_policy import apply as apply_policy


def _banks_module():
    from .audio_conform import _convert_module
    _convert_module()  # Establish tools/ import path, also in portable packages.
    import nfl2k5_commentary_swap
    return nfl2k5_commentary_swap


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _stamp(path):
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


@dataclass(frozen=True)
class EncodedMusicEdit:
    stream_id: str
    encoded_path: Path
    encoded_sha256: str
    expected_sha256: str


def slot_for_stream(stream):
    cursor, spans = 0, []
    for part in stream.spans:
        spans.append(StreamingPackSpan(part.pack_name, int(part.pack_name, 16),
                                       part.pack_offset, part.length, cursor))
        cursor += part.length
    return CanonicalStreamingSlot(stream.stream_id, stream.bank.external_outer_index,
        stream.bank.entry.name_id, stream.start, stream.end, stream.channels,
        stream.sample_rate, stream.frame_count, (), tuple(spans))


def _plan(disc, edits, *, music_policy="retail", music_unlock=False, music_userlist=False,
          cancelled=None):
    writes, rows, states = [], [], set()
    ids = [edit.stream_id for edit in edits]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate music replacement slot")
    for stream_id in ids:
        bank, number = stream_id.split(":")
        if bank in ("cribmusic", "crib22"):
            twin = ("crib22" if bank == "cribmusic" else "cribmusic") + ":" + number
            if twin not in ids:
                raise ValueError("Jukebox music must include both stereo and mono replacements")
    for edit in edits:
        if cancelled and cancelled():
            raise ValueError("Music build cancelled")
        stream = disc.stream_by_id(edit.stream_id)
        from .json_stream import read_bounded_regular_file
        _path, encoded = read_bounded_regular_file(edit.encoded_path, "Encoded music",
                                                  maximum=stream.size)
        if len(encoded) != stream.size or sha(encoded) != edit.encoded_sha256:
            raise ValueError(f"Authored music changed or has the wrong length: {edit.stream_id}")
        verified = verify_xbox_ima_stream(io.BytesIO(encoded), slot_for_stream(stream),
                                          cancelled=cancelled)
        before = disc.read_stream(stream)
        current_hash = sha(before)
        state = ("applied" if current_hash == edit.encoded_sha256 else
                 "retail" if current_hash == edit.expected_sha256 else "foreign")
        states.add(state)
        if state == "foreign":
            raise ValueError(f"Music source slot differs from its original pin: {edit.stream_id}")
        cursor = 0
        for part in stream.spans:
            end = cursor+part.length
            writes.append((part.xiso_offset, before[cursor:end], encoded[cursor:end],
                           f"vc_53450030/{part.pack_name}"))
            cursor = end
        rows.append({"stream_id": edit.stream_id, "state": state,
                     "before_sha256": current_hash, "after_sha256": sha(encoded),
                     "encoded_bytes": len(encoded), "frames": stream.frame_count,
                     "decoded_pcm_sha256": verified.decoded_pcm_sha256,
                     "descriptor_changed": False, "spans": [vars(s) for s in stream.spans]})
    if len(states) > 1:
        raise ValueError("Mixed applied/original music recipe; no output was written")
    policy_receipt = None
    if music_policy != "retail" or music_unlock or music_userlist:
        xbe = disc.entries.get("default.xbe")
        if xbe is None:
            raise ValueError("Music policy needs default.xbe")
        cs = _banks_module()
        original = cs._pread_exact(disc.descriptor, xbe.byte_offset, xbe.size)
        patched, policy_receipt = apply_policy(original, music_policy=music_policy,
            music_unlock=music_unlock, music_userlist=music_userlist)
        # Exact changed runs only: generated pointers/keys/digest, no originals.
        for a, b in modpack.differences(original, patched):
            writes.append((xbe.byte_offset+a, original[a:b], patched[a:b], "default.xbe"))
    writes.sort(key=lambda w: w[0])
    for left, right in zip(writes, writes[1:]):
        if left[0]+len(left[1]) > right[0]:
            raise ValueError("Music write spans overlap")
    return writes, rows, policy_receipt


def build_copy(source, destination, edits, *, descriptors=None, progress=None,
               cancelled=None, **policy):
    """Preflight all twins, stage once, verify, close every reader, publish once.

    Source may be an already staged image carrying unrelated roster/XBE edits.
    All extents are resolved from that image, including after prior XBE growth.
    Existing outputs and source aliases are refused. Failure removes the stage.
    """
    cs = _banks_module()
    source = modpack._regular_path(source, "music source")
    destination = Path(destination).expanduser().absolute()
    if os.path.lexists(destination):
        raise ValueError("Music output already exists; choose a new copy")
    destination = destination.resolve()
    before_stamp = _stamp(source)
    report = progress or (lambda stage, done, total: None)
    def check():
        if cancelled and cancelled():
            raise ValueError("Music build cancelled; no output published")
    args = {} if descriptors is None else {"descriptors": descriptors}
    with tempfile.TemporaryDirectory(prefix=".music-build-", dir=destination.parent) as work:
        stage = Path(work).resolve()/"image.iso"
        with cs.DiscBanks(source, **args) as disc:
            writes, rows, policy_receipt = _plan(disc, tuple(edits), cancelled=cancelled, **policy)
            check()
            source_hash = hashlib.sha256()
            with stage.open("xb") as out:
                for at in range(0, disc.image_size, 4*1024*1024):
                    check()
                    data = cs._pread_exact(disc.descriptor, at, min(4*1024*1024, disc.image_size-at))
                    source_hash.update(data)
                    out.write(data)
                    report("Copy music image", at+len(data), disc.image_size)
                out.flush()
                os.fsync(out.fileno())
        # Closed source parser, no file handles survive publication.
        with stage.open("r+b") as out:
            for at, old, new, _region in writes:
                check()
                out.seek(at)
                if out.read(len(old)) != old:
                    raise ValueError("Source changed while staging music")
                out.seek(at)
                out.write(new)
            out.flush()
            os.fsync(out.fileno())
            for at, _old, new, _region in writes:
                out.seek(at)
                if out.read(len(new)) != new:
                    raise ValueError("Music write read-back failed")
        # Detect edits to any part of the source during the copy, not only slots.
        def checked_progress(stage_name, done, total):
            check()
            report(stage_name, done, total)
        if (_stamp(source) != before_stamp or
            modpack.hash_file(source, progress=checked_progress) != source_hash.hexdigest() or
            _stamp(source) != before_stamp):
            raise ValueError("Source changed during music build")
        result_hash = modpack.hash_file(stage, progress=checked_progress)
        check()
        platform_compat.publish_no_replace(stage, destination)
    return {"schema": "nfl2k5_music_build/v1", "runtime_witnessed": False,
            "source_sha256": source_hash.hexdigest(), "result_sha256": result_hash,
            "source_size": before_stamp[2], "result_size": destination.stat().st_size,
            "status": "applied", "already_applied": all(old == new for _,old,new,_ in writes),
            "streams": rows, "music_policy": policy_receipt,
            "layout_changed": False, "output": str(destination)}


def export_patch(source, built, destination, edits, *, descriptors=None, progress=None,
                 cancelled=None, **policy):
    """Explicit format-2 byte runs; every music payload byte is authored audio."""
    cs = _banks_module()
    args = {} if descriptors is None else {"descriptors": descriptors}
    with cs.DiscBanks(Path(source), **args) as disc:
        writes, rows, policy_receipt = _plan(disc, tuple(edits), cancelled=cancelled, **policy)
        if not writes or all(old == new for _,old,new,_ in writes):
            raise ValueError("No new music changes to export")
        partition = modpack.partition_base(disc.descriptor, disc.image_size) or 0
        runs, payload = [], bytearray()
        for at, old, new, region in writes:
            runs.append({"op": "replace", "offset": at-partition, "length": len(new),
                         "payload_offset": len(payload), "expected_sha256": sha(old),
                         "new_sha256": sha(new), "region": region})
            payload.extend(new)
        member = "operations/music.bin"
        operation = {"type": 0, "name": "byte_runs", "version": 1,
                     "before_size": disc.image_size-partition,
                     "after_size": disc.image_size-partition, "runs": runs,
                     "payload": {"member": member, "length": len(payload), "sha256": sha(payload)}}
    def checked_progress(stage, done, total):
        if cancelled and cancelled():
            raise ValueError("Music patch export cancelled")
        if progress:
            progress(stage, done, total)
    return modpack.export(source, built, destination,
        {"name": "Fixed-length music", "description": "EXPERIMENTAL / UNWITNESSED",
         "operations": [{"op": "music_fixed_slots", "schema_version": 1,
                         "streams": rows, "music_policy": policy_receipt}]},
        format_version=2, recipe=False, patch_operations=[operation],
        operation_payloads={member: bytes(payload)}, progress=checked_progress)

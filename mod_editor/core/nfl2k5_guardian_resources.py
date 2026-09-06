"""Guardian B-shell geometry and one common helmet01 TXTR, route A.

EXPERIMENTAL / UNWITNESSED. The existing lo_body and hi_head positions are
edited within fixed SCNE spans. A/C, accessory/facemask vertices, UVs, skinning,
topology and wrappers are retained. Append one native six-mip P8 texture to
outer 3 through a streamed pack rebuild, never the 544-byte alignment gap.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile

from . import nfl2k5_guardian_cap as cap
from . import nfl2k5_guardian_overlay as runtime
from . import nfl2k5_music_archive as archive
from . import nfl2k5_resource_growth as growth
from . import nfl2k5_depth_chart_storage as storage
from . import platform_compat as io

EVIDENCE = runtime.EVIDENCE
PROFILE = "b_overlay_v1"
OUTER, OUTER_ID, RETAIL_START, RETAIL_SIZE = 3, 2397695725, 0xD0000, 2387424
TEXTURE_NAME, TEXTURE_SIZE = "helmet01", 88544
TARGETS = (
    replace(cap.TARGETS[0], shell_material=14, first_vertex=4229, shell_vertices=120,
            shell_name="HI_HELMET_B", applied_sha256="863be42715d650f326c9d001082aa01c4d3b0b0a78b90d04cea8ad43ef057e58"),
    replace(cap.TARGETS[1], shell_material=2, first_vertex=10620, shell_vertices=402,
            shell_name="HI_HELMET_B", applied_sha256="22e198aed7a04be16275d8946adee6ef36ae560020f24e003639313f919d8a8a"),
)
TEXTURE_SHA256 = "a8fc8a8fe4a9bbf257ed5c6d3b0687df6719ce8420d7440eafdd46f3384fe19a"
require = archive.require


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compile_texture(template):
    """Use the existing live-helmet mip encoder, then emit an ordinary raw TXTR.

    All six mips are validated by the existing codec. Uncompressed native
    registration needs 128 system bytes and 88384 video/palette bytes, no LZ
    overlap scratch. The generated artwork is the existing neutral quilt.
    """
    require(digest(template) == cap.TARGETS[2].retail_sha256, "foreign helmet texture template")
    painted, receipt = cap._compile(template, cap.TARGETS[2])
    tx = cap.models._tools_module("nfl_txtr")
    chunk = tx.parse_chunks(painted)[0]
    body = bytearray(tx.decode_chunk(painted, chunk)[0])
    body[32:50] = (TEXTURE_NAME+"\0").encode("utf-16le")
    result = struct.pack("<4s7I", b"TXTR", len(body), 128, len(body)-128, 0, 0, 0, 0)+body
    c = tx.parse_chunks(result)[0]
    decoded, _ = tx.decode_chunk(result, c)
    texture = tx.parse_texture(decoded, c)
    require(len(result) == TEXTURE_SIZE and texture.name == TEXTURE_NAME
            and texture.mip_levels == 6 and texture.width == texture.height == 256,
            "Guardian texture native round trip failed")
    return bytes(result), dict(name=TEXTURE_NAME, size=len(result), sha256=digest(result),
                               system_bytes=128, video_bytes=88384, scratch_bytes=0,
                               compiler=receipt)


def collection_status(payload):
    if len(payload) not in (RETAIL_SIZE, RETAIL_SIZE+TEXTURE_SIZE):
        return "foreign"
    expected = "retail_sha256" if len(payload) == RETAIL_SIZE else "applied_sha256"
    for target in TARGETS:
        at = target.pack_offset-RETAIL_START
        if digest(payload[at:at+target.size]) != getattr(target, expected):
            return "foreign"
    if expected == "applied_sha256" and digest(payload[RETAIL_SIZE:]) != TEXTURE_SHA256:
        return "foreign"
    try:
        chunks = list(archive.chunks(payload))
        require(len(chunks) == (225 if expected == "applied_sha256" else 224), "common resource count changed")
    except ValueError:
        return "foreign"
    return "retail" if expected == "retail_sha256" else "applied"


def compile_collection(payload, template=None):
    """Stage all dependent resources; refuse mixed/foreign bytes before compile."""
    state = collection_status(payload)
    require(state != "foreign", "foreign/mixed Guardian models and texture; rebuild from supported resources")
    if state == "applied":
        return bytes(payload), dict(status="already_applied", changed_bytes=0, profile=PROFILE)
    require(template is not None and digest(template) == cap.TARGETS[2].retail_sha256,
            "Guardian texture template is missing or foreign")
    result, receipts = bytearray(payload), []
    with tempfile.TemporaryDirectory(prefix="guardian-models-") as tmp:
        directory = Path(tmp).resolve()
        for target in TARGETS:
            at = target.pack_offset-RETAIL_START
            before = payload[at:at+target.size]
            after, receipt = cap._compile_model(before, target, directory)
            require(digest(after) == target.applied_sha256, "Guardian B compiler differs from its pin")
            result[at:at+target.size] = after
            receipts.append(dict(key=target.key, before_sha256=digest(before), after_sha256=digest(after),
                                 compiler={**receipt, "profile": PROFILE}))
    texture, texture_receipt = compile_texture(template)
    result.extend(texture)
    require(collection_status(result) == "applied", "Guardian collection postcondition failed")
    return bytes(result), dict(status="applied", profile=PROFILE, experimental=True, runtime_witnessed=False,
                               outer=OUTER, size_before=len(payload), size_after=len(result),
                               before_sha256=digest(payload), after_sha256=digest(result),
                               changed_prefix_bytes=sum(a != b for a,b in zip(payload,result)),
                               models=receipts, texture=texture_receipt)


def _inputs(disc):
    entry = disc.archive_entries[OUTER]
    require(entry.name_id == OUTER_ID and entry.size in (RETAIL_SIZE, RETAIL_SIZE+TEXTURE_SIZE),
            "Guardian common player collection identity changed")
    payload = disc.read_entry_range(entry, 0, entry.size)
    return entry, payload


def image_status(path):
    try:
        with archive.Disc(path, descriptors=()) as disc:
            _, collection = _inputs(disc)
            x = disc.entries["default.xbe"]
            require(x.size <= 16*archive.BLOCK, "oversized XBE")
            states = (collection_status(collection), runtime.status(disc.read(x.size, x.byte_offset)))
            return states[0] if states[0] == states[1] else "foreign"
    except (OSError, ValueError, KeyError, IndexError, struct.error):
        return "foreign"


def apply_to_image(path, *, guardian_everyone_practice=runtime._UNSET, guardian_players=None, extra_requests=()):
    """Paired resources/XBE transaction on a disposable build copy.

    Plan before opening a writer. Append/verify the pack in 1 MiB blocks, switch
    its XDVDFS node, then use the existing XBE growth writer. Restore original
    nodes, XBE and length on ordinary I/O failures. Public build publication is
    the enclosing build's closed-temp os.replace transaction.
    """
    path = Path(path).resolve()
    with archive.Disc(path, descriptors=()) as disc:
        original_identity = archive.identity(path)
        entry, before = _inputs(disc)
        state = collection_status(before)
        x = disc.entries["default.xbe"]
        require(x.size <= 16*archive.BLOCK, "oversized XBE")
        old_xbe = disc.read(x.size, x.byte_offset)
        require(state in ("retail", "applied") and state == runtime.status(old_xbe),
                "mixed/foreign Guardian executable/resource pair")
        requests = runtime.REQUESTS+tuple(extra_requests)
        runtime.space.plan(requests)  # validates duplicates, kinds and budgets before mutation
        allocated = old_xbe
        if state == "retail" and runtime.space.status(old_xbe) == "retail":
            allocated, _ = runtime.space.apply(old_xbe, requests, scaleout=True)
        elif runtime.space.status(old_xbe) == "applied":
            present = {(a["owner"],a["kind"],a["size"],a["align"])
                       for a in runtime.space.layout(old_xbe)["allocations"]}
            require(all(tuple(row) in present for row in requests),
                    "Guardian requested owner union differs from the installed allocation")
        new_xbe, xr = runtime.apply(allocated, guardian_everyone_practice=guardian_everyone_practice)
        template = None
        if state == "retail":
            donor = disc.archive_entries[4002]
            require(donor.name_id == 0x07E10847 and donor.size >= 0x661B0+36704, "Guardian donor uniform changed")
            template = disc.read_entry_range(donor, 0x661B0, 36704)
        after, resources = compile_collection(before, template)
        fixed_spans, roster_receipt = [], None
        if guardian_players is not None:
            from . import nfl2k5_player_tags as tags
            rost = disc.archive_entries[tags.ROST_OUTER_INDEX]
            require(rost.size == tags.RESOURCE_SIZE, "Guardian main ROST size changed")
            raw = disc.read_entry_range(rost, 0, rost.size)
            require(tags.resource_status(raw) != "foreign", "Guardian main ROST wrapper changed")
            body, roster_receipt = runtime.apply_roster_body(raw[32:], guardian_players)
            if body != raw[32:]:
                fixed_spans.append((rost.virtual_offset, raw, raw[:32]+body))
        if state == "applied" and not fixed_spans:
            return dict(status="already_applied", image_growth=0, resources=resources, xbe=xr)
        p = disc.pack_extents["0"]
        read_pack = lambda n, at: disc.read(n, p.byte_offset+at)
        # Retail uses a uniform 0x9F alignment fill; earlier rebuilds use zero.
        # Neither fill is a resource. Explicit collection growth owns the new
        # span and retains the recognized fill value in its new padding.
        plan = growth.plan_pack0(read_pack, p.size, OUTER, OUTER_ID, after,
                                 fixed_spans=fixed_spans, padding_bytes=(0, 0x9F))
        require(plan.start == entry.virtual_offset, "common collection is not contained in pack 0")
        old_size = disc.image_size
        xnode = storage.image_file_node(disc.read, x.base_offset, old_size, x.path)
        nodes = [(disc.nodes["0"][0], struct.pack("<II", p.sector, p.size)),
                 (xnode[0], struct.pack("<II", x.sector, x.size))]
        require(xnode[1:] == (x.sector, x.size), "XBE node disagrees with its extent")
        require(archive.identity(path) == original_identity, "image changed after Guardian preflight")
        with path.open("r+b") as writer:
            fd = writer.fileno()

            def write(data, at):
                require(io.pwrite(fd, data, at) == len(data), "short Guardian transaction write")

            attempted_xbe = False
            try:
                offset = archive.align_up(old_size)
                if offset > old_size:
                    write(bytes(offset-old_size), old_size)
                transport = growth.write_pack0(fd, read_pack, plan, offset)
                write(struct.pack("<II", (offset-p.base_offset)//2048, plan.size_after), nodes[0][0])
                attempted_xbe = True
                xtransport = storage.write_image_xbe(fd, new_xbe)
                require(image_status(path) == "applied", "Guardian paired readback failed")
                os.fsync(fd)
            except Exception as exc:
                try:
                    for node, data in reversed(nodes):
                        write(data, node)
                    if attempted_xbe:
                        write(old_xbe, x.byte_offset)
                    os.ftruncate(fd, old_size)
                    os.fsync(fd)
                    require(all(io.pread(fd, 8, node) == data for node,data in nodes), "Guardian rollback node mismatch")
                    require(io.pread(fd, x.size, x.byte_offset) == old_xbe, "Guardian rollback XBE mismatch")
                except Exception as rollback:
                    raise ValueError(f"{exc}; rollback failed: {rollback}; discard output copy") from exc
                raise
            image_growth = os.fstat(fd).st_size-old_size
    return dict(status="applied", experimental=True, runtime_witnessed=False, resources=resources,
                xbe=xr, roster=roster_receipt, pack_transport=transport, xbe_transport=xtransport, image_growth=image_growth)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "check", "apply"))
    parser.add_argument("image", type=Path)
    parser.add_argument("--selected-only", action="store_true")
    parser.add_argument("--players", type=Path, help="JSON array of exact roster record selections; [] clears all")
    args = parser.parse_args(argv)
    if args.command == "apply":
        if args.players is not None:
            require(args.players.stat().st_size <= 1024**2, "Guardian selections exceed 1 MiB")
        result = apply_to_image(args.image, guardian_everyone_practice=not args.selected_only,
                                guardian_players=json.loads(args.players.read_text()) if args.players else None)
    else:
        result = dict(status=image_status(args.image), evidence=EVIDENCE)
        if args.command == "check":
            require(result["status"] != "foreign", "Guardian paired validation refused")
    print(json.dumps(result, indent=2))
    return int(result["status"] == "foreign")


if __name__ == "__main__":
    raise SystemExit(main())

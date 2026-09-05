"""Format-2 operation registry. See docs/MODPACK_FORMAT.md for the wire contract.

Handlers describe writes against a projected image, then replay them on a
transactional output. No handler or executable code is ever loaded from a pack.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import struct
from typing import Any, Callable, Mapping

from . import modpack as m
from . import nfl2k5_depth_chart_storage as storage

REGISTRY_VERSION = 1
READER_VERSION = 2
NEWER_READER = "this mod needs a newer Mod Studio"


@dataclass(frozen=True)
class Span:
    offset: int
    length: int
    read: Callable[[int, int], bytes]  # count, relative offset


class View:
    """Read-only source plus ordered replacement spans, never a whole image."""

    def __init__(self, descriptor: int, size: int, partition: int):
        self.descriptor = descriptor
        self.original_size = self.size = size
        self.partition = partition
        self.spans: list[Span] = []

    def read(self, count: int, offset: int) -> bytes:
        m._require(0 <= offset <= offset + count <= self.size, "operation read extends past image")
        available = max(0, min(count, self.original_size - offset))
        data = bytearray(m._pread_exact(self.descriptor, available, offset, "operation input"))
        data.extend(bytes(count - available))
        for span in self.spans:
            lo, hi = max(offset, span.offset), min(offset + count, span.offset + span.length)
            if lo < hi:
                data[lo - offset:hi - offset] = span.read(hi - lo, lo - span.offset)
        return bytes(data)

    def digest(self, offset: int, size: int) -> str:
        return digest(lambda count, at: self.read(count, offset + at), size)

    def put(self, offset: int, length: int, read: Callable[[int, int], bytes]) -> None:
        self.spans.append(Span(offset, length, read))
        self.size = max(self.size, offset + length)


def digest(read, size: int) -> str:
    h = hashlib.sha256()
    for at in range(0, size, m.BLOCK):
        h.update(read(min(m.BLOCK, size - at), at))
    return h.hexdigest()


def literal(data: bytes):
    return lambda count, offset: data[offset:offset + count]


def blob_reader(pack, blob):
    return lambda count, offset: pack.read_blob(blob["member"], count, offset)


def _blob(blob: Any, label: str) -> dict:
    m._require(isinstance(blob, Mapping), f"{label} needs a payload object")
    member = blob.get("member")
    m._require(isinstance(member, str) and member.startswith("operations/")
               and member.endswith(".bin") and len(member.split("/")) == 2
               and bool(m._SAFE_NAME.fullmatch(member.split("/")[1])), f"unsafe operation member: {member!r}")
    m._int(blob.get("length"), label + ".length")
    m._hex64(blob.get("sha256"), label + ".sha256")
    return dict(blob)


def _state(state, label):
    m._require(isinstance(state, Mapping), f"{label} must be an object")
    for key in ("size", "sector"):
        m._int(state.get(key), label + "." + key)
        m._require(state[key] <= 0xFFFFFFFF, f"{label}.{key} exceeds XDVDFS's uint32 field")
    m._hex64(state.get("sha256"), label + ".sha256")


class ByteRuns:
    name = "byte_runs"
    version = 1
    min_reader_version = 2

    @staticmethod
    def validate(op, before, payload):
        m._require(op["before_size"] == op["after_size"], "byte_runs cannot resize an image")
        runs = op.get("runs")
        m._require(isinstance(runs, list) and runs, "byte_runs needs runs")
        end = cursor = 0
        for i, run in enumerate(runs):
            m._require(isinstance(run, Mapping) and run.get("op") == "replace", f"run {i} is not a replace op")
            off = m._int(run.get("offset"), "run.offset")
            size = m._int(run.get("length"), "run.length", minimum=1)
            m._require(end <= off and off + size <= before, f"run {i} overlaps or extends past image")
            m._require(m._int(run.get("payload_offset"), "run.payload_offset") == cursor,
                       "byte_runs payload offsets must be contiguous within the operation")
            for key in ("expected_sha256", "new_sha256"):
                m._hex64(run.get(key), key)
            region = run.get("region")
            m._require(region is None or isinstance(region, str) and len(region) <= 260, "invalid run region")
            cursor += size
            end = off + size
        m._require(cursor == op["payload"]["length"], "byte_runs payload length differs from run lengths")

    @staticmethod
    def plan(op, view, pack, verify):
        read = blob_reader(pack, op["payload"])
        for i, run in enumerate(op["runs"]):
            start = view.partition + run["offset"]
            length = run["length"]
            if verify:
                m._require(view.digest(start, length) == run["expected_sha256"],
                           f"byte_runs run {i} at 0x{start:x}: expected-before hash differs")
            head = run["payload_offset"]
            replacement = lambda count, at, head=head: read(count, head + at)
            m._require(digest(replacement, length) == run["new_sha256"], f"byte_runs run {i}: expected-after hash differs from payload")
            view.put(start, length, replacement)


    @staticmethod
    def verify_written(op, view):
        for i, run in enumerate(op["runs"]):
            m._require(view.digest(view.partition + run["offset"], run["length"]) == run["new_sha256"],
                       f"byte_runs run {i}: written expected-after hash differs")


class FileReplace:
    name = "file_replace"
    version = 1
    min_reader_version = 2
    grow = False
    shrink = False
    special = False

    @classmethod
    def validate(cls, op, before, payload):
        path = op.get("path")
        m._require(isinstance(path, str) and len(path) <= 4096 and all(
            p not in ("", ".", "..") and "\\" not in p and "\0" not in p for p in path.split("/")), "invalid named disc path")
        _state(op.get("before"), "file.before")
        _state(op.get("after"), "file.after")
        node = m._int(op.get("directory_offset"), "directory_offset")
        m._require(node + 8 <= before, "directory node extends past image")
        old, new = op["before"], op["after"]
        m._require(old["sector"] * 2048 + old["size"] <= before, "old file extends past image")
        m._require(new["size"] == payload["length"] and new["sha256"] == payload["sha256"], "file payload differs from expected-after identity")
        if cls.grow:
            m._require(new["size"] > old["size"], "file_grow must grow the named file")
            m._require(new["sector"] * 2048 == (before + 2047) // 2048 * 2048,
                       "growth must append at the first sector after the image")
            m._require(op["after_size"] == new["sector"] * 2048 + new["size"], "growth result size differs from append extent")
        elif cls.shrink:
            m._require(0 < new['size'] < old['size'], 'file_shrink must shorten a nonempty named file')
            m._require(new['sector'] == old['sector'] and op['after_size'] == before,
                       'file_shrink keeps its sector and physical image size')
        else:
            m._require((new["sector"], new["size"], op["after_size"]) == (old["sector"], old["size"], before),
                       "file_replace keeps its extent; use file_grow for a larger file")
        # A named data file may never alias its directory node or volume header.
        for state in (old, new):
            lo, hi = state["sector"] * 2048, state["sector"] * 2048 + state["size"]
            m._require(not (lo < node + 8 and node < hi) and not (lo < 0x10800 and 0x10000 < hi),
                       "file overlaps XDVDFS metadata")
        if cls.special:
            m._require(path.casefold() == "default.xbe" and old["size"] == storage.RETAIL_FILE_SIZE
                       and new["size"] == storage.FILE_SIZE, "unrecognised SPECIAL storage transition")

    @classmethod
    def plan(cls, op, view, pack, verify):
        old, new = op["before"], op["after"]
        node = view.partition + op["directory_offset"]
        if verify:
            actual = storage.image_file_node(view.read, view.partition, view.size, op["path"])
            m._require(actual == (node, old["sector"], old["size"]), f"{op['path']}: expected-before directory extent differs")
            start = view.partition + old["sector"] * 2048
            m._require(view.digest(start, old["size"]) == old["sha256"], f"{op['path']}: expected-before file hash differs")
            if cls.special:
                m._require(storage.state(view.read(old["size"], start)) == "retail", "unrecognised SPECIAL storage before growth")
        read = blob_reader(pack, op["payload"])
        if cls.special:
            from . import nfl2k5_depth_chart_rows as rows
            m._require(rows.status(read(new["size"], 0)) == "applied", "expected a complete SPECIAL XBE")
        start = view.partition + new["sector"] * 2048
        if cls.grow:
            if start > view.size:
                padding = start - view.size
                view.put(view.size, padding, literal(bytes(padding)))
        view.put(start, new["size"], read)
        if cls.grow or cls.shrink:
            view.put(node, 8, literal(struct.pack("<II", new["sector"], new["size"])))
        if verify:
            actual = storage.image_file_node(view.read, view.partition, view.size, op["path"])
            m._require(actual == (node, new["sector"], new["size"]), f"{op['path']}: expected-after directory differs")


    @staticmethod
    def verify_written(op, view):
        node, sector, length = storage.image_file_node(view.read, view.partition, view.size, op["path"])
        expected = op["after"]
        m._require((node, sector, length) == (view.partition + op["directory_offset"], expected["sector"], expected["size"]),
                   f"{op['path']}: written expected-after extent differs")
        m._require(view.digest(view.partition + sector * 2048, length) == expected["sha256"],
                   f"{op['path']}: written expected-after hash differs")

    @staticmethod
    def verify_final(op, projected, actual):
        # Later operations may change this same file. Compare the final name
        # resolution with the final projection, rather than this op's interim extent.
        wanted = storage.image_file_node(projected.read, projected.partition, projected.size, op["path"])
        found = storage.image_file_node(actual.read, actual.partition, actual.size, op["path"])
        m._require(found == wanted, f"{op['path']}: final named extent differs")


class FileGrow(FileReplace):
    name = "file_grow"
    grow = True


class XbeGrow(FileGrow):
    name = "xbe_grow"
    special = True

    @staticmethod
    def execute(op, pack, descriptor, spans):
        storage.write_image_xbe(descriptor, blob_reader(pack, op["payload"])(op["after"]["size"], 0))


class FileShrink(FileReplace):
    """Shorten the named extent; retain all physical allocation slack."""
    name = 'file_shrink'
    shrink = True


# Never reuse IDs. Registering a handler is the only dispatcher change needed.
REGISTRY: dict[int, Any] = {}


def register(op_type: int, handler) -> None:
    m._int(op_type, "op_type")
    m._require(op_type not in REGISTRY, f"operation type {op_type} is already registered")
    m._int(handler.min_reader_version, "handler.min_reader_version", minimum=2)
    REGISTRY[op_type] = handler


register(0, ByteRuns)
register(1, XbeGrow)
register(2, FileReplace)
register(3, FileGrow)
register(5, FileShrink)  # ID 4 remains reserved for file_add.
# 4 is reserved for file_add, whose directory-tree allocation is not implemented.


def reader_version():
    return max(READER_VERSION, *(handler.min_reader_version for handler in REGISTRY.values()))


def validate(operations, base, result):
    m._require(isinstance(operations, list) and operations, "manifest has no operations")
    size = base["size"] - base["partition_base"]
    m._require(size > 0, "base partition exceeds image")
    for i, op in enumerate(operations):
        m._require(isinstance(op, Mapping), f"operation {i} is not an object")
        op_type = m._int(op.get("type"), "operation.type")
        handler = REGISTRY.get(op_type)
        m._require(handler is not None, f"{NEWER_READER}: unknown operation type {op_type}")
        version = m._int(op.get("version"), "operation.version", minimum=1)
        m._require(version == handler.version, f"{NEWER_READER}: {handler.name} version {version}")
        m._require(op.get("name") == handler.name, f"operation {i} type/name disagree")
        m._require(m._int(op.get("before_size"), "operation.before_size", minimum=1) == size, f"operation {i} image size chain differs")
        m._int(op.get("after_size"), "operation.after_size", minimum=1)
        payload = _blob(op.get("payload"), f"operation {i}.payload")
        handler.validate(op, size, payload)
        size = op["after_size"]
    m._require(size + base["partition_base"] == result["size"], "operation result size differs from manifest")
    return tuple(dict(op) for op in operations)


def plan(pack, descriptor, *, verify=True):
    size = os.fstat(descriptor).st_size
    partition = m.partition_base(descriptor, size) or 0
    view = View(descriptor, size, partition)
    ops = pack.manifest.patch_operations
    if verify:
        m._require(size - partition == ops[0]["before_size"], "operation 0: expected-before image size differs")
    else:
        # Project the final writes onto the current image to recognise an applied
        # pack, including overlapping writes from different operations.
        view.size = partition + ops[0]["before_size"]
    steps = []
    for i, op in enumerate(ops):
        first = len(view.spans)
        try:
            REGISTRY[op["type"]].plan(op, view, pack, verify)
            m._require(view.size == partition + op["after_size"], "expected-after image size differs")
        except (ValueError, struct.error) as exc:
            raise m.ModpackError(f"operation {i} ({op['name']}): {exc}") from exc
        steps.append(view.spans[first:])
    return view, steps


def final_matches(view, descriptor):
    if os.fstat(descriptor).st_size != view.size:
        return False
    ranges = m.coalesce(sorted((s.offset, s.offset + s.length) for s in view.spans), 1)
    for lo, hi in ranges:
        for at in range(lo, hi, m.BLOCK):
            count = min(m.BLOCK, hi - at)
            if m._pread_exact(descriptor, count, at, "operation result") != view.read(count, at):
                return False
    return True


def verify_payloads(pack):
    seen = set()
    for op in pack.manifest.patch_operations:
        blob = op["payload"]
        key = (blob["member"], blob["length"], blob["sha256"])
        if key not in seen:
            m._require(pack.blob_size(blob["member"]) == blob["length"], f"{blob['member']}: payload size differs")
            m._require(digest(blob_reader(pack, blob), blob["length"]) == blob["sha256"], f"{blob['member']}: payload digest differs")
            seen.add(key)


def check(pack, descriptor, progress):
    verify_payloads(pack)
    try:
        view, steps = plan(pack, descriptor)
        return "ready", "Every operation's expected-before and expected-after bytes verify; the patch can be applied.", view, steps
    except m.ModpackError as exc:
        explanation = str(exc)
    try:
        view, steps = plan(pack, descriptor, verify=False)
        if final_matches(view, descriptor):
            # Names still have to resolve; matching recorded offsets alone must
            # not accept a different or damaged directory tree.
            actual = View(descriptor, os.fstat(descriptor).st_size, view.partition)
            for op in pack.manifest.patch_operations:
                verifier = getattr(REGISTRY[op["type"]], "verify_final", None)
                if verifier:
                    verifier(op, view, actual)
            return "applied", "Every operation's final bytes are already present.", view, steps
    except (ValueError, struct.error):
        pass
    return "mismatch", explanation, None, None


def execute(pack, descriptor, progress):
    view, steps = plan(pack, descriptor)
    for i, (op, spans) in enumerate(zip(pack.manifest.patch_operations, steps)):
        # Re-plan the single operation against bytes written by its predecessors.
        current = View(descriptor, os.fstat(descriptor).st_size, view.partition)
        REGISTRY[op["type"]].plan(op, current, pack, True)
        custom = getattr(REGISTRY[op["type"]], "execute", None)
        if custom:
            custom(op, pack, descriptor, spans)
        else:
            for span in spans:
                for at in range(0, span.length, m.BLOCK):
                    m._pwrite_all(descriptor, span.read(min(m.BLOCK, span.length - at), at), span.offset + at, op["name"])
        m._require(final_matches(current, descriptor), f"operation {i} ({op['name']}): result read-back differs")
        verifier = getattr(REGISTRY[op["type"]], "verify_written", None)
        if verifier:
            verifier(op, View(descriptor, os.fstat(descriptor).st_size, view.partition))
        progress("Applying operations", i + 1, len(steps))
    m._require(final_matches(view, descriptor), "composed operation result read-back differs")
    return view.size


@dataclass(frozen=True)
class Payload:
    length: int
    read: Callable[[int, int], bytes]

    def document(self, member):
        return {"member": member, "length": self.length, "sha256": digest(self.read, self.length)}


class DraftPack:
    """The export verifier reads the proposed ZIP members from source spans."""

    def __init__(self, manifest, payloads):
        self.manifest = manifest
        self.payloads = payloads

    def read_blob(self, member, count, offset):
        return self.payloads[member].read(count, offset)

    def blob_size(self, member):
        return self.payloads[member].length


def _subtract(ranges, exclusions):
    for lo, hi in ranges:
        for start, end in sorted(exclusions):
            if start >= hi:
                break
            if end <= lo:
                continue
            if lo < start:
                yield lo, start
            lo = max(lo, end)
        if lo < hi:
            yield lo, hi


def detect(base, patched, size, patched_size, partition, ranges, named_files):
    """Conservative automatic export; arbitrary operations use the explicit API.

    Size changes must be accounted for by named allocations. SPECIAL is the
    sole implicit allocation; other files require the caller to name them.
    """
    m._require(patched_size >= size, "unrecognised image size change: shrinking needs a registered operation")
    named = list(named_files)
    before_entries = after_entries = {}
    if size != patched_size or named:
        try:
            before_entries, _ = m._xdvdfs_module().parse_xdvdfs(base, size)
            after_entries, _ = m._xdvdfs_module().parse_xdvdfs(patched, patched_size)
        except ValueError as exc:
            raise m.ModpackError(f"unrecognised image size change: {exc}") from exc
        m._require(before_entries.keys() == after_entries.keys(), "file additions/removals need a registered directory operation")
        old, new = before_entries.get("default.xbe"), after_entries.get("default.xbe")
        if old and new and old.size == storage.RETAIL_FILE_SIZE and new.size == storage.FILE_SIZE and old.sector != new.sector:
            named = [p for p in named if p.casefold() != "default.xbe"] + ["default.xbe"]
        allowed = {p.casefold() for p in named}
        for path, old in before_entries.items():
            new = after_entries[path]
            m._require(old.attributes == new.attributes, f"unrecognised file attributes change: {old.path}")
            m._require(path in allowed or (old.sector, old.size) == (new.sector, new.size),
                       f"unrecognised file allocation change: {old.path}; name it in file_operations")
    named = sorted(set(named), key=lambda name: after_entries[name.casefold()].byte_offset
                   if name.casefold() in after_entries else -1)
    exclusions, file_ops, payloads = [], [], {}
    for name in named:
        old, new = before_entries.get(name.casefold()), after_entries.get(name.casefold())
        m._require(old is not None and new is not None and not old.attributes & 0x10, f"missing named disc file: {name}")
        old_node = storage.image_file_node(lambda n, at: m._pread_exact(base, n, at, name), partition, size, name)
        new_node = storage.image_file_node(lambda n, at: m._pread_exact(patched, n, at, name), partition, patched_size, name)
        m._require(old_node[0] == new_node[0], f"{name}: directory node moved; needs a directory operation")
        growing = new.size > old.size
        special = (name.casefold() == "default.xbe" and old.size == storage.RETAIL_FILE_SIZE
                   and new.size == storage.FILE_SIZE and growing)
        # The implicit SPECIAL path must remain a recognised storage transition.
        if special:
            from . import nfl2k5_depth_chart_rows as rows
            m._require(rows.status(m._pread_exact(patched, new.size, new.byte_offset, name)) == "applied",
                       "unrecognised SPECIAL storage transition")
        shrinking = new.size < old.size
        if shrinking:
            m._require(new.sector == old.sector, 'file_shrink cannot relocate a file')
            tail = old.size - new.size
            m._require(digest(lambda n, at: m._pread_exact(base, n, old.byte_offset + new.size + at, 'old file slack'), tail)
                       == digest(lambda n, at: m._pread_exact(patched, n, old.byte_offset + new.size + at, 'new file slack'), tail),
                       'file_shrink must preserve unused physical allocation bytes')
        op_type = 1 if special else 3 if growing else 5 if shrinking else 2
        member = f"operations/file-{len(file_ops):04d}.bin"
        payload = Payload(new.size, lambda n, at, start=new.byte_offset: m._pread_exact(patched, n, start + at, "named file payload"))
        payloads[member] = payload
        payload_doc = payload.document(member)
        # byte_runs precedes file operations. In a growth build the old allocation
        # can already contain earlier studio edits, which must travel too.
        before_fd = patched if growing else base
        before_hash = digest(lambda n, at, start=old.byte_offset: m._pread_exact(before_fd, n, start + at, "named file before"), old.size)
        op = {"type": op_type, "name": REGISTRY[op_type].name, "version": 1,
              "path": old.path, "directory_offset": old_node[0] - partition,
              "before": {"sector": old.sector, "size": old.size, "sha256": before_hash},
              "after": {"sector": new.sector, "size": new.size, "sha256": payload_doc["sha256"]},
              "payload": payload_doc}
        file_ops.append(op)
        exclusions.append((old_node[0], old_node[0] + 8))
        if not growing:
            exclusions.append((old.byte_offset, old.byte_offset + old.size))
    ranges = list(_subtract(ranges, exclusions))
    operations = []
    if ranges:
        regions = m.image_regions(base, size)
        runs, cursor = [], 0
        for lo, hi in ranges:
            runs.append({"op": "replace", "offset": lo - partition, "length": hi - lo,
                         "payload_offset": cursor,
                         "expected_sha256": digest(lambda n, at, lo=lo: m._pread_exact(base, n, lo + at, "base run"), hi - lo),
                         "new_sha256": digest(lambda n, at, lo=lo: m._pread_exact(patched, n, lo + at, "patched run"), hi - lo),
                         "region": m._region_of(regions, lo)})
            cursor += hi - lo

        def read_runs(count, offset):
            result, cursor = bytearray(), 0
            end = offset + count
            for lo, hi in ranges:
                length = hi - lo
                left, right = max(offset, cursor), min(end, cursor + length)
                if left < right:
                    result += m._pread_exact(patched, right - left, lo + left - cursor, "run payload")
                cursor += length
                if cursor >= end:
                    break
            return bytes(result)

        payload = Payload(cursor, read_runs)
        member = "operations/byte-runs.bin"
        payloads[member] = payload
        operations.append({"type": 0, "name": "byte_runs", "version": 1,
                           "before_size": size - partition, "after_size": size - partition,
                           "runs": runs, "payload": payload.document(member)})
    current_size = size - partition
    for op in file_ops:
        op["before_size"] = current_size
        if op["type"] in (1, 3):
            current_size = op["after"]["sector"] * 2048 + op["after"]["size"]
        op["after_size"] = current_size
        operations.append(op)
    m._require(operations, "the patched image is identical to the base; there is nothing to share")
    m._require(current_size + partition == patched_size, "unrecognised image size change: appended bytes are not a named file allocation")
    return operations, payloads

"""Conservative, bounded static XBE cave analysis; never modifies an executable.

``reachable`` means a decoded reference/path exists in the stated root model,
not that gameplay executed it. Pointer-shaped raw words are speculative roots.
Unresolved transfers/reads and analysis limits taint otherwise unobserved bytes
``unknown``. See docs/NFL2K5_CAVE_ORACLE.md for the complete proof boundary.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, deque
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Iterable

RETAIL_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
SCHEMA = "nfl2k5-cave-oracle-v1"
MANIFEST_SCHEMA = "nfl2k5-cave-reservations-v1"
ENTRY_KEYS = {"retail": 0xA8FC57AB, "debug": 0x94859D4B, "sega": 0x40B5C16E}
THUNK_KEYS = {"retail": 0x5B6D40B6, "debug": 0xEFB1F152, "sega": 0x2290059D}
DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / "data/nfl2k5_cave_reservations.json"
MODEL = (
    "32-bit x86, validated XBE section mappings and decoded entry/TLS/import roots; "
    "all unaligned section dwords into mapped sections are possible pointer roots; "
    "bytewise relative transfers and callback stores supplement recursive decoding. "
    "Raw encodings without a rooted instruction boundary are speculative. "
    "Known paths include call return/fallthrough; returns use balanced call stacks. "
    "No injected code, self modification, address synthesis outside decoded operations, "
    "external DMA, or undocumented loader entry points is assumed. Unresolved memory "
    "accesses/indirect transfers, malformed roots, and exhausted budgets remain unknown "
    "across the image. Free is conditional on this model, never a gameplay proof."
)


class OracleError(ValueError):
    """Malformed input, stale ownership evidence, or unsafe allocation."""


@dataclass(frozen=True, slots=True)
class Section:
    name: str
    start: int
    size: int
    raw: int
    raw_size: int
    flags: int
    header: int

    @property
    def end(self) -> int:
        return self.start + self.size

    @property
    def file_end(self) -> int:
        return self.start + min(self.size, self.raw_size)

    @property
    def executable(self) -> bool:
        return bool(self.flags & 4)

    @property
    def writable(self) -> bool:
        # The explicit .text veto is intentional even for a modified header.
        return bool(self.flags & 1) and self.name != ".text"


class XbeImage:
    """Bounds checked VA/file mapping, including non-linear raw section offsets."""

    def __init__(self, data: bytes):
        self.data = data
        if len(data) < 0x178 or data[:4] != b"XBEH":
            raise OracleError("expected a complete XBEH header")
        self.base, self.headers_size, self.image_size = struct.unpack_from("<3I", data, 0x104)
        if not 0x178 <= self.headers_size <= len(data):
            raise OracleError("invalid SizeOfHeaders")
        if not self.headers_size <= self.image_size <= 0x10000000 or self.base + self.image_size > 2**32:
            raise OracleError("invalid or excessive SizeOfImage (limit 256 MiB)")
        count, table = struct.unpack_from("<II", data, 0x11C)
        off = table - self.base
        if not 0 < count <= 4096 or off < 0 or off + count * 56 > self.headers_size:
            raise OracleError("section table outside headers")
        sections = []
        for i in range(count):
            h = off + i * 56
            flags, va, size, raw, raw_size, name_va = struct.unpack_from("<6I", data, h)
            name_off = name_va - self.base
            if not 0 <= name_off < self.headers_size:
                raise OracleError("section name outside headers")
            end = data.find(b"\0", name_off, min(name_off + 256, self.headers_size))
            if end < 0:
                raise OracleError("unterminated section name")
            name = data[name_off:end].decode("ascii", "replace")
            if size <= 0 or va < self.base + self.headers_size or va + size > self.base + self.image_size:
                raise OracleError(f"invalid virtual bounds for section {name}")
            if raw_size and (raw < self.headers_size or raw + raw_size > len(data)):
                raise OracleError(f"truncated/overlapping raw data for section {name}")
            sections.append(Section(name, va, size, raw, raw_size, flags, h))
        self.sections = sorted(sections, key=lambda s: s.start)
        for left, right in zip(self.sections, self.sections[1:]):
            if left.end > right.start:
                raise OracleError("overlapping virtual sections")
        raws = sorted((s.raw, s.raw + s.raw_size) for s in sections if s.raw_size)
        if any(a[1] > b[0] for a, b in zip(raws, raws[1:])):
            raise OracleError("overlapping raw sections")
        self.starts = [s.start for s in self.sections]
        self.sha256 = hashlib.sha256(data).hexdigest()

    def section(self, va: int, size: int = 1) -> Section | None:
        i = bisect_right(self.starts, va) - 1
        if i >= 0 and size > 0:
            s = self.sections[i]
            if s.start <= va and va + size <= s.end:
                return s
        return None

    def offset(self, va: int, size: int = 1) -> int:
        if size <= 0:
            raise OracleError("read size must be positive")
        if self.base <= va and va + size <= self.base + self.headers_size:
            return va - self.base
        s = self.section(va, size)
        if s is None or va + size > s.file_end:
            raise OracleError(f"{va:#x}+{size:#x} has no file-backed mapping")
        return s.raw + va - s.start

    def read(self, va: int, size: int) -> bytes:
        off = self.offset(va, size)
        return self.data[off:off + size]

    def word(self, va: int) -> int:
        return struct.unpack("<I", self.read(va, 4))[0]

    def va_for_offset(self, off: int) -> int | None:
        if 0 <= off < self.headers_size:
            return self.base + off
        for s in self.sections:
            if s.raw <= off < s.raw + min(s.size, s.raw_size):
                return s.start + off - s.raw
        return None

    def runtime_writable(self, va: int, size: int = 1) -> bool | None:
        """Check the WHOLE access. Gaps inherit only agreeing page neighbours.

        This matches the existing write gate's shared-page model; gap allocation
        itself is still unknown and never a runtime-data cave.
        """
        if size <= 0 or va < 0 or va + size > 2**32:
            return None
        result: bool | None = True
        for address in range(va, va + size):
            s = self.section(address)
            if s:
                if not s.writable:
                    return False
            elif self.base <= address < self.base + self.headers_size:
                return False
            else:
                page = address & ~0xFFF
                neighbours = [s for s in self.sections if s.start < page + 0x1000 and page < s.end]
                if not neighbours:
                    result = None
                elif not all(s.writable for s in neighbours):
                    return False
        return result


@dataclass(frozen=True, slots=True)
class Evidence:
    start: int
    end: int
    source: int | None
    kind: str
    detail: str
    certainty: str = "reachable"

    def report(self) -> dict:
        return {"start": hex(self.start), "end": hex(self.end),
                "source": hex(self.source) if self.source is not None else None,
                "kind": self.kind, "detail": self.detail, "certainty": self.certainty}


class ReservationManifest:
    def __init__(self, document: dict, image: XbeImage, *, source_root: Path | None = None):
        if document.get("schema") != MANIFEST_SCHEMA:
            raise OracleError("unsupported reservation manifest schema")
        if document.get("retail_sha256") != image.sha256:
            raise OracleError("reservation manifest belongs to different XBE bytes")
        if not document.get("complete"):
            raise OracleError("reservation manifest is incomplete")
        spans = document.get("spans")
        if not isinstance(spans, list) or not spans:
            raise OracleError("reservation manifest contains no spans")
        stack_size = document.get("stack_image_size", image.image_size)
        if type(stack_size) is not int or not image.image_size <= stack_size <= 0x10000000:
            raise OracleError("invalid reservation stack image size")
        self.spans = []
        for row in spans:
            a, b = int(row["start"], 0), int(row["end"], 0)
            if not image.base <= a < b <= image.base + stack_size or not row.get("owner"):
                raise OracleError("invalid reserved span")
            self.spans.append(Evidence(a, b, None, "reserved", row["owner"] + ": " + row["basis"], "reserved"))
        if source_root is not None:
            if not document.get("source_sha256"):
                raise OracleError("reservation manifest lacks patch source fingerprints")
            root = source_root.resolve()
            for relative, expected in document["source_sha256"].items():
                path = (root / relative).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    raise OracleError(f"reservation source missing: {relative}; regenerate manifest")
                if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise OracleError(f"stale reservation source: {relative}; regenerate manifest")
        self.document = document

    @classmethod
    def load(cls, path: Path, image: XbeImage, *, source_root: Path | None = None):
        return cls(json.loads(path.read_text(encoding="utf-8")), image, source_root=source_root)

    def overlaps(self, start: int, end: int, *, exclude_owner: str | None = None) -> list[Evidence]:
        return [s for s in self.spans if s.start < end and start < s.end
                and (exclude_owner is None or s.detail.split(":", 1)[0] != exclude_owner)]


def _capstone():
    try:
        import capstone
    except ImportError as exc:
        raise OracleError("capstone is required; install tools/requirements-nfl2k5-cave-oracle.txt") from exc
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    return capstone, md


def relative_encodings(image: XbeImage, *, legacy: bool = False) -> Iterable[Evidence]:
    """Bytewise superset, including overlapping instructions and embedded data.

    Evidence is speculative until a recursive decode establishes the boundary.
    The legacy mode deliberately preserves the old gate's scanning endpoints.
    """
    for s in image.sections:
        if (legacy and s.name != ".text") or (not legacy and not s.executable):
            continue
        data = image.data[s.raw:s.raw + min(s.raw_size, s.size)]
        stop = len(data) - 5 if legacy else len(data)
        for off in range(max(0, stop)):
            op, width, prefix = data[off], 0, 0
            if op in (0xE8, 0xE9):
                width, prefix = 4, 1
            elif op == 0x0F and off + 1 < len(data) and 0x80 <= data[off + 1] <= 0x8F:
                width, prefix = 4, 2
            elif not legacy and (op == 0xEB or 0x70 <= op <= 0x7F or 0xE0 <= op <= 0xE3):
                width, prefix = 1, 1
            if not width or off + prefix + width > len(data):
                continue
            rel = int.from_bytes(data[off + prefix:off + prefix + width], "little", signed=True)
            target = (s.start + off + prefix + width + rel) & 0xFFFFFFFF
            target_section = image.section(target)
            if target_section and (not legacy or target_section.name == ".text"):
                yield Evidence(target, target + 1, s.start + off, "rel" + str(width * 8),
                               "bytewise transfer encoding; instruction boundary not established", "unknown")


def legacy_references(image: XbeImage) -> dict[int, list[Evidence]]:
    """Compatibility projection of test_xbe_patch_cave_references.py, not a proof of freedom."""
    targets: dict[int, list[Evidence]] = {}
    for e in relative_encodings(image, legacy=True):
        targets.setdefault(e.start, []).append(e)
    for s in image.sections:
        if s.name not in (".text", ".rdata", ".data"):
            continue
        step = 1 if s.name == ".text" else 4
        for off in range(s.raw, s.raw + s.raw_size - 4, step):
            v = struct.unpack_from("<I", image.data, off)[0]
            target = image.section(v)
            if not target or target.name != ".text":
                continue
            if s.name == ".text":
                prev = image.data[off - 1]
                if not (prev == 0x68 or 0xB8 <= prev <= 0xBF
                        or image.data[off - 2:off] == b"\xc7\x05"
                        or image.data[off - 6:off - 4] == b"\xc7\x05"):
                    continue
            e = Evidence(v, v + 1, s.start + off - s.raw, "legacy-pointer",
                         f"legacy pointer filter in {s.name}", "unknown")
            targets.setdefault(v, []).append(e)
    return targets


def legacy_external_references(targets: dict[int, list[Evidence]], start: int, end: int) -> list[Evidence]:
    """Old gate permits a replaced entry and references originating inside the span."""
    return [e for t, refs in targets.items() if start < t < end for e in refs
            if e.source is None or not start <= e.source < end]


class CaveOracle:
    def __init__(self, data: bytes, *, manifest: ReservationManifest | None = None,
                 instruction_budget: int = 250_000, reference_budget: int = 2_000_000):
        if instruction_budget <= 0 or reference_budget <= 0:
            raise OracleError("analysis budgets must be positive")
        self.image = XbeImage(data)
        if manifest and manifest.document["retail_sha256"] != self.image.sha256:
            raise OracleError("manifest/XBE mismatch")
        self.manifest = manifest
        self.instruction_budget, self.reference_budget = instruction_budget, reference_budget
        self.evidence: list[Evidence] = []
        self.unknowns: list[Evidence] = []
        self._unknown_keys: set[tuple] = set()
        self._unknown_kinds: dict[str, Evidence] = {}
        self.instructions: dict[int, tuple[int, str, str]] = {}
        self.writes: list[dict] = []
        self.roots: list[dict] = []
        self._queue: deque[tuple[int, str, int | None, str]] = deque()
        self._queued: set[tuple[int, str]] = set()
        self._ran = False
        self._reference_limit = False
        self._instruction_limit = False
        self.reference_count = 0
        self._states = {s.start: bytearray(s.size) for s in self.image.sections}

    def _unknown(self, source: int | None, kind: str, detail: str):
        key = source, kind
        if key not in self._unknown_keys:
            self._unknown_keys.add(key)
            evidence = Evidence(self.image.base, self.image.base + self.image.image_size,
                                source, kind, detail, "unknown")
            self.unknowns.append(evidence)
            self._unknown_kinds.setdefault(kind, evidence)

    def _add(self, e: Evidence):
        if e.kind != "instruction" and self.reference_count >= self.reference_budget:
            self._reference_limit = True
            self._unknown(None, "reference-budget", "reference budget exhausted; unexamined bytes remain unknown")
            return
        if e.kind != "instruction":
            self.reference_count += 1
        self.evidence.append(e)
        value = 2 if e.certainty == "reachable" else 1
        # Some structures straddle section ends, and pointer words can cross raw padding.
        for s in self.image.sections:
            a, b = max(e.start, s.start), min(e.end, s.end)
            if a >= b:
                continue
            state = self._states[s.start]
            lo, hi = a - s.start, b - s.start
            if value == 2:
                state[lo:hi] = b"\x02" * (hi - lo)
            else:
                for i in range(lo, hi):
                    if state[i] == 0:
                        state[i] = 1

    def _root(self, va: int, certainty: str, source: int | None, kind: str):
        s = self.image.section(va)
        if s is None:
            self._unknown(source, "unmapped-root", f"{kind} targets unmapped {va:#x}")
            return
        self._add(Evidence(va, va + 1, source, kind, f"{kind} root at {va:#x}", certainty))
        if s.executable:
            key = va, certainty
            if key not in self._queued:
                self._queued.add(key)
                row = (va, certainty, source, kind)
                if certainty == "reachable":
                    self._queue.appendleft(row)
                else:
                    self._queue.append(row)

    def _terminated_words(self, va: int, kind: str, *, callbacks: bool = False):
        for i in range(4096):
            at = va + 4 * i
            v = self.image.word(at)
            self._add(Evidence(at, at + 4, va, kind, "loader/table reads this dword"))
            if v == 0:
                return
            if callbacks:
                self._root(v, "reachable", at, kind + "-target")
            elif v & 0x80000000:
                self._unknown(at, "external-import", "import ABI/body is outside the image; effects unresolved")
            else:
                self._root(v, "unknown", at, kind + "-nonordinal")
        raise OracleError(f"{kind} table did not terminate within 4096 words")

    def _loader_roots(self):
        d = self.image.data
        encoded = struct.unpack_from("<I", d, 0x128)[0]
        matches = [(k, encoded ^ key) for k, key in ENTRY_KEYS.items()
                   if (s := self.image.section(encoded ^ key)) and s.executable]
        if len(matches) != 1:
            self._unknown(self.image.base + 0x128, "entry-decode", "entry XOR key is absent or ambiguous")
        for kind, va in matches:
            self.roots.append({"kind": "entry", "encoding": kind, "address": hex(va)})
            self._root(va, "reachable", self.image.base + 0x128, "entry")
            thunk = struct.unpack_from("<I", d, 0x158)[0] ^ THUNK_KEYS[kind]
            if thunk:
                try:
                    self._terminated_words(thunk, "kernel-import")
                except OracleError as exc:
                    self._unknown(thunk, "malformed-import", str(exc))
        tls = struct.unpack_from("<I", d, 0x12C)[0]
        if tls:
            try:
                values = struct.unpack("<6I", self.image.read(tls, 24))
                self.roots.append({"kind": "tls", "address": hex(tls)})
                self._add(Evidence(tls, tls + 24, self.image.base + 0x12C, "tls", "loader TLS directory"))
                start, end, index, callbacks, zero_fill, _ = values
                if end < start or end - start + zero_fill > self.image.image_size:
                    raise OracleError("invalid TLS template bounds")
                if end > start:
                    self.image.read(start, end - start)
                    self._add(Evidence(start, end, tls, "tls-template", "TLS initialized data read by loader"))
                if index:
                    self._add(Evidence(index, index + 4, tls + 8, "tls-index", "TLS runtime index written by loader"))
                if callbacks:
                    self._terminated_words(callbacks, "tls-callback", callbacks=True)
            except OracleError as exc:
                self._unknown(tls, "malformed-tls", str(exc))
        imports = struct.unpack_from("<I", d, 0x15C)[0]
        if imports:
            try:
                for i in range(4096):
                    at = imports + 8 * i
                    thunk, name = struct.unpack("<II", self.image.read(at, 8))
                    self._add(Evidence(at, at + 8, imports, "nonkernel-import", "thunk/name directory record"))
                    if thunk == 0:
                        break
                    self._terminated_words(thunk, "nonkernel-thunk")
                    # Names are UTF-16; their extent is significant too.
                    for n in range(4096):
                        if self.image.read(name + n * 2, 2) == b"\0\0":
                            self._add(Evidence(name, name + 2 * (n + 1), at + 4, "import-name", "loader reads UTF-16 module name"))
                            break
                    else:
                        raise OracleError("unterminated import module name")
                else:
                    raise OracleError("unterminated nonkernel import directory")
            except OracleError as exc:
                self._unknown(imports, "malformed-import", str(exc))
        logo, size = struct.unpack_from("<II", d, 0x170)
        if logo and size:
            try:
                self.image.read(logo, size)
                self._add(Evidence(logo, logo + size, self.image.base + 0x170, "boot-logo", "kernel reads boot bitmap"))
            except OracleError as exc:
                self._unknown(logo, "malformed-logo", str(exc))

    def _raw_roots(self):
        # Explicit encodings across ALL executable sections are considered before
        # potentially enormous pointer-shaped data tables consume the budget.
        for s in self.image.sections:
            # Explicit callback stores have a complete instruction witness even
            # if the enclosing function was never reached by the entry traversal.
            if s.executable:
                chunk = self.image.data[s.raw:s.raw + min(s.size, s.raw_size)]
                for match in re.finditer(b"\xc7\x05", chunk):
                    off = match.start()
                    if off + 10 > len(chunk):
                        continue
                    dst, value = struct.unpack_from("<II", chunk, off + 2)
                    target = self.image.section(value)
                    if target and target.executable and self.image.section(dst, 4):
                        source = s.start + off
                        self._add(Evidence(value, value + 1, source, "callback-store",
                                           f"mov dword ptr [{dst:#x}], {value:#x}; static store witness"))
                        self._root(value, "reachable", source, "callback-target")
        for e in relative_encodings(self.image):
            if self._reference_limit:
                return
            self._add(e)
            self._root(e.start, "unknown", e.source, e.kind)
        # Scan all byte alignments, including the last complete word in each section.
        high_bytes = {a for s in self.image.sections for a in range(s.start >> 24, ((s.end - 1) >> 24) + 1)}
        for s in self.image.sections:
            stop = s.raw + min(s.size, s.raw_size) - 3
            for off in range(s.raw, stop):
                if self._reference_limit:
                    return
                if self.image.data[off + 3] not in high_bytes:
                    continue
                value = struct.unpack_from("<I", self.image.data, off)[0]
                if self.image.section(value) is None:
                    continue
                source = s.start + off - s.raw
                self._add(Evidence(source, source + 4, source, "possible-pointer-storage",
                                   f"unaligned dword may contain pointer to {value:#x}", "unknown"))
                self._root(value, "unknown", source, "possible-pointer")

    def _memory_operand(self, insn, op, certainty: str, is_transfer: bool):
        from capstone import CS_AC_READ, CS_AC_WRITE
        m = op.mem
        absolute = m.base == 0 and m.index == 0 and m.segment == 0
        disp = m.disp & 0xFFFFFFFF
        width = max(1, op.size)
        access = op.access
        if insn.mnemonic == "lea":
            if absolute and self.image.section(disp):
                self._root(disp, certainty, insn.address, "address-materialized")
            return
        if not absolute:
            # No base/index range analysis is claimed. Even stack-derived pointers
            # can escape, so these accesses cannot justify any new free bytes.
            self._unknown(insn.address, "unresolved-memory", f"unbounded address: {insn.mnemonic} {insn.op_str}")
            if not m.base and m.index and self.image.section(disp):
                self._add(Evidence(disp, disp + width, insn.address, "indexed-table",
                                   "static table base; index/extent unresolved", "unknown"))
                if is_transfer and m.scale == 4:
                    for i in range(4096):
                        try:
                            v = self.image.word(disp + i * 4)
                        except OracleError:
                            break
                        s = self.image.section(v)
                        if not s or not s.executable:
                            break
                        self._add(Evidence(disp + i * 4, disp + i * 4 + 4, insn.address,
                                           "jump-table-slot", "contiguous pointer run; not a proven table bound", "unknown"))
                        self._root(v, "unknown", disp + i * 4, "jump-table-target")
            return
        if self.image.section(disp) or self.image.base <= disp < self.image.base + self.image.headers_size:
            self._add(Evidence(disp, disp + width, insn.address, "data-write" if access & CS_AC_WRITE else "data-read",
                               f"{insn.mnemonic} {insn.op_str} (width {width})", certainty))
        elif access & CS_AC_READ:
            self._unknown(insn.address, "external-read", f"read at {disp:#x} is outside the image model")
        if access & CS_AC_WRITE:
            self.writes.append({"instruction": hex(insn.address), "target": hex(disp), "size": width,
                                "writable": self.image.runtime_writable(disp, width), "certainty": certainty,
                                "detail": f"{insn.mnemonic} {insn.op_str}"})
        if access & CS_AC_READ:
            try:
                for offset in range(max(0, width - 3)):
                    v = self.image.word(disp + offset)
                    if self.image.section(v):
                        self._root(v, certainty, insn.address, "read-pointer" if is_transfer else "possible-read-pointer")
            except OracleError:
                self._unknown(insn.address, "unbacked-read", f"read at {disp:#x} lacks complete file bytes")

    def _decode(self):
        cs, md = _capstone()
        from capstone.x86 import X86_OP_IMM, X86_OP_MEM
        visited: set[tuple[int, str]] = set()
        count = 0
        # Definite roots get the budget first. A speculative decode never upgrades
        # a root/path into a definite one merely because its opcodes look valid.
        self._queue = deque(sorted(self._queue, key=lambda row: row[1] != "reachable"))
        while self._queue:
            va, certainty, source, reason = self._queue.popleft()
            while (va, certainty) not in visited:
                if count >= self.instruction_budget:
                    self._instruction_limit = True
                    self._unknown(va, "instruction-budget", "bounded decode stopped with unexamined roots/paths")
                    self.instruction_count = count
                    return
                visited.add((va, certainty))
                s = self.image.section(va)
                if s is None or not s.executable or va >= s.file_end:
                    self._unknown(source, "unbacked-code", f"code path reaches non-executable/unbacked {va:#x}")
                    break
                raw = self.image.read(va, min(15, s.file_end - va))
                insn = next(md.disasm(raw, va, count=1), None)
                if insn is None:
                    self._unknown(va, "decode-failure", "invalid/truncated instruction on a rooted path")
                    break
                count += 1
                self.instructions[va] = (insn.size, insn.mnemonic, insn.op_str)
                self._add(Evidence(va, va + insn.size, source, "instruction",
                                   f"{reason}: {insn.mnemonic} {insn.op_str}", certainty))
                transfer = insn.group(cs.CS_GRP_JUMP) or insn.group(cs.CS_GRP_CALL)
                for op in insn.operands:
                    if op.type == X86_OP_MEM:
                        self._memory_operand(insn, op, certainty, transfer)
                    elif op.type == X86_OP_IMM and not transfer:
                        target = op.imm & 0xFFFFFFFF
                        if self.image.section(target):
                            self._root(target, certainty, va, "immediate-address")
                if transfer:
                    if insn.operands and insn.operands[0].type == X86_OP_IMM:
                        target = insn.operands[0].imm & 0xFFFFFFFF
                        self._root(target, certainty, va, "direct-transfer")
                    else:
                        self._unknown(va, "indirect-transfer", f"unresolved target: {insn.mnemonic} {insn.op_str}")
                    if insn.mnemonic in ("jmp", "ljmp"):
                        break
                if insn.group(cs.CS_GRP_RET):
                    break
                if insn.group(cs.CS_GRP_INT) or insn.mnemonic in ("hlt", "ud2", "iret", "iretd", "sysenter", "sysexit"):
                    self._unknown(va, "external-control", f"{insn.mnemonic} requires external control semantics")
                    break
                if insn.mnemonic.startswith(("rep", "movs", "stos", "lods", "scas", "cmps")):
                    self._unknown(va, "implicit-memory", "implicit/string access extent unresolved")
                source, va, reason = va, va + insn.size, "call-return" if insn.group(cs.CS_GRP_CALL) else "fallthrough"
        self.instruction_count = count

    def analyze(self):
        if self._ran:
            return self
        self._loader_roots()
        self._raw_roots()
        self._decode()
        for s in self.image.sections:
            if s.file_end < s.end:
                self._add(Evidence(s.file_end, s.end, s.start, "zero-fill",
                                   "virtual allocation has no offline patchable bytes", "unknown"))
        self.evidence.sort(key=lambda e: e.start)
        self._evidence_starts = [e.start for e in self.evidence]
        highest = 0
        self._prefix_end = []
        for e in self.evidence:
            highest = max(highest, e.end)
            self._prefix_end.append(highest)
        self._ran = True
        return self

    def witnesses(self, start: int, end: int) -> list[Evidence]:
        self.analyze()
        first = bisect_right(self._prefix_end, start)
        last = bisect_left(self._evidence_starts, end)
        return [e for e in self.evidence[first:last] if e.end > start]

    def _eligibility(self, start: int, end: int, kind: str) -> tuple[bool, str]:
        if kind not in ("code", "data"):
            raise OracleError("kind must be code or data")
        s = self.image.section(start, end - start)
        if s is None:
            return False, "range is in headers, a gap, unmapped memory, or crosses sections"
        if end > s.file_end:
            return False, "range includes virtual zero-fill with no offline file bytes"
        if kind == "code":
            return s.executable, "executable section" if s.executable else "section is not executable"
        return s.writable, "writable section" if s.writable else "runtime data forbidden: section is read-only or .text"

    def assess(self, start: int, size: int, *, kind: str = "code", exclude_owner: str | None = None) -> dict:
        self.analyze()
        if size <= 0 or start < 0 or start + size > 2**32:
            raise OracleError("invalid candidate bounds")
        end = start + size
        reserved = self.manifest.overlaps(start, end, exclude_owner=exclude_owner) if self.manifest else []
        evidence = self.witnesses(start, end)
        definite = [e for e in evidence if e.certainty == "reachable"]
        possible = [e for e in evidence if e.certainty == "unknown"]
        eligible, permission = self._eligibility(start, end, kind)
        if reserved:
            verdict, reasons = "reserved", reserved
            witness_count = len(reserved)
        elif definite:
            verdict, reasons = "reachable", definite
            witness_count = len(definite)
        elif possible or self.unknowns or not eligible:
            verdict, reasons = "unknown", possible + list(self._unknown_kinds.values())[:8]
            witness_count = len(possible) + len(self.unknowns)
        else:
            verdict, reasons = "free-under-closed-world", []
            witness_count = 0
        # Prefer a callback or transfer witness over an arbitrary instruction at the
        # same address. Keep the total count; display truncation never affects verdicts.
        reasons = sorted(reasons, key=lambda e: (e.kind != "callback-store", e.kind == "instruction"))
        return {"start": hex(start), "end": hex(end), "size": size, "kind": kind,
                "section": (s.name if (s := self.image.section(start, size)) else None),
                "verdict": verdict, "eligible": eligible, "permission_reason": permission,
                "allocatable": eligible and verdict == "free-under-closed-world",
                "witnesses": [e.report() for e in reasons[:8]], "witness_count": witness_count,
                "unresolved_count": len(self.unknowns)}

    def require_cave(self, start: int, size: int, *, kind: str = "code", exclude_owner: str | None = None):
        result = self.assess(start, size, kind=kind, exclude_owner=exclude_owner)
        if not result["allocatable"]:
            raise OracleError(f"cave {start:#x}+{size:#x}: {result['verdict']}; {result['permission_reason']}")
        return result

    def neighbour(self, address: int) -> dict:
        s = self.image.section(address)
        if s is None:
            return {"address": hex(address), "reason": "section boundary / unmapped or header byte", "instructions": []}
        ev = self.witnesses(address, address + 1)
        reserved = self.manifest.overlaps(address, address + 1) if self.manifest else []
        reasons = reserved + sorted(ev, key=lambda e: (e.certainty != "reachable", e.kind != "instruction"))
        covering = [{"start": hex(e.start), "end": hex(e.end), "reason": e.detail,
                     "certainty": e.certainty} for e in ev if e.kind == "instruction"]
        return {"address": hex(address), "section": s.name,
                "reason": reasons[0].detail if reasons else ("unresolved image-wide access" if self.unknowns else "unreferenced in closed-world model"),
                "instructions": covering[:8], "witnesses": [e.report() for e in reasons[:4]]}

    def scan(self, *, min_size: int = 64, kind: str = "code") -> dict:
        self.analyze()
        if min_size <= 0 or kind not in ("code", "data"):
            raise OracleError("positive min-size and code|data kind required")
        ranges, sections = [], []
        labels = {0: "free-under-closed-world", 1: "unknown", 2: "reachable", 3: "reserved"}
        for s in self.image.sections:
            state = bytearray(self._states[s.start])
            eligible = s.executable if kind == "code" else s.writable
            if self.unknowns or not eligible:
                state = state.replace(b"\x00", b"\x01")
            if self.manifest:
                for e in self.manifest.overlaps(s.start, s.end):
                    a, b = max(s.start, e.start) - s.start, min(s.end, e.end) - s.start
                    state[a:b] = b"\x03" * (b - a)
            sections.append({**asdict(s), "eligible": eligible,
                             "coverage": {name: state.count(value) for value, name in labels.items()}})
            for match in re.finditer(b"(\x00+|\x01+|\x02+|\x03+)", state):
                if match.end() - match.start() < min_size:
                    continue
                a, b = s.start + match.start(), s.start + match.end()
                row = self.assess(a, b - a, kind=kind)
                row["left"] = self.neighbour(a - 1)
                row["right"] = self.neighbour(b)
                ranges.append(row)
        return {"schema": SCHEMA, "xbe_sha256": self.image.sha256, "model": MODEL,
                "reservation_model": "current patch stack" if self.manifest else "retail only; patch ownership not supplied",
                "kind": kind, "min_size": min_size, "range_filter": "all maximal verdict runs at least min_size; coverage counts include shorter runs",
                "budgets": {"instructions": self.instruction_budget, "references": self.reference_budget},
                "budget_exhausted": {"instructions": self._instruction_limit, "references": self._reference_limit},
                "instruction_count": self.instruction_count, "evidence_count": len(self.evidence),
                "reference_count": self.reference_count,
                "roots": self.roots, "unresolved_count": len(self.unknowns),
                "unresolved_by_kind": dict(Counter(e.kind for e in self.unknowns)),
                "unresolved_examples": [e.report() for e in list(self._unknown_kinds.values())[:20]],
                "absolute_writes": self.writes, "sections": sections, "ranges": ranges}


def absolute_writes(data: bytes, spans: Iterable[tuple[int, int]]) -> list[dict]:
    """Check operand access flags, all operands and full widths at supplied code boundaries.

    Spans must be complete instructions/code bodies, not byte-diff run starts.
    Invalid decoding is returned as unknown, never silently skipped.
    """
    image = XbeImage(data)
    cs, md = _capstone()
    from capstone.x86 import X86_OP_MEM
    findings = []
    for start, end in spans:
        data_slice = image.read(start, end - start)
        cursor = start
        for insn in md.disasm(data_slice, start):
            cursor = insn.address + insn.size
            for op in insn.operands:
                if op.type != X86_OP_MEM or not op.access & cs.CS_AC_WRITE:
                    continue
                m = op.mem
                absolute = m.base == m.index == m.segment == 0
                target, size = m.disp & 0xFFFFFFFF, max(1, op.size)
                findings.append({"instruction": hex(insn.address), "target": hex(target) if absolute else None,
                                 "size": size, "writable": image.runtime_writable(target, size) if absolute else None,
                                 "detail": f"{insn.mnemonic} {insn.op_str}"})
        if cursor != end:
            findings.append({"instruction": hex(cursor), "target": None, "size": end - cursor,
                             "writable": None, "detail": "undecoded trailing bytes"})
    return findings

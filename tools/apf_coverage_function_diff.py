#!/usr/bin/env python3
"""Offline, symbol-free comparison of APF's flat PPC PE memory images.

No executable bytes are emitted. Bounds come from .pdata, corroborated by a
PPC mflr-r12 prologue scan. Leaf gaps are reported separately, never silently
called unchanged. Normalized matches are evidence of instruction shape, not
proof of equivalent behavior: referenced code and data can still change.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import difflib
import hashlib
import json
from pathlib import Path
import struct


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Function:
    start: int
    size: int
    source: str = "pdata"


class Image:
    def __init__(self, data: bytes):
        self.data = data
        if len(data) < 0x100 or data[:2] != b"MZ":
            raise ValueError("expected a decompressed flat PE memory image")
        p = struct.unpack_from("<I", data, 0x3C)[0]
        if p + 0x78 > len(data) or data[p:p + 4] != b"PE\0\0":
            raise ValueError("invalid PE header")
        n, opt = struct.unpack_from("<H", data, p + 6)[0], struct.unpack_from("<H", data, p + 20)[0]
        self.base = struct.unpack_from("<I", data, p + 52)[0]
        self.sections = {}
        for i in range(n):
            o = p + 24 + opt + 40 * i
            if o + 40 > len(data):
                raise ValueError("truncated section table")
            name = data[o:o + 8].rstrip(b"\0").decode("ascii")
            size, rva, raw_size, raw_offset = struct.unpack_from("<IIII", data, o + 8)
            # XEX omits part of the discardable PE relocation section from
            # its memory payload. Only mapped sections used here must fit.
            if name in (".text", ".pdata", ".rdata", ".data") and rva + size > len(data):
                raise ValueError("section exceeds flat image")
            self.sections[name] = (self.base + rva, size)
        self.text, self.text_size = self.sections[".text"]

    def read(self, va: int, size: int) -> bytes:
        o = va - self.base
        if o < 0 or size < 0 or o + size > len(self.data):
            raise ValueError(f"flat address outside image: {va:#x}")
        return self.data[o:o + size]

    def word(self, va: int) -> int:
        return struct.unpack(">I", self.read(va, 4))[0]

    def functions(self) -> list[Function]:
        address, size = self.sections[".pdata"]
        if size % 8:
            raise ValueError(".pdata size is not a whole number of records")
        result = []
        for a in range(address, address + size, 8):
            start, packed = struct.unpack(">II", self.read(a, 8))
            length = ((packed >> 8) & 0x3FFFFF) * 4
            if not (length and start % 4 == 0 and self.text <= start < start + length <= self.text + self.text_size):
                raise ValueError(f"invalid .pdata record at {a:#x}")
            if result and result[-1].start + result[-1].size > start:
                raise ValueError("overlapping or unsorted .pdata functions")
            result.append(Function(start, length))
        return result

    def prologues(self) -> list[int]:
        return [a for a in range(self.text, self.text + self.text_size - 3, 4)
                if self.word(a) == 0x7D8802A6]  # mflr r12

    def normalized(self, f: Function) -> tuple[int, ...]:
        words = list(struct.unpack(f">{f.size // 4}I", self.read(f.start, f.size)))
        out = words.copy()
        for i, w in enumerate(words):
            a, op = f.start + i * 4, w >> 26
            # PPC switch tables are interleaved in .text and consist of
            # absolute branch destinations, not executable lwzu instructions.
            if self.text <= w < self.text + self.text_size and w % 4 == 0:
                out[i] = (0xF0000000 | (w - f.start)) if f.start <= w < f.start + f.size else 0xF1000000
                continue
            if op == 18:
                disp = w & 0x03FFFFFC
                if disp & 0x02000000:
                    disp -= 0x04000000
                target = (disp if w & 2 else a + disp) & 0xFFFFFFFF
                if not f.start <= target < f.start + f.size:
                    out[i] &= 0xFC000003
            if op == 15 and (w >> 16) & 31 == 0:
                hi, reg = (w & 0xFFFF) << 16, (w >> 21) & 31
                if not self.base <= hi <= self.base + len(self.data) + 0x10000:
                    continue
                for j in range(i + 1, len(words)):
                    z, q = words[j], words[j] >> 26
                    if (z >> 16) & 31 == reg and q in (14, 32, 34, 36, 38, 40, 42, 44, 48, 50, 52, 54):
                        low = z & 0xFFFF
                        target = (hi + (low - 0x10000 if low & 0x8000 else low)) & 0xFFFFFFFF
                        if self.base <= target < self.base + len(self.data):
                            out[i] &= 0xFFFF0000
                            out[j] &= 0xFFFF0000
                    if (z >> 21) & 31 == reg and q in (14, 15, 32, 34, 40, 42):
                        break
        # Also track high halves copied by mr (common in switch arms). This
        # is a signature heuristic, not a CFG proof or a behavior comparison.
        highs = {}
        for i, w in enumerate(words):
            op, rt, ra, rb = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
            if op == 15 and ra == 0:
                value = (w & 65535) << 16
                highs.pop(rt, None)
                if self.base <= value <= self.base + len(self.data) + 0x10000:
                    highs[rt] = (value, i)
            elif op == 31 and (w >> 1) & 1023 == 444 and rt == rb:  # mr ra,rt
                highs.pop(ra, None)
                if rt in highs:
                    highs[ra] = highs[rt]
            else:
                if op in (14, 32, 34, 36, 38, 40, 42, 44, 48, 50, 52, 54) and ra in highs:
                    hi, origin = highs[ra]
                    low = w & 65535
                    target = (hi + (low - 65536 if low & 32768 else low)) & 0xFFFFFFFF
                    if self.base <= target < self.base + len(self.data):
                        out[origin] &= 0xFFFF0000
                        out[i] &= 0xFFFF0000
                if op in (14, 32, 34, 40, 42):
                    highs.pop(rt, None)
        return tuple(out)


def compare(base: Image, tu: Image) -> dict:
    bf, tf = base.functions(), tu.functions()
    bn, tn = [base.normalized(f) for f in bf], [tu.normalized(f) for f in tf]
    def signature(words):
        return sha(struct.pack(f">{len(words)}I", *words))
    bs, ts = list(map(signature, bn)), list(map(signature, tn))
    bc, tc = Counter(bs), Counter(ts)
    matcher = difflib.SequenceMatcher(None, bs, ts, autojunk=False)
    pairs, unmatched_base, unmatched_tu = [], [], []
    for tag, i, j, k, l in matcher.get_opcodes():
        if tag == "equal":
            for x, y in zip(range(i, j), range(k, l)):
                pairs.append((x, y, "unique_normalized_signature" if bc[bs[x]] == tc[ts[y]] == 1 else "ordered_equal_signature", 1.0))
        else:
            # Small changed runs may include added/deleted functions. Align
            # their shapes monotonically between the exact-signature anchors.
            if (j - i) * (l - k) > 4096:
                unmatched_base.extend(range(i, j))
                unmatched_tu.extend(range(k, l))
                continue
            scores = {(x, y): difflib.SequenceMatcher(None, bn[x], tn[y], autojunk=False).ratio()
                      for x in range(i, j) for y in range(k, l)}
            dp = {(i, k): (0.0, [])}
            for x in range(i, j + 1):
                for y in range(k, l + 1):
                    if (x, y) == (i, k):
                        continue
                    options = []
                    if x > i:
                        options.append(dp[x - 1, y])
                    if y > k:
                        options.append(dp[x, y - 1])
                    if x > i and y > k and scores[x - 1, y - 1] >= 0.55:
                        old, path = dp[x - 1, y - 1]
                        options.append((old + scores[x - 1, y - 1] - 0.55,
                                        path + [(x - 1, y - 1)]))
                    dp[x, y] = max(options, key=lambda v: v[0])
            used = dp[j, l][1]
            pairs.extend((x, y, "ordered_between_signature_anchors", scores[x, y]) for x, y in used)
            unmatched_base.extend(x for x in range(i, j) if x not in {a for a, _ in used})
            unmatched_tu.extend(y for y in range(k, l) if y not in {b for _, b in used})
    rows = []
    for x, y, method, score in sorted(pairs):
        f, g = bf[x], tf[y]
        a, b = base.read(f.start, f.size), tu.read(g.start, g.size)
        kind = "identical" if a == b else "normalized_equal" if bn[x] == tn[y] else "normalized_different"
        rows.append({"base_va": f"0x{f.start:08x}", "tu_va": f"0x{g.start:08x}",
                     "base_size": f.size, "tu_size": g.size,
                     "base_file_offset": f.start - base.base, "tu_file_offset": g.start - tu.base,
                     "base_sha256": sha(a), "tu_sha256": sha(b), "comparison": kind,
                     "alignment": method, "alignment_grade": "B_INFERENCE", "shape_similarity": round(score, 6),
                     "classification": "UNKNOWN",
                     "changed_bytes_at_aligned_offsets": sum(v != w for v, w in zip(a, b)) + abs(len(a) - len(b))})
    def unresolved(indices, fs):
        return [{"va": f"0x{fs[i].start:08x}", "size": fs[i].size} for i in indices]
    def inventory(im, fs):
        ps = set(im.prologues())
        starts = {f.start for f in fs}
        return {"sha256": sha(im.data), "size": len(im.data), "pdata_functions": len(fs),
                "prologues": len(ps), "pdata_starts_with_prologue": len(starts & ps),
                "prologues_without_pdata": [f"0x{a:08x}" for a in sorted(ps - starts)],
                "text_bytes_outside_pdata": im.text_size - sum(f.size for f in fs)}
    by_base = {x: y for x, y, _, _ in pairs}
    gap_counts, gap_differences = Counter(), []
    for i in range(len(bf) - 1):
        start, end = bf[i].start + bf[i].size, bf[i + 1].start
        if start == end:
            continue
        if i not in by_base or by_base.get(i + 1) != by_base[i] + 1:
            gap_counts["unmatched"] += 1
            gap_differences.append({"base_va": f"0x{start:08x}", "base_size": end - start,
                                    "comparison": "unmatched", "classification": "UNKNOWN"})
            continue
        y = by_base[i]
        ts_, te = tf[y].start + tf[y].size, tf[y + 1].start
        a, b = base.read(start, end - start), tu.read(ts_, te - ts_)
        kind = "identical" if a == b else "normalized_equal" if (
            base.normalized(Function(start, end - start)) == tu.normalized(Function(ts_, te - ts_))) else "normalized_different"
        gap_counts[kind] += 1
        if kind != "identical":
            gap_differences.append({"base_va": f"0x{start:08x}", "tu_va": f"0x{ts_:08x}",
                                    "base_size": len(a), "tu_size": len(b), "base_sha256": sha(a), "tu_sha256": sha(b),
                                    "comparison": kind, "alignment_grade": "B_INFERENCE",
                                    "classification": "UNKNOWN", "kind": "gap_may_contain_leaves_and_padding"})
    return {"schema": "apf_coverage_function_diff/v1", "runtime_witnessed": False,
            "method": "flat mapping; pdata lengths; mflr-r12 corroboration; ordered normalized signatures",
            "limitations": ["Normalized equality does not prove equal referenced data or callees.",
                            "Normalization is a shape heuristic, not CFG dataflow; residual differences may be relocation-only.",
                            "Leaf functions and padding outside pdata appear as anchored gaps, not claimed function bounds.",
                            "Text before the first pdata function and after the last is not aligned by the gap pass.",
                            "All cross-image alignments are static inferences; unmatched functions remain UNKNOWN."],
            "base": inventory(base, bf), "tu": inventory(tu, tf),
            "counts": dict(Counter(r["comparison"] for r in rows)),
            "gap_counts": dict(gap_counts), "gap_differences": gap_differences,
            "unmatched_base": unresolved(unmatched_base, bf), "unmatched_tu": unresolved(unmatched_tu, tf),
            "functions": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-pe", type=Path, required=True)
    parser.add_argument("--tu-pe", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    report = compare(Image(args.base_pe.read_bytes()), Image(args.tu_pe.read_bytes()))
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": report["counts"], "unmatched_base": len(report["unmatched_base"]),
                      "unmatched_tu": len(report["unmatched_tu"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

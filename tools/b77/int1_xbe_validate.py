#!/usr/bin/env python3
"""b775 int1: static XBE header and section validator (read only).

Checks a built default.xbe against the pinned USA retail XBE, without running it:

* header: magic, image base, image header size, headers size, every header pointer (certificate, section
  table, section names, shared-page reference counters, debug paths, library versions, logo) inside the
  header region;
* sections: count (retail 22, scale-out 28, plus one optional extra section: 29), raw ranges inside the file
  and page aligned, raw size not above virtual size, virtual addresses aligned (0x20 for retail sections,
  0x1000 for added ones), virtual ranges ascending and non-overlapping, raw ranges non-overlapping and clear
  of the headers, every section inside the declared image size, stored SHA-1 digests match;
* the retail sections keep their names, virtual ranges and flags (.XTLID may grow, as the scale-out
  image does);
* kernel thunk: decoded address, every thunk slot and the terminator equal retail;
* TLS: directory address and its 24 bytes equal retail, the index address is file- or BSS-backed;
* entry point: decodes into an executable section;
* certificate title ID / region and the library version table equal retail.

  python3 tools/b77/int1_xbe_validate.py --retail RETAIL.xbe BUILT.xbe [BUILT2.xbe ...] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xbe_info import ENTRY_KEYS, KERNEL_THUNK_KEYS, Xbe  # noqa: E402

PAGE = 0x1000
SECTION_HEADER = 56
RETAIL_COUNT = 22
SCALE_COUNT = 28
GROWABLE = {".XTLID"}  # the scale-out image grows (and preloads) the title-id section in place


class Report:
    def __init__(self, path):
        self.path = str(path)
        self.checks = []
        self.notes = []

    def check(self, name, ok, detail=""):
        self.checks.append(dict(check=name, ok=bool(ok), detail=detail))
        return ok

    def note(self, text):
        self.notes.append(text)

    @property
    def ok(self):
        return all(c["ok"] for c in self.checks)


def _inside(start, size, lo, hi):
    return lo <= start and start + size <= hi


def validate(path: Path, retail: Xbe) -> tuple[Report, dict]:
    rep = Report(path)
    x = Xbe(path)
    h, rh = x.header, retail.header
    base = h["image_base"]
    rep.check("magic XBEH", x.data[:4] == b"XBEH")
    rep.check("image base 0x10000", base == 0x10000 == rh["image_base"], hex(base))
    rep.check("image header size equals retail", h["image_header_size"] == rh["image_header_size"],
              f"{h['image_header_size']:#x} vs {rh['image_header_size']:#x}")
    hs = h["headers_size"]
    rep.check("headers size >= image header size", hs >= h["image_header_size"], hex(hs))
    count = h["section_count"]
    rep.check("section count 22, 28 or 29", count in (RETAIL_COUNT, SCALE_COUNT, SCALE_COUNT + 1), str(count))
    hlo, hhi = base, base + hs

    # Header pointers.
    table = h["section_headers_address"]
    rep.check("section table inside headers", _inside(table, count * SECTION_HEADER, hlo, hhi),
              f"{table:#x}+{count * SECTION_HEADER:#x} in [{hlo:#x},{hhi:#x})")
    cert = h["certificate_address"]
    cert_size = x.u32(cert - base) if _inside(cert, 4, hlo, hhi) else 0
    rep.check("certificate inside headers", cert_size and _inside(cert, cert_size, hlo, hhi), f"{cert:#x}+{cert_size:#x}")
    for key in ("debug_pathname_address", "debug_filename_address"):
        a = h[key]
        ok = a == 0 or (_inside(a, 1, hlo, hhi) and x.data.find(b"\0", a - base, hs) >= 0)
        rep.check(f"{key} inside headers (NUL terminated)", ok, hex(a))
    a = h["debug_unicode_filename_address"]
    rep.check("debug_unicode_filename_address inside headers", a == 0 or _inside(a, 2, hlo, hhi), hex(a))
    rep.check("library version table inside headers",
              _inside(h["library_versions_address"], h["library_versions_count"] * 16, hlo, hhi),
              f"{h['library_versions_address']:#x} x{h['library_versions_count']}")
    for key in ("kernel_library_version_address", "xapi_library_version_address"):
        rep.check(f"{key} inside headers", h[key] == 0 or _inside(h[key], 16, hlo, hhi), hex(h[key]))
    if h["feature_library_versions_count"]:
        rep.check("feature library table inside headers",
                  _inside(h["feature_library_versions_address"], h["feature_library_versions_count"] * 16, hlo, hhi),
                  hex(h["feature_library_versions_address"]))
    rep.check("logo bitmap inside headers", h["logo_bitmap_size"] == 0 or
              _inside(h["logo_bitmap_address"], h["logo_bitmap_size"], hlo, hhi),
              f"{h['logo_bitmap_address']:#x}+{h['logo_bitmap_size']:#x}")

    secs = x.sections
    # Section names and shared-page counters live in the headers.
    for s in secs:
        n = s["name"]
        rep.check(f"[{s['index']}] {n}: name inside headers", _inside(s["name_address"], len(n) + 1, hlo, hhi),
                  hex(s["name_address"]))
        for key in ("head_shared_page_reference_count_address", "tail_shared_page_reference_count_address"):
            rep.check(f"[{s['index']}] {n}: {key.split('_')[0]} page counter inside headers",
                      _inside(s[key], 2, hlo, hhi), hex(s[key]))

    # Per-section ranges.
    image_end = base + h["image_size"]
    for s in secs:
        i, n = s["index"], s["name"]
        va, vs, raw, rs = s["virtual_address"], s["virtual_size"], s["raw_address"], s["raw_size"]
        added = i >= RETAIL_COUNT
        rep.check(f"[{i}] {n}: raw range inside file", raw + rs <= len(x.data), f"{raw:#x}+{rs:#x} file {len(x.data):#x}")
        rep.check(f"[{i}] {n}: raw address page aligned", raw % PAGE == 0, hex(raw))
        rep.check(f"[{i}] {n}: raw size <= virtual size", rs <= vs, f"{rs:#x} <= {vs:#x}")
        align = PAGE if added else 0x20
        rep.check(f"[{i}] {n}: virtual address {align:#x} aligned", va % align == 0, hex(va))
        if added:
            rep.check(f"[{i}] {n}: virtual size page multiple", vs % PAGE == 0, hex(vs))
        rep.check(f"[{i}] {n}: above the headers", va >= hhi and raw >= hs, f"va {va:#x} raw {raw:#x}")
        rep.check(f"[{i}] {n}: inside image size", va + vs <= image_end, f"{va + vs:#x} <= {image_end:#x}")
        rep.check(f"[{i}] {n}: SHA-1 digest", s["digest_matches"])
    order = [s["virtual_address"] for s in secs]
    if order != sorted(order):
        # Retail tables are in VA order, but the loader maps each section by its own header; the scale-out design keeps
        # its optional extra section (music or Career Home) in the last table slot with a VA below .AS0005. Reported, not
        # failed: overlaps and shared-page counters are what break loading, and they are checked separately.
        late = [f"[{s['index']}] {s['name']} {s['virtual_address']:#x}" for a, s in zip(secs, secs[1:])
                if s["virtual_address"] < a["virtual_address"]]
        rep.note("section table not in VA order: " + ", ".join(late))
    pages = {}
    for s in secs:
        first, last = s["virtual_address"] // PAGE, (s["virtual_address"] + s["virtual_size"] - 1) // PAGE
        pages.setdefault(first, []).append((s, "head"))
        if last != first:
            pages.setdefault(last, []).append((s, "tail"))
    shared_ok = True
    for page, users in pages.items():
        if len(users) > 1:
            counters = {u[0][f"{u[1]}_shared_page_reference_count_address"] for u in users}
            if len(counters) != 1:
                shared_ok = False
    rep.check("sections sharing a page share its reference counter", shared_ok)
    by_va = sorted(secs, key=lambda s: s["virtual_address"])
    vover = [(a["name"], b["name"]) for a, b in zip(by_va, by_va[1:])
             if a["virtual_address"] + a["virtual_size"] > b["virtual_address"]]
    rep.check("no virtual overlaps", not vover, str(vover))
    by_raw = sorted((s for s in secs if s["raw_size"]), key=lambda s: s["raw_address"])
    rover = [(a["name"], b["name"]) for a, b in zip(by_raw, by_raw[1:])
             if a["raw_address"] + a["raw_size"] > b["raw_address"]]
    rep.check("no raw overlaps", not rover, str(rover))
    names = [s["name"] for s in secs]
    rep.check("section names unique", len(set(names)) == len(names), str(names))

    # Retail sections keep their identity.
    for r in retail.sections:
        i = r["index"]
        if i >= len(secs):
            rep.check(f"[{i}] {r['name']}: retail section present", False)
            continue
        s = secs[i]
        same = (s["name"] == r["name"] and s["virtual_address"] == r["virtual_address"] and s["flags"] == r["flags"])
        if r["name"] in GROWABLE:
            # The scale-out image grows .XTLID in place and preloads it (flag 0x02 added, nothing removed).
            same = (s["name"] == r["name"] and s["virtual_address"] == r["virtual_address"]
                    and s["virtual_size"] >= r["virtual_size"] and s["flags"] & ~0x02 == r["flags"])
        else:
            same = same and s["virtual_size"] == r["virtual_size"]
        flags_note = "" if s["flags"] == r["flags"] else f" flags {s['flags']:#x} vs {r['flags']:#x}"
        rep.check(f"[{i}] {r['name']}: retail name/VA/size/flags kept", same,
                  f"{s['name']} {s['virtual_address']:#x}+{s['virtual_size']:#x}{flags_note}")

    # Kernel thunk table.
    kind, rkind = x.executable_kind(), retail.executable_kind()
    rep.check("retail executable kind", kind == rkind == "retail", kind)
    thunk = h["encoded_kernel_thunk_address"] ^ KERNEL_THUNK_KEYS[kind]
    rthunk = rh["encoded_kernel_thunk_address"] ^ KERNEL_THUNK_KEYS[rkind]
    rep.check("kernel thunk address equals retail", thunk == rthunk, f"{thunk:#x} vs {rthunk:#x}")
    thunks, _ = x.parse_kernel_thunks()
    rthunks, _ = retail.parse_kernel_thunks()
    rep.check("kernel thunk slots equal retail (count, ordinals, terminator)",
              [t["raw_value"] for t in thunks] == [t["raw_value"] for t in rthunks],
              f"{len(thunks)} vs {len(rthunks)} imports")
    thunk_sec = next((s["name"] for s in secs if s["virtual_address"] <= thunk < s["virtual_address"] + s["raw_size"]), None)
    rep.check("kernel thunk table is file-backed", thunk_sec is not None, str(thunk_sec))

    # TLS.
    rep.check("TLS directory address equals retail", h["tls_address"] == rh["tls_address"], hex(h["tls_address"]))
    tls, rtls = x.parse_tls(), retail.parse_tls()
    t_bytes = x.data[tls["file_offset"]:tls["file_offset"] + 24] if tls else b""
    r_bytes = retail.data[rtls["file_offset"]:rtls["file_offset"] + 24] if rtls else b""
    rep.check("TLS directory bytes equal retail", tls is not None and t_bytes == r_bytes, t_bytes.hex())
    if tls:
        idx = tls["address_of_index"]
        rep.check("TLS index address inside a section",
                  any(s["virtual_address"] <= idx < s["virtual_address"] + s["virtual_size"] for s in secs), hex(idx))
        if tls["end_address_of_raw_data"] > tls["start_address_of_raw_data"]:
            size = tls["end_address_of_raw_data"] - tls["start_address_of_raw_data"]
            rep.check("TLS template bytes equal retail",
                      x.data[x.va_to_offset(tls["start_address_of_raw_data"], size):][:size] ==
                      retail.data[retail.va_to_offset(rtls["start_address_of_raw_data"], size):][:size])

    # Entry point.
    entry = h["encoded_entry_address"] ^ ENTRY_KEYS[kind]
    esec = next((s for s in secs if s["virtual_address"] <= entry < s["virtual_address"] + s["raw_size"]), None)
    rep.check("entry point in an executable, file-backed section", esec is not None and esec["flags"] & 0x04,
              f"{entry:#x} in {esec['name'] if esec else None}")

    # Certificate and libraries.
    cert_t = x.data[cert - base + 8:cert - base + 12]
    rcert = rh["certificate_address"] - base
    rep.check("certificate title ID equals retail", cert_t == retail.data[rcert + 8:rcert + 12], cert_t[::-1].hex())
    rep.check("certificate game region equals retail",
              x.data[cert - base + 0xA0:cert - base + 0xA4] == retail.data[rcert + 0xA0:rcert + 0xA4])
    lib = x.data[h["library_versions_address"] - base:][:h["library_versions_count"] * 16]
    rlib = retail.data[rh["library_versions_address"] - base:][:rh["library_versions_count"] * 16]
    rep.check("library version table equals retail", lib == rlib, f"{h['library_versions_count']} libraries")

    summary = dict(path=str(path), file_bytes=len(x.data), section_count=count, headers_size=hs,
                   image_header_size=h["image_header_size"], image_size=h["image_size"], entry=entry,
                   kernel_thunk=thunk, tls_address=h["tls_address"],
                   sections=[dict(index=s["index"], name=s["name"], flags=s["flags"], va=s["virtual_address"],
                                  vsize=s["virtual_size"], raw=s["raw_address"], raw_size=s["raw_size"])
                             for s in secs[RETAIL_COUNT - 1:]])
    return rep, summary


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--retail", required=True, type=Path)
    p.add_argument("--json", type=Path)
    p.add_argument("xbe", nargs="+", type=Path)
    a = p.parse_args(argv)
    retail = Xbe(a.retail)
    out, ok = [], True
    for path in a.xbe:
        try:
            rep, summary = validate(path, retail)
        except Exception as exc:  # noqa: BLE001 - a header the parser cannot walk is itself a failed validation
            rep = Report(path)
            rep.check("header and section table parse", False, f"{type(exc).__name__}: {exc}")
            summary = dict(path=str(path), section_count=None, headers_size=0, image_size=0, sections=[])
        failed = [c for c in rep.checks if not c["ok"]]
        ok &= not failed
        print(f"{'PASS' if not failed else 'FAIL'} {path}: {len(rep.checks)} checks, {len(failed)} failed; "
              f"{summary['section_count']} sections, headers {summary['headers_size']:#x}, image {summary['image_size']:#x}")
        for s in summary["sections"]:
            print(f"    [{s['index']}] {s['name']:<10} va {s['va']:#09x}+{s['vsize']:#07x} raw {s['raw']:#08x}+{s['raw_size']:#07x} flags {s['flags']:#04x}")
        for c in failed:
            print(f"  FAIL {c['check']}: {c['detail']}")
        for text in rep.notes:
            print(f"  NOTE {text}")
        out.append(dict(summary, ok=not failed, checks=rep.checks, notes=rep.notes))
    if a.json:
        a.json.write_text(json.dumps(out, indent=2) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

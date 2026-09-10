#!/usr/bin/env python3
"""Extract a hash-verified default.xexp from a bounded, single-table LIVE STFS.

Retail payload outputs MUST be outside the checkout. This reader deliberately
supports only a root-level, consecutive default.xexp and a one-block directory,
with at most two hash-tree levels. It checks SHA-1 integrity, not RSA signatures.
Use apf_coverage_tu_apply.cpp plus local XenonUtils for the XEX delta stage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

BLOCK = 4096
FANOUT = 170
END = 0xFFFFFF
TU_SHA256 = "5f71cdf4ec679f8e33fd95e02ff2b67981fbf918d4d03a2099576734c5cfb42b"
XEXP_SHA256 = "14e272063536656d2aae9b4743fdcebb927566722dc1e2f34fe75029e1e8ada6"
BASE_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
TU_PE_SHA256 = "65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457"


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def extract(data: bytes) -> tuple[bytes, dict]:
    """Parse an in-memory package. Synthetic packages exercise this same path."""
    def take(o: int, n: int) -> bytes:
        require(o >= 0 and n >= 0 and o + n <= len(data), "truncated STFS range")
        return data[o:o + n]

    def be32(o):
        return int.from_bytes(take(o, 4), "big")

    require(0xB000 <= len(data) <= 128 * 1024 * 1024, "unsupported LIVE size")
    require(take(0, 4) == b"LIVE", "expected LIVE STFS")
    header_size = be32(0x340)
    header = (header_size + BLOCK - 1) & -BLOCK
    require(0x971A <= header_size <= len(data), "invalid LIVE header size")
    require(hashlib.sha1(take(0x344, header - 0x344)).digest() == take(0x32C, 20),
            "metadata SHA-1 mismatch")
    require(be32(0x3A9) == 0 and take(0x379, 1) == b"\x24", "unsupported filesystem descriptor")
    require(take(0x37B, 1) == b"\x01", "only single-table STFS is supported")
    require(int.from_bytes(take(0x37C, 2), "little") == 1, "only one directory block is supported")
    first = int.from_bytes(take(0x37E, 3), "little")
    allocated = be32(0x395)
    require(1 <= allocated <= FANOUT ** 2, "unsupported STFS hash-tree depth")
    require(first < allocated, "directory block is unallocated")
    top_level = int(allocated > FANOUT)
    top_offset = header + (FANOUT + 1) * BLOCK if top_level else header
    top = take(top_offset, BLOCK)
    require(hashlib.sha1(top).digest() == take(0x381, 20), "top-table SHA-1 mismatch")
    cache, verified = {}, set()

    def backing(block):
        return block + block // FANOUT + 1 + int(block >= FANOUT)

    def read_block(block):
        require(0 <= block < allocated, "data block is unallocated")
        group = block // FANOUT
        if group not in cache:
            if not top_level:
                table = top
            else:
                # Parent status byte is an active-copy selector, NOT a data
                # allocation flag. This LIVE has valid zero-status parents.
                parent = top[group * 24:group * 24 + 24]
                require(not parent[20] & 0x40, "alternate hash copy in single-table layout")
                address = header + (group * (FANOUT + 1) + int(group > 0)) * BLOCK
                table = take(address, BLOCK)
                require(hashlib.sha1(table).digest() == parent[:20], "level-zero SHA-1 mismatch")
            cache[group] = table
        entry = cache[group][block % FANOUT * 24:block % FANOUT * 24 + 24]
        require(bool(entry[20] & 0x80), "data block allocation flag missing")
        payload = take(header + backing(block) * BLOCK, BLOCK)
        require(hashlib.sha1(payload).digest() == entry[:20], "data-block SHA-1 mismatch")
        verified.add(block)
        return payload, int.from_bytes(entry[21:24], "big")

    directory, next_block = read_block(first)
    require(next_block == END, "directory chain has extra blocks")
    entries = []
    for i in range(64):
        row = directory[i * 64:(i + 1) * 64]
        length, flags = row[0x28] & 63, row[0x28] >> 6
        if not length:
            continue
        require(length <= 40, "invalid directory name length")
        name = row[:length]
        require(name == b"default.xexp" and flags == 1, "unexpected LIVE directory entry")
        require(int.from_bytes(row[0x32:0x34], "big") == 0xFFFF, "nested XEXP is unsupported")
        count = int.from_bytes(row[0x29:0x2C], "little")
        require(count == int.from_bytes(row[0x2C:0x2F], "little"), "duplicate block counts disagree")
        start = int.from_bytes(row[0x2F:0x32], "little")
        size = int.from_bytes(row[0x34:0x38], "big")
        require(size > 0 and count == (size + BLOCK - 1) // BLOCK, "file size/block count mismatch")
        require(start + count <= allocated and not start <= first < start + count, "invalid XEXP extent")
        entries.append((i, start, count, size))
    require(len(entries) == 1, "expected exactly one default.xexp")
    index, start, count, size = entries[0]
    # The directory's consecutive flag is authoritative for extent traversal;
    # hash-entry next pointers need not describe a consecutive file's chain.
    payload = b"".join(read_block(i)[0] for i in range(start, start + count))[:size]
    receipt = {"schema": "apf_coverage_tu_extract/v1", "package_sha256": hashlib.sha256(data).hexdigest(),
               "package_size": len(data), "header_size": header_size, "first_hash_offset": header,
               "top_level": top_level, "top_hash_offset": top_offset, "allocated_blocks": allocated,
               "directory_index": index, "file_start_block": start, "file_blocks": count,
               "payload_size": size, "payload_sha256": hashlib.sha256(payload).hexdigest(),
               "verified_data_blocks_including_directory": len(verified), "verified_level_zero_tables": len(cache),
               "metadata_sha1_verified": True, "hash_tree_verified": True, "rsa_verified": False}
    return payload, receipt


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tu", type=Path, required=True)
    p.add_argument("--xexp-out", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--base-xex", type=Path)
    p.add_argument("--delta-helper", type=Path)
    p.add_argument("--pe-out", type=Path)
    p.add_argument("--header-out", type=Path)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    require(not a.xexp_out.resolve().is_relative_to(root), "retail payload output must be outside the checkout")
    require(a.xexp_out.resolve() != a.tu.resolve(), "cannot overwrite retail input")
    require(not a.xexp_out.exists(), "payload output already exists")
    require(a.receipt.resolve() not in (a.tu.resolve(), a.xexp_out.resolve()), "receipt path overlaps binary input/output")
    reconstruction = (a.base_xex, a.delta_helper, a.pe_out, a.header_out)
    if any(reconstruction):
        require(all(reconstruction), "reconstruction requires base-xex, delta-helper, pe-out and header-out")
        outputs = (a.xexp_out, a.pe_out, a.header_out)
        paths = [p.resolve() for p in outputs] + [a.receipt.resolve()]
        require(len(set(paths)) == len(paths), "output paths overlap")
        for path in outputs:
            require(not path.exists() and not path.resolve().is_relative_to(root), "binary output must be fresh and outside checkout")
        require(a.receipt.resolve() not in (a.base_xex.resolve(), a.delta_helper.resolve()), "receipt overlaps reconstruction input")
        require(hashlib.sha256(a.base_xex.read_bytes()).hexdigest() == BASE_XEX_SHA256, "unsupported base XEX SHA-256")
    raw = a.tu.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == TU_SHA256, "unsupported TU SHA-256")
    payload, receipt = extract(raw)
    require(receipt["payload_sha256"] == XEXP_SHA256, "extracted XEXP pin mismatch")
    with a.xexp_out.open("xb") as f:
        f.write(payload)
    # Re-read the on-disk extraction before emitting the small derived receipt.
    require(hashlib.sha256(a.xexp_out.read_bytes()).hexdigest() == XEXP_SHA256, "written XEXP failed verification")
    if all(reconstruction):
        run = subprocess.run([str(a.delta_helper.resolve()), str(a.base_xex), str(a.xexp_out),
                              str(a.pe_out), str(a.header_out)], check=True, capture_output=True, text=True)
        require(hashlib.sha256(a.pe_out.read_bytes()).hexdigest() == TU_PE_SHA256, "reconstructed PE SHA-256 mismatch")
        receipt["reconstruction"] = {"base_xex_sha256": BASE_XEX_SHA256, "tu_pe_sha256": TU_PE_SHA256,
                                     "tu_pe_size": a.pe_out.stat().st_size,
                                     "header_sha256": hashlib.sha256(a.header_out.read_bytes()).hexdigest(),
                                     "helper_sha256": hashlib.sha256(a.delta_helper.read_bytes()).hexdigest(),
                                     "helper_result": run.stdout.strip()}
    a.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

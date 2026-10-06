"""Prepare the opt-in league art and repair missing native midfield overlays.

Never opens a disc. Pins DEN/MIA field spans and PIT's contiguous field-detail
prefix, allowing independent stadium repairs to compose. Existing midfield
fields remain byte-identical; PIT's detail pixels remain lossless.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_midfield_art as midfield
from mod_editor.core import nfl2k5_modern_metlife as ml
from mod_editor.core import nfl2k5_modern_venues_2026 as mv

TEAMS = {"s08": "DEN", "s14": "MIA", "s22": "PIT"}
SCHEMA = "b765_s2_missing_midfield/v2"
PINS = Path(__file__).with_name("s2_midfield_pins.json")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare_art(source, output):
    """Copy the complete league root and change only three selected manifests."""
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output:
        raise ValueError("Art preparation requires a separate output folder")
    if source in output.parents:
        raise ValueError("Art output must be outside the source folder")
    if output.exists():
        raise ValueError("Art output already exists; choose a new folder")
    shutil.copytree(source, output)
    changed = []
    for team in TEAMS.values():
        path = output / team / "venue" / "manifest.json"
        path.chmod(0o644)
        doc = json.loads(path.read_text())
        doc["add_missing_midfield"] = True
        path.write_text(json.dumps(doc, indent=2) + "\n", newline="\n")
        changed.append(str(path.relative_to(output)))
    scope = []
    for path in sorted(p for p in source.rglob("*") if p.is_file()):
        rel = path.relative_to(source)
        before, after = path.read_bytes(), (output / rel).read_bytes()
        if str(rel) not in changed and before != after:
            raise ValueError("Art outside three selected manifests changed: " + str(rel))
        scope.append(dict(file=str(rel), before_sha256=sha(before), after_sha256=sha(after), unchanged=before == after))
    output.chmod(0o755)
    (output / "midfield_source_scope.json").write_text(json.dumps(dict(changed_manifests=changed, files=scope), indent=2) + "\n", newline="\n")
    mv.load_art(output)
    return output


def logos(art_root):
    art = mv.load_art(art_root)
    result = {}
    for prefix in TEAMS:
        venue = art["venues"].get(prefix)
        if not venue or not venue.get("add_missing_midfield"):
            raise ValueError(f"{prefix}: source manifest must enable add_missing_midfield")
        item = next(i for i in venue["items"] if i["scene"] == "field" and i["key"] == "center_logo")
        result[prefix] = mv._art_at(item, 256, 256)
    return result


def owned_scope(data, name):
    if name[:3] == midfield.LOAN_PREFIX:
        _field, _layer, normal, _decoded = midfield.pit_sites(data)
        return 0, normal.end_offset, "field_detail_prefix"
    chunk = ml.bundle_scenes(data)["field"]
    return chunk.offset, len(ml.scene_span(data, chunk)), "field"


def transform(data, name, logo):
    if name[:3] == midfield.LOAN_PREFIX:
        return midfield.append_pit_bundle(data, name, logo)
    chunk = ml.bundle_scenes(data)["field"]
    before = ml.scene_span(data, chunk)
    after, receipt = midfield.append_span(before, name, logo)
    end = chunk.offset + len(before)
    return data[:chunk.offset] + after + data[end:], receipt


def repair_bundle(data, name, logo, pins):
    pin = pins["bundles"].get(name)
    if pin is None:
        raise ValueError("Unowned missing-midfield resource: " + name)
    if sha(logo.tobytes()) != pins["logo_rgba_sha256"][name[:3]]:
        raise ValueError("Unexpected midfield source pixels: " + name)
    at, size, kind = owned_scope(data, name)
    if pin.get("scope_kind") != kind:
        raise ValueError("Unexpected midpoint scope kind: " + name)
    before = data[at:at + size]
    digest = sha(before)
    if digest == pin["after_sha256"]:
        return data, dict(name=name, already_applied=True, before_sha256=sha(data), after_sha256=sha(data))
    if digest != pin["before_sha256"]:
        raise ValueError("Unexpected native field hash: " + name)
    result, receipt = transform(data, name, logo)
    after = result[at:at + size]
    if sha(after) != pin["after_sha256"]:
        raise ValueError("Midfield output differs from the deterministic pin: " + name)
    end = at + size
    assert len(result) == len(data) and result[:at] == data[:at] and result[end:] == data[end:]
    return result, {**receipt, "name": name, "before_sha256": sha(data), "after_sha256": sha(result),
                    "field_before_sha256": digest, "field_after_sha256": sha(after),
                    "scope_kind": kind, "scope_offset": at, "scope_size": size,
                    "outside_field_sha256": sha(data[:at] + data[end:]), "outside_field_identical": True}


def pin_fields(input_dir, art_root):
    arrays = logos(art_root)
    doc = dict(schema=SCHEMA, logo_rgba_sha256={p: sha(a.tobytes()) for p, a in arrays.items()}, bundles={})
    for prefix in TEAMS:
        for code in ("dd", "dr", "ds") if prefix == "s14" else mv.CODES:
            name = prefix + code + ".iff"
            data = (Path(input_dir) / name).read_bytes()
            at, size, kind = owned_scope(data, name)
            after, receipt = transform(data, name, arrays[prefix])
            doc["bundles"][name] = dict(scope_kind=kind, before_sha256=sha(data[at:at + size]),
                                        after_sha256=sha(after[at:at + size]), receipt=receipt)
            print(name, receipt["encoder"], "scratch", receipt["alias_scratch"], "/", receipt["scratch"], flush=True)
    return doc


def prove_native_decoder(input_dir, xbe):
    """Execute retail FUN_0004dc00 offline on the nine pinned PIT field maps."""
    import struct
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
    from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP, UC_X86_REG_EAX
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
    executable = Path(xbe).read_bytes()
    if sha(executable) != RETAIL_SHA256:
        raise ValueError("Native decoder proof needs the recognized retail XBE")
    code = XbeImage(executable).read(0x4D000, 0x2000)
    pins = json.loads(PINS.read_text())
    tx = ml._tools()[0]
    rows = []
    for name in sorted(n for n in pins["bundles"] if n.startswith("s22")):
        data = (Path(input_dir) / name).read_bytes()
        field, _layer, normal, _normal_data = midfield.pit_sites(data)
        if sha(data[:normal.end_offset]) != pins["bundles"][name]["after_sha256"]:
            raise ValueError("Native decoder proof needs a frozen repaired PIT prefix: " + name)
        for kind, chunk in (("field", field), ("detail_normal", normal)):
            decoded, _ = tx.decode_chunk(data, chunk)
            body = data[chunk.body_offset:chunk.end_offset]
            base, stack, stop = 0x10000000, 0x20000000, 0x30000000
            uc = Uc(UC_ARCH_X86, UC_MODE_32)
            uc.mem_map(0x4D000, 0x2000)
            uc.mem_write(0x4D000, code)
            allocation = len(decoded) + chunk.overlap_scratch_bytes
            mapped = (allocation + 4095 + 4096) & ~4095
            uc.mem_map(base, mapped)
            uc.mem_map(stack, 0x10000)
            uc.mem_map(stop, 0x1000)
            uc.mem_write(stop, b"\xf4")
            uc.mem_write(base, bytes([0xCC]) * allocation)
            source = base + allocation - len(body)
            uc.mem_write(source, body)
            uc.mem_write(base + allocation, bytes([0xA5]) * 128)
            sp = stack + 0x8000
            uc.mem_write(sp, struct.pack("<I", stop))
            uc.reg_write(UC_X86_REG_ESP, sp)
            uc.reg_write(UC_X86_REG_ECX, source)
            uc.reg_write(UC_X86_REG_EDX, base)
            access = dict(max_read=0, max_write=0)
            def read_hook(_uc, _type, address, size, _value, _user):
                if base <= address < base + mapped:
                    access["max_read"] = max(access["max_read"], address + size - base)
            def write_hook(_uc, _type, address, size, _value, _user):
                if base <= address < base + mapped:
                    access["max_write"] = max(access["max_write"], address + size - base)
            uc.hook_add(UC_HOOK_MEM_READ, read_hook)
            uc.hook_add(UC_HOOK_MEM_WRITE, write_hook)
            uc.emu_start(0x4DC00, stop, count=20_000_000)
            if (bytes(uc.mem_read(base, len(decoded))) != decoded
                    or bytes(uc.mem_read(base + allocation, 128)) != bytes([0xA5]) * 128
                    or access["max_read"] > allocation or access["max_write"] > len(decoded)
                    or uc.reg_read(UC_X86_REG_EAX) != len(decoded)):
                raise ValueError("Native in-place decoder or allocation guard differs: " + name + " " + kind)
            rows.append(dict(name=name, kind=kind, scratch=chunk.overlap_scratch_bytes,
                             decoded_bytes=len(decoded), stored_bytes=len(body),
                             offset_bits=body[8], exact_native_output=True,
                             guard_unchanged=True, **access))
    return dict(xbe_sha256=sha(executable), native_entry="0x4dc00", chunks=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare-art")
    prepare.add_argument("--source", required=True)
    prepare.add_argument("--output", required=True)
    pin = sub.add_parser("pin", help="Developer-only derivation; review pins before shipping")
    pin.add_argument("--input", required=True)
    pin.add_argument("--art-root", required=True)
    pin.add_argument("--pins", required=True)
    repair = sub.add_parser("repair")
    repair.add_argument("--input", required=True)
    repair.add_argument("--output", required=True)
    repair.add_argument("--art-root", required=True)
    repair.add_argument("--receipt", required=True)
    proof = sub.add_parser("prove-decoder", help="Run the actual retail decoder offline on frozen PIT outputs")
    proof.add_argument("--input", required=True)
    proof.add_argument("--xbe", required=True)
    proof.add_argument("--receipt", required=True)
    args = parser.parse_args()
    if args.command == "prepare-art":
        prepare_art(args.source, args.output)
    elif args.command == "pin":
        Path(args.pins).write_text(json.dumps(pin_fields(args.input, args.art_root), indent=2) + "\n", newline="\n")
    elif args.command == "prove-decoder":
        Path(args.receipt).write_text(json.dumps(prove_native_decoder(args.input, args.xbe), indent=2) + "\n", newline="\n")
    else:
        if Path(args.input).resolve() == Path(args.output).resolve():
            raise ValueError("Repair input and output must be separate folders")
        doc = json.loads(PINS.read_text())
        if doc.get("schema") != SCHEMA:
            raise ValueError("Unexpected missing-midfield pin schema")
        expected = {p + c + ".iff" for p in TEAMS for c in (("dd", "dr", "ds") if p == "s14" else mv.CODES)}
        if set(doc["bundles"]) != expected:
            raise ValueError("Unexpected missing-midfield resource set")
        arrays = logos(args.art_root)
        destination = Path(args.output)
        destination.mkdir(parents=True, exist_ok=True)
        receipts = []
        for name in sorted(doc["bundles"]):
            data = (Path(args.input) / name).read_bytes()
            result, receipt = repair_bundle(data, name, arrays[name[:3]], doc)
            output_file = destination / name
            if output_file.exists() and output_file.read_bytes() != result:
                raise ValueError("Refusing to overwrite a differing output: " + str(output_file))
            if not output_file.exists():
                output_file.write_bytes(result)
            receipts.append(receipt)
            print(name, "unchanged" if result == data else "fixed", flush=True)
        Path(args.receipt).write_text(json.dumps(dict(schema=SCHEMA, bundles=receipts), indent=2) + "\n", newline="\n")


if __name__ == "__main__":
    main()

"""Synthetic metadata and packages for the real backend CLI; no retail bytes.

Only retail identity constants/target metadata are substituted in the child.
Archive parsing, PNG encoders, adapter loader, staging, copy, union verification
and receipt publication are the production implementation.
"""
from dataclasses import asdict, replace
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests")]
from nfl_txtr import HEADER, compress_vc_lz, decode_chunk, parse_chunks
from nfl_jersey_tset_targets import JerseyTarget
from nfl_uniform_inventory import uniform_name_id
from nfl2k5_commentary_swap_test import _dir_node
from tests.mod_editor.test_nfl2k5_equipment_texture_chain import Fixture


def sha(data):
    return hashlib.sha256(data).hexdigest()


def create(root):
    equipment = Fixture(root, family=8)
    system = bytearray(256)
    struct.pack_into("<II", system, 0, 13, 2)
    for base, name_at, desc, name, palette in ((24, 84, 128, "jersey00", 174720),
                                               (60, 102, 160, "jersey00_mud", 175744)):
        system[base:base+4] = b"TXTR"
        for field, target in ((base+4, name_at), (base+8, desc), (base+20, 0)):
            struct.pack_into("<i", system, field, target-field+1)
        encoded = (name + "\0").encode("utf-16le")
        system[name_at:name_at+len(encoded)] = encoded
        struct.pack_into("<6I", system, desc, 0, 0, palette, 0x08960b29, 0, 0x80000000)
    decoded = bytes(system) + bytes(174720) + bytes((0, 0, 0, 255))*512
    compressed, _ = compress_vc_lz(decoded, stream_tag=1, offset_bits=12)
    stored = (len(compressed)+8192+15) & ~15
    jersey = HEADER.pack(b"TSET", stored, 256, 176768, 0xFEEDBEEF, stored, 0, 0)
    jersey += compressed + bytes(stored-len(compressed))
    dummy = HEADER.pack(b"TEST", 32, 32, 0, 0, 0, 0, 0) + bytes(32)
    package = dummy + jersey + dummy*6 + equipment.span
    pack = bytearray((2048+len(package)+2047)//2048*2048)
    outer_size = len(pack) - 2048
    name_id = uniform_name_id("18H0.IFF")
    struct.pack_into("<4I", pack, 0, 1, 0, 1, len(pack)//2048)
    struct.pack_into("<III", pack, 156, name_id, outer_size, 1)
    pack[2048:2048+len(package)] = package
    (root / "0").write_bytes(pack)
    inventory = dict(schema="nfl2k5_resource_chunk_inventory/v1", chunks=[dict(
        outer_index=0, outer_id=hex(name_id), outer_size=outer_size, chunk_index=1,
        chunk_offset=64, kind="TSET", stored_size=stored, word_08=256, word_0c=176768,
        word_10=0xFEEDBEEF, word_14=stored)])
    (root / "inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    target = JerseyTarget("18", "H", 0, "18H0.IFF", 0, name_id, outer_size, 1, 64,
        stored, len(jersey), 256, 176768, len(decoded), 0xFEEDBEEF, stored, 1, 12,
        sha(jersey), sha(decoded), len(compressed), stored-len(compressed), "synthetic",
        "0", 0, 2112, "vc_53450030/0", 64, 64*2048, len(pack), sha(pack), 64*2048+2112)
    metadata = dict(jersey=asdict(target), equipment=[asdict(row) for row in equipment.rows],
                    equipment_span_sha256=sha(equipment.span))
    (root / "targets.json").write_text(json.dumps(metadata), encoding="utf-8")
    xbe = b"XBEH" + b"synthetic executable" + bytes(128)
    # Nineteen files, exactly as the production container identity gate expects.
    children = _dir_node([(64, len(pack), 0x80, "0")])
    rows = [(40, len(children), 0x10, "vc_53450030"), (41, len(xbe), 0x80, "default.xbe")]
    rows += [(42+i, 1, 0x80, f"f{i:02}.dat") for i in range(17)]
    directory = _dir_node(rows)
    disc = bytearray(64*2048+len(pack))
    disc[0x10000:0x10014] = disc[0x107ec:0x10800] = b"MICROSOFT*XBOX*MEDIA"
    struct.pack_into("<II", disc, 0x10014, 33, len(directory))
    disc[33*2048:33*2048+len(directory)] = directory
    disc[40*2048:40*2048+len(children)] = children
    disc[41*2048:41*2048+len(xbe)] = xbe
    disc[64*2048:] = pack
    (root / "source.iso").write_bytes(disc)
    (root / "xbe.bin").write_bytes(xbe)
    return equipment, target


def configure(tool, root):
    metadata_path = root / "targets.json"
    raw = metadata_path.read_bytes()
    metadata = json.loads(raw)
    target = JerseyTarget(**metadata["jersey"])
    tool.INDEX_SIZE = (root / "0").stat().st_size
    tool.INDEX_SHA256 = sha((root / "0").read_bytes())
    tool.INVENTORY_SIZE = (root / "inventory.json").stat().st_size
    tool.INVENTORY_SHA256 = sha((root / "inventory.json").read_bytes())
    tool.common.EXPECTED_XBE_SIZE = (root / "xbe.bin").stat().st_size
    tool.common.EXPECTED_XBE_SHA256 = sha((root / "xbe.bin").read_bytes())
    for kind in ("torso", "uniform_equipment_texture"):
        tool.REPORTS[kind] = metadata_path
        tool.REPORT_SHA256[kind] = sha(raw)
    # Resolve fixture metadata, preserving every encoder/layout/readback check.
    select = lambda *args: (metadata_path, metadata, raw, target)
    tool.jersey_targets.select_target = select
    tool.jersey_import.select_target = select
    adapter = tool.uniform_equipment_adapter
    assert adapter.__name__ == "_nfl2k5_uniform_equipment_unified_adapter"
    assert not adapter.__package__
    rows = tuple(adapter.EquipmentTarget(**row) for row in metadata["equipment"])
    adapter.load_targets = lambda *args, **kw: ({row.asset_id: row for row in rows}, {(0, 8): rows})
    adapter._chain_pins = lambda: {(0, 8): metadata["equipment_span_sha256"]}


def cli():
    root = Path(sys.argv[1])
    sys.argv = [str(ROOT / "tools/nfl2k5_visual_mod_project.py"), *sys.argv[2:]]
    spec = importlib.util.spec_from_file_location("_b661_cli", sys.argv[0])
    tool = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = tool
    spec.loader.exec_module(tool)
    configure(tool, root)
    return tool.main()


if __name__ == "__main__":
    raise SystemExit(cli())

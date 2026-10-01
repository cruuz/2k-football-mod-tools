"""PROVED OFFLINE (ig, 2026-09-28): Astra xc's compact writer and Astra sd2's final disc-extent guard compose.

The build runs xdvdfs_compact.finish_private after every growth writer and then the final extent gate
(nfl2k5_disc_extents.validate_image). Every image the compact writer produces, in place or as a standalone copy, with
and without a front video partition and with nested and empty entries, must pass the guard with every extent checked.
"""
from pathlib import Path
import struct
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from nfl2k5_xiso_fixture import dir_node  # noqa: E402
from mod_editor.core import nfl2k5_disc_extents as bounds  # noqa: E402
from mod_editor.core import xdvdfs_compact as xc  # noqa: E402


def image(path, files, *, base=0, gaps=3, nested=False):
    """The same synthetic layout as test_xdvdfs_compact.image: files in the given order with gaps between them."""
    at = 40 * xc.SECTOR
    entries = {}
    with path.open("wb") as out:
        for name, data in files.items():
            entries[name] = (at // xc.SECTOR, len(data), 0x80, name)
            out.seek(base + at)
            out.write(data)
            at += xc.align(len(data)) + gaps * xc.SECTOR
        rows = [entries[name] for name in sorted(entries, key=str.casefold)]
        if nested:
            rows += [(34, 24, 0x10, "Sub"), (0, 0, 0x10, "empty")]
            sub = dir_node([(0, 0, 0x20, "zero.bin")])
            out.seek(base + 34 * xc.SECTOR)
            out.write(sub)
            rows.sort(key=lambda row: row[3].casefold())
        root = dir_node(rows)
        header = bytearray(xc.SECTOR)
        header[:20] = header[-20:] = xc.xiso.XDVDFS_MAGIC
        struct.pack_into("<II", header, 20, 33, len(root))
        out.seek(base + 32 * xc.SECTOR)
        out.write(header)
        out.seek(base + 33 * xc.SECTOR)
        out.write(root)
        out.truncate(base + at + 64 * xc.SECTOR)
    return path


@pytest.mark.parametrize("base", [0, 0x20000])
@pytest.mark.parametrize("nested", [False, True])
def test_compact_output_passes_the_final_extent_guard(tmp_path, base, nested):
    files = {"default.xbe": b"XBEH" * 1500, "middle.bin": bytes(range(256)) * 37, "tail": b"tail" * 1200}
    source = image(tmp_path / "source.iso", files, base=base, nested=nested)
    before = bounds.validate_image(source)
    copy, private = tmp_path / "copy.iso", tmp_path / "private.iso"
    private.write_bytes(source.read_bytes())
    receipt = xc.compact_copy(source, copy)
    xc.finish_private(private)
    assert private.read_bytes() == copy.read_bytes()
    assert receipt["all_file_hashes_identical"]
    for compacted in (copy, private):
        report = bounds.validate_image(compacted)
        assert report["extents_checked"] == before["extents_checked"]
        assert before["partition_base"] == base
        assert report["partition_base"] == 0          # xc always writes a base-0 XISO (its own _verify requires it)
        assert report["image_bytes"] == compacted.stat().st_size
        assert report["image_bytes"] <= source.stat().st_size


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))

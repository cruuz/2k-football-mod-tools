"""PROVED OFFLINE: synthetic compaction, relocation, publication and bounds checks."""
from pathlib import Path
import hashlib
import os
import random
import struct
import sys
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from nfl2k5_xiso_fixture import dir_node
from mod_editor.core import xdvdfs_compact as xc
from mod_editor.core import nfl2k5_music_archive as archive


def image(path, files, *, physical=None, base=0, gaps=3, nested=False):
    physical = physical or list(files)
    at = 40 * xc.SECTOR
    entries = {}
    with path.open("wb") as out:
        for name in physical:
            data = files[name]
            entries[name] = (at // xc.SECTOR, len(data), 0x80, name)
            out.seek(base + at)
            out.write(data)
            at += xc.align(len(data)) + gaps * xc.SECTOR
        rows = [entries[name] for name in sorted(entries, key=str.casefold)]
        if nested:
            rows += [(34, 24, 0x10, "Sub"), (0, 0, 0x10, "empty")]
            # A differently cased directory with a zero-length file.
            sub = dir_node([(0, 0, 0x20, "zero.bin")])
            assert len(sub) == 24
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


def payloads(path):
    with path.open("rb", buffering=0) as stream:
        layout = xc.read_layout(stream)
        return {key: xc.read_at(stream, entry.byte_offset, entry.size)
                for key, entry in layout.entries.items() if not entry.attributes & 0x10}


def test_middle_growth_returns_to_original_slot(tmp_path):
    files = {"default.xbe": b"XBEH" * 1500, "middle": b"middle", "tail": b"tail" * 1200}
    source = image(tmp_path / "source.iso", files)
    private = tmp_path / "private.iso"
    private.write_bytes(source.read_bytes())
    replacement = b"GROWN" * 2100
    with private.open("r+b", buffering=0) as stream:
        archive.write_named(stream.fileno(), lambda n, at: xc.read_at(stream, at, n), 0,
                            "middle", lambda n, at: replacement[at:at+n], len(replacement))
    before = payloads(private)
    receipt = xc.finish_private(private, original=source)
    assert payloads(private) == before == dict(files, middle=replacement)
    assert [r["path"] for r in receipt["files"]] == list(files)
    assert receipt["scratch_disk_bytes"] == 0
    assert receipt["peak_cycle_buffer_bytes"] <= xc.BLOCK
    assert private.stat().st_size < source.stat().st_size
    rows = receipt["files"]
    assert all(a["offset"] + xc.align(a["size"]) == b["offset"] for a, b in zip(rows, rows[1:]))


@pytest.mark.parametrize("base", [0, 0x20000])
def test_copy_and_private_match_with_nested_empty_and_partial_files(tmp_path, base):
    files = {"default.xbe": b"XBEH" * 51, "caf\xe9.bin": bytes(range(256)) * 37, "z": b"end"}
    # Fixture names use latin-1 below via patched helper to retain byte spelling.
    def latin_rows(rows):
        result = bytearray()
        for i, (sector, size, attrs, name) in enumerate(rows):
            raw = name.encode("latin-1")
            n = xc.align(14 + len(raw), 4)
            right = (len(result) + n) // 4 if i + 1 < len(rows) else 0
            result.extend(struct.pack("<HHIIBB", 0, right, sector, size, attrs, len(raw)) + raw + bytes(n - 14 - len(raw)))
        return result
    with mock.patch(f"{__name__}.dir_node", side_effect=latin_rows):
        source = image(tmp_path / "source.iso", files, base=base, nested=True)
    before = source.read_bytes()
    copy, private = tmp_path / "copy.iso", tmp_path / "private.iso"
    private.write_bytes(before)
    receipt = xc.compact_copy(source, copy)
    xc.finish_private(private)
    assert private.read_bytes() == copy.read_bytes()
    assert payloads(copy) == dict(files, **{"sub/zero.bin": b""})
    assert source.read_bytes() == before
    assert receipt["all_file_hashes_identical"]
    assert receipt["output_bytes"] % (32 * xc.SECTOR) == 0


def test_permutations_and_memmove_crossing_buffer_boundaries(tmp_path):
    rng = random.Random(20260928)
    for case in range(35):
        names = ["default.xbe", "a", "b", "c", "d", "e"]
        files = {name: bytes([i + 1]) * (rng.randrange(1, 70) * xc.SECTOR - rng.randrange(0, 100))
                 for i, name in enumerate(names)}
        if case == 0:
            files["a"] = bytes(range(256)) * (xc.BLOCK // 256 + 17)
        original = image(tmp_path / "original.iso", files, gaps=0)
        rng.shuffle(names)
        source = image(tmp_path / "source.iso", files, physical=names, gaps=case % 4)
        dest = tmp_path / "out.iso"
        xc.compact_copy(source, dest, reference=original)
        receipt = xc.finish_private(source, original=original)
        assert source.read_bytes() == dest.read_bytes(), case
        assert payloads(source) == files
        assert receipt["peak_cycle_buffer_bytes"] <= xc.BLOCK
        dest.unlink()


def test_cycle_buffer_is_used_and_bounded(tmp_path):
    files = {"default.xbe": b"x" * (2 * xc.BLOCK), "a": b"a" * (2 * xc.BLOCK)}
    original = image(tmp_path / "original.iso", files, gaps=0)
    staged = tmp_path / "staged.iso"
    xc.compact_copy(original, staged)
    # Reverse two exact adjacent extents in the private image's directory.
    with staged.open("r+b", buffering=0) as stream:
        layout = xc.read_layout(stream)
        a, b = [layout.entries[name] for name in files]
        for name, sector in (("default.xbe", b.sector), ("a", a.sector)):
            parent, node = layout.nodes[name]
            xc.write_at(stream, layout.directories[parent][0] + node, struct.pack("<I", sector))
    expected = payloads(staged)
    result = xc.finish_private(staged, original=original)
    assert payloads(staged) == expected
    assert result["peak_cycle_buffer_bytes"] == xc.BLOCK


def test_portable_reader_without_posix_pread(tmp_path, monkeypatch):
    source = image(tmp_path / "source.iso", {"default.xbe": b"XBEH", "a": b"portable"})
    monkeypatch.delattr(os, "pread", raising=False)
    output = tmp_path / "out.iso"
    xc.compact_copy(source, output)
    xc.finish_private(output)
    assert payloads(source) == payloads(output)


def test_raw_partition_ignores_video_tree_and_moves_directory_below_header(tmp_path):
    video = image(tmp_path / "video.iso", {"video.bin": b"video placeholder"}).read_bytes()
    source = image(tmp_path / "raw.iso", {"default.xbe": b"XBEH", "a": b"game"}, base=0x80000)
    with source.open("r+b", buffering=0) as stream:
        xc.write_at(stream, 0, video)
        root = xc.read_at(stream, 0x80000 + 33 * xc.SECTOR, xc.SECTOR)
        xc.write_at(stream, 0x80000 + 30 * xc.SECTOR, root)
        xc.write_at(stream, 0x80000 + 0x10014, struct.pack("<I", 30))
    output = tmp_path / "game.iso"
    xc.compact_copy(source, output)
    assert payloads(output) == {"default.xbe": b"XBEH", "a": b"game"}
    xc.finish_private(source)
    assert source.read_bytes() == output.read_bytes()


def test_retail_order_uses_names_not_current_sectors(tmp_path):
    # A real retail-order source is unnecessary: the pinned name order is the contract.
    from types import SimpleNamespace
    entries = {name: SimpleNamespace(attributes=0x80, byte_offset=i, size=1)
               for i, name in enumerate(reversed(xc.NFL_ORDER))}
    order, mode = xc.file_order(SimpleNamespace(entries=entries))
    assert tuple(order) == xc.NFL_ORDER and mode == "nfl2k5-retail"


def test_refusals_and_failed_copy_leave_source_and_destination_alone(tmp_path):
    source = image(tmp_path / "source.iso", {"default.xbe": b"XBEH", "a": b"payload"})
    before = source.read_bytes()
    with pytest.raises(ValueError):
        xc.compact_copy(source, source)
    output = tmp_path / "out.iso"
    output.write_bytes(b"keep")
    with pytest.raises(ValueError):
        xc.compact_copy(source, output)
    assert output.read_bytes() == b"keep"
    output.unlink()
    with mock.patch.object(xc, "_verify", side_effect=ValueError("read-back failure")):
        with pytest.raises(ValueError, match="read-back"):
            xc.compact_copy(source, output)
    assert not output.exists() and not list(tmp_path.glob(".xdvdfs-*"))
    assert source.read_bytes() == before


def test_studio_sidecars_follow_copy_without_overwriting_existing_receipts(tmp_path):
    source = image(tmp_path / "source.iso", {"default.xbe": b"XBEH"})
    for suffix in xc.STUDIO_RECEIPTS:
        Path(str(source) + suffix).write_bytes(b'{"source": "resource pins"}\n')
    output = tmp_path / "copy.iso"
    xc.compact_copy(source, output)
    for suffix in xc.STUDIO_RECEIPTS:
        assert Path(str(output) + suffix).read_bytes() == Path(str(source) + suffix).read_bytes()
    refused = tmp_path / "refused.iso"
    existing = Path(str(refused) + xc.STUDIO_RECEIPTS[0])
    existing.write_bytes(b"keep")
    with pytest.raises(ValueError, match="receipt already exists"):
        xc.compact_copy(source, refused)
    assert not refused.exists() and existing.read_bytes() == b"keep"


@pytest.mark.parametrize("fault", ["overlap", "out_of_bounds", "cycle", "metadata_budget"])
def test_bad_structure_refuses_before_private_write(tmp_path, fault):
    source = image(tmp_path / "bad.iso", {"default.xbe": b"x" * 4096, "a": b"a" * 4096})
    with source.open("r+b", buffering=0) as stream:
        layout = xc.read_layout(stream)
        parent, node = layout.nodes["a"]
        offset = layout.directories[parent][0] + node
        if fault == "overlap":
            xc.write_at(stream, offset, struct.pack("<I", layout.entries["default.xbe"].sector))
        elif fault == "out_of_bounds":
            xc.write_at(stream, offset, struct.pack("<I", 0xffffffff))
        elif fault == "cycle":
            xc.write_at(stream, offset - 4, struct.pack("<H", (node - 4) // 4 or 1))
        else:
            xc.write_at(stream, 0x10018, struct.pack("<I", xc.MAX_METADATA + 1))
    before = source.read_bytes()
    with pytest.raises((ValueError, xc.xiso.PatchError)):
        xc.finish_private(source)
    assert source.read_bytes() == before


def test_build_compacts_and_failure_preserves_published_target(tmp_path):
    from mod_editor.core import mod_build
    from test_mod_build_performance import synthetic_disc
    source, output = tmp_path / "source.iso", tmp_path / "out.iso"
    synthetic_disc(source)
    original = payloads(source)
    # This minimal executable fixture deliberately contains no PLAY archive.
    with mock.patch.object(mod_build, "_check_playbook_scoring", return_value={"synthetic": True}):
        receipt = mod_build.build(mod_build.BuildPlan(str(source), str(output)))
    assert payloads(output) == original
    assert receipt["disc_compaction"]["bytes_saved"] > 0
    assert receipt["result"]["image_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    before = output.read_bytes()
    with mock.patch.object(xc, "finish_private", side_effect=ValueError("compaction failed")):
        with pytest.raises(ValueError, match="compaction failed"):
            mod_build.build(mod_build.BuildPlan(str(source), str(output), overwrite=True))
    assert output.read_bytes() == before
    assert not list(tmp_path.glob(".studio-build-*"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


# beta 76.3: a dump that stores the 2K5 files in another order (other xiso tools) made the in-place retail-order
# permutation run for hours (Discord, 10-02: "stuck at Compacting disc image" on Windows). Sizes are the USA retail
# file sizes; J_ROWS is the SOFTDRINK 2K28 v0.2 build's own compaction (relocated growth back into retail slots).
RETAIL_SIZES = {
    "update.xbe": 2326528, "default.xbe": 11948032, "dashupdate.xbe": 58421248, "vc_53450030/9": 634941440,
    "vc_53450030/5": 307972096, "vc_53450030/3": 315508736, "vc_53450030/1": 299999232, "vc_53450030/0": 193710080,
    "vc_53450030/2": 309252096, "vc_53450030/4": 313178112, "vc_53450030/7": 319197184, "vc_53450030/6": 458231808,
    "vc_53450030/8": 929370112, "vc_53450030/d": 309135360, "vc_53450030/b": 458248192, "vc_53450030/a": 310294528,
    "vc_53450030/c": 315131904, "vc_53450030/e": 301813760, "vc_53450030/f": 451733504}
J_ROWS = [
    ("update.xbe", 69632, 71680, 2326528), ("default.xbe", 5883691008, 2398208, 12300288),
    ("dashupdate.xbe", 14344192, 14698496, 58421248), ("vc_53450030/9", 72767488, 73119744, 634941440),
    ("vc_53450030/5", 707708928, 708061184, 307972096), ("vc_53450030/3", 6319216640, 1016033280, 323686400),
    ("vc_53450030/1", 1331189760, 1339719680, 299999232), ("vc_53450030/0", 8121899008, 1639718912, 194072576),
    ("vc_53450030/2", 1631188992, 1833791488, 309252096), ("vc_53450030/4", 1940441088, 2143043584, 313178112),
    ("vc_53450030/7", 2253619200, 2456221696, 319197184), ("vc_53450030/6", 2572816384, 2775418880, 458231808),
    ("vc_53450030/8", 3031048192, 3233650688, 929370112), ("vc_53450030/d", 3960418304, 4163020800, 309135360),
    ("vc_53450030/b", 6953203712, 4472156160, 458260480), ("vc_53450030/a", 6642903040, 4930416640, 310300672),
    ("vc_53450030/c", 5038096384, 5240717312, 315131904), ("vc_53450030/e", 5353228288, 5555849216, 301813760),
    ("vc_53450030/f", 8012922880, 5857662976, 67778560)]


def _rows(order):
    at, source = 33 * xc.SECTOR + xc.SECTOR * 2, {}
    for name in order:
        source[name], at = at, at + xc.align(RETAIL_SIZES[name])
    dest, rows = 33 * xc.SECTOR + xc.SECTOR * 2, []
    for name in xc.NFL_ORDER:
        rows.append(dict(path=name, source_offset=source[name], offset=dest, size=RETAIL_SIZES[name]))
        dest += xc.align(RETAIL_SIZES[name])
    return rows


def test_dry_run_rejects_a_reordered_retail_dump_and_keeps_real_growth_in_place():
    import time
    start = time.monotonic()
    assert not xc._in_place_fits(_rows(sorted(RETAIL_SIZES)))
    assert not xc._in_place_fits(_rows(list(reversed(xc.NFL_ORDER))))
    assert time.monotonic() - start < 4 * xc.IN_PLACE_MAX_SECONDS + 2
    assert xc._in_place_fits(_rows(xc.NFL_ORDER))
    assert xc._in_place_fits([dict(path=p, source_offset=s, offset=d, size=n) for p, s, d, n in J_ROWS])


def _nfl_image(path, files, physical, gaps=1):
    """The retail tree's shape: three executables in the root, sixteen packs under vc_53450030."""
    at, placed = 40 * xc.SECTOR, {}
    with path.open("wb") as out:
        for name in physical:
            placed[name] = (at // xc.SECTOR, len(files[name]))
            out.seek(at)
            out.write(files[name])
            at += xc.align(len(files[name])) + gaps * xc.SECTOR
        sub = dir_node(sorted(((placed[n][0], placed[n][1], 0x80, n.split("/")[1]) for n in files if "/" in n),
                              key=lambda row: row[3].casefold()))
        root = dir_node(sorted([(placed[n][0], placed[n][1], 0x80, n) for n in files if "/" not in n]
                               + [(34, len(sub), 0x10, "vc_53450030")], key=lambda row: row[3].casefold()))
        header = bytearray(xc.SECTOR)
        header[:20] = header[-20:] = xc.xiso.XDVDFS_MAGIC
        struct.pack_into("<II", header, 20, 33, len(root))
        for sector, data in ((32, header), (33, root), (34, sub)):
            out.seek(sector * xc.SECTOR)
            out.write(data)
        out.truncate(at + 64 * xc.SECTOR)
    return path


def _reversed_2k5(tmp_path):
    files = {name: bytes([i + 1]) * (xc.SECTOR * (i % 3 + 1) + 7 * i) for i, name in enumerate(xc.NFL_ORDER)}
    source = _nfl_image(tmp_path / "source.iso", files, list(reversed(xc.NFL_ORDER)))
    return files, source


def test_reordered_2k5_dump_compacts_in_its_own_order_when_retail_order_is_too_fragmented(tmp_path, monkeypatch):
    files, source = _reversed_2k5(tmp_path)
    private = tmp_path / "private.iso"
    private.write_bytes(source.read_bytes())
    real = xc._in_place_fits
    monkeypatch.setattr(xc, "_in_place_fits", lambda rows: [r["path"] for r in rows] != list(xc.NFL_ORDER) and real(rows))
    receipt = xc.finish_private(private, original=source)
    assert receipt["order"] == "reference" and receipt["scratch_disk_bytes"] == 0
    assert [r["path"] for r in receipt["files"]] == list(reversed(xc.NFL_ORDER))
    assert payloads(private) == files


def test_too_fragmented_plans_rewrite_beside_with_the_in_place_bytes(tmp_path, monkeypatch):
    files, source = _reversed_2k5(tmp_path)
    in_place, beside = tmp_path / "in_place.iso", tmp_path / "beside.iso"
    in_place.write_bytes(source.read_bytes())
    beside.write_bytes(source.read_bytes())
    first = xc.finish_private(in_place, original=source)
    assert first["order"] == "nfl2k5-retail" and first["scratch_disk_bytes"] == 0
    monkeypatch.setattr(xc, "_in_place_fits", lambda rows: False)
    second = xc.finish_private(beside, original=source)
    assert beside.read_bytes() == in_place.read_bytes()
    assert second["order"] == "nfl2k5-retail" and second["scratch_disk_bytes"] == second["output_bytes"]
    assert payloads(beside) == files
    assert sorted(p.name for p in tmp_path.iterdir()) == ["beside.iso", "in_place.iso", "source.iso"]


def test_rewrite_refuses_clearly_without_space_and_leaves_the_image(tmp_path, monkeypatch):
    files, source = _reversed_2k5(tmp_path)
    private = tmp_path / "private.iso"
    private.write_bytes(source.read_bytes())
    before = private.read_bytes()
    monkeypatch.setattr(xc, "_in_place_fits", lambda rows: False)
    monkeypatch.setattr(xc.shutil, "disk_usage", lambda path: mock.Mock(free=1024))
    with pytest.raises(ValueError, match="different order from the retail disc"):
        xc.finish_private(private, original=source)
    assert private.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["private.iso", "source.iso"]


def test_replace_retries_a_briefly_held_windows_file(tmp_path, monkeypatch):
    staged, target = tmp_path / "staged", tmp_path / "target"
    staged.write_bytes(b"new")
    target.write_bytes(b"old")
    calls, real = [], os.replace
    def flaky(a, b):
        calls.append(a)
        if len(calls) < 3:
            raise PermissionError(32, "The process cannot access the file")
        real(a, b)
    monkeypatch.setattr(xc.os, "replace", flaky)
    monkeypatch.setattr(xc.os, "name", "nt")
    monkeypatch.setattr(xc.time, "sleep", lambda s: None)
    xc._replace_image(staged, target)
    assert len(calls) == 3 and target.read_bytes() == b"new" and not staged.exists()

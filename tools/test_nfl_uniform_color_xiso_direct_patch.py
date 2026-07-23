#!/usr/bin/env python3
"""Deterministic helper tests for the layout-preserving NFL XISO writer."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nfl_uniform_color_xiso_direct_patch as direct  # noqa: E402
import nfl_uniform_color_xiso_direct_verify as virtual  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def node(
    name: str,
    sector: int,
    size: int,
    attributes: int,
    left_dwords: int = 0,
    right_dwords: int = 0,
) -> bytes:
    encoded = name.encode("ascii")
    value = struct.pack(
        "<HHIIBB",
        left_dwords,
        right_dwords,
        sector,
        size,
        attributes,
        len(encoded),
    ) + encoded
    return value + bytes((-len(value)) & 3)


def synthetic_xiso(path: Path) -> None:
    image = bytearray(0x18000)
    header = bytearray(0x800)
    header[:20] = direct.XDVDFS_MAGIC
    header[-20:] = direct.XDVDFS_MAGIC

    root_sector = 33
    root_first = node("default.xbe", 40, 4, 0x20, right_dwords=7)
    check(len(root_first) == 28, "synthetic root offset changed")
    root_second = node("vc_53450030", 35, 20, 0x10)
    root = root_first + root_second
    struct.pack_into("<II", header, 20, root_sector, len(root))
    image[direct.XDVDFS_HEADER_OFFSET : direct.XDVDFS_HEADER_OFFSET + 0x800] = header
    root_offset = root_sector * direct.SECTOR_SIZE
    image[root_offset : root_offset + len(root)] = root

    subdirectory = node("A", 41, 8, 0x20)
    subdir_offset = 35 * direct.SECTOR_SIZE
    image[subdir_offset : subdir_offset + len(subdirectory)] = subdirectory
    image[40 * direct.SECTOR_SIZE : 40 * direct.SECTOR_SIZE + 4] = b"XBE!"
    image[41 * direct.SECTOR_SIZE : 41 * direct.SECTOR_SIZE + 8] = b"PACKDATA"
    path.write_bytes(image)


def synthetic_run_xiso(path: Path) -> None:
    """Build a small but structurally complete 19-file image for run()."""
    image = bytearray(13 * 1024 * 1024)
    header = bytearray(0x800)
    header[:20] = direct.XDVDFS_MAGIC
    header[-20:] = direct.XDVDFS_MAGIC

    records = [
        ("default.xbe", 100, direct.EXPECTED_XBE_SIZE, 0x20),
        ("vc_53450030", 35, 32, 0x10),
        *((f"dummy{index:02d}", 42 + index, 0, 0x20) for index in range(16)),
    ]
    root_parts: list[bytes] = []
    offset = 0
    for index, (name, sector, size, attributes) in enumerate(records):
        provisional = node(name, sector, size, attributes)
        next_offset = offset + len(provisional)
        right = next_offset // 4 if index + 1 < len(records) else 0
        encoded = node(name, sector, size, attributes, right_dwords=right)
        check(len(encoded) == len(provisional), "synthetic node size changed")
        root_parts.append(encoded)
        offset = next_offset
    root = b"".join(root_parts)
    struct.pack_into("<II", header, 20, 33, len(root))
    image[direct.XDVDFS_HEADER_OFFSET:direct.XDVDFS_HEADER_OFFSET + 0x800] = header
    image[33 * direct.SECTOR_SIZE:33 * direct.SECTOR_SIZE + len(root)] = root

    first = node("A", 40, 8, 0x20, right_dwords=4)
    check(len(first) == 16, "synthetic subdirectory offset changed")
    subdirectory = first + node("B", 41, 8, 0x20)
    image[35 * direct.SECTOR_SIZE:35 * direct.SECTOR_SIZE + len(subdirectory)] = subdirectory
    before = struct.pack("<II", 0xFF000000, 0xFF385AAF)
    image[40 * direct.SECTOR_SIZE:40 * direct.SECTOR_SIZE + 8] = before
    image[41 * direct.SECTOR_SIZE:41 * direct.SECTOR_SIZE + 8] = before
    path.write_bytes(image)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nfl-xiso-direct-test-") as temp:
        root = Path(temp)
        image_path = root / "synthetic.iso"
        copy_path = root / "copy.iso"
        synthetic_xiso(image_path)

        source = os.open(image_path, os.O_RDONLY)
        output = os.open(copy_path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        try:
            image_size = image_path.stat().st_size
            entries, metadata = direct.parse_xdvdfs(source, image_size)
            check(metadata["root_sector"] == 33, "root sector mismatch")
            check(metadata["directory_nodes"] == 3, "node count mismatch")
            check(entries["default.xbe"].sector == 40, "file sector mismatch")
            check(entries["vc_53450030/a"].size == 8, "nested file mismatch")

            method = direct.copy_fd_exact(source, output, image_size)
            check(method in {"copy_file_range", "pread_pwrite"}, "copy method")
            patch_offsets = {0x120, 0x123}
            os.pwrite(output, b"Q", 0x120)
            os.pwrite(output, b"R", 0x123)
            source_hash, output_hash, differences = direct.compare_and_hash(
                source, output, image_size, patch_offsets
            )
            check(source_hash == hashlib.sha256(image_path.read_bytes()).hexdigest(),
                  "source hash mismatch")
            check(source_hash != output_hash, "output hash did not change")
            check(differences == [0x120, 0x123], "difference ledger mismatch")

            try:
                direct.compare_and_hash(source, output, image_size, {0x120})
            except direct.PatchError:
                pass
            else:
                raise AssertionError("unexpected extra difference was accepted")

            try:
                direct.compare_and_hash(source, output, image_size,
                                        {0x120, 0x123, 0x124})
            except direct.PatchError:
                pass
            else:
                raise AssertionError("missing required difference was accepted")
        finally:
            os.close(output)
            os.close(source)

        cycle_path = root / "cycle.iso"
        synthetic_xiso(cycle_path)
        descriptor = os.open(cycle_path, os.O_RDWR)
        try:
            # Second root node begins at byte 28; point its left link to itself.
            os.pwrite(descriptor, struct.pack("<H", 7), 33 * direct.SECTOR_SIZE + 28)
            try:
                direct.parse_xdvdfs(descriptor, cycle_path.stat().st_size)
            except direct.PatchError:
                pass
            else:
                raise AssertionError("cyclic XDVDFS tree was accepted")
        finally:
            os.close(descriptor)

        owned = direct.reserve_file(root / "exclusive.bin")
        os.close(owned.descriptor)
        try:
            direct.reserve_file(root / "exclusive.bin")
        except direct.PatchError:
            pass
        else:
            raise AssertionError("existing exclusive output was replaced")

        # A pathname replacement must not be mistaken for the inode reserved by
        # the writer, and cleanup must never unlink the replacement.
        swap_owned = direct.reserve_file(root / "swap.bin")
        os.close(swap_owned.descriptor)
        moved = root / "owned-moved.bin"
        swap_owned.path.rename(moved)
        swap_owned.path.write_bytes(b"replacement")
        check(not direct.owned_path_matches(swap_owned),
              "pathname replacement retained false ownership")
        direct.unlink_if_owned(swap_owned)
        check(swap_owned.path.read_bytes() == b"replacement",
              "cleanup unlinked an unowned replacement")

        # run() must reject a caller-supplied source symlink before any output
        # path is reserved, even though the link resolves to a regular file.
        source_link = root / "source-link.iso"
        source_link.symlink_to(image_path)
        rejected_output = root / "symlink-output.iso"
        rejected_manifest = root / "symlink-manifest.json"
        try:
            direct.run(source_link, rejected_output, rejected_manifest)
        except direct.PatchError as exc:
            check("symbolic link" in str(exc), "wrong symlink rejection reason")
        else:
            raise AssertionError("caller-supplied source symlink was accepted")
        check(not rejected_output.exists() and not rejected_manifest.exists(),
              "symlink rejection created outputs")

        check(
            [(target.expected_sector, target.expected_absolute_patch_offset)
             for target in direct.TARGETS]
            == [(2_403_082, 5_011_470_416), (2_179_328, 4_718_884_944)],
            "retail target sector/offset pins changed",
        )

        # Exercise the complete descriptor-bound run on a synthetic 19-file
        # image by temporarily replacing only its frozen retail constants.
        run_source = root / "run-source.iso"
        run_output = root / "run-output.iso"
        run_manifest = root / "run-manifest.json"
        original_values = (
            direct.EXPECTED_XISO_SIZE,
            direct.EXPECTED_XISO_SHA256,
            direct.EXPECTED_XBE_SHA256,
            direct.TARGETS,
        )
        try:
            synthetic_run_xiso(run_source)
            direct.EXPECTED_XISO_SIZE = run_source.stat().st_size
            direct.EXPECTED_XISO_SHA256 = hashlib.sha256(run_source.read_bytes()).hexdigest()
            xbe_offset = 100 * direct.SECTOR_SIZE
            with run_source.open("rb") as stream:
                stream.seek(xbe_offset)
                direct.EXPECTED_XBE_SHA256 = hashlib.sha256(
                    stream.read(direct.EXPECTED_XBE_SIZE)
                ).hexdigest()
            before = struct.pack("<II", 0xFF000000, 0xFF385AAF)
            before_hash = hashlib.sha256(before).hexdigest()
            direct.TARGETS = (
                direct.Target("vc_53450030/A", 40, 0, 40 * direct.SECTOR_SIZE,
                              8, before_hash, before),
                direct.Target("vc_53450030/B", 41, 0, 41 * direct.SECTOR_SIZE,
                              8, before_hash, before),
            )
            source_before = hashlib.sha256(run_source.read_bytes()).hexdigest()
            result = direct.run(run_source, run_output, run_manifest)
            check(result["patch"]["actual_changed_byte_count"] == 10,
                  "full synthetic run difference count")
            check(hashlib.sha256(run_source.read_bytes()).hexdigest() == source_before,
                  "full synthetic run changed source")
            check(run_output.stat().st_size == run_source.stat().st_size,
                  "full synthetic run changed image size")
            check(run_manifest.exists(), "full synthetic run omitted manifest")

            # Force a post-copy failure and confirm only the writer-owned
            # output is removed; no manifest should ever appear.
            failed_output = root / "forced-failure.iso"
            failed_manifest = root / "forced-failure.json"
            original_compare = direct.compare_and_hash

            def forced_failure(*_args: object, **_kwargs: object) -> object:
                raise direct.PatchError("forced post-copy failure")

            direct.compare_and_hash = forced_failure
            try:
                direct.run(run_source, failed_output, failed_manifest)
            except direct.PatchError as exc:
                check("forced post-copy failure" in str(exc),
                      "wrong forced-failure reason")
            else:
                raise AssertionError("forced post-copy failure was accepted")
            finally:
                direct.compare_and_hash = original_compare
            check(not failed_output.exists() and not failed_manifest.exists(),
                  "forced failure left writer-owned output")
        finally:
            (direct.EXPECTED_XISO_SIZE,
             direct.EXPECTED_XISO_SHA256,
             direct.EXPECTED_XBE_SHA256,
             direct.TARGETS) = original_values

        # The artifact-independent verifier overlays only the frozen ranges,
        # including when a streaming chunk splits one replacement window.
        patches = ((4, b"ABCD", b"WXYZ"),)
        check(virtual.virtualize_chunk(b"00AB", 2, patches) == b"00WX",
              "virtual prefix overlay mismatch")
        check(virtual.virtualize_chunk(b"CD11", 6, patches) == b"YZ11",
              "virtual suffix overlay mismatch")
        untouched = b"outside"
        check(virtual.virtualize_chunk(untouched, 20, patches) == untouched,
              "virtual overlay changed an unrelated chunk")
        try:
            virtual.virtualize_chunk(b"00AX", 2, patches)
        except virtual.VerifyError as exc:
            check("retail bytes differ" in str(exc),
                  "wrong virtual source-tamper rejection reason")
        else:
            raise AssertionError("virtual source tamper was accepted")
        try:
            virtual.validate_virtual_patches(
                32, ((4, b"AAAA", b"BBBB"), (6, b"CC", b"DD"))
            )
        except virtual.VerifyError as exc:
            check("overlap" in str(exc),
                  "wrong overlapping-patch rejection reason")
        else:
            raise AssertionError("overlapping virtual patches were accepted")

        # A symlink in any parent component is as unsafe as a symlink leaf.
        real_parent = root / "real-parent"
        real_parent.mkdir()
        parent_file = real_parent / "pinned.bin"
        parent_file.write_bytes(b"pinned")
        symlink_parent = root / "symlink-parent"
        symlink_parent.symlink_to(real_parent, target_is_directory=True)
        try:
            virtual.open_pinned(symlink_parent / parent_file.name, 6)
        except virtual.VerifyError as exc:
            check("component is a symlink" in str(exc),
                  "wrong parent-symlink rejection reason")
        else:
            raise AssertionError("symlinked parent was accepted")

        hardlink = root / "pinned-hardlink.bin"
        hardlink.hardlink_to(parent_file)
        try:
            virtual.open_pinned(parent_file, 6)
        except virtual.VerifyError as exc:
            check("hard-linked" in str(exc),
                  "wrong hardlink rejection reason")
        else:
            raise AssertionError("hardlinked pinned input was accepted")

        # A BaseException after open_pinned acquires its descriptor must close
        # that descriptor rather than leaking it out of the failed pin.
        interrupt_pin = root / "interrupt-pin.bin"
        interrupt_pin.write_bytes(b"interrupt-pin")
        real_hash_extent = virtual.hash_extent
        real_close = virtual.os.close
        interrupt_closed: list[int] = []

        def interrupt_pin_hash(_descriptor: int, _offset: int,
                               _size: int) -> str:
            raise KeyboardInterrupt("synthetic pin hash interrupt")

        def track_interrupt_close(descriptor: int) -> None:
            interrupt_closed.append(descriptor)
            real_close(descriptor)

        virtual.hash_extent = interrupt_pin_hash
        virtual.os.close = track_interrupt_close
        try:
            try:
                virtual.open_pinned(
                    interrupt_pin, 13,
                    hashlib.sha256(b"interrupt-pin").hexdigest(),
                )
            except KeyboardInterrupt:
                pass
            else:
                raise AssertionError("pin hash interrupt was accepted")
        finally:
            virtual.hash_extent = real_hash_extent
            virtual.os.close = real_close
        check(len(interrupt_closed) == 1,
              "pin hash interrupt did not close exactly its owned fd")

        # Manifest reads use the same cleanup policy: report a close failure on
        # success, while preserving a primary parse/read failure.
        tiny_manifest = root / "tiny-manifest.json"
        tiny_manifest_payload = b"{}\n"
        tiny_manifest.write_bytes(tiny_manifest_payload)
        original_manifest_values = (
            virtual.MANIFEST_SIZE, virtual.MANIFEST_SHA256
        )
        real_pread_exact = virtual.pread_exact
        virtual.MANIFEST_SIZE = len(tiny_manifest_payload)
        virtual.MANIFEST_SHA256 = hashlib.sha256(
            tiny_manifest_payload
        ).hexdigest()

        close_failure_pending = True

        def close_then_fail(descriptor: int) -> None:
            nonlocal close_failure_pending
            real_close(descriptor)
            if close_failure_pending:
                close_failure_pending = False
                raise PermissionError("synthetic manifest close failure")

        virtual.os.close = close_then_fail
        try:
            try:
                virtual.pinned_manifest_payload(tiny_manifest)
            except PermissionError as exc:
                check("manifest close" in str(exc),
                      "wrong successful-manifest cleanup error")
            else:
                raise AssertionError("manifest close error was swallowed")
        finally:
            virtual.os.close = real_close

        close_failure_pending = True

        def fail_manifest_read(_descriptor: int, _offset: int,
                               _length: int) -> bytes:
            raise virtual.VerifyError("primary manifest read failure")

        virtual.pread_exact = fail_manifest_read
        virtual.os.close = close_then_fail
        try:
            try:
                virtual.pinned_manifest_payload(tiny_manifest)
            except virtual.VerifyError as exc:
                check(str(exc) == "primary manifest read failure",
                      "manifest cleanup masked the primary exception")
            else:
                raise AssertionError("primary manifest failure was swallowed")
        finally:
            virtual.pread_exact = real_pread_exact
            virtual.os.close = real_close
            (virtual.MANIFEST_SIZE,
             virtual.MANIFEST_SHA256) = original_manifest_values

        # Restoring bytes, size, nlink, and mtime must not hide an in-place
        # mutation: ctime/mode are part of the descriptor/path identity pin.
        mutable_pin = root / "mutable-pin.bin"
        mutable_payload = b"mutable-pin"
        mutable_pin.write_bytes(mutable_payload)
        mutable_before = mutable_pin.stat()
        mutable_fd, mutable_identity = virtual.open_pinned(
            mutable_pin, len(mutable_payload),
            hashlib.sha256(mutable_payload).hexdigest(),
        )
        try:
            # This filesystem can coalesce metadata updates within one clock
            # tick, so cross a tick before creating the adversarial write.
            time.sleep(0.02)
            mutable_pin.write_bytes(b"X" * len(mutable_payload))
            mutable_pin.write_bytes(mutable_payload)
            os.chmod(mutable_pin, mutable_before.st_mode & 0o777)
            os.utime(
                mutable_pin,
                ns=(mutable_before.st_atime_ns, mutable_before.st_mtime_ns),
            )
            check(mutable_pin.stat().st_ctime_ns != mutable_identity[6],
                  "fixture did not change pinned-file ctime")
            try:
                virtual.require_stable(
                    mutable_pin, mutable_fd, mutable_identity,
                    hashlib.sha256(mutable_payload).hexdigest(),
                )
            except virtual.VerifyError as exc:
                check("changed during verification" in str(exc),
                      "wrong in-place mutate/restore rejection reason")
            else:
                raise AssertionError("in-place mutate/restore was accepted")
        finally:
            os.close(mutable_fd)

        rehash_pin = root / "rehash-pin.bin"
        rehash_pin.write_bytes(b"rehash-old")
        rehash_fd, _rehash_identity = virtual.open_pinned(rehash_pin, 10)
        try:
            rehash_pin.write_bytes(b"rehash-new")
            changed_identity = virtual.file_identity(os.fstat(rehash_fd))
            try:
                virtual.require_stable(
                    rehash_pin, rehash_fd, changed_identity,
                    hashlib.sha256(b"rehash-old").hexdigest(),
                )
            except virtual.VerifyError as exc:
                check("bytes changed" in str(exc),
                      "wrong final-rehash rejection reason")
            else:
                raise AssertionError("final rehash accepted changed bytes")
        finally:
            os.close(rehash_fd)

        # Materialized-mode cross-checks execute the verified extract-xiso
        # bytes from a write-sealed anonymous inode. Replacing the pathname or
        # mutating the original inode after the copy must not select new bytes.
        fake_tool = root / "extract-xiso"
        fake_tool_payload = (
            "#!/bin/sh\n"
            "printf '%s\\n' 'extract-xiso v2.7.1 (01.11.14) test' "
            "'/file (1 bytes)' '19 files in fixture, total 1 bytes'\n"
        )
        fake_tool.write_text(fake_tool_payload, encoding="utf-8")
        fake_tool.chmod(0o700)
        fake_image = root / "extract-image.iso"
        fake_image.write_bytes(b"image")
        tool_descriptor = os.open(fake_tool, os.O_RDONLY)
        sealed_tool_descriptor = virtual.sealed_executable_copy(
            tool_descriptor, len(fake_tool_payload.encode("utf-8")),
            hashlib.sha256(fake_tool_payload.encode("utf-8")).hexdigest(),
        )
        image_descriptor = os.open(fake_image, os.O_RDONLY)
        moved_tool = root / "extract-xiso-opened"
        fake_tool.rename(moved_tool)
        fake_tool.write_text("#!/bin/sh\nexit 42\n", encoding="utf-8")
        fake_tool.chmod(0o700)
        moved_tool.write_text("#!/bin/sh\nexit 43\n", encoding="utf-8")
        moved_tool.chmod(0o700)
        try:
            banner, listing, total = virtual.extract_listing(
                sealed_tool_descriptor, image_descriptor
            )
            check(banner.endswith("test") and listing == [("/file", 1)] and
                  total == 1,
                  "sealed descriptor-bound extract listing differs")
            virtual.require_sealed_executable(
                sealed_tool_descriptor,
                len(fake_tool_payload.encode("utf-8")),
                hashlib.sha256(fake_tool_payload.encode("utf-8")).hexdigest(),
            )
            try:
                os.pwrite(sealed_tool_descriptor, b"X", 0)
            except OSError:
                pass
            else:
                raise AssertionError("write-sealed executable accepted a mutation")
        finally:
            os.close(image_descriptor)
            os.close(sealed_tool_descriptor)
            os.close(tool_descriptor)

        # A Ctrl-C while filling a new memfd must close the anonymous inode.
        seal_interrupt_source = root / "seal-interrupt-source.bin"
        seal_interrupt_source.write_bytes(b"seal-interrupt")
        seal_interrupt_source_fd = os.open(
            seal_interrupt_source, os.O_RDONLY
        )
        real_memfd_create = virtual.os.memfd_create
        real_write = virtual.os.write
        interrupted_memfds: list[int] = []

        def track_memfd_create(name: str, flags: int = 0) -> int:
            descriptor = real_memfd_create(name, flags)
            interrupted_memfds.append(descriptor)
            return descriptor

        def interrupt_memfd_write(_descriptor: int, _payload: bytes) -> int:
            raise KeyboardInterrupt("synthetic sealed-copy interrupt")

        virtual.os.memfd_create = track_memfd_create
        virtual.os.write = interrupt_memfd_write
        try:
            try:
                virtual.sealed_executable_copy(
                    seal_interrupt_source_fd, len(b"seal-interrupt"),
                    hashlib.sha256(b"seal-interrupt").hexdigest(),
                )
            except KeyboardInterrupt:
                pass
            else:
                raise AssertionError("sealed-copy interrupt was accepted")
        finally:
            virtual.os.memfd_create = real_memfd_create
            virtual.os.write = real_write
            os.close(seal_interrupt_source_fd)
        check(len(interrupted_memfds) == 1,
              "sealed-copy interrupt did not create exactly one memfd")
        try:
            os.fstat(interrupted_memfds[0])
        except OSError:
            pass
        else:
            os.close(interrupted_memfds[0])
            raise AssertionError("sealed-copy interrupt leaked its memfd")

    print(
        "NFL_UNIFORM_COLOR_XISO_DIRECT_PATCH_TEST_PASS parser=yes "
        "cycle_refused=yes copy=yes diff_gate=yes exclusive=yes "
        "inode_swap_refused=yes source_symlink_refused=yes lbas_pinned=yes "
        "full_run=yes forced_cleanup=yes virtual_overlay=yes "
        "virtual_source_tamper_refused=yes virtual_overlap_refused=yes "
        "parent_symlink_refused=yes hardlink_refused=yes "
        "pin_interrupt_clean=yes manifest_close_error_reported=yes "
        "manifest_primary_preserved=yes "
        "inplace_restore_refused=yes rehash_mismatch_refused=yes "
        "extract_sealed_exec=yes sealed_copy_interrupt_clean=yes "
        "extract_path_swap_ignored=yes extract_inode_mutation_ignored=yes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

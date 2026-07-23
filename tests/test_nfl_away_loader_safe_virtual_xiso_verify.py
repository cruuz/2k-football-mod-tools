#!/usr/bin/env python3
"""Tamper tests for the artifact-independent AWAY XISO stream overlay."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import nfl_away_loader_safe_virtual_xiso_verify as verify  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_preview_set(directory: Path, payloads: dict[str, bytes]) -> None:
    directory.mkdir()
    for name, payload in payloads.items():
        (directory / name).write_bytes(payload)


def main() -> int:
    runtime_gate = (
        Path(__file__).resolve().parents[1] / "tools" /
        "validate_nfl_actual_jersey_binding_away_loader_safe_xemu_runtime.sh"
    ).read_text(encoding="utf-8")
    check("import_inputs_staged=not_applicable" in runtime_gate and
          "import_inputs_staged=$import_inputs_staged" in runtime_gate,
          "materialized runtime diagnostic still claims private importer staging")

    before = b"abcdefgh"
    after = b"aXcYeZg!"
    check(verify.virtualize_chunk(b"00ab", 6, 8, before, after) == b"00aX",
          "split virtual prefix differs")
    check(verify.virtualize_chunk(b"cdefgh11", 10, 8, before, after) ==
          b"cYeZg!11", "split virtual suffix differs")
    check(verify.virtualize_chunk(b"outside", 32, 8, before, after) == b"outside",
          "unrelated virtual chunk changed")
    try:
        verify.virtualize_chunk(b"00ax", 6, 8, before, after)
    except verify.VirtualVerifyError as exc:
        check("retail bytes differ" in str(exc), "wrong source-tamper reason")
    else:
        raise AssertionError("virtual source tamper was accepted")

    with tempfile.TemporaryDirectory(prefix="nfl-away-virtual-test-") as temp:
        path = Path(temp) / "image.bin"
        source = b"01234567" + before + b"89ABCDEF"
        path.write_bytes(source)
        descriptor = os.open(path, os.O_RDONLY)
        try:
            result = verify.scan_virtual_image(
                descriptor, len(source), 8, before, after, chunk_size=3
            )
        finally:
            os.close(descriptor)

        real_parent = Path(temp) / "real-parent"
        real_parent.mkdir()
        pinned = real_parent / "pinned.bin"
        pinned.write_bytes(b"pinned")
        alias_parent = Path(temp) / "alias-parent"
        alias_parent.symlink_to(real_parent, target_is_directory=True)
        try:
            verify.open_input(alias_parent / pinned.name, 6, None)
        except verify.VirtualVerifyError as exc:
            check("component is a symlink" in str(exc),
                  "wrong parent-symlink rejection reason")
        else:
            raise AssertionError("symlinked input parent was accepted")

        # A BaseException after open must still close the newly pinned input fd.
        interrupt_open_source = Path(temp) / "interrupt-open-source.bin"
        interrupt_open_source.write_bytes(b"open-interrupt")
        real_hash_fd = verify.hash_fd
        real_close = verify.os.close
        closed_after_interrupt: list[int] = []

        def interrupt_input_hash(_descriptor: int, _size: int) -> str:
            raise KeyboardInterrupt("synthetic open-input interrupt")

        def track_close(descriptor: int) -> None:
            closed_after_interrupt.append(descriptor)
            real_close(descriptor)

        verify.hash_fd = interrupt_input_hash
        verify.os.close = track_close
        try:
            try:
                verify.open_input(
                    interrupt_open_source, 14, "unused-but-required"
                )
            except KeyboardInterrupt:
                pass
            else:
                raise AssertionError("open-input interrupt was accepted")
        finally:
            verify.hash_fd = real_hash_fd
            verify.os.close = real_close
        check(len(closed_after_interrupt) == 1,
              "open-input interrupt did not close exactly its owned fd")

        # The canonical extracted index is intentionally a two-link inode. It
        # is admitted only under that exact count, then consumed as a private
        # mode-0400, single-link descriptor-derived copy.
        canonical_index = Path(temp) / "canonical-index.bin"
        canonical_index.write_bytes(b"canonical-index")
        canonical_index_alias = Path(temp) / "canonical-index-alias.bin"
        canonical_index_alias.hardlink_to(canonical_index)
        with verify.PinnedCopySession("nfl-away-stage-test-", Path(temp)) as session:
            staged = session.add(
                canonical_index, "0", expected_size=15,
                expected_sha256=hashlib.sha256(b"canonical-index").hexdigest(),
                expected_nlink=2,
            )
            staged_info = staged.lstat()
            check(staged.read_bytes() == b"canonical-index",
                  "canonical two-link staged bytes differ")
            check(staged_info.st_nlink == 1 and
                  (staged_info.st_mode & 0o777) == 0o400,
                  "canonical two-link input was not privately staged")
            session.validate()

        with verify.PinnedCopySession("nfl-away-link-test-", Path(temp)) as session:
            try:
                session.add(
                    canonical_index, "unexpected.bin", expected_size=15,
                    expected_sha256=hashlib.sha256(b"canonical-index").hexdigest(),
                    expected_nlink=1,
                )
            except verify.VirtualVerifyError as exc:
                check("link count differs" in str(exc),
                      "wrong unexpected-hardlink rejection reason")
            else:
                raise AssertionError("unexpected hardlinked input was accepted")

        report = Path(temp) / "report.json"
        report.write_bytes(b"{}\n")
        with verify.PinnedCopySession("nfl-away-alias-test-", Path(temp)) as session:
            session.add(
                report, "report.json", expected_size=3,
                expected_sha256=hashlib.sha256(b"{}\n").hexdigest(),
            )
            try:
                session.add(
                    report, "image.png", expected_size=3,
                    expected_sha256=hashlib.sha256(b"{}\n").hexdigest(),
                )
            except verify.VirtualVerifyError as exc:
                check("alias one inode" in str(exc),
                      "wrong report/image-alias rejection reason")
            else:
                raise AssertionError("report/image inode alias was accepted")

        # Constructor rollback must remove the freshly created mode-0700 root
        # even when a BaseException arrives while opening its directory fd.
        real_open = verify.os.open

        def interrupt_directory_open(path: object, flags: int, mode: int = 0o777,
                                     *, dir_fd: int | None = None) -> int:
            if (flags & getattr(os, "O_DIRECTORY", 0) and
                    "nfl-away-constructor-test-" in str(path)):
                raise KeyboardInterrupt("synthetic constructor interrupt")
            if dir_fd is None:
                return real_open(path, flags, mode)  # type: ignore[arg-type]
            return real_open(path, flags, mode, dir_fd=dir_fd)  # type: ignore[arg-type]

        verify.os.open = interrupt_directory_open
        try:
            try:
                verify.PinnedCopySession(
                    "nfl-away-constructor-test-", Path(temp)
                )
            except KeyboardInterrupt:
                pass
            else:
                raise AssertionError("constructor interrupt was accepted")
        finally:
            verify.os.open = real_open
        check(not any(Path(temp).glob("nfl-away-constructor-test-*")),
              "constructor interrupt leaked its private root")

        # add() must roll back an unregistered partial leaf on Ctrl-C rather
        # than leaving a potentially huge current pack in /tmp.
        interrupt_source = Path(temp) / "interrupt-source.bin"
        interrupt_source.write_bytes(b"interrupt-me")
        interrupt_session = verify.PinnedCopySession(
            "nfl-away-interrupt-test-", Path(temp)
        )
        interrupt_root = interrupt_session.root
        real_pread = verify.os.pread
        real_chunk = verify.CHUNK
        interrupt_reads = 0

        def interrupt_copy(descriptor: int, size: int, offset: int) -> bytes:
            nonlocal interrupt_reads
            interrupt_reads += 1
            if interrupt_reads == 1:
                return real_pread(descriptor, size, offset)
            raise KeyboardInterrupt("synthetic copy interrupt")

        verify.CHUNK = 4
        verify.os.pread = interrupt_copy
        try:
            try:
                interrupt_session.add(
                    interrupt_source, "partial.bin", expected_size=12
                )
            except KeyboardInterrupt:
                pass
            else:
                raise AssertionError("copy interrupt was accepted")
        finally:
            verify.os.pread = real_pread
            verify.CHUNK = real_chunk
            interrupt_session.close()
        check(interrupt_reads == 2 and not interrupt_root.exists(),
              "copy interrupt leaked its private root/partial leaf")

        # A late root-identity failure occurs after all bytes and metadata have
        # been written.  It must not register then close the same fds twice.
        late_source = Path(temp) / "late-source.bin"
        late_source.write_bytes(b"late-check")
        late_session = verify.PinnedCopySession(
            "nfl-away-late-test-", Path(temp)
        )
        late_root = late_session.root
        real_root_check = late_session._checked_current_root_identity

        def fail_late_root_check() -> verify.FileIdentity:
            raise verify.VirtualVerifyError("synthetic late root identity failure")

        late_session._checked_current_root_identity = fail_late_root_check
        try:
            try:
                late_session.add(late_source, "late.bin", expected_size=10)
            except verify.VirtualVerifyError as exc:
                check("late root identity" in str(exc),
                      "wrong late-root failure reason")
            else:
                raise AssertionError("late root-identity failure was accepted")
        finally:
            late_session._checked_current_root_identity = real_root_check
            late_session.close()
        check(not late_root.exists(),
              "late root-identity failure leaked its private root")

        # close() must attempt every owned target, then report the first cleanup
        # failure. A cleanup error must never replace an already-active primary
        # exception from inside a with block.
        cleanup_source_a = Path(temp) / "cleanup-source-a.bin"
        cleanup_source_b = Path(temp) / "cleanup-source-b.bin"
        cleanup_source_a.write_bytes(b"cleanup-a")
        cleanup_source_b.write_bytes(b"cleanup-b")
        cleanup_session = verify.PinnedCopySession(
            "nfl-away-cleanup-test-", Path(temp)
        )
        cleanup_root = cleanup_session.root
        cleanup_session.add(cleanup_source_a, "first.bin", expected_size=9)
        cleanup_session.add(cleanup_source_b, "second.bin", expected_size=9)
        real_unlink = verify.os.unlink
        unlink_attempts: list[str] = []

        def fail_first_unlink(path: object, *, dir_fd: int | None = None) -> None:
            unlink_attempts.append(str(path))
            if str(path) == "first.bin":
                raise PermissionError("synthetic owned unlink failure")
            real_unlink(path, dir_fd=dir_fd)  # type: ignore[arg-type]

        verify.os.unlink = fail_first_unlink
        try:
            try:
                cleanup_session.close()
            except PermissionError as exc:
                check("owned unlink" in str(exc),
                      "wrong cleanup failure surfaced")
            else:
                raise AssertionError("owned unlink failure was swallowed")
        finally:
            verify.os.unlink = real_unlink
        check(unlink_attempts == ["first.bin", "second.bin"] and
              not (cleanup_root / "second.bin").exists(),
              "cleanup stopped before attempting every staged file")
        (cleanup_root / "first.bin").unlink()
        cleanup_root.rmdir()

        primary_source = Path(temp) / "primary-source.bin"
        primary_source.write_bytes(b"primary")
        primary_session = verify.PinnedCopySession(
            "nfl-away-primary-test-", Path(temp)
        )
        primary_root = primary_session.root
        primary_session.add(primary_source, "primary.bin", expected_size=7)

        def fail_primary_unlink(path: object, *, dir_fd: int | None = None) -> None:
            if str(path) == "primary.bin":
                raise PermissionError("secondary cleanup failure")
            real_unlink(path, dir_fd=dir_fd)  # type: ignore[arg-type]

        verify.os.unlink = fail_primary_unlink
        try:
            try:
                with primary_session:
                    raise verify.VirtualVerifyError("primary verification failure")
            except verify.VirtualVerifyError as exc:
                check(str(exc) == "primary verification failure",
                      "cleanup masked the primary exception")
            else:
                raise AssertionError("primary verification failure was swallowed")
        finally:
            verify.os.unlink = real_unlink
        (primary_root / "primary.bin").unlink()
        primary_root.rmdir()

        # A pathname swap at close must be reported, and cleanup must not
        # remove the replacement directory.  The original directory fd still
        # lets close() remove its owned leaf without trusting either pathname.
        swap_close_source = Path(temp) / "swap-close-source.bin"
        swap_close_source.write_bytes(b"swap-close")
        swap_close_session = verify.PinnedCopySession(
            "nfl-away-swap-close-test-", Path(temp)
        )
        swap_close_root = swap_close_session.root
        swap_close_session.add(
            swap_close_source, "owned.bin", expected_size=10
        )
        moved_close_root = Path(temp) / "swap-close-opened"
        swap_close_root.rename(moved_close_root)
        swap_close_root.mkdir(mode=0o700)
        try:
            try:
                swap_close_session.close()
            except verify.VirtualVerifyError as exc:
                check("directory changed before cleanup" in str(exc),
                      "wrong close-time root-swap rejection reason")
            else:
                raise AssertionError("close-time staging-root swap was accepted")
            check(swap_close_root.is_dir(),
                  "cleanup removed an unowned replacement directory")
            check(not (moved_close_root / "owned.bin").exists(),
                  "cleanup failed to unlink its descriptor-bound owned leaf")
        finally:
            swap_close_root.rmdir()
            moved_close_root.rmdir()

        preview_payloads = {"a.png": b"preview-a", "b.png": b"preview-bb"}
        exact_previews = Path(temp) / "previews-exact"
        write_preview_set(exact_previews, preview_payloads)
        verify.validate_retained_previews(exact_previews, preview_payloads)

        # A cleanup failure is surfaced on an otherwise successful preview
        # read, but cannot replace the primary verification exception.
        close_error_previews = Path(temp) / "previews-close-error"
        write_preview_set(close_error_previews, preview_payloads)
        real_close = verify.os.close
        fail_next_close = True

        def close_then_fail(descriptor: int) -> None:
            nonlocal fail_next_close
            real_close(descriptor)
            if fail_next_close:
                fail_next_close = False
                raise PermissionError("synthetic preview close failure")

        verify.os.close = close_then_fail
        try:
            try:
                verify.validate_retained_previews(
                    close_error_previews, preview_payloads
                )
            except PermissionError as exc:
                check("preview close" in str(exc),
                      "wrong successful-preview cleanup error")
            else:
                raise AssertionError("preview cleanup error was swallowed")
        finally:
            verify.os.close = real_close

        primary_close_previews = Path(temp) / "previews-primary-close"
        write_preview_set(primary_close_previews, preview_payloads)
        primary_directory_fd = -1

        def remember_preview_directory(descriptor: int) -> None:
            nonlocal primary_directory_fd
            primary_directory_fd = descriptor

        def fail_preview_before_open(_name: str, _descriptor: int) -> None:
            raise verify.VirtualVerifyError("primary preview verification failure")

        def fail_directory_close(descriptor: int) -> None:
            real_close(descriptor)
            if descriptor == primary_directory_fd:
                raise PermissionError("secondary preview close failure")

        verify.os.close = fail_directory_close
        try:
            try:
                verify.validate_retained_previews(
                    primary_close_previews, preview_payloads,
                    after_directory_open=remember_preview_directory,
                    before_file_open=fail_preview_before_open,
                )
            except verify.VirtualVerifyError as exc:
                check(str(exc) == "primary preview verification failure",
                      "preview cleanup masked the primary exception")
            else:
                raise AssertionError("primary preview failure was swallowed")
        finally:
            verify.os.close = real_close

        preview_alias = Path(temp) / "preview-external-alias.png"
        preview_alias.hardlink_to(exact_previews / "a.png")
        try:
            verify.validate_retained_previews(exact_previews, preview_payloads)
        except verify.VirtualVerifyError as exc:
            check("type/link/size differs" in str(exc),
                  "wrong preview-hardlink rejection reason")
        else:
            raise AssertionError("hardlinked retained preview was accepted")
        preview_alias.unlink()

        replacement_previews = Path(temp) / "previews-replacement"
        write_preview_set(replacement_previews, preview_payloads)
        replacement_done = False

        def replace_before_open(name: str, directory_fd: int) -> None:
            nonlocal replacement_done
            if replacement_done or name != "a.png":
                return
            replacement_done = True
            os.rename("a.png", "a-old.png", src_dir_fd=directory_fd,
                      dst_dir_fd=directory_fd)
            descriptor = os.open(
                "a.png", os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600, dir_fd=directory_fd,
            )
            try:
                os.write(descriptor, preview_payloads["a.png"])
            finally:
                os.close(descriptor)

        try:
            verify.validate_retained_previews(
                replacement_previews, preview_payloads,
                before_file_open=replace_before_open,
            )
        except verify.VirtualVerifyError as exc:
            check("changed while opening" in str(exc),
                  "wrong preview-replacement rejection reason")
        else:
            raise AssertionError("retained preview replacement was accepted")

        swap_previews = Path(temp) / "previews-swap"
        moved_previews = Path(temp) / "previews-swap-opened"
        write_preview_set(swap_previews, preview_payloads)

        def swap_directory(_directory_fd: int) -> None:
            swap_previews.rename(moved_previews)
            write_preview_set(swap_previews, preview_payloads)

        try:
            verify.validate_retained_previews(
                swap_previews, preview_payloads,
                after_directory_open=swap_directory,
            )
        except verify.VirtualVerifyError as exc:
            check("directory identity/path changed" in str(exc),
                  "wrong preview-directory-swap rejection reason")
        else:
            raise AssertionError("retained preview directory swap was accepted")
        expected = source[:8] + after + source[16:]
        check(result["source_sha256"] == hashlib.sha256(source).hexdigest(),
              "synthetic source hash differs")
        check(result["virtual_sha256"] == hashlib.sha256(expected).hexdigest(),
              "synthetic virtual hash differs")
        check(result["relative_differences"] == [1, 3, 5, 7],
              "synthetic difference ledger differs")
        check(result["runs"] == [(1, 1), (3, 3), (5, 5), (7, 7)],
              "synthetic run ledger differs")

        tampered = Path(temp) / "tampered.bin"
        tampered.write_bytes(source[:11] + b"Q" + source[12:])
        descriptor = os.open(tampered, os.O_RDONLY)
        try:
            try:
                verify.scan_virtual_image(
                    descriptor, len(source), 8, before, after, chunk_size=5
                )
            except verify.VirtualVerifyError as exc:
                check("retail bytes differ" in str(exc),
                      "wrong streamed source-tamper reason")
            else:
                raise AssertionError("streamed source tamper was accepted")
        finally:
            os.close(descriptor)

    print(
        "NFL_AWAY_LOADER_SAFE_VIRTUAL_XISO_TEST_PASS "
        "materialized_diagnostic_honest=yes "
        "split_overlay=yes unrelated_identity=yes source_tamper_refused=yes "
        "stream_hash=yes diff_ledger=yes streamed_tamper_refused=yes "
        "parent_symlink_refused=yes canonical_nlink2_staged=yes "
        "open_input_interrupt_clean=yes "
        "unexpected_hardlink_refused=yes report_image_alias_refused=yes "
        "constructor_interrupt_clean=yes copy_interrupt_clean=yes "
        "late_root_failure_clean=yes "
        "cleanup_errors_reported=yes cleanup_continues=yes "
        "primary_error_preserved=yes "
        "close_root_swap_refused=yes close_replacement_preserved=yes "
        "preview_close_error_reported=yes preview_primary_preserved=yes "
        "preview_hardlink_refused=yes preview_replacement_refused=yes "
        "preview_directory_swap_refused=yes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

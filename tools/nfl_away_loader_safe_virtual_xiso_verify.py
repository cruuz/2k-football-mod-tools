#!/usr/bin/env python3
"""Reconstruct and verify the deleted loader-safe AWAY XISO as a virtual image.

The historical XISO is not recreated.  This verifier pins the retail inputs,
deterministically rebuilds the exact 09A0 fixed span in memory, and streams a
virtual one-span overlay across the retail XISO.  It proves the frozen output
hash and difference ledgers while leaving the filesystem and runtime evidence
unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
from typing import Any, Callable

import nfl_uniform_color_xiso_direct_verify as xdvdfs
from nfl_jersey_tset_png_import import import_png
from nfl_jersey_tset_targets import select_target
from nfl_tset_loader_alias_audit import alias_decode, token_requirements
from nfl_txtr import HEADER, decompress_vc_lz


SCHEMA = "nfl2k5_away_loader_safe_virtual_xiso_verify/v1"
IMAGE_SIZE = 6_300_499_968
SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
VIRTUAL_OUTPUT_SHA256 = "5e8cf7c36c511878e5d5073fe96d757c1e21de08a360a5ca15f5ec7584242f2d"
INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
INVENTORY_SIZE = 55_746_414
INVENTORY_SHA256 = "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac"
COMPATIBILITY_SIZE = 2_155_807
COMPATIBILITY_SHA256 = "ba54bc19604f5cc2ca80d6524f3b2fb93d66924ddf0d3704132578f4ae33ee82"
PNG_SIZE = 2_598
PNG_SHA256 = "6ae65b7c4f982fbadb6da20444b21d7a2bb3c13f28a84b22c612967dc8a8f3c8"
PACK_INPUTS: dict[str, tuple[int, str, int]] = {
    "0": (193_710_080, INDEX_SHA256, 2),
    "1": (299_999_232, "40dedc28bb6f8fc8644534857e857ca944f0c3c1614323cc66f3b45554cdfb54", 2),
    "2": (309_252_096, "21e00e0f41b3e016e416c44f3e1f3a07f9d5d7fdb5b9fe586685fadceb335886", 2),
    "3": (315_508_736, "921a139a9fd1a9470cc77f78455a6282e426376d4c201635b97a512d1f947aa7", 2),
    "4": (313_178_112, "94e6f16dc53fe6e06a6357ecd23879244e6dd1854bd1b222e3a985f4611bf487", 2),
    "5": (307_972_096, "20d58c635bdccc9c66fae73defeb580fb5280e45a4c9bd4d6f70c4e389d3b811", 2),
    "6": (458_231_808, "6d8f0c24e9997938a48a7f47d6c1c179b013a4ed2d9d4121d76244a0762ec17a", 2),
    "7": (319_197_184, "e3bc7609dc173bfba9ddcbfc103ae44e140bf159d0d9fd7599cf9a7c2df209c7", 2),
    "8": (929_370_112, "265560a55bebc13e5c8bfbe7770dac2032624946b4767fad72191bb3266aca14", 1),
    "9": (634_941_440, "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a", 1),
    "A": (310_294_528, "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b", 1),
    "B": (458_248_192, "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614", 1),
    "C": (315_131_904, "ce3af83768640230499f10d1d0a9799fc9ea56809a8a8a788679c78744f54090", 2),
    "D": (309_135_360, "dbf286add93d3b032822597bcbf5a1dfc58eaf3fe4d8ef63d1d77686c02f1ae2", 2),
    "E": (301_813_760, "ca858b2afa8ea0c0787379366c8fc88d65fb9ef6d55f809e1da2319558de2400", 2),
    "F": (451_733_504, "376f2d0ea4a5c01453408fbd9747bffbfb8715b56a7e3f41339158217b07da8d", 2),
}
SPAN_OFFSET = 4_718_884_976
SPAN_SIZE = 79_120
SOURCE_SPAN_SHA256 = "5da01c3440daae955f94a19cdeeeb47c6858090de114dc67128366c37675d4ec"
REPLACEMENT_SPAN_SHA256 = "12b4ffd5f6926a3c404190262e0a8c19d6c3335cd046b9dfff79797a05016766"
DECODED_SHA256 = "f5ed9101fa5c8bb742168b18fac698f57185c6b6a0190545ecafc1bb1b99c30e"
IMPORT_MANIFEST_SHA256 = "146b320388c05c6135a437fadb3a54a07bc8a2e673b3c79b19b740fedafa365e"
PACK_B_OFFSET = 2_179_328 * 2_048
PACK_B_SIZE = 458_248_192
SOURCE_PACK_B_SHA256 = "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614"
VIRTUAL_PACK_B_SHA256 = "a2353dee32db56cc2e8d8ac816ffe184a91af1978c6bf02ea75b28fa694386ce"
CHANGED_BYTES = 74_705
CHANGED_RUNS = 3_605
RELATIVE_OFFSETS_SHA256 = "e544eeff25ebb3fddca738a7d8af6e538d13a773f25888138af58b652b0a5968"
RELATIVE_RUNS_SHA256 = "ae2e4eb916aeb79dd5b913f3843400b896689b3577b5d3988b61f48c0c77528a"
ABSOLUTE_OFFSETS_SHA256 = "eaf9bda31d9181cfa492a6e75299c0dc6435012b9bd8fffaa6facdfcd5d6dbc5"
CHUNK = 16 * 1024 * 1024

PREVIEW_SHA256 = {
    "clean_mip0_512x256.png": "6ae65b7c4f982fbadb6da20444b21d7a2bb3c13f28a84b22c612967dc8a8f3c8",
    "clean_mip1_256x128.png": "fe86ef34d66464f24850326b582ff39785295d839d757edc79db5383546b21cd",
    "clean_mip2_128x64.png": "dc1d2c4a5d93b5d0e9986345d6f34ae8732b6116a45ed9ef02fa2a4732cfdbe7",
    "clean_mip3_64x32.png": "0dd5d769a5832431ede9fb83378db23f63247ff285afca6ad404590b4a880e98",
    "clean_mip4_32x16.png": "dbaca95db3fda150ca5ed699f87cb8e476cd213d4671bea0022115c3519f09e4",
    "clean_mip5_16x8.png": "11672dc394ecbbbc46f2182ccfd83eb5f63bf95a10ecd98d111e72d5787174db",
    "mud_mip0_512x256.png": "2fb8d0ae35c1a012b36c6f5bbfcfc369375750446c21a070b291a8a3026defc4",
    "mud_mip1_256x128.png": "ba1988eeb637240587aa62f029672cf6e48ae633900eb3724a66af936bef1a0b",
    "mud_mip2_128x64.png": "5832cc5ffca07bf285921864109c133a8fb491debd4fedd7ce19d0cb5cd15be6",
    "mud_mip3_64x32.png": "e6a272d06f0cf7159700b55398b0babea4ef94cc5ebca3c7066559bfc8599944",
    "mud_mip4_32x16.png": "bb62aae8e8e531caf8a9635e77c346c47c785d566f25133ea7433f053897a704",
    "mud_mip5_16x8.png": "2f814cb83128f728f3e55a4ba0005bd2d9a3dab1875b10d098b991917ea6e2df",
}


class VirtualVerifyError(ValueError):
    """A pinned input, reconstruction, or virtual-image invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VirtualVerifyError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require_no_symlink_components(path: Path, *, missing_tail_ok: bool = False) \
        -> None:
    require(".." not in path.parts, f"pinned path contains '..': {path}")
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor)
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    for index, component in enumerate(parts):
        current /= component
        try:
            info = current.lstat()
        except FileNotFoundError:
            require(missing_tail_ok,
                    f"pinned path component is unavailable: {current}")
            return
        require(not stat.S_ISLNK(info.st_mode),
                f"pinned path component is a symlink: {current}")


def hash_fd(descriptor: int, size: int) -> str:
    digest = hashlib.sha256()
    position = 0
    while position < size:
        payload = os.pread(descriptor, min(CHUNK, size - position), position)
        require(bool(payload), f"short input read at 0x{position:x}")
        digest.update(payload)
        position += len(payload)
    return digest.hexdigest()


FileIdentity = tuple[int, int, int, int, int, int, int]


def file_identity(info: os.stat_result) -> FileIdentity:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
        info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )


def open_input(path: Path, size: int | None, expected_sha256: str | None,
               *, expected_nlink: int = 1) \
        -> tuple[int, FileIdentity]:
    require_no_symlink_components(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode),
            f"input is not a non-symlink regular file: {path}")
    require(before.st_nlink == expected_nlink,
            f"input link count differs: {path}")
    if size is not None:
        require(before.st_size == size, f"input size differs: {path}")
    identity = file_identity(before)
    descriptor = -1
    try:
        # Acquire inside the cleanup region.  In particular, a Ctrl-C between
        # os.open() and the first identity check must not strand the fd.
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
            getattr(os, "O_CLOEXEC", 0),
        )
        opened = os.fstat(descriptor)
        require(file_identity(opened) == identity,
                f"input changed while opening: {path}")
        if expected_sha256 is not None:
            require(hash_fd(descriptor, opened.st_size) == expected_sha256,
                    f"input SHA-256 differs: {path}")
        return descriptor, identity
    except BaseException:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException:
                pass
        raise


def require_stable(path: Path, descriptor: int,
                   identity: FileIdentity) -> None:
    opened = os.fstat(descriptor)
    current = path.lstat()
    require(file_identity(opened) == file_identity(current) == identity,
            f"input identity changed during verification: {path}")


class PinnedCopySession:
    """Hold original descriptors and expose only private, single-link copies."""

    def __init__(self, prefix: str, parent: Path | None = None):
        if parent is not None:
            require_no_symlink_components(parent)
            parent_info = parent.lstat()
            require(stat.S_ISDIR(parent_info.st_mode),
                    f"staging parent is not a directory: {parent}")
        self._originals: list[
            tuple[Path, int, FileIdentity, str]
        ] = []
        self._staged: dict[str, tuple[int, FileIdentity, str]] = {}
        self._original_inodes: set[tuple[int, int]] = set()
        self._closed = True

        root: Path | None = None
        root_identity: FileIdentity | None = None
        directory_fd = -1
        try:
            # tempfile.mkdtemp() creates the directory mode 0700.  Requiring
            # that mode instead of reopening the pathname for chmod keeps the
            # constructor bound to the inode it just observed.
            root = Path(tempfile.mkdtemp(
                prefix=prefix, dir=None if parent is None else str(parent)
            ))
            root_info = root.lstat()
            root_identity = file_identity(root_info)
            require(stat.S_ISDIR(root_info.st_mode) and
                    stat.S_IMODE(root_info.st_mode) == 0o700,
                    "private staging directory mode/type differs")
            directory_fd = os.open(
                root,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                getattr(os, "O_NOFOLLOW", 0) |
                getattr(os, "O_CLOEXEC", 0),
            )
            require(file_identity(os.fstat(directory_fd)) == root_identity,
                    "private staging directory changed while opening")
        except BaseException:
            if directory_fd >= 0:
                try:
                    os.close(directory_fd)
                except BaseException:
                    pass
            if root is not None and root_identity is not None:
                try:
                    current = root.lstat()
                    if (current.st_dev, current.st_ino) == root_identity[:2]:
                        root.rmdir()
                except BaseException:
                    pass
            raise

        assert root is not None and root_identity is not None and directory_fd >= 0
        self.root = root
        self._root_identity = root_identity
        self._dir_fd = directory_fd
        self._closed = False

    def _checked_current_root_identity(self) -> FileIdentity:
        """Return the current root identity only when path and fd still agree."""
        current = self.root.lstat()
        current_identity = file_identity(current)
        opened_identity = file_identity(os.fstat(self._dir_fd))
        require(current_identity[:2] == self._root_identity[:2] and
                opened_identity == current_identity and
                stat.S_ISDIR(current.st_mode) and
                stat.S_IMODE(current.st_mode) == 0o700,
                "private staging directory changed while adding a copy")
        return current_identity

    @staticmethod
    def _record_cleanup_error(errors: list[BaseException] | None,
                              error: BaseException) -> None:
        if errors is not None:
            errors.append(error)

    def _unlink_owned_stage(
        self,
        stage_name: str,
        inode: tuple[int, int] | None,
        errors: list[BaseException] | None = None,
    ) -> None:
        if inode is None or self._dir_fd < 0:
            return
        try:
            current = os.stat(
                stage_name, dir_fd=self._dir_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            if errors is not None:
                errors.append(VirtualVerifyError(
                    f"private staged copy disappeared during cleanup: {stage_name}"
                ))
            return
        except BaseException as exc:
            self._record_cleanup_error(errors, exc)
            return
        if (current.st_dev, current.st_ino) != inode:
            if errors is not None:
                errors.append(VirtualVerifyError(
                    f"private staged copy identity changed during cleanup: {stage_name}"
                ))
            return
        try:
            os.unlink(stage_name, dir_fd=self._dir_fd)
        except FileNotFoundError:
            if errors is not None:
                errors.append(VirtualVerifyError(
                    f"private staged copy disappeared during cleanup: {stage_name}"
                ))
        except BaseException as exc:
            self._record_cleanup_error(errors, exc)

    @staticmethod
    def _close_noexcept(descriptor: int) -> None:
        if descriptor < 0:
            return
        try:
            os.close(descriptor)
        except BaseException:
            pass

    @staticmethod
    def _close_collect(descriptor: int,
                       errors: list[BaseException]) -> None:
        if descriptor < 0:
            return
        try:
            os.close(descriptor)
        except BaseException as exc:
            errors.append(exc)

    def add(self, path: Path, stage_name: str, *,
            expected_size: int | None = None,
            expected_sha256: str | None = None,
            expected_nlink: int = 1) -> Path:
        require(not self._closed, "private staging session is closed")
        require(stage_name not in self._staged and stage_name not in ("", ".", "..") and
                Path(stage_name).name == stage_name and "/" not in stage_name and
                "\\" not in stage_name,
                f"unsafe or duplicate private stage name: {stage_name!r}")
        descriptor = -1
        identity: FileIdentity | None = None
        inode: tuple[int, int] | None = None
        staged_fd = -1
        stage_created = False
        stage_inode: tuple[int, int] | None = None
        output = -1
        original_registered = False
        staged_registered = False
        inode_registered = False
        try:
            # Pin inside this transaction so every BaseException after the
            # descriptor is acquired reaches the rollback below.
            descriptor, identity = open_input(
                path, expected_size, None,
                expected_nlink=expected_nlink,
            )
            inode = (identity[0], identity[1])
            require(inode not in self._original_inodes,
                    f"private-copy inputs alias one inode: {path}")
            size = identity[4]
            digest_state = hashlib.sha256()
            output = os.open(
                stage_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=self._dir_fd,
            )
            stage_created = True
            created_info = os.fstat(output)
            stage_inode = (created_info.st_dev, created_info.st_ino)
            try:
                position = 0
                while position < size:
                    payload = os.pread(descriptor, min(CHUNK, size - position), position)
                    require(bool(payload), f"short private-copy source read: {path}")
                    digest_state.update(payload)
                    written = 0
                    while written < len(payload):
                        count = os.write(output, payload[written:])
                        require(count > 0, f"short private-copy write: {stage_name}")
                        written += count
                    position += len(payload)
                os.fsync(output)
                os.fchmod(output, 0o400)
            except BaseException:
                self._close_noexcept(output)
                output = -1
                raise
            else:
                try:
                    os.close(output)
                finally:
                    output = -1
            digest = digest_state.hexdigest()
            if expected_sha256 is not None:
                require(digest == expected_sha256,
                        f"private-copy source SHA-256 differs: {path}")
            staged_fd = os.open(
                stage_name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                getattr(os, "O_CLOEXEC", 0),
                dir_fd=self._dir_fd,
            )
            staged_info = os.fstat(staged_fd)
            staged_path_info = os.stat(
                stage_name, dir_fd=self._dir_fd, follow_symlinks=False
            )
            staged_identity = file_identity(staged_info)
            require(staged_identity == file_identity(staged_path_info) and
                    stat.S_ISREG(staged_info.st_mode) and
                    stat.S_IMODE(staged_info.st_mode) == 0o400 and
                    staged_info.st_nlink == 1 and staged_info.st_size == size,
                    f"private staged copy identity/bytes differ: {stage_name}")
            new_root_identity = self._checked_current_root_identity()
            result_path = self.root / stage_name

            # Commit ownership only after every fallible copy/root check.  If a
            # container operation itself fails, the rollback below removes any
            # partial registrations before closing the still-local fds.
            original_registered = True
            self._originals.append((path, descriptor, identity, digest))
            staged_registered = True
            self._staged[stage_name] = (staged_fd, staged_identity, digest)
            inode_registered = True
            self._original_inodes.add(inode)
            self._root_identity = new_root_identity
            return result_path
        except BaseException:
            if inode_registered and inode is not None:
                self._original_inodes.discard(inode)
            if staged_registered:
                self._staged.pop(stage_name, None)
            if original_registered and self._originals and \
                    self._originals[-1][1] == descriptor:
                self._originals.pop()
            if stage_inode is None and output >= 0:
                try:
                    created_info = os.fstat(output)
                    stage_inode = (created_info.st_dev, created_info.st_ino)
                except OSError:
                    pass
            self._close_noexcept(output)
            self._close_noexcept(staged_fd)
            if stage_created or stage_inode is not None:
                self._unlink_owned_stage(stage_name, stage_inode)
            self._close_noexcept(descriptor)

            # A failed add may have created and removed a leaf, changing only
            # the directory timestamps. Refresh them when the trusted path and
            # descriptor still name the same staging inode so the caller may
            # safely close or reuse the session.
            try:
                current = self.root.lstat()
                current_identity = file_identity(current)
                if (current_identity[:2] == self._root_identity[:2] and
                        file_identity(os.fstat(self._dir_fd)) == current_identity):
                    self._root_identity = current_identity
            except BaseException:
                pass
            raise

    def validate(self) -> None:
        require(not self._closed, "private staging session is closed")
        require(set(os.listdir(self._dir_fd)) == set(self._staged),
                "private staging file set differs")
        for path, descriptor, identity, digest in self._originals:
            require_stable(path, descriptor, identity)
            require(hash_fd(descriptor, identity[4]) == digest,
                    f"private-copy source bytes changed: {path}")
        for name, (descriptor, identity, digest) in self._staged.items():
            opened = os.fstat(descriptor)
            current = os.stat(name, dir_fd=self._dir_fd, follow_symlinks=False)
            require(file_identity(opened) == file_identity(current) == identity and
                    opened.st_nlink == 1 and stat.S_ISREG(opened.st_mode) and
                    stat.S_IMODE(opened.st_mode) == 0o400 and
                    hash_fd(descriptor, opened.st_size) == digest,
                    f"private staged copy changed: {name}")
        current_root = self.root.lstat()
        require(file_identity(os.fstat(self._dir_fd)) ==
                file_identity(current_root) == self._root_identity and
                stat.S_IMODE(current_root.st_mode) == 0o700,
                "private staging directory identity changed")

    def close(self, *, suppress_errors: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        errors: list[BaseException] = []
        root_owned = False
        try:
            current_root = self.root.lstat()
            current_identity = file_identity(current_root)
            opened_identity = file_identity(os.fstat(self._dir_fd))
            root_owned = (
                current_identity == opened_identity == self._root_identity and
                stat.S_ISDIR(current_root.st_mode) and
                stat.S_IMODE(current_root.st_mode) == 0o700
            )
            if not root_owned:
                errors.append(VirtualVerifyError(
                    "private staging directory changed before cleanup"
                ))
        except FileNotFoundError:
            errors.append(VirtualVerifyError(
                "private staging directory disappeared before cleanup"
            ))
        except BaseException as exc:
            errors.append(exc)
        for _path, descriptor, _identity, _digest in self._originals:
            self._close_collect(descriptor, errors)
        for name, (descriptor, identity, _digest) in self._staged.items():
            self._close_collect(descriptor, errors)
            self._unlink_owned_stage(name, identity[:2], errors)
        self._originals.clear()
        self._staged.clear()
        self._original_inodes.clear()
        self._close_collect(self._dir_fd, errors)
        self._dir_fd = -1
        try:
            if root_owned:
                # Recheck immediately before the path-based rmdir.  The child
                # leaves changed directory timestamps, so the inode/type/mode
                # (rather than the pre-cleanup timestamp tuple) is authoritative
                # at this point.
                final_root = self.root.lstat()
                if ((final_root.st_dev, final_root.st_ino) !=
                        self._root_identity[:2] or
                        not stat.S_ISDIR(final_root.st_mode) or
                        stat.S_IMODE(final_root.st_mode) != 0o700):
                    errors.append(VirtualVerifyError(
                        "private staging directory changed during cleanup"
                    ))
                else:
                    self.root.rmdir()
        except FileNotFoundError:
            errors.append(VirtualVerifyError(
                "private staging directory disappeared during cleanup"
            ))
        except BaseException as exc:
            errors.append(exc)
        if errors and not suppress_errors:
            raise errors[0]

    def __enter__(self) -> "PinnedCopySession":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc_type is not None:
            self.close(suppress_errors=True)
            return
        try:
            self.validate()
        except BaseException:
            self.close(suppress_errors=True)
            raise
        self.close()


PreviewHook = Callable[[str, int], None]
DirectoryHook = Callable[[int], None]


def validate_retained_previews(
    directory: Path,
    expected_payloads: dict[str, bytes],
    *,
    after_directory_open: DirectoryHook | None = None,
    before_file_open: PreviewHook | None = None,
) -> None:
    """Validate a closed preview set through one stable directory descriptor."""
    require_no_symlink_components(directory)
    before = directory.lstat()
    require(stat.S_ISDIR(before.st_mode) and not stat.S_ISLNK(before.st_mode),
            "historical previews path is not a real directory")
    directory_identity = file_identity(before)
    descriptor = -1
    try:
        descriptor = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
            getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        require(file_identity(os.fstat(descriptor)) == directory_identity,
                "historical preview directory changed while opening")
        if after_directory_open is not None:
            after_directory_open(descriptor)
        expected_names = set(expected_payloads)
        require(set(os.listdir(descriptor)) == expected_names,
                "historical preview name set differs")
        for name in sorted(expected_names):
            require(name not in ("", ".", "..") and Path(name).name == name,
                    f"unsafe historical preview name: {name!r}")
            expected = expected_payloads[name]
            leaf_before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            require(stat.S_ISREG(leaf_before.st_mode) and
                    not stat.S_ISLNK(leaf_before.st_mode) and
                    leaf_before.st_nlink == 1 and
                    leaf_before.st_size == len(expected),
                    f"historical preview type/link/size differs: {name}")
            leaf_identity = file_identity(leaf_before)
            if before_file_open is not None:
                before_file_open(name, descriptor)
            leaf_fd = -1
            try:
                leaf_fd = os.open(
                    name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                    getattr(os, "O_CLOEXEC", 0),
                    dir_fd=descriptor,
                )
                opened = os.fstat(leaf_fd)
                require(file_identity(opened) == leaf_identity,
                        f"historical preview changed while opening: {name}")
                payload = pread_exact(leaf_fd, 0, len(expected))
                require(os.pread(leaf_fd, 1, len(expected)) == b"" and
                        payload == expected,
                        f"historical preview bytes differ: {name}")
                after = os.fstat(leaf_fd)
                current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                require(file_identity(after) == file_identity(current) == leaf_identity,
                        f"historical preview changed during read: {name}")
            finally:
                active_exception = sys.exc_info()[0] is not None
                if leaf_fd >= 0:
                    try:
                        os.close(leaf_fd)
                    except BaseException:
                        if not active_exception:
                            raise
        require(set(os.listdir(descriptor)) == expected_names,
                "historical preview name set changed during validation")
        current_directory = directory.lstat()
        require(file_identity(os.fstat(descriptor)) ==
                file_identity(current_directory) == directory_identity,
                "historical preview directory identity/path changed")
    finally:
        active_exception = sys.exc_info()[0] is not None
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException:
                if not active_exception:
                    raise


def pread_exact(descriptor: int, offset: int, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        payload = os.pread(descriptor, size - len(result), offset + len(result))
        require(bool(payload), f"short image read at 0x{offset + len(result):x}")
        result.extend(payload)
    return bytes(result)


def virtualize_chunk(payload: bytes, position: int, patch_offset: int,
                     source_span: bytes, replacement_span: bytes) -> bytes:
    require(len(source_span) == len(replacement_span) > 0,
            "virtual source/replacement span sizes differ")
    require(position >= 0 and patch_offset >= 0,
            "virtual chunk/span offset is negative")
    result = bytearray(payload)
    overlap_start = max(position, patch_offset)
    overlap_end = min(position + len(payload), patch_offset + len(source_span))
    if overlap_start < overlap_end:
        chunk_start = overlap_start - position
        span_start = overlap_start - patch_offset
        length = overlap_end - overlap_start
        require(payload[chunk_start:chunk_start + length] ==
                source_span[span_start:span_start + length],
                f"retail bytes differ at virtual span 0x{patch_offset:x}")
        result[chunk_start:chunk_start + length] = \
            replacement_span[span_start:span_start + length]
    return bytes(result)


def scan_virtual_image(descriptor: int, image_size: int, patch_offset: int,
                       source_span: bytes, replacement_span: bytes,
                       chunk_size: int = CHUNK) -> dict[str, Any]:
    require(chunk_size > 0 and patch_offset + len(source_span) <= image_size,
            "virtual span is outside the image")
    source_digest = hashlib.sha256()
    virtual_digest = hashlib.sha256()
    relative_differences: list[int] = []
    position = 0
    while position < image_size:
        payload = pread_exact(descriptor, position,
                              min(chunk_size, image_size - position))
        virtual = virtualize_chunk(
            payload, position, patch_offset, source_span, replacement_span
        )
        source_digest.update(payload)
        virtual_digest.update(virtual)
        if payload != virtual:
            relative_differences.extend(
                position + index - patch_offset
                for index, (old, new) in enumerate(zip(payload, virtual))
                if old != new
            )
        position += len(payload)
    runs: list[tuple[int, int]] = []
    for offset in relative_differences:
        if not runs or offset != runs[-1][1] + 1:
            runs.append((offset, offset))
        else:
            start, _end = runs[-1]
            runs[-1] = (start, offset)
    return {
        "source_sha256": source_digest.hexdigest(),
        "virtual_sha256": virtual_digest.hexdigest(),
        "relative_differences": relative_differences,
        "runs": runs,
    }


def hash_virtual_extent(descriptor: int, offset: int, size: int,
                        patch_offset: int, source_span: bytes,
                        replacement_span: bytes) -> str:
    digest = hashlib.sha256()
    position = 0
    while position < size:
        absolute = offset + position
        payload = pread_exact(descriptor, absolute, min(CHUNK, size - position))
        digest.update(virtualize_chunk(
            payload, absolute, patch_offset, source_span, replacement_span
        ))
        position += len(payload)
    return digest.hexdigest()


def packed_hash(values: list[int] | list[tuple[int, int]], width: int) -> str:
    digest = hashlib.sha256()
    if values and isinstance(values[0], tuple):
        for start, end in values:  # type: ignore[misc]
            digest.update(struct.pack("<II", start, end))
    else:
        for value in values:  # type: ignore[assignment]
            digest.update(struct.pack("<I" if width == 4 else "<Q", value))
    return digest.hexdigest()


def canonical_manifest(report: dict[str, object]) -> bytes:
    return (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    require_no_symlink_components(args.historical_output, missing_tail_ok=True)
    require(not args.historical_output.exists() and
            not args.historical_output.is_symlink(),
            "virtual mode requires the historical output to be absent")
    source_fd = -1
    source_identity: FileIdentity | None = None
    staging: PinnedCopySession | None = None
    try:
        source_fd, source_identity = open_input(
            args.source, IMAGE_SIZE, None, expected_nlink=1
        )
        staging = PinnedCopySession("nfl-away-import-")
        staged_index: Path | None = None
        for pack_name, (pack_size, pack_sha256, pack_nlink) in PACK_INPUTS.items():
            source_pack = args.index if pack_name == "0" else args.index.parent / pack_name
            staged_pack = staging.add(
                source_pack, pack_name, expected_size=pack_size,
                expected_sha256=pack_sha256, expected_nlink=pack_nlink,
            )
            if pack_name == "0":
                staged_index = staged_pack
        require(staged_index is not None, "private staged index is absent")
        staged_inventory = staging.add(
            args.inventory, "nfl2k5_resource_chunks_v2.json",
            expected_size=INVENTORY_SIZE, expected_sha256=INVENTORY_SHA256,
            expected_nlink=1,
        )
        staged_compatibility = staging.add(
            args.compatibility, "nfl2k5_jersey_tset_compatibility.json",
            expected_size=COMPATIBILITY_SIZE,
            expected_sha256=COMPATIBILITY_SHA256, expected_nlink=1,
        )
        staged_png = staging.add(
            args.clean_png, args.clean_png.name,
            expected_size=PNG_SIZE, expected_sha256=PNG_SHA256,
            expected_nlink=1,
        )
        *_, target = select_target("09", "A", 0, staged_compatibility)
        replacement, previews, import_report = import_png(
            staged_index, staged_inventory, staged_compatibility, target,
            staged_png, None,
            "darken_60",
        )
        # The path-only importer consumed only private descriptor-derived
        # copies. Restore the frozen logical provenance labels before requiring
        # the exact historical canonical-manifest digest.
        import_report["source_index"] = str(args.index)
        import_report["canonical_inventory"] = str(args.inventory)
        import_report["compatibility_report"]["path"] = str(args.compatibility)
        import_report["input"]["clean"]["file_name"] = args.clean_png.name
        import_report["outputs"] = {
            "span_file": "replacement.tset.bin",
            "manifest_file": "import.json",
            "preview_directory": "import-previews",
            "preview_file_count": 12,
        }
        import_payload = canonical_manifest(import_report)
        require(sha256_bytes(import_payload) == IMPORT_MANIFEST_SHA256,
                "reconstructed import manifest differs")
        require(len(replacement) == SPAN_SIZE and
                sha256_bytes(replacement) == REPLACEMENT_SPAN_SHA256,
                "reconstructed replacement span differs")
        preview_payloads = dict(previews)
        require(set(preview_payloads) == set(PREVIEW_SHA256),
                "reconstructed preview set differs")
        for name, expected_hash in PREVIEW_SHA256.items():
            require(sha256_bytes(preview_payloads[name]) == expected_hash,
                    f"reconstructed preview differs: {name}")
        validate_retained_previews(args.historical_previews, preview_payloads)

        source_span = pread_exact(source_fd, SPAN_OFFSET, SPAN_SIZE)
        require(sha256_bytes(source_span) == SOURCE_SPAN_SHA256,
                "retail source span differs")
        require(HEADER.unpack_from(source_span) ==
                (b"TSET", 79_088, 256, 176_768, 0xFEEDBEEF, 16, 0, 0),
                "retail source wrapper differs")
        require(HEADER.unpack_from(replacement) ==
                (b"TSET", 79_088, 256, 176_768, 0xFEEDBEEF, 56_816, 0, 0),
                "replacement wrapper differs")
        decoded, decode_info = decompress_vc_lz(replacement[HEADER.size:], 177_024)
        require(sha256_bytes(decoded) == DECODED_SHA256 and
                decode_info.consumed_bytes == 22_285,
                "replacement independent decode differs")
        requirements = token_requirements(
            replacement[HEADER.size:], 177_024, 79_088
        )
        require(requirements["exact_minimum_scratch_bytes"] == 56_792,
                "replacement alias minimum differs")
        alias = alias_decode(
            replacement[HEADER.size:], 177_024, 79_088, 56_816,
            decode_info.consumed_bytes,
        )
        require(alias["output_sha256"] == DECODED_SHA256 and
                alias["first_unread_source_collision"] is None and
                alias["first_invalid_match"] is None,
                "replacement is not loader-alias safe")

        entries, root, directories = xdvdfs.parse_xdvdfs(source_fd, IMAGE_SIZE)
        xdvdfs.validate_expected_entries(entries)
        require(root == (33, 108) and
                directories == [(33, 108), (35_530, 2_048)],
                "retail XDVDFS metadata differs")
        pack_b = entries["vc_53450030/b"]
        require(pack_b.offset == PACK_B_OFFSET and pack_b.size == PACK_B_SIZE and
                pack_b.offset <= SPAN_OFFSET and
                SPAN_OFFSET + SPAN_SIZE <= pack_b.offset + pack_b.size,
                "virtual span is not inside pinned pack B")

        scan = scan_virtual_image(
            source_fd, IMAGE_SIZE, SPAN_OFFSET, source_span, replacement
        )
        require(scan["source_sha256"] == SOURCE_SHA256,
                "retail source SHA-256 differs")
        require(scan["virtual_sha256"] == VIRTUAL_OUTPUT_SHA256,
                "virtual output SHA-256 differs")
        differences = scan["relative_differences"]
        runs = scan["runs"]
        require(len(differences) == CHANGED_BYTES and len(runs) == CHANGED_RUNS,
                "virtual difference count/run ledger differs")
        require(packed_hash(differences, 4) == RELATIVE_OFFSETS_SHA256 and
                packed_hash(runs, 4) == RELATIVE_RUNS_SHA256 and
                packed_hash([SPAN_OFFSET + value for value in differences], 8) ==
                ABSOLUTE_OFFSETS_SHA256,
                "virtual difference digest ledger differs")
        require(xdvdfs.hash_extent(source_fd, PACK_B_OFFSET, PACK_B_SIZE) ==
                SOURCE_PACK_B_SHA256 and
                hash_virtual_extent(
                    source_fd, PACK_B_OFFSET, PACK_B_SIZE, SPAN_OFFSET,
                    source_span, replacement,
                ) == VIRTUAL_PACK_B_SHA256,
                "virtual target-pack hash differs")
        xbe = entries["default.xbe"]
        pack0 = entries["vc_53450030/0"]
        require(xdvdfs.hash_extent(source_fd, xbe.offset, xbe.size) ==
                xdvdfs.XBE_SHA256 and
                xdvdfs.hash_extent(source_fd, pack0.offset, pack0.size) ==
                INDEX_SHA256,
                "unrelated retail extent differs")

        staging.validate()
        assert source_identity is not None
        require_stable(args.source, source_fd, source_identity)

        return {
            "schema": SCHEMA,
            "source_sha256": SOURCE_SHA256,
            "virtual_output_sha256": VIRTUAL_OUTPUT_SHA256,
            "output_materialized": False,
            "historical_output_path": str(args.historical_output),
            "target": "09A0",
            "outer_index": 4002,
            "pack": "B",
            "files": 19,
            "mips": 6,
            "previews": 12,
            "stored_size": 79_088,
            "encoded_bytes": 22_285,
            "zero_padding_bytes": 56_803,
            "replacement_span_sha256": REPLACEMENT_SPAN_SHA256,
            "import_manifest_sha256": IMPORT_MANIFEST_SHA256,
            "changed_bytes": CHANGED_BYTES,
            "changed_runs": CHANGED_RUNS,
            "all_other_image_bytes_identical": True,
            "xdvdfs_tree_and_extents_preserved": True,
            "runtime_visibility_proved_by_reconstruction": False,
            "historical_runtime_reexecuted": False,
        }
    finally:
        active_exception = sys.exc_info()[0] is not None
        cleanup_errors: list[BaseException] = []
        try:
            if staging is not None:
                staging.close(suppress_errors=active_exception)
        except BaseException as exc:
            cleanup_errors.append(exc)
        if source_fd >= 0:
            try:
                os.close(source_fd)
            except BaseException as exc:
                cleanup_errors.append(exc)
        if cleanup_errors and not active_exception:
            raise cleanup_errors[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--historical-output", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--compatibility", required=True, type=Path)
    parser.add_argument("--clean-png", required=True, type=Path)
    parser.add_argument("--historical-previews", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

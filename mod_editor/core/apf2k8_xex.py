"""Read a player's APF executable and optional installed 1.1 update in memory.

The BASE path mirrors tools/xex_extract_pe.cpp, before import resolution.
The TU path mirrors the pinned reconstruction in tools/apf_playcall_audit.py.
No compiler, subprocess, Java, native codec, emulator or on-disk PE is used.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

from .errors import ValidationError
from .xex_codec import aes_cbc_decrypt, lzx_decompress, require

RETAIL_KEY = bytes.fromhex("20b185a59d28fdc340583fbb0896bf91")
TU_SHA256 = "5f71cdf4ec679f8e33fd95e02ff2b67981fbf918d4d03a2099576734c5cfb42b"
XEXP_SHA256 = "14e272063536656d2aae9b4743fdcebb927566722dc1e2f34fe75029e1e8ada6"
MAX_INPUT = 128 * 1024 * 1024


def _slice(data, offset, size):
    require(0 <= offset <= len(data) and 0 <= size <= len(data) - offset,
            "XEX data is truncated or a header points outside the file")
    return data[offset:offset + size]


def _u32(data, offset):
    return struct.unpack(">I", _slice(data, offset, 4))[0]


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def read_input(path):
    try:
        with Path(path).open("rb") as stream:
            require(0 < Path(path).stat().st_size <= MAX_INPUT,
                    "Executable or Title Update exceeds the 128 MiB input limit")
            data = stream.read(MAX_INPUT + 1)
        require(0 < len(data) <= MAX_INPUT, "Executable or Title Update has an invalid size")
        return data
    except OSError as exc:
        raise ValidationError(f"Could not read {path}: {exc}") from exc


def _headers(data):
    require(data[:4] == b"XEX2", "Choose an Xbox 360 game folder containing default.xex")
    header_size, security, count = _u32(data, 8), _u32(data, 16), _u32(data, 20)
    require(24 <= header_size <= min(len(data), 4 * 1024 * 1024)
            and count <= (header_size - 24) // 8, "Invalid XEX header size or count")
    header = _slice(data, 0, header_size)
    _slice(header, security, 0x184)
    options = {}
    for i in range(count):
        key, offset = struct.unpack_from(">II", header, 24 + i * 8)
        require(key not in options, "Duplicate XEX optional header")
        options[key] = offset
    require(0x3FF in options, "XEX has no file-format header")
    fmt = options[0x3FF]
    format_size = _u32(header, fmt)
    require(format_size >= 8, "Invalid XEX file-format header")
    _slice(header, fmt, format_size)
    return header, security, options


def _session(header, key):
    return aes_cbc_decrypt(key, _slice(header, _u32(header, 16) + 0x150, 16))


def _blocks(payload, size, digest):
    offset = 0
    while size:
        require(size >= 24, "Invalid XEX compressed block size")
        block = _slice(payload, offset, size)
        require(hashlib.sha1(block).digest() == digest,
                f"Executable compressed block SHA-1 mismatch at byte {offset}; the file may be damaged")
        yield block
        offset += size
        size, digest = _u32(block, 0), block[4:24]


def decode_xex(data: bytes, progress=None) -> tuple[bytes, dict]:
    """Derive the exact flat image, without changing import ordinal words."""
    header, security, options = _headers(data)
    size, fmt = _u32(header, security + 4), options[0x3FF]
    require(0 < size <= 64 * 1024 * 1024, "Unsupported XEX image size")
    encryption, compression = struct.unpack(">HH", _slice(header, fmt + 4, 4))
    payload = data[len(header):]
    if encryption == 1:
        payload = aes_cbc_decrypt(_session(header, RETAIL_KEY), payload, progress)
    else:
        require(encryption == 0, "Unsupported XEX encryption type")
    receipt = {"xex_sha256": _sha(data), "encryption": encryption,
               "compression": compression, "image_size": size,
               "decoder": "studio-python-xex/v1", "compressed_blocks_sha1_verified": 0}
    if compression == 0:
        require(size <= len(payload) < size + 16, "XEX uncompressed payload size differs")
        image = payload[:size]
    elif compression == 1:
        format_size = _u32(header, fmt)
        require((format_size - 8) % 8 == 0, "Invalid XEX basic compression table")
        image, position = bytearray(), 0
        for off in range(fmt + 8, fmt + format_size, 8):
            stored, zeros = struct.unpack_from(">II", header, off)
            require(len(image) + stored + zeros <= size, "XEX basic block exceeds image size")
            image.extend(_slice(payload, position, stored))
            image.extend(bytes(zeros))
            position += stored
        require(len(image) == size and len(payload) - position < 16,
                "XEX basic compression size differs")
        image = bytes(image)
    elif compression == 2:
        require(_u32(header, fmt) == 36, "Invalid XEX normal compression header")
        window = _u32(header, fmt + 8)
        require(window != 0 and window & (window - 1) == 0,
                "XEX LZX window is not a power of two")
        bits = window.bit_length() - 1
        stream, chunks, blocks = bytearray(), 0, 0
        for block in _blocks(payload, _u32(header, fmt + 12), header[fmt + 16:fmt + 36]):
            off = 24
            while True:
                length = struct.unpack(">H", _slice(block, off, 2))[0]
                off += 2
                if length == 0:
                    break
                stream.extend(_slice(block, off, length))
                off += length
                chunks += 1
            blocks += 1
        image = lzx_decompress(bytes(stream), size, bits, progress=progress)
        receipt.update(window_size=window, window_bits=bits, lzx_bytes=len(stream),
                       lzx_chunks=chunks, compressed_blocks_sha1_verified=blocks)
    else:
        raise ValidationError("This is an update delta, not a complete executable. Choose the game folder and its Title Update content.")
    require(image[:2] == b"MZ", "Decoded executable is not a flat PE image")
    receipt["image_sha256"] = _sha(image)
    return image, receipt


def _extract_update(package):
    # Reuse the shipped STFS verifier. The LIVE parent-status exception is
    # restricted to this exact package; no roster extraction rule is relaxed.
    from tools.apf_stfs_roster_extract import _StfsReader, HASHES_PER_TABLE, BLOCK_SIZE

    require(_sha(package) == TU_SHA256,
            f"Title Update 1.1 package SHA-256 mismatch. Saw {_sha(package)}; accepts {TU_SHA256}.")

    class PinnedLiveReader(_StfsReader):
        def _level_zero_table(self, block):
            if self.top_level == 0:
                return self.top_table
            parent = self.top_entries[block // HASHES_PER_TABLE]
            address = (self.first_table_address + self._first_level_backing_block(block) * BLOCK_SIZE
                       + ((parent.status & 0x40) << 6))
            table = _slice(self.data, address, BLOCK_SIZE)
            require(hashlib.sha1(table).digest() == parent.digest, "Title Update STFS parent SHA-1 differs")
            return table

    try:
        reader = PinnedLiveReader(package)
        entries = reader.directory_entries()
        require(len(entries) == 1 and entries[0].path == "default.xexp", "Unexpected Title Update directory")
        delta = reader.extract(entries[0])
    except ValueError as exc:
        raise ValidationError(f"Could not read Title Update 1.1: {exc}") from exc
    require(_sha(delta) == XEXP_SHA256, "Title Update default.xexp SHA-256 differs")
    return delta, len(reader._verified_data_blocks)


def _apply_delta(data, target):
    offset, records = 0, 0
    while offset < len(data):
        if len(data) - offset < 12:
            require(not any(data[offset:]), "Truncated Title Update delta record")
            break
        old, new, size, compressed = struct.unpack(">IIHH", _slice(data, offset, 12))
        offset += 12
        if not (old | new | size | compressed):
            return records
        require(size > 0 and max(old + size, new + size) <= len(target),
                "Title Update delta points outside its target")
        if compressed == 0:
            target[new:new + size] = bytes(size)
        elif compressed == 1:
            target[new:new + size] = target[old:old + size]
        else:
            require(size <= 32768, "Title Update LZX record exceeds 32 KiB")
            reference = bytes(32768 - size) + bytes(target[old:old + size])
            target[new:new + size] = lzx_decompress(
                _slice(data, offset, compressed), size, 15, reference=reference)
            offset += compressed
        records += 1
    return records


def reconstruct_tu(base_image, base_xex, update, progress=None):
    from .apf2k8_playcall_patch import check_image, PROFILES

    require(check_image(base_image) == PROFILES[0], "Title Update 1.1 requires the retail BASE executable")
    if update[:4] == b"XEX2":
        require(_sha(update) == XEXP_SHA256,
                f"Title Update default.xexp SHA-256 mismatch. Saw {_sha(update)}; accepts {XEXP_SHA256}.")
        delta, verified = update, 0
    else:
        delta, verified = _extract_update(update)
    dh, _, opts = _headers(delta)
    require(0x5FF in opts, "Title Update has no delta descriptor")
    fmt, desc = opts[0x3FF], opts[0x5FF]
    require(struct.unpack(">IHHI", _slice(dh, fmt, 12)) == (36, 1, 3, 32768),
            "Unexpected Title Update compression format")
    original, security, _ = _headers(base_xex)
    require(hashlib.sha1(original[security + 8:security + 0x108]).digest() == _slice(dh, desc + 12, 20),
            "Title Update source executable signature digest differs")
    layout = struct.unpack(">7I", _slice(dh, desc + 48, 28))
    require(layout == (0x7000, 0, 0x7000, 0, 0, 0x3380000, 0), "Unsupported Title Update delta layout")
    header, image = bytearray(original), bytearray(base_image)
    old_key = _session(header, RETAIL_KEY)
    records = _apply_delta(_slice(dh, desc + 76, _u32(dh, desc) - 76), header)
    del header[layout[0]:]
    new_key = _session(header, RETAIL_KEY)
    require(aes_cbc_decrypt(new_key, _slice(dh, desc + 32, 16)) == old_key,
            "Title Update source key differs")
    payload = aes_cbc_decrypt(_session(dh, new_key), delta[len(dh):])
    blocks = 0
    for block in _blocks(payload, _u32(dh, fmt + 12), _slice(dh, fmt + 16, 20)):
        records += _apply_delta(block[24:], image)
        blocks += 1
        if progress is not None:
            progress("Checking Title Update 1.1", blocks, 0)
    require(check_image(image) == PROFILES[1], "Reconstructed executable is not Title Update 1.1")
    return bytes(image), {"update_sha256": _sha(update), "xexp_sha256": _sha(delta),
                          "stfs_data_blocks_verified": verified, "delta_blocks_sha1_verified": blocks,
                          "delta_records": records, "image_sha256": _sha(image),
                          "rsa_signature_verified": False}


def discover_title_update(game_folder, *, configured=None, content_roots=()):
    """Search only known installation locations, never recursively scan disks.

    Explicit configured input wins and must exist. Multiple installed copies
    must agree byte-for-byte; an unknown update is never ignored in favor of BASE.
    """
    if configured is not None:
        path = Path(configured)
        if path.is_file():
            return path
        require(path.is_dir(), f"Configured Title Update is missing: {path}")
        roots = [path]
    else:
        folder = Path(game_folder)
        roots = [folder, folder / "content", folder.parent / "content", *map(Path, content_roots)]
    found = set()
    for root in roots:
        for directory in (root, root / "54540807" / "000B0000",
                          root / "0000000000000000" / "54540807" / "000B0000"):
            if not directory.is_dir():
                continue
            for path in directory.iterdir():
                if path.is_file() and (path.name.casefold() == "default.xexp"
                                       or path.name.upper().startswith("TU_")):
                    found.add(path.resolve())
    if not found:
        require(configured is None, "No APF Title Update content found in that folder")
        return None
    paths = sorted(found)
    if len(paths) > 1:
        hashes = {_sha(read_input(path)) for path in paths}
        require(len(hashes) == 1, "Several different Title Updates were found. Choose the installed 1.1 content explicitly.")
    return paths[0]


def xenia_content_roots(executable):
    """Read nearby Xenia configuration; resolve relative paths beside Xenia."""
    import tomllib

    directory = Path(executable).parent
    roots = [directory / "content"]
    for name in ("xenia-canary.config.toml", "xenia.config.toml"):
        config = directory / name
        if not config.is_file():
            continue
        try:
            storage = tomllib.loads(read_input(config).decode("utf-8-sig")).get("Storage", {})
            base = Path(storage.get("storage_root") or directory).expanduser()
            if not base.is_absolute():
                base = directory / base
            content = Path(storage.get("content_root") or "content").expanduser()
            roots.append(content if content.is_absolute() else base / content)
        except (ValueError, TypeError, UnicodeError) as exc:
            raise ValidationError(f"Could not read Xenia content settings in {config}: {exc}") from exc
    return tuple(dict.fromkeys(roots))


def derive_image(source, *, title_update=None, content_roots=(), progress=None):
    """Game folder and expert PE routes share the exact same final SHA gate."""
    from .apf2k8_playcall_patch import check_image

    source = Path(source)
    is_folder = source.is_dir()
    path = source / "default.xex" if is_folder else source
    if is_folder:
        require(path.is_file(), f"No default.xex found in {source}. Choose the Xbox 360 game folder.")
    data = read_input(path)
    inputs = [path.resolve()]
    if data[:4] == b"XEX2":
        image, receipt = decode_xex(data, progress)
        check_image(image)
        update = discover_title_update(path.parent, configured=title_update, content_roots=content_roots)
        if update is not None:
            image, tu_receipt = reconstruct_tu(image, data, read_input(update), progress)
            receipt["title_update"] = tu_receipt
            inputs.append(update.resolve())
        kind = "game_folder" if is_folder else "executable"
    else:
        require(title_update is None, "Choose the game folder to apply Title Update content; a flat image is already decoded.")
        image, receipt, kind = data, {}, "flat_image"
    profile = check_image(image)
    return image, {"source_kind": kind, "input_paths": [str(p) for p in inputs],
                   "source_sha256": _sha(data), "image": profile.name,
                   "image_sha256": profile.sha256, "derivation": receipt}

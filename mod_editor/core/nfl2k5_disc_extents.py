"""Final read-only XDVDFS extent gate for Studio's disposable build output.

Python integers provide wide arithmetic; explicit field/range checks precede
rounding and addition. Image capacity is independent of each 32-bit file length.
The conservative xemu sector ceiling comes from its signed-int LBA consumers.
"""
from pathlib import Path
import os
import struct

SECTOR = 0x800
MAX_FILE_BYTES = 0xFFFFF800
MAX_XEMU_SECTORS = 0x7FFFFFFF
MAX_U64 = (1 << 64) - 1


class DiscExtentError(ValueError):
    pass


def check_extent(start_sector: int, size: int, volume_sectors: int, *, name: str = '') -> int:
    """Validate a file or directory, returning its exclusive rounded end LBA."""
    if not all(type(n) is int for n in (start_sector, size, volume_sectors)):
        raise DiscExtentError(f'{name}: extent fields must be integers')
    if not 0 <= start_sector <= 0xFFFFFFFF or not 0 <= size <= MAX_FILE_BYTES:
        raise DiscExtentError(f'{name}: unrepresentable sector or length exceeds 0xFFFFF800')
    if not 0 <= volume_sectors <= MAX_XEMU_SECTORS:
        raise DiscExtentError(f'{name}: volume exceeds conservative xemu signed-LBA limit')
    rounded_sectors = (size + SECTOR - 1) // SECTOR
    end_sector = start_sector + rounded_sectors
    if end_sector > volume_sectors:
        raise DiscExtentError(f'{name}: rounded extent exceeds final volume')
    return end_sector


def validate_image(path: Path | str) -> dict:
    """Read every reachable file/directory, including the root, without writes.

    The existing parser supplies structural validation (cycles, node ranges,
    names and duplicate paths). This additional gate checks the kernel's
    rounded extent math rather than only each unrounded byte end.
    """
    from .nfl2k5_throw_tuning import _xdvdfs_module
    xc = _xdvdfs_module()
    with Path(path).open('rb') as source:
        image_bytes = os.fstat(source.fileno()).st_size
        if not 0 < image_bytes <= MAX_U64 or image_bytes % SECTOR:
            raise DiscExtentError('image length must be positive, sector aligned and uint64')
        entries, _ = xc.parse_xdvdfs(source.fileno(), image_bytes)
        if not entries:
            raise DiscExtentError('empty XDVDFS tree')
        base = next(iter(entries.values())).base_offset
        if not 0 <= base <= image_bytes or base % SECTOR:
            raise DiscExtentError('invalid partition base')
        sectors = (image_bytes - base) // SECTOR
        source.seek(base + xc.XDVDFS_HEADER_OFFSET + 20)
        root_sector, root_size = struct.unpack('<II', source.read(8))
        all_extents = [('/', root_sector, root_size)]
        all_extents += [(entry.path, entry.sector, entry.size) for entry in entries.values()]
        for name, start, size in all_extents:
            end = check_extent(start, size, sectors, name=name)
            # Explicitly check the wide absolute address, including a front
            # video partition, without a narrowed intermediate multiplication.
            absolute_end = base + end * SECTOR
            if not 0 <= absolute_end <= min(image_bytes, MAX_U64):
                raise DiscExtentError(f'{name}: absolute extent exceeds image')
        return dict(extents_checked=len(all_extents), image_bytes=image_bytes,
                    partition_base=base, volume_sectors=sectors,
                    per_file_cap=MAX_FILE_BYTES, max_xemu_sectors=MAX_XEMU_SECTORS)

"""Explicit prerequisites for tests using private retail NFL data."""
import hashlib
import os
from pathlib import Path
import unittest


def read_nfl_retail_xbe() -> bytes:
    from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256

    candidates = []
    if path := os.environ.get('NFL2K5_RETAIL_XBE'):
        candidates.append(Path(path))
    if root := os.environ.get('NFL2K5_RETAIL_EXTRACTION'):
        candidates.extend((Path(root) / 'default.xbe', Path(root) / 'ESPN NFL 2K5 (USA)' / 'default.xbe'))
    for candidate in candidates:
        if candidate.is_file():
            with candidate.open('rb') as source:
                payload = source.read(16 * 1024**2 + 1)
            if hashlib.sha256(payload).hexdigest() != RETAIL_SHA256:
                raise AssertionError(f'Unexpected retail USA executable in {candidate}')
            return payload
    raise unittest.SkipTest('A retail USA executable or its extraction is required')


def require_nfl_retail_packs(source: Path) -> None:
    """Keep strict size/hash validation active once all sixteen inputs exist."""
    path = Path(source)
    if path.is_file():
        return  # Image files keep the strict reader's own validation.
    folder = path if path.name == "vc_53450030" else path / "vc_53450030"
    missing = [f"{index:X}" for index in range(16)
               if not (folder / f"{index:X}").is_file()]
    if missing:
        raise unittest.SkipTest(
            f"complete private NFL archive required; missing packs {', '.join(missing)} in {folder}"
        )

"""Disposable, bounded local compile results. Never included in a shared project.

JSON plus a content digest detects incomplete/corrupt entries; no executable
serialization is loaded. The caller keys compiler, pinned inputs and options,
then applies the same source-span and write/readback gates on a hit.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

MAX_ENTRY_BYTES = 64 * 1024 * 1024
MAX_CACHE_BYTES = 1024 * 1024 * 1024


def _encode(value):
    if isinstance(value, bytes):
        return {"$bytes": base64.b64encode(value).decode("ascii")}
    if isinstance(value, tuple):
        return {"$tuple": [_encode(item) for item in value]}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    return value


def _decode(value):
    if isinstance(value, dict):
        if set(value) == {"$bytes"}:
            return base64.b64decode(value["$bytes"], validate=True)
        if set(value) == {"$tuple"}:
            return tuple(_decode(item) for item in value["$tuple"])
        return {key: _decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


class CompileCache:
    def __init__(self, root: Path | None):
        self.root = root
        self.hits = self.misses = 0

    def _ready(self):
        if self.root is None:
            return False
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        return stat.S_ISDIR(self.root.lstat().st_mode) and not self.root.is_symlink()

    def get(self, key):
        try:
            if self._ready():
                path = self.root / (key + ".json")
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
                if path.is_symlink():
                    raise ValueError("cache symlink")
                fd = os.open(path, flags)
                with os.fdopen(fd, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise ValueError("cache entry is not regular")
                    raw = stream.read(MAX_ENTRY_BYTES + 1)
                if len(raw) > MAX_ENTRY_BYTES:
                    raise ValueError("oversized cache entry")
                envelope = json.loads(raw)
                payload = envelope["payload"].encode("ascii")
                if envelope["key"] != key or hashlib.sha256(payload).hexdigest() != envelope["sha256"]:
                    raise ValueError("cache digest mismatch")
                result = _decode(json.loads(payload))
                os.utime(path, None, follow_symlinks=False)
                self.hits += 1
                return result
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            pass
        self.misses += 1
        return None

    def put(self, key, result):
        temporary = None
        try:
            if not self._ready():
                return
            payload = json.dumps(_encode(result), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            raw = json.dumps(dict(key=key, payload=payload,
                                  sha256=hashlib.sha256(payload.encode("ascii")).hexdigest())).encode("ascii")
            if len(raw) > MAX_ENTRY_BYTES:
                return
            with tempfile.NamedTemporaryFile(dir=self.root, prefix=".pending-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw)
            os.replace(temporary, self.root / (key + ".json"))
            temporary = None
            entries = []
            for path in self.root.glob("*.json"):
                info = path.lstat()
                if stat.S_ISREG(info.st_mode):
                    entries.append((info.st_mtime_ns, info.st_size, path))
            total = sum(size for _, size, _ in entries)
            for _, size, path in sorted(entries):
                if total <= MAX_CACHE_BYTES:
                    break
                path.unlink()
                total -= size
        except (OSError, ValueError, TypeError):
            # Cache failures cannot refuse a valid build.
            pass
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

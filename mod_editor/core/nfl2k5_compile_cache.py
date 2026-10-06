"""Disposable, bounded local compile results. Never included in a shared project.

JSON plus a content digest detects incomplete/corrupt entries; no executable
serialization is loaded. The caller keys compiler, pinned inputs and options,
then applies the same source-span and write/readback gates on a hit.
"""
from __future__ import annotations

import base64
from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from . import platform_compat

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
        self._entries = None
        self._bytes = 0
        self._directory_stamp = None
        self._generation = None

    def _stamp(self):
        info = self.root.stat(follow_symlinks=False)
        return info.st_dev, info.st_ino, info.st_mtime_ns

    def _inventory(self):
        """Scan once, or after another writer changes the cache directory."""
        stamp = self._stamp()
        if self._entries is not None and stamp == self._directory_stamp:
            return
        entries = []
        for path in self.root.glob("*.json"):
            info = path.lstat()
            if stat.S_ISREG(info.st_mode):
                entries.append((info.st_mtime_ns, path, info.st_size))
        self._entries = OrderedDict((path, size) for _, path, size in sorted(entries))
        self._bytes = sum(self._entries.values())
        self._directory_stamp = stamp

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
                if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), str):
                    raise ValueError("invalid cache envelope")
                payload = envelope["payload"].encode("ascii")
                if envelope["key"] != key or hashlib.sha256(payload).hexdigest() != envelope["sha256"]:
                    raise ValueError("cache digest mismatch")
                result = _decode(json.loads(payload))
                if os.utime in os.supports_follow_symlinks:
                    os.utime(path, None, follow_symlinks=False)
                elif not os.path.islink(path):
                    # Windows: os.utime cannot skip symlinks; touch only a real file
                    os.utime(path, None)
                if self._entries is not None and path in self._entries:
                    self._entries.move_to_end(path)
                self.hits += 1
                return result
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            pass
        self.misses += 1
        return None

    def put(self, key, result, *, evict=True):
        """Store a cache entry, or a build-owned temporary result with no eviction.

        The latter is a handoff spool whose lifetime is the current build. Its
        records are still size-bounded, hashed JSON; evicting unfinished work
        would make the serial consumer repeat a completed compilation.
        """
        temporary = None
        lock_fd = None
        locked = False
        try:
            if not self._ready():
                return
            payload = json.dumps(_encode(result), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            raw = json.dumps(dict(key=key, payload=payload,
                                  sha256=hashlib.sha256(payload.encode("ascii")).hexdigest())).encode("ascii")
            if len(raw) > MAX_ENTRY_BYTES:
                return
            if evict:
                # Several builds can share this disposable cache. A nonblocking
                # cross-platform lock lets a contending writer skip caching,
                # keeping compilation and the GUI responsive. The generation
                # catches other writers even on coarse directory timestamps.
                lock_fd = os.open(self.root / ".writer.lock", os.O_CREAT | os.O_RDWR
                                  | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0), 0o600)
                if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                    return
                platform_compat.exclusive_nonblocking_lock(lock_fd)
                locked = True
                os.lseek(lock_fd, 0, os.SEEK_SET)
                generation = int(os.read(lock_fd, 32) or b"0")
                if generation != self._generation:
                    self._entries = None
                self._inventory()
            with tempfile.NamedTemporaryFile(dir=self.root, prefix=".pending-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw)
            destination = self.root / (key + ".json")
            os.replace(temporary, destination)
            temporary = None
            if not evict:
                return
            self._bytes -= self._entries.pop(destination, 0)
            self._entries[destination] = len(raw)
            self._bytes += len(raw)
            while self._bytes > MAX_CACHE_BYTES and self._entries:
                path, size = self._entries.popitem(last=False)
                path.unlink(missing_ok=True)
                self._bytes -= size
            self._directory_stamp = self._stamp()
            self._generation = generation + 1
            os.lseek(lock_fd, 0, os.SEEK_SET)
            os.write(lock_fd, str(self._generation).encode("ascii").ljust(32))
        except (OSError, ValueError, TypeError):
            # Cache failures cannot refuse a valid build.
            self._entries = None
        finally:
            if lock_fd is not None:
                try:
                    if locked:
                        platform_compat.release_lock(lock_fd)
                finally:
                    os.close(lock_fd)
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

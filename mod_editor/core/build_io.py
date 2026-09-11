"""Bounded, cancellable copies for private build outputs."""
from __future__ import annotations

import errno
import os
from pathlib import Path
import time

from . import platform_compat

CHUNK = 8 * 1024 * 1024
_UNSUPPORTED = {errno.EXDEV, errno.EINVAL, errno.ENOSYS, errno.ENOTSUP}


def copy_descriptors(source, target, size, progress=None):
    """Copy exact bytes with kernel acceleration, falling back only if unsupported.

    Explicit offsets preserve descriptor positions on every path. Short copies
    and interrupted system calls are retried; storage failures remain failures.
    """
    copied, last = 0, 0.0
    accelerated = True
    while copied < size:
        count = min(CHUNK, size - copied)
        try:
            if accelerated:
                done = platform_compat.copy_file_range(source, target, count,
                    offset_src=copied, offset_dst=copied)
            else:
                data = platform_compat.pread(source, count, copied)
                done = 0
                while done < len(data):
                    written = platform_compat.pwrite(target, memoryview(data)[done:], copied + done)
                    if written <= 0:
                        raise OSError("short write while copying the disc")
                    done += written
        except InterruptedError:
            continue
        except OSError as exc:
            if accelerated and exc.errno in _UNSUPPORTED:
                accelerated = False
                continue
            raise
        if done <= 0:
            raise OSError("source image shrank during the copy")
        copied += done
        now = time.monotonic()
        if progress is not None and (now - last >= 0.1 or copied == size):
            progress("Copying disc image", copied, size)
            last = now
    return copied


def copy_image(source, target, progress=None):
    with Path(source).open("rb") as src, Path(target).open("xb") as dst:
        return copy_descriptors(src.fileno(), dst.fileno(), os.fstat(src.fileno()).st_size, progress)


class StageProgress:
    """Record elapsed time per reported stage without changing progress messages."""
    def __init__(self, sink=None):
        self.sink = sink
        self.started = time.monotonic()
        self.stage = "preflight"
        self.seconds = {}

    def __call__(self, stage, done=0, total=0):
        if stage != self.stage:
            self.finish()
            self.stage = stage
        if self.sink:
            self.sink(stage, done, total)

    def finish(self):
        now = time.monotonic()
        self.seconds[self.stage] = self.seconds.get(self.stage, 0.0) + now - self.started
        self.started = now
        return dict(self.seconds)

"""Bounded JSON decoding for large metadata tables shared with a Qt process.

CPython's JSON decoder holds the GIL for an entire value. Decode table rows
separately and yield between batches so a worker cannot starve the UI thread.
No global cache: callers retain ownership and their existing authenticity checks.
"""
from __future__ import annotations

import json
import io
import time


def load(path):
    with open(path, encoding="utf-8") as stream:
        return _load_stream(stream)


def loads(payload):
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    with io.StringIO(text) as stream:
        return _load_stream(stream)


def dump(value, stream):
    """Match compact metadata JSON without a single long C encoder call."""
    encoder = json.JSONEncoder(ensure_ascii=True, separators=(",", ":"))
    yielded = time.monotonic()
    parts = []
    for part in encoder.iterencode(value):
        parts.append(part)
        if len(parts) == 2048:
            stream.write("".join(parts))
            parts.clear()
            if time.monotonic() - yielded > .01:
                time.sleep(.001)
                yielded = time.monotonic()
    stream.write("".join(parts))


def _load_stream(stream):
    decoder = json.JSONDecoder()
    buffer = ""
    offset = 0
    eof = False
    yielded = time.monotonic()

    def refill():
        nonlocal buffer, offset, eof, yielded
        buffer = buffer[offset:] + stream.read(65536)
        offset = 0
        eof = not buffer
        if time.monotonic() - yielded > .01:
            time.sleep(.001)
            yielded = time.monotonic()

    def space():
        nonlocal offset, eof
        while True:
            while offset < len(buffer) and buffer[offset] in " \t\r\n":
                offset += 1
            if offset < len(buffer) or eof:
                return
            refill()

    def token(expected):
        nonlocal offset
        space()
        if buffer[offset:offset+1] != expected:
            raise json.JSONDecodeError(f"Expected {expected}", buffer, offset)
        offset += 1

    def value(depth=0):
        nonlocal offset, buffer, eof, yielded
        if time.monotonic() - yielded > .01:
            time.sleep(.001)
            yielded = time.monotonic()
        space()
        char = buffer[offset:offset+1]
        if char == "{" and depth == 0:
            offset += 1
            result = {}
            space()
            if buffer[offset:offset+1] == "}":
                offset += 1
                return result
            while True:
                key = value(depth+1)
                if not isinstance(key, str):
                    raise json.JSONDecodeError("Object key must be a string", buffer, offset)
                token(":")
                result[key] = value(depth+1)
                space()
                if buffer[offset:offset+1] == "}":
                    offset += 1
                    return result
                token(",")
        if char == "[" and depth < 3:
            offset += 1
            result = []
            space()
            if buffer[offset:offset+1] == "]":
                offset += 1
                return result
            while True:
                result.append(value(depth+1))
                space()
                if buffer[offset:offset+1] == "]":
                    offset += 1
                    return result
                token(",")
        while True:
            try:
                result, end = decoder.raw_decode(buffer, offset)
                # A number at a buffer boundary may continue in the next block.
                if (end < len(buffer) and buffer[end] in " \r\n\t,:]}") or eof:
                    offset = end
                    return result
            except json.JSONDecodeError:
                if eof:
                    raise
            remainder = buffer[offset:]
            block = stream.read(65536)
            buffer, offset, eof = remainder + block, 0, not block

    result = value()
    space()
    if offset != len(buffer):
        raise json.JSONDecodeError("Extra data", buffer, offset)
    return result

"""Recover old oversized manifests without materializing their fit history.

Beta 75 could write more than its reader's 16 MiB limit. Fit receipts are an
advisory cache, so recovery discards that top-level field while validating the
entire JSON stream. Authored fields still have the ordinary manifest budget.
The caller enforces ZIP member and total expanded-size limits first.
"""
from __future__ import annotations

import io
import json
import re

from mod_editor.core.errors import ValidationError


RECOVERY_NOTE = (
    'Recovered a large project saved by an older beta. Your artwork and edits '
    'are intact. Old fit measurements were cleared and will be checked at Build. '
    'Save Project to keep the smaller project file. The original file has not been changed.'
)

_SPACE = re.compile(r'[ \t\r\n]*')
_STRING = re.compile(r'[^"\\\x00-\x1f]+')
_ATOM = re.compile(r'[^,\]} \t\r\n]+')


class _RecoveryReader:
    def __init__(self, stream, maximum):
        self.stream = stream
        self.maximum = maximum
        self.retained = 0
        self.buffer = ''
        self.position = 0

    def available(self, count=1):
        while len(self.buffer) - self.position < count:
            block = self.stream.read(65536)
            if not block:
                break
            self.buffer = self.buffer[self.position:] + block
            self.position = 0
        return self.buffer[self.position:self.position+count]

    def take(self, count, charge=False):
        text = self.buffer[self.position:self.position+count]
        self.position += count
        if charge:
            self.retained += len(text.encode('utf-8'))
            if self.retained > self.maximum:
                raise ValidationError('Project authored metadata exceeds the manifest limit even after '
                                      'clearing old fit measurements. The original file is unchanged.')
        return text

    def space(self):
        while self.available():
            end = _SPACE.match(self.buffer, self.position).end()
            self.position = end
            if end < len(self.buffer):
                return

    def token(self, token, charge=False):
        self.space()
        if self.available() != token:
            raise ValidationError(f'Project manifest JSON expected {token!r}.')
        self.take(1, charge)

    def string(self, retain, charge):
        self.token('"', charge)
        parts = ['"'] if retain else None
        size = 0
        while True:
            char = self.available()
            if not char:
                raise ValidationError('Project manifest JSON ended inside a string.')
            if char == '"':
                self.take(1, charge)
                if retain:
                    parts.append('"')
                    return json.loads(''.join(parts))
                return None
            if char == '\\':
                escaped = self.available(2)
                count = 6 if escaped == '\\u' else 2
                text = self.available(count)
                if (len(text) != count or (count == 6 and not re.fullmatch(r'\\u[0-9a-fA-F]{4}', text))
                        or (count == 2 and text[1] not in '"\\/bfnrt')):
                    raise ValidationError('Project manifest JSON contains an invalid escape.')
            else:
                match = _STRING.match(self.buffer, self.position)
                if match is None:
                    raise ValidationError('Project manifest JSON contains a control character.')
                count = match.end() - self.position
            text = self.take(count, charge)
            if retain:
                size += len(text)
                if size > self.maximum:
                    raise ValidationError('Project manifest JSON string exceeds the metadata limit.')
                parts.append(text)

    def value(self, retain=True, depth=0):
        if depth > 64:
            raise ValidationError('Project manifest JSON is nested too deeply.')
        self.space()
        char = self.available()
        if char == '"':
            return self.string(retain, retain)
        if char in ('{', '['):
            mapping = char == '{'
            close = '}' if mapping else ']'
            self.take(1, retain)
            result = ({} if mapping else []) if retain else None
            seen = set()
            self.space()
            if self.available() == close:
                self.take(1, retain)
                return result
            while True:
                if mapping:
                    key = self.string(True, retain)
                    if key in seen:
                        raise ValidationError(f'Project JSON contains a duplicate object key: {key!r}.')
                    seen.add(key)
                    if len(seen) > 25000:
                        raise ValidationError('Project manifest JSON object has too many fields.')
                    self.token(':', retain)
                    keep = retain and not (depth == 0 and key == 'fit_receipts')
                    item = self.value(keep, depth+1)
                    if keep:
                        result[key] = item
                else:
                    item = self.value(retain, depth+1)
                    if retain:
                        result.append(item)
                self.space()
                if self.available() == close:
                    self.take(1, retain)
                    return result
                self.token(',', retain)
        # Scalars are small in Studio metadata. Bound even discarded numeric
        # tokens so an invalid old cache cannot exhaust Python's integer parser.
        parts = []
        while self.available():
            match = _ATOM.match(self.buffer, self.position)
            if match is None:
                break
            parts.append(self.take(match.end() - self.position, retain))
            if sum(map(len, parts)) > 128:
                raise ValidationError('Project manifest JSON scalar is too long.')
        text = ''.join(parts)
        if not re.fullmatch(r'(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)', text):
            raise ValidationError('Project manifest JSON contains an invalid value.')
        return json.loads(text) if retain else None


def recover_manifest(stream, maximum):
    """Validate all JSON, retaining only authored top-level fields."""
    with io.TextIOWrapper(stream, encoding='utf-8') as text:
        reader = _RecoveryReader(text, maximum)
        document = reader.value()
        reader.space()
        if reader.available():
            raise ValidationError('Project manifest JSON has trailing data.')
        if not isinstance(document, dict):
            raise ValidationError('Project manifest must be an object.')
        return document

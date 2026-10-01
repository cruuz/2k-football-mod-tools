"""Pinned replacement histories, owned by the identities in a roster-edits file.

DESIGN: regular seasons through epoch-1, sparse zero counters, no invented
participation. Unrelated streams remain byte-for-byte intact. Old seasons stay
separate even outside the 15-row card window so career sums cannot overflow a
16-bit folded cell. Native rollover may subsequently fold those seasons.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
import hashlib
import re
import struct

from . import nfl2k5_career_stats as cs
from . import nfl2k5_save_rost as sr

SCHEMA = 'nfl2k5_franchise_history/v1'


def require(ok, message):
    if not ok:
        raise cs.CareerStatsError(message)


def repack(body, document, replacements):
    """Transactional ownership check and bounded repack, including shrink/clear."""
    pool = document.pool
    require(pool is not None, 'missing history pool')
    at = pool
    owners = sorted((p for p in document.players if document.history_offsets[p.key] is not None),
                    key=lambda p: document.history_offsets[p.key])
    for p in owners:
        require(document.history_offsets[p.key] == at, 'history has gaps or shared ownership')
        at += len(document.history_words[p.key]) * 4
    require(at == pool + document.pool_used * 4, 'history has unowned words')
    streams = {p.key: replacements.get(p.key, document.history_words[p.key]) for p in document.players}
    used = sum(map(len, streams.values()))
    require(used <= document.pool_capacity, f'history needs {used} dwords, capacity {document.pool_capacity}')
    require(not any(body[pool + document.pool_used * 4:pool + used * 4]), 'nonzero history slack')
    out = bytearray(body)
    out[pool:pool + max(used, document.pool_used) * 4] = bytes(max(used, document.pool_used) * 4)
    at = pool
    # Retain old stream order; append newly populated players in stable key order.
    order = owners + sorted((p for p in document.players if document.history_offsets[p.key] is None), key=lambda p:p.key)
    for p in order:
        words = streams[p.key]
        ptr = p.offset + 0x2C
        struct.pack_into('<i', out, ptr, at - ptr + 1 if words else 0)
        if words:
            require(words[-1] & 0x80000000 and not any(w & 0x80000000 for w in words[:-1]), 'bad terminators')
            for word in words:
                struct.pack_into('<I', out, at, word)
                at += 4
    struct.pack_into('<I', out, document.layout.root + 0x40, used)
    result = bytes(out)
    check = sr.decode(result, preamble=0, reference_year=document.reference_year)
    require(all(tuple(streams[p.key]) == check.history_words[p.key] for p in document.players), 'history readback differs')
    return result, {'used_before':document.pool_used, 'used_after':used,
                    'capacity':document.pool_capacity, 'free_after':document.pool_capacity-used,
                    'preserved_players':len(document.players)-len(replacements),
                    'replaced_players':len(replacements), 'roundtrip_verified':True}


def apply_body(body: bytes, spec: dict):
    require(spec.get('schema') == SCHEMA, 'unknown franchise history schema')
    epoch = spec.get('base_year')
    require(type(epoch) is int and 1901 <= epoch <= 2100, 'invalid franchise epoch')
    doc = sr.decode(body, preamble=0, reference_year=epoch)
    require(doc.layout.version == 17, 'franchise history requires disc version 17')
    sources = spec.get('sources', {})
    for pin in sources.values():
        require(re.fullmatch('[0-9a-f]{64}', pin.get('sha256','')) and pin.get('updated_at') and pin.get('url'), 'source needs hash, date and URL')
    replacement = {}
    identities = set()
    seasons = 0
    for identity in spec['players']:
        key = (identity['pool'], identity['index'])
        require(key not in replacement, 'duplicate replacement player')
        require(identity['gsis_id'] and identity['gsis_id'] not in identities, 'missing or duplicate source ID')
        identities.add(identity['gsis_id'])
        p = doc.by_key.get(key)
        require(p is not None, 'replacement player not found')
        require((p.first,p.last) == (identity['first'],identity['last']) and
                p.record.birth_date == dt.date.fromisoformat(identity['birth_date']), 'replacement identity pin differs')
        require(identity['identity_source'] in sources, 'identity source not pinned')
        count = p.record.values['years_pro']
        words = []
        seen = set()
        for season in identity['seasons']:
            year = season['year']
            slot = count - (epoch - year)
            require(type(year) is int and 1900 <= year < epoch and 0 <= slot < count <= 31, 'unrepresentable completed season')
            require(year not in seen, 'duplicate player season')
            seen.add(year)
            require(season['source'] in sources, 'stats source not pinned')
            counters = season['stats']
            require('games' in counters and counters['games'] > 0, 'season needs positive sourced games')
            for name, value in counters.items():
                require(name in cs.BY_NAME, 'unknown stat field')
                field = cs.BY_NAME[name]
                raw = cs._raw_value(field, Decimal(str(value)))
                if raw or name == 'games':
                    words.append((slot << 23) | (field.id << 16) | raw)
            # TEAM is written only after this modern season has its games slot.
            if 'team_index' in season:
                team = season['team_index']
                require(type(team) is int and 0 <= team < 32, 'invalid season team')
                require(season.get('team_source') in sources, 'TEAM source not pinned')
                words.append((slot << 23) | (87 << 16) | (team + 1))
            seasons += 1
        words.sort(key=lambda w:(cs.Word(w).slot, cs.Word(w).field))
        if words:
            words[-1] |= 0x80000000
        replacement[key] = tuple(words)
    result, receipt = repack(body, doc, replacement)
    return result, {**receipt, 'schema':SCHEMA, 'base_year':epoch, 'source_seasons':seasons,
                    'source_body_sha256':hashlib.sha256(body).hexdigest(),
                    'output_body_sha256':hashlib.sha256(result).hexdigest()}

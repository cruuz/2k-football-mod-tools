"""ROST tendency edits, following each team's relative tendency pointer.

Native 8492A440 expands +5A and +8E/+99 into the working tendency object.
84929B4C..84929E44 READ the optional row arrays, so they are implemented.
They feed an optional cache; the ordinary category lottery does not read it.
"""
from __future__ import annotations
import struct

from . import apf2k8_book_identity  # installs the repository's APF tool imports
from .apf2k8_playcall_model import _int
from .apf2k8_playcall_model import PlaycallError as ValidationError
import apf_roster


def _record(rost, team_index):
    if not isinstance(rost, bytes):
        raise ValidationError('ROST must be immutable decoded bytes')
    try:
        tables, _ = apf_roster.parse_root(rost)
        teams, tendencies = tables[4], tables[9]
        _int(team_index, 0, teams.count - 1, 'Team index')
        if teams.stride != 384 or tendencies.stride != 180:
            raise ValidationError('Unsupported ROST team or tendency record size')
        field = teams.offset + team_index * teams.stride + 0xF8
        target = apf_roster.resolve_relative(rost, field, 'team tendency')
        if not tendencies.offset <= target < tendencies.offset + tendencies.count * 180 or (target - tendencies.offset) % 180:
            raise ValidationError('Team tendency pointer is outside the tendency table')
        return target
    except (IndexError, struct.error) as exc:
        raise ValidationError('ROST tendency table is truncated') from exc


def team_tendency(rost: bytes, team_index: int) -> int:
    value = rost[_record(rost, team_index) + 0x5A]
    _int(value, 0, 100, 'Run percentage')
    return value


def set_team_tendency(rost: bytes, team_index: int, value: int) -> bytes:
    _int(value, 0, 100, 'Run percentage')
    at = _record(rost, team_index)
    output = bytearray(rost)
    output[at + 0x5A] = value
    result = bytes(output)
    if team_tendency(result, team_index) != value:
        raise ValidationError('Run percentage reparse failed')
    return result


def row_weights(rost: bytes, team_index: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    at = _record(rost, team_index)
    return tuple(rost[at + 0x8E:at + 0x99]), tuple(rost[at + 0x99:at + 0xA4])


def set_row_weights(rost: bytes, team_index: int, run: tuple[int, ...], pass_: tuple[int, ...]) -> bytes:
    for values in (run, pass_):
        if not isinstance(values, tuple) or len(values) != 11:
            raise ValidationError('Supply eleven run and eleven pass row weights')
        for value in values:
            _int(value, 0, 255, 'Row weight')
    at = _record(rost, team_index)
    output = bytearray(rost)
    output[at + 0x8E:at + 0xA4] = bytes(run + pass_)
    result = bytes(output)
    if row_weights(result, team_index) != (run, pass_):
        raise ValidationError('Row weight reparse failed')
    return result

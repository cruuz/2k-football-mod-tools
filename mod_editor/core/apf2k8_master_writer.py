"""Edits to MASTER affect every book on the disc, including team clones."""
from __future__ import annotations

from .apf2k8_playcall_model import _master, _int, category_table
from .apf2k8_playcall_model import PlaycallError as ValidationError


def verify_master(master: bytes) -> None:
    _master(master)
    category_table(master)


def set_category_row(master: bytes, category_id: int, row: int) -> bytes:
    verify_master(master)
    _int(category_id, 0, 27, 'Category')
    _int(row, 0, 27, 'Personnel row')
    output = bytearray(master)
    at = 0x48 + category_id * 16
    output[at] = (output[at] & 0xC0) | row
    result = bytes(output)
    verify_master(result)
    if category_table(result)[category_id].row != row:
        raise ValidationError('MASTER row reparse failed')
    return result


def set_category_roles(master: bytes, category_id: int, roles: tuple[int, ...]) -> bytes:
    verify_master(master)
    _int(category_id, 0, 27, 'Category')
    if not isinstance(roles, tuple) or len(roles) != 11:
        raise ValidationError('A personnel category must have exactly eleven roles')
    for role in roles:
        _int(role, 0, 31, 'Role')
    output = bytearray(master)
    at = 0x49 + category_id * 16
    for slot, role in enumerate(roles):
        output[at + slot] = (output[at + slot] & 0xE0) | role
    result = bytes(output)
    verify_master(result)
    if tuple(b & 31 for b in result[at:at + 11]) != roles:
        raise ValidationError('MASTER role reparse failed')
    return result

"""Speed-scaled human ordinary tap bursts, layered over the sp1 return fix.

Requested full-condition bonus: 4% at 65, 6% at 75, 10% at 90+, linear between.
Duration grows from 0.25s at 65 to 0.5s at 90. Each genuine human tap refreshes
expiry without resetting native elapsed time or removing native repeat extra.
CPU bursts and charged bursts retain native behavior. Max stores preserve
existing star benefits. No rating, permission, charge or Speedster field changes.
The successful initializer tail and native throttle call are the only hooks.
"""
from __future__ import annotations

import hashlib
import struct
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_human_tap_burst"
CODE_SIZE = 512
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
HOOKS = (("initialize", 0x30EF48, bytes.fromhex("e98331d9ff")),
         ("update", 0x30EFBB, bytes.fromhex("e8d01fedff")))
GUARDS = ((0x30ED50, 0x440, "81db1fe74bc32c4884f4f34c4a1ca9e1553fc565000e69342e9b20acbaff8e0c"),
          (0x50CB54, 0x34, "7cdb3a90fc9948f3f9db5ab3f3b31885bd0323d596bb312e441f2415f4bbe275"))
# Authored x87 calculator: ECX=raw Speed, ST0=native condition curve.
# Clamp 65..90. Bonus numerator is 30*Speed-1350 through 75, else 40*Speed-2100,
# divided by 15000. Return ST0=.25+(clampedSpeed-65)/100, ST1=1+bonus*condition.
# This never writes the player's raw or effective Speed.
CALCULATOR = bytes.fromhex(
    "5083ec1083f9417705b94100000083f95a7605b95a00000089c883e84189042483f94b770b6bc91e"
    "81e946050000eb096bc92881e934080000894c2404c7442408983a0000db442404da742408dec9d9"
    "e8dec1db0424c744240864000000da742408c744240c0000803ed844240c83c41058c3"
)


def code_for(base):
    a=_Asm(base)
    a.label('initialize')
    a.b('9c6089cf31d2') # flags/registers; entity=ECX; initial
    a.j32('e8','boost')
    a.b('619d')
    a.jmp_abs(0xa20d0)
    a.label('update')
    a.call(0x1e0f90) # displaced native throttle call
    a.b('9c60ba01000000') # EDI already entity; repeated tap
    a.j32('e8','boost')
    a.b('619dc3')
    a.label('boost')
    a.b('833db802e6000e') # live phase
    a.j32('0f85','done')
    a.b('8b470c833803') # unsigned controller 0..3
    a.j32('0f87','done')
    a.b('83781c16') # genuine decoded tap, not synthesized EBX
    a.j32('0f85','done')
    a.b('8b77108b869000000083e00383f801') # charged selector
    a.j32('0f84','done')
    a.b('8b5f3c0fb64b3683f941') # raw Speed <=65 stays native
    a.j32('0f86','done')
    a.b('89d58b43308b4004ff7004') # EBP=refresh; condition argument
    a.b('8b1554cb5000b958cb5000')
    a.call(0x1b0ae0) # native condition curve
    a.b('0fb64b36')
    a.j32('e8','calculate') # ST0 duration, ST1 requested multiplier
    a.b('83ec08d91c24d95c2404')
    a.b('8b4424043b86e0000000') # never reduce a preexisting multiplier
    a.j8('76','duration')
    a.b('8986e0000000')
    a.label('duration')
    a.b('85ed')
    a.j8('74','duration_compare')
    a.b('d90424d84608d91c24') # refresh expiry; keep native elapsed/extra
    a.label('duration_compare')
    a.b('8b04243b86d8000000')
    a.j8('76','release')
    a.b('8986d8000000')
    a.label('release')
    a.b('83c408')
    a.label('done')
    a.b('c3')
    a.label('calculate')
    a.b(CALCULATOR.hex())
    code=a.assemble()
    space._require(len(code)<=CODE_SIZE, "human tap code exceeds reservation")
    return code.ljust(CODE_SIZE,b'\xcc'),{k:base+v for k,v in a.labels.items()},len(code)


def sites(labels):
    return [(name, va, before, before[:1] + struct.pack("<i", labels[name] - va - 5))
            for name, va, before in HOOKS]


def _inspect(payload):
    layout = space.layout(payload)
    image = XbeImage(payload)
    rows = [a for a in layout["allocations"] if a["owner"] == OWNER]
    state, labels = "retail", None
    if rows:
        space._require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"])
                       == ("code", CODE_SIZE, 16), "foreign human tap allocation")
        a = rows[0]
        code, labels, _ = code_for(a["va"])
        actual = image.read(a["va"], CODE_SIZE)
        space._require(actual in (code, b"\xcc" * CODE_SIZE), "foreign human tap owner code")
        state = "applied" if actual == code else "retail"
    for name, va, before in HOOKS:
        expected = before if state == "retail" else next(r[3] for r in sites(labels) if r[0] == name)
        space._require(image.read(va, len(before)) == expected, "foreign or partial human tap hook")
    for va, size, digest in GUARDS:
        data = bytearray(image.read(va, size))
        for _, hook, before in HOOKS:
            if va <= hook and hook + len(before) <= va + size:
                data[hook-va:hook-va+len(before)] = before
        space._require(hashlib.sha256(data).hexdigest() == digest, "foreign human tap dependency")
    return state, rows


def status(payload):
    try:
        return _inspect(payload)[0]
    except (ValueError, KeyError, TypeError, IndexError, struct.error):
        return "foreign"


def normalize_sp1_guard(payload, va, data):
    """Normalize only fully verified sp2 hooks, never arbitrary jump bytes."""
    space._require(_inspect(payload)[0] == "applied", "unverified human tap overlay")
    out = bytearray(data)
    for _, hook, before in HOOKS:
        if va <= hook and hook + len(before) <= va + len(out):
            out[hook-va:hook-va+len(before)] = before
    return bytes(out)


def reservations(payload):
    if status(payload) != "applied":
        return []
    out = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    return out + [dict(owner=OWNER, start=hex(va), end=hex(va+len(before)), size=len(before),
                       basis="human ordinary tap " + name + "; pinned native site")
                  for name, va, before in HOOKS]


def apply(payload):
    from . import nfl2k5_tap_burst as ordinary
    space._require(ordinary.status(payload) == "applied", "sp1 ordinary return burst is required")
    state, rows = _inspect(payload)
    if state == "applied":
        return payload, dict(status="already_applied", changed_bytes=0, edits=[])
    allocated, allocation = (payload, {}) if rows else space.extend_scaleout(payload, REQUESTS)
    a = next(r for r in space.layout(allocated)["allocations"] if r["owner"] == OWNER)
    code, labels, length = code_for(a["va"])
    installed, _ = space.install_code(allocated, OWNER, code)
    image, buf, edits = XbeImage(installed), bytearray(installed), []
    for name, va, before, after in sites(labels):
        off = image.offset(va, len(before))
        buf[off:off+len(after)] = after
        edits.append(dict(label="human_tap_"+name, va=hex(va), file_offset=hex(off),
                          size=len(after), before=before.hex(), after=after.hex()))
    for section in _sections(buf):
        buf[section.header_offset+36:section.header_offset+56] = section_digest(buf, section)
    result = bytes(buf)
    space._require(status(result) == "applied" and ordinary.status(result) == "applied",
                   "human tap postcondition failed")
    return result, dict(status="applied", changed_bytes=space.count_differing_bytes(payload, result),
                        edits=edits, allocation=allocation, code_bytes=length,
                        reserved_bytes=CODE_SIZE, rating_and_speedster_rules_unchanged=True,
                        charge_rules_unchanged=True, human_only=True)

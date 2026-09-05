"""Portable animation math from the recovered NFL sampler and pose sources.

Binary64 semantic model with float32 stores, NOT Xbox x87 bit identity.
The fixed sine table is the same table as quaternion_interpolation_table.inc.
"""
from __future__ import annotations
import math
import struct
from typing import Any, Iterable


def f32(value: float) -> float:
    return struct.unpack('<f', struct.pack('<f', value))[0]


def from_bits(value: int) -> float:
    return struct.unpack('<f', struct.pack('<I', value))[0]


SINE_BITS = (
    (0x34f80a77, 0x38c90ab0),
    (0x3787a18a, 0x38c8ebaf),
    (0x389fcff4, 0x38c8adb3),
    (0x395c4485, 0x38c850c5),
    (0x39ea6f8a, 0x38c7d4f3),
    (0x3a561ae1, 0x38c73a51),
    (0x3ab0ae5a, 0x38c680f5),
    (0x3b07a499, 0x38c5a8fe),
    (0x3b45506a, 0x38c4b28c),
    (0x3b899bce, 0x38c39dc4),
    (0x3bb99913, 0x38c26ad3),
    (0x3bf38931, 0x38c119e6),
    (0x3c1c2920, 0x38bfab33),
    (0x3c446b7e, 0x38be1ef1),
    (0x3c72fb3c, 0x38bc755e),
    (0x3c9422f7, 0x38baaebb),
    (0x3cb25b87, 0x38b8cb4e),
    (0x3cd45bee, 0x38b6cb63),
    (0x3cfa579d, 0x38b4af48),
    (0x3d124062, 0x38b2774f),
    (0x3d298423, 0x38b023d2),
    (0x3d430ed3, 0x38adb52b),
    (0x3d5ef77a, 0x38ab2bbb),
    (0x3d7d5461, 0x38a887e6),
    (0x3d8f1d86, 0x38a5ca13),
    (0x3da0e017, 0x38a2f2b0),
    (0x3db3fbd3, 0x38a0022c),
    (0x3dc87a3b, 0x389cf8fc),
    (0x3dde645f, 0x3899d797),
    (0x3df5c2d7, 0x38969e79),
    (0x3e074ee4, 0x38934e21),
    (0x3e147e6c, 0x388fe711),
    (0x3e227397, 0x388c69d1),
    (0x3e3131bb, 0x3888d6ea),
    (0x3e40bbe8, 0x38852eea),
    (0x3e5114ef, 0x3881725f),
    (0x3e623f59, 0x387b43bd),
    (0x3e743d6b, 0x38737bfd),
    (0x3e838893, 0x386b8eb1),
    (0x3e8d5e1e, 0x38637d12),
    (0x3e97a010, 0x385b485e),
    (0x3ea24efa, 0x3852f1da),
    (0x3ead6b49, 0x384a7acf),
    (0x3eb8f544, 0x3841e48a),
    (0x3ec4ed0d, 0x3839305f),
    (0x3ed152a0, 0x38305fa6),
    (0x3ede25d0, 0x382773ba),
    (0x3eeb664c, 0x381e6dfc),
    (0x3ef9139b, 0x38154fcf),
    (0x3f03968e, 0x380c1a9c),
    (0x3f0ad904, 0x3802cfcf),
    (0x3f1250b8, 0x37f2e1aa),
    (0x3f19fd1e, 0x37dffe43),
    (0x3f21dd99, 0x37ccf851),
    (0x3f29f174, 0x37b9d2c3),
    (0x3f3237ea, 0x37a6908e),
    (0x3f3ab021, 0x379334aa),
    (0x3f43592b, 0x377f8425),
    (0x3f4c3208, 0x3758778f),
    (0x3f5539a1, 0x37314997),
    (0x3f5e6ed1, 0x370a004a),
    (0x3f67d05c, 0x36c54367),
    (0x3f715cf4, 0x366ccfa1),
    (0x3f7b1339, 0x359de7df),
    (0x3f8278db, 0xb59de7df),
    (0x3f877b74, 0xb66ccfa1),
    (0x3f8c909b, 0xb6c54367),
    (0x3f91b77b, 0xb70a004a),
    (0x3f96ef37, 0xb7314997),
    (0x3f9c36e7, 0xb758778f),
    (0x3fa18d9f, 0xb77f8425),
    (0x3fa6f266, 0xb79334aa),
    (0x3fac643c, 0xb7a6908e),
    (0x3fb1e21c, 0xb7b9d2c3),
    (0x3fb76af5, 0xb7ccf851),
    (0x3fbcfdb0, 0xb7dffe43),
    (0x3fc29931, 0xb7f2e1aa),
    (0x3fc83c51, 0xb802cfcf),
    (0x3fcde5e3, 0xb80c1a9c),
    (0x3fd394b6, 0xb8154fcf),
    (0x3fd9478f, 0xb81e6dfc),
    (0x3fdefd2e, 0xb82773ba),
    (0x3fe4b44e, 0xb8305fa6),
    (0x3fea6ba3, 0xb839305f),
    (0x3ff021db, 0xb841e48a),
    (0x3ff5d5a1, 0xb84a7acf),
    (0x3ffb8598, 0xb852f1da),
    (0x40009831, 0xb85b485e),
    (0x40036a4d, 0xb8637d12),
    (0x4006386b, 0xb86b8eb1),
    (0x400901d5, 0xb8737bfd),
    (0x400bc5d4, 0xb87b43bd),
    (0x400e83ae, 0xb881725f),
    (0x40113aa8, 0xb8852eea),
    (0x4013ea06, 0xb888d6ea),
    (0x4016910b, 0xb88c69d1),
    (0x40192ef8, 0xb88fe711),
    (0x401bc30f, 0xb8934e21),
    (0x401e4c8f, 0xb8969e79),
    (0x4020caba, 0xb899d797),
    (0x40233cce, 0xb89cf8fc),
    (0x4025a20b, 0xb8a0022c),
    (0x4027f9b1, 0xb8a2f2b0),
    (0x402a42ff, 0xb8a5ca13),
    (0x402c7d37, 0xb8a887e6),
    (0x402ea799, 0xb8ab2bbb),
    (0x4030c166, 0xb8adb52b),
    (0x4032c9e3, 0xb8b023d2),
    (0x4034c051, 0xb8b2774f),
    (0x4036a3f7, 0xb8b4af48),
    (0x4038741b, 0xb8b6cb63),
    (0x403a3006, 0xb8b8cb4e),
    (0x403bd701, 0xb8baaebb),
    (0x403d6859, 0xb8bc755e),
    (0x403ee35c, 0xb8be1ef1),
    (0x4040475c, 0xb8bfab33),
    (0x404193ab, 0xb8c119e6),
    (0x4042c79f, 0xb8c26ad3),
    (0x4043e292, 0xb8c39dc4),
    (0x4044e3e0, 0xb8c4b28c),
    (0x4045cae7, 0xb8c5a8fe),
    (0x4046970b, 0xb8c680f5),
    (0x404747b2, 0xb8c73a51),
    (0x4047dc47, 0xb8c7d4f3),
    (0x40485436, 0xb8c850c5),
    (0x4048aef3, 0xb8c8adb3),
    (0x4048ebf3, 0xb8c8ebaf),
    (0x40490ab2, 0xb8c90ab0),
    (0x40490aae, 0xb8c90ab0),
    (0x4048eb6c, 0xb8c8ebaf),
    (0x4048ac74, 0xb8c8adb3),
    (0x40484d54, 0xb8c850c5),
    (0x4047cda0, 0xb8c7d4f3),
    (0x40472cef, 0xb8c73a51),
    (0x40466ae0, 0xb8c680f5),
    (0x40458715, 0xb8c5a8fe),
    (0x40448137, 0xb8c4b28c),
    (0x404358f6, 0xb8c39dc4),
    (0x40420e06, 0xb8c26ad3),
    (0x4040a021, 0xb8c119e6),
    (0x403f0f0a, 0xb8bfab33),
    (0x403d5a85, 0xb8be1ef1),
    (0x403b8262, 0xb8bc755e),
    (0x40398675, 0xb8baaebb),
    (0x40376697, 0xb8b8cb4e),
    (0x403522ab, 0xb8b6cb63),
    (0x4032ba98, 0xb8b4af48),
    (0x40302e4e, 0xb8b2774f),
    (0x402d7dc1, 0xb8b023d2),
    (0x402aa8f0, 0xb8adb52b),
    (0x4027afdd, 0xb8ab2bbb),
    (0x40249294, 0xb8a887e6),
    (0x40215127, 0xb8a5ca13),
    (0x401debaf, 0xb8a2f2b0),
    (0x401a624e, 0xb8a0022c),
    (0x4016b52a, 0xb89cf8fc),
    (0x4012e474, 0xb899d797),
    (0x400ef062, 0xb8969e79),
    (0x400ad932, 0xb8934e21),
    (0x40069f2b, 0xb88fe711),
    (0x40024298, 0xb88c69d1),
    (0x3ffb879e, 0xb888d6ea),
    (0x3ff24656, 0xb8852eea),
    (0x3fe8c220, 0xb881725f),
    (0x3fdefbd2, 0xb87b43bd),
    (0x3fd4f44f, 0xb8737bfd),
    (0x3fcaac8c, 0xb86b8eb1),
    (0x3fc0258a, 0xb8637d12),
    (0x3fb5605a, 0xb85b485e),
    (0x3faa5e1c, 0xb852f1da),
    (0x3f9f1ffd, 0xb84a7acf),
    (0x3f93a739, 0xb841e48a),
    (0x3f87f51c, 0xb839305f),
    (0x3f7815fc, 0xb8305fa6),
    (0x3f5fd48c, 0xb82773ba),
    (0x3f4728d1, 0xb81e6dfc),
    (0x3f2e15d1, 0xb8154fcf),
    (0x3f149eab, 0xb80c1a9c),
    (0x3ef58d33, 0xb802cfcf),
    (0x3ec121e4, 0xb7f2e1aa),
    (0x3e8c0248, 0xb7dffe43),
    (0x3e2c6ae0, 0xb7ccf851),
    (0x3d7e14f4, 0xb7b9d2c3),
    (0xbd3a75bf, 0xb7a6908e),
    (0xbe1deddd, 0xb79334aa),
    (0xbe872e32, 0xb77f8425),
    (0xbebfec80, 0xb758778f),
    (0xbef929ab, 0xb7314997),
    (0xbf196eac, 0xb70a004a),
    (0xbf367f82, 0xb6c54367),
    (0xbf53c300, 0xb66ccfa1),
    (0xbf7134bb, 0xb59de7df),
    (0xbf87681a, 0x359de7df),
    (0xbf96486e, 0x366ccfa1),
    (0xbfa53908, 0x36c54367),
    (0xbfb4378d, 0x370a004a),
    (0xbfc3419c, 0x37314997),
    (0xbfd254cb, 0x3758778f),
    (0xbfe16ea8, 0x377f8425),
    (0xbff08cba, 0x379334aa),
    (0xbfffac83, 0x37a6908e),
    (0xc00765bf, 0x37b9d2c3),
    (0xc00ef38e, 0x37ccf851),
    (0xc0167e69, 0x37dffe43),
    (0xc01e0503, 0x37f2e1aa),
    (0xc0258610, 0x3802cfcf),
    (0xc02d0040, 0x380c1a9c),
    (0xc0347243, 0x38154fcf),
    (0xc03bdac5, 0x381e6dfc),
    (0xc0433874, 0x382773ba),
    (0xc04a89fa, 0x38305fa6),
    (0xc051ce01, 0x3839305f),
    (0xc0590333, 0x3841e48a),
    (0xc0602838, 0x384a7acf),
    (0xc0673bb9, 0x3852f1da),
    (0xc06e3c60, 0x385b485e),
    (0xc07528d5, 0x38637d12),
    (0xc07bffc3, 0x386b8eb1),
    (0xc0815fea, 0x38737bfd),
    (0xc084b3d9, 0x387b43bd),
    (0xc087fb07, 0x3881725f),
    (0xc08b34c9, 0x38852eea),
    (0xc08e6078, 0x3888d6ea),
    (0xc0917d6e, 0x388c69d1),
    (0xc0948b05, 0x388fe711),
    (0xc0978898, 0x38934e21),
    (0xc09a7584, 0x38969e79),
    (0xc09d5128, 0x3899d797),
    (0xc0a01ae5, 0x389cf8fc),
    (0xc0a2d21c, 0x38a0022c),
    (0xc0a57630, 0x38a2f2b0),
    (0xc0a80689, 0x38a5ca13),
    (0xc0aa828e, 0x38a887e6),
    (0xc0ace9aa, 0x38ab2bbb),
    (0xc0af3b49, 0x38adb52b),
    (0xc0b176da, 0x38b023d2),
    (0xc0b39bd0, 0x38b2774f),
    (0xc0b5a99f, 0x38b4af48),
    (0xc0b79fbf, 0x38b6cb63),
    (0xc0b97daa, 0x38b8cb4e),
    (0xc0bb42de, 0x38baaebb),
    (0xc0bceedb, 0x38bc755e),
    (0xc0be8127, 0x38be1ef1),
    (0xc0bff947, 0x38bfab33),
    (0xc0c156c8, 0x38c119e6),
    (0xc0c29939, 0x38c26ad3),
    (0xc0c3c02b, 0x38c39dc4),
    (0xc0c4cb36, 0x38c4b28c),
    (0xc0c5b9f3, 0x38c5a8fe),
    (0xc0c68c00, 0x38c680f5),
    (0xc0c74102, 0x38c73a51),
    (0xc0c7d89d, 0x38c7d4f3),
    (0xc0c8527e, 0x38c850c5),
    (0xc0c8ae53, 0x38c8adb3),
    (0xc0c8ebd1, 0x38c8ebaf),
    (0xc0c90ab1, 0x38c90ab0),
)
SINE_TABLE = [{'base': from_bits(a), 'slope': from_bits(b)} for a, b in SINE_BITS]
CONSTANTS = dict(zip(range(0x4e5be8, 0x4e5c00, 4), map(from_bits,
    (0x3f65ae43, 0x3e23b485, 0x3dfd9dfb, 0x3b514270, 0x4622f7e2, 0xc612150c))))
THRESHOLD = from_bits(0x3f7ff2e5)
SCALE = from_bits(0x3ab55fa3)


def fixed_sine(angle: int, table: list[dict[str, Any]]) -> float:
    angle &= 0xFFFF
    entry = table[angle >> 8]
    return float(entry["base"]) + float(entry["slope"]) * angle


def fixed_angle_units(value: float, constants: dict[int, float]) -> int:
    """Binary64 semantic model of 0x21390; not an x87 bit-identity claim."""
    value = f32(value)
    if value < -1.0:
        return 0x8000
    if value > 1.0:
        return 0
    negative = value < 0.0
    work = -value if negative else value
    transformed = work > 0.5
    if transformed:
        work = f32(math.sqrt(f32((1.0 - work) * 0.5)))
    numerator = (
        (constants[0x004E5BFC] * work + constants[0x004E5BF8]) * work
        + constants[0x004E5BF4]
    )
    denominator = (
        (
            (work * constants[0x004E5BF0] - constants[0x004E5BEC]) * work
            - constants[0x004E5BE8]
        )
        * work
        + 1.0
    )
    approximation = numerator / denominator
    angle = 2.0 * approximation if transformed else 16384.0 - approximation
    if negative:
        angle = 32768.0 - angle
    return math.trunc(f32(angle + 0.5))


def cvtt_round_product(angle: int, t: float) -> int:
    product = float(angle) * f32(t)
    adjusted = product + 0.5 if product >= 0.0 else product - 0.5
    stored = f32(adjusted)
    if not math.isfinite(stored) or stored >= 2147483648.0 or stored < -2147483648.0:
        return -2147483648
    return math.trunc(stored)


def interpolate_reference(
    q0: Iterable[float],
    q1: Iterable[float],
    t: float,
    threshold: float,
    constants: dict[int, float],
    table: list[dict[str, Any]],
) -> dict[str, Any]:
    left = tuple(f32(value) for value in q0)
    right = tuple(f32(value) for value in q1)
    t = f32(t)
    dot = float(left[0]) * float(right[0])
    dot += float(left[1]) * float(right[1])
    dot += float(left[2]) * float(right[2])
    dot += float(left[3]) * float(right[3])
    negative = dot < 0.0
    absolute = -dot if negative else dot
    absolute_stored = f32(absolute)

    theta = -1
    step = -1
    if not math.isfinite(absolute) or absolute > threshold:
        branch = "linear"
        weight0 = 1.0 - t
        weight1 = float(t)
    else:
        branch = "fixed_slerp"
        theta = fixed_angle_units(absolute_stored, constants)
        step = cvtt_round_product(theta, t)
        denominator = fixed_sine(theta, table)
        inverse = 1.0 / denominator
        weight0 = fixed_sine((theta - step) & 0xFFFF, table) * inverse
        weight1 = fixed_sine(step & 0xFFFF, table) * inverse
    if negative:
        weight1 = -weight1
    output = tuple(
        f32(weight1 * float(right[lane]) + weight0 * float(left[lane]))
        for lane in range(4)
    )
    return {
        "dot": dot,
        "absolute_dot_stored": absolute_stored,
        "shortest_path_negated": negative,
        "branch": branch,
        "theta_units": theta,
        "step_units": step,
        "weight0": weight0,
        "weight1": weight1,
        "output": output,
    }



def interpolate(left, right, factor):
    return interpolate_reference(left, right, factor, THRESHOLD, CONSTANTS, SINE_TABLE)['output']


def unit(q):
    if len(q) != 4 or not all(math.isfinite(v) for v in q):
        raise ValueError('A rotation must contain four finite numbers')
    length = math.sqrt(sum(v*v for v in q))
    if length < 1e-12:
        raise ValueError('A rotation cannot have zero length')
    return tuple(v/length for v in q)


def decode(word):
    stored = [f32(((word >> shift) & 1023) - 512) * SCALE for shift in (20, 10, 0)]
    stored = [f32(v) for v in stored]
    radicand = f32(1.0 - f32(f32(f32(stored[0]*stored[0]) + f32(stored[1]*stored[1])) + f32(stored[2]*stored[2])))
    if radicand < 0:
        raise ValueError('Packed rotation has a negative square root')
    stored.insert(word >> 30, f32(math.sqrt(radicand)))
    return tuple(stored)


def encode(q, original):
    """Retain the original omission/sign when representable; reuse unchanged bits."""
    q = unit(q)
    before = unit(decode(original))
    if min(max(abs(a-b) for a,b in zip(q,before)),
           max(abs(a+b) for a,b in zip(q,before))) <= 2e-7:
        return original
    preferred = original >> 30
    for omitted in [preferred] + [i for i in sorted(range(4), key=lambda i: -abs(q[i])) if i != preferred]:
        sign = -1 if q[omitted] < 0 else 1
        lanes = [int(math.floor(sign*q[i]/SCALE + 512.5)) for i in range(4) if i != omitted]
        if all(0 <= v <= 1023 for v in lanes):
            word = (omitted << 30) | (lanes[0] << 20) | (lanes[1] << 10) | lanes[2]
            try:
                decoded = unit(decode(word))
            except ValueError:
                continue
            dot = min(1.0, abs(sum(a*b for a,b in zip(q,decoded))))
            if math.degrees(2*math.acos(dot)) <= 0.35:
                return word
    raise ValueError('Rotation cannot fit the native encoding')


def multiply(a, b):
    w,x,y,z = a
    v,i,j,k = b
    return (w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
            w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v)


def conjugate(q):
    return (q[0], -q[1], -q[2], -q[3])


def rotate(q, v):
    return multiply(multiply(q, (0.0, *v)), conjugate(q))[1:]


REF_MAP = (0,0,1,5,2,6,3,7,4,8,5,1,6,2,7,3,8,4,9,9,10,10,11,11,12,12,
           13,17,14,18,-1,-1,15,19,-1,-1,16,20,17,13,18,14,-1,-1,19,15,-1,-1,20,16)
PLAYER_MAP = (0,0,1,5,2,6,3,7,4,8,5,1,6,2,7,3,8,4,9,9,10,10,11,11,12,12,
              13,17,14,18,15,19,-1,-1,16,20,17,13,18,14,19,15,-1,-1,20,16,21,22,22,21)
REF_AXES = tuple(tuple(float.fromhex(v) for v in row) for row in (
    ('0x1.9966d0p+3', '-0x1.7dba46p+1', '0x1.a8fa40p+2'),
    ('-0x1.998ea0p+3', '-0x1.7dcf04p+1', '0x1.a87854p+2')))
PLAYER_AXES = tuple(tuple(float.fromhex(v) for v in row) for row in (
    ('0x1.1f59c0p+3', '-0x1.71480cp-2', '0x1.a2db40p+2'),
    ('-0x1.1f3e5cp+3', '-0x1.716e02p-2', '0x1.a321d2p+2')))


def twist(axis, q, half):
    dot = lambda a,b: sum(x*y for x,y in zip(a,b))
    norm = dot(axis,axis)
    perpendicular = (-axis[1],axis[0],0) if axis[0] or axis[1] else (1,0,0)
    rotated = rotate(q, perpendicular)
    projected = tuple(v-a*dot(rotated,axis)/norm for v,a in zip(rotated,axis))
    divisor = math.sqrt(dot(projected,projected)*dot(perpendicular,perpendicular))
    if divisor == 0:
        raise ValueError('Cannot resolve a derived joint from this rotation')
    cosine = max(-1.0,min(1.0,dot(perpendicular,projected)/divisor))
    cross = (perpendicular[1]*projected[2]-perpendicular[2]*projected[1],
             perpendicular[2]*projected[0]-perpendicular[0]*projected[2],
             perpendicular[0]*projected[1]-perpendicular[1]*projected[0])
    if half:
        cosine = math.sqrt((1+cosine)*0.5)
    scale = math.sqrt((1-cosine)*0.5)/math.sqrt(norm)
    if dot(cross,axis) < 0:
        scale = -scale
    return tuple(f32(v) for v in (math.sqrt((1+cosine)*0.5), *(a*scale for a in axis)))


def complete_pose(pose, family):
    pose = list(pose)
    if family == 'referee':
        for axis, source, derived in zip(REF_AXES,(14,20),(15,21)):
            q = twist(axis,pose[source],True)
            pose[source] = tuple(map(f32,multiply(pose[source],conjugate(q))))
            pose[derived] = q
    elif family == 'player':
        for axis, source, derived in zip(PLAYER_AXES,(17,22),(16,21)):
            q = twist(axis,pose[source],False)
            pose[source] = tuple(map(f32,multiply(conjugate(q),pose[source])))
            pose[derived] = q
    return tuple(pose)

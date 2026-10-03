"""Platform-independent math for the pinned model compiles: the same double on every platform.

The stadium models pin the bytes they compile. Their geometry, lights and cameras go through sin, cos, atan2, pow and
hypot, and the C library behind ``math`` and numpy rounds those differently on Windows, Linux and macOS (main,
2026-10-02: the installer's Windows CPython moved SoFi screen vertices by one unit in the last place, and the build
stopped with "SoFi Stadium state is foreign"; ``x ** y`` is the C library's pow too). Here:

* sin, cos, tan, asin, acos, atan, atan2, exp, log and pow return the exact value rounded to the nearest double (ties
  to even), computed with Python integers alone;
* hypot and dist are CPython's own (correctly rounded in practice, the same since 3.10), not the C library's;
* glibc_hypot and np_hypot are glibc's hypot algorithm in plain IEEE arithmetic: numpy.hypot on glibc recorded the
  pins, and it is not correctly rounded;
* the other names (pi, sqrt, floor, radians, ...) are the exact ``math`` originals, and the C library's remaining
  transcendental functions are left out on purpose;
* np_dot, np_matmul, np_norm, np_solve and np_det are numpy's BLAS and LAPACK products as the pins' reference machine
  computed them (OpenBLAS's Haswell/Zen kernels), in IEEE arithmetic and an exact FMA: other CPUs' kernels round
  differently.

The model modules use it in place of ``math`` (``from . import exact_math as math``); ``np_arctan2``, ``np_hypot`` and
``np_power`` are the numpy forms of the functions above (float64, elementwise).
"""
from __future__ import annotations

from functools import lru_cache
from math import (ceil, copysign, degrees, dist, e, fabs, floor, frexp, fsum, hypot, inf, isclose, isfinite, isinf,
                  isnan, isqrt, ldexp, nan, nextafter, pi, radians, sqrt, tau, trunc, ulp)
import math as _math

#: the first working precision in bits after the binary point; a result too close to a rounding boundary doubles it
_BITS = 128
#: guard bits under the working precision: every fixed-point value below is within 2 units of its true value
_GUARD = 24


def _rounded(y, err, bits):
    """The double nearest ``y / 2**bits`` when everything within ``err / 2**bits`` of it rounds there too, else None."""
    one = 1 << bits
    lo, hi = (y - err) / one, (y + err) / one
    return lo if lo == hi and copysign(1.0, lo) == copysign(1.0, hi) else None


def _ziv(compute, bits=_BITS):
    """``compute(bits) -> (y, err)`` at doubling precision until the result's rounding is certain."""
    while True:
        out = _rounded(*compute(bits), bits)
        if out is not None:
            return out
        bits *= 2


def _fixed(x, bits):
    """A finite double times ``2**bits`` (floor; exact once ``bits`` covers its last bit)."""
    n, d = x.as_integer_ratio()
    s = d.bit_length() - 1
    return n << (bits - s) if bits >= s else n >> (s - bits)


@lru_cache(maxsize=None)
def _pi(bits):
    """pi * 2**bits within 2 (Machin's formula)."""
    g = bits + _GUARD

    def acot(n):
        t = s = (1 << g) // n
        k = 1
        while t:
            t //= n * n
            s += (-1) ** k * (t // (2 * k + 1))
            k += 1
        return s
    return (16 * acot(5) - 4 * acot(239)) >> _GUARD


@lru_cache(maxsize=None)
def _ln2(bits):
    """log(2) * 2**bits within 2 (twice atanh(1/3))."""
    g = bits + _GUARD
    t, s, k = (1 << g) // 3, 0, 0
    while t:
        s += t // (2 * k + 1)
        t //= 9
        k += 1
    return (2 * s) >> _GUARD


@lru_cache(maxsize=None)
def _atan_eighths(bits):
    """atan(j / 8) * 2**bits for j = 0..8, each within 2 (Euler's series)."""
    g = bits + _GUARD
    out = []
    for j in range(9):
        num, den = j * j, 64 + j * j
        t, s, i = (8 * j << g) // den, 0, 0
        while t:
            s += t
            i += 1
            t = t * 2 * i * num // ((2 * i + 1) * den)
        out.append(s >> _GUARD)
    return tuple(out)


def _sincos(x, bits):
    """(sin x, cos x) * 2**bits for a finite double x, each within 2."""
    n, d = x.as_integer_ratio()
    kb = max(0, n.bit_length() - d.bit_length()) + 2          # |x| / (pi / 2) < 2**kb
    p = bits + _GUARD
    g = p + kb + 8
    xg = _fixed(x, g)
    half = _pi(g - 1)                                         # pi / 2 * 2**g within 2
    k = (2 * xg + half) // (2 * half)                         # x = k pi / 2 + r, |r| <= pi / 4
    r = (xg - k * half) >> (g - p)
    neg = r < 0
    r = -r if neg else r
    r2 = r * r >> p
    t = s = r
    i, sign = 1, -1
    while t:
        t = (t * r2 >> p) // ((i + 1) * (i + 2))
        s += sign * t
        i, sign = i + 2, -sign
    t = c = 1 << p
    i, sign = 0, -1
    while t:
        t = (t * r2 >> p) // ((i + 1) * (i + 2))
        c += sign * t
        i, sign = i + 2, -sign
    s, c = (-s if neg else s) >> _GUARD, c >> _GUARD
    return ((s, c), (c, -s), (-s, -c), (-c, s))[k % 4]


def sin(x):
    x = float(x)
    if not isfinite(x):
        return _math.sin(x)
    if fabs(x) < 2.0 ** -26:                                  # sin x = x - x**3 / 6 + ... rounds to x
        return x
    return _ziv(lambda bits: (_sincos(x, bits)[0], 2))


def cos(x):
    x = float(x)
    if not isfinite(x):
        return _math.cos(x)
    if fabs(x) < 2.0 ** -27:                                  # cos x = 1 - x**2 / 2 + ... rounds to 1
        return 1.0
    return _ziv(lambda bits: (_sincos(x, bits)[1], 2))


def tan(x):
    x = float(x)
    if not isfinite(x):
        return _math.tan(x)
    if fabs(x) < 2.0 ** -27:                                  # tan x = x + x**3 / 3 + ... rounds to x
        return x

    def compute(bits):
        s, c = _sincos(x, bits)
        if abs(c) <= 4:
            return 0, 1 << 2 * bits                           # too near a pole for this precision
        t = (s << bits) // c
        return t, ((2 << bits) + 2 * abs(t)) // (abs(c) - 2) + 2
    return _ziv(compute)


def _atan_ratio(a, b, bits):
    """atan(a / b) * 2**bits within 2, for integers a >= 0 and b > 0."""
    p = bits + _GUARD
    flip = a > b                                              # atan(a / b) = pi / 2 - atan(b / a)
    if flip:
        a, b = b, a
    j = (16 * a + b) // (2 * b)                               # the nearest eighth to a / b
    num, den = 8 * a - j * b, 8 * b + j * a                   # atan(a / b) = atan(j / 8) + atan(num / den)
    u = (abs(num) << p) // den
    u2 = u * u >> p
    t = s = u
    i, sign = 1, -1
    while t:
        t = t * u2 >> p
        s += sign * (t // (2 * i + 1))
        i, sign = i + 1, -sign
    t = _atan_eighths(p)[j] + (-s if num < 0 else s)
    return (_pi(p - 1) - t if flip else t) >> _GUARD


def atan2(y, x):
    y, x = float(y), float(x)
    if not (isfinite(x) and isfinite(y)):
        return _math.atan2(y, x)
    if y == 0.0:
        return copysign(0.0 if copysign(1.0, x) > 0 else pi, y)
    if x == 0.0:
        return copysign(pi / 2, y)
    (yn, yd), (xn, xd) = fabs(y).as_integer_ratio(), fabs(x).as_integer_ratio()
    a, b = yn * xd, xn * yd                                   # |y / x| = a / b exactly

    def compute(bits):
        t = _atan_ratio(a, b, bits)
        return (_pi(bits) - t, 4) if x < 0 else (t, 2)
    return copysign(_ziv(compute, _BITS + max(0, b.bit_length() - a.bit_length())), y)


def atan(x):
    return atan2(x, 1.0)


def asin(x):
    x = float(x)
    if not isfinite(x) or fabs(x) > 1.0:
        return _math.asin(x)
    if fabs(x) < 2.0 ** -26:                                  # asin x = x + x**3 / 6 + ... rounds to x
        return x
    if fabs(x) == 1.0:
        return copysign(pi / 2, x)
    n, d = fabs(x).as_integer_ratio()
    root = d * d - n * n                                      # asin |x| = atan(n / sqrt(d**2 - n**2))

    def compute(bits):
        g = bits + _GUARD
        return _atan_ratio(n << g, isqrt(root << 2 * g), bits), 3
    return copysign(_ziv(compute), x)


def acos(x):
    x = float(x)
    if not isfinite(x) or fabs(x) > 1.0:
        return _math.acos(x)
    if x == 1.0:
        return 0.0
    if x == 0.0:
        return pi / 2
    if x == -1.0:
        return pi
    n, d = fabs(x).as_integer_ratio()
    root = d * d - n * n                                      # acos |x| = atan(sqrt(d**2 - n**2) / n)

    def compute(bits):
        g = bits + _GUARD
        t = _atan_ratio(isqrt(root << 2 * g), n << g, bits)
        return (_pi(bits) - t, 4) if x < 0 else (t, 3)
    return _ziv(compute)


def _exp_scaled(z, bits):
    """exp(z / 2**bits) as (k, y): 2**k * y / 2**bits, y within 4 (z itself within 2)."""
    p = bits + _GUARD
    zp = z << _GUARD
    ln2 = _ln2(p)
    k = (2 * zp + ln2) // (2 * ln2)
    r = zp - k * ln2                                          # exp(z) = 2**k exp(r), |r| <= log(2) / 2
    neg = r < 0
    r = -r if neg else r
    t = y = 1 << p
    i = 1
    while t:
        t = (t * r >> p) // i
        y += -t if neg and i & 1 else t
        i += 1
    return k, y >> _GUARD


def _scaled(k, y, err, bits):
    """The double nearest 2**k * y / 2**bits when 2**k * err / 2**bits cannot change it, else None."""
    if k >= 0:
        return _rounded(y << k, err << k, bits)
    return _rounded(y, err, bits - k)


def exp(x):
    x = float(x)
    if not isfinite(x) or x == 0.0:
        return _math.exp(x)
    if x > 710.0:
        raise OverflowError("math range error")
    if x < -746.0:
        return 0.0
    bits = _BITS
    while True:
        k, y = _exp_scaled(_fixed(x, bits), bits)
        out = _scaled(k, y, 4, bits)
        if out is not None:
            return out
        bits *= 2


def _log_fixed(x, bits):
    """log(x) * 2**bits within 2, for a finite double x > 0."""
    m, ex = frexp(x)
    if m < 0.7071067811865476:                                # keep m in [sqrt(1/2), sqrt(2))
        m, ex = 2.0 * m, ex - 1
    n, d = m.as_integer_ratio()
    p = bits + _GUARD
    u = (abs(n - d) << p) // (n + d)                          # log m = 2 atanh((m - 1) / (m + 1))
    u2 = u * u >> p
    t = s = u
    i = 1
    while t:
        t = t * u2 >> p
        s += t // (2 * i + 1)
        i += 1
    return (ex * _ln2(p) + (-2 * s if n < d else 2 * s)) >> _GUARD


def log(x):
    x = float(x)
    if not isfinite(x) or x <= 0.0 or x == 1.0:
        return _math.log(x)
    return _ziv(lambda bits: (_log_fixed(x, bits), 2))


def pow(x, y):
    x, y = float(x), float(y)
    if y == 0.0 or x == 1.0 or x == 0.0 or not (isfinite(x) and isfinite(y)):
        return _math.pow(x, y)                                # the exact special cases, and math's errors
    whole = y.is_integer()
    if x < 0.0 and not whole:
        raise ValueError("math domain error")
    sign = -1.0 if x < 0.0 and int(y) % 2 else 1.0
    ax = fabs(x)
    if whole and fabs(y) <= 64:                               # an exact power of an exact fraction
        n, d = ax.as_integer_ratio()
        p = int(y)
        try:
            return sign * (n ** p / d ** p if p > 0 else d ** -p / n ** -p)
        except OverflowError:
            raise OverflowError("math range error") from None
    yn, yd = y.as_integer_ratio()
    ys = yd.bit_length() - 1
    lift = max(0, yn.bit_length() - ys) + 4                   # |y| < 2**(lift - 4)
    bits = _BITS
    while True:
        z = yn * _log_fixed(ax, bits + lift) >> (ys + lift)  # y log|x| * 2**bits within 2
        if z > 710 << bits:
            raise OverflowError("math range error")
        if z < -746 << bits:
            return sign * 0.0
        k, out = _exp_scaled(z, bits)
        out = _scaled(k, out, 8, bits)                        # 4 from exp, 2 from z (times exp(r) < 1.5)
        if out is not None:
            return sign * out
        bits *= 2


# -- glibc's hypot ---------------------------------------------------------------------------------------------------

def _hypot_kernel(ax, ay):
    h = sqrt(ax * ax + ay * ay)
    if h <= 2.0 * ay:
        d = h - ay
        t1, t2 = ax * (2.0 * d - ax), (d - 2.0 * (ax - ay)) * d
    else:
        d = h - ax
        t1, t2 = 2.0 * d * (ax - 2.0 * ay), (4.0 * d - ay) * ay + d * d
    return h - (t1 + t2) / (2.0 * h)


def glibc_hypot(x, y):
    """hypot(x, y) exactly as glibc 2.35 and later computes it (the kernel without FMA, after Borges 2019), in plain
    IEEE arithmetic, so the same everywhere. It is not correctly rounded (about 0.6% of results are one unit off), but
    the pins were recorded with numpy.hypot on glibc, and Windows' and macOS's hypot round differently again."""
    x, y = fabs(float(x)), fabs(float(y))
    if not (isfinite(x) and isfinite(y)):
        return inf if isinf(x) or isinf(y) else x + y
    ax, ay = (y, x) if x < y else (x, y)
    if ax > 2.0 ** 511:
        return ax + ay if ay <= ax * 2.0 ** -54 else _hypot_kernel(ax * 2.0 ** -600, ay * 2.0 ** -600) * 2.0 ** 600
    if ay < 2.0 ** -511:
        return ax + ay if ax >= ay * 2.0 ** 54 else _hypot_kernel(ax * 2.0 ** 600, ay * 2.0 ** 600) * 2.0 ** -600
    return ax + ay if ay <= ax * 2.0 ** -54 else _hypot_kernel(ax, ay)


# -- numpy forms (float64, elementwise; numpy loads on first use) ----------------------------------------------------

def _np_map(function, *arrays):
    import numpy as np
    args = np.broadcast_arrays(*(np.asarray(a, dtype=np.float64) for a in arrays))
    if not args[0].ndim:
        return np.float64(function(*(float(a) for a in args)))
    out = np.array([function(*v) for v in zip(*(a.ravel().tolist() for a in args))], dtype=np.float64)
    return out.reshape(args[0].shape)


def np_arctan2(y, x):
    return _np_map(atan2, y, x)


def np_power(x, y):
    return _np_map(pow, x, y)


def np_hypot(x, y):
    """numpy.hypot with :func:`glibc_hypot`, vectorized."""
    import numpy as np
    x = np.abs(np.asarray(x, dtype=np.float64))
    y = np.abs(np.asarray(y, dtype=np.float64))
    if not (x.ndim or y.ndim):
        return np.float64(glibc_hypot(x, y))
    ax, ay = np.maximum(x, y), np.minimum(x, y)
    with np.errstate(all="ignore"):
        big = ax > 2.0 ** 511
        tiny = ~big & (ay < 2.0 ** -511)
        scale = np.where(big, 2.0 ** -600, np.where(tiny, 2.0 ** 600, 1.0))
        a, b = ax * scale, ay * scale
        h = np.sqrt(a * a + b * b)
        d1, d2 = h - b, h - a
        near = h <= 2.0 * b
        t1 = np.where(near, a * (2.0 * d1 - a), 2.0 * d2 * (a - 2.0 * b))
        t2 = np.where(near, (d1 - 2.0 * (a - b)) * d1, (4.0 * d2 - b) * b + d2 * d2)
        out = (h - (t1 + t2) / (2.0 * h)) / scale
        out = np.where(np.where(tiny, ax >= ay * 2.0 ** 54, ay <= ax * 2.0 ** -54), ax + ay, out)
        return np.where(np.isinf(x) | np.isinf(y), np.inf, out)


# -- numpy's BLAS and LAPACK products, as the pins' reference computed them -------------------------------------------
# numpy hands float64 dot and matrix products, 2 x 2 solves and determinants to OpenBLAS, whose kernels differ by CPU:
# the pins were recorded with its Haswell/Zen kernels, and the pre-2013 and AVX-512 kernels (Ryzen 7000 and later,
# Intel's 11th generation) add in other orders, with or without FMA (main, 2026-10-02: under OPENBLAS_CORETYPE=
# Sandybridge every bundle of twelve model stadiums came out foreign). The functions below reproduce the reference
# kernels' arithmetic exactly with IEEE operations and an exact FMA; a shape they do not cover goes to numpy.

def fma(a, b, c):
    """a * b + c rounded once, as the FMA instruction computes it (exact integers)."""
    a, b, c = float(a), float(b), float(c)
    if not (isfinite(a) and isfinite(b) and isfinite(c)):
        return a * b + c
    (an, ad), (bn, bd), (cn, cd) = a.as_integer_ratio(), b.as_integer_ratio(), c.as_integer_ratio()
    num, den = an * bn, ad * bd
    if den >= cd:
        num += cn * (den // cd)
    else:
        num, den = num * (cd // den) + cn, cd
    if num:
        return num / den
    return -0.0 if copysign(1.0, a) * copysign(1.0, b) < 0 and copysign(1.0, c) < 0 else 0.0


def _ddot(x, y, unit):
    """OpenBLAS ddot: unit-stride vectors take FMA lanes over blocks of 16 (four registers of four lanes), then the
    rest in order; strided vectors keep two interleaved sums."""
    n = len(x)
    if not unit:
        t1 = t2 = 0.0
        n4 = n & -4
        for i in range(0, n4, 4):
            t1 += x[i] * y[i] + x[i + 2] * y[i + 2]
            t2 += x[i + 1] * y[i + 1] + x[i + 3] * y[i + 3]
        for i in range(n4, n):
            t1 += x[i] * y[i]
        return t1 + t2
    dot = 0.0
    n16 = n & -16
    if n16:
        acc = [0.0] * 16
        for i in range(0, n16, 16):
            for j in range(16):
                acc[j] = fma(x[i + j], y[i + j], acc[j])
        half = [acc[j] + acc[j + 2] for j in (0, 1, 4, 5, 8, 9, 12, 13)]
        lanes = [(half[k] + half[k + 2]) + (half[k + 4] + half[k + 6]) for k in (0, 1)]
        dot = lanes[0] + lanes[1]
    for i in range(n16, n):
        dot += x[i] * y[i]
    return dot


def _plain_dot(x, y):
    s = 0.0
    for a, b in zip(x, y):
        s += a * b
    return s


def _vector_dot(a, b):
    """numpy's float64 dot of two 1-D arrays: BLAS for positive strides, its own loop otherwise."""
    sa, sb = a.strides[0], b.strides[0]
    if sa > 0 and sb > 0 and not sa % 8 and not sb % 8:
        return 0.0 + _ddot(a.tolist(), b.tolist(), sa == 8 and sb == 8)
    return _plain_dot(a.tolist(), b.tolist())


def _row_major(a):
    """numpy's test that BLAS takes a 2-D float64 array row by row."""
    return a.strides[1] == 8 and a.strides[0] > 0 and not a.strides[0] % 8 and a.strides[0] // 8 >= a.shape[1]


def _gemv_row(row, x):
    """One output of OpenBLAS dgemv_t for one to three columns (its tail code, compiled with FMA)."""
    if len(x) == 3:
        return fma(row[2], x[2], fma(row[0], x[0], row[1] * x[1]))
    if len(x) == 2:
        return fma(row[0], x[0], row[1] * x[1])
    return 0.0 + row[0] * x[0]


def _gemm_entry(row, col):
    s = row[0] * col[0]
    for a, b in zip(row[1:], col[1:]):
        s = fma(a, b, s)
    return s


def _product(a, b, copy_bad):
    """numpy.dot / numpy.matmul of float64 arrays of up to two dimensions as the reference kernels compute it, or
    None for a case they do not cover. ``copy_bad``: numpy.dot copies arrays with negative or zero strides first."""
    import numpy as np
    a, b = np.asarray(a), np.asarray(b)
    if np.result_type(a, b) != np.float64 or not (1 <= a.ndim <= 2 and 1 <= b.ndim <= 2):
        return None
    a, b = a.astype(np.float64, copy=False), b.astype(np.float64, copy=False)
    if copy_bad:
        a, b = (v if all(s > 0 and not s % 8 or s == 0 and d < 2 for s, d in zip(v.strides, v.shape)) else v.copy()
                for v in (a, b))
    if a.shape[-1] != b.shape[0]:
        return None
    if a.ndim == 1 and b.ndim == 1:
        return np.float64(_vector_dot(a, b))
    if a.ndim == 2 and b.ndim == 1:
        if a.shape[0] == 1:
            return np.array([_vector_dot(a[0], b)])
        if a.shape[1] > 3 or not _row_major(a) or b.strides[0] <= 0 or b.strides[0] % 8:
            return None
        x = b.tolist()
        return np.array([_gemv_row(row, x) for row in a.tolist()], dtype=np.float64).reshape(a.shape[0])
    if a.ndim == 1:
        if b.shape[1] == 1:
            return np.array([_vector_dot(a, b[:, 0])])
        if b.shape[0] > 3 or not _row_major(b):
            return None
        x = a.tolist()
        return np.array([_plain_dot(x, col) for col in b.T.tolist()])
    if min(a.shape[0], a.shape[1], b.shape[1]) < 2 or not (_row_major(a) and _row_major(b)):
        return None
    cols = b.T.tolist()
    return np.array([[_gemm_entry(row, col) for col in cols] for row in a.tolist()])


def np_dot(a, b):
    import numpy as np
    out = _product(a, b, True)
    return np.dot(a, b) if out is None else out


def np_matmul(a, b):
    import numpy as np
    out = _product(a, b, False)
    return np.matmul(a, b) if out is None else out


def np_norm(x, ord=None, axis=None, keepdims=False):
    """numpy.linalg.norm; the 2-norm of the whole array is the reference's BLAS dot (an axis needs no BLAS)."""
    import numpy as np
    x = np.asarray(x)
    if ord is not None or axis is not None or not (x.dtype == np.float64 or x.dtype.kind in "biu"):
        return np.linalg.norm(x, ord=ord, axis=axis, keepdims=keepdims)
    flat = x.astype(np.float64, copy=False).ravel(order="K").tolist()
    out = np.sqrt(np.float64(0.0 + _ddot(flat, flat, True)))
    return out.reshape((1,) * x.ndim) if keepdims else out


def _lu2(m):
    """OpenBLAS getf2 of a 2 x 2 matrix: ((a00, a01), (l, u11), swapped)."""
    (a00, a01), (a10, a11) = m
    swap = fabs(a10) > fabs(a00)
    if swap:
        a00, a01, a10, a11 = a10, a11, a00, a01
    l = a10 * (1.0 / a00)
    return (a00, a01), (l, a11 - l * a01), swap


def np_solve(m, rhs):
    """numpy.linalg.solve for one 2 x 2 system as OpenBLAS's dgesv computes it (others go to numpy)."""
    import numpy as np
    m, rhs = np.asarray(m, dtype=np.float64), np.asarray(rhs, dtype=np.float64)
    if m.shape != (2, 2) or rhs.shape != (2,):
        return np.linalg.solve(m, rhs)
    (a00, a01), (l, u11), swap = _lu2(m.tolist())
    b0, b1 = rhs.tolist()[::-1] if swap else rhs.tolist()
    if a00 == 0.0 or u11 == 0.0:
        return np.linalg.solve(m, rhs)                            # singular: numpy raises
    x1 = (b1 - l * b0) / u11
    return np.array([(b0 - a01 * x1) / a00, x1])


def np_det(m):
    """numpy.linalg.det of a 2 x 2 matrix: numpy's sign * exp(sum of log |u_ii|) over the LU factors."""
    import numpy as np
    m = np.asarray(m, dtype=np.float64)
    if m.shape != (2, 2):
        return np.linalg.det(m)
    (a00, _a01), (_l, u11), swap = _lu2(m.tolist())
    if a00 == 0.0 or u11 == 0.0:
        return np.float64(0.0)
    sign = (-1.0 if swap else 1.0) * copysign(1.0, a00) * copysign(1.0, u11)
    return np.float64(sign * exp(log(fabs(a00)) + log(fabs(u11))))

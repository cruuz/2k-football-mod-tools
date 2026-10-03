"""exact_math: correctly rounded math, the same double on every platform, for the pinned model compiles (main,
2026-10-02: the installer's Windows CPython rounded sin, cos and pow differently from glibc, and a build stopped with
"SoFi Stadium state is foreign")."""
import ast
import json
import math
import random
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import exact_math as xm  # noqa: E402

#: (function, arguments, correctly rounded binary64 result). Original references use mpmath at 300 bits; the
#: two macOS tan regressions use MPFR directed enclosures at 300, 600 and 1200 bits. The first nine are SoFi inputs
#: where Wine's C library rounds differently from glibc; other cases exercise rounding differences in platform libm.
VECTORS = (
    ("cos", ("0x1.197c987c952c4p-1",), "0x1.b48d406a50540p-1"),
    ("cos", ("0x1.6e6127ff9d970p-1",), "0x1.82694b4a11c38p-1"),
    ("pow", ("0x1.82694b4a11c38p-1", "0x1.89d89d89d89d8p-1"), "0x1.9c56cc494f069p-1"),
    ("cos", ("0x1.72d8f9a8323e6p-1",), "0x1.7f771fcde1b9fp-1"),
    ("pow", ("0x1.7f771fcde1b9fp-1", "0x1.89d89d89d89d8p-1"), "0x1.99eb31e83f048p-1"),
    ("pow", ("0x1.797c6a435ce84p-1", "0x1.89d89d89d89d8p-1"), "0x1.94fe382631103p-1"),
    ("sin", ("0x1.00e9975d63941p+0",), "0x1.afd100eafc290p-1"),
    ("sin", ("0x1.03258031ade7cp+0",), "0x1.b2335c2cda945p-1"),
    ("sin", ("0x1.12c8ddffb6315p+1",), "0x1.ad663a8ae2fdbp-1"),
    ("sin", ("0x1.29023f50cdd7cp+3",), "0x1.246189f6c1465p-3"),
    ("sin", ("-0x1.45d2dd6e0c29bp+2",), "0x1.dbbd936b54a85p-1"),
    ("sin", ("-0x1.b7d9ac64f0714p+1",), "0x1.2975eae4e8439p-2"),
    ("cos", ("-0x1.3de0eba1e7a40p+2",), "0x1.01c4a9fec4c89p-2"),
    ("cos", ("0x1.16422ed330e6cp+2",), "-0x1.6d2208f50412fp-2"),
    ("cos", ("-0x1.24bdd74715868p+2",), "-0x1.1a57264968599p-3"),
    ("tan", ("0x1.ae65906921bd0p-3",), "0x1.b4d8cbe1496dfp-3"),
    ("tan", ("-0x1.447f4bdd0fc0fp+0",), "-0x1.991b0395ddc53p+1"),
    ("tan", ("0x1.cf68b0e884fa8p-1",), "0x1.45ff9293aa16bp+0"),
    ("tan", ("0x1.f595181def544p-1",), "0x1.7d66362f29e1bp+0"),
    ("asin", ("-0x1.61532c00b9a3ep-1",), "-0x1.85f1c55f97529p-1"),
    ("asin", ("0x1.73f3b3c425b32p-1",), "0x1.a057b5d1bc80bp-1"),
    ("exp", ("0x1.d0263bae60920p+0",), "0x1.8846bc86dfa7dp+2"),
    ("exp", ("0x1.085060f3aacb0p+4",), "0x1.c7f708be0ea89p+23"),
    ("log", ("0x1.341c11cf56c29p+1",), "0x1.c1c0fb15c9699p-1"),
    ("log", ("0x1.4d7ecded0fd28p+8",), "0x1.73d0f5924ceccp+2"),
    ("atan2", ("-0x1.8ee714fc76148p+5", "0x1.cf5ccdd0dd0acp+7"), "-0x1.b226ca79a3a57p-3"),
    ("atan2", ("-0x1.38c366ab76e4ap+8", "0x1.63d5ae78a3c46p+8"), "-0x1.712fa32913b20p-1"),
    ("atan2", ("0x1.0dbf9ce0773b0p+8", "0x1.be30759071d04p+7"), "0x1.c27277db729e1p-1"),
    ("pow", ("0x1.649ec79fbd3fbp+7", "0x1.0000000000000p+1"), "0x1.f0c9fdaf4b308p+14"),
    ("pow", ("0x1.c38e918cdd1a7p+7", "0x1.0000000000000p+1"), "0x1.8e3fd21e0f08ap+15"),
    ("pow", ("0x1.d3e602b2eb3c3p+8", "0x1.0000000000000p+1"), "0x1.ab987e40cfe1cp+17"),
)

#: (x, y, glibc's hypot, the correctly rounded hypot): np_hypot keeps glibc's rounding, the pins were recorded with it
HYPOT = (
    ("-0x1.587e11db8fe3cp+8", "-0x1.40bcc7b2a77b2p+7", "0x1.7bfdb3c3346dbp+8", "0x1.7bfdb3c3346dap+8"),
    ("0x1.d1f358b71ec3cp+7", "0x1.1ac4344aa0520p+6", "0x1.e6eda3a9797c5p+7", "0x1.e6eda3a9797c4p+7"),
    ("0x1.67defb55f9a00p+7", "0x1.4ee90ad407c70p+7", "0x1.eb99feabf2eb2p+7", "0x1.eb99feabf2eb3p+7"),
    ("-0x1.636952ac31864p+8", "0x1.5850308ca0cfap+8", "0x1.eed79fc4294c6p+8", "0x1.eed79fc4294c5p+8"),
)


class CorrectlyRounded(unittest.TestCase):
    def test_vectors(self):
        for name, args, want in VECTORS:
            with self.subTest(name=name, args=args):
                self.assertEqual(getattr(xm, name)(*(float.fromhex(a) for a in args)).hex(), want)

    def test_seeded_samples_match_independent_mpfr_vectors(self):
        # Platform libm is not an accuracy oracle: macOS tan differs by two ULPs
        # on the explicit regressions above. These independent MPFR RNDD/RNDU
        # enclosures both round to the same nearest/even binary64. No MPFR is
        # needed at test time; preserve every original custom-function draw.
        corpus = json.loads((ROOT / "tests/mod_editor/exact_math_mpfr_vectors.json").read_text(encoding="utf-8"))
        self.assertEqual(corpus["schema"], "exact_math_mpfr_vectors/v1")
        rng = random.Random(20261002)
        cases = dict(sin=lambda: (rng.uniform(-1e3, 1e3),), cos=lambda: (rng.uniform(-1e3, 1e3),),
                     tan=lambda: (rng.uniform(-1.5, 1.5),), asin=lambda: (rng.uniform(-1, 1),),
                     acos=lambda: (rng.uniform(-1, 1),), atan=lambda: (rng.uniform(-50, 50),),
                     exp=lambda: (rng.uniform(-700, 700),), log=lambda: (rng.uniform(1e-9, 1e9),),
                     atan2=lambda: (rng.uniform(-500, 500), rng.uniform(-500, 500)),
                     pow=lambda: (rng.uniform(0, 100), rng.uniform(-4, 4)))
        # hypot is the math.hypot alias, verified by the identity and fixed-value
        # tests below; comparing that function with itself adds no coverage.
        self.assertEqual(len(corpus["vectors"]), 300 * len(cases))
        references = iter(corpus["vectors"])
        for name, draw in cases.items():
            for _ in range(300):
                args = draw()
                reference = next(references)
                with self.subTest(name=name, args=args):
                    self.assertEqual(reference["function"], name)
                    self.assertEqual(reference["input_hex"], [arg.hex() for arg in args])
                    self.assertEqual(getattr(xm, name)(*args).hex(), reference["expected_hex"])

    def test_special_values(self):
        self.assertEqual(math.copysign(1.0, xm.sin(-0.0)), -1.0)
        self.assertEqual(xm.cos(0.0), 1.0)
        self.assertEqual(xm.sin(1e-300), 1e-300)
        self.assertEqual(xm.atan2(0.0, -1.0), math.pi)
        self.assertEqual(xm.atan2(-0.0, -0.0), -math.pi)
        self.assertEqual(xm.atan2(-0.0, 1.0), -0.0)
        self.assertEqual(xm.atan2(2.0, 0.0), math.pi / 2)
        self.assertEqual(xm.atan2(-1.0, -1.0), -3 * math.pi / 4)
        self.assertEqual(xm.asin(-1.0), -math.pi / 2)
        self.assertEqual(xm.acos(-1.0), math.pi)
        self.assertEqual(xm.log(1.0), 0.0)
        self.assertEqual(xm.exp(0.0), 1.0)
        self.assertEqual(xm.pow(2.0, 0.5), math.sqrt(2.0))
        self.assertEqual(xm.pow(4.0, 0.5), 2.0)
        self.assertEqual(xm.pow(-2.0, 3.0), -8.0)
        self.assertEqual(xm.pow(10.0, -2), 0.01)
        tie = 1 + 2.0 ** -27                                  # its square is a tie between two doubles: even wins
        self.assertEqual(xm.pow(tie, 2), tie * tie)
        self.assertEqual(xm.pow(tie, 2), 1 + 2.0 ** -26)
        self.assertEqual(xm.hypot(3.0, 4.0), 5.0)
        self.assertEqual(xm.dist((1.0, 2.0, 2.0), (0.0, 0.0, 0.0)), 3.0)
        self.assertEqual(xm.exp(-800.0), 0.0)
        with self.assertRaises(ValueError):
            xm.pow(-2.0, 0.5)
        with self.assertRaises(ValueError):
            xm.asin(1.5)
        with self.assertRaises(ValueError):
            xm.log(0.0)
        with self.assertRaises(OverflowError):
            xm.exp(800.0)
        with self.assertRaises(OverflowError):
            xm.pow(10.0, 400.0)

    def test_only_exact_functions_are_offered(self):
        for name in ("sinh", "cosh", "tanh", "log10", "log2", "log1p", "expm1", "cbrt", "erf", "gamma"):
            self.assertFalse(hasattr(xm, name), name)
        for name in ("sqrt", "hypot", "dist", "floor", "ceil", "copysign", "radians", "degrees", "isfinite", "nextafter",
                     "fsum"):
            self.assertIs(getattr(xm, name), getattr(math, name))
        self.assertEqual((xm.pi, xm.inf), (math.pi, math.inf))

    def test_imports_without_numpy(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); from mod_editor.core import exact_math as m; "
                "m.sin(1.0); m.hypot(3.0, 4.0); assert 'numpy' not in sys.modules")
        subprocess.run([sys.executable, "-c", code, str(ROOT)], check=True, timeout=60)


class NumpyForms(unittest.TestCase):
    def setUp(self):
        try:
            import numpy
        except ImportError:
            self.skipTest("numpy is not installed")
        self.np = numpy

    def test_hypot_keeps_glibc_rounding(self):
        np = self.np
        for x, y, glibc, exact in HYPOT:
            x, y = float.fromhex(x), float.fromhex(y)
            self.assertEqual(xm.glibc_hypot(x, y).hex(), glibc)
            self.assertEqual(float(xm.np_hypot(x, y)).hex(), glibc)
            self.assertEqual(xm.np_hypot(np.array([x, 1.0]), np.array([y, 1.0]))[0].hex(), glibc)
            self.assertEqual(xm.hypot(x, y).hex(), exact)
        a = np.array([3.0, 0.0, -1e-320, 1e300, np.inf, 2.0 ** -520])
        b = np.array([4.0, 0.0, 0.0, 1e300, 1.0, 2.0 ** -521])
        want = [5.0, 0.0, 1e-320, float.fromhex("0x1.0e4d50f99b211p+997"), np.inf, xm.glibc_hypot(a[5], b[5])]
        self.assertEqual(xm.np_hypot(a, b).tolist(), want)
        self.assertEqual([xm.glibc_hypot(x, y) for x, y in zip(a, b)], want)

    def test_shapes_and_scalars(self):
        np = self.np
        y = np.linspace(-3.0, 3.0, 12).reshape(3, 4)
        out = xm.np_arctan2(y, 1.5)
        self.assertEqual(out.shape, (3, 4))
        self.assertEqual(out.tolist(), [[xm.atan2(v, 1.5) for v in row] for row in y.tolist()])
        self.assertIsInstance(xm.np_arctan2(1.0, 2.0), np.float64)
        self.assertEqual(xm.np_power(np.array([2.0, 9.0]), 0.5).tolist(), [math.sqrt(2.0), 3.0])
        self.assertEqual(xm.np_hypot(np.array([[3.0], [6.0]]), np.array([4.0, 8.0])).tolist(),
                         [[5.0, xm.glibc_hypot(3.0, 8.0)], [xm.glibc_hypot(6.0, 4.0), 10.0]])


#: numpy's BLAS and LAPACK results on the pins' reference machine (numpy 1.26.4, OpenBLAS Haswell/Zen kernels): each
#: case adds in an order or with FMAs that plain left-to-right arithmetic does not reproduce
B = float.fromhex
GEMV3 = ((("0x1.24cb70683d396p-1", "0x1.a3335e944f8e0p-4", "-0x1.06422c28d17c6p-1", "-0x1.530a32811467cp-2",
           "-0x1.73528db840b90p-2", "-0x1.c1edde1a47468p-3"), ("0x1.2d4cf9574e82ep+8", "-0x1.9932c7b8b491bp+8",
          "-0x1.f9809f2ee3110p+6"), ("0x1.865048e93f326p+7", "0x1.318da6d594fcap+6")),
         (("0x1.2a508ce4d7860p-1", "0x1.08e12c22eb0bep-1", "0x1.a9e1bb1bd1438p-3", "-0x1.7a1d3d781da14p-1",
           "-0x1.1f09c031d2f40p-2", "0x1.7bb4446ab2b80p-1"), ("0x1.de2213f3e4264p+8", "0x1.9e5cbf21a9138p+7",
          "-0x1.5320845171b7fp+8"), ("0x1.3b3e95233e7a5p+8", "-0x1.4b56d40b16784p+9")))
GEMV2 = (("0x1.839b77382a430p-1", "-0x1.5a381507441eep-1", "-0x1.48ef762455428p-2", "-0x1.2c99a5a5edadcp-2",
          "-0x1.ca20a01aafe38p-3", "-0x1.893e073172ec0p-1"), ("-0x1.3a7defd4831d2p+8", "0x1.fdcee068fc5a4p+7"),
         ("-0x1.9a7401bddc1a7p+8", "0x1.a31d4cf7a000ep+4", "-0x1.f5b76b2ed0790p+6"))
DOT21 = (("-0x1.448c32b42cc40p+6", "0x1.9f22a344e6f00p+8", "0x1.21dd445c73f20p+4", "0x1.5120d1f80a6c4p+8",
          "-0x1.fea92be7d65e0p+6", "0x1.165f5d6997c68p+6", "-0x1.e10eabc1b208cp+6", "-0x1.5fb7c50e8e726p+7",
          "0x1.437bbaa6f6938p+6", "0x1.5a652e4aba5f0p+7", "0x1.5e3d1c779cf7ep+8", "-0x1.f77add875e9a2p+7",
          "0x1.abedc53d25a54p+7", "0x1.a425c40f03f20p+7", "0x1.70b76aff4c0aep+8", "-0x1.0a33e09bb9f26p+8",
          "0x1.aa0c25644ddd4p+8", "-0x1.820ebfa55eb30p+8", "-0x1.0d9c7cbe14d10p+6", "0x1.b2257546d0f9ap+8",
          "0x1.257b0a2a515a0p+4"),
         ("-0x1.ab7a4086cccb4p-2", "0x1.39acce97db000p-10", "-0x1.3213be3a09fa0p-5", "0x1.069bc091aa698p-2",
          "-0x1.8781d0e96ed00p-5", "0x1.99d5092f902b6p-1", "-0x1.80469926a7c00p-3", "-0x1.710cb4f479a78p-2",
          "0x1.8eed4ebb8de90p-1", "0x1.af7a58aaacc58p-1", "-0x1.b26e58633f240p-5", "0x1.5224b330e9b9ap-1",
          "-0x1.037e08b0f757ep-1", "0x1.4cb71a19b1bd0p-4", "0x1.1ea660906ebb2p-1", "0x1.4d30ddce14224p-1",
          "-0x1.6bb2136d2af9ap-1", "0x1.8f5d6cf6d8b90p-3", "0x1.4b6b953a284b0p-4", "0x1.db6bd4d6680e0p-5",
          "0x1.ecf998251dea8p-2"), "-0x1.cdf7a4fcc5bc6p+6")
DOT6S = (("-0x1.e74c5378740c4p+7", "-0x1.7694f8c3de0dbp+8", "0x1.750b7717a5a16p+8", "0x1.6785c75178f90p+6",
          "0x1.cd084e74f3818p+8", "-0x1.d5d4c3bf2cb32p+8", "-0x1.56fd0752db0d4p+6", "-0x1.8d8f5e3eb6ca8p+6",
          "0x1.70b522b75a2fep+8", "-0x1.8122a0d671a9cp+7", "0x1.672ad4875dfb0p+5", "0x1.f7cc56af29300p+7"),
         ("-0x1.5de4d31672be0p-2", "0x1.2f689baa11e00p-8", "-0x1.2b1a08be755a0p-2", "-0x1.776d4f9515d30p-4",
          "0x1.891627357934ap-1", "-0x1.e62bdb9820620p-2", "0x1.a2e16c4172de8p-3", "0x1.d1ff5f98125c8p-1",
          "0x1.c43d96fc46874p-2", "0x1.85ed09faac1acp-1", "-0x1.64eae2c60c48ap-1", "0x1.78bfcf9804794p-2"),
         "-0x1.1779662d50f58p+5")
GEMM = (("-0x1.c762077ad624cp+8", "0x1.9a4df7051f1c0p+6", "-0x1.e0182d6c0ceebp+8", "0x1.fcbeff3f4c990p+5",
         "-0x1.e46be37f161c0p+7", "-0x1.7a03fda7831c0p+7"),
        ("-0x1.53cce29442700p-6", "-0x1.b8ba0124049f0p-3", "-0x1.b9fe8b1b1ab42p-1", "-0x1.624af84a57eb8p-1",
         "-0x1.b7aeae35c3b7ep-1", "0x1.2d796c22b0350p-1", "0x1.7e67fb9b9cfbap-1", "0x1.d600e4ce73b80p-4",
         "-0x1.3f35a4b3fac0ap-1"),
        ("-0x1.a41cbc9c63809p+8", "-0x1.696f56f15e8bbp+5", "0x1.786add7ed61a5p+9", "0x1.91e3f72c1166ap+4",
         "0x1.5940ad567c8d2p+7", "-0x1.3eb626e841947p+6"))
NORM3 = (("-0x1.9660b9ce44750p+1", "-0x1.2915f2716b9aap+4", "-0x1.4287a6e8918ecp+5"), "0x1.63ffdb7009c43p+5")
SOLVE = (("0x1.f3ac369558742p-1", "-0x1.b060485170aa8p-1", "0x1.d8352e9dc1aa0p-2", "0x1.737cf4edb3720p-4"),
         ("0x1.0a22113297448p+7", "0x1.1e7013f32cd0cp+6"), ("0x1.2f8f984394facp+7", "0x1.1d533bdacffc9p+4"),
         "0x1.e9687b130ee42p-2")


def floats(values, shape=None):
    import numpy as np
    out = np.array([B(v) for v in values])
    return out.reshape(shape) if shape else out


#: the pinned stadium compiles and the helpers their geometry and light go through
MODEL_MODULES = ("nfl2k5_allegiant_model", "nfl2k5_att_model", "nfl2k5_board_kit", "nfl2k5_everbank_model",
                 "nfl2k5_gillette_model", "nfl2k5_hard_rock_model", "nfl2k5_highmark_model", "nfl2k5_lambeau_model",
                 "nfl2k5_levis_model", "nfl2k5_lucas_oil_model", "nfl2k5_mercedes_benz_model", "nfl2k5_metlife_model",
                 "nfl2k5_practice_field_model", "nfl2k5_sofi_model", "nfl2k5_stadium_environment",
                 "nfl2k5_state_farm_model", "nfl2k5_usbank_model")
#: numpy functions that call the C library's (or numpy's own SIMD) transcendental math, or BLAS and LAPACK (whose
#: kernels round differently by CPU); numpy.linalg.svd stays for the MetLife gates (2 columns: the same bits under the
#: Haswell/Zen, Sandybridge, Nehalem and Prescott kernels)
C_LIBRARY_NUMPY = {"sin", "cos", "tan", "arcsin", "arccos", "arctan", "arctan2", "hypot", "exp", "exp2", "expm1",
                   "log", "log2", "log10", "log1p", "power", "float_power", "sinh", "cosh", "tanh", "cbrt",
                   "dot", "matmul", "inner", "vdot", "tensordot", "polyfit", "lstsq"}
LINALG = {"norm", "solve", "det", "inv", "lstsq", "pinv", "eig", "eigh", "qr", "cholesky", "slogdet", "multi_dot",
          "matrix_power"}


class ReferenceKernels(unittest.TestCase):
    def setUp(self):
        try:
            import numpy
        except ImportError:
            self.skipTest("numpy is not installed")
        self.np = numpy

    def hexes(self, values):
        return [float(v).hex() for v in self.np.ravel(values)]

    def test_gemv_and_gemm(self):
        for a, x, want in GEMV3:
            self.assertEqual(self.hexes(xm.np_matmul(floats(a, (2, 3)), floats(x))), list(want))
            self.assertEqual(self.hexes(xm.np_dot(floats(a, (2, 3)), floats(x))), list(want))
        a, x, want = GEMV2
        self.assertEqual(self.hexes(xm.np_matmul(floats(a, (3, 2)), floats(x))), list(want))
        a, b, want = GEMM
        self.assertEqual(self.hexes(xm.np_matmul(floats(a, (2, 3)), floats(b, (3, 3)))), list(want))

    def test_dots_and_norms(self):
        a, b, want = DOT21
        self.assertEqual(float(xm.np_dot(floats(a), floats(b))).hex(), want)
        self.assertEqual(float(xm.np_matmul(floats(a), floats(b))).hex(), want)
        a, b, want = DOT6S
        self.assertEqual(float(xm.np_dot(floats(a, (6, 2))[:, 0], floats(b, (6, 2))[:, 1])).hex(), want)
        v, want = NORM3
        self.assertEqual(float(xm.np_norm(floats(v))).hex(), want)
        self.assertEqual(xm.np_norm(floats(v).reshape(1, 3), axis=1).tolist(), [float(xm.np_norm(floats(v)))])
        self.assertEqual(xm.np_norm(self.np.arange(12).reshape(3, 4)), self.np.sqrt(506.0))

    def test_solve_and_det(self):
        m, rhs, want, det = SOLVE
        self.assertEqual(self.hexes(xm.np_solve(floats(m, (2, 2)), floats(rhs))), list(want))
        self.assertEqual(float(xm.np_det(floats(m, (2, 2)))).hex(), det)
        self.assertEqual(float(xm.np_det(self.np.array([[1.0, 2.0], [2.0, 4.0]]))), 0.0)

    def test_numpy_agrees_on_the_reference_kernels(self):
        # informative where numpy runs on the Haswell/Zen kernels; other CPUs' kernels may differ, which is the point
        np = self.np
        rng = np.random.default_rng(7)
        a, x = rng.uniform(-1, 1, (40, 3)), rng.uniform(-500, 500, 3)
        self.assertEqual(xm.np_matmul(a, x).shape, (40,))
        self.assertEqual(xm.np_dot(a[0], x).shape, ())
        self.assertIsInstance(xm.np_dot(a[0], x), np.float64)


class ModelModules(unittest.TestCase):
    def test_the_pinned_compiles_use_exact_math(self):
        for module in MODEL_MODULES:
            tree = ast.parse((ROOT / "mod_editor" / "core" / f"{module}.py").read_text(encoding="utf-8"))
            with self.subTest(module=module):
                self.assertNotIn("math", [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names])
                self.assertIn(("exact_math", "math"), [(a.name, a.asname) for n in ast.walk(tree)
                                                       if isinstance(n, ast.ImportFrom) for a in n.names])
                powers = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow)]
                self.assertEqual(powers, [], "** calls the C library's pow: use math.pow, or np.square for arrays")
                numpy = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in C_LIBRARY_NUMPY
                         and isinstance(n.value, ast.Name) and n.value.id == "np"]
                self.assertEqual(numpy, [], "use the exact_math form (math.np_arctan2, math.np_dot, ...)")
                linalg = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in LINALG
                          and isinstance(n.value, ast.Attribute) and n.value.attr == "linalg"]
                self.assertEqual(linalg, [], "use math.np_norm, math.np_solve or math.np_det")
                matmul = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.MatMult)]
                self.assertEqual(matmul, [], "@ is BLAS: use math.np_matmul")

    def test_it_ships(self):
        allow = set((ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split())
        self.assertLessEqual({"mod_editor/core/exact_math.py", "tests/mod_editor/test_exact_math.py",
                              "tests/mod_editor/exact_math_mpfr_vectors.json"}, allow)
        probe = (ROOT / "packaging" / "check_2k5_mod_studio_runtime.py").read_text(encoding="utf-8")
        self.assertIn('"mod_editor.core.exact_math"', probe)


if __name__ == "__main__":
    unittest.main()

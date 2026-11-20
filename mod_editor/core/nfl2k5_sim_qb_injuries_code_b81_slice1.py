# FROZEN: the slice 1 quarterback bank as d8ceb91e3 generated it (beta 81). nfl2k5_sim_qb_injuries uses it only to read a
# slice 1 install (QBMEDv1) and reverse it exactly. Everything below these two lines is that file byte for byte; never edit it.
"""Relocatable 128 MiB scheduled-franchise QB rules. The native selector and medical writes come from the user's game.

The weekly scheduler and Gamecast enter through the same fixture guard. The completion caller alone uses the
franchise gain curve. The original escape and zero-yard callers keep the standard simulator's converter.
The template and its relocations are generated from the assembly and C in tools/qb_sim_injuries.
"""
from __future__ import annotations

from hashlib import sha256
import struct
from typing import Callable

CODE_SIZE = 0x4000
MARK_OFFSET = 0x3FC0
MARK_SIZE = struct.calcsize("<8sIII")
DEFAULT_RATE = 310                  # Base probability numerator per 100,000 eligible opportunities.
RATE_DENOMINATOR = 100_000
REFERENCE_DURABILITY = 74.72222222222223
GAIN_TABLE = 0x3B00
GAIN_CONSTANTS = 0x3D80
LENGTH_ACCEPT = ((1, 507082694), (2, 601295421), (3, 1503238554), (4, 196716059),
                 (7, 149245968), (8, 195151244), (14, 348438850), (255, 2050967529))

# Both high-level callers, the Gamecast screen reset, and the three ordinary/sack/escape medical calls.
_FIXED_CALLS = (
    ("weekly_entry", 0x10B95A, 0x10B280, "match_entry"),
    ("gamecast_entry", 0xEC007, 0x10B280, "match_entry"),
    ("gamecast_screen", 0xEBF46, 0x6C780, "gamecast_screen_entry"),
    ("rush", 0x1081E3, 0x1028B0, "medical"),
    ("pass", 0x10904A, 0x1028B0, "medical"),
    ("sack_escape", 0x108A02, 0x1028B0, "medical"),
)
CONTEST_SITE = 0x108B12
COMPLETION_SITE = 0x1094E4
FIXED_SPANS = tuple((at, 5) for _, at, _, _ in _FIXED_CALLS) + ((CONTEST_SITE, 6), (COMPLETION_SITE, 5))

# These native checks cover the master Injury option, selector stack contract, switch tables and shared constants.
# Four routines are also pinned independently before they are linked into the reserved space.
_NATIVE_ABI = (
    (0x62550, 44, 'injury mode test and four destinations',
     'c6cfcfe1ffe83f092bd149f3edbfc6568925af14e3ab224b91b83d6ab9a74099'),
    (0x625a0, 37, 'master Injury slider predicate',
     '3b81eb41fd08a60f9d233fc9a0ec59842de64c69e80e3b7cba8f3b3f16fbd267'),
    (0x102580, 760, 'primary patient selector, base health writer and stack return',
     'e0228d5cfdb2607aa84e5118683ec7c69369f3ea635ea8d40d20126e41fac702'),
    (0x102878, 49, 'four position handlers and all 33 slot categories',
     '703c1a5985b517f6d9837aab65db8fd4c0becf6c93461b4ba4a7fc88a6bfba1d'),
    (0x1028b0, 82, 'scheduled injury entry with both stack returns',
     '4e5d79a90866054543c2d0684873e1f3579fd065ef2219615087282bbeaae2fb'),
    (0x4e6d10, 4, 'shared default QB entry probability',
     '0b9d79ff0fc4d0a77ef398763bbe45c445501e826219f2b6a1aa709411ab631d'),
    (0x4f6b48, 4, 'stock outer gate multiplier',
     '2bf14e785577603fda60476e5e5cfd313b95b39166647c4fa6b0b00fcd6d46b3'),
)

# Each relocation names an instruction field in the local fragment, its native addressing mode and exact target.
_LOCAL_FUNCTIONS = (
    ('descriptor', 0x102580, 139, '72437c36a4e2e8ed98c44491a98ce91ad5f740b745890ec5b0cac7c90c6ef445', (
        (31, True, 'group', 0x0),
        (38, True, 'stock', 0x13e260),
        (79, False, 'private_rng', 0x0),
        (102, True, 'stock', 0x48b90),
    )),
    ('duration', 0x10278b, 93, 'ba50cb26a9df3db43765d2ef631eae897c4da66abe0f07f7d83742244a57060b', (
        (16, True, 'stock', 0x10286e),
        (32, True, 'weeks', 0x0),
        (67, False, 'private_rng', 0x0),
        (74, True, 'stock', 0x48b50),
    )),
    ('group', 0x13e420, 157, '6d3ba41c638463ff7b5f7313ef4c3ac6ba8c7081b47301fc64c26522b00adfc8', (
        (11, False, 'private_rng', 0x0),
        (16, True, 'stock', 0x48b50),
        (38, True, 'stock', 0x13e260),
        (46, False, 'private_rng', 0x0),
        (54, True, 'stock', 0x48b50),
        (107, True, 'stock', 0x13e260),
        (115, False, 'private_rng', 0x0),
        (123, True, 'stock', 0x48b50),
    )),
    ('weeks', 0x13dfe0, 421, '52f80473ec83d1872c8a7c8e7bd346a5ddb5fd8697176ac1f3c66e5900f587f5', (
        (53, False, 'private_rng', 0x0),
        (58, True, 'stock', 0x48b90),
        (223, False, 'private_rng', 0x0),
        (228, True, 'stock', 0x48b90),
        (385, True, 'stock', 0x13dd50),
        (411, True, 'stock', 0x13dd50),
    )),
)


def _checked(read_game, at, size, label, expected):
    content = read_game(at, size)
    if len(content) != size or sha256(content).hexdigest() != expected:
        raise ValueError(f"Unrecognized native quarterback injury input: {label} at {at:#x}")
    return content


def check_native_sources(read_game: Callable[[int, int], bytes]) -> None:
    """Verify the original selector's indirect tables, slider gate and return ABI on this physical image."""
    for at, size, name, pin in _NATIVE_ABI:
        _checked(read_game, at, size, name, pin)


def _set32(bank, offset, value):
    struct.pack_into("<I", bank, offset, value & 0xFFFFFFFF)


def _rate(rate):
    if type(rate) is not int or not 0 <= rate <= RATE_DENOMINATOR:
        raise ValueError("Quarterback injury chance must be a whole number from 0 to 100,000")
    return rate


def _configure_tables(bank, rate):
    # The health slider scales these 31-bit thresholds again in the native handler. Sacks and escapes carry 4x exposure.
    for label, factor in (("ordinary_thresholds", 1), ("special_thresholds", 4)):
        chance = rate / RATE_DENOMINATOR
        values = (2 * chance * factor * max(0, 100 - d) / (100 - REFERENCE_DURABILITY) * (1 << 31)
                  for d in range(256))
        struct.pack_into("<256f", bank, LABELS[label], *values)
    start = 0
    for end, threshold in LENGTH_ACCEPT:
        count = end + 1 - start
        struct.pack_into(f"<{count}I", bank, LABELS["length_thresholds"] + 4 * start, *([threshold] * count))
        start = end + 1
    for accuracy in range(101):
        position = min(1.0, max(0.0, (accuracy - 92) / 6))
        gain = .982 * (.935 + .130 * position**4)
        struct.pack_into("<f", bank, GAIN_TABLE + 4 * accuracy, gain)
    struct.pack_into("<ff", bank, GAIN_CONSTANTS, .77, .982)


def _link_authored(bank_va: int, sim_code_va: int, sim_data_va: int, depth: int) -> bytearray:
    from . import nfl2k5_sim_realism as sim

    origins = {
        "stock": 0, "literal": 0, "bank": bank_va, "sim_data": sim_data_va,
        "depth": depth,
        "pass_converter": sim_code_va + sim.label_offsets()["pass_scale"],
        "red_zone_line": sim_code_va + sim.QB_BONUS_RZ_OFF,
        "mix_slope": sim_code_va + sim.MIX_QB_SLOPE_OFF, "mix_bias": sim_code_va + sim.MIX_BIAS_OFF,
    }
    bank = bytearray(_TEMPLATE)
    for offset, relative, family, addend in _RELOCATIONS:
        target = origins[family] + addend
        _set32(bank, offset, target - (bank_va + offset) if relative else target)
    return bank


def bank_bytes(read_game: Callable[[int, int], bytes], bank_va: int, sim_code_va: int, sim_data_va: int,
               lineup_va: int | None = None, *, rate: int = DEFAULT_RATE, marker: bytes = b"") -> bytes:
    """Link against the installed simulator, optional lineup owner and four verified local functions."""
    from . import nfl2k5_lineup_roles as roles

    _rate(rate)
    if not isinstance(marker, bytes) or len(marker) not in (0, MARK_SIZE):
        raise ValueError(f"An installed quarterback settings record requires {MARK_SIZE} bytes")
    addresses = (bank_va, sim_code_va, sim_data_va)
    if lineup_va is not None:
        addresses += (lineup_va,)
    for address in addresses:
        if type(address) is not int or not 0 < address <= 0xFFFFFFFF - CODE_SIZE:
            raise ValueError("The quarterback runtime needs valid 32-bit executable addresses")
    check_native_sources(read_game)
    recovery = lineup_va is not None and rate > 0
    depth = lineup_va + 0x455 if recovery else roles.AUTO_DEPTH
    bank = _link_authored(bank_va, sim_code_va, sim_data_va, depth)
    for name, at, size, pin, fields in _LOCAL_FUNCTIONS:
        offset = LABELS[name]
        bank[offset:offset + size] = _checked(read_game, at, size, name, pin)
        for field, relative, symbol, addend in fields:
            target = addend if symbol == "stock" else bank_va + LABELS[symbol] + addend
            where = offset + field
            _set32(bank, where, target - (bank_va + where + 4) if relative else target)
    _configure_tables(bank, rate)
    if not recovery:
        start, end = LABELS["depth_hook"], LABELS["match_hook"]
        bank[start:end] = b"\xc3" + b"\xcc" * (end - start - 1)
    if marker:
        bank[MARK_OFFSET:MARK_OFFSET + len(marker)] = marker
    return bytes(bank)


def _call(at, destination, width=5):
    return (b"\xe8" + struct.pack("<I", (destination - at - 5) & 0xFFFFFFFF)).ljust(width, b"\x90")


def edits(bank_va: int, sim_code_va: int, sim_data_va: int, lineup_va: int | None = None,
          *, rate: int = DEFAULT_RATE) -> tuple[tuple[str, int, bytes, bytes], ...]:
    """Return (name, virtual address, expected physical instruction/data, installed bytes) for every external edit."""
    from . import nfl2k5_sim_realism as sim

    _rate(rate)
    result = [(name, at, _call(at, stock), _call(at, bank_va + LABELS[label]))
              for name, at, stock, label in _FIXED_CALLS]
    result.append(("contest", CONTEST_SITE, bytes.fromhex("8b15a071a900"),
                   _call(CONTEST_SITE, bank_va + LABELS["contest"], 6)))
    physical = sim.code_for(sim_code_va, sim_data_va)
    for label, offset in (("slope", 0x38), ("bias", 0x3E), ("flat", 0x62)):
        at = sim_code_va + offset
        result.append((label, at, physical[offset:offset + 6], _call(at, bank_va + LABELS[label], 6)))
    result.append(("completed_pass", COMPLETION_SITE, _call(COMPLETION_SITE, sim_code_va + sim.label_offsets()["pass_scale"]),
                   _call(COMPLETION_SITE, bank_va + LABELS["route_completed_pass"])))
    for label, offset, value in (("MIX_BIAS", sim.MIX_BIAS_OFF, 9.0), ("MIX_QB_SLOPE", sim.MIX_QB_SLOPE_OFF, .16)):
        result.append((label, sim_code_va + offset, physical[offset:offset + 4], struct.pack("<f", value)))
    if lineup_va is not None and rate > 0:
        at = lineup_va + 0x44B
        result.append(("recovery", at, _call(at, lineup_va + 0x455), _call(at, bank_va + LABELS["depth_hook"])))
    return tuple(result)


# Generated from tools/qb_sim_injuries by build.py.
_TEMPLATE = b''.join((
    bytes.fromhex('50a19c71a90085c074038b4008870424ff742410ff742410ff742410e8ac281000e9fcffffff9090'),
    bytes.fromhex('90909083e4f00fae0424898c2400020000837934000f85db0100008b359c71a90085f60f84cd0100'),
    bytes.fromhex('0083bedc000000000f85c00100008b6e0885ed0f84b50100008b9424000200003b6a240f85a50100'),
    bytes.fromhex('00807d35000f859b010000f64523800f8591010000f64527700f8587010000e89c25060085c00f84'),
    bytes.fromhex('7a0100008b3da071a90085ff0f846c0100008b0d1829b70085c90f845e0100008b491c8b068b1729'),
    bytes.fromhex('c829ca3d8c3c00000f874801000081fa8c3c00000f873c01000039d00f84340100007201928b0db8'),
    bytes.fromhex('76e5008b1db476e5003b05c405000075183b15c805000075103b0dbc05000075083b1dc005000074'),
    bytes.fromhex('57a3c40500008915c8050000890dbc050000891dc0050000c1c01031d03531494251e8f300000031'),
    bytes.fromhex('c8c1c31031d8e8e70000003305a8fce500e8dc0000003305b0fce500e8d1000000a3cc050000c705'),
    bytes.fromhex('d005000000000000ff05d0050000a1d005000069c0b979379e0305cc050000e8a600000089c33545'),
    bytes.fromhex('544147e89a00000025ffffff7fa3d40500000fb64d3bbaa8070000ff05d80500008b842400020000'),
    bytes.fromhex('817828078a10007511ff0dd8050000ff05dc050000baa80b0000d9048ad80d0402e600db05d40500'),
    bytes.fromhex('00ded9dfe0f6c4017434ff05e005000089d835314e454ce836000000d1e85089d8353154414ee827'),
    bytes.fromhex('00000089c2b9e8050000e8dc8b04006a00e8360000000fae0c248ba42400020000619d8d642404c2'),
    bytes.fromhex('0c0089c2c1ea1031d069c06bcaeb8589c2c1ea0d31d069c035aeb2c289c2c1ea1031d0c3'),
    bytes(139),
    bytes.fromhex('8b7c2410a19c71a90089442414c7442418'),
    bytes(97),
    bytes.fromhex('89d83dff0000000f876a2810008b54243c3b1485a80f00000f836a281000ff05e4050000e9fcffff'),
    bytes.fromhex('ff'),
    bytes(578),
    bytes.fromhex('ffffffffffffffffffffffffffffffff'),
    bytes(3548),
    b'\xcc' * 3160,
    bytes.fromhex('9c605756e8fcffffff83c408619de8fcffffff9c605756e8fcffffff83c408619dc39c608d442424'),
    bytes.fromhex('505251e8fcffffff83c40c619dc7042400000000e97cb210009c60e8fcffffff619de95bb910008b'),
    bytes.fromhex('502081e20000c0bf750f8b4024a9000000700f94c00fb6c0c331c0c38b0d1829b70085c90f84ef01'),
    bytes.fromhex('00005557565383ec1489c68b511c39d00f82d301000029d03d7f3e00000f87c6010000bbf4010000'),
    bytes.fromhex('31d2f7f389d585d20f85b30100006bd8548bbb10000000893c2485ff0f849f010000398b04000000'),
    bytes.fromhex('0f859301000039b3000000000f85870100008b0db876e500398b080000000f85750100008b0db476'),
    bytes.fromhex('e500398b0c0000000f85630100008d90d75d39008b14950000000085d2740e8b154001e60085d20f'),
    bytes.fromhex('84440100000fb68e1c01000080f9410f87340100008d1c8e895c240c6bd85431c089442404895c24'),
    bytes.fromhex('108b44240c39c60f849d0000008b3e85ff0f848b0000008a473584c00f858000000031c939bccb14'),
    bytes.fromhex('0000007408418b042439c172ef390c240f84e3000000b801000000d3e0854424040f85d200000009'),
    bytes.fromhex('44240489f8e8b5feffff85c00f84bf0000008b4424108d94c8100000000fb6420889442408668b47'),
    bytes.fromhex('2866c1e80a83e007394424080f85970000008a42098a575238d00f8589000000394c24087404a801'),
    bytes.fromhex('757f83c604e957ffffffb8010000008a0c24d3e0488b7c240439f87564a10000000031c90fb6b318'),
    bytes.fromhex('00000089f239ee74388b35000000008b8b14000000890cf5000000008d7e01893d000000008814f5'),
    bytes.fromhex('04000000668b512880e6e389eec1e60a09f26689512840b1014583c308392c2475b284c97405a300'),
    bytes.fromhex('000000ff050000000083c4145b5e5f5dc3c35557565383ec0c8b742424837c24201f0f873d010000'),
    bytes.fromhex('6b4424205431d28990100000008b3d1829b70085ff0f84220100008b571c69442420f401000001d0'),
    bytes.fromhex('39f00f850d0100008b44242005d75d39008b04850000000085c0740da14001e60085c00f84ec0000'),
    bytes.fromhex('000fb6961c01000080fa410f87dc0000008d04968944240489342431db31ed6b4424205489442408'),
    bytes.fromhex('8b442404390424743e8b04248b1085d2742f8a4a3584c97528668b4a2866c1e90a83e107b8010000'),
    bytes.fromhex('00d3e085e80f859200000009c5438b4424088994c81400000083042404ebb98d43fe83f8067776b8'),
    bytes.fromhex('0100000088d9d3e04839e875686b6c2420548b85140000008b402085c07956250000c03f3d000040'),
    bytes.fromhex('00754ab9010000008b84cd14000000e8cbfcffff85c074354139cb75eb6b442420548d9000000000'),
    bytes.fromhex('89b00000000089b804000000a1b876e500894208a1b476e50089420c895a10ff050000000083c40c'),
    bytes.fromhex('5b5e5f5dc355575653837c24141f0f87810000006b542414548d82000000008bb21000000085f674'),
    bytes.fromhex('6c8b7c241839ba0000000075608d3cf031db8b6814668b4d2866c1e90a83e1078848188a55528850'),
    bytes.fromhex('190fb7c9ba01000000d3e209d383c00839f875d66b4424145480b81800000000740e89f1ba010000'),
    bytes.fromhex('00d3e24a39da740f6b4424145431d2899010000000eb06ff05000000005b5e5f5dc3538b5424088b'),
    bytes.fromhex('5c240c8b44241031c9890d0000000081781ce0b910007533817834587b0c00752aa180ffe50083f8'),
    bytes.fromhex('047520a1a476e50083e80883f801771339da740f89d0e8c9fbffff89d85be9c1fbffff5bc3a10000'),
    bytes.fromhex('000085c0742748a3000000008b0cc500000000668b51280fb604c504000000c1e00a80e6e309d066'),
    bytes.fromhex('894128ebd0c36690'),
    bytes(2849),
    b'\xcc' * 255,
    bytes.fromhex('9c60817c24245fb910000f8586000000817c2440e0b91000757c817c2458587b0c007572833d80ff'),
    bytes.fromhex('e500047569a1a476e50083e80783f802775ca1b876e5003b0500000000754fa1b476e5003b050000'),
    bytes.fromhex('00007542a11829b70085c074398b401c29c129c281f98c3c0000772a81fa8c3c0000772239d1741e'),
    bytes.fromhex('720287d13b0d0000000075123b1500000000750ac70500000000ffffffff619de9fcffffff'),
    b'\xcc' * 99,
    bytes.fromhex('91e30c8d4c24d083c124b901000000919c6089e181ec10020000e9fcffffff'),
    b'\xcc' * 225,
    bytes.fromhex('9c505183ec08833d80ffe500040f8597000000a1a476e50083e80783f8020f8786000000a19c71a9'),
    bytes.fromhex('0085c0747d3b68087578807d35007572f745200000c0bf7569f74524000000707560d914248b0c24'),
    bytes.fromhex('85c978563b0db8000000734ed905b8000000d8e18b0d0072a90081f90000a0417e1581f90000c842'),
    bytes.fromhex('7f0dd80dc4000000a1c8000000eb0bd80dbc000000a1c0000000d95424048b4c240439c1760addd8'),
    bytes.fromhex('89442404d9442404dec18d64240859589d8b15a071a900c385eb513fcdcccc3e0ad7a33d0000403f'),
    bytes.fromhex('295c0f3e'),
    b'\xcc' * 308,
    bytes.fromhex('9c505183ec04833d80ffe500047569a1a476e50083e80783f802775ca19c71a90085c074538b4008'),
    bytes.fromhex('85c0744c807835007546f740200000c0bf753df74024000000707534d91424833c24007e2b0fb648'),
    bytes.fromhex('42b85500000029c87e1e83f8177605b817000000890424db0424d80d8c000000d82d88000000dec9'),
    bytes.fromhex('d80d000000008d64240459589dc3cccc0000803fbc74933c'),
    b'\xcc' * 112,
    bytes.fromhex('9c60c60500000000008b4424243d0000000074273d000000000f85e6000000817c2440000000000f'),
    bytes.fromhex('85d8000000817c2458000000000f85ca000000833d00000000020f85bd000000833d00000000040f'),
    bytes.fromhex('85b0000000a10000000083e80783f8020f879f000000a10000000085c00f84920000008b581c85db'),
    bytes.fromhex('0f848700000089ce29de81fe8c3c0000777b89d729df81ff8c3c0000776f39fe746bb9f401000089'),
    bytes.fromhex('f031d2f7f185d2755c89f831d2f7f185d27552c6050000000001a1000000003b0500000000752da1'),
    bytes.fromhex('000000003b0500000000752039fe720287fe3b350000000075123b3d00000000750ac70500000000'),
    bytes.fromhex('ffffffff817c242400000000740e619de9fcffffff619de9fcffffffc7050000000000000000833d'),
    bytes.fromhex('000000000872128b442418e8fcffffff8b442414e8fcffffff619dc7042400000000e9fcffffff9c'),
    bytes.fromhex('60e8fcffffff619de9fcffffff9c803d000000000074069de9fcffffff9de9fcffffff9c803d0000'),
    bytes.fromhex('00000074069de9fcffffff9d8b1500000000c39c803d000000000074069de9fcffffff9dd80dfc01'),
    bytes.fromhex('0000c39c803d000000000074069de9fcffffff9dd80d00020000c39c803d000000000074089dd80d'),
    bytes.fromhex('00000000c39dd80d04020000c39c803d000000000074089dd80500000000c39dd80508020000c39c'),
    bytes.fromhex('803d000000000074089dd81d00000000c39dd81d08020000c3cccccc'),
    bytes(17),
    bytes.fromhex('ccccccc6050000000000e9fcffffff'),
    b'\xcc' * 36,
    bytes.fromhex('9c803d000000000074069de9fcffffff9de9fcffffff'),
    b'\xcc' * 170,
    bytes.fromhex('9c83fb04723083fb07772b83fb04751081fae57b8d0a721e81fae57b8d0aeb0e81fadb940108720e'),
    bytes.fromhex('81fadb940108bb0300000073014b9de9e4271000'),
    b'\xcc' * 196,
    bytes.fromhex('9c506a00833d80ffe500047550a1a476e50083e80783f8027743a19c71a90085c0743a8b400885c0'),
    bytes.fromhex('743380783500752df740200000c0bf7524f7402400000070751bd91424833c24007e120fb6404283'),
    bytes.fromhex('f8647709d80c8500000000eb06d80d000000008d642404589dc3'),
    b'\xcc' * 662,
    bytes.fromhex('d90500000000d81d00000000dfe0f6c441740ed9442404e8fcffffff90d95c24048b0424a3000000'),
    bytes.fromhex('0058e8fcffffffe8fcffffff908b150000000052c3'),
    b'\xcc' * 707,
))

# (field offset, PC-relative, address family, offset including ELF addend)
_RELOCATIONS = (
    (0x001d, True, 'stock', 0x1028ac),
    (0x0022, True, 'bank', 0x31fc),
    (0x0098, True, 'stock', 0x6259c),
    (0x00fb, False, 'bank', 0x5c4),
    (0x0103, False, 'bank', 0x5c8),
    (0x010b, False, 'bank', 0x5bc),
    (0x0113, False, 'bank', 0x5c0),
    (0x011a, False, 'bank', 0x5c4),
    (0x0120, False, 'bank', 0x5c8),
    (0x0126, False, 'bank', 0x5bc),
    (0x012c, False, 'bank', 0x5c0),
    (0x0162, False, 'bank', 0x5cc),
    (0x0168, False, 'bank', 0x5d0),
    (0x0172, False, 'bank', 0x5d0),
    (0x0177, False, 'bank', 0x5d0),
    (0x0183, False, 'bank', 0x5cc),
    (0x019e, False, 'bank', 0x5d4),
    (0x01a7, False, 'bank', 0x7a8),
    (0x01ad, False, 'bank', 0x5d8),
    (0x01c3, False, 'bank', 0x5d8),
    (0x01c9, False, 'bank', 0x5dc),
    (0x01ce, False, 'bank', 0xba8),
    (0x01dd, False, 'bank', 0x5d4),
    (0x01ec, False, 'bank', 0x5e0),
    (0x020e, False, 'bank', 0x5e8),
    (0x0213, True, 'stock', 0x48bdc),
    (0x035a, True, 'stock', 0x10286a),
    (0x0365, False, 'bank', 0xfa8),
    (0x036b, True, 'stock', 0x10286a),
    (0x0371, False, 'bank', 0x5e4),
    (0x0376, True, 'bank', 0x38fc),
    (0x2005, True, 'bank', 0x2266),
    (0x200f, True, 'depth', -0x4),
    (0x2018, True, 'bank', 0x23c1),
    (0x202c, True, 'bank', 0x2456),
    (0x2038, False, 'bank', 0x2041),
    (0x203d, True, 'stock', 0x10b27c),
    (0x2044, True, 'bank', 0x24a9),
    (0x204b, True, 'stock', 0x10b95b),
    (0x20b3, False, 'bank', 0x2590),
    (0x20c4, False, 'bank', 0x2584),
    (0x20d0, False, 'bank', 0x2580),
    (0x20e2, False, 'bank', 0x2588),
    (0x20f4, False, 'bank', 0x258c),
    (0x2167, False, 'bank', 0x2594),
    (0x21a9, False, 'bank', 0x2590),
    (0x21fe, False, 'bank', 0x24e0),
    (0x2207, False, 'bank', 0x2598),
    (0x2213, False, 'bank', 0x24f0),
    (0x2219, False, 'bank', 0x2594),
    (0x2220, False, 'bank', 0x2500),
    (0x2229, False, 'bank', 0x24f0),
    (0x2230, False, 'bank', 0x2504),
    (0x2257, False, 'bank', 0x24e0),
    (0x225d, False, 'bank', 0x24e4),
    (0x2289, False, 'bank', 0x2590),
    (0x2335, False, 'bank', 0x2594),
    (0x235c, False, 'bank', 0x2594),
    (0x237b, False, 'bank', 0x2594),
    (0x2394, False, 'bank', 0x2580),
    (0x239a, False, 'bank', 0x2580),
    (0x23a0, False, 'bank', 0x2584),
    (0x23b9, False, 'bank', 0x24ec),
    (0x23db, False, 'bank', 0x2580),
    (0x23e1, False, 'bank', 0x2590),
    (0x23ef, False, 'bank', 0x2580),
    (0x242b, False, 'bank', 0x2598),
    (0x2449, False, 'bank', 0x2590),
    (0x2451, False, 'bank', 0x24e8),
    (0x246b, False, 'bank', 0x24f0),
    (0x24ae, False, 'bank', 0x24f0),
    (0x24b8, False, 'bank', 0x24f0),
    (0x24bf, False, 'bank', 0x2500),
    (0x24cb, False, 'bank', 0x2504),
    (0x3141, False, 'bank', 0x5bc),
    (0x314e, False, 'bank', 0x5c0),
    (0x317e, False, 'bank', 0x5c4),
    (0x3186, False, 'bank', 0x5c8),
    (0x318e, False, 'bank', 0x5bc),
    (0x3199, True, 'bank', 0x201e),
    (0x321b, True, 'bank', 0x27),
    (0x3356, False, 'bank', 0x33b8),
    (0x335e, False, 'bank', 0x33b8),
    (0x337c, False, 'bank', 0x33c4),
    (0x3381, False, 'bank', 0x33c8),
    (0x3389, False, 'bank', 0x33bc),
    (0x338e, False, 'bank', 0x33c0),
    (0x356c, False, 'bank', 0x358c),
    (0x3572, False, 'bank', 0x3588),
    (0x357a, False, 'bank', 0x3d80),
    (0x3604, False, 'bank', 0x380c),
    (0x360e, False, 'stock', 0xec00c),
    (0x3615, False, 'stock', 0x10b95f),
    (0x3623, False, 'stock', 0x10b9e0),
    (0x3631, False, 'stock', 0xc7b58),
    (0x363d, False, 'stock', 0xe576a0),
    (0x364a, False, 'stock', 0xe5ff80),
    (0x3656, False, 'stock', 0xe576a4),
    (0x3667, False, 'stock', 0xb72918),
    (0x36b5, False, 'bank', 0x380c),
    (0x36bb, False, 'stock', 0xe576b8),
    (0x36c1, False, 'bank', 0x5bc),
    (0x36c8, False, 'stock', 0xe576b4),
    (0x36ce, False, 'bank', 0x5c0),
    (0x36dc, False, 'bank', 0x5c4),
    (0x36e4, False, 'bank', 0x5c8),
    (0x36ec, False, 'bank', 0x5bc),
    (0x36f8, False, 'stock', 0xec00c),
    (0x3701, True, 'bank', 0x201e),
    (0x3708, True, 'stock', 0x10b27c),
    (0x370e, False, 'bank', 0x24f0),
    (0x3718, False, 'stock', 0xe576a4),
    (0x3724, True, 'bank', 0x2068),
    (0x372d, True, 'bank', 0x2068),
    (0x3736, False, 'bank', 0x373f),
    (0x373b, True, 'stock', 0x10b27c),
    (0x3742, True, 'bank', 0x24a9),
    (0x3749, True, 'stock', 0xec008),
    (0x3750, False, 'bank', 0x380c),
    (0x3759, True, 'bank', -0x4),
    (0x375f, True, 'stock', 0x1028ac),
    (0x3766, False, 'bank', 0x380c),
    (0x376f, True, 'bank', 0x32fc),
    (0x3776, False, 'stock', 0xa971a0),
    (0x377e, False, 'bank', 0x380c),
    (0x3787, True, 'bank', 0x34fc),
    (0x378e, False, 'bank', 0x37fc),
    (0x3796, False, 'bank', 0x380c),
    (0x379f, True, 'bank', 0x39fc),
    (0x37a6, False, 'bank', 0x3800),
    (0x37ae, False, 'bank', 0x380c),
    (0x37b8, False, 'mix_slope', 0x0),
    (0x37c0, False, 'bank', 0x3804),
    (0x37c8, False, 'bank', 0x380c),
    (0x37d2, False, 'mix_bias', 0x0),
    (0x37da, False, 'bank', 0x3808),
    (0x37e2, False, 'bank', 0x380c),
    (0x37ec, False, 'mix_bias', 0x0),
    (0x37f4, False, 'bank', 0x3808),
    (0x37fc, False, 'literal', 0x3f23d70a),
    (0x3800, False, 'literal', 0x3f68f5c3),
    (0x3804, False, 'literal', 0x3ecccccd),
    (0x3808, False, 'literal', 0x41080000),
    (0x3812, False, 'bank', 0x380c),
    (0x3818, True, 'stock', 0x6c77c),
    (0x3843, False, 'bank', 0x380c),
    (0x384c, True, 'bank', 0x3cfc),
    (0x3852, True, 'pass_converter', -0x4),
    (0x3938, True, 'stock', 0x1027e4),
    (0x3a57, False, 'bank', 0x3b00),
    (0x3a5f, False, 'bank', 0x3d84),
    (0x3d02, False, 'stock', 0xa97200),
    (0x3d08, False, 'red_zone_line', 0x0),
    (0x3d18, True, 'bank', 0x34fc),
    (0x3d25, False, 'sim_data', 0xc),
    (0x3d2b, True, 'stock', 0x10647c),
    (0x3d30, True, 'bank', 0x39fc),
    (0x3d37, False, 'sim_data', 0xc),
)

LABELS = {
    'active': 0x380c,
    'adjust': 0x3500,
    'before_primary': 0xd,
    'bias': 0x37c5,
    'completed_catch_scale': 0x3d00,
    'contest': 0x3763,
    'continue_capture': 0x2b,
    'depth_hook': 0x2000,
    'descriptor': 0x254,
    'duration': 0x2f4,
    'finished': 0x21e,
    'flat': 0x37df,
    'gamecast_screen_entry': 0x3810,
    'group': 0x37a,
    'length_thresholds': 0xfa8,
    'match_entry': 0x3600,
    'match_hook': 0x2022,
    'medical': 0x374d,
    'ordinary_thresholds': 0x7a8,
    'passing_scale': 0x3a00,
    'private_rng': 0x5e8,
    'revise': 0x3900,
    'route_completed_pass': 0x3840,
    'slope': 0x37ab,
    'special_thresholds': 0xba8,
    'supplement': 0x0,
    'weeks': 0x417,
}

"""Opt-in global fourth-down thresholds for pinned APF BASE and TU 1.1.

The persistent block occupies unused .rdata raw padding in both images.
A 40-byte leaf supplies a separate own-half threshold without changing the
shared goal-coordinate constant. No SPLB/MASTER situation data is changed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import struct
import tomllib

from .errors import ValidationError
from .apf2k8_playcall_patch import IMAGE_BASE, PROFILES, TITLE_ID, _branch, _d, check_image, export_patch

DEFAULT_ENABLED = False
CLASSIFICATION = 'EXPERIMENTAL'
FILENAME = '54540807-studio-fourth-down.patch.toml'
NAME = 'CPU fourth-down thresholds (experimental, unwitnessed)'
DATA = 0x844DBD80
DATA_LIMIT = 0x844DBDC0
CAVE = 0x84D0D000
CAVE_LIMIT = 0x84D0D040
YARD = 91.44

# (public field, title, retail, min, max, step, description)
FIELDS = (
    ('short_yards', 'Punt short-yardage cutoff (yards)', 1., 0., 10., .25,
     'At or below this distance, the punt predicate uses its short-yardage random test. Other gates still apply.'),
    ('own_half_limit', 'Automatic punt beyond goal distance (yards)', 50., 0., 100., 1.,
     'Ordinary early-game punts beyond this distance from the attacking goal. Higher values allow more short-yardage attempts in your own half.'),
    ('punt_slope', 'Short-yardage punt probability per spare yard', .05, 0., 1., .01,
     'Below the cutoff, punt when the cached random value is below (cutoff minus distance) times this slope.'),
    ('fallback_threshold', 'Fallback kick random threshold', .95, 0., 1., .01,
     'After other predicates, a cached random value above this threshold can still choose a punt or field goal. One disables this fallback for random values in [0,1].'),
    ('fg_margin', 'Field-goal safety margin (yards)', 5., 0., 15., .5,
     'Subtract this margin from the kicker range at neutral urgency. Urgency can reduce the margin; end-game branches still apply.'),
    ('draw_max_yards', 'Draw-offside maximum distance (yards)', 2., 0., 5., .25,
     'The draw attempt requires fourth down, a selected punt/field-goal family, timeout eligibility, three timeouts and additional clock, score and field gates.'),
    ('draw_max_goal', 'Draw-offside maximum goal distance (yards)', 55., 0., 100., 1.,
     'Maximum distance to the attacking goal for a draw attempt. The retail one-attempt latch still applies.'),
    ('timeout_seconds', 'Draw-offside timeout below play clock (seconds)', 2., .5, 10., .25,
     'The pre-snap controller requests a timeout below this threshold when its draw flag is active and the defense has not triggered its snap gate.'),
)


def f32(x):
    return struct.unpack('>f', struct.pack('>f', x))[0]


@dataclass(frozen=True)
class Thresholds:
    short_yards: float = 1.
    own_half_limit: float = 50.
    punt_slope: float = .05
    fallback_threshold: float = .95
    fg_margin: float = 5.
    draw_max_yards: float = 2.
    draw_max_goal: float = 55.
    timeout_seconds: float = 2.

    def __post_init__(self):
        for name, title, _, low, high, _, _ in FIELDS:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValidationError(f'{title} must be a finite number from {low:g} to {high:g}')


def address(base, profile):
    if profile == PROFILES[0]:
        return base
    if profile != PROFILES[1]:
        raise ValidationError('Choose BASE or Title Update 1.1')
    return base + (0xCA0 if base < 0x84864700 else 0xCD0 if base < 0x84867938 else 0xD00)


# Original instruction words are independently checked on both pinned images.
SITES = (
    (0x84867078, 0x8486707C, 0x3D60820B, 0xC00B75C0, 0xC00B75E0, 0),
    (0x8486708C, 0x84867090, 0x3D608200, 0xC00B3740, 0xC00B3740, 8),
    (0x8486BF00, 0x8486BF04, 0x3D608200, 0xC00B3850, 0xC00B3850, 12),
    (0x8486B99C, 0x8486B9A4, 0x3D60820C, 0xC00B837C, 0xC00B839C, 16),
    (0x8485EDF0, 0x8485EDF4, 0x3D608200, 0xC00B3708, 0xC00B3708, 20),
    (0x8485EE6C, 0x8485EE70, 0x3D60820B, 0xC00B7A5C, 0xC00B7A7C, 24),
    (0x84836B20, 0x84836B2C, 0x3D608200, 0xC3EB0AC8, 0xC3EB0AC8, 28),
    (0x8486B978, 0x8486B980, 0x3D60820C, 0xC98B92D0, 0xC98B92F0, 32),
)


def _load_pair(original_load, offset):
    target = DATA + offset
    return _d(15, 11, 0, (target + 0x8000) >> 16), (original_load & 0xFFFF0000) | (target & 0xFFFF)


def trampoline(profile):
    """Preserve r11, f0, SP, LR and CTR; replace only the intended CR6 compare."""
    hi, low = _load_pair(0xC00B0000, 4)
    words = (
        _d(62, 1, 1, -0x30) | 1,  # stdu r1,-48(r1)
        _d(62, 11, 1, 8), _d(54, 0, 1, 16),
        hi, low, 0xFF1E0000,  # fcmpu cr6,f30,f0
        _d(50, 0, 1, 16), _d(58, 11, 1, 8), _d(14, 1, 1, 0x30),
        _branch(CAVE + 36, address(0x84867054, profile) + 4),
    )
    return b''.join(struct.pack('>I', w) for w in words)


@dataclass(frozen=True)
class PatchDocument:
    profile: object
    thresholds: Thresholds = Thresholds()
    enabled: bool = DEFAULT_ENABLED

    def __post_init__(self):
        if self.profile not in PROFILES or not isinstance(self.thresholds, Thresholds) or type(self.enabled) is not bool:
            raise ValidationError('Choose a supported image, validated thresholds and a boolean enable flag')

    @property
    def words(self):
        p = self.thresholds
        margin = f32(-p.fg_margin * YARD)
        data = struct.pack('>8fd', p.short_yards * YARD, p.own_half_limit * YARD,
                           p.punt_slope, p.fallback_threshold, margin,
                           p.draw_max_yards * YARD, p.draw_max_goal * YARD,
                           p.timeout_seconds, margin)
        writes = [(DATA + i, int.from_bytes(data[i:i+4], 'big')) for i in range(0, len(data), 4)]
        code = trampoline(self.profile)
        writes += [(CAVE + i, int.from_bytes(code[i:i+4], 'big')) for i in range(0, len(code), 4)]
        writes.append((address(0x84867054, self.profile), _branch(address(0x84867054, self.profile), CAVE)))
        for hi, lo, _, original, _, offset in SITES:
            upper, lower = _load_pair(original, offset)
            writes += [(address(hi, self.profile), upper), (address(lo, self.profile), lower)]
        return tuple(writes)

    @property
    def receipt(self):
        return {'schema': 'apf2k8_fourth_down/v1', 'classification': CLASSIFICATION,
                'profile': self.profile.name, 'image_sha256': self.profile.sha256,
                'thresholds': asdict(self.thresholds), 'enabled': self.enabled,
                'scope': 'Global; all CPU books. Gameplay UNWITNESSED.',
                'data': DATA, 'trampoline': CAVE}

    def as_toml(self):
        lines = [f'title_name = "All-Pro Football 2K8"', f'title_id = "{TITLE_ID}"',
                 f'hash = "{self.profile.module_hash}"', '', '[studio_fourth_down]',
                 *[f'{k} = {float(v)!r}' for k, v in asdict(self.thresholds).items()],
                 '', '[[patch]]', f'name = "{NAME}"',
                 'desc = "Global CPU fourth-down and draw-offside thresholds. In-game result UNWITNESSED."',
                 'author = "2K Football Mod Tools"', f'is_enabled = {str(self.enabled).lower()}']
        for a, v in self.words:
            lines += ['', '[[patch.be32]]', f'address = 0x{a:08X}', f'value = 0x{v:08X}']
        return '\n'.join(lines) + '\n'


def parse_payload(payload: bytes):
    try:
        parsed = tomllib.loads(payload.decode('utf-8'))
        profile = next(p for p in PROFILES if p.module_hash == parsed['hash'])
        row, = parsed['patch']
        document = PatchDocument(profile, Thresholds(**parsed['studio_fourth_down']), row['is_enabled'])
        if parsed != tomllib.loads(document.as_toml()):
            raise ValueError('Metadata, instructions or data differ from the canonical patch')
        return document
    except (UnicodeError, ValueError, TypeError, KeyError, StopIteration) as exc:
        raise ValidationError(f'Choose a canonical Studio fourth-down patch: {exc}') from exc


def canonical_payload(payload):
    document = parse_payload(payload)
    return document.profile, document.enabled


def verify_image(image, document):
    if check_image(image) != document.profile:
        raise ValidationError('Fourth-down document and executable profiles differ')
    for start, end in ((DATA, DATA_LIMIT), (CAVE, CAVE_LIMIT)):
        if any(image[start-IMAGE_BASE:end-IMAGE_BASE]):
            raise ValidationError('Fourth-down persistent reservation is occupied')
    expected = [(0x84867054, 0xFF1EC800)]
    for hi, lo, upper, lower, updated_lower, _ in SITES:
        expected += [(hi, upper), (lo, lower if document.profile == PROFILES[0] else updated_lower)]
    for site, word in expected:
        if struct.unpack_from('>I', image, address(site, document.profile)-IMAGE_BASE)[0] != word:
            raise ValidationError(f'Fourth-down instruction differs at {site:08X}')
    return document.receipt


def preview(thresholds=Thresholds(), *, yards=1., goal_yards=50., kicker_yards=50., random_value=.5):
    """Neutral first-period/tied decision only; tested against native BASE/TU.

    No preview of end-game strategy, skill-derived range, animations or later
    snap behavior. Coordinates follow the harness's float32 stores.
    """
    for value, low, high in ((yards, 0, 100), (goal_yards, 0, 100), (kicker_yards, 1, 100), (random_value, 0, 1)):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValidationError('Preview distances must be 0..100 yards and random value 0..1')
    p = thresholds
    ball = f32(4572 - goal_yards * YARD)
    distance = f32(f32(ball + yards * YARD) - ball)
    goal, kick, random_value = f32(4572 - ball), f32(kicker_yards * YARD), f32(random_value)
    if goal <= f32(kick + f32(-p.fg_margin * YARD)):
        return 'Field goal'
    if goal >= f32(kick - f32(5 * YARD)):
        if goal > f32(p.own_half_limit * YARD):
            return 'Punt'
        cutoff = f32(p.short_yards * YARD)
        chance = f32(f32(f32(cutoff - distance) * f32(p.punt_slope)) * f32(1 / YARD))
        if distance > cutoff or random_value < chance:
            return 'Punt'
    if random_value > f32(p.fallback_threshold):
        return 'Field goal' if goal <= kick else 'Punt'
    return 'Go / scrimmage'


def write_patch(document, output):
    from pathlib import Path
    output = Path(output)
    if output.is_symlink():
        raise ValidationError('Choose a regular patch output file')
    receipt = export_patch(document, output, {"input_paths": []})
    if parse_payload(output.read_bytes()) != document:
        raise ValidationError('Fourth-down patch readback differs')
    return receipt


def main(argv=None):
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=[p.name for p in PROFILES], required=True)
    parser.add_argument('--thresholds', type=Path, help='Authored JSON object; omitted means retail thresholds')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--enable', action='store_true', help='Explicit opt-in; exported patches default disabled')
    args = parser.parse_args(argv)
    parameters = Thresholds(**json.loads(args.thresholds.read_text())) if args.thresholds else Thresholds()
    doc = PatchDocument(next(p for p in PROFILES if p.name == args.profile), parameters, args.enable)
    export_patch(doc, args.output, {"input_paths": [str(args.thresholds)] if args.thresholds else []})
    parse_payload(args.output.read_bytes())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

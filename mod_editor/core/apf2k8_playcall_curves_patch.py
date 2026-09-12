"""EXPERIMENTAL, opt-in category distance curves for pinned BASE and TU 1.1.

No executable is rewritten. Use playcall_patch.export_patch for atomic TOML
export and the Studio installer after its explicit consent step.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import struct
import tomllib
from pathlib import Path

from .apf2k8_playcall_patch import PROFILES, TITLE_ID, ImageProfile, check_image, export_patch
from .apf2k8_playcall_model import OFFENSE_CURVE, DEFENSE_CURVE, f32
from .apf2k8_playcall_model import PlaycallError as ValidationError

DEFAULT_ENABLED = False
CLASSIFICATION = 'EXPERIMENTAL'
NAME = 'Situation personnel distance curves (experimental, unwitnessed)'
DESCRIPTION = 'Make the CPU stick closer to the situation\'s personnel. Shared executable curves affect every team. In-game result unwitnessed.'


def _values(values, count):
    if values is None:
        return None
    if not isinstance(values, tuple) or len(values) != count:
        raise ValidationError(f'Supply exactly {count} category distance weights')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x <= 1 for x in values):
        raise ValidationError('Category distance weights must be finite numbers from zero to one')
    if values[0] != 1 or any(a < b for a, b in zip(values, values[1:])):
        raise ValidationError('Distance weights must start at one and never increase with distance')
    return tuple(f32(x) for x in values)


@dataclass(frozen=True)
class PatchDocument:
    profile: ImageProfile
    offense_category_curve: tuple[float, ...] | None
    defense_category_curve: tuple[float, ...] | None

    def __post_init__(self):
        if self.profile not in PROFILES:
            raise ValidationError('Choose the pinned BASE or TU 1.1 profile')
        object.__setattr__(self, 'offense_category_curve', _values(self.offense_category_curve, 5))
        object.__setattr__(self, 'defense_category_curve', _values(self.defense_category_curve, 3))
        if self.offense_category_curve is None and self.defense_category_curve is None:
            raise ValidationError('Choose at least one curve to export; curves are off by default')

    @property
    def words(self):
        delta = 0x20 if self.profile == PROFILES[1] else 0
        return tuple((base + delta + 8 + i * 8, struct.unpack('>I', struct.pack('>f', value))[0])
                     for base, values in ((0x820C88A8, self.offense_category_curve), (0x820C88D4, self.defense_category_curve))
                     if values is not None for i, value in enumerate(values))

    @property
    def receipt(self):
        return {'schema': 'apf2k8_playcall_curves/v1', 'classification': CLASSIFICATION,
                'status': 'UNWITNESSED in game', 'image_sha256': self.profile.sha256,
                'image': self.profile.name, 'module_hash': self.profile.module_hash,
                'offense_category_curve': self.offense_category_curve,
                'defense_category_curve': self.defense_category_curve}

    def as_toml(self):
        lines = [f'title_name = "All-Pro Football 2K8"', f'title_id = "{TITLE_ID}"',
                 f'hash = "{self.profile.module_hash}"', '', '[[patch]]',
                 f'    name = "{NAME}"', f'    desc = "{DESCRIPTION}"',
                 '    author = "2K Football Mod Tools"', '    is_enabled = true',
                 f'    # Flat image SHA-256: {self.profile.sha256}']
        for address, value in self.words:
            lines.extend(('', '    [[patch.be32]]', f'        address = 0x{address:08X}', f'        value = 0x{value:08X}'))
        return '\n'.join(lines) + '\n'


def build_curve_patch(profile, *, offense_category_curve: tuple[float, ...] | None,
                      defense_category_curve: tuple[float, ...] | None) -> PatchDocument:
    return PatchDocument(profile, offense_category_curve, defense_category_curve)


def verify_curve_image(image: bytes, document: PatchDocument) -> None:
    if check_image(image) != document.profile:
        raise ValidationError('Curve document and executable profiles differ')
    delta = 0x20 if document.profile == PROFILES[1] else 0
    for address, expected in ((0x820C88A8, OFFENSE_CURVE), (0x820C88D4, DEFENSE_CURVE)):
        offset = address - 0x82000000 + delta
        count = struct.unpack_from('>I', image, offset)[0]
        actual = tuple(struct.unpack_from('>f', image, offset + 8 + i * 8)[0] for i in range(count))
        xs = tuple(struct.unpack_from('>f', image, offset + 4 + i * 8)[0] for i in range(count))
        if actual != tuple(map(f32, expected)) or xs != tuple(range(len(expected))):
            raise ValidationError('Pinned retail category curve differs')


def canonical_curve_payload(payload: bytes):
    """Strict installer gate: reconstruct and compare the whole TOML document.

    Returns (profile, enabled). Addresses, metadata, duplicate writes and
    unrelated patches cannot pass by merely using the right title hash.
    """
    try:
        parsed = tomllib.loads(payload.decode('utf-8'))
        profile = next(p for p in PROFILES if p.module_hash == parsed['hash'])
        patch, = parsed['patch']
        enabled = patch['is_enabled']
        if type(enabled) is not bool:
            raise ValueError('Patch enabled flag must be boolean')
        writes = patch['be32']
        mapped = {w['address']: w['value'] for w in writes}
        if len(mapped) != len(writes):
            raise ValueError('Duplicate curve writes')
        delta = 0x20 if profile == PROFILES[1] else 0
        curves = []
        for base, count in ((0x820C88A8, 5), (0x820C88D4, 3)):
            addresses = [base + delta + 8 + 8 * i for i in range(count)]
            curves.append(tuple(struct.unpack('>f', struct.pack('>I', mapped[a]))[0] for a in addresses)
                          if any(a in mapped for a in addresses) else None)
        document = build_curve_patch(profile, offense_category_curve=curves[0], defense_category_curve=curves[1])
        expected = tomllib.loads(document.as_toml())
        expected['patch'][0]['is_enabled'] = enabled
        if parsed != expected:
            raise ValueError('Document differs from the canonical curve patch')
        return profile, enabled
    except (UnicodeError, ValueError, KeyError, TypeError, StopIteration, struct.error) as exc:
        raise ValidationError(f'Choose a canonical Studio category curve patch: {exc}') from exc


def install_xenia_patch(source: Path, patches_folder: Path, config_path: Path, *, consent: bool = False) -> dict:
    """Use P2's verified atomic installer primitives, in a separate curve file.

    The existing pass-fetch file is independently owned and can coexist.
    This function is only called by an explicit install action, never build.
    """
    from mod_editor.apf_studio.launcher import _atomic_bytes, _enabled_config
    if not consent:
        raise ValidationError('Installing the curve patch and enabling Xenia patches requires consent')
    source, patches_folder, config_path = Path(source), Path(patches_folder), Path(config_path)
    destination = patches_folder / '54540807-category-curves.patch.toml'
    for path in (source, destination, config_path):
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValidationError('Curve patch and config paths must be regular files')
    if patches_folder.is_symlink():
        raise ValidationError('Xenia patches folder must not be a symlink')
    try:
        payload = source.read_bytes()
        profile, enabled = canonical_curve_payload(payload)
        if not enabled:
            raise ValidationError('Export an enabled curve patch before installing it')
        old_patch = destination.read_bytes() if destination.exists() else None
        if old_patch is not None:
            canonical_curve_payload(old_patch)
        old_config = config_path.read_bytes() if config_path.exists() else None
        new_config = _enabled_config(old_config or b'')
        if destination.resolve() == config_path.resolve():
            raise ValidationError('Patch and configuration paths must differ')
        _atomic_bytes(destination, payload)
        try:
            _atomic_bytes(config_path, new_config)
            if destination.read_bytes() != payload or config_path.read_bytes() != new_config:
                raise ValidationError('Curve installation readback failed')
        except BaseException:
            if old_patch is None:
                destination.unlink(missing_ok=True)
            else:
                _atomic_bytes(destination, old_patch)
            if old_config is None:
                config_path.unlink(missing_ok=True)
            else:
                _atomic_bytes(config_path, old_config)
            raise
    except OSError as exc:
        raise ValidationError(f'Could not install the curve patch: {exc}') from exc
    return {'installed': True, 'enabled': True, 'profile': profile.name,
            'patch_path': str(destination.resolve()), 'config_path': str(config_path.resolve()),
            'message': 'Experimental category curves installed. In-game result unwitnessed.'}

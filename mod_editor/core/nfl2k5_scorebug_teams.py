"""Official per-team sprite accents, validated before native table compilation.

Two classes of team colour are accepted:

- Sourced accents: an official colour from team_colors_official_2026.json or one of its listed gain/lift
  variants, with at least 4.5:1 contrast against the white label. Every role may use this class.
- Broadcast display shades (the scorebug-only display layer in broadcast_display.json): the on-air shade ESPN
  draws for a team's sourced colour, either measured from a broadcast or fitted from the sourced colour with the
  transfer recorded in that file. Only the wing (and the wash, which mirrors the wing) may use it. The validator
  recomputes every value: a fitted shade from its official parent, a measured shade from the pinned measurement,
  which must also sit within the transfer's recorded bound of its parent's fitted shade. No label is drawn over
  the wing (the down-and-distance label sits on the plate, which keeps the 4.5:1 gate), so the display class has
  no white-label gate; the team's sourced accent for the same role is retained in the record and must stay valid.
"""
import json
import math
from pathlib import Path
import struct

DATA = Path(__file__).resolve().parents[2] / 'data/nfl2k5_scorebug_sprite'
ENTRY = struct.Struct('<5I')  # two UTF16 code units, team kind, wing, rim, plate
FOOTER = struct.Struct('<3I')  # magic, count, scene-relative entries offset
MAGIC = 0x35544e54
ROLES = ('wing', 'rim', 'plate', 'wash')
DISPLAY_FILE = 'broadcast_display.json'
DISPLAY_ROLES = ('wing', 'wash')


def rgb(value):
    if not isinstance(value, str) or len(value) != 7 or value[0] != '#':
        raise ValueError('Expected #RRGGBB team colour')
    return tuple(int(value[i:i+2], 16) for i in (1, 3, 5))


def variants(colours):
    result = {'#'+''.join(f'{round(c*gain+255*lift):02X}' for c in rgb(colour))
              for colour in colours for gain, lift in ((1, 0), (.75, 0), (.5, 0), (.85, .15), (.7, .3))}
    # Brighten a dark official shade without mixing in white, changing its
    # RGB proportions or clipping a channel. The independent 4.5:1 check
    # below still applies to every role, including the possession label.
    result.update('#'+''.join(f'{c*3:02X}' for c in rgb(colour))
                  for colour in colours if max(rgb(colour)) <= 85)
    return result


def contrast_white(value):
    channels = [v/255 for v in rgb(value)]
    linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in channels]
    return 1.05 / (.05 + sum(v*w for v, w in zip(linear, (.2126, .7152, .0722))))


# ---------------------------------------------------------------- broadcast display class
def _linear(channel):
    c = channel / 255
    return c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4


def _encode(value):
    v = min(max(value, 0.0), 1.0)
    return 255 * (12.92 * v if v <= .0031308 else 1.055 * v ** (1 / 2.4) - .055)


def oklab(colour):
    """OKLab (L, a, b) of an sRGB triple on the 0..255 scale."""
    r, g, b = (_linear(c) for c in colour)
    l = (0.4122214708*r + 0.5363325363*g + 0.0514459929*b) ** (1/3)
    m = (0.2119034982*r + 0.6806995451*g + 0.1073969566*b) ** (1/3)
    s = (0.0883024619*r + 0.2817188376*g + 0.6299787005*b) ** (1/3)
    return (0.2104542553*l + 0.7936177850*m - 0.0040720468*s,
            1.9779984951*l - 2.4285922050*m + 0.4505937099*s,
            0.0259040371*l + 0.7827717662*m - 0.8086757660*s)


def oklab_distance(first, second):
    return math.dist(oklab(rgb(first)), oklab(rgb(second)))


def _hsv(colour):
    r, g, b = (c / 255 for c in colour)
    top, low = max(r, g, b), min(r, g, b)
    span = top - low
    if span == 0:
        hue = 0.0
    elif top == r:
        hue = 60 * (((g - b) / span) % 6)
    elif top == g:
        hue = 60 * ((b - r) / span + 2)
    else:
        hue = 60 * ((r - g) / span + 4)
    return hue, (0.0 if top == 0 else span / top), top


def _from_hsv(hue, saturation, value):
    chroma = value * saturation
    x = chroma * (1 - abs((hue / 60) % 2 - 1))
    base = value - chroma
    r, g, b = ((chroma, x, 0), (x, chroma, 0), (0, chroma, x),
               (0, x, chroma), (x, 0, chroma), (chroma, 0, x))[int(hue // 60) % 6]
    return tuple(255 * (c + base) for c in (r, g, b))


def broadcast_shade_rgb(colour, transfer):
    """The display shade of one sourced colour under the fitted broadcast transfer, unrounded.

    Hue kept, saturation scaled, value set (HSV). A chromatic result lighter than the lightest wing measured on
    air (OKLab L above ``lightness_cap``) is scaled down in linear light, keeping its chromaticity, so the
    transfer never extrapolates above the lightness range it was fitted on. Neutral parents (OKLab chroma below
    ``neutral_chroma``) are not capped: the measured silver wing is near white.
    """
    hue, saturation, _value = _hsv(rgb(colour))
    shade = _from_hsv(hue, min(1.0, transfer['saturation'] * saturation), transfer['value'])
    _l, a, b = oklab(rgb(colour))
    if math.hypot(a, b) >= transfer['neutral_chroma'] and oklab(shade)[0] > transfer['lightness_cap']:
        light = [_linear(c) for c in shade]
        low, high = 0.0, 1.0
        for _ in range(48):
            middle = (low + high) / 2
            if oklab([_encode(v * middle) for v in light])[0] > transfer['lightness_cap']:
                high = middle
            else:
                low = middle
        shade = [_encode(v * low) for v in light]
    return tuple(min(max(c, 0.0), 255.0) for c in shade)


def broadcast_shade(colour, transfer):
    """``broadcast_shade_rgb`` as a #RRGGBB colour."""
    return '#' + ''.join('%02X' % int(round(c)) for c in broadcast_shade_rgb(colour, transfer))


def load_display(folder=None):
    path = Path(folder or DATA) / DISPLAY_FILE
    if not path.is_file():
        return None
    display = json.loads(path.read_text(encoding='utf-8'))
    transfer = display.get('transfer', {})
    for key in ('saturation', 'value', 'lightness_cap', 'neutral_chroma', 'measured_bound'):
        if not isinstance(transfer.get(key), (int, float)) or not 0 <= transfer[key] <= 1:
            raise ValueError('Invalid broadcast display transfer: ' + key)
    if tuple(display.get('roles', ())) != DISPLAY_ROLES:
        raise ValueError('The broadcast display layer covers the wing and wash only')
    return display


def display_shade(name, team, display):
    """The display-class value one team's wing must carry, recomputed; raises for any foreign value."""
    layer = team['display']
    if display is None or team['slot'] >= 32 or not isinstance(layer, dict) or layer.get('class') != 'broadcast':
        raise ValueError('Foreign broadcast display record: ' + name)
    parent, sourced = layer.get('parent'), layer.get('sourced')
    if parent not in team['official']:
        raise ValueError('Foreign broadcast display parent: ' + name)
    if sourced not in variants(team['official']) or contrast_white(sourced) < 4.5:
        raise ValueError('Foreign or low-contrast accent: ' + name + '/sourced wing')
    fitted = broadcast_shade(parent, display['transfer'])
    measured = display.get('measured', {}).get(name)
    if layer.get('source') == 'fitted' and measured is None:
        return fitted
    if layer.get('source') == 'measured' and measured is not None:
        value = measured.get('wing')
        rgb(value)
        if measured.get('parent') != parent or not measured.get('evidence'):
            raise ValueError('Foreign broadcast display measurement: ' + name)
        if oklab_distance(value, fitted) > display['transfer']['measured_bound']:
            raise ValueError('Foreign broadcast display measurement, outside the transfer bound: ' + name)
        return value
    raise ValueError('Foreign broadcast display source: ' + name)


def load(path=None):
    data = json.loads(Path(path or DATA/'team_accents.json').read_text(encoding='utf-8'))
    official = json.loads((DATA/'team_colors_official_2026.json').read_text(encoding='utf-8'))
    source = {t['nfl2k5_retail_slot']['index']: {c['hex'].upper() for c in t['colors']
              if not c.get('logo_detail_only')} for t in official['teams']}
    teams = data['teams']
    if {t['slot'] for t in teams.values()} != set(range(52)) or len(teams) != 52:
        raise ValueError('Team accents must cover the 52 roster slots exactly')
    display = load_display() if any('display' in t for t in teams.values()) else None
    identities = {}
    for name, team in teams.items():
        if team['slot'] < 32 and set(team['official']) != source[team['slot']]:
            raise ValueError('Official team palette differs: ' + name)
        allowed = variants(team['official'])
        shade = display_shade(name, team, display) if 'display' in team else None
        for role in ROLES:
            if shade is not None and role in DISPLAY_ROLES:
                if team[role] != shade:
                    raise ValueError('Foreign or low-contrast accent: ' + name + '/' + role
                                     + ' (not its broadcast display shade)')
                continue
            if team[role] not in allowed or contrast_white(team[role]) < 4.5:
                raise ValueError('Foreign or low-contrast accent: ' + name + '/' + role)
        code, kind = team['asset_code'], team['kind']
        if len(code) != 2 or not code.isascii() or not code.isdigit() or kind not in (0, 1, 2, 4, 5):
            raise ValueError('Invalid native team identity: ' + name)
        values = tuple(team[r] for r in ('wing', 'rim', 'plate'))
        if (code, kind) in identities and identities[code, kind] != values:
            raise ValueError('Shared native team identity has conflicting accents: ' + name)
        identities[code, kind] = values
    return teams


def table(teams, scene_offset):
    result = bytearray()
    for team in sorted(teams.values(), key=lambda t: t['slot']):
        code = struct.unpack('<I', team['asset_code'].encode('utf-16le'))[0]
        result += ENTRY.pack(code, team['kind'], *(0xff000000 | int(team[r][1:], 16)
                                                for r in ('wing', 'rim', 'plate')))
    result += FOOTER.pack(MAGIC, len(teams), scene_offset)
    return result

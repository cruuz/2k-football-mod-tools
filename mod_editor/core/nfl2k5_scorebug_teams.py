"""Official per-team sprite accents, validated before native table compilation."""
import json
from pathlib import Path
import struct

DATA = Path(__file__).resolve().parents[2] / 'data/nfl2k5_scorebug_sprite'
ENTRY = struct.Struct('<5I')  # two UTF16 code units, team kind, wing, rim, plate
FOOTER = struct.Struct('<3I')  # magic, count, scene-relative entries offset
MAGIC = 0x35544e54
ROLES = ('wing', 'rim', 'plate', 'wash')


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


def load(path=None):
    data = json.loads(Path(path or DATA/'team_accents.json').read_text(encoding='utf-8'))
    official = json.loads((DATA/'team_colors_official_2026.json').read_text(encoding='utf-8'))
    source = {t['nfl2k5_retail_slot']['index']: {c['hex'].upper() for c in t['colors']
              if not c.get('logo_detail_only')} for t in official['teams']}
    teams = data['teams']
    if {t['slot'] for t in teams.values()} != set(range(52)) or len(teams) != 52:
        raise ValueError('Team accents must cover the 52 roster slots exactly')
    identities = {}
    for name, team in teams.items():
        if team['slot'] < 32 and set(team['official']) != source[team['slot']]:
            raise ValueError('Official team palette differs: ' + name)
        allowed = variants(team['official'])
        for role in ROLES:
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

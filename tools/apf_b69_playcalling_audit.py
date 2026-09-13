"""Read-only sparse XEX evidence for beta-69 control-surface limits."""
from pathlib import Path
import hashlib
import json
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mod_editor.core.apf2k8_playcall_patch import check_image


def audit(image):
    profile = check_image(image)
    if profile.name != 'base':
        raise ValueError('This sparse control-surface audit uses the pinned BASE addresses')
    spans = ((0x84860730,0x848608B0,'independent lineup row search'),
             (0x84867600,0x84867938,'ordinary requested row'),
             (0x8486A1F8,0x8486A720,'situation adjustment'),
             (0x8486AEB0,0x8486B2D0,'category lottery'),
             (0x84A89B40,0x84A89BC8,'MASTER category pointers from book mask'),
             (0x84A8A330,0x84A8A3FC,'record B membership'),
             (0x84A8B438,0x84A8B4DC,'category row read from MASTER'),
             (0x8486BC08,0x8486BD90,'supplied-play formation resolution'),
             (0x84864E90,0x84864EBC,'Hail Mary constructor cache'),
             (0x8486BE14,0x8486BE48,'cached Hail Mary special branch after predicate'))
    result = {'schema':'apf_b69_control_audit/v1','image_sha256':hashlib.sha256(image).hexdigest(),
              'spans':[{'start_va':f'{lo:08X}','end_va_exclusive':f'{hi:08X}',
                        'purpose':name,'sha256':hashlib.sha256(image[lo-0x82000000:hi-0x82000000]).hexdigest()}
                       for lo,hi,name in spans],
              'xex_lineup_offsets':list(struct.unpack_from('>6i',image,0xB9080)),
              'personnel_storage':'Category records and eleven role bytes are MASTER+44, stride16, reached through book+7E0C. The six fallback offsets are XEX-resident.',
              'strings':{},'grade':'PROVED pinned bytes; string presence is not an editable policy lever',
              'limits':'No proved tempo, snap-count, weather-dependent run/pass ratio or coin-toss policy field in the inspected selector/book surface. Executable-wide absence is NOT proved.'}
    for text in ('Weather','Coin Toss','Huddle','Snap Count','Tempo'):
        needle=text.encode('utf-16-be')
        matches=[]; start=0
        while (at:=image.find(needle,start))>=0:
            start=at+2
            if at%2==0:
                matches.append(f'{0x82000000+at:08X}')
        result['strings'][text]=matches
    return result


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.image.read_bytes())
    args.report.write_bytes((json.dumps(result,indent=2,sort_keys=True)+'\n').encode())
    print('PROVED sparse BASE audit; no policy lever inferred from strings')


if __name__=='__main__':main()

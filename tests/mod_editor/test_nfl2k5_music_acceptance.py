"""Opt-in disposable retail image acceptance. Removes every built ISO in finally."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests/mod_editor')]
from test_nfl2k5_music_banks import tone
from mod_editor.core import nfl2k5_music_banks as banks
from mod_editor.core import nfl2k5_music_archive as archive

SOURCE=Path(os.environ.get('NFL2K5_RETAIL_XISO','/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'))


@unittest.skipUnless(os.environ.get('NFL2K5_MUSIC_ACCEPTANCE')=='1' and SOURCE.is_file(),
                     'set NFL2K5_MUSIC_ACCEPTANCE=1 with retail XISO for disposable multi-GB acceptance')
class RetailImageAcceptance(unittest.TestCase):
    def test_menu_200_then_retail_count_and_200_twins(self):
        scratch=ROOT/'.scratch'
        scratch.mkdir(exist_ok=True)
        reports=[]
        last=0
        def progress(stage,done,total):
            nonlocal last
            if time.monotonic()-last>15:
                print(f'{stage}: {done}/{total}',flush=True);last=time.monotonic()
        with tempfile.TemporaryDirectory(prefix='music-acceptance-',dir=scratch) as temp:
            work=Path(temp).resolve()
            paths=[tone(work/f'tone-{i:03}.wav',64*(2+i%5)+17,channels=1 if i%2 else 2) for i in range(200)]
            for bank,count in (('femusic',200),('femusic',7),('cribmusic',200),('cribmusic',59)):
                tracks=[dict(wav=str(p),title=f'Tone {i+1:03}',artist='Synthetic') for i,p in enumerate(paths[:count])]
                recipe=dict(schema=banks.SCHEMA,bank=bank,tracks=tracks)
                output=work/f'{bank}-{count}.iso'
                try:
                    receipt=banks.rebuild(SOURCE,output,recipe,progress=progress)
                    self.assertEqual(receipt['verification']['unaffected_outers'],4321 if bank=='femusic' else 4320)
                    self.assertEqual(receipt['plan']['same_count_fast_path'],count in (7,59))
                    self.assertEqual(output.stat().st_size,receipt['plan']['layout']['image_size'])
                    (scratch/f'music-acceptance-{bank}-{count}.json').write_text(json.dumps(receipt,indent=2)+'\n')
                    reports.append(dict(bank=bank,count=count,encoded_bytes=receipt['plan']['encoded_bytes'],
                        virtual_size=receipt['plan']['layout']['virtual_size'],iso_size=output.stat().st_size,
                        elapsed_seconds=receipt['elapsed_seconds'],planning_seconds=receipt['plan']['planning_seconds'],
                        source_sha256=receipt['plan']['source_sha256'],output_sha256=receipt['verification']['output_sha256'],
                        moved_outers=len(receipt['plan']['layout']['moved_outers']),
                        scratch_bytes=receipt['plan']['scratch_bytes'],pack_f_bytes=receipt['plan']['layout']['packs'][-1]['size']))
                    print(json.dumps(reports[-1]),flush=True)
                finally:
                    output.unlink(missing_ok=True)
            estimates=[banks.estimate(SOURCE,twins=t) for t in (False,True)]
            report=dict(builds=reports,estimates=estimates,disposable_images_deleted=True)
            (scratch/'music-acceptance-summary.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':unittest.main()

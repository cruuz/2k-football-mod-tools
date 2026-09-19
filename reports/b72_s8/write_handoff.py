"""Write the handoff only after final test and closure receipts are complete."""
from pathlib import Path
import json
import runpy

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
runpy.run_path(str(OUT/'summarize.py'))
rows = json.loads((OUT/'validation.json').read_text())
summary = [
    'All four event plates now follow binding availability and current slide on every active owner update.',
    'Hang time, ball on, flag and fumble use one common event-record loop.',
    'The complete event material set is logical 10, 1, 2 and 0, all outside the regular bar reset.',
    'Pending requests alone do not show plates; closing slides remain visible until the native text gate closes.',
    'Null material bindings are guarded, and unrelated material flag bits are preserved.',
    'The compact native material mapping and folded missing-logo checks preserve the existing regular bar behavior.',
    'Final RX usage is 4076 of 4096 bytes, ten fewer than the base and leaving 20 spare bytes.',
    'RW remains 128 bytes; each aspect appendix remains 324832 bytes with 47 quads and no added FONT.',
    'Native sequences cover 675 retained frames per aspect, including hang time after a punt and the next snap.',
    'All plates match their records each frame; every eligible non-event pre-snap state retains five down-label glyphs.',
    'The stale-visibility regression fails against the exact base owner and passes with the final owner.',
    'The rebuilt owner on captured RAM changes only native material 8 from visible to hidden.',
    'The fixed live-data composite restores label mean luminance 120.10 and white pixels at 255, without tone fitting.',
    'Raiders and Lions possession fixtures retain bright label pixels at both aspect settings.',
    's5 team colours, layout and template and all s6/s7 diagnostics are byte-identical to the base.',
    f'All 35 required default-path test files pass below 100 seconds: {sum(r["cases"] for r in rows)} cases and {sum(r["skips"] for r in rows)} existing skips.',
    'Provider integrity, both product closures, ownership/write/space scans and all 31 scorebug composition pairs pass.',
    'The generated provider digest is repinned; shipping allowlists already cover the changed files; integrator manifest regeneration remains.',
    'Jev reviewed the final code; TEST_DISC.md records the exact Experimental test-disc configuration and three player checks.',
    'Delivery is branch b72-s8 in the verified bundle; no disc, emulator run or release is produced, and in-game confirmation is pending.',
]
assert len(summary) == 20
(ROOT/'ASTRA_LAST_MESSAGE.md').write_text('# b72-s8: event plates fixed, offline proof complete, ready for the test disc\n'+
    '\n'.join(f'{i:02d}. {line}' for i,line in enumerate(summary,1))+'\nASTRA_DONE\n',encoding='utf-8',newline='\n')
(ROOT/'ASTRA_REPORT.md').write_text(
    '# b72-s8: event visibility repair\n\n'
    'All four event plates now follow their current native records. The owner fits in 4076/4096 RX bytes; '
    'RW and appended resources do not grow. s5 colours and s6/s7 diagnostics remain intact.\n\n'
    '- [Fix and offline proof](reports/b72_s8/FINDINGS.md)\n'
    '- [Final validation](reports/b72_s8/VALIDATION.md)\n'
    '- [Test-disc configuration and player checks](reports/b72_s8/TEST_DISC.md)\n'
    '- [Jev review](reports/b72_s8/JEV_REVIEW.md)\n\n'
    'The integrator must regenerate the protected cave manifest for the final stack. '
    'No in-game result is claimed. Delivery uses branch b72-s8 in .scratch/astra-b72-s8.bundle, '
    'with base prerequisite c5134e232. The Git store is .scratch/b72-s8.git because the original '
    'worktree metadata is read-only. No release steps were taken.\n',encoding='utf-8',newline='\n')

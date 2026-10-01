"""PROVED OFFLINE: inspect the finished combined disc, with no emulator launch."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import mod_build as mb
from mod_editor.core import nfl2k5_stock_books as stock, nfl2k5_era_rules as era
from mod_editor.core import nfl2k5_espn25_more_moments as moments
from mod_editor.core import nfl2k5_espn25_rosters as rosters
from mod_editor.core import nfl2k5_historic_styles as styles
from mod_editor.core import nfl2k5_depth_roles as roles
from mod_editor.core import nfl2k5_scorebug_runtime as sprite

OUT = Path('/media/noah/Storage/.b76-research/e2/astra-build')
disc = OUT / 'candidate_B_e2.xiso.iso'
build = json.loads(disc.with_suffix('.build.json').read_text())
summary = json.loads(disc.with_suffix('.summary.json').read_text())
assert not summary['not_applied'], summary['not_applied']
receipt = build['result']
result = receipt['result']
for name in ('historic_stock_books', 'espn25_more_moments', 'espn25_named_previews',
             'espn25_era_rules', 'espn25_rosters', 'historic_teams_quick_game'):
    assert result[name] == 'applied', (name, result.get(name))
code_changes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name, digest in json.loads((OUT / 'build-code-hashes.json').read_text()).items()
                if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest}
reader_fix = json.loads((OUT / 'postbuild-reader-fix.json').read_text())
assert code_changes == {name: row['after_sha256'] for name, row in reader_fix['changes'].items()}, code_changes
assert reader_fix['all_other_module_ast_identical'] and reader_fix['provider_change_only_reader_content_pin']
assert not reader_fix['disc_rewritten']
xbe = rosters.read_xbe(disc)
checks = dict(stock_xbe=stock.status(xbe), stock_bank=stock.image_status(disc),
              moments_xbe=moments.status(xbe), moments_resources=moments.image_status(disc),
              named_previews=moments.named_image_status(disc), era_rules=era.status(xbe),
              original_rosters=rosters.image_status(disc))
assert all(value == 'applied' for value in checks.values()), checks
# Every enabled executable owner is checked again on the final copy.
states = mb.tt._grown_status_fields(xbe)
for name, value in states.items():
    if name in summary['applied'] and isinstance(value, str):
        assert value == 'applied', (name, value)
inactive_foreign = {name: value for name, value in states.items() if value == 'foreign'}
assert set(inactive_foreign) <= {'flatter_deep_ball'}, inactive_foreign
assert all(receipt['plan'][name] is False for name in inactive_foreign), inactive_foreign
assert set(summary['expected_foreign']) <= {'scorebug', 'depth_roles'}, summary['expected_foreign']
# The legacy byte-pin inspectors cannot describe a sprite HUD or custom books.
# Read their active owners directly, including every book the role writer touched.
assert sprite.status(xbe) == 'applied'
role_step = next(step for step in receipt['steps'] if step['step'] == 'depth_roles')
assert role_step['status'] == 'applied' and role_step['gate_ok']
scoring = receipt['playbook_scoring']
assert scoring['status'] == 'applied' and scoring['faults'] == 0
assert scoring['books'] == len(scoring['results']) == 37 + len(stock.aliases())
with styles.Source(disc) as source:
    table = source.archive.entries
    role_books = []
    for row in role_step['books']:
        raw = source.archive.read_entry(row['outer_index'])
        normalized = roles.normalise(raw)
        assert normalized.replacement == raw, ('depth roles changed later', row['outer_index'])
        role_books.append(dict(outer_index=row['outer_index'], name=normalized.report['name'],
                               sha256=hashlib.sha256(raw).hexdigest(), changed_bytes=0))
    books = [dict(source=row['source'], alias=row['alias'],
                  stock_sha256=hashlib.sha256(source.get(row['alias'])).hexdigest(),
                  modern_sha256=hashlib.sha256(source.get(row['source'])).hexdigest())
             for row in stock.aliases()]
    assert all(b['stock_sha256'] != b['modern_sha256'] for b in books)
    stock_indices = {source.by_id[styles.name_id(row['alias'])].index for row in stock.aliases()}
    assert stock_indices <= {row['entry'] for row in scoring['results']}
    directory = dict(count=len(table), first_payload=table[0].virtual_offset,
                     unique_ids=len({entry.name_id for entry in table}))
    assert directory['unique_ids'] == directory['count']
digest = hashlib.sha256()
with disc.open('rb') as stream:
    for block in iter(lambda: stream.read(1 << 24), b''):
        digest.update(block)
output = dict(size=disc.stat().st_size, sha256=digest.hexdigest())
assert output == {k: receipt['outcome']['output'][k] for k in output}
proof = dict(classification='PROVED OFFLINE', runtime_witnessed=False, output=output,
             postbuild_reader_fix=reader_fix,
             checks=checks, directory=directory, books=books, route=era.routing_info(xbe),
             runtime_states=states, applied=summary['applied'],
             inactive_inspection_exceptions=inactive_foreign,
             legacy_inspection_exceptions=summary['expected_foreign'],
             active_owner_readback=dict(scorebug_runtime='applied', depth_roles='applied',
                                        depth_role_books=role_books),
             native_play_scoring=dict(status=scoring['status'], books=scoring['books'],
                                      faults=scoring['faults'], stock_aliases=len(stock_indices)),
             settings_and_inputs=summary['not_inspected'])
(OUT / 'full-disc-proof.json').write_text(json.dumps(proof, indent=2, default=str) + '\n')
print('PROVED OFFLINE', json.dumps(dict(checks=checks, directory=directory, output=output)), flush=True)

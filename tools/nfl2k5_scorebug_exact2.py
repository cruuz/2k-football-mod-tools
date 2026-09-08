#!/usr/bin/env python3
"""Continue the broadcast comparison with bounded, retained coordinate trials.

This is an authoring tool. --write installs a converged candidate and its pins.
It reads pinned pack slices, writes no disc, and makes no GPU/gameplay claim.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import nfl2k5_scorebug_exact as comparator
from mod_editor.core import nfl2k5_scorebug_exact as exact
from mod_editor.core import nfl2k5_scorebug_fonts as fonts
from mod_editor.core import nfl2k5_scorebug_resources as art
from mod_editor.core import nfl2k5_scorebug_ingame as scene


def settings():
    return dict(anchors=deepcopy(exact.RUNTIME_ANCHORS), scales=fonts.SCALES,
                weight=fonts.WEIGHT, chevron=fonts.CHEVRON, compact=fonts.COMPACT_SCORES,
                quarter_caps=fonts.QUARTER_CAPS,
                chevron_size=fonts.CHEVRON_SIZE,
                style=deepcopy(getattr(exact, 'STYLE', {})))


def configure(config):
    exact.RUNTIME_ANCHORS = deepcopy(config['anchors'])
    fonts.SCALES = tuple(tuple(v) for v in config['scales'])
    fonts.WEIGHT, fonts.CHEVRON, fonts.COMPACT_SCORES = config['weight'], config['chevron'], config['compact']
    fonts.QUARTER_CAPS = config.get('quarter_caps', False)
    fonts.CHEVRON_SIZE = tuple(config.get('chevron_size', (8,4)))
    if hasattr(exact, 'STYLE'):
        exact.STYLE = deepcopy(config['style'])


def replace_constants(path, values):
    """Replace only explicitly named assignments, including multiline values."""
    contents = path.read_text(encoding='utf-8')
    lines, edits = contents.splitlines(keepends=True), []
    for node in ast.parse(contents).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in values:
                edits.append((node.lineno - 1, node.end_lineno, name))
    if {name for _, _, name in edits} != set(values):
        raise ValueError('missing unique compiler assignment')
    for first, last, name in reversed(edits):
        lines[first:last] = [name + ' = ' + repr(values[name]) + '\n']
    path.write_text(''.join(lines), encoding='utf-8')


class Loop:
    def __init__(self, pack, xbe, output, stage):
        self.output, self.stage = output, stage
        self.build = comparator.Build(pack, xbe)
        self.source, self.target = comparator.reference()
        self.text_boxes = comparator.reference_text_boxes(self.source)
        self.document = json.loads((output / 'scores.json').read_text())
        self.trials = self.document['iterations']
        self.cache = {json.dumps(row['parameters'], sort_keys=True): row for row in self.trials
                      if row.get('stage') == stage and row.get('metric_version') == 4}
        self.plateaus = []
        self.panel_style = None

    def close(self):
        self.build.close()

    def refresh(self, config):
        configure(config)
        self.build.font_spans = fonts.compile_collection(self.build.view)
        self.build.private_fonts = [comparator.projection.private_font(span, self.build.fonts[slot])
            for span, (slot, _sx, _sy) in zip(self.build.font_spans, fonts.SCALES)]
        panel_keys = ('silver', 'red', 'silver_falloff', 'silver_reflection', 'red_reflection',
                      'wordmark_hou', 'wordmark_weight')
        key = json.dumps({k:v for k,v in config['style'].items() if k in panel_keys or k.startswith(('lv_', 'hou_'))}, sort_keys=True)
        if key != self.panel_style:
            art._compiled_panels.cache_clear()
            self.build.panels = []
            for team, side in (('LV', 'away'), ('HOU', 'home')):
                record = art.TEAM_LOGOS[team]
                span = self.build.view[record['pack_offset']:record['pack_offset'] + record['span_size']]
                self.build.panels.extend(art._compiled_panels(self.build.spans['score_buga'], span, team, side))
            self.panel_style = key

    def trial(self, config, label):
        from PIL import Image
        import numpy as np
        key = json.dumps(config, sort_keys=True)
        if key in self.cache:
            return self.cache[key]
        self.refresh(config)
        number = len(self.trials)
        path = self.output / f'iter_{number:02d}_runtime.png'
        geometry = self.build.render(path, runtime=True)
        with Image.open(path) as opened:
            picture = opened.convert('RGB')
        scores = comparator.compare(self.target, picture, geometry, self.text_boxes, runtime=True)
        if scores['containment']:
            raise ValueError('candidate escapes native frame: ' + str(scores['containment']))
        ref, rendered = np.asarray(self.target).astype(float), np.asarray(picture).astype(float)
        for callback, source_box in comparator.TEXT_ROIS.items():
            a, b, c, d = map(round, exact.hud_box(source_box))
            scores['text'][callback]['roi_rgb_mae'] = float(np.abs(ref[b:d, a:c] - rendered[b:d, a:c]).mean())
        if config['chevron']:
            cue = [row for row in geometry['draws'] if row['font'] == fonts.NAMES[4] and
                   any(int(v['color'],16) >> 24 for v in row['vertices'])]
            if len(cue) != 1 or len(cue[0]['vertices']) != 4 or cue[0]['text'] != 'v':
                raise ValueError('possession must submit exactly one native glyph')
            box = comparator.box_of([v['screen'] for v in cue[0]['vertices']])
            target = exact.hud_box((1138,947,1181,955))
            a,b,c,d = map(round,exact.hud_box((1125,941,1195,960)))
            scores['possession'] = dict(native_quad_box=box,reference_ink_box=target,
                max_error_px=max(abs(x-y) for x,y in zip(box,target)), glyph_count=1,
                roi_rgb_mae=float(np.abs(ref[b:d,a:c]-rendered[b:d,a:c]).mean()))
        record = dict(iteration=number, label=self.stage + ': ' + label, stage=self.stage,
                      parameters=deepcopy(config), layers={'runtime': scores}, metric_version=4,
                      resources=geometry['resource_receipt'], private_fonts=geometry['private_fonts'],
                      accepted=False, variant_is_shipped=False)
        if self.stage == 'compact':
            self.stress(record)
        self.trials.append(record)
        self.cache[key] = record
        self.document['complete'] = False
        comparator.write_json(self.output / 'scores.json', self.document)
        print(number, label, 'MAE', round(scores['mean_region_rgb_mae'], 4), flush=True)
        return record

    def stress(self, record):
        if 'three_digit' not in record:
            self.refresh(record['parameters'])
            stress = self.build.render(self.output / f"iter_{record['iteration']:02d}_three_digit.png",runtime=True,
                                       score_values=(333,333),previous_scores=(99,99))
            boxes = {row['callback']:comparator.box_of([v['screen'] for v in row['vertices']])
                     for row in stress['draws'] if row['callback'] in ('0xfc050','0xfc070') and row['vertices']}
            left,_,right,_ = exact.hud_box(exact.SOURCE_REGIONS['centre_pill'])
            record['three_digit'] = dict(scores=(333,333),native_boxes=boxes,
                home_clearance=boxes['0xfc050'][0]-right,away_clearance=left-boxes['0xfc070'][2],
                minimum_clearance=3.,native_fonts={r['callback']:r['font'] for r in stress['draws']
                    if r['callback'] in boxes},containment=comparator.projection.containment_failures(stress,stress['frame'],.02),
                metric='Clearance from the centre pill; no three-digit reference photograph exists.')
        return record['three_digit']

    def descend(self, best, name, getter, setter, steps, bounds, objective, epsilon=.001):
        """Both neighbours must fail at every step; bounds are reported explicitly."""
        evidence = []
        for step in steps:
            for _ in range(32):
                current = getter(best['parameters'])
                choices = [best]
                for direction in (-1, 1):
                    value = round(current + step * direction, 6)
                    if bounds[0] <= value <= bounds[1]:
                        config = deepcopy(best['parameters'])
                        setter(config, value)
                        choices.append(self.trial(config, name + '=' + str(value)))
                candidate = min(choices, key=lambda row: (objective(row), row['iteration']))
                evidence.append(dict(step=step, centre=best['iteration'], neighbours=[r['iteration'] for r in choices[1:]],
                                     objective_before=objective(best), objective_best=objective(candidate)))
                if objective(best) - objective(candidate) <= epsilon:
                    break
                best = candidate
            else:
                raise ValueError('coordinate did not plateau within 32 moves: ' + name)
        self.plateaus.append(dict(parameter=name, bounds=bounds, steps=steps, epsilon=epsilon, trials=evidence,
                                  selected_iteration=best['iteration']))
        return best

    def font_stage(self, best, groups=None):
        groups = groups or ((0, ('drop_down',), ('0xfc7d0',)),
                  (1, ('clock_a', 'clock_b'), ('0xfc150',)),
                  (2, ('home_score', 'away_score'), ('0xfc050', '0xfc070')),
                  (5, ('quarter',), ('0xfc090',)), (6, ('drop_clock',), ('0xfbe30',)))
        for slot, anchors, callbacks in groups:
            def objective(row):
                text = row['layers']['runtime']['text']
                return sum(text[key]['max_error_px'] + .002 * text[key]['roi_rgb_mae'] for key in callbacks) / len(callbacks)
            for axis in (1, 2):
                def set_scale(config, value):
                    scales = [list(v) for v in config['scales']]
                    scales[slot][axis] = value
                    config['scales'] = scales
                centre = best['parameters']['scales'][slot][axis]
                best = self.descend(best, f'font{slot}.scale{axis}', lambda c: c['scales'][slot][axis],
                                    set_scale, (.01,), (max(.2, centre-.06), min(1.5, centre+.06)), objective)
            for axis in (0, 1):
                def set_anchor(config, value):
                    difference = value - config['anchors'][anchors[0]][axis]
                    for anchor in anchors:
                        xyz = list(config['anchors'][anchor]); xyz[axis] += difference
                        config['anchors'][anchor] = xyz
                centre = best['parameters']['anchors'][anchors[0]][axis]
                best = self.descend(best, f'{anchors[0]}.axis{axis}', lambda c: c['anchors'][anchors[0]][axis],
                                    set_anchor, (1., .5, .25), (centre-2, centre+2), objective)
        return best

    def quarter_stage(self, best):
        candidate = deepcopy(best['parameters'])
        scales = [list(v) for v in candidate['scales']]
        scales[5] = [3, .43, .59]
        candidate['scales'] = scales
        candidate['anchors']['quarter'] = (-28.333, -19.855, -4)
        revised = self.trial(candidate, 'quarter excludes capsule-border component')
        objective = lambda r: r['layers']['runtime']['text']['0xfc090']['max_error_px']
        best = min((best, revised), key=objective)
        return self.font_stage(best, ((5, ('quarter',), ('0xfc090',)),))

    @staticmethod
    def region_objective(*names):
        def objective(row):
            regions = row['layers']['runtime']['regions']
            return sum(regions[name]['rgb_mae'] for name in names) / len(names)
        return objective

    def style_coordinate(self, best, name, steps, bounds, regions):
        integer = type(best['parameters']['style'][name]) is int
        def setter(config, value):
            config['style'][name] = int(value) if integer else value
        return self.descend(best, name, lambda c: c['style'][name], setter, steps, bounds,
                            self.region_objective(*regions), epsilon=.005)

    def choices(self, best, name, values, setter, objective):
        rows = [best]
        for value in values:
            config = deepcopy(best['parameters'])
            setter(config, value)
            rows.append(self.trial(config, name + '=' + str(value)))
        selected = min(rows, key=lambda row: (objective(row), row['iteration']))
        self.plateaus.append(dict(parameter=name, enumerated_values=values, trials=[r['iteration'] for r in rows],
            objective_values=[objective(r) for r in rows], selected_iteration=selected['iteration']))
        return selected

    def rim_stage(self, best):
        regions = ('frame_rim', 'left_panel', 'right_panel')
        best = self.choices(best, 'rim reflection profile', (0,1),
            lambda c,v: c['style'].__setitem__('rim', v), self.region_objective(*regions))
        for name, steps, bounds, affected in (
            ('rim_gain', (8,2,1), (-24,24), ('frame_rim',)),
            ('rim_red', (12,3,1), (-24,24), ('frame_rim',)),
            ('silver', (8,2), (208,248), ('left_panel',)),
            ('silver_falloff', (.1,.025), (.1,.5), ('left_panel',)),
            ('silver_reflection', (.4,.1), (0.,2.), ('left_panel',)),
            ('red', (12,3), (191,254), ('right_panel',)),
            ('red_reflection', (.4,.1), (0.,2.), ('right_panel',))):
            best = self.style_coordinate(best, name, steps, bounds, affected)
        return best

    def cells_stage(self, best):
        def pill_profile(config, value):
            config['style'].update(pill_profile=value, pill_radius=3 if value else 0)
        candidate = deepcopy(best['parameters'])
        pill_profile(candidate,1)
        shaped = self.trial(candidate,'pill lower corners=1')
        shaped = self.style_coordinate(shaped,'pill_radius',(1,),(0,8),('centre_pill',))
        best = min((best,shaped),key=self.region_objective('centre_pill'))
        def separator_profile(config, value):
            config['style'].update(separator_profile=value, separator=168 if value else 248,
                separator_right_x=46.5 if value else 46., separator_left_x=16.5 if value else 16.,
                separator_left=1)
        candidate = deepcopy(best['parameters'])
        separator_profile(candidate,1)
        reflected = self.trial(candidate,'separator reflection=1 with fractional texel placement')
        for key in ('separator_left_x','separator_right_x'):
            bounds = (14.,19.) if key.endswith('left_x') else (44.,50.)
            reflected = self.style_coordinate(reflected,key,(.5,.25),bounds,('clock_strip',))
        reflected = self.style_coordinate(reflected,'separator',(16,4),(8,255),('clock_strip',))
        best = min((best,reflected),key=self.region_objective('clock_strip'))
        for name, steps, bounds, regions in (
            ('pill_radius', (1,), (0,8), ('centre_pill',)),
            ('clock_radius', (1,), (0,10), ('clock_strip',)),
            ('clock_fill', (8,2), (207,255), ('clock_strip',)),
            ('separator', (16,4), (8,255), ('clock_strip',))):
            best = self.style_coordinate(best, name, steps, bounds, regions)
        best = self.choices(best, 'left clock separator', (0,1),
            lambda c,v: c['style'].__setitem__('separator_left',v), self.region_objective('clock_strip'))
        if best['parameters']['style'].get('separator_profile'):
            best = self.style_coordinate(best, 'separator_left_x', (.5,.25), (14.,19.), ('clock_strip',))
            best = self.style_coordinate(best, 'separator_right_x', (.5,.25), (44.,50.), ('clock_strip',))
        return best

    def weights_stage(self, best):
        for slot, callbacks in ((0,('0xfc7d0',)), (1,('0xfc150',)),
                                (2,('0xfc050','0xfc070')), (5,('0xfc090',)), (6,('0xfbe30',))):
            def objective(row):
                rows = [row['layers']['runtime']['text'][key] for key in callbacks]
                return sum(r['roi_rgb_mae'] + 200*max(0,r['max_error_px']-1) for r in rows) / len(rows)
            def setter(config, value):
                weights = [config['weight']]*len(fonts.NAMES) if type(config['weight']) is int else list(config['weight'])
                weights[slot] = value
                if slot == 2: weights[3] = value
                config['weight'] = weights
            best = self.choices(best, 'font'+str(slot)+' mask weight', (-1,0,1), setter, objective)
        best = self.choices(best, 'quarter superscript capitals', (False,True),
            lambda c,v: c.__setitem__('quarter_caps',v),
            lambda r: r['layers']['runtime']['text']['0xfc090']['roi_rgb_mae'] +
                200*max(0,r['layers']['runtime']['text']['0xfc090']['max_error_px']-1))
        best = self.choices(best, 'TEXANS wordmark', (0,1),
            lambda c,v: c['style'].__setitem__('wordmark_hou',v), self.region_objective('right_panel'))
        return self.choices(best, 'tiny wordmark weight', (-1,0,1),
            lambda c,v: c['style'].__setitem__('wordmark_weight',v), self.region_objective('left_panel','right_panel'))

    def logos_stage(self, best):
        for prefix, region in (('lv','left_panel'), ('hou','right_panel')):
            for suffix, steps, bounds in (('width',(2,1),(36,60)), ('height',(2,1),(27,43)),
                                         ('dx',(2,1),(-8,8)), ('dy',(2,1),(-8,3))):
                best = self.style_coordinate(best, prefix+'_'+suffix, steps, bounds, (region,))
        return best

    def chevron_stage(self, best, objective=None):
        if not best['parameters']['chevron']:
            config = deepcopy(best['parameters'])
            config.update(chevron=True, chevron_size=(14,4))
            config['anchors'].update(home_city=(59.5,0,-64),away_city=(-75,0,-64))
            best = self.trial(config,'one native possession glyph')
        def cue_objective(row):
            cue = row['layers']['runtime']['possession']
            return cue['roi_rgb_mae'] + 100*max(0,cue['max_error_px']-1)
        objective = objective or cue_objective
        for axis, bounds in ((0,(10,18)),(1,(2,6))):
            def setter(config,value):
                size = list(config['chevron_size'])
                if axis == 0:
                    for anchor in ('home_city','away_city'):
                        xyz = list(config['anchors'][anchor]); xyz[0] += (size[0]-value)/2
                        config['anchors'][anchor] = xyz
                size[axis] = int(value); config['chevron_size'] = size
            best = self.descend(best,'chevron dimension '+str(axis),lambda c:c['chevron_size'][axis],
                                setter,(1,),bounds,objective,epsilon=.005)
        for axis in (0,1):
            def setter(config,value):
                delta=value-config['anchors']['home_city'][axis]
                for anchor in ('home_city','away_city'):
                    xyz=list(config['anchors'][anchor]);xyz[axis]+=delta;config['anchors'][anchor]=xyz
            centre=best['parameters']['anchors']['home_city'][axis]
            best=self.descend(best,'possession position '+str(axis),lambda c:c['anchors']['home_city'][axis],
                              setter,(1.,.5,.25),(centre-2,centre+2),objective,epsilon=.005)
        return best

    def compact_stage(self, best):
        if not best['parameters']['compact']:
            config=deepcopy(best['parameters']);config['compact']=True
            best=self.trial(config,'independent compact FONT at 100+')
        def objective(row):
            stress=self.stress(row)
            gap=min(stress['home_clearance'],stress['away_clearance'])
            return 100*max(0,3-gap)-row['parameters']['scales'][3][1]
        def setter(config,value):
            scales=[list(v) for v in config['scales']]
            scales[3][1]=value;scales[3][2]=scales[2][2];config['scales']=scales
        return self.descend(best,'compact score width',lambda c:c['scales'][3][1],setter,
                            (.04,.02,.01),(.35,.75),objective,epsilon=.0001)

    def plateau_stage(self, best):
        """Recheck coupled regions at the final settings, including rounding jumps.

        Earlier stages retain their wider domains and alternative model families.
        This final neighbourhood uses the same five-region RGB score with hard
        penalties for losing the measured one-pixel text/possession fit. Every
        candidate retains all regional scores, including rejected tradeoffs.
        """
        def objective(row):
            layer = row['layers']['runtime']
            errors = [v['max_error_px'] for v in layer['text'].values()]
            if 'possession' in layer:
                errors.append(layer['possession']['max_error_px'])
            return layer['mean_region_rgb_mae'] + 1000*sum(max(0,v-1) for v in errors)
        for name, step, bounds in (
            ('rim_gain',1,(-24,24)), ('rim_red',1,(-24,24)),
            ('silver',2,(208,248)), ('silver_falloff',.025,(.1,.5)),
            ('silver_reflection',.1,(0.,2.)), ('red',3,(191,254)), ('red_reflection',.1,(0.,2.)),
            ('pill_radius',1,(0,8)), ('clock_radius',1,(0,10)), ('clock_fill',2,(207,255)),
            ('separator',4,(8,255)), ('separator_left_x',.25,(14.,19.)), ('separator_right_x',.25,(44.,50.)),
            ('lv_width',1,(36,60)), ('lv_height',1,(27,43)), ('lv_dx',1,(-8,8)), ('lv_dy',1,(-8,3)),
            ('hou_width',1,(36,60)), ('hou_height',1,(27,43)), ('hou_dx',1,(-8,8)), ('hou_dy',1,(-8,3))):
            integer = type(best['parameters']['style'][name]) is int
            def setter(config,value): config['style'][name] = int(value) if integer else value
            best = self.descend(best,name,lambda c:c['style'][name],setter,(step,),bounds,objective,epsilon=.005)
        for slot, anchors in ((0,('drop_down',)), (1,('clock_a','clock_b')),
                              (2,('home_score','away_score')), (5,('quarter',)), (6,('drop_clock',))):
            for axis in (1,2):
                def setter(config,value):
                    scales = [list(v) for v in config['scales']];scales[slot][axis] = value
                    if slot == 2 and axis == 2: scales[3][2] = value
                    config['scales'] = scales
                centre = best['parameters']['scales'][slot][axis]
                best = self.descend(best,f'font{slot}.scale{axis}',lambda c:c['scales'][slot][axis],
                    setter,(.01,),(max(.2,centre-.03),min(1.5,centre+.03)),objective,epsilon=.005)
            for axis in (0,1):
                def setter(config,value):
                    delta = value-config['anchors'][anchors[0]][axis]
                    for name in anchors:
                        xyz = list(config['anchors'][name]);xyz[axis] += delta;config['anchors'][name] = xyz
                centre = best['parameters']['anchors'][anchors[0]][axis]
                best = self.descend(best,anchors[0]+'.axis'+str(axis),lambda c:c['anchors'][anchors[0]][axis],
                    setter,(1.,.5,.25),(centre-2,centre+2),objective,epsilon=.005)
            def setter(config,value):
                weights = list(config['weight']);weights[slot] = value
                if slot == 2: weights[3] = value
                config['weight'] = weights
            best = self.choices(best,f'font{slot}.weight',(-1,0,1),setter,objective)
        for name,values in (('wordmark_hou',(0,1)), ('wordmark_weight',(-1,0,1)),
                            ('separator_left',(0,1)), ('rim',(0,1))):
            best = self.choices(best,name,values,lambda c,v:c['style'].__setitem__(name,v),objective)
        best = self.choices(best,'quarter capitals',(False,True),lambda c,v:c.__setitem__('quarter_caps',v),objective)
        best = self.chevron_stage(best,objective=objective)
        return self.compact_stage(best)

    def install(self, best, write):
        config = best['parameters']
        self.refresh(config)
        pins = comparator.compiler_pins(self.build)
        if write:
            replace_constants(Path(exact.__file__), dict(RUNTIME_ANCHORS=config['anchors'],
                **({'STYLE': config['style']} if hasattr(exact, 'STYLE') else {})))
            replace_constants(Path(fonts.__file__), dict(SCALES=tuple(tuple(v) for v in config['scales']),
                WEIGHT=config['weight'], CHEVRON=config['chevron'], COMPACT_SCORES=config['compact'],
                QUARTER_CAPS=config.get('quarter_caps', False), CHEVRON_SIZE=tuple(config.get('chevron_size',(8,4)))))
            replace_constants(Path(art.__file__), pins)
            for name, value in pins.items(): setattr(art, name, value)
            scene.PATCHED_SHA256 = art.PATCHED_SHA256
        for row in self.trials:
            row['variant_is_shipped'] = bool(write and row is best)
        best['accepted'] = True
        self.document.update(complete=True, selected_iteration=best['iteration'], selected_red_bias=exact.RED_BIAS,
            exact_match=False, loop_scope='Measured local plateaus in documented parameter ranges; no global optimum or gameplay witness.')
        self.document.setdefault('first_pass_final_scores', self.document.get('final_scores', {}))
        self.document['final_scores'] = {'runtime_4x3_mode0': best['layers']['runtime']}
        self.document['full_audit_current'] = False
        self.document['audit_scope'] = 'Current stage checkpoint; final audit refreshes both aspects and modes.'
        self.document.setdefault('audit', {})['current_source_sha256'] = {
            str(Path(module.__file__).relative_to(ROOT)): scene.digest(Path(module.__file__).read_bytes())
            for module in (exact, fonts, art, comparator, comparator.projection)}
        self.document.setdefault('converged_stages', []).append(dict(stage=self.stage, iteration=best['iteration'],
            installed=write, coordinates=self.plateaus))
        comparator.write_json(self.output / 'compiler_pins.json', pins)
        comparator.write_json(self.output / 'scores.json', self.document)
        self.summary_images(best)

    def summary_images(self, best):
        from PIL import Image, ImageDraw
        strip = Image.new('RGB', (740, 85 * len(self.trials)), '#101010')
        for trial in self.trials:
            y = trial['iteration'] * 85
            ImageDraw.Draw(strip).text((6, y+2), trial['label'], fill='white')
            for i, suffix in enumerate(('static', 'runtime')):
                path = self.output / f"iter_{trial['iteration']:02d}_{suffix}.png"
                if path.is_file():
                    with Image.open(path) as opened:
                        strip.paste(opened.crop((135, 398, 505, 460)), (i*370, y+20))
        strip.save(self.output / 'iteration_strip.png')
        sheet = Image.new('RGB', (740, 112), '#101010')
        sheet.paste(self.target.crop((135,398,505,460)), (0,24))
        with Image.open(self.output / f"iter_{best['iteration']:02d}_runtime.png") as opened:
            sheet.paste(opened.crop((135,398,505,460)), (370,24))
        draw = ImageDraw.Draw(sheet)
        draw.text((6,6), 'REAL BROADCAST', fill='white')
        draw.text((376,6), f"NATIVE INPUTS, ITERATION {best['iteration']}", fill='white')
        draw.text((6,94), 'EXPERIMENTAL / UNWITNESSED / GPU BLEND REMAINS A MODEL', fill='white')
        sheet.save(self.output / 'final_side_by_side.png')


def main(argv=None):
    retail = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', type=Path, default=retail / 'vc_53450030/0')
    parser.add_argument('--xbe', type=Path, default=retail / 'default.xbe')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/scorebug_ingame/exact')
    parser.add_argument('--stage', choices=('fonts','quarter','rim','cells','weights','logos','chevron','compact','plateau'), required=True)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)
    loop = Loop(args.pack, args.xbe, args.output, args.stage)
    try:
        best = loop.trial(settings(), 'starting compiler')
        method = getattr(loop, 'font_stage' if args.stage == 'fonts' else args.stage + '_stage')
        for pass_number in range(16):
            previous = best
            best = method(best)
            if best is previous:
                break
        else:
            raise ValueError('stage did not settle in 16 coordinate passes')
        loop.install(best, args.write)
        print('selected', best['iteration'], 'plateau coordinates', len(loop.plateaus), flush=True)
    finally:
        loop.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

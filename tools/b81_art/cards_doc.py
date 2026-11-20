"""Writes data/nfl2k5_b81_art_cards.json (what the tests pin) from the pass receipts: every Team Select card and mini
helmet the cleanup replaces, by RGBA SHA-256 of the project PNG it was made from and of the new PNG."""
import sys, json; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C
OUT = C.WORK.parent / 'out'
def build():
    cards = json.load(open(OUT / 'card_receipt.json')); minis = json.load(open(OUT / 'mini_receipt.json'))
    target = C.WT / 'data' / 'nfl2k5_b81_art_cards.json'
    old = json.load(open(target))
    pick = lambda r: dict(changed_pixels=int(r.get('changed_pixels', r.get('changed', 0))), new_rgba_sha256=r['new_rgba_sha256'], source_rgba_sha256=r['source_rgba_sha256'])
    doc = dict(schema='nfl2k5_b81_art_cards/v1', about=old['about'],
               cards={k: pick(v) for k, v in sorted(cards.items())}, minis={k: pick(v) for k, v in sorted(minis.items())},
               helmet_reassign=json.load(open(OUT / 'helmet_reassign.json')),
               helmets={k: dict(new_rgba_sha256=v['new_rgba_sha256'], source_rgba_sha256=v['source_rgba_sha256'])
                        for k, v in sorted(json.load(open(OUT / 'helmet_receipt.json')).items())})
    target.write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    return doc
if __name__ == '__main__':
    d = build(); print('cards', len(d['cards']), 'minis', len(d['minis']), 'helmets', sorted(d['helmets']))

"""Current getting-started and FAQ links resolve without fetching the internet."""
from __future__ import annotations
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
DOCS = [ROOT / 'docs/mod_editor' / (product + '_mod_studio_' + kind + '.md')
        for product in ('2k5', 'apf2k8') for kind in ('getting_started', 'faq')]
LINK = re.compile(r'(?<!!)\[[^\]]+\]\(([^)]+)\)')

class DocLinkTests(unittest.TestCase):
    def test_current_guides_and_faqs_have_no_broken_local_links(self):
        failures = []
        for doc in DOCS:
            for raw in LINK.findall(doc.read_text(encoding='utf-8')):
                target = raw.strip().split(' "')[0].strip('<>')
                parsed = urlsplit(target)
                if parsed.scheme or target.startswith('#'):
                    continue
                path = (doc.parent / unquote(parsed.path)).resolve()
                if not path.is_file():
                    failures.append(f'{doc.name}: {target}')
        self.assertEqual(failures, [])

    def test_active_instructions_use_current_release_and_public_voice(self):
        for doc in DOCS:
            text = doc.read_text(encoding='utf-8')
            with self.subTest(doc=doc.name):
                self.assertIn('beta 69', text)
                self.assertNotRegex(text, r'\b[Bb]eta[ -]6[0-8]\b|\bRC8[0-9]\b')
                self.assertNotIn('WIRING.md', text)
                self.assertNotIn('ASTRA_REPORT.md', text)
                self.assertNotRegex(text, r'Noah (?:must|needs to|should)')

    def test_guides_link_their_own_faq_and_faqs_return_to_the_guide(self):
        for product in ('2k5', 'apf2k8'):
            guide, faq = [ROOT / 'docs/mod_editor' / f'{product}_mod_studio_{kind}.md'
                          for kind in ('getting_started', 'faq')]
            self.assertIn(f'({faq.name})', guide.read_text(encoding='utf-8'))
            self.assertIn(f'({guide.name})', faq.read_text(encoding='utf-8'))

if __name__ == '__main__':
    unittest.main()

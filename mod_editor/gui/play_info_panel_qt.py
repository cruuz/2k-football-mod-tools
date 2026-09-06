"""Read-only, searchable PLAY reference generated from play_rules.json."""
from __future__ import annotations

import html
import json

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QTextBrowser, QVBoxLayout, QWidget

from mod_editor.core import nfl2k5_play_rules as rules
from mod_editor.core.errors import ValidationError


class PlayInfoPanel(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._report_dir = rules.REFERENCE_PATH.parents[2].resolve()
        self.setObjectName('playInfoPanel')
        root = QVBoxLayout(self)
        root.addWidget(QLabel('PLAY reference | EXPERIMENTAL / UNWITNESSED'))
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search rules, opcodes, coverage, spy, packs or limits')
        self.search.setClearButtonEnabled(True)
        root.addWidget(self.search)
        split = QHBoxLayout()
        root.addLayout(split, 1)
        self.topics = QListWidget()
        self.topics.setMaximumWidth(370)
        self.reader = QTextBrowser()
        self.reader.setOpenLinks(False)
        self.reader.setOpenExternalLinks(False)
        self.reader.anchorClicked.connect(self._open_report)
        split.addWidget(self.topics, 1)
        split.addWidget(self.reader, 3)
        self.status = QLabel()
        root.addWidget(self.status)
        self._entries = []
        try:
            data = rules.reference()
            for section in data['sections']:
                paragraphs = ''.join('<p>' + html.escape(p) + '</p>' for p in section['text'])
                links = ''.join(f'<p><a href="{html.escape(p)}">{html.escape(p)}</a></p>'
                                for p in section.get('links', []))
                self._entries.append((section['title'], paragraphs + links))
            for row in data['vocabulary']:
                self._entries.append(('Rule: ' + row['term'], ''.join(
                    '<p>' + html.escape(row[key]) + '</p>'
                    for key in ('encoding', 'evidence', 'meaning', 'consumers'))))
            for row in data['opcodes']:
                params = ''.join('<tr><td>' + html.escape(p['key']) + '</td><td>' +
                    html.escape(p['label']) + '</td><td>' + html.escape(p['kind']) + '</td><td>' +
                    html.escape(', '.join(f'{k}: {v}' for k, v in p['choices'].items())) + '</td></tr>'
                    for p in row['parameters'])
                content = ('<p>' + html.escape(row['meaning']) + '</p>'
                    '<p>Coordinates shown by the decoder are centimetres; 91.44 cm = 1 yard. '
                    'Time values are seconds. Unnamed fields retain their raw labels.</p>'
                    '<table border="1" cellpadding="5"><tr><th>Field</th><th>Meaning</th><th>Unit/type</th><th>Choices</th></tr>' +
                    params + '</table><p>' + html.escape(row['evidence']) + '</p><p>' +
                    html.escape('Callbacks: ' + json.dumps(row['callbacks']) +
                                '; runtime initializer: ' + str(row['runtime_initializer'])) + '</p>')
                self._entries.append((f"0x{row['opcode']:02X}: {row['name']}", content))
        except (OSError, ValueError, ValidationError) as exc:
            self.status.setText(f'PLAY reference could not be loaded: {exc}')
        self.search.textChanged.connect(self._filter)
        self.topics.currentItemChanged.connect(self._show)
        self._filter()

    def _filter(self, *_args):
        query = self.search.text().casefold().split()
        self.topics.clear()
        for index, (title, content) in enumerate(self._entries):
            haystack = (title + ' ' + html.unescape(content)).casefold()
            if all(term in haystack for term in query):
                item = QListWidgetItem(title)
                item.setData(Qt.UserRole, index)
                self.topics.addItem(item)
        if self.topics.count():
            self.topics.setCurrentRow(0)
        else:
            self.reader.setPlainText('No reference topics match this search.')
        if self._entries:
            self.status.setText(f'{self.topics.count()} reference topics. Read only. Links open local report text here.')

    def _show(self, item, _previous):
        if item is not None:
            self._report_dir = rules.REFERENCE_PATH.parents[2].resolve()
            title, content = self._entries[item.data(Qt.UserRole)]
            self.reader.setHtml('<h2>' + html.escape(title) + '</h2>' + content)

    def _open_report(self, url):
        # No browser/process/network launch. Only shipped local reference files.
        root = rules.REFERENCE_PATH.parents[2].resolve()
        if not url.scheme() and not url.path() and url.hasFragment():
            self.reader.scrollToAnchor(url.fragment())
            return
        path = (self._report_dir / url.path()).resolve()
        if (url.scheme() or not path.is_relative_to(root) or
                path.suffix not in ('.md', '.json', '.py')):
            self.status.setText('Only local report links can be opened here.')
            return
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError('The report is larger than the viewer limit.')
            text = path.read_text(encoding='utf-8')
            if path.suffix == '.md':
                self.reader.setMarkdown(text)
            else:
                self.reader.setPlainText(text)
            self._report_dir = path.parent
            if url.hasFragment():
                self.reader.scrollToAnchor(url.fragment())
            self.status.setText(str(path.relative_to(root)))
        except (OSError, ValueError) as exc:
            self.status.setText(f'This report is not available in this installation: {exc}')

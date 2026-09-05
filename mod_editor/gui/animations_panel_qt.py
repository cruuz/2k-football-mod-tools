"""Animations inspection workspace. Import is intentionally disabled pending gates."""
from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtCore import QObject, QPointF, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QSlider, QSplitter,
    QVBoxLayout, QWidget,
)

from mod_editor.core import nfl2k5_animation as animation
from mod_editor.gui.task_delivery import bound


class SkeletonProjection(QWidget):
    """A software-painted 2D projection, including when Qt runs offscreen."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.segments = []
        self.setMinimumSize(280,220)
        self.setAccessibleName('Animation skeleton preview')

    def set_segments(self,segments):
        self.segments = list(segments)
        self.update()

    def paintEvent(self,event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(),QColor('#19232e'))
        if not self.segments:
            painter.setPen(QColor('#dde6ef'))
            painter.drawText(self.rect(),Qt.AlignCenter,'Select an animation to preview its pose')
            return
        points = [p for a,b,_ in self.segments for p in (a,b)]
        lo = [min(p[i] for p in points) for i in (0,1)]
        hi = [max(p[i] for p in points) for i in (0,1)]
        scale = min((self.width()-40)/max(hi[0]-lo[0],1),(self.height()-40)/max(hi[1]-lo[1],1))
        def screen(p):
            return QPointF(self.width()/2+(p[0]-(lo[0]+hi[0])/2)*scale,
                           self.height()/2-(p[1]-(lo[1]+hi[1])/2)*scale)
        painter.setPen(QPen(QColor('#76c9fb'),2))
        for a,b,_ in self.segments:
            painter.drawLine(screen(a),screen(b))
        painter.setBrush(QColor('#f2bd67'))
        painter.setPen(Qt.NoPen)
        for point in points:
            painter.drawEllipse(screen(point),2.5,2.5)


class _Signals(QObject):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)


class _Task(QRunnable):
    def __init__(self,operation):
        super().__init__()
        self.setAutoDelete(False)
        self.signals = _Signals()
        self.operation = operation

    def run(self):
        try:
            self.signals.done.emit(self.operation())
        except Exception as exc:
            self.signals.failed.emit(f'{type(exc).__name__}: {exc}')


class AnimationsPanel(QWidget):
    def __init__(self,facade=None,parent=None):
        super().__init__(parent)
        self._facade = facade
        self._paths = None
        self._source = None
        self._catalog = {'archive':[],'embedded_xbe':[]}
        self._clip = None
        self._skeleton = None
        self._busy = False
        self._generation = 0
        self._task = None
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        layout = QVBoxLayout(self)
        self.badge = QLabel('EXPERIMENTAL / UNWITNESSED')
        layout.addWidget(self.badge)
        intro = QLabel('Inspect and export local animation poses. Import is disabled until the checks and game testing are complete.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        top = QHBoxLayout()
        self.reload_button = QPushButton('Refresh list')
        self.reload_button.clicked.connect(self.reload)
        top.addWidget(self.reload_button)
        self.xbe_field = QLineEdit()
        self.xbe_field.setPlaceholderText('Optional retail executable for the two known embedded clips')
        top.addWidget(self.xbe_field,1)
        xbe_browse = QPushButton('Choose executable')
        xbe_browse.clicked.connect(self._choose_xbe)
        top.addWidget(xbe_browse)
        layout.addLayout(top)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        self.scope_combo = QComboBox()
        self.scope_combo.addItem('Archive animations','archive')
        self.scope_combo.addItem('Known embedded executable clips','embedded_xbe')
        self.scope_combo.currentIndexChanged.connect(self._filter)
        ll.addWidget(self.scope_combo)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search names, family or archive identity')
        self.search.textChanged.connect(self._filter)
        ll.addWidget(self.search)
        self.clip_list = QListWidget()
        self.clip_list.setAccessibleName('Animations')
        self.clip_list.itemSelectionChanged.connect(self._select)
        ll.addWidget(self.clip_list)
        self.count_label = QLabel()
        ll.addWidget(self.count_label)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        self.root_combo = QComboBox()
        self.root_combo.currentIndexChanged.connect(self._root_changed)
        rl.addWidget(self.root_combo)
        self.preview_note = QLabel('Local pose only. Actor movement is not shown.')
        self.preview_note.setWordWrap(True)
        rl.addWidget(self.preview_note)
        self.preview = SkeletonProjection()
        rl.addWidget(self.preview,2)
        self.plane_combo = QComboBox()
        self.plane_combo.addItem('Front','front')
        self.plane_combo.addItem('Side','side')
        self.plane_combo.currentIndexChanged.connect(self._scrub)
        rl.addWidget(self.plane_combo)
        self.scrubber = QSlider(Qt.Horizontal)
        self.scrubber.setAccessibleName('Native animation frame')
        self.scrubber.valueChanged.connect(self._scrub)
        rl.addWidget(self.scrubber)
        self.frame_label = QLabel()
        rl.addWidget(self.frame_label)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        rl.addWidget(self.details,1)
        split.addWidget(right)
        layout.addWidget(split,1)
        export_row = QHBoxLayout()
        self.export_button = QPushButton('Export glTF and native files')
        self.export_button.clicked.connect(self._export)
        export_row.addWidget(self.export_button)
        self.keys_field = QLineEdit()
        self.keys_field.setPlaceholderText('Edited animation.keys.json for a change preview')
        self.keys_field.textChanged.connect(self._refresh)
        export_row.addWidget(self.keys_field,1)
        self.browse_keys_button = QPushButton('Choose edited keys')
        self.browse_keys_button.clicked.connect(self._choose_keys)
        export_row.addWidget(self.browse_keys_button)
        self.check_button = QPushButton('What would change')
        self.check_button.clicked.connect(self.check_changes)
        export_row.addWidget(self.check_button)
        self.import_button = QPushButton('Import disabled')
        self.import_button.setToolTip('Import is unavailable until byte checks and in-game tests pass.')
        export_row.addWidget(self.import_button)
        layout.addLayout(export_row)
        self.status_label = QLabel('Open your NFL 2K5 disc to list animations.')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self._refresh()

    def _source_paths(self):
        return self._paths or getattr(self._facade,'models_source_paths',None)

    def set_source_paths(self,index_path,inventory_path,xbe_path=None):
        self._generation += 1
        self._paths = (Path(index_path),Path(inventory_path))
        self.xbe_field.setText(str(xbe_path) if xbe_path else '')
        self._source = None
        self._catalog = {'archive':[],'embedded_xbe':[]}
        self._filter()
        self._refresh()

    def _refresh(self,*_):
        self.reload_button.setEnabled(bool(self._source_paths()) and not self._busy)
        self.export_button.setEnabled(self._clip is not None and not self._busy)
        self.check_button.setEnabled(self._clip is not None and self._clip.kind == 'SMCD' and
                                     bool(self.keys_field.text().strip()) and not self._busy)
        # No code path connects this button to a writer or enables it.
        self.import_button.setEnabled(False)
        for widget in (self.clip_list,self.search,self.scope_combo,self.root_combo,self.scrubber,self.plane_combo):
            widget.setEnabled(not self._busy)

    def _run(self,operation,done):
        if self._busy:
            return
        generation = self._generation
        task = _Task(operation)
        def finish(result):
            self._busy = False
            if generation == self._generation:
                done(result)
            self._refresh()
        def fail(message):
            self._busy = False
            if generation == self._generation:
                self.status_label.setText(message)
            self._refresh()
        task.signals.done.connect(bound(self,finish))
        task.signals.failed.connect(bound(self,fail))
        self._task = task
        self._busy = True
        self._refresh()
        self._pool.start(task)

    def reload(self):
        paths = self._source_paths()
        if not paths or self._busy:
            return
        self._generation += 1
        self._source = None
        self._catalog = {'archive':[],'embedded_xbe':[]}
        self._filter()
        index,inventory = map(Path,paths)
        xbe = Path(self.xbe_field.text().strip()) if self.xbe_field.text().strip() else None
        self.status_label.setText('Reading animation headers and hashes...')
        def operation():
            source = animation.AnimationSource(index,inventory,xbe)
            return source,source.catalog()
        self._run(operation,lambda result:self.apply_catalog(*result))

    def apply_catalog(self,source,catalog):
        self._source,self._catalog = source,catalog
        self._filter()
        self.status_label.setText('Choose a clip. Embedded clips are a separate, limited list.')
        self._refresh()

    def _filter(self,*_):
        self.clip_list.blockSignals(True)
        self.clip_list.clear()
        query = self.search.text().casefold()
        rows = self._catalog[self.scope_combo.currentData()]
        for row in rows:
            text = f"{row['name']} | {row['identity']} | {row['family']}"
            if query in text.casefold():
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole,row['identity'])
                self.clip_list.addItem(item)
        self.clip_list.blockSignals(False)
        self.count_label.setText(f'{self.clip_list.count():,} of {len(rows):,} resources')
        self._clip = self._skeleton = None
        self.root_combo.clear()
        self.details.clear()
        self.preview.set_segments([])
        self.frame_label.clear()
        self._refresh()

    def select_identity(self,identity):
        for i in range(self.clip_list.count()):
            if self.clip_list.item(i).data(Qt.UserRole) == identity:
                self.clip_list.setCurrentRow(i)
                return True
        return False

    def _select(self):
        item = self.clip_list.currentItem()
        if item is None or self._source is None or self._busy:
            return
        identity,source = item.data(Qt.UserRole),self._source
        self._clip = self._skeleton = None
        self.preview.set_segments([])
        def operation():
            clip = source.load(identity)
            return clip,source.skeleton(clip)
        self._run(operation,lambda result:self.apply_clip(*result))

    def apply_clip(self,clip,skeleton=None):
        self._clip,self._skeleton = clip,skeleton
        self.root_combo.blockSignals(True)
        self.root_combo.clear()
        for r in clip.roots:
            self.root_combo.addItem(f'Clip part {r.index+1} of {len(clip.roots)}',r.index)
        self.root_combo.blockSignals(False)
        self.preview_note.setText('Local skeleton pose only. Actor movement is not shown.' if skeleton else
                                  'Skeleton family is unknown. Lines show separate rotation channels, not body bones.')
        self._root_changed()
        self._refresh()

    def _root_changed(self,*_):
        if self._clip is None or self.root_combo.currentIndex() < 0:
            return
        r = self._clip.roots[self.root_combo.currentIndex()]
        self.scrubber.setRange(0,r.frames-1)
        self.scrubber.setValue(0)
        self.details.setPlainText(describe_clip(self._clip,r.index))
        self._scrub()

    def _scrub(self,*_):
        if self._clip is None or self.root_combo.currentIndex() < 0:
            return
        root_index = self.root_combo.currentIndex()
        r = self._clip.roots[root_index]
        frame = self.scrubber.value()
        seconds = frame/(r.rate*r.multiplier)
        try:
            segments = animation.project_pose(self._clip,seconds,self._skeleton,root_index,
                                               self.plane_combo.currentData(),loop=False)
            self.preview.set_segments(segments)
            self.frame_label.setText(f'Frame {frame+1} / {r.frames} | {seconds:.4f} seconds | native samples')
        except ValueError as exc:
            self.preview.set_segments([])
            self.status_label.setText(str(exc))

    def _choose_xbe(self):
        path,_ = QFileDialog.getOpenFileName(self,'Choose retail executable','','Xbox executable (*.xbe)')
        if path:
            self.xbe_field.setText(path)

    def _choose_keys(self):
        path,_ = QFileDialog.getOpenFileName(self,'Choose edited primary keys','','Animation keys (*.json)')
        if path:
            self.keys_field.setText(path)

    def _export(self):
        if self._clip is None or self._busy:
            return
        folder = QFileDialog.getExistingDirectory(self,'Choose a parent folder for the new export')
        if folder:
            name = self._clip.identity.replace(':','_').replace('/','_')
            self.export_to(Path(folder)/name)

    def export_to(self,destination):
        if self._clip is None:
            return
        clip,skeleton = self._clip,self._skeleton
        self.status_label.setText('Preparing glTF and native files...')
        self._run(lambda:animation.export_clip(clip,Path(destination),skeleton),
                  lambda result:self.status_label.setText(f"Exported glTF and native files to {result['directory']}"))

    def check_changes(self):
        if self._clip is None or self._clip.kind != 'SMCD':
            return
        clip,path = self._clip,Path(self.keys_field.text())
        def operation():
            if path.stat().st_size > 64*1024*1024:
                raise animation.AnimationError('Edited key file exceeds 64 MiB')
            return animation.check_key_document(clip,json.loads(path.read_text(encoding='utf-8'))).receipt
        def done(receipt):
            self.details.setPlainText(change_report(receipt))
            self.status_label.setText('Change preview complete. Nothing was written to your game.')
        self._run(operation,done)

    def wait_idle(self,timeout_ms=30000):
        return bool(self._pool.waitForDone(timeout_ms))

    def closeEvent(self,event):  # noqa: N802
        self.wait_idle()
        super().closeEvent(event)


def describe_clip(clip,root_index=0):
    r = clip.roots[root_index]
    lines = [clip.name,clip.identity,f'Family: {clip.family}',f'Namespace: {clip.namespace or "unresolved"}',
             f'Bones: {25 if clip.map_id else "unresolved"} | Stored channels: {r.channels}',
             f'Native frames: {r.frames} | Rate: {r.rate} Hz | Time multiplier: {r.multiplier:g}',
             f'Controller duration: {r.duration:.9f} seconds',
             f'Loop: {bool(r.flags&1)} | Mirror: {bool(r.flags&4)} | Original flags: {r.flags:#x}',
             f'Events: {len(r.events)} | Movement samples: {r.frames} | Record bytes: {r.stride}',
             f'Auxiliary records: {r.frames if r.auxiliary is not None else 0}',
             f'Native SHA-256: {animation.sha256(clip.original)}',
             '', 'Events (all retained, including those after the clip ends):']
    lines += [f'  Event {i}: {seconds:.6f} seconds, ticks {ticks}' for i,ticks,seconds in r.events]
    lines += ['',*animation.ASSUMPTIONS]
    return '\n'.join(lines)


def change_report(receipt):
    changes = receipt['changed_keys']
    lines = ['EXPERIMENTAL / UNWITNESSED',f"{len(changes)} changed keys; {receipt['changed_bytes']} changed bytes.",
             'Events, movement samples, clip length and root settings are retained.',
             'Nothing was written to your game. Import remains disabled.','']
    lines += [f"Frame {c['frame']+1}, channel {c['packed_channel']}, joint {c['logical_joint']}: "
              f"native offset {c['offset']:#x}, word {c['before_word']:08x} -> {c['after_word']:08x}" for c in changes]
    lines += ['', 'Exact byte ranges:',json.dumps(receipt['write_spans'],indent=2),
              'Archive byte ranges:',json.dumps(receipt['archive_write_spans'],indent=2)]
    return '\n'.join(lines)

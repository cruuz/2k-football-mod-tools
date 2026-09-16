"""Asynchronous native sprite preview over a selected game screenshot."""
from pathlib import Path
import json
import sys
import tempfile
from PyQt5.QtCore import QProcess, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QCheckBox,QComboBox,QDialog,QFileDialog,QFormLayout,QHBoxLayout,
                            QLabel,QLineEdit,QPushButton,QScrollArea,QSpinBox,QVBoxLayout,QWidget)
from mod_editor.core.nfl2k5_scorebug_sprite import DEFAULT_FOLDER,STANDARD_STATE
from mod_editor.core.nfl2k5_scorebug_resources import TEAM_LOGOS

class SpritePreviewDialog(QDialog):
    design_chosen = pyqtSignal(str)
    def __init__(self,parent=None,source=None):
        super().__init__(parent)
        self.setWindowTitle('Sprite scorebug preview');self.resize(980,760)
        self.temporary=tempfile.TemporaryDirectory(prefix='scorebug-preview-')
        self.process=QProcess(self);self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.finished.connect(self._finished);self.process.errorOccurred.connect(self._error)
        root=QVBoxLayout(self);form=QFormLayout();root.addLayout(form)
        self.source=QLineEdit(str(source or ''));self.screenshot=QLineEdit();self.folder=QLineEdit(str(DEFAULT_FOLDER))
        for title,edit,kind in (('Game source',self.source,'game'),('Screenshot',self.screenshot,'image'),('Design folder',self.folder,'folder')):
            edit.setAccessibleName(title);row=QHBoxLayout();row.addWidget(edit)
            button=QPushButton('Choose…');button.setAccessibleName('Choose '+title.lower())
            button.clicked.connect(lambda _checked=False,e=edit,k=kind:self._choose(e,k));row.addWidget(button);form.addRow(title,row)
        self.state={}
        teams=QHBoxLayout()
        for key in ('away','home','possession'):
            combo=QComboBox();combo.setAccessibleName(key.title())
            combo.addItems(sorted(TEAM_LOGOS) if key!='possession' else ['home','away']);combo.setCurrentText(STANDARD_STATE[key]);self.state[key]=combo
            teams.addWidget(QLabel(key.title()));teams.addWidget(combo)
        form.addRow('Teams',teams)
        numbers=QHBoxLayout()
        for key,title,low,high in (('away_score','Away score',0,999),('home_score','Home score',0,999),('away_timeouts','Away timeouts',0,3),('home_timeouts','Home timeouts',0,3),('down','Down',1,4),('distance','Distance',0,99),('play_clock','Play clock',0,99)):
            spin=QSpinBox();spin.setAccessibleName(title);spin.setRange(low,high);spin.setValue(STANDARD_STATE[key]);self.state[key]=spin
            column=QVBoxLayout();column.addWidget(QLabel(title));column.addWidget(spin);numbers.addLayout(column)
        form.addRow('Situation',numbers)
        self.goal=QCheckBox('Goal to go');self.goal.setAccessibleName('Goal to go');form.addRow('',self.goal)
        clockrow=QHBoxLayout();self.clock=QLineEdit('4:33');self.clock.setAccessibleName('Game clock minutes and seconds');clockrow.addWidget(self.clock)
        self.quarter=QComboBox();self.quarter.setAccessibleName('Quarter');self.quarter.addItems(['1st','2nd','3rd','4th','OT']);self.quarter.setCurrentIndex(1);clockrow.addWidget(self.quarter)
        self.aspect=QComboBox();self.aspect.setAccessibleName('Preview aspect ratio');self.aspect.addItems(['4:3','16:9']);clockrow.addWidget(self.aspect)
        self.event=QComboBox();self.event.setAccessibleName('Retail event');self.event.addItems(['standard','FLAG','FUMBLE','hang time','ball on','score slabs','hidden play clock']);clockrow.addWidget(self.event)
        form.addRow('Clock and display',clockrow)
        self.preview_button=QPushButton('Preview');self.preview_button.setAccessibleName('Render sprite scorebug preview');self.preview_button.clicked.connect(self.preview);root.addWidget(self.preview_button)
        use=QPushButton('Use design in Build');use.setAccessibleName('Use sprite design in Build');use.clicked.connect(self._use_design);root.addWidget(use)
        self.status=QLabel('Choose a screenshot and your game source, then Preview. The design uses the sprite scorebug option.');self.status.setWordWrap(True);root.addWidget(self.status)
        self.picture=QLabel();self.picture.setAlignment(Qt.AlignCenter);self.picture.setAccessibleName('Native sprite scorebug over the screenshot')
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setWidget(self.picture);root.addWidget(self.scroll,1)
        note=QLabel('Experimental scorebug. The preview shows the compiled design; appearance in a played game still needs verification.');note.setWordWrap(True);root.addWidget(note)

    def _use_design(self):
        try:
            from mod_editor.core.nfl2k5_scorebug_sprite import compile_folder
            compile_folder(self.folder.text())
        except (OSError,ValueError) as exc:self.status.setText(str(exc));return
        except (KeyError,TypeError,AttributeError):
            self.status.setText('Invalid sprite design. Check the required fields in layout.json against the supplied template.');return
        self.design_chosen.emit(self.folder.text());self.status.setText('Sprite design handed to Build with the sprite scorebug option enabled.')

    def _choose(self,edit,kind):
        if kind=='folder':path=QFileDialog.getExistingDirectory(self,'Choose sprite design folder',edit.text())
        else:path,_=QFileDialog.getOpenFileName(self,'Choose screenshot' if kind=='image' else 'Choose game source',edit.text(),'Images (*.png *.jpg *.jpeg)' if kind=='image' else 'Xbox disc image (*.iso);;Extracted pack 0 (0)')
        if path:edit.setText(path)

    def preview(self):
        try:
            source=Path(self.source.text());shot=Path(self.screenshot.text())
            if not source.is_file() or not shot.is_file():raise ValueError('Choose an existing game source and screenshot.')
            minute,second=map(int,self.clock.text().split(':'))
            if not 0<=second<60:raise ValueError('Use minutes:seconds for the clock, such as 4:33.')
            state={k:w.currentText() if isinstance(w,QComboBox) else w.value() for k,w in self.state.items()}
            state.update(clock=minute*60+second,quarter=self.quarter.currentIndex()+1,event=self.event.currentText(),goal_to_go=self.goal.isChecked())
            from mod_editor.core.nfl2k5_scorebug_sprite import normalize_state
            normalize_state(state)
        except (ValueError,OSError) as exc:self.status.setText(str(exc));return
        self.output=Path(self.temporary.name)/'preview.png'
        args=['-m','mod_editor.core.nfl2k5_scorebug_sprite','preview','--screenshot',str(shot),'--state',json.dumps(state),'--aspect',self.aspect.currentText(),'--folder',self.folder.text(),'--output',str(self.output)]
        args+=['--pack' if source.name=='0' else '--source',str(source)]
        self.preview_button.setEnabled(False);self.status.setText('Rendering the selected game state…');self.process.start(sys.executable,args)

    def _finished(self,code,status):
        self.preview_button.setEnabled(True);message=bytes(self.process.readAllStandardOutput()).decode('utf-8','replace')
        if code or status!=QProcess.NormalExit:
            if 'unicorn' in message:self.status.setText('Native preview support is missing from this installation. Install the native preview dependencies listed in the sprite scorebug guide, then try again.')
            else:self.status.setText('Preview failed: '+(message.strip().splitlines()[-1] if message.strip() else 'Check the selected game source and design folder.'))
            return
        pixmap=QPixmap(str(self.output));self.picture.setPixmap(pixmap.scaledToWidth(960,Qt.SmoothTransformation));self.status.setText('Preview ready. Scores, labels and ticks use the compiled sprite quads.')
        QTimer.singleShot(0,self._show_bar)

    def _show_bar(self):
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())
        horizontal=self.scroll.horizontalScrollBar();horizontal.setValue(horizontal.maximum()//2)

    def _error(self,_error):
        self.preview_button.setEnabled(True);self.status.setText('The preview process could not start. Check this installation’s Python runtime and try again.')

    def closeEvent(self,event):
        if self.process.state()!=QProcess.NotRunning:
            self.process.kill();self.process.waitForFinished(1000)
        self.temporary.cleanup();super().closeEvent(event)

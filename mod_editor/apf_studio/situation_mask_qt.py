"""Live-bucket exclusions and the stored personnel rows they consult."""
from __future__ import annotations
import json
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox,QComboBox,QFileDialog,QFormLayout,QGroupBox,
    QHBoxLayout,QLabel,QMessageBox,QPushButton,QSpinBox,QTableWidget,QTableWidgetItem,QVBoxLayout)
from mod_editor.core.apf2k8_situation_mask import KEY_LABELS
from mod_editor.core.errors import ValidationError


class SituationMaskPanel(QGroupBox):
    def __init__(self, owner):
        super().__init__('Live situations: exclusions and requested personnel')
        self.owner, self.context, self.loading = owner, None, False
        root=QVBoxLayout(self)
        self.enabled=QCheckBox('Enable per-book situation exclusions (experimental)')
        self.enabled.setToolTip('Off by default. Save these choices with the project, then install the matching situation patch. No preset enables this control.')
        root.addWidget(self.enabled)
        label=QLabel('Each bucket uses actual down and distance. Clock, score and field position can change the native personnel request within a bucket. '
                     'These exclusions apply only to ordinary CPU offense calls. If exclusions empty a draw, the game uses its original draw and records the fallback. '
                     'Exported builds include BASE and TU 1.1 patches; install the matching patch to enable them in game. '
                     'Undo or disabling this project option does not remove an installed patch. Remove it or install an empty mask, then restart the game.')
        label.setWordWrap(True);root.addWidget(label)
        self.bucket=QComboBox();self.bucket.addItems(KEY_LABELS);root.addWidget(self.bucket)
        self.request=QLabel();self.request.setWordWrap(True);root.addWidget(self.request)
        self.candidates=QTableWidget(0,4)
        self.candidates.setHorizontalHeaderLabels(('Formation','Candidacy at sample state','Personnel / requested TEs','Exclude here'))
        self.candidates.setAccessibleName('Per-situation formation exclusion checkboxes')
        root.addWidget(self.candidates)
        label=QLabel('Requested row is computed by the game and is read-only. The stored comparison row below is editable in MASTER and affects that personnel category in every book and situation. '
                     'Requested TEs are roles, not guaranteed players: an empty TE depth list substitutes an FB.')
        label.setWordWrap(True);root.addWidget(label)
        self.personnel=QComboBox();self.stored_row=QSpinBox();self.stored_row.setRange(0,27)
        self.stored_row.setAccessibleName('Stored personnel comparison row for every book')
        form=QFormLayout();form.addRow('Personnel category',self.personnel);form.addRow('Stored comparison row (all books)',self.stored_row);root.addLayout(form)
        self.roles=QLabel();self.roles.setWordWrap(True);root.addWidget(self.roles)
        self.write_row=QPushButton('Stage stored personnel row for all books')
        self.write_row.clicked.connect(self.stage_row);root.addWidget(self.write_row)
        actions=QHBoxLayout();self.preview=QPushButton('Preview this live situation')
        self.preview.clicked.connect(self.preview_bucket);actions.addWidget(self.preview)
        self.profile=QComboBox();self.profile.addItem('BASE','base');self.profile.addItem('TU 1.1','tu_1_1');actions.addWidget(self.profile)
        self.export=QPushButton('Export situation patch…');self.export.clicked.connect(self.export_patch);actions.addWidget(self.export)
        self.install=QPushButton('Review and install situation patch…');self.install.clicked.connect(self.install_patch);actions.addWidget(self.install)
        root.addLayout(actions)
        self.status=QLabel('Situation patch has not been checked. Gameplay UNWITNESSED.');self.status.setWordWrap(True);root.addWidget(self.status)
        actions=QHBoxLayout()
        self.check=QPushButton('Check installed situation patch');self.check.clicked.connect(self.check_patch);actions.addWidget(self.check)
        self.remove=QPushButton('Remove installed situation patch');self.remove.clicked.connect(self.remove_patch);actions.addWidget(self.remove)
        root.addLayout(actions)
        self.enabled.toggled.connect(self.toggle_enabled)
        self.bucket.currentIndexChanged.connect(self.render)
        self.personnel.currentIndexChanged.connect(self.render_personnel)
        explanations = {
            self.enabled: 'Off by default. Stage the switch explicitly, then install the exported patch for your executable version.',
            self.bucket: 'Choose one of twelve actual down and distance buckets. Exclusions in other buckets stay independent.',
            self.personnel: 'Inspect the stored personnel category used by the native weighted draw. This definition is shared by every book.',
            self.stored_row: 'Edit the stored comparison row for this personnel category in every book. The game-computed requested row remains read-only.',
            self.write_row: 'Stage this shared MASTER personnel-row edit with a receipt. Undo and project save apply to it.',
            self.preview: 'Set the existing custom call preview to the representative down and distance of this bucket, then recalculate it.',
            self.profile: 'Choose the executable profile you launch. The patch carries the exact BASE or TU 1.1 module identity.',
            self.export: 'Export this project’s enabled masks as an authored patch plus its receipt. This action does not install it.',
            self.install: 'Review the destination and explicitly consent to installing this project’s patch and enabling Xenia patches.',
            self.check: 'Read and validate the installed situation patch and the selected Xenia configuration.',
            self.remove: 'Remove the canonical installed situation patch. Restart Xenia to return to the original draws.',
        }
        for control, text in explanations.items():
            control.setToolTip(text); control.setAccessibleDescription(text)
        self.setEnabled(False)

    def set_context(self,context,side):
        self.context=context
        self.setEnabled(side=='offense' and context is not None and not self.owner._loading)
        self.loading=True
        self.enabled.setChecked(context['state'].situation_masks_enabled)
        selected=self.personnel.currentData();self.personnel.clear()
        for c in context['categories']:
            if c.row<=10:self.personnel.addItem(c.name,c.id)
        if selected is not None:self.personnel.setCurrentIndex(max(0,self.personnel.findData(selected)))
        self.loading=False
        self.render();self.render_personnel()

    def sample(self):
        from .playcalling_editor_qt import situation
        key=max(0,self.bucket.currentIndex())
        return situation(key//3+1,(1,5,10)[key%3])

    def render(self,*_):
        if self.loading or not self.context:return
        model=self.owner.facade._playcalling.backend.model
        state=self.context['state'];book=self.context['book'];values=self.sample();s=model.Situation(**values)
        row=model.requested_offense_row(s)
        low=model.requested_offense_row(s,0);high=model.requested_offense_row(s,1)
        self.request.setText(f'Sample: down {s.down}, {s.distance_yards:g} yards, midfield, neutral clock/score. '
                             f'Computed requested row: {row}; RNG range here: {low}–{high}. '
                             'Urgency and overtime field position can change it further. Use Preview for this sample.')
        candidates=model.situation_candidates(state.books[book],state.master,s)
        masks=state.situation_masks.get(book,[[] for _ in range(12)])[self.bucket.currentIndex()]
        forms=[f for f in self.context['formations'] if f['id']<151]
        self.candidates.setRowCount(len(forms))
        for i,f in enumerate(forms):
            pairs=[c for c in candidates if c['formation']==f['id']]
            text='Candidate' if pairs else 'No ordinary candidate at this sample'
            if f['id'] in masks:text+='; excluded when patch is enabled'
            personnel=', '.join(dict.fromkeys(f"{c['personnel']} ({c['tight_ends']} TE)" for c in pairs)) or '—'
            for col,value in enumerate((f['name'],text,personnel)):
                item=QTableWidgetItem(value);item.setFlags(item.flags()&~Qt.ItemIsEditable);self.candidates.setItem(i,col,item)
            check=QCheckBox();check.setChecked(f['id'] in masks)
            check.setAccessibleName(f"Exclude {f['name']} in {self.bucket.currentText()}")
            check.setToolTip("Exclude this formation only in the selected live bucket; an empty draw falls back to the original candidates.")
            check.setAccessibleDescription(check.toolTip())
            check.setEnabled(state.situation_masks_enabled)
            check.toggled.connect(lambda value,formation=f['id']:self.exclude(formation,value))
            self.candidates.setCellWidget(i,3,check)
        self.candidates.resizeColumnsToContents()

    def render_personnel(self,*_):
        if self.loading or not self.context:return
        c=next((c for c in self.context['categories'] if c.id==self.personnel.currentData()),None)
        if c:
            self.stored_row.setValue(c.row)
            self.roles.setText('Requested slots: '+', '.join(c.roles)+'. Empty TE depth list: FB fallback.')

    def toggle_enabled(self,value):
        if not self.loading and self.context:
            self.owner.review_request({'kind':'situation_masks_enabled','enabled':value})

    def exclude(self,formation,value):
        if not self.loading and self.context:
            self.owner.review_request({'kind':'situation_mask','book':self.context['book'],
                                       'key':self.bucket.currentIndex(),'formation':formation,'exclude':value})

    def stage_row(self):
        if self.context and self.personnel.currentData() is not None:
            self.owner.review_request({'kind':'master_row','category':self.personnel.currentData(),'row':self.stored_row.value()})

    def preview_bucket(self):
        values=self.sample()
        for name,widget in self.owner.custom.items():
            if name in values:widget.setValue(values[name])
        self.owner.refresh()

    def export_patch(self):
        profile=self.profile.currentData()
        def done(prepared):
            filename,_=QFileDialog.getSaveFileName(self,'Export situation patch',f'situations-{profile}.patch.toml','Xenia patches (*.patch.toml)')
            if not filename:return
            try:
                from .launcher import _atomic_bytes
                from mod_editor.core.apf2k8_situation_mask import canonical_payload
                path=Path(filename)
                if not path.name.endswith('.patch.toml'):raise ValueError('Choose a .patch.toml filename')
                _atomic_bytes(path,prepared['payload']);canonical_payload(path.read_bytes())
                _atomic_bytes(path.with_suffix('.receipt.json'),(json.dumps(prepared['receipt'],indent=2)+'\n').encode())
                self.status.setText(f'Exported {path.name}. Install it for {profile}; gameplay UNWITNESSED.')
            except (OSError,ValueError,ValidationError) as exc:self.status.setText(f'Could not export situation patch: {exc}')
        self.owner._task('Prepare situation patch',lambda p:self.owner.facade.prepare_situation_patch(profile),done)

    def install_patch(self):
        def done(prepared):
            if 'patch_path' not in prepared:
                self.status.setText(prepared['message']);return
            answer=QMessageBox.question(self,'Install situation exclusions',
                f"Install the reviewed {prepared['profile']} patch at:\n{prepared['patch_path']}\n\n"
                f"Enable patches in:\n{prepared['config_path']}\n\n"
                'This also activates other enabled patches in that folder. Restart Xenia after installation. Gameplay is UNWITNESSED.',
                QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
            if answer==QMessageBox.Yes:
                self.owner._task('Install situation exclusions',lambda p:self.owner.facade.install_situation_patch(prepared,consent=True),
                                 lambda r:self.status.setText(r['message']),True)
        self.owner._task('Review situation patch',lambda p:self.owner.facade.prepare_situation_patch(self.profile.currentData()),done)

    def check_patch(self):
        self.owner._task('Check situation patch',lambda p:self.owner.facade.launcher.pass_fetch_status(kind='situations'),lambda r:self.status.setText(r['message']))

    def remove_patch(self):
        self.owner._task('Remove situation patch',lambda p:self.owner.facade.launcher.remove_pass_fetch_patch(kind='situations'),lambda r:self.status.setText(r['message']),True)

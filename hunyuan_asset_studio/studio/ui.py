import json
import os
import sys
import time
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets
from .core import CATEGORIES, CONFIG_PATH, atomic_json, export_mesh, hardware, import_to_game, initialize, load_settings, model_dir, validate_image
from .viewport import Viewport

STYLE = '''
QWidget { background:#181c22; color:#dce2e8; font-family: Segoe UI; font-size: 12px; }
QMainWindow, QDialog { background:#14181e; }
QFrame#panel { background:#1d2229; border:1px solid #303741; border-radius:6px; }
QLabel#title { color:#f4f7f9; font-size:18px; font-weight:700; }
QLabel#section { color:#98a6b5; font-size:11px; font-weight:700; }
QLabel#muted { color:#8d9aaa; }
QPushButton { background:#292f38; border:1px solid #3a434e; border-radius:4px; padding:8px 12px; }
QPushButton:hover { background:#343d48; } QPushButton:disabled { color:#68727c; }
QPushButton#primary { background:#b4e177; color:#132015; border:0; font-weight:700; }
QLineEdit, QTextEdit, QSpinBox, QComboBox { background:#15191f; border:1px solid #39414c; border-radius:4px; padding:6px; selection-background-color:#60834b; }
QListWidget, QPlainTextEdit { background:#15191f; border:1px solid #303741; border-radius:4px; }
QProgressBar { background:#15191f; border:1px solid #39414c; border-radius:3px; text-align:center; }
QProgressBar::chunk { background:#a6d574; }
'''


class ImageDrop(QtWidgets.QLabel):
    dropped = QtCore.Signal(str)
    def __init__(self):
        super().__init__('DROP REFERENCE IMAGE\n\nPNG, JPG or WebP')
        self.setAlignment(QtCore.Qt.AlignCenter); self.setAcceptDrops(True)
        self.setMinimumHeight(180); self.setWordWrap(True)
        self.setStyleSheet('background:#15191f; border:1px dashed #48535f; color:#95a5b4; border-radius:5px;')
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls and urls[0].isLocalFile(): self.dropped.emit(urls[0].toLocalFile())


def button(text, slot, primary=False):
    b = QtWidgets.QPushButton(text); b.clicked.connect(slot)
    if primary: b.setObjectName('primary')
    return b


def section(text):
    label = QtWidgets.QLabel(text); label.setObjectName('section'); return label


def panel():
    f = QtWidgets.QFrame(); f.setObjectName('panel'); layout = QtWidgets.QVBoxLayout(f); layout.setContentsMargins(15,15,15,15); layout.setSpacing(10); return f, layout


class Studio(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings(); self.root = initialize(self.settings['storage'])
        self.image_path = None; self.current_model = None; self.process = None; self.buffer = ''; self.job_done = False; self.started = None
        self.setWindowTitle('Hunyuan Asset Studio'); self.resize(1440, 900); self.setMinimumSize(1000, 700)
        self.build(); self.refresh_library()
        self.timer = QtCore.QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(1000)
        self.log('Ready. Shape-only generation; no textures or rigging. Use Model Manager to set up weights.')
        if not CONFIG_PATH.exists():
            atomic_json(CONFIG_PATH, self.settings)
            QtCore.QTimer.singleShot(150, self.show_manager)

    def build(self):
        base = QtWidgets.QWidget(); self.setCentralWidget(base); main = QtWidgets.QVBoxLayout(base); main.setContentsMargins(18,14,18,14)
        header = QtWidgets.QHBoxLayout(); title = QtWidgets.QLabel('HUNYUAN  /  ASSET STUDIO'); title.setObjectName('title'); header.addWidget(title)
        sub = QtWidgets.QLabel('IMAGE TO 3D  •  LOCAL WORKSPACE'); sub.setObjectName('muted'); header.addWidget(sub); header.addStretch()
        header.addWidget(button('Model manager', self.show_manager)); header.addWidget(button('Storage settings', self.storage_settings)); main.addLayout(header)
        splitter = QtWidgets.QSplitter(); main.addWidget(splitter, 1)
        left, l = panel(); splitter.addWidget(left); l.addWidget(section('01   REFERENCE IMAGE'))
        self.preview = ImageDrop(); self.preview.dropped.connect(self.set_image); l.addWidget(self.preview)
        row = QtWidgets.QHBoxLayout(); row.addWidget(button('Import / replace', self.choose_image)); row.addWidget(button('Remove', self.remove_image)); l.addLayout(row)
        self.image_info = QtWidgets.QLabel('No image selected'); self.image_info.setWordWrap(True); self.image_info.setObjectName('muted'); l.addWidget(self.image_info)
        l.addWidget(section('ASSET NOTES  ·  NOT A PROMPT')); self.notes = QtWidgets.QTextEdit(); self.notes.setPlaceholderText('Describe the intended asset for your records…'); self.notes.setMaximumHeight(100); l.addWidget(self.notes)
        l.addWidget(section('ASSET LIBRARY')); self.library = QtWidgets.QListWidget(); self.library.itemDoubleClicked.connect(self.open_library); l.addWidget(self.library, 1)
        row = QtWidgets.QHBoxLayout(); row.addWidget(button('Open', self.open_library)); row.addWidget(button('Refresh', self.refresh_library)); l.addLayout(row)
        l.addWidget(button('Use reference & settings', self.restore_generation))
        center, c = panel(); splitter.addWidget(center)
        head = QtWidgets.QHBoxLayout(); head.addWidget(section('02   3D VIEWPORT')); head.addStretch(); head.addWidget(button('Reset camera', self.reset_camera)); self.wire_btn = button('Wireframe', self.toggle_wire); head.addWidget(self.wire_btn); c.addLayout(head)
        self.viewport = Viewport(); c.addWidget(self.viewport, 1)
        hint = QtWidgets.QLabel('Left drag orbit  ·  Middle drag pan  ·  Wheel zoom  |  Display centered and scaled; exported geometry is unchanged.'); hint.setObjectName('muted'); hint.setWordWrap(True); c.addWidget(hint)
        self.mesh_info = QtWidgets.QLabel('No generated model loaded'); self.mesh_info.setWordWrap(True); c.addWidget(self.mesh_info)
        row = QtWidgets.QHBoxLayout(); row.addWidget(button('Export GLB / OBJ', self.export)); row.addWidget(button('Import to game…', self.game_import)); c.addLayout(row)
        right, r = panel(); splitter.addWidget(right); r.addWidget(section('03   GENERATION SETTINGS'))
        label = QtWidgets.QLabel('Hunyuan3D-2mini  /  shape only'); label.setWordWrap(True); r.addWidget(label)
        form = QtWidgets.QFormLayout()
        self.category = QtWidgets.QComboBox(); self.category.addItems(CATEGORIES); form.addRow('Category', self.category)
        self.steps = QtWidgets.QSpinBox(); self.steps.setRange(1, 100); self.steps.setValue(30); form.addRow('Inference steps', self.steps)
        self.resolution = QtWidgets.QSpinBox(); self.resolution.setRange(64, 512); self.resolution.setValue(380); form.addRow('Octree resolution', self.resolution)
        self.chunks = QtWidgets.QSpinBox(); self.chunks.setRange(1000, 200000); self.chunks.setSingleStep(1000); self.chunks.setValue(20000); form.addRow('Decode chunk size', self.chunks)
        self.seed = QtWidgets.QSpinBox(); self.seed.setRange(0, 2147483647); self.seed.setValue(12345); form.addRow('Seed', self.seed); r.addLayout(form)
        warn = QtWidgets.QLabel('6 GB GPU: experimental, not guaranteed to fit. Close other GPU apps. Defaults follow Tencent’s example. Lower resolution / chunks may reduce memory but are unverified. No CPU offload is enabled.'); warn.setWordWrap(True); warn.setStyleSheet('color:#dcb57b;'); r.addWidget(warn)
        self.generate_btn = button('GENERATE 3D', self.generate, True); r.addWidget(self.generate_btn); self.cancel_btn = button('Cancel current task', self.cancel); self.cancel_btn.setEnabled(False); r.addWidget(self.cancel_btn); r.addStretch()
        splitter.setSizes([300, 760, 300])
        bottom, b = panel(); main.addWidget(bottom)
        row = QtWidgets.QHBoxLayout(); row.addWidget(section('04   TASK STATUS')); self.status = QtWidgets.QLabel('Idle'); row.addWidget(self.status, 1); self.elapsed = QtWidgets.QLabel('00:00'); row.addWidget(self.elapsed); b.addLayout(row)
        self.progress = QtWidgets.QProgressBar(); self.progress.setRange(0,1); self.progress.setValue(0); self.progress.setFormat('Idle'); b.addWidget(self.progress)
        self.logs = QtWidgets.QPlainTextEdit(); self.logs.setReadOnly(True); self.logs.setMaximumBlockCount(2000); self.logs.setMaximumHeight(105); b.addWidget(self.logs)

    def log(self, text):
        self.logs.appendPlainText(str(text))
        try:
            with open(self.root / 'Logs' / 'studio.log', 'a', encoding='utf8') as f: f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {text}\n')
        except OSError: pass

    def error(self, text):
        self.log('ERROR: ' + str(text)); QtWidgets.QMessageBox.critical(self, 'Hunyuan Asset Studio', str(text))

    def choose_image(self):
        name, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Choose reference image', '', 'Images (*.png *.jpg *.jpeg *.webp)')
        if name: self.set_image(name)

    def set_image(self, path):
        try:
            image = validate_image(path); pix = QtGui.QPixmap(path)
            if pix.isNull(): raise ValueError('Could not display image.')
            self.image_path = str(Path(path).resolve()); self.preview.setPixmap(pix.scaled(260, 180, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
            self.image_info.setText(f'{Path(path).name}\n{image.width} × {image.height} px  ·  {Path(path).stat().st_size / 1024:.0f} KB')
        except Exception as e: self.error(e)

    def remove_image(self):
        self.image_path = None; self.preview.clear(); self.preview.setText('DROP REFERENCE IMAGE\n\nPNG, JPG or WebP'); self.image_info.setText('No image selected')

    def refresh_library(self):
        self.library.clear()
        for category in CATEGORIES:
            for path in sorted((self.root / 'Generated' / category).glob('*/model.glb'), reverse=True):
                item = QtWidgets.QListWidgetItem(f'{category}  /  {path.parent.name}'); item.setData(QtCore.Qt.UserRole, str(path)); self.library.addItem(item)

    def open_library(self, *_):
        item = self.library.currentItem()
        if item: self.display_model(item.data(QtCore.Qt.UserRole))

    def restore_generation(self):
        item = self.library.currentItem()
        if not item: return self.error('Select a generation first.')
        folder = Path(item.data(QtCore.Qt.UserRole)).parent
        try:
            with open(folder / 'metadata.json', encoding='utf-8') as f: meta = json.load(f)
            self.set_image(str(folder / 'reference.png'))
            self.notes.setPlainText(meta.get('notes', ''))
            self.category.setCurrentText(meta['category'])
            params = meta['parameters']
            self.steps.setValue(params['steps']); self.resolution.setValue(params['resolution']); self.chunks.setValue(params['chunks']); self.seed.setValue(params['seed'])
            self.log('Reference and recorded settings restored. Generate to create a separate asset.')
        except Exception as e: self.error(e)

    def display_model(self, path):
        try:
            mesh = self.viewport.show_mesh(path); self.current_model = str(path)
            dim = ' × '.join(f'{n:.3f}' for n in mesh.extents)
            self.mesh_info.setText(f'{Path(path).parent.name}   |   {len(mesh.vertices):,} vertices  ·  {len(mesh.faces):,} triangles\nDimensions: {dim}  ·  {Path(path).stat().st_size / 1024:.0f} KB  ·  shape only')
        except Exception as e: self.error(e)

    def reset_camera(self): self.viewport.reset_camera()
    def toggle_wire(self): self.viewport.wire = not self.viewport.wire; self.viewport.redraw(); self.wire_btn.setText('Solid' if self.viewport.wire else 'Wireframe')

    def export(self):
        if not self.current_model: return self.error('Open or generate a mesh first.')
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Export geometry', '', 'GLB (*.glb);;OBJ (*.obj)')
        if not path: return
        try: export_mesh(self.current_model, path); QtWidgets.QMessageBox.information(self, 'Export complete', f'Validated export saved to:\n{path}')
        except Exception as e: self.error(e)

    def game_import(self):
        if not self.current_model: return self.error('Open or generate a mesh first.')
        dest = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select destination in your game project', self.settings['game_directory'])
        if not dest: return
        try:
            result = import_to_game(self.current_model, dest); self.settings['game_directory'] = dest; atomic_json(CONFIG_PATH, self.settings)
            QtWidgets.QMessageBox.information(self, 'Imported', f'Copied without modifying the original:\n{result}')
        except Exception as e: self.error(e)

    def storage_settings(self):
        if self.process: return self.error('Wait for the current task first.')
        dest = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select studio data directory', str(self.root))
        if dest:
            try:
                self.root = initialize(dest); self.settings['storage'] = str(self.root); atomic_json(CONFIG_PATH, self.settings); self.refresh_library(); self.log(f'Storage changed to {self.root}; existing files were not moved.')
            except Exception as e: self.error(e)

    def show_manager(self):
        try: report = hardware(self.root)
        except Exception as e: return self.error(e)
        msg = '\n'.join(f'{k}: {v}' for k,v in report.items())
        folder = model_dir(self.root)
        present = (folder / 'config.yaml').is_file() and (folder / 'model.fp16.safetensors').is_file()
        msg += f'\n\nStorage: {self.root}\nModel folder: {folder}\nFiles: {"present (not yet verified)" if present else "missing / incomplete"}\n\nOnly the mini config and fp16 safetensors (~3.82 GB) are downloaded. SHA-256 verification can take several minutes. Loading/inference require a CUDA GPU. Windows setup and 6 GB inference are not yet validated.'
        dialog = QtWidgets.QMessageBox(self); dialog.setWindowTitle('Setup & model manager'); dialog.setText(msg)
        download = dialog.addButton('Download / resume', QtWidgets.QMessageBox.ActionRole); verify = dialog.addButton('Verify files', QtWidgets.QMessageBox.ActionRole); dialog.addButton('Close', QtWidgets.QMessageBox.RejectRole); dialog.exec()
        if dialog.clickedButton() == download: self.start_job('download')
        elif dialog.clickedButton() == verify: self.start_job('verify')

    def generate(self):
        if not self.image_path: return self.error('Import a reference image first.')
        try: validate_image(self.image_path)
        except Exception as e: return self.error(e)
        try: gpu = hardware(self.root)['GPU']
        except Exception as e: return self.error(f'Hardware check failed: {e}')
        if gpu == 'Unavailable': return self.error('CUDA GPU is unavailable to PyTorch. Check the NVIDIA driver and CUDA PyTorch installation in Model Manager.')
        warning = f'{gpu}\n\nThe official pipeline will load on CUDA without CPU offloading. A 6 GB GPU may run out of memory; actual requirements depend on settings and free VRAM. Continue?'
        if QtWidgets.QMessageBox.warning(self, 'GPU memory warning', warning, QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No) != QtWidgets.QMessageBox.Yes: return
        data = {'image':self.image_path, 'category':self.category.currentText(), 'steps':self.steps.value(), 'resolution':self.resolution.value(), 'chunks':self.chunks.value(), 'seed':self.seed.value(), 'notes':self.notes.toPlainText()}
        self.start_job('generate', data)

    def start_job(self, command, data=None):
        if self.process: return self.error('Only one task can run at a time.')
        self.job_done = False; self.buffer = ''; self.started = time.monotonic()
        self.progress.setRange(0, 0); self.progress.setFormat('Working…'); self.status.setText(command.capitalize()); self.generate_btn.setEnabled(False); self.cancel_btn.setEnabled(True)
        self.process = QtCore.QProcess(self); self.process.setProcessChannelMode(QtCore.QProcess.MergedChannels); self.process.setWorkingDirectory(str(Path(__file__).resolve().parents[1])); self.process.readyReadStandardOutput.connect(self.read_output); self.process.finished.connect(self.finished); self.process.errorOccurred.connect(self.process_error)
        args = ['-u', '-m', 'studio.worker', command, str(self.root)]
        if data is not None: args.append(json.dumps(data))
        self.process.start(sys.executable, args)
        self.log('Started ' + command)

    def read_output(self):
        if not self.process: return
        self.buffer += bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace').replace('\r', '\n')
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            if line.startswith('STUDIO_EVENT:'):
                try: self.handle_event(json.loads(line[len('STUDIO_EVENT:'):]))
                except Exception as e: self.log(f'Event error: {e}')
            elif line.strip(): self.log(line)

    def handle_event(self, ev):
        kind = ev.get('kind'); message = ev.get('message', '')
        if message: self.status.setText(message); self.log(message)
        if kind == 'step':
            self.progress.setRange(0, ev['total']); self.progress.setValue(ev['step']); self.progress.setFormat(f"Diffusion {ev['step']} / {ev['total']}  ·  GPU {ev['gpu']}")
            if ev['step'] == ev['total']: self.progress.setRange(0,0); self.progress.setFormat('Decoding geometry…')
        if kind == 'done':
            self.job_done = True
            if ev.get('path'): self.refresh_library(); self.display_model(ev['path'])
        if kind == 'error': self.error(message)

    def process_error(self, err):
        if err == QtCore.QProcess.FailedToStart: self.error('Worker failed to start: ' + self.process.errorString()); self.finished(-1, QtCore.QProcess.CrashExit)

    def finished(self, code, status):
        if not self.process: return
        self.read_output(); self.process.deleteLater(); self.process = None; self.started = None; self.generate_btn.setEnabled(True); self.cancel_btn.setEnabled(False); self.progress.setRange(0,1); self.progress.setValue(1 if self.job_done and code == 0 else 0)
        if code != 0 or not self.job_done:
            self.status.setText('Task failed or cancelled. See log.'); self.progress.setFormat('Failed / cancelled'); self.log(f'Worker ended with code {code}.')
        else: self.progress.setFormat('Complete')

    def cancel(self):
        if self.process and QtWidgets.QMessageBox.question(self, 'Cancel task', 'Stop the worker now? Partially completed work will not be published.') == QtWidgets.QMessageBox.Yes:
            self.log('Cancelling worker'); self.process.kill()

    def tick(self):
        if self.started is not None:
            seconds = int(time.monotonic() - self.started); self.elapsed.setText(f'{seconds//60:02}:{seconds%60:02}')

    def closeEvent(self, event):
        if self.process:
            self.process.kill(); self.process.waitForFinished(5000)
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv); app.setStyleSheet(STYLE); win = Studio(); win.show(); sys.exit(app.exec())

import hashlib
import contextlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

MODEL_REPO = 'tencent/Hunyuan3D-2mini'
REVISION = 'f90a0f7df7d5e6f71109cf333f6a95a0ae3194a6'
SUBFOLDER = 'hunyuan3d-dit-v2-mini'
WEIGHT_SHA256 = '3cc66f3bea33e4062b7dbc875ffe1d70c4888914aec3e91b60f94e9bd01b522b'
CONFIG_GIT_SHA1 = '9b5e721842d1bc751b3a54ee8adc8d59a2630367'
WEIGHT_SIZE = 3819958234
CATEGORIES = ('Buildings', 'Environment', 'Furniture', 'Vegetation', 'StreetProps', 'DecorativeObjects', 'NonWeaponVehicles')
DEFAULT_ROOT = Path.home() / 'HunyuanAssetStudio'
CONFIG_PATH = DEFAULT_ROOT / 'Settings' / 'settings.json'


def load_settings(path=CONFIG_PATH):
    data = {'storage': str(DEFAULT_ROOT), 'game_directory': ''}
    try:
        with open(path, encoding='utf-8') as f:
            content = json.load(f)
        if isinstance(content, dict):
            data.update({k: v for k, v in content.items() if k in data and isinstance(v, str)})
    except (FileNotFoundError, ValueError, OSError):
        pass
    return data


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.studio-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def initialize(root):
    root = Path(root).expanduser().resolve()
    for name in ('Models', 'Generated', 'Previews', 'ReferenceImages', 'Logs', 'Cache', 'Settings'):
        (root / name).mkdir(parents=True, exist_ok=True)
    for cat in CATEGORIES: (root / 'Generated' / cat).mkdir(exist_ok=True)
    return root


@contextlib.contextmanager
def generation_lock(lock_path=None):
    """OS-owned lock: a killed worker cannot leave a stale lock behind."""
    path = Path(lock_path or DEFAULT_ROOT / 'Cache' / 'generation.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a+b') as f:
        f.seek(0, os.SEEK_END)
        if f.tell() == 0:
            f.write(b'0'); f.flush()
        f.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Another Hunyuan Asset Studio generation is already running.') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def file_hash(path, algo='sha256', git_blob=False):
    h = hashlib.new(algo)
    if git_blob:
        h.update(f'blob {Path(path).stat().st_size}\0'.encode())
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def model_dir(root): return Path(root) / 'Models' / SUBFOLDER


def verify_model(root):
    folder = model_dir(root)
    config, weight = folder / 'config.yaml', folder / 'model.fp16.safetensors'
    if not config.is_file() or not weight.is_file(): raise FileNotFoundError('Mini model config or weights missing. Download them in Model Manager.')
    if weight.stat().st_size != WEIGHT_SIZE: raise ValueError('Model weights have an incorrect size. Download them again.')
    if file_hash(config, 'sha1', True) != CONFIG_GIT_SHA1: raise ValueError('Model config checksum mismatch. Download it again.')
    if file_hash(weight) != WEIGHT_SHA256: raise ValueError('Model weights checksum mismatch. Download them again.')
    return True


def validate_image(path):
    from PIL import Image, ImageOps
    path = Path(path)
    if path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'): raise ValueError('Use a PNG, JPEG or WebP image.')
    with Image.open(path) as im:
        if im.format not in ('PNG', 'JPEG', 'WEBP'): raise ValueError('Unsupported image format.')
        if min(im.size) < 2 or max(im.size) > 16384: raise ValueError('Image dimensions must be between 2 and 16384 pixels.')
        im.load()
        im = ImageOps.exif_transpose(im).convert('RGBA')
        if not im.getchannel('A').getbbox(): raise ValueError('Image is fully transparent.')
        return im.copy()


def validate_mesh(mesh):
    import numpy as np
    import trimesh
    if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.vertices) or not len(mesh.faces): raise ValueError('Generation returned empty or invalid geometry.')
    if not np.isfinite(mesh.vertices).all(): raise ValueError('Mesh contains non-finite vertices.')
    if (mesh.faces < 0).any() or (mesh.faces >= len(mesh.vertices)).any(): raise ValueError('Mesh contains invalid face indices.')
    return mesh


def load_mesh(path):
    import trimesh
    mesh = trimesh.load(str(path), force='mesh', process=False)
    return validate_mesh(mesh)


def save_generation(root, category, image_path, mesh, parameters, notes, reference_image=None):
    validate_mesh(mesh)
    if category not in CATEGORIES: raise ValueError('Invalid asset category.')
    image = reference_image.copy() if reference_image is not None else validate_image(image_path)
    parent = initialize(root) / 'Generated' / category
    token = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
    temp = Path(tempfile.mkdtemp(prefix='.pending-', dir=parent))
    final = parent / token
    try:
        image.save(temp / 'reference.png')
        mesh.export(str(temp / 'model.glb'))
        load_mesh(temp / 'model.glb')
        atomic_json(temp / 'metadata.json', {'id': token, 'created_utc': datetime.now(timezone.utc).isoformat(), 'model': MODEL_REPO, 'revision': REVISION, 'subfolder': SUBFOLDER, 'reference': 'reference.png', 'geometry': 'model.glb', 'parameters': parameters, 'notes': notes, 'category': category})
        os.replace(temp, final)
        return final / 'model.glb'
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def export_mesh(source, destination):
    dest = Path(destination)
    ext = dest.suffix.lower()
    if ext not in ('.glb', '.obj'): raise ValueError('Only GLB and OBJ export are currently supported.')
    if dest.exists(): raise FileExistsError('Destination already exists; choose a different filename.')
    mesh = load_mesh(source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Single-file OBJ is suitable for the untextured shape meshes this app creates.
    if ext == '.obj':
        payload = mesh.export(file_type='obj', include_texture=False).encode('utf-8')
    else:
        payload = mesh.export(file_type='glb')
    fd, name = tempfile.mkstemp(dir=dest.parent, suffix=ext, prefix='.export-')
    try:
        with os.fdopen(fd, 'wb') as f: f.write(payload)
        load_mesh(name)
        # Exclusive creation prevents silently overwriting a concurrently created file.
        with open(dest, 'xb') as out:
            try:
                with open(name, 'rb') as src: shutil.copyfileobj(src, out)
            except BaseException:
                out.close(); dest.unlink(missing_ok=True); raise
    finally:
        if os.path.exists(name): os.unlink(name)
    return dest


def import_to_game(source, destdir):
    source = Path(source)
    load_mesh(source)
    destdir = Path(destdir)
    if not destdir.is_dir(): raise ValueError('Choose an existing destination folder.')
    dest = destdir / (source.parent.name + source.suffix)
    with open(dest, 'xb') as out, open(source, 'rb') as src:
        try: shutil.copyfileobj(src, out)
        except BaseException:
            out.close(); dest.unlink(missing_ok=True); raise
    return dest


def hardware(root):
    import psutil
    report = {'OS': platform.platform(), 'Python': sys.version.split()[0], 'RAM': f'{psutil.virtual_memory().total / 2**30:.1f} GiB', 'Disk free': f'{shutil.disk_usage(root).free / 2**30:.1f} GiB', 'GPU': 'Unavailable', 'CUDA': 'Unavailable', 'PyTorch': 'Not installed'}
    try:
        import torch
        report['PyTorch'] = torch.__version__
        report['CUDA'] = str(torch.version.cuda or 'not installed') + (' (available)' if torch.cuda.is_available() else ' (unavailable)')
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            report['GPU'] = f'{torch.cuda.get_device_name(0)}; {free / 2**30:.1f} / {total / 2**30:.1f} GiB free'
    except Exception as e: report['CUDA'] = str(e)
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.free', '--format=csv,noheader'], capture_output=True, text=True, timeout=5, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        report['NVIDIA driver'] = result.stdout.strip()
    except (OSError, subprocess.SubprocessError): report['NVIDIA driver'] = 'nvidia-smi unavailable'
    return report

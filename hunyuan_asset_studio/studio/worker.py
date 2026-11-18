"""Separate, single-job process. stdout events are prefixed so library output is never mistaken for status."""
import gc
import json
import os
import shutil
import sys
import traceback
from pathlib import Path
from .core import MODEL_REPO, REVISION, SUBFOLDER, WEIGHT_SIZE, WEIGHT_SHA256, CONFIG_GIT_SHA1, file_hash, generation_lock, initialize, save_generation, validate_image, verify_model


def event(kind, **data):
    print('STUDIO_EVENT:' + json.dumps({'kind': kind, **data}), flush=True)


def download(root):
    root = initialize(root)
    if shutil.disk_usage(root).free < WEIGHT_SIZE * 2 + 1024**3:
        raise RuntimeError('Not enough free disk space for the download and its cache; free at least about 8 GiB.')
    os.environ['HF_HOME'] = str(root / 'Cache' / 'huggingface')
    from huggingface_hub import hf_hub_download
    for name in ('config.yaml', 'model.fp16.safetensors'):
        target = root / 'Models' / SUBFOLDER / name
        force = False
        if target.is_file():
            event('status', message=f'Checking existing {name}')
            if name == 'config.yaml':
                force = file_hash(target, 'sha1', True) != CONFIG_GIT_SHA1
            else:
                force = target.stat().st_size != WEIGHT_SIZE or file_hash(target) != WEIGHT_SHA256
        event('status', message=f'{"Repairing" if force else "Downloading / resuming"} {name}; progress is shown in the log')
        hf_hub_download(repo_id=MODEL_REPO, filename=f'{SUBFOLDER}/{name}', revision=REVISION, local_dir=str(root / 'Models'), force_download=force)
    event('status', message='Checking model SHA-256 (this can take several minutes)')
    verify_model(root)
    event('done', message='Weights verified. Model loading and inference have not yet been tested.')


def generate(root, data):
    root = initialize(root)
    event('status', message='Verifying model files')
    verify_model(root)
    image = validate_image(data['image'])
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor' / 'Hunyuan3D-2'))
    os.environ['HF_HOME'] = str(root / 'Cache' / 'huggingface')
    os.environ['HY3DGEN_MODELS'] = str(root / 'Models')
    import torch
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
    if not torch.cuda.is_available(): raise RuntimeError('CUDA is unavailable. Install compatible NVIDIA drivers and the CUDA PyTorch build; CPU fallback is not verified.')
    free, total = torch.cuda.mem_get_info()
    event('status', message=f'CUDA: {torch.cuda.get_device_name(0)}; {free / 2**30:.2f} GiB free of {total / 2**30:.2f} GiB. Loading model.')
    pipeline = None
    try:
        pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(str(root / 'Models'), subfolder=SUBFOLDER, use_safetensors=True, device='cuda')
        event('status', message='Model loaded. Starting diffusion.')
        def callback(step, _t, _outputs):
            free_mem, total_mem = torch.cuda.mem_get_info()
            event('step', step=step + 1, total=data['steps'], gpu=f'{(total_mem-free_mem)/2**30:.2f} / {total_mem/2**30:.2f} GiB in use')
        with torch.inference_mode():
            meshes = pipeline(image=image, num_inference_steps=data['steps'], octree_resolution=data['resolution'], num_chunks=data['chunks'], generator=torch.manual_seed(data['seed']), output_type='trimesh', mc_algo='mc', callback=callback, callback_steps=1, enable_pbar=False)
        event('status', message='Validating and saving generated mesh')
        if not meshes: raise ValueError('Pipeline returned no mesh.')
        params = {k: data[k] for k in ('steps', 'resolution', 'chunks', 'seed')}
        path = save_generation(root, data['category'], data['image'], meshes[0], params, data.get('notes', ''), reference_image=image)
        event('done', message='Generation saved and reopened successfully.', path=str(path))
    finally:
        del pipeline
        gc.collect()
        if torch.cuda.is_available(): torch.cuda.empty_cache()


def main():
    try:
        command, root = sys.argv[1:3]
        if command == 'download': download(root)
        elif command == 'verify':
            event('status', message='Checking checksums')
            verify_model(root)
            event('done', message='Model files verified. Loading and inference are not yet tested.')
        elif command == 'generate':
            with generation_lock():
                generate(root, json.loads(sys.argv[3]))
        else: raise ValueError('Unknown worker command')
    except BaseException as exc:
        traceback.print_exc()
        text = str(exc)
        if 'out of memory' in text.lower(): text += ' Close other GPU applications; reduce resolution/chunks. 6 GiB operation is not guaranteed.'
        event('error', message=text)
        sys.exit(1)

if __name__ == '__main__': main()

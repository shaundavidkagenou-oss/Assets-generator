# Hunyuan Asset Studio — experimental implementation

**Status: not acceptance-tested.** This is an isolated desktop implementation that calls Tencent's actual `Hunyuan3DDiTFlowMatchingPipeline`, but it has not been run on Windows or with CUDA, and no model was downloaded or inference performed in the development environment. It may need compatibility fixes before it works on your machine. In particular, **6 GB operation is not established**. It is not the complete application described in the original request; see Limitations below.

## Setup on Windows (experimental)

1. Review Tencent's [license](https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/f8db63096c8282cb27354314d896feba5ba6ff8a/LICENSE) and [notices](https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/f8db63096c8282cb27354314d896feba5ba6ff8a/NOTICE), the [model card](https://huggingface.co/tencent/Hunyuan3D-2mini), and the terms for all third-party dependencies. The community agreement explicitly excludes the EU, UK and South Korea, imposes use and distribution restrictions, and has additional commercial terms. It is your responsibility to check the applicable current terms; no commercial permission is represented here. Source files in the upstream repo contain headers with inconsistent license terminology; consult Tencent if uncertain.
2. Install 64-bit Python 3.10, Git for Windows, and an up-to-date NVIDIA driver. Ensure `py -3.10` and `git` work in Command Prompt. The setup script selects PyTorch 2.5.1 / CUDA 12.4 wheels; confirm that your driver supports this CUDA runtime. This combination is a candidate, **not a Windows-tested lockfile**. Installer network access to PyPI, PyTorch's wheel index and GitHub is required.
3. Run `setup_windows.bat` from this folder. It creates `.venv`, installs the specified packages, and clones Tencent's official repository into ignored `vendor/` at commit `f8db63096c8282cb27354314d896feba5ba6ff8a`. Errors stop the script; rerun it after resolving them. It does **not** prove model loading or inference.
4. Run `launch_windows.bat`. Open **Model manager**, review hardware and choose **Download / resume**. Only `config.yaml` and `model.fp16.safetensors` for `hunyuan3d-dit-v2-mini` at revision `f90a0f7df7d5e6f71109cf333f6a95a0ae3194a6` are requested (approximately 3.82 GB, plus temporary/cache space). Hugging Face access is required. Progress appears in the task log; incomplete downloads may resume via Hugging Face's client. Existing corrupt files are redownloaded. The config's Git blob hash and weight SHA-256 are checked after download and before each generation.
5. Import a PNG/JPEG/WebP reference, preferably a single object on a transparent background, and click **Generate 3D**. Notes are stored as metadata, not sent to the model. The defaults (30 steps, resolution 380, 20,000 chunks, seed 12345) come from Tencent's model card; they are **not proven to fit 6 GB**. Progress reports actual diffusion callbacks. Decoding is indeterminate, not simulated. A successful mesh is validated, saved, reopened, and displayed. Use **Export GLB / OBJ** or **Import to game** to copy it to a chosen folder without overwrite. Use **Use reference & settings** on a previous entry to regenerate as a separate asset.

Default data path: `%USERPROFILE%\HunyuanAssetStudio`. Change it using Storage settings; existing files are not moved. The bootstrap settings file stays under the default path's `Settings` folder. Each asset is saved under `Generated/<category>/<timestamp-id>/` as `model.glb`, `reference.png`, and `metadata.json`. Files are written outside the game and originals are never overwritten. The GPU worker is a separate process and an OS lock prevents concurrent generations across studio instances. Cancelling kills the worker; a hidden `.pending-*` directory may remain if interrupted while saving and can be removed manually after all studio workers have stopped.

## Important limitations

- **No validated low-VRAM offload mode, presets, or CPU fallback.** The pinned upstream pipeline's offload method refers to a `components` attribute not provided by that class; the upstream demo's low-VRAM flag mainly clears CUDA cache. We do not pretend this provides model offloading. The pipeline loads on CUDA as-is. Reducing resolution/chunks is exposed as an experiment, not a tested preset. A GTX 1660 Super can still run out of memory, including during model load. No alternative model or unofficial fork is silently substituted.
- No verified installation, download, actual model load, inference, displayed result, camera behavior or GPU performance test on Windows. A real, end-to-end acceptance run on the target PC remains essential.
- Shape-only; no texture/PBR, text-to-3D, FBX, GLTF, rigging or animation. Generated topology is not guaranteed game-ready. OBJ is a geometry-only export; use GLB for the generated shape. No automatic background-removal model is installed; use a transparent reference for best results.
- Library is browse/open/regenerate only: no rename, delete, duplicate or side-by-side comparison. Viewport has orbit, pan, zoom, reset and wireframe; no ground plane, lighting presets, fullscreen, material information or mesh processing. No persistent queue: only one job at a time. The memory display is sampled at diffusion steps, not continuously during decode. No load-only test or first-run inference test is automated. Disk warnings are only applied to downloads.
- Logs may include local paths and error details. No local network service is started.

## Troubleshooting

- **Setup fails:** read the command-window error. Check Python 3.10 x64, Git, disk space, internet, and package/driver compatibility; rerun `setup_windows.bat`. If the environment is broken, close the app, remove only this folder's `.venv`, and run setup again. Do not remove your assets.
- **Model verify fails:** use Download / resume again to repair files; confirm enough free space and network access to Hugging Face. The integrity check reads the entire weight file.
- **CUDA unavailable:** check `nvidia-smi`, driver, and that the installed torch build reports CUDA in Model manager. The script's CUDA wheels require a compatible NVIDIA driver. No unverified CPU fallback is enabled.
- **Out of memory:** close GPU-heavy apps, retry with a lower octree resolution and chunk size. These changes are experimental and may degrade output; there is no promise they will fit on 6 GB. Save the log under `Logs/studio.log` for diagnosis.
- **Empty / invalid mesh:** the pipeline can fail to extract a surface; the app reports failure and does not publish a result. Try a clearer centered reference image, another seed or settings.
- **Viewport blank:** verify a mesh was actually generated/opened; check graphics drivers and OpenGL support. An OpenGL failure is not an inference success.
- **Import collision:** choose another game folder or rename the existing destination yourself. No automatic overwrite is performed.

## Development / test record

The repository initially contained only `README.md`; no game engine or import system was present. The development sandbox was Linux/Python 3.11 with ~3.8 GiB RAM, ~20 GiB free disk, no `nvidia-smi`, no CUDA/PyTorch, and no OpenGL system library. Unit tests exercise image validation, mesh validation, checksums, atomic generation storage using a synthetic test mesh (never used by the app as a generated result), GLB/OBJ round trips, settings, collisions, game import, the generation lock, and a mocked pipeline-call contract (not real inference). Python 3.10 Windows wheels were checked for the explicitly listed UI and inference packages, but full installation/resolution and execution were not tested. PyTorch CUDA wheels were not tested. OpenGL prevented desktop smoke testing in this sandbox. No claim of real inference success is made.

Run tests in an environment with UI requirements installed:

```text
cd hunyuan_asset_studio
python -m unittest discover -s tests -v
```

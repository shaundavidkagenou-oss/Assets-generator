@echo off
setlocal
cd /d "%~dp0"
echo HUNYUAN ASSET STUDIO -- experimental Windows setup
where py >nul 2>&1 || (echo Python launcher not found. Install 64-bit Python 3.10 and Git. & exit /b 1)
where git >nul 2>&1 || (echo Git not found. Install Git for Windows. & exit /b 1)
py -3.10 -c "import struct; assert struct.calcsize('P') == 8" || (echo 64-bit Python 3.10 is required. & exit /b 1)
if not exist .venv\Scripts\python.exe py -3.10 -m venv .venv
if errorlevel 1 exit /b 1
set PY=.venv\Scripts\python.exe
%PY% -m pip install --upgrade pip==24.3.1 || exit /b 1
%PY% -m pip install -r requirements-ui.txt || exit /b 1
%PY% -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124 || exit /b 1
%PY% -m pip install -r requirements-inference.txt || exit /b 1
if not exist vendor\Hunyuan3D-2\.git git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2.git vendor\Hunyuan3D-2
if errorlevel 1 exit /b 1
git -C vendor\Hunyuan3D-2 fetch origin f8db63096c8282cb27354314d896feba5ba6ff8a || exit /b 1
git -C vendor\Hunyuan3D-2 checkout --detach f8db63096c8282cb27354314d896feba5ba6ff8a || exit /b 1
%PY% -c "import torch; from PIL import Image; import trimesh, skimage, pymeshlab; print('PyTorch',torch.__version__,'CUDA available:',torch.cuda.is_available())" || exit /b 1
echo Dependencies installed. CUDA, model loading, and actual inference are NOT yet verified.
echo Run launch_windows.bat, open Model Manager, download and verify weights, then test an image.
endlocal

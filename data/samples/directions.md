Railway deployment failed with error: "Package libgl1-mesa-glx is not available"
This is a dependency needed by OpenCV/image processing libraries. Fix the nixpacks.toml to use the correct packages.
Update nixpacks.toml to:
[phases.setup]
nixPkgs = ["python311", "tesseract", "poppler_utils", "libGL", "glib"]
aptPkgs = ["libgl1", "libglib2.0-0", "tesseract-ocr", "poppler-utils"]

[phases.install]
cmds = ["pip install --upgrade pip", "pip install -r requirements.txt"]

[start]
cmd = "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"
Also check if there's a Dockerfile that might be overriding nixpacks. If so, either:
1.	Delete the Dockerfile to use nixpacks only, OR
2.	Update the Dockerfile to use the correct packages: 
o	Replace libgl1-mesa-glx with libgl1
Check requirements.txt for any packages that need OpenGL (like opencv-python) and consider replacing with opencv-python-headless which doesn't need GUI libraries.


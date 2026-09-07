"""Windows entry point for the checksum-verified portable Blender installer."""
import os
from pathlib import Path
import subprocess
import zipfile

if os.name != "nt":
    raise SystemExit("Install Blender 4.5 LTS for your OS and set BLENDER_PATH in .env.")
result = subprocess.call([
    "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
    "-File", str(Path(__file__).with_suffix(".ps1")),
])
if result:
    raise SystemExit(result)
root = Path(__file__).resolve().parents[1] / ".tools"
target = root / "blender-4.5.3-windows-x64"
marker = target / ".science-video-install-complete"
if not marker.exists():
    print("Extracting verified Blender archive...", flush=True)
    with zipfile.ZipFile(root / "blender-4.5.3-windows-x64.zip") as archive:
        for member in archive.infolist():
            if not (root / member.filename).resolve().is_relative_to(root.resolve()):
                raise SystemExit("Unsafe ZIP member")
        archive.extractall(root)
    subprocess.run([str(target / "blender.exe"), "--version"], check=True, stdout=subprocess.DEVNULL)
    marker.write_text("Verified Blender 4.5.3 portable installation\n", encoding="utf-8")
print(target / "blender.exe")

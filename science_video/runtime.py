import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def executable(name: str) -> str:
    override = os.getenv(f"{name.upper()}_PATH")
    if override:
        candidate = shutil.which(override)
        if candidate:
            return candidate
        raise ValueError(f"{name.upper()}_PATH does not point to an executable: {override}")
    found = shutil.which(name)
    if found:
        return found
    if name == "ffmpeg":
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    if name == "blender":
        candidates = list((ROOT / ".tools").glob("blender*/blender.exe"))
        candidates += list(Path("C:/Program Files/Blender Foundation").glob("Blender */blender.exe"))
        if candidates:
            return str(sorted(candidates)[-1])
    raise ValueError(f"{name} not found. Install it or set {name.upper()}_PATH in .env.")


def run(args, *, cwd=None, log: Path | None = None):
    if log:
        with log.open("a", encoding="utf-8") as stream:
            result = subprocess.run([str(a) for a in args], cwd=cwd, stdout=stream,
                                    stderr=subprocess.STDOUT, check=False)
        if result.returncode:
            raise RuntimeError(f"{Path(args[0]).name} failed ({result.returncode}); see {log}")
        return ""
    result = subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(f"{Path(args[0]).name} failed: {result.stderr[-3000:]}")
    return result.stdout + result.stderr

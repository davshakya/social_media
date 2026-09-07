import json
import os
from pathlib import Path
import shutil
from datetime import datetime, timezone
from uuid import uuid4

from .audio import narration, soundtrack
from .captions import write_captions
from .runtime import executable, run


def hindi_fonts(font_dir):
    return [p for p in font_dir.rglob("*") if p.suffix.lower() in {".ttf", ".otf", ".ttc"}
            and any(n in p.name.lower() for n in ("nirmala", "devanagari", "mangal"))]


def preflight():
    ffmpeg, blender = executable("ffmpeg"), executable("blender")
    filters = run([ffmpeg, "-hide_banner", "-filters"])
    if "subtitles" not in filters:
        raise ValueError("FFmpeg must include the libass subtitles filter")
    font_dir = Path(os.getenv("FONT_DIR") or ("C:/Windows/Fonts" if os.name == "nt" else "/usr/share/fonts"))
    if not font_dir.is_dir():
        raise ValueError("Set FONT_DIR to a directory containing a Hindi Devanagari font")
    if not hindi_fonts(font_dir):
        raise ValueError("FONT_DIR must contain Nirmala UI, Mangal, or Noto Sans Devanagari font files")
    return ffmpeg, blender, font_dir


def compose(folder, ffmpeg, fps, *, music=None, font_dir=None):
    # Copy fonts locally: avoids Windows drive-colon / quote escaping in filter syntax.
    local_fonts = folder / "fonts"
    local_fonts.mkdir(exist_ok=True)
    if font_dir:
        fonts = hindi_fonts(font_dir)
        if not fonts:
            raise ValueError("FONT_DIR must contain Nirmala UI, Mangal, or Noto Sans Devanagari font files")
        for path in fonts:
            shutil.copy2(path, local_fonts / path.name)
    music_input = "music.wav"
    if music:
        source = Path(music).resolve()
        if not source.is_file():
            raise ValueError(f"Music file not found: {source}")
        # Normalize arbitrary filenames before using FFmpeg's filter graph.
        run([ffmpeg, "-y", "-i", source, "-ar", "24000", "-ac", "1", folder / "user-music.wav"])
        music_input = "user-music.wav"
    graph = (
        "[0:v]subtitles=filename=captions.ass:fontsdir=fonts[v];"
        "[1:a]highpass=f=70,lowpass=f=16000,loudnorm=I=-16:TP=-1.5:LRA=11[voice];[2:a]volume=0.14,afade=t=out:st=28:d=2[music];"
        "[3:a]volume=0.5[sfx];[voice][music][sfx]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.95[a]"
    )
    run([ffmpeg, "-y", "-framerate", fps, "-start_number", "1", "-i", "frames/frame_%04d.png",
         "-i", "voice.wav", "-stream_loop", "-1", "-i", music_input, "-i", "sfx.wav",
         "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-t", "30",
         "-r", fps, "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-maxrate", "14M", "-bufsize", "28M",
         "-g", str(fps * 2), "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
         "-movflags", "+faststart", "final.mp4"],
        cwd=folder, log=folder / "ffmpeg.log")
    # Decode the completed file to catch corrupt or incomplete media.
    run([ffmpeg, "-v", "error", "-xerror", "-i", "final.mp4", "-f", "null", "-"], cwd=folder,
        log=folder / "ffmpeg.log")


def generate(story, output=Path("videos"), *, preview=False, silent=False, voice_dir=None,
             music=None, still=False, resolution=1080):
    ffmpeg, blender, font_dir = preflight()
    if music and not Path(music).is_file():
        raise ValueError(f"Music file not found: {music}")
    folder = Path(output).resolve() / (datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8])
    folder.mkdir(parents=True)
    story.write(folder / "storyboard.json")
    manifest = {"status": "running", "silent": silent, "preview": preview, "topic": story.topic}
    def save():
        (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    save()
    print(f"Job: {folder}", flush=True)
    try:
        if preview:
            fps, width, height = 5, 270, 480
        elif resolution in (720, 1080):
            fps, width, height = 30, resolution, resolution * 16 // 9
        else:
            raise ValueError("Production resolution must be 720 or 1080")
        print("Preparing narration and measuring scene timing...", flush=True)
        timeline = narration(story, folder, ffmpeg, silent=silent, voice_dir=voice_dir, fps=fps)
        job = {"width": width, "height": height, "fps": fps, "preview": preview, "timeline": timeline}
        (folder / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        write_captions(folder, timeline, os.getenv("CAPTION_FONT", "Nirmala UI"), silent=silent,
                       recorded=voice_dir is not None)
        soundtrack(folder, timeline)
        print(f"Rendering Blender scenes ({width}×{height}, {fps} fps). See blender.log for progress...", flush=True)
        cmd = [blender, "--background", "--factory-startup", "--disable-autoexec", "--python-exit-code", "1",
               "--python", Path(__file__).with_name("blender_engine.py"), "--", "--job", folder / "job.json"]
        if still:
            cmd.append("--still")
        run(cmd, log=folder / "blender.log")
        render_log = (folder / "blender.log").read_text(encoding="utf-8", errors="replace")
        if any(line.startswith("Error:") for line in render_log.splitlines()):
            raise RuntimeError(f"Blender reported render errors; see {folder / 'blender.log'}")
        if not still:
            print("Adding Hindi captions, music and sound effects...", flush=True)
            compose(folder, ffmpeg, fps, music=music, font_dir=font_dir)
        manifest.update(status="stills_complete" if still else "complete", **{k: job[k] for k in ("width", "height", "fps")})
        save()
        return folder if still else folder / "final.mp4"
    except BaseException as exc:
        manifest.update(status="failed", error=str(exc))
        save()
        raise

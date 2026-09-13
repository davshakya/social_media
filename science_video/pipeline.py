import json
import os
from pathlib import Path
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

from .audio import narration, soundtrack
from .captions import write_captions
from .runtime import executable, run


def render_progress_bar(frame, total, width=24):
    """Return a compact, terminal-safe render progress bar."""
    frame = min(max(0, frame), total)
    filled = round(width * frame / total) if total else width
    return f"[{'#' * filled}{'-' * (width - filled)}] {frame / total:.0%} ({frame}/{total} frames)" if total else "[########################] 100%"


def blender_progress(total_frames):
    """Create a callback that turns Blender's frame messages into one progress bar."""
    last_frame = -1

    def update(line):
        nonlocal last_frame
        match = re.search(r"\bFra:(\d+)", line)
        if not match:
            return
        frame = int(match.group(1))
        if frame == last_frame:
            return
        last_frame = frame
        print("\rRendering " + render_progress_bar(frame, total_frames), end="", flush=True)

    return update


def resolve_image_provider(provider, requested=None):
    selected = (requested or os.getenv("TOPIC_IMAGE_PROVIDER", "none")).lower()
    if selected == "local":
        return "local"
    if selected in {"none", "off", ""}:
        return "none"
    if provider not in {"openai", "gemini"}:
        raise ValueError("AI media requires --provider openai or gemini.")
    if requested and selected not in {"auto", provider}:
        raise ValueError(f"--topic-image {selected} conflicts with --provider {provider}. Use --topic-image auto or none.")
    return provider


def generate_image(topic, output, *, provider="gemini", image_provider="local", model=None):
    from .topic_image import generate_topic_image
    selected = resolve_image_provider(provider, image_provider)
    if selected == "none":
        raise ValueError("Image output requires an image provider.")
    folder = Path(output).resolve() / (datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8])
    folder.mkdir(parents=True)
    manifest = {"status": "running", "output_type": "image", "topic": topic}
    def save():
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    save()
    try:
        result = generate_topic_image(topic, folder / "topic_image.png", provider=selected, model=model, standalone=True)
        if not result:
            raise ValueError("No image was generated.")
        manifest.update(status="image_complete", image=result.name)
        save()
        return result
    except Exception as exc:
        manifest.update(status="failed", error=str(exc))
        save()
        raise


def check_render_log(render_log):
    warnings = set()
    for line in render_log.splitlines():
        if line.startswith("Error:"):
            if line.startswith("Error: Shadow buffer full,") or line == "Error: Reached max shadow updates.":
                warnings.add("Blender shadow buffer limit reached; some shadows may be missing.")
            else:
                raise RuntimeError(f"Blender reported render errors: {line}; see blender.log")
    return sorted(warnings)


def check_render_frames(folder, count):
    for index in range(1, count + 1):
        path = folder / "frames" / f"frame_{index:04d}.png"
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Missing or empty rendered frame: {path}")


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


def compose(folder, ffmpeg, fps, *, duration=30, music=None, font_dir=None):
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
    music_fade_start = max(0, duration - 2)
    graph = (
        "[0:v]subtitles=filename=captions.ass:fontsdir=fonts[v];"
        f"[1:a]highpass=f=70,lowpass=f=16000,loudnorm=I=-16:TP=-1.5:LRA=11[voice];[2:a]volume=0.14,afade=t=out:st={music_fade_start}:d=2[music];"
        "[3:a]volume=0.5[sfx];[voice][music][sfx]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.95[a]"
    )
    run([ffmpeg, "-y", "-framerate", fps, "-start_number", "1", "-i", "frames/frame_%04d.png",
         "-i", "voice.wav", "-stream_loop", "-1", "-i", music_input, "-i", "sfx.wav",
         "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-t", str(duration),
         "-r", fps, "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-maxrate", "14M", "-bufsize", "28M",
         "-g", str(fps * 2), "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
         "-movflags", "+faststart", "final.mp4"],
        cwd=folder, log=folder / "ffmpeg.log")
    # Decode the completed file to catch corrupt or incomplete media.
    run([ffmpeg, "-v", "error", "-xerror", "-i", "final.mp4", "-f", "null", "-"], cwd=folder,
        log=folder / "ffmpeg.log")


def generate(story, output=Path("videos"), *, preview=False, silent=False, voice_dir=None,
             music=None, still=False, resolution=1080, fast=False, workers=1,
             topic_image_provider=None, topic_image_model=None, provider="openai", require_image=False):
    selected_image_provider = resolve_image_provider(provider, topic_image_provider)
    ffmpeg, blender, font_dir = preflight()
    if music and not Path(music).is_file():
        raise ValueError(f"Music file not found: {music}")
    folder = Path(output).resolve() / (datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8])
    folder.mkdir(parents=True)
    story.write(folder / "storyboard.json")
    topic_image_path = None
    topic_image_status = "not_requested"
    topic_image_error = None
    if selected_image_provider not in {"", "none", "off"}:
        try:
            from .topic_image import generate_topic_image
            topic_image_path = generate_topic_image(
                story.topic, folder / "topic_image.png", provider=selected_image_provider,
                model=topic_image_model)
            topic_image_status = "generated" if topic_image_path else "fallback"
        except Exception as exc:
            topic_image_status = "fallback"
            topic_image_error = str(exc)
            print(f"Topic image unavailable: {exc}" if require_image else
                  f"Topic image unavailable; using procedural visuals: {exc}", flush=True)
    hashtags = [tag if tag.startswith("#") else f"#{tag}" for tag in story.hashtags]
    social_metadata = {
        "title": story.hook[:100],
        "description": f"{story.hook}\n\n{story.cta}\n\n" + " ".join(hashtags),
        "tags": [tag.lstrip("#") for tag in story.hashtags],
        "youtube_visibility": os.getenv("YOUTUBE_VISIBILITY", "public"),
        "made_for_kids": False,
    }
    (folder / "social_metadata.json").write_text(
        json.dumps(social_metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {"status": "running", "silent": silent, "preview": preview, "topic": story.topic,
                "output_type": "both" if require_image else "video",
                "hook": story.hook, "cta": story.cta, "hashtags": story.hashtags,
                "topic_image": {"status": topic_image_status,
                                 "path": str(topic_image_path.name) if topic_image_path else None,
                                 "error": topic_image_error}}
    def save():
        (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    save()
    print(f"Job: {folder}", flush=True)
    try:
        if require_image and topic_image_path is None:
            raise ValueError(f"Both outputs requested but image generation failed: {topic_image_error or 'no image generated'}")
        if preview:
            fps, width, height = 5, 270, 480
        elif resolution in (320, 480, 720, 1080):
            fps, width, height = 30, resolution, resolution * 16 // 9
        else:
            raise ValueError("Production resolution must be 320, 480, 720, or 1080")
        if workers < 1:
            raise ValueError("--workers must be at least 1")
        narrator = "local silence" if silent else "local WAV files" if voice_dir else f"{provider} TTS"
        print(f"Narration: {narrator}. Timing is measured locally.", flush=True)
        print("Video processing: local Python, Blender, and FFmpeg (animation, captions, music, and assembly).", flush=True)
        timeline = narration(story, folder, ffmpeg, silent=silent, voice_dir=voice_dir, fps=fps, provider=provider)
        job = {"width": width, "height": height, "fps": fps, "duration": story.duration,
               "preview": preview, "fast": fast,
               "job_folder": str(folder),
               "topic_image": str(topic_image_path.name) if topic_image_path else None,
               "timeline": timeline}
        (folder / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        write_captions(folder, timeline, os.getenv("CAPTION_FONT", "Nirmala UI"), silent=silent,
                       recorded=voice_dir is not None)
        soundtrack(folder, timeline, story.duration)
        print(f"Rendering Blender scenes ({width}×{height}, {fps} fps). Blender output follows:", flush=True)
        total_frames = round(story.duration * fps)
        render_threads = max(1, (os.cpu_count() or 1) // workers)
        cmd = [blender, "--background", "--factory-startup", "--disable-autoexec", "--threads",
               str(render_threads), "--python-exit-code", "1",
               "--python", Path(__file__).with_name("blender_engine.py"), "--", "--job", folder / "job.json"]
        if still:
            cmd.append("--still")
        if workers == 1:
            progress = blender_progress(total_frames)
            try:
                # A separate Blender process per scene avoids the Windows
                # Blender 4.5 background renderer corrupting later scenes.
                for index in range(len(timeline)):
                    run(cmd + ["--scene-index", str(index)], log=folder / "blender.log",
                        line_callback=progress)
            finally:
                print(flush=True)
        else:
            def render_scene(index):
                scene_log = folder / f"blender-{index + 1:02d}.log"
                run(cmd + ["--scene-index", str(index)], log=scene_log, live=True)

            errors = []
            with ThreadPoolExecutor(max_workers=min(workers, len(timeline))) as pool:
                futures = [pool.submit(render_scene, index) for index in range(len(timeline))]
                for future in futures:
                    try:
                        future.result()
                    except BaseException as exc:
                        errors.append(exc)
            (folder / "blender.log").write_text(
                "".join((folder / f"blender-{index + 1:02d}.log").read_text(encoding="utf-8", errors="replace")
                        for index in range(len(timeline))),
                encoding="utf-8")
            if errors:
                raise RuntimeError(f"Blender scene rendering failed; see {folder / 'blender.log'}") from errors[0]
        render_log = (folder / "blender.log").read_text(encoding="utf-8", errors="replace")
        manifest["render_warnings"] = check_render_log(render_log)
        for warning in manifest["render_warnings"]:
            print(f"Warning: {warning}", flush=True)
        if not still:
            check_render_frames(folder, round(story.duration * fps))
            print("Adding Hindi captions, music and sound effects...", flush=True)
            compose(folder, ffmpeg, fps, duration=story.duration, music=music, font_dir=font_dir)
        manifest.update(status="stills_complete" if still else "complete", **{k: job[k] for k in ("width", "height", "fps")})
        save()
        return folder if still else folder / "final.mp4"
    except BaseException as exc:
        manifest.update(status="failed", error=str(exc))
        save()
        raise

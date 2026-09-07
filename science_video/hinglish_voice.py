"""Create recorded Hinglish narration tracks with Edge's online neural voices."""

import argparse
import asyncio
import os
from pathlib import Path
import shutil
import sys
import tempfile

from dotenv import load_dotenv

from .runtime import ROOT, executable, run
from .storyboard import Storyboard


DEFAULT_VOICE = "hi-IN-SwaraNeural"


def track_paths(folder: Path, scene_count: int) -> list[Path]:
    return [folder / f"{number:02d}.wav" for number in range(1, scene_count + 1)]


async def synthesize_mp3(text: str, voice: str, rate: str, destination: Path) -> None:
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError(
            "Edge TTS is not installed. Run: .\\.venv\\Scripts\\python.exe -m pip install -e \".[voice]\""
        ) from exc
    await edge_tts.Communicate(text, voice=voice, rate=rate).save(str(destination))


def generate_tracks(storyboard: Path, output: Path, *, voice: str = DEFAULT_VOICE,
                    rate: str = "+0%", overwrite: bool = False) -> list[Path]:
    """Generate one 24 kHz mono WAV per scene, ready for ``--voice-dir``."""
    story = Storyboard.read(storyboard)
    tracks = track_paths(output, len(story.scenes))
    existing = [path for path in tracks if path.exists()]
    if existing and not overwrite:
        names = ", ".join(path.name for path in existing)
        raise ValueError(f"Voice tracks already exist in {output}: {names}. Use --overwrite to replace them.")

    output.mkdir(parents=True, exist_ok=True)
    ffmpeg = executable("ffmpeg")
    with tempfile.TemporaryDirectory(prefix="hinglish-voice-", dir=output) as temporary:
        temp_dir = Path(temporary)
        for index, (scene, track) in enumerate(zip(story.scenes, tracks), start=1):
            mp3 = temp_dir / f"{index:02d}.mp3"
            wav = temp_dir / f"{index:02d}.wav"
            asyncio.run(synthesize_mp3(scene.narration, voice, rate, mp3))
            run([ffmpeg, "-y", "-i", mp3, "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", wav])
            shutil.move(str(wav), str(track))
    return tracks


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Create Hinglish WAV narration tracks for the science-video generator.")
    command.add_argument("storyboard", type=Path, help="Validated storyboard JSON")
    command.add_argument("--output", type=Path, required=True, help="Directory for 01.wav, 02.wav, ...")
    command.add_argument("--voice", default=os.getenv("HINGLISH_EDGE_VOICE", DEFAULT_VOICE),
                         help=f"Edge neural voice (default: {DEFAULT_VOICE})")
    command.add_argument("--rate", default="+0%", help="Edge rate, for example +5%% or -5%%")
    command.add_argument("--overwrite", action="store_true", help="Replace existing numbered WAV tracks")
    return command


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    args = parser().parse_args(argv)
    try:
        tracks = generate_tracks(args.storyboard, args.output, voice=args.voice, rate=args.rate, overwrite=args.overwrite)
    except (RuntimeError, ValueError) as exc:
        print(f"Voice generation error: {exc}", file=sys.stderr)
        return 1
    print(f"Created {len(tracks)} Hinglish voice tracks in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

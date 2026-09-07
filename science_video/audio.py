import math
import os
import struct
import wave
from pathlib import Path

from .runtime import run

RATE = 24000


def wav_duration(path: Path):
    with wave.open(str(path), "rb") as stream:
        return stream.getnframes() / stream.getframerate()


def write_wave(path, samples):
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(samples)


def silence(path, duration):
    write_wave(path, b"\x00\x00" * round(RATE * duration))


def tempo_filter(ratio):
    filters = []
    while ratio > 2:
        filters.append("atempo=2")
        ratio /= 2
    while ratio < 0.5:
        filters.append("atempo=0.5")
        ratio *= 2
    return ",".join(filters + [f"atempo={ratio:.8f}"])


def narration(story, folder, ffmpeg, *, silent=False, voice_dir=None, fps=30):
    """Synthesize separately so measured audio defines exact scene boundaries."""
    client = None
    if not silent and voice_dir is None:
        from openai import OpenAI
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("Set OPENAI_API_KEY, provide --voice-dir, or explicitly use --silent.")
        client = OpenAI(timeout=90, max_retries=2)
    raw, lengths = [], []
    for i, scene in enumerate(story.scenes):
        path = folder / f"voice-{i:02d}-raw.wav"
        if silent:
            silence(path, scene.duration)
        elif voice_dir is not None:
            source = Path(voice_dir) / f"{i+1:02d}.wav"
            if not source.is_file():
                raise ValueError(f"Missing narration file: {source}")
            run([ffmpeg, "-y", "-i", source, "-ar", RATE, "-ac", "1", "-c:a", "pcm_s16le", path])
        else:
            with client.audio.speech.with_streaming_response.create(
                model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
                voice=os.getenv("OPENAI_TTS_VOICE", "coral"), input=scene.narration,
                instructions=("Speak in a warm, confident, conversational Hinglish voice for a short science video. "
                              "Pronounce Devanagari Hindi naturally. Pronounce Latin-script English science words in clear English. "
                              "Use a lively but unhurried pace, with a short pause at sentence endings. Do not read punctuation aloud."),
                response_format="wav",
            ) as response:
                response.stream_to_file(path)
        duration = wav_duration(path)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError(f"Empty or invalid narration: {path}")
        raw.append(path)
        lengths.append(duration)
    speed = sum(lengths) / story.duration
    if not silent and not 0.67 <= speed <= 1.5:
        raise ValueError(f"Narration is {sum(lengths):.1f}s; fitting 30s would sound unnatural. Shorten/lengthen the script or recording.")
    # Round cumulative boundaries rather than individual durations to prevent frame drift.
    bounds = [0]
    for i in range(len(lengths)):
        bounds.append(round(sum(lengths[:i+1]) / sum(lengths) * story.duration * fps))
    timeline = []
    for i, (scene, path) in enumerate(zip(story.scenes, raw)):
        frames = bounds[i+1] - bounds[i]
        if frames < 1:
            raise ValueError("A narration segment is too short to occupy one frame")
        duration = frames / fps
        target = folder / f"voice-{i:02d}.wav"
        run([ffmpeg, "-y", "-i", path, "-af",
             f"{tempo_filter(lengths[i]/duration)},apad,atrim=duration={duration:.8f}",
             "-ar", RATE, "-ac", "1", "-c:a", "pcm_s16le", target])
        timeline.append({**scene.model_dump(), "start_frame": bounds[i]+1,
                         "end_frame": bounds[i+1], "start": bounds[i]/fps,
                         "duration": duration, "raw_voice_duration": lengths[i]})
    with wave.open(str(folder / "voice.wav"), "wb") as output:
        output.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        for i in range(len(raw)):
            with wave.open(str(folder / f"voice-{i:02d}.wav"), "rb") as source:
                output.writeframes(source.readframes(source.getnframes()))
    return timeline


def soundtrack(folder, timeline, duration=30):
    """Original quiet tonal bed and short scene transition chimes, no licensed assets."""
    bed, effects = bytearray(), bytearray()
    starts = [s["start"] for s in timeline[1:]]
    for i in range(RATE * duration):
        t = i / RATE
        fade = min(1, t / 2, (duration-t) / 2)
        chord = sum(math.sin(2*math.pi*f*t) for f in (130.81, 164.81, 196)) / 3
        bed.extend(struct.pack("<h", round(1100 * fade * chord)))
        chime = sum(math.sin(2*math.pi*660*(t-s)) * math.exp(-12*(t-s))
                    for s in starts if 0 <= t-s < 0.45)
        effects.extend(struct.pack("<h", round(1800 * chime)))
    write_wave(folder / "music.wav", bed)
    write_wave(folder / "sfx.wav", effects)

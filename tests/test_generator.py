from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from science_video.audio import narration, silence, tempo_filter, wav_duration
from science_video.captions import safe_ass, stamp, write_captions
from science_video.hinglish_voice import track_paths
from science_video.queue import TopicQueue
from science_video.runtime import executable, run
from science_video.storyboard import Storyboard, demo_storyboard


@pytest.mark.parametrize("change", [
    lambda d: d["scenes"][0].update(action="exec_python"),
    lambda d: d["scenes"][0].update(duration=5),
    lambda d: d["scenes"][0].update(duration=float("nan")),
    lambda d: d["scenes"][0].update(narration="Only English words here"),
    lambda d: d["scenes"][0].update(caption="बर्फ floats"),
    lambda d: d.update(code="import os"),
])
def test_invalid_storyboards_rejected(change):
    data = demo_storyboard().model_dump()
    change(data)
    with pytest.raises(ValidationError):
        Storyboard.model_validate(data)


def test_roundtrip_unicode(tmp_path):
    path = tmp_path / "story.json"
    demo_storyboard().write(path)
    assert Storyboard.read(path) == demo_storyboard()


def test_real_audio_timing_and_captions(tmp_path):
    ffmpeg = executable("ffmpeg")
    timeline = narration(demo_storyboard(), tmp_path, ffmpeg, silent=True, fps=5)
    assert wav_duration(tmp_path / "voice.wav") == 30
    assert timeline[0]["start_frame"] == 1
    assert timeline[-1]["end_frame"] == 150
    assert all(a["end_frame"] + 1 == b["start_frame"] for a, b in zip(timeline, timeline[1:]))
    write_captions(tmp_path, timeline, silent=True)
    srt = (tmp_path / "captions.srt").read_text(encoding="utf-8-sig")
    assert "00:00:30,000" in srt
    assert "Why Does Ice Float?" in srt
    assert srt.isascii()
    assert "SILENT PREVIEW" in (tmp_path / "captions.ass").read_text(encoding="utf-8-sig")


def test_hinglish_voice_and_english_only_on_screen_text():
    story = demo_storyboard()
    for scene in story.scenes:
        assert any("\u0900" <= char <= "\u097f" for char in scene.narration)
        assert any(char.isascii() and char.isalpha() for char in scene.narration)
        assert scene.caption.isascii()
        assert not any("\u0900" <= char <= "\u097f" for char in scene.caption)


def test_hinglish_voice_track_names_match_voice_dir_contract(tmp_path):
    assert track_paths(tmp_path / "voice", 3) == [
        tmp_path / "voice" / "01.wav", tmp_path / "voice" / "02.wav", tmp_path / "voice" / "03.wav",
    ]


def test_recorded_voice_controls_timeline(tmp_path):
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    output.mkdir()
    for i, duration in enumerate([3, 7, 9, 5, 6]):
        silence(source / f"{i+1:02}.wav", duration)
    timeline = narration(demo_storyboard(), output, executable("ffmpeg"), voice_dir=source, fps=30)
    assert [s["duration"] for s in timeline] == [3, 7, 9, 5, 6]
    assert wav_duration(output / "voice.wav") == 30


def test_empty_voice_rejected(tmp_path):
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    output.mkdir()
    silence(source / "01.wav", 0)
    with pytest.raises(ValueError, match="Empty"):
        narration(demo_storyboard(), output, executable("ffmpeg"), voice_dir=source)


def test_captions_escape_and_time_carry():
    assert stamp(59.9999) == "00:01:00,000"
    assert stamp(59.9999, True) == "0:01:00.00"
    assert "\\" not in safe_ass(r"{\pos(0,0)}")
    assert "{" not in safe_ass(r"{\pos(0,0)}")
    assert tempo_filter(4).startswith("atempo=2,")


def test_queue_claims_are_exclusive_and_future_topics_wait(tmp_path):
    path = tmp_path / "queue.sqlite3"
    queue = TopicQueue(path)
    id = queue.add("Ice floats", "2026-01-01")
    queue.add("Future", "2099-01-01")
    def claim():
        worker = TopicQueue(path)
        try:
            return worker.claim("2026-09-06")
        finally:
            worker.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sum(r is not None for r in results) == 1
    queue.finish(id, error="render failed")
    queue.retry(id)
    assert queue.claim("2026-09-06")["id"] == id
    queue.finish(id, output="final.mp4")
    assert queue.rows()[0]["status"] == "complete"
    assert queue.claim("2026-09-06") is None
    queue.close()


def test_missing_api_key_does_not_silently_fake_narration(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        narration(demo_storyboard(), tmp_path, executable("ffmpeg"))


def test_api_planner_contract_and_refusal(monkeypatch):
    from types import SimpleNamespace
    import openai
    from science_video.storyboard import plan
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    captured = {}
    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_parsed=demo_storyboard())
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    assert plan("Why does ice float?") == demo_storyboard()
    assert captured["text_format"] is Storyboard
    assert captured["input"][-1]["content"] == "Why does ice float?"
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: SimpleNamespace(
        responses=SimpleNamespace(parse=lambda **kw: SimpleNamespace(output_parsed=None))))
    with pytest.raises(ValueError, match="refused"):
        plan("Unsupported topic")


def test_composition_with_hindi_and_awkward_output_path(tmp_path):
    from pathlib import Path
    import os
    import imageio_ffmpeg
    from science_video.pipeline import compose, hindi_fonts
    font_dir = Path(os.getenv("FONT_DIR") or ("C:/Windows/Fonts" if os.name == "nt" else "/usr/share/fonts"))
    if not hindi_fonts(font_dir):
        pytest.skip("A Devanagari font is needed for the media integration test")
    folder = tmp_path / "Hindi video's output"
    (folder / "frames").mkdir(parents=True)
    ffmpeg = executable("ffmpeg")
    run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=0x102030:s=270x480:r=1:d=30",
         folder / "frames" / "frame_%04d.png"])
    timeline = narration(demo_storyboard(), folder, ffmpeg, silent=True, fps=1)
    write_captions(folder, timeline, silent=True)
    silence(folder / "music.wav", 30)
    silence(folder / "sfx.wav", 30)
    compose(folder, ffmpeg, 1, font_dir=font_dir)
    frames = imageio_ffmpeg.read_frames(str(folder / "final.mp4"))
    metadata = next(frames)
    assert metadata["size"] == (270, 480)
    assert metadata["duration"] == 30
    assert sum(1 for _ in frames) == 30
    frames.close()

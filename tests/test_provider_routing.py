import base64
import json
from io import BytesIO

import pytest

from science_video import gemini_media, storyboard
from science_video.audio import narration, wav_duration
from science_video.pipeline import resolve_image_provider
from science_video.runtime import executable


@pytest.mark.parametrize("provider", ["gemini", "openai"])
def test_image_provider_cannot_cross_services(provider, monkeypatch):
    other = "openai" if provider == "gemini" else "gemini"
    monkeypatch.setenv("TOPIC_IMAGE_PROVIDER", other)
    assert resolve_image_provider(provider) == provider
    assert resolve_image_provider(provider, "auto") == provider
    assert resolve_image_provider(provider, "none") == "none"
    with pytest.raises(ValueError, match="conflicts"):
        resolve_image_provider(provider, other)


@pytest.mark.parametrize("provider", ["gemini", "openai"])
def test_explicit_planner_never_falls_back(provider, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    calls = []

    def fail(*args, **kwargs):
        calls.append(provider)
        raise TimeoutError("timeout")

    def wrong(*args, **kwargs):
        pytest.fail("Called the other provider")

    monkeypatch.setattr(storyboard, "_plan_gemini", fail if provider == "gemini" else wrong)
    monkeypatch.setattr(storyboard, "_plan_openai", fail if provider == "openai" else wrong)
    with pytest.raises(TimeoutError):
        storyboard.plan("Example", provider=provider)
    assert calls


def test_gemini_narration_uses_only_google_and_writes_valid_wav(tmp_path, monkeypatch):
    import openai
    monkeypatch.setenv("GEMINI_API_KEY", "google-test")
    monkeypatch.setenv("OPENAI_API_KEY", "unused")
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: pytest.fail("OpenAI called"))
    calls = []

    def respond(request, **kwargs):
        assert request.get_header("X-goog-api-key") == "google-test"
        assert request.full_url.startswith("https://generativelanguage.googleapis.com/")
        payload = json.loads(request.data)
        assert payload["generationConfig"]["responseModalities"] == ["AUDIO"]
        calls.append(payload)
        return BytesIO(json.dumps({"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;codec=pcm;rate=24000",
            "data": base64.b64encode(b"\0\0" * 24000 * 6).decode(),
        }}]}}]}).encode())

    monkeypatch.setattr(gemini_media, "urlopen", respond)
    narration(storyboard.demo_storyboard(), tmp_path, executable("ffmpeg"), provider="gemini")
    assert len(calls) == 5
    assert wav_duration(tmp_path / "voice.wav") == 30


def test_gemini_image_does_not_use_openai(tmp_path, monkeypatch):
    import openai
    from science_video.topic_image import generate_topic_image
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: pytest.fail("OpenAI called"))
    monkeypatch.setattr(gemini_media, "generate_media", lambda *args: (b"\x89PNG\r\n\x1a\nimage", "image/png"))
    image = generate_topic_image("Python", tmp_path / "topic.png", provider="gemini")
    assert image.exists()
    assert json.loads((tmp_path / "topic_image.json").read_text())["provider"] == "gemini"


def test_gemini_key_cannot_fall_back_to_openai_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "unused")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        storyboard.plan("Example", provider="gemini")

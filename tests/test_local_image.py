import json
import socket

import pytest
from PIL import Image

from science_video.pipeline import resolve_image_provider
from science_video.topic_image import generate_topic_image


def test_catalog_lessons_have_all_sections(tmp_path):
    from science_video.topic_catalog import TOPICS
    from science_video.topic_lessons import LESSONS, lesson_for
    assert len(LESSONS) == len(TOPICS)
    for topic in TOPICS:
        assert len(lesson_for(topic)) == 4
        assert all(lesson_for(topic))
    path = generate_topic_image(TOPICS[4], tmp_path / "api.png", provider="local", standalone=True)
    assert path.exists()
    notes = (tmp_path / "topic_notes.md").read_text()
    assert "Application Programming Interface" in notes
    assert "GET /weather" in notes


def test_repeated_topic_gets_a_new_design(tmp_path, monkeypatch):
    from science_video import local_image
    seeds = iter([123, 456])
    monkeypatch.setattr(local_image.secrets, "randbits", lambda bits: next(seeds))
    first = local_image.create_image("Python dictionaries", tmp_path / "first/image.png", standalone=True)
    second = local_image.create_image("Python dictionaries", tmp_path / "second/image.png", standalone=True)
    assert first.read_bytes() != second.read_bytes()


@pytest.mark.parametrize("topic,style", [
    ("Python dictionaries", "key_value"), ("Data charts", "chart"),
    ("Water molecules", "molecules"), ("Python functions", "code"),
    ("Neural networks", "network"),
])
def test_local_image_is_valid_and_offline(tmp_path, monkeypatch, topic, style):
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("Network access"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert resolve_image_provider("gemini", "local") == "local"
    path = generate_topic_image(topic, tmp_path / "topic.png", provider="local")
    with Image.open(path) as image:
        image.load()
        assert image.size == (1024, 1024)
        assert image.format == "PNG"
    assert json.loads((tmp_path / "topic_image.json").read_text())["style"] == style

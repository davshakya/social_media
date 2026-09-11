import json

import pytest

from science_video import cli, pipeline
from science_video.storyboard import demo_storyboard


def test_image_only_skips_planning_and_video(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda *a: None)
    monkeypatch.setattr(cli, "plan", lambda *a, **k: pytest.fail("Planner called"))
    monkeypatch.setattr(pipeline, "preflight", lambda: pytest.fail("Blender preflight called"))
    assert cli.main(["generate", "--type", "image", "--topic", "Python dictionaries",
                     "--output", str(tmp_path)]) == 0
    images = list(tmp_path.glob("*/topic_image.png"))
    assert len(images) == 1
    manifest = json.loads((images[0].parent / "manifest.json").read_text())
    assert manifest["status"] == "image_complete"
    assert not list(tmp_path.rglob("*.mp4"))


@pytest.mark.parametrize("kind", ["video", "both"])
def test_video_output_routes_existing_storyboard(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(cli, "load_dotenv", lambda *a: None)
    story = tmp_path / "story.json"
    demo_storyboard().write(story)
    captured = {}
    def generate(*args, **kwargs):
        captured.update(kwargs)
        return tmp_path / "final.mp4"
    monkeypatch.setattr(pipeline, "generate", generate)
    assert cli.main(["generate", "--type", kind, "--storyboard", str(story), "--silent"]) == 0
    assert captured["require_image"] == (kind == "both")
    if kind == "both":
        assert captured["topic_image_provider"] == "local"


def test_both_rejects_disabled_images_before_planning(monkeypatch):
    monkeypatch.setattr(cli, "plan", lambda *a, **k: pytest.fail("Planner called"))
    assert cli.main(["generate", "--type", "both", "--topic-image", "none"]) == 1


def test_image_failure_is_recorded(tmp_path, monkeypatch):
    from science_video import topic_image
    def fail(*a, **k):
        raise ValueError("Image failed")
    monkeypatch.setattr(topic_image, "generate_topic_image", fail)
    with pytest.raises(ValueError, match="Image failed"):
        pipeline.generate_image("Example", tmp_path)
    manifest = json.loads(next(tmp_path.glob("*/manifest.json")).read_text())
    assert manifest["status"] == "failed"

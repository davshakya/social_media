from science_video.presentation import create_presentation
from science_video.storyboard import demo_storyboard


def test_creates_one_vertical_slide_per_story_scene(tmp_path):
    path = create_presentation(demo_storyboard(), tmp_path / "lesson.pptx")
    from pptx import Presentation
    deck = Presentation(path)
    assert len(deck.slides) == 5
    assert deck.slide_height > deck.slide_width

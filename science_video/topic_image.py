"""Optional topic artwork generation for animated video backgrounds."""
import base64
import json
import os
from pathlib import Path
from urllib.request import urlopen


MAX_IMAGE_BYTES = 15 * 1024 * 1024


def _valid_image(data):
    return (data.startswith(b"\x89PNG\r\n\x1a\n") or
            data.startswith(b"\xff\xd8\xff"))


def generate_topic_image(topic, destination, *, provider=None, model=None):
    """Generate one bounded topic image and return its path, or None when disabled."""
    provider = (provider or os.getenv("TOPIC_IMAGE_PROVIDER", "none")).lower()
    if provider in {"", "none", "off"}:
        return None
    if provider != "openai":
        raise ValueError("Unsupported topic image provider. Use none or openai.")
    api_key = os.getenv("TOPIC_IMAGE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Set TOPIC_IMAGE_API_KEY or OPENAI_API_KEY for topic images.")
    destination = Path(destination)
    if destination.is_file() and destination.stat().st_size <= MAX_IMAGE_BYTES:
        data = destination.read_bytes()
        if _valid_image(data):
            return destination
    from openai import OpenAI
    prompt = (
        "Create a clean, colorful educational illustration for a short vertical technology video. "
        "Show the core idea visually with simple shapes, diagrams, and friendly lighting. "
        "Do not include readable text, logos, brand names, faces, or watermarks. "
        f"The topic is: {topic[:300]}"
    )
    client = OpenAI(api_key=api_key, timeout=120, max_retries=2)
    response = client.images.generate(
        model=model or os.getenv("TOPIC_IMAGE_MODEL", "gpt-image-1"),
        prompt=prompt, size="1024x1024")
    item = response.data[0]
    if getattr(item, "b64_json", None):
        data = base64.b64decode(item.b64_json)
    elif getattr(item, "url", None):
        with urlopen(item.url, timeout=60) as stream:
            data = stream.read(MAX_IMAGE_BYTES + 1)
    else:
        raise ValueError("Image provider returned no image data.")
    if len(data) > MAX_IMAGE_BYTES or not _valid_image(data):
        raise ValueError("Image provider returned an unsupported or oversized image.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    (destination.parent / "topic_image.json").write_text(
        json.dumps({"provider": provider, "model": model or os.getenv("TOPIC_IMAGE_MODEL", "gpt-image-1"),
                    "topic": topic}, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination

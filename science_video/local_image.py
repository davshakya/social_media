"""Offline procedural topic illustrations drawn with Pillow."""
import colorsys
import secrets
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter


def create_image(topic, destination, *, standalone=False):
    """Draw a text-free background; captions remain the source of explanations."""
    seed = secrets.randbits(64)
    rng = random.Random(seed)
    hue = rng.random()
    def color(offset, saturation, value):
        return tuple(round(c * 255) for c in colorsys.hsv_to_rgb((hue + offset) % 1, saturation, value))
    image = Image.new("RGB", (1024, 1024), "#101827")
    draw = ImageDraw.Draw(image)
    accent = rng.choice(["#49d6bc", "#65b5ff", "#bb98ff", "#ffbf69"])
    for y in range(1024):
        draw.line((0, y, 1024, y), fill=color(y / 8000, 0.62, 0.15 + y / 9000))
    glow = Image.new("RGBA", image.size)
    glow_draw = ImageDraw.Draw(glow)
    shift = rng.randint(-120, 120)
    glow_draw.ellipse((-150 + shift, -240, 650 + shift, 420), fill=(*color(0, 0.75, 0.95), 85))
    glow_draw.ellipse((690 - shift, 350, 1220 - shift, 1100), fill=(*color(0.35, 0.85, 0.9), 55))
    image = Image.alpha_composite(image.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(100))).convert("RGB")
    draw = ImageDraw.Draw(image)
    palette = [color(i / 6, 0.42, 1) for i in range(6)]
    accent = palette[0]
    spacing = rng.choice((48, 56, 64, 72))
    for x in range(rng.randint(15, 48), 1024, spacing):
        for y in range(48, 1024, spacing):
            draw.ellipse((x, y, x + 2, y + 2), fill="#35465c")
    background = image.copy()
    text = topic.casefold()
    if any(word in text for word in ("dictionary", "dictionaries", "lookup", "index")):
        style = "key_value"
        for i, y in enumerate((280, 440, 600)):
            color = palette[i]
            fill = tuple(round(channel * 0.32) for channel in color)
            for left, right in ((140, 360), (640, 880)):
                draw.rounded_rectangle((left, y+12, right, y+108), radius=23, fill="#101323")
                draw.rounded_rectangle((left, y, right, y+96), radius=23, fill=fill, outline=color, width=2)
                draw.rounded_rectangle((left+20, y+18, left+25, y+78), radius=2, fill=color)
            draw.line((394, y+48, 608, y+48), fill=color, width=5)
            draw.polygon([(612, y+48), (587, y+33), (587, y+63)], fill=color)
            draw.ellipse((476, y+33, 506, y+63), fill=color)
    elif any(word in text for word in ("data", "chart", "accuracy", "regression", "correlation", "csv")):
        style = "chart"
        draw.line([(160, 260), (160, 760), (870, 760)], fill="#8294ad", width=5)
        for i in range(6):
            x = 210 + i * 100
            height = rng.randint(120, 400)
            draw.rounded_rectangle((x, 750 - height, x + 65, 750), radius=12, fill=palette[i])
    elif any(word in text for word in ("ice", "water", "molecule", "density", "oil")):
        style = "molecules"
        for _ in range(16):
            x, y = rng.randint(220, 800), rng.randint(280, 750)
            draw.line((x - 25, y + 35, x, y, x + 36, y + 25), fill="#8294ad", width=8)
            for cx, cy, radius, color in [(x, y, 22, accent), (x - 25, y + 35, 12, "#eeeeee"), (x + 36, y + 25, 12, "#eeeeee")]:
                draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), fill=color)
    elif any(word in text for word in ("code", "python", "function", "debug", "git", "api", "automation", "algorithm")):
        style = "code"
        draw.rounded_rectangle((140, 250, 884, 790), radius=28, fill="#172639", outline="#60738e", width=3)
        for x in (180, 210, 240):
            draw.ellipse((x, 280, x + 12, 292), fill=accent)
        for i in range(7):
            x, y = 190 + (i % 3) * 35, 340 + i * 55
            draw.rounded_rectangle((x, y, x + rng.randint(220, 440), y + 13), radius=6, fill=palette[i % len(palette)])
    else:
        style = "network"
        layers = [[(230 + i * 280, 512 + (j - (n-1)/2) * 120) for j in range(n)] for i, n in enumerate((3, 5, 3))]
        for left, right in zip(layers, layers[1:]):
            for a in left:
                for b in right:
                    draw.line([a, b], fill="#435d77", width=3)
        for i, layer in enumerate(layers):
            for x, y in layer:
                draw.ellipse((x-26, y-26, x+26, y+26), fill=palette[i], outline="#eeeeee", width=3)
    if standalone:
        def font(size):
            for name in ("C:/Windows/Fonts/segoeuib.ttf", "DejaVuSans-Bold.ttf"):
                try:
                    return ImageFont.truetype(name, size)
                except OSError:
                    pass
            return ImageFont.load_default(size=size)

        def centered(text, y, size=30, color="#eeeeee", x=512, width=880):
            face = font(size)
            while draw.textlength(text, font=face) > width and size > 12:
                size -= 1
                face = font(size)
            draw.text((x, y), text, font=face, fill=color, anchor="mm")

        # Wrap titles by measured width so longer catalog topics remain readable.
        words, lines, line = topic.split(), [], ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if line and draw.textlength(candidate, font=font(44)) > 880:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        draw.rounded_rectangle((365, 26, 659, 62), radius=18, fill="#443667")
        centered("LEARN VISUALLY", 44, 16, "#d7c9ff")
        for index, line in enumerate(lines[:3]):
            centered(line, 105 + index * 48, 44)
        if style == "key_value":
            centered("KEY", 235, 22, accent, x=250)
            centered("VALUE", 235, 22, accent, x=760)
            for y, key, value in [(328, '"name"', '"Alice"'), (488, '"age"', '25'), (648, '"language"', '"Python"')]:
                centered(key, y, 28, x=250, width=200)
                centered(value, y, 28, x=760, width=210)
            if "dictionar" in text:
                draw.rounded_rectangle((72, 760, 952, 948), radius=26, fill="#171e35", outline="#485171", width=2)
                draw.rounded_rectangle((95, 777, 100, 925), radius=2, fill="#54dec9")
                centered('person = {"name": "Alice", "age": 25, "language": "Python"}', 805, 24)
                centered('person["name"] returns "Alice"', 862, 30, accent)
                centered("A dictionary maps each unique key to a value.", 922, 25)
            else:
                centered("Illustration: keys point to stored values.", 862, 28)
        else:
            descriptions = {
                "chart": "Illustrative chart - values are examples, not measured data.",
                "molecules": "Schematic molecular illustration - not to scale.",
                "code": "Illustration of code organized into a sequence of instructions.",
                "network": "Schematic network of connected nodes.",
            }
            centered(descriptions[style], 865, 26)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lesson = None
    if standalone:
        from .topic_lessons import lesson_for
        from .infographic import render_lesson
        lesson = lesson_for(topic)
        if lesson:
            image = render_lesson(background, topic, lesson, palette)
            headings = ("What it is", "How it works", "Practical example", "Remember")
            (destination.parent / "topic_notes.md").write_text(
                f"# {topic}\n\n" + "\n\n".join(f"## {h}\n\n{body}" for h, body in zip(headings, lesson)) + "\n",
                encoding="utf-8")
    image.save(destination, format="PNG")
    (destination.parent / "topic_image.json").write_text(json.dumps({
        "provider": "local", "model": None, "topic": topic, "style": style, "standalone": standalone, "seed": seed,
        "content": dict(zip(("definition", "mechanism", "example", "takeaway"), lesson)) if lesson else None,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination

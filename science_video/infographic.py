"""Readable offline lesson cards with measured text wrapping."""
from PIL import Image, ImageDraw, ImageFont


def render_lesson(background, topic, lesson, palette):
    image = background.resize((1080, 1500))
    draw = ImageDraw.Draw(image)

    def font(size, bold=False):
        names = ("C:/Windows/Fonts/segoeuib.ttf", "DejaVuSans-Bold.ttf") if bold else ("C:/Windows/Fonts/segoeui.ttf", "DejaVuSans.ttf")
        for name in names:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                pass
        return ImageFont.load_default(size=size)

    def lines(text, face, width):
        result, line = [], ""
        for word in text.split():
            candidate = (line + " " + word).strip()
            if line and draw.textlength(candidate, font=face) > width:
                result.append(line)
                line = word
            else:
                line = candidate
        return result + ([line] if line else [])

    draw.text((64, 44), "TECH EXPLAINED  /  QUICK GUIDE", font=font(19, True), fill=palette[1])
    title_font = font(43, True)
    title_lines = lines(topic, title_font, 952)
    for i, line in enumerate(title_lines):
        draw.text((64, 95 + i*55), line, font=title_font, fill="white")
    top = max(250, 110 + len(title_lines)*55)
    for i, (label, content) in enumerate(zip(("WHAT IT IS", "HOW IT WORKS", "PRACTICAL EXAMPLE", "REMEMBER"), lesson)):
        face = font(28)
        wrapped = lines(content, face, 870)
        height = 86 + len(wrapped)*39
        if top + height > image.height - 40:
            extended = Image.new("RGB", (1080, top + height + 60), "#171d32")
            extended.paste(image, (0, 0))
            image, draw = extended, ImageDraw.Draw(extended)
        draw.rounded_rectangle((56, top+7, 1024, top+height+7), radius=24, fill="#101425")
        draw.rounded_rectangle((56, top, 1024, top+height), radius=24, fill="#1c263d", outline=palette[i], width=2)
        draw.text((88, top+22), f"0{i+1}  {label}", font=font(21, True), fill=palette[i])
        for j, line in enumerate(wrapped):
            draw.text((88, top+65+j*39), line, font=face, fill="#f2f3fa")
        top += height + 26
    return image.crop((0, 0, 1080, top + 24))

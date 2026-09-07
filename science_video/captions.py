"""English-only on-screen captions for Hinglish narration."""


def stamp(seconds, ass=False):
    units = round(seconds * (100 if ass else 1000))
    base = 100 if ass else 1000
    seconds, sub = divmod(units, base)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours}:{minutes:02}:{seconds:02}.{sub:02}" if ass else f"{hours:02}:{minutes:02}:{seconds:02},{sub:03}"


def safe_ass(text):
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ").replace("\r", " ")


def write_captions(folder, timeline, font="Nirmala UI", silent=False, recorded=False):
    """Write only the approved English scene captions; never transcribe narration."""
    if any(char in font for char in ",\n\r"):
        raise ValueError("Caption font must be a font family name")
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{font},66,&H00FFFFFF,&H00FFFFFF,&H0024190D,&H9024190D,-1,0,0,0,100,100,0,0,1,3,1,2,70,70,230,1
Style: Brand,{font},29,&H00DFD1A3,&H00FFFFFF,&H0024190D,&H0024190D,0,0,0,0,100,100,0,0,1,1,0,8,30,30,95,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    label = "SILENT PREVIEW" if silent else ("RECORDED VOICE" if recorded else "AI VOICE")
    events = [f"Dialogue: 0,0:00:00.00,0:00:30.00,Brand,,0,0,0,,SCIENCE IN 30 SEC - {label}"]
    srt = []
    for number, scene in enumerate(timeline, start=1):
        start = scene["start"]
        end = start + scene["duration"]
        caption = safe_ass(scene["caption"])
        events.append(f"Dialogue: 0,{stamp(start, True)},{stamp(end, True)},Title,,0,0,0,,{caption}")
        srt.append(f"{number}\n{stamp(start)} --> {stamp(end)}\n{scene['caption']}\n")
    (folder / "captions.ass").write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")
    (folder / "captions.srt").write_text("\n".join(srt), encoding="utf-8-sig")

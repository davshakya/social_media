"""The allowlisted contract between the planner and the Blender engine."""
from pathlib import Path
from typing import Literal
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

Action = Literal["show_glass_water_ice", "zoom_into_ice", "show_water_molecules",
                 "compare_density", "return_to_glass", "show_oil_water"]


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration: float = Field(gt=0, le=30)
    action: Action
    camera: Literal["wide", "close", "macro", "medium"]
    narration: str = Field(min_length=1, max_length=500, description="Natural Hinglish narration: Devanagari Hindi with English science terms in Latin script.")
    caption: str = Field(min_length=1, max_length=90, description="English-only on-screen caption in plain ASCII.")


class Storyboard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: str = Field(min_length=1, max_length=300)
    language: Literal["Hinglish"]
    duration: Literal[30]
    scenes: list[Scene] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def check_story(self):
        if abs(sum(s.duration for s in self.scenes) - self.duration) > 0.01:
            raise ValueError("Scene durations must total 30 seconds")
        for scene in self.scenes:
            if not any("\u0900" <= c <= "\u097f" for c in scene.narration):
                raise ValueError("Hinglish narration must include Hindi Devanagari")
            if not re.search(r"[A-Za-z]", scene.narration):
                raise ValueError("Hinglish narration must include English science terms in Latin script")
            if not scene.caption.isascii() or not re.search(r"[A-Za-z]", scene.caption):
                raise ValueError("On-screen captions must be English-only plain ASCII text")
        return self

    @classmethod
    def read(cls, path: Path):
        return cls.model_validate_json(path.read_text(encoding="utf-8-sig"))

    def write(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")


def demo_storyboard():
    lines = [
        (4, "show_glass_water_ice", "wide", "Ice पानी पर क्यों float करती है? इसका reason है density.", "Why Does Ice Float?"),
        (6, "zoom_into_ice", "close", "जब water freeze होता है, उसके molecules open structure बनाते हैं.", "Freezing Creates Open Space"),
        (10, "show_water_molecules", "macro", "इस open structure में molecules के बीच ज्यादा space होता है. इसलिए same mass की ice ज्यादा volume लेती है.", "Same Mass, More Volume"),
        (6, "compare_density", "medium", "Density मतलब mass divided by volume. Ice की density water से कम होती है.", "Lower Density Floats"),
        (4, "return_to_glass", "wide", "इसीलिए ice float करती है, और उसका बड़ा हिस्सा water के नीचे रहता है.", "Most Ice Stays Underwater"),
    ]
    return Storyboard(topic="Why does ice float on water?", language="Hinglish", duration=30,
                      scenes=[Scene(duration=d, action=a, camera=c, narration=n, caption=t)
                              for d, a, c, n, t in lines])


def plan(topic: str):
    import os
    from openai import OpenAI
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("Set OPENAI_API_KEY in .env, or use the bundled demo storyboard.")
    client = OpenAI(timeout=90, max_retries=2)
    response = client.responses.parse(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        input=[{"role": "system", "content": (
            "Write an accurate Hinglish science short, exactly 30 seconds and 60-80 spoken words. "
            "Use 4-6 scenes. Narration must naturally mix Devanagari Hindi with familiar English science words in Latin script, "
            "such as Ice, water, density, molecules, mass, volume, or float. Do not transliterate English terms into Devanagari. "
            "Every caption is visible on the video: it must be English-only ASCII, short, clear, and at most 55 characters. "
            "Never include Hindi, Devanagari, emojis, or non-English symbols in captions. Durations must sum to 30. "
            "The ONLY supported visual topics are ice floating, water molecules, density, and oil/water separation. "
            "For unsupported topics refuse instead of inventing scene actions. "
            "show_water_molecules depicts equal molecule counts, compact liquid versus a schematic open ice lattice; "
            "compare_density depicts water 1.00 and ice 0.917 g/cm3 (approximate near freezing). "
            "show_oil_water depicts static separated oil above water. Do not claim pouring is animated. "
            "All glass actions depict floating ice. Do not use ice actions for oil. "
            "No publishing instructions, code, paths, or external resources." )},
            {"role": "user", "content": topic}], text_format=Storyboard)
    if response.output_parsed is None:
        raise ValueError("Planner refused or returned no valid storyboard. Try an ice/water/density topic.")
    return response.output_parsed

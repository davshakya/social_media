"""The allowlisted contract between the planner and the Blender engine."""
from pathlib import Path
from typing import Literal
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

Action = Literal["show_glass_water_ice", "zoom_into_ice", "show_water_molecules",
                 "compare_density", "return_to_glass", "show_oil_water", "show_code",
                 "show_data_chart", "show_neural_network", "show_algorithm_steps"]


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
    duration: int = Field(ge=30, le=180)
    scenes: list[Scene] = Field(min_length=1, max_length=10)
    hook: str = Field(default="Learn one useful tech idea in 30 seconds.", min_length=1, max_length=160)
    cta: str = Field(default="Follow for practical tech lessons.", min_length=1, max_length=160)
    hashtags: list[str] = Field(default_factory=lambda: ["TechGyaan", "Technology", "Shorts"], max_length=12)

    @model_validator(mode="after")
    def check_story(self):
        if abs(sum(s.duration for s in self.scenes) - self.duration) > 0.01:
            raise ValueError(f"Scene durations must total {self.duration} seconds")
        for scene in self.scenes:
            if not any("\u0900" <= c <= "\u097f" for c in scene.narration):
                raise ValueError("Hinglish narration must include Hindi Devanagari")
            if not re.search(r"[A-Za-z]", scene.narration):
                raise ValueError("Hinglish narration must include English science terms in Latin script")
            if not scene.caption.isascii() or not re.search(r"[A-Za-z]", scene.caption):
                raise ValueError("On-screen captions must be English-only plain ASCII text")
        if any(not tag.strip() or not re.fullmatch(r"#?[A-Za-z0-9_]+", tag) for tag in self.hashtags):
            raise ValueError("Hashtags must contain only letters, numbers, underscores, and an optional #")
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


def _plan_gemini(topic, model, api_key, system_prompt, duration):
    import json
    import time
    from urllib.error import HTTPError, URLError
    from urllib.parse import quote
    from urllib.request import Request, urlopen

    schema = {
        "type": "OBJECT",
        "properties": {
            "topic": {"type": "STRING"},
            "language": {"type": "STRING", "enum": ["Hinglish"]},
            "duration": {"type": "INTEGER"},
            "hook": {"type": "STRING"},
            "cta": {"type": "STRING"},
            "hashtags": {"type": "ARRAY", "items": {"type": "STRING"}},
            "scenes": {"type": "ARRAY", "items": {
                "type": "OBJECT",
                "properties": {
                    "duration": {"type": "NUMBER"},
                    "action": {"type": "STRING", "enum": list(Action.__args__)},
                    "camera": {"type": "STRING", "enum": ["wide", "close", "macro", "medium"]},
                    "narration": {"type": "STRING"},
                    "caption": {"type": "STRING"},
                },
                "required": ["duration", "action", "camera", "narration", "caption"],
            }},
        },
        "required": ["topic", "language", "duration", "hook", "cta", "hashtags", "scenes"],
    }
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": topic}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema},
    }
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model)}:generateContent?key={quote(api_key)}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    for attempt in range(3):
        try:
            with urlopen(request, timeout=90) as response:
                result = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise ValueError(f"Gemini planner request failed ({exc.code}): {detail[:1200]}") from exc
        except URLError as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise ValueError(f"Gemini planner request failed: {exc.reason}") from exc
    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        parsed = Storyboard.model_validate_json(text)
        if parsed.duration != duration:
            raise ValueError(f"Planner returned {parsed.duration} seconds; expected {duration} seconds.")
        return parsed
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError(f"Gemini returned an invalid storyboard: {exc}") from exc


def _provider_failure(exc):
    text = str(exc).lower()
    status = getattr(exc, "status_code", None)
    return status in {401, 408, 429, 500, 502, 503, 504} or any(term in text for term in (
        "credit", "quota", "rate limit", "too many requests", "timed out", "timeout",
        "connection", "connect error", "temporarily unavailable", "service unavailable",
        "429", "500", "502", "503", "504"))


def _plan_openai(topic, model, api_key, system_prompt, duration, *, base_url=None):
    from openai import OpenAI
    client_options = {"api_key": api_key, "timeout": 90, "max_retries": 2}
    if base_url:
        client_options["base_url"] = base_url
    client = OpenAI(**client_options)
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": topic}]
    if base_url is None:
        response = client.responses.parse(model=model, input=messages, text_format=Storyboard)
        parsed = response.output_parsed
    else:
        response = client.beta.chat.completions.parse(
            model=model, messages=messages, response_format=Storyboard)
        parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError("Planner refused or returned no valid storyboard.")
    if parsed.duration != duration:
        raise ValueError(f"Planner returned {parsed.duration} seconds; expected {duration} seconds.")
    return parsed


def plan(topic: str, *, provider=None, model=None, duration=30, _allow_fallback=True):
    import os
    explicit_provider = provider is not None
    provider = (provider or os.getenv("AI_PLANNER_PROVIDER", "gemini")).lower()
    if not explicit_provider and provider == "gemini" and not os.getenv("GEMINI_API_KEY"):
        provider = "openai"
    api_key = (os.getenv("GEMINI_API_KEY") if provider == "gemini" else None) or os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY, AI_API_KEY, or OPENAI_API_KEY in .env, or use the bundled demo storyboard.")
    if provider not in {"openai", "openrouter", "groq", "together", "custom", "gemini"}:
        raise ValueError("Unsupported planner provider. Use openai, openrouter, groq, together, custom, or gemini.")
    if duration not in (30, 120, 150, 180):
        raise ValueError("Video duration must be 30, 120, 150, or 180 seconds")
    selected_model = model or os.getenv("AI_PLANNER_MODEL") or (
        os.getenv("GEMINI_MODEL", "gemini-3.5-flash") if provider == "gemini" else os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    system_prompt = (
            f"Write an accurate Hinglish technology or science short, exactly {duration} seconds. "
            "Use approximately 2 spoken words per second and make the explanation practical, engaging, and easy to understand. "
            "Use 4-8 scenes. Every narration scene MUST contain actual Devanagari Hindi characters such as यह, है, or क्यों, mixed naturally with familiar English science words in Latin script. Do not write any scene narration entirely in English. "
            "such as Ice, water, density, molecules, mass, volume, or float. Do not transliterate English terms into Devanagari. "
            "Every caption is visible on the video: it must be English-only ASCII, short, clear, and at most 55 characters. "
            f"Never include Hindi, Devanagari, emojis, or non-English symbols in captions. Scene durations must sum to {duration}. "
            "For technology topics, narration must include natural Devanagari Hindi plus English terms such as model, data, code, feature, or Python. "
            "The supported visual topics are ice floating, water molecules, density, oil/water separation, Python code, data charts, neural networks, and algorithm steps. "
            "For unsupported topics refuse instead of inventing scene actions. "
            "show_water_molecules depicts equal molecule counts, compact liquid versus a schematic open ice lattice; "
            "compare_density depicts water 1.00 and ice 0.917 g/cm3 (approximate near freezing). "
            "show_oil_water depicts static separated oil above water. Do not claim pouring is animated. "
            "All glass actions depict floating ice. Do not use ice actions for oil. "
            "Use show_code for Python or coding concepts, show_data_chart for data science concepts, "
            "show_neural_network for AI or machine learning concepts, and show_algorithm_steps for practical coding workflows. "
            "Include an attention-grabbing hook, a concise call to action, and 4-8 relevant hashtags. "
            "No publishing instructions, code, paths, or external resources.")
    if provider == "gemini":
        try:
            return _plan_gemini(topic, selected_model, api_key, system_prompt, duration)
        except Exception as exc:
            fallback = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest")
            if selected_model != fallback and _provider_failure(exc):
                try:
                    print(f"Gemini model unavailable; retrying with {fallback}.", flush=True)
                    return _plan_gemini(topic, fallback, api_key, system_prompt, duration)
                except Exception as fallback_exc:
                    exc = fallback_exc
            if _allow_fallback and _provider_failure(exc) and (os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")):
                print("Gemini unavailable; trying OpenAI planner.", flush=True)
                return plan(topic, provider="openai", duration=duration, _allow_fallback=False)
            raise
    base_url = os.getenv("AI_BASE_URL")
    if not base_url:
        base_urls = {
            "openrouter": "https://openrouter.ai/api/v1",
            "groq": "https://api.groq.com/openai/v1",
            "together": "https://api.together.xyz/v1",
        }
        base_url = base_urls.get(provider)
    if provider == "custom" and not base_url:
        raise ValueError("Set AI_BASE_URL when using the custom planner provider.")
    try:
        return _plan_openai(topic, selected_model, api_key, system_prompt, duration,
                            base_url=base_url if provider != "openai" else None)
    except Exception as exc:
        if _allow_fallback and _provider_failure(exc) and os.getenv("GEMINI_API_KEY"):
            print("OpenAI unavailable; trying Gemini planner.", flush=True)
            return plan(topic, provider="gemini", duration=duration, _allow_fallback=False)
        raise

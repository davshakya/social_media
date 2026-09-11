"""Gemini-only media requests using the REST API."""
import base64
import json
import os
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


def generate_media(prompt, model, config, kind):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("Set GEMINI_API_KEY for Gemini speech and images.")
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='')}:generateContent",
        data=json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                         "generationConfig": config}).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urlopen(request, timeout=120) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise ValueError(f"Gemini {kind} request failed (HTTP {exc.code}); check Gemini model access and quota. No other provider was used.") from exc
    for candidate in result.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData", {})
            if inline.get("mimeType", "").startswith(kind + "/") and inline.get("data"):
                return base64.b64decode(inline["data"], validate=True), inline["mimeType"]
    raise ValueError(f"Gemini returned no {kind} data; check model support or content blocking.")


def speech(text, destination):
    from .audio import write_wave
    data, mime = generate_media(
        "Read this Hinglish narration naturally, preserving Hindi and English words: " + text,
        os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts"),
        {"responseModalities": ["AUDIO"], "speechConfig": {
            "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": os.getenv("GEMINI_TTS_VOICE", "Kore")}}}},
        "audio",
    )
    if "L16" not in mime or "rate=24000" not in mime or not data or len(data) % 2:
        raise ValueError(f"Unsupported Gemini PCM audio format: {mime}")
    write_wave(destination, data)


def illustration(prompt, model=None):
    model = model or os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    data, _ = generate_media(prompt, model, {"responseModalities": ["TEXT", "IMAGE"]}, "image")
    return data, model

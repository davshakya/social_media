# Verification

Verified locally on Windows with Python 3.13.3, Blender 4.5.3 LTS and FFmpeg 7.1.

- `python -m pytest -q --basetemp .tools/pytest-final-verified`: **14 passed**.
- The complete Cycles → FFmpeg pipeline produced [ice-float-preview.mp4](videos/ice-float-preview.mp4): H.264, AAC, 270 × 480, 5 fps, exactly 30 seconds and 150 decoded frames.
- Glass, molecule and density frames were visually inspected; Hindi captions render correctly.
- A Cycles diagnostic frame was rendered at 1080 × 1920. A complete 1080 × 1920 animation has not been rendered locally.
- The portable Blender installer was repaired and its repeat invocation verified. It verifies SHA-256, avoids extracting over an active Blender process, and leaves a completed installation intact.
- Experimental Eevee rendering produced shadow-buffer errors and blank frames on the local Intel driver. That option was removed; the application uses Cycles. Failed diagnostic artifacts remain in their job directories.
- API planning is covered by a mocked contract/refusal test. Live OpenAI planning and Hindi TTS have **not** been exercised because no API key is configured. Recorded WAV and explicit no-narration audio paths were tested with real FFmpeg.

The preview contains captions, generated music and sound effects, but **no spoken narration**. Add `OPENAI_API_KEY` to `.env` and follow the README to generate narration. Full-resolution rendering on CPU can be slow.

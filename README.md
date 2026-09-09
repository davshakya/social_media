# Educational Technology Video Generator

For TechGyaan YouTube, Instagram and Facebook uploads, see [PUBLISHING.md](PUBLISHING.md).

## Voice and on-screen language

Production narration is Hinglish: natural Hindi in Devanagari with clear English science terms. Every visible caption, subtitle and 3D label is English-only. Production output uses 16-sample Cycles rendering with adaptive denoising, 30 fps H.264 at CRF 18 and 48 kHz AAC. Use preview mode only for quick review; production rendering defaults to 1080 x 1920.

Turn an educational technology topic into a Hinglish storyboard, Blender animation, narration, captions, music and a **2-minute vertical MP4**. The series covers Python, coding tips, data science, AI, machine learning, and related technology. Use `--duration 120` for 2 minutes, `--duration 150` for 2.5 minutes, or `--duration 180` for 3 minutes. Production defaults to 1080 × 1920; use `--resolution 320` for 320 × 568, `--resolution 480` for 480 × 853, or `--resolution 720` for 720 × 1280 HD. The animation library includes code flow, data charts, neural networks, algorithm steps, floating ice, molecules, density, and oil/water separation.

## Windows quick start

Run in PowerShell from this directory. Python 3.11+ is required.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
# Download a portable Blender 4.5 build with SHA-256 verification:
.\.venv\Scripts\python.exe scripts/install_blender.py
.\.venv\Scripts\python.exe science_video_generator.py doctor
```

Alternatively install Blender 4.5 LTS yourself and set `BLENDER_PATH` in `.env`. FFmpeg is supplied by `imageio-ffmpeg`; an installed build with libass can be selected with `FFMPEG_PATH`. No global PATH changes are needed.

The default Windows font is **Nirmala UI**. On Linux/macOS install Noto Sans Devanagari and set `FONT_DIR` to its containing directory and `CAPTION_FONT=Noto Sans Devanagari`. Only matching Hindi font files are copied into each job for portable subtitle rendering.

### First video, without API credentials

```powershell
.\.venv\Scripts\python.exe science_video_generator.py demo
.\.venv\Scripts\python.exe science_video_generator.py generate --storyboard examples/ice_float.json --preview --silent
```

This produces a **270 × 480, 5 fps, 30-second preview** with English-only captions and generated background audio. It is visibly labeled `SILENT PREVIEW`; it does not contain narration. Remove `--preview` for production at 30 fps. Production defaults to 1080 × 1920; use `--resolution 480` for 480 × 853 or `--resolution 720` for 720 × 1280 HD. Full rendering is substantially slower on CPU. `--still` renders one diagnostic image per scene instead of an MP4.

For recorded narration, render the included voice tracks at 480p with:

```powershell
.\.venv\Scripts\python.exe science_video_generator.py generate --storyboard examples\ice_float.json --voice-dir voice_tracks\ice_float --resolution 480
```

For a faster 480p render, use Blender Eevee and render independent scenes concurrently:

```powershell
.\.venv\Scripts\python.exe science_video_generator.py generate --storyboard examples\ice_float.json --voice-dir voice_tracks\ice_float --resolution 480 --fast --workers 2
```

`--fast` uses Eevee instead of the default Cycles renderer. `--workers 2` runs two Blender processes at the same time; try `--workers 4` only if the computer has enough CPU cores and memory. Higher worker counts do not always improve speed. Omit both options for the highest-quality default Cycles render.

Each job writes `blender.log` and `ffmpeg.log` in its job folder. Watch Blender while it renders with `Get-Content .\videos\<job-id>\blender.log -Wait`. The job is ready when `manifest.json` reports `"status": "complete"` and `final.mp4` exists.

### Hinglish narration and AI topic planning

#### Use multiple AI providers

The planner and narrator are separate. You can use Gemini, OpenAI, OpenRouter, Groq, Together, or another compatible provider to create the storyboard, then use OpenAI TTS, Edge TTS, or recorded WAV files for narration.

Each video can optionally include a topic-related AI background image. It uses the OpenAI Images API while the trusted Blender diagrams remain in front; the image receives a subtle animated zoom. Add these settings to `.env`:

```env
TOPIC_IMAGE_PROVIDER=openai
TOPIC_IMAGE_API_KEY=your-openai-image-key
TOPIC_IMAGE_MODEL=gpt-image-1
```

`TOPIC_IMAGE_API_KEY` falls back to `OPENAI_API_KEY`. If image generation fails, the video still renders with procedural visuals and the job manifest records the fallback. Disable it with `TOPIC_IMAGE_PROVIDER=none`. Image generation adds a separate API cost to each video.

Never commit API keys. Add the provider settings to your local `.env` file. For Gemini:

```env
GEMINI_API_KEY=your-gemini-api-key
AI_PLANNER_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash
GEMINI_FALLBACK_MODEL=gemini-flash-lite-latest
```

When both providers are configured, planning tries Gemini first. Credit, quota, rate-limit, timeout, and connectivity failures automatically retry with the fallback Gemini model and then OpenAI. A model that returns invalid storyboard content is reported for correction instead of silently switching providers.

Generate and validate a Gemini storyboard:

```powershell
.\.venv\Scripts\python.exe science_video_generator.py plan "Why does ice float on water?" --provider gemini --out examples\gemini_story.json
.\.venv\Scripts\python.exe science_video_generator.py validate examples\gemini_story.json
```

Render it with OpenAI narration:

```powershell
# Put OPENAI_API_KEY in .env before running this command.
.\.venv\Scripts\python.exe science_video_generator.py generate --storyboard examples\gemini_story.json --resolution 480 --fast --topic-image openai
```

On PowerShell, set `OPENAI_API_KEY` in `.env` instead of placing it on the command line. To use another narrator, use recorded audio or Edge TTS:

```powershell
# Recorded narration: one PCM WAV file per scene, named 01.wav, 02.wav, ...
.\.venv\Scripts\python.exe science_video_generator.py generate --storyboard examples\gemini_story.json --voice-dir recordings --resolution 480

# Generate narration without an OpenAI key
.\.venv\Scripts\python.exe -m pip install -e ".[voice]"
.\.venv\Scripts\python.exe scripts\generate_hinglish_voice.py examples\gemini_story.json --output voice_tracks\gemini_story
.\.venv\Scripts\python.exe science_video_generator.py generate --storyboard examples\gemini_story.json --voice-dir voice_tracks\gemini_story --resolution 480
```

For OpenAI-compatible planners, set `AI_API_KEY`, `AI_PLANNER_PROVIDER`, and `AI_PLANNER_MODEL` in `.env`. Supported providers are `openai`, `openrouter`, `groq`, `together`, and `custom`. Set `AI_BASE_URL` for `custom`.

```powershell
# Render the included script with Hinglish AI speech:
.\.venv\Scripts\python.exe science_video_generator.py generate --storyboard examples/ice_float.json

# Plan and inspect a new supported topic before rendering:
.\.venv\Scripts\python.exe science_video_generator.py plan "Why does ice float on water?" --out examples/my_story.json
.\.venv\Scripts\python.exe science_video_generator.py validate examples/my_story.json
.\.venv\Scripts\python.exe science_video_generator.py generate --storyboard examples/my_story.json

# Or run the complete pipeline in one command:
.\.venv\Scripts\python.exe science_video_generator.py generate --topic "Why does ice float on water?"
```

These commands use paid API requests. The integration uses [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) and [text-to-speech](https://developers.openai.com/api/docs/guides/text-to-speech). AI narration is labeled on the video. Review generated scientific claims and pronunciation before sharing.

You can use recorded narration without any API: put PCM WAV files named `01.wav` through `05.wav` in a directory, matching the storyboard scenes, then pass `--voice-dir recordings` with `--storyboard`. Pass `--music path/to/music.mp3` to use your own background track. Otherwise a quiet original tonal bed and transition chimes are generated locally.

### Hinglish voice without OpenAI credits

The included Python script uses [edge-tts](https://github.com/rany2/edge-tts), Microsoft's online neural voice service, to generate the numbered WAV files automatically. It does not use an OpenAI key, but it does require an internet connection. The default `hi-IN-SwaraNeural` voice speaks the Hindi portions naturally and keeps English science terms audible; `hi-IN-MadhurNeural` is available as a male alternative. Listen to the tracks before publishing, especially technical names.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[voice]"
.\.venv\Scripts\python.exe scripts\generate_hinglish_voice.py examples\ice_float.json --output voice_tracks\ice_float
.\.venv\Scripts\python.exe science_video_generator.py generate --storyboard examples\ice_float.json --voice-dir voice_tracks\ice_float
```

Use `--voice hi-IN-MadhurNeural` to switch voices, `--rate +5%` for a faster delivery, and `--overwrite` only when replacing an existing set of tracks.

## Publish to TechGyaan accounts

The configured destinations are:

| Platform  | Destination                                    |
| --------- | ---------------------------------------------- |
| YouTube   | `https://www.youtube.com/@TechGyaan_India`   |
| Instagram | `https://www.instagram.com/techgyaan_india/` |
| Facebook  | TechGyaan Page`61593902113213`               |

Publishing is supported through the official YouTube Data API and Meta Graph API. Install the optional dependencies and create a local `.env` file from the templates. Never commit `.env`, OAuth tokens, or access tokens.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[publish]"
Copy-Item .env.example .env
Get-Content .env.publishing.example | Add-Content .env
```

### YouTube setup

1. In [Google Cloud Console](https://console.cloud.google.com/), select the project used for this publisher.
2. Open **APIs & Services → Library**, search for **YouTube Data API v3**, and click **Enable**.
3. Open **Google Auth Platform → Branding** and complete the required app information:
   - App name: `TechGyaan Video Publisher`
   - User support email: the Google account that owns or manages TechGyaan
   - Developer contact email: the same account
4. Open **Audience**, choose **External**, and add the Google account as a **Test user**. Keep the app in **Testing** mode; verification is not needed for this personal test workflow.
5. Open **Google Auth Platform → Clients → Create client**, choose **Desktop app**, and download the JSON file.
6. Replace the empty placeholder, if present, with the downloaded file at `.secrets/youtube-client.json`.

The TechGyaan channel is a Brand Account. During OAuth, choose the Brand Account connected to TechGyaan, not a different personal channel. The channel URL and handle must be `@TechGyaan_India`. If the wrong channel was authorized, delete only the local token and repeat OAuth; do not delete the other YouTube channel.

```powershell
Remove-Item .\.secrets\youtube-token.json -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe science_video_generator.py publish login-youtube
.\.venv\Scripts\python.exe science_video_generator.py publish check --online --platform youtube
```

The login opens a browser and saves the refresh token locally at `.secrets/youtube-token.json`. A successful check prints `OK youtube`. If it reports that the connected channel does not match, sign in again and select the TechGyaan Brand Account. The Google account must be an owner or manager of that Brand Account.

### Facebook and Instagram setup

Instagram publishing requires a **Professional Instagram account** linked to the configured Facebook Page. A personal Instagram account cannot publish Reels through this integration. The Meta token must be a **Page access token**, not a password, app token, or ordinary user token.

1. Register at [Meta for Developers](https://developers.facebook.com/), if necessary.
2. Open **My Apps → Create App** and create a Business or Other app named `TechGyaan Video Publisher`.
3. Add the Facebook Login and Instagram API/Graph API products if Meta requests them.
4. Confirm that the TechGyaan Facebook Page is owned or managed by the Facebook account used for the app.
5. Confirm that `@techgyaan_india` is a Professional Instagram account linked to that same Page.
6. Open [Graph API Explorer](https://developers.facebook.com/tools/explorer/), select the new app, generate a user access token, and grant the Page and Instagram permissions requested by Meta. Typical permissions include:
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
   - `pages_manage_metadata`
   - `instagram_basic`
   - `instagram_content_publish`
7. In Graph API Explorer, request:

```text
/me/accounts?fields=id,name,access_token,instagram_business_account{id,username}
```

8. Find the TechGyaan Page and copy its returned `access_token`. This is the Page token required by this project. Do not paste it into chat or commit it.
9. Add the token and the Graph API version to `.env`:

```env
META_GRAPH_VERSION=v25.0
META_PAGE_ACCESS_TOKEN=paste_the_page_access_token_here
```

Use the current version available to your Meta app if `v25.0` is no longer available. The configured Page ID is `61593902113213`, and the provider verifies both that Page and its linked Instagram username before any upload.

### Check and publish

Check configuration without making network calls:

```powershell
.\.venv\Scripts\python.exe science_video_generator.py publish check
```

Check one provider online:

```powershell
.\.venv\Scripts\python.exe science_video_generator.py publish check --online --platform youtube
.\.venv\Scripts\python.exe science_video_generator.py publish check --online --platform facebook
.\.venv\Scripts\python.exe science_video_generator.py publish check --online --platform instagram
```

Publish a completed production render. YouTube visibility can be `public`, `private`, or `unlisted`; Instagram and Facebook uploads are sent when those platforms are selected.

```powershell
.\.venv\Scripts\python.exe science_video_generator.py publish video videos\<job-id>\final.mp4 --platform youtube --title "Science video" --description "Hindi science short" --visibility private --made-for-kids no
.\.venv\Scripts\python.exe science_video_generator.py publish video videos\<job-id>\final.mp4 --platform all --title "Science video" --description "Hindi science short" --visibility private --made-for-kids no
```

Use `--platform youtube`, `instagram`, `facebook`, or `all`. Title, description, and audience declaration are required. Any valid vertical production resolution is preserved during upload. Preview jobs are rejected:

```powershell
.\.venv\Scripts\python.exe science_video_generator.py publish video videos\<job-id>\final.mp4 --platform youtube --title "Ice floats on water" --description "Hindi science short" --visibility unlisted --made-for-kids no
```

Videos are published at their original resolution. The upload package does not upscale the source; use a production render rather than `--preview`.

```powershell
\.\.venv\Scripts\python.exe science_video_generator.py publish video videos\<job-id>\final.mp4 --platform youtube --title "Technology lesson" --description "A practical technology lesson." --visibility private --made-for-kids no
```

YouTube visibility applies to YouTube uploads. Receipts are written to `publishing\<job-id>\receipts.json`; this directory is ignored by Git. If a platform fails after another platform has succeeded, inspect the receipts and retry only the failed platform rather than publishing all platforms again.

## Timing and outputs

Each narration segment is synthesized and measured separately. Its share of the total speech duration determines its scene length. Cumulative frame rounding avoids drift; FFmpeg adjusts speech tempo to fill the requested 30, 120, 150, or 180 seconds without cutting off the last sentence. Extreme tempo changes (outside 0.67–1.5×) fail with guidance to revise the script.

Captions are drawn from the supplied script. Phrase timings are interpolated within measured scene boundaries; they are **not forced-aligned word timestamps**. Devanagari shaping is handled by FFmpeg/libass, outside Blender's text engine.

Every invocation creates a unique directory under `videos/`:

| File                               | Purpose                                       |
| ---------------------------------- | --------------------------------------------- |
| `final.mp4`                      | Completed vertical video                      |
| `storyboard.json`                | Validated narration and visual plan           |
| `job.json`                       | Measured timing and exact frame ranges        |
| `voice.wav`                      | Fitted full narration                         |
| `captions.srt`, `captions.ass` | Sidecar subtitles and styled burn-in captions |
| `scene-01.blend`, etc.           | Editable reusable Blender scenes              |
| `frames/`                        | Rendered PNG sequence                         |
| `music.wav`, `sfx.wav`         | Generated background audio                    |
| `manifest.json`                  | Running, completed, or failed status          |
| `blender.log`, `ffmpeg.log`    | Diagnostics                                   |

Failed jobs retain artifacts. Retry by rerunning the command (a new job is created). There is no automatic render resume. Daily jobs can upload to YouTube automatically after a successful 1080p render; manual publishing remains available for other platforms.

## Topic queue and daily scheduling

```powershell
.\.venv\Scripts\python.exe science_video_generator.py queue schedule --days 7
.\.venv\Scripts\python.exe science_video_generator.py queue list
.\.venv\Scripts\python.exe science_video_generator.py queue daily --provider gemini --fast --resolution 1080 --duration 120
```

`queue daily` selects the next unused topic from the AI, machine learning, data science, Python, and coding series, asks the configured planner to create a validated 2-minute storyboard, renders one animated video, uploads it to YouTube, and keeps only the two newest completed jobs. It also writes `social_metadata.json` containing the hook, CTA, and hashtags. Automatic upload requires YouTube OAuth setup (`publish login-youtube`) and a production render of at least 1080 × 1920. Use `--duration 180` for 3-minute videos, `--no-upload` for local-only renders, or `--resolution 320` for a small 320 × 568 video. For Gemini planning with AI narration, configure both `GEMINI_API_KEY` and `OPENAI_API_KEY`; use `--silent` or `--voice-dir` if you do not want OpenAI TTS.

Daily YouTube uploads are public by default. Set `YOUTUBE_VISIBILITY=private` or `unlisted` in `.env` when testing.

To generate a 3-minute daily video manually:

```powershell
python science_video_generator.py queue daily --provider gemini --fast --resolution 1080 --duration 180
```

### Manual video generation

If `--topic` is omitted, the command automatically selects a random topic from the curated Python, coding, data science, AI, and machine learning series.

```powershell
python science_video_generator.py generate `
   --provider gemini `
   --duration 120 `
   --resolution 1080 `
   --fast
```

Generate a 2-minute video directly from a new Gemini topic without using the queue:

```powershell
.\.venv\Scripts\python.exe science_video_generator.py generate `
   --topic "What is machine learning?" `
   --provider gemini `
   --duration 120 `
   --resolution 1080 `
   --fast
```

Generate a 3-minute video:

```powershell
.\.venv\Scripts\python.exe science_video_generator.py generate `
   --topic "How does Python automation save time?" `
   --provider gemini `
   --duration 180 `
   --resolution 1080 `
   --fast
```

To render an existing storyboard without uploading it to YouTube:

```powershell
.\.venv\Scripts\python.exe science_video_generator.py generate `
   --storyboard examples\gemini_story.json `
   --duration 120 `
   --resolution 1080 `
   --fast
```

```powershell
.\.venv\Scripts\python.exe science_video_generator.py queue add "Why does ice float on water?" --due 2026-09-07
.\.venv\Scripts\python.exe science_video_generator.py queue list
.\.venv\Scripts\python.exe science_video_generator.py queue run --limit 1
```

Use Windows Task Scheduler to run the following daily at 21:00 (9:00 PM) local time:

- Program: `powershell.exe`
- Arguments: `-NoProfile -ExecutionPolicy Bypass -File "D:\social_media\scripts\run_daily.ps1"`
- Start in: `D:\social_media`

Create the task directly from PowerShell:

```powershell
schtasks.exe /Create `
   /TN "Social Media Daily Video" `
   /TR 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\social_media\scripts\run_daily.ps1"' `
   /SC DAILY /ST 21:00 /F
```

Test and inspect the task:

```powershell
Start-ScheduledTask -TaskName "Social Media Daily Video"
Get-ScheduledTaskInfo -TaskName "Social Media Daily Video"
```

Remove it when needed:

```powershell
schtasks.exe /Delete /TN "Social Media Daily Video" /F
```

The script reads `.env`, uses `AI_PLANNER_PROVIDER` to choose the planner, uploads each successful production video to YouTube, and writes jobs under `videos\`. Complete YouTube login once before enabling the task:

```powershell
.\.venv\Scripts\python.exe science_video_generator.py publish login-youtube
```

To run Gemini explicitly, set `AI_PLANNER_PROVIDER=gemini` and `GEMINI_API_KEY` in `.env` before enabling the task. Add `--no-upload` to `queue daily` when testing locally.

No task is automatically registered. Use `queue schedule --days 7` to prefill a week, or run `queue daily` once per day. SQLite claims are transactional so concurrent workers cannot take the same pending item. Failed items require `queue retry ID`. A killed worker can leave an item running; stop that worker before using `queue retry ID`. Queue planning requires a configured planner API key, even if rendering with `--silent`.

## Extending the scene library

`science_video/blender_engine.py` contains reusable procedural scenes for code flow, data charts, neural networks, algorithm steps, glass cutaways, molecules, density, camera and lighting. They generate editable `.blend` scenes without requiring external asset downloads. The educational technology visuals are explanatory diagrams, not full software simulations.

AI output is validated by `science_video/storyboard.py`; Blender dispatches only known action names. AI never supplies executable Python. Add a trusted action handler, extend the `Action` literal and planner capability prompt together, and include a validated example before enabling a new topic. Arbitrary AI-generated Blender code is intentionally not supported.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe science_video_generator.py generate --storyboard examples/ice_float.json --preview --silent
```

Tests cover invalid plans, Hindi serialization, real FFmpeg audio fitting, caption escaping and timing, missing API credentials, and concurrent queue claims. Rendering uses Blender Cycles with CPU support and denoising; a GPU is not required.

If Windows denies access to its shared pytest temporary directory, use a fresh workspace directory: `python -m pytest -q --basetemp .tools/pytest-local-1`.

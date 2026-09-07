# Hindi 3D Science Video Generator

For TechGyaan YouTube, Instagram and Facebook uploads, see [PUBLISHING.md](PUBLISHING.md).

## Voice and on-screen language

Production narration is Hinglish: natural Hindi in Devanagari with clear English science terms. Every visible caption, subtitle and 3D label is English-only. Production output uses 64-sample Cycles rendering with adaptive denoising, 30 fps H.264 at CRF 18 and 48 kHz AAC. Use preview mode only for quick review; production rendering is 1080 x 1920.

Turn a supported science topic into a Hindi storyboard, Blender animation, narration, captions, music and a **30-second, 1080 × 1920 MP4**. The first version includes floating ice, camera movement, schematic water molecules, a density comparison, and separated oil/water.

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

This produces a **270 × 480, 5 fps, 30-second preview** with English-only captions and generated background audio. It is visibly labeled `SILENT PREVIEW`; it does not contain narration. Remove `--preview` for 1080 × 1920 at 30 fps. Full rendering is substantially slower on CPU. `--still` renders one diagnostic image per scene instead of an MP4.

### Hinglish narration and AI topic planning

Set `OPENAI_API_KEY` in `.env` (never commit it). Models and voice can be changed through `OPENAI_MODEL`, `OPENAI_TTS_MODEL`, and `OPENAI_TTS_VOICE`.

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

Publish a completed render. Start with YouTube `private` or `unlisted`; Instagram and Facebook uploads are sent when those platforms are selected.

```powershell
.\.venv\Scripts\python.exe science_video_generator.py publish video videos\<job-id>\final.mp4 --platform youtube --visibility private
.\.venv\Scripts\python.exe science_video_generator.py publish video videos\<job-id>\final.mp4 --platform all --visibility private
```

Use `--platform youtube`, `instagram`, `facebook`, or `all`. Optional metadata flags are available:

```powershell
.\.venv\Scripts\python.exe science_video_generator.py publish video videos\<job-id>\final.mp4 --platform youtube --title "बर्फ पानी पर क्यों तैरती है?" --description "Hindi science short" --visibility unlisted
```

YouTube visibility applies to YouTube uploads. Receipts are written to `publishing\<job-id>\receipts.json`; this directory is ignored by Git. If a platform fails after another platform has succeeded, inspect the receipts and retry only the failed platform rather than publishing all platforms again.

## Timing and outputs

Each narration segment is synthesized and measured separately. Its share of the total speech duration determines its scene length. Cumulative frame rounding avoids drift; FFmpeg adjusts speech tempo to fill exactly 30 seconds without cutting off the last sentence. Extreme tempo changes (outside 0.67–1.5×) fail with guidance to revise the script.

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

Failed jobs retain artifacts. Retry by rerunning the command (a new job is created). There is no automatic render resume. Publishing is a separate explicit command and does not run automatically after generation or from the topic queue.

## Topic queue and daily scheduling

```powershell
.\.venv\Scripts\python.exe science_video_generator.py queue add "Why does ice float on water?" --due 2026-09-07
.\.venv\Scripts\python.exe science_video_generator.py queue list
.\.venv\Scripts\python.exe science_video_generator.py queue run --limit 1
```

Use Windows Task Scheduler to run the following daily at 07:00 local time:

- Program: absolute path to `.venv\Scripts\python.exe`
- Arguments: `"D:\social_media\science_video_generator.py" queue run --limit 1`
- Start in: `D:\social_media`

No task is automatically registered. Increase `--limit` to generate a batch of due topics. SQLite claims are transactional so concurrent workers cannot take the same pending item. Failed items require `queue retry ID`. A killed worker can leave an item running; stop that worker before using `queue retry ID`. Queue planning requires an API key, even if rendering with `--silent`.

## Extending the scene library

`science_video/blender_engine.py` contains reusable procedural `create_glass`, `create_water`, `create_ice`, `create_molecule`, camera and lighting functions. They generate editable `.blend` scenes without requiring external asset downloads. The initial glass is an outlined scientific cutaway, and the molecule layout is a labeled schematic rather than an atomistic simulation.

AI output is validated by `science_video/storyboard.py`; Blender dispatches only known action names. AI never supplies executable Python. Add a trusted action handler, extend the `Action` literal and planner capability prompt together, and include a validated example before enabling a new topic. Pressure cookers, fans, human anatomy, steam and other assets from the longer-term proposal are not implemented in this first version.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe science_video_generator.py generate --storyboard examples/ice_float.json --preview --silent
```

Tests cover invalid plans, Hindi serialization, real FFmpeg audio fitting, caption escaping and timing, missing API credentials, and concurrent queue claims. Rendering uses Blender Cycles with CPU support and denoising; a GPU is not required.

If Windows denies access to its shared pytest temporary directory, use a fresh workspace directory: `python -m pytest -q --basetemp .tools/pytest-local-1`.

# Publish TechGyaan videos

The app supports YouTube uploads, Instagram Reels and Facebook Page Reels. Your destinations are saved in [config/social_accounts.json](config/social_accounts.json). An authenticated identity check runs before upload. Public account links alone do not grant access.

The current 270p, 5 fps preview is not upload-ready. Use a narrated production video or an existing finished vertical MP4. No videos have been published during implementation.

## Account setup

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[publish,dev]"
.\.venv\Scripts\python.exe science_video_generator.py publish check
```

Add [.env.publishing.example](.env.publishing.example) settings to your existing `.env`. Keep actual tokens local; do not paste them into chat. `.secrets/` and generated publishing packages are ignored by source control.

### YouTube

Create a Google Cloud project, enable YouTube Data API v3, configure OAuth consent, and create a **Desktop app** OAuth client. Save the downloaded JSON to `.secrets/youtube-client.json`. For an app in testing, add the Google account managing your channel as a test user.

```powershell
.\.venv\Scripts\python.exe science_video_generator.py publish login-youtube
.\.venv\Scripts\python.exe science_video_generator.py publish check --online --platform youtube
```

Login opens Google's authorization page. Select TechGyaan's managing account/channel. The app requests upload/read-only scopes, stores the token locally and checks the channel against `@TechGyaan_India`. [Google upload guide](https://developers.google.com/youtube/v3/guides/uploading_a_video).

Certain unverified API projects are restricted to private uploads until they pass Google's audit. The uploader records the visibility returned by YouTube. [YouTube API restrictions](https://developers.google.com/youtube/v3/docs/videos).

### Instagram and Facebook

This implementation uses **Facebook Login for Business and a Page access token** for both Meta platforms, rather than the separate Instagram Login token flow.

1. Confirm that `61593902113213` is the TechGyaan **Page ID**. The `/people/` URL format does not establish eligibility. Personal-profile posting is not implemented.
2. Make `techgyaan_india` a professional Instagram account and link it to that Page.
3. Configure a Meta app with Facebook Login for Business and the appropriate access: `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`, `instagram_basic`, and `instagram_content_publish`. Resolve any additional business permissions/App Review requirements in the Meta app dashboard.
4. Obtain a **Page access token** for that Page via your Meta app. Set `META_PAGE_ACCESS_TOKEN` locally and `META_GRAPH_VERSION` to the version enabled for your app.

```powershell
.\.venv\Scripts\python.exe science_video_generator.py publish check --online --platform facebook
.\.venv\Scripts\python.exe science_video_generator.py publish check --online --platform instagram
```

Instagram uploads a local file through a resumable container, waits for processing, then publishes. Facebook uses Reels start/upload/finish. No public video-hosting server is needed. See [Meta's Instagram sample](https://github.com/fbsamples/reels_publishing_apis/tree/main/insta_reels_publishing_api_sample) and [Facebook Reels reference](https://www.postman.com/meta/facebook/documentation/r56bjfd/facebook-api).

Meta authentication currently uses a manually configured local Page token; there is no Meta browser-login UI or automatic token renewal. Replace expired/revoked tokens locally.

## Prepare a post

Review [examples/ice_float_post.json](examples/ice_float_post.json): Hindi title, description, hashtags and YouTube visibility. Set `made_for_kids` to `true` or `false` for the intended audience; `null` deliberately requires this decision. Edit the AI-voice disclosure if using recorded speech.

```powershell
# Requires OPENAI_API_KEY for Hindi speech:
.\.venv\Scripts\python.exe science_video_generator.py generate --storyboard examples/ice_float.json
# Replace YOUR-JOB with the actual completed job:
.\.venv\Scripts\python.exe science_video_generator.py publish prepare videos/YOUR-JOB/final.mp4 --metadata examples/ice_float_post.json
```

Preparation does not upload anything. It rejects failed/preview jobs and makes a separate 1080×1920, 30 fps H.264/AAC MP4 with 48 kHz, 128 kbps audio. The original stays intact. `publishing/post-.../post.json` contains reviewable metadata, destinations and a video hash. The first workflow accepts 3–60 second vertical sources at least 1080×1920 and 23–60 fps. `--allow-silent` permits completed production jobs without narration, but cannot bypass preview resolution/frame-rate checks.

## Publish and track

Review the prepared file, then use the actual package path:

```powershell
.\.venv\Scripts\python.exe science_video_generator.py publish send publishing/post-EXAMPLE/post.json --platform youtube
.\.venv\Scripts\python.exe science_video_generator.py publish send publishing/post-EXAMPLE/post.json --platform all
.\.venv\Scripts\python.exe science_video_generator.py publish history
.\.venv\Scripts\python.exe science_video_generator.py publish status
```

`send` uploads/posts content. Instagram/Facebook use their normal public publishing flow; `youtube_visibility` affects only YouTube. `all` verifies all selected accounts before any upload. Use `youtube` while only that account is connected.

The one-command interface is also supported: `publish video PATH --platform youtube --title "TITLE" --description "CAPTION" --visibility private --made-for-kids no`. It prepares a package and uploads immediately.

SQLite tracks each platform/account/video hash. Rerunning skips successful uploads. Timeouts/interruption block blind retries because the service might already have accepted the post. Inspect `history`, `status` and the creator interface. Only after confirming that nothing was published and no worker is active, run `publish resolve-not-published KEY` and retry. Keep the ledger; deleting it removes duplicate protection.

Facebook initially returns `submitted`; YouTube returns `uploaded`. These are not claims of completed processing/public visibility. `status` reads the remote state. Instagram returns a post ID after publication. Social scheduling, automatic recovery of interrupted byte transfers and guaranteed platform acceptance are not implemented.

## Verification scope

Tests cover encoding, media rejection, metadata/audience validation, account mismatch, upload host validation, partial failure, credential redaction and concurrent duplicate protection. Publishing calls are mocked until suitable authorized content is available. YouTube identity was checked live; Meta credentials remain unconfigured.

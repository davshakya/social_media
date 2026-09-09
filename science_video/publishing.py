"""Prepare local upload packages, verify destinations, and track independent uploads."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Literal
from uuid import uuid4

import imageio_ffmpeg
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .runtime import ROOT, executable, run

PLATFORMS = ("youtube", "instagram", "facebook")
ACCOUNTS = ROOT / "config" / "social_accounts.json"


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2200)
    tags: list[str] = Field(max_length=20)
    youtube_visibility: Literal["public", "private", "unlisted"]
    made_for_kids: bool

    @model_validator(mode="after")
    def check_text(self):
        if not self.title.strip() or not self.description.strip() or any(c in self.title for c in "<>"):
            raise ValueError("Use a nonempty title/caption, without angle brackets in the title.")
        if any(not t.strip() for t in self.tags) or sum(len(t)+1 for t in self.tags) > 450:
            raise ValueError("Keep combined nonempty tags under 450 characters.")
        return self


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def media_info(path):
    reader = imageio_ffmpeg.read_frames(str(path))
    try:
        return next(reader)
    finally:
        reader.close()


def check_media(info, *, allow_low_resolution=False):
    width, height = info["size"]
    if abs(width/height - 9/16) > 0.001:
        raise ValueError("Publish a vertical video with a 9:16 aspect ratio.")
    if not 23 <= info.get("fps", 0) <= 60:
        raise ValueError("Publishing requires 23–60 fps; generate without --preview.")
    if not 3 <= info.get("duration", 0) <= 180:
        raise ValueError("This publishing workflow supports 3–180 second Shorts/Reels.")
    if not info.get("audio_codec"):
        raise ValueError("The video needs an audio track before publishing.")


def prepare(video, metadata_path, output, *, allow_silent=False, allow_low_resolution=False):
    video = Path(video).resolve()
    if not video.is_file():
        raise ValueError(f"Video not found: {video}")
    metadata = Metadata.model_validate_json(Path(metadata_path).read_text(encoding="utf-8-sig"))
    manifest = video.parent / "manifest.json"
    if manifest.exists():
        job = json.loads(manifest.read_text(encoding="utf-8"))
        if job.get("status") != "complete" or job.get("preview"):
            raise ValueError("Only completed production jobs can be prepared for publishing.")
        if job.get("silent") and not allow_silent:
            raise ValueError("This job has no narration. Provide a narrated video or explicitly pass --allow-silent.")
    check_media(media_info(video), allow_low_resolution=allow_low_resolution)
    folder = Path(output).resolve() / ("post-" + uuid4().hex[:12])
    folder.mkdir(parents=True)
    target = folder / "video.mp4"
        # Preserve the source resolution; publishing does not upscale the video.
    run([executable("ffmpeg"), "-y", "-i", video, "-map", "0:v:0", "-map", "0:a:0",
            "-vf", "setsar=1", "-r", "30", "-c:v", "libx264", "-preset", "fast",
         "-crf", "20", "-maxrate", "12M", "-bufsize", "24M", "-g", "60", "-flags", "+cgop",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
         "-movflags", "+faststart", "-use_editlist", "0", target], log=folder / "encoding.log")
    run([executable("ffmpeg"), "-v", "error", "-xerror", "-i", target, "-f", "null", "-"], log=folder / "encoding.log")
    if target.stat().st_size > 1_000_000_000:
        raise ValueError("Encoded video exceeds the 1 GB package limit")
    package = {"version": 1, "video": str(target), "sha256": digest(target), "source": str(video),
               "allow_low_resolution": allow_low_resolution,
               "metadata": metadata.model_dump(), "accounts": json.loads(ACCOUNTS.read_text(encoding="utf-8")),
               "media": media_info(target)}
    path = folder / "post.json"
    path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_package(path):
    package = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if package.get("version") != 1:
        raise ValueError("Unknown publishing package version")
    package["metadata"] = Metadata.model_validate(package["metadata"]).model_dump()
    if package["accounts"] != json.loads(ACCOUNTS.read_text(encoding="utf-8")):
        raise ValueError("Package destinations differ from config/social_accounts.json; prepare a new package.")
    if digest(package["video"]) != package["sha256"]:
        raise ValueError("Video changed after preparation. Prepare a new package before uploading.")
    check_media(media_info(package["video"]), allow_low_resolution=package.get("allow_low_resolution", False))
    return package


class Ledger:
    def __init__(self, path):
        Path(path).resolve().parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS uploads (
            key TEXT PRIMARY KEY, platform TEXT NOT NULL, account TEXT NOT NULL,
            video_hash TEXT NOT NULL, state TEXT NOT NULL, receipt TEXT, error TEXT,
            updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        self.db.commit()

    def claim(self, platform, account, video_hash):
        key = hashlib.sha256(f"{platform}:{account}:{video_hash}".encode()).hexdigest()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT * FROM uploads WHERE key=?", (key,)).fetchone()
            if row:
                if row["state"] == "complete":
                    return key, json.loads(row["receipt"])
                raise ValueError(f"Upload {key} is {row['state']}. Check publish status/history before resolving or retrying.")
            self.db.execute("INSERT INTO uploads(key,platform,account,video_hash,state) VALUES(?,?,?,?,'started')",
                            (key, platform, account, video_hash))
        return key, None

    def save(self, key, state, *, receipt=None, error=None):
        with self.db:
            self.db.execute("UPDATE uploads SET state=?,receipt=COALESCE(?,receipt),error=?,updated=CURRENT_TIMESTAMP WHERE key=?",
                            (state, json.dumps(receipt) if receipt else None, error, key))

    def rows(self):
        rows = []
        for row in self.db.execute("SELECT * FROM uploads ORDER BY updated,key"):
            result = dict(row)
            result["receipt"] = json.loads(result["receipt"]) if result["receipt"] else None
            rows.append(result)
        return rows

    def resolve_not_published(self, key):
        with self.db:
            changed = self.db.execute("DELETE FROM uploads WHERE key=? AND state IN ('uncertain','started','transferring')", (key,)).rowcount
            if not changed:
                raise ValueError("No unresolved upload with that key; completed uploads cannot be reset.")

    def close(self):
        self.db.close()


def provider(platform, accounts):
    from .social_providers import Meta, YouTube
    return YouTube(accounts) if platform == "youtube" else Meta(accounts, platform)


def accounts():
    return json.loads(ACCOUNTS.read_text(encoding="utf-8"))


def publish(video, platforms=PLATFORMS, *, title=None, description=None, tags=None,
            visibility="private", made_for_kids=None, allow_silent=False, allow_low_resolution=False):
    """One-command compatibility wrapper around package preparation and tracked uploads."""
    if made_for_kids is None:
        raise ValueError("Specify whether this video is made for kids before publishing.")
    if not title or not description:
        raise ValueError("Provide a title and description, or use publish prepare with a metadata file.")
    output = ROOT / "publishing"
    output.mkdir(exist_ok=True)
    metadata = Metadata(title=title, description=description, tags=tags or [],
                        youtube_visibility=visibility, made_for_kids=made_for_kids)
    meta_path = output / ("metadata-" + uuid4().hex + ".json")
    meta_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    package = prepare(video, meta_path, output, allow_silent=allow_silent,
                      allow_low_resolution=allow_low_resolution)
    print(f"Prepared package: {package}", flush=True)
    return send(package, platforms, output / "uploads.sqlite3")


def publish_job(video, *, platform="youtube"):
    """Publish generated job metadata and return the tracked upload report."""
    video = Path(video).resolve()
    metadata_path = video.parent / "social_metadata.json"
    if not metadata_path.is_file():
        raise ValueError(f"Generated job metadata not found: {metadata_path}")
    metadata = Metadata.model_validate_json(metadata_path.read_text(encoding="utf-8-sig"))
    report = publish(video, (platform,), title=metadata.title, description=metadata.description,
                     tags=metadata.tags, visibility=metadata.youtube_visibility,
                     made_for_kids=metadata.made_for_kids, allow_low_resolution=True)
    result = report.get(platform, {})
    if "error" in result:
        raise RuntimeError(f"{platform} upload failed: {result['error']}")
    return report


def prune_completed_jobs(output=ROOT / "videos", *, keep=2):
    """Remove older completed job folders, preserving the newest completed jobs."""
    jobs = []
    for folder in Path(output).resolve().iterdir():
        if not folder.is_dir() or not (folder / "final.mp4").is_file():
            continue
        manifest = folder / "manifest.json"
        if manifest.is_file() and json.loads(manifest.read_text(encoding="utf-8")).get("status") != "complete":
            continue
        jobs.append(folder)
    jobs.sort(key=lambda path: path.name, reverse=True)
    removed = jobs[keep:]
    for folder in removed:
        import shutil
        shutil.rmtree(folder)
    return removed


def selected(value):
    return PLATFORMS if value == "all" else (value,)


def redact_error(exc):
    # SDK exceptions can include entire URLs or OAuth payloads: never persist raw errors.
    if type(exc) is ValueError or type(exc) is RuntimeError:
        text = str(exc)
        for key in ("META_PAGE_ACCESS_TOKEN", "OPENAI_API_KEY"):
            if os.getenv(key):
                text = text.replace(os.environ[key], "[redacted]")
        return text
    return f"{type(exc).__name__}: platform request failed. Verify authorization and remote upload status."


def send(path, platforms, db, *, factory=provider):
    package = read_package(path)
    # Verify all selected destinations before making the first upload.
    providers = {p: factory(p, package["accounts"]) for p in platforms}
    ledger = Ledger(db)
    report = {}
    try:
        for platform, uploader in providers.items():
            try:
                key, existing = ledger.claim(platform, uploader.account_id, package["sha256"])
            except ValueError as exc:
                report[platform] = {"error": str(exc)}
                continue
            if existing:
                report[platform] = {"key": key, "already_uploaded": True, **existing}
                continue
            try:
                receipt = uploader.publish(package, lambda r: ledger.save(key, "transferring", receipt=r))
                ledger.save(key, "complete", receipt=receipt)
                report[platform] = {"key": key, **receipt}
            except BaseException as exc:
                ledger.save(key, "uncertain", error=redact_error(exc))
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                report[platform] = {"key": key, "error": redact_error(exc)}
    finally:
        ledger.close()
    return report


def add_cli(sub):
    p = sub.add_parser("publish", help="Prepare and publish TechGyaan videos")
    actions = p.add_subparsers(dest="publish_action", required=True)
    check = actions.add_parser("check")
    check.add_argument("--online", action="store_true", help="Read authenticated account identities; does not upload")
    check.add_argument("--platform", choices=(*PLATFORMS, "all"), default="all")
    actions.add_parser("login-youtube")
    direct = actions.add_parser("video", help="Prepare and publish a finished video in one command")
    direct.add_argument("video", type=Path)
    direct.add_argument("--platform", choices=(*PLATFORMS, "all"), default="all")
    direct.add_argument("--title", required=True)
    direct.add_argument("--description", required=True)
    direct.add_argument("--visibility", choices=("private", "unlisted", "public"), default="private")
    direct.add_argument("--made-for-kids", choices=("yes", "no"), required=True)
    direct.add_argument("--allow-silent", action="store_true")
    direct.add_argument("--allow-low-resolution", action="store_true",
                        help="Allow 320p/480p input; the upload package is still encoded at 1080p")
    prep = actions.add_parser("prepare", help="Encode a local, reviewable upload package; no upload")
    prep.add_argument("video", type=Path)
    prep.add_argument("--metadata", type=Path, required=True)
    prep.add_argument("--output", type=Path, default=ROOT / "publishing")
    prep.add_argument("--allow-silent", action="store_true")
    prep.add_argument("--allow-low-resolution", action="store_true",
                      help="Allow 320p/480p input; the upload package is still encoded at 1080p")
    upload = actions.add_parser("send", help="Upload/post the prepared package to selected platforms")
    upload.add_argument("package", type=Path)
    upload.add_argument("--platform", choices=(*PLATFORMS, "all"), required=True)
    for parser in (upload, actions.add_parser("history"), actions.add_parser("status")):
        parser.add_argument("--db", type=Path, default=ROOT / "publishing" / "uploads.sqlite3")
    reset = actions.add_parser("resolve-not-published", help="Reset ONLY after checking the remote platform for duplicates")
    reset.add_argument("key")
    reset.add_argument("--db", type=Path, default=ROOT / "publishing" / "uploads.sqlite3")


def run_cli(args):
    action = args.publish_action
    if action == "video":
        result = publish(args.video, selected(args.platform), title=args.title, description=args.description,
                         visibility=args.visibility, made_for_kids=args.made_for_kids == "yes",
                         allow_silent=args.allow_silent, allow_low_resolution=args.allow_low_resolution)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if any("error" in r for r in result.values()) else 0
    elif action == "login-youtube":
        from .social_providers import youtube_login
        print(youtube_login())
    elif action == "prepare":
        print(prepare(args.video, args.metadata, args.output, allow_silent=args.allow_silent,
                  allow_low_resolution=args.allow_low_resolution))
    elif action == "check":
        from .social_providers import local_path
        accounts = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
        result = {"accounts": accounts, "credentials": {
            "youtube_client": local_path("YOUTUBE_CLIENT_SECRET_FILE", ".secrets/youtube-client.json").is_file(),
            "youtube_token": local_path("YOUTUBE_TOKEN_FILE", ".secrets/youtube-token.json").is_file(),
            "meta_page_token": bool(os.getenv("META_PAGE_ACCESS_TOKEN")),
            "meta_graph_version": bool(os.getenv("META_GRAPH_VERSION"))}}
        if args.online:
            result["verified_accounts"] = {}
            for platform in selected(args.platform):
                result["verified_accounts"][platform] = provider(platform, accounts).account_id
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif action == "send":
        result = send(args.package, selected(args.platform), args.db)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if any("error" in r for r in result.values()) else 0
    else:
        ledger = Ledger(args.db)
        try:
            if action == "resolve-not-published":
                ledger.resolve_not_published(args.key)
                print("Unresolved attempt reset. The same package may now be retried.")
            else:
                rows = ledger.rows()
                if action == "status":
                    accounts = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
                    for row in rows:
                        if row["receipt"]:
                            remote = provider(row["platform"], accounts)
                            if remote.account_id != row["account"]:
                                raise ValueError("Receipt belongs to a different account")
                            row["remote"] = remote.status(row["receipt"])
                print(json.dumps(rows, ensure_ascii=False, indent=2))
        finally:
            ledger.close()
    return 0

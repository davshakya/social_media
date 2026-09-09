import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from science_video import publishing as pub
from science_video.social_providers import Meta


def metadata():
    return {"title": "Science", "description": "Hindi science video", "tags": ["Science"],
            "youtube_visibility": "private", "made_for_kids": False}


def test_cli_has_one_publishing_namespace():
    from science_video.cli import parser
    assert parser().parse_args(["publish", "check"]).publish_action == "check"
    assert parser().parse_args(["publish", "send", "post.json", "--platform", "all"]).platform == "all"


@pytest.mark.parametrize("info", [
    {"size": (270,480), "fps": 5, "duration": 30, "audio_codec": "aac"},
    {"size": (1920,1080), "fps": 30, "duration": 30, "audio_codec": "aac"},
    {"size": (1080,1920), "fps": 5, "duration": 30, "audio_codec": "aac"},
    {"size": (1080,1920), "fps": 30, "duration": 181, "audio_codec": "aac"},
    {"size": (1080,1920), "fps": 30, "duration": 30},
])
def test_preview_and_incompatible_media_rejected(info):
    with pytest.raises(ValueError):
        pub.check_media(info)


def test_audience_requires_boolean():
    for value in (None, "false"):
        with pytest.raises(ValidationError):
            pub.Metadata.model_validate({**metadata(), "made_for_kids": value})


def test_concurrent_claim_and_ambiguous_result_block_duplicates(tmp_path):
    path = tmp_path / "uploads.sqlite3"
    pub.Ledger(path).close()
    def claim():
        ledger = pub.Ledger(path)
        try:
            return ledger.claim("youtube", "channel", "abc")
        except ValueError:
            return None
        finally:
            ledger.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sum(r is not None for r in results) == 1
    key = next(r[0] for r in results if r)
    ledger = pub.Ledger(path)
    ledger.save(key, "uncertain", receipt={"id": "remote-id"}, error="timeout")
    with pytest.raises(ValueError):
        ledger.claim("youtube", "channel", "abc")
    assert ledger.rows()[0]["receipt"]["id"] == "remote-id"
    ledger.resolve_not_published(key)
    assert ledger.claim("youtube", "channel", "abc")[1] is None
    ledger.save(key, "complete", receipt={"id": "published"})
    assert ledger.claim("youtube", "channel", "abc")[1]["id"] == "published"
    with pytest.raises(ValueError):
        ledger.resolve_not_published(key)
    ledger.close()


def test_partial_failure_does_not_reupload_successes(tmp_path, monkeypatch):
    monkeypatch.setattr(pub, "read_package", lambda p: {"accounts": {}, "sha256": "abc"})
    calls = []
    class Fake:
        account_id = "account"
        def __init__(self, platform):
            self.platform = platform
        def publish(self, package, record):
            calls.append(self.platform)
            record({"id": "remote-" + self.platform})
            if self.platform == "facebook":
                raise RuntimeError("timeout after submission")
            return {"id": "remote-" + self.platform, "state": "uploaded"}
    factory = lambda platform, accounts: Fake(platform)
    db = tmp_path / "uploads.sqlite3"
    first = pub.send("post.json", pub.PLATFORMS, db, factory=factory)
    assert "error" in first["facebook"]
    second = pub.send("post.json", pub.PLATFORMS, db, factory=factory)
    assert second["youtube"]["already_uploaded"]
    assert second["instagram"]["already_uploaded"]
    assert calls == list(pub.PLATFORMS)


def test_all_accounts_checked_before_first_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(pub, "read_package", lambda p: {"accounts": {}, "sha256": "abc"})
    calls = []
    def factory(platform, accounts):
        if platform == "instagram":
            raise ValueError("wrong Instagram account")
        return SimpleNamespace(account_id="a", publish=lambda *a: calls.append("uploaded"))
    with pytest.raises(ValueError, match="wrong Instagram"):
        pub.send("post.json", pub.PLATFORMS, tmp_path / "db.sqlite3", factory=factory)
    assert calls == []


def test_video_changed_after_preparation_is_rejected(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"original")
    package = {"version": 1, "video": str(video), "sha256": pub.digest(video),
               "metadata": metadata(), "accounts": pub.accounts()}
    path = tmp_path / "post.json"
    path.write_text(json.dumps(package), encoding="utf-8")
    video.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        pub.read_package(path)


@pytest.mark.parametrize("url", ["https://attacker.example/upload", "https://rupload.facebook.com.attacker.example/u",
                                "http://rupload.facebook.com/u", "https://user@rupload.facebook.com/u"])
def test_upload_never_sends_token_to_untrusted_host(url):
    meta = Meta.__new__(Meta)
    with pytest.raises(ValueError, match="host"):
        meta.upload(url, "unused.mp4")


def test_wrong_meta_identity_rejected(monkeypatch):
    monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("META_GRAPH_VERSION", "v25.0")
    monkeypatch.setattr(Meta, "call", lambda *a, **k: {"id": "different", "category": "Education"})
    with pytest.raises(ValueError, match="Page"):
        Meta(pub.accounts(), "facebook")


def test_meta_upload_order_and_submission_state():
    meta = Meta.__new__(Meta)
    meta.platform, meta.page_id, meta.account_id = "instagram", "page", "ig"
    calls, records = [], []
    responses = iter([{"id":"container", "uri":"https://rupload.facebook.com/u"},
                      {"status_code":"FINISHED"}, {"id":"post"}, {"permalink":"https://www.instagram.com/reel/post/"}])
    def call(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return next(responses)
    meta.call = call
    meta.upload = lambda url, path: calls.append(("UPLOAD", url, path))
    result = meta.publish({"metadata": metadata(), "video":"file.mp4"}, lambda r: records.append(dict(r)))
    assert [c[0] for c in calls] == ["POST", "UPLOAD", "GET", "POST", "GET"]
    assert calls[0][2]["data"]["upload_type"] == "resumable"
    assert result["state"] == "published"
    assert records[0]["container_id"] == "container"
    meta.platform = "facebook"
    responses = iter([{"video_id":"fb", "upload_url":"https://rupload.facebook.com/u"}, {"success":True}])
    result = meta.publish({"metadata": metadata(), "video":"file.mp4"}, lambda r: None)
    assert result["state"] == "submitted"


def test_raw_sdk_errors_do_not_leak_credentials(monkeypatch):
    monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "secret-token")
    assert "secret-token" not in pub.redact_error(RuntimeError("token=secret-token"))
    assert "secret-token" not in pub.redact_error(OSError("https://x?token=secret-token"))


def test_prepare_encodes_real_platform_package(tmp_path):
    from science_video.runtime import executable, run
    video = tmp_path / "source.mp4"
    run([executable("ffmpeg"), "-y", "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=24000", "-t", "3", "-c:v", "libx264",
         "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", video])
    meta = tmp_path / "metadata.json"
    meta.write_text(json.dumps(metadata()), encoding="utf-8")
    path = pub.prepare(video, meta, tmp_path / "packages")
    package = pub.read_package(path)
    assert package["media"]["size"] == [1080,1920]
    assert package["media"]["fps"] == 30
    assert package["media"]["audio_codec"] == "aac"
    assert package["metadata"]["youtube_visibility"] == "private"


def test_youtube_upload_preserves_audience_and_reports_actual_visibility(tmp_path):
    from science_video.social_providers import YouTube
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mocked media")
    youtube = YouTube.__new__(YouTube)
    captured, records = {}, []
    def insert(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(next_chunk=lambda **kwargs: (None, {"id":"video-id", "status":{"privacyStatus":"private"}}))
    youtube.api = SimpleNamespace(videos=lambda: SimpleNamespace(insert=insert))
    result = youtube.publish({"video":str(video), "metadata":{**metadata(), "youtube_visibility":"public"}}, records.append)
    assert captured["body"]["status"] == {"privacyStatus":"public", "selfDeclaredMadeForKids":False}
    assert result["visibility"] == "private"
    assert result["state"] == "uploaded"
    assert records[0]["id"] == "video-id"


def test_metadata_validation_applies_when_reviewed_package_is_edited():
    with pytest.raises(ValidationError):
        pub.Metadata.model_validate({**metadata(), "tags":["x"*451]})
    with pytest.raises(ValidationError):
        pub.Metadata.model_validate({**metadata(), "title":" "})

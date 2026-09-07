"""Official upload APIs. Credentials are used locally and never included in receipts."""
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse

from .runtime import ROOT

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]


def local_path(env, default):
    path = Path(os.getenv(env) or default).expanduser()
    return path if path.is_absolute() else ROOT / path


def youtube_login():
    from google_auth_oauthlib.flow import InstalledAppFlow
    client = local_path("YOUTUBE_CLIENT_SECRET_FILE", ".secrets/youtube-client.json")
    target = local_path("YOUTUBE_TOKEN_FILE", ".secrets/youtube-token.json")
    if not client.is_file():
        raise ValueError(f"Save your Google Desktop OAuth client JSON at {client}. See PUBLISHING.md.")
    flow = InstalledAppFlow.from_client_secrets_file(str(client), scopes=SCOPES)
    credentials = flow.run_local_server(host="localhost", port=0, open_browser=True,
                                        access_type="offline", prompt="consent", timeout_seconds=300)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(credentials.to_json(), encoding="utf-8")
    return "YouTube authorization saved locally. Run publish check --online to verify the channel."


class YouTube:
    def __init__(self, accounts):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        token_file = local_path("YOUTUBE_TOKEN_FILE", ".secrets/youtube-token.json")
        if not token_file.is_file():
            raise ValueError("YouTube is not connected. Run publish login-youtube.")
        credentials = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            token_file.write_text(credentials.to_json(), encoding="utf-8")
        if not credentials.valid:
            raise ValueError("YouTube authorization expired. Run publish login-youtube again.")
        self.api = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        handle = accounts["youtube_handle"]
        expected = self.api.channels().list(part="id", forHandle="@" + handle.lstrip("@")).execute().get("items", [])
        own = self.api.channels().list(part="id,snippet", mine=True).execute().get("items", [])
        if len(expected) != 1 or not any(c["id"] == expected[0]["id"] for c in own):
            raise ValueError("Connected YouTube channel does not match @" + accounts["youtube_handle"])
        self.account_id = expected[0]["id"]

    def publish(self, package, record):
        from googleapiclient.http import MediaFileUpload
        metadata = package["metadata"]
        request = self.api.videos().insert(
            part="snippet,status", body={
                "snippet": {"title": metadata["title"], "description": metadata["description"],
                            "categoryId": "28", "defaultLanguage": "hi", "tags": metadata["tags"]},
                "status": {"privacyStatus": metadata["youtube_visibility"],
                           "selfDeclaredMadeForKids": metadata["made_for_kids"]}},
            media_body=MediaFileUpload(package["video"], mimetype="video/mp4", chunksize=8*1024*1024, resumable=True))
        response = None
        while response is None:
            _, response = request.next_chunk(num_retries=3)
        if not response.get("id"):
            raise RuntimeError("YouTube did not return an upload ID")
        receipt = {"id": response["id"], "url": f"https://www.youtube.com/watch?v={response['id']}",
                   "state": "uploaded", "visibility": response.get("status", {}).get("privacyStatus", "unknown")}
        record(receipt)
        return receipt

    def status(self, receipt):
        items = self.api.videos().list(part="status,processingDetails", id=receipt["id"]).execute().get("items", [])
        if not items:
            raise ValueError("YouTube video is not visible to the connected account")
        return {**receipt, "status": items[0].get("status"), "processing": items[0].get("processingDetails")}


class Meta:
    def __init__(self, accounts, platform):
        import requests
        self.http = requests.Session()
        self.token = os.getenv("META_PAGE_ACCESS_TOKEN", "")
        version = os.getenv("META_GRAPH_VERSION", "")
        if not self.token or not re.fullmatch(r"v\d+\.\d+", version):
            raise ValueError("Set META_PAGE_ACCESS_TOKEN and META_GRAPH_VERSION in .env. See PUBLISHING.md.")
        self.base = "https://graph.facebook.com/" + version
        self.platform = platform
        page = self.call("GET", "/me", params={"fields": "id,name,category,instagram_business_account{id,username}"})
        if page.get("id") != accounts["facebook_page_id"] or not page.get("category"):
            raise ValueError("Meta token must belong to the configured Facebook Page; personal profiles are not supported.")
        self.page_id = page["id"]
        self.account_id = self.page_id
        if platform == "instagram":
            instagram = page.get("instagram_business_account") or {}
            if instagram.get("username", "").lower() != accounts["instagram_username"].lower() or not instagram.get("id"):
                raise ValueError("The Page must be linked to the professional Instagram account @" + accounts["instagram_username"])
            self.account_id = instagram["id"]

    def call(self, method, path, **kwargs):
        # Do not expose token-bearing URLs, response bodies, or raw request exceptions.
        try:
            response = self.http.request(method, self.base + path,
                headers={"Authorization": "Bearer " + self.token}, timeout=(15, 90), allow_redirects=False, **kwargs)
            body = response.json()
        except Exception:
            raise RuntimeError("Meta request failed or returned invalid JSON; check connectivity and account authorization") from None
        if not 200 <= response.status_code < 300 or "error" in body:
            code = body.get("error", {}).get("code", response.status_code)
            raise RuntimeError(f"Meta rejected the request (code {code}); check permissions, token expiry and app access")
        return body

    def upload(self, url, video):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "rupload.facebook.com" or parsed.port not in (None,443) or parsed.username:
            raise ValueError("Meta returned an unexpected upload host")
        video = Path(video)
        with video.open("rb") as stream:
            try:
                response = self.http.post(url, data=stream, allow_redirects=False, timeout=(15, 300), headers={
                    "Authorization": "OAuth " + self.token, "offset": "0", "file_size": str(video.stat().st_size),
                    "Content-Type": "application/octet-stream"})
                body = response.json()
            except Exception:
                raise RuntimeError("Meta binary transfer failed; inspect the saved upload ID before retrying") from None
        if not 200 <= response.status_code < 300 or body.get("success") is not True:
            raise RuntimeError("Meta did not accept the binary transfer")

    def publish(self, package, record):
        metadata = package["metadata"]
        caption = metadata["description"]
        if self.platform == "instagram":
            created = self.call("POST", f"/{self.account_id}/media", data={
                "media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true"})
            receipt = {"container_id": created["id"], "state": "upload_created"}
            record(receipt)
            self.upload(created["uri"], package["video"])
            for _ in range(60):
                status = self.call("GET", f"/{created['id']}", params={"fields": "status_code"}).get("status_code")
                if status == "FINISHED":
                    break
                if status in {"ERROR", "EXPIRED"}:
                    raise RuntimeError("Instagram rejected or expired the media container")
                time.sleep(5)
            else:
                raise RuntimeError("Instagram processing timed out; inspect the saved container before retrying")
            published = self.call("POST", f"/{self.account_id}/media_publish", data={"creation_id": created["id"]})
            receipt.update(id=published["id"], state="published")
            record(receipt)
            # A failed permalink lookup must not turn an already-published post into a failed upload.
            try:
                receipt["url"] = self.call("GET", f"/{published['id']}", params={"fields": "permalink"}).get("permalink")
            except RuntimeError:
                pass
            return receipt
        created = self.call("POST", f"/{self.page_id}/video_reels", data={"upload_phase": "start"})
        receipt = {"id": created["video_id"], "state": "upload_created"}
        record(receipt)
        self.upload(created["upload_url"], package["video"])
        response = self.call("POST", f"/{self.page_id}/video_reels", data={"upload_phase": "finish",
            "video_id": created["video_id"], "video_state": "PUBLISHED", "title": metadata["title"], "description": caption})
        if response.get("success") is not True:
            raise RuntimeError("Facebook did not acknowledge publication")
        receipt.update(state="submitted", url=f"https://www.facebook.com/reel/{created['video_id']}")
        record(receipt)
        # Submission acknowledgement is not confirmation of completed processing.
        return receipt

    def status(self, receipt):
        if self.platform == "instagram":
            if receipt.get("id"):
                return self.call("GET", f"/{receipt['id']}", params={"fields": "id,permalink"})
            return self.call("GET", f"/{receipt['container_id']}", params={"fields": "status_code,status"})
        return self.call("GET", f"/{receipt['id']}", params={"fields": "status"})

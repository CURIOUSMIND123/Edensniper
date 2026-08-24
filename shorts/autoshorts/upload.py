"""YouTube upload via the Data API.

You authorise once with `autoshorts auth-youtube`; the refresh token is
cached in the work directory and reused forever after.

Quota note: an upload costs ~1600 units of the default 10,000/day, so
roughly 6 uploads a day before YouTube itself says stop. The runner treats
that like any other quota wall and waits it out.
"""
from __future__ import annotations

import json
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_NAME = "client_secret.json"
TOKEN_NAME = "youtube_token.json"


class YouTubeNotConfigured(RuntimeError):
    pass


def _paths(cfg) -> tuple[Path, Path]:
    return cfg.work_dir / CLIENT_SECRET_NAME, cfg.work_dir / TOKEN_NAME


def authorize(cfg, log=print) -> Path:
    """Interactive one-time consent. Run this yourself, once."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    secret, token = _paths(cfg)
    if not secret.exists():
        raise YouTubeNotConfigured(
            f"Put your OAuth client secrets at {secret}\n"
            "Google Cloud Console -> APIs & Services -> Credentials ->\n"
            "Create OAuth client ID -> Desktop app -> Download JSON.\n"
            "The YouTube Data API v3 must be enabled on that project."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    try:
        creds = flow.run_local_server(port=0)
    except Exception:  # headless box / phone: fall back to copy-paste
        creds = flow.run_console()
    token.write_text(creds.to_json(), encoding="utf-8")
    log(f"authorised — token saved to {token}")
    return token


def _service(cfg):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    _, token = _paths(cfg)
    if not token.exists():
        raise YouTubeNotConfigured(
            "Not authorised yet. Run:  python -m autoshorts auth-youtube"
        )
    creds = Credentials.from_authorized_user_info(json.loads(token.read_text()), SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        token.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(cfg, path: Path, title: str, description: str, tags: list[str], log=print) -> str:
    """Resumable upload. Returns the new video id."""
    from googleapiclient.http import MediaFileUpload

    settings = cfg["youtube"]
    service = _service(cfg)

    disclosure = settings.get("disclosure") or ""
    body_description = description.strip()
    if disclosure:
        body_description = f"{body_description}\n\n{disclosure}"
    hashtags = " ".join(f"#{tag.replace(' ', '')}" for tag in tags[:3])
    body_description = f"{body_description}\n\n#Shorts {hashtags}".strip()

    body = {
        "snippet": {
            "title": title[:100],
            "description": body_description[:4900],
            "tags": [tag[:30] for tag in tags][:15],
            "categoryId": str(settings.get("category_id", "27")),
        },
        "status": {
            "privacyStatus": settings.get("privacy", "private"),
            "selfDeclaredMadeForKids": bool(settings.get("made_for_kids", False)),
        },
    }

    media = MediaFileUpload(str(path), chunksize=4 * 1024 * 1024, resumable=True,
                            mimetype="video/mp4")
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log(f"  uploading… {int(status.progress() * 100)}%")
    video_id = response["id"]
    log(f"  live at https://youtube.com/shorts/{video_id} ({body['status']['privacyStatus']})")
    return video_id

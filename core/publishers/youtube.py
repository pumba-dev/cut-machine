"""Publisher YouTube: OAuth installed-app + videos.insert resumable.

Credenciais por conta em credentials_dir(account): credentials.json (OAuth
client Desktop app, baixado do Google Cloud Console) + token.json (gerado
aqui). Imports google ficam dentro dos metodos para o pacote carregar sem as
deps instaladas.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..accounts import credentials_dir
from .base import Publisher, QuotaExceededError

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CHUNK_SIZE = 8 * 1024 * 1024
QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "uploadLimitExceeded"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _is_quota_error(exc: Any) -> bool:
    """HttpError 403 com reason de quota (quotaExceeded e afins)."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status != 403:
        return False
    details = getattr(exc, "error_details", None) or []
    reasons = {d.get("reason") for d in details if isinstance(d, dict)}
    if reasons & QUOTA_REASONS:
        return True
    content = getattr(exc, "content", b"") or b""
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    return any(reason in content for reason in QUOTA_REASONS)


class YouTubePublisher(Publisher):
    platform = "youtube"

    def authenticate(self, account: dict) -> Any:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        cred_dir = credentials_dir(account)
        client_secrets = cred_dir / "credentials.json"
        token_path = cred_dir / "token.json"
        if not client_secrets.exists():
            raise FileNotFoundError(
                f"credentials.json nao encontrado em {cred_dir}. Baixe o OAuth "
                "client (tipo Desktop app) no Google Cloud Console e salve como "
                f"{client_secrets}"
            )

        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                # Modo Testing do consent screen: refresh token expira em 7
                # dias; cai para o fluxo interativo completo.
                creds = None
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def upload(self, video_path: Path, metadata: dict, account: dict) -> dict:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload

        creds = self.authenticate(account)
        youtube = build("youtube", "v3", credentials=creds)

        language = metadata.get("language") or "pt-BR"
        body = {
            "snippet": {
                "title": (metadata.get("title") or video_path.stem)[:100],
                "description": (metadata.get("description") or "")[:5000],
                "tags": metadata.get("tags") or [],
                "categoryId": str(metadata.get("category_id") or "22"),
                "defaultLanguage": language,
                "defaultAudioLanguage": language,
            },
            "status": {
                "privacyStatus": metadata.get("privacy") or "private",
                # madeForKids e derivado pelo YouTube; declaracao vai no self*.
                "selfDeclaredMadeForKids": bool(metadata.get("made_for_kids", False)),
            },
        }
        media = MediaFileUpload(
            str(video_path), mimetype="video/mp4",
            chunksize=CHUNK_SIZE, resumable=True,
        )
        request = youtube.videos().insert(
            part="snippet,status", body=body, media_body=media)

        try:
            response = None
            while response is None:
                progress, response = request.next_chunk()
                if progress:
                    print(f"upload {int(progress.progress() * 100)}%", file=sys.stderr)
        except HttpError as exc:
            if _is_quota_error(exc):
                raise QuotaExceededError(
                    "quota diaria da YouTube Data API esgotada (videos.insert = 1600 unidades)"
                ) from exc
            raise

        remote_id = response["id"]
        return {
            "remote_id": remote_id,
            "url": f"https://youtu.be/{remote_id}",
            "published_at": _now_iso(),
        }

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

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    # readonly permite reler status/estatisticas do proprio video (videos.list);
    # sem ele, videos.list retorna 403 insufficientPermissions.
    "https://www.googleapis.com/auth/youtube.readonly",
]
CHUNK_SIZE = 8 * 1024 * 1024
QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "uploadLimitExceeded"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sanitize_text(text: str) -> str:
    """A API rejeita < e > em title/description."""
    return text.replace("<", "").replace(">", "")


def _truncate_bytes(text: str, limit: int) -> str:
    """Corta em bytes UTF-8 (limite real da API) sem quebrar char no meio."""
    return text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def _fit_tags(tags: list, budget: int = 500) -> list[str]:
    """Dedupe (case-insensitive, preserva ordem) e corta para caber no orcamento
    da API (~500 chars somados; tag com espaco conta +2 pelas aspas). Tags vem
    do especifico ao generico, entao pular as do fim custa menos."""
    if not isinstance(tags, (list, tuple)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    used = 0
    for tag in tags:
        if not isinstance(tag, str) or not tag.strip():
            continue
        tag = tag.strip()
        key = tag.lower()
        if key in seen:
            continue
        cost = len(tag) + (2 if " " in tag else 0)
        if used + cost > budget:
            continue
        seen.add(key)
        used += cost
        result.append(tag)
    return result


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
                "title": _sanitize_text(metadata.get("title") or video_path.stem)[:100],
                "description": _truncate_bytes(
                    _sanitize_text(metadata.get("description") or ""), 5000),
                "tags": _fit_tags(metadata.get("tags") or []),
                "categoryId": str(metadata.get("category_id") or "22"),
                "defaultLanguage": language,
                "defaultAudioLanguage": language,
            },
            "status": {
                # projeto auditado/liberado: default public (upload de teste
                # confirmou public + thumbnails.set). Private por clip via metadata.
                "privacyStatus": metadata.get("privacy") or "public",
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
        result = {
            "remote_id": remote_id,
            "url": f"https://youtu.be/{remote_id}",
            "published_at": _now_iso(),
        }
        thumb = metadata.get("thumbnail_path")
        if thumb:
            result["thumbnail_set"] = _set_thumbnail(youtube, remote_id, Path(thumb))
        return result


def _set_thumbnail(youtube: Any, remote_id: str, thumb_path: Path) -> bool:
    """thumbnails.set best-effort (custa 50 unidades). Nunca lanca: canal nao
    verificado (403), quota, arquivo ausente etc. viram aviso no stderr. O
    upload ja esta 'published' independentemente disso."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    if not thumb_path.exists():
        print(f"thumbnail: arquivo nao encontrado ({thumb_path}); pulando",
              file=sys.stderr)
        return False
    mime = "image/png" if thumb_path.suffix.lower() == ".png" else "image/jpeg"
    try:
        youtube.thumbnails().set(
            videoId=remote_id,
            media_body=MediaFileUpload(str(thumb_path), mimetype=mime),
        ).execute()
        return True
    except HttpError as exc:
        reason = "canal nao verificado / quota / video bloqueado"
        print(f"thumbnail: thumbnails.set falhou ({reason}): {exc}; "
              "suba a miniatura manualmente no YouTube Studio", file=sys.stderr)
        return False
    except Exception as exc:  # rede, credencial, etc. — best-effort
        print(f"thumbnail: thumbnails.set erro inesperado: {exc}", file=sys.stderr)
        return False

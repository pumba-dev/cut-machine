"""Publisher YouTube: OAuth installed-app + videos.insert resumable.

Credenciais por conta em credentials_dir(account): credentials.json (OAuth
client Desktop app, baixado do Google Cloud Console) + token.json (gerado
aqui). Imports google ficam dentro dos metodos para o pacote carregar sem as
deps instaladas.
"""
import sys
import time
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

# Shorts recem-publicados: a classificacao interna do YouTube (video vertical
# curto -> Short) ainda nao terminou no instante seguinte ao videos.insert, e
# o thumbnails.set() e ignorado mesmo respondendo 200 (a API confirma OK e o
# campo publish.thumbnail_set fica True, mas a thumb nunca aparece no Studio).
# Confirmado empiricamente 2026-07-09 e de novo 2026-07-11 (shorts da conta
# negocios com thumbnail_set=True e sem thumb aplicada) — um delay fixo de
# 120s nao e suficiente. Troca: em vez de dormir um tempo fixo e tentar as
# cegas, faz *poll* de videos.list ate o video sair de uploadStatus="uploaded"
# para "processed" (processamento completo, inclusive classificacao Short) e
# so entao tenta o thumbnails.set — so para format == "short"; corte
# (long-form) nao precisa (nunca precisou).
SHORT_THUMBNAIL_POLL_INTERVAL_S = 20
SHORT_THUMBNAIL_MAX_WAIT_S = 600


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


def _http_error_reason(exc: Any) -> str | None:
    """Extrai o `reason` estruturado (ex.: 'uploadRateLimitExceeded') de um HttpError."""
    details = getattr(exc, "error_details", None) or []
    for d in details:
        if isinstance(d, dict) and d.get("reason"):
            return d["reason"]
    content = getattr(exc, "content", b"") or b""
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    for reason in QUOTA_REASONS | {"uploadRateLimitExceeded"}:
        if reason in content:
            return reason
    return None


def _is_quota_error(exc: Any) -> bool:
    """HttpError 403 com reason de quota (quotaExceeded e afins)."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status != 403:
        return False
    return _http_error_reason(exc) in QUOTA_REASONS


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
            is_short = metadata.get("format") == "short"
            ok, _rate_limited = _set_thumbnail(
                youtube, remote_id, Path(thumb), wait_for_processing=is_short)
            result["thumbnail_set"] = ok
        return result

    def set_thumbnail(self, remote_id: str, thumb_path: Path, account: dict,
                       wait_for_processing: bool = False) -> tuple[bool, bool]:
        """thumbnails.set fora do fluxo de upload — retrofit de video ja
        publicado (usado por scripts/thumbnail_backfill.py). Retorna
        (ok, rate_limited)."""
        from googleapiclient.discovery import build

        creds = self.authenticate(account)
        youtube = build("youtube", "v3", credentials=creds)
        return _set_thumbnail(youtube, remote_id, thumb_path,
                               wait_for_processing=wait_for_processing)


def _wait_for_processed(youtube: Any, remote_id: str, max_wait_s: int,
                         poll_interval_s: int) -> bool:
    """Poll de videos.list (part=status, 1 unidade por chamada — bem mais
    barato que uma tentativa extra de thumbnails.set a 50) ate
    uploadStatus == "processed" ou estourar max_wait_s. Retorna True se
    processou a tempo; False se estourou o teto ou o video falhou/foi
    rejeitado (chamador tenta o thumbnails.set assim mesmo — best-effort)."""
    deadline = time.monotonic() + max_wait_s
    while True:
        try:
            resp = youtube.videos().list(part="status", id=remote_id).execute()
            items = resp.get("items") or []
            upload_status = (items[0].get("status") or {}).get("uploadStatus") if items else None
        except Exception as exc:
            print(f"thumbnail: erro ao consultar status de {remote_id}: {exc}",
                  file=sys.stderr)
            upload_status = None

        if upload_status == "processed":
            return True
        if upload_status in ("failed", "rejected", "deleted"):
            print(f"thumbnail: {remote_id} uploadStatus={upload_status}; "
                  "abortando espera de processamento", file=sys.stderr)
            return False
        if time.monotonic() >= deadline:
            print(f"thumbnail: {remote_id} nao processou em {max_wait_s}s "
                  f"(uploadStatus={upload_status}); tentando thumbnails.set assim mesmo",
                  file=sys.stderr)
            return False
        time.sleep(poll_interval_s)


def _set_thumbnail(youtube: Any, remote_id: str, thumb_path: Path,
                    wait_for_processing: bool = False) -> tuple[bool, bool]:
    """thumbnails.set best-effort, 1 unica tentativa (50 unidades). Nunca
    lanca: canal nao verificado, quota, arquivo ausente etc. viram aviso no
    stderr — o upload ja esta 'published' independentemente disso. Retorna
    (ok, rate_limited).

    `wait_for_processing` faz poll (`_wait_for_processed`) ate o video estar
    totalmente processado antes da tentativa: logo apos o insert, o YouTube
    ainda pode nao ter classificado o video como Short, e o thumbnails.set()
    e ignorado mesmo respondendo 200 (ver comentario de
    SHORT_THUMBNAIL_MAX_WAIT_S)."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    if not thumb_path.exists():
        print(f"thumbnail: arquivo nao encontrado ({thumb_path}); pulando",
              file=sys.stderr)
        return False, False

    if wait_for_processing:
        _wait_for_processed(youtube, remote_id, SHORT_THUMBNAIL_MAX_WAIT_S,
                             SHORT_THUMBNAIL_POLL_INTERVAL_S)

    mime = "image/png" if thumb_path.suffix.lower() == ".png" else "image/jpeg"
    try:
        youtube.thumbnails().set(
            videoId=remote_id,
            media_body=MediaFileUpload(str(thumb_path), mimetype=mime),
        ).execute()
        return True, False
    except HttpError as exc:
        status = getattr(getattr(exc, "resp", None), "status", None)
        reason = _http_error_reason(exc)
        print(f"thumbnail: thumbnails.set falhou (HTTP {status} {reason or ''}): "
              f"{exc}; suba a miniatura manualmente no YouTube Studio", file=sys.stderr)
        return False, reason == "uploadRateLimitExceeded"
    except Exception as exc:  # rede, credencial, etc.
        print(f"thumbnail: erro inesperado: {exc}; suba a miniatura manualmente "
              "no YouTube Studio", file=sys.stderr)
        return False, False

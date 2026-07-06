"""Fonte YouTube via yt-dlp (API Python).

O import de yt_dlp acontece dentro dos metodos para que este modulo importe
mesmo sem a dependencia instalada (o registry precisa carregar sempre).

Fallback anti-bot: se o YouTube exigir login/captcha ("Sign in to confirm
you're not a bot"), ha duas saidas (ver references/youtube-api.md):
1. Exportar cookies logados para secrets/youtube-cookies.txt (formato Netscape,
   via extensao "Get cookies.txt LOCALLY") - detectado automaticamente abaixo.
   cookiesfrombrowser NAO funciona com Chrome/Edge atuais no Windows
   (criptografia app-bound - yt-dlp issue #10927).
2. Plugin bgutil-ytdlp-pot-provider (PO token, requer Node) - decisao do usuario.
"""
import re
from pathlib import Path

from ..paths import ROOT
from .base import VideoSource

# Decisao fixa da arquitetura: h264 mp4 ate 1080p com audio m4a, senao melhor mp4.
FORMAT = "bv*[ext=mp4][vcodec^=avc1][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]/b"

_URL_PATTERNS = (
    re.compile(r"(?:https?://)?(?:www\.|m\.)?youtube\.com/(?:watch\?|live/|shorts/)", re.IGNORECASE),
    re.compile(r"(?:https?://)?youtu\.be/[\w-]{6,}", re.IGNORECASE),
)


class YouTubeSource(VideoSource):
    """Baixa videos do YouTube (watch, live, shorts, youtu.be)."""

    name = "youtube"

    @classmethod
    def matches(cls, url: str) -> bool:
        return any(p.search(url) for p in _URL_PATTERNS)

    def _base_opts(self) -> dict:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "restrictfilenames": True,
        }
        cookies = ROOT / "secrets" / "youtube-cookies.txt"
        if cookies.exists():
            opts["cookiefile"] = str(cookies)
        return opts

    def probe_id(self, url: str) -> str:
        import yt_dlp

        opts = self._base_opts()
        opts["skip_download"] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info["id"]

    def fetch(self, url: str, workspace: Path) -> dict:
        import yt_dlp

        opts = self._base_opts()
        opts.update({
            "format": FORMAT,
            "merge_output_format": "mp4",
            "writeinfojson": True,
            "outtmpl": str(workspace / "source.%(ext)s"),
        })
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        video_path = self._ensure_artifact(workspace, "source.mp4", exclude_suffixes=(".json", ".part"))
        self._ensure_artifact(workspace, "source.info.json")

        try:
            path_str = video_path.relative_to(ROOT).as_posix()
        except ValueError:
            path_str = str(video_path)

        duration = info.get("duration")
        fps = info.get("fps")
        return {
            "video_id": info["id"],
            "url": info.get("webpage_url") or url,
            "title": info.get("title") or "",
            "channel": info.get("channel") or info.get("uploader") or "",
            "duration_s": float(duration) if duration is not None else None,
            "width": info.get("width"),
            "height": info.get("height"),
            "fps": float(fps) if fps is not None else None,
            "language": info.get("language"),
            "path": path_str,
        }

    def _ensure_artifact(self, workspace: Path, target_name: str,
                         exclude_suffixes: tuple[str, ...] = ()) -> Path:
        """Garante workspace/<target_name>, renomeando source.* que o yt-dlp gerou."""
        target = workspace / target_name
        if target.exists():
            return target
        for candidate in sorted(workspace.glob("source.*")):
            if candidate.name == target_name:
                continue
            if exclude_suffixes and candidate.suffix.lower() in exclude_suffixes:
                continue
            if target_name.endswith(".info.json") and not candidate.name.endswith(".info.json"):
                continue
            candidate.rename(target)
            return target
        raise FileNotFoundError(f"yt-dlp nao gerou {target_name} em {workspace}")

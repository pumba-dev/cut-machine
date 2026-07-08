"""Fonte YouTube via yt-dlp (API Python).

O import de yt_dlp acontece dentro dos metodos para que este modulo importe
mesmo sem a dependencia instalada (o registry precisa carregar sempre).

Autenticacao anti-bot ("Sign in to confirm you're not a bot" / LOGIN_REQUIRED),
em camadas (ver references/youtube-api.md):
1. Cookies exportados (principal): secrets/youtube-cookies.txt (Netscape, via
   extensao "Get cookies.txt LOCALLY") - detectado automaticamente abaixo.
   cookiesfrombrowser NAO funciona com Chrome/Edge atuais no Windows
   (criptografia app-bound - yt-dlp issue #10927). Sessao e fragil: poucas
   dezenas de chamadas em minutos ja foram suficientes para o YouTube
   invalidar o cookie (LOGIN_REQUIRED). Reduzir chamadas repetidas/testes em
   rajada; re-exportar (janela anonima, fechar sem deslogar) quando quebrar.
2. Plugin bgutil-ytdlp-pot-provider (PO token, requer Node) - reserva, ja
   instalado e buildado (ver references/youtube-api.md).
NAO USAR: OAuth2 device-flow (yt-dlp-youtube-oauth2) - testado em 2026-07-06,
falha com HTTP 400 no passo de device code; repositorio arquivado (jan/2026),
bug aberto sem correcao desde nov/2024. Projeto morto, nao reativar.
"""
import glob
import os
import re
import subprocess
from pathlib import Path

from ..paths import ROOT
from .base import VideoSource

# Decisao fixa da arquitetura: h264 mp4 ate 1080p com audio m4a, senao melhor mp4.
FORMAT = "bv*[ext=mp4][vcodec^=avc1][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]/b"

_URL_PATTERNS = (
    re.compile(r"(?:https?://)?(?:www\.|m\.)?youtube\.com/(?:watch\?|live/|shorts/)", re.IGNORECASE),
    re.compile(r"(?:https?://)?youtu\.be/[\w-]{6,}", re.IGNORECASE),
)

# nvm-for-windows costuma deixar um Node EOL (ex.: v12) como ativo. O solver do
# desafio nsig do yt-dlp (EJS/jsc) exige Node >= 20; com um node velho o YouTube
# devolve so storyboard ("Only images available", zero formatos A/V) mesmo com
# cookie e PO token validos. Resolve um Node >= 20 explicito (override em
# YTDLP_NODE, senao varre as versoes do nvm em %APPDATA%\nvm) e passa via
# js_runtimes; None => usa o node do PATH. Resultado cacheado no modulo.
_NODE_GE20_CACHE: object = False  # False = ainda nao computado; depois str|None


def _node_ge20() -> str | None:
    global _NODE_GE20_CACHE
    if _NODE_GE20_CACHE is not False:
        return _NODE_GE20_CACHE  # type: ignore[return-value]
    candidates: list[str] = []
    env = os.environ.get("YTDLP_NODE")
    if env:
        candidates.append(env)
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates += sorted(
            glob.glob(str(Path(appdata) / "nvm" / "v*" / "node.exe")), reverse=True)
    found: str | None = None
    for cand in candidates:
        try:
            out = subprocess.run([cand, "--version"], capture_output=True,
                                 text=True, timeout=10)
            major = int((out.stdout or "").strip().lstrip("v").split(".")[0])
            if major >= 20:
                found = cand
                break
        except Exception:
            continue
    _NODE_GE20_CACHE = found
    return found


class YouTubeSource(VideoSource):
    """Baixa videos do YouTube (watch, live, shorts, youtu.be)."""

    name = "youtube"

    @classmethod
    def matches(cls, url: str) -> bool:
        return any(p.search(url) for p in _URL_PATTERNS)

    def _base_opts(self) -> dict:
        node = _node_ge20()
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "restrictfilenames": True,
            # yt-dlp >= 2025.11 exige runtime JS para os desafios do YouTube; o
            # default e deno (ausente aqui) - usamos Node. IMPORTANTE: precisa
            # ser Node >= 20 (ver _node_ge20); o node ativo do nvm pode ser EOL
            # e derruba o solver nsig (YouTube devolve so storyboard).
            "js_runtimes": {"node": {"path": node}} if node else {"node": {}},
            # Solver oficial de desafios do yt-dlp (baixado do GitHub deles,
            # cacheado local). Sem ele o YouTube nao entrega formato nenhum.
            # Autorizado pelo dono do repo em 2026-07-06.
            "remote_components": ["ejs:github"],
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

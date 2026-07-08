"""Montagem de comandos ffmpeg e renderizacao de clips.

Corte preciso exige re-encode: stream copy so inicia em keyframe e o corte
gruda no IDR anterior/posterior. -ss antes de -i (seek rapido + decode ate
o ponto exato) faz o output comecar em t=0, por isso o ASS usa tempos
rebased.
"""
import os
import subprocess
from pathlib import Path

from .. import paths
from ..contracts import FORMAT_RULES
from ..media import video_info
from .branding import build_border_ass, build_corte_filter, resolve_brand
from .captions import build_ass
from .corte_frame import BG_FALLBACK as CORTE_BG_FALLBACK
from .corte_frame import build_corte_frame_filter
from .short_frame import BG_FALLBACK, build_short_filter
from .thumbnail import generate_thumbnail


def _t(value: float) -> str:
    return f"{float(value):.3f}"


def _resolve_frame_png(rel: str | None) -> str | None:
    """Caminho absoluto do PNG de moldura (short/corte), ou None se ausente/inexistente.

    Path relativo e resolvido a partir da raiz do repo. Retornar absoluto e
    seguro no `-i` do ffmpeg (so o filtro `ass=` sofre com escaping no Windows).
    """
    if not rel or not str(rel).strip():
        return None
    p = Path(rel)
    if not p.is_absolute():
        p = paths.ROOT / rel
    return str(p.resolve()) if p.exists() else None


def build_short_cmd(start: float, dur: float, captions_ass: str,
                    out_filename: str, source: str = "source.mp4",
                    frame_png: str | None = None, bg_hex: str = BG_FALLBACK) -> list[str]:
    """Comando ffmpeg para short 1080x1920 com moldura fixa + legendas queimadas.

    Fundo ESTATICO (nao mais blur): arte PNG decorativa da conta (`frame_png`,
    caminho absoluto — seguro em `-i`, ao contrario do filtro `ass=`) ou, sem
    PNG, uma cor chapada (`bg_hex`). O video 16:9 entra SEM CROP numa janela
    (escala por largura, altura par via `-2`) e a arte e sobreposta POR CIMA
    (janela transparente). Toda a marca/CTA ja vem embutida na arte PNG; so
    `captions_ass` (legendas) e queimado por cima, por nome relativo ao cwd.
    `-map 0:a?` torna o audio opcional (fonte sem audio nao quebra o comando).

    `-t _t(dur)` na SAIDA e obrigatorio: as fontes sinteticas do filtro (color +
    `-loop 1` no PNG) sao infinitas e o `overlay(...:shortest=1)` sozinho NAO
    encerra o grafo de dois overlays (`-t` no input so limita a leitura do
    video); sem o `-t` de saida o encode nunca termina.
    """
    has_png = bool(frame_png)
    filter_complex = build_short_filter(bg_hex, has_png, captions_ass)
    cmd = ["ffmpeg", "-ss", _t(start), "-t", _t(dur), "-i", source]
    if has_png:
        cmd += ["-loop", "1", "-i", frame_png]
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a?",
        "-r", "30",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-t", _t(dur),
        "-y", out_filename,
    ]
    return cmd


def build_corte_cmd(start: float, dur: float, out_filename: str,
                    source: str = "source.mp4",
                    filter_complex: str | None = None,
                    frame_png: str | None = None) -> list[str]:
    """Comando ffmpeg para corte 1920x1080.

    Com `filter_complex` (moldura de marca) aplica a cadeia -> [v] e mapeia
    video+audio explicitamente (`-map [v] -map 0:a?`, audio opcional). Sem
    ele, corte cru sem filtro de video (mapeamento default). filter_complex
    referencia o .border.ass por nome relativo ao cwd do processo.

    Com `frame_png` (caminho absoluto), adiciona a arte da moldura como 2o input
    (`-loop 1`); o proprio `filter_complex` deve entao vir de
    `build_corte_frame_filter` (video sob a arte, janela transparente).

    `-t _t(dur)` na SAIDA e obrigatorio quando ha `filter_complex` com fontes
    sinteticas (color + `-loop 1` no PNG): elas sao infinitas e o
    `overlay(...:shortest=1)` sozinho NAO encerra o grafo de dois overlays (o
    `-t` de input so limita a leitura do video); sem ele o encode nunca termina.
    """
    has_png = bool(frame_png)
    cmd = ["ffmpeg", "-ss", _t(start), "-t", _t(dur), "-i", source]
    if has_png:
        cmd += ["-loop", "1", "-i", frame_png]
    if filter_complex:
        cmd += ["-filter_complex", filter_complex, "-map", "[v]", "-map", "0:a?",
                "-r", "30"]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-t", _t(dur),
        "-y", out_filename,
    ]
    return cmd


def render_clip(clip: dict, video_id: str, transcript: dict | None = None,
                account: dict | None = None) -> dict:
    """Renderiza um clip e valida o resultado contra FORMAT_RULES.

    Gera o .ass quando o formato queima legendas, aplica a moldura de marca
    quando o formato tem `border` (corte), roda o ffmpeg e valida o output
    (resolucao exata, duracao end-start +-0.5s, audio presente). Depois gera
    a miniatura (thumbnail) do clip. Retorna o dict de core.media.video_info
    do mp4, acrescido de `thumbnail_path`/`thumbnail_ts` (ou `thumbnail_error`
    se a miniatura falhar — nunca fatal). `account` fornece o brand da borda.
    """
    fmt = clip["format"]
    rules = FORMAT_RULES[fmt]
    start = float(clip["start"])
    dur = float(clip["end"]) - start

    source = paths.source_video_path(video_id)
    if not source.exists():
        raise FileNotFoundError(f"source.mp4 nao encontrado: {source}")

    out_path = paths.clip_output_path(video_id, clip["id"])
    clip_dir = out_path.parent
    clip_dir.mkdir(parents=True, exist_ok=True)
    # cwd na pasta do clip + caminhos relativos: path absoluto dentro do
    # filtro ass= exige escaping duplo no Windows e quebra facil.
    source_rel = os.path.relpath(source, clip_dir)
    # id do YouTube pode comecar com '-'; sem o prefixo ./ o ffmpeg leria o
    # nome do output como opcao.
    out_name = "./" + out_path.name

    if rules["burn_captions"]:
        if not transcript:
            raise ValueError(f"{clip['id']}: formato {fmt} exige transcript para legendas")
        brand = resolve_brand(account)
        ass_path = paths.clip_ass_path(video_id, clip["id"])
        ass_path.write_text(build_ass(clip, transcript), encoding="utf-8")
        frame_png = _resolve_frame_png(brand.get("short_frame"))
        cmd = build_short_cmd(
            start, dur, ass_path.name, out_name, source=source_rel,
            frame_png=frame_png, bg_hex=brand.get("short_bg_color", BG_FALLBACK),
        )
    elif rules.get("border"):
        brand = resolve_brand(account)
        corte_png = _resolve_frame_png(brand.get("corte_frame"))
        if corte_png:
            # Arte PNG estatica (janela fixa) substitui a moldura gerada.
            fc = build_corte_frame_filter(CORTE_BG_FALLBACK, has_png=True)
            cmd = build_corte_cmd(start, dur, out_name, source=source_rel,
                                  filter_complex=fc, frame_png=corte_png)
        else:
            # Fallback: moldura gerada (padding + rim + faixa de texto ASS).
            border_ass = paths.clip_border_ass_path(video_id, clip["id"])
            border_ass.write_text(build_border_ass(brand), encoding="utf-8")
            fc = build_corte_filter(brand, border_ass.name)
            cmd = build_corte_cmd(start, dur, out_name, source=source_rel, filter_complex=fc)
    else:
        cmd = build_corte_cmd(start, dur, out_name, source=source_rel)

    proc = subprocess.run(
        cmd, cwd=str(clip_dir), capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-20:])
        raise RuntimeError(f"ffmpeg falhou (exit {proc.returncode}): {tail}")

    info = video_info(out_path)
    problems: list[str] = []
    resolution = f"{info['width']}x{info['height']}"
    if resolution != rules["resolution"]:
        problems.append(f"resolucao {resolution}, esperada {rules['resolution']}")
    if abs(info["duration_s"] - dur) > 0.5:
        problems.append(f"duracao {info['duration_s']:.2f}s, esperada {dur:.2f}s (+-0.5s)")
    if not info["has_audio"]:
        problems.append("sem stream de audio")
    if problems:
        raise ValueError(f"{out_path.name} invalido: " + "; ".join(problems))

    # Miniatura: enfeite de engajamento, nunca fatal para o clip.
    try:
        thumb = generate_thumbnail(clip, video_id)
        info["thumbnail_path"] = thumb["path"]
        info["thumbnail_ts"] = thumb["ts"]
    except Exception as exc:
        info["thumbnail_error"] = str(exc) or exc.__class__.__name__
    return info

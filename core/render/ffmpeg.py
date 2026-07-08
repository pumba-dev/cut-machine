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
from .thumbnail import generate_thumbnail


def _t(value: float) -> str:
    return f"{float(value):.3f}"


def build_short_cmd(start: float, dur: float, ass_filename: str, out_filename: str,
                    source: str = "source.mp4") -> list[str]:
    """Comando ffmpeg para short 1080x1920 com legendas queimadas.

    Sem crop: o video original inteiro (16:9) e escalado para caber dentro
    de 1080x1920 e centralizado sobre um fundo blurado (o mesmo frame,
    escalado para preencher o canvas e desfocado). Fundo (bg) e primeiro
    plano (fg) sao gerados a partir da mesma fonte para nao exigir arquivo
    de imagem extra. `trunc(iw/2)*2` no fg garante dimensao par (exigido
    por yuv420p) apos o scale com aspect ratio preservado. `-map 0:a?`
    torna o audio opcional (fonte sem audio nao quebra o comando).
    ass_filename deve ser relativo ao cwd do processo.
    """
    filter_complex = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=20[bg];"
        "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,ass={ass_filename}[v]"
    )
    return [
        "ffmpeg",
        "-ss", _t(start), "-t", _t(dur), "-i", source,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a?",
        "-r", "30",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-y", out_filename,
    ]


def build_corte_cmd(start: float, dur: float, out_filename: str,
                    source: str = "source.mp4",
                    filter_complex: str | None = None) -> list[str]:
    """Comando ffmpeg para corte 1920x1080.

    Com `filter_complex` (moldura de marca) aplica a cadeia -> [v] e mapeia
    video+audio explicitamente (`-map [v] -map 0:a?`, audio opcional). Sem
    ele, corte cru sem filtro de video (mapeamento default). filter_complex
    referencia o .border.ass por nome relativo ao cwd do processo.
    """
    cmd = ["ffmpeg", "-ss", _t(start), "-t", _t(dur), "-i", source]
    if filter_complex:
        cmd += ["-filter_complex", filter_complex, "-map", "[v]", "-map", "0:a?"]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
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
        ass_path = paths.clip_ass_path(video_id, clip["id"])
        ass_path.write_text(build_ass(clip, transcript), encoding="utf-8")
        cmd = build_short_cmd(start, dur, ass_path.name, out_name, source=source_rel)
    elif rules.get("border"):
        brand = resolve_brand(account)
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

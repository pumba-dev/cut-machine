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
from .captions import build_ass


def _t(value: float) -> str:
    return f"{float(value):.3f}"


def build_short_cmd(start: float, dur: float, ass_filename: str, out_filename: str,
                    source: str = "source.mp4") -> list[str]:
    """Comando ffmpeg para short 1080x1920 com legendas queimadas.

    scale antes de crop garante largura par (crop direto de 9:16 em 1080p
    da 607.5px, quebrado em yuv420p). ass_filename deve ser relativo ao cwd
    do processo.
    """
    return [
        "ffmpeg",
        "-ss", _t(start), "-t", _t(dur), "-i", source,
        "-vf", f"scale=-2:1920,crop=1080:1920,ass={ass_filename}",
        "-r", "30",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-y", out_filename,
    ]


def build_corte_cmd(start: float, dur: float, out_filename: str,
                    source: str = "source.mp4") -> list[str]:
    """Comando ffmpeg para corte 1920x1080 sem filtro de video."""
    return [
        "ffmpeg",
        "-ss", _t(start), "-t", _t(dur), "-i", source,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-y", out_filename,
    ]


def render_clip(clip: dict, video_id: str, transcript: dict | None = None) -> dict:
    """Renderiza um clip e valida o resultado contra FORMAT_RULES.

    Gera o .ass quando o formato queima legendas, roda o ffmpeg e retorna o
    dict de core.media.video_info do arquivo final. Levanta excecao em
    falha do ffmpeg ou output fora do contrato (resolucao exata, duracao
    end-start +-0.5s, presenca de audio).
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
    return info

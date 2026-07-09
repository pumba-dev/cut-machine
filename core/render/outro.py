"""Vinheta de fim (outro): concatena uma arte de encerramento ao mp4 do clip.

Aplica-se a ambos os formatos (short/corte), opt-in por conta via
`brand.short_outro`/`brand.corte_outro` (caminho do mp4; vazio = desligado).
A arte e colada ao FINAL do clip JA renderizado e validado.

A arte de outro vem de IA em resolucao/fps/codec arbitrarios (ex.: 1280x720@24
num short 1080x1920), entao a juncao normaliza tudo por RE-ENCODE sobre frames
decodificados (concat filter, nao demuxer): escala + pad para a resolucao exata
do formato (letterbox/pillarbox — preserva o outro inteiro, sem distorcer nem
cortar), 30fps, yuv420p e audio 48k estereo AAC (os mesmos alvos do render dos
clips em `ffmpeg.py`). Assim o arquivo final continua com a resolucao/fps que o
QA exige; so a DURACAO cresce (pelo tamanho do outro).

Escreve num temp e faz `os.replace` atomico. Em falha do ffmpeg o temp e
removido e a excecao sobe: a vinheta e requisito de marca, entao um append
quebrado deve reprovar o clip (nao e best-effort como a miniatura).
"""
import os
import subprocess
from pathlib import Path

from ..media import video_info


def _t(v: float) -> str:
    return f"{float(v):.3f}"


def _norm_video(w: int, h: int) -> str:
    """Cadeia de normalizacao de video: fit+pad para w:h, SAR 1, 30fps, yuv420p."""
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p")


def append_outro(main_mp4: Path, outro_path: str, resolution: str,
                 crf: int = 18) -> float:
    """Concatena `outro_path` ao final de `main_mp4` (in-place, atomico).

    `resolution` = "LARGxALT" do formato (o main ja vem nessa resolucao; o outro
    e normalizado para ela). `crf` casa com o do render do formato (short 18,
    corte 20). Retorna a duracao (s) efetivamente acrescentada ao arquivo
    (= duracao do outro no resultado). Levanta RuntimeError se o ffmpeg falhar.
    """
    main_mp4 = Path(main_mp4)
    w, h = (int(x) for x in resolution.split("x"))
    before = video_info(main_mp4)["duration_s"]
    outro_info = video_info(Path(outro_path))
    vnorm = _norm_video(w, h)

    parts = [
        f"[0:v]{vnorm}[v0]",
        f"[1:v]{vnorm}[v1]",
        "[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a0]",
    ]
    if outro_info["has_audio"]:
        parts.append(
            "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a1]")
    else:
        # Outro mudo: silencio do tamanho do outro para o concat casar v+a.
        dur = _t(outro_info["duration_s"])
        parts.append(f"anullsrc=r=48000:cl=stereo:d={dur}[a1]")
    parts.append("[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
    filter_complex = ";".join(parts)

    tmp = main_mp4.with_suffix(".outro.tmp.mp4")
    cmd = [
        "ffmpeg",
        "-i", str(main_mp4),
        "-i", str(outro_path),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-r", "30",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-y", str(tmp),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-20:])
        raise RuntimeError(f"ffmpeg outro concat falhou (exit {proc.returncode}): {tail}")

    os.replace(tmp, main_mp4)
    after = video_info(main_mp4)["duration_s"]
    return round(after - before, 3)

"""Intro (capa): prepende a miniatura como ~1s congelado no INICIO do clip.

So faz sentido em shorts (opt-in por conta via `thumbnail.intro_short`): o feed
do YouTube Shorts usa o 1o frame do video como capa, entao colar a thumb
desenhada la garante que a capa do feed = a thumb (que via `thumbnails.set` nem
sempre aparece no feed).

Espelha `outro.py`, mas cola no COMECO e a fonte e uma IMAGEM (nao um mp4): a
still e transformada num trecho de `duration_s` (`-loop 1 -t`), com audio mudo
(`anullsrc`, o intro nao tem som), normalizada para a resolucao exata do formato
(fit+pad, 30fps, yuv420p) e concatenada ANTES do main por RE-ENCODE (concat
filter). So a DURACAO cresce; resolucao/audio do conteudo ficam intactos.

Roda DEPOIS do render+validacao do conteudo (o check de duracao do conteudo,
sobre `end-start`, ja passou isolado). A duracao acrescentada volta em
`render.intro_duration_s` e entra em `contracts.expected_output_duration`.

Escreve num temp e faz `os.replace` atomico. Paths absolutos em `-i` e sem
filtro `ass=` -> sem o escaping duplo do Windows (nao precisa de cwd relativo).
"""
import os
import subprocess
from pathlib import Path

from ..media import video_info
from .encoder import is_nvenc_error, note_nvenc_failure, video_codec_args


def _norm_video(w: int, h: int) -> str:
    """Fit+pad para w:h, SAR 1, 30fps, yuv420p (mesma cadeia do outro)."""
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p")


def prepend_intro(main_mp4: Path, still_image: Path, resolution: str,
                  duration_s: float = 1.0, encoder: str = "libx264",
                  fmt: str = "short") -> float:
    """Prepende `still_image` (congelada por `duration_s`) a `main_mp4` (in-place, atomico).

    `resolution` = "LARGxALT" do formato (o main ja vem nessa resolucao; a still
    e normalizada para ela). `encoder`/`fmt` definem o codec de video (NVENC ou
    libx264; a qualidade por formato vem de `encoder.video_codec_args`). Retorna
    a duracao (s) efetivamente acrescentada ao arquivo. Levanta RuntimeError se o
    ffmpeg falhar (o chamador trata como nao-fatal — o intro e bonus, ao
    contrario do outro). Se o NVENC falhar com erro de encoder, re-tenta uma vez
    em libx264 (e degrada o resto do processo para CPU)."""
    main_mp4 = Path(main_mp4)
    w, h = (int(x) for x in resolution.split("x"))
    dur = f"{float(duration_s):.3f}"
    before = video_info(main_mp4)["duration_s"]
    vnorm = _norm_video(w, h)

    # input 0 = still (loop por `dur`); input 1 = main ja renderizado.
    filter_complex = ";".join([
        f"[0:v]{vnorm}[vi]",
        f"anullsrc=r=48000:cl=stereo:d={dur}[ai]",
        f"[1:v]{vnorm}[vm]",
        "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[am]",
        "[vi][ai][vm][am]concat=n=2:v=1:a=1[v][a]",
    ])

    tmp = main_mp4.with_suffix(".intro.tmp.mp4")

    def _cmd(enc: str) -> list[str]:
        return [
            "ffmpeg",
            "-loop", "1", "-framerate", "30", "-t", dur, "-i", str(still_image),
            "-i", str(main_mp4),
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-r", "30",
            *video_codec_args(fmt, enc),
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-y", str(tmp),
        ]

    proc = subprocess.run(
        _cmd(encoder), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0 and encoder == "nvenc" and is_nvenc_error(proc.stderr):
        note_nvenc_failure()
        proc = subprocess.run(
            _cmd("libx264"), capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-20:])
        raise RuntimeError(f"ffmpeg intro concat falhou (exit {proc.returncode}): {tail}")

    os.replace(tmp, main_mp4)
    after = video_info(main_mp4)["duration_s"]
    return round(after - before, 3)

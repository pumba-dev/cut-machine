"""Intro (capa): prepende a miniatura como ~1s congelado no INICIO do clip.

So faz sentido em shorts (opt-in por conta via `thumbnail.intro_short`): o feed
do YouTube Shorts usa o 1o frame do video como capa, entao colar a thumb
desenhada la garante que a capa do feed = a thumb (que via `thumbnails.set` nem
sempre aparece no feed).

Caminho rapido (concat-copy): encoda SO a still como um segmento de ~1s casando
os params de video do conteudo (pix_fmt/range, SAR, fps, timebase, codec) e o
cola ANTES do main por stream-copy (`concat.concat_copy`) — o video do conteudo
e COPIADO, nao re-encodado. Se o caminho rapido falhar ou produzir arquivo
invalido, cai no fallback classico (`_prepend_intro_reencode`): concat filter
que re-encoda tudo (mais lento, porem provado). So a DURACAO cresce; resolucao/
audio do conteudo ficam intactos em ambos.

Roda DEPOIS do render+validacao do conteudo. A duracao acrescentada volta em
`render.intro_duration_s` e entra em `contracts.expected_output_duration`.

Escreve num temp e faz `os.replace` atomico. O main so e substituido DEPOIS de o
resultado ser validado — em falha o main original fica intacto para o fallback.
"""
import os
import subprocess
from pathlib import Path

from ..media import video_info
from .concat import concat_copy, output_ok
from .encoder import is_nvenc_error, note_nvenc_failure, video_codec_args


def _norm_video(w: int, h: int, pix_fmt: str = "yuv420p") -> str:
    """Fit+pad para w:h, SAR 1, 30fps, pix_fmt (default yuv420p; o concat-copy
    passa o pix_fmt real do conteudo para casar full/limited range)."""
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format={pix_fmt}")


def _build_intro_segment(still_image: Path, seg_out: Path, w: int, h: int,
                         dur: str, pix_fmt: str, encoder: str, fmt: str) -> None:
    """Encoda a still como um segmento de video de `dur` casando os params do
    conteudo (para o concat-copy aceitar). Audio: silencio 48k estereo. Fallback
    NVENC->libx264 no erro de encoder. Levanta RuntimeError se o ffmpeg falhar."""
    vnorm = _norm_video(w, h, pix_fmt)
    filter_complex = ";".join([
        f"[0:v]{vnorm}[v]",
        f"anullsrc=r=48000:cl=stereo:d={dur}[a]",
    ])

    def _cmd(enc: str) -> list[str]:
        return [
            "ffmpeg",
            "-loop", "1", "-framerate", "30", "-t", dur, "-i", str(still_image),
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-r", "30",
            *video_codec_args(fmt, enc, pix_fmt=pix_fmt),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-t", dur,
            "-movflags", "+faststart",
            "-y", str(seg_out),
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
        seg_out.unlink(missing_ok=True)
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-20:])
        raise RuntimeError(f"ffmpeg intro segment falhou (exit {proc.returncode}): {tail}")


def prepend_intro(main_mp4: Path, still_image: Path, resolution: str,
                  duration_s: float = 1.0, encoder: str = "libx264",
                  fmt: str = "short") -> float:
    """Prepende `still_image` (congelada por `duration_s`) a `main_mp4` (in-place,
    atomico). Tenta o concat-copy (video do conteudo copiado); em qualquer falha
    ou saida invalida cai no re-encode. Retorna a duracao (s) acrescentada.
    Levanta RuntimeError so se o fallback tambem falhar (o chamador trata o intro
    como nao-fatal)."""
    main_mp4 = Path(main_mp4)
    w, h = (int(x) for x in resolution.split("x"))
    dur = f"{float(duration_s):.3f}"
    before = video_info(main_mp4)["duration_s"]

    seg_tmp = main_mp4.with_suffix(".introseg.tmp.mp4")
    out_tmp = main_mp4.with_suffix(".introout.tmp.mp4")
    try:
        info = video_info(main_mp4)
        pix_fmt = info.get("pix_fmt") or "yuv420p"
        _build_intro_segment(still_image, seg_tmp, w, h, dur, pix_fmt, encoder, fmt)
        # main entra como 2o segmento (READ); resultado vai para out_tmp (o main
        # so e tocado no os.replace final -> intacto se algo aqui falhar).
        concat_copy([seg_tmp, main_mp4], out_tmp)
        if not output_ok(out_tmp, resolution, before + float(dur)):
            raise RuntimeError("intro concat-copy: saida invalida (res/audio/duracao)")
        os.replace(out_tmp, main_mp4)
    except Exception:  # noqa: BLE001 — caminho rapido falhou -> re-encode provado
        out_tmp.unlink(missing_ok=True)
        return _prepend_intro_reencode(main_mp4, still_image, resolution,
                                       duration_s, encoder, fmt)
    finally:
        seg_tmp.unlink(missing_ok=True)

    after = video_info(main_mp4)["duration_s"]
    return round(after - before, 3)


def _prepend_intro_reencode(main_mp4: Path, still_image: Path, resolution: str,
                            duration_s: float, encoder: str, fmt: str) -> float:
    """Fallback provado: concat FILTER que re-encoda o clip inteiro (mais lento).

    input 0 = still (loop por `dur`); input 1 = main ja renderizado. Normaliza
    ambos para a resolucao exata (fit+pad, 30fps, yuv420p) + audio 48k estereo e
    concatena por re-encode. Escreve num temp e faz `os.replace` atomico."""
    main_mp4 = Path(main_mp4)
    w, h = (int(x) for x in resolution.split("x"))
    dur = f"{float(duration_s):.3f}"
    before = video_info(main_mp4)["duration_s"]
    vnorm = _norm_video(w, h)

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

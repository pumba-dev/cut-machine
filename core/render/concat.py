"""Concatenacao por stream-copy (concat demuxer) — junta segmentos SEM
re-encodar o video.

Usado pelo intro/outro para colar a arte (still/mp4 pequeno) no clip JA
renderizado sem pagar o re-encode do clip inteiro: o video de cada segmento e
COPIADO bit-a-bit (`-c:v copy`, rapido e sem perda) e so o audio e re-encodado
num stream continuo (`-c:a aac`) — o que mata o "click" de priming AAC na
emenda (o audio dos dois segmentos vira um encode unico) por um custo baixo.

Pre-requisitos (garantidos pelo chamador): todos os segmentos com MESMOS params
de video (codec/pix_fmt/resolucao/SAR/timebase) e de audio (sample-rate/canais)
— o concat demuxer recusa segmentos divergentes. O ponto de emenda cai num IDR
por construcao (cada segmento e um encode independente que comeca em keyframe).

Escreve num temp e faz `os.replace` atomico sobre `out` (que PODE ser um dos
segmentos de entrada — o output vai para um temp distinto, sem colisao de I/O).
"""
import os
import subprocess
from pathlib import Path

from ..media import video_info


def output_ok(path: Path, resolution: str, expected_duration: float,
              tol: float = 0.5) -> bool:
    """True se o mp4 concatenado passa os mesmos invariantes do QA: resolucao
    exata, audio presente, duracao dentro de `tol`. Usado para decidir se o
    caminho concat-copy vale ou se cai no fallback de re-encode (pega o caso
    'exit 0 mas arquivo torto', que o try/except sozinho nao pegaria)."""
    try:
        info = video_info(Path(path))
    except Exception:  # noqa: BLE001 — probe quebrado = saida invalida
        return False
    if f"{info['width']}x{info['height']}" != resolution:
        return False
    if not info["has_audio"]:
        return False
    return abs(info["duration_s"] - expected_duration) <= tol


def _list_line(seg: Path) -> str:
    """Linha `file '...'` do formato concat. Barra normal (evita escaping de
    backslash no Windows) e aspas simples escapadas (path com `'` e raro)."""
    p = str(seg.resolve()).replace("\\", "/").replace("'", "'\\''")
    return f"file '{p}'"


def concat_copy(segments: list[Path], out: Path,
                audio_bitrate: str = "192k") -> None:
    """Concatena `segments` (na ordem) em `out` por stream-copy de video.

    Video copiado (`-c:v copy`); audio re-encodado continuo (`aac`, 48k estereo).
    `out` pode coincidir com um dos segmentos: o ffmpeg escreve num temp e so
    entao `os.replace` sobre `out`. Levanta RuntimeError se o ffmpeg falhar
    (chamador trata — cai no fallback de re-encode)."""
    out = Path(out)
    segments = [Path(s) for s in segments]
    list_path = out.with_suffix(".concat.txt")
    tmp = out.with_suffix(".concat.tmp.mp4")
    list_path.write_text("\n".join(_list_line(s) for s in segments) + "\n",
                         encoding="utf-8")
    cmd = [
        "ffmpeg",
        "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", audio_bitrate, "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        "-y", str(tmp),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            tmp.unlink(missing_ok=True)
            tail = "\n".join((proc.stderr or "").strip().splitlines()[-20:])
            raise RuntimeError(f"ffmpeg concat-copy falhou (exit {proc.returncode}): {tail}")
        os.replace(tmp, out)
    finally:
        list_path.unlink(missing_ok=True)

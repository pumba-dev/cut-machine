"""Transcricao com faster-whisper: gera transcript.json, .compact.json e .srt.

GTX 1660 SUPER: sempre compute int8 (fp16 produz NaN na serie 16xx).
Fallback automatico para CPU com modelo small quando CUDA nao esta disponivel.
"""
import json
import os
import sys
from pathlib import Path

from ..paths import transcript_compact_path, transcript_path, transcript_srt_path


def _add_cuda_dlls() -> None:
    """Expoe DLLs cuBLAS/cuDNN instaladas via pip (pacotes nvidia-*) no Windows.

    Cobre site-packages global E de usuario (pip sem admin instala em
    %APPDATA%\\Python\\...). Alem de add_dll_directory, prepende no PATH -
    o loader do ctranslate2 nao honra add_dll_directory em todas as versoes.
    """
    if sys.platform != "win32":
        return
    import site

    site_dirs = [*site.getsitepackages(), site.getusersitepackages()]
    for site_dir in site_dirs:
        base = Path(site_dir) / "nvidia"
        if not base.is_dir():
            continue
        for bin_dir in base.glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def load_model(model: str = "large-v3", device: str = "auto", compute: str = "int8"):
    """Carrega WhisperModel; retorna (modelo, dict com device/model/compute efetivos)."""
    from faster_whisper import WhisperModel

    _add_cuda_dlls()
    if device in ("auto", "cuda"):
        try:
            wm = WhisperModel(model, device="cuda", compute_type=compute)
            return wm, {"device": "cuda", "model": model, "compute": compute}
        except Exception:
            if device == "cuda":
                raise
            # auto sem GPU: small int8 e o unico combo com velocidade aceitavel em CPU
            model, compute = "small", "int8"
    wm = WhisperModel(model, device="cpu", compute_type=compute, cpu_threads=os.cpu_count() or 4)
    return wm, {"device": "cpu", "model": model, "compute": compute}


def _fmt_srt(seconds: float) -> str:
    """Formata segundos como timestamp SRT (HH:MM:SS,mmm)."""
    ms = max(0, round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _build_srt(segments: list[dict]) -> str:
    blocks = [
        f"{i}\n{_fmt_srt(seg['start'])} --> {_fmt_srt(seg['end'])}\n{seg['text']}\n"
        for i, seg in enumerate(segments, start=1)
    ]
    return "\n".join(blocks)


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def transcribe_video(
    video_path: Path,
    video_id: str,
    model: str = "large-v3",
    device: str = "auto",
    compute: str = "int8",
) -> dict:
    """Transcreve o video e grava os tres artefatos no workspace. Retorna resumo."""
    whisper, effective = load_model(model=model, device=device, compute=compute)
    segments_gen, info = whisper.transcribe(
        str(video_path),
        language="pt",
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
    )

    segments: list[dict] = []
    total_words = 0
    for seg in segments_gen:
        words = [
            {
                "w": w.word.strip(),
                "start": round(w.start, 3),
                "end": round(w.end, 3),
                "prob": round(w.probability, 3),
            }
            for w in (seg.words or [])
        ]
        total_words += len(words)
        segments.append({
            "id": seg.id,
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "words": words,
        })

    duration = round(float(info.duration), 3)
    transcript = {
        "video_id": video_id,
        "language": "pt",
        "model": effective["model"],
        "duration": duration,
        "segments": segments,
    }
    _write_json(transcript_path(video_id), transcript)

    compact = {
        **transcript,
        "segments": [{k: v for k, v in s.items() if k != "words"} for s in segments],
    }
    _write_json(transcript_compact_path(video_id), compact)

    transcript_srt_path(video_id).write_text(_build_srt(segments), encoding="utf-8")

    return {
        "segments": len(segments),
        "words": total_words,
        "duration": duration,
        "device": effective["device"],
        "model": effective["model"],
    }

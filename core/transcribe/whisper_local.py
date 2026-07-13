"""Transcricao com faster-whisper: gera transcript.json, .compact.json e .srt.

GTX 1660 SUPER: sempre compute int8 (fp16 produz NaN na serie 16xx).
Fallback automatico para CPU com modelo small quando CUDA nao esta disponivel.
Apos o whisper roda diarizacao (core.diarize, sherpa-onnx CPU): palavras
ganham `spk`, segmentos ganham `speaker` e o transcript ganha `speakers`.
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
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
    diarize: bool = True,
    num_speakers: int = -1,
    batch_size: int = 4,
) -> dict:
    """Transcreve o video e grava os tres artefatos no workspace. Retorna resumo.

    batch_size > 1 (e device efetivo cuda) usa BatchedInferencePipeline: chunks
    entre janelas de VAD sao decodificados em paralelo na GPU (~2.5-4x em Turing
    int8). O caminho batched forca condition_on_previous_text=False por
    construcao — mata os loops de repeticao/alucinacao em audio longo (ganho de
    qualidade de graca). batch_size <= 1, ou fallback CPU, cai no stream
    single-pass classico (byte-identico ao comportamento antigo).

    A diarizacao (CPU, sherpa-onnx) depende SO do audio, nao do transcript, entao
    roda numa thread concorrente com o Whisper (GPU) quando o device efetivo e
    cuda: o wall-clock cai de whisper+diarize para max(whisper, diarize). No
    fallback CPU roda sequencial (evita contenda CPU-vs-CPU).
    """
    whisper, effective = load_model(model=model, device=device, compute=compute)

    # Diarizacao concorrente: submete a thread ANTES do loop do Whisper. O gate
    # depende do device EFETIVO (so conhecido pos-load: `auto` pode cair pra CPU).
    diarize_turns = assign_speakers = None
    if diarize:
        from ..diarize import assign_speakers, diarize_turns
    overlap = diarize and effective["device"] == "cuda"
    executor = None
    diar_future = None
    if overlap:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="diarize")
        diar_future = executor.submit(diarize_turns, video_path, num_speakers)

    try:
        common = dict(language="pt", word_timestamps=True, vad_filter=True, beam_size=5)
        if batch_size > 1 and effective["device"] == "cuda":
            from faster_whisper import BatchedInferencePipeline
            bs = batch_size
            while True:
                try:
                    pipeline = BatchedInferencePipeline(whisper)
                    segments_gen, info = pipeline.transcribe(str(video_path), batch_size=bs, **common)
                    break
                except RuntimeError as exc:  # ct2 sinaliza OOM como RuntimeError
                    if "out of memory" in str(exc).lower() and bs > 1:
                        bs = max(1, bs // 2)
                        # Contexto CUDA fica sujo pos-OOM: recarrega os pesos antes de tentar de novo.
                        whisper, effective = load_model(model=model, device=device, compute=compute)
                        continue
                    raise
            effective["batch_size"] = bs
        else:
            segments_gen, info = whisper.transcribe(str(video_path), **common)
            effective["batch_size"] = 1

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
    finally:
        # Nunca vaza a thread de diarize — junta mesmo se o loop do Whisper levantar.
        if executor is not None:
            executor.shutdown(wait=True)

    # Diarizacao: grava spk por palavra e speaker por segmento.
    # Falha aqui nao derruba a transcricao — legendas caem em cor unica.
    # future.result() re-levanta a excecao da thread DENTRO deste try (overlap) —
    # mesmo padrao de degradacao do caminho sequencial.
    speakers = 0
    diarize_error = None
    if diarize:
        try:
            if diar_future is not None:  # overlapped (cuda)
                turns = diar_future.result()
            else:                        # sequencial (cpu / fallback)
                turns = diarize_turns(video_path, num_speakers=num_speakers)
            speakers = assign_speakers(segments, turns)
        except Exception as exc:  # noqa: BLE001 — degradacao intencional
            diarize_error = str(exc)

    duration = round(float(info.duration), 3)
    transcript = {
        "video_id": video_id,
        "language": "pt",
        "model": effective["model"],
        "duration": duration,
        "speakers": speakers,
        "segments": segments,
    }
    _write_json(transcript_path(video_id), transcript)

    compact = {
        **transcript,
        "segments": [{k: v for k, v in s.items() if k != "words"} for s in segments],
    }
    _write_json(transcript_compact_path(video_id), compact)

    transcript_srt_path(video_id).write_text(_build_srt(segments), encoding="utf-8")

    summary = {
        "segments": len(segments),
        "words": total_words,
        "duration": duration,
        "device": effective["device"],
        "model": effective["model"],
        "batch_size": effective.get("batch_size", 1),
        "speakers": speakers,
    }
    if diarize_error:
        summary["diarize_error"] = diarize_error
    return summary

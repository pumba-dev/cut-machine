"""Diarizacao de falantes com sherpa-onnx (CPU, sem torch, sem token HF).

Stack: segmentacao pyannote/segmentation-3.0 em ONNX + embeddings NeMo
TitaNet-large + clustering — tudo via sherpa-onnx (onnxruntime puro).
Modelos MIT redistribuidos como release assets do GitHub k2-fsa/sherpa-onnx
(o gate do HuggingFace fica fora do caminho); download unico para
models/diarization/ (gitignored).

Atribuicao palavra->falante: intersecao temporal maxima (algoritmo do
whisperX) + suavizacao por sentenca via voto majoritario — obrigatoria
porque timestamps do faster-whisper derrapam centenas de ms perto de
trocas de turno.
"""
import os
import subprocess
import sys
import tarfile
import urllib.request
import wave
from bisect import bisect_left
from collections import Counter
from pathlib import Path

import numpy as np

from .paths import MODELS_ROOT

DIARIZE_MODELS_DIR = MODELS_ROOT / "diarization"

# Typo "recongition" e real na URL do release upstream.
_SEG_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
            "speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2")
_EMB_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
            "speaker-recongition-models/nemo_en_titanet_large.onnx")

SEG_MODEL = DIARIZE_MODELS_DIR / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
EMB_MODEL = DIARIZE_MODELS_DIR / "nemo_en_titanet_large.onnx"

# Diarizacao automatica (num_speakers nao informado): roda com um TETO de
# clusters e funde os micro-clusters de ruido. Clustering por threshold puro e
# inutilizavel aqui (dependente da duracao: 0.5 deu 83 falantes num podcast de 2;
# a janela entre arco-iris e colapso e' fina demais). num_clusters=k forca k
# clusters exatos; num audio real de 2 pessoas isso gera 2 dominantes + varios
# fragmentos soltos de 1-2 turnos. Roda-se com teto folgado e fundem-se os
# clusters abaixo de MIN_SPEAKER_SHARE do tempo de fala no falante major mais
# proximo no tempo — sobra o numero real de falantes (2/3), sem arco-iris.
AUTO_MAX_SPEAKERS = 6
MIN_SPEAKER_SHARE = 0.08

# Threads da diarizacao (onnxruntime CPU). Defaults 2/4 (seg/emb). MEDIDO
# (12-core, clip de 10min): subir threads NAO acelera — 2/4=158s, 3/6=154s,
# 4/8=168s (pior), e o resultado e byte-identico (mesmo hash de turns). O
# workload nao e thread-bound (dependencia sequencial por chunk). Deixado
# overridavel por env so pra experimentacao futura noutra maquina; nao mexa sem
# medir. A diarizacao roda concorrente com o whisper (GPU) no caminho normal
# (core.transcribe.whisper_local), entao seu custo fica escondido sob o whisper.
_SEG_THREADS = int(os.environ.get("DIARIZE_SEG_THREADS") or 0) or 2
_EMB_THREADS = int(os.environ.get("DIARIZE_EMB_THREADS") or 0) or 4

# Palavras a menos de 0.25s de uma fronteira de turno sao pouco confiaveis
# (drift do whisper); sentenca inteira vai para o falante majoritario.
_SENTENCE_END = (".", "!", "?", "…")
_SENTENCE_MAX_WORDS = 50


def _download(url: str, dest: Path) -> None:
    """Baixa url para dest de forma atomica (arquivo .part + rename)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    print(f"[diarize] baixando {url} -> {dest}", file=sys.stderr)
    urllib.request.urlretrieve(url, part)
    part.replace(dest)


def ensure_models() -> None:
    """Garante os dois modelos ONNX em models/diarization/ (idempotente)."""
    if not SEG_MODEL.exists():
        tar_path = DIARIZE_MODELS_DIR / "segmentation.tar.bz2"
        _download(_SEG_URL, tar_path)
        with tarfile.open(tar_path, "r:bz2") as tar:
            try:
                tar.extractall(DIARIZE_MODELS_DIR, filter="data")
            except TypeError:  # Python < 3.11.4 sem parametro filter
                tar.extractall(DIARIZE_MODELS_DIR)
        tar_path.unlink()
        if not SEG_MODEL.exists():
            raise FileNotFoundError(f"modelo de segmentacao nao encontrado apos extracao: {SEG_MODEL}")
    if not EMB_MODEL.exists():
        _download(_EMB_URL, EMB_MODEL)


def extract_wav16k(video: Path, wav: Path) -> None:
    """Extrai audio mono 16kHz PCM s16le com ffmpeg (formato do sherpa-onnx)."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(video),
           "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
           "-y", str(wav)]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-10:])
        raise RuntimeError(f"ffmpeg falhou ao extrair audio (exit {proc.returncode}): {tail}")


def read_wav16k_mono(wav: Path) -> np.ndarray:
    """Le wav mono 16kHz s16le como float32 1-D em [-1, 1] (stdlib wave)."""
    with wave.open(str(wav), "rb") as wf:
        if wf.getframerate() != 16000 or wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            raise ValueError(
                f"wav inesperado: rate={wf.getframerate()} ch={wf.getnchannels()} "
                f"width={wf.getsampwidth()} (esperado 16000/1/2)")
        pcm = wf.readframes(wf.getnframes())
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def _remap_by_talk_time(turns: list[dict]) -> list[dict]:
    """Reindexa falantes por tempo total de fala (0 = quem mais fala)."""
    totals: Counter = Counter()
    for t in turns:
        totals[t["speaker"]] += t["end"] - t["start"]
    order = [spk for spk, _ in totals.most_common()]
    remap = {old: new for new, old in enumerate(order)}
    return [{**t, "speaker": remap[t["speaker"]]} for t in turns]


def _merge_minor_speakers(turns: list[dict], min_share: float = MIN_SPEAKER_SHARE) -> list[dict]:
    """Funde clusters de ruido (pouco tempo de fala) no falante major mais proximo.

    num_clusters forcado gera N clusters exatos: num audio real de 2 pessoas,
    2 dominantes + varios fragmentos soltos. Falante com < min_share do tempo
    total de fala e' considerado ruido e cada turno seu vai para o falante
    "major" (>= min_share) mais proximo no tempo. Sobra o numero real de
    falantes. Idempotente se todos ja sao majors.
    """
    if len(turns) < 2:
        return turns
    total = sum(t["end"] - t["start"] for t in turns)
    if total <= 0:
        return turns
    talk: Counter = Counter()
    for t in turns:
        talk[t["speaker"]] += t["end"] - t["start"]
    major = {spk for spk, dur in talk.items() if dur >= min_share * total}
    if len(major) <= 1:
        # 0 ou 1 falante relevante: colapsa tudo no que mais fala.
        top = talk.most_common(1)[0][0]
        return [{**t, "speaker": top} for t in turns]
    major_turns = [t for t in turns if t["speaker"] in major]
    out: list[dict] = []
    for t in turns:
        if t["speaker"] in major:
            out.append(t)
            continue
        nearest = min(major_turns,
                      key=lambda m: max(m["start"] - t["end"], t["start"] - m["end"], 0.0))
        out.append({**t, "speaker": nearest["speaker"]})
    return out


def diarize_turns(video: Path, num_speakers: int = -1) -> list[dict]:
    """Diariza o audio do video; retorna turnos [{start, end, speaker}] em segundos.

    num_speakers > 0 fixa exatamente N falantes (merge ignorado) — passe quando
    conhecido: e' o caminho mais confiavel.

    num_speakers <= 0 (automatico): roda com teto AUTO_MAX_SPEAKERS e funde os
    micro-clusters de ruido (_merge_minor_speakers). Nao usamos clustering por
    threshold puro: e' inutilizavel aqui (ver nota em AUTO_MAX_SPEAKERS).

    Falantes saem reindexados por tempo de fala (0 = quem mais fala).
    """
    import sherpa_onnx

    ensure_models()
    wav = video.parent / "audio16k.tmp.wav"
    try:
        extract_wav16k(video, wav)
        audio = read_wav16k_mono(wav)
    finally:
        wav.unlink(missing_ok=True)

    auto = num_speakers <= 0
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(SEG_MODEL)),
            num_threads=_SEG_THREADS,
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(EMB_MODEL),
            num_threads=_EMB_THREADS,
        ),
        clustering=sherpa_onnx.FastClusteringConfig(
            # auto: teto folgado + merge do ruido depois. Fixo: exatamente N.
            # num_clusters > 0 ignora threshold (deixado no default do sherpa).
            num_clusters=AUTO_MAX_SPEAKERS if auto else num_speakers,
        ),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not config.validate():
        raise RuntimeError("config de diarizacao invalida (modelos ausentes/corrompidos?)")

    sd = sherpa_onnx.OfflineSpeakerDiarization(config)
    if sd.sample_rate != 16000:
        raise RuntimeError(f"sample rate do modelo: {sd.sample_rate}, esperado 16000")

    def _progress(processed: int, total: int) -> int:
        print(f"[diarize] {processed}/{total} chunks", file=sys.stderr)
        return 0

    result = sd.process(audio, callback=_progress).sort_by_start_time()
    turns = [{"start": round(seg.start, 3), "end": round(seg.end, 3),
              "speaker": int(seg.speaker)} for seg in result]
    if auto:
        turns = _merge_minor_speakers(turns)
    return _remap_by_talk_time(turns)


def _word_speaker(w_start: float, w_end: float, turns: list[dict],
                  starts: list[float], max_len: float, pmax_end: list[int]) -> int | None:
    """Falante com maior intersecao temporal com a palavra; gap -> turno mais proximo.

    turns ordenados por start; starts/max_len/pmax_end pre-computados para
    restringir a varredura (O(palavras x turnos) inviabiliza videos longos).
    """
    hi = bisect_left(starts, w_end)  # turnos com start < w_end
    overlap: Counter = Counter()
    j = hi - 1
    while j >= 0 and turns[j]["start"] > w_start - max_len:
        t = turns[j]
        ov = min(t["end"], w_end) - max(t["start"], w_start)
        if ov > 0:
            overlap[t["speaker"]] += ov
        j -= 1
    if overlap:
        return overlap.most_common(1)[0][0]
    # Gap: escolhe o turno mais proximo. Depois = turns[hi] (menor start >=
    # w_end, sorted). Antes = maior end em [0, hi) (pmax_end) — NAO turns[hi-1]:
    # com turnos longos sobrepostos o mais proximo antes pode estar bem atras
    # no indice. Ambos garantidamente sem sobreposicao aqui (senao overlap != {}).
    best, best_dist = None, None
    if hi < len(turns):
        best, best_dist = turns[hi]["speaker"], turns[hi]["start"] - w_end
    if hi > 0:
        b = turns[pmax_end[hi - 1]]
        dist = w_start - b["end"]
        if best_dist is None or dist < best_dist:
            best = b["speaker"]
    return best


def _smooth_sentences(words: list[dict]) -> None:
    """Voto majoritario por sentenca: reatribui trocas espurias no meio da frase."""
    sentence: list[dict] = []
    for w in words:
        sentence.append(w)
        if w["w"].endswith(_SENTENCE_END) or len(sentence) >= _SENTENCE_MAX_WORDS:
            _majority_vote(sentence)
            sentence = []
    _majority_vote(sentence)


def _majority_vote(sentence: list[dict]) -> None:
    spks = [w["spk"] for w in sentence if w.get("spk") is not None]
    if len(set(spks)) <= 1:
        return
    maj, count = Counter(spks).most_common(1)[0]
    if count / len(spks) > 0.5:
        for w in sentence:
            w["spk"] = maj


def assign_speakers(segments: list[dict], turns: list[dict]) -> int:
    """Grava `spk` em cada palavra e `speaker` em cada segmento (voto majoritario).

    Muta `segments` in place. Retorna o numero de falantes distintos dos
    turnos. Sem turnos: nada e gravado e retorna 0.
    """
    if not turns:
        return 0
    turns = sorted(turns, key=lambda t: t["start"])
    starts = [t["start"] for t in turns]
    max_len = max(t["end"] - t["start"] for t in turns)
    # pmax_end[i] = indice do turno com maior end em turns[0..i] (para achar,
    # num gap, o turno anterior mais proximo mesmo com turnos longos fora de ordem de end).
    pmax_end: list[int] = []
    best_i = 0
    for i, t in enumerate(turns):
        if t["end"] > turns[best_i]["end"]:
            best_i = i
        pmax_end.append(best_i)
    all_words = [w for seg in segments for w in seg.get("words", [])]
    for w in all_words:
        w["spk"] = _word_speaker(w["start"], w["end"], turns, starts, max_len, pmax_end)
    _smooth_sentences(all_words)
    for seg in segments:
        spks = [w["spk"] for w in seg.get("words", []) if w.get("spk") is not None]
        if spks:
            seg["speaker"] = Counter(spks).most_common(1)[0][0]
    return len({t["speaker"] for t in turns})

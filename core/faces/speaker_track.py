"""Rastreio do falante ATIVO por tempo (AV-sync boca x audio), CPU-only.

Constroi a peca que falta entre a diarizacao (core.diarize: quem fala, por
audio) e o faces.json (core.faces.analyze: quem aparece, por video) -- os dois
pipelines hoje sao independentes. Aqui, para cada turno de fala (reconstruido
do transcript ja diarizado), reamostra o video em fps ALTO (so dentro do turno,
nao o video inteiro -- orcamento de frames adaptativo, mesma logica de
core.faces.analyze), detecta rostos (YuNet), rastreia cada rosto por IoU
frame-a-frame dentro do turno e mede o movimento da regiao da boca (diferenca
de pixel entre frames consecutivos do mesmo rosto). Correlaciona esse sinal
visual com a envolvente RMS do audio do proprio turno (janela deslizante) --
o rosto cuja boca mais "acompanha" o audio e o falante ativo daquele turno.

Clusteriza os rostos vencedores de TODOS os turnos (mesmo algoritmo guloso de
core.faces.cluster, embedding SFace) para uma identidade global consistente
ao longo do video (0 = quem mais aparece falando), independente do faces.json
(clustering proprio, auto-contido -- evita acoplar duas amostragens distintas).

Degrada com seguranca (mesma filosofia de faces.json): sem transcript
diarizado, sem correlacao confiavel, ou falha de CV -> `degraded: true`,
`segments: []`; o render (core.render.reframe) cai no crop central estatico.
"""
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .. import paths
from ..media import video_info
from .analyze import _read_exact
from .cluster import cluster_embeddings

# distancia minima entre trocas de "camera" (turnos do mesmo falante emendados
# viram 1 segmento so). Ver core.render.reframe (hard cut entre planos).
DEFAULT_MIN_SEGMENT_S = 1.2
# score minimo (correlacao boca x audio) para aceitar um turno como resolvido;
# abaixo disso o turno fica sem segmento (reframe cai no crop central ali).
DEFAULT_MIN_CONFIDENCE = 0.15


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_speaker_track(video_id: str) -> dict | None:
    p = paths.speaker_track_path(video_id)
    if not p.exists():
        return None
    try:
        import json
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _degraded(video_id: str, reason: str) -> dict:
    return {"schema_version": 1, "video_id": video_id, "generated_at": _now(),
            "degraded": True, "reason": reason, "segments": []}


# ---------------------------------------------------------------------------
# Turnos a partir do transcript ja diarizado (core.diarize grava `spk` por
# palavra). Turnos brutos da diarizacao nao sao persistidos em disco -- so o
# resultado (spk/speaker) sobrevive no transcript.json -- entao reconstruimos
# aqui agrupando palavras consecutivas do mesmo `spk`.
# ---------------------------------------------------------------------------

def turns_from_transcript(transcript: dict, max_gap: float = 1.0) -> list[dict]:
    """Turnos [{start, end, speaker}] a partir do `spk` por palavra. `max_gap`:
    pausas ate esse tamanho ainda emendam no mesmo turno (evita fragmentar em
    micro-turnos por hesitacao). Sem diarizacao (spk ausente) -> lista vazia."""
    words = sorted(
        (w for seg in transcript.get("segments", []) for w in seg.get("words", [])
         if isinstance(w.get("spk"), int) and not isinstance(w.get("spk"), bool)),
        key=lambda w: w["start"],
    )
    turns: list[dict] = []
    cur: dict | None = None
    for w in words:
        if cur and w["spk"] == cur["speaker"] and w["start"] - cur["end"] <= max_gap:
            cur["end"] = w["end"]
        else:
            if cur:
                turns.append(cur)
            cur = {"start": w["start"], "end": w["end"], "speaker": w["spk"]}
    if cur:
        turns.append(cur)
    return turns


# ---------------------------------------------------------------------------
# Amostragem de frames dentro de uma janela [start, start+dur) do source.
# ---------------------------------------------------------------------------

def _iter_window_frames(source: Path, start: float, dur: float, interval: float,
                        w: int, h: int):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{max(start, 0.0):.3f}", "-t", f"{max(dur, 0.0):.3f}",
           "-i", str(source), "-vf", f"fps=1/{interval:.6f},scale={w}:{h}",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    frame_bytes = w * h * 3
    i = 0
    try:
        while True:
            buf = _read_exact(proc.stdout, frame_bytes)
            if buf is None:
                break
            yield round(start + i * interval, 3), np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3)
            i += 1
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.wait()


# ---------------------------------------------------------------------------
# Boca: crop em torno dos 2 pontos de canto de boca (kps do YuNet), diferenca
# de pixel entre frames consecutivos do mesmo rosto = sinal de "fala".
# ---------------------------------------------------------------------------

def _mouth_patch(frame: np.ndarray, kps: list, size: tuple[int, int] = (24, 16)):
    import cv2
    rm, lm = kps[3], kps[4]
    cx, cy = (rm[0] + lm[0]) / 2.0, (rm[1] + lm[1]) / 2.0
    mw = abs(lm[0] - rm[0]) or 4.0
    half_w, half_h = mw * 0.9, mw * 0.6
    x0, y0 = int(max(0, cx - half_w)), int(max(0, cy - half_h))
    x1 = int(min(frame.shape[1], cx + half_w))
    y1 = int(min(frame.shape[0], cy + half_h))
    if x1 <= x0 or y1 <= y0:
        return None
    gray = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, size).astype(np.float32) / 255.0


def _mouth_diff(a, b) -> float:
    if a is None or b is None:
        return 0.0
    return float(np.mean(np.abs(a - b)))


def _iou(a: list, b: list) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix0, iy0 = max(ax, bx), max(ay, by)
    ix1, iy1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _track_within_turn(dets_by_frame: list[list[dict]], iou_thresh: float = 0.3) -> list[list[tuple[int, int]]]:
    """Rastros [(indice_frame, indice_deteccao)] por IoU frame-a-frame (sem
    persistencia por gap: rosto que some 1 frame vira um rastro novo -- simples
    e suficiente, a fps alta o suficiente para nao fragmentar turnos curtos)."""
    tracks: list[list[tuple[int, int]]] = []
    active: dict[int, list] = {}
    for fi, dets in enumerate(dets_by_frame):
        matched: set[int] = set()
        for ti, bbox in list(active.items()):
            best_j, best_iou = -1, iou_thresh
            for j, d in enumerate(dets):
                if j in matched:
                    continue
                iou = _iou(bbox, d["bbox"])
                if iou > best_iou:
                    best_j, best_iou = j, iou
            if best_j >= 0:
                tracks[ti].append((fi, best_j))
                active[ti] = dets[best_j]["bbox"]
                matched.add(best_j)
            else:
                del active[ti]
        for j, d in enumerate(dets):
            if j not in matched:
                tracks.append([(fi, j)])
                active[len(tracks) - 1] = d["bbox"]
    return tracks


# ---------------------------------------------------------------------------
# Audio: RMS por janela de tempo (energia da fala naquele intervalo).
# ---------------------------------------------------------------------------

def _rms_in_window(audio: np.ndarray, sr: int, t0: float, t1: float) -> float:
    i0, i1 = int(max(0.0, t0) * sr), int(max(0.0, t1) * sr)
    i0, i1 = max(0, i0), min(len(audio), max(i0 + 1, i1))
    if i1 <= i0:
        return 0.0
    seg = audio[i0:i1].astype(np.float64)
    return float(np.sqrt(np.mean(seg ** 2)))


def _safe_corr(a: np.ndarray, b: np.ndarray) -> float | None:
    if a.std() < 1e-6 or b.std() < 1e-6:
        return None
    r = float(np.corrcoef(a, b)[0, 1])
    return r if r == r else None  # descarta NaN


def _windowed_correlation(motion: np.ndarray, audio: np.ndarray, window: int) -> float:
    """Correlacao de Pearson em janelas deslizantes (~1s cada), media das
    janelas com variancia suficiente. Serie curta demais -> 1 janela so."""
    if len(motion) < 3:
        return 0.0
    if len(motion) <= window:
        c = _safe_corr(motion, audio)
        return c if c is not None else 0.0
    scores = []
    step = max(1, window // 2)
    for i in range(0, len(motion) - window + 1, step):
        c = _safe_corr(motion[i:i + window], audio[i:i + window])
        if c is not None:
            scores.append(c)
    return float(np.mean(scores)) if scores else 0.0


# ---------------------------------------------------------------------------
# Processamento por turno.
# ---------------------------------------------------------------------------

def _process_turn(engine, source: Path, turn: dict, fps: float, w: int, h: int,
                  audio: np.ndarray, window: int) -> list[dict]:
    """Rostos candidatos do turno com score de sincronia boca x audio, bbox
    representativo (fracao 0-1 do frame) e embedding (p/ clustering global)."""
    interval = 1.0 / fps
    frames = list(_iter_window_frames(source, turn["start"], turn["end"] - turn["start"],
                                      interval, w, h))
    if len(frames) < 3:
        return []

    dets_by_frame: list[list[dict]] = []
    mouth_by_frame: list[list] = []
    for _, frame in frames:
        fd, fm = [], []
        for fdet in engine.detect(frame):
            x, y, fw, fh = fdet["bbox"]
            fd.append({"bbox": [x / w, y / h, fw / w, fh / h],
                       "raw": fdet["raw"], "score": fdet["score"]})
            fm.append(_mouth_patch(frame, fdet["kps"]))
        dets_by_frame.append(fd)
        mouth_by_frame.append(fm)

    tracks = _track_within_turn(dets_by_frame)
    ts_list = [ts for ts, _ in frames]
    out: list[dict] = []
    for track in tracks:
        if len(track) < 3:
            continue
        motion = [0.0]
        for k in range(1, len(track)):
            fi0, j0 = track[k - 1]
            fi1, j1 = track[k]
            motion.append(_mouth_diff(mouth_by_frame[fi0][j0], mouth_by_frame[fi1][j1])
                         if fi1 - fi0 == 1 else 0.0)
        track_ts = [ts_list[fi] for fi, _ in track]
        audio_e = [
            _rms_in_window(audio, 16000, track_ts[k - 1] if k else max(0.0, track_ts[0] - interval),
                           track_ts[k])
            for k in range(len(track_ts))
        ]
        score = _windowed_correlation(np.array(motion), np.array(audio_e), window)
        best_k = max(range(len(track)), key=lambda k: dets_by_frame[track[k][0]][track[k][1]]["score"])
        fi, j = track[best_k]
        _, frame = frames[fi]
        emb, _ = engine.embed(frame, dets_by_frame[fi][j]["raw"])
        out.append({"score": score, "bbox": dets_by_frame[fi][j]["bbox"], "embedding": emb})
    return out


def _merge_segments(segments: list[dict], min_gap: float) -> list[dict]:
    if not segments:
        return segments
    segments = sorted(segments, key=lambda s: s["start"])
    merged = [dict(segments[0])]
    for seg in segments[1:]:
        last = merged[-1]
        if seg["identity"] == last["identity"] and seg["start"] - last["end"] <= min_gap:
            last["end"] = seg["end"]
            last["confidence"] = round((last["confidence"] + seg["confidence"]) / 2, 3)
        else:
            merged.append(dict(seg))
    return merged


# ---------------------------------------------------------------------------
# Entrada principal.
# ---------------------------------------------------------------------------

def analyze_speaker_track(video: Path, video_id: str, transcript: dict, *,
                          fps: float = 5.0, max_frames: int = 4000,
                          min_segment_s: float = DEFAULT_MIN_SEGMENT_S,
                          min_confidence: float = DEFAULT_MIN_CONFIDENCE,
                          downscale_w: int = 480) -> dict:
    """Roda o rastreio e retorna o dict do speaker_track.json. Levanta em falha
    sistemica (cv2/ffmpeg); o chamador (scripts/track_speaker.py) degrada."""
    from ..diarize import extract_wav16k, read_wav16k_mono
    from .detector import FaceEngine

    turns = turns_from_transcript(transcript)
    if not turns:
        return _degraded(video_id, "sem turnos de diarizacao no transcript (spk ausente)")

    info = video_info(video)
    src_w, src_h = int(info["width"]), int(info["height"])
    if src_w <= 0 or src_h <= 0:
        return _degraded(video_id, f"dimensoes invalidas do source: {src_w}x{src_h}")
    w = downscale_w - (downscale_w % 2)
    h = round(src_h * w / src_w)
    h -= h % 2

    total_turn_dur = sum(t["end"] - t["start"] for t in turns)
    eff_fps = fps if total_turn_dur * fps <= max_frames else max(2.0, max_frames / max(total_turn_dur, 1.0))
    window = max(3, round(eff_fps))  # ~1s de janela p/ correlacao

    wav = video.parent / "audio16k.speaker_track.tmp.wav"
    try:
        extract_wav16k(video, wav)
        audio = read_wav16k_mono(wav)
    finally:
        wav.unlink(missing_ok=True)

    engine = FaceEngine(score_thresh=0.6)

    raw_segments: list[dict] = []
    n_turns_processed = 0
    for i, turn in enumerate(turns):
        cands = _process_turn(engine, video, turn, eff_fps, w, h, audio, window)
        n_turns_processed += 1
        if not cands:
            continue
        best = max(cands, key=lambda c: c["score"])
        if best["score"] < min_confidence:
            continue
        raw_segments.append({"start": turn["start"], "end": turn["end"],
                             "confidence": best["score"], "bbox": best["bbox"],
                             "embedding": best["embedding"]})
        if (i + 1) % 20 == 0:
            print(f"[speaker_track] {i + 1}/{len(turns)} turnos, "
                  f"{len(raw_segments)} resolvidos", file=sys.stderr)

    if not raw_segments:
        return _degraded(video_id, "nenhum turno com correlacao boca x audio suficiente")

    labels = cluster_embeddings([s["embedding"] for s in raw_segments])
    talk_time: Counter = Counter()
    for seg, lab in zip(raw_segments, labels):
        talk_time[lab] += seg["end"] - seg["start"]
    remap = {lab: i for i, (lab, _) in enumerate(talk_time.most_common())}

    out_segments = [
        {"start": round(seg["start"], 3), "end": round(seg["end"], 3),
         "identity": remap[lab], "confidence": round(seg["confidence"], 3),
         "bbox": [round(v, 4) for v in seg["bbox"]]}
        for seg, lab in zip(raw_segments, labels)
    ]
    out_segments = _merge_segments(out_segments, min_segment_s)

    return {
        "schema_version": 1, "video_id": video_id, "generated_at": _now(),
        "degraded": False,
        "sampling": {"fps": round(eff_fps, 3), "turns_total": len(turns),
                     "turns_processed": n_turns_processed,
                     "segments_resolved": len(out_segments), "downscale_w": w,
                     "identities": len(remap)},
        "segments": out_segments,
    }

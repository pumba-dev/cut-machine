"""Amostra frames do source, detecta rostos/emocoes e monta o dict do faces.json.

Amostragem via ffmpeg (fps=1/interval) decodificado como rawvideo bgr24 num pipe
-> numpy -> cv2 (nada em disco). Interval adaptativo: interval =
max(interval_s, duracao/max_frames), entao um podcast de 2h cai em ~2500 frames
(~2.9s) e o custo CPU fica em minutos, sem estourar. bbox normalizado 0-1 (o
render extrai o frame full-res depois pelo ts). Host = identidade com maior tempo
de tela; identidades reindexadas por tempo de tela (0 = host).
"""
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .. import paths
from ..media import video_info
from .cluster import cluster_embeddings

# offset do nariz (relativo a distancia dos olhos) abaixo do qual o rosto e
# considerado frontal — heuristica barata p/ desempate de host / boa foto.
_FRONTAL_MAX = 0.35


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_faces(video_id: str) -> dict | None:
    p = paths.faces_path(video_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _read_exact(stream, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def _iter_frames(source: Path, interval: float, w: int, h: int, max_frames: int):
    """Gera (i, frame_bgr) amostrando o source a cada `interval` s, escalado p/ w x h."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(source),
           "-vf", f"fps=1/{interval:.6f},scale={w}:{h}",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    frame_bytes = w * h * 3
    i = 0
    try:
        while i < max_frames:
            buf = _read_exact(proc.stdout, frame_bytes)
            if buf is None:
                break
            yield i, np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3)
            i += 1
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.wait()


def _nose_offset(kps: list) -> float:
    """Offset horizontal do nariz vs centro dos olhos, em unidades de dist. dos olhos."""
    re, le, nose = kps[0], kps[1], kps[2]
    eye_cx = (re[0] + le[0]) / 2.0
    eye_d = abs(le[0] - re[0]) or 1.0
    return abs(nose[0] - eye_cx) / eye_d


def _build_identities(dets: list[dict], interval: float, duration: float) -> list[dict]:
    """Agrega os detections por cluster -> identidades, ordenadas por tempo de tela."""
    by_cluster: dict[int, list[dict]] = {}
    for d in dets:
        by_cluster.setdefault(d["_cluster"], []).append(d)

    idents = []
    for cid, group in by_cluster.items():
        frames_present = len({d["ts"] for d in group})
        screen_time = round(frames_present * interval, 1)
        emos = Counter(d["emotion"] for d in group if d["emotion"])
        total_emo = sum(emos.values())
        emotion_hist = ({k: round(v / total_emo, 3) for k, v in emos.most_common()}
                        if total_emo else {})
        frontal = sum(1 for d in group if d["_frontal"])
        rep = max(group, key=lambda d: d["det_score"])
        idents.append({
            "_cluster": cid,
            "frames_present": frames_present,
            "screen_time_s": screen_time,
            "share": round(screen_time / duration, 3) if duration else 0.0,
            "avg_area": round(sum(d["area"] for d in group) / len(group), 4),
            "frontal_share": round(frontal / len(group), 3),
            "representative_ts": rep["ts"],
            "emotion_hist": emotion_hist,
        })
    # host = maior tempo de tela; desempate por area media (rosto maior/mais perto).
    idents.sort(key=lambda x: (x["screen_time_s"], x["avg_area"]), reverse=True)
    return idents


def analyze_faces(video: Path, video_id: str, *, interval_s: float = 2.0,
                  max_frames: int = 2500, downscale_w: int = 640,
                  score_thresh: float = 0.6) -> dict:
    """Roda a extracao e retorna o dict do faces.json. Levanta em falha sistemica
    (cv2/modelos/ffmpeg); o chamador (scripts/analyze_faces.py) degrada."""
    from .detector import FaceEngine  # import tardio: cv2 so p/ quem usa a feature

    info = video_info(video)
    src_w, src_h = int(info["width"]), int(info["height"])
    duration = float(info["duration_s"])
    if src_w <= 0 or src_h <= 0:
        raise ValueError(f"dimensoes invalidas do source: {src_w}x{src_h}")

    interval = max(float(interval_s), duration / max_frames if max_frames > 0 else interval_s)
    w = downscale_w - (downscale_w % 2)
    h = round(src_h * w / src_w)
    h -= h % 2

    engine = FaceEngine(score_thresh=score_thresh)

    dets: list[dict] = []
    embs: list[np.ndarray] = []
    n_sampled = 0
    for i, frame in _iter_frames(video, interval, w, h, max_frames):
        ts = round(i * interval, 3)
        n_sampled += 1
        for fdet in engine.detect(frame):
            emb, aligned = engine.embed(frame, fdet["raw"])
            label, _ = engine.emotion(aligned)
            x, y, fw, fh = fdet["bbox"]
            dets.append({
                "ts": ts,
                "bbox": [round(x / w, 4), round(y / h, 4),
                         round(fw / w, 4), round(fh / h, 4)],
                "det_score": round(fdet["score"], 3),
                "emotion": label,
                "area": round((fw * fh) / (w * h), 4),
                "_frontal": _nose_offset(fdet["kps"]) < _FRONTAL_MAX,
            })
            embs.append(emb)
        if n_sampled % 200 == 0:
            print(f"[faces] {n_sampled} frames, {len(dets)} rostos", file=sys.stderr)

    labels = cluster_embeddings(embs) if embs else []
    for d, lab in zip(dets, labels):
        d["_cluster"] = lab

    identities = _build_identities(dets, interval, duration)
    remap = {ident["_cluster"]: new for new, ident in enumerate(identities)}
    for new, ident in enumerate(identities):
        ident.pop("_cluster")
        ident["id"] = new
        ident["role"] = "host" if new == 0 else "guest"
    # reordena as chaves p/ id/role virem primeiro (legibilidade)
    identities = [{"id": x["id"], "role": x["role"], **{k: v for k, v in x.items()
                   if k not in ("id", "role")}} for x in identities]

    frames_map: dict[float, list[dict]] = {}
    for d in dets:
        face = {"identity": remap.get(d["_cluster"]), "bbox": d["bbox"],
                "det_score": d["det_score"], "emotion": d["emotion"],
                "area": d["area"]}
        frames_map.setdefault(d["ts"], []).append(face)
    frames_out = [{"ts": ts, "faces": frames_map[ts]} for ts in sorted(frames_map)]

    return {
        "schema_version": 1,
        "video_id": video_id,
        "generated_at": _now(),
        "source_duration_s": round(duration, 3),
        "degraded": False,
        "sampling": {
            "interval_s": round(interval, 3),
            "frames_sampled": n_sampled,
            "downscale_w": w,
            "detector": "yunet_2023mar",
            "embed": "sface_2021dec",
            "emotion": "fer_mobilefacenet_2022july",
        },
        "identities": identities,
        "frames": frames_out,
    }

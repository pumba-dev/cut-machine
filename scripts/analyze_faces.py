"""CLI: detecta rostos + emocoes no source (fase `faces`, opt-in) -> faces.json.

Extracao pesada UNICA por video (espelha transcribe/diarize): amostra frames em
CPU, agrupa identidades por embedding e marca a mais presente como host. Roda
apos transcribe e antes de plan; e insumo do subagente thumbnail-director e da
thumb via IA.

Idempotente (stage faces done + faces.json existe -> skipped). Gate opt-in: conta
sem `thumbnail.face_aware` -> no-op barato (skipped, stage done). Falha de CV
degrada (faces.json degradado + stage done + emit ok) — nunca bloqueia o pipeline.

Uso: python scripts/analyze_faces.py --video-id <id> [--account <id>]
                                     [--interval 2.0] [--max-frames 2500] [--force]
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import accounts, paths, state
from core.cli import emit, fail
from core.render.thumbnail_config import resolve_thumbnail


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Deteccao de rosto/emocao do source (fase faces)")
    ap.add_argument("--video-id", required=True)
    ap.add_argument("--account", default=None, help="conta para o gate opt-in (default = conta padrao)")
    ap.add_argument("--interval", type=float, default=2.0, help="segundos entre frames amostrados")
    ap.add_argument("--max-frames", type=int, default=2500, help="teto de frames (interval e ajustado p/ caber)")
    ap.add_argument("--force", action="store_true", help="reprocessa mesmo se ja feito")
    args = ap.parse_args()

    vid = args.video_id
    st_path = paths.state_path(vid)
    st = state.load(st_path)
    if st is None:
        fail(f"state.json nao existe para {vid}; rode scripts/download.py antes", video_id=vid)

    faces_file = paths.faces_path(vid)
    if not args.force and state.stage_status(st, "faces") == "done" and faces_file.exists():
        emit(True, skipped=True, video_id=vid, faces=str(faces_file))
        return

    # Gate opt-in: sem face_aware na conta, a fase e um no-op barato.
    try:
        acc = accounts.get_account("youtube", args.account)
    except Exception:  # noqa: BLE001 — sem config valida, cai no default off
        acc = None
    if not resolve_thumbnail(acc).get("face_aware"):
        state.set_stage(st, "faces", "done", skipped=True, reason="face_aware off")
        state.save(st_path, st)
        emit(True, skipped=True, video_id=vid, reason="face_aware off")
        return

    video = paths.source_video_path(vid)
    if not video.exists():
        fail(f"source.mp4 nao encontrado: {video}", video_id=vid)

    state.set_stage(st, "faces", "running")
    state.save(st_path, st)

    # Import tardio: cv2/modelos so p/ quem realmente roda a feature.
    try:
        from core.faces import analyze_faces
        data = analyze_faces(video, vid, interval_s=args.interval, max_frames=args.max_frames)
        _write_json(faces_file, data)
    except Exception as exc:  # noqa: BLE001 — degrada, nunca bloqueia o pipeline
        msg = str(exc) or exc.__class__.__name__
        try:
            _write_json(faces_file, {
                "schema_version": 1, "video_id": vid, "generated_at": None,
                "degraded": True, "error": msg, "identities": [], "frames": [],
            })
        except Exception:  # noqa: BLE001
            pass
        state.set_stage(st, "faces", "done", degraded=True)
        state.record_error(st, "faces", msg)
        state.save(st_path, st)
        emit(True, degraded=True, video_id=vid, error=msg)
        return

    identities = data.get("identities", [])
    host = next((i for i in identities if i.get("role") == "host"), None)
    state.set_stage(st, "faces", "done",
                    identities=len(identities),
                    frames_sampled=data["sampling"]["frames_sampled"])
    state.save(st_path, st)
    emit(True, video_id=vid, identities=len(identities),
         frames_sampled=data["sampling"]["frames_sampled"],
         interval_s=data["sampling"]["interval_s"],
         host_share=(host or {}).get("share"),
         faces=str(faces_file))


if __name__ == "__main__":
    main()

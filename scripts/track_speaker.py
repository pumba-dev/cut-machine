"""CLI: rastreia o falante ativo por tempo, AV-sync boca x audio (fase
`speaker-track`, opt-in) -> speaker_track.json.

Roda apos `faces` e antes do `render`: e insumo do reframe dinamico (crop ao
redor de quem fala). Idempotente (stage speaker-track done + speaker_track.json
existe -> skipped). Gate opt-in: conta sem `reframe.enabled` -> no-op barato
(skipped, stage done). Falha de CV/audio degrada (speaker_track.json degradado
+ stage done + emit ok) -- nunca bloqueia o pipeline.

Uso: python scripts/track_speaker.py --video-id <id> [--account <id>]
                                     [--fps 5.0] [--max-frames 4000] [--force]
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import accounts, paths, state
from core.cli import emit, fail
from core.render.reframe_config import reframe_enabled, resolve_reframe


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Rastreio do falante ativo (fase speaker-track)")
    ap.add_argument("--video-id", required=True)
    ap.add_argument("--account", default=None, help="conta para o gate opt-in (default = conta padrao)")
    ap.add_argument("--fps", type=float, default=5.0, help="fps de amostragem dentro de cada turno")
    ap.add_argument("--max-frames", type=int, default=4000, help="teto de frames (fps e ajustado p/ caber)")
    ap.add_argument("--force", action="store_true", help="reprocessa mesmo se ja feito")
    args = ap.parse_args()

    vid = args.video_id
    st_path = paths.state_path(vid)
    st = state.load(st_path)
    if st is None:
        fail(f"state.json nao existe para {vid}; rode scripts/download.py antes", video_id=vid)

    track_file = paths.speaker_track_path(vid)
    if not args.force and state.stage_status(st, "speaker-track") == "done" and track_file.exists():
        emit(True, skipped=True, video_id=vid, speaker_track=str(track_file))
        return

    try:
        acc = accounts.get_account("youtube", args.account)
    except Exception:  # noqa: BLE001 — sem config valida, cai no default off
        acc = None
    rcfg = resolve_reframe(acc)
    if not reframe_enabled(rcfg):
        state.set_stage(st, "speaker-track", "done", skipped=True, reason="reframe off")
        state.save(st_path, st)
        emit(True, skipped=True, video_id=vid, reason="reframe off")
        return

    video = paths.source_video_path(vid)
    if not video.exists():
        fail(f"source.mp4 nao encontrado: {video}", video_id=vid)
    transcript_file = paths.transcript_path(vid)
    if not transcript_file.exists():
        fail(f"transcript.json nao encontrado: {transcript_file}", video_id=vid)
    transcript = json.loads(transcript_file.read_text(encoding="utf-8"))

    state.set_stage(st, "speaker-track", "running")
    state.save(st_path, st)

    # Import tardio: cv2/modelos so p/ quem realmente roda a feature.
    try:
        from core.faces.speaker_track import analyze_speaker_track
        data = analyze_speaker_track(
            video, vid, transcript,
            fps=args.fps, max_frames=args.max_frames,
            min_segment_s=float(rcfg["min_segment_s"]),
            min_confidence=float(rcfg["min_confidence"]),
        )
        _write_json(track_file, data)
    except Exception as exc:  # noqa: BLE001 — degrada, nunca bloqueia o pipeline
        msg = str(exc) or exc.__class__.__name__
        try:
            _write_json(track_file, {
                "schema_version": 1, "video_id": vid, "generated_at": None,
                "degraded": True, "reason": msg, "segments": [],
            })
        except Exception:  # noqa: BLE001
            pass
        state.set_stage(st, "speaker-track", "done", degraded=True)
        state.record_error(st, "speaker-track", msg)
        state.save(st_path, st)
        emit(True, degraded=True, video_id=vid, error=msg)
        return

    segments = data.get("segments", [])
    state.set_stage(st, "speaker-track", "done",
                    degraded=data.get("degraded", False),
                    segments=len(segments))
    state.save(st_path, st)
    emit(True, video_id=vid, degraded=data.get("degraded", False),
         segments=len(segments), sampling=data.get("sampling"),
         speaker_track=str(track_file))


if __name__ == "__main__":
    main()

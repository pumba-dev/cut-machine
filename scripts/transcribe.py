"""CLI: transcreve video-output/<video_id>/source.mp4 com faster-whisper."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import state
from core.cli import emit, fail
from core.paths import source_video_path, state_path, transcript_path
from core.transcribe import transcribe_video


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcricao local do video fonte de um workspace")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--device", default="auto", choices=("auto", "cuda", "cpu"))
    parser.add_argument("--compute", default="int8")
    args = parser.parse_args()

    st_path = state_path(args.video_id)
    st = state.load(st_path)
    if st is None:
        fail(f"state.json nao existe para {args.video_id}; rode scripts/download.py antes",
             video_id=args.video_id)

    if state.stage_status(st, "transcribe") == "done" and transcript_path(args.video_id).exists():
        emit(True, skipped=True, video_id=args.video_id,
             transcript=str(transcript_path(args.video_id)))
        return

    video = source_video_path(args.video_id)
    if not video.exists():
        fail(f"video fonte nao encontrado: {video}", video_id=args.video_id)

    state.set_stage(st, "transcribe", "running", model=args.model, device=args.device)
    state.save(st_path, st)

    try:
        summary = transcribe_video(
            video, args.video_id,
            model=args.model, device=args.device, compute=args.compute,
        )
    except Exception as exc:
        state.set_stage(st, "transcribe", "failed")
        state.record_error(st, "transcribe", str(exc))
        state.save(st_path, st)
        fail(str(exc), video_id=args.video_id, stage="transcribe")

    state.set_stage(st, "transcribe", "done", model=summary["model"], device=summary["device"])
    state.save(st_path, st)
    emit(True, video_id=args.video_id, **summary)


if __name__ == "__main__":
    main()

"""CLI: diariza um video ja transcrito e grava os falantes no transcript.

Retrofit para transcripts gerados antes da diarizacao existir (ou re-rodada
com --speakers/--threshold melhores). Nao mexe em state.json — a etapa
transcribe continua done; apenas transcript.json e transcript.compact.json
ganham os campos spk/speaker/speakers.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.cli import emit, fail
from core.diarize import assign_speakers, diarize_turns
from core.paths import source_video_path, transcript_compact_path, transcript_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Diarizacao de falantes de um transcript existente")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--speakers", type=int, default=-1,
                        help="numero exato de falantes, se conhecido (caminho confiavel); "
                             "omitido = auto (teto + merge de ruido)")
    parser.add_argument("--force", action="store_true",
                        help="re-diariza mesmo que o transcript ja tenha falantes")
    args = parser.parse_args()

    t_path = transcript_path(args.video_id)
    if not t_path.exists():
        fail(f"transcript.json nao existe para {args.video_id}; rode scripts/transcribe.py antes",
             video_id=args.video_id)
    video = source_video_path(args.video_id)
    if not video.exists():
        fail(f"video fonte nao encontrado: {video}", video_id=args.video_id)

    transcript = json.loads(t_path.read_text(encoding="utf-8"))
    if transcript.get("speakers", 0) > 0 and not args.force:
        emit(True, skipped=True, video_id=args.video_id, speakers=transcript["speakers"])
        return

    try:
        turns = diarize_turns(video, num_speakers=args.speakers)
        speakers = assign_speakers(transcript["segments"], turns)
    except Exception as exc:
        fail(str(exc), video_id=args.video_id)

    transcript["speakers"] = speakers
    t_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=1), encoding="utf-8")

    compact = {
        **transcript,
        "segments": [{k: v for k, v in s.items() if k != "words"} for s in transcript["segments"]],
    }
    transcript_compact_path(args.video_id).write_text(
        json.dumps(compact, ensure_ascii=False, indent=1), encoding="utf-8")

    emit(True, video_id=args.video_id, speakers=speakers, turns=len(turns))


if __name__ == "__main__":
    main()

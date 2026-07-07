"""Baixa o video fonte de uma URL suportada para video-output/<video_id>/.

Uso: python scripts/download.py --url <URL>
Idempotente: se o stage download ja esta done e source.mp4 existe, emite skipped.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json

from core import cli, paths, state
from core.sources import get_source


def main() -> None:
    parser = argparse.ArgumentParser(description="Baixa video fonte para o workspace")
    parser.add_argument("--url", required=True, help="URL do video (ex.: YouTube)")
    args = parser.parse_args()

    try:
        source = get_source(args.url)
    except LookupError as exc:
        cli.fail(str(exc))

    try:
        video_id = source.probe_id(args.url)
    except Exception as exc:
        cli.fail(f"falha ao identificar o video: {exc}", url=args.url)

    workspace = paths.workspace_dir(video_id, create=True)
    st_path = paths.state_path(video_id)
    st = state.load(st_path)
    video_path = paths.source_video_path(video_id)
    source_json_path = workspace / "source.json"

    if st and state.stage_status(st, "download") == "done" and video_path.exists():
        src = {}
        if source_json_path.exists():
            src = json.loads(source_json_path.read_text(encoding="utf-8"))
        cli.emit(
            True, skipped=True, video_id=video_id, path=str(video_path),
            duration_s=src.get("duration_s"), title=src.get("title"),
        )
        return

    if st is None:
        st = state.new_state(video_id, args.url)
    state.set_stage(st, "download", "running", source=source.name)
    state.save(st_path, st)

    try:
        src = source.fetch(args.url, workspace)
    except Exception as exc:
        state.record_error(st, "download", str(exc))
        state.set_stage(st, "download", "failed")
        state.save(st_path, st)
        cli.fail(f"download falhou: {exc}", video_id=video_id)

    source_json_path.write_text(
        json.dumps(src, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    state.set_stage(st, "download", "done", output="source.mp4")
    state.save(st_path, st)
    cli.emit(
        True, video_id=video_id, path=str(video_path),
        duration_s=src.get("duration_s"), title=src.get("title"),
    )


if __name__ == "__main__":
    main()

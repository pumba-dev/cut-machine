"""Renderiza clips de um video (ffmpeg + legendas ASS) a partir de clips.json."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import accounts, contracts, paths, state
from core.cli import emit, fail
from core.render import render_clip


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _output_rel(video_id: str, clip_id: str) -> str:
    return paths.clip_output_path(video_id, clip_id).relative_to(paths.ROOT).as_posix()


def _rel(path) -> str:
    return Path(path).resolve().relative_to(paths.ROOT).as_posix()


def _account_for(clip: dict) -> dict | None:
    """Conta do clip (para o brand da moldura). Tolerante: sem config valida,
    o render cai nos defaults de brand."""
    pub = clip.get("publish") or {}
    try:
        return accounts.get_account(pub.get("platform") or "youtube", pub.get("account"))
    except Exception:
        return None


def _skip_result(video_id: str, plan: dict, clip: dict) -> dict:
    """Resultado de clip ja rendered: regenera metadata.json so se o mp4 existe."""
    result = {"clip_id": clip["id"], "status": "rendered",
              "output": _output_rel(video_id, clip["id"])}
    if paths.clip_output_path(video_id, clip["id"]).exists():
        meta_err = _save_metadata(video_id, plan, clip)
        if meta_err:
            result["metadata_error"] = meta_err
    return result


def _save_metadata(video_id: str, plan: dict, clip: dict) -> str | None:
    """metadata.json e derivado e regeneravel: falha aqui nunca derruba o clip."""
    try:
        contracts.save_clip_metadata(
            paths.clip_metadata_path(video_id, clip["id"]), plan, clip)
        return None
    except Exception as exc:
        return str(exc) or exc.__class__.__name__


def _clip_error(clip: dict) -> str | None:
    """Valida format/start/end/duracao do clip contra FORMAT_RULES."""
    fmt = clip.get("format")
    if fmt not in contracts.FORMAT_RULES:
        return f"format invalido: {fmt}"
    rules = contracts.FORMAT_RULES[fmt]
    start, end = clip.get("start"), clip.get("end")
    if start is None or end is None or start >= end:
        return f"start/end invalidos ({start}..{end})"
    duration = end - start
    if not (rules["min_duration_s"] <= duration <= rules["max_duration_s"]):
        return (f"duracao {duration:.1f}s fora dos limites do formato {fmt} "
                f"({rules['min_duration_s']}-{rules['max_duration_s']}s)")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Renderiza clips de um video")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--clip", default=None, help="renderiza apenas este clip_id")
    parser.add_argument("--all-approved", action="store_true",
                        help="renderiza todos os clips com status approved")
    args = parser.parse_args()

    if bool(args.clip) == args.all_approved:
        fail("use exatamente um de --clip ou --all-approved")

    video_id = args.video_id
    state_file = paths.state_path(video_id)
    st = state.load(state_file)
    if st is None:
        fail(f"state.json nao encontrado para {video_id}; rode download antes")

    clips_file = paths.clips_path(video_id)
    if not clips_file.exists():
        fail(f"clips.json nao encontrado para {video_id}; rode o planejamento antes")
    plan = contracts.load_plan(clips_file)

    if not paths.source_video_path(video_id).exists():
        fail(f"source.mp4 nao encontrado em {paths.workspace_dir(video_id)}")

    if args.clip:
        try:
            targets = [contracts.get_clip(plan, args.clip)]
        except LookupError as exc:
            fail(str(exc))
        clip = targets[0]
        if clip.get("status") == "rendered" and paths.clip_output_path(video_id, clip["id"]).exists():
            emit(True, skipped=True, video_id=video_id,
                 results=[_skip_result(video_id, plan, clip)])
            return
    else:
        targets = [c for c in plan["clips"] if c.get("status") == "approved"]
        if not targets:
            rendered = [c for c in plan["clips"] if c.get("status") == "rendered"]
            if rendered:
                emit(True, skipped=True, video_id=video_id,
                     results=[_skip_result(video_id, plan, c) for c in rendered])
                return
            fail("nenhum clip com status approved em clips.json")

    transcript = None
    transcript_file = paths.transcript_path(video_id)
    if transcript_file.exists():
        transcript = json.loads(transcript_file.read_text(encoding="utf-8"))

    state.set_stage(st, "render", "running", started_at=_now())
    state.save(state_file, st)

    results: list[dict] = []
    for clip in targets:
        cid = clip["id"]
        err = _clip_error(clip)
        if err is None and clip["format"] == "short" and transcript is None:
            err = "transcript.json nao encontrado (short exige legendas)"
        if err:
            contracts.set_clip_status(clip, "failed", error=err)
            contracts.save_plan(clips_file, plan)
            state.record_error(st, "render", err, clip_id=cid)
            state.save(state_file, st)
            results.append({"clip_id": cid, "status": "failed", "output": None, "error": err})
            continue

        contracts.set_clip_status(clip, "rendering")
        contracts.save_plan(clips_file, plan)
        try:
            info = render_clip(clip, video_id, transcript, account=_account_for(clip))
        except Exception as exc:
            msg = str(exc)
            contracts.set_clip_status(clip, "failed", error=msg)
            contracts.save_plan(clips_file, plan)
            state.record_error(st, "render", msg, clip_id=cid)
            state.save(state_file, st)
            results.append({"clip_id": cid, "status": "failed", "output": None, "error": msg})
            continue

        render_block = clip.setdefault("render", {})
        render_block["output_path"] = _output_rel(video_id, cid)
        render_block["rendered_at"] = _now()
        render_block["actual_duration_s"] = round(info["duration_s"], 3)
        if info.get("thumbnail_path") is not None:
            render_block["thumbnail_path"] = _rel(info["thumbnail_path"])
            render_block["thumbnail_ts"] = round(float(info["thumbnail_ts"]), 3)
        contracts.set_clip_status(clip, "rendered")
        contracts.save_plan(clips_file, plan)
        result = {"clip_id": cid, "status": "rendered",
                  "output": render_block["output_path"]}
        if info.get("thumbnail_error"):
            result["thumbnail_error"] = info["thumbnail_error"]
        meta_err = _save_metadata(video_id, plan, clip)
        if meta_err:
            result["metadata_error"] = meta_err
        results.append(result)

    rendered = [r for r in results if r["status"] == "rendered"]
    failed = [r for r in results if r["status"] == "failed"]
    still_approved = [c for c in plan["clips"] if c.get("status") == "approved"]
    if rendered and not failed and not still_approved:
        stage = "done"
    elif rendered:
        stage = "partial"
    else:
        stage = "failed"
    state.set_stage(st, "render", stage,
                    clips_rendered=len(rendered), clips_failed=len(failed))
    state.save(state_file, st)

    if not rendered:
        emit(False, error="nenhum clip renderizado", video_id=video_id,
             stage=stage, results=results)
        sys.exit(1)
    emit(True, video_id=video_id, stage=stage, results=results)


if __name__ == "__main__":
    main()

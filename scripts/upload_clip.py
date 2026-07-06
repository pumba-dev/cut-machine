"""Publica um clip renderizado na plataforma/conta configuradas.

Uso: python scripts/upload_clip.py --video-id <id> --clip <clip_id>
     [--platform youtube] [--account <account_id>]

Regras: clip precisa estar 'rendered' ou 'queued'; respeita
account["daily_upload_limit"] via core.publishers.upload_log (excedente vira
'queued'); quota da API esgotada tambem re-enfileira. Idempotente: clip ja
'published' com remote_id vira skip.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from core import accounts, cli, contracts, paths, state
from core.publishers import QuotaExceededError, get_publisher, upload_log


def _publish_stage_status(plan: dict) -> str:
    """done quando nenhum clip resta em transito para publicacao."""
    pending = ("approved", "rendering", "rendered", "queued", "uploading", "failed")
    if any(c.get("status") in pending for c in plan.get("clips", [])):
        return "partial"
    return "done"


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica um clip renderizado.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--clip", required=True, help="id do clip em clips.json")
    parser.add_argument("--platform", default=None,
                        help="default: clip.publish.platform (ou youtube)")
    parser.add_argument("--account", default=None,
                        help="default: clip.publish.account ou conta default da plataforma")
    args = parser.parse_args()

    plan_path = paths.clips_path(args.video_id)
    if not plan_path.exists():
        cli.fail(f"clips.json nao encontrado para video {args.video_id}")
    plan = contracts.load_plan(plan_path)

    try:
        clip = contracts.get_clip(plan, args.clip)
    except LookupError as exc:
        cli.fail(str(exc))

    publish = clip.setdefault("publish", {})
    platform = args.platform or publish.get("platform") or "youtube"

    st_path = paths.state_path(args.video_id)
    st = state.load(st_path)
    if st is None:
        cli.fail(f"state.json nao encontrado para video {args.video_id}")

    if clip.get("status") == "published" and publish.get("remote_id"):
        cli.emit(True, skipped=True, clip=args.clip, platform=platform,
                 remote_id=publish["remote_id"], url=publish.get("url"))
        return

    if clip.get("status") not in ("rendered", "queued"):
        cli.fail(
            f"clip {args.clip} com status '{clip.get('status')}'; "
            "precisa estar rendered ou queued para upload", clip=args.clip)

    video_path = paths.clip_output_path(args.video_id, args.clip)
    if not video_path.exists():
        cli.fail(f"video renderizado nao encontrado: {video_path}", clip=args.clip)

    try:
        account = accounts.get_account(platform, args.account or publish.get("account"))
        publisher = get_publisher(platform)
    except LookupError as exc:
        cli.fail(str(exc), clip=args.clip)

    limit = int(account.get("daily_upload_limit") or 0)
    if limit and upload_log.count_today(account) >= limit:
        contracts.set_clip_status(clip, "queued")
        contracts.save_plan(plan_path, plan)
        state.set_stage(st, "publish", "partial")
        state.save(st_path, st)
        cli.emit(True, queued=True, clip=args.clip, platform=platform,
                 account=account["id"], reason="limite diario")
        return

    contracts.set_clip_status(clip, "uploading")
    contracts.save_plan(plan_path, plan)
    state.set_stage(st, "publish", "running")
    state.save(st_path, st)

    metadata = {
        "title": clip.get("title") or "",
        "description": clip.get("description") or "",
        "tags": clip.get("tags") or [],
        "category_id": publish.get("category_id") or "22",
        "privacy": publish.get("privacy") or "private",
        "made_for_kids": bool(publish.get("made_for_kids", False)),
        "language": plan.get("source", {}).get("language") or "pt-BR",
    }

    try:
        result = publisher.upload(video_path, metadata, account)
    except QuotaExceededError as exc:
        contracts.set_clip_status(clip, "queued")
        contracts.save_plan(plan_path, plan)
        state.set_stage(st, "publish", "partial")
        state.save(st_path, st)
        cli.fail(str(exc), queued=True, clip=args.clip, account=account["id"])
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        contracts.set_clip_status(clip, "failed", error=message)
        contracts.save_plan(plan_path, plan)
        state.record_error(st, "publish", message, clip_id=args.clip)
        state.set_stage(st, "publish", "partial")
        state.save(st_path, st)
        cli.fail(f"falha no upload do clip {args.clip}: {message}", clip=args.clip)

    publish.update({
        "platform": platform,
        "account": account["id"],
        "remote_id": result["remote_id"],
        "url": result["url"],
        "published_at": result["published_at"],
    })
    contracts.set_clip_status(clip, "published")
    contracts.save_plan(plan_path, plan)

    upload_log.append(account, {
        "video_id": args.video_id,
        "clip_id": args.clip,
        "remote_id": result["remote_id"],
    })

    state.set_stage(st, "publish", _publish_stage_status(plan))
    state.save(st_path, st)

    cli.emit(True, clip=args.clip, platform=platform, account=account["id"],
             remote_id=result["remote_id"], url=result["url"],
             published_at=result["published_at"])


if __name__ == "__main__":
    main()

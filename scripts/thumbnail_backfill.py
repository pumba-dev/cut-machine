"""Retrofit: reaplica thumbnails.set nos shorts ja publicados sem thumb confirmada.

Espelho do padrao qa_backfill.py/cleanup_published.py: usa o mesmo
thumbnails.set de core/publishers/youtube.py, fora do fluxo normal de
upload_clip.py, para o backlog de shorts publicados antes do fix (ou cuja
tentativa dentro do upload falhou). 1 tentativa por clip, como no upload.

So mexe em clips com status=='published', format=='short', com
render.thumbnail_path existente em disco (video ainda nao limpo pelo
cleanup) e publish.thumbnail_set != true.

Idempotente: pula clip com publish.thumbnail_set == true (--force reaplica
mesmo assim). Imprime UMA linha JSON no fim.

Uso: python scripts/thumbnail_backfill.py [--video-id <id>] [--force]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import accounts, contracts, paths
from core.cli import emit
from core.publishers import get_publisher

# Espaco entre clips (chamada real, nao skip) para nao rajar o
# uploadRateLimitExceeded do canal (limite de thumbnails, janela de 24h).
BACKFILL_INTER_CLIP_DELAY_S = 30


def _process_video(video_id: str, force: bool, first_call: bool) -> tuple[dict, bool, bool]:
    """Retorna (counts, first_call, rate_limited_stop). first_call vira False
    apos a 1a chamada real (usado pra saber se deve dormir antes da proxima).
    rate_limited_stop=True corta o clip corrente E sinaliza pro chamador nao
    seguir pros proximos videos (limite e por canal, nao por video)."""
    cf = paths.clips_path(video_id)
    plan = contracts.load_plan(cf)
    counts = {"set": 0, "failed": 0, "skipped": 0}
    changed = False
    rate_limited_stop = False
    for clip in plan["clips"]:
        if clip.get("status") != "published" or clip.get("format") != "short":
            continue
        publish = clip.setdefault("publish", {})
        if publish.get("thumbnail_set") and not force:
            counts["skipped"] += 1
            continue
        thumb_rel = (clip.get("render") or {}).get("thumbnail_path")
        remote_id = publish.get("remote_id")
        if not thumb_rel or not remote_id:
            counts["skipped"] += 1
            continue
        thumb_path = paths.ROOT / thumb_rel
        if not thumb_path.exists():
            print(f"{video_id}/{clip['id']}: thumb ausente ({thumb_path}), pulando",
                  file=sys.stderr)
            counts["skipped"] += 1
            continue

        if not first_call:
            time.sleep(BACKFILL_INTER_CLIP_DELAY_S)
        first_call = False

        try:
            account = accounts.get_account("youtube", publish.get("account"))
            publisher = get_publisher("youtube")
            ok, rate_limited = publisher.set_thumbnail(remote_id, thumb_path, account)
        except Exception as e:
            ok, rate_limited = False, False
            print(f"{video_id}/{clip['id']}: erro inesperado: {e}", file=sys.stderr)
        publish["thumbnail_set"] = ok
        counts["set" if ok else "failed"] += 1
        changed = True
        if rate_limited:
            print(f"thumbnail_backfill: uploadRateLimitExceeded em {video_id}/{clip['id']} "
                  "— parando o lote (limite e por canal; tente de novo mais tarde)",
                  file=sys.stderr)
            rate_limited_stop = True
            break
    if changed:
        contracts.save_plan(cf, plan)
    return counts, first_call, rate_limited_stop


def main() -> None:
    ap = argparse.ArgumentParser(description="Reaplica thumbnails.set nos shorts publicados")
    ap.add_argument("--video-id", default=None, help="so este video (default: todos)")
    ap.add_argument("--force", action="store_true", help="reaplica mesmo com thumbnail_set=true")
    args = ap.parse_args()

    if args.video_id:
        video_ids = [args.video_id]
    else:
        video_ids = sorted(d.name for d in paths.OUTPUT_ROOT.iterdir()
                           if d.is_dir() and (d / "clips.json").exists())

    total = {"set": 0, "failed": 0, "skipped": 0}
    per_video: dict[str, dict] = {}
    first_call = True
    rate_limited_stop = False
    for vid in video_ids:
        c, first_call, rate_limited_stop = _process_video(vid, args.force, first_call)
        if any(c.values()):
            per_video[vid] = c
        for k in total:
            total[k] += c[k]
        if rate_limited_stop:
            break

    emit(True, action="thumbnail_backfill", total=total, videos=per_video,
         rate_limited_stop=rate_limited_stop)


if __name__ == "__main__":
    main()

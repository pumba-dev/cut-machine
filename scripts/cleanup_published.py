"""Apaga a pasta de cada video totalmente postado (libera disco).

Um video e apagado quando tem >=1 clip published e nenhum clip pendente (todos
published/failed/rejected). O clips.json vai para video-output/_archive/ antes
(preserva URLs/IDs). A regra roda automatica ao final do publish_next.py apos
cada publicacao; este script existe para (1) retrofit do backlog ja concluido
(que o publish_next nao revisita, pois nao tem clip pendente) e (2) limpeza
manual em massa.

Idempotente. Use --dry-run para ver o que seria apagado sem apagar. Imprime
UMA linha JSON no fim.

Uso: python scripts/cleanup_published.py [--video-id <id>] [--dry-run]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import cleanup, contracts, paths
from core.cli import emit


def main() -> None:
    ap = argparse.ArgumentParser(description="Apaga a pasta de videos totalmente postados")
    ap.add_argument("--video-id", default=None, help="so este video (default: todos)")
    ap.add_argument("--dry-run", action="store_true",
                    help="so mostra o que apagaria; nao apaga nada")
    args = ap.parse_args()

    if not paths.OUTPUT_ROOT.exists():
        emit(True, skipped=True, reason="sem video-output"); return

    if args.video_id:
        video_ids = [args.video_id]
    else:
        video_ids = sorted(d.name for d in paths.OUTPUT_ROOT.iterdir()
                           if d.is_dir() and (d / "clips.json").exists())

    cleaned: list[dict] = []
    skipped = 0
    for vid in video_ids:
        cf = paths.clips_path(vid)
        if not cf.exists():
            continue
        plan = contracts.load_plan(cf)
        if not cleanup.video_complete(plan):
            skipped += 1
            continue
        if args.dry_run:
            cleaned.append({"video_id": vid, "dry_run": True,
                            "freed_bytes": cleanup.dir_size(paths.workspace_dir(vid))})
        else:
            cleaned.append(cleanup.purge_video(vid, plan))

    freed = sum(c.get("freed_bytes", 0) for c in cleaned)
    emit(True, action="cleanup_published", dry_run=args.dry_run,
         cleaned=cleaned, cleaned_count=len(cleaned),
         skipped_count=skipped, freed_bytes=freed)


if __name__ == "__main__":
    main()

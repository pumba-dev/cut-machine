"""Publica o PROXIMO clip pendente de um formato (short|corte), 1 por execucao.

Feito para o Agendador de Tarefas do Windows / cron: escolhe o proximo clip
ainda nao publicado (ordem intercalada entre videos, score desc), chama
scripts/upload_clip.py (publico por padrao + miniatura best-effort, respeita
daily_upload_limit/quota) e imprime UMA linha JSON com o resultado.

Idempotente e seguro para sobre-disparo: se a quota/limite diario estourou,
upload_clip.py apenas re-enfileira (nao gasta unidade) e este script reporta
{"skipped": true, "reason": "queued"}; o mesmo clip sera tentado na proxima vez.

Trava de QA: so publica clip que ja passou pelo qa-reviewer (qa.status ==
'pass'). Clip 'rendered' sem QA fica na fila ate o QA rodar — fecha o race em
que a Task pegaria um render ainda nao validado. Se ha pendentes mas nenhum
com QA, reporta reason='aguardando QA'.

Limpeza de disco: apos publicar com sucesso, se aquele video ficou completo
(>=1 published e nenhum clip pendente), a pasta dele e apagada — o clips.json
e arquivado antes (core.cleanup). Best-effort: nunca derruba o resultado do
publish.

Uso: python scripts/publish_next.py --format short|corte [--account <id>]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import cleanup, contracts, paths
from core.cli import emit

# status de clip prontos para upload (ainda nao publicados)
PENDING = ("rendered", "queued")


def _interleaved(video_ids: list[str], fmt: str) -> list[tuple[str, dict]]:
    """(video_id, clip) na ordem: round-robin entre videos, score desc dentro
    de cada video, so do formato pedido."""
    per: dict[str, list[dict]] = {}
    for vid in video_ids:
        cf = paths.clips_path(vid)
        if not cf.exists():
            continue
        plan = contracts.load_plan(cf)
        shorts = [c for c in plan["clips"] if c.get("format") == fmt]
        shorts.sort(key=lambda c: -(c.get("score") or 0))
        per[vid] = shorts
    order: list[tuple[str, dict]] = []
    i = 0
    while any(i < len(per.get(v, [])) for v in video_ids):
        for v in video_ids:
            lst = per.get(v, [])
            if i < len(lst):
                order.append((v, lst[i]))
        i += 1
    return order


def main() -> None:
    ap = argparse.ArgumentParser(description="Publica o proximo clip pendente de um formato")
    ap.add_argument("--format", required=True, choices=list(contracts.CLIP_FORMATS))
    ap.add_argument("--account", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="so mostra qual clip publicaria; nao sobe nada")
    args = ap.parse_args()

    if not paths.OUTPUT_ROOT.exists():
        emit(True, skipped=True, reason="sem video-output"); return
    video_ids = sorted(d.name for d in paths.OUTPUT_ROOT.iterdir()
                       if d.is_dir() and (d / "clips.json").exists())

    order = _interleaved(video_ids, args.format)
    pending = [(v, c) for v, c in order if c.get("status") in PENDING]
    # trava de QA: so publica clip aprovado pelo qa-reviewer (qa.status == 'pass')
    nxt = next(((v, c) for v, c in pending if contracts.qa_passed(c)), None)
    if nxt is None:
        total = len(order)
        done = sum(1 for _, c in order if c.get("status") == "published")
        awaiting_qa = sum(1 for _, c in pending if not contracts.qa_passed(c))
        emit(True, skipped=True,
             reason="aguardando QA" if awaiting_qa else "fila concluida",
             format=args.format, total=total, published=done,
             awaiting_qa=awaiting_qa)
        return

    vid, clip = nxt
    if args.dry_run:
        emit(True, dry_run=True, format=args.format, would_publish={
            "video_id": vid, "clip_id": clip["id"], "status": clip.get("status"),
            "score": clip.get("score"), "title": clip.get("title")})
        return
    cmd = [sys.executable, str(paths.ROOT / "scripts" / "upload_clip.py"),
           "--video-id", vid, "--clip", clip["id"]]
    if args.account:
        cmd += ["--account", args.account]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    # ultima linha JSON do upload_clip e o resultado canonico
    last = ""
    for line in (proc.stdout or "").strip().splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            last = line
    try:
        result = json.loads(last) if last else {"ok": False, "error": "sem saida JSON do upload_clip"}
    except json.JSONDecodeError:
        result = {"ok": False, "error": "saida do upload_clip nao e JSON", "raw": last[:300]}
    result["picked"] = {"video_id": vid, "clip_id": clip["id"], "format": args.format}
    # limpeza de disco: se este video ficou completo, apaga a pasta (arquiva
    # o clips.json antes). Best-effort — nunca invalida um publish bem-sucedido.
    if result.get("ok"):
        try:
            cleaned = cleanup.cleanup_if_complete(vid)
            if cleaned:
                result["cleanup"] = cleaned
        except Exception as e:  # noqa: BLE001 — limpeza nao pode derrubar o publish
            result["cleanup_error"] = str(e)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()

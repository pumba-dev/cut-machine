"""QA tecnico deterministico (ffprobe) — carimba qa.status nos clips 'rendered'.

Espelho em codigo do qa-reviewer (o agente LLM): roda os mesmos checks de
FORMAT_RULES via ffprobe e grava o bloco `qa` que o publish_next exige para
publicar. Serve para (1) retrofit da fila ja renderizada antes da trava de QA
existir e (2) rede de seguranca / re-verificacao em massa.

Por clip com status 'rendered':
  - probe o mp4; confere resolucao exata, duracao (contracts.expected_output_duration,
    +-0.5s -- end-start ou render.content_duration_s se o jump-cut mudou a duracao) e audio;
  - audio_risk == true -> status 'rejected' + qa.fail (mesmo com tecnica ok);
  - tudo ok -> qa.status 'pass' (mantem 'rendered');
  - check falhou -> status 'failed' + error + qa.fail.

Idempotente: pula clip que ja tem `qa` (use --force para revalidar).
Nao toca em clips com status != 'rendered'. Imprime UMA linha JSON no fim.

Uso: python scripts/qa_backfill.py [--video-id <id>] [--force]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import contracts, paths
from core.cli import emit
from core.media import video_info


def _check(clip: dict, mp4: Path) -> tuple[str, str | None]:
    """Retorna (veredito, note). veredito in {'pass','failed','rejected'}."""
    if not mp4.exists():
        return "failed", f"arquivo ausente: {mp4.name}"
    try:
        info = video_info(mp4)
    except Exception as e:  # ffprobe/stream quebrado
        return "failed", f"probe falhou: {e}"

    fmt = clip.get("format")
    rules = contracts.FORMAT_RULES.get(fmt)
    if rules is None:
        return "failed", f"format invalido: {fmt}"

    exp_w, exp_h = (int(x) for x in rules["resolution"].split("x"))
    if (info["width"], info["height"]) != (exp_w, exp_h):
        return "failed", (f"resolucao {info['width']}x{info['height']}, "
                          f"esperado {rules['resolution']}")

    expected = contracts.expected_output_duration(clip)
    if abs(info["duration_s"] - expected) > 0.5:
        return "failed", (f"duracao {info['duration_s']:.2f}s vs esperada "
                          f"{expected:.2f}s (conteudo + vinheta, tolerancia 0.5s)")

    if not info["has_audio"]:
        return "failed", "sem stream de audio"

    if clip.get("audio_risk"):
        return "rejected", "audio_risk: transcricao de baixa confianca no trecho"

    return "pass", None


def _process_video(video_id: str, force: bool) -> dict:
    cf = paths.clips_path(video_id)
    plan = contracts.load_plan(cf)
    counts = {"pass": 0, "failed": 0, "rejected": 0, "skipped": 0}
    changed = False
    for clip in plan["clips"]:
        if clip.get("status") != "rendered":
            continue
        if clip.get("qa") and not force:
            counts["skipped"] += 1
            continue
        mp4 = paths.clip_output_path(video_id, clip["id"])
        verdict, note = _check(clip, mp4)
        if verdict == "pass":
            contracts.set_clip_qa(clip, "pass")
        elif verdict == "rejected":
            contracts.set_clip_status(clip, "rejected", note)
            contracts.set_clip_qa(clip, "fail", note)
        else:  # failed
            contracts.set_clip_status(clip, "failed", note)
            contracts.set_clip_qa(clip, "fail", note)
        counts[verdict] += 1
        changed = True
    if changed:
        contracts.save_plan(cf, plan)
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Carimba qa.status nos clips rendered (ffprobe)")
    ap.add_argument("--video-id", default=None, help="so este video (default: todos)")
    ap.add_argument("--force", action="store_true", help="revalida mesmo clip que ja tem qa")
    args = ap.parse_args()

    if args.video_id:
        video_ids = [args.video_id]
    else:
        video_ids = sorted(d.name for d in paths.OUTPUT_ROOT.iterdir()
                           if d.is_dir() and (d / "clips.json").exists())

    total = {"pass": 0, "failed": 0, "rejected": 0, "skipped": 0}
    per_video: dict[str, dict] = {}
    for vid in video_ids:
        c = _process_video(vid, args.force)
        if any(c.values()):
            per_video[vid] = c
        for k in total:
            total[k] += c[k]

    emit(True, action="qa_backfill", total=total, videos=per_video)


if __name__ == "__main__":
    main()

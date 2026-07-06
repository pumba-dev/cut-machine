"""Contrato central do pipeline: clips.json (workspace/<id>/clips.json).

Donos por campo — ninguem sobrescreve campo de outro dono:
- clip-scout (LLM): objeto do clip + campos de analise (start/end, hook_text, score...)
- copywriter (LLM): title, title_alts, description, tags
- render_clip.py: bloco render.*
- upload_clip.py: bloco publish.* (remote_id, url, published_at)
- humano/orquestrador: transicao approved/rejected
"""
import json
import os
from pathlib import Path

CLIP_FORMATS = ("short", "corte")

# Maquina de estados por clip. "queued" existe por causa da quota de upload diaria.
CLIP_STATUSES = (
    "planned", "approved", "rejected", "rendering", "rendered",
    "queued", "uploading", "published", "failed",
)

FORMAT_RULES = {
    "short": {
        "min_duration_s": 15.0,
        "max_duration_s": 59.0,
        "resolution": "1080x1920",
        "crop": "center",
        "burn_captions": True,
    },
    "corte": {
        "min_duration_s": 120.0,
        "max_duration_s": 600.0,
        "resolution": "1920x1080",
        "crop": "none",
        "burn_captions": False,
    },
}


def new_plan(video_id: str, source: dict) -> dict:
    """source: url, title, channel, duration_s, width, height, fps, language."""
    return {
        "schema_version": 1,
        "video_id": video_id,
        "source": source,
        "generated_at": None,
        "clips": [],
        "rejected_notable": [],
    }


def load_plan(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_plan(path: Path, plan: dict) -> None:
    path = Path(path)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def get_clip(plan: dict, clip_id: str) -> dict:
    for clip in plan["clips"]:
        if clip["id"] == clip_id:
            return clip
    raise LookupError(f"clip {clip_id} nao existe em clips.json")


def set_clip_status(clip: dict, status: str, error: str | None = None) -> dict:
    if status not in CLIP_STATUSES:
        raise ValueError(f"status invalido: {status}")
    if status == "failed" and not error:
        raise ValueError("status failed exige mensagem em error")
    clip["status"] = status
    clip["error"] = error
    return clip


def validate_plan(plan: dict) -> list[str]:
    """Retorna lista de erros (vazia = valido). Nao lanca excecao."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    src_duration = float(plan.get("source", {}).get("duration_s") or 0)

    for clip in plan.get("clips", []):
        cid = clip.get("id", "<sem id>")
        if cid in seen_ids:
            errors.append(f"{cid}: id duplicado")
        seen_ids.add(cid)

        fmt = clip.get("format")
        if fmt not in CLIP_FORMATS:
            errors.append(f"{cid}: format invalido ({fmt})")
            continue
        rules = FORMAT_RULES[fmt]

        start, end = clip.get("start"), clip.get("end")
        if start is None or end is None or start >= end:
            errors.append(f"{cid}: start/end invalidos ({start}..{end})")
            continue
        duration = end - start
        if abs(duration - clip.get("duration_s", duration)) > 0.5:
            errors.append(f"{cid}: duration_s nao bate com end-start")
        if not (rules["min_duration_s"] <= duration <= rules["max_duration_s"]):
            errors.append(
                f"{cid}: duracao {duration:.1f}s fora dos limites do formato "
                f"{fmt} ({rules['min_duration_s']}-{rules['max_duration_s']}s)")
        if src_duration and end > src_duration + 1:
            errors.append(f"{cid}: end ({end}) alem da duracao do video fonte")

        if clip.get("status") not in CLIP_STATUSES:
            errors.append(f"{cid}: status invalido ({clip.get('status')})")

        score = clip.get("score")
        if score is None or not (0 <= score <= 100):
            errors.append(f"{cid}: score fora de 0-100 ({score})")

    return errors

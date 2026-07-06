"""Estado do pipeline por video (workspace/<id>/state.json).

Fonte de verdade para retomada: toda etapa le o estado antes de rodar e
nunca refaz etapa 'done'. Escrita atomica (tmp + os.replace) para que um
processo morto no meio nunca corrompa o arquivo.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

STAGES = ("download", "transcribe", "plan", "copy", "render", "qa", "publish")
STAGE_STATUSES = ("pending", "running", "partial", "done", "failed")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def new_state(video_id: str, url: str) -> dict:
    return {
        "schema_version": 1,
        "video_id": video_id,
        "url": url,
        "created_at": _now(),
        "updated_at": _now(),
        "stages": {s: {"status": "pending"} for s in STAGES},
        "last_error": None,
    }


def load(path: Path) -> dict | None:
    if not Path(path).exists():
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path: Path, state: dict) -> None:
    path = Path(path)
    state["updated_at"] = _now()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def stage_status(state: dict, stage: str) -> str:
    return state["stages"].get(stage, {}).get("status", "pending")


def set_stage(state: dict, stage: str, status: str, **fields) -> dict:
    if stage not in STAGES:
        raise ValueError(f"etapa desconhecida: {stage}")
    if status not in STAGE_STATUSES:
        raise ValueError(f"status invalido: {status}")
    entry = state["stages"].setdefault(stage, {})
    entry["status"] = status
    entry.update(fields)
    if status == "done":
        entry["finished_at"] = _now()
    return state


def record_error(state: dict, stage: str, message: str, clip_id: str | None = None) -> dict:
    state["last_error"] = {"stage": stage, "clip_id": clip_id, "message": message, "at": _now()}
    return state

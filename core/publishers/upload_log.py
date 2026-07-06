"""Registro diario de uploads por conta (credentials_dir/upload_log.json).

Formato: {"uploads": [{"at": iso, "video_id", "clip_id", "remote_id",
"units": 1600}]}. count_today alimenta a checagem de
account["daily_upload_limit"] em scripts/upload_clip.py.
"""
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from ..accounts import credentials_dir

UPLOAD_UNITS = 1600  # custo de videos.insert na quota da YouTube Data API


def log_path(account: dict) -> Path:
    return credentials_dir(account) / "upload_log.json"


def _load(account: dict) -> dict:
    path = log_path(account)
    if not path.exists():
        return {"uploads": []}
    return json.loads(path.read_text(encoding="utf-8"))


def count_today(account: dict) -> int:
    """Conta uploads registrados hoje (data local, prefixo do timestamp ISO)."""
    today = date.today().isoformat()
    return sum(1 for u in _load(account)["uploads"]
               if str(u.get("at", "")).startswith(today))


def append(account: dict, entry: dict) -> None:
    """Registra um upload; entry: video_id, clip_id, remote_id (at/units automaticos)."""
    data = _load(account)
    record = {
        "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        **entry,
    }
    record.setdefault("units", UPLOAD_UNITS)
    data["uploads"].append(record)
    path = log_path(account)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)

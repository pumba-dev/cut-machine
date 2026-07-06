"""Helpers ffprobe para validacao de artefatos de video."""
import json
import subprocess
from pathlib import Path


def probe(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def video_info(path: Path) -> dict:
    data = probe(path)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    if video is None:
        raise ValueError(f"{path}: nenhum stream de video")
    num, _, den = (video.get("avg_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den) if float(den or 1) else 0.0
    return {
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": round(fps, 3),
        "duration_s": float(data["format"]["duration"]),
        "has_audio": audio is not None,
    }

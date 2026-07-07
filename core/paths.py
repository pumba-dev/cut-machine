"""Localizacao canonica de pastas e artefatos do projeto.

Layout de saida (gitignored):
    video-output/<video_id>/          video completo + artefatos do pipeline
    video-output/<video_id>/<clip_id>/  mp4 do corte, .ass (short) e metadata.json
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "video-output"
SECRETS_ROOT = ROOT / "secrets"
CONFIG_DIR = ROOT / "config"
REFERENCES_DIR = ROOT / "references"


def workspace_dir(video_id: str, create: bool = False) -> Path:
    d = OUTPUT_ROOT / video_id
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def state_path(video_id: str) -> Path:
    return workspace_dir(video_id) / "state.json"


def clips_path(video_id: str) -> Path:
    return workspace_dir(video_id) / "clips.json"


def transcript_path(video_id: str) -> Path:
    return workspace_dir(video_id) / "transcript.json"


def transcript_compact_path(video_id: str) -> Path:
    return workspace_dir(video_id) / "transcript.compact.json"


def transcript_srt_path(video_id: str) -> Path:
    return workspace_dir(video_id) / "transcript.srt"


def source_video_path(video_id: str) -> Path:
    return workspace_dir(video_id) / "source.mp4"


def source_info_path(video_id: str) -> Path:
    return workspace_dir(video_id) / "source.info.json"


def clip_dir(video_id: str, clip_id: str, create: bool = False) -> Path:
    d = workspace_dir(video_id) / clip_id
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def clip_output_path(video_id: str, clip_id: str) -> Path:
    return clip_dir(video_id, clip_id) / f"{clip_id}.mp4"


def clip_ass_path(video_id: str, clip_id: str) -> Path:
    return clip_dir(video_id, clip_id) / f"{clip_id}.ass"


def clip_metadata_path(video_id: str, clip_id: str) -> Path:
    return clip_dir(video_id, clip_id) / "metadata.json"

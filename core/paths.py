"""Localizacao canonica de pastas e artefatos do projeto.

Layout de saida (gitignored):
    video-output/<video_id>/          video completo + artefatos do pipeline
    video-output/<video_id>/<clip_id>/  mp4 do corte, .ass (short) e metadata.json
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "video-output"
MODELS_ROOT = ROOT / "models"
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


def faces_path(video_id: str) -> Path:
    """Deteccao de rosto/emocao do source (fase faces, opt-in)."""
    return workspace_dir(video_id) / "faces.json"


def speaker_track_path(video_id: str) -> Path:
    """Rastreio do falante ativo por tempo, AV-sync boca x audio (fase
    speaker-track, opt-in; core.faces.speaker_track)."""
    return workspace_dir(video_id) / "speaker_track.json"


def clip_dir(video_id: str, clip_id: str, create: bool = False) -> Path:
    d = workspace_dir(video_id) / clip_id
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def clip_output_path(video_id: str, clip_id: str) -> Path:
    return clip_dir(video_id, clip_id) / f"{clip_id}.mp4"


def clip_ass_path(video_id: str, clip_id: str) -> Path:
    return clip_dir(video_id, clip_id) / f"{clip_id}.ass"


def clip_border_ass_path(video_id: str, clip_id: str) -> Path:
    """.ass do texto de marca queimado na borda do corte (so formato corte)."""
    return clip_dir(video_id, clip_id) / f"{clip_id}.border.ass"


def clip_thumbnail_ass_path(video_id: str, clip_id: str) -> Path:
    """.ass das frases de impacto/gancho sobrepostas na miniatura."""
    return clip_dir(video_id, clip_id) / f"{clip_id}.thumb.ass"


def clip_thumbnail_path(video_id: str, clip_id: str) -> Path:
    """Miniatura (thumbnail) do clip para upload manual/API."""
    return clip_dir(video_id, clip_id) / f"{clip_id}.thumb.jpg"


def clip_metadata_path(video_id: str, clip_id: str) -> Path:
    return clip_dir(video_id, clip_id) / "metadata.json"

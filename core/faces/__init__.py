"""Deteccao de rosto + emocao no source (fase `faces`, opt-in).

Espelha core/diarize.py: onnxruntime/cv2 em CPU (sem disputar a GPU do whisper/
render), modelos baixados sob demanda para models/faces/, falha degrada e nunca
derruba o pipeline. Produz faces.json (identidades + host + emocoes por frame),
insumo do subagente thumbnail-director e da thumb via IA.
"""
from .analyze import analyze_faces, load_faces

__all__ = ["analyze_faces", "load_faces"]

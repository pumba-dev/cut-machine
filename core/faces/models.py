"""Modelos ONNX de rosto/emocao (OpenCV Zoo), baixados sob demanda p/ models/faces/.

Espelha core/diarize.py: download atomico (.part + rename), CPU-only, idempotente.
Modelos do OpenCV Zoo (Apache-2.0), servidos como LFS media (binario real, nao
ponteiro de texto):
- YuNet: deteccao de rosto + 5 landmarks (~230 KB)
- SFace: embedding 128-d p/ agrupar identidades (mesma pessoa entre frames) (~39 MB)
- FER MobileFaceNet: classificacao de 7 emocoes (~4.8 MB)

Rodados via cv2 (FaceDetectorYN / FaceRecognizerSF / dnn) — API pronta, muito
menos codigo (e menos fragil) que decodificar SCRFD/ArcFace no onnxruntime cru.
"""
import sys
import urllib.request
from pathlib import Path

from ..paths import MODELS_ROOT

FACES_MODELS_DIR = MODELS_ROOT / "faces"

_BASE = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
_URLS = {
    "yunet": f"{_BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "sface": f"{_BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    "fer": f"{_BASE}/facial_expression_recognition/"
           "facial_expression_recognition_mobilefacenet_2022july.onnx",
}

YUNET = FACES_MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE = FACES_MODELS_DIR / "face_recognition_sface_2021dec.onnx"
FER = FACES_MODELS_DIR / "facial_expression_recognition_mobilefacenet_2022july.onnx"

_PATHS = {"yunet": YUNET, "sface": SFACE, "fer": FER}
_MIN_BYTES = 100 * 1024  # abaixo disso = ponteiro LFS ou download truncado


def _download(url: str, dest: Path) -> None:
    """Baixa url -> dest de forma atomica (.part + rename), validando o binario."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    print(f"[faces] baixando {url} -> {dest}", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=120) as r, open(part, "wb") as f:
        head = r.read(64)
        if head.startswith(b"version https://git-lfs"):
            part.unlink(missing_ok=True)
            raise RuntimeError(f"URL retornou ponteiro git-lfs, nao o binario: {url}")
        f.write(head)
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    if part.stat().st_size < _MIN_BYTES:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"download suspeito (<100KB): {url}")
    part.replace(dest)


def ensure_models() -> None:
    """Garante os 3 modelos em models/faces/ (idempotente)."""
    for key, path in _PATHS.items():
        if not path.exists():
            _download(_URLS[key], path)

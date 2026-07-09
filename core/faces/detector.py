"""FaceEngine: deteccao + embedding + emocao via cv2 (CPU).

Envolve os 3 modelos do OpenCV Zoo:
- YuNet (FaceDetectorYN): bbox + 5 landmarks + score por rosto.
- SFace (FaceRecognizerSF): alinha o rosto (112x112) e extrai embedding 128-d
  (L2-normalizado por nos) para agrupar identidades entre frames.
- FER MobileFaceNet (dnn): 7 emocoes sobre o rosto alinhado.

Tudo forcado em CPU (cv2 dnn default = CPU; nao setamos target CUDA) para nao
disputar os 6 GB da GPU usados por whisper/render. Emocao e best-effort: qualquer
erro por rosto vira emotion=None (o host e o crop nao dependem dela).
"""
import cv2
import numpy as np

from . import models

# Ordem das classes do modelo FER do OpenCV Zoo (facial_fer_model.py).
EMOTIONS = ["angry", "disgust", "fearful", "happy", "neutral", "sad", "surprised"]


class FaceEngine:
    def __init__(self, score_thresh: float = 0.6, nms_thresh: float = 0.3,
                 top_k: int = 50):
        models.ensure_models()
        # input_size e placeholder; setInputSize e chamado por frame em detect().
        self.detector = cv2.FaceDetectorYN_create(
            str(models.YUNET), "", (320, 320), score_thresh, nms_thresh, top_k)
        self.recognizer = cv2.FaceRecognizerSF_create(str(models.SFACE), "")
        self.emotion_net = cv2.dnn.readNet(str(models.FER))

    def detect(self, bgr: np.ndarray) -> list[dict]:
        """Rostos no frame BGR. Retorna [{raw, bbox:[x,y,w,h], score, kps}]."""
        h, w = bgr.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(bgr)
        out: list[dict] = []
        if faces is None:
            return out
        for f in faces:
            f = np.asarray(f, dtype=np.float32).flatten()
            out.append({
                "raw": f,
                "bbox": [float(f[0]), float(f[1]), float(f[2]), float(f[3])],
                "score": float(f[-1]),
                # landmarks: right-eye, left-eye, nose, right-mouth, left-mouth
                "kps": f[4:14].reshape(5, 2).astype(float).tolist(),
            })
        return out

    def embed(self, bgr: np.ndarray, raw_face: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(embedding L2-normalizado 128-d, rosto alinhado 112x112 BGR)."""
        aligned = self.recognizer.alignCrop(bgr, raw_face)
        feat = self.recognizer.feature(aligned)
        v = np.asarray(feat, dtype=np.float32).flatten()
        n = float(np.linalg.norm(v))
        if n > 0:
            v = v / n
        return v, aligned

    def emotion(self, aligned_bgr: np.ndarray) -> tuple[str | None, dict]:
        """Emocao do rosto alinhado. Best-effort: erro -> (None, {}).

        Preprocessamento identico ao OpenCV Zoo FER: /255 -> (x-0.5)/0.5, BGR
        (sem swapRB), 112x112.
        """
        try:
            img = cv2.resize(aligned_bgr, (112, 112)).astype(np.float32) / 255.0
            img = (img - 0.5) / 0.5
            blob = cv2.dnn.blobFromImage(img)
            self.emotion_net.setInput(blob)
            logits = np.asarray(self.emotion_net.forward()).flatten()
            e = np.exp(logits - logits.max())
            probs = e / e.sum()
            idx = int(probs.argmax())
            label = EMOTIONS[idx] if idx < len(EMOTIONS) else None
            scores = {EMOTIONS[i]: round(float(probs[i]), 3)
                      for i in range(min(len(EMOTIONS), len(probs)))}
            return label, scores
        except Exception:  # noqa: BLE001 — emocao e advisory, nunca fatal
            return None, {}

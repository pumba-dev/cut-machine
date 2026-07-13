"""QA: presenca de rosto no mp4 RENDERIZADO (pega reframe apontando pro vazio).

O reframe dinamico (core/render/reframe.py) corta a "camera" ao redor do
falante. Quando o speaker_track erra a posicao, o crop aponta pro vazio e o
frame sai SEM ninguem. Aqui amostramos frames do mp4 final (so na regiao de
conteudo, fora de intro/vinheta) e medimos a fracao com >=1 rosto (YuNet, CPU).
Fracao baixa num clip com reframe = crop quebrado.

Degrada com seguranca: sem cv2/modelos ou video ilegivel -> retorna None (o
chamador NAO reprova o clip por isso; so reprova quando ha rosto de menos de
fato). Nunca levanta pro chamador.
"""
from pathlib import Path


def sample_face_fraction(mp4, t0: float, t1: float, samples: int = 15,
                         min_score: float = 0.6):
    """Fracao dos frames amostrados em [t0, t1] (segundos) com >=1 rosto.

    Retorna (frac, n_com_rosto, n_amostrados) ou None se indeterminado
    (janela curta demais, video ilegivel, cv2/modelos ausentes).
    """
    try:
        import cv2
        from .detector import FaceEngine
    except Exception:
        return None

    span = max(0.0, float(t1) - float(t0))
    if span < 1.0:
        return None
    n = max(6, min(int(samples), 24))

    cap = None
    try:
        cap = cv2.VideoCapture(str(Path(mp4)))
        if not cap.isOpened():
            return None
        engine = FaceEngine(score_thresh=min_score)
        hit = 0
        used = 0
        for i in range(n):
            t = float(t0) + span * (i + 0.5) / n
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            used += 1
            try:
                if engine.detect(frame):
                    hit += 1
            except Exception:
                continue
        if used == 0:
            return None
        return hit / used, hit, used
    except Exception:
        return None
    finally:
        if cap is not None:
            cap.release()

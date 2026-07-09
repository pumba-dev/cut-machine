"""Agrupamento de embeddings de rosto em identidades + escolha do host.

Embeddings SFace sao L2-normalizados, entao similaridade de cosseno = produto
interno. O threshold 0.363 e o valor de "mesma pessoa" recomendado pelo OpenCV
para SFace no modo cosseno. Agrupamento guloso incremental (1 passada): cada
rosto entra no cluster mais similar acima do threshold, senao abre um novo. Ao
contrario da diarizacao (onde threshold puro era inutilizavel), aqui embeddings
de rosto sao discriminativos o bastante para o threshold funcionar.
"""
import numpy as np

# Similaridade de cosseno minima para considerar o mesmo rosto (OpenCV SFace).
SAME_FACE_COS = 0.363


def cluster_embeddings(embs: list[np.ndarray], thresh: float = SAME_FACE_COS) -> list[int]:
    """Rotula cada embedding com um id de cluster (guloso, 1 passada).

    Retorna uma lista de ints do mesmo tamanho de `embs`. Assume embeddings ja
    L2-normalizados (cos = dot). Ids nao tem ordem semantica aqui — a reindexacao
    por tempo de tela (0 = host) e feita em analyze."""
    centroids: list[np.ndarray] = []   # soma dos vetores por cluster
    counts: list[int] = []
    labels: list[int] = []
    for e in embs:
        best, best_sim = -1, thresh
        for i, c in enumerate(centroids):
            mean = c / counts[i]
            nm = float(np.linalg.norm(mean))
            sim = float(np.dot(e, mean) / nm) if nm > 0 else 0.0
            if sim >= best_sim:
                best, best_sim = i, sim
        if best < 0:
            centroids.append(e.astype(np.float64).copy())
            counts.append(1)
            labels.append(len(centroids) - 1)
        else:
            centroids[best] += e
            counts[best] += 1
            labels.append(best)
    return labels

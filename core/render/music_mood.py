"""Deriva o clima ("agressiva"/"neutra"/"calma") da musica de fundo a partir
do CONTEUDO do clip -- deterministico, sem LLM (decisao explicita: mood vem
do render, nao de um campo novo escrito por clip-scout/copywriter).

Combina 3 sinais, cada um best-effort (ausente/invalido contribui 0, nunca
lanca): o `dominant_signal` do clip-scout, o ritmo de fala do clip (palavras
por segundo, do transcript ja carregado no render) e uma varredura de
palavras-chave pt-BR nos campos de copy/hook/rationale. Score fora da faixa
central vira "agressiva"/"calma"; dentro dela -- inclusive quando todo sinal
esta ausente -- cai em "neutra", o default seguro (mesma filosofia de
degradacao usada em faces.json/reframe: ambiguidade nunca vira excecao).
"""
import unicodedata

_HIGH, _LOW = 1.5, -1.5

# dominant_signal (texto livre do clip-scout, inspirado no vocabulario de
# references/heuristicas-virais.md, NAO um enum garantido) -> delta de humor.
_SIGNAL_WEIGHTS = {
    "pico emocional": 2.0,
    "polemica": 2.0,
    "opiniao forte": 2.0,
    "hook forte": 1.0,
    "utilidade condensada": -1.0,
    "identificacao": -1.0,
}

_FAST_WPS, _SLOW_WPS = 3.3, 2.0

_AGRESSIVA_KEYWORDS = (
    "briga", "revolta", "grito", "absurdo", "escandalo", "ataque", "guerra",
    "caos", "bomba", "chocante", "urgente", "denuncia", "critica",
)
_CALMA_KEYWORDS = (
    "calma", "tranquilo", "sereno", "reflexao", "medite", "respire",
    "devagar", "conselho", "dica", "aprenda", "explica", "historia",
)


def _norm(s) -> str:
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.lower().strip()


def _signal_delta(clip: dict) -> float:
    norm = _norm(clip.get("dominant_signal"))
    if not norm:
        return 0.0
    return sum(w for key, w in _SIGNAL_WEIGHTS.items() if key in norm)


def _pace_delta(clip: dict, transcript: dict | None) -> float:
    if not isinstance(transcript, dict):
        return 0.0
    try:
        start, end = float(clip["start"]), float(clip["end"])
    except (KeyError, TypeError, ValueError):
        return 0.0
    dur = end - start
    if dur <= 0:
        return 0.0
    words = [
        w for seg in transcript.get("segments", [])
        for w in seg.get("words", [])
        if start <= w.get("start", -1) < end
    ]
    if not words:
        return 0.0
    wps = len(words) / dur
    if wps >= _FAST_WPS:
        return 1.5
    if wps <= _SLOW_WPS:
        return -1.5
    return 0.0


def _keyword_delta(clip: dict) -> float:
    fields = [
        clip.get("hook_text"), clip.get("payoff_text"), clip.get("transcript_excerpt"),
        clip.get("rationale"), clip.get("title"), clip.get("description"),
    ]
    tags = clip.get("tags")
    if isinstance(tags, list):
        fields.extend(t for t in tags if isinstance(t, str))
    text = _norm(" ".join(f for f in fields if isinstance(f, str)))
    if not text:
        return 0.0
    delta = 0.5 * sum(1 for kw in _AGRESSIVA_KEYWORDS if kw in text)
    delta -= 0.5 * sum(1 for kw in _CALMA_KEYWORDS if kw in text)
    return max(-2.0, min(2.0, delta))


def derive_mood(clip: dict, transcript: dict | None = None) -> str:
    if not isinstance(clip, dict):
        return "neutra"
    score = _signal_delta(clip) + _pace_delta(clip, transcript) + _keyword_delta(clip)
    if score >= _HIGH:
        return "agressiva"
    if score <= _LOW:
        return "calma"
    return "neutra"

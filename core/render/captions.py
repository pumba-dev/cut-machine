"""Geracao de legendas ASS para shorts a partir do transcript word-level.

Tempos sao rebased (t - clip.start) porque o ffmpeg corta com -ss antes de
-i e o output comeca em t=0. Estilo fixo: Arial Black 110 @ PlayRes
1080x1920, Outline 8, Alignment 2 (baixo-centro), MarginV 550.
"""

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Arial Black,110,&H00FFFFFF,&H0000FFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,8,0,2,60,60,550,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def group_words(words: list[dict], max_words: int = 3, max_gap: float = 0.6) -> list[list[dict]]:
    """Agrupa palavras consecutivas em blocos de ate max_words.

    Quebra o grupo quando atinge max_words ou quando a pausa entre palavras
    passa de max_gap segundos.
    """
    groups: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        if cur and (len(cur) >= max_words or w["start"] - cur[-1]["end"] > max_gap):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def ass_time(t: float) -> str:
    """Formata segundos como tempo ASS H:MM:SS.cc."""
    t = max(t, 0.0)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02}:{s:05.2f}"


def build_ass(clip: dict, transcript: dict) -> str:
    """Gera o conteudo do arquivo .ass para as palavras dentro do clip.

    Seleciona palavras com start em [clip.start, clip.end), rebase para o
    t0 do clip e emite eventos Dialogue em CAIXA ALTA.
    """
    start = clip["start"]
    end = clip["end"]
    words = [
        w
        for seg in transcript["segments"]
        for w in seg.get("words", [])
        if start <= w["start"] < end
    ]
    events: list[str] = []
    for group in group_words(words):
        ev_start = ass_time(group[0]["start"] - start)
        ev_end = ass_time(min(group[-1]["end"], end) - start)
        text = " ".join(w["w"] for w in group).upper()
        events.append(f"Dialogue: 0,{ev_start},{ev_end},Cap,,0,0,0,,{text}")
    return ASS_HEADER + "\n".join(events) + "\n"

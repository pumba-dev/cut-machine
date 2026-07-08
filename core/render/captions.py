"""Geracao de legendas ASS para shorts a partir do transcript word-level.

Tempos sao rebased (t - clip.start) porque o ffmpeg corta com -ss antes de
-i e o output comeca em t=0. Estilo base: Arial Black 110 @ PlayRes
1080x1920, Outline 8, Alignment 2 (baixo-centro), MarginV 550.

Cores por falante: um Style por falante (Cap0..Cap4, paleta fixa), palavra
usa o campo `spk` gravado pela diarizacao (core.diarize). Transcript sem
diarizacao cai no estilo Cap (branco) — retrocompatibilidade total.
"""

# PrimaryColour em &HAABBGGRR (BGR!). Ordem = prioridade do falante
# (spk 0 = quem mais fala). Cores claras de alta luminancia sobre outline
# preto; sem vermelho-vs-verde (daltonismo), sem vermelho/azul puro.
SPEAKER_COLOURS = [
    "&H00FFFFFF",  # spk 0: branco  #FFFFFF
    "&H003DD9FF",  # spk 1: amarelo #FFD93D
    "&H00FFCC66",  # spk 2: azul-claro #66CCFF
    "&H0090EE90",  # spk 3: verde-claro #90EE90
    "&H0000A5FF",  # spk 4: laranja #FFA500
]

_STYLE_FMT = ("Style: {name},Arial Black,110,{colour},&H0000FFFF,&H00000000,"
              "&H96000000,-1,0,0,0,100,100,0,0,1,8,0,2,60,60,550,1")


def _ass_header() -> str:
    styles = [_STYLE_FMT.format(name="Cap", colour=SPEAKER_COLOURS[0])]
    styles += [_STYLE_FMT.format(name=f"Cap{i}", colour=c)
               for i, c in enumerate(SPEAKER_COLOURS)]
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        + "\n".join(styles) + "\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


ASS_HEADER = _ass_header()


def _style_for(spk) -> str:
    # bool e subclasse de int em Python: True passaria como spk valido.
    if not isinstance(spk, int) or isinstance(spk, bool) or spk < 0:
        return "Cap"
    return f"Cap{spk % len(SPEAKER_COLOURS)}"


def group_words(words: list[dict], max_words: int = 3, max_gap: float = 0.6) -> list[list[dict]]:
    """Agrupa palavras consecutivas em blocos de ate max_words.

    Quebra o grupo quando atinge max_words, quando a pausa entre palavras
    passa de max_gap segundos ou quando o falante (`spk`) muda — grupo
    nunca mistura cores.
    """
    groups: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        if cur and (
            len(cur) >= max_words
            or w["start"] - cur[-1]["end"] > max_gap
            or w.get("spk") != cur[-1].get("spk")
        ):
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
    t0 do clip e emite eventos Dialogue em CAIXA ALTA, um estilo por
    falante.
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
        style = _style_for(group[0].get("spk"))
        text = " ".join(w["w"] for w in group).upper()
        events.append(f"Dialogue: 0,{ev_start},{ev_end},{style},,0,0,0,,{text}")
    return ASS_HEADER + "\n".join(events) + "\n"

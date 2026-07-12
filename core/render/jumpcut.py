"""Jump-cut: remove silencio/pausa longa entre palavras (opt-in, Fase 7).

POR ULTIMO e ISOLADA de proposito: e a unica fase que muda a DURACAO do clip
(todas as anteriores preservavam `end-start` por construcao). Usa os gaps que
a transcricao ja expoe (word.start/word.end) dentro da janela do clip -- sem
diarizacao nova, sem CV, so os tempos que ja existem.

v1 e so corte seco (sem speed-ramp): pausa >= `min_gap_s` vira um corte,
mantendo um respiro `buffer_s` em cada ponta (nao corta a respiracao/inicio da
proxima palavra "em cima"). Especular um trecho acelerado em vez de cortado
exigiria sincronizar audio+video a velocidades DIFERENTES por pedaco (atempo
por segmento) alem da velocidade global do transform -- fora de escopo desta
rodada (registrado como ideia futura); corte seco com todo pedaco a 1x mantem
audio e video trivialmente sincronizados entre si E com a velocidade global
do transform (`core.render.transform`, suprimida quando ha corte real -- ver
core.render.ffmpeg.render_clip).

Produz uma lista de trechos MANTIDOS (core.render.timemap.TimeMap) que o
render usa tanto para montar o video (trim+concat, mesmo mecanismo do
reframe) quanto para remapear legendas e o crop do reframe pelo mesmo corte.
"""

DEFAULTS = {
    "min_gap_s": 1.2,
    "buffer_s": 0.15,
}


def _words_in_window(transcript: dict, clip_start: float, clip_end: float) -> list[dict]:
    words = [
        w for seg in transcript.get("segments", []) for w in seg.get("words", [])
        if clip_start <= w["start"] < clip_end
    ]
    words.sort(key=lambda w: w["start"])
    return words


def build_segments(clip_start: float, clip_end: float, transcript: dict, *,
                   min_gap_s: float = DEFAULTS["min_gap_s"],
                   buffer_s: float = DEFAULTS["buffer_s"]) -> list[dict]:
    """Trechos mantidos [{start, end}] em tempo LOCAL ORIGINAL do clip (0 =
    clip_start), cobrindo [0, clip_end-clip_start] MENOS os buracos dos
    cortes. Sem gaps >= `min_gap_s` (ou transcript sem palavras) -> um unico
    trecho cobrindo o clipe inteiro (no-op, `has_real_cuts` = False)."""
    clip_dur = clip_end - clip_start
    words = _words_in_window(transcript, clip_start, clip_end)
    if len(words) < 2:
        return [{"start": 0.0, "end": clip_dur}]

    pieces: list[dict] = []
    cursor = clip_start
    for i in range(len(words) - 1):
        gap = words[i + 1]["start"] - words[i]["end"]
        if gap < min_gap_s:
            continue
        gap_start, gap_end = words[i]["end"], words[i + 1]["start"]
        cut_start = min(gap_start + buffer_s, gap_end)
        cut_end = max(gap_end - buffer_s, cut_start)
        if cut_end <= cut_start:
            continue
        if cut_start > cursor:
            pieces.append({"start": cursor - clip_start, "end": cut_start - clip_start})
        cursor = cut_end
    if cursor < clip_end:
        pieces.append({"start": cursor - clip_start, "end": clip_dur})

    pieces = [p for p in pieces if p["end"] - p["start"] > 0.02]
    return pieces or [{"start": 0.0, "end": clip_dur}]


def has_real_cuts(segments: list[dict]) -> bool:
    """True se ha pelo menos um buraco removido (2+ trechos mantidos) -- um
    unico segmento cobrindo o clipe inteiro e um no-op."""
    return len(segments) > 1


def build_audio_trim_filter(pieces: list[dict], *, in_label: str = "0:a",
                            out_label: str = "a_jc") -> str:
    """Subgrafo de audio que aplica o MESMO corte dos `pieces` (trim+concat) a
    `in_label` -> `[out_label]`, pareado com o corte do video (mesmo mecanismo
    de core.render.frame_common.build_video_stage, mas para audio: `atrim`/
    `asetpts`/`concat=v=0:a=1`). Todo pedaco toca a 1x -- audio e video ficam
    trivialmente sincronizados entre si (cortados nos mesmos pontos, sem
    esticar/comprimir nada)."""
    n = len(pieces)
    if n == 1 and abs(pieces[0]["start"]) < 1e-6:
        return f"[{in_label}]asetpts=PTS-STARTPTS[{out_label}]"
    parts = [f"[{in_label}]asetpts=PTS-STARTPTS,asplit={n}"
            + "".join(f"[{out_label}_s{i}]" for i in range(n)) + ";"]
    labels = []
    for i, p in enumerate(pieces):
        lbl = f"{out_label}_c{i}"
        labels.append(f"[{lbl}]")
        parts.append(f"[{out_label}_s{i}]atrim={p['start']:.3f}:{p['end']:.3f},"
                     f"asetpts=PTS-STARTPTS[{lbl}];")
    parts.append("".join(labels) + f"concat=n={n}:v=0:a=1[{out_label}]")
    return "".join(parts)

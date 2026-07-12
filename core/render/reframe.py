"""Reframe dinamico: crop de "camera" ao redor de quem fala (opt-in, Fase 4).

Le `speaker_track.json` (core.faces.speaker_track) + a janela [start, end] do
clip e produz uma lista de sub-segmentos de crop (core.render.frame_common
.build_video_stage): cada troca de falante ativo vira um CORTE DE PLANO (nao
pan continuo -- mais robusto, sem jitter por pixel, e combina com o pedido
original: "ficar cortando ao redor de quem fala").

Trechos do clip sem segmento resolvido (falante nao identificado com confianca
suficiente, ou fala sobreposta) caem num crop central classico (mesmo
enquadramento do crop-to-fill estatico) -- nunca deixa buraco na timeline, que
quebraria o `concat` do filtro. Sem track/degraded/sem overlap -> None (o
chamador usa o crop central unico de sempre, regressao zero).
"""
from ..faces.speaker_track import load_speaker_track

# bbox do rosto -> altura do crop (inclui cabeca+ombros; ~4.5x a altura do
# rosto e um enquadramento de busto tipico).
_HEIGHT_FACTOR = 4.5
# Piso da altura do crop (fracao do frame). Em short (janela 9:16, fill
# height-driven) o zoom efetivo ~= altura_janela / (crop_h * altura_fonte),
# entao um piso MAIOR = crop mais AMPLO = menos zoom. 0.30 deixava rosto pequeno
# (bh~0.04) travar em crop_h=0.30 -> ~4.8x de zoom (cortava a cabeca / fechava
# demais). 0.70 limita o zoom em ~2x. Sobreescrito por conta via
# reframe.min_crop_h. No corte a trava de largura (crop_w>1) ja recalcula
# crop_h p/ ~0.565, entao este piso mexe na pratica so no short.
_MIN_CROP_H = 0.70
_MAX_CROP_H = 1.0
# rosto fica a 38% do topo do crop (nao 50%): mais espaco pro tronco embaixo
# do que pro topo da cabeca -- enquadramento de busto, nao passe-de-rosto.
_VERTICAL_BIAS = 0.38
# O detector de rosto (YuNet) marca so o rosto -- exclui testa/cabelo, ~_HAIR_MARGIN
# da altura do bbox acima do topo dele. Garantir essa folga acima evita cortar o
# topo da cabeca quando o vies de busto sozinho posicionaria o crop baixo demais.
_HAIR_MARGIN = 0.35

# Cutaway (Fase 5, opt-in): so pausas CURTAS do falante ativo viram corte pro
# ouvinte -- pausa longa e melhor servida pelo crop central classico (o
# ouvinte tambem pode ja ter saido de quadro).
_CUTAWAY_MAX_GAP_S = 3.0

# Punch-in do hook (Fase 5, opt-in): zoom breve no timestamp do gancho do clip
# (thumbnail_ts/hook, vindo do clip-scout). Fracao do crop vigente naquele
# instante (menor = mais perto); janela curta o bastante pra nao formar um
# segmento "de verdade" (fica de fora da fusao por histerese, de proposito --
# e uma enfase pontual, nao uma troca de camera).
_HOOK_PUNCH_DUR_S = 1.2
_HOOK_PUNCH_ZOOM = 0.75


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def target_aspect_for(fmt: str) -> float:
    """Aspecto (w/h) da janela de video do formato, ja arredondada p/ par
    (core.render.frame_common.even) -- mesma janela que build_video_stage usa."""
    from .frame_common import even
    if fmt == "short":
        from .short_frame import WINDOW
    else:
        from .corte_frame import WINDOW
    _, _, ww, wh = WINDOW
    ew, eh = even(ww), even(wh)
    return ew / eh


def _center_crop(target_aspect: float) -> tuple[float, float, float, float]:
    """Crop central classico (mesmo aspecto da janela) -- fallback p/ trechos
    sem falante ativo resolvido."""
    if target_aspect <= 1.0:
        h, w = 1.0, min(1.0, target_aspect)
    else:
        w, h = 1.0, min(1.0, 1.0 / target_aspect)
    return (round((1.0 - w) / 2.0, 4), round((1.0 - h) / 2.0, 4), round(w, 4), round(h, 4))


def _bbox_to_crop(bbox: list, target_aspect: float, margin: float,
                  min_crop_h: float = _MIN_CROP_H) -> tuple[float, float, float, float]:
    bx, by, bw, bh = bbox
    cx, cy = bx + bw / 2.0, by + bh / 2.0
    crop_h = _clamp(bh * _HEIGHT_FACTOR * (1.0 + margin), min_crop_h, _MAX_CROP_H)
    crop_w = crop_h * target_aspect
    if crop_w > 1.0:
        crop_w = 1.0
        crop_h = crop_w / target_aspect
    x0 = _clamp(cx - crop_w / 2.0, 0.0, 1.0 - crop_w)
    # Vertical: vies de busto (rosto a _VERTICAL_BIAS do topo), MAS nunca deixando
    # o topo do crop cair abaixo do cabelo estimado (by - _HAIR_MARGIN*bh) -- entre
    # os dois, o mais ALTO (menor y) vence, pra n cortar a cabeca. Clamp na moldura.
    y_bias = cy - crop_h * _VERTICAL_BIAS
    y_hair = by - _HAIR_MARGIN * bh
    y0 = _clamp(min(y_bias, y_hair), 0.0, 1.0 - crop_h)
    return (round(x0, 4), round(y0, 4), round(crop_w, 4), round(crop_h, 4))


def _find_cutaway_bbox(track_segments: list[dict], gap_start_g: float, gap_end_g: float,
                       exclude_identities: set) -> list | None:
    """Bbox de quem NAO esta falando (identidade != a do falante ativo em volta
    do buraco), mais proximo no tempo do meio do buraco -- procura no track
    INTEIRO do video (nao so no clip: um ouvinte visto em outro trecho ainda
    serve de referencia de enquadramento)."""
    mid = (gap_start_g + gap_end_g) / 2.0
    candidates = [s for s in track_segments if s.get("identity") not in exclude_identities]
    if not candidates:
        return None
    best = min(candidates, key=lambda s: min(abs(s["start"] - mid), abs(s["end"] - mid)))
    return best.get("bbox")


def _punch_in(piece: dict) -> dict:
    cx, cy = piece["x"] + piece["w"] / 2.0, piece["y"] + piece["h"] / 2.0
    pw, ph = piece["w"] * _HOOK_PUNCH_ZOOM, piece["h"] * _HOOK_PUNCH_ZOOM
    x = _clamp(cx - pw / 2.0, 0.0, 1.0 - pw)
    y = _clamp(cy - ph / 2.0, 0.0, 1.0 - ph)
    return {**piece, "x": round(x, 4), "y": round(y, 4), "w": round(pw, 4), "h": round(ph, 4)}


def _apply_hook_punch(pieces: list[dict], hook_ts: float | None, clip_dur: float) -> list[dict]:
    """Insere um zoom breve centrado em `hook_ts` (tempo LOCAL do clip),
    dividindo a peca que cobre aquele instante em ate 3 (antes/punch/depois).
    Roda DEPOIS de `_merge_pieces` de proposito -- o punch e uma enfase
    pontual, nao uma troca de "camera" sujeita a histerese de min_segment_s."""
    if hook_ts is None or not pieces or not (0.0 <= hook_ts <= clip_dur):
        return pieces
    half = _HOOK_PUNCH_DUR_S / 2.0
    h_start = _clamp(hook_ts - half, 0.0, clip_dur)
    h_end = _clamp(hook_ts + half, 0.0, clip_dur)
    if h_end - h_start < 0.3:
        return pieces
    out: list[dict] = []
    for p in pieces:
        if h_end <= p["start"] or h_start >= p["end"]:
            out.append(p)
            continue
        if p["start"] < h_start:
            out.append({**p, "end": h_start})
        out.append(_punch_in({**p, "start": max(p["start"], h_start), "end": min(p["end"], h_end)}))
        if p["end"] > h_end:
            out.append({**p, "start": h_end})
    return out


def _merge_pieces(pieces: list[dict], min_segment_s: float) -> list[dict]:
    if not pieces:
        return pieces
    merged = [dict(pieces[0])]
    for p in pieces[1:]:
        last = merged[-1]
        same_region = (abs(p["x"] - last["x"]) < 1e-3 and abs(p["y"] - last["y"]) < 1e-3
                      and abs(p["w"] - last["w"]) < 1e-3 and abs(p["h"] - last["h"]) < 1e-3)
        too_short = (p["end"] - p["start"]) < min_segment_s
        if same_region or too_short:
            last["end"] = p["end"]
        else:
            merged.append(dict(p))
    if len(merged) > 1 and (merged[0]["end"] - merged[0]["start"]) < min_segment_s:
        merged[1]["start"] = merged[0]["start"]
        merged.pop(0)
    return merged


def build_crop_segments(clip_start: float, clip_end: float, track: dict | None,
                        target_aspect: float, *, margin: float = 0.35,
                        min_segment_s: float = 1.2, min_crop_h: float = _MIN_CROP_H,
                        mirror_x: bool = False, cutaway: bool = False,
                        hook_ts: float | None = None) -> list[dict] | None:
    """Sub-segmentos de crop (tempo LOCAL do clip) cobrindo [0, clip_end-clip_start]
    sem buracos. None se nao ha reframe aplicavel (sem track/degraded/sem overlap
    com o clip) -- o chamador cai no crop central unico (regressao zero).

    `mirror_x`: quando `transform.flip` (hflip) esta ativo na conta, o frame ja
    saiu espelhado ANTES do crop (vfx roda primeiro); sem espelhar aqui tambem o
    crop recortaria o lado errado do frame original. `cutaway` (Fase 5): pausas
    curtas do falante ativo cortam pro rosto de quem ouve, em vez do crop
    central. `hook_ts` (Fase 5, tempo LOCAL do clip): zoom breve no gancho.
    """
    if not track or track.get("degraded"):
        return None
    all_segs = track.get("segments", [])
    segs = [s for s in all_segs if s["end"] > clip_start and s["start"] < clip_end]
    if not segs:
        return None

    clip_dur = clip_end - clip_start
    segs = sorted(segs, key=lambda s: s["start"])
    pieces: list[dict] = []
    cursor = 0.0
    for i, s in enumerate(segs):
        local_start = max(0.0, s["start"] - clip_start)
        local_end = min(clip_dur, s["end"] - clip_start)
        if local_end <= cursor:
            continue
        if local_start > cursor:
            gap_dur = local_start - cursor
            cut_bbox = None
            if cutaway and gap_dur <= _CUTAWAY_MAX_GAP_S:
                cut_bbox = _find_cutaway_bbox(
                    all_segs, cursor + clip_start, local_start + clip_start, {s["identity"]})
            if cut_bbox:
                x, y, w, h = _bbox_to_crop(cut_bbox, target_aspect, margin, min_crop_h)
            else:
                x, y, w, h = _center_crop(target_aspect)
            if mirror_x and cut_bbox:
                x = round(1.0 - x - w, 4)
            pieces.append({"start": cursor, "end": local_start, "x": x, "y": y, "w": w, "h": h})
        x, y, w, h = _bbox_to_crop(s["bbox"], target_aspect, margin, min_crop_h)
        if mirror_x:
            x = round(1.0 - x - w, 4)
        pieces.append({"start": max(cursor, local_start), "end": local_end, "x": x, "y": y, "w": w, "h": h})
        cursor = local_end
    if cursor < clip_dur - 1e-6:
        x, y, w, h = _center_crop(target_aspect)
        pieces.append({"start": cursor, "end": clip_dur, "x": x, "y": y, "w": w, "h": h})

    pieces = _merge_pieces(pieces, min_segment_s)
    pieces = _apply_hook_punch(pieces, hook_ts, clip_dur)
    if len(pieces) <= 1:
        return None
    return pieces


def crop_at(segments: list[dict] | None, t: float) -> tuple[float, float, float, float] | None:
    """Crop (x,y,w,h) vigente no tempo `t` (tempo ORIGINAL local do clip),
    ou None se `segments` vazio/None ou `t` fora de qualquer trecho."""
    if not segments:
        return None
    for s in segments:
        if s["start"] <= t <= s["end"]:
            return (s["x"], s["y"], s["w"], s["h"])
    return None


def compose_with_keep_ranges(keep_ranges: list[dict], reframe_segments: list[dict] | None,
                             target_aspect: float) -> list[dict]:
    """Funde os trechos MANTIDOS do jump-cut (core.render.jumpcut, tempo
    ORIGINAL local do clip) com o crop do reframe vigente em cada um (ponto
    medio do trecho). Sem reframe ativo, cada trecho usa o frame INTEIRO
    (0,0,1,1) -- o crop-to-fill da janela ja cuida do encaixe, igual ao
    caminho classico sem reframe (regressao zero)."""
    out = []
    for kr in keep_ranges:
        mid = (kr["start"] + kr["end"]) / 2.0
        crop = crop_at(reframe_segments, mid)
        x, y, w, h = crop if crop else (0.0, 0.0, 1.0, 1.0)
        out.append({"start": kr["start"], "end": kr["end"], "x": x, "y": y, "w": w, "h": h})
    return out


def resolve_crop_segments(clip: dict, video_id: str, rcfg: dict, *,
                          mirror_x: bool = False) -> list[dict] | None:
    """Ponto de entrada do render (core.render.ffmpeg): carrega o
    speaker_track.json e monta os sub-segmentos de crop deste clip. `rcfg`
    (core.render.reframe_config.resolve_reframe) ja resolvido pelo chamador."""
    if not rcfg.get("enabled"):
        return None
    track = load_speaker_track(video_id)
    aspect = target_aspect_for(clip["format"])
    clip_start = float(clip["start"])
    hook_ts = None
    if rcfg.get("hook_punch"):
        raw_hook = (clip.get("thumbnail_plan") or {}).get("frame_ts", clip.get("thumbnail_ts"))
        if isinstance(raw_hook, (int, float)) and not isinstance(raw_hook, bool):
            hook_ts = float(raw_hook) - clip_start
    return build_crop_segments(
        clip_start, float(clip["end"]), track, aspect,
        margin=float(rcfg.get("margin", 0.35)),
        min_segment_s=float(rcfg.get("min_segment_s", 1.2)),
        min_crop_h=float(rcfg.get("min_crop_h", _MIN_CROP_H)),
        mirror_x=mirror_x, cutaway=bool(rcfg.get("cutaway")), hook_ts=hook_ts,
    )

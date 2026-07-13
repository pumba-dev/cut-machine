"""Miniatura compositada 100% local (sem IA paga, sem VRAM, deterministica).

Reproduz o layout da thumb via IA usando so ferramentas locais — resultado em
9:16 (ou 16:9) EXATO, texto perfeito e pessoa 100% fiel (sao os pixels reais
dela, nao uma repintura):

1. fundo = o frame real no `frame_ts`, cover-crop p/ a resolucao do formato +
   blur + escurecido + saturado (visual dramatico de thumbnail);
2. sujeito = recorte da pessoa (rembg) — enquadrado no HOST via `faces.json`
   (bbox do rosto que mais aparece perto do frame_ts) p/ isolar o apresentador
   de eventuais convidados — com um GLOW na cor de marca da conta por baixo;
3. texto = frase de impacto + ganchos queimados pelo motor ASS atual
   (`thumbnail.build_thumb_ass`) — mesmo estilo/zona segura das thumbs locais.

Custo zero, reproduzivel. Falha -> levanta (o chamador cai na thumb ASS simples).
"""
import os
import subprocess
import tempfile
from pathlib import Path

from .. import paths
from ..contracts import FORMAT_RULES
from ..faces import load_faces
from .thumbnail import build_thumb_ass

_ACCENT = (255, 217, 61)  # #FFD93D amarelo (fallback sem brand.accent_color)


def _hex_to_rgb(hex_color, default=_ACCENT):
    """#RRGGBB (accent da conta) -> (r,g,b). Invalido -> default (amarelo)."""
    if not isinstance(hex_color, str):
        return default
    h = hex_color.strip().lstrip("#")
    if len(h) != 6:
        return default
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return default


def _frame_ts(clip: dict) -> float:
    start, end = float(clip["start"]), float(clip["end"])
    for src in ((clip.get("thumbnail_plan") or {}).get("frame_ts"), clip.get("thumbnail_ts")):
        if isinstance(src, (int, float)) and not isinstance(src, bool) and start <= src <= end:
            return float(src)
    return start + 0.4 * (end - start)


def _extract_frame(source: Path, ts: float, out_png: Path) -> None:
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{ts:.3f}", "-i", str(source),
           "-frames:v", "1", "-y", str(out_png)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-12:])
        raise RuntimeError(f"ffmpeg extract frame falhou (exit {proc.returncode}): {tail}")


# area do rosto do host (fracao do frame) abaixo da qual ele e "distante demais"
# p/ virar sujeito (gate do has_subject). Se ausente/degradado -> fundo sem recorte.
_MIN_HOST_AREA = 0.02
# area "confortavel": abaixo dela preferimos o MAIOR close-up do host na janela ao
# inves do frame mais proximo de `ts` (evita recortar um host distante/pequeno que,
# esticado, vira uma cabeca minuscula ou de baixa resolucao).
_COMFORT_HOST_AREA = 0.05


def _resolve_host_frame(video_id: str, ts: float, start: float | None,
                        end: float | None) -> tuple[float, list | None, float]:
    """(ts_escolhido, bbox do host, area). Usa o frame mais proximo de `ts`; se o
    host ali estiver pequeno/distante (plano aberto), troca pelo frame com o MAIOR
    rosto do host dentro de [start, end] (melhor close-up disponivel). area=0 se
    nao ha host (o chamador cai no fundo sem recorte)."""
    faces = load_faces(video_id)
    if not faces or faces.get("degraded"):
        return ts, None, 0.0
    hf = [(fr["ts"], fc) for fr in (faces.get("frames") or [])
          for fc in fr.get("faces", []) if fc.get("identity") == 0]
    if not hf:
        return ts, None, 0.0
    cts, cfc = min(hf, key=lambda x: abs(x[0] - ts))
    if cfc.get("area", 0.0) < _COMFORT_HOST_AREA:
        win = [(t, fc) for t, fc in hf if start is None or end is None
               or start <= t <= end] or hf
        bt, bfc = max(win, key=lambda x: x[1].get("area", 0.0))
        if bfc.get("area", 0.0) > cfc.get("area", 0.0):
            cts, cfc = bt, bfc
    return cts, cfc.get("bbox"), float(cfc.get("area", 0.0))


def _cutout(pil_rgb, model: str):
    """Recorte da pessoa (rembg/U2Net) -> PIL RGBA aparado ao conteudo.

    O rembg devolve o RGBA no tamanho da coluna recortada (alta/estreita), mas a
    pessoa ocupa so uma parte dela (o resto vira transparente). Aparamos ao bbox
    do alpha p/ que o sujeito PREENCHA a altura ao escalar em `_compose_subject`
    (sem isso o host distante virava uma cabeca minuscula flutuando no canto)."""
    os.environ.setdefault("U2NET_HOME", str(paths.MODELS_ROOT / "rembg"))
    from rembg import new_session, remove
    out = remove(pil_rgb, session=new_session(model)).convert("RGBA")
    box = out.split()[3].getbbox()                             # bbox do alpha != 0
    return out.crop(box) if box else out


def _background(frame, w: int, h: int, has_subject: bool = True):
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    bg = ImageOps.fit(frame, (w, h), method=Image.Resampling.LANCZOS)  # cover-crop centrado
    if has_subject:
        # blur leve + escurecido: contexto atras do recorte, sem concorrer com o
        # sujeito (o escurecido segura o "fantasma" do mesmo rosto).
        bg = bg.filter(ImageFilter.GaussianBlur(radius=max(6, w // 100)))
        bg = ImageEnhance.Brightness(bg).enhance(0.45)
    else:
        # sem sujeito (evento/slide): o FRAME e o conteudo -> quase nitido, so um
        # leve escurecido p/ o texto (com contorno/caixa) ficar legivel por cima.
        bg = bg.filter(ImageFilter.GaussianBlur(radius=2))
        bg = ImageEnhance.Brightness(bg).enhance(0.62)
    bg = ImageEnhance.Color(bg).enhance(1.15)
    bg = ImageEnhance.Contrast(bg).enhance(1.06)
    return bg.convert("RGBA")


def _host_crop(frame, bbox: list | None):
    """Recorta a coluna cabeca+tronco do host (bbox do rosto expandido)."""
    if not bbox:
        return frame
    fw, fh = frame.size
    x, y, w, h = bbox
    fx, fy, fbw, fbh = x * fw, y * fh, w * fw, h * fh
    cx = fx + fbw / 2
    crop_w = min(fw, fbw * 4.0)                                # largo: nao corta ombro/braco
    x0 = max(0, min(fw - crop_w, cx - crop_w / 2))
    y0 = max(0, fy - fbh * 0.9)                                # folga acima do cabelo
    return frame.crop((int(x0), int(y0), int(x0 + crop_w), fh))  # ate a base (tronco)


def _compose_subject(bg, cutout, side: str, w: int, h: int, glow_rgb=_ACCENT):
    from PIL import Image, ImageFilter
    # escala o recorte pela altura, limitando a largura.
    # center (short): sujeito dominante ~60%+. side (corte): ocupa ~metade,
    # altura quase cheia, encostado na borda -> deixa a outra metade pro texto.
    cw, ch = cutout.size
    if side == "center":
        target_h, max_w = int(h * 0.94), int(w * 0.92)
    else:
        target_h, max_w = int(h * 0.99), int(w * 0.60)
    scale = target_h / ch
    tw = int(cw * scale)
    if tw > max_w:
        scale = max_w / cw
        tw, target_h = max_w, int(ch * scale)
    cutout = cutout.resize((max(1, tw), max(1, target_h)), Image.Resampling.LANCZOS)

    if side == "right":
        x = w - tw - int(w * 0.01)
    elif side == "left":
        x = int(w * 0.01)
    else:
        x = (w - tw) // 2
    y = h - target_h                                           # alinhado a base

    # GLOW: silhueta na cor de marca borrada por baixo (duas passadas p/ intensidade)
    alpha = cutout.split()[3]
    sil = Image.new("RGBA", cutout.size, tuple(glow_rgb) + (255,))
    sil.putalpha(alpha)
    glow = sil.filter(ImageFilter.GaussianBlur(radius=max(6, w // 70)))
    canvas = bg.copy()
    for _ in range(3):
        canvas.alpha_composite(glow, (x, y))
    canvas.alpha_composite(cutout, (x, y))
    return canvas.convert("RGB")


def _burn_text(clip: dict, composite_png: Path, out_jpg: Path, w: int, h: int,
               region: str = "full", accent: str | None = None) -> None:
    """Queima impacto+ganchos (ASS, mesmo estilo das thumbs locais) sobre o PNG."""
    clip_dir = out_jpg.parent
    ass_path = paths.clip_thumbnail_ass_path(clip["video_id"], clip["id"]) \
        if clip.get("video_id") else clip_dir / f"{clip['id']}.thumb.ass"
    ass_path.write_text(build_thumb_ass(clip, w, h, region=region, accent=accent),
                        encoding="utf-8")
    tmp = clip_dir / f"{out_jpg.stem}.tmp.jpg"
    cmd = ["ffmpeg", "-v", "error", "-i", "./" + composite_png.name,
           "-vf", f"ass={ass_path.name}", "-frames:v", "1", "-q:v", "2",
           "-y", "./" + tmp.name]
    proc = subprocess.run(cmd, cwd=str(clip_dir), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-12:])
        raise RuntimeError(f"ffmpeg burn text falhou (exit {proc.returncode}): {tail}")
    os.replace(tmp, out_jpg)


def generate_thumbnail_composite(clip: dict, video_id: str, tcfg: dict,
                                 account: dict | None) -> dict:
    """Gera a thumb compositada local em `<clip_id>.thumb.jpg`. Retorna
    {path, ts, provider}. Levanta em falha (chamador cai na thumb ASS simples)."""
    from PIL import Image

    fmt = clip["format"]
    w, h = (int(x) for x in FORMAT_RULES[fmt]["thumbnail_resolution"].split("x"))
    # cor de marca da conta (glow do sujeito + texto); sem accent -> amarelo.
    accent_hex = ((account or {}).get("brand") or {}).get("accent_color")
    glow_rgb = _hex_to_rgb(accent_hex)
    # frame do fundo/recorte: parte do frame_ts pedido, mas troca por um close-up
    # do host se o rosto ali for pequeno/distante (plano aberto de evento).
    ts, host_bbox, host_area = _resolve_host_frame(
        video_id, _frame_ts(clip), clip.get("start"), clip.get("end"))
    has_subject = host_bbox is not None and host_area >= _MIN_HOST_AREA

    # Layout. COM sujeito: short = central (texto topo/base); corte = lateral
    # (sujeito num lado, texto na outra metade). SEM sujeito (evento/slide sem
    # rosto usavel): sem recorte, o frame vira o fundo e o texto vai centralizado
    # (region full) — evita recorte quebrado de um pedaco de tela/gráfico.
    plan_layout = (clip.get("thumbnail_plan") or {}).get("layout")
    if not has_subject:
        side, region = None, "full"
    elif fmt == "corte":
        side, region = ("left", "right") if plan_layout == "left-face" else ("right", "left")
    else:
        side, region = "center", "full"

    clip_dir = paths.clip_dir(video_id, clip["id"], create=True)
    out_path = paths.clip_thumbnail_path(video_id, clip["id"])

    with tempfile.TemporaryDirectory() as td:
        frame_png = Path(td) / "frame.png"
        _extract_frame(paths.source_video_path(video_id), ts, frame_png)
        frame = Image.open(frame_png).convert("RGB")

        bg = _background(frame, w, h, has_subject=has_subject)
        if has_subject:
            cutout = _cutout(_host_crop(frame, host_bbox),
                             tcfg.get("rembg_model", "u2net"))
            composite = _compose_subject(bg, cutout, side, w, h, glow_rgb=glow_rgb)
        else:
            composite = bg.convert("RGB")

        comp_png = clip_dir / f"{clip['id']}.thumb.comp.png"
        composite.save(comp_png)
        try:
            _burn_text({**clip, "video_id": video_id}, comp_png, out_path, w, h,
                       region, accent=accent_hex)
        finally:
            comp_png.unlink(missing_ok=True)

    return {"path": out_path, "ts": ts, "provider": "local_composite"}

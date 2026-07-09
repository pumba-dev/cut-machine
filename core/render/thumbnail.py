"""Geracao da miniatura (thumbnail) do clip: frame chamativo + frases.

Extrai 1 frame do source no `thumbnail_ts` (apontado pelo clip-scout) e queima
por cima a frase de impacto + 2-3 frases de gancho (do copywriter, campo
`thumbnail_text`). Texto via ASS (mesma tecnica das legendas: fonte por nome,
cwd na pasta do clip, paths relativos — sem escaping de fontfile no Windows).

Resolucao por formato (FORMAT_RULES["...']["thumbnail_resolution"]): corte
1280x720 (16:9), short 1080x1920 (vertical). A miniatura PODE cortar as
laterais (crop central) — e uma imagem chamativa, nao o video.

Fallback: sem `thumbnail_text`, deriva o texto de hook_text/title, entao a
geracao nunca depende do copywriter ter rodado.
"""
import os
import subprocess

from .. import paths
from ..contracts import FORMAT_RULES

# Cores da miniatura em ASS (&HAABBGGRR, AA=00 opaco). Amarelo de marca #FFD93D.
_ACCENT = "&H003DD9FF"   # amarelo
_BLACK = "&H00000000"
_WHITE = "&H00FFFFFF"

# Tamanhos/paddings por formato (relativos ao PlayRes da miniatura).
# impact = frase amarela grande no topo; hook = chip de gancho na faixa inferior.
# corte usa layout LATERAL (impacto+chips na metade da largura): fonte menor que
# o short p/ o impacto longo caber em poucas linhas sem colidir com os chips.
_FONT_SIZES = {
    "corte": {"impact": 96, "hook": 46, "imp_out": 7, "chip_pad": 13},
    "short": {"impact": 220, "hook": 90, "imp_out": 13, "chip_pad": 24},
}
_DEFAULT_SIZES = {"impact": 170, "hook": 76, "imp_out": 10, "chip_pad": 18}


def _t(value: float) -> str:
    return f"{float(value):.3f}"


def _resolve_ts(clip: dict) -> float:
    """Timestamp absoluto do frame. Usa thumbnail_ts; fallback = 40% do clip."""
    start = float(clip["start"])
    end = float(clip["end"])
    ts = clip.get("thumbnail_ts")
    if isinstance(ts, (int, float)) and not isinstance(ts, bool) and start <= ts <= end:
        return float(ts)
    return start + 0.4 * (end - start)


def _first_words(text: str, max_chars: int = 38) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut or text[:max_chars]


def _title_miolo(clip: dict) -> str:
    title = clip.get("title")
    if isinstance(title, str) and " | " in title:
        parts = title.split(" | ")
        if len(parts) >= 2:
            return parts[1]
    return title if isinstance(title, str) else ""


def _content(clip: dict) -> tuple[str, list[str]]:
    """(impact, hooks) em CAIXA ALTA, com fallback para hook_text/title."""
    tt = clip.get("thumbnail_text")
    impact, hooks = "", []
    if isinstance(tt, dict):
        if isinstance(tt.get("impact"), str):
            impact = tt["impact"].strip()
        if isinstance(tt.get("hooks"), list):
            hooks = [h.strip() for h in tt["hooks"]
                     if isinstance(h, str) and h.strip()]
    if not impact:
        impact = _first_words(clip.get("hook_text") or "") or _title_miolo(clip)
    if not impact:
        impact = "ASSISTA ATE O FIM"
    hooks = hooks[:3]
    return impact.upper(), [h.upper() for h in hooks]


def _ass_escape(text: str) -> str:
    """Neutraliza caracteres que o parser de override ASS interpretaria."""
    return (text or "").replace("\\", "").replace("{", "(").replace("}", ")")


def build_thumb_ass(clip: dict, width: int, height: int, region: str = "full") -> str:
    """.ass da miniatura (PlayRes = resolucao da thumb).

    Layout (revisado 2026-07-08): frase de IMPACTO amarela GRANDE no topo
    (Alignment 8, ocupa boa parte da largura, quebra em 2 linhas se longa) +
    os ganchos como CHIPS distintos empilhados na FAIXA INFERIOR — cada gancho
    em Dialogue proprio com BorderStyle=3 (caixa opaca), cores ALTERNANDO
    preto/amarelo e folga vertical entre eles, para o usuario ler 3 frases
    SEPARADAS e longe da frase principal (nao mais um bloco unico embaixo dela).

    `region` confina o texto a uma COLUNA (layout lateral do corte 16:9): "left"
    = impacto+chips na metade esquerda (sujeito na direita), "right" = espelho,
    "full" (default) = comportamento classico (centro, topo/base).
    """
    fmt = clip.get("format")
    s = _FONT_SIZES.get(fmt, _DEFAULT_SIZES)
    impact, hooks = _content(clip)
    if region != "full":  # layout lateral (corte): coluna estreita -> so 2 chips
        hooks = hooks[:2]
    impact_fs, hook_fs = s["impact"], s["hook"]
    imp_out, chip_pad = s["imp_out"], s["chip_pad"]
    top_margin = round(height * 0.035)

    # Coluna do texto conforme a region (para o layout lateral do corte). Chips
    # ANCORADOS na borda da coluna (an4/an6), nao centrados: frase longa cresce
    # p/ dentro sem clipar na borda (centrado, chip largo estourava a lateral).
    if region == "left":
        imp_ml, imp_mr, chip_an, chip_x = 40, round(width * 0.40), 4, 40
    elif region == "right":
        imp_ml, imp_mr, chip_an, chip_x = round(width * 0.40), 40, 6, width - 40
    else:
        imp_ml, imp_mr, chip_an, chip_x = 40, 40, 5, round(width / 2)

    # Impacto: topo-centro (da coluna), contorno preto grosso + sombra leve.
    impact_style = (
        f"Style: Impact,Arial Black,{impact_fs},{_ACCENT},{_WHITE},{_BLACK},"
        f"&H64000000,-1,0,0,0,100,100,0,0,1,{imp_out},{max(2, imp_out // 3)},"
        f"8,{imp_ml},{imp_mr},{top_margin},1"
    )
    # Ganchos: chip com caixa (BorderStyle=3); cor da caixa/texto vem inline.
    hook_style = (
        f"Style: Hook,Arial Black,{hook_fs},{_WHITE},{_WHITE},{_BLACK},"
        f"&H00000000,-1,0,0,0,100,100,0,0,3,{chip_pad},0,5,40,40,40,1"
    )

    events = [
        f"Dialogue: 0,0:00:00.00,0:00:10.00,Impact,,0,0,0,,{{\\b1}}{_ass_escape(impact)}"
    ]
    n = len(hooks)
    if n:
        step = round(hook_fs * 2.2)
        band_bottom = round(height * (0.90 if region != "full" else 0.92))
        for i, h in enumerate(hooks):
            y = band_bottom - (n - 1 - i) * step
            box, txt = (_BLACK, _ACCENT) if i % 2 == 0 else (_ACCENT, _BLACK)
            tag = (f"{{\\pos({chip_x},{y})\\an{chip_an}\\1c{txt}\\3c{box}"
                   f"\\bord{chip_pad}\\b1}}")
            events.append(
                f"Dialogue: 0,0:00:00.00,0:00:10.00,Hook,,0,0,0,,{tag}{_ass_escape(h)}"
            )

    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{impact_style}\n"
        f"{hook_style}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        + "\n".join(events) + "\n"
    )


def generate_thumbnail(clip: dict, video_id: str) -> dict:
    """Gera <clip_id>.thumb.jpg. Assume que a pasta do clip ja existe (render).

    Retorna {"path": Path, "ts": float}. Levanta em falha do ffmpeg — o
    chamador (render_clip) trata como nao-fatal para nao derrubar o clip.
    """
    fmt = clip["format"]
    rules = FORMAT_RULES[fmt]
    width, height = (int(x) for x in rules["thumbnail_resolution"].split("x"))
    ts = _resolve_ts(clip)

    source = paths.source_video_path(video_id)
    clip_dir = paths.clip_dir(video_id, clip["id"], create=True)
    source_rel = os.path.relpath(source, clip_dir)

    ass_path = paths.clip_thumbnail_ass_path(video_id, clip["id"])
    ass_path.write_text(build_thumb_ass(clip, width, height), encoding="utf-8")

    out_path = paths.clip_thumbnail_path(video_id, clip["id"])
    out_name = "./" + out_path.name
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
          f"crop={width}:{height},ass={ass_path.name}")
    cmd = [
        "ffmpeg",
        "-ss", _t(ts), "-i", source_rel,
        "-frames:v", "1",
        "-vf", vf,
        "-q:v", "2",
        "-y", out_name,
    ]
    proc = subprocess.run(
        cmd, cwd=str(clip_dir), capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-15:])
        raise RuntimeError(f"ffmpeg thumbnail falhou (exit {proc.returncode}): {tail}")
    return {"path": out_path, "ts": ts}

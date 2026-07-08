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

# Cor de acento da miniatura (amarelo #FFD93D) em override inline ASS (&HBBGGRR&).
_ACCENT_INLINE = "&H3DD9FF&"
_WHITE_INLINE = "&HFFFFFF&"

# Tamanhos de fonte por formato (relativos ao PlayRes da miniatura).
_FONT_SIZES = {
    "corte": {"impact": 76, "hook": 44, "outline": 5},
    "short": {"impact": 120, "hook": 68, "outline": 7},
}
_DEFAULT_SIZES = {"impact": 90, "hook": 52, "outline": 6}


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


def build_thumb_ass(clip: dict, width: int, height: int) -> str:
    """.ass da miniatura (PlayRes = resolucao da thumb). Um Dialogue com a
    frase de impacto grande (acento) + ganchos menores (branco), Alignment 8
    (topo-centro) para deixar a cena visivel embaixo."""
    fmt = clip.get("format")
    sizes = _FONT_SIZES.get(fmt, _DEFAULT_SIZES)
    impact, hooks = _content(clip)

    imp_tag = f"{{\\fs{sizes['impact']}\\1c{_ACCENT_INLINE}\\b1}}"
    text = imp_tag + _ass_escape(impact)
    if hooks:
        hook_tag = f"{{\\fs{sizes['hook']}\\1c{_WHITE_INLINE}}}"
        text += "\\N" + hook_tag + "\\N".join(_ass_escape(h) for h in hooks)

    margin_v = round(height * 0.06)
    style = (
        f"Style: Thumb,Arial Black,{sizes['hook']},&H00FFFFFF,&H0000FFFF,"
        f"&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{sizes['outline']},0,"
        f"8,50,50,{margin_v},1"
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
        f"{style}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:10.00,Thumb,,0,0,0,,{text}\n"
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

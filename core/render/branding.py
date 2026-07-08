"""Identidade visual dos cortes: moldura de marca (preto+amarelo) + CTA.

Aplica-se SOMENTE ao formato `corte` (16:9). A moldura usa padding — o video
16:9 e reduzido e centralizado num canvas 1920x1080, deixando borda preta com
rim amarelo e uma faixa inferior com o texto de inscricao. Nada do video e
cortado (coerente com o short sem crop).

O texto e queimado via ASS (filtro `ass=`), como as legendas: libass resolve a
fonte "Arial Black" pelo nome, evitando o escaping de fontfile no Windows. O
.border.ass usa PlayRes 1920x1080 (diferente do 1080x1920 das legendas).

Config por conta em config/accounts.json (bloco opcional "brand"); campos
ausentes caem nos defaults abaixo.
"""

# Canvas de saida do corte (bate com FORMAT_RULES["corte"]["resolution"]).
CANVAS_W, CANVAS_H = 1920, 1080
SIDE = 40    # borda lateral preta (px)
TOP = 30     # borda superior preta (px)
BAR_H = 90   # faixa inferior preta que recebe o texto (px)
RIM = 8      # espessura do rim amarelo externo (px)
SEP = 3      # espessura da linha amarela acima da faixa de texto (px)

# Area interna maxima do video (o scale preserva aspecto dentro dela).
_INNER_W = CANVAS_W - 2 * SIDE
_INNER_H = CANVAS_H - TOP - BAR_H
_BAR_Y = CANVAS_H - BAR_H

BRAND_DEFAULTS = {
    "border_text": "Curta e se inscreva no canal",
    "border_color": "#000000",   # fundo/borda (corte)
    "accent_color": "#FFD93D",   # rim + texto (corte)
    # Moldura fixa do short (core/render/short_frame.py): a arte PNG ja traz
    # todo o texto/marca embutido; o render so compoe PNG + video + legendas.
    "short_frame": "",                  # path do PNG (rel. a raiz do repo); vazio = fallback solido
    "short_bg_color": "#111111",        # cor do fallback quando nao ha short_frame
    # Moldura fixa do corte (core/render/corte_frame.py): idem, arte 16:9. Vazio
    # = fallback para a moldura GERADA (padding + rim + faixa de texto ASS).
    "corte_frame": "",                  # path do PNG (rel. a raiz do repo)
}


def resolve_brand(account: dict | None) -> dict:
    """Mescla o bloco `brand` da conta sobre os defaults. Nunca lanca."""
    brand = dict(BRAND_DEFAULTS)
    if isinstance(account, dict) and isinstance(account.get("brand"), dict):
        for k, v in account["brand"].items():
            if k in brand and isinstance(v, str) and v.strip():
                brand[k] = v.strip()
    return brand


def _hex_rgb(color: str) -> tuple[int, int, int]:
    """'#RRGGBB' | '0xRRGGBB' | 'RRGGBB' -> (r, g, b). Fallback preto."""
    s = color.strip().lstrip("#")
    if s.lower().startswith("0x"):
        s = s[2:]
    if len(s) == 6:
        try:
            return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        except ValueError:
            pass
    return (0, 0, 0)


def ff_color(color: str) -> str:
    """Cor para o ffmpeg (drawbox/pad): 0xRRGGBB."""
    r, g, b = _hex_rgb(color)
    return f"0x{r:02X}{g:02X}{b:02X}"


def ass_color(color: str) -> str:
    """Cor para o ASS: &H00BBGGRR (BGR, alpha 00 = opaco)."""
    r, g, b = _hex_rgb(color)
    return f"&H00{b:02X}{g:02X}{r:02X}"


def build_corte_filter(brand: dict, border_ass_name: str) -> str:
    """filter_complex da moldura do corte -> label [v].

    border_ass_name deve ser relativo ao cwd do ffmpeg (pasta do clip).
    """
    bg = ff_color(brand["border_color"])
    accent = ff_color(brand["accent_color"])
    return (
        f"[0:v]scale={_INNER_W}:{_INNER_H}:force_original_aspect_ratio=decrease,"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,"
        f"pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:{TOP}:color={bg},"
        f"drawbox=x=0:y=0:w={CANVAS_W}:h={CANVAS_H}:color={accent}:t={RIM},"
        f"drawbox=x=0:y={_BAR_Y}:w={CANVAS_W}:h={SEP}:color={accent}:t=fill,"
        f"ass={border_ass_name}[v]"
    )


def build_border_ass(brand: dict) -> str:
    """.ass do texto de marca na faixa inferior do corte (PlayRes 1920x1080).

    Um unico Dialogue estatico (dura o clip inteiro), Arial Black na cor de
    acento, Alignment 2 (baixo-centro), MarginV pequeno para cair na faixa.
    """
    colour = ass_color(brand["accent_color"])
    text = brand["border_text"].replace("\n", " ").strip()
    fontsize = 54
    margin_v = 18
    style = (
        f"Style: Brand,Arial Black,{fontsize},{colour},&H0000FFFF,&H00000000,"
        f"&H00000000,-1,0,0,0,100,100,0,0,1,4,0,2,60,60,{margin_v},1"
    )
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {CANVAS_W}\n"
        f"PlayResY: {CANVAS_H}\n"
        "WrapStyle: 2\n"
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
        f"Dialogue: 0,0:00:00.00,9:59:59.99,Brand,,0,0,0,,{text}\n"
    )

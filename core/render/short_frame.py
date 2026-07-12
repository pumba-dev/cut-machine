"""Moldura fixa do short (9:16): video sob a arte PNG (janela transparente).

Aplica-se SOMENTE ao formato `short`. Substitui o antigo fundo blur (que
enjoava, por ser animado) por uma arte PNG decorativa estatica da conta
(`brand.short_frame`) ou, sem PNG, uma cor chapada de fallback
(`brand.short_bg_color`).

COMPOSICAO (PNG POR CIMA): o video 16:9 entra CROPADO PARA PREENCHER a "janela"
(retangulo TRANSPARENTE da arte, agora quase do tamanho do canvas) sobre um
canvas, e a arte PNG e sobreposta POR CIMA. Como a janela do PNG e transparente
(alpha 0), o video aparece por ela; elementos opacos que invadem a janela ficam
por cima do video. Progress bar e legendas word-level sao queimadas POR ULTIMO
(sempre visiveis, sobre tudo).

Crop-to-fill (nao mais letterbox): a janela nova e bem maior/mais vertical que
o video fonte 16:9 — encaixar por largura sobraria ~480px de barra preta em
cima/embaixo. O video escala ate COBRIR a janela e o excesso lateral e cortado
(perde borda da fonte, sem barra preta). Sem reframe dinamico
(core.render.reframe, opt-in) o corte e um crop central estatico o clipe
inteiro; com reframe, vira uma serie de cortes de "camera" ao redor de quem
fala (ver core.render.frame_common.build_video_stage).

TODO o texto/marca (nome do canal, numero, @handle, CTAs de curtir/comentar/
inscrever) e os icones ja vem EMBUTIDOS na propria arte PNG — o render NAO
desenha texto de marca por cima (so as legendas de fala + a progress bar).

WINDOW e a posicao/tamanho do retangulo transparente da arte atual
(assets/short-frame/principal.png), medida UMA vez e fixada aqui. Se a arte
mudar a janela, remedir e atualizar WINDOW. Para remedir (ffmpeg + numpy, via
ALPHA — a janela agora e transparente, nao preta):
    raw = subprocess.run(["ffmpeg","-v","error","-i",PNG,"-vf","scale=1080:1920",
          "-f","rawvideo","-pix_fmt","rgba","-"], capture_output=True).stdout
    a = numpy.frombuffer(raw, "u1").reshape(1920,1080,4)
    ys, xs = numpy.where(a[...,3] < 128)   # bounding box dos pixels transparentes
    # WINDOW = (xs.min(), ys.min(), xs.max()-xs.min()+1, ys.max()-ys.min()+1)
"""
from .branding import ff_color
from .frame_common import build_video_stage, even

CANVAS_W, CANVAS_H = 1080, 1920

# Janela do video (x, y, w, h) no canvas 1080x1920 = retangulo transparente da
# arte assets/short-frame/principal.png (medido via alpha). Video crop-to-fill
# preenche esta janela por inteiro (sem barra preta).
WINDOW = (20, 0, 1040, 1545)

# Cor de fundo quando a conta nao tem arte PNG (fallback estatico, sem marca).
BG_FALLBACK = "#111111"

# Progress bar: barra fina no topo que enche esquerda->direita ao longo do
# clip (TODOS os shorts, nao opt-in). y pequeno = nao invade a janela do video.
_PBAR_Y = 8
_PBAR_H = 10
_PBAR_TRACK = "0x333333@0.55"

# NAO usar drawbox p/ a largura animada: a opcao `t` do PROPRIO drawbox
# (thickness) sombreia a variavel de tempo `t` dentro das expressoes de
# x/y/w/h do MESMO filtro -- `w='CANVAS_W*t/dur'` avalia `t` como a
# thickness (ex.: "fill" vira um valor enorme -> largura sempre cheia,
# constante, nunca anima; confirmado empiricamente). `crop` tambem nao serve:
# w/h de saida sao fixados na config do filtro (nao podem variar quadro a
# quadro). Solucao: duas fontes solidas (`fill` cheia + `cov`, cor do "vazio")
# sobrepostas via `overlay`, cujo `x` SUPORTA `t` de verdade (deslocamento de
# posicao, nao redimensionamento) -- `cov` desliza da esquerda encobrindo o
# `fill` e revelando por baixo, um pixel a menos a cada instante.
def _progress_bar_chain(dur: float, accent_hex: str, in_label: str, out_label: str) -> str:
    accent = ff_color(accent_hex)
    safe_dur = max(dur, 0.01)
    d = f"{safe_dur + 0.5:.3f}"
    return (
        f"color=c={accent}@0.95:s={CANVAS_W}x{_PBAR_H}:d={d}:r=30[pbfill];"
        f"color=c={_PBAR_TRACK}:s={CANVAS_W}x{_PBAR_H}:d={d}:r=30[pbcov];"
        f"[{in_label}][pbfill]overlay=x=0:y={_PBAR_Y}[pbf];"
        f"[pbf][pbcov]overlay=x='{CANVAS_W}*t/{safe_dur:.3f}':y={_PBAR_Y}[{out_label}]"
    )


def build_short_filter(bg_hex: str, has_png: bool, captions_ass_name: str,
                       vfx: str = "", crop_segments: list[dict] | None = None,
                       dur: float | None = None, accent_hex: str = "#FFD93D") -> str:
    """filter_complex do short -> label [v]. Nome do .ass relativo ao cwd.

    Encaixa o video (crop-to-fill) dentro de WINDOW, sem barra preta; a arte PNG
    (input 1, quando ha) e sobreposta POR CIMA (janela transparente deixa o
    video aparecer). Progress bar (`dur`, sempre que informado) e queimada logo
    antes das legendas, que vao por ULTIMO. O `overlay=...:shortest=1` do video
    limita a saida a sua duracao (canvas/PNG sao fontes infinitas). Toda a marca
    ja vem embutida na arte PNG.

    `vfx` (core.render.transform.video_filters) e um fragmento opcional de
    filtros de video (speed/zoom/cor) inserido ANTES do crop-to-fill — terminado
    em virgula ou "". `crop_segments` (core.render.reframe, opt-in): lista de
    cortes de camera ao redor de quem fala; None = crop central classico.
    """
    wx, wy, ww, wh = WINDOW
    ew, eh = even(ww), even(wh)
    ox, oy = wx + (ww - ew) // 2, wy + (wh - eh) // 2
    # setpts=PTS-STARTPTS: zera o PTS do video (seek `-ss` deixa o 1o frame com
    # PTS > 0) para alinhar com o canvas/PNG (fontes em t=0) — sem isso o overlay
    # so mostra o canvas ate o video chegar (abertura preta).
    stage = build_video_stage(ew, eh, crop_segments, out_label="fg")
    fg = f"[0:v]setpts=PTS-STARTPTS,{vfx}{stage};"
    ov = f"[canvas][fg]overlay=x={ox}:y={oy}:shortest=1"
    if has_png:
        chain = (fg
                + f"color=c=black:s={CANVAS_W}x{CANVAS_H}[canvas];"
                + ov + "[base];"
                + f"[1:v]scale={CANVAS_W}:{CANVAS_H}[png];"
                + f"[base][png]overlay=0:0[bp];")
    else:
        chain = (fg
                + f"color=c={ff_color(bg_hex)}:s={CANVAS_W}x{CANVAS_H}[canvas];"
                + ov + "[bp];")
    pre_ass = "bp"
    if dur:
        chain += _progress_bar_chain(dur, accent_hex, pre_ass, "pb") + ";"
        pre_ass = "pb"
    return chain + f"[{pre_ass}]ass={captions_ass_name}[v]"

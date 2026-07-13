"""Moldura fixa do corte (16:9): video sob a arte PNG (janela transparente).

Aplica-se SOMENTE ao formato `corte`. Quando a conta tem `brand.corte_frame`,
substitui a moldura GERADA (core/render/branding.py: padding preto + rim
amarelo + faixa de texto ASS) por uma arte PNG decorativa estatica.

COMPOSICAO (PNG POR CIMA): o video 16:9 entra CROPADO PARA PREENCHER a "janela"
(retangulo TRANSPARENTE da arte, agora quase do tamanho do canvas) sobre um
canvas preto, e a arte PNG e sobreposta POR CIMA. Como a janela do PNG e
transparente (alpha 0), o video aparece por ela; elementos opacos que invadem a
janela (ex.: o badge no topo) ficam ENTAO por cima do video. Sem legendas
queimadas (corte nao queima); sem progress bar (so shorts).

Crop-to-fill (nao mais letterbox): a janela e quase do tamanho do canvas — sem
reframe dinamico (core.render.reframe, opt-in) o corte e um crop central
estatico o clipe inteiro; com reframe, vira uma serie de cortes de "camera" ao
redor de quem fala (ver core.render.frame_common.build_video_stage).

TODO o texto/marca (nome do canal, numero, @handle, CTAs de curtir/comentar/
inscrever) e os icones ja vem EMBUTIDOS na propria arte PNG — o render NAO
desenha texto de marca por cima. Trocar identidade = trocar o PNG.

WINDOW e a posicao/tamanho do retangulo transparente da arte atual
(assets/corte-frame/politica.png), medida UMA vez e fixada aqui. Se a arte
mudar a janela, remedir e atualizar WINDOW. Para remedir (ffmpeg + numpy, via
ALPHA — a janela agora e transparente, nao preta):
    raw = subprocess.run(["ffmpeg","-v","error","-i",PNG,"-vf","scale=1920:1080",
          "-f","rawvideo","-pix_fmt","rgba","-"], capture_output=True).stdout
    a = numpy.frombuffer(raw, "u1").reshape(1080,1920,4)
    ys, xs = numpy.where(a[...,3] < 128)   # bounding box dos pixels transparentes
    # WINDOW = (xs.min(), ys.min(), xs.max()-xs.min()+1, ys.max()-ys.min()+1)
"""
from .branding import ff_color
from .frame_common import build_video_stage, even

CANVAS_W, CANVAS_H = 1920, 1080

# Janela do video (x, y, w, h) no canvas 1920x1080 = retangulo transparente da
# arte assets/corte-frame/politica.png (medido via alpha). Video crop-to-fill
# preenche esta janela por inteiro (sem barra preta).
WINDOW = (48, 44, 1824, 863)

# Cor de fundo quando a conta nao tem arte PNG (fallback estatico, sem marca).
BG_FALLBACK = "#111111"


def build_corte_frame_filter(bg_hex: str, has_png: bool, vfx: str = "",
                             crop_segments: list[dict] | None = None) -> str:
    """filter_complex do corte com moldura PNG -> label [v].

    Encaixa o video (crop-to-fill) dentro de WINDOW, sem barra preta; a arte
    PNG (input 1) e sobreposta POR CIMA (janela transparente deixa o video
    aparecer; elementos opacos que invadem a janela cobrem o video). O
    `overlay=...:shortest=1` do video limita a saida a sua duracao (canvas/PNG
    sao fontes infinitas). Sem has_png, cai numa cor chapada (fallback do smoke).

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
        return (fg
                + f"color=c=black:s={CANVAS_W}x{CANVAS_H}[canvas];"
                + ov + "[base];"
                + f"[1:v]scale={CANVAS_W}:{CANVAS_H}[png];"
                + "[base][png]overlay=0:0[v]")
    return (fg
            + f"color=c={ff_color(bg_hex)}:s={CANVAS_W}x{CANVAS_H}[canvas];"
            + ov + "[v]")

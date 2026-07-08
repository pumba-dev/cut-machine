"""Moldura fixa do corte (16:9): video sob a arte PNG (janela transparente).

Aplica-se SOMENTE ao formato `corte`. Quando a conta tem `brand.corte_frame`,
substitui a moldura GERADA (core/render/branding.py: padding preto + rim
amarelo + faixa de texto ASS) por uma arte PNG decorativa estatica.

COMPOSICAO (PNG POR CIMA): o video 16:9 entra SEM CROP encaixado na "janela"
(retangulo TRANSPARENTE da arte) sobre um canvas preto, e a arte PNG e
sobreposta POR CIMA. Como a janela do PNG e transparente (alpha 0), o video
aparece por ela; elementos opacos que invadem a janela (ex.: o badge da onca no
topo) ficam ENTAO por cima do video. Sem legendas queimadas (corte nao queima).

TODO o texto/marca (nome do canal, numero, @handle, CTAs de curtir/comentar/
inscrever) e os icones ja vem EMBUTIDOS na propria arte PNG — o render NAO
desenha texto de marca por cima. Trocar identidade = trocar o PNG.

WINDOW e a posicao/tamanho do retangulo transparente da arte atual
(assets/corte-frame/principal.png), medida UMA vez e fixada aqui. Se a arte
mudar a janela, remedir e atualizar WINDOW. Para remedir (ffmpeg + numpy, via
ALPHA — a janela agora e transparente, nao preta):
    raw = subprocess.run(["ffmpeg","-v","error","-i",PNG,"-vf","scale=1920:1080",
          "-f","rawvideo","-pix_fmt","rgba","-"], capture_output=True).stdout
    a = numpy.frombuffer(raw, "u1").reshape(1080,1920,4)
    ys, xs = numpy.where(a[...,3] < 128)   # bounding box dos pixels transparentes
    # WINDOW = (xs.min(), ys.min(), xs.max()-xs.min()+1, ys.max()-ys.min()+1)
"""
from .branding import ff_color

CANVAS_W, CANVAS_H = 1920, 1080

# Janela do video (x, y, w, h) no canvas 1920x1080 = retangulo transparente da
# arte assets/corte-frame/principal.png (medido via alpha). Video 16:9 encaixa
# aqui sem crop (ajusta por altura -> ~1378x776 centralizado; sobra preta).
WINDOW = (250, 155, 1421, 776)

# Cor de fundo quando a conta nao tem arte PNG (fallback estatico, sem marca).
BG_FALLBACK = "#111111"


def build_corte_frame_filter(bg_hex: str, has_png: bool) -> str:
    """filter_complex do corte com moldura PNG -> label [v].

    Encaixa o video (SEM crop) dentro de WINDOW, centralizado sobre um canvas
    preto; a arte PNG (input 1) e sobreposta POR CIMA (janela transparente deixa
    o video aparecer; elementos opacos que invadem a janela cobrem o video). O
    `overlay=...:shortest=1` do video limita a saida a sua duracao (canvas/PNG
    sao fontes infinitas). Sem has_png, cai numa cor chapada (fallback do smoke).
    """
    wx, wy, ww, wh = WINDOW
    # setpts=PTS-STARTPTS: zera o PTS do video (seek `-ss` deixa o 1o frame com
    # PTS > 0) para alinhar com o canvas/PNG (fontes em t=0) — sem isso o overlay
    # so mostra o canvas ate o video chegar (abertura preta).
    fg = (f"[0:v]setpts=PTS-STARTPTS,scale={ww}:{wh}:force_original_aspect_ratio=decrease,"
          "scale=trunc(iw/2)*2:trunc(ih/2)*2[fg];")
    ov = f"[canvas][fg]overlay=x={wx}+({ww}-w)/2:y={wy}+({wh}-h)/2:shortest=1"
    if has_png:
        return (fg
                + f"color=c=black:s={CANVAS_W}x{CANVAS_H}[canvas];"
                + ov + "[base];"
                + f"[1:v]scale={CANVAS_W}:{CANVAS_H}[png];"
                + "[base][png]overlay=0:0[v]")
    return (fg
            + f"color=c={ff_color(bg_hex)}:s={CANVAS_W}x{CANVAS_H}[canvas];"
            + ov + "[v]")

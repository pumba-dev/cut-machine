"""Moldura fixa do short (9:16): video sob a arte PNG (janela transparente).

Aplica-se SOMENTE ao formato `short`. Substitui o antigo fundo blur (que
enjoava, por ser animado) por uma arte PNG decorativa estatica da conta
(`brand.short_frame`) ou, sem PNG, uma cor chapada de fallback
(`brand.short_bg_color`).

COMPOSICAO (PNG POR CIMA): o video 16:9 entra SEM CROP encaixado na "janela"
(retangulo TRANSPARENTE da arte) sobre um canvas, e a arte PNG e sobreposta POR
CIMA. Como a janela do PNG e transparente (alpha 0), o video aparece por ela;
elementos opacos que invadem a janela ficam por cima do video. As legendas
word-level sao queimadas POR ULTIMO (sempre visiveis, sobre tudo).

TODO o texto/marca (nome do canal, numero, @handle, CTAs de curtir/comentar/
inscrever) e os icones ja vem EMBUTIDOS na propria arte PNG — o render NAO
desenha texto de marca por cima (so as legendas de fala).

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

CANVAS_W, CANVAS_H = 1080, 1920

# Janela do video (x, y, w, h) no canvas 1080x1920 = retangulo transparente da
# arte assets/short-frame/principal.png (medido via alpha). Video 16:9 encaixa
# aqui sem crop.
WINDOW = (20, 656, 1040, 608)

# Cor de fundo quando a conta nao tem arte PNG (fallback estatico, sem marca).
BG_FALLBACK = "#111111"


def build_short_filter(bg_hex: str, has_png: bool, captions_ass_name: str) -> str:
    """filter_complex do short -> label [v]. Nome do .ass relativo ao cwd.

    Encaixa o video (SEM crop) dentro de WINDOW, centralizado sobre um canvas; a
    arte PNG (input 1, quando ha) e sobreposta POR CIMA (janela transparente
    deixa o video aparecer). As legendas sao queimadas por ULTIMO. O
    `overlay=...:shortest=1` do video limita a saida a sua duracao (canvas/PNG
    sao fontes infinitas). Toda a marca ja vem embutida na arte PNG.
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
                + f"[base][png]overlay=0:0[bp];"
                + f"[bp]ass={captions_ass_name}[v]")
    return (fg
            + f"color=c={ff_color(bg_hex)}:s={CANVAS_W}x{CANVAS_H}[canvas];"
            + ov + f",ass={captions_ass_name}[v]")

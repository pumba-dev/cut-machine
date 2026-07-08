"""Moldura fixa do short (9:16): fundo estatico + janela do video.

Aplica-se SOMENTE ao formato `short`. Substitui o antigo fundo blur (que
enjoava, por ser animado) por um fundo ESTATICO: a arte PNG decorativa da conta
(`brand.short_frame`) ou, sem PNG, uma cor chapada de fallback
(`brand.short_bg_color`). O video 16:9 entra SEM CROP encaixado na "janela"
(retangulo preto) da arte, centralizado, e as legendas word-level sao queimadas
por cima.

TODO o texto/marca (nome do canal, numero, @handle, CTAs de curtir/comentar/
inscrever) e os icones ja vem EMBUTIDOS na propria arte PNG — o render NAO
desenha texto de marca por cima (so as legendas de fala).

WINDOW e a posicao/tamanho do retangulo preto da arte atual
(assets/short-frame/principal.png), medida UMA vez e fixada aqui. Se a arte
mudar a janela, remedir e atualizar WINDOW. Para remedir (ffmpeg + numpy):
    raw = subprocess.run(["ffmpeg","-v","error","-i",PNG,"-vf","scale=1080:1920",
          "-f","rawvideo","-pix_fmt","gray","-"], capture_output=True).stdout
    a = numpy.frombuffer(raw, "u1").reshape(1920,1080) < 24   # mascara de preto
    # y = maior run vertical de True na coluna 540; x = maior run na linha do meio
"""
from .branding import ff_color

CANVAS_W, CANVAS_H = 1080, 1920

# Janela do video (x, y, w, h) no canvas 1080x1920 = retangulo preto da arte
# assets/short-frame/principal.png (medido). Video 16:9 encaixa aqui sem crop.
WINDOW = (20, 656, 1040, 608)

# Cor de fundo quando a conta nao tem arte PNG (fallback estatico, sem marca).
BG_FALLBACK = "#111111"


def build_short_filter(bg_hex: str, has_png: bool, captions_ass_name: str) -> str:
    """filter_complex do short -> label [v]. Nome do .ass relativo ao cwd.

    Encaixa o video (SEM crop) dentro de WINDOW, centralizado; bg = arte PNG
    (input 1, quando ha) ou cor chapada. `overlay=...:shortest=1` limita a saida
    a duracao do video (bg/PNG sao fontes infinitas). So as legendas sao
    queimadas por cima; toda a marca ja vem embutida na arte PNG.
    """
    wx, wy, ww, wh = WINDOW
    fg = (f"[0:v]scale={ww}:{wh}:force_original_aspect_ratio=decrease,"
          "scale=trunc(iw/2)*2:trunc(ih/2)*2[fg];")
    if has_png:
        bg = f"[1:v]scale={CANVAS_W}:{CANVAS_H}[bg];"
    else:
        bg = f"color=c={ff_color(bg_hex)}:s={CANVAS_W}x{CANVAS_H}[bg];"
    ov = f"[bg][fg]overlay=x={wx}+({ww}-w)/2:y={wy}+({wh}-h)/2:shortest=1,"
    return fg + bg + ov + f"ass={captions_ass_name}[v]"

"""Escolha do encoder de video (libx264 CPU vs h264_nvenc GPU) + probe/fallback.

Modulo FOLHA (so stdlib): `ffmpeg.py` importa `intro.py`/`outro.py`, entao um
helper compartilhado por eles nao pode morar em `ffmpeg.py` (ciclo de import).

Encoder e propriedade DA MAQUINA (mesma GPU para todas as contas), nao da conta.
`RENDER_ENCODER=auto|nvenc|libx264` (default `auto`) decide; `auto` roda um probe
cacheado 1x por processo. Se o NVENC falhar em runtime, `note_nvenc_failure()`
degrada o resto do processo para libx264 (uma falha de driver nao deve virar
tentar-e-falhar por clip).

Alvo de qualidade: o `cq` do NVENC e escolhido para casar VISUALMENTE com o `crf`
do libx264 (short 18->19, corte 20->21). NVENC H.264 e menos eficiente que
`x264 -preset medium` (~20-40% maior no arquivo local; irrelevante -- o YouTube
re-encoda no servidor). `-maxrate/-bufsize` limitam o pico de bitrate causado
pelo filtro `noise=c0f=t` (transform), que e alto-entropia e infla o NVENC.
"""
import functools
import os
import re
import subprocess

# fmt -> (crf libx264, cq nvenc)
_QUALITY = {"short": (18, 19), "corte": (20, 21)}
# fmt -> (maxrate, bufsize) para o NVENC (teto contra picos do filtro noise)
_MAXRATE = {"short": ("24M", "48M"), "corte": ("16M", "32M")}

# Conjunto SEGURO de opcoes NVENC para o TU116 (GTX 1660 SUPER, Turing 7a ger.):
# -bf 3 e -spatial-aq sao aceitos; -temporal-aq e -b_ref_mode costumam ser
# rejeitados em H.264 na serie 16xx, entao ficam de fora (teste de hardware).
_NVENC_BASE = [
    "-preset", "p5", "-tune", "hq",
    "-rc", "vbr", "-b:v", "0",
    "-bf", "3", "-spatial-aq", "1", "-aq-strength", "8",
    "-rc-lookahead", "20", "-profile:v", "high", "-g", "60",
]

# Marcadores de erro ESPECIFICO de NVENC no stderr do ffmpeg: so estes disparam
# o fallback para CPU. Erro fora desta lista e bug de filtro/graph (libx264
# falharia igual) e deve propagar.
_NVENC_ERR = re.compile(
    r"OpenEncodeSessionEx|InitializeEncoder|nvcuda|No capable devices|"
    r"Cannot load|Provided device doesn't support|nvEncode|"
    r"generic error in an external library|Function not implemented",
    re.IGNORECASE,
)

# Setado no 1o fallback de runtime -> resto do processo pula NVENC.
_force_libx264 = False


def video_codec_args(fmt: str, encoder: str, pix_fmt: str = "yuv420p") -> list[str]:
    """Span `-c:v ... -pix_fmt <pix_fmt>` para o formato/encoder.

    Retorna SO o codec de video; `-r 30`, `-c:a`, `-movflags`, `-t`, `-y out`
    ficam a cargo do chamador. Com `encoder="libx264"` e `pix_fmt="yuv420p"`
    produz exatamente o span de hoje (sem regressao no caminho CPU). `pix_fmt`
    e overridavel para o concat-copy do intro/outro casar o range do conteudo
    (short=`yuvj420p`/full vs corte=`yuv420p`/limited)."""
    crf, cq = _QUALITY[fmt]
    if encoder == "nvenc":
        maxrate, bufsize = _MAXRATE[fmt]
        return [
            "-c:v", "h264_nvenc", *_NVENC_BASE,
            "-cq", str(cq), "-maxrate", maxrate, "-bufsize", bufsize,
            "-pix_fmt", pix_fmt,
        ]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
            "-pix_fmt", pix_fmt]


@functools.lru_cache(maxsize=1)
def _nvenc_available() -> bool:
    """True se um encode NVENC de 1 frame de fato roda nesta maquina.

    `ffmpeg -encoders | grep nvenc` so prova que o BINARIO tem nvenc (o build
    Gyan sempre tem) -- nao que o driver esta carregado, a GPU existe e uma
    sessao abre. O encode de 1 frame lavfi exercita o caminho inteiro
    (nvcuda.dll + OpenEncodeSessionEx + GPU) em ~0.3-1s."""
    try:
        p = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1:r=30",
             "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        return p.returncode == 0
    except Exception:  # noqa: BLE001 -- qualquer falha = NVENC indisponivel
        return False


def resolve_encoder() -> str:
    """Encoder efetivo para este processo: "nvenc" ou "libx264"."""
    if _force_libx264:
        return "libx264"
    choice = os.environ.get("RENDER_ENCODER", "auto").strip().lower()
    if choice in ("libx264", "cpu"):
        return "libx264"
    if choice in ("nvenc", "gpu"):
        return "nvenc"
    return "nvenc" if _nvenc_available() else "libx264"


def is_nvenc_error(stderr: str | None) -> bool:
    """True se o stderr indica falha ESPECIFICA de NVENC (dispara fallback CPU)."""
    return bool(stderr and _NVENC_ERR.search(stderr))


def note_nvenc_failure() -> None:
    """Marca o processo para pular NVENC no resto do run (degrada para CPU)."""
    global _force_libx264
    _force_libx264 = True

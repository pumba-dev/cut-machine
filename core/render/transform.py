"""Camada de transformacao anti-deteccao do render (opt-in por conta).

Gera fragmentos de filtro ffmpeg (video e audio) que tornam cada corte
TECNICAMENTE distinto do video original (quebra fingerprint do Content ID) e
distinto entre si (reduz padrao de reused-content), SEM mudar os invariantes que
o QA exige: resolucao exata e duracao end-start (+-0.5s) se mantem por
construcao.

- Config por conta em config/accounts.json, bloco opcional "transform" (irmao de
  "brand"). Campos ausentes caem em TRANSFORM_DEFAULTS (tudo NEUTRO) -> conta sem
  o bloco nao sofre nenhuma mudanca (regressao zero).
- Jitter POR CLIP: cada parametro ativo varia um pouco em torno da base, com
  amplitude `jitter`, de forma DETERMINISTICA (seed = hash do clip_id). Mesmo
  clip -> mesmo resultado (idempotente); clips diferentes -> parametros
  diferentes. `jitter=0` desliga a variacao (valores fixos da conta).
- So parametros ATIVOS (base != neutro) sofrem jitter: "off" continua off.

Invariantes:
- Video: velocidade via `setpts=PTS/speed`; zoom via `crop=iw/Z:ih/Z` (crop-in
  central, aspecto preservado; o `scale` para a janela vem DEPOIS, entao a
  resolucao final nao muda); cor via `eq=`/`lut3d=`.
- Audio: pitch SR-agnostico (`aresample=48000` antes do `asetrate`), EQ +
  `acompressor`, velocidade via `atempo` (casa com o `setpts` do video) e musica
  de fundo com duck reverso (sidechain = voz), sempre `duration=first` (= duracao
  da voz) para nao alterar o comprimento.
"""
import hashlib
import math
from pathlib import Path

from .. import paths

# Extensoes de audio aceitas em music_dir.
_MUSIC_EXTS = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac")

# Amplitude MAXIMA do jitter por parametro (multiplicada por `jitter` da conta e
# por um sinal em [-1, 1) derivado do seed). Mantido pequeno de proposito.
_JITTER_SPAN = {
    "speed": 0.015,
    "pitch_semitones": 0.5,
    "zoom": 0.025,
    "music_volume": 0.02,
    "contrast": 0.03,
    "brightness": 0.02,
    "saturation": 0.05,
    "gamma": 0.03,
}

# Limites duros (mantem legibilidade e evita valores que reprovariam no QA).
_SPEED_MIN, _SPEED_MAX = 0.95, 1.05
_ZOOM_MAX = 1.15

TRANSFORM_DEFAULTS = {
    "speed": 1.0,            # 1.0 = off
    "pitch_semitones": 0.0,  # 0 = off
    "eq": False,             # highpass/lowpass + equalizer + acompressor
    "music_dir": "",         # "" = off
    "music_volume": 0.20,    # ganho (trim) apos a normalizacao; a voz sempre tem prioridade
    "music_lufs": -16.0,     # alvo de loudness da musica (loudnorm) — iguala faixas de loudness diferente
    "color": None,           # dict {contrast,brightness,saturation,gamma} = off se None
    "lut": "",               # path .cube (tem precedencia sobre color); "" = off
    "zoom": 1.0,             # 1.0 = off
    "jitter": 0.0,           # 0 = fixo; ate 1.0 = amplitude relativa da variacao por clip
}


def resolve_transform(account: dict | None) -> dict:
    """Mescla o bloco `transform` da conta sobre os defaults. Nunca lanca.

    Tolerante a tipo: so aceita chaves conhecidas com tipo compativel; o resto
    fica no default neutro.
    """
    cfg = dict(TRANSFORM_DEFAULTS)
    src = account.get("transform") if isinstance(account, dict) else None
    if isinstance(src, dict):
        for k, v in src.items():
            if k in cfg and v is not None:
                cfg[k] = v
    return cfg


# ---------------------------------------------------------------------------
# Determinismo (seed por clip) + jitter
# ---------------------------------------------------------------------------

def seed_for(clip_id: str) -> int:
    """Seed deterministico do clip (idempotente; varia entre clips)."""
    h = hashlib.sha1(str(clip_id).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


def _rand01(seed: int, key: str) -> float:
    """Float deterministico em [0, 1) a partir de (seed, key)."""
    h = hashlib.sha1(f"{seed}:{key}".encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


def _rand_int(seed: int, key: str, n: int) -> int:
    if n <= 1:
        return 0
    return int(_rand01(seed, key) * n) % n


def _signed(seed: int, key: str) -> float:
    """[-1, 1) deterministico."""
    return _rand01(seed, key) * 2.0 - 1.0


def _as_float(v, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _jitter_amount(cfg: dict) -> float:
    return _clamp(_as_float(cfg.get("jitter"), 0.0), 0.0, 1.0)


def _jitter_delta(cfg: dict, seed: int, key: str) -> float:
    """Deslocamento deterministico do parametro `key` (0 se jitter desligado)."""
    return _signed(seed, key) * _jitter_amount(cfg) * _JITTER_SPAN.get(key, 0.0)


# ---------------------------------------------------------------------------
# Parametros efetivos
# ---------------------------------------------------------------------------

def speed_factor(cfg: dict, seed: int) -> float:
    """Fator de velocidade efetivo (1.0 = sem alteracao)."""
    base = _clamp(_as_float(cfg.get("speed"), 1.0), _SPEED_MIN, _SPEED_MAX)
    if abs(base - 1.0) < 1e-6:
        return 1.0
    return _clamp(base + _jitter_delta(cfg, seed, "speed"), _SPEED_MIN, _SPEED_MAX)


def _pitch_ratio(cfg: dict, seed: int) -> float:
    """Razao de frequencia do pitch (1.0 = sem alteracao)."""
    semi = _as_float(cfg.get("pitch_semitones"), 0.0)
    if abs(semi) < 1e-6:
        return 1.0
    semi += _jitter_delta(cfg, seed, "pitch_semitones")
    return 2.0 ** (semi / 12.0)


def _zoom(cfg: dict, seed: int) -> float:
    base = _as_float(cfg.get("zoom"), 1.0)
    if base <= 1.0 + 1e-6:
        return 1.0
    return _clamp(base + _jitter_delta(cfg, seed, "zoom"), 1.0, _ZOOM_MAX)


def _music_volume(cfg: dict, seed: int) -> float:
    base = _as_float(cfg.get("music_volume"), 0.08)
    return _clamp(base + _jitter_delta(cfg, seed, "music_volume"), 0.0, 0.5)


def _music_lufs(cfg: dict) -> float:
    """Alvo de loudness (LUFS) da musica. Sem jitter: consistencia e o objetivo."""
    return _clamp(_as_float(cfg.get("music_lufs"), -20.0), -70.0, -5.0)


def _resolve_path(rel) -> str | None:
    """Path absoluto (rel. a raiz do repo), ou None se ausente/inexistente."""
    if not rel or not str(rel).strip():
        return None
    p = Path(rel)
    if not p.is_absolute():
        p = paths.ROOT / str(rel)
    return str(p) if p.exists() else None


def _lut_path_escaped(cfg: dict) -> str | None:
    lut = cfg.get("lut")
    p = _resolve_path(lut) if isinstance(lut, str) else None
    if not p:
        return None
    # Filtro lut3d: barra normal + escapar ':' (drive do Windows) para o parser.
    return p.replace("\\", "/").replace(":", "\\:")


def _color_filter(cfg: dict, seed: int) -> str:
    """`lut3d=` (se `lut`) ou `eq=` (se `color` dict). "" se nenhum."""
    lut = _lut_path_escaped(cfg)
    if lut:
        return f"lut3d='{lut}'"
    color = cfg.get("color")
    if not isinstance(color, dict):
        return ""
    params: list[str] = []
    for key in ("contrast", "brightness", "saturation", "gamma"):
        v = color.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            vj = float(v) + _jitter_delta(cfg, seed, key)
            params.append(f"{key}={vj:.4f}")
    return "eq=" + ":".join(params) if params else ""


# ---------------------------------------------------------------------------
# Fragmentos de filtro
# ---------------------------------------------------------------------------

def video_filters(cfg: dict, seed: int) -> str:
    """Fragmento de filtros de VIDEO, terminado em virgula (ou "" se nenhum).

    Inserido logo apos `setpts=PTS-STARTPTS,` no grafo do frame (short/corte),
    ANTES do `scale` para a janela — por isso o `crop` de zoom nao altera a
    resolucao final.
    """
    parts: list[str] = []
    speed = speed_factor(cfg, seed)
    if abs(speed - 1.0) > 1e-6:
        parts.append(f"setpts=PTS/{speed:.5f}")
    zoom = _zoom(cfg, seed)
    if zoom > 1.0 + 1e-6:
        parts.append(f"crop=iw/{zoom:.5f}:ih/{zoom:.5f}")
    color = _color_filter(cfg, seed)
    if color:
        parts.append(color)
    return ",".join(parts) + "," if parts else ""


def audio_active(cfg: dict, seed: int, has_music: bool) -> bool:
    """True se ha qualquer processamento de audio a aplicar.

    Velocidade tambem conta: `setpts` acelera o video, entao o audio PRECISA de
    `atempo` para nao dessincronizar.
    """
    return (
        bool(cfg.get("eq"))
        or abs(_pitch_ratio(cfg, seed) - 1.0) > 1e-6
        or abs(speed_factor(cfg, seed) - 1.0) > 1e-6
        or has_music
    )


def build_audio_graph(cfg: dict, seed: int, *, music_index: int | None = None,
                      speed: float = 1.0, out_label: str = "aout") -> str:
    """Subgrafo de audio do filter_complex, terminado em `[out_label]`.

    Voz (`[0:a]`): normaliza para 48k, EQ + acompressor (se `eq`), pitch
    SR-agnostico (asetrate/atempo) e `atempo=speed` (casa com o `setpts` do
    video). Com musica: `loudnorm` iguala o loudness de QUALQUER faixa ao alvo
    `music_lufs` (mata o spread entre faixas — o motivo de uma cama sumir e outra
    estourar), `volume` faz o trim fino, e o duck reverso (`sidechaincompress`,
    sidechain = voz) abaixa a musica na fala; mistura com `amix duration=first`
    (comprimento = o da voz -> saida invariante). A VOZ nunca e comprimida pela
    musica; so a musica cede.
    """
    voice: list[str] = ["[0:a]aresample=48000"]
    if cfg.get("eq"):
        voice.append("highpass=f=60")
        voice.append("lowpass=f=15000")
        voice.append("equalizer=f=3000:t=q:w=1.5:g=2")
        voice.append("acompressor=threshold=-18dB:ratio=3:attack=20:release=250")
    ratio = _pitch_ratio(cfg, seed)
    if abs(ratio - 1.0) > 1e-6:
        voice.append(f"asetrate=48000*{ratio:.6f}")
        voice.append("aresample=48000")
        voice.append(f"atempo={1.0 / ratio:.6f}")
    if abs(speed - 1.0) > 1e-6:
        voice.append(f"atempo={speed:.6f}")
    voice_chain = ",".join(voice)

    if music_index is None:
        return f"{voice_chain}[{out_label}]"

    vol = _music_volume(cfg, seed)
    lufs = _music_lufs(cfg)
    return (
        f"{voice_chain},aformat=sample_fmts=fltp:channel_layouts=stereo,asplit=2[a0][a0side];"
        f"[{music_index}:a]aresample=48000,loudnorm=I={lufs:.1f}:TP=-1.5:LRA=11,"
        f"aresample=48000,volume={vol:.4f},"
        "aformat=sample_fmts=fltp:channel_layouts=stereo[mus];"
        # Duck SUAVE (threshold alto + ratio baixo): a musica so cede um pouco na
        # fala, mantendo uma cama de nivel CONSTANTE independente da densidade de
        # fala do trecho (ratio alto viraria gate: sumia em fala continua e
        # estourava nas pausas — a inconsistencia short-vs-corte).
        "[mus][a0side]sidechaincompress=threshold=0.3:ratio=3:attack=10:release=400[musd];"
        f"[a0][musd]amix=inputs=2:duration=first:normalize=0[{out_label}]"
    )


def pick_music(cfg: dict, seed: int) -> str | None:
    """Caminho absoluto de uma faixa de `music_dir`, escolhida deterministicamente.

    None se `music_dir` vazio/inexistente ou sem faixas — musica desligada sem erro.
    """
    d = cfg.get("music_dir")
    base = _resolve_path(d) if isinstance(d, str) else None
    if base is None or not Path(base).is_dir():
        return None
    files = sorted(
        p for p in Path(base).iterdir()
        if p.is_file() and p.suffix.lower() in _MUSIC_EXTS
    )
    if not files:
        return None
    return str(files[_rand_int(seed, "music", len(files))].resolve())


def summary(cfg: dict, seed: int, *, speed: float, music_path: str | None) -> dict:
    """Resumo dos parametros EFETIVOS aplicados (para render.transform)."""
    ratio = _pitch_ratio(cfg, seed)
    out: dict = {}
    if abs(speed - 1.0) > 1e-6:
        out["speed"] = round(speed, 5)
    if abs(ratio - 1.0) > 1e-6:
        out["pitch_semitones"] = round(12.0 * math.log2(ratio), 4)
    if cfg.get("eq"):
        out["eq"] = True
    zoom = _zoom(cfg, seed)
    if zoom > 1.0 + 1e-6:
        out["zoom"] = round(zoom, 5)
    if _color_filter(cfg, seed):
        out["color"] = _color_filter(cfg, seed)
    if music_path:
        out["music"] = Path(music_path).name
        out["music_volume"] = round(_music_volume(cfg, seed), 4)
    return out

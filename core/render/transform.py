"""Camada de transformacao anti-deteccao do render (opt-in por conta).

Gera fragmentos de filtro ffmpeg (video e audio) que tornam cada corte
TECNICAMENTE distinto do video original (quebra fingerprint do Content ID) e
distinto entre si (reduz padrao de reused-content), SEM mudar os invariantes que
o QA exige: resolucao exata e duracao end-start (+-0.5s) se mantem por
construcao.

- Config por conta em config/accounts.json, bloco opcional "transform" (irmao de
  "brand"). Campos ausentes caem em TRANSFORM_DEFAULTS (tudo NEUTRO) -> conta sem
  o bloco nao sofre nenhuma mudanca (regressao zero).
- VARIACAO POR CLIP (identidade unica): cada parametro numerico pode vir como
  RANGE `{"min": a, "max": b}` -> cada clip sorteia UM valor uniforme em [a, b]
  de forma DETERMINISTICA (seed = hash do clip_id). Clips diferentes pegam
  valores diferentes (cada corte tecnicamente distinto do outro); re-render do
  mesmo clip da o mesmo valor (idempotente, como o resto do pipeline). Ou como
  ESCALAR (valor fixo) — nesse caso a variacao vem do `jitter` legado (amplitude
  relativa em torno da base, mesmo seed; `jitter=0` = totalmente fixo). Os dois
  modos convivem por parametro; ranges IGNORAM jitter (o range ja e a variacao).
- So parametros ATIVOS (base/range != neutro) variam: "off" continua off. Os
  limites duros (_SPEED_MIN etc.) clampam por cima do sorteio.

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

# Pool compartilhado de musica (nao mais por conta) + extensoes aceitas.
MUSIC_ROOT = paths.ROOT / "assets" / "music"
MUSIC_EXTS = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac")
_MUSIC_MOODS = ("agressiva", "neutra", "calma")

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
    "eq_notch_db": 0.4,
    "noise": 3.0,
}

# Limites duros (mantem legibilidade e evita valores que reprovariam no QA).
_SPEED_MIN, _SPEED_MAX = 0.95, 1.05
_ZOOM_MAX = 1.15
_NOTCH_DB_MIN = -5.0     # notch mais fundo que isso abafa sibilancia/consoantes (voz muffled)
_NOISE_MAX = 40.0        # forca de grain acima disso vira granulado visivel + estoura bitrate

TRANSFORM_DEFAULTS = {
    "speed": 1.0,            # 1.0 = off
    "pitch_semitones": 0.0,  # 0 = off
    "eq": False,             # highpass/lowpass + equalizer + acompressor
    "eq_notch": False,       # dip 5-8kHz na "assinatura de voz" (requer eq); off por padrao
    "eq_notch_db": -3.0,     # profundidade do notch em dB (negativo); clamp [-5, 0]
    "noise": 0.0,            # grain de luma temporal por frame; 0 = off (pixels distintos por frame)
    "music": False,          # False = off; liga a musica do pool compartilhado assets/music/
    "music_volume": 0.20,    # ganho (trim) apos a normalizacao; a voz sempre tem prioridade
    "music_lufs": -16.0,     # alvo de loudness da musica (loudnorm) — iguala faixas de loudness diferente
    "color": None,           # dict {contrast,brightness,saturation,gamma} = off se None
    "lut": "",               # path .cube (tem precedencia sobre color); "" = off
    "zoom": 1.0,             # 1.0 = off
    "flip": False,           # espelha horizontalmente (hflip) -- pixels tecnicamente distintos
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
# Range por parametro (identidade unica por clip)
# ---------------------------------------------------------------------------
# Um parametro numerico pode vir como ESCALAR (valor fixo + jitter, compat com
# configs antigas) OU como {"min": a, "max": b} — nesse caso cada clip sorteia
# UM valor uniforme em [a, b] de forma DETERMINISTICA (seed = clip_id): clips
# diferentes pegam valores diferentes (identidade unica), mas re-renderizar o
# mesmo clip da o mesmo valor (idempotente, como o resto do pipeline). O jitter
# NAO se aplica a params em range (o range JA e a variacao). Os limites duros
# (_SPEED_MIN etc.) continuam clampando por cima do sorteio.

def _range_ends(v, default: float) -> tuple[float, float]:
    """(lo, hi) de um valor escalar (lo==hi) ou de um dict {min,max}."""
    if isinstance(v, dict):
        lo = _as_float(v.get("min"), default)
        hi = _as_float(v.get("max"), lo)
        return (min(lo, hi), max(lo, hi))
    f = _as_float(v, default)
    return (f, f)


def _sample(cfg: dict, seed: int, key: str, default: float) -> float:
    """Valor-base efetivo do parametro, com a variacao por clip ja embutida:
    range {min,max} -> sorteio uniforme deterministico; escalar -> valor + jitter.
    NAO clampa nos limites duros nem trata 'off' (o chamador faz)."""
    v = cfg.get(key, default)
    if isinstance(v, dict):
        lo, hi = _range_ends(v, default)
        return lo + _rand01(seed, key) * (hi - lo)
    return _as_float(v, default) + _jitter_delta(cfg, seed, key)


# ---------------------------------------------------------------------------
# Parametros efetivos
# ---------------------------------------------------------------------------

def speed_factor(cfg: dict, seed: int) -> float:
    """Fator de velocidade efetivo (1.0 = sem alteracao)."""
    lo, hi = _range_ends(cfg.get("speed", 1.0), 1.0)
    if abs(lo - 1.0) < 1e-6 and abs(hi - 1.0) < 1e-6:
        return 1.0
    return _clamp(_sample(cfg, seed, "speed", 1.0), _SPEED_MIN, _SPEED_MAX)


def _pitch_ratio(cfg: dict, seed: int) -> float:
    """Razao de frequencia do pitch (1.0 = sem alteracao)."""
    lo, hi = _range_ends(cfg.get("pitch_semitones", 0.0), 0.0)
    if abs(lo) < 1e-6 and abs(hi) < 1e-6:
        return 1.0
    semi = _sample(cfg, seed, "pitch_semitones", 0.0)
    return 2.0 ** (semi / 12.0)


def _zoom(cfg: dict, seed: int) -> float:
    lo, hi = _range_ends(cfg.get("zoom", 1.0), 1.0)
    if hi <= 1.0 + 1e-6:
        return 1.0
    return _clamp(_sample(cfg, seed, "zoom", 1.0), 1.0, _ZOOM_MAX)


def _noise(cfg: dict, seed: int) -> float:
    """Forca efetiva do grain de video (0 = off)."""
    lo, hi = _range_ends(cfg.get("noise", 0.0), 0.0)
    if hi <= 1e-6:
        return 0.0
    return _clamp(_sample(cfg, seed, "noise", 0.0), 0.0, _NOISE_MAX)


def _notch_db(cfg: dict, seed: int) -> float:
    """Ganho efetivo do notch 5-8kHz em dB (negativo; 0 = sem dip)."""
    return _clamp(_sample(cfg, seed, "eq_notch_db", -3.0), _NOTCH_DB_MIN, 0.0)


def _music_volume(cfg: dict, seed: int) -> float:
    return _clamp(_sample(cfg, seed, "music_volume", 0.08), 0.0, 0.5)


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
    # Neutro de cada canal do filtro eq (usado como default do range).
    _NEUTRAL = {"contrast": 1.0, "brightness": 0.0, "saturation": 1.0, "gamma": 1.0}
    params: list[str] = []
    for key in ("contrast", "brightness", "saturation", "gamma"):
        v = color.get(key)
        if isinstance(v, dict):  # range {min,max}: sorteio deterministico por clip
            lo, hi = _range_ends(v, _NEUTRAL[key])
            vj = lo + _rand01(seed, f"color.{key}") * (hi - lo)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):  # escalar + jitter
            vj = float(v) + _jitter_delta(cfg, seed, key)
        else:
            continue
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
    if cfg.get("flip"):
        parts.append("hflip")
    noise = _noise(cfg, seed)
    if noise > 0.0:
        # Grain de LUMA (c0 evita speckle de croma em yuv420p) TEMPORAL (c0f=t:
        # frame novo a cada frame -> DCT distinto por frame), seed deterministico
        # por clip (idempotente). Aplicado na resolucao da fonte, antes do scale.
        # c0s (strength) e INT no ffmpeg -> arredonda.
        parts.append(f"noise=c0s={round(noise)}:c0f=t:all_seed={seed % 2147483647}")
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
                      speed: float = 1.0, out_label: str = "aout",
                      in_label: str = "0:a") -> str:
    """Subgrafo de audio do filter_complex, terminado em `[out_label]`.

    Voz (`in_label`, default `0:a`): normaliza para 48k, EQ + acompressor (se
    `eq`), pitch SR-agnostico (asetrate/atempo) e `atempo=speed` (casa com o
    `setpts` do video). Com musica: `loudnorm` iguala o loudness de QUALQUER
    faixa ao alvo `music_lufs` (mata o spread entre faixas — o motivo de uma
    cama sumir e outra estourar), `volume` faz o trim fino, e o duck reverso
    (`sidechaincompress`, sidechain = voz) abaixa a musica na fala; mistura com
    `amix duration=first` (comprimento = o da voz -> saida invariante). A VOZ
    nunca e comprimida pela musica; so a musica cede.

    `in_label` (core.render.jumpcut, opt-in): quando o jump-cut ja cortou
    `[0:a]` em `[a_jc]` (trim+concat nos mesmos pontos do video), a cadeia de
    voz continua a PARTIR do audio ja cortado, nao do audio cru.
    """
    voice: list[str] = [f"[{in_label}]aresample=48000"]
    if cfg.get("eq"):
        voice.append("highpass=f=60")
        voice.append("lowpass=f=15000")
        voice.append("equalizer=f=3000:t=q:w=1.5:g=2")
        if cfg.get("eq_notch"):
            # Dip largo (~4.7-7.9kHz) na banda de "assinatura de voz", ANTES do
            # compressor (o acompressor reage ao sinal ja atenuado). Peaking com
            # ganho negativo (nao brick-wall) para nao "lispar" a voz.
            voice.append(f"equalizer=f=6300:t=q:w=2.0:g={_notch_db(cfg, seed):.2f}")
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


def _music_files_in(d: Path) -> list[Path]:
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in MUSIC_EXTS)


def pick_music(cfg: dict, seed: int, mood: str = "neutra") -> str | None:
    """Caminho absoluto de uma faixa do pool compartilhado `assets/music/<mood>/`,
    escolhida deterministicamente (mesmo seed de sempre -> mesmo clip_id sempre
    pega a mesma faixa).

    None se `cfg["music"]` for falsy (opt-in explicito por conta) ou se nao
    houver nenhuma faixa em lugar nenhum -- musica desligada sem erro. `mood`
    (core.render.music_mood.derive_mood) cai em cascata se a pasta pedida
    estiver ausente/vazia: `mood` -> "neutra" -> uniao achatada dos 3 moods.
    """
    if not cfg.get("music"):
        return None
    mood = mood if mood in _MUSIC_MOODS else "neutra"
    files = _music_files_in(MUSIC_ROOT / mood)
    if not files and mood != "neutra":
        files = _music_files_in(MUSIC_ROOT / "neutra")
    if not files:
        files = sorted(p for m in _MUSIC_MOODS for p in _music_files_in(MUSIC_ROOT / m))
    if not files:
        return None
    return str(files[_rand_int(seed, "music", len(files))].resolve())


def summary(cfg: dict, seed: int, *, speed: float, music_path: str | None,
            music_mood: str | None = None) -> dict:
    """Resumo dos parametros EFETIVOS aplicados (para render.transform)."""
    ratio = _pitch_ratio(cfg, seed)
    out: dict = {}
    if abs(speed - 1.0) > 1e-6:
        out["speed"] = round(speed, 5)
    if abs(ratio - 1.0) > 1e-6:
        out["pitch_semitones"] = round(12.0 * math.log2(ratio), 4)
    if cfg.get("eq"):
        out["eq"] = True
        if cfg.get("eq_notch"):
            out["eq_notch_db"] = round(_notch_db(cfg, seed), 2)
    zoom = _zoom(cfg, seed)
    if zoom > 1.0 + 1e-6:
        out["zoom"] = round(zoom, 5)
    if _color_filter(cfg, seed):
        out["color"] = _color_filter(cfg, seed)
    if cfg.get("flip"):
        out["flip"] = True
    noise = _noise(cfg, seed)
    if noise > 0.0:
        out["noise"] = round(noise, 1)
    if music_path:
        out["music"] = Path(music_path).name
        out["music_volume"] = round(_music_volume(cfg, seed), 4)
        if music_mood:
            out["music_mood"] = music_mood
    return out

"""Config opt-in do reframe dinamico por conta (bloco `reframe` em accounts.json).

Irmao dos blocos `brand`/`transform`/`thumbnail`. Tudo opt-in e retrocompativel
(bloco ausente = tudo-off = comportamento classico: crop central estatico, sem
speaker-track, sem cutaway/punch-in/sfx):

- `enabled`: liga a fase `speaker-track` (core.faces.speaker_track) + o crop
  dinamico ao redor de quem fala no render (core.render.reframe).
- `min_segment_s`: histerese -- nao troca de "camera" mais rapido que isso.
- `margin`: folga em volta do bbox do rosto ativo (fracao do bbox) antes de
  clampar na janela de crop.
- `min_crop_h`: piso da altura do crop (fracao do frame). MAIOR = crop mais
  AMPLO = MENOS zoom (mostra mais do video). Em short limita o zoom em
  ~altura_janela/(min_crop_h*altura_fonte); 0.70 => ~2x. Mexe na pratica so no
  short (no corte a trava de largura ja recalcula a altura do crop).
- `fps`/`max_frames`: orcamento de amostragem do speaker-track (core.faces
  .speaker_track.analyze_speaker_track).
- `min_confidence`: score minimo de correlacao boca x audio p/ aceitar um turno.
- `cutaway`: corta rapido pro rosto de quem OUVE nas pausas do falante ativo.
- `hook_punch`: zoom no timestamp do hook/gancho do clip (thumbnail_ts).
- `sfx_dir`/`sfx_volume`: stinger sonoro em cada troca de plano do reframe.
"""

REFRAME_DEFAULTS = {
    "enabled": False,
    "min_segment_s": 1.2,
    "margin": 0.35,
    "min_crop_h": 0.70,
    "fps": 5.0,
    "max_frames": 4000,
    "min_confidence": 0.15,
    "cutaway": False,
    "hook_punch": False,
    "sfx_dir": "",
    "sfx_volume": 0.5,
}

_BOOL_KEYS = ("enabled", "cutaway", "hook_punch")
_STR_KEYS = ("sfx_dir",)
_NUM_KEYS = ("min_segment_s", "margin", "min_crop_h", "fps", "max_frames", "min_confidence", "sfx_volume")


def resolve_reframe(account: dict | None) -> dict:
    """Mescla o bloco `reframe` da conta sobre os defaults. Nunca lanca."""
    cfg = dict(REFRAME_DEFAULTS)
    block = account.get("reframe") if isinstance(account, dict) else None
    if not isinstance(block, dict):
        return cfg
    for k in _BOOL_KEYS:
        if isinstance(block.get(k), bool):
            cfg[k] = block[k]
    for k in _STR_KEYS:
        v = block.get(k)
        if isinstance(v, str):
            cfg[k] = v.strip()
    for k in _NUM_KEYS:
        v = block.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            cfg[k] = v
    return cfg


def reframe_enabled(cfg: dict) -> bool:
    return bool(cfg.get("enabled"))

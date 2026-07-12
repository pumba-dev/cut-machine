"""Config opt-in do jump-cut por conta (bloco `jumpcut` em accounts.json).

Irmao dos blocos `brand`/`transform`/`thumbnail`/`reframe`. Ausente = tudo-off
= comportamento classico (duracao = end-start, sem cortes de silencio).

- `enabled`: liga o corte de pausas longas (core.render.jumpcut).
- `min_gap_s`: pausa minima entre palavras pra virar corte.
- `buffer_s`: respiro mantido em cada ponta do corte (nao corta em cima da
  respiracao/inicio da proxima palavra).
"""

JUMPCUT_DEFAULTS = {
    "enabled": False,
    "min_gap_s": 1.2,
    "buffer_s": 0.15,
}

_BOOL_KEYS = ("enabled",)
_NUM_KEYS = ("min_gap_s", "buffer_s")


def resolve_jumpcut(account: dict | None) -> dict:
    """Mescla o bloco `jumpcut` da conta sobre os defaults. Nunca lanca."""
    cfg = dict(JUMPCUT_DEFAULTS)
    block = account.get("jumpcut") if isinstance(account, dict) else None
    if not isinstance(block, dict):
        return cfg
    for k in _BOOL_KEYS:
        if isinstance(block.get(k), bool):
            cfg[k] = block[k]
    for k in _NUM_KEYS:
        v = block.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            cfg[k] = v
    return cfg


def jumpcut_enabled(cfg: dict) -> bool:
    return bool(cfg.get("enabled"))

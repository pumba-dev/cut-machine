"""Config opt-in de miniatura por conta (bloco `thumbnail` em accounts.json).

Irmao dos blocos `brand`/`transform`. Controla, todas opt-in e retrocompativeis
(bloco ausente = tudo-off = comportamento classico: thumb ASS local com crop
central, sem intro):

- `face_aware`: liga a fase `faces` (deteccao de rosto/emocao) + o subagente
  thumbnail-director + a thumb COMPOSITADA local (fundo+recorte+glow+texto,
  enquadrada no host). Sem isso, a thumb usa o crop central ASS simples.
- `intro_short`: cola a thumb como ~1s congelado no INICIO dos shorts (capa do
  feed do Shorts). So o formato short.
- `rembg_model`: modelo de recorte de fundo usado pelo composite (recorte da pessoa).

`resolve_thumbnail` NAO reusa `branding.resolve_brand` de proposito: aquele so
copia campos string (dropa bool/numero), e aqui a maioria dos campos nao e string.
"""

# Tudo desligado por padrao: zero regressao para contas sem o bloco `thumbnail`.
THUMBNAIL_DEFAULTS = {
    "face_aware": False,          # liga fase faces + director + composite local
    "intro_short": False,         # prepend da thumb (~1s) nos shorts
    "intro_duration_s": 1.0,      # duracao do congelado inicial
    "rembg_model": "u2net",       # modelo de recorte da pessoa (composite)
}

_BOOL_KEYS = ("face_aware", "intro_short")
_STR_KEYS = ("rembg_model",)
_NUM_KEYS = ("intro_duration_s",)


def resolve_thumbnail(account: dict | None) -> dict:
    """Mescla o bloco `thumbnail` da conta sobre os defaults. Nunca lanca."""
    cfg = dict(THUMBNAIL_DEFAULTS)
    block = account.get("thumbnail") if isinstance(account, dict) else None
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


def intro_enabled(tcfg: dict, fmt: str) -> bool:
    """True se deve prepender a thumb como intro. So shorts (capa do feed)."""
    return fmt == "short" and bool(tcfg.get("intro_short"))


def composite_enabled(tcfg: dict) -> bool:
    """True se a thumb local deve ser a COMPOSITADA (fundo+recorte+glow+texto),
    e nao a ASS simples (crop central). Gratis e deterministica; gated no mesmo
    master switch da pipeline de rosto."""
    return bool(tcfg.get("face_aware"))

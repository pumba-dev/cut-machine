"""Registro de contas por plataforma (config/accounts.json).

Multi-conta: cada conta tem plataforma, id proprio e um diretorio de
credenciais isolado (secrets/<plataforma>/<conta>/). Publishers recebem a
conta resolvida e nunca assumem caminho fixo de token.
"""
import json
from pathlib import Path

from .paths import CONFIG_DIR, ROOT

ACCOUNTS_PATH = CONFIG_DIR / "accounts.json"


def load_accounts() -> list[dict]:
    data = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    return data["accounts"]


def get_account(platform: str, account_id: str | None = None) -> dict:
    candidates = [a for a in load_accounts() if a["platform"] == platform]
    if not candidates:
        raise LookupError(f"nenhuma conta configurada para {platform} em config/accounts.json")
    if account_id:
        for account in candidates:
            if account["id"] == account_id:
                return account
        raise LookupError(f"conta {platform}/{account_id} nao existe em config/accounts.json")
    defaults = [a for a in candidates if a.get("default")]
    return (defaults or candidates)[0]


def credentials_dir(account: dict, create: bool = True) -> Path:
    d = ROOT / account["credentials_dir"]
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d

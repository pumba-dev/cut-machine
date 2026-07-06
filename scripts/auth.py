"""Autentica uma conta de publicacao (gera/renova token OAuth).

Uso: python scripts/auth.py --platform youtube [--account <account_id>]
Idempotente: reusa token valido; so abre o navegador quando necessario.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from core import accounts, cli
from core.publishers import get_publisher


def main() -> None:
    parser = argparse.ArgumentParser(description="Autentica conta de publicacao (OAuth).")
    parser.add_argument("--platform", default="youtube")
    parser.add_argument("--account", default=None, help="id da conta em config/accounts.json")
    args = parser.parse_args()

    try:
        account = accounts.get_account(args.platform, args.account)
        publisher = get_publisher(args.platform)
    except LookupError as exc:
        cli.fail(str(exc))

    try:
        publisher.authenticate(account)
    except FileNotFoundError as exc:
        cli.fail(str(exc))
    except Exception as exc:
        cli.fail(f"falha na autenticacao: {exc}")

    token_path = accounts.credentials_dir(account) / "token.json"
    cli.emit(True, platform=args.platform, account=account["id"],
             token_path=str(token_path))


if __name__ == "__main__":
    main()

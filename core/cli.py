"""Helpers compartilhados pelos CLIs em scripts/.

Convencao: todo script imprime UMA linha JSON como ultimo output no stdout,
com pelo menos {"ok": true|false}. O orquestrador (Claude) le essa linha.
"""
import json
import sys
from typing import NoReturn


def emit(ok: bool, **fields) -> None:
    print(json.dumps({"ok": ok, **fields}, ensure_ascii=False))


def fail(message: str, **fields) -> NoReturn:
    emit(False, error=message, **fields)
    sys.exit(1)

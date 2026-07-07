"""Valida clips.json: erros duros (contracts.validate_plan) + avisos de padrao
editorial (contracts.lint_copy, ver references/padrao-copy.md).

Uso: python scripts/validate_plan.py --video-id <id>
Read-only: nao toca state.json nem clips.json. errors nao-vazio -> exit 1.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from core import contracts, paths
from core.cli import emit, fail


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida copy e contrato do clips.json")
    parser.add_argument("--video-id", required=True)
    args = parser.parse_args()

    clips_file = paths.clips_path(args.video_id)
    if not clips_file.exists():
        fail(f"clips.json nao encontrado para {args.video_id}")
    plan = contracts.load_plan(clips_file)

    errors = contracts.validate_plan(plan)
    warnings = contracts.lint_copy(plan)
    clips_com_copy = sum(1 for c in plan.get("clips", [])
                         if c.get("title") is not None)

    if errors:
        emit(False, video_id=args.video_id, errors=errors, warnings=warnings,
             clips_com_copy=clips_com_copy)
        sys.exit(1)
    emit(True, video_id=args.video_id, errors=[], warnings=warnings,
         clips_com_copy=clips_com_copy)


if __name__ == "__main__":
    main()

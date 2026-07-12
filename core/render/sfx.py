"""Stinger sonoro nos cortes de plano do reframe (opt-in, Fase 6).

Um som curto (whoosh/ding) tocado em cada troca de "camera" produzida pelo
reframe dinamico (core.render.reframe) -- reforca a sensacao de edicao alem
do corte visual (mais um sinal de conteudo transformado, nao so cosmetico).
Escolha da faixa deterministica por clip (mesmo esquema de seed de
core.render.transform.pick_music); pasta precisa ser livre de claim
(`reframe.sfx_dir`, irmao de `transform.music_dir`).
"""
import hashlib
from pathlib import Path

from .. import paths

_SFX_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".ogg")


def _resolve_path(rel) -> str | None:
    if not rel or not str(rel).strip():
        return None
    p = Path(rel)
    if not p.is_absolute():
        p = paths.ROOT / str(rel)
    return str(p) if p.exists() else None


def pick_sfx(sfx_dir: str, seed: int) -> str | None:
    """Caminho absoluto de uma faixa de `sfx_dir`, escolhida deterministicamente.
    None se `sfx_dir` vazio/inexistente ou sem faixas -- sfx desligado sem erro."""
    base = _resolve_path(sfx_dir)
    if base is None or not Path(base).is_dir():
        return None
    files = sorted(p for p in Path(base).iterdir()
                   if p.is_file() and p.suffix.lower() in _SFX_EXTS)
    if not files:
        return None
    idx = int.from_bytes(hashlib.sha1(f"{seed}:sfx".encode("utf-8")).digest()[:8], "big") % len(files)
    return str(files[idx].resolve())


def cut_times(crop_segments: list[dict] | None) -> list[float]:
    """Timestamps (tempo LOCAL do clip) das trocas de plano do reframe -- todo
    `start` de segmento exceto o primeiro (t=0, inicio do clip, nao e um corte)."""
    if not crop_segments or len(crop_segments) < 2:
        return []
    return [round(seg["start"], 3) for seg in crop_segments[1:]]


def build_sfx_filter(sfx_index: int, cuts: list[float], volume: float, *,
                     in_label: str, out_label: str = "aout") -> str:
    """Subgrafo de audio que mixa uma copia (com delay) da faixa de sfx em
    cada tempo de `cuts` sobre `in_label` -> `[out_label]`. `sfx_index` e o
    indice do input ffmpeg da faixa (`-i sfx.mp3`); decodificada uma vez,
    `asplit` gera N copias internas (uma por corte)."""
    n = len(cuts)
    parts = [f"[{sfx_index}:a]volume={volume:.3f},asplit={n}"
            + "".join(f"[sfx{i}]" for i in range(n)) + ";"]
    delayed = []
    for i, t in enumerate(cuts):
        ms = max(0, round(t * 1000))
        parts.append(f"[sfx{i}]adelay={ms}:all=1[sfxd{i}];")
        delayed.append(f"[sfxd{i}]")
    mix_inputs = f"[{in_label}]" + "".join(delayed)
    parts.append(f"{mix_inputs}amix=inputs={n + 1}:duration=first:normalize=0[{out_label}]")
    return "".join(parts)

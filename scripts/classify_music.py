"""Classifica as faixas soltas em assets/music/ por clima (mood) e move cada
uma para a subpasta correspondente (agressiva/neutra/calma).

Analise de audio REAL via ffmpeg (decodifica mono float32) + numpy: RMS
(energia), zero-crossing rate (distorcao/percussao), centroide espectral
(brilho) e um proxy de tempo/batida (autocorrelacao do envelope de onset).
Sem dependencia nova (ffmpeg ja e obrigatorio no projeto; numpy ja esta em
requirements.txt).

So enxerga arquivos soltos DIRETO na raiz de assets/music/ (nao desce nas
pastas de mood) -- uma faixa ja classificada fica invisivel pro scanner,
entao mover um arquivo a mao entre pastas de mood nunca e desfeito. Isso
tambem e a idempotencia do script: sem arquivo novo solto, `skipped: true`.

O score de cada faixa e um z-score contra estatisticas do CORPUS, cacheadas
em assets/music/_classify_stats.json -- evita que adicionar faixas novas
reembaralhe o bucket de faixas ja classificadas a cada run. Use --force pra
recomputar a distribuicao de referencia do zero (reclassifica todo mundo).

Idempotente. Imprime UMA linha JSON no fim.

Uso: python scripts/classify_music.py [--dry-run] [--force] [--report <path>]
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from core.cli import emit, fail
from core.render.transform import MUSIC_EXTS, MUSIC_ROOT

_MOODS = ("agressiva", "neutra", "calma")
_SR = 22050
_MIN_CORPUS_FOR_STATS = 8
_WEIGHTS = {"rms": 0.35, "zcr": 0.25, "centroid": 0.25, "tempo": 0.15}

_STATS_PATH = MUSIC_ROOT / "_classify_stats.json"
_REPORT_PATH = MUSIC_ROOT / "_classify_report.md"


# ---------------------------------------------------------------------------
# Extracao de features (por faixa, nunca fatal)
# ---------------------------------------------------------------------------

def _decode_mono(path: Path, sr: int = _SR) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        stderr = proc.stderr.decode("utf-8", errors="replace")[-400:]
        raise RuntimeError(f"ffmpeg falhou ao decodificar {path.name}: {stderr!r}")
    return np.frombuffer(proc.stdout, dtype=np.float32)


def _rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))) if audio.size else 0.0


def _zcr(audio: np.ndarray) -> float:
    if audio.size < 2:
        return 0.0
    signs = np.sign(audio)
    signs[signs == 0] = 1.0
    return float(np.mean(signs[:-1] != signs[1:]))


def _spectral_centroid(audio: np.ndarray, sr: int = _SR, win: int = 2048, hop: int = 512) -> float:
    if audio.size < win:
        return 0.0
    window = np.hanning(win)
    freqs = np.fft.rfftfreq(win, d=1.0 / sr)
    n_frames = 1 + (audio.size - win) // hop
    energies, centroids = [], []
    for i in range(n_frames):
        frame = audio[i * hop: i * hop + win] * window
        mag = np.abs(np.fft.rfft(frame))
        e = float(mag.sum())
        if e > 1e-9:
            centroids.append(float((freqs * mag).sum() / e))
            energies.append(e)
    if not centroids:
        return 0.0
    c, e = np.array(centroids), np.array(energies)
    return float((c * e).sum() / e.sum())


def _onset_tempo_proxy(audio: np.ndarray, sr: int = _SR, frame: int = 1024, hop: int = 512) -> float:
    n_frames = 1 + (audio.size - frame) // hop if audio.size >= frame else 0
    if n_frames < 4:
        return 0.0
    rms_frames = np.array([_rms(audio[i * hop: i * hop + frame]) for i in range(n_frames)])
    onset = np.diff(rms_frames)
    onset[onset < 0] = 0.0
    onset = onset - onset.mean()
    ac = np.correlate(onset, onset, mode="full")[len(onset) - 1:]
    if ac[0] <= 1e-12:
        return 0.0
    ac = ac / ac[0]
    frame_rate = sr / hop
    min_lag = max(1, int(frame_rate * 60 / 180))
    max_lag = min(len(ac) - 1, int(frame_rate * 60 / 60))
    if max_lag <= min_lag:
        return 0.0
    return float(np.max(ac[min_lag:max_lag]))


def extract_features(path: Path) -> dict:
    audio = _decode_mono(path)
    return {
        "rms": _rms(audio),
        "zcr": _zcr(audio),
        "centroid": _spectral_centroid(audio),
        "tempo": _onset_tempo_proxy(audio),
    }


# ---------------------------------------------------------------------------
# Stats do corpus + bucket
# ---------------------------------------------------------------------------

def _zscore(value: float, mean: float, std: float) -> float:
    return (value - mean) / std if std > 1e-9 else 0.0


def combined_score(feat: dict, stats: dict) -> float:
    return sum(
        _WEIGHTS[k] * _zscore(feat[k], stats["features"][k]["mean"], stats["features"][k]["std"])
        for k in _WEIGHTS
    )


def compute_stats(features_by_file: dict) -> dict:
    feature_stats = {}
    for k in _WEIGHTS:
        values = np.array([f[k] for f in features_by_file.values()])
        feature_stats[k] = {"mean": float(values.mean()), "std": float(values.std()) or 1.0}
    prelim = {"features": feature_stats}
    combined = np.array([combined_score(f, prelim) for f in features_by_file.values()])
    low, high = np.percentile(combined, [33.33, 66.67])
    return {
        "schema_version": 1,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_tracks": len(features_by_file),
        "features": feature_stats,
        "weights": dict(_WEIGHTS),
        "score_thresholds": {"low": float(low), "high": float(high)},
    }


def bucket(score: float, stats: dict) -> str:
    t = stats["score_thresholds"]
    if score >= t["high"]:
        return "agressiva"
    if score <= t["low"]:
        return "calma"
    return "neutra"


def load_stats() -> dict | None:
    if not _STATS_PATH.exists():
        return None
    return json.loads(_STATS_PATH.read_text(encoding="utf-8"))


def save_stats(stats: dict) -> None:
    tmp = _STATS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _STATS_PATH)


# ---------------------------------------------------------------------------
# Relatorio
# ---------------------------------------------------------------------------

def write_report(mode: str, features_by_file: dict, scores: dict, moods: dict,
                  stats: dict, errors: dict, report_path: Path) -> None:
    lines = [
        f"# Classificacao de musica ({mode})",
        "",
        f"- Gerado em: {datetime.now(timezone.utc).isoformat()}",
        f"- Faixas no corpus desta run: {len(features_by_file)}",
        "",
    ]
    for mood in _MOODS:
        names = sorted((n for n, m in moods.items() if m == mood), key=lambda n: -scores[n])
        lines.append(f"## {mood} ({len(names)} faixas)")
        lines.append("")
        for name in names:
            f = features_by_file[name]
            lines.append(
                f"- `{name}` — score={scores[name]:.3f}, rms={f['rms']:.4f}, "
                f"zcr={f['zcr']:.4f}, centroide={f['centroid']:.0f}Hz, tempo={f['tempo']:.3f}"
            )
        lines.append("")
    if errors:
        lines.append("## Erros")
        lines.append("")
        for name, err in errors.items():
            lines.append(f"- `{name}`: {err}")
        lines.append("")
    lines.append("## Estatisticas de referencia em uso")
    lines.append("")
    lines.append(f"```json\n{json.dumps(stats, ensure_ascii=False, indent=1)}\n```")
    report_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _unsorted_files() -> list[Path]:
    if not MUSIC_ROOT.is_dir():
        return []
    return sorted(
        p for p in MUSIC_ROOT.iterdir()
        if p.is_file() and p.suffix.lower() in MUSIC_EXTS
    )


def _all_classified_files() -> list[Path]:
    files = []
    for mood in _MOODS:
        d = MUSIC_ROOT / mood
        if d.is_dir():
            files.extend(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in MUSIC_EXTS)
    return files


def main() -> None:
    ap = argparse.ArgumentParser(description="Classifica faixas de assets/music/ por clima (mood)")
    ap.add_argument("--dry-run", action="store_true", help="so mostra o resultado, nao move nada")
    ap.add_argument("--force", action="store_true",
                     help="recomputa as estatisticas de referencia com TODAS as faixas e reclassifica todo mundo")
    ap.add_argument("--report", default=None, help="caminho do relatorio (default: assets/music/_classify_report.md)")
    args = ap.parse_args()

    report_path = Path(args.report) if args.report else _REPORT_PATH

    if not MUSIC_ROOT.is_dir():
        fail(f"pasta nao encontrada: {MUSIC_ROOT}")

    targets = _all_classified_files() + _unsorted_files() if args.force else _unsorted_files()
    if not targets:
        emit(True, skipped=True, reason="nenhum arquivo novo em assets/music/")
        return

    source_path: dict[str, Path] = {p.name: p for p in targets}
    features_by_file: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for path in targets:
        try:
            features_by_file[path.name] = extract_features(path)
        except Exception as exc:  # decode/formato invalido -- nunca aborta o lote
            errors[path.name] = str(exc)

    if not features_by_file:
        fail("nenhuma faixa pode ser decodificada", errors=errors)

    if args.force:
        stats = compute_stats(features_by_file)
    else:
        stats = load_stats()
        if stats is None:
            if len(features_by_file) < _MIN_CORPUS_FOR_STATS:
                stats = None  # corpus pequeno demais: tudo neutra, nao grava stats ainda
            else:
                stats = compute_stats(features_by_file)

    scores: dict[str, float] = {}
    moods: dict[str, str] = {}
    for name, feat in features_by_file.items():
        if stats is None:
            scores[name] = 0.0
            moods[name] = "neutra"
        else:
            scores[name] = combined_score(feat, stats)
            moods[name] = bucket(scores[name], stats)

    moved = []
    if not args.dry_run:
        for name, mood in moods.items():
            src = source_path[name]
            dest_dir = MUSIC_ROOT / mood
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / name
            if src.resolve() != dest.resolve():
                src.rename(dest)
                moved.append(name)
        if stats is not None:
            save_stats(stats)

    if stats is not None:
        write_report(
            mode="force" if args.force else ("dry-run" if args.dry_run else "incremental"),
            features_by_file=features_by_file, scores=scores, moods=moods,
            stats=stats, errors=errors, report_path=report_path,
        )

    counts = {mood: sum(1 for m in moods.values() if m == mood) for mood in _MOODS}
    emit(True, dry_run=args.dry_run, force=args.force,
         classified=len(features_by_file), moved=len(moved),
         counts=counts, errors=len(errors), report=str(report_path))


if __name__ == "__main__":
    main()

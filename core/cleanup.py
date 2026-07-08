"""Limpeza de disco: apaga a pasta de um video quando nada mais sera postado.

Regra (adicionada 2026-07-08): um video esta "pronto para limpar" quando tem
pelo menos 1 clip `published` E nenhum clip em estado pendente — ou seja, todos
os clips estao em estado terminal (`published`/`failed`/`rejected`). Um clip
quebrado (`failed`/`rejected`) NAO trava a limpeza; mas um video sem NENHUM clip
publicado nunca e apagado (nunca postou -> pode ser re-render/re-download).

Antes de apagar, o `clips.json` e arquivado em
`video-output/_archive/<video_id>.clips.json` (KB) para preservar o registro do
que foi publicado (remote_id, url, published_at). A midia pesada (mp4, source.mp4,
thumbnails — os GB) e apagada com o resto da pasta.

Idempotente e best-effort: e chamado ao final do `publish_next.py` e nunca deve
derrubar o resultado do publish (o chamador envolve em try/except).
"""
import shutil
from pathlib import Path

from core import contracts, paths

# Estados em que o clip nao produzira mais upload (nao ha o que esperar).
TERMINAL_STATUSES = ("published", "failed", "rejected")
# Subpasta de video-output onde os clips.json de videos ja apagados sobrevivem.
ARCHIVE_DIRNAME = "_archive"


def video_complete(plan: dict) -> bool:
    """True se o video pode ser limpo: >=1 clip published e nenhum pendente.

    Um video sem clips, ou sem nenhum published (ex.: todos failed), retorna
    False — nao apagamos algo que nunca postou (pode querer re-render)."""
    clips = plan.get("clips") or []
    if not clips:
        return False
    statuses = [c.get("status") for c in clips]
    if not any(s == "published" for s in statuses):
        return False
    return all(s in TERMINAL_STATUSES for s in statuses)


def dir_size(d: Path) -> int:
    """Soma dos bytes dos arquivos sob `d` (best-effort; ignora erros de I/O)."""
    total = 0
    if not d.exists():
        return 0
    for p in d.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            pass
    return total


def archive_dir() -> Path:
    return paths.OUTPUT_ROOT / ARCHIVE_DIRNAME


def archive_plan(video_id: str, plan: dict) -> Path:
    """Grava o clips.json em video-output/_archive/<video_id>.clips.json."""
    dest = archive_dir() / f"{video_id}.clips.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    contracts.save_plan(dest, plan)  # escrita atomica (tmp + os.replace)
    return dest


def purge_video(video_id: str, plan: dict | None = None) -> dict:
    """Arquiva o clips.json e apaga a pasta do video. NAO checa completude —
    use `cleanup_if_complete` para o gate. Retorna resumo do que foi feito."""
    wd = paths.workspace_dir(video_id)
    if plan is None:
        cf = paths.clips_path(video_id)
        if cf.exists():
            plan = contracts.load_plan(cf)
    archived = str(archive_plan(video_id, plan)) if plan is not None else None
    freed = dir_size(wd)
    if wd.exists():
        shutil.rmtree(wd)
    return {"video_id": video_id, "purged": True,
            "archived": archived, "freed_bytes": freed}


def cleanup_if_complete(video_id: str) -> dict | None:
    """Apaga a pasta do video se ele estiver completo (video_complete). Retorna
    o resumo do purge, ou None se ainda ha clips pendentes / nada publicado."""
    cf = paths.clips_path(video_id)
    if not cf.exists():
        return None
    plan = contracts.load_plan(cf)
    if not video_complete(plan):
        return None
    return purge_video(video_id, plan)

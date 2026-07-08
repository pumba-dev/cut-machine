"""Contrato central do pipeline: clips.json (video-output/<id>/clips.json).

Donos por campo — ninguem sobrescreve campo de outro dono:
- clip-scout (LLM): objeto do clip + campos de analise (start/end, hook_text, score...)
- copywriter (LLM): title, title_alts, description, tags
- render_clip.py: bloco render.*
- upload_clip.py: bloco publish.* (remote_id, url, published_at)
- humano/orquestrador: transicao approved/rejected
"""
import json
import os
from pathlib import Path

CLIP_FORMATS = ("short", "corte")

# Maquina de estados por clip. "queued" existe por causa da quota de upload diaria.
CLIP_STATUSES = (
    "planned", "approved", "rejected", "rendering", "rendered",
    "queued", "uploading", "published", "failed",
)

# Limites da API do YouTube + padrao editorial (references/padrao-copy.md).
TITLE_MAX = 100          # limite duro da API
TITLE_RECOMMENDED = 70   # acima disso: aviso (mobile trunca ~70); titulo = gancho caps
DESC_MAX_BYTES = 5000    # a API conta BYTES (UTF-8), nao chars
TAGS_BUDGET = 500        # soma; tag com espaco conta +2 (aspas)
MIN_TAGS, MAX_TAGS = 10, 15
# Espelho do bloco 1 de references/padrao-copy.md — manter em sincronia.
CTA_FIXA = ("🔥 Curtiu? Deixa o LIKE 👍, comenta o que achou 💬 "
            "e se INSCREVE no canal pra não perder os próximos cortes!")

FORMAT_RULES = {
    "short": {
        "min_duration_s": 15.0,
        "max_duration_s": 59.0,
        "resolution": "1080x1920",
        # sem crop: video 16:9 numa janela sobre moldura fixa (short_frame.py)
        "crop": "frame",
        "burn_captions": True,
        "border": False,
        # miniatura vertical (frame do clip + frases sobrepostas)
        "thumbnail_resolution": "1080x1920",
    },
    "corte": {
        # >=8 min habilita mid-roll ads / monetizacao no YouTube; alvo 8-15 min.
        "min_duration_s": 480.0,
        "max_duration_s": 900.0,
        "resolution": "1920x1080",
        "crop": "none",
        "burn_captions": False,
        # moldura de marca preto+amarelo com CTA de inscricao (branding.py)
        "border": True,
        # miniatura 16:9 (tamanho recomendado do YouTube)
        "thumbnail_resolution": "1280x720",
    },
}


def new_plan(video_id: str, source: dict) -> dict:
    """source: url, title, channel, duration_s, width, height, fps, language."""
    return {
        "schema_version": 1,
        "video_id": video_id,
        "source": source,
        "generated_at": None,
        "clips": [],
        "rejected_notable": [],
    }


def load_plan(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_plan(path: Path, plan: dict) -> None:
    path = Path(path)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def get_clip(plan: dict, clip_id: str) -> dict:
    for clip in plan["clips"]:
        if clip["id"] == clip_id:
            return clip
    raise LookupError(f"clip {clip_id} nao existe em clips.json")


def set_clip_status(clip: dict, status: str, error: str | None = None) -> dict:
    if status not in CLIP_STATUSES:
        raise ValueError(f"status invalido: {status}")
    if status == "failed" and not error:
        raise ValueError("status failed exige mensagem em error")
    clip["status"] = status
    clip["error"] = error
    return clip


def tags_budget_len(tags: list[str]) -> int:
    """Custo das tags na API do YouTube: +2 por tag com espaco (aspas)."""
    return sum(len(t) + (2 if " " in t else 0) for t in tags)


def _description_hashtags(description: str | None) -> list[str]:
    """Hashtags do ultimo bloco da description (bloco 4 do padrao-copy.md)."""
    blocks = [b.strip() for b in (description or "").split("\n\n") if b.strip()]
    if blocks:
        tokens = blocks[-1].split()
        if tokens and all(t.startswith("#") for t in tokens):
            return tokens
    return []


def clip_metadata(plan: dict, clip: dict) -> dict:
    """Metadados de postagem do clip, derivados de clips.json (fonte de verdade).

    Gravado em video-output/<video_id>/<clip_id>/metadata.json ao lado do mp4,
    para a publicacao manual (YouTube Studio etc.). Nunca editar a mao: e
    regenerado no render e no upload.
    """
    tags = [t for t in (clip.get("tags") or []) if isinstance(t, str) and t.strip()]
    src = plan.get("source", {})
    return {
        "clip_id": clip["id"],
        "video_id": plan.get("video_id"),
        "format": clip.get("format"),
        "status": clip.get("status"),
        "title": clip.get("title"),
        "title_alts": clip.get("title_alts") or [],
        "description": clip.get("description"),
        "tags": tags,
        "hashtags": _description_hashtags(clip.get("description"))
        or ["#" + t.replace(" ", "").replace("-", "") for t in tags[:5]],
        "hook_text": clip.get("hook_text"),
        "thumbnail_ts": clip.get("thumbnail_ts"),
        "thumbnail_text": clip.get("thumbnail_text") or {},
        "score": clip.get("score"),
        "start": clip.get("start"),
        "end": clip.get("end"),
        "duration_s": clip.get("duration_s"),
        "source": {
            "url": src.get("url"),
            "title": src.get("title"),
            "channel": src.get("channel"),
        },
        "render": clip.get("render") or {},
        "publish": clip.get("publish") or {},
    }


def save_clip_metadata(path: Path, plan: dict, clip: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(clip_metadata(plan, clip), ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _copy_errors(cid: str, clip: dict) -> list[str]:
    """Erros duros de copy: o que quebra a API ou copy incompleta.

    Gate em title-not-null: plano recem-saido do clip-scout tem copy null.
    Tolerante a tipo errado (o copywriter e um LLM escrevendo JSON):
    reporta erro, nunca lanca.
    """
    title = clip.get("title")
    if title is None:
        return []
    if not isinstance(title, str):
        return [f"{cid}: title nao e string ({type(title).__name__})"]

    errors: list[str] = []
    if not title.strip():
        errors.append(f"{cid}: title vazio")
    if len(title) > TITLE_MAX:
        errors.append(f"{cid}: title com {len(title)} chars (max {TITLE_MAX})")
    if "<" in title or ">" in title:
        errors.append(f"{cid}: title contem < ou > (API rejeita)")

    desc = clip.get("description")
    if desc is not None and not isinstance(desc, str):
        errors.append(f"{cid}: description nao e string ({type(desc).__name__})")
    else:
        desc = desc or ""
        if not desc.strip():
            errors.append(f"{cid}: title preenchido mas description vazia")
        elif len(desc.encode("utf-8")) > DESC_MAX_BYTES:
            errors.append(
                f"{cid}: description com {len(desc.encode('utf-8'))} bytes "
                f"(max {DESC_MAX_BYTES})")
        if "<" in desc or ">" in desc:
            errors.append(f"{cid}: description contem < ou > (API rejeita)")

    raw_tags = clip.get("tags")
    if raw_tags is not None and not isinstance(raw_tags, list):
        errors.append(f"{cid}: tags nao e lista ({type(raw_tags).__name__})")
    else:
        tags = [t for t in (raw_tags or [])
                if isinstance(t, str) and t.strip()]
        if not tags:
            errors.append(f"{cid}: title preenchido mas tags vazias")
        elif tags_budget_len(tags) > TAGS_BUDGET:
            errors.append(
                f"{cid}: tags somam {tags_budget_len(tags)} chars "
                f"(max {TAGS_BUDGET}, +2 por tag com espaco)")
    return errors


def validate_plan(plan: dict) -> list[str]:
    """Retorna lista de erros (vazia = valido). Nao lanca excecao."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    src_duration = float(plan.get("source", {}).get("duration_s") or 0)

    for clip in plan.get("clips", []):
        cid = clip.get("id", "<sem id>")
        if cid in seen_ids:
            errors.append(f"{cid}: id duplicado")
        seen_ids.add(cid)

        # Copy antes dos checks estruturais: erro de format/start-end nao pode
        # esconder erro de copy do mesmo clip (o retry do copywriter e 1 so).
        errors.extend(_copy_errors(cid, clip))

        fmt = clip.get("format")
        if fmt not in CLIP_FORMATS:
            errors.append(f"{cid}: format invalido ({fmt})")
            continue
        rules = FORMAT_RULES[fmt]

        start, end = clip.get("start"), clip.get("end")
        if start is None or end is None or start >= end:
            errors.append(f"{cid}: start/end invalidos ({start}..{end})")
            continue
        duration = end - start
        if abs(duration - clip.get("duration_s", duration)) > 0.5:
            errors.append(f"{cid}: duration_s nao bate com end-start")
        if not (rules["min_duration_s"] <= duration <= rules["max_duration_s"]):
            errors.append(
                f"{cid}: duracao {duration:.1f}s fora dos limites do formato "
                f"{fmt} ({rules['min_duration_s']}-{rules['max_duration_s']}s)")
        if src_duration and end > src_duration + 1:
            errors.append(f"{cid}: end ({end}) alem da duracao do video fonte")

        if clip.get("status") not in CLIP_STATUSES:
            errors.append(f"{cid}: status invalido ({clip.get('status')})")

        score = clip.get("score")
        if score is None or not (0 <= score <= 100):
            errors.append(f"{cid}: score fora de 0-100 ({score})")

    return errors


def _title_problems(title: str, fmt: str) -> list[str]:
    """Adere ao formato de titulo (references/padrao-copy.md):
    '<TEXTO CAIXA ALTA> | #tag #tag #tag'. Retorna lista de problemas (vazia=ok)."""
    if " | " not in title:
        return ["sem ' | ' (formato: TEXTO | #tag #tag #tag)"]
    text_part, tags_part = title.rsplit(" | ", 1)
    toks = tags_part.split()
    tags = [w for w in toks if w.startswith("#")]
    low = [t.lower() for t in tags]
    probs: list[str] = []
    if text_part.upper() != text_part:
        probs.append("texto nao esta em CAIXA ALTA")
    if "#" in text_part:
        probs.append("hashtag antes do ' | '")
    if len(tags) != 3 or len(toks) != 3:
        probs.append(f"precisa de exatamente 3 hashtags apos ' | ' (tem {len(tags)})")
    if fmt == "short" and "#shorts" not in low:
        probs.append("short sem #shorts no titulo")
    if fmt == "corte" and "#shorts" in low:
        probs.append("corte nao leva #shorts")
    return probs


def lint_copy(plan: dict) -> list[str]:
    """Avisos de aderencia ao padrao editorial (references/padrao-copy.md).

    Nao bloqueiam nada: o humano decide no checkpoint pos-copy. Clips sem
    copy (title null) sao pulados.
    """
    warnings: list[str] = []
    src_url = plan.get("source", {}).get("url") or ""

    for clip in plan.get("clips", []):
        cid = clip.get("id", "<sem id>")
        title = clip.get("title")
        if title is None or not isinstance(title, str):
            continue  # sem copy, ou tipo errado (validate_plan ja reporta)
        fmt = clip.get("format")

        # Titulo (revisado 2026-07-08 v2): "<TEXTO CAIXA ALTA> | #tag #tag #tag".
        # Sem categoria; 3 hashtags (short: #shorts + 2; corte: 3) das
        # default_hashtags da conta. Limite duro de 100 chars: validate_plan (erro).
        for p in _title_problems(title, fmt):
            warnings.append(f"{cid}: title {p}")

        # Pool de variantes para teste A/B (title_alts) - MESMO formato do title.
        alts = clip.get("title_alts")
        if isinstance(alts, list):
            clean = [a for a in alts if isinstance(a, str) and a.strip()]
            if len(clean) < 3:
                warnings.append(
                    f"{cid}: title_alts com {len(clean)} variantes (pool A/B recomenda 6-10)")
            if any(_title_problems(a, fmt) for a in clean):
                warnings.append(f"{cid}: alguma variante fora do formato 'TEXTO | #tag #tag #tag'")
            pool = [t.lower() for t in [title] + clean]
            if len(set(pool)) != len(pool):
                warnings.append(f"{cid}: variantes de title duplicadas (pool A/B deve ser distinto)")

        desc = clip.get("description")
        desc = desc if isinstance(desc, str) else ""
        blocks = [b.strip() for b in desc.split("\n\n") if b.strip()]
        if len(blocks) < 4:
            warnings.append(f"{cid}: description com {len(blocks)} blocos (padrao: 4)")
        if not blocks or blocks[0] != CTA_FIXA:
            warnings.append(f"{cid}: bloco 1 da description nao e a CTA fixa")
        if src_url and (len(blocks) < 2 or src_url not in blocks[1]):
            warnings.append(
                f"{cid}: bloco 2 da description sem o link do video original")

        hs = [h.lower() for h in _description_hashtags(desc)]
        fmt = clip.get("format")
        if hs:
            if fmt == "short" and "#shorts" not in hs:
                warnings.append(f"{cid}: bloco de hashtags de short sem #shorts")
            if fmt == "corte" and "#shorts" in hs:
                warnings.append(f"{cid}: bloco de hashtags de corte com #shorts")
            if not (3 <= len(hs) <= 5):
                warnings.append(
                    f"{cid}: {len(hs)} hashtags na description (padrao: 3-5)")
        elif len(blocks) >= 4:
            warnings.append(f"{cid}: ultimo bloco da description nao e so hashtags")

        raw_tags = clip.get("tags")
        tags = [t for t in (raw_tags or []) if isinstance(t, str) and t.strip()] \
            if isinstance(raw_tags, list) else []
        if len(tags) < MIN_TAGS:
            warnings.append(f"{cid}: {len(tags)} tags (minimo {MIN_TAGS})")
        elif len(tags) > MAX_TAGS:
            warnings.append(f"{cid}: {len(tags)} tags (maximo recomendado {MAX_TAGS})")

        warnings.extend(_thumbnail_warnings(cid, clip))

    return warnings


def _thumbnail_warnings(cid: str, clip: dict) -> list[str]:
    """Avisos leves de thumbnail_text (copywriter). Nao bloqueiam: a geracao
    da miniatura tem fallback para hook_text/title quando falta."""
    warnings: list[str] = []
    tt = clip.get("thumbnail_text")
    if tt is None:
        warnings.append(f"{cid}: sem thumbnail_text (miniatura usara fallback)")
        return warnings
    if not isinstance(tt, dict):
        warnings.append(f"{cid}: thumbnail_text nao e objeto ({type(tt).__name__})")
        return warnings
    impact = tt.get("impact")
    if not isinstance(impact, str) or not impact.strip():
        warnings.append(f"{cid}: thumbnail_text.impact vazio")
    elif len(impact) > 40:
        warnings.append(
            f"{cid}: thumbnail_text.impact com {len(impact)} chars (recomendado <= 40)")
    hooks = tt.get("hooks")
    if not isinstance(hooks, list):
        warnings.append(f"{cid}: thumbnail_text.hooks nao e lista")
    else:
        clean = [h for h in hooks if isinstance(h, str) and h.strip()]
        if not (2 <= len(clean) <= 3):
            warnings.append(
                f"{cid}: {len(clean)} frases de gancho na thumbnail (padrao 2-3)")
        for h in clean:
            if len(h) > 30:
                warnings.append(
                    f"{cid}: gancho de thumbnail '{h[:20]}...' com {len(h)} chars "
                    "(recomendado <= 30)")
            if not (h.rstrip().endswith("!") or h.rstrip().endswith("?")):
                warnings.append(
                    f"{cid}: gancho '{h[:20]}...' sem ! nem ? "
                    "(padrao: afirmacao com ! ou pergunta aberta com ?)")
    return warnings

---
name: publicar
description: Publica no YouTube os clips renderizados de um video, com checkpoint de quota antes do upload. Aceita um clip especifico ou todos; reprocessa clips queued de dias anteriores. Uso - /publicar <video_id> [clip_id] [--conta <id>]
---

# /publicar <video_id> [clip_id] [--conta <id>]

Executa a fase `publish` do pipeline. Uploads saem **`public` por padrao** (teste 2026-07-08 confirmou que este projeto aceita publico + `thumbnails.set`; ver `references/youtube-api.md`). `privacy` por clip em `clips.json` pode ser `private`/`unlisted` para excecoes. Publicar e irreversivel/externo: confirme antes de subir em lote.

## Pre-condicoes

1. Leia `video-output/<video_id>/state.json` e `clips.json`. Candidatos a upload: clips com `status: "rendered"` **e tambem** clips `status: "queued"` (ficaram aguardando quota em execucao anterior — reprocesse-os, priorizando por `score` decrescente).
2. Se nao ha candidatos, informe e sugira `/renderizar <video_id>` ou `/status <video_id>`.
3. **A conta vem da `publish.account` dos clips candidatos** (o clip-scout gravou; e a fonte da verdade — nunca use default). Se o usuario passou `--conta <id>`, confirme que **bate** com a `publish.account` dos clips; se divergir, PARE e alerte (risco de publicar no canal errado). Confirme que o `secrets/<plataforma>/<conta-dos-clips>/token.json` existe; se nao, oriente `python scripts/auth.py --platform youtube --account <id>`. Nunca leia o conteudo de arquivos em `secrets/`.

## 1. CHECKPOINT de quota (obrigatorio)

Antes de qualquer upload, apresente ao usuario e **aguarde confirmacao explicita**:

- N clips a publicar contra o limite de **uploads = 100/dia** (contador separado das 10k queries/dia; o upload não drena as 10k a 1600/un — ver `references/youtube-api.md`).
- `daily_upload_limit` da conta (em `config/accounts.json`): uploads alem desse limite hoje ficarao `queued` por score, para publicar amanha.
- Lista dos clips: id | formato | score | titulo.

Sem confirmacao, nao publique nada.

## 2. Upload

**Um clip especifico** (rode direto, sem subagente):

```
python scripts/upload_clip.py --video-id <video_id> --clip <clip_id>
```

Sem `--account`, o `upload_clip.py` usa a `publish.account` do proprio clip (o correto — evita subir no canal errado). So passe `--account` se precisar forcar E ja tiver confirmado que bate com o clip.

**Todos os candidatos**: spawne o subagente `publisher` via Task com o caminho do video (`video-output/<video_id>`). O publisher ja roda `upload_clip.py` sem `--account` (usa a `publish.account` de cada clip). Ele itera os clips por score, roda `upload_clip.py` um a um e registra `publish.remote_id`, `publish.url`, `publish.published_at` e `status: "published"` em `clips.json` (o `metadata.json` de cada clip em `video-output/<video_id>/<clip_id>/` e regenerado pelo proprio `upload_clip.py`).

Contrato: ultima linha do stdout de cada script e JSON `{"ok": ...}`. Clip ja `published` nao e refeito (`{"ok": true, "skipped": true}`). Erro 403 `quotaExceeded`: pare os uploads imediatamente, marque/deixe os restantes como `queued` e reporte quantos sobraram — nao tente de novo hoje.

## 3. Relatorio final

- Publicados: id | titulo | URL | privacidade retornada pela API. Na 1a publicacao, confirme que o video permanece **public** (abra a URL).
- `queued` aguardando quota (re-rodar `/publicar <video_id>` amanha).
- Falhas com motivo (`clips.json.clips[].error`, `state.json.last_error`).
- Quota consumida estimada (uploads x 1600).

---
name: produzir
description: Pipeline completo de cortes virais - baixa o video, transcreve, planeja cortes (clip-scout), escreve copy (copywriter), checkpoint humano, renderiza, valida (qa-reviewer) e publica (publisher). Retoma automaticamente de onde parou. Uso - /produzir <url> [--sem-upload] [--conta <id>]
---

# /produzir <url> [--sem-upload] [--conta <id>]

Voce e o orquestrador: delega analise criativa a subagentes (Task) e execucao determinista a `scripts/`. Regras permanentes:

- A **ultima linha do stdout** de todo script e uma linha JSON `{"ok": ...}`. Leia-a para decidir o proximo passo. `{"ok": true, "skipped": true}` = etapa ja estava feita.
- **Nunca refaca etapa `done`** — os scripts ja checam `state.json` e pulam sozinhos.
- Se um script falhar (`ok: false` ou exit != 0): leia stderr e `state.json.last_error`, tente 1 correcao obvia (ex.: re-rodar), senao pare e reporte ao usuario.
- Ordem das etapas em `state.json.stages`: `download → transcribe → faces → plan → copy → render → qa → publish` (`faces` é opt-in; o script se auto-pula se a conta não usa).
- **`--conta <id>` e OBRIGATORIA** (define o brand do render, o nicho da copy e o canal do upload). Se o usuario NAO passar, **PARE e pergunte qual canal** — nunca assuma o default. Canais atuais em `config/accounts.json` (e na lista do `CLAUDE.md` §8); o id tem que existir la. Repasse a conta ao clip-scout, ao copywriter e ao publisher.

## 1. Retomada

1. Extraia o `video_id` da URL (padroes: `watch?v=<id>`, `youtu.be/<id>`, `/shorts/<id>`, `/live/<id>` — id de 11 chars).
2. Se `video-output/<video_id>/state.json` **existe**: leia-o, identifique a primeira etapa nao-`done` e **avise o usuario** ("retomando <video_id> a partir da etapa X"). Pule direto para o passo correspondente abaixo. Etapa `running` orfa (processo morreu): re-rode o script — ele e idempotente e verifica os artefatos.
3. Se nao existe: pipeline completo desde o inicio.

## 2. Download, transcricao e rostos

```
python scripts/download.py --url <URL>
python scripts/transcribe.py --video-id <video_id>
python scripts/analyze_faces.py --video-id <video_id> [--account <conta>]
```

Sequencial (transcribe depende de `source.mp4`). Nao passe `--model/--device/--compute` a menos que o usuario peca — os defaults ja sao os corretos para a GPU local.

`analyze_faces.py` e a fase **`faces`** (opt-in): detecta rosto/emocao no source (CPU, minutos) e escreve `faces.json`. Sempre pode ser chamado — se a conta nao tem `thumbnail.face_aware`, ele retorna `{"skipped": true}` (no-op); se a deteccao falhar, degrada (`degraded: true`) e o pipeline segue com a thumb ASS local. Nao bloqueia nada.

## 3. Planejamento (clip-scout)

Spawne o subagente `clip-scout` via Task, informando no prompt: o workspace (`video-output/<video_id>/`) e a conta de publicacao (a do `--conta`, **obrigatoria — sem default**). Ele le `transcript.compact.json` + `references/` e escreve os candidatos em `clips.json` com `status: "planned"` (e grava a conta em `publish.account`).

**Regra inviolavel**: se o clip-scout voltar com **0 clips de score >= 60, isso e um resultado valido**. Nao invente cortes, nao rebaixe criterios, nao re-rode "para tentar de novo". Encerre graciosamente com o relatorio final explicando que o video nao rendeu cortes acima do corte de qualidade.

Apos validar o retorno (clips.json existe e respeita FORMAT_RULES), marque a etapa como concluida — subagentes nao mexem em `state.json`: `python -c` com `core.state` (load, `set_stage(st, "plan", "done")`, save).

## 4. Copy (copywriter)

Spawne o subagente `copywriter` via Task com o mesmo workspace e o `account_id` da conta alvo (o do `--conta`; **sem default**). Ele preenche `title`, `title_alts`, `description`, `tags` dos clips `planned` em `clips.json`, seguindo `references/padrao-copy.md` (universal) **+ `references/copy/<copy_profile>.md`** (nicho da conta) e a identidade do canal (`channel_name`, `niche`, `default_hashtags`).

Depois, valide a copy:

```
python scripts/validate_plan.py --video-id <video_id>
```

A ultima linha e um JSON `{ok, errors, warnings, clips_com_copy}`. Se houver `errors`: re-spawne o copywriter **1 vez** com os erros no prompt e re-valide (e a regra de max 1 retry); se persistirem, pare e reporte. `warnings` nao bloqueiam — guarde-os para listar no checkpoint. Por fim, marque `copy` como `done` em `state.json` (mesmo procedimento da etapa plan).

### 4.1 Miniatura inteligente (opcional — thumbnail-director)

**Quando rodar:** a conta tem `thumbnail.face_aware` e `video-output/<video_id>/faces.json` existe sem `"degraded": true`. É **opcional** — melhora a escolha de frame/rosto/layout da thumb. Se pular, o render monta a thumb do mesmo jeito (composite local), só que escolhendo o frame/rosto no automático (`thumbnail_ts` + host do `faces.json`).

Spawne o subagente `thumbnail-director` via Task com o workspace + `account_id`. Ele lê `faces.json` + `thumbnail_text` e escreve `thumbnail_plan` (frame_ts, rosto/host, layout) nos clips `planned`. Sem etapa em `state.json` — o artefato durável é o `thumbnail_plan` em `clips.json` (idempotente por presença). O render (passo 6) usa `frame_ts`/`identity`/`layout` na **thumb compositada local**.

## 5. CHECKPOINT humano 1 — aprovacao dos cortes

Leia `clips.json` e apresente a tabela:

```
id | formato | start-end | dur | score | chars | titulo
```

`chars` = numero de caracteres do `title` (alvo <= 85, duro 100 — ver `references/padrao-copy.md`); mostre o **titulo completo**, sem truncar. Logo abaixo da tabela, liste os `warnings` do `validate_plan.py` para o usuario decidir se ajusta algo.

Pergunte ao usuario o que aprovar (via AskUserQuestion se disponivel, senao texto livre): aprovar todos, rejeitar alguns por id, ou editar titulos. Aplique a resposta editando `clips.json`: clips aceitos -> `status: "approved"`, recusados -> `status: "rejected"` (transicao approved/rejected e do humano/orquestrador — nao mexa em campos de outros donos). Se o usuario nao aprovar nenhum, encerre com relatorio.

## 6. Render

```
python scripts/render_clip.py --video-id <video_id> --all-approved
```

Uma chamada so; o script renderiza os aprovados **sequencialmente** (GPU de 6GB nao comporta paralelo). Clips ja `rendered` sao pulados. Falha em um clip nao invalida os demais — confira o JSON final para saber quantos renderizaram.

## 7. QA (qa-reviewer)

Spawne o subagente `qa-reviewer` via Task com o workspace. Ele valida cada `<clip_id>/<clip_id>.mp4` com ffprobe (resolucao, duracao, audio) e marca `failed` + `error` no que reprovar. Depois, marque `qa` como `done` em `state.json` (subagentes nao mexem em `state.json`).

## 8. CHECKPOINT humano 2 — quota e publicacao

Pule esta secao se `--sem-upload` (informe que os clips estao renderizados e que `/publicar <video_id>` publica depois).

1. Conte N = clips `rendered` aprovados no QA. Leia `daily_upload_limit` da conta em `config/accounts.json`.
2. Apresente ao usuario: "Publicar N clips (limite de **uploads = 100/dia**, contador separado das 10k queries/dia; limite da conta: <daily_upload_limit>/dia). Clips acima do limite ficarao `queued` por score. Confirmar?"
3. So apos confirmacao explicita, spawne o subagente `publisher` via Task com workspace + conta. Ele roda `scripts/upload_clip.py` clip a clip e registra `publish.remote_id/url/published_at`. Uploads saem `public` por padrao (revisado 2026-07-08; `private`/`unlisted` por clip para excecoes).

## 9. Relatorio final

Sempre encerre com um relatorio, mesmo em encerramento gracioso:

- Clips publicados: id, titulo, URL (lembrando que estao **private**).
- Clips `queued` aguardando quota (publicar amanha com `/publicar <video_id>`).
- Clips `failed`/`rejected` e motivo.
- Quota consumida estimada (uploads x 1600).

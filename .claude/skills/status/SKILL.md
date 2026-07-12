---
name: status
description: Mostra o estado consolidado do pipeline - etapa atual de cada video em video-output/, clips por status e alertas (token OAuth perto de expirar, clips queued, erros pendentes). Somente leitura. Uso - /status [video_id]
---

# /status [video_id]

Skill **somente leitura**: nao rode scripts de pipeline, nao altere `state.json` nem `clips.json`.

## 1. Coleta

- Com `video_id`: leia apenas `video-output/<video_id>/state.json` e `clips.json`.
- Sem argumento: liste os diretorios de `video-output/` e leia o `state.json` + `clips.json` de cada um (ignore diretorios sem `state.json`).

Etapa atual de um video = primeira etapa nao-`done` na ordem `download → transcribe → faces → plan → copy → render → qa → publish` (se todas `done`: "concluido"). `faces` e opt-in: pode aparecer `done` com `skipped: true` (conta sem face-aware) — trate como concluida.

## 2. Tabela consolidada

```
video | titulo | shorts publicados | shorts pendentes | cortes publicados | cortes pendentes | na fila pra publicar
```

Agregue `clips.json.clips[].status` **separado por `format`** (`short` vs `corte`) em dois baldes:
- **publicados** = `status == "published"` (numero).
- **pendentes** = qualquer outro status (`planned/approved/rendering/rendered/queued/uploading`, tambem `failed`/`rejected` — mas marque esses com sufixo, ex. `c3(rejected)`) — numero **+ lista dos ids** (sufixo curto, sem prefixo do video e sem zero a esquerda: `GaD5LydtZ6g-c02` -> `c2`, `-s01` -> `s1`). Formato da celula: `2 (c2, c3)`. Zero pendentes: `0`.

**Na fila pra publicar** (coluna extra — o balde de pendentes acima nao diz quais ja podem sair, so quantos faltam em qualquer etapa): short+corte somados com `status == "rendered"` **e** `qa.status == "pass"` (o que `publish_next.py` de fato pega, ver CLAUDE.md). Numero + ids (mesmo formato do balde de pendentes: `2 (c2, s3)`). Zero: `0`.

Video sem `clips.json` ainda: `-` nas cinco colunas. Video arquivado (pasta limpa, so existe `video-output/_archive/<video_id>.clips.json`): inclua na tabela normalmente, marcando o nome do video com `(arquivado)` — pendentes e fila ali deveria ser sempre `0` (cleanup so roda com tudo terminal).

Com `video_id` unico, mostre tambem o detalhe clip a clip: id | formato | status | score | titulo | url (quando publicado).

## 3. Alertas

Verifique e liste ao final (apenas os que se aplicarem):

1. **Token OAuth envelhecendo**: para cada conta em `config/accounts.json`, cheque a data de modificacao de `<credentials_dir>/token.json` (campo `credentials_dir` da conta, ex.: `secrets/youtube/principal`) (use `Get-Item ... | Select LastWriteTime` ou equivalente — **nunca leia o conteudo** de arquivos em `secrets/`). Se tiver **mais de 6 dias**, alerte: app OAuth em modo Testing expira o refresh token em 7 dias — rodar `python scripts/auth.py --platform youtube --account <id>` para renovar. Se `token.json` nao existe, alerte que a conta nunca autenticou.
2. **Clips `queued`**: ha clips aguardando quota de upload — sugerir `/publicar <video_id>` (limite diario por conta em `config/accounts.json`).
3. **`last_error` preenchido** em algum `state.json`: mostre etapa, clip e mensagem, e sugira o skill que retoma aquela fase (`/produzir` retoma o pipeline inteiro do ponto onde parou; `/renderizar` e `/publicar` retomam as fases finais).

## 4. Encerramento

Se `video-output/` esta vazio, diga que nao ha videos em andamento e aponte `/produzir <url>` para comecar.

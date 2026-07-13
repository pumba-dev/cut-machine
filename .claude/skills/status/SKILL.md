---
name: status
description: Mostra o estado consolidado do pipeline, separado por canal/conta - etapa atual de cada video em video-output/, clips por status e alertas (token OAuth perto de expirar, clips queued, erros pendentes). Somente leitura. Uso - /status [video_id]
---

# /status [video_id]

Skill **somente leitura**: nao rode scripts de pipeline, nao altere `state.json` nem `clips.json`.

## 1. Coleta

- Com `video_id`: leia apenas `video-output/<video_id>/state.json` e `clips.json`.
- Sem argumento: liste os diretorios de `video-output/` e leia o `state.json` + `clips.json` de cada um (ignore diretorios sem `state.json`).

Etapa atual de um video = primeira etapa nao-`done` na ordem `download → transcribe → faces → plan → copy → render → qa → publish` (se todas `done`: "concluido"). `faces` e opt-in: pode aparecer `done` com `skipped: true` (conta sem face-aware) — trate como concluida.

**Conta do video**: leia `clips.json.clips[0].publish.account` (todo clip de um mesmo video pertence a mesma conta — sao produzidos juntos por um unico `account_id` passado aos subagentes). Clip legado sem `publish.account`: cai na conta `default: true` de `config/accounts.json` (mesma regra do `publish_next.py`). Video sem nenhum clip ainda (`clips.json` ausente ou vazio): sem conta conhecida ainda — agrupe numa secao `Sem conta definida ainda` no fim, separada das contas.

## 2. Tabela consolidada — SEPARADA POR CANAL

Uma tabela por conta (uma secao com titulo `### <channel_name> (<account_id>)`, na ordem de `config/accounts.json`), cada uma so com os videos daquela conta. Nao junte contas na mesma tabela — o objetivo e o humano bater o olho no canal que importa sem filtrar linha por linha.

```
video | titulo | shorts publicados | shorts pendentes | cortes publicados | cortes pendentes | na fila pra publicar
```

Agregue `clips.json.clips[].status` **separado por `format`** (`short` vs `corte`) em dois baldes:
- **publicados** = `status == "published"` (numero).
- **pendentes** = qualquer outro status (`planned/approved/rendering/rendered/queued/uploading`, tambem `failed`/`rejected` — mas marque esses com sufixo, ex. `c3(rejected)`) — numero **+ lista dos ids** (sufixo curto, sem prefixo do video e sem zero a esquerda: `GaD5LydtZ6g-c02` -> `c2`, `-s01` -> `s1`). Formato da celula: `2 (c2, c3)`. Zero pendentes: `0`.

**Na fila pra publicar** (coluna extra — o balde de pendentes acima nao diz quais ja podem sair, so quantos faltam em qualquer etapa): short+corte somados com `status == "rendered"` **e** `qa.status == "pass"` (o que `publish_next.py` de fato pega, ver CLAUDE.md). Numero + ids (mesmo formato do balde de pendentes: `2 (c2, s3)`). Zero: `0`.

Video sem `clips.json` ainda: `-` nas cinco colunas (entra na secao `Sem conta definida ainda`, nao numa tabela de canal). Video arquivado (pasta limpa, so existe `video-output/_archive/<video_id>.clips.json`): inclua na tabela do canal normalmente, marcando o nome do video com `(arquivado)` — pendentes e fila ali deveria ser sempre `0` (cleanup so roda com tudo terminal).

Ao fim de cada tabela de canal, uma linha de subtotal: soma de publicados/pendentes/fila daquele canal (so os numeros, sem lista de ids).

Com `video_id` unico (uma conta so), mostre tambem o detalhe clip a clip: id | formato | status | score | titulo | url (quando publicado).

## 3. Alertas

Agrupe tambem por canal (`### <channel_name> (<account_id>)`, mesma ordem da secao 2). Verifique e liste ao final de cada grupo (apenas os que se aplicarem):

1. **Token OAuth envelhecendo**: cheque a data de modificacao de `<credentials_dir>/token.json` da conta (campo `credentials_dir` em `config/accounts.json`, ex.: `secrets/youtube/politica`) (use `Get-Item ... | Select LastWriteTime` ou equivalente — **nunca leia o conteudo** de arquivos em `secrets/`). Se tiver **mais de 6 dias**, alerte: app OAuth em modo Testing expira o refresh token em 7 dias — rodar `python scripts/auth.py --platform youtube --account <id>` para renovar. Se `token.json` nao existe, alerte que a conta nunca autenticou.
2. **Clips `queued`**: ha clips aguardando quota de upload — sugerir `/publicar <video_id>` (limite diario da conta em `config/accounts.json`).
3. **`last_error` preenchido** em algum `state.json` de video daquele canal: mostre etapa, clip e mensagem, e sugira o skill que retoma aquela fase (`/produzir` retoma o pipeline inteiro do ponto onde parou; `/renderizar` e `/publicar` retomam as fases finais).

## 4. Encerramento

Se `video-output/` esta vazio, diga que nao ha videos em andamento e aponte `/produzir <url>` para comecar.

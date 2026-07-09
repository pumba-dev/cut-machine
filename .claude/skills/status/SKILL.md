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
video | titulo | etapa atual | clips por status
```

Em "clips por status", agregue `clips.json.clips[].status`, ex.: `3 published, 1 queued, 1 rejected`. Video sem `clips.json` ainda: `-`. Com `video_id` unico, mostre tambem o detalhe clip a clip: id | formato | status | score | titulo | url (quando publicado).

## 3. Alertas

Verifique e liste ao final (apenas os que se aplicarem):

1. **Token OAuth envelhecendo**: para cada conta em `config/accounts.json`, cheque a data de modificacao de `<credentials_dir>/token.json` (campo `credentials_dir` da conta, ex.: `secrets/youtube/principal`) (use `Get-Item ... | Select LastWriteTime` ou equivalente — **nunca leia o conteudo** de arquivos em `secrets/`). Se tiver **mais de 6 dias**, alerte: app OAuth em modo Testing expira o refresh token em 7 dias — rodar `python scripts/auth.py --platform youtube --account <id>` para renovar. Se `token.json` nao existe, alerte que a conta nunca autenticou.
2. **Clips `queued`**: ha clips aguardando quota de upload — sugerir `/publicar <video_id>` (limite diario por conta em `config/accounts.json`).
3. **`last_error` preenchido** em algum `state.json`: mostre etapa, clip e mensagem, e sugira o skill que retoma aquela fase (`/produzir` retoma o pipeline inteiro do ponto onde parou; `/renderizar` e `/publicar` retomam as fases finais).

## 4. Encerramento

Se `video-output/` esta vazio, diga que nao ha videos em andamento e aponte `/produzir <url>` para comecar.

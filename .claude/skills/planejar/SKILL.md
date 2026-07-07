---
name: planejar
description: Executa somente as etapas de planejamento e copy de um video ja transcrito - spawna clip-scout e copywriter e faz o checkpoint humano de aprovacao dos cortes. Uso - /planejar <video_id> [--conta <id>]
---

# /planejar <video_id> [--conta <id>]

Roda apenas as fases `plan` + `copy` do pipeline, com checkpoint humano ao final. Util para re-planejar sem custo de download/transcricao e para preparar o `/renderizar`.

## Pre-condicoes

1. Leia `video-output/<video_id>/state.json`. Se nao existe, ou se `stages.transcribe.status != "done"`, **pare** e informe: e preciso rodar `/produzir <url>` (ou ao menos download + transcribe) antes de planejar.
2. Se `stages.plan.status == "done"` e ja existe `clips.json` com clips: avise o usuario que o planejamento ja foi feito e pergunte se deseja apenas rever/aprovar os clips existentes (pule para o checkpoint) ou re-planejar do zero (so re-spawne o clip-scout com confirmacao explicita — re-planejar descarta a analise anterior).

## 1. clip-scout

Spawne o subagente `clip-scout` via Task, informando: workspace (`video-output/<video_id>/`) e a conta de publicacao (`--conta`, ou a conta `"default": true` de `config/accounts.json`). Ele escreve os candidatos em `clips.json` com `status: "planned"`.

Apos o retorno, valide: `clips.json` existe e os clips respeitam os limites de formato (`short` 15-59s, `corte` 120-600s). Confirme que a etapa `plan` ficou `done` em `state.json`; se o subagente nao marcou, atualize voce mesmo com `python -c` usando `core.state` (load, `set_stage(state, "plan", "done")`, save).

**Regra inviolavel**: 0 clips com score >= 60 e um resultado valido. Nao invente cortes nem rebaixe criterios — encerre graciosamente com um resumo do porque o video nao rendeu.

## 2. copywriter

Spawne o subagente `copywriter` via Task com o mesmo workspace e o `account_id` da conta alvo (`--conta` ou a default de `config/accounts.json`). Ele preenche `title`, `title_alts`, `description`, `tags` dos clips `planned` seguindo `references/padrao-copy.md` e a identidade do canal (`channel_name`, `niche`, `default_hashtags` da conta). Confirme a etapa `copy` como `done` em `state.json` (mesmo procedimento acima).

Antes do checkpoint, valide a copy: rode `python scripts/validate_plan.py --video-id <video_id>` e leia a ultima linha JSON (`{ok, errors, warnings, clips_com_copy}`). Se houver `errors`, re-spawne o copywriter **1 vez** com os erros no prompt e rode a validacao de novo; se ainda falhar, pare e reporte ao usuario com os erros exatos. `warnings` nao bloqueiam — guarde-os para exibir sob a tabela do checkpoint.

## 3. CHECKPOINT humano

Leia `clips.json` e apresente a tabela:

```
id | formato | start-end | dur | score | chars | titulo
```

(`chars` = tamanho do titulo em caracteres; exiba o titulo **completo**, sem truncar.) Logo abaixo da tabela, liste os `warnings` do `validate_plan.py` para o humano decidir se corrige algo.

Pergunte ao usuario (AskUserQuestion se disponivel, senao texto): quais clips aprovar/rejeitar, e se quer trocar algum titulo por uma das `title_alts`. Aplique em `clips.json`: aceitos -> `status: "approved"`, recusados -> `status: "rejected"`. A transicao approved/rejected e do humano/orquestrador; nao sobrescreva campos de outros donos (analise do clip-scout, copy do copywriter, blocos render/publish).

## Encerramento

Resuma: quantos clips aprovados/rejeitados e o proximo passo (`/renderizar <video_id>`).

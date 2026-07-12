---
name: renderizar
description: Renderiza os clips aprovados de um video (ffmpeg via render_clip.py) e valida o resultado com o qa-reviewer. Aceita um clip especifico ou todos os aprovados. Uso - /renderizar <video_id> [clip_id]
---

# /renderizar <video_id> [clip_id]

Executa as fases `render` + `qa` do pipeline.

## Pre-condicoes

1. Leia `video-output/<video_id>/state.json` e `video-output/<video_id>/clips.json`. Se nao existem, pare e oriente: rodar `/produzir` ou `/planejar` primeiro.
2. Deve haver ao menos 1 clip com `status: "approved"` (ou o `clip_id` pedido deve existir em `clips.json`). Se todos ainda estao `planned`, oriente a rodar `/planejar <video_id>` para o checkpoint de aprovacao. Se o clip pedido esta `rejected`, so renderize com confirmacao explicita do usuario (mude antes para `approved` em `clips.json`).

## 1. Render

Clip especifico:

```
python scripts/render_clip.py --video-id <video_id> --clip <clip_id>
```

Todos os aprovados (uma unica chamada; o script itera **sequencialmente** — nao paralelize, a GPU de 6GB nao comporta):

```
python scripts/render_clip.py --video-id <video_id> --all-approved
```

Contrato: a ultima linha do stdout e JSON `{"ok": ...}`. Clip ja `rendered` nao e refeito — o script emite `{"ok": true, "skipped": true}`. Cada clip sai em `video-output/<video_id>/<clip_id>/` (`<clip_id>.mp4`, `.ass` se short, e `metadata.json` gravado pelo script ao lado do mp4 — derivado de `clips.json`, ninguem edita a mao). Falha em um clip nao invalida os demais (estado fino por clip vive em `clips.json`); em `ok: false`, leia stderr e `state.json.last_error`, tente 1 correcao obvia (re-rodar), senao reporte.

## 2. QA (qa-reviewer)

Spawne o subagente `qa-reviewer` via Task com o workspace. Ele roda ffprobe em cada `<clip_id>/<clip_id>.mp4` renderizado e valida:

- short: 1080x1920, duracao do conteudo 30-165s (alvo media ~60s), legendas queimadas;
- corte: 1920x1080, 480-600s (8-10 min);
- audio presente; duracao real ~ `contracts.expected_output_duration` = `(end - start) + intro + vinheta de fim` (`render.intro_duration_s` da capa ~1s do short + `render.outro_duration_s`, cada um 0 se ausente), tolerancia 0.5s.

Clips reprovados ficam `failed` com `error` preenchido em `clips.json`. Ao final, marque a etapa `qa` como `done` em `state.json` — subagentes nao mexem em `state.json`: `python -c` com `core.state` (load, `set_stage(st, "qa", "done")`, save).

## Encerramento

Tabela final: clip | status (rendered / failed / skipped) | duracao real | observacao do QA. Se houve `failed`, sugira o diagnostico; se tudo ok, proximo passo: `/publicar <video_id>`.

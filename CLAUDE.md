# CLAUDE.md — Orquestrador do pipeline de cortes virais

## 1. Papel

Você é o **orquestrador** de um pipeline de produção de cortes virais (shorts 9:16 e cortes 16:9).
Você **NÃO processa mídia**: delega análise criativa a subagentes (`.claude/agents/`) e execução
determinística a `scripts/` (Bash). Seu trabalho é coordenar, decidir, apresentar checkpoints ao
usuário e **retomar** pipelines interrompidos. Você nunca toca em tokens/secrets.

## 2. Pipeline (máquina de estados)

```
download -> transcribe -> plan -> copy -> render -> qa -> publish
```

- Estado **por fase**: `video-output/<video_id>/state.json` (`core.state`, status `pending|running|partial|done|failed`).
- Estado **por clip**: `clips.json.clips[].status` (`planned -> approved -> rendering -> rendered -> queued -> uploading -> published`; desvios `rejected`/`failed` com `error` obrigatório).

**REGRA DE OURO**: antes de QUALQUER etapa, leia `state.json`. Nunca refaça etapa `done`.
`partial` retoma pelo delta (só clips não concluídos, via `clips.json`). `running` órfão
(processo morreu) → verifique o artefato com `ffprobe` e reclassifique para `done` ou `failed`.

## 3. LLM vs determinístico

| Tarefa | Quem |
|---|---|
| Download + metadados | `scripts/download.py` (yt-dlp via `core/sources`) |
| Transcrição word-level | `scripts/transcribe.py` (faster-whisper CUDA) |
| Seleção de momentos virais, start/end finos | **clip-scout** (LLM) |
| Títulos, descrições, tags | **copywriter** (LLM) |
| Geração do .ass + corte/crop/burn/encode + moldura do corte + miniatura | `scripts/render_clip.py` (ffmpeg; `core/render/branding.py` + `thumbnail.py`) |
| Validação técnica do render | **qa-reviewer** (LLM orquestrando ffprobe) |
| OAuth + upload | `scripts/auth.py` / `scripts/upload_clip.py` |
| Retomada, checkpoints, retry | **você** (orquestrador) |

## 4. Convenções

- `video_id` = id nativo da fonte (ex.: id do YouTube). `clip_id` = `<video_id>-s01` (short) / `<video_id>-c01` (corte).
- Timestamps sempre em **segundos float** (`1234.56`), alinhados a fronteiras de palavras do `transcript.json`.
- **Contrato de script**: todo CLI em `scripts/` é idempotente (emite `{"ok": true, "skipped": true}` se já feito), imprime **UMA linha JSON como último output** no stdout (`core.cli.emit`), atualiza `state.json` sozinho, I/O sempre UTF-8. Você lê só essa última linha.
- `clips.json` é o **único contrato** entre subagentes e scripts — nenhum dado de clip vive fora dele. Dono por campo (ver `core/contracts.py`): clip-scout cria o clip + análise; copywriter preenche copy; `render_clip.py` preenche `render.*`; `upload_clip.py` preenche `publish.*`; humano/você transiciona `approved/rejected`. **Ninguém sobrescreve campo de outro dono.**
- Cada clip tem subpasta própria `video-output/<video_id>/<clip_id>/` com `<clip_id>.mp4`, `<clip_id>.ass` (só shorts), `<clip_id>.border.ass` (só cortes), `<clip_id>.thumb.jpg` (miniatura, ambos os formatos) e `metadata.json` — este último é **derivado** de `clips.json` (gerado por `render_clip.py`, regenerado por `upload_clip.py` após publish). Ninguém edita `metadata.json` à mão; subagentes LLM não escrevem nele.
- Formatos (`core.contracts.FORMAT_RULES`): `short` 15–59s, 1080x1920, sem crop (vídeo numa janela sobre moldura fixa de marca — `core/render/short_frame.py`; substituiu o fundo blur), legendas queimadas; `corte` 480–900s (8–15 min, ≥8 min para monetização), 1920x1080, sem burn.

## 5. Comandos canônicos

```
python scripts/download.py    --url <URL>
python scripts/transcribe.py  --video-id <id> [--model large-v3] [--device auto|cuda|cpu] [--compute int8] [--no-diarize] [--speakers N]
python scripts/diarize.py     --video-id <id> [--speakers N] [--force]
python scripts/render_clip.py --video-id <id> [--clip <clip_id>] [--all-approved]
python scripts/upload_clip.py --video-id <id> --clip <clip_id> [--platform youtube] [--account <account_id>]
python scripts/auth.py        --platform youtube [--account <account_id>]
```

Render é **sequencial** por clip (GPU 6GB não comporta paralelismo folgado).
`transcribe.py` já diariza os falantes por padrão (grava `spk`/`speaker` no `transcript.json` → cor por falante nas legendas). Modo automático usa teto de clusters + fusão dos micro-clusters de ruído (contagem por threshold é inutilizável — dependente da duração). `diarize.py` só é preciso para **retrofit** de transcript antigo ou re-diarizar com `--speakers N` (número exato, caminho confiável). Diarização roda em CPU (sem VRAM), baixa modelos ONNX sob demanda em `models/` no 1º uso e falha degrada para cor única (não derruba a transcrição). **Confira `transcript.json.speakers` após transcrever**: se destoar do esperado (podcast costuma ter 2–3), re-rode `diarize.py --speakers N --force` com o número real.

## 6. Subagentes (Task)

| Agente | Quando spawnar | Faz |
|---|---|---|
| `clip-scout` | após `transcribe` done | lê `transcript.compact.json` + `references/heuristicas-virais.md`; escreve clips `planned` em `clips.json` (start/end, hook, score, rationale, `thumbnail_ts`) |
| `copywriter` | após `plan` done | preenche `title`, `title_alts`, `description`, `tags`, `thumbnail_text` dos clips `planned` |
| `qa-reviewer` | após `render` | ffprobe em cada mp4 (resolução, duração ±0.5s, áudio); mantém `rendered` ou marca `failed` |
| `publisher` | só após aprovação explícita do usuário | roda `upload_clip.py` por clip, valida retorno, registra `publish.*`; em `quotaExceeded` para tudo e reporta |

Passe sempre no prompt do subagente: `video_id`, caminho da pasta do vídeo (`video-output/<video_id>`) e o que se espera de volta (resumo curto, não o JSON inteiro).

## 7. Skills

- `/setup` — instala deps (ffmpeg, yt-dlp, faster-whisper) + walkthrough GCP/OAuth.
- `/produzir <url>` — pipeline completo com retomada e checkpoints.
- `/planejar <video_id>` — só plan+copy (clip-scout + copywriter + checkpoint).
- `/renderizar <video_id> [clip_id]` — só render+qa dos aprovados.
- `/publicar <video_id> [clip_id]` — só publish (com checkpoint de quota).
- `/status [video_id]` — tabela consolidada de fases e clips; alerta token OAuth perto de expirar.

## 8. Multi-conta e multi-plataforma

- Contas em `config/accounts.json`; credenciais isoladas em `secrets/<plataforma>/<conta>/`.
  Resolução via `core.accounts.get_account(platform, account_id)` (default por flag `"default"`).
- Cada conta define a identidade editorial: `channel_name`, `niche` e `default_hashtags`.
  O copywriter usa o nicho para coerência e completa as hashtags específicas (extraídas da
  transcrição) com as `default_hashtags` da conta. Passe o `account_id` no prompt dele.
- Fontes: `core/sources/` — `VideoSource.matches(url)/fetch()` + registry `get_source(url)`.
- Destinos: `core/publishers/` — `Publisher.authenticate()/upload()` + registry `get_publisher(platform)`.
- **Nova plataforma = nova classe + registro no `__init__.py`. O schema de `clips.json` NÃO muda** (`publish.platform` já parametrizado).

## 9. Checkpoints humanos OBRIGATÓRIOS

1. **Pós-plan/copy, pré-render**: rode `python scripts/validate_plan.py --video-id <id>` ANTES da tabela. `errors` → re-spawn do copywriter **1 vez** com os erros no prompt; `warnings` → liste sob a tabela como avisos de copy para o humano decidir. Apresente tabela (id | formato | start–end | duração | score | chars | título **completo**) e peça aprovação. Aplique `rejected` conforme resposta; demais viram `approved`. Default: sugerir aprovação apenas de clips com `score >= 70`.
2. **Pré-publish**: confirme quota — **dois contadores separados** (revisado 2026-07-08): **uploads = 100/dia** (teto real) e **queries = 10k/dia** (`videos.insert` 1600, `thumbnails.set` 50; upload NÃO drena as 10k a 1600/un). Respeite `daily_upload_limit` da conta (100). Excedente fica `queued` ordenado por score.

**Privacidade do upload — default `public`** (revisado em 2026-07-08). Um upload de teste
(`KGs0aTqKwaQ-c04`) subiu com `privacyStatus=public` + `uploadStatus=uploaded` (sem rejection)
e `thumbnails.set` funcionou → este projeto GCP aceita público e o canal é verificado. A premissa
antiga de "locked private" **não se aplica** a este projeto. Pipeline agora sobe `public` por
padrão (`privacy` por clip pode ser `private`/`unlisted` para exceções). Ainda assim: publicar é
ação irreversível/externa — confirme com o usuário antes de subir em lote, e valide na 1ª vez que
o vídeo continua público (o token só tem escopo de leitura após re-auth com `youtube.readonly`).

## 10. Tratamento de erro

- Script falhou (`ok: false` ou exit != 0): leia stderr + `state.json.last_error`. Tente **no máximo 1 retry óbvio** (ex.: re-rodar, corrigir flag); senão pare e reporte ao usuário com o erro exato.
- **Nunca marque `done` sem artefato verificado** (`ffprobe` no mp4, JSON parseável no transcript).
- Falha de clip individual (render/upload) **não derruba os demais**: marque o clip `failed` com `error`, continue o loop, reporte no final.
- Erros de quota/OAuth (403, token expirado): pare a fase publish inteira, informe quantos clips restaram `queued` e o remédio (`scripts/auth.py` para re-auth; token em modo Testing expira em 7 dias).

## 11. Ponteiros

- `docs/ARQUITETURA.md` — fonte de verdade: estrutura, interfaces, decisões técnicas fixas (Whisper int8, yt-dlp, ffmpeg, ASS, quota).
- `docs/PLAN.md` — plano de implementação e progresso.
- `references/heuristicas-virais.md` — rubrica de score e padrões de hook/título (clip-scout, copywriter).
- `references/padrao-copy.md` — padrão editorial de título/descrição/tags (copywriter, fonte única).
- `references/formatos-redes.md` — limites por plataforma e zonas seguras (copywriter, qa-reviewer).
- `references/estilo-legendas.md` — spec das legendas ASS queimadas.
- `references/youtube-api.md` — GCP, OAuth, quota, videos.insert (skill /setup, publisher).

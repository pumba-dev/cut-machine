# CLAUDE.md — Orquestrador do pipeline de cortes virais

## 1. Papel

Você é o **orquestrador** de um pipeline de produção de cortes virais (shorts 9:16 e cortes 16:9).
Você **NÃO processa mídia**: delega análise criativa a subagentes (`.claude/agents/`) e execução
determinística a `scripts/` (Bash). Seu trabalho é coordenar, decidir, apresentar checkpoints ao
usuário e **retomar** pipelines interrompidos. Você nunca toca em tokens/secrets.

## 2. Pipeline (máquina de estados)

```
download -> transcribe -> faces* -> plan -> copy -> [thumbnail-director*] -> render -> qa -> publish
```
*`faces` e `thumbnail-director` são **opt-in por conta** (bloco `thumbnail` em `accounts.json`); conta sem eles pula direto (comportamento clássico, thumb ASS local).

- Estado **por fase**: `video-output/<video_id>/state.json` (`core.state`, status `pending|running|partial|done|failed`).
- Estado **por clip**: `clips.json.clips[].status` (`planned -> approved -> rendering -> rendered -> queued -> uploading -> published`; desvios `rejected`/`failed` com `error` obrigatório).
- **Trava de QA no auto-publish**: `publish_next.py` (Task do Windows) só publica clip com `qa.status == "pass"` (bloco carimbado pelo qa-reviewer, dono do campo `qa`). Clip `rendered` sem QA fica retido na fila — fecha o race render→QA→publish (a Task não pegava um render antes do QA validar). Retrofit/rede de segurança determinística: `python scripts/qa_backfill.py` (mesmos checks via ffprobe, carimba em massa).
- **Limpeza de disco pós-publish** (`core/cleanup.py`): quando um vídeo fica **completo** — ≥1 clip `published` E nenhum clip pendente (todos `published`/`failed`/`rejected`) — a pasta `video-output/<video_id>/` é apagada para liberar disco (mp4/source/thumbs = os GB). Antes de apagar, o `clips.json` é arquivado em `video-output/_archive/<video_id>.clips.json` (preserva URLs/IDs publicados). Um clip `failed`/`rejected` **não** trava a limpeza; um vídeo sem nenhum `published` **nunca** é apagado. Roda automático no fim do `publish_next.py` (best-effort — nunca derruba o publish). Retrofit do backlog / limpeza manual: `python scripts/cleanup_published.py [--video-id <id>] [--dry-run]`.

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
| Detecção de rosto/emoção + host (`faces.json`) | `scripts/analyze_faces.py` (opencv/onnx CPU; opt-in) |
| Escolha do frame/rosto/layout + prompt da thumb via IA | **thumbnail-director** (LLM; opt-in) |
| Geração do .ass + corte/crop/burn/encode + moldura + miniatura (composite local **default** / ASS fallback) + intro (thumb ~1s, só shorts) + vinheta de fim | `scripts/render_clip.py` (ffmpeg; `short_frame.py` + `corte_frame.py` + `branding.py` + `thumbnail.py` + `thumbnail_local.py` + `intro.py` + `outro.py`) |
| Validação técnica do render | **qa-reviewer** (LLM orquestrando ffprobe) |
| OAuth + upload | `scripts/auth.py` / `scripts/upload_clip.py` |
| Retomada, checkpoints, retry | **você** (orquestrador) |

## 4. Convenções

- `video_id` = id nativo da fonte (ex.: id do YouTube). `clip_id` = `<video_id>-s01` (short) / `<video_id>-c01` (corte).
- Timestamps sempre em **segundos float** (`1234.56`), alinhados a fronteiras de palavras do `transcript.json`.
- **Contrato de script**: todo CLI em `scripts/` é idempotente (emite `{"ok": true, "skipped": true}` se já feito), imprime **UMA linha JSON como último output** no stdout (`core.cli.emit`), atualiza `state.json` sozinho, I/O sempre UTF-8. Você lê só essa última linha.
- `clips.json` é o **único contrato** entre subagentes e scripts — nenhum dado de clip vive fora dele. Dono por campo (ver `core/contracts.py`): clip-scout cria o clip + análise; copywriter preenche copy (`title`/`description`/`tags`/`thumbnail_text`); **thumbnail-director preenche `thumbnail_plan`** (frame/rosto/layout da thumb compositada; opt-in); `render_clip.py` preenche `render.*`; **qa-reviewer preenche `qa.*`** (`qa.status` pass/fail); `upload_clip.py` preenche `publish.*`; humano/você transiciona `approved/rejected`. **Ninguém sobrescreve campo de outro dono.**
- Cada clip tem subpasta própria `video-output/<video_id>/<clip_id>/` com `<clip_id>.mp4`, `<clip_id>.ass` (só shorts), `<clip_id>.border.ass` (só cortes **sem arte PNG** — fallback da moldura gerada), `<clip_id>.thumb.jpg` (miniatura, ambos os formatos) e `metadata.json` — este último é **derivado** de `clips.json` (gerado por `render_clip.py`, regenerado por `upload_clip.py` após publish). Ninguém edita `metadata.json` à mão; subagentes LLM não escrevem nele.
- Formatos (`core.contracts.FORMAT_RULES`): `short` 30–165s (conteúdo; alvo média ~60s, reserva ~15s p/ intro+vinheta → final ≤180s, teto do Shorts), 1080x1920, sem crop (vídeo numa janela com a arte PNG da conta **por cima** — janela transparente; `core/render/short_frame.py`; substituiu o fundo blur), legendas queimadas; `corte` 480–900s (8–15 min, ≥8 min para monetização), 1920x1080, sem burn (vídeo numa janela com a arte PNG por cima — `core/render/corte_frame.py`; fallback sem PNG: moldura gerada preto+amarelo de `branding.py`). **Compositing:** canvas preto → vídeo na janela → arte PNG por cima → (short) legendas queimadas por último. Toda a marca/CTA vem embutida no PNG.
- **Camada anti-detecção** (`core/render/transform.py`, **opt-in por conta**): bloco `transform` em `config/accounts.json` (irmão de `brand`) torna cada render tecnicamente distinto do original (quebra Content ID) e distinto entre si (reduz reused-content). Técnicas: `speed` (nudge), `pitch_semitones`, `eq` (EQ+compressor), `music_dir`/`music_volume` (música de fundo com duck reverso — voz sempre prioritária), `color`/`lut` (grade), `zoom` (crop-in). `jitter` (0–1) aplica variação **determinística por clip** (seed = `clip_id`, idempotente); só parâmetros ativos jitteram ("off" continua off). **Invariantes preservados de propósito**: duração (lê `dur*speed` da fonte, saída travada em `dur`) e resolução (crop-in antes do scale) não mudam → **QA não precisa mudar**. Bloco ausente = tudo-off = zero regressão. Efetivos registrados em `render.transform`. Short com `speed≠1` reescala os tempos do `.ass` (`build_ass(..., speed=)`). Faixas de música **precisam ser livres de claim** (`assets/music/<conta>/`).
- **Vinheta de fim** (`core/render/outro.py`, **opt-in por conta**): `brand.short_outro`/`brand.corte_outro` em `config/accounts.json` (mp4 por conta em `assets/short-end/<conta>.mp4` / `assets/corte-end/<conta>.mp4`; vazio = sem vinheta, retrocompatível). Colada ao **final** do clip **depois** do render+validação do conteúdo — o check de duração do conteúdo roda antes, isolado. Normaliza a arte (fit+pad para a resolução do formato, 30fps, yuv420p, áudio 48k estéreo AAC) via concat filter (re-encode), então a arte pode vir em qualquer resolução/fps que ela é encaixada sem distorcer/cortar. **Só a duração cresce** (resolução/áudio intactos). Falha no append é **fatal** (marca de fim é requisito, ao contrário da miniatura). Duração acrescentada em `render.outro_duration_s`.
- **Miniatura inteligente** (**opt-in por conta**, bloco `thumbnail` em `accounts.json`; `core/render/thumbnail_config.py`). Três alavancas independentes:
  - **Detecção de rosto/emoção** (fase `faces`, `scripts/analyze_faces.py` + `core/faces/`): amostra frames do source em **CPU** (opencv YuNet+SFace+FER via onnx, modelos em `models/faces/`, padrão diarize: download sob demanda + degrada), agrupa identidades por embedding e marca o **host** (quem mais aparece). Gera `video-output/<id>/faces.json` (derivado; apagado com a pasta no cleanup). Falha → `faces.json` degradado + stage `done`, pipeline segue.
  - **Geração da thumb — precedência (best-effort, degrada em cascata; `render.thumbnail_provider`):**
    1. **`local_composite`** (`core/render/thumbnail_local.py`, **default das contas `face_aware`**): monta a thumb 100% local — fundo = frame real (blur leve+escurecido), sujeito = recorte rembg do **host** (enquadrado via `faces.json`) com glow amarelo, texto = motor ASS (`thumbnail.build_thumb_ass`). **9:16/16:9 exato, texto perfeito, pessoa 100% fiel, grátis e determinístico** (~4s). Layout: **short** = sujeito central, texto topo/base; **corte** = layout lateral (sujeito num lado, texto na outra metade — `build_thumb_ass(region=)`). `render.thumbnail_composite_error` = caiu pro fallback.
    2. **`local`** (`thumbnail.py`): thumb ASS simples (crop central) — fallback final quando o composite falha ou a conta não é `face_aware`.
    - Fluxo de geração via IA (gpt-image-1) foi **removido** (custo + não fazia 9:16 nativo + fidelidade pior que o recorte real). Se um dia quiser IA, um provedor com 9:16 nativo + foto de input (Imagen/Flux/Ideogram) entraria como novo tier aqui.
  - **Intro (capa do feed)** (`core/render/intro.py`, `intro_short: true`, **só shorts**): cola a thumb como ~1s congelado no **início** do short (o feed do Shorts usa o 1º frame como capa). **Best-effort não-fatal** (≠ outro); duração acrescentada em `render.intro_duration_s`.
- **Duração esperada do mp4 final = `(end-start) + intro_duration_s + outro_duration_s`** (`contracts.expected_output_duration`, fonte única dos checks de `qa_backfill.py` e qa-reviewer; cada extra entra só quando aplicado). O check **interno** do render valida o **conteúdo isolado** (`end-start`, antes de intro/outro).

## 5. Comandos canônicos

```
python scripts/download.py     --url <URL>
python scripts/transcribe.py   --video-id <id> [--model large-v3] [--device auto|cuda|cpu] [--compute int8] [--no-diarize] [--speakers N]
python scripts/diarize.py      --video-id <id> [--speakers N] [--force]
python scripts/analyze_faces.py --video-id <id> [--account <id>] [--interval 2.0] [--max-frames 2500] [--force]
python scripts/render_clip.py  --video-id <id> [--clip <clip_id>] [--all-approved]
python scripts/upload_clip.py --video-id <id> --clip <clip_id> [--platform youtube] [--account <account_id>]
python scripts/auth.py        --platform youtube [--account <account_id>]
python scripts/cleanup_published.py [--video-id <id>] [--dry-run]
```

Render é **sequencial** por clip (GPU 6GB não comporta paralelismo folgado).
`transcribe.py` já diariza os falantes por padrão (grava `spk`/`speaker` no `transcript.json` → cor por falante nas legendas). Modo automático usa teto de clusters + fusão dos micro-clusters de ruído (contagem por threshold é inutilizável — dependente da duração). `diarize.py` só é preciso para **retrofit** de transcript antigo ou re-diarizar com `--speakers N` (número exato, caminho confiável). Diarização roda em CPU (sem VRAM), baixa modelos ONNX sob demanda em `models/` no 1º uso e falha degrada para cor única (não derruba a transcrição). **Confira `transcript.json.speakers` após transcrever**: se destoar do esperado (podcast costuma ter 2–3), re-rode `diarize.py --speakers N --force` com o número real.

## 6. Subagentes (Task)

| Agente | Quando spawnar | Faz |
|---|---|---|
| `clip-scout` | após `transcribe` done | lê `transcript.compact.json` + `references/heuristicas-virais.md`; escreve clips `planned` em `clips.json` (start/end, hook, score, rationale, `thumbnail_ts`) |
| `copywriter` | após `plan` done | preenche `title`, `title_alts`, `description`, `tags`, `thumbnail_text` dos clips `planned` |
| `thumbnail-director` | após `copy`, **se** conta opt-in + `faces.json` ok (opcional) | lê `faces.json` + `thumbnail_text`; escreve `thumbnail_plan` (frame_ts, rosto/host, layout) nos clips `planned` — usado pela thumb compositada |
| `qa-reviewer` | após `render` | ffprobe em cada mp4 (resolução, duração ±0.5s, áudio); aprova → carimba `qa.status: "pass"` (mantém `rendered`, libera auto-publish) ou marca `failed`/`rejected` + `qa.status: "fail"` |
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

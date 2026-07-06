# POC — Agente Orquestrador de Cortes Virais (social-accounts-agent)

## Contexto

Construir, sobre o Claude Code, um agente gerenciador de redes sociais cujo trabalho é: baixar um vídeo longo público do YouTube, planejar cortes virais maximizando retenção e compartilhamento, renderizar em dois formatos (Shorts 9:16 <60s com legendas queimadas; corte 16:9 até 10min) e fazer upload no YouTube. A POC cobre só o ciclo YouTube→YouTube; TikTok/Instagram/Facebook ficam para depois (o schema já nasce parametrizado por plataforma).

O Claude Code é o orquestrador (CLAUDE.md), subagentes fazem o trabalho criativo (análise de transcrição, copy), e scripts Python determinísticos fazem mídia e API (download, transcrição, ffmpeg, upload).

**Ambiente**: Windows 11, Python 3.13.5, GTX 1660 SUPER 6GB (CUDA ok, sem tensor cores). ffmpeg e yt-dlp ainda não instalados.

**Decisões do usuário**: Python; faster-whisper local; Shorts = crop central + legendas queimadas; setup GCP incluso no plano.

## Limitações críticas (aceitas de antemão)

1. **Upload via API fica travado como `private`**: projetos GCP novos não-auditados têm todo vídeo de `videos.insert` bloqueado em privado (política YouTube, sem apelação). POC usa `privacyStatus=private` sempre — o upload valida o pipeline; publicação real é manual via YouTube Studio até passar na auditoria ("YouTube API Audit and Quota Extension Form", submeter no dia 1, leva semanas).
2. **Quota**: 10.000 unidades/dia; upload = 1.600 → **~6 uploads/dia**. Pipeline precisa de fila (`status: queued`) e limite diário configurável.
3. **OAuth em modo Testing**: refresh token expira em 7 dias → re-consentimento semanal (documentado no /setup).
4. **Direitos autorais**: crédito não é licença. POC roda com vídeo do próprio usuário ou com licença explícita (Creative Commons). Pré-condição declarada no /produzir.

## Estrutura do repositório

```
social-accounts-agent/
├── CLAUDE.md                        # orquestrador: papel, máquina de estados, convenções, comandos canônicos
├── requirements.txt
├── .gitignore                       # workspace/, secrets/, *.mp4
├── .claude/
│   ├── settings.json                # env PYTHONUTF8=1; permissões: python scripts/*, ffmpeg, ffprobe, yt-dlp
│   ├── agents/
│   │   ├── clip-scout.md            # transcrição → clips.json (tools: Read, Grep, Write)
│   │   ├── copywriter.md            # títulos/descrições/tags (tools: Read, Edit)
│   │   ├── qa-reviewer.md           # valida renders via ffprobe (tools: Read, Bash, Edit)
│   │   └── publisher.md             # uploads + registro de IDs (tools: Read, Bash, Edit)
│   └── skills/
│       ├── setup/SKILL.md           # /setup — instala deps + walkthrough GCP
│       ├── produzir/SKILL.md        # /produzir <url> — pipeline completo com checkpoints
│       ├── planejar/SKILL.md        # /planejar <video_id>
│       ├── renderizar/SKILL.md      # /renderizar <video_id> [clip_id]
│       ├── publicar/SKILL.md        # /publicar <video_id> [clip_id]
│       └── status/SKILL.md          # /status [video_id]
├── references/
│   ├── heuristicas-virais.md        # sinais, rubrica, duração, ajuste fino, títulos, anti-padrões, densidade
│   ├── formatos-redes.md            # specs Shorts/corte + zona segura de legenda; stubs TikTok/Reels
│   ├── youtube-api.md               # GCP passo a passo, quota, política private-lock, categoryId
│   └── estilo-legendas.md           # spec ASS: fonte, tamanho, outline, posição
├── scripts/
│   ├── lib/state.py                 # load/save state.json atômico (tmp + os.replace)
│   ├── lib/media.py                 # helpers ffprobe
│   ├── download.py                  # yt-dlp API Python
│   ├── transcribe.py                # faster-whisper word-level
│   ├── render_clip.py               # ASS + ffmpeg (corte, crop, burn)
│   ├── auth_youtube.py              # OAuth installed-app flow
│   └── upload_youtube.py            # videos.insert resumable
├── secrets/                         # gitignored: credentials.json, token.json
└── workspace/<video_id>/            # gitignored
    ├── state.json                   # progresso por fase
    ├── source.mp4 + source.info.json
    ├── transcript.json              # word-level (para render e ajuste fino)
    ├── transcript.compact.json      # só segmentos (para o clip-scout não estourar contexto)
    ├── clips.json                   # CONTRATO CENTRAL
    └── clips/<clip_id>.ass|.mp4
```

## Convenções (vão no CLAUDE.md)

- Pipeline: `download → transcribe → plan → copy → render → qa → publish`. Antes de qualquer etapa, ler `state.json`; nunca refazer etapa `done`.
- `video_id` = ID do YouTube; `clip_id` = `<video_id>-s01` (short) / `<video_id>-c01` (corte).
- Todo script: aceita `--workspace workspace/<id>`, é idempotente, atualiza `state.json` sozinho, imprime 1 linha JSON no stdout como último output (`{"ok": true, ...}`). UTF-8 em todo I/O (`encoding="utf-8"`; `PYTHONUTF8=1` no env do settings.json).
- Timestamps em segundos float, alinhados a fronteiras de palavra do transcript.
- Checkpoint humano: entre plan/copy e render (aprovar tabela de clips); entre qa e publish (confirmar quota).
- LLM faz: seleção de momentos, timestamps finos, copy, decisão de retry. Script faz: download, transcrição, ASS, ffmpeg, OAuth, upload. LLM nunca toca em tokens/secrets.

## Contratos de dados

### `clips.json` (schema canônico — único; resolve conflito entre designs)

```json
{
  "schema_version": 1,
  "video_id": "abc123",
  "source": {"url": "...", "title": "...", "channel": "...", "duration_s": 5432.1,
             "width": 1920, "height": 1080, "fps": 30.0, "language": "pt"},
  "generated_at": "ISO-8601",
  "clips": [
    {
      "id": "abc123-s01",
      "format": "short",                  // "short" | "corte"
      "start": 1234.56, "end": 1289.30, "duration_s": 54.74,
      "hook_text": "citação literal dos 3 primeiros segundos",
      "payoff_text": "citação literal do payoff",
      "transcript_excerpt": "trecho representativo (~500 chars)",
      "rationale": "por que viraliza (1-2 frases)",
      "dominant_signal": "pico emocional",
      "loop_potential": false,
      "audio_risk": false,                // true se prob média das palavras < 0.5
      "score": 87,
      "score_breakdown": {"hook": 30, "retencao": 27, "compartilhabilidade": 18, "clareza": 12},
      "title": null, "title_alts": [], "description": null, "tags": [],   // copywriter preenche
      "captions": {"burn": true, "ass_path": "clips/abc123-s01.ass"},
      "render": {"crop": "center", "target_resolution": "1080x1920",
                 "output_path": "clips/abc123-s01.mp4", "rendered_at": null, "actual_duration_s": null},
      "publish": {"platform": "youtube", "privacy": "private", "category_id": "22",
                  "made_for_kids": false, "youtube_video_id": null, "youtube_url": null, "published_at": null},
      "status": "planned",
      "error": null
    }
  ],
  "rejected_notable": [{"start": 0.0, "end": 0.0, "reason": "auditoria humana das rejeições"}]
}
```

Regras:
- `format`: `short` → 15–59s, 1080x1920, crop center, legendas queimadas; `corte` → 120–600s, 1920x1080, sem burn na POC.
- `status`: `planned → approved → rendering → rendered → queued → uploading → published`; desvios `rejected` | `failed` (com `error`). `queued` existe por causa da quota de 6/dia.
- Rubrica (de references/heuristicas-virais.md): 4 eixos 0–10 × pesos — hook ×3.5, retenção ×3.0, compartilhabilidade ×2.0, clareza ×1.5 = máx 100. Propor só score ≥ 60; veto se clareza ≤ 3. Densidade: 4–8 shorts + 2–4 cortes por hora; zero clips viáveis é resultado válido (terminar graciosamente com relatório).
- `internal_cuts` (jump cuts) FORA do escopo da POC — cortes contíguos apenas. Campo pode existir no futuro; render v1 ignora.
- Dono por campo: clip-scout cria objeto/análise; copywriter preenche copy; render_clip.py preenche render.*; upload_youtube.py preenche publish.*; humano decide approved/rejected.

### `transcript.json`

```json
{"video_id": "...", "language": "pt", "model": "large-v3", "duration": 5432.1,
 "segments": [{"id": 0, "start": 0.0, "end": 7.4, "text": "...",
               "words": [{"w": "Frase", "start": 0.0, "end": 0.42, "prob": 0.98}]}]}
```
+ `transcript.compact.json` (mesma estrutura sem `words`) para o clip-scout; + `transcript.srt` para conferência humana.

### `state.json`

Por vídeo: `stages: {download|transcribe|plan|copy|render|qa|publish: {status: pending|running|partial|done|failed, ...}}` + `last_error`. Escrita atômica via `lib/state.py`. `running` órfão → verificar artefato com ffprobe e reclassificar.

## Especificações técnicas chave

### Transcrição (GTX 1660 SUPER)
- `WhisperModel("large-v3", device="cuda", compute_type="int8")` (~3.1GB VRAM, cabe). **`int8`, não `int8_float16`** — série GTX 16xx tem histórico de NaN em fp16. Fallback: CPU int8 modelo `small`.
- ctranslate2 ≥4.8 tem wheels cp313; CUDA via wheels pip `nvidia-cublas-cu12` + `nvidia-cudnn-cu12` (cuDNN 9) — sem instalar CUDA Toolkit; no Windows carregar DLLs com `os.add_dll_directory(site-packages/nvidia/{cublas,cudnn}/bin)`.
- `word_timestamps=True, vad_filter=True, language="pt", beam_size=5`. Preservar `probability` das palavras (alimenta `audio_risk`).
- Smoke test: `python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"` → `1`.

### Download
- yt-dlp API Python: formato `bv*[ext=mp4][vcodec^=avc1][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]/b`, `merge_output_format=mp4`, `writeinfojson`, `restrictfilenames`, `noplaylist`, saída `workspace/<id>/source.mp4`.
- Fallback anti-bot documentado: `--cookies-from-browser` (YouTube exige PO token/cookies cada vez mais).

### Render (ffmpeg — libx264, NVENC fica para depois)
- Shorts: `-ss <start> -t <dur> -i source.mp4 -vf "scale=-2:1920,crop=1080:1920,ass=<clip>.ass" -r 30 -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart`. `scale` antes de `crop` evita largura ímpar; `-ss` antes de `-i` + re-encode = corte preciso (stream copy gruda em keyframe — inaceitável). Rodar ffmpeg com `cwd` na pasta do clipe e caminho ASS relativo (escaping de path absoluto no Windows quebra o filtro).
- Corte 16:9: mesmo padrão sem crop/ass, `-crf 20`.
- ASS: tempos rebased (`t - clip.start`), Arial Black 110 (PlayRes 1080x1920), outline 8 preto, Alignment 2, MarginV 550 (zona segura acima da UI do Shorts), 2–4 palavras por evento em CAIXA ALTA, agrupadas por word timestamps (max_gap 0.6s).
- qa-reviewer bloqueia clip com `audio_risk: true` ou prob média < limiar (legendas dessincronizadas).

### Upload
- Setup GCP: criar projeto → ativar YouTube Data API v3 → OAuth consent External/Testing + test user → credential Desktop app → `secrets/credentials.json`; primeiro run abre browser → `secrets/token.json`. Escopo mínimo `youtube.upload`.
- `videos.insert` resumable (chunks 8MB), `privacyStatus="private"`, `selfDeclaredMadeForKids=False`, `defaultLanguage="pt-BR"`, categoryId 22 (People & Blogs). Shorts é detectado automático (vertical ≤3min) — sem flag, `#shorts` opcional.
- Publisher: respeita limite diário (default 5 uploads, margem sob 6), clips excedentes ficam `queued` priorizados por score; 403 quotaExceeded → parar e reportar.

## Etapas de implementação (ordem = risco primeiro)

### Etapa 1 — Fundação + stack de mídia validada
1. Scaffold: árvore de pastas, `.gitignore`, `requirements.txt`, `.claude/settings.json` (PYTHONUTF8=1 + permissões), `git init`.
2. Instalar: `winget install --id=Gyan.FFmpeg -e` (build full, tem libass), `pip install -r requirements.txt` (yt-dlp, faster-whisper≥1.2.1, ctranslate2≥4.8.1, nvidia-cublas-cu12, nvidia-cudnn-cu12>=9.1,<10, google-api-python-client, google-auth-oauthlib).
3. Smoke tests: `ffmpeg -filters | findstr ass`, CUDA device count = 1.
4. `lib/state.py` + `download.py` + `transcribe.py`; testar com vídeo real curto (~10min) do usuário.
5. **Em paralelo (humano)**: criar projeto GCP e submeter formulário de auditoria (prazo externo longo).

### Etapa 2 — Conhecimento + agentes de planejamento
1. `references/heuristicas-virais.md` (sinais, rubrica ×3.5/3.0/2.0/1.5, duração, ajuste fino início/meio/fim, títulos BR, anti-padrões, densidade), `formatos-redes.md`, `estilo-legendas.md`.
2. `.claude/agents/clip-scout.md` (lê heurísticas + transcript.compact.json, refina timestamps no transcript.json word-level, escreve clips.json) e `copywriter.md`.
3. `CLAUDE.md` com papel, máquina de estados, convenções, comandos canônicos.
4. Testar: rodar clip-scout no transcript real → validar clips.json à mão.

### Etapa 3 — Render + QA
1. `render_clip.py`: gerador ASS (agrupamento de palavras, rebase) + comandos ffmpeg acima; validações de duração por formato.
2. `.claude/agents/qa-reviewer.md`: ffprobe em cada render (resolução, duração ±0.5s, áudio presente).
3. Testar: renderizar 1 short + 1 corte do vídeo real; conferir legendas sincronizadas a olho.

### Etapa 4 — Upload
1. `references/youtube-api.md`, `auth_youtube.py`, `upload_youtube.py` (resumable, private), `.claude/agents/publisher.md` (fila, limite diário, quota).
2. Testar: subir 1 short como private, conferir no Studio que virou Short (vertical).

### Etapa 5 — Skills + ponta a ponta
1. Skills: `/setup`, `/produzir` (com pré-condição de direitos + retomada por state.json + 2 checkpoints humanos + `--sem-upload`), `/planejar`, `/renderizar`, `/publicar`, `/status` (inclui alerta de token OAuth >6 dias).
2. Rodada completa: `/produzir <url>` num vídeo longo real → aprovar clips → renders → uploads private → relatório final (URLs, quota consumida, falhas).

## Verificação

- **Etapa 1**: transcript.json de vídeo real tem words com prob; tempo de transcrição ~5–10x tempo real na GPU.
- **Etapa 2**: clips.json valida contra o schema; scores plausíveis; hooks citados existem na transcrição (conferir 2–3 timestamps abrindo o vídeo no ponto).
- **Etapa 3**: ffprobe confirma 1080x1920/<60s e 1920x1080; assistir o short: legenda sincronizada, dentro da zona segura, corte não decepa palavra.
- **Etapa 4**: vídeo aparece no Studio como Short private; upload_log registra 1600 unidades.
- **Etapa 5**: matar o processo no meio do render e re-rodar /produzir → retoma sem refazer download/transcrição; vídeo sem momentos bons → relatório "0 clips viáveis" sem inventar cortes.

## Fora do escopo da POC (registrado para o futuro)

TikTok/Instagram/Facebook (schema já parametrizado); jump cuts internos; reframe com face-tracking; NVENC; Shorts até 3min; A/B de títulos; auditoria GCP aprovada → uploads públicos + agendamento.

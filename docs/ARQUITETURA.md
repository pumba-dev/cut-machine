# Arquitetura — social-accounts-agent

Pipeline de cortes virais orquestrado pelo Claude Code. Fluxo:
`download → transcribe → plan → copy → render → qa → publish`

## Princípios

1. **LLM vs determinístico**: subagentes (LLM) fazem seleção de momentos, timestamps finos e copy; scripts Python fazem download, transcrição, ffmpeg, OAuth e upload. LLM nunca toca em tokens/secrets.
2. **Abstração de fonte**: `core/sources/` — `VideoSource` (ABC) com registry por URL. Hoje YouTube; amanhã qualquer plataforma implementa `matches(url)` + `fetch()`.
3. **Abstração de destino**: `core/publishers/` — `Publisher` (ABC) com registry por plataforma. Hoje YouTube; amanhã TikTok/Instagram/Facebook implementam `authenticate()` + `upload()`.
4. **Multi-conta**: `config/accounts.json` registra contas por plataforma; credenciais isoladas em `secrets/<plataforma>/<conta>/`. Publishers recebem a conta resolvida por `core.accounts.get_account(platform, account_id)`. Cada conta carrega a identidade editorial do canal: `channel_name`, `niche` (nicho de publicação — todo clip deve ser coerente com ele) e `default_hashtags` (hashtags padrão do canal, usadas pelo copywriter para completar as específicas tiradas da transcrição).
5. **Estado retomável**: `video-output/<video_id>/state.json` (por fase, via `core.state`) + `clips.json.clips[].status` (por clip). Toda etapa lê estado antes; nunca refaz etapa `done`. Escrita atômica.
6. **Contrato de script**: todo CLI em `scripts/` imprime UMA linha JSON no stdout como último output (`core.cli.emit`), é idempotente e atualiza o estado sozinho. UTF-8 em todo I/O.

## Estrutura

```
CLAUDE.md                      # orquestrador
config/accounts.json           # contas por plataforma
.claude/agents/                # clip-scout, copywriter, qa-reviewer, publisher
.claude/skills/                # setup, produzir, planejar, renderizar, publicar, status
references/                    # heuristicas-virais, padrao-copy, formatos-redes, estilo-legendas, youtube-api
core/                          # pacote Python
  paths.py state.py contracts.py media.py accounts.py cli.py diarize.py
  sources/    base.py youtube.py       # + __init__.py com get_source(url)
  transcribe/ whisper_local.py
  render/     captions.py ffmpeg.py
  publishers/ base.py youtube.py       # + __init__.py com get_publisher(platform)
scripts/                       # CLIs finos sobre o core
models/diarization/            # gitignored: modelos ONNX de diarização (baixados sob demanda)
video-output/<video_id>/       # gitignored: state.json, source.mp4, source.json,
                               #   source.info.json, transcript*.json, clips.json
  <clip_id>/                   # por clip: <clip_id>.mp4, <clip_id>.ass (só shorts), metadata.json
secrets/<plataforma>/<conta>/  # gitignored: credentials.json, token.json, upload_log.json
```

## Interfaces dos CLIs (contrato com CLAUDE.md e skills)

```
python scripts/download.py    --url <URL>
python scripts/transcribe.py  --video-id <id> [--model large-v3] [--device auto|cuda|cpu] [--compute int8] [--no-diarize] [--speakers N]
python scripts/diarize.py     --video-id <id> [--speakers N] [--force]   # retrofit de transcript existente
python scripts/render_clip.py --video-id <id> [--clip <clip_id>] [--all-approved]
python scripts/upload_clip.py --video-id <id> --clip <clip_id> [--platform youtube] [--account <account_id>]
python scripts/auth.py        --platform youtube [--account <account_id>]
```

Todos os scripts fazem bootstrap do pacote: `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`.

## Abstrações (assinaturas)

```python
# core/sources/base.py
class VideoSource(ABC):
    name: str                                   # "youtube"
    @classmethod
    def matches(cls, url: str) -> bool: ...
    def probe_id(self, url: str) -> str:
        """video_id canonico da URL sem baixar (idempotencia do download)."""
    def fetch(self, url: str, workspace: Path) -> dict:
        """Baixa video + metadados. Retorna dict source (contrato abaixo),
        que download.py grava em video-output/<id>/source.json."""

# retorno de fetch() — vira o bloco "source" do clips.json:
# {"video_id", "url", "title", "channel", "duration_s", "width", "height",
#  "fps", "language", "path"}

# core/sources/__init__.py
def get_source(url: str) -> VideoSource   # varre registry; LookupError se nenhum matches

# core/publishers/base.py
class Publisher(ABC):
    platform: str                               # "youtube"
    def authenticate(self, account: dict) -> Any: ...
    def upload(self, video_path: Path, metadata: dict, account: dict) -> dict:
        """metadata: title, description, tags, category_id, privacy, made_for_kids,
        language. Retorna {"remote_id", "url", "published_at"}."""

# core/publishers/__init__.py
def get_publisher(platform: str) -> Publisher
```

## Contratos de dados

- `clips.json`: ver `core/contracts.py` (FORMAT_RULES, CLIP_STATUSES, validate_plan com copy-checks duros, `lint_copy` com warnings do padrão editorial — `references/padrao-copy.md`). Call site canônico da validação: `python scripts/validate_plan.py --video-id <id>` → 1 linha JSON `{ok, errors, warnings, clips_com_copy}`; errors → exit 1. Formatos: `short` 15–59s 1080x1920 sem crop (vídeo numa janela + arte PNG da conta por cima, janela transparente) legendas queimadas; `corte` 480–900s (8–15 min, ≥8 min p/ monetização) 1920x1080 sem burn, com arte PNG por cima (fallback sem PNG: moldura gerada preto+amarelo + CTA de inscrição). Campos de miniatura: `thumbnail_ts` (float, clip-scout), `thumbnail_text {impact, hooks[]}` (copywriter), `render.thumbnail_path` (render). Bloco `publish` de cada clip: `{"platform", "account", "privacy": "public", "category_id": "22", "made_for_kids": false, "remote_id": null, "url": null, "published_at": null}` (padrão **public** desde 2026-07-08; `private`/`unlisted` por clip só p/ exceções).
- `metadata.json` (em `video-output/<video_id>/<clip_id>/`): artefato **derivado** de `clips.json` (que segue como única fonte de verdade e único contrato entre subagentes e scripts). Gerado por `render_clip.py` no render e regenerado por `upload_clip.py` após o publish. Contém: `clip_id`, `video_id`, `format`, `status`, `title`, `title_alts`, `description`, `tags`, `hashtags`, `hook_text`, `thumbnail_ts`, `thumbnail_text`, `score`, `start/end/duration_s`, `source{url,title,channel}`, `render{}` (inclui `thumbnail_path`), `publish{}`. `hashtags` deriva do bloco final de hashtags da `description` (fallback: as 5 primeiras `tags`). Ninguém edita metadata.json à mão; subagentes LLM não escrevem nele.
- `transcript.json`: `{"video_id", "language", "model", "duration", "speakers", "segments": [{"id", "start", "end", "text", "speaker", "words": [{"w", "start", "end", "prob", "spk"}]}]}`. `speakers` = nº de falantes detectados (0 = diarização pulada/falhou); `spk` por palavra e `speaker` por segmento = índice do falante (0 = quem mais fala), gravados por `core.diarize` após o Whisper. + `transcript.compact.json` (sem `words`, mantém `speaker` por segmento, para o clip-scout) + `transcript.srt` (conferência humana).
- `state.json`: ver `core/state.py`.

## Decisões técnicas fixas

- **Whisper**: `WhisperModel("large-v3", device="cuda", compute_type="int8")` — GTX 1660 SUPER: `int8`, nunca fp16 (NaN na série 16xx). Fallback CPU int8 + modelo `small`. `word_timestamps=True, vad_filter=True, beam_size=5`. DLLs CUDA: `os.add_dll_directory(site-packages/nvidia/{cublas,cudnn}/bin)` no Windows.
- **yt-dlp**: formato `bv*[ext=mp4][vcodec^=avc1][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]/b`, merge mp4, writeinfojson, restrictfilenames, noplaylist. Fallback anti-bot: `cookiesfrombrowser`.
- **ffmpeg** (libx264; NVENC futuro): ambos os formatos com moldura = **arte PNG estática da conta POR CIMA do vídeo** (janela transparente na arte). Composição comum: `[0:v]setpts=PTS-STARTPTS,scale=WW:WH:force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2[fg];color=c=black:s=CWxCH[canvas];[canvas][fg]overlay=x=WX+(WW-w)/2:y=WY+(WH-h)/2:shortest=1[base];[1:v]scale=CW:CH[png];[base][png]overlay=0:0[v]` (short: `[v]` recebe `,ass=<clip>.ass` por último — legendas sempre no topo). Janela `WINDOW` fixa por formato: short `core/render/short_frame.py` (1080x1920), corte `core/render/corte_frame.py` (1920x1080), medida uma vez via **alpha** da arte. `setpts=PTS-STARTPTS` alinha o vídeo (seek deixa 1º frame com PTS>0) ao `color`/PNG (t=0) — sem isso a abertura fica preta. **`-t <dur>` na SAÍDA é obrigatório**: `color` + `-loop 1` no PNG são fontes infinitas e o grafo de dois overlays não encerra sozinho (o `-t` de input só limita a leitura do vídeo) → sem ele o encode nunca termina. Flags: `-r 30 -c:v libx264 -preset medium -crf 18` (short) / `-crf 20` (corte) `-pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart -t <dur>`. Fallback do corte sem arte PNG: **moldura gerada** (`core/render/branding.py`): `scale`+`pad` + `drawbox` rim amarelo + `ass=<clip>.border.ass`. Rodar com `cwd` na pasta do clip e caminho ASS relativo (escaping Windows). Corte preciso exige re-encode (stream copy gruda em keyframe).
- **Miniatura** (`core/render/thumbnail.py`): gerada no render p/ ambos os formatos — `ffmpeg -ss <thumbnail_ts> -i source -frames:v 1 -vf "scale/crop <res> + ass=<clip>.thumb.ass" -q:v 2` → `<clip>.thumb.jpg` (corte 1280x720, short 1080x1920). Texto = `thumbnail_text` (fallback `hook_text`/`title`); nunca fatal ao render. Upload via `thumbnails.set` best-effort no publisher (50 unidades, exige canal verificado; falha só avisa).
- **ASS**: tempos rebased (`t - clip.start`), Arial Black 110 @ PlayRes 1080x1920, Outline 8, Alignment 2, MarginV 550, 2–4 palavras por evento em CAIXA ALTA, max_gap 0.6s. **Cor por falante**: um Style por falante (`Cap0..Cap4`, paleta fixa em `SPEAKER_COLOURS`); a palavra usa o `spk` da diarização; grupo nunca mistura falantes. Transcript sem diarização cai no estilo branco `Cap` (retrocompat). `ScaledBorderAndShadow: yes`; nunca usar `force_style` no filtro (sobrescreve os estilos e mata as cores). Ver `references/estilo-legendas.md`.
- **Diarização** (`core/diarize.py`): sherpa-onnx `OfflineSpeakerDiarization` (onnxruntime CPU, sem torch, sem token HF). Segmentação pyannote/segmentation-3.0 ONNX (MIT) + embeddings NeMo TitaNet-large + FastClustering; modelos baixados sob demanda para `models/diarization/` (`ensure_models`). Roda após o Whisper dentro do `transcribe_video` (falha degrada para cor única, não derruba a transcrição); `scripts/diarize.py` faz retrofit de transcripts antigos. Áudio extraído mono 16kHz s16le via ffmpeg. Atribuição palavra→falante: interseção temporal máxima (whisperX) + suavização por sentença (voto majoritário) — obrigatória pelo drift de ~ms do Whisper. **Contagem de falantes**: `num_speakers` explícito (`--speakers N`) fixa N exato — caminho confiável. Automático (default) roda com teto `AUTO_MAX_SPEAKERS`=6 e funde os micro-clusters de ruído (`_merge_minor_speakers`, <8% do tempo de fala → falante major mais próximo). Clustering por threshold puro é inutilizável: dependente da duração (0.5 deu 83 falantes num podcast de 2; janela entre arco-íris e colapso é fina demais). Validado no real: teto+merge → 2 falantes limpos num trecho de 30min. Confira `transcript.json.speakers`; se destoar, `diarize.py --speakers N --force`.
- **Upload YouTube**: `videos.insert` resumable (chunks 8MB), `privacyStatus=public` por padrão (revisado 2026-07-08 — este projeto GCP aceita público + `thumbnails.set`; premissa antiga de "locked private" não se aplica; `private`/`unlisted` por clip para exceções). Quota = DOIS contadores separados: **100 uploads/dia** (teto real) e **10k queries/dia** (`videos.insert` 1600, `thumbnails.set` 50); upload não drena as 10k a 1600/un. `daily_upload_limit` por conta em accounts.json (100); excedente fica `queued` por score. Shorts detectado automático (vertical ≤3min).
- **OAuth**: installed-app flow, escopo `youtube.upload`, `credentials.json`/`token.json` em `secrets/youtube/<conta>/`. Modo Testing: refresh token expira em 7 dias.

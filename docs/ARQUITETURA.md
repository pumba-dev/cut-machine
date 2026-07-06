# Arquitetura — social-accounts-agent

Pipeline de cortes virais orquestrado pelo Claude Code. Fluxo:
`download → transcribe → plan → copy → render → qa → publish`

## Princípios

1. **LLM vs determinístico**: subagentes (LLM) fazem seleção de momentos, timestamps finos e copy; scripts Python fazem download, transcrição, ffmpeg, OAuth e upload. LLM nunca toca em tokens/secrets.
2. **Abstração de fonte**: `core/sources/` — `VideoSource` (ABC) com registry por URL. Hoje YouTube; amanhã qualquer plataforma implementa `matches(url)` + `fetch()`.
3. **Abstração de destino**: `core/publishers/` — `Publisher` (ABC) com registry por plataforma. Hoje YouTube; amanhã TikTok/Instagram/Facebook implementam `authenticate()` + `upload()`.
4. **Multi-conta**: `config/accounts.json` registra contas por plataforma; credenciais isoladas em `secrets/<plataforma>/<conta>/`. Publishers recebem a conta resolvida por `core.accounts.get_account(platform, account_id)`.
5. **Estado retomável**: `workspace/<video_id>/state.json` (por fase, via `core.state`) + `clips.json.clips[].status` (por clip). Toda etapa lê estado antes; nunca refaz etapa `done`. Escrita atômica.
6. **Contrato de script**: todo CLI em `scripts/` imprime UMA linha JSON no stdout como último output (`core.cli.emit`), é idempotente e atualiza o estado sozinho. UTF-8 em todo I/O.

## Estrutura

```
CLAUDE.md                      # orquestrador
config/accounts.json           # contas por plataforma
.claude/agents/                # clip-scout, copywriter, qa-reviewer, publisher
.claude/skills/                # setup, produzir, planejar, renderizar, publicar, status
references/                    # heuristicas-virais, formatos-redes, estilo-legendas, youtube-api
core/                          # pacote Python
  paths.py state.py contracts.py media.py accounts.py cli.py
  sources/    base.py youtube.py       # + __init__.py com get_source(url)
  transcribe/ whisper_local.py
  render/     captions.py ffmpeg.py
  publishers/ base.py youtube.py       # + __init__.py com get_publisher(platform)
scripts/                       # CLIs finos sobre o core
workspace/<video_id>/          # gitignored: state.json, source.mp4, source.json,
                               #   source.info.json, transcript*.json, clips.json, clips/
secrets/<plataforma>/<conta>/  # gitignored: credentials.json, token.json, upload_log.json
```

## Interfaces dos CLIs (contrato com CLAUDE.md e skills)

```
python scripts/download.py    --url <URL>
python scripts/transcribe.py  --video-id <id> [--model large-v3] [--device auto|cuda|cpu] [--compute int8]
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
        que download.py grava em workspace/<id>/source.json."""

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

- `clips.json`: ver `core/contracts.py` (FORMAT_RULES, CLIP_STATUSES, validate_plan). Formatos: `short` 15–59s 1080x1920 crop central legendas queimadas; `corte` 120–600s 1920x1080 sem burn. Bloco `publish` de cada clip: `{"platform", "account", "privacy": "private", "category_id": "22", "made_for_kids": false, "remote_id": null, "url": null, "published_at": null}`.
- `transcript.json`: `{"video_id", "language", "model", "duration", "segments": [{"id", "start", "end", "text", "words": [{"w", "start", "end", "prob"}]}]}`. + `transcript.compact.json` (sem `words`, para o clip-scout) + `transcript.srt` (conferência humana).
- `state.json`: ver `core/state.py`.

## Decisões técnicas fixas

- **Whisper**: `WhisperModel("large-v3", device="cuda", compute_type="int8")` — GTX 1660 SUPER: `int8`, nunca fp16 (NaN na série 16xx). Fallback CPU int8 + modelo `small`. `word_timestamps=True, vad_filter=True, beam_size=5`. DLLs CUDA: `os.add_dll_directory(site-packages/nvidia/{cublas,cudnn}/bin)` no Windows.
- **yt-dlp**: formato `bv*[ext=mp4][vcodec^=avc1][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]/b`, merge mp4, writeinfojson, restrictfilenames, noplaylist. Fallback anti-bot: `cookiesfrombrowser`.
- **ffmpeg** (libx264; NVENC futuro): short `-ss <start> -t <dur> -i source.mp4 -vf "scale=-2:1920,crop=1080:1920,ass=<clip>.ass" -r 30 -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart`; corte igual sem vf com `-crf 20`. Rodar com `cwd` na pasta do clip e caminho ASS relativo (escaping Windows). Corte preciso exige re-encode (stream copy gruda em keyframe).
- **ASS**: tempos rebased (`t - clip.start`), Arial Black 110 @ PlayRes 1080x1920, Outline 8, Alignment 2, MarginV 550, 2–4 palavras por evento em CAIXA ALTA, max_gap 0.6s.
- **Upload YouTube**: `videos.insert` resumable (chunks 8MB), sempre `privacyStatus=private` (projeto GCP não-auditado trava uploads como private — política YouTube). Quota: 10k unidades/dia, upload = 1600 → ~6/dia; `daily_upload_limit` por conta em accounts.json; excedente fica `queued` por score. Shorts detectado automático (vertical ≤3min).
- **OAuth**: installed-app flow, escopo `youtube.upload`, `credentials.json`/`token.json` em `secrets/youtube/<conta>/`. Modo Testing: refresh token expira em 7 dias.

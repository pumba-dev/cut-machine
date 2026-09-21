# Pivô: de "só cortes" para "produção com comentários"

> Plano de reprojeto do pipeline após o banimento dos canais por evasão de detecção +
> conteúdo copiado + produção em massa (ver §"Contexto"). Baseado no mapa real do código
> (render/contracts/scripts) e em pesquisa de política do YouTube (2025-2026) + TTS local + mascote.

## Contexto e razão do pivô

Os canais foram encerrados por violar a política de spam/práticas enganosas do YouTube. As causas,
mapeadas nome-por-nome contra a política oficial:

1. **Evasão de detecção** — o bloco `transform` (flip/speed/pitch/eq/noise/música-fingerprint) é
   literalmente o exemplo citado pela política: *"technical manipulation (such as speeding up audio,
   heavy filters, cropping) designed to bypass abuse detection"*.
2. **Conteúdo copiado** — recorte de clipe de terceiro com legenda + moldura + música não cruza a
   barra de transformação: *"significant original commentary, substantive modifications, or
   educational or entertainment value"*.
3. **Produção em massa** — 100 uploads/dia automáticos, template, vídeos intercambiáveis (política
   "inauthentic content", renomeada em 15/07/2025).
4. **Rede coordenada** — 3 canais irmãos, mesmo projeto GCP, cross-link (política nomeia
   *"coordinated networks of channels"*; punição em unidade → os 3 caíram juntos).

**O que este plano resolve:** a camada técnica que torna o produto *transformativo* de verdade
(comentário original é a substância; o clipe vira matéria-prima) e remove os sinais de evasão.

**O que este plano NÃO resolve (pré-requisitos externos ao código, ver §9):** direitos autorais
(Content ID/strike é eixo separado) e a inexistência de um canal legítimo para publicar (canal
banido + auto-alt = circumvention). Construir o pipeline é seguro; **publicar** depende de resolver
esses dois pontos.

---

## 1. Estrutura nova do vídeo

```
[INTRO CARD]   novo    → fundo de marca + card de texto (resumo/gancho) + mascote + voz TTS lendo o resumo
[CORE]         rework  → clipe intercalado com comentário original do host/mascote:
                          - segmentos INSERT (clipe pausa/cutaway; mascote fala; é a substância transformativa)
                          - mascote em OVERLAY reagindo ao longo do clipe (lip-sync + emoção)
                          - (opcional) comentário em OVERLAY de áudio (mascote fala por cima, clipe ducka)
[OUTRO]        mantém  → vinheta de marca (mp4 por conta, já existe)
```

**Removido:** moldura PNG (`brand.short_frame`/`corte_frame`) e a camada `transform` inteira.
**Mantido:** vinheta de encerramento, progress bar (short), legendas queimadas (valor de edição/acessibilidade).

---

## 2. Decisões técnicas fixadas (da pesquisa)

| Tema | Decisão v1 | Por quê | Fonte |
|---|---|---|---|
| **Voz TTS** | **Piper**, voz fixa pt-BR por canal (`faber`/`cadu`/`jeff`) | **CC0** (domínio público, comercial irrestrito — verificado no MODEL_CARD), CPU/0-VRAM (não briga com Whisper/NVENC na 1660), **determinística** (idempotente por clip travando `noise_scale`/`noise_w`), pt-BR clara | huggingface.co/rhasspy/piper-voices |
| **Clonagem de voz** | **Não usar** | A voz é de um **mascote fictício**, não de pessoa real → clonagem é desnecessária e evita a licença NC dos cloners bons (XTTS/F5) | — |
| **Divulgação de IA** | **Não obrigatória** | Personagem claramente fictício/animado + voz não imita pessoa real + footage-fonte não é alterado de forma enganosa | support.google.com/youtube/answer/14328491 |
| **Boca do mascote** | RMS 3-estados (fechada/média/aberta) do wav TTS a ~12-15fps | Determinístico, CPU, sem deps pesadas; padrão PNGtuber; repo já usa RMS em `speaker_track` | — |
| **Emoção do mascote** | **LeIA** (léxico VADER pt-BR) sobre o **texto do comentário**, por frase | Licença permissiva (comercial OK), CPU, determinístico; mapeia polaridade → alegria/tristeza/raiva/surpresa | pypi.org/project/leia-br |
| **Compositing do mascote** | PIL renderiza ~12 frames únicos → **1 overlay alpha** (PNG seq ou VP9 yuva420p) → **1** `overlay=x:y` no canto | `overlay=enable='between(t,...)'` por frame **não escala** (60s@15fps ≈ 900 filtros) | — |

**Alternativas de fallback:** TTS → **Chatterbox** (MIT, clonagem zero-shot, mais expressivo, mas
~5-7GB VRAM aperta a 1660 e default fp16=NaN na série 16xx → forçar fp32/CPU). Emoção → **pysentimiento**
(4 rótulos direto, mais preciso, **mas checar licença do modelo** — muitos datasets são non-commercial).
**Evitar sempre** (monetização): Coqui XTTS-v2 (CPML NC) e F5-TTS-pt-br (CC-BY-NC-4.0); Wav2Lip/SadTalker (foto-realista, VRAM alta, licença de pesquisa).

**Cuidado fp16=NaN série 16xx:** já documentado para o Whisper. Piper (CPU) não é afetado. Se usar
Chatterbox na GPU, forçar fp32 ou CPU.

### 2.1 Voz por canal + regra de moldagem

Catálogo Piper pt-BR tem **3 vozes masculinas distintas, todas CC0** (verificado no MODEL_CARD de cada,
dataset `OHF-Voice/voice-datasets`, 1 locutor cada). Uma por canal, sem treinar/clonar. Chave nova
`brand.tts_voice` por conta:

| canal | `brand.tts_voice` | licença |
|---|---|---|
| **futebol** (piloto) | `pt_BR-faber-medium` | CC0 (comercial irrestrito, sem atribuição) |
| política | `pt_BR-cadu-medium` | CC0 |
| economia | `pt_BR-jeff-medium` | CC0 |

Timbres realmente diferentes (locutores distintos, não pitch-shift). Ordem trocável após ouvir amostras
em rhasspy.github.io/piper-samples. Download: `.../pt/pt_BR/<voz>/medium/pt_BR-<voz>-medium.onnx` (+ `.json`).

> ⚠️ **Regra de moldagem de voz (não reintroduzir evasão):** qualquer ajuste de pitch/EQ para dar
> "caráter" ao mascote aplica-se **SOMENTE à trilha TTS** (áudio sintético de personagem fictício =
> design de voz legítimo). **NUNCA** ao clipe-fonte — alterar o original era a evasão que causou o ban.
> v1 = voz-base limpa, sem moldagem (as 3 vozes já são distintas).

### 2.2 Mascote do futebol (8-bit)

Bola de futebol clássica com rosto expressivo (amarra no logo do canal), paleta midnight `#060B18` /
azul-elétrico `#00A8FF` / ciano `#22D3FF`, pixel art. **Catálogo v1: base (neutro) + 9 emoções + 3 bocas**
(alegria, euforia, tristeza, raiva, surpresa, deboche, duvida, desprezo, medo) compostos em PIL → 1 overlay
alpha (o compositing não cresce com o nº de emoções, só a arte). Prompts em `design.prompts` do futebol
(`mascot_base`, `mascot_<emoção>`, `mascot_boca_{fechada,media,aberta}`). Assets em `brand.mascot_dir`
→ `assets/mascot/futebol/`.

**Driver da emoção:** o `commentary-writer` emite `commentary[].emotion` de um **enum fixo** por segmento
(preciso, dirigido pelo conteúdo real, determinístico na saída). `leia-br` (valência) = fallback quando o
campo faltar. **Nunca** aleatório — a variedade vem do conteúdo, não de embaralhar assets.

**Movimento (v2):** piscar, respiração/bob, loops de 2-4 frames por emoção, transições — mesma pipeline
PIL→overlay, custo só de arte.

---

## 3. Máquina de estados: nova fase `commentary`

`core/state.py` `STAGES` (L19-20) — inserir entre `copy` e `render`:

```
download → transcribe → faces* → speaker-track* → plan → copy → commentary* → render → qa → publish
```

`*` = opt-in por conta (conta sem bloco `commentary`/`mascot` pula, como `faces`/`speaker-track`).
`new_state()`/`set_stage()` derivam de `STAGES` — não mudam. **Espelhar a ordem** em: `CLAUDE.md` §2,
`.claude/skills/produzir/SKILL.md` (L13), `/planejar`, `/renderizar`, e a `/status` (lê os nomes).

---

## 4. Contrato `clips.json`: campos novos (aditivos, não quebram)

Novo dono: **commentary-writer**. Declarar na docstring de `core/contracts.py` (L1-11) e no `CLAUDE.md` §4/§6.

```jsonc
{
  // ... campos existentes (clip-scout, copywriter) ...
  "intro_summary": {                 // dono: commentary-writer
    "script": "texto do gancho/resumo que a voz lê na abertura",
    "on_screen": "texto curto exibido no card (pode = script encurtado)"
  },
  "commentary": [                    // dono: commentary-writer
    {
      "anchor_ts": 1234.5,           // ponto dentro de [start,end] onde o comentário entra
      "mode": "insert",              // "insert" (pausa+fala, estende duração) | "overlay" (fala por cima)
      "text": "análise/opinião original do host sobre este trecho",
      "emotion": null                // opcional; senão derivado do texto por LeIA em tempo de render
    }
  ]
}
```

- **Placeholders** `intro_summary: null` e `commentary: []` entram no **template do clip-scout**
  (`.claude/agents/clip-scout.md` L69-101), ao lado de `title:null`/`tags:[]`, para manter
  "nenhum dado de clip vive fora do clips.json".
- `validate_plan()`/`_copy_errors()` **ignoram** campos desconhecidos → aditivo por construção
  (mesmo status do `thumbnail_plan` hoje). Avisos não-bloqueantes opcionais em novo `_commentary_warnings()`.

Campos novos de `render.*` (dono: `render_clip.py`, gravados a partir do retorno de `core/render/ffmpeg.py::render_clip`):
`render.intro_summary_duration_s`, `render.commentary_added_s`, `render.tts_provider`, `render.mascot` (bool/summary).

---

## 5. Fases de implementação

### Fase 0 — Refactor de desmonte (pré-requisito; **não muda o output** das contas clássicas)

**Objetivo:** remover moldura + transform sem quebrar música/áudio/reframe.

> ⚠️ **Entrave crítico:** `seed_for` (L101), `pick_music` (L379), `build_audio_graph` (L316, o duck
> sidechain) e `MUSIC_ROOT` **vivem dentro de `transform.py`** e são usados por reframe (espelho),
> sfx, música e futuramente pelo TTS. "Remover transform" **não pode** ser delete do arquivo.

1. **Extrair** para um módulo-guardião `core/render/audio.py` (+ `core/render/seed.py`):
   `seed_for`, `pick_music`, `build_audio_graph`, `MUSIC_ROOT`. Atualizar imports em `ffmpeg.py`,
   `reframe.py`, `sfx.py`.
2. **Remover filtros de vídeo do transform** em `core/render/ffmpeg.py`: `resolve_transform` (L246),
   bloco `vcfg/speed/vfx` (L295-323), `transform_summary` (L513-515), imports (L39-48). Deletar
   `core/render/transform.py` (partes de vídeo). O ajuste `/speed` dos `crop_segments` (L307-323)
   vira no-op.
3. **Remover moldura PNG:**
   - `core/render/short_frame.py::build_short_filter` L104-109 (ramo `has_png`).
   - `core/render/corte_frame.py::build_corte_frame_filter` L71-76.
   - Inputs em `build_short_cmd` (L118-127) / `build_corte_cmd` (L179-188): remover `-loop 1 -i frame_png`.
   - `_resolve_frame_png(brand.short_frame/corte_frame)` em `ffmpeg.py` L375/L386. **Manter** a
     resolução do outro (`_resolve_frame_png(brand[f'{fmt}_outro'])` L501).
   - Decisão do corte sem PNG: cair em crop-to-fill puro (recomendado) **ou** manter a moldura gerada
     (`branding.build_corte_filter`). Recomendo **crop-to-fill puro** (sem moldura).
4. **Config `config/accounts.json`** (todas as 3 contas):
   - Deletar `brand.short_frame`, `brand.corte_frame`. **Manter** `short_outro`/`corte_outro`/`accent_color`.
   - Deletar o bloco `transform` inteiro. **Migrar** `music`/`music_volume`/`music_lufs` para um novo
     bloco `audio` (ou `brand.music`) — a música é produção legítima (pool livre de claim), só não
     mora mais dentro de `transform`. (Ou dropar música no v1 para simplificar.)
   - Deletar o bloco `reframe`? **Não** — reframe (recompor o quadro no falante) é edição legítima e
     ajuda a transformação. Manter opt-in. (Só o `transform` é evasão.)
5. **Assets:** `assets/short-frame/*`, `assets/corte-frame/*` ficam órfãos (deletar depois). `short-end/`,
   `corte-end/` (outro) e `music/` ficam.
6. **Verificar:** renderizar 1 short + 1 corte de teste; confirmar mp4 válido (resolução/duração/áudio),
   sem moldura, sem alteração de velocidade/pitch/flip.

### Fase 1 — TTS determinístico (novo script + módulo)

**Objetivo:** sintetizar áudio de voz do mascote, idempotente por clip.

1. `core/render/tts.py`: wrapper Piper (invoca binário/modelo em `models/tts/`, resample 48k estéreo,
   saída wav determinística). Voz por conta via nova chave `brand.tts_voice` (default `pt_BR-faber-medium`).
2. `scripts/synthesize_commentary.py` (modelado em `scripts/analyze_faces.py`): lê `clips.json`
   (`intro_summary.script` + cada `commentary[].text`), sintetiza wavs em
   `video-output/<id>/<clip_id>/tts/{intro.wav, c00.wav, ...}`, **idempotente** (`{"ok":true,"skipped":true}`
   se já existem), imprime **1 linha JSON**, atualiza `state.json` stage `commentary`. Degrada com
   segurança (sem modelo → stage `done` com aviso, render cai sem voz? **não** — se a conta é opt-in
   de comentário, sem TTS o vídeo perde a substância → tratar como `failed` da fase, não silencioso).
3. `core/paths.py`: helpers `clip_tts_dir()`, `clip_tts_path(clip_id, key)`. Artefato derivado →
   apagado no cleanup como `faces.json`/`speaker_track.json`.

### Fase 2 — Agente `commentary-writer` (a substância transformativa)

**Objetivo:** gerar o comentário **original** — é aqui que mora o valor que satisfaz a política.

1. `.claude/agents/commentary-writer.md` (frontmatter `tools: Read, Edit`; edita **só** `clips.json`;
   idempotente por presença; responde resumo de 1 linha por clip). Modelo: `copywriter.md`.
2. Entrada no prompt: `video_id`, `account_id` (**obrigatório**), workspace, e o clip com
   `hook`/`payoff`/`rationale`/`dominant_signal` + a copy já escrita + trecho do transcript.
3. Saída: `intro_summary` + `commentary[]` com **análise genuína** (tese, contexto, opinião, crítica,
   previsão) — não resumo do que a pessoa disse. **Regra editorial:** o clipe é a minoria; o
   comentário é a substância primária. Cada vídeo com ângulo próprio (não template).
4. Orquestração: `/produzir` spawna o agente após `copy`, antes de `render`; marca a stage
   `commentary` `done` via `python -c core.state` (subagentes não tocam `state.json`).

### Fase 3 — Intro card narrado (render)

**Objetivo:** abertura = card de texto + mascote + voz TTS lendo o gancho.

1. Reprojetar `core/render/intro.py`: hoje `_build_intro_segment` (L38-74) encoda a thumb congelada
   com áudio silencioso (`anullsrc`). Trocar por: fundo de marca (cor `accent_color`/arte) +
   `drawtext`/ASS com `intro_summary.on_screen` + overlay do mascote + **áudio = `intro.wav`**
   (aresample 48k estéreo). `dur` = duração do TTS. Prepend via `concat_copy` (ou `_prepend_intro_reencode`).
2. `render.intro_summary_duration_s`. Somar em `contracts.expected_output_duration` (L124-146).
3. Gate: opt-in por conta (bloco `commentary`/`mascot`). Substitui a intro-thumb de ~0.1s atual.

### Fase 4 — Comentário intercalado (core rework)

**Objetivo:** intercalar segmentos de fala do host no meio do clipe.

1. **Modo INSERT** (recomendado como principal): renderizar o conteúdo em pedaços cortados nos
   `anchor_ts` e montar `[pedaço0, host_seg0, pedaço1, host_seg1, ...]`. Usar o padrão concat-filter
   re-encode de `outro._append_outro_reencode` (`outro.py` L115-172) — segmentos compostos de formas
   diferentes. `host_seg` = mesmo molde do intro card (fundo + mascote + TTS + texto), mid-roll.
2. **Modo OVERLAY** (opcional): TTS mixado por cima do clipe em `core/render/ffmpeg.py::_audio_for`
   (L342-364), com **duck** do áudio do clipe sob a voz via `sidechaincompress` (reusar
   `build_audio_graph`, sidechain = TTS). Não estende duração.
3. **Legendas:** os inserts deslocam o tempo como o jump-cut já faz → remapear via
   `core/render/timemap.py::TimeMap` (o mesmo caminho que `captions.build_ass` já usa).
4. `render.commentary_added_s`. Somar em `contracts.expected_output_duration`.
5. **Interação com jump-cut/reframe:** os `anchor_ts` de insert entram como novos pontos de corte na
   composição de pedaços (`reframe.compose_with_keep_ranges` L671 / `frame_common.build_video_stage`).

### Fase 5 — Mascote animado (overlay)

**Objetivo:** mascote no canto, reagindo (emoção) + lip-sync com o TTS.

1. **Assets:** `assets/mascot/<account>/{alegria,tristeza,raiva,surpresa}.png` (corpos) +
   `boca_{fechada,media,aberta}.png` (transparentes). Resolver via nova chave `brand.mascot_dir`.
2. `core/render/mascot.py`:
   - **Emoção** por segmento: `leia-br` sobre `commentary[].text` → polaridade → sprite
     (positivo→alegria; negativo forte→raiva; negativo leve→tristeza; `?!`/marcadores→surpresa).
     Determinístico. (Ou usar `commentary[].emotion` se preenchido.)
   - **Boca**: RMS por janela do wav TTS (numpy/librosa) a ~12-15fps, normaliza, threshold 3-estados.
   - **Compositing**: PIL compõe os ~12 frames únicos (emoção × boca, cache) → escreve overlay alpha
     (PNG sequence `-framerate N` **ou** VP9 yuva420p) → **1** `overlay=x:y` no canto, no mesmo ponto
     onde a moldura PNG entrava (`short_frame`/`corte_frame`). Determinístico, CPU, segundos.
3. Gate opt-in. Novas deps: `piper-tts`, `numpy`/`librosa`, `Pillow`, `leia-br` (adicionar ao `/setup`).
4. `render.mascot` summary.

### Fase 6 — QA, duração e docs

1. `core/contracts.py::expected_output_duration` (L124-146): somar `intro_summary_duration_s` +
   `commentary_added_s` (aditivo, ausente→0). Propaga automático para `scripts/qa_backfill.py` (L83) e
   qa-reviewer. **Tolerância é ±0.5s** — qualquer extra não contabilizado reprova.
2. **Presença de rosto**: `qa_backfill.py::_face_check` (L42-61) e o qa-reviewer usam a janela
   `[intro_duration_s, dur-outro_duration_s]`. Ajustar para **excluir** o card de intro e os segmentos
   de comentário `insert` (frames só-mascote/só-card não têm rosto humano → derrubariam o clip).
3. Atualizar `.claude/agents/qa-reviewer.md` (texto dos componentes de duração + janela de rosto).
4. **Docs a sincronizar:** `CLAUDE.md` (§2 diagrama+estados, §3 tabela LLM/deterministico, §4 donos,
   §6 subagentes, §7 skills), `docs/ARQUITETURA.md`, `docs/PLAN.md`, e cada `SKILL.md`.

---

## 6. Ordem de execução sugerida

```
Fase 0 (desmonte)  →  Fase 1 (TTS)  →  Fase 2 (agente)  →  Fase 3 (intro card)
                                                              →  Fase 4 (intercalado)
                                                              →  Fase 5 (mascote)  →  Fase 6 (QA+docs)
```

Fase 0 é independente e entregável sozinha (remove evasão já). Fases 3/4/5 dependem de 1+2. Cada fase
mantém o pipeline rodável (contas clássicas degradam para o comportamento sem-comentário).

---

## 7. Invariantes a preservar (do mapa do código)

- **Concat exige uniformidade**: todo segmento colado (intro card, host_seg, outro) precisa casar
  `pix_fmt`/`SAR`/timebase/codec + áudio 48k estéreo AAC + `-r 30` (o concat demuxer recusa divergência).
- **Determinismo por clip**: manter `seed_for(clip_id)` em qualquer passo novo (re-render idempotente).
- **Contrato de script**: `synthesize_commentary.py` segue `core/cli.py::emit` (1 linha JSON) +
  auto-update do `state.json` + idempotência.
- **Filtergraph grande** cai em `-filter_complex_script` (`ffmpeg.py` L55) — respeitar no overlay do mascote.
- **Encoder é da máquina**: reusar `encoder.resolve_encoder`/`video_codec_args` (fallback NVENC→libx264)
  em todo passo de encode novo.
- **Duas duplicações de estado** a manter em sincronia: (1) `STAGES` em `core/state.py` × ordem no
  `CLAUDE.md`/`SKILL.md`; (2) dono-por-campo em `contracts.py` docstring × `CLAUDE.md`.

---

## 8. Impacto na compliance (por que isto resolve as violações)

| Violação original | O que o plano faz |
|---|---|
| Evasão de detecção (`transform`) | **Removida** (Fase 0). Fim do flip/speed/pitch/música-fingerprint. |
| Conteúdo copiado | **Comentário original** é a substância (Fase 2/4); clipe vira minoria. Cruza a barra "significant original commentary". |
| Produção em massa | Volume menor + humano no loop + variação editorial por vídeo (não template). |
| Rede coordenada | Fora do código — decisão operacional (§9). |

---

## 9. Pré-requisitos EXTERNOS ao código (bloqueiam publicar, não construir)

1. **Direitos autorais (eixo separado do spam):** mesmo transformativo, reusar clipe de terceiro
   dispara **Content ID** (receita vai pro dono) e risco de **copyright strike** (3/90 dias = encerra).
   Resolver com: licença/permissão da fonte **ou** clipe curto + comentário primário (fair-use
   defensável). Transformar **não** bloqueia Content ID.
2. **Canal legítimo:** os 3 canais estão banidos. Auto-criar canal novo = **circumvention** (cascata
   de re-ban, inclui canais onde o operador aparece). Vias legítimas: **appeal** (YouTube Studio, até
   1 ano — chance baixa dada a violação clara) ou **Second Chances** (pedir canal novo 1 ano após o
   ban). **Construir o pipeline agora é seguro; publicar espera um canal legítimo.**

---

## 10. Novas dependências (adicionar ao `/setup`)

`piper-tts` + modelo `pt_BR-faber-medium` (→ `models/tts/`) · `numpy`/`librosa` (RMS) · `Pillow` (compositing) · `leia-br` (emoção).
Todas CPU, licenças permissivas. Nenhuma disputa a VRAM da 1660.

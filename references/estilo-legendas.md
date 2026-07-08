# Estilo de Legendas Queimadas

Spec do arquivo ASS gerado por `core/render/captions.py` e queimado no vídeo pelo filtro `ass=` do ffmpeg (build com libass). As **legendas word-level** (este topo) aplicam-se **só ao formato `short`** — o `corte` (16:9) não leva legenda de fala. O `corte` tem, porém, um **texto de marca fixo** na moldura (seção "Texto de marca do corte") e ambos os formatos têm **texto de miniatura** (seção "Texto da miniatura"), gerados por `branding.py`/`thumbnail.py` com a mesma técnica ASS.

## Estilo ASS exato

```
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Arial Black,110,&H00FFFFFF,&H0000FFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,8,0,2,60,60,550,1
Style: Cap0,Arial Black,110,&H00FFFFFF,...   # branco  (falante 0 = quem mais fala)
Style: Cap1,Arial Black,110,&H003DD9FF,...   # amarelo (falante 1)
Style: Cap2,Arial Black,110,&H00FFCC66,...   # azul-claro (falante 2)
Style: Cap3,Arial Black,110,&H0090EE90,...   # verde-claro (falante 3)
Style: Cap4,Arial Black,110,&H0000A5FF,...   # laranja (falante 4)
```

`Cap` (branco) é o estilo-base/fallback; `Cap0..Cap4` são idênticos a ele exceto pela `PrimaryColour`. Decodificação do estilo `Cap`:

| Parâmetro | Valor | Por quê |
|---|---|---|
| Fontname / Fontsize | Arial Black, 110 | fonte nativa do Windows 11, peso máximo; 110 é relativo ao PlayRes 1080x1920 |
| PrimaryColour | `&H00FFFFFF` | texto branco opaco |
| OutlineColour + Outline | `&H00000000`, 8 | contorno preto grosso — legível sobre qualquer fundo |
| BackColour | `&H96000000` | preto semi-transparente (alpha 0x96) atrás do texto |
| Bold | -1 | negrito ativado |
| BorderStyle / Shadow | 1 / 0 | borda por outline, sem sombra deslocada |
| Alignment | 2 | baixo-centro |
| MarginL / MarginR / MarginV | 60 / 60 / 550 | bloco no centro-baixo do frame, acima da UI do Shorts |

## Cor por falante

A diarização (`core/diarize.py`, sherpa-onnx) grava um índice de falante `spk` em cada palavra do `transcript.json` (0 = quem mais fala). Cada evento `Dialogue` usa o estilo `Cap<spk>`, dando **uma cor por pessoa** — ajuda o espectador a acompanhar quem fala num corte de podcast/entrevista.

| spk | Cor | `PrimaryColour` (`&HAABBGGRR`, BGR!) |
|---|---|---|
| 0 (principal) | branco `#FFFFFF` | `&H00FFFFFF` |
| 1 | amarelo `#FFD93D` | `&H003DD9FF` |
| 2 | azul-claro `#66CCFF` | `&H00FFCC66` |
| 3 | verde-claro `#90EE90` | `&H0090EE90` |
| 4 | laranja `#FFA500` | `&H0000A5FF` |

Regras (fonte: `SPEAKER_COLOURS` em `captions.py`):

- Cores claras de alta luminância sobre o outline preto; **nunca** distinguir dois falantes por vermelho-vs-verde (daltonismo), nem usar vermelho/azul puro (some no contorno preto).
- Ordem = prioridade: o falante que mais fala fica branco (mais neutro/legível). Mais de 5 falantes: as cores ciclam (`spk % 5`) — raro em corte de talking-head.
- Um evento **nunca** mistura falantes: o agrupamento quebra na troca de `spk` além de quebrar por `max_words`/`max_gap`.
- Transcript **sem** diarização (`spk` ausente): tudo cai no estilo branco `Cap` — retrocompatível com clips antigos.
- `ScaledBorderAndShadow: yes` faz o outline escalar com o PlayRes. **Nunca** passar `force_style` no filtro `ass=`/`subtitles=` do ffmpeg: ele sobrescreve todos os estilos e destrói as cores por falante.

## Eventos (Dialogue)

- **2–4 palavras por evento** (agrupamento padrão: 3), texto em **CAIXA ALTA**.
- Agrupamento quebra quando o gap entre palavras consecutivas excede **0.6s** (`max_gap`) — pausas longas ficam sem legenda na tela, o que preserva o efeito dramático.
- **Tempos SEMPRE rebased ao início do clip**: `t_ass = t_transcript - clip.start`. Motivo: o ffmpeg corta com `-ss` antes de `-i`, então o vídeo de saída começa em t=0; usar tempos absolutos da transcrição dessincroniza tudo.
- Fim do último evento limitado a `clip.end` (também rebased).
- Formato de tempo ASS: `H:MM:SS.cc` (centésimos de segundo).
- Timestamps vêm de `transcript.json` (`segments[].words[]`, gerados com `word_timestamps=True` no faster-whisper); a cor vem do `spk` da mesma palavra (ver "Cor por falante").

Exemplo de evento (falante 1 = amarelo):

```
Dialogue: 0,0:00:00.12,0:00:00.88,Cap1,,0,0,0,,ISSO MUDA TUDO
```

## Texto de marca do corte (`branding.py`)

Diferente das legendas: aplica-se **só ao formato `corte`** (16:9) e é um texto
**fixo e estático** queimado na faixa inferior da moldura de marca (não vem da
transcrição). Gerado por `core/render/branding.py` → `<clip_id>.border.ass`.

- **PlayRes 1920x1080** (não 1080x1920 — canvas do corte). Style próprio `Brand`:
  Arial Black, ~54px, cor de **acento** da conta (default amarelo `#FFD93D`),
  Outline 4 preto, `Alignment 2` (baixo-centro), `MarginV 18` (cai na faixa preta).
- **Um único `Dialogue`** cobrindo o clip inteiro (`0:00:00.00` → `9:59:59.99`).
- Texto default `"Curta e se inscreva no canal"`, configurável por conta em
  `config/accounts.json` (`brand.border_text`).
- A moldura em si (fundo preto + rim amarelo + faixa) é `filter_complex` do
  ffmpeg (`build_corte_filter`), não ASS — o ASS só desenha o texto por cima.

## Texto da miniatura (`thumbnail.py`)

Frases queimadas na miniatura (short e corte), geradas por
`core/render/thumbnail.py` → `<clip_id>.thumb.ass`. Fonte do texto:
`thumbnail_text` do copywriter (fallback `hook_text`/`title`).

- **PlayRes = resolução da thumb** (corte 1280x720, short 1080x1920). Style
  `Thumb`: Arial Black branco, Outline grosso preto (5 corte / 7 short),
  `Alignment 8` (topo-centro) para deixar a cena visível embaixo.
- **Um `Dialogue`** com override inline: `impact` grande na cor de acento
  (`\fs<big>\1c&H3DD9FF&\b1`) + `\N` + `hooks` menores em branco
  (`\fs<small>\1c&HFFFFFF&`), ganchos separados por `\N`.
- Tamanhos por formato em `_FONT_SIZES` (corte impact 76/hook 44; short 120/68).
- Caracteres `{`/`}`/`\` do texto são neutralizados antes de entrar no override.

## Racional

- **Retenção:** boa parte do consumo de Shorts começa sem som; legenda grande palavra-a-palavra segura o espectador nos 3 primeiros segundos (janela onde ocorre 50–60% do drop-off) e reforça o hook.
- **Legibilidade:** CAIXA ALTA + Arial Black + outline 8 + fundo semi-transparente garantem leitura em tela pequena sobre fundo imprevisível.
- **Zona segura:** `MarginV 550` mantém o texto fora dos ~25% inferiores do frame, que a UI do Shorts (título, canal, botões) cobre — ver `references/formatos-redes.md`. Como o vídeo original não é cropado (fundo blur preenche as laterais/topo/base), a margem também evita que a legenda caia sobre a faixa de fundo em vez do vídeo.
- **Ritmo:** blocos de 2–4 palavras acompanham a cadência da fala; blocos maiores viram "parede de texto", perdem sincronia e cobrem o frame.

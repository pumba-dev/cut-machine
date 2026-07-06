# Estilo de Legendas Queimadas

Spec do arquivo ASS gerado por `core/render/captions.py` e queimado no vídeo pelo filtro `ass=` do ffmpeg (build com libass). Aplica-se **somente ao formato `short`** — o formato `corte` (16:9) não leva legenda queimada.

## Estilo ASS exato

```
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Arial Black,110,&H00FFFFFF,&H0000FFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,8,0,2,60,60,550,1
```

Decodificação do estilo `Cap`:

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

## Eventos (Dialogue)

- **2–4 palavras por evento** (agrupamento padrão: 3), texto em **CAIXA ALTA**.
- Agrupamento quebra quando o gap entre palavras consecutivas excede **0.6s** (`max_gap`) — pausas longas ficam sem legenda na tela, o que preserva o efeito dramático.
- **Tempos SEMPRE rebased ao início do clip**: `t_ass = t_transcript - clip.start`. Motivo: o ffmpeg corta com `-ss` antes de `-i`, então o vídeo de saída começa em t=0; usar tempos absolutos da transcrição dessincroniza tudo.
- Fim do último evento limitado a `clip.end` (também rebased).
- Formato de tempo ASS: `H:MM:SS.cc` (centésimos de segundo).
- Timestamps vêm de `transcript.json` (`segments[].words[]`, gerados com `word_timestamps=True` no faster-whisper).

Exemplo de evento:

```
Dialogue: 0,0:00:00.12,0:00:00.88,Cap,,0,0,0,,ISSO MUDA TUDO
```

## Racional

- **Retenção:** boa parte do consumo de Shorts começa sem som; legenda grande palavra-a-palavra segura o espectador nos 3 primeiros segundos (janela onde ocorre 50–60% do drop-off) e reforça o hook.
- **Legibilidade:** CAIXA ALTA + Arial Black + outline 8 + fundo semi-transparente garantem leitura em tela pequena sobre fundo imprevisível.
- **Zona segura:** `MarginV 550` mantém o texto fora dos ~25% inferiores do frame, que a UI do Shorts (título, canal, botões) cobre — ver `references/formatos-redes.md`. Também evita cobrir o rosto no crop central típico de talking-head.
- **Ritmo:** blocos de 2–4 palavras acompanham a cadência da fala; blocos maiores viram "parede de texto", perdem sincronia e cobrem o frame.

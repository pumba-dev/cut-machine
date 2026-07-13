# Música de fundo — pool compartilhado (todas as contas)

Faixas `.mp3` / `.m4a` / `.wav` / `.ogg` / `.flac`, organizadas por clima:

```
assets/music/
  agressiva/   energia alta, percussivo, brilhante (rock, eletrônico, trap...)
  neutra/      meio-termo / ambíguo (default seguro)
  calma/       baixa energia, textura quente/suave (lo-fi, ambiente...)
```

**OBRIGATÓRIO: faixas livres de claim** (YouTube Audio Library, Epidemic Sound
licenciado, etc.). Música com copyright faz o Content ID passar a reclamar a
**própria trilha** — troca um problema por outro.

## Como adicionar uma faixa nova

1. Solte o arquivo direto em `assets/music/` (raiz, sem subpasta).
2. Rode `python scripts/classify_music.py` — analisa o áudio de verdade
   (RMS, zero-crossing rate, centróide espectral, proxy de tempo/batida) e
   move a faixa pra `agressiva/`/`neutra/`/`calma/`. Veja o relatório em
   `_classify_report.md` pra conferir onde ela caiu; mova à mão entre pastas
   se discordar — o script nunca reclassifica uma faixa que já está numa
   pasta de clima.
3. `_classify_stats.json` guarda a distribuição de referência do corpus
   (evita que faixas novas reembaralhem o bucket das antigas). Use
   `--force` só se quiser recomputar tudo do zero.

## Como o render escolhe

- O clima usado num clipe é **derivado do conteúdo** em tempo de render
  (`core/render/music_mood.py::derive_mood` — determinístico, sem LLM: combina
  `dominant_signal` do clip-scout, ritmo de fala e palavras-chave do
  hook/copy), não configurado por conta.
- Dentro do clima escolhido, a faixa é sorteada **deterministicamente** por
  clip (seed = `clip_id`): mesmo clip → mesma faixa sempre; clips diferentes
  → faixas variadas.
- A música entra **baixa** (`transform.music_volume` da conta) e **abaixa
  ainda mais quando alguém fala** (duck reverso por sidechain) — a voz do
  vídeo original é sempre prioridade.
- **`transform.music: false`** (ou bloco `transform` ausente) desliga música
  pra aquela conta, sem erro. Pasta de um clima vazia cai em cascata pra
  `neutra`, depois pra qualquer faixa disponível, depois desliga — nunca
  quebra o render.
